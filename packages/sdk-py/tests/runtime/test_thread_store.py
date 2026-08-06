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


# ══ fatia 2 — quem APLICA a retenção, e a troca de framework de verdade ══
#
# A fatia 1 deixou o slot, a conta e as duas metades do export sem ninguém que
# agisse: uma política que ninguém varre é um número num YAML, e um export que
# ninguém importa é metade de um caminho. O que este bloco mede:
#
# 1. **o default que não apaga** — sem retenção declarada a porta não é sequer
#    consultada (o pior defeito possível deste módulo seria o contrário);
# 2. **a ordem do apagamento** — transcript primeiro, índice depois, para que
#    uma queda no meio deixe uma varredura repetível e não checkpoint órfão;
# 3. **o envelope atravessando processo** — round-trip JSON, e formato
#    desconhecido RECUSADO;
# 4. **o apagador oficial** — o adapter delega ao ``adelete_thread`` do
#    checkpointer em vez de escrever DELETE nosso.


from datetime import datetime, timedelta, timezone  # noqa: E402

from dna.runtime.thread_store import (  # noqa: E402
    RetentionSweep,
    ThreadMigration,
    ThreadPurgePort,
    ThreadRef,
    TranscriptExport,
    TranscriptPurgePort,
    export_from_json,
    export_to_json,
    migrate_thread,
    parse_timestamp,
    sweep_retention,
    thread_expired,
)

AGORA = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def _ref(thread_id: str, *, dias_atras: float, copilot: str | None = None) -> ThreadRef:
    return ThreadRef(
        thread_id=thread_id,
        owner="oid-1",
        copilot=copilot,
        updated_at=(AGORA - timedelta(days=dias_atras)).isoformat(),
    )


# ── as decisões puras do vencimento ─────────────────────────────────────


def test_carimbo_e_lido_nas_formas_que_os_hosts_realmente_escrevem():
    """``Z`` no fim e carimbo ingênuo são as duas formas que aparecem na
    prática. Ler só a canônica faria a conversa parecer eterna."""
    esperado = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    assert parse_timestamp("2026-08-05T12:00:00Z") == esperado
    assert parse_timestamp("2026-08-05T12:00:00+00:00") == esperado
    assert parse_timestamp("2026-08-05T12:00:00") == esperado  # ingênuo = UTC
    assert parse_timestamp(esperado) == esperado
    assert parse_timestamp("ontem") is None
    assert parse_timestamp(None) is None and parse_timestamp("") is None


@pytest.mark.parametrize(
    "updated_at,esperado",
    [
        ((AGORA - timedelta(days=31)).isoformat(), True),
        ((AGORA - timedelta(days=29)).isoformat(), False),
        (None, False),          # não datável → nunca vence
        ("qualquer coisa", False),
    ],
)
def test_vencimento_e_fail_safe_no_que_nao_da_para_datar(updated_at, esperado):
    corte = retention_cutoff(ThreadRetention(max_age_days=30), now=AGORA)
    assert thread_expired(ThreadRef("t", "oid-1", updated_at=updated_at), corte) is esperado


def test_sem_politica_nada_vence_nem_o_thread_mais_antigo_do_mundo():
    """O custo do falso-negativo é guardar demais; o do falso-positivo é a
    conversa de alguém."""
    antigo = ThreadRef("t", "oid-1", updated_at="2001-01-01T00:00:00+00:00")
    assert thread_expired(antigo, None) is False


def test_exatamente_na_idade_limite_ainda_esta_dentro_dela():
    corte = retention_cutoff(ThreadRetention(max_age_days=30), now=AGORA)
    assert corte is not None
    no_limite = ThreadRef("t", "oid-1", updated_at=corte.isoformat())
    assert thread_expired(no_limite, corte) is False


# ── a varredura ─────────────────────────────────────────────────────────


class _PortaEspia:
    """Uma :class:`ThreadPurgePort` que REGISTRA tudo — inclusive o fato de ter
    sido chamada, que é o que o teste do default precisa afirmar."""

    def __init__(self, threads, *, log=None, apagaveis=None):
        self._threads = list(threads)
        self.log = log if log is not None else []
        self._apagaveis = apagaveis

    async def expired_threads(self, *, cutoff, copilot=None, limit=100):
        self.log.append(("consulta", cutoff, copilot, limit))
        vencidas = [
            t
            for t in self._threads
            if (copilot is None or t.copilot == copilot) and thread_expired(t, cutoff)
        ]
        vencidas.sort(key=lambda t: t.updated_at or "")
        return vencidas[:limit]

    async def delete_thread(self, thread_id):
        self.log.append(("apaga-indice", thread_id))
        if self._apagaveis is not None and thread_id not in self._apagaveis:
            return False
        return True


