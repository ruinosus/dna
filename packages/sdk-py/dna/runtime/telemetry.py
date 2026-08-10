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

## ⚠️ O que o turno CONSEGUIU, e o que ele CUSTOU — duas perguntas diferentes

``status`` responde *"estourou exceção?"*, e só isso. Ele foi lido como se
respondesse *"resolveu?"*, que é a pergunta do negócio, e as duas divergem: um
turno pode terminar sem exceção nenhuma e não ter resolvido coisa alguma.

Por isso ``outcome`` (``resolved``/``escalated``/``abandoned``), e por isso ele
é **declarado, nunca inferido**. Vazio significa DESCONHECIDO — jamais
``resolved``. Um desfecho inferido do ``status`` seria exatamente o zero
fabricado que este produto proíbe, com a agravante de inclinar a conta a favor
do agente: todo turno sem exceção viraria "sucesso".

## ⚠️ O ZERO de tokens também tem dois significados, e um deles é mentira

MEDIDO em 07/08/2026, contra os 85 turnos do Postgres de desenvolvimento. A
hipótese registrada na spec era *"8 dos 9 turnos com erro não gravam os tokens
que consumiram"* — um defeito de escrita, que se consertaria gravando no
caminho de exceção. **A medição desmentiu a hipótese**, e a correção é outra.

``model`` e ``input_tokens`` são escritos pelo MESMO lugar (``_llm``), e no
banco inteiro eles andam juntos: ``model = ''`` ⟺ ``input_tokens = 0``, em 9 de
9 linhas. Modelo vazio prova que **nenhum span de LLM chegou ao recorder** —
não que o token se perdeu no caminho. Sete daqueles turnos morreram em 7–32 ms,
antes de qualquer chamada ao modelo (401 no carregamento das tools,
``CancelledError``). Para eles o zero é a MEDIÇÃO CERTA, e o turno que somou
5.662 tokens antes de morrer de ``DiskFull`` prova que a acumulação já
sobrevivia à exceção.

Sobra um caso, e é o real: o turno que chamou o modelo e cuja chamada
**estourou**. O ``openinference`` monta os atributos com
``_token_counts(run.outputs)``, e numa run que errou ``run.outputs`` é ``None``
— então sai ``llm.model_name`` (que ele lê do ``extra``, carimbado na largada)
e NENHUM contador. O provedor cobrou o prompt; o span não sabe quanto.

Contar de novo por conta própria seria estimar, e estimativa aqui é o zero
fabricado com outra roupa. Então o registro passa a dizer **qual dos dois zeros
ele é**, via ``tokens_partial``:

``False``
    a conta está fechada — toda chamada ao modelo reportou seu uso, inclusive o
    caso de nenhuma chamada (zero chamadas, zero tokens, medição correta);
``True``
    pelo menos uma chamada terminou sem reportar uso. ``input_tokens`` é um
    **piso**, não a conta.

Um ROI que soma tokens sem olhar esta coluna continua subestimando o custo — a
diferença é que agora ele tem como saber que está.

## ⭐ E de QUE RAIA o turno é: ``lane`` (``i-158``)

*"Uma coisa é conversa de teste, outra é conversa real."* Um turno gerado por
uma suíte de avaliação, um smoke, ou um agente exercitando o produto **existe**
— consumiu tokens de verdade, e o provedor cobrou — mas ele não é uso. Somá-lo
à conta do cliente é a mesma classe de erro que ``outcome`` inferido do
``status``: um número certo respondendo a outra pergunta.

MEDIDO em 08/08/2026 no Postgres de desenvolvimento: **86 turnos, 76 do mesmo
copiloto, TODOS gerados por agente durante desenvolvimento e nenhum de uso
real.** Nenhuma coluna dizia isso, e por isso o painel da conta somava os 86.

``lane`` mora AQUI, em ``dna_turn``, e não numa tabela do host, por uma razão
que decide sozinha: **quem precisa excluir o turno de teste da conta é
:mod:`dna.runtime.roi`, que é deste SDK.** Uma raia que vivesse só no índice de
conversas do host seria invisível para o leitor que a consome, e cada
consumidor do SDK reinventaria a exclusão por conta própria — que é como um
invariante vira convenção e depois vira bug. ``thread_id`` também pode ser
vazio (turno de A2A, de worker), e uma raia presa à conversa não cobriria esses.

