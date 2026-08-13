"""O registro de um turno — e os três sintomas que ele existe para fechar.

Sem OTEL instalado e sem banco: os spans são dublês com a forma que o
OpenInference produz. O que se exercita aqui é a REGRA — agrupar, somar, cortar,
e distinguir "morreu" de "está rodando" —, que é justamente a parte que um teste
contra o provider real nunca chega a exercitar nos casos difíceis.
"""
from __future__ import annotations

import pytest

from dna.runtime import telemetry
from dna.runtime.telemetry import (
    LANE_REAL,
    LANE_TEST,
    LANES,
    MAX_TEXT,
    TRUNCATION_MARK,
    Turn,
    TurnRecorder,
    clip,
)


class _Ctx:
    def __init__(self, trace_id: int):
        self.trace_id = trace_id


class _Status:
    def __init__(self, code: str = "OK", description: str | None = None):
        self.status_code = type("_C", (), {"name": code})()
        self.description = description


class _Span:
    """A forma que o OpenInference produz — atributos achatados, nanos, parent."""

    def __init__(
        self, *, kind=None, trace_id=1, parent=object(), attrs=None,
        start=0, end=1_000_000, status="OK", description=None, events=(), name="span",
    ):
        self.context = _Ctx(trace_id)
        self.parent = parent
        self.start_time = start
        self.end_time = end
        self.status = _Status(status, description)
        self.events = list(events)
        self.name = name
        self.attributes = dict(attrs or {})
        if kind:
            self.attributes["openinference.span.kind"] = kind


def _gravar(*spans):
    """Devolve os turnos entregues ao sink, na ordem."""
    saida = []
    rec = TurnRecorder(saida.append)
    for s in spans:
        rec.on_end(s)
    return saida


def _raiz(**kw):
    kw.setdefault("parent", None)
    kw.setdefault("kind", "CHAIN")
    return _Span(**kw)


# ── o sintoma #1: falha renderizando como pendência ─────────────────────────


def test_um_turno_que_MORREU_e_registrado_como_ERRO_com_a_mensagem():
    """⚠️ O sintoma que motivou o módulo, observado na tela em 02/08/2026.

    `generate_image` morreu com `ImportError: aiohttp package is not installed`,
    e vinte minutos depois a conversa reaberta ainda dizia "em curso". A tela
    não tinha como distinguir "rodando" de "morto" porque NADA registrava o
    fim.

    Sem esta asserção o módulo inteiro não resolve o problema que o originou.
    """
    [turno] = _gravar(_raiz(status="ERROR", description="aiohttp não instalado"))
    assert turno.status == "error"
    assert "aiohttp" in turno.error


def test_a_TOOL_que_estourou_aparece_como_erro_no_passo_dela():
    """Não basta o turno falhar: a tela mostra QUAL tool morreu."""
    tool = _Span(kind="TOOL", attrs={"tool.name": "generate_image"},
                 status="ERROR", description="404 DeploymentNotFound")
    [turno] = _gravar(tool, _raiz())
    [passo] = turno.steps
    assert passo.name == "generate_image"
    assert passo.status == "error"
    assert "DeploymentNotFound" in passo.error


def test_uma_EXCECAO_sem_status_de_erro_tambem_conta_como_falha():
    """Nem todo runtime marca o status; alguns só anexam o evento `exception`.

    Ler só o `status_code` deixaria esses turnos verdes — e verdes é exatamente
    como o defeito se apresentava.
    """
    evento = type("_E", (), {
        "name": "exception",
        "attributes": {"exception.message": "conexão recusada"},
    })()
    [turno] = _gravar(_raiz(events=[evento]))
    assert turno.status == "error"
    assert "conexão recusada" in turno.error


# ── o sintoma #2: o input/output de cada tool ───────────────────────────────


def test_cada_TOOL_vira_um_passo_com_input_e_output():
    tools = [
        _Span(kind="TOOL", attrs={"tool.name": "analyze_spreadsheet",
                                  "input.value": '{"file_id":"f-1"}',
                                  "output.value": "12345 linhas"}),
        _Span(kind="TOOL", attrs={"tool.name": "generate_image",
                                  "input.value": "um gato",
                                  "output.value": "/api/artifacts/abc"},
              start=2_000_000, end=3_000_000),
    ]
    [turno] = _gravar(*tools, _raiz())
    assert [p.name for p in turno.steps] == ["analyze_spreadsheet", "generate_image"]
    assert turno.steps[0].output == "12345 linhas"
    assert turno.steps[1].input == "um gato"