class _TranscriptEspiao:
    def __init__(self, log):
        self.log = log

    async def delete_transcript(self, thread_id):
        self.log.append(("apaga-transcript", thread_id))


@pytest.mark.asyncio
async def test_sem_retencao_declarada_a_porta_NAO_e_consultada():
    """O default é guardar para sempre, e ele tem de ser visível: uma varredura
    que "não achou nada" é indistinguível de uma que não devia ter rodado."""

    class _PortaQueExplode:
        async def expired_threads(self, **_):
            raise AssertionError("consultou a porta sem política declarada")

        async def delete_thread(self, _):
            raise AssertionError("apagou sem política declarada")

    for retencao in (None, ThreadRetention(), ThreadRetention(max_age_days=0)):
        sweep = await sweep_retention(_PortaQueExplode(), retencao)
        assert sweep == RetentionSweep(cutoff=None, expired=(), deleted=0, dry_run=False)
        assert sweep.has_policy is False


@pytest.mark.asyncio
async def test_varredura_apaga_transcript_antes_do_indice():
    """A ordem é contrato: morrer no meio deixa a linha de índice viva, e a
    passada seguinte reencontra o thread. Ao contrário, sobra checkpoint que
    ninguém mais lista, apaga ou sabe que existe."""
    log = []
    porta = _PortaEspia([_ref("velho", dias_atras=40), _ref("novo", dias_atras=1)], log=log)
    sweep = await sweep_retention(
        porta,
        ThreadRetention(max_age_days=30),
        transcript=_TranscriptEspiao(log),
        now=AGORA,
    )

    assert sweep.expired == ("velho",) and sweep.deleted == 1
    assert sweep.has_policy and sweep.cutoff == AGORA - timedelta(days=30)
    assert log[1:] == [("apaga-transcript", "velho"), ("apaga-indice", "velho")]


@pytest.mark.asyncio
async def test_varredura_sem_apagador_de_transcript_ainda_limpa_o_indice():
    """Um host que ainda não ligou o apagador do framework não fica sem
    retenção nenhuma — ele fica sem METADE dela, e isso é uma escolha dele."""
    log = []
    porta = _PortaEspia([_ref("velho", dias_atras=40)], log=log)
    sweep = await sweep_retention(porta, ThreadRetention(max_age_days=30), now=AGORA)
    assert sweep.deleted == 1
    assert log[1:] == [("apaga-indice", "velho")]


@pytest.mark.asyncio
async def test_dry_run_seleciona_e_reporta_sem_apagar():
    """É como se olha uma política nova antes de confiar nela."""
    log = []
    porta = _PortaEspia([_ref("velho", dias_atras=40)], log=log)
    sweep = await sweep_retention(
        porta, ThreadRetention(max_age_days=30), transcript=_TranscriptEspiao(log),
        now=AGORA, dry_run=True,
    )
    assert sweep.expired == ("velho",) and sweep.deleted == 0 and sweep.dry_run
    assert [evento[0] for evento in log] == ["consulta"]


@pytest.mark.asyncio
async def test_a_varredura_e_recortada_pelo_copiloto_que_declarou_a_politica():
    """A retenção mora no documento do Copilot — varrer sem esse recorte
    aplicaria a política de um copiloto às conversas de outro."""
    porta = _PortaEspia(
        [
            _ref("a", dias_atras=40, copilot="suporte"),
            _ref("b", dias_atras=40, copilot="juridico"),
        ]
    )
    sweep = await sweep_retention(
        porta, ThreadRetention(max_age_days=30), copilot="suporte", now=AGORA
    )
    assert sweep.expired == ("a",)