Três estados, e o terceiro é o que mais importa:

``"real"``
    uso de verdade. **Só quem declara.**
``"test"``
    exercício: suíte de avaliação, smoke, demonstração.
``""`` (vazio)
    ⭐ **NÃO DECLARADA — e isto não é "real" nem "test".** Os 86 turnos
    existentes são assim e continuam assim: um backfill para ``real`` afirmaria
    que aquilo foi uso de cliente (é o oposto do que foi medido), e um backfill
    para ``test`` difamaria qualquer turno que porventura fosse real. É a mesma
    decisão que a 0012 tomou sobre ``outcome``, e pelo mesmo motivo. Quem lê a
    conta tem de DIZER quantos são — ver
    :attr:`dna.runtime.roi.Sample.undeclared_lane`.

Como o desfecho, a raia é DECLARADA (:func:`stamp_turn`) e um valor fora de
:data:`LANES` é recusado, deixando o turno vazio. E como o desfecho, ela é
**apagada no início de cada turno** — porque o estrago tem direção: uma raia
``test`` herdada por um turno de gente de verdade sumiria com uso REAL da conta,
em silêncio. Um host que esqueça de recarimbar produz turnos NÃO DECLARADOS, que
a conta mostra; jamais turnos ``real`` que ninguém declarou.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

_LOGGER = logging.getLogger("dna.runtime.telemetry")