def test_os_passos_saem_na_ordem_em_que_COMECARAM():
    """⚠️ `on_end` chega na ordem em que os spans TERMINAM.

    Duas tools concorrentes terminam fora de ordem, e a tela mostraria a segunda
    antes da primeira — um histórico que mente sobre a sequência é pior que
    nenhum, porque ninguém desconfia dele.
    """
    tarde = _Span(kind="TOOL", attrs={"tool.name": "primeira"},
                  start=1_000_000, end=9_000_000)
    cedo = _Span(kind="TOOL", attrs={"tool.name": "segunda"},
                 start=5_000_000, end=6_000_000)
    # `cedo` TERMINA antes, então chega antes no processor.
    [turno] = _gravar(cedo, tarde, _raiz())
    assert [p.name for p in turno.steps] == ["primeira", "segunda"]
    assert [p.step_index for p in turno.steps] == [0, 1]


# ── o sintoma #3: tokens ────────────────────────────────────────────────────


def test_os_tokens_do_vocabulario_do_OPENINFERENCE_sao_lidos():
    """⚠️ MEDIDO em 02/08/2026, e o defeito era um ZERO plausível.

    A spec mandava seguir `gen_ai.*` — certo para EXPORTAR, errado para LER:
    quem produz os spans aqui é o OpenInference, e ele emite
    `llm.token_count.prompt`. O primeiro turno gravado veio com
    `input_tokens=0` e `model=''`, que parece um turno barato em vez de um
    leitor cego.
    """
    llm = _Span(kind="LLM", attrs={"llm.token_count.prompt": 1200,
                                   "llm.token_count.completion": 80,
                                   "llm.model_name": "gpt-5.4"})
    [turno] = _gravar(llm, _raiz())
    assert (turno.input_tokens, turno.output_tokens) == (1200, 80)
    assert turno.model == "gpt-5.4"


def test_os_tokens_SOMAM_entre_as_chamadas_do_turno():
    """⚠️ Um turno com tool tem no mínimo DUAS chamadas ao modelo.

    Guardar só a última contaria menos da metade — e um número errado é pior que
    nenhum, porque parece confiável.
    """
    llm1 = _Span(kind="LLM", attrs={"gen_ai.usage.input_tokens": 100,
                                    "gen_ai.usage.output_tokens": 20,
                                    "gen_ai.request.model": "gpt-5.4"})
    llm2 = _Span(kind="LLM", attrs={"gen_ai.usage.input_tokens": 300,
                                    "gen_ai.usage.output_tokens": 40})
    [turno] = _gravar(llm1, llm2, _raiz())
    assert (turno.input_tokens, turno.output_tokens) == (400, 60)
    assert turno.model == "gpt-5.4"


# ── o corte, e por que ele é anunciado ──────────────────────────────────────


def test_texto_grande_e_CORTADO_e_o_corte_APARECE():
    """Um corte silencioso faria quem lê acreditar que a tool respondeu aquilo —
    e depurar a partir de uma resposta que nunca existiu é pior que não ter
    registro."""
    cortado = clip("x" * (MAX_TEXT * 3))
    assert len(cortado) <= MAX_TEXT
    assert cortado.endswith(TRUNCATION_MARK)


def test_ausencia_e_diferente_de_vazio():
    assert clip(None) is None
    assert clip("") == ""


def test_estrutura_vira_JSON_em_vez_de_repr_de_python():
    """`str(dict)` produz aspas simples, que nenhum leitor de JSON aceita — e a
    tela do console lê isto."""
    assert clip({"a": 1}) == '{"a": 1}'


# ── o agrupamento ───────────────────────────────────────────────────────────


