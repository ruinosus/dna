"""O que um turno FEZ — uma instrumentação, dois destinos.

::

            LangChainInstrumentor (OpenInference)
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
       TurnRecorder            OTLP Exporter
       → o Postgres do DNA     → o APM de quem opera
       → a tela do PRODUTO     → opcional

## O que este módulo existe para consertar

Nada registrava o que acontecia num turno. Três sintomas, observados na tela do
dna-cloud em 02/08/2026, são o mesmo buraco visto de ângulos diferentes:

* uma tool que **morreu** no meio continuava dizendo ``em curso`` vinte minutos
  depois, ao vivo e ao reabrir a conversa — **falha renderizando como
  pendência**;
* o input/output de cada tool **some** ao recarregar: vive só no checkpoint do
  LangGraph, e a conversão do ``ag_ui_langgraph`` para o navegador o descarta;
* contagem de tokens nunca foi gravada em lugar nenhum.

## ⚠️ Por que DOIS destinos, e não só o OTLP

A tentação é exportar tudo para o APM e ler de lá. Ela quebra o produto por três
motivos independentes:

1. **cada cliente escolhe o seu** — Grafana, Azure Monitor, App Insights, ou
   nenhum. Uma tela do produto que dependa dessa escolha não existe para quem
   não escolheu;
2. o APM é de **quem opera**. Ninguém dá acesso ao Grafana para o cliente ver o
   que a tool respondeu na conversa dele;
3. o dado que a tela precisa é **por thread**, e um APM indexa por serviço e
   tempo.

Então o ``TurnRecorder`` grava aqui, e o OTLP sai em paralelo — ligado **só** se
``OTEL_EXPORTER_OTLP_ENDPOINT`` existir. Com ele vazio, tudo o que a tela mostra
continua funcionando; é isso que prova que o produto não ficou acoplado à
escolha do cliente.

## ⚠️ Por que um SpanProcessor, e não um `record_turn()` no fim do handler

A chamada explícita é mais fácil de ler e tem um defeito estrutural: **só
registra quem lembrou de chamar.** Um processor instrumenta a plataforma uma vez
e todo runtime passa a registrar — copiloto, porta A2A, MCP, REST —, inclusive
os que ninguém pensou em instrumentar.

E ele pega justamente o caso que a chamada explícita perde: o turno que
**estourou**. Um ``record_turn`` no fim do handler não roda quando o handler
levanta — que é exatamente o sintoma #1.

## O que este módulo NÃO faz

Não escreve no banco. O processor produz ``Turn``/``TurnStep`` e os entrega a um
``sink`` injetado; quem tem a conexão grava. É a mesma fronteira de
``capabilities`` e ``agent_grant``: a regra é daqui, o I/O é de quem tem o
cliente — e é o que torna esta lógica exercitável **sem banco e sem rede**.

## Os nomes dos atributos

``gen_ai.*`` da convenção semântica do OpenTelemetry onde ela existe, ``dna.*``
só para o que é nosso. O motivo é o mesmo de usar o SDK oficial: o APM do cliente
**já sabe** ler ``gen_ai.usage.input_tokens``. Um nome próprio transformaria um
painel pronto num painel a construir.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

_LOGGER = logging.getLogger("dna.runtime.telemetry")

__all__ = [
    "MAX_TEXT",
    "TRUNCATION_MARK",
    "Turn",
    "TurnStep",
    "TurnRecorder",
    "clip",
    "otlp_endpoint",
    "setup_telemetry",
    "stamp_turn",
]

#: Teto de cada campo de texto gravado. O registro é para leitura HUMANA — uma
#: tool que devolve 200 KB de JSON viraria 200 KB por turno, para sempre, que é
#: o mesmo defeito do Base64 no checkpoint com outra roupa.
MAX_TEXT = 8 * 1024

#: ⚠️ O corte é ANUNCIADO. Um truncamento silencioso faria quem lê o histórico
#: acreditar que a tool respondeu exatamente aquilo — e depurar a partir de uma
#: resposta que nunca existiu é pior que não ter registro nenhum.
TRUNCATION_MARK = "\n…[truncado por dna.runtime.telemetry]"

# ── convenção semântica ─────────────────────────────────────────────────────

# ⚠️ DOIS vocabulários, e ler só um custou uma medição.
#
# A convenção do OpenTelemetry (`gen_ai.*`) é a que o APM do cliente entende, e
# é a certa para EXPORTAR. Mas quem PRODUZ os spans aqui é o OpenInference, e
# ele emite o vocabulário dele.
#
# MEDIDO em 02/08/2026 contra o runtime real: o turno gravou com
# `input_tokens=0`, `output_tokens=0` e `model=''` — corretamente, porque
# `gen_ai.usage.input_tokens` simplesmente não existia no span. O que existia
# era `llm.token_count.prompt`.
#
# Um leitor que aceita só um vocabulário não dá erro: dá ZERO, que parece um
# turno barato. Por isso a ordem abaixo é "o que o produtor emite primeiro,
# o padrão depois" — e não o contrário.
ATTR_INPUT_TOKENS = ("llm.token_count.prompt", "gen_ai.usage.input_tokens")
ATTR_OUTPUT_TOKENS = ("llm.token_count.completion", "gen_ai.usage.output_tokens")
ATTR_MODEL = ("llm.model_name", "gen_ai.request.model")


def _primeiro(atributos: Mapping[str, Any], nomes: Sequence[str]) -> Any:
    """O primeiro nome presente, na ordem de preferência."""
    for nome in nomes:
        if nome in atributos:
            return atributos[nome]
    return None

#: Nossos — o que a convenção não cobre porque é do produto.
ATTR_WORKSPACE = "dna.workspace"
ATTR_THREAD = "dna.thread_id"
ATTR_OID = "dna.oid"
ATTR_AGENT = "dna.agent"

#: Do OpenInference, que é quem produz os spans de LangChain.
OI_KIND = "openinference.span.kind"
OI_INPUT = "input.value"
OI_OUTPUT = "output.value"
OI_TOOL_NAME = "tool.name"


def clip(value: Any, limit: int = MAX_TEXT) -> str | None:
    """O texto que vai para o banco: string, dentro do teto, corte anunciado.

    ``None`` continua ``None`` — ausência é diferente de vazio, e a coluna
    distingue as duas. Estrutura vira JSON compacto; o resto vira ``str``.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            value = str(value)
    if len(value) <= limit:
        return value
    return value[: limit - len(TRUNCATION_MARK)] + TRUNCATION_MARK


