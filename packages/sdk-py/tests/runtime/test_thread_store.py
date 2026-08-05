"""``ThreadStorePort`` — o contrato de conversa (spec-conversa-como-dado-do-dna,
fatia 1), exercitado como KIT: as mesmas asserções rodam contra a implementação
de referência em memória e contra a projeção de leitura do LangGraph.

O kit é o ponto. Duas implementações da mesma porta divergem em silêncio — foi
assim que cada face (console, REST) acabou com a sua própria leitura de
transcript. Aqui a divergência falha em CI.

O que este arquivo mede, em ordem de importância:

1. **posse fail-closed** — a regra é UMA (:func:`can_read_thread`), e indexar/
   importar sobre thread alheio levanta ANTES de escrever;
2. **transcript AG-UI pelo conversor OFICIAL** — o adapter roda mensagens
   LangChain de verdade pelo ``langchain_messages_to_agui`` do bridge, não por
   uma tradução nossa;
3. **zero escrita na leitura** — o grafo dublê registra toda chamada e o teste
   afirma que só houve ``aget_state``;
4. **a honestidade do export** — um run pendente NÃO atravessa, e o envelope diz.
"""
from __future__ import annotations

import pytest

from dna.runtime.thread_store import (
    TRANSCRIPT_FORMAT,
    InMemoryThreadStore,
    ThreadIndexPort,
    ThreadOwnershipError,
    ThreadRetention,
    ThreadStorePort,
    ThreadTranscriptPort,
    Transcript,
    can_read_thread,
    derive_title,
    resolve_conversation,
    retention_cutoff,
)


# ── as decisões puras (sem banco, sem grafo) ────────────────────────────


@pytest.mark.parametrize(
    "owner,requester,esperado",
    [
        ("oid-1", "oid-1", True),
        ("oid-1", "oid-2", False),   # thread de outro
        (None, "oid-1", False),      # thread não indexado — nunca vaza
        ("oid-1", None, False),      # pedido sem identidade
        ("oid-1", "", False),
    ],
)
def test_posse_e_fail_closed_em_todo_eixo(owner, requester, esperado):
    assert can_read_thread(owner, requester) is esperado


def test_titulo_vem_do_primeiro_turno_humano():
    """Uma conversa é nomeada por como ABRIU. O primeiro humano vence, o
    assistente antes dele não conta, e a quebra de linha vira espaço."""
    assert (
        derive_title(
            [
                {"role": "assistant", "content": "Olá!"},
                {"role": "user", "content": "quero  entender\na retenção"},
                {"role": "user", "content": "e depois isso"},
            ]
        )
        == "quero entender a retenção"
    )


def test_titulo_trunca_e_e_nulo_sem_humano():
    from dna.runtime.thread_store import TITLE_MAX

    longo = derive_title([{"role": "user", "content": "x" * 300}])
    assert longo is not None and len(longo) == TITLE_MAX and longo.endswith("…")
    assert derive_title([{"role": "assistant", "content": "só eu falei"}]) is None
    assert derive_title([]) is None


def test_titulo_le_conteudo_multimodal_e_objeto_de_framework():
    """A mensagem chega em duas formas (dict AG-UI no gate, objeto do framework
    no grafo) e o conteúdo pode ser lista de partes. Ler só a forma fácil daria
    título nulo justamente na conversa com anexo."""
    from langchain_core.messages import HumanMessage

    assert (
        derive_title([{"role": "user", "content": [{"type": "text", "text": "com anexo"}]}])
        == "com anexo"
    )
    assert derive_title([HumanMessage(content="do framework")]) == "do framework"


def test_resolve_conversation_le_o_slot_e_a_retencao():
    binding = resolve_conversation(
        {
            "checkpoint": {"backend": "postgres", "ref": "primary-pg"},
            "conversation": {
                "backend": "postgres",
                "ref": "primary-pg",
                "retention": {"max_age_days": 30},
            },
        }
    )
    assert binding is not None
    assert (binding.backend, binding.ref) == ("postgres", "primary-pg")
    assert binding.retention == ThreadRetention(max_age_days=30)