def test_dois_turnos_no_mesmo_processo_nao_se_MISTURAM():
    """O agrupamento é por trace. Sem isso, uma conversa herdaria as tools da
    outra — e num servidor com concorrência isso é o caso NORMAL, não a
    exceção."""
    a = _Span(kind="TOOL", trace_id=1, attrs={"tool.name": "tool_a"})
    b = _Span(kind="TOOL", trace_id=2, attrs={"tool.name": "tool_b"})
    turnos = _gravar(a, b, _raiz(trace_id=1), _raiz(trace_id=2))
    assert [[p.name for p in t.steps] for t in turnos] == [["tool_a"], ["tool_b"]]


def test_um_turno_que_nunca_FECHA_nao_e_entregue():
    """Materializar no início criaria registro fantasma para todo processo que
    morre no meio — e o registro fantasma seria indistinguível do sintoma #1."""
    assert _gravar(_Span(kind="TOOL", attrs={"tool.name": "sozinha"})) == []


def test_o_span_raiz_carrega_as_dimensoes_do_produto():
    [turno] = _gravar(_raiz(attrs={
        "dna.thread_id": "th-1", "dna.workspace": "ws-1",
        "dna.oid": "user-1", "dna.agent": "supervisor-copilot",
        "input.value": "oi", "output.value": "olá",
    }))
    assert (turno.thread_id, turno.workspace, turno.oid, turno.agent) == (
        "th-1", "ws-1", "user-1", "supervisor-copilot"
    )
    assert (turno.input_text, turno.output_text) == ("oi", "olá")


# ── telemetria não derruba o observado ──────────────────────────────────────


def test_um_SINK_que_estoura_nao_propaga():
    """Telemetria é observação. Derrubar o turno que ela observa inverteria a
    relação — e o modo de falha seria "o copiloto quebrou quando ligamos o
    OTEL"."""
    def _explode(_turno):
        raise RuntimeError("banco fora")

    rec = TurnRecorder(_explode)
    rec.on_end(_raiz())  # não levanta


def test_um_SPAN_deformado_nao_propaga():
    rec = TurnRecorder(lambda _t: None)
    rec.on_end(object())  # sem context, sem attributes, sem nada


def test_o_OTLP_e_OPCIONAL():
    """⚠️ O critério de aceitação #4 da spec, e o que prova que o produto não
    ficou acoplado à escolha de APM do cliente.

    Com o endpoint vazio, o registro que a TELA lê continua sendo produzido.
    """
    import os

    from dna.runtime.telemetry import otlp_endpoint

    anterior = os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    try:
        assert otlp_endpoint() == ""
        [turno] = _gravar(_raiz(attrs={"dna.thread_id": "th-9"}))
        assert turno.thread_id == "th-9"
    finally:
        if anterior is not None:
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = anterior


def test_setup_sem_os_pacotes_NAO_derruba_o_boot():
    """Um deployment sem o extra `otel` deve SERVIR, não crashar.

    Mesma assimetria de `require_capabilities`: ausência de medição é problema
    de operação, não negação de capacidade.
    """
    import builtins

    from dna.runtime import telemetry

    real = builtins.__import__

    def _sem_otel(name, *a, **kw):
        if name.startswith("opentelemetry"):
            raise ImportError("sem otel")
        return real(name, *a, **kw)

    builtins.__import__ = _sem_otel
    try:
        assert telemetry.setup_telemetry(sink=lambda _t: None) is None
    finally:
        builtins.__import__ = real


# ── contra o SDK DE VERDADE ─────────────────────────────────────────────────