@dataclass
class TurnStep:
    """Uma tool chamada — o que a tela mostra quando alguém expande o turno."""

    name: str
    step_index: int = 0
    input: str | None = None
    output: str | None = None
    status: str = "ok"
    error: str | None = None
    started_at: str | None = None
    duration_ms: int = 0


@dataclass
class Turn:
    """O que um turno fez. NÃO é o trace — é o que um humano precisa ler.

    ``trace_id`` fica guardado para quem quiser pular para o APM, quando existir
    um. Sem ele, o registro seria uma ilha; com ele, é uma porta.
    """

    turn_id: str
    trace_id: str = ""
    thread_id: str = ""
    workspace: str = ""
    oid: str = ""
    agent: str = ""
    model: str = ""
    input_text: str | None = None
    output_text: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    status: str = "ok"
    error: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int = 0
    steps: list[TurnStep] = field(default_factory=list)


def _attrs(span: Any) -> Mapping[str, Any]:
    return getattr(span, "attributes", None) or {}


def _nanos_to_ms(start: Any, end: Any) -> int:
    try:
        return max(0, int((int(end) - int(start)) / 1_000_000))
    except (TypeError, ValueError):
        return 0


def _iso(nanos: Any) -> str | None:
    """Instante em ISO-8601 UTC, a partir dos nanos do span.

    Vem do SPAN e não do relógio de quem grava: o processor pode rodar segundos
    depois, e um registro que mente sobre quando o turno começou é pior que um
    sem horário.
    """
    from datetime import UTC, datetime

    try:
        return datetime.fromtimestamp(int(nanos) / 1e9, UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _status_of(span: Any) -> tuple[str, str | None]:
    """``(status, erro)`` — e é ESTA função que fecha o sintoma #1.

    Um span que terminou em erro vira um turno com ``status="error"`` e a
    mensagem. Sem isso a tela não tem como distinguir "ainda rodando" de "morreu
    há vinte minutos", e mostra as duas como pendentes.
    """
    st = getattr(span, "status", None)
    code = getattr(getattr(st, "status_code", None), "name", "") or ""
    if code.upper() == "ERROR":
        return "error", (getattr(st, "description", None) or "erro sem descrição")
    for event in getattr(span, "events", None) or []:
        if getattr(event, "name", "") == "exception":
            atributos = getattr(event, "attributes", None) or {}
            return "error", str(
                atributos.get("exception.message")
                or atributos.get("exception.type")
                or "exceção sem mensagem"
            )
    return "ok", None


class TurnRecorder:
    """``SpanProcessor`` que transforma spans num registro de turno.

    Agrupa por ``trace_id``: um turno é uma trace, e as tools são spans-filhos
    dela. Quando a trace fecha (o span raiz termina), entrega ao ``sink``.

    ``sink`` recebe um ``Turn`` e é síncrono do ponto de vista deste objeto —
    exportar spans é caminho quente, então quem grava deve enfileirar em vez de
    bloquear. Uma exceção do sink é **engolida com log**: telemetria não derruba
    o turno que ela observa.
    """

    def __init__(self, sink: Callable[[Turn], None]) -> None:
        self._sink = sink
        self._abertos: dict[str, Turn] = {}

    # ── a interface de SpanProcessor ────────────────────────────────────────
    #
    # ⚠️ Implementada por INTEIRO, e `_on_ending` é a razão deste aviso.
    #
    # Esta classe não herda de `opentelemetry.sdk.trace.SpanProcessor` de
    # propósito: herdar exigiria o pacote no import, e é justamente não exigi-lo
    # que torna a regra exercitável sem OTEL instalado. O preço é que a
    # superfície tem de ser mantida à mão.
    #
    # MEDIDO em 02/08/2026, contra o runtime real: faltava `_on_ending` — um
    # método PRIVADO que o `Span.end()` do SDK chama — e o resultado foi
    # `AttributeError: 'TurnRecorder' object has no attribute '_on_ending'`
    # repetido a cada span, com ZERO turnos gravados. Os 16 testes estavam
    # verdes: o dublê tinha a forma de um span, mas não a SEQUÊNCIA de chamadas
    # do SDK. É a mesma cegueira de dublê que este produto já pagou antes.
    #
    # A guarda contra a repetição é `test_um_span_REAL_do_SDK_chega_ao_sink`,
    # que roda o provider de verdade em vez de um dublê.

    def on_start(self, span: Any, parent_context: Any = None) -> None:  # noqa: D102
        return None

    def _on_ending(self, span: Any) -> None:
        """Gancho do SDK, chamado ANTES de o span virar imutável.

        No-op aqui: só lemos o span depois de pronto. Existe porque o SDK o
        chama sem verificar, e a ausência vira `AttributeError` por span.
        """
        return None

    def shutdown(self) -> None:  # noqa: D102
        self._abertos.clear()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:  # noqa: D102
        return True

    def on_end(self, span: Any) -> None:
        try:
            self._absorver(span)
        except Exception:  # noqa: BLE001 — telemetria NUNCA derruba o observado
            _LOGGER.warning("TurnRecorder falhou ao absorver um span", exc_info=True)

    # ── a leitura ───────────────────────────────────────────────────────────

    def _absorver(self, span: Any) -> None:
        ctx = getattr(span, "context", None) or getattr(span, "get_span_context", lambda: None)()
        trace_id = format(getattr(ctx, "trace_id", 0) or 0, "032x")
        atributos = _attrs(span)
        kind = str(atributos.get(OI_KIND) or "").upper()

        turno = self._abertos.setdefault(trace_id, Turn(turn_id=trace_id, trace_id=trace_id))

        # ⚠️ As dimensoes sao colhidas de QUALQUER span da trace, nao so do
        # raiz. MEDIDO em 02/08/2026: o primeiro registro real gravou com
        # thread_id, workspace e oid VAZIOS — quem as conhece e o host, e ele as
        # carimba de dentro do turno (um middleware), onde o span corrente e um
        # FILHO. Ler so o raiz encontrava um span que ninguem carimbou.
        #
        # O registro existia e nao podia ser ligado a nenhuma conversa: a tela
        # filtraria por thread e acharia sempre vazio. Um registro orfao e pior
        # que nenhum, porque ocupa espaco parecendo cobertura.
        self._dimensoes(turno, atributos)

        if kind == "TOOL":
            self._passo(turno, span, atributos)
            return

        if kind == "LLM":
            self._llm(turno, atributos)
            return

        # Sem `parent`, este é o span RAIZ: o turno inteiro. É aqui que ele
        # fecha — e é por isso que um processo que morre não deixa registro
        # pela metade, e sim registro nenhum.
        if getattr(span, "parent", None) is None:
            self._fechar(turno, span, atributos, trace_id)

    def _dimensoes(self, turno: Turn, atributos: Mapping[str, Any]) -> None:
        """As dimensoes do produto, de onde quer que venham. Primeiro valor vence."""
        for campo, chave in (
            ("thread_id", ATTR_THREAD), ("workspace", ATTR_WORKSPACE),
            ("oid", ATTR_OID), ("agent", ATTR_AGENT),
        ):
            if not getattr(turno, campo) and atributos.get(chave):
                setattr(turno, campo, str(atributos[chave]))

    def _passo(self, turno: Turn, span: Any, atributos: Mapping[str, Any]) -> None:
        status, erro = _status_of(span)
        turno.steps.append(
            TurnStep(
                name=str(atributos.get(OI_TOOL_NAME) or getattr(span, "name", "") or "?"),
                step_index=len(turno.steps),
                input=clip(atributos.get(OI_INPUT)),
                output=clip(atributos.get(OI_OUTPUT)),
                status=status,
                error=clip(erro, 1024),
                started_at=_iso(getattr(span, "start_time", None)),
                duration_ms=_nanos_to_ms(
                    getattr(span, "start_time", 0), getattr(span, "end_time", 0)
                ),
            )
        )

    def _llm(self, turno: Turn, atributos: Mapping[str, Any]) -> None:
        # SOMA em vez de sobrescrever: um turno com tool tem no mínimo duas
        # chamadas ao modelo, e guardar só a última contaria menos da metade dos
        # tokens — um número errado é pior que nenhum, porque parece confiável.
        turno.input_tokens += int(_primeiro(atributos, ATTR_INPUT_TOKENS) or 0)
        turno.output_tokens += int(_primeiro(atributos, ATTR_OUTPUT_TOKENS) or 0)
        if not turno.model:
            turno.model = str(_primeiro(atributos, ATTR_MODEL) or "")

    def _fechar(
        self, turno: Turn, span: Any, atributos: Mapping[str, Any], trace_id: str
    ) -> None:
        status, erro = _status_of(span)
        self._dimensoes(turno, atributos)
        # A `ContextVar` é a fonte que funciona sob o OpenInference; os
        # atributos do span cobrem quem propaga contexto de verdade.
        self._dimensoes(turno, _contexto().get() or {})
        turno.input_text = clip(atributos.get(OI_INPUT))
        turno.output_text = clip(atributos.get(OI_OUTPUT))
        turno.status = status
        turno.error = clip(erro, 1024)
        turno.started_at = _iso(getattr(span, "start_time", None))
        turno.ended_at = _iso(getattr(span, "end_time", None))
        turno.duration_ms = _nanos_to_ms(
            getattr(span, "start_time", 0), getattr(span, "end_time", 0)
        )
        # Ordena os passos pelo início REAL. O `on_end` chega na ordem em que os
        # spans TERMINAM, e duas tools concorrentes terminam fora de ordem — a
        # tela mostraria a segunda antes da primeira.
        turno.steps.sort(key=lambda s: (s.started_at or "", s.step_index))
        for i, passo in enumerate(turno.steps):
            passo.step_index = i

        self._abertos.pop(trace_id, None)
        try:
            self._sink(turno)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("sink de telemetria falhou", exc_info=True)


#: ⚠️ As dimensões viajam por `ContextVar`, e não pelo span corrente.
#:
#: MEDIDO em 02/08/2026: dentro de um nó do grafo, `trace.get_current_span()`
#: devolve um `NonRecordingSpan`. O OpenInference instrumenta o LangChain por
#: CALLBACKS e não propaga o contexto OTEL para o código do nó — então
#: `span.set_attribute` ali não escreve em lugar nenhum, e não dá erro.
#:
#: `ContextVar` é por-task, então duas requisições concorrentes não se
#: misturam; e o `on_end` do span raiz roda na mesma task que o turno, que é o
#: que faz a leitura funcionar.
_DIMENSOES: Any = None


def _contexto():
    global _DIMENSOES
    if _DIMENSOES is None:
        from contextvars import ContextVar

        _DIMENSOES = ContextVar("dna_turn_dims", default=None)
    return _DIMENSOES


def stamp_turn(
    *,
    thread_id: str | None = None,
    workspace: str | None = None,
    oid: str | None = None,
    agent: str | None = None,
) -> None:
    """Carimba as dimensoes do produto no span CORRENTE.

    Quem as conhece e o host — elas chegam nos cabecalhos da requisicao, que o
    SDK nao le. Chame de dentro do turno (um middleware `before_agent` serve);
    o `TurnRecorder` as colhe de qualquer span da trace, entao nao importa se o
    span corrente e o raiz ou um filho.

    Silencioso sem OTEL: um deployment sem telemetria continua servindo.
    """
    dims = {
        chave: str(valor)
        for chave, valor in (
            (ATTR_THREAD, thread_id), (ATTR_WORKSPACE, workspace),
            (ATTR_OID, oid), (ATTR_AGENT, agent),
        )
        if valor
    }
    if not dims:
        return
    _contexto().set(dims)

    # Também no span, quando houver um gravável: outras instrumentações
    # propagam o contexto, e aí o atributo viaja junto para o APM do cliente.
    try:
        from opentelemetry import trace
    except ImportError:
        return
    span = trace.get_current_span()
    if span is not None and getattr(span, "is_recording", lambda: False)():
        for chave, valor in dims.items():
            span.set_attribute(chave, valor)


# ── a ligação ───────────────────────────────────────────────────────────────


def otlp_endpoint() -> str:
    """O endpoint do APM de quem opera, ou vazio.

    Vazio é o caso NORMAL, não uma degradação: o cliente pode não ter APM, e o
    produto não perde nada — é o que o teste de aceitação #4 da spec verifica.
    """
    return (os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()


def setup_telemetry(
    *,
    sink: Callable[[Turn], None] | None = None,
    service_name: str = "dna-runtime",
    resource_attributes: Mapping[str, str] | None = None,
) -> Any | None:
    """Liga a instrumentação. Devolve o ``TracerProvider``, ou ``None``.

    ``None`` significa "não ligou", e nunca levanta: um deployment sem os
    pacotes de telemetria instalados deve **servir**, não crashar no boot. É a
    mesma assimetria de ``require_capabilities`` — ausência de medição é
    problema de operação, não negação de capacidade.

    Idempotente por baixo: chamar duas vezes não empilha dois provedores,
    porque o segundo ``set_tracer_provider`` do OpenTelemetry é ignorado com
    aviso.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
    except ImportError:
        _LOGGER.info(
            "telemetria desligada: instale o extra `otel` "
            "(dna-sdk[otel]) para registrar o que cada turno faz"
        )
        return None

    recursos = {"service.name": service_name, **(resource_attributes or {})}
    provider = TracerProvider(resource=Resource.create(recursos))

    if sink is not None:
        provider.add_span_processor(TurnRecorder(sink))

    destino = otlp_endpoint()
    if destino:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        except ImportError:
            # Configurou o endpoint e não tem o exportador. Avisa alto: é uma
            # intenção declarada que não está sendo cumprida, e o silêncio aqui
            # viraria "liguei o OTLP e não chega nada".
            _LOGGER.warning(
                "OTEL_EXPORTER_OTLP_ENDPOINT=%s definido, mas o exportador OTLP "
                "não está instalado — nada será exportado", destino
            )

    trace.set_tracer_provider(provider)
    _instrument_langchain(provider)
    return provider


def _instrument_langchain(provider: Any) -> None:
    """Instrumenta LangChain/LangGraph pela biblioteca OFICIAL.

    ``openinference-instrumentation-langchain`` (Arize) é a implementação de
    referência, e a regra não-negociável do produto manda usá-la em vez de
    escrever callbacks à mão. Ela é quem produz os atributos ``openinference.*``
    e ``gen_ai.*`` que o ``TurnRecorder`` lê.
    """
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
    except ImportError:
        _LOGGER.info(
            "openinference-instrumentation-langchain ausente: os spans do "
            "agente não serão produzidos (o provider OTEL está de pé)"
        )
        return
    try:
        LangChainInstrumentor().instrument(tracer_provider=provider)
    except Exception:  # noqa: BLE001 — instrumentar não pode derrubar o boot
        _LOGGER.warning("falha ao instrumentar o LangChain", exc_info=True)