__all__ = [
    "LANES",
    "LANE_REAL",
    "LANE_TEST",
    "MAX_TEXT",
    "OUTCOMES",
    "TRUNCATION_MARK",
    "Turn",
    "TurnStep",
    "TurnRecorder",
    "clip",
    "otlp_endpoint",
    "setup_telemetry",
    "stamp_outcome",
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
ATTR_OUTCOME = "dna.outcome"
ATTR_LANE = "dna.lane"

#: Uso de verdade. ⚠️ **Só quem DECLARA.** Um turno que não diz nada não é
#: real — é de raia desconhecida, que é uma terceira coisa.
LANE_REAL = "real"

#: Exercício: suíte de avaliação, smoke, demonstração. O turno aconteceu e
#: custou; ele só não é uso.
LANE_TEST = "test"

#: As únicas raias que existem. Um valor fora desta lista é RECUSADO e o turno
#: fica vazio — a mesma disciplina de :data:`OUTCOMES`, e pelo mesmo motivo:
#: aceitar o valor estranho o faria aparecer numa contagem que não sabe o que
#: ele significa. ⚠️ E vazio NÃO é um membro desta lista de propósito: ele é a
#: ausência de declaração, e um default aqui a transformaria numa declaração.
LANES = frozenset({LANE_REAL, LANE_TEST})

#: Os únicos desfechos que existem. Um valor fora desta lista é RECUSADO e o
#: turno fica vazio — porque vazio é "não sei", e "não sei" é a verdade sobre um
#: desfecho que ninguém soube declarar. Aceitar o valor estranho o faria
#: aparecer numa contagem que não sabe o que ele significa.
OUTCOMES = frozenset({"resolved", "escalated", "abandoned"})

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
    #: ``True`` = alguma chamada ao modelo não reportou uso, e ``input_tokens``
    #: é um PISO. Ver o aviso "o ZERO de tokens tem dois significados" no topo.
    #: Começa ``False``: um turno sem chamada nenhuma tem a conta fechada em
    #: zero, e isso é uma medição, não uma ausência.
    tokens_partial: bool = False
    status: str = "ok"
    #: ⭐ O que o turno CONSEGUIU — declarado por quem fecha, nunca inferido.
    #: Vazio é DESCONHECIDO. Nada neste módulo o transforma em ``resolved``.
    outcome: str = ""
    #: ⭐ De que RAIA este turno é: ``real``, ``test``, ou vazio (`i-158`).
    #: Vazio é NÃO DECLARADA — e não é nenhuma das duas. Nada neste módulo o
    #: transforma em ``real``; ver a seção da raia no topo.
    lane: str = ""
    error: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int = 0
    steps: list[TurnStep] = field(default_factory=list)


def _attrs(span: Any) -> Mapping[str, Any]:
    return getattr(span, "attributes", None) or {}


def _desfecho(fonte: Mapping[str, Any]) -> str:
    """O desfecho declarado nesta fonte, ou ``""``.

    ⭐ **É a única porta pela qual um desfecho entra num ``Turn``**, e ela só
    deixa passar o que está em ``OUTCOMES``. Qualquer outra coisa — ``"ok"``,
    ``"sucesso"``, ``True``, um typo — sai como vazio.

    O que a função NÃO faz é o ponto: ela não olha ``status``, não tem
    fallback, e não tem um "se não disseram, assuma que deu certo". Um desfecho
    presumido pareceria uma declaração e contaria como uma, e a conta que ele
    alimenta é justamente a de quanto o agente resolveu sozinho.
    """
    valor = fonte.get(ATTR_OUTCOME)
    if valor is None:
        return ""
    texto = str(valor).strip().lower()
    if texto in OUTCOMES:
        return texto
    if texto:
        _LOGGER.warning(
            "desfecho %r não é um de %s — o turno fica DESCONHECIDO",
            valor, sorted(OUTCOMES),
        )
    return ""


def _raia(fonte: Mapping[str, Any]) -> str:
    """A raia declarada nesta fonte, ou ``""`` (`i-158`).

    ⭐ **É a única porta pela qual uma raia entra num ``Turn``**, e ela só deixa
    passar o que está em :data:`LANES`. Um valor fora — ``"testing"``,
    ``"prod"``, ``True``, um typo — sai como vazio.

    O gêmeo de :func:`_desfecho`, e deliberadamente escrito ao lado dele: as
    duas recusam pelo mesmo motivo, e uma delas escrita mais frouxa seria a que
    deixaria entrar o valor que ninguém sabe contar.
    """
    valor = fonte.get(ATTR_LANE)
    if valor is None:
        return ""
    texto = str(valor).strip().lower()
    if texto in LANES:
        return texto
    if texto:
        _LOGGER.warning(
            "raia %r não é uma de %s — o turno fica NÃO DECLARADO",
            valor, sorted(LANES),
        )
    return ""


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

    #: Quantas traces já entregues ficam lembradas, para reconhecer um span
    #: atrasado em vez de ressuscitar a trace como um turno fantasma. Teto
    #: pequeno de propósito: o atraso, quando existe, é de milissegundos.
    LEMBRAR_FECHADAS = 256

    def __init__(self, sink: Callable[[Turn], None]) -> None:
        self._sink = sink
        self._abertos: dict[str, Turn] = {}
        # `dict` e não `set`: a ordem de inserção é o que permite descartar a
        # mais antiga quando o teto estoura, sem carregar um LRU inteiro.
        self._fechadas: dict[str, None] = {}

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
        self._fechadas.clear()

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

        # ⚠️ Um span ATRASADO, de uma trace que já foi entregue, não pode
        # recriar a trace. O `setdefault` abaixo o faria: nasceria um `Turn`
        # com o mesmo `turn_id`, sem raiz para fechá-lo, preso em `_abertos`
        # para sempre. Dois estragos, e o segundo é silencioso — um vazamento
        # de memória num processo que roda por semanas, cujo tamanho é o número
        # de traces que já passaram.
        if trace_id in self._fechadas:
            _LOGGER.debug(
                "span atrasado para a trace %s, já entregue — ignorado", trace_id
            )
            return

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
        elif kind == "LLM":
            self._llm(turno, atributos)

        # Sem `parent`, este é o span RAIZ: o turno inteiro. É aqui que ele
        # fecha — e é por isso que um processo que morre não deixa registro
        # pela metade, e sim registro nenhum.
        #
        # ⚠️ Este teste é feito para TODO span, e não só para os que não são
        # TOOL/LLM. Os dois ramos acima faziam `return`, e um span raiz que
        # fosse ELE MESMO um LLM — uma invocação direta do modelo, sem chain
        # em volta — somava os tokens e nunca fechava: o turno inteiro sumia,
        # tokens e tudo. Somar e fechar são coisas independentes, e tratá-las
        # em sequência é o que torna a raiz-LLM um caso e não uma exceção.
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
        entrada = _primeiro(atributos, ATTR_INPUT_TOKENS)
        saida = _primeiro(atributos, ATTR_OUTPUT_TOKENS)
        turno.input_tokens += int(entrada or 0)
        turno.output_tokens += int(saida or 0)
        if not turno.model:
            turno.model = str(_primeiro(atributos, ATTR_MODEL) or "")

        # ⚠️ Nenhum contador presente = uma chamada ao modelo cujo uso NINGUÉM
        # sabe. É o que o `openinference` produz quando a run estourou
        # (`_token_counts(run.outputs)` com `outputs is None`), e o provedor
        # cobrou o prompt do mesmo jeito. Somar zero aqui e calar é o que fazia
        # o turno caro parecer barato.
        if entrada is None and saida is None:
            turno.tokens_partial = True

    @staticmethod
    def _consumir_desfecho() -> None:
        """Tira o desfecho do contexto, para que ele não conte duas vezes."""
        var = _contexto()
        atual = var.get()
        if atual and ATTR_OUTCOME in atual:
            var.set({k: v for k, v in atual.items() if k != ATTR_OUTCOME})

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
        # ⭐ DECLARADO ou vazio — nunca derivado do `status`. As duas fontes são
        # as mesmas das dimensões, e pela mesma razão; o que não existe em
        # nenhuma delas fica vazio, que é como se escreve "não sei".
        turno.outcome = _desfecho(_contexto().get() or {}) or _desfecho(atributos)
        # ⭐ A RAIA, pelas mesmas duas fontes e com a mesma recusa (`i-158`).
        # Quem impede a herança de uma raia para o turno seguinte é `stamp_turn`,
        # que a apaga ao abrir cada turno — a razão está escrita lá.
        turno.lane = _raia(_contexto().get() or {}) or _raia(atributos)
        # ⚠️ E o desfecho é CONSUMIDO: uma declaração vale por UM turno.
        #
        # `stamp_turn` já limpa o desfecho ao abrir o turno seguinte, e isto
        # aqui é a mesma garantia pelo outro lado — a que não depende de o host
        # ter lembrado de carimbar. As duas juntas fecham a herança nos dois
        # sentidos, e é a herança que transformaria "não sei" em `resolved`.
        self._consumir_desfecho()
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
        self._fechadas[trace_id] = None
        while len(self._fechadas) > self.LEMBRAR_FECHADAS:
            self._fechadas.pop(next(iter(self._fechadas)))
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
    lane: str | None = None,
) -> None:
    """Carimba as dimensoes do produto no span CORRENTE.

    Quem as conhece e o host — elas chegam nos cabecalhos da requisicao, que o
    SDK nao le. Chame de dentro do turno (um middleware `before_agent` serve);
    o `TurnRecorder` as colhe de qualquer span da trace, entao nao importa se o
    span corrente e o raiz ou um filho.

    ⚠️ **Tambem marca o INICIO do turno, e por isso APAGA o desfecho anterior**
    — ver o comentario abaixo. Um host que carimbe uma vez por processo em vez
    de uma vez por turno perde essa protecao; carimbe por turno.

    ``lane`` é a RAIA (`i-158`): ``"real"``, ``"test"``, ou nada. ⚠️ **Nada não
    é ``real``** — é raia NÃO DECLARADA, e é o default de propósito: um host que
    nunca ouviu falar de raia continua produzindo turnos honestamente
    indefinidos em vez de turnos que se dizem de produção. Um valor fora de
    :data:`LANES` é RECUSADO com aviso e o turno segue sem raia.

    Silencioso sem OTEL: um deployment sem telemetria continua servindo.
    """
    # ⚠️ Carimbar o turno APAGA o desfecho do turno anterior, e esta linha é a
    # única coisa entre o produto e um número inflado.
    #
    # A `ContextVar` é por-task, e uma task serve VÁRIOS turnos da mesma
    # conversa. Sem esta limpeza, um turno que declarou `resolved` deixaria o
    # valor no contexto, e o PRÓXIMO turno — que não declarou nada, e cujo
    # desfecho é honestamente desconhecido — o herdaria. Vazio viraria
    # `resolved` sem ninguém declarar, silenciosamente, e a taxa de resolução
    # só subiria: uma vez que um turno resolvesse, todos os seguintes daquela
    # conversa contariam como resolvidos.
    #
    # `stamp_turn` é o marco de INÍCIO do turno (o middleware `before_agent` a
    # chama), então é aqui que o desfecho anterior morre.
    #
    # ⭐ E a RAIA morre junto, pela mesma razão e na direção que importa
    # (`i-158`): sem esta limpeza, uma suíte de avaliação que declarasse `test`
    # deixaria a raia no contexto, e o turno seguinte da mesma task — de um
    # usuário de verdade — a herdaria. A conta do cliente perderia turnos que
    # aconteceram, e perderia CALADA. O erro simétrico (um turno de teste que
    # perde a marca e conta como uso) é o que a linha abaixo previne quando o
    # host esquece de recarimbar: ele vira NÃO DECLARADO, que é visível, em vez
    # de `real`, que não é.
    var = _contexto()
    contexto = {
        k: v for k, v in (var.get() or {}).items()
        if k not in (ATTR_OUTCOME, ATTR_LANE)
    }
    var.set(contexto)

    _carimbar({
        chave: str(valor)
        for chave, valor in (
            (ATTR_THREAD, thread_id), (ATTR_WORKSPACE, workspace),
            (ATTR_OID, oid), (ATTR_AGENT, agent),
            # ⚠️ A raia passa pela MESMA recusa da leitura (`_raia`): um
            # `lane="prod"` não vira dimensão nenhuma, e o aviso sai aqui, na
            # chamada de quem errou — não no `on_end`, longe do erro.
            (ATTR_LANE, _raia({ATTR_LANE: lane}) if lane else None),
        )
        if valor
    })
    if lane and not _raia({ATTR_LANE: lane}):
        # `_raia` já avisou QUAL valor caiu; esta linha diz a CONSEQUÊNCIA, que
        # é a metade que muda o que alguém faz a respeito.
        _LOGGER.warning(
            "o turno segue com raia NÃO DECLARADA — ele NÃO vira %r", LANE_REAL,
        )