def test_um_span_REAL_do_SDK_chega_ao_sink():
    """⚠️ A guarda que os 16 testes acima NÃO davam, e o defeito que provou isso.

    MEDIDO em 02/08/2026: faltava `_on_ending` — um método PRIVADO que o
    `Span.end()` do OpenTelemetry chama sem verificar se existe. Contra o
    runtime real o resultado foi `AttributeError` a cada span e **zero** turnos
    gravados; contra os dublês, quinze testes verdes.

    O dublê tinha a FORMA de um span e não a SEQUÊNCIA de chamadas do SDK. É por
    isso que este teste roda o `TracerProvider` de verdade: ele é o único aqui
    que exerce a superfície inteira de `SpanProcessor`.
    """
    pytest = __import__("pytest")
    trace = pytest.importorskip("opentelemetry.trace")
    sdk = pytest.importorskip("opentelemetry.sdk.trace")

    entregues = []
    provider = sdk.TracerProvider()
    provider.add_span_processor(TurnRecorder(entregues.append))
    tracer = provider.get_tracer("teste")

    with tracer.start_as_current_span("turno") as raiz:
        raiz.set_attribute("openinference.span.kind", "CHAIN")
        raiz.set_attribute("dna.thread_id", "th-real")
        with tracer.start_as_current_span("ferramenta") as filho:
            filho.set_attribute("openinference.span.kind", "TOOL")
            filho.set_attribute("tool.name", "analyze_spreadsheet")

    assert len(entregues) == 1, "nenhum turno chegou ao sink"
    [turno] = entregues
    assert turno.thread_id == "th-real"
    assert [p.name for p in turno.steps] == ["analyze_spreadsheet"]


def test_um_span_REAL_que_levanta_vira_turno_com_ERRO():
    """O sintoma #1 contra o SDK real: a exceção precisa virar `status=error`.

    O SDK grava o evento `exception` e marca o status; os dois caminhos que
    `_status_of` lê existem de verdade aqui.
    """
    pytest = __import__("pytest")
    sdk = pytest.importorskip("opentelemetry.sdk.trace")

    entregues = []
    provider = sdk.TracerProvider()
    provider.add_span_processor(TurnRecorder(entregues.append))
    tracer = provider.get_tracer("teste")

    try:
        with tracer.start_as_current_span("turno") as raiz:
            raiz.set_attribute("openinference.span.kind", "CHAIN")
            raise RuntimeError("aiohttp package is not installed")
    except RuntimeError:
        pass

    [turno] = entregues
    assert turno.status == "error"
    assert "aiohttp" in turno.error


def test_as_dimensoes_vem_de_QUALQUER_span_da_trace():
    """⚠️ MEDIDO em 02/08/2026: o primeiro registro real gravou com `thread_id`,
    `workspace` e `oid` VAZIOS.

    Quem conhece essas dimensoes e o HOST, e ele as carimba de dentro do turno —
    onde o span corrente e um FILHO, nao o raiz. Ler so o raiz encontrava um span
    que ninguem carimbou, e o registro ficava orfao: existia, ocupava espaco, e a
    tela filtrando por thread achava sempre vazio.

    Um registro que nao se liga a nada e pior que nenhum, porque PARECE cobertura.
    """
    filho = _Span(kind="TOOL", attrs={
        "tool.name": "analyze_spreadsheet",
        "dna.thread_id": "th-42", "dna.workspace": "ws-1", "dna.oid": "user-1",
    })
    [turno] = _gravar(filho, _raiz())  # o raiz NAO carrega dimensao nenhuma
    assert (turno.thread_id, turno.workspace, turno.oid) == ("th-42", "ws-1", "user-1")


# ── o DESFECHO: o que o turno CONSEGUIU ─────────────────────────────────────
#
# ⭐ Esta seção inteira defende UMA propriedade: **vazio nunca vira
# `resolved`**. Ela é atacada de vários ângulos porque o modo de falha é
# silencioso e inclina a conta a favor de quem a calcula — uma taxa de
# resolução inflada não parece errada, parece boa notícia.


@pytest.fixture(autouse=True)
def _contexto_limpo():
    """Zera a `ContextVar` entre testes.

    Sem isto, um desfecho carimbado num teste vazaria para o seguinte — que é
    literalmente o defeito que esta seção existe para provar que não acontece,
    e um teste que o sofre não consegue detectá-lo.
    """
    telemetry._contexto().set(None)
    yield
    telemetry._contexto().set(None)


def test_um_turno_sem_declaracao_fica_DESCONHECIDO_e_nao_resolvido():
    """⭐ O AC central. Ninguém declarou nada: o desfecho é vazio, e vazio NÃO é
    `resolved`."""
    [turno] = _gravar(_raiz())
    assert turno.outcome == ""