def test_sem_slot_declarado_nao_ha_contrato_de_conversa():
    """O copiloto de HOJE — só checkpoint — continua sem porta. Presença é a
    decisão; ausência é o comportamento atual, intacto."""
    assert resolve_conversation(None) is None
    assert resolve_conversation({}) is None
    assert resolve_conversation({"checkpoint": {"backend": "postgres"}}) is None


def test_retencao_declarada_vira_uma_conta_so():
    from datetime import datetime, timezone

    agora = datetime(2026, 8, 5, tzinfo=timezone.utc)
    corte = retention_cutoff(ThreadRetention(max_age_days=30), now=agora)
    assert corte is not None and (agora - corte).days == 30
    # Sem retenção declarada não há corte — guardar para sempre é o default.
    assert retention_cutoff(None, now=agora) is None
    assert retention_cutoff(ThreadRetention(), now=agora) is None


# ── as camadas do contrato ──────────────────────────────────────────────


def test_as_camadas_dizem_o_que_cada_um_consegue_prometer():
    """A razão de existirem TRÊS Protocols: um adapter de leitura sobre o
    checkpoint não sabe de quem é a conversa, e o tipo tem de dizer isso."""
    from dna.runtime.adapters.langgraph_threads import LangGraphTranscriptStore

    memoria = InMemoryThreadStore()
    leitor = LangGraphTranscriptStore(graph=object())

    assert isinstance(memoria, ThreadStorePort)
    assert isinstance(memoria, ThreadIndexPort)
    assert isinstance(memoria, ThreadTranscriptPort)

    assert isinstance(leitor, ThreadTranscriptPort)
    # E NÃO a porta inteira — sem índice, sem posse, sem import.
    assert not isinstance(leitor, ThreadIndexPort)
    assert not isinstance(leitor, ThreadStorePort)


# ── o índice: posse, título e "de onde nasceu" ──────────────────────────


@pytest.mark.asyncio
async def test_indice_registra_lista_e_filtra_pelo_dono():
    store = InMemoryThreadStore()
    await store.index_thread(
        owner="oid-1",
        thread_id="t1",
        workspace="ws",
        messages=[{"role": "user", "content": "primeira"}],
        copilot="memory-copilot",
        surface="memory-composer",
    )
    await store.index_thread(
        owner="oid-1", thread_id="t2", workspace="ws", messages=[], copilot="outro"
    )
    await store.index_thread(owner="oid-2", thread_id="t3", workspace="ws")

    minhas = await store.fetch_threads(owner="oid-1", workspace="ws")
    assert {t.thread_id for t in minhas} == {"t1", "t2"}
    # O filtro por copiloto COMPÕE com o dono, nunca o substitui.
    so_um = await store.fetch_threads(owner="oid-1", copilot="memory-copilot")
    assert [t.thread_id for t in so_um] == ["t1"]
    assert so_um[0].title == "primeira"
    assert so_um[0].surface == "memory-composer"
    # Sem dono, nada — jamais "todas".
    assert await store.fetch_threads(owner="") == []


@pytest.mark.asyncio
async def test_indice_nao_grava_conversa_sem_dono():
    """Fail-closed na entrada: sem oid ou sem thread_id não se indexa nada. Uma
    linha sem dono não é listável por ninguém e não deve existir."""
    store = InMemoryThreadStore()
    assert await store.index_thread(owner=None, thread_id="t1") is None
    assert await store.index_thread(owner="oid-1", thread_id=None) is None
    assert await store.fetch_threads(owner="oid-1") == []


@pytest.mark.asyncio
async def test_thread_de_outro_dono_e_recusado_antes_de_qualquer_escrita():
    """O buraco que isto fecha: o checkpoint é chaveado só por thread_id, então
    um id chutado continuaria a conversa de outra pessoa."""
    store = InMemoryThreadStore()
    await store.index_thread(owner="oid-1", thread_id="t1", messages=[])
    with pytest.raises(ThreadOwnershipError):
        await store.index_thread(owner="invasor", thread_id="t1", messages=[])
    # E a linha do dono legítimo continua intacta.
    assert await store.thread_owner("t1") == "oid-1"


