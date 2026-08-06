"""Walking the DERIVED reference graph — ``dna_edges``, one instance at a time.

The companion of :mod:`dna.kernel.query.references`: that module says what a
Kind DECLARES (``x-dna-ref``), this one answers what the instances actually
say to each other. The rows come from the write path — the same lookups
``WritePipeline._resolve_references`` performs to validate a reference also
record which Kind it resolved to — so nothing here derives, guesses or parses a
slug. It reads a fact somebody's write produced.

**Why the kernel and not the adapter alone.** The SQL is the adapter's (a
recursive CTE, identical on Postgres and SQLite). The POLICY is not: the depth
ceiling, the refusal to answer at all on a store that keeps no edges, and the
vocabulary the face renders — those belong where the registry lives.

**The refusal that matters most.** A store without an edge table does not
return an empty list. ``[]`` reads as "nothing points at this instance", which
is a claim only a store that actually records edges may make; the filesystem
adapter has neither a transaction to write edges in nor a table to write them
to, so the answer is :class:`GraphUnsupported` and the face says so. Serving a
confident empty answer from a store that cannot know is the fail-open silence
this codebase treats as a defect, not a convenience.

## ⭐ A instrumentação (fatia 0 de ``spec-topologia-do-grafo``)

A spec recomendou **ficar no Postgres** e nomeou **dois gatilhos MEDIDOS** que
invertem a recomendação. Um deles — o de ESCALA — não era mensurável: ninguém
conseguia dizer se `p95` de uma travessia `depth=3` já passou de 500 ms, nem em
que fração das chamadas `MAX_TRAVERSAL_ROWS` está sendo atingido. Este módulo
passou a responder as duas, e o desenho tem três restrições que valem mais que
a métrica:

**1. Custo zero desligada.** Nenhum relógio é lido, nenhum dicionário é montado
e nenhuma string é formatada quando o funil está desligado: :func:`traverse`
consulta ``logging.Logger.isEnabledFor`` UMA vez (uma comparação de inteiro
com cache do próprio stdlib) e, dando ``False``, o caminho quente é
byte-a-byte o de antes. O relógio passa por :data:`_clock` para que o teste
possa provar isso pelo negativo — ele o troca por algo que LEVANTA e exige que
a travessia desligada siga verde.

**2. Rótulo é de cardinalidade baixa, e nenhum identifica ninguém.** ``kind``,
``direction``, ``depth``, ``stop`` e ``producer`` são vocabulários fechados.
``name`` NÃO entra — é cardinalidade infinita e, num banco multi-tenant, o nome
de uma instância é conteúdo do cliente num log de operador. ``scope`` também
não: nenhum dos dois gatilhos precisa dele. ``tenant`` entra **balde**, um
blake2s de 4 bytes: dá para AGRUPAR as chamadas por tenant (o gatilho diz "no
maior tenant real", e sem agrupar só se responde a média de todos juntos) e não
dá para NOMEAR o tenant numa linha de log que o operador compartilha.

**3. O número CHEGA em alguém.** Métrica que ninguém lê é a mesma família de
"capacidade existe, porta não". A linha é uma só, marcada com
:data:`TRAVERSAL_MARK` e com um objeto JSON — legível a olho e parseável sem
biblioteca. Quem a transforma nos dois veredictos é :func:`traversal_stats`,
que mora **neste mesmo arquivo** de propósito: emissor e leitor que possam
divergir divergem, e um relatório de p95 calculado sobre um formato que mudou é
pior que nenhum. A porta humana é ``dna graph stats`` (lê arquivo ou stdin,
imprime o veredicto de cada gatilho, e com ``--gate`` sai 1 se algum disparou).

**Por que não OpenTelemetry Metrics, nem Prometheus.** Já existe telemetria
nesta casa — ``dna.runtime.telemetry`` — e ela foi lida antes de escrever isto:
são SPANS de TURNO de agente, ligados dentro de ``build_runtime`` e dependentes
do extra opcional ``otel``. O caminho de travessia não passa por ``build_runtime``
(a rota REST e o CLI não constroem runtime nenhum), então reusá-la exigiria
ligá-la num segundo lugar E tornar a fatia 0 dependente de um extra que o
deployment do ``api`` não instala. Um ``Meter`` do OTel também só vira número
legível com um coletor + um painel — infraestrutura nova, recorrente, para
responder duas perguntas que uma linha de log responde. A própria spec escreveu
"instrumentáveis hoje, **com uma linha de log**". **Zero dependência nova:
``logging``, ``json``, ``hashlib`` e ``time`` são stdlib.** No dia em que a
resposta precisar ser um painel contínuo em vez de duas perguntas com gatilho,
o registro estruturado já está lá para um handler OTLP consumir.

**O gatilho 1 (expressividade) não está aqui, e não podia estar.** Ele conta
FORMAS de pergunta, não chamadas: "duas rotas de travessia de forma diferente"
ou "o primeiro parâmetro que COMPÕE". Isso é a assinatura deste módulo, não o
tráfego — e por isso vira uma GUARDA, em
``tests/test_graph_telemetry.py::TestGatilho1Expressividade``, que fica vermelha
no dia em que uma segunda forma entrar. Ver :data:`TRIGGER_P95_MS`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

#: Default walk depth. ONE, on purpose: ``Spec.supersedes → Spec`` and
#: ``Story.dependencies → Story`` are self-referential by design, so an
#: unbounded default would be an incident waiting for the first cyclic board.
DEFAULT_DEPTH = 1

#: Ceiling the caller cannot raise. Overridable by the operator through
#: ``DNA_GRAPH_MAX_DEPTH`` — configuration, never request input.
DEFAULT_MAX_DEPTH = 5

# ── os LIMIARES do gatilho 2, escritos uma vez ──────────────────────────────
#
# Vêm literalmente de `spec-topologia-do-grafo` §10, GATILHO 2. Ficam aqui, e
# não no comando que imprime, porque o número que decide uma topologia não pode
# morar num `if` de apresentação: quem lê o emissor tem de ver o limiar.

#: A partir de qual ``depth`` uma travessia conta como PROFUNDA para o gatilho.
#: A spec diz ``depth=3``; medimos ``depth >= 3`` porque uma travessia de 4 ou 5
#: é mais cara que a de 3, e excluí-la esconderia o pior caso.
TRIGGER_DEPTH = 3

#: `p95` acima disto (em ms), nas travessias profundas, DISPARA o gatilho.
TRIGGER_P95_MS = 500.0

#: Fração de chamadas com ``stop="truncated"`` acima da qual o gatilho dispara.
#: 1% — a spec diz "mais de 1%", então a comparação é ESTRITA, e o teste mede
#: os dois lados de 0,01 para que trocar ``>`` por ``>=`` fique vermelho.
TRIGGER_TRUNCATED_RATIO = 0.01

# ── o funil: uma linha por travessia ────────────────────────────────────────

#: O logger. O NÍVEL DELE é a chave liga/desliga — nenhum mecanismo novo, e
#: ``isEnabledFor`` é o gate de custo zero que o stdlib já mantém com cache.
TRAVERSAL_LOGGER = "dna.graph.traversal"

#: A marca no início da mensagem. Existe porque o formato de log do host é dele,
#: não nosso: o nome do logger pode não sair na linha, e sem uma marca estável
#: no TEXTO não há como pescar estas linhas de um ``az containerapp logs show``.
TRAVERSAL_MARK = "dna.graph.traversal "

_TRAVERSAL_LOG = logging.getLogger(TRAVERSAL_LOGGER)

#: Indireção do relógio para que o teste do custo-zero possa provar, pelo
#: negativo, que o caminho desligado não o toca (ele o troca por algo que
#: levanta). Não é um ponto de extensão.
_clock = time.perf_counter


def _configure_from_env() -> None:
    """``DNA_GRAPH_TELEMETRY=on`` liga o funil — e garante que ele SAIA.

    Ligar o nível não basta e a diferença já custou caro nesta casa: sob
    ``uvicorn`` o logger raiz não tem handler, e um record INFO sem handler é
    descartado em silêncio (``logging.lastResort`` só atende WARNING+). O
    resultado seria a instrumentação "ligada" e nenhum número em lugar nenhum —
    capacidade existe, porta não. Então, e SÓ quando ninguém mais está ouvindo
    (:meth:`~logging.Logger.hasHandlers`), este funil ganha o seu próprio
    handler para ``stderr``, que é o que o container coleta.

    ⚠️ ``stderr`` e NÃO ``stdout``, por um motivo medido no smoke: ``dna graph
    refs --json`` escreve o resultado em stdout, e uma linha de telemetria no
    meio dele quebraria o ``| jq`` de quem consome a saída. Observar não pode
    estragar o observado — nem o que ele responde, nem o canal por onde responde.

    Lido uma vez, no import: o custo por travessia tem de ser zero, e um
    ``os.environ`` por chamada não é zero. Quem quiser mexer ao vivo mexe pelo
    caminho normal do stdlib (``logging.getLogger(TRAVERSAL_LOGGER).setLevel``),
    que continua valendo e é justamente por isso que não há chave própria.
    """
    raw = os.environ.get("DNA_GRAPH_TELEMETRY", "").strip().lower()
    if raw not in ("1", "on", "true", "yes"):
        return
    _TRAVERSAL_LOG.setLevel(logging.INFO)
    if not _TRAVERSAL_LOG.hasHandlers():
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        _TRAVERSAL_LOG.addHandler(handler)
        # Nós passamos a ser o emissor desta linha; propagar para uma raiz que
        # ganhe handlers depois duplicaria a mesma travessia no relatório.
        _TRAVERSAL_LOG.propagate = False


_configure_from_env()


def traversal_logging_enabled() -> bool:
    """O funil está ligado? Uma comparação de inteiro, com cache do stdlib."""
    return _TRAVERSAL_LOG.isEnabledFor(logging.INFO)


def tenant_bucket(tenant: str | None) -> str:
    """Um BALDE do tenant — agrupa sem nomear.

    O gatilho 2 fala "no maior tenant real", o que exige agrupar as chamadas
    por tenant; um log de operador não pode carregar o identificador do cliente.
    blake2s de 4 bytes resolve os dois: estável entre processos e réplicas (o
    mesmo tenant cai sempre no mesmo balde, então o `p95` por tenant fecha) e
    não é o nome. ``-`` para as chamadas sem tenant, que é a maioria do board.

    ⚠️ Isto é PSEUDONIMIZAÇÃO, não anonimização: quem já tem a lista de tenants
    pode re-derivar os baldes. É o suficiente para o que este log é — um
    artefato operacional — e não é um mecanismo de privacidade.
    """
    if not tenant:
        return "-"
    return hashlib.blake2s(tenant.encode("utf-8"), digest_size=4).hexdigest()


def _emit_traversal(
    *, kind: str, direction: str, depth: int, stop: str, edges: int,
    ms: float, producer: str, tenant: str | None,
) -> None:
    """Uma linha, marcada e em JSON. Só chamada com o funil ligado.

    O mesmo objeto viaja em ``extra["dna_graph"]``, para que um handler que já
    emita JSON estruturado leia os campos sem re-parsear o texto.
    """
    record = {
        "kind": kind,
        "dir": direction,
        "depth": depth,
        "stop": stop,
        "edges": edges,
        "ms": round(ms, 1),
        "producer": producer,
        "tenant": tenant_bucket(tenant),
    }
    _TRAVERSAL_LOG.info(
        "%s%s", TRAVERSAL_MARK,
        json.dumps(record, sort_keys=True, separators=(",", ":")),
        extra={"dna_graph": record},
    )


class GraphUnsupported(RuntimeError):
    """The active source keeps no derived edge graph, so there is no answer.

    Deliberately an exception and not an empty result: see the module
    docstring. The faces translate it into an explicit ``unsupported``
    capability, never into a list.
    """


def max_depth() -> int:
    """The traversal ceiling, read per call so an operator can change it live."""
    raw = os.environ.get("DNA_GRAPH_MAX_DEPTH", "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_DEPTH
    return value if 1 <= value <= 50 else DEFAULT_MAX_DEPTH


def producer_mode() -> str:
    """How the edge PRODUCER is configured — ``warn`` / ``enforce`` / ``off``.

    Reported alongside every traversal because ``DNA_REF_VALIDATION=off`` skips
    the reference lookups entirely, so no edges are produced. That is a
    defensible operational choice; a screen rendering the resulting emptiness
    as "no relations" is not. Same shape as the degree-0 ``as_of_reads`` /
    ``as_of_truncated`` capability flags.
    """
    mode = os.environ.get("DNA_REF_VALIDATION", "warn").strip().lower()
    return mode if mode in ("enforce", "warn", "off") else "warn"


@dataclass(frozen=True)
class GraphResult:
    """One traversal, with the reason it stopped where it did.

    ``stop`` is not decoration. A caller that cannot tell "this is everything"
    from "this is where I gave up" will render the second as the first.
    """

    edges: list[dict[str, Any]] = field(default_factory=list)
    direction: str = "in"
    depth: int = DEFAULT_DEPTH
    #: ``complete`` | ``depth_reached`` | ``truncated``
    stop: str = "complete"
    #: The producer's configured mode — see :func:`producer_mode`.
    graph_producer: str = "warn"

    @property
    def dangling(self) -> list[dict[str, Any]]:
        """Edges that resolve to nothing — the list of what is broken."""
        return [e for e in self.edges if not e.get("resolved")]


def _clamp_depth(depth: int | None) -> int:
    if depth is None:
        return DEFAULT_DEPTH
    try:
        value = int(depth)
    except (TypeError, ValueError):
        return DEFAULT_DEPTH
    return max(1, min(value, max_depth()))


async def traverse(
    source: Any, scope: str, kind: str, name: str, *,
    tenant: str | None = None,
    direction: str = "in",
    depth: int | None = None,
) -> GraphResult:
    """Walk ``source``'s edge graph from one instance.

    ``direction``: ``in`` (what points at this — the product question),
    ``out`` (what this points at), ``both``.

    Raises :class:`GraphUnsupported` when the source declares no edge graph.

    **Este é o ÚNICO ponto medido, e é de propósito.** A rota REST, o comando
    ``dna graph refs`` e a face MCP passam todos por ``Kernel.graph_refs``, que
    é uma fachada fina sobre esta função — instrumentar aqui alcança as três
    portas de uma vez, inclusive a que ninguém lembrar de instrumentar. Ver o
    docstring do módulo para o desenho e para o que NÃO é registrado.
    """
    from dna.kernel.capabilities import source_capabilities

    if direction not in ("in", "out", "both"):
        raise ValueError(
            f"direction must be 'in', 'out' or 'both' (got {direction!r})"
        )
    caps = source_capabilities(source)
    if not caps.edge_graph:
        raise GraphUnsupported(
            f"the active source ({caps.source}) does not record the derived "
            f"reference graph, so it cannot answer what points at "
            f"{kind}/{name}. This is not the same as 'nothing points at it' — "
            f"run against an adapter that declares edge_graph (the SQL "
            f"adapter, on either dialect) to get a real answer."
        )
    effective = _clamp_depth(depth)
    # Desligado, esta é a ÚNICA linha a mais no caminho quente: uma comparação
    # de nível. Nenhum relógio é lido — `_clock` fica intocado abaixo.
    observing = traversal_logging_enabled()
    started = _clock() if observing else 0.0
    rows = await source.traverse_edges(
        scope, kind, name,
        tenant=tenant, direction=direction, depth=effective,
    )
    deepest = max((int(r.get("depth", 1)) for r in rows), default=0)
    stop = "depth_reached" if deepest >= effective else "complete"
    if len(rows) >= getattr(source, "MAX_TRAVERSAL_ROWS", 10**9):
        # The walk hit the adapter's row ceiling: what came back is a PREFIX of
        # the answer, and saying "complete" here would be the graph's version
        # of a truncated list rendered as a full one.
        stop = "truncated"
    producer = producer_mode()
    if observing:
        # O `stop` não é derivado de novo para o log: é o MESMO valor que a
        # resposta carrega. Duas contas do mesmo fato divergem, e a taxa de
        # truncamento do relatório tem de ser a do que o cliente recebeu.
        _emit_traversal(
            kind=kind, direction=direction, depth=effective, stop=stop,
            edges=len(rows), ms=(_clock() - started) * 1000.0,
            producer=producer, tenant=tenant,
        )
    return GraphResult(
        edges=rows, direction=direction, depth=effective, stop=stop,
        graph_producer=producer,
    )


# ── o LEITOR: das linhas para os dois veredictos ────────────────────────────


def parse_traversal_line(line: str) -> dict[str, Any] | None:
    """Uma linha de log → o registro, ou ``None`` se ela não for nossa.

    Tolerante por desenho: a entrada real é a saída de ``az containerapp logs
    show``/``docker logs``, onde cada linha vem prefixada por carimbo de tempo,
    nome de container e nível. Achamos a marca, e o JSON começa na primeira
    ``{`` depois dela.
    """
    at = line.find(TRAVERSAL_MARK)
    if at < 0:
        return None
    brace = line.find("{", at + len(TRAVERSAL_MARK) - 1)
    if brace < 0:
        return None
    try:
        record = json.loads(line[brace:])
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def percentile(values: list[float], q: float) -> float:
    """Percentil por RANK MAIS PRÓXIMO, sem interpolação e sem dependência.

    ``ceil(q * n)``-ésimo valor da lista ordenada. Escolhido em vez da
    interpolação linear (o default do ``numpy``) porque devolve sempre um valor
    OBSERVADO: um `p95` de 500,4 ms que nenhuma chamada levou é um número que
    ninguém consegue ir procurar no log. ``0.0`` para lista vazia.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return float(ordered[min(rank, len(ordered)) - 1])


def traversal_stats(lines: Iterable[str]) -> dict[str, Any]:
    """As linhas → os dois números do gatilho 2, e o veredicto de cada um.

    Não filtra nada em silêncio: ``ignored`` conta as linhas que não eram
    nossas e ``calls`` as que eram, para que um relatório feito sobre o arquivo
    errado se denuncie em vez de imprimir ``p95 = 0`` e um "não disparou".
    """
    calls: list[Mapping[str, Any]] = []
    ignored = 0
    for line in lines:
        record = parse_traversal_line(line)
        if record is None:
            ignored += 1
            continue
        calls.append(record)

    total = len(calls)
    truncated = sum(1 for r in calls if r.get("stop") == "truncated")
    ratio = (truncated / total) if total else 0.0

    deep = [float(r.get("ms", 0.0)) for r in calls
            if int(r.get("depth", 0) or 0) >= TRIGGER_DEPTH]
    deep_p95 = percentile(deep, 0.95)

    # Por balde de tenant, porque o gatilho fala "no maior tenant real": um
    # tenant lento e pequeno some no p95 global de todo mundo junto.
    per_tenant: dict[str, list[float]] = {}
    for r in calls:
        if int(r.get("depth", 0) or 0) >= TRIGGER_DEPTH:
            per_tenant.setdefault(str(r.get("tenant", "-")), []).append(
                float(r.get("ms", 0.0))
            )
    tenants = sorted(
        (
            {"tenant": bucket, "calls": len(v), "p95_ms": percentile(v, 0.95)}
            for bucket, v in per_tenant.items()
        ),
        key=lambda t: (-t["p95_ms"], t["tenant"]),
    )
    worst = tenants[0] if tenants else None
    worst_p95 = worst["p95_ms"] if worst else 0.0

    by_depth: dict[str, int] = {}
    for r in calls:
        by_depth[str(r.get("depth"))] = by_depth.get(str(r.get("depth")), 0) + 1

    # ⚠️ ESTRITAMENTE maior, nos dois. A spec diz "acima de 500 ms" e "mais de
    # 1%"; um `>=` faria a chamada que bate exatamente no limiar disparar uma
    # migração de topologia.
    p95_fired = max(deep_p95, worst_p95) > TRIGGER_P95_MS
    trunc_fired = ratio > TRIGGER_TRUNCATED_RATIO

    return {
        "calls": total,
        "ignored": ignored,
        "by_depth": by_depth,
        "p95_ms": percentile([float(r.get("ms", 0.0)) for r in calls], 0.95),
        "deep": {
            "depth_min": TRIGGER_DEPTH,
            "calls": len(deep),
            "p95_ms": deep_p95,
        },
        "tenants": tenants,
        "worst_tenant": worst,
        "truncated": truncated,
        "truncated_ratio": ratio,
        "triggers": {
            "scale_p95": {
                "fired": p95_fired,
                "value_ms": max(deep_p95, worst_p95),
                "threshold_ms": TRIGGER_P95_MS,
                "basis": (
                    f"p95 das travessias depth>={TRIGGER_DEPTH}, global e no "
                    f"pior balde de tenant"
                ),
            },
            "scale_truncated": {
                "fired": trunc_fired,
                "value": ratio,
                "threshold": TRIGGER_TRUNCATED_RATIO,
                "basis": "fração das chamadas com stop='truncated'",
            },
        },
        "fired": p95_fired or trunc_fired,
    }