def test_um_turno_que_terminou_SEM_EXCECAO_nao_e_presumido_resolvido():
    """⚠️ A inferência tentadora, e a razão de ela estar proibida.

    `status='ok'` significa "não estourou exceção", não "resolveu". Derivar o
    desfecho dele produziria uma taxa de resolução que mede a AUSÊNCIA DE
    CRASHES e se apresenta como medida de valor entregue — nos 85 turnos
    medidos em 07/08/2026 daria 89%, um número inventado a favor de quem o
    calcula.
    """
    [turno] = _gravar(
        _Span(kind="LLM", attrs={"llm.token_count.prompt": 900,
                                 "llm.model_name": "gpt-5.4"}),
        _Span(kind="TOOL", attrs={"tool.name": "write_instance"}),
        _raiz(status="OK", attrs={"input.value": "oi", "output.value": "pronto"}),
    )
    assert turno.status == "ok"
    assert turno.outcome == ""


def test_o_desfecho_DECLARADO_chega_ao_turno():
    for declarado in ("resolved", "escalated", "abandoned"):
        telemetry.stamp_outcome(declarado)
        [turno] = _gravar(_raiz())
        assert turno.outcome == declarado


def test_um_desfecho_INVENTADO_e_recusado_e_o_turno_fica_vazio():
    """Nem "ok", nem "sucesso", nem `True`. O que não está em `OUTCOMES` não
    entra — aceitá-lo o faria aparecer numa contagem que não sabe o que ele
    significa."""
    for lixo in ("ok", "sucesso", "done", "resolvido", "", None, True):
        telemetry.stamp_outcome(lixo)
        [turno] = _gravar(_raiz())
        assert turno.outcome == "", f"{lixo!r} não podia ter passado"


def test_um_desfecho_no_SPAN_tambem_e_validado():
    """A `ContextVar` não é a única fonte — o atributo do span também entra, e
    ele vem de fora. A validação é da PORTA, não da chamada."""
    [bom] = _gravar(_raiz(attrs={"dna.outcome": "escalated"}))
    assert bom.outcome == "escalated"
    [ruim] = _gravar(_raiz(attrs={"dna.outcome": "resolvido_eu_acho"}))
    assert ruim.outcome == ""


def test_o_desfecho_de_um_turno_NAO_VAZA_para_o_proximo():
    """⚠️⚠️ O jeito mais provável de "vazio virar resolved" na vida real.

    A `ContextVar` é por-task, e uma task serve VÁRIOS turnos da mesma conversa.
    Se o desfecho sobrevivesse ao turno que o declarou, o turno seguinte — que
    não declarou nada — o herdaria, e a partir do primeiro `resolved` TODOS os
    turnos daquela conversa contariam como resolvidos.
    """
    saida = []
    rec = TurnRecorder(saida.append)

    telemetry.stamp_outcome("resolved")
    rec.on_end(_raiz(trace_id=1))
    rec.on_end(_raiz(trace_id=2))          # ninguém declarou nada neste
    rec.on_end(_raiz(trace_id=3))          # nem neste

    assert [t.outcome for t in saida] == ["resolved", "", ""]


def test_carimbar_o_TURNO_apaga_o_desfecho_do_turno_anterior():
    """A mesma proteção pelo outro lado: `stamp_turn` marca o INÍCIO de um
    turno, então é onde o desfecho anterior morre — sem depender de o recorder
    ter consumido."""
    telemetry.stamp_outcome("resolved")
    telemetry.stamp_turn(thread_id="th-1", workspace="ws-1")
    [turno] = _gravar(_raiz())
    assert turno.outcome == ""
    # ...e o que `stamp_turn` carimbou continua lá: apagar o desfecho não pode
    # levar as dimensões junto.
    assert (turno.thread_id, turno.workspace) == ("th-1", "ws-1")


def test_carimbar_o_desfecho_NAO_apaga_as_dimensoes():
    """⚠️ `stamp_outcome` roda naturalmente DEPOIS de `stamp_turn` — o desfecho
    só se sabe no fim. Se ele substituísse o contexto em vez de fundir, zeraria
    thread/workspace/oid justamente no turno que teve desfecho declarado: o
    registro melhor viraria o registro órfão."""
    telemetry.stamp_turn(thread_id="th-9", workspace="ws-9", oid="user-9",
                         agent="supervisor-copilot")
    telemetry.stamp_outcome("escalated")
    [turno] = _gravar(_raiz())
    assert turno.outcome == "escalated"
    assert (turno.thread_id, turno.workspace, turno.oid, turno.agent) == (
        "th-9", "ws-9", "user-9", "supervisor-copilot"
    )