@pytest.mark.asyncio
async def test_titulo_e_origem_nao_se_reescrevem_a_cada_turno():
    """COALESCE do primeiro valor: um item de lista cujo título muda sozinho é
    um item que ninguém reencontra."""
    store = InMemoryThreadStore()
    await store.index_thread(
        owner="oid-1",
        thread_id="t1",
        messages=[{"role": "user", "content": "abriu assim"}],
        copilot="memory-copilot",
        surface="memory-composer",
    )
    await store.index_thread(
        owner="oid-1",
        thread_id="t1",
        messages=[
            {"role": "user", "content": "abriu assim"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "outro assunto agora"},
        ],
        copilot="copiloto-diferente",
        surface="outra-surface",
    )
    (ref,) = await store.fetch_threads(owner="oid-1")
    assert ref.title == "abriu assim"
    assert (ref.copilot, ref.surface) == ("memory-copilot", "memory-composer")
    # O que MUDA a cada turno é só a atividade.
    assert ref.message_count == 3


# ── transcript + export/import (a porta inteira, em memória) ────────────


@pytest.mark.asyncio
async def test_state_so_sai_por_allowlist():
    """O state de um grafo carrega internals que não são contrato de ninguém —
    sem allowlist explícita, a porta devolve só as mensagens."""
    store = InMemoryThreadStore()
    store.seed_transcript(
        Transcript(
            thread_id="t1",
            messages=({"role": "user", "content": "oi"},),
            state={"draft": {"text": "rascunho"}, "__interno__": "não é contrato"},
        )
    )
    assert (await store.fetch_transcript("t1")).state == {}
    com_allowlist = await store.fetch_transcript("t1", state_keys=["draft"])
    assert com_allowlist.state == {"draft": {"text": "rascunho"}}
    assert com_allowlist.message_count == 1


@pytest.mark.asyncio
async def test_thread_inexistente_devolve_transcript_vazio_nao_erro():
    """É o que uma conversa recém-criada legitimamente parece."""
    vazio = await InMemoryThreadStore().fetch_transcript("nunca-existiu")
    assert vazio.messages == () and vazio.state == {} and vazio.pending is False


@pytest.mark.asyncio
async def test_export_declara_o_run_pendente_que_fica_para_tras():
    """A promessa honesta do contrato: o histórico visível atravessa; uma
    aprovação em curso, não. Dizer isso POR THREAD é o que impede a promessa
    implícita e falsa de "trocar de framework sem perder nada"."""
    store = InMemoryThreadStore()
    store.seed_transcript(
        Transcript(thread_id="t1", messages=({"role": "user", "content": "oi"},), pending=True)
    )
    envelope = await store.export_transcript("t1")
    assert envelope.pending_state_dropped is True
    assert envelope.format == TRANSCRIPT_FORMAT and envelope.source == "inmemory"
    assert envelope.exported_at


@pytest.mark.asyncio
async def test_import_restaura_historico_e_nunca_o_run_pendente():
    origem = InMemoryThreadStore()
    origem.seed_transcript(
        Transcript(
            thread_id="t1",
            messages=(
                {"role": "user", "content": "a pergunta"},
                {"role": "assistant", "content": "a resposta"},
            ),
            state={"draft": "x"},
            pending=True,
        )
    )
    envelope = await origem.export_transcript("t1", state_keys=["draft"])

    destino = InMemoryThreadStore()
    ref = await destino.import_transcript(envelope, owner="oid-1", workspace="ws")
    assert ref.owner == "oid-1" and ref.thread_id == "t1"
    # O título é derivado do transcript importado — a conversa chega nomeada.
    assert ref.title == "a pergunta"
    assert [t.thread_id for t in await destino.fetch_threads(owner="oid-1")] == ["t1"]

    lido = await destino.fetch_transcript("t1", state_keys=["draft"])
    assert lido.messages == envelope.messages and lido.state == {"draft": "x"}
    # O run pendente NÃO ressuscita do outro lado.
    assert lido.pending is False


