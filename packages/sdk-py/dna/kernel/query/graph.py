"""Walking the DERIVED reference graph — ``dna_edges``, one instance at a time.

The companion of :mod:`dna.kernel.query.references`: that module says what a
Kind DECLARES (``x-dna-ref``), this one answers what the instances actually
say to each other. The rows come from the write path — the same lookups
``WritePipeline._resolve_references`` performs to validate a reference also
record which Kind it resolved to — so nothing here derives, guesses or parses a
slug. It reads a fact somebody's write produced.

**And a fact somebody's DELETE produced (i-131).** ``resolved`` used to be
``to_kind IS NOT NULL``, which is a fact about the WRITE — *"the reference
found a target"* — served as a fact about the READ — *"this still points at
something"*. Deleting the target left the edge in place, correctly, saying
``resolved: true`` about an instance that no longer existed. The fix keeps this
module free of derivation: the delete stamps ``to_deleted_at`` on the incoming
edges in its own transaction, so the traversal still only reports what a write
recorded. Recomputing here instead would have meant a second resolution rule
beside ``Kernel.get_instance``'s parent-scope fallback — see the 0011
revision's docstring for the measurement that killed it.

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

## ⭐ ``as_of`` — o grafo COMO ELE ERA em T (fatia 4 de ``spec-topologia-do-grafo``)

O quarto eixo da MESMA pergunta: *de onde* (``kind``/``name``), *para que lado*
(``direction``), *até onde* (``depth``) e agora **quando** (``as_of``). Uma
rota, uma forma, quatro coordenadas — ver :data:`TRAVERSAL_QUESTION_PARAMS`,
onde o gatilho 1 foi CONTADO em vez de contornado.

**A medição que decidiu o desenho, e ela derrubou a leitura óbvia.** A leitura
óbvia era filtrar ``dna_edges`` por ``from_version``: a coluna existe desde a
revisão 0006 e o comentário do schema já a chamava de *"the anchor a future
as-of traversal needs"*. Medido no banco do dna-cloud em 07/08/2026:

```
arestas                                              33
from_version = 0 (backfill, proveniência ignorada)    0
from_version < versão atual da instância (STALE)      0   ← ⭐
```

**Zero.** Não porque o grafo esteja fresco, e sim porque uma linha stale **não
pode existir**: ``_replace_edges`` APAGA e reinsere o conjunto inteiro a cada
escrita, então ``from_version`` é sempre a versão de hoje. A tabela de arestas
não tem história por CONSTRUÇÃO, e filtrá-la por tempo devolveria o presente
com um carimbo do passado — exatamente a mentira confiante que ``as_of`` existe
para recusar.

O que ``from_version`` de fato é: a **testemunha da qual versão produziu estas
arestas**. Ela não guarda o passado, ela DIZ de qual instante o presente fala —
e é por isso que toda linha devolvida por uma travessia ``as_of`` também a
carrega, valendo então a versão que a instância tinha **em T**.

**Então a travessia ``as_of`` RE-DERIVA.** ``dna_versions.content`` guarda o
envelope INTEIRO por escrita (não um diff, não um ponteiro) desde a revisão
0001 — a mesma observação que fez o ``as_of`` de instância não precisar de
coluna nova. Reconstrói-se o estado que o store acreditava em T e caminha-se
sobre ele com a MESMA política: mesmo teto de profundidade, mesmo anti-ciclo,
mesmo vocabulário de ``stop``. **Nenhuma migração**: 0012 chegou a ser cogitada
e não existe, porque não há coluna nova a criar.

**Procuramos antes de construir, e o resultado foi "quase nada, mas o desenho
existe".** Nenhuma biblioteca Python faz travessia de grafo point-in-time sobre
armazém relacional (`gh api search/repositories`, 07/08). O que existe é o
DESENHO, em dois lugares independentes: o ``as-of`` do **Datomic/XTDB** — pegar
o banco *como valor* num instante e rodar a consulta ORDINÁRIA contra ele — e a
NEP-001 do Neo4j (``temporal.asOf.traverse``, 1★, referência de proposta). Os
dois dizem a mesma coisa e é a que está implementada aqui: **o instante produz
um estado, e a travessia sobre esse estado é a de sempre.** Roubamos o desenho;
não havia pacote a adotar.

### As recusas — e elas são metade da entrega

* **store sem história → 501.** :class:`~dna.memory.as_of.AsOfUnsupported`. O
  adapter de filesystem declara ``versions=True`` e não guarda nenhuma
  (``list_versions`` → ``[]``). Devolver o grafo de HOJE sob um timestamp
  passado, ou ``[]``, é a mentira que esta casa mais cara paga.
* **história podada antes de ``as_of`` → 410.**
  :class:`~dna.memory.as_of.AsOfTruncated`, quando a ÂNCORA tem história e
  nenhuma alcança T. Medido: 8 de 431 instâncias com história têm a v1 podada
  (1,9%), **todas Engram** — ``VERSION_CHURN_RETENTION`` retém 3 versões
  porque o autopilot reescreve a mesma memória milhares de vezes. Não é
  hipótese.
* **a instância não existia em T → 404** (``LookupError``, e é uma RESPOSTA —
  a mesma distinção que ``get_instance(as_of=…)`` já faz).
* **um nó ALCANÇADO no meio da caminhada e podado NÃO derruba a travessia** —
  ele entra em :attr:`GraphResult.as_of_truncated` pelo nome. Derrubar a
  resposta inteira por um vizinho cego seria trocar um relatório útil por um
  erro; omiti-lo em silêncio seria deixar o leitor concluir "ninguém apontava"
  de "não dá para saber o que estes diziam". O vocabulário é o mesmo que as
  superfícies de LISTA já usam (ver :class:`~dna.memory.as_of.AsOfTruncated`).

### ⚠️ O limite honesto: quem foi APAGADO depois de T é invisível

``delete_instance`` remove as linhas de ``dna_versions`` junto com a instância —
delete é a poda mais completa que existe. Uma instância viva em T e apagada
depois não deixa rastro para este eixo ler, e o store **não tem como saber que
ela existiu**. Está fixado por teste (não descoberto depois), e dito aqui porque
quem não souber vai ler um grafo mais curto como um grafo menor.

### ⚠️ Os DOIS eixos continuam SEPARADOS

``as_of`` é tempo de TRANSAÇÃO (``dna_versions.created_at`` — *no que o store
acreditava em T*). ``valid_at`` é tempo de VALIDADE
(``dna_instances.valid_at`` — *o que era verdade em T*). Esta travessia tem
**um** eixo, e o segundo não entra por conveniência: a interseção bitemporal
exigiria a janela de validade nas LINHAS DE VERSÃO, e ``dna_versions`` não a
tem — a mesma lacuna nomeada que faz ``get_instance(as_of=…, valid_at=…)``
juntos serem recusados com ``ValueError``. Uma guarda mede que a travessia
declara um eixo só.
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

from dna.kernel.errors import CapabilityRefusal

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


#: O eixo da travessia — ``live`` (a CTE sobre ``dna_edges``) ou ``as_of`` (a
#: re-derivação sobre ``dna_versions``). Rótulo fechado, como todos os outros.
#:
#: ⚠️ Ele existe por uma razão que não é curiosidade: uma travessia ``as_of``
#: re-deriva e é N+1 POR CONSTRUÇÃO, então ela é mais lenta que a CTE — e se as
#: duas caírem no mesmo `p95`, o **gatilho 2 dispara por causa de uma feature
#: que acabamos de enviar**, e alguém migra a topologia inteira lendo o número
#: errado. :func:`traversal_stats` separa os dois: o veredicto do gatilho é
#: calculado sobre ``live``, e ``as_of`` é reportado ao lado, com o seu próprio
#: p95, para quem quiser otimizá-lo.
_AXIS_LIVE = "live"
_AXIS_AS_OF = "as_of"


def _emit_traversal(
    *, kind: str, direction: str, depth: int, stop: str, edges: int,
    ms: float, producer: str, tenant: str | None, axis: str = _AXIS_LIVE,
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
        "axis": axis,
    }
    _TRAVERSAL_LOG.info(
        "%s%s", TRAVERSAL_MARK,
        json.dumps(record, sort_keys=True, separators=(",", ":")),
        extra={"dna_graph": record},
    )


class GraphUnsupported(CapabilityRefusal, RuntimeError):
    """The active source keeps no derived edge graph, so there is no answer.

    Deliberately an exception and not an empty result: see the module
    docstring. The faces translate it into an explicit ``unsupported``
    capability, never into a list.

    A :class:`~dna.kernel.errors.CapabilityRefusal` — the marker base for *the
    store wired into this deployment cannot answer that at all*, which is
    precisely what this says and is NOT a verdict on the caller's request.
    Still a ``RuntimeError``, so every ``except`` written before the base
    existed behaves exactly as it did.
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
    #: The transaction instant this walk answered for (normalized ISO-8601 UTC),
    #: or ``None`` for a LIVE walk. Echoed rather than assumed: a caller holding
    #: only ``edges`` must be able to tell a historical answer from a current
    #: one, which is the same reason ``get_instance`` echoes its ``as_of``.
    as_of: str | None = None
    #: ``Kind/name`` for every node the walk REACHED and could not read at
    #: ``as_of`` because its history was pruned that far back. Reported, never
    #: dropped: omitting them lets a reader conclude "nothing pointed at this"
    #: from "we cannot know what these said". Always empty on a live walk.
    as_of_truncated: list[str] = field(default_factory=list)

    @property
    def dangling(self) -> list[dict[str, Any]]:
        """Edges that resolve to nothing — the list of what is broken.

        i-131 widened WHAT lands here without widening the definition: an edge
        whose target was deleted after the edge was written resolves to
        nothing, and used to be reported as ``resolved`` because the
        producer's write-time ``to_kind`` was being served as a live fact. See
        :attr:`orphaned` for the half of this list that HAD a target and lost
        it.
        """
        return [e for e in self.edges if not e.get("resolved")]

    @property
    def orphaned(self) -> list[dict[str, Any]]:
        """The subset of :attr:`dangling` whose target was DELETED (i-131).

        Its own reading rather than a filter left to the caller, because the
        two halves of ``dangling`` are different problems with different
        owners. An edge that NEVER resolved accuses its own author — a typo, or
        a target nobody ever wrote. An orphaned one accuses a DELETE: something
        removed an instance while live references pointed at it, and the delete
        path has no reference veto at all (``WritePipeline.delete``: deletes
        have no ``pre_save``). Collapsing them is how "47 Stories just lost
        their Feature" gets read as "47 Stories have typos".
        """
        return [e for e in self.edges if e.get("to_deleted_at")]