def test_NENHUM_caminho_de_leitura_produz_resolved_sozinho():
    """⭐ A varredura: nenhuma combinação de status, erro, tokens, passos ou
    dimensões faz um turno não-declarado dizer `resolved`.

    Enumerar as formas de turno em vez de testar uma é o que transforma "não vi
    acontecer" em "não pode acontecer".
    """
    formas = (
        _raiz(),
        _raiz(status="ERROR", description="estourou"),
        _raiz(status="OK", attrs={"input.value": "oi", "output.value": "ok"}),
        _raiz(attrs={"dna.outcome": ""}),
        _raiz(attrs={"dna.outcome": "ok"}),
        _raiz(attrs={"dna.thread_id": "th", "dna.agent": "a"}),
        _raiz(events=[type("_E", (), {"name": "exception", "attributes": {}})()]),
    )
    for raiz in formas:
        [turno] = _gravar(
            _Span(kind="LLM", attrs={"llm.token_count.prompt": 10}),
            _Span(kind="TOOL", attrs={"tool.name": "t"}),
            raiz,
        )
        assert turno.outcome != "resolved"
        assert turno.outcome == ""


def test_o_default_do_dataclass_e_vazio_e_nao_resolved():
    """A última porta: quem constrói um `Turn` à mão também não ganha um
    `resolved` de graça."""
    assert Turn(turn_id="x").outcome == ""


# ── o ZERO de tokens, e os dois significados dele ───────────────────────────


def test_o_turno_que_ESTOUROU_grava_os_tokens_consumidos_ate_a_falha():
    """⭐ O AC do viés. MEDIDO em 07/08/2026 contra os 85 turnos reais.

    A hipótese da spec era "o turno que falha sai de graça: 8 de 9 não gravam
    tokens". A acumulação, na verdade, JÁ sobrevivia à exceção — o turno
    `d2b8520b` morreu de `DiskFull` com 5.662/1.732 gravados. Este teste
    congela o comportamento que a spec pedia e o código já tinha.
    """
    llm = _Span(kind="LLM", attrs={"llm.token_count.prompt": 5662,
                                   "llm.token_count.completion": 1732,
                                   "llm.model_name": "gpt-5.4"})
    [turno] = _gravar(llm, _raiz(status="ERROR", description="DiskFull(...)"))
    assert turno.status == "error"
    assert (turno.input_tokens, turno.output_tokens) == (5662, 1732)
    assert turno.tokens_partial is False


def test_uma_chamada_ao_modelo_SEM_contador_marca_a_conta_como_PISO():
    """⚠️ O caso real que a medição encontrou, e a razão de `tokens_partial`.

    O turno `65ccc02e`: 404 na chamada, `model='gpt-5-mini'`, tokens 0. O
    `openinference` monta os contadores com `_token_counts(run.outputs)`, e numa
    run que errou `run.outputs` é `None` — sai o nome do modelo (lido do
    `extra`, carimbado na largada) e NENHUM contador. O provedor cobrou o
    prompt; o span não sabe quanto.

    Zero aqui não é medição, é ausência — e é isso que a coluna passa a dizer.
    """
    llm = _Span(kind="LLM", attrs={"llm.model_name": "gpt-5-mini"},
                status="ERROR", description="NotFoundError 404")
    [turno] = _gravar(llm, _raiz(status="ERROR", description="NotFoundError 404"))
    assert turno.model == "gpt-5-mini"
    assert turno.input_tokens == 0
    assert turno.tokens_partial is True


def test_um_turno_SEM_chamada_ao_modelo_tem_a_conta_FECHADA_em_zero():
    """⚠️ O outro zero, e ele é a MEDIÇÃO CERTA — não pode ser confundido com o
    de cima.

    Sete dos nove turnos com erro morreram em 7–32 ms, antes de qualquer
    chamada ao modelo (401 no carregamento das tools, `CancelledError`). Zero
    chamadas, zero tokens, conta fechada. Marcá-los como parciais transformaria
    a coluna em ruído: se tudo é suspeito, nada é.
    """
    [turno] = _gravar(_raiz(status="ERROR", description="401 Unauthorized"))
    assert turno.model == ""
    assert turno.input_tokens == 0
    assert turno.tokens_partial is False