@pytest.mark.asyncio
async def test_import_recusa_formato_desconhecido_em_vez_de_adivinhar():
    from dna.runtime.thread_store import TranscriptExport

    with pytest.raises(ValueError):
        await InMemoryThreadStore().import_transcript(
            TranscriptExport(thread_id="t1", format="formato-de-outra-casa"),
            owner="oid-1",
        )


@pytest.mark.asyncio
async def test_import_sobre_thread_alheio_usa_a_mesma_regra_de_posse():
    """Duas regras de posse podem divergir; a divergência só aparece quando
    alguém abre o thread de outro. Então é UMA."""
    from dna.runtime.thread_store import TranscriptExport

    destino = InMemoryThreadStore()
    await destino.index_thread(owner="dono", thread_id="t1", messages=[])
    with pytest.raises(ThreadOwnershipError):
        await destino.import_transcript(
            TranscriptExport(thread_id="t1"), owner="invasor"
        )


# ── a projeção de leitura do LangGraph ──────────────────────────────────


class _GrafoDuble:
    """Um grafo compilado o suficiente para a projeção: devolve um snapshot e
    REGISTRA toda chamada, para o teste poder afirmar que nada foi escrito."""

    def __init__(self, values: dict, proximo: tuple = ()):
        self._values = values
        self._proximo = proximo
        self.chamadas: list[str] = []

    async def aget_state(self, config):
        self.chamadas.append("aget_state")
        assert config == {"configurable": {"thread_id": "t1"}}
        import types

        return types.SimpleNamespace(values=self._values, next=self._proximo)

    def __getattr__(self, nome):  # qualquer outro uso do grafo é registrado
        def _registra(*_a, **_kw):
            self.chamadas.append(nome)
            raise AssertionError(f"a projeção de LEITURA chamou {nome!r} no grafo")

        return _registra


def _mensagens_langchain():
    from langchain_core.messages import AIMessage, HumanMessage

    return [
        HumanMessage(content="qual é o contrato?", id="m1"),
        AIMessage(content="a conversa é dado do DNA", id="m2"),
    ]


@pytest.mark.asyncio
async def test_projecao_le_o_checkpoint_pelo_conversor_oficial():
    """O conversor é o do bridge AG-UI do LangGraph — o MESMO do caminho de
    streaming. Um conversor nosso herdaria a nossa leitura da spec, e a
    divergência só apareceria com um cliente externo real na linha."""
    from dna.runtime.adapters.langgraph_threads import LangGraphTranscriptStore

    grafo = _GrafoDuble({"messages": _mensagens_langchain(), "draft": {"t": 1}})
    transcript = await LangGraphTranscriptStore(grafo).fetch_transcript("t1")

    assert [m["role"] for m in transcript.messages] == ["user", "assistant"]
    assert transcript.messages[0]["content"] == "qual é o contrato?"
    # dicts JSON na fronteira, nunca modelos do framework
    assert all(isinstance(m, dict) for m in transcript.messages)
    # e o state fica de fora sem allowlist
    assert transcript.state == {}
    # LEITURA: só o snapshot foi tocado — nenhuma escrita, nenhum turno mais caro
    assert grafo.chamadas == ["aget_state"]


@pytest.mark.asyncio
async def test_projecao_devolve_o_state_da_allowlist_declarada():
    from dna.runtime.adapters.langgraph_threads import LangGraphTranscriptStore

    grafo = _GrafoDuble(
        {"messages": [], "draft": {"t": 1}, "_interno": "x", "vazio": None}
    )
    store = LangGraphTranscriptStore(grafo, state_keys=("draft", "_interno"))
    # o default da instância
    assert (await store.fetch_transcript("t1")).state == {"draft": {"t": 1}, "_interno": "x"}
    # ...e o chamador pode estreitar por chamada (a allowlist de um host cujas
    # surfaces são declarativas muda por workspace)
    assert (await store.fetch_transcript("t1", state_keys=["draft"])).state == {
        "draft": {"t": 1}
    }
    # chave declarada mas vazia não vira ruído na UI
    assert (await store.fetch_transcript("t1", state_keys=["vazio"])).state == {}


