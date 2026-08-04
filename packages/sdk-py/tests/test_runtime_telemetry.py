"""O registro de um turno — e os três sintomas que ele existe para fechar.

Sem OTEL instalado e sem banco: os spans são dublês com a forma que o
OpenInference produz. O que se exercita aqui é a REGRA — agrupar, somar, cortar,
e distinguir "morreu" de "está rodando" —, que é justamente a parte que um teste
contra o provider real nunca chega a exercitar nos casos difíceis.
"""
from __future__ import annotations

from dna.runtime.telemetry import (
    MAX_TEXT,
    TRUNCATION_MARK,
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