def test_uma_chamada_ilegivel_contamina_o_turno_inteiro():
    """Duas chamadas, uma reporta e a outra não: o total é um PISO. Marcar só a
    chamada perdida deixaria o total do turno parecendo completo."""
    boa = _Span(kind="LLM", attrs={"llm.token_count.prompt": 1200,
                                   "llm.token_count.completion": 80,
                                   "llm.model_name": "gpt-5.4"})
    perdida = _Span(kind="LLM", attrs={"llm.model_name": "gpt-5.4"},
                    status="ERROR", description="timeout")
    [turno] = _gravar(boa, perdida, _raiz(status="ERROR", description="timeout"))
    assert (turno.input_tokens, turno.output_tokens) == (1200, 80)
    assert turno.tokens_partial is True


# ── os dois caminhos onde tokens CONSUMIDOS eram descartados ────────────────


def test_uma_raiz_que_e_ELA_MESMA_um_LLM_fecha_o_turno():
    """⚠️ Uma invocação direta do modelo, sem chain em volta: o span raiz é de
    kind LLM.

    Os ramos TOOL/LLM faziam `return` antes do teste de raiz, então este turno
    somava os tokens e NUNCA fechava — o registro inteiro sumia, tokens e tudo,
    e ficava preso em `_abertos` para sempre. Somar e fechar são independentes.
    """
    so_llm = _Span(kind="LLM", parent=None,
                   attrs={"llm.token_count.prompt": 900,
                          "llm.token_count.completion": 30,
                          "llm.model_name": "gpt-5.4"})
    [turno] = _gravar(so_llm)
    assert (turno.input_tokens, turno.output_tokens) == (900, 30)
    assert turno.model == "gpt-5.4"


def test_uma_raiz_que_e_ELA_MESMA_uma_TOOL_tambem_fecha():
    assert len(_gravar(_Span(kind="TOOL", parent=None,
                             attrs={"tool.name": "sozinha"}))) == 1


def test_um_span_ATRASADO_nao_ressuscita_a_trace_como_turno_fantasma():
    """⚠️ Vazamento de memória silencioso, num processo que roda por semanas.

    Um span que chega depois de a raiz ter fechado recriava o `Turn` pelo
    `setdefault`: nascia um registro com o mesmo `turn_id`, sem raiz para
    fechá-lo, preso em `_abertos` para sempre. O tamanho do vazamento é o
    número de traces que já passaram.
    """
    saida = []
    rec = TurnRecorder(saida.append)
    rec.on_end(_raiz(trace_id=7))
    rec.on_end(_Span(kind="LLM", trace_id=7,
                     attrs={"llm.token_count.prompt": 4000}))
    assert len(saida) == 1
    assert rec._abertos == {}


def test_a_memoria_de_traces_fechadas_tem_TETO():
    """Lembrar das fechadas resolve o fantasma e não pode criar um segundo
    vazamento no lugar do primeiro."""
    rec = TurnRecorder(lambda _t: None)
    for i in range(TurnRecorder.LEMBRAR_FECHADAS * 3):
        rec.on_end(_raiz(trace_id=i + 1))
    assert len(rec._fechadas) <= TurnRecorder.LEMBRAR_FECHADAS
    assert rec._abertos == {}


# ── a RAIA do turno (`i-158`) ────────────────────────────────────────────────
#
# ⭐ A regra é a mesma do desfecho e o estrago tem a MESMA forma — só que a
# direção que assusta é a inversa. No desfecho, o risco é vazio virar
# `resolved` (a conta infla). Aqui, o risco é uma raia `test` herdada por um
# turno de gente de verdade: uso REAL some da conta, em silêncio.