@pytest.mark.asyncio
async def test_projecao_de_thread_sem_checkpoint_e_vazia():
    from dna.runtime.adapters.langgraph_threads import LangGraphTranscriptStore

    grafo = _GrafoDuble({})
    transcript = await LangGraphTranscriptStore(grafo).fetch_transcript("t1")
    assert transcript.messages == () and transcript.pending is False


@pytest.mark.asyncio
async def test_export_do_langgraph_sinaliza_o_interrupt_pendente():
    """``next`` não-vazio = o grafo parou no meio (tipicamente um interrupt
    esperando um humano). O transcript continua válido; o envelope avisa."""
    from dna.runtime.adapters.langgraph_threads import LangGraphTranscriptStore

    parado = _GrafoDuble({"messages": _mensagens_langchain()}, proximo=("tools",))
    envelope = await LangGraphTranscriptStore(parado).export_transcript("t1")
    assert envelope.pending_state_dropped is True
    assert envelope.source == "langchain" and envelope.format == TRANSCRIPT_FORMAT
    assert len(envelope.messages) == 2

    corrido = _GrafoDuble({"messages": _mensagens_langchain()})
    assert (
        await LangGraphTranscriptStore(corrido).export_transcript("t1")
    ).pending_state_dropped is False


@pytest.mark.asyncio
async def test_o_transcript_exportado_do_grafo_importa_na_porta_inteira():
    """O caminho REAL de trocar de framework, ponta a ponta: exporta AG-UI do
    backend velho, importa no novo. É isto — e não uma tradução de checkpoint —
    o que a porta promete."""
    from dna.runtime.adapters.langgraph_threads import LangGraphTranscriptStore

    grafo = _GrafoDuble({"messages": _mensagens_langchain()}, proximo=("tools",))
    envelope = await LangGraphTranscriptStore(grafo).export_transcript("t1")

    destino = InMemoryThreadStore()
    ref = await destino.import_transcript(envelope, owner="oid-1", copilot="novo")
    assert ref.title == "qual é o contrato?"
    lido = await destino.fetch_transcript("t1")
    assert [m["content"] for m in lido.messages] == [
        "qual é o contrato?",
        "a conversa é dado do DNA",
    ]
    # o interrupt do backend de origem ficou lá, como o envelope avisava
    assert envelope.pending_state_dropped is True and lido.pending is False


# ── a porta é ALCANÇÁVEL de quem já tem o app ───────────────────────────


def test_o_handle_langgraph_expoe_a_leitura_de_conversa():
    """Capacidade sem caminho até ela é o mesmo que não existir — e o host acaba
    escrevendo a sua própria leitura do checkpoint, que é o que a porta veio
    matar."""
    from dna.runtime.adapters.langchain_rt import _LangGraphAGUIApp

    app = _LangGraphAGUIApp(graph=object(), agent_name="a", transcript_state_keys=("draft",))
    store = app.thread_store
    assert isinstance(store, ThreadTranscriptPort)
    assert store.source == "langchain"


def test_o_handle_maf_declara_o_gap_em_vez_de_fingir():
    """Trocar ``serving.framework`` para este backend hoje perde o histórico. O
    handle diz ``None`` para que um host possa PERGUNTAR antes de prometer
    conversa — e para que o dia em que isso mudar seja verificável."""
    pytest.importorskip("agent_framework")
    from dna.runtime.adapters.maf_rt import _MafAGUIApp

    assert _MafAGUIApp(agent=object()).thread_store is None


def test_a_porta_e_exportada_pelo_pacote_runtime():
    import dna.runtime as runtime

    for nome in (
        "ThreadStorePort",
        "ThreadTranscriptPort",
        "ThreadIndexPort",
        "InMemoryThreadStore",
        "can_read_thread",
        "resolve_conversation",
    ):
        assert hasattr(runtime, nome), nome
        assert nome in runtime.__all__