def stamp_outcome(outcome: str) -> None:
    """Declara O QUE ESTE TURNO CONSEGUIU: ``resolved``/``escalated``/``abandoned``.

    ⭐ **O seam de escrita do desfecho, e ele é declarativo por desenho.** Quem
    sabe se o turno resolveu é quem conhece o trabalho — um nó do grafo que
    fechou o ticket, uma tool de escalada, o handler que viu o usuário desistir.
    O runtime não sabe, e esta função é como ele fica sabendo.

    **Se ninguém chamar, o turno fica vazio, e vazio significa DESCONHECIDO.**
    Isso é o comportamento certo, não uma lacuna a tapar depois: a alternativa
    — presumir ``resolved`` para todo turno sem exceção — produziria uma taxa
    de resolução que mede a ausência de crashes e se apresenta como medida de
    valor entregue.

    Um valor fora de ``OUTCOMES`` é RECUSADO com aviso, e o turno segue vazio.

    Chame de dentro do turno, como ``stamp_turn``; vale a última chamada, então
    um passo posterior pode corrigir o que um anterior declarou. Silenciosa sem
    OTEL — um deployment sem telemetria continua servindo.
    """
    texto = str(outcome or "").strip().lower()
    if texto not in OUTCOMES:
        if texto:
            # Vazio não avisa: declarar "não sei" é legítimo, e é o default.
            # O que merece aviso é o valor que ALGUÉM quis dizer e não existe.
            _LOGGER.warning(
                "desfecho %r recusado (esperado um de %s) — o turno fica DESCONHECIDO",
                outcome, sorted(OUTCOMES),
            )
        return
    _carimbar({ATTR_OUTCOME: texto})


def _carimbar(dims: Mapping[str, str]) -> None:
    """Funde ``dims`` no contexto do turno e no span corrente.

    ⚠️ **Funde, não substitui.** Um ``set`` do dicionário inteiro faria a
    segunda chamada apagar o que a primeira carimbou — e como ``stamp_outcome``
    naturalmente roda DEPOIS de ``stamp_turn`` (o desfecho só se sabe no fim),
    substituir zeraria thread, workspace e oid justamente no turno que teve
    desfecho declarado: o registro melhor viraria o registro órfão.
    """
    if not dims:
        return
    var = _contexto()
    var.set({**(var.get() or {}), **dims})

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