@pytest.mark.asyncio
async def test_o_que_expirou_e_o_que_sumiu_sao_contados_separados():
    """Divergir é informação: um id que expirou e não foi apagado volta na
    próxima passada, e um contador só de sucesso esconderia isso."""
    porta = _PortaEspia(
        [_ref("some", dias_atras=40), _ref("resiste", dias_atras=41)],
        apagaveis={"some"},
    )
    sweep = await sweep_retention(porta, ThreadRetention(max_age_days=30), now=AGORA)
    assert set(sweep.expired) == {"some", "resiste"} and sweep.deleted == 1


@pytest.mark.asyncio
async def test_a_implementacao_de_referencia_cumpre_a_varredura_inteira():
    """O par de conformidade de sempre: se a porta de expurgo não é
    implementável de ponta a ponta, ela é desenho e não contrato."""
    store = InMemoryThreadStore()
    assert isinstance(store, ThreadPurgePort) and isinstance(store, TranscriptPurgePort)

    await store.index_thread(owner="oid-1", thread_id="t1", messages=[])
    store.seed_transcript(Transcript(thread_id="t1", messages=({"role": "user"},)))
    # O índice carimba `updated_at` com o agora REAL, então quem viaja é o
    # relógio da varredura: dois dias à frente, com política de um dia, a
    # conversa recém-criada já venceu.
    futuro = datetime.now(timezone.utc) + timedelta(days=2)
    sweep = await sweep_retention(
        store, ThreadRetention(max_age_days=1), transcript=store, now=futuro
    )
    assert sweep.expired == ("t1",) and sweep.deleted == 1
    assert await store.fetch_threads(owner="oid-1") == []
    assert (await store.fetch_transcript("t1")).messages == ()
    # Idempotente: a segunda passada não acha nada e não levanta.
    de_novo = await sweep_retention(store, ThreadRetention(max_age_days=1), now=futuro)
    assert de_novo.expired == () and de_novo.deleted == 0


# ── o envelope atravessando processo ────────────────────────────────────


def test_o_envelope_faz_round_trip_por_json():
    """Sem codec no contrato, cada host inventaria a sua serialização do MESMO
    envelope — divergência silenciosa na fronteira mais cara de todas."""
    import json

    original = TranscriptExport(
        thread_id="t1",
        messages=({"role": "user", "content": "oi"}, {"role": "assistant", "content": "olá"}),
        state={"draft": {"text": "x"}},
        source="langchain",
        exported_at="2026-08-05T12:00:00+00:00",
        pending_state_dropped=True,
    )
    # atravessa de verdade: serializa, escreve, lê, desserializa
    de_volta = export_from_json(json.loads(json.dumps(export_to_json(original))))
    assert de_volta == original


def test_formato_desconhecido_e_recusado_em_vez_de_lido_otimisticamente():
    """"Quase certo" numa conversa importada é pior do que recusar."""
    payload = export_to_json(TranscriptExport(thread_id="t1"))
    payload["format"] = "ag-ui/messages@99"
    with pytest.raises(ValueError):
        export_from_json(payload)
    with pytest.raises(ValueError):
        export_from_json({"thread_id": "t1"})  # sem format nenhum
    with pytest.raises(TypeError):
        export_from_json("nem é um objeto")


def test_corpo_malformado_falha_alto_em_vez_de_importar_pela_metade():
    payload = export_to_json(TranscriptExport(thread_id="t1"))
    with pytest.raises(ValueError):
        export_from_json({**payload, "messages": "uma string não é uma lista"})
    with pytest.raises(ValueError):
        export_from_json({**payload, "state": ["nem é um objeto"]})


# ── a troca de framework em uma chamada ─────────────────────────────────


@pytest.mark.asyncio
async def test_migrate_thread_leva_o_historico_e_denuncia_o_run_pendente():
    """Um caminho que existe só como "chame A e depois B" é um caminho que cada
    host percorre à sua maneira."""
    from dna.runtime.adapters.langgraph_threads import LangGraphTranscriptStore

    origem = LangGraphTranscriptStore(
        _GrafoDuble({"messages": _mensagens_langchain()}, proximo=("tools",))
    )
    destino = InMemoryThreadStore()

    resultado = await migrate_thread(
        origem, destino, "t1", owner="oid-1", workspace="ws", copilot="novo"
    )
    assert isinstance(resultado, ThreadMigration)
    assert resultado.source == "langchain" and resultado.message_count == 2
    # A aprovação em curso do outro lado NÃO veio, e o resultado diz.
    assert resultado.pending_state_dropped is True
    assert resultado.thread.owner == "oid-1" and resultado.thread.title == "qual é o contrato?"

    lido = await destino.fetch_transcript("t1")
    assert [m["content"] for m in lido.messages][0] == "qual é o contrato?"
    assert lido.pending is False