@dataclass(frozen=True)
class KindLens:
    """The three registry questions an ``as_of`` walk has to ask.

    An INJECTED COLLABORATOR, not a parameter of the question — the same shape
    ``dna.kernel.query.references.resolve_relations`` already uses, and for the
    same reason: this module stays free of kernel imports, and the answers stay
    the kernel's so a second resolution rule cannot appear beside the first.
    :class:`TestGatilho1Expressividade` counts it separately from the question
    coordinates for exactly that reason.

    Why re-derivation needs a registry at all: the edges of T come from the
    SPECS of T, and knowing WHICH spec fields are relations is a declaration
    (``spec.relations``), never a slug-shaped guess at a field name. That is
    the same line ``dna.kernel.query.graph``'s live path holds by reading rows
    a write produced.
    """

    #: ``(kind, *, api_version=None, scope=None) -> KindPort | None``.
    port_for: Any
    #: ``() -> Iterable[KindPort]`` — every registered Kind. Needed only by
    #: ``direction="in"``: *who pointed at me* is answered by the Kinds that
    #: DECLARE a relation to mine, which is a registry question.
    ports: Any
    #: ``async (kind, scope) -> list[str]`` — the scopes a live read would
    #: probe, in order. Not a convenience: 3 of the 33 edges in the dna-cloud
    #: database (9%) resolved through the parent-scope chain, so a historical
    #: read pinned to one scope would report them DANGLING — a confident
    #: ``resolved: false`` about a relation that was fine.
    scope_chain: Any


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
    as_of: str | None = None,
    kinds: "KindLens | None" = None,
) -> GraphResult:
    """Walk ``source``'s edge graph from one instance.

    ``direction``: ``in`` (what points at this — the product question),
    ``out`` (what this points at), ``both``.

    ``as_of`` (normalized ISO-8601 UTC) answers the SAME question at a past
    TRANSACTION instant — *the graph as it was in T* — by re-deriving it from
    ``dna_versions`` rather than by filtering ``dna_edges``, which keeps no
    history. See the module docstring for the measurement that decided that and
    for the three refusals it brings; ``kinds`` is the registry lens the
    re-derivation needs and is an injected collaborator, never a question.

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
    blind: list[str] = []
    if as_of is None:
        rows = await source.traverse_edges(
            scope, kind, name,
            tenant=tenant, direction=direction, depth=effective,
        )
    else:
        rows, blind = await _walk_as_of(
            source, scope, kind, name,
            tenant=tenant, direction=direction, depth=effective,
            as_of=as_of, kinds=kinds,
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
            producer=producer, tenant=tenant, axis=_AXIS_AS_OF if as_of else _AXIS_LIVE,
        )
    return GraphResult(
        edges=rows, direction=direction, depth=effective, stop=stop,
        graph_producer=producer, as_of=as_of, as_of_truncated=blind,
    )


# ── a travessia ``as_of``: o grafo RE-DERIVADO em T ─────────────────────────
#
# Privada, e por desenho: ``TestGatilho1Expressividade`` exige que exista UMA
# travessia PÚBLICA no módulo de policy, porque "duas rotas de travessia de
# forma diferente" é metade do gatilho 1. Isto não é uma segunda forma de
# pergunta — é a MESMA pergunta com a coordenada de tempo, alcançável só por
# ``traverse``, com o mesmo teto, o mesmo anti-ciclo e o mesmo vocabulário de
# ``stop``. Uma função pública aqui seria a segunda porta; um helper privado
# atrás da primeira não é.


def _marker(kind: str | None, name: str) -> str:
    """``>Kind/name>`` — o mesmo delimitador que a CTE usa.

    Escrito aqui em Python e ali em SQL porque as duas travessias caminham
    sobre estruturas diferentes; o TESTE que as mantém honestas não compara o
    código, compara a RESPOSTA (``as_of`` no instante de agora tem de devolver
    o mesmo grafo que a travessia viva).
    """
    return f">{kind or ''}/{name}>"


async def _walk_as_of(
    source: Any, scope: str, kind: str, name: str, *,
    tenant: str | None, direction: str, depth: int,
    as_of: str, kinds: "KindLens | None",
) -> tuple[list[dict[str, Any]], list[str]]:
    """O grafo como o store acreditava em ``as_of`` — re-derivado, não filtrado.

    Devolve ``(rows, blind)`` com as MESMAS chaves que
    ``SqlAlchemySource.traverse_edges`` produz, porque a face que as renderiza
    é uma só e uma resposta histórica com outro formato seria uma segunda forma
    de pergunta pela porta dos fundos.

    Duas chaves valem uma nota, e as duas são sobre honestidade:

    * ``from_version`` é a versão que a instância de origem tinha **em T**, não
      a de hoje. É o que a coluna sempre quis dizer — *de qual versão estas
      arestas foram derivadas* — só que agora derivada de uma versão do
      passado.
    * ``to_deleted_at`` é SEMPRE ``None`` numa linha ``as_of``, e isso é uma
      afirmação, não uma omissão: um delete registrado DEPOIS de T não faz
      parte do que o store acreditava em T. (O contrário — carimbar o delete de
      hoje numa resposta sobre o passado — seria misturar dois instantes numa
      linha só.)
    """
    from dna.kernel.identity import instance_id_of  # noqa: PLC0415
    from dna.kernel.kinds.relations import (  # noqa: PLC0415
        relation_values,
        relations_of,
    )
    # ``_api_version_of`` é privado do módulo vizinho e importado assim de
    # propósito: ele lê as DUAS formas que um getter devolve (dict cru ou
    # instância parseada), e uma segunda leitura escrita aqui divergiria da
    # dele exatamente no dia em que a forma mudasse — que é o defeito que o
    # docstring dele descreve.
    from dna.kernel.query.references import (  # noqa: PLC0415
        _api_version_of,
        resolve_relations,
    )
    from dna.memory.as_of import AsOfTruncated, AsOfUnsupported  # noqa: PLC0415

    if not callable(getattr(source, "load_one_as_of", None)):
        raise AsOfUnsupported(
            f"an as_of traversal reads the SPECS this store recorded at that "
            f"instant, so it needs version history with a transaction "
            f"timestamp; {type(source).__name__} does not implement "
            f"load_one_as_of. Refusing rather than walking TODAY's edge graph "
            f"and presenting it as the graph at {as_of}."
        )
    if direction != "out" and not callable(
        getattr(source, "load_kind_as_of", None)
    ):
        raise AsOfUnsupported(
            f"'what pointed AT {kind}/{name} at {as_of}' has to read the "
            f"candidate authors' specs as of that instant; "
            f"{type(source).__name__} does not implement load_kind_as_of. "
            f"direction='out' is answerable on this store; 'in' and 'both' are "
            f"not, and [] would say nothing pointed at it."
        )
    if kinds is None:
        # A wiring bug, not a capability and not a bad request: every face
        # reaches this through ``Kernel.graph_refs``, which always supplies the
        # lens. A ``ValueError`` here would surface as a 400 and accuse the
        # caller of something the deployment did.
        raise RuntimeError(
            "traverse(as_of=...) re-derives the graph from the versions' "
            "specs, and knowing WHICH spec fields are relations is a registry "
            "question — pass kinds=KindLens(...). Guessing at field names is "
            "the slug-shaped derivation this module refuses."
        )

    blind: set[str] = set()
    #: ``(kind, name)`` → ``(scope it resolved in, the as-of row)``. One read
    #: per node per walk: a diamond asks for the same target from four routes.
    believed: dict[tuple[str, str], tuple[str | None, dict[str, Any] | None]] = {}
    #: ``(kind, api_version)`` → the whole Kind at T, for the ``in`` direction.
    per_kind: dict[tuple[str, str | None], dict[str, Any]] = {}

    async def _believed(k: str, n: str) -> tuple[str | None, dict[str, Any] | None]:
        key = (k, n)
        if key in believed:
            return believed[key]
        try:
            chain = list(await kinds.scope_chain(k, scope))
        except Exception:  # noqa: BLE001 — fail-soft exactly like the live
            # read's own chain lookup: an unreadable chain degrades to the
            # scope we were asked about, never to an exception on a read.
            chain = [scope]
        hit: tuple[str | None, dict[str, Any] | None] = (None, None)
        for sc in chain:
            res = await source.load_one_as_of(
                sc, k, n, as_of=as_of, tenant=tenant,
            ) or {}
            if res.get("raw") is not None:
                hit = (sc, res)
                break
            if res.get("truncated"):
                # Blind HERE stops the chain: "this scope's copy may have
                # existed and we cannot read it" is not a licence to answer
                # with the parent's copy, which a live read would never have
                # reached.
                blind.add(f"{k}/{n}")
                break
        believed[key] = hit
        return hit

    async def _getter(sc: str, k: str, n: str, *, tenant: str | None = None) -> Any:
        _, res = await _believed(k, n)
        return (res or {}).get("raw")

    async def _local_getter(
        sc: str, k: str, n: str, *, tenant: str | None = None,
    ) -> Any:
        found_in, res = await _believed(k, n)
        return (res or {}).get("raw") if found_in == sc else None

    def _port_for(target: str) -> Any:
        return kinds.port_for(target, scope=scope)

    #: ``(kind, name)`` → quando o alvo foi apagado. Carregado UMA vez, e só
    #: quando alguma aresta de fato não resolveu — o caso raro paga, o comum não.
    deletions: dict[tuple[str, str], str] | None = None

    async def _deletions() -> dict[tuple[str, str], str]:
        nonlocal deletions
        if deletions is None:
            reader = getattr(source, "deleted_targets", None)
            rows = await reader(scope, tenant=tenant) if callable(reader) else []
            deletions = {
                (r["to_kind"], r["to_name"]): r["to_deleted_at"]
                for r in rows
                if r.get("to_kind") and r.get("to_deleted_at")
            }
        return deletions

    async def _rescue_deleted(row: dict[str, Any]) -> None:
        """A instância existia em T e foi APAGADA depois — o delete deixou prova.

        Sem isto, uma aresta cujo alvo morreu depois de T volta ``resolved:
        false``: o histórico da instância apagada foi embora com ela
        (``delete_instance`` apaga as linhas de ``dna_versions``), então a
        re-derivação não acha nada e conclui "não existia". **É a resposta
        OPOSTA, com a mesma confiança** — em T aquilo estava perfeitamente vivo.

        O que salva é um fato que uma ESCRITA produziu: o delete carimba
        ``to_deleted_at`` nas arestas que apontavam para ele e as mantém de
        propósito. Se o carimbo é POSTERIOR a ``as_of``, o alvo estava vivo em
        T — e o que continua desconhecido é só o CONTEÚDO dele, que vira nome
        em ``as_of_truncated``. ``to_id`` e ``to_api_version`` ficam ``None``,
        que é o valor que este esquema já usa para "desconhecido"; preenchê-los
        com o que o registro diz HOJE seria carimbar o presente de novo.
        """
        stamps = await _deletions()
        for declared in row["declared_to"]:
            stamp = stamps.get((declared, row["to_name"]))
            # ISO-8601 UTC de largura fixa dos dois lados: comparar como texto É
            # comparar cronologicamente, a mesma premissa de ``created_at``.
            if stamp and stamp > as_of:
                row["to_kind"] = declared
                row["resolved"] = True
                blind.add(f"{declared}/{row['to_name']}")
                return

    async def _kind_at(k: str, api_version: str | None) -> dict[str, Any]:
        key = (k, api_version)
        if key not in per_kind:
            payload = await source.load_kind_as_of(
                scope, k, as_of=as_of, tenant=tenant, api_version=api_version,
            ) or {}
            for gone in payload.get("truncated") or []:
                blind.add(f"{k}/{gone.get('name')}")
            per_kind[key] = payload
        return per_kind[key]

    async def _out_rows(
        k: str, n: str, raw: Any, version: int, *, at_depth: int, path: str,
    ) -> list[dict[str, Any]]:
        port = kinds.port_for(
            k, api_version=_api_version_of(raw), scope=scope,
        )
        if port is None:
            return []
        edges, _problems, _discords, complete = await resolve_relations(
            port, raw, scope=scope, name=n, tenant=tenant,
            getter=_getter, port_for=_port_for, local_getter=_local_getter,
        )
        if not complete:
            # ``resolve_relations`` returns this when a read raised part-way.
            # The write path's answer is "say nothing"; a TRAVERSAL's cannot
            # be, because a short list renders as a small graph. Refuse the
            # whole answer rather than serve a partial one that looks whole —
            # the same rule the producer applies to a partial edge set.
            raise RuntimeError(
                f"the store failed part-way through re-deriving "
                f"{k}/{n}'s relations at {as_of}; refusing a PARTIAL as-of "
                f"graph, which would be indistinguishable from a small one."
            )
        rows = []
        from_api = _api_version_of(raw) or ""
        for e in edges:
            closes = _marker(e.to_kind, e.value) in path
            rows.append({
                "direction": "out", "depth": at_depth,
                "from_api_version": from_api,
                "from_kind": k, "from_name": n,
                "source_field": e.field, "ordinal": int(e.ordinal),
                "to_scope": e.to_scope, "to_kind": e.to_kind,
                "to_name": e.value,
                "to_api_version": e.to_api_version,
                "to_id": e.to_id,
                "declared_to": tuple(e.declared),
                # See the function docstring: a delete recorded after T is not
                # part of the belief state at T.
                "to_deleted_at": None,
                "resolved": e.to_kind is not None,
                "closes_cycle": closes,
                "from_version": int(version or 0),
            })
        for row in rows:
            if not row["resolved"]:
                await _rescue_deleted(row)
        return rows

    async def _winner(rel: Any, value: str) -> str | None:
        """WHICH declared target a polymorphic relation actually hit at T.

        The same order ``resolve_relations`` probes in — first declared target
        that resolves wins. Re-deriving the order here rather than assuming the
        anchor's Kind is what keeps ``in`` and ``out`` from disagreeing about
        one edge.
        """
        targets = [t for t in rel.to if _port_for(t) is not None] or list(rel.to)
        for t in targets:
            _, res = await _believed(t, value)
            if (res or {}).get("raw") is not None:
                return t
        return None

    async def _in_rows(
        k: str, n: str, raw: Any, *, at_depth: int, path: str,
        found_in: str | None,
    ) -> list[dict[str, Any]]:
        to_api = _api_version_of(raw)
        to_id = instance_id_of(raw)
        rows = []
        seen_ports: set[tuple[str, str | None]] = set()
        for port in kinds.ports() or []:
            src_kind = getattr(port, "kind", None)
            if not src_kind:
                continue
            src_api = getattr(port, "api_version", None)
            if (src_kind, src_api) in seen_ports:
                continue
            seen_ports.add((src_kind, src_api))
            candidates = [
                rel for rel in relations_of(port).values()
                if rel.resolved and k in rel.to
            ]
            if not candidates:
                continue
            payload = await _kind_at(src_kind, src_api)
            for inst in payload.get("instances") or []:
                spec = (inst.get("raw") or {}).get("spec")
                for rel in candidates:
                    values = relation_values(rel, spec)
                    for ordinal, value in enumerate(values):
                        if value != n:
                            continue
                        if len(rel.to) > 1 and await _winner(rel, value) != k:
                            # A polymorphic relation whose value resolved to a
                            # DIFFERENT declared Kind: the edge is real and it
                            # is not ours.
                            continue
                        # ⚠️ O nó em que ESTA aresta chega, andando para
                        # dentro, é o lado FROM — o autor — e não o alvo. A CTE
                        # espelha o join inteiro quando ``direction='in'``
                        # (``node_kind = from_kind``); usar o alvo aqui marcaria
                        # ciclo já no primeiro salto, porque o alvo é o nó de
                        # onde a caminhada partiu.
                        closes = _marker(src_kind, inst.get("name")) in path
                        rows.append({
                            "direction": "in", "depth": at_depth,
                            "from_api_version": inst.get("api_version") or "",
                            "from_kind": src_kind,
                            "from_name": inst.get("name"),
                            "source_field": rel.name, "ordinal": int(ordinal),
                            "to_scope": scope if found_in == scope else None,
                            "to_kind": k, "to_name": n,
                            "to_api_version": to_api,
                            "to_id": to_id,
                            "declared_to": tuple(rel.to),
                            "to_deleted_at": None,
                            "resolved": True,
                            "closes_cycle": closes,
                            "from_version": int(inst.get("version") or 0),
                        })
        return rows

    anchor = await source.load_one_as_of(
        scope, kind, name, as_of=as_of, tenant=tenant,
    ) or {}
    if anchor.get("truncated"):
        raise AsOfTruncated(
            f"{kind} {name!r} in scope {scope!r} HAS history, but none of it "
            f"reaches back to {as_of} — the versions that old were pruned, so "
            f"what pointed at it then is not knowable. This is NOT 'nothing "
            f"pointed at it', and it is not 'the instance did not exist'."
        )
    if anchor.get("raw") is None:
        raise LookupError(
            f"no {kind} named {name!r} in scope {scope!r} at {as_of} — "
            f"nothing was recorded under that name at or before that instant, "
            f"so there is no graph around it to walk."
        )
    believed[(kind, name)] = (scope, anchor)

    max_rows = getattr(source, "MAX_TRAVERSAL_ROWS", 10**9)
    lanes = ("out", "in") if direction == "both" else (direction,)
    merged: list[dict[str, Any]] = []
    for lane in lanes:
        # One dedup dict PER LANE, exactly like the adapter's ``both`` (which
        # calls itself twice): the same edge legitimately appears once as an
        # ``out`` of one node and once as an ``in`` of the other.
        out: dict[tuple, dict[str, Any]] = {}
        frontier = [(kind, name, _marker(kind, name))]
        for level in range(1, depth + 1):
            if not frontier or len(out) >= max_rows:
                break
            nxt: list[tuple[str, str, str]] = []
            for node_kind, node_name, path in frontier:
                found_in, res = await _believed(node_kind, node_name)
                raw = (res or {}).get("raw")
                if raw is None:
                    continue
                if lane == "out":
                    rows = await _out_rows(
                        node_kind, node_name, raw,
                        int((res or {}).get("version") or 0),
                        at_depth=level, path=path,
                    )
                else:
                    rows = await _in_rows(
                        node_kind, node_name, raw,
                        at_depth=level, path=path, found_in=found_in,
                    )
                for row in rows:
                    key = (row["from_api_version"], row["from_kind"],
                           row["from_name"], row["source_field"],
                           row["ordinal"])
                    if key not in out:
                        out[key] = row
                    if len(out) >= max_rows:
                        break
                    if row["closes_cycle"]:
                        # Emitted (a cycle in the data is information), never
                        # expanded FROM — the CTE's rule, in Python.
                        continue
                    step = (
                        (row["to_kind"], row["to_name"]) if lane == "out"
                        else (row["from_kind"], row["from_name"])
                    )
                    if step[0] is None:
                        # A dangling target has no Kind and therefore no rows
                        # to walk into; the CTE's NULL join says the same.
                        continue
                    nxt.append((step[0], step[1], path + _marker(*step)[1:]))
                if len(out) >= max_rows:
                    break
            frontier = nxt
        merged.extend(out.values())
    return merged, sorted(blind)


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

    ⚠️ **O veredicto do gatilho é calculado sobre as travessias VIVAS.** Uma
    travessia ``as_of`` re-deriva o grafo das versões e é N+1 por construção —
    mais lenta que a CTE por DESENHO, não por escala. Somá-las faria o gatilho
    2 disparar por causa de uma feature que acabamos de enviar, e alguém
    migraria a topologia inteira lendo o número errado. As ``as_of`` aparecem
    em ``as_of`` com o seu próprio ``p95``, para quem quiser otimizá-las — o
    que não é a mesma decisão.

    ⚠️ Uma linha SEM ``axis`` (emitida antes deste campo existir) conta como
    ``live``, que é o que ela era. O default fica aqui e não no emissor porque
    é o LEITOR que encontra as linhas velhas.
    """
    calls: list[Mapping[str, Any]] = []
    ignored = 0
    for line in lines:
        record = parse_traversal_line(line)
        if record is None:
            ignored += 1
            continue
        calls.append(record)

    historical = [r for r in calls if r.get("axis") == _AXIS_AS_OF]
    calls = [r for r in calls if r.get("axis", _AXIS_LIVE) != _AXIS_AS_OF]
    hist_deep = [float(r.get("ms", 0.0)) for r in historical
                 if int(r.get("depth", 0) or 0) >= TRIGGER_DEPTH]

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
        # Reportado ao lado, NUNCA somado — ver o docstring. ``calls`` acima é
        # o das vivas, e é sobre elas que o veredicto abaixo é calculado.
        "as_of": {
            "calls": len(historical),
            "p95_ms": percentile(
                [float(r.get("ms", 0.0)) for r in historical], 0.95,
            ),
            "deep": {
                "depth_min": TRIGGER_DEPTH,
                "calls": len(hist_deep),
                "p95_ms": percentile(hist_deep, 0.95),
            },
            "counts_toward_trigger": False,
        },
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