def test_o_VAZIO_nao_e_uma_raia_do_vocabulario():
    """⭐ Vazio é a AUSÊNCIA de declaração, e pô-lo na lista o tornaria uma.

    Se `""` fosse membro de `LANES`, `_raia` o deixaria passar como valor
    válido e a distinção inteira da `i-158` morreria na porta de entrada.

    ⚠️ Esta asserção veio de `test_a_raia_do_turno.py` quando a leitura de
    rendimento saiu deste repositório (11/08/2026). Ela era a ÚNICA daquele
    arquivo que media o vocabulário e não a conta — o resto media a conta, e
    foi com a conta. Deixá-la ir junto teria tirado daqui a guarda do
    vocabulário que ESTE módulo publica.
    """
    assert "" not in LANES
    assert LANES == {LANE_REAL, LANE_TEST}


def test_um_turno_sem_declaracao_fica_SEM_RAIA_e_nao_real():
    """⭐ O AC central da raia. Ninguém declarou: vazio — e vazio NÃO é `real`.

    Um default `real` faria todo host que nunca ouviu falar de raia produzir
    turnos que se dizem de produção, e a suíte de avaliação que a `i-159` vai
    construir cairia inteira na conta do cliente.
    """
    [turno] = _gravar(_raiz())
    assert turno.lane == ""


def test_a_raia_DECLARADA_chega_ao_turno():
    for raia in sorted(telemetry.LANES):
        telemetry.stamp_turn(lane=raia)
        [turno] = _gravar(_raiz())
        assert turno.lane == raia


def test_uma_raia_INVENTADA_e_recusada_e_o_turno_fica_sem_raia():
    """Nem `prod`, nem `staging`, nem `True`. O que não está em `LANES` não
    entra — e o turno NÃO cai para `real` como consolo, que seria transformar
    um typo numa afirmação sobre a conta de alguém."""
    for lixo in ("prod", "staging", "testing", "producao", "", None, True):
        telemetry.stamp_turn(lane=lixo)
        [turno] = _gravar(_raiz())
        assert turno.lane == "", f"{lixo!r} não podia ter passado"


def test_uma_raia_no_SPAN_tambem_e_validada():
    """A validação é da PORTA, não da chamada: o atributo do span vem de fora
    (outra instrumentação, um contexto propagado) e passa pela mesma recusa."""
    [boa] = _gravar(_raiz(attrs={"dna.lane": "test"}))
    assert boa.lane == "test"
    [ruim] = _gravar(_raiz(attrs={"dna.lane": "prod"}))
    assert ruim.lane == ""


def test_a_raia_de_um_turno_NAO_VAZA_para_o_proximo():
    """⚠️⚠️ O defeito que custa dinheiro de verdade, e na direção pior.

    A `ContextVar` é por-task e uma task serve vários turnos. Se a raia
    sobrevivesse, uma suíte de avaliação que declarou `test` faria o turno
    seguinte — de um usuário real, na mesma task — sumir da conta. E sumir
    calado: ninguém procura um turno que o painel nunca mostrou.
    """
    telemetry.stamp_turn(lane="test")
    [primeiro] = _gravar(_raiz(trace_id=1))
    telemetry.stamp_turn(thread_id="th-2")   # o host recarimbou, SEM raia
    [segundo] = _gravar(_raiz(trace_id=2))
    assert (primeiro.lane, segundo.lane) == ("test", "")


def test_carimbar_a_raia_NAO_apaga_as_demais_dimensoes():
    """Mesma armadilha do `stamp_outcome`: fundir, nunca substituir."""
    telemetry.stamp_turn(thread_id="th-7", workspace="ws-7", oid="user-7",
                         agent="supervisor-copilot", lane="test")
    [turno] = _gravar(_raiz())
    assert turno.lane == "test"
    assert (turno.thread_id, turno.workspace, turno.oid, turno.agent) == (
        "th-7", "ws-7", "user-7", "supervisor-copilot"
    )


def test_a_raia_e_INDEPENDENTE_do_desfecho():
    """As duas viajam pela mesma `ContextVar` e não podem se atropelar: um
    turno de teste pode ter resolvido, e um turno real pode não ter."""
    telemetry.stamp_turn(lane="test")
    telemetry.stamp_outcome("resolved")
    [turno] = _gravar(_raiz())
    assert (turno.lane, turno.outcome) == ("test", "resolved")