@pytest.mark.asyncio
async def test_migrate_thread_afirma_a_posse_no_destino():
    """A posse é afirmada UMA vez, no destino — e antes de qualquer escrita."""
    origem = InMemoryThreadStore()
    origem.seed_transcript(
        Transcript(thread_id="t1", messages=({"role": "user", "content": "oi"},))
    )
    destino = InMemoryThreadStore()
    await destino.index_thread(owner="dono", thread_id="t1", messages=[])

    with pytest.raises(ThreadOwnershipError):
        await migrate_thread(origem, destino, "t1", owner="invasor")
    assert (await destino.fetch_transcript("t1")).messages == ()


@pytest.mark.asyncio
async def test_migrate_thread_pode_renomear_o_thread_no_destino():
    """Dois backends podem já ter um thread com o mesmo id; o destino manda."""
    origem = InMemoryThreadStore()
    origem.seed_transcript(
        Transcript(thread_id="antigo", messages=({"role": "user", "content": "oi"},))
    )
    destino = InMemoryThreadStore()
    resultado = await migrate_thread(
        origem, destino, "antigo", owner="oid-1", target_thread_id="novo"
    )
    assert resultado.thread.thread_id == "novo"
    assert (await destino.fetch_transcript("novo")).message_count == 1


# ── o apagador do framework é o OFICIAL ─────────────────────────────────


class _CheckpointerDuble:
    def __init__(self):
        self.apagados: list[str] = []

    async def adelete_thread(self, thread_id):
        self.apagados.append(thread_id)


@pytest.mark.asyncio
async def test_o_expurgo_delega_ao_apagador_oficial_do_checkpointer():
    """Regra da casa aplicada ao apagar: existindo a implementação oficial
    (``BaseCheckpointSaver.adelete_thread``), ela é obrigatória — e ela conhece
    tabelas (blobs, writes) que uma varredura nossa esqueceria."""
    import types

    from dna.runtime.adapters.langgraph_threads import LangGraphTranscriptPurge

    checkpointer = _CheckpointerDuble()
    # pelo grafo compilado...
    await LangGraphTranscriptPurge(
        types.SimpleNamespace(checkpointer=checkpointer)
    ).delete_transcript("t1")
    # ...e pelo checkpointer direto, que é o que um job de varredura tem em mãos
    await LangGraphTranscriptPurge(checkpointer).delete_transcript("t2")
    assert checkpointer.apagados == ["t1", "t2"]


@pytest.mark.asyncio
async def test_sem_checkpointer_o_expurgo_e_no_op_e_nao_erro():
    """Um copiloto em memória não tem o que apagar, e isso é NORMAL: levantar
    ali transformaria "não persiste" numa exceção no meio da varredura."""
    import types

    from dna.runtime.adapters.langgraph_threads import LangGraphTranscriptPurge

    await LangGraphTranscriptPurge(types.SimpleNamespace(checkpointer=None)).delete_transcript("t")
    await LangGraphTranscriptPurge(object()).delete_transcript("t")


def test_a_projecao_de_leitura_continua_sem_saber_apagar():
    """A classe que promete não escrever nada não pode ganhar um método que
    apaga — a promessa não sobreviveria, e quem só lê receberia o apagador."""
    from dna.runtime.adapters.langgraph_threads import (
        LangGraphTranscriptPurge,
        LangGraphTranscriptStore,
    )

    leitor = LangGraphTranscriptStore(graph=object())
    assert isinstance(leitor, ThreadTranscriptPort)
    assert not isinstance(leitor, TranscriptPurgePort)
    assert isinstance(LangGraphTranscriptPurge(object()), TranscriptPurgePort)


def test_os_verbos_da_fatia_2_sao_exportados_pelo_pacote_runtime():
    import dna.runtime as runtime

    for nome in (
        "ThreadPurgePort",
        "TranscriptPurgePort",
        "RetentionSweep",
        "ThreadMigration",
        "sweep_retention",
        "thread_expired",
        "migrate_thread",
        "export_to_json",
        "export_from_json",
    ):
        assert hasattr(runtime, nome), nome
        assert nome in runtime.__all__
