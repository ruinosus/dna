# Runtime & threads — serving a live copilot

Emitting produces a file. These ports produce a **running** agent, and the conversation state that outlives a single request. The thread ports are split along a real fault line — what the framework knows versus what only the host knows — and the split is the whole design.

!!! info "Generated from the source"

    Names, signatures and docstrings are parsed out of `packages/sdk-py/dna`
    by `scripts/gen_ports_docs.py`. The prose around each contract is
    hand-written in `scripts/ports_prose.py`, and the generator **fails**
    if a port has none — so a new port cannot ship undocumented.

## AGUIApp

`dna.runtime.port.AGUIApp` · `@runtime_checkable` · :material-power-plug: **extension point**

The handle a `RuntimePort` hands back: a framework-agnostic AG-UI app the host mounts on a path.

!!! quote "From the source"

    The handle a :class:`RuntimePort` returns — a framework-agnostic AG-UI
    app the host can mount and, where the backend is LangGraph-shaped,
    rehydrate against.

    **Optional member — ``thread_store``.** An adapter MAY expose the read half
    of :mod:`dna.runtime.thread_store` over its own backend (the LangGraph one
    does; MAF has no thread store yet and says so with ``None``). It is
    deliberately NOT a required member of this Protocol: making it one would
    flip ``isinstance`` for every adapter written before it existed. Probe it
    with ``getattr(app, "thread_store", None)``.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `attach` | <code>def attach(self, app: Any, path: str='/agui') -> None</code> | Mount this app's native AG-UI endpoint onto ``app`` at ``path``. |

**Swap it when** — Whenever you implement `RuntimePort` — you have to return one of these.

**The minimum that works** — `attach(app, path)`.

**What it lights up** — The copilot being reachable over HTTP at all. Note the standing house rule: AG-UI has official client libraries, and the wire protocol is not something to re-derive from its specification. Your job is mounting, not re-implementing the protocol.

**How you prove it** — Drive it with an official AG-UI client, not with a hand-rolled one.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

## AgentHarnessPort

`dna.runtime.harness.AgentHarnessPort` · typing-only (not `@runtime_checkable`) · :material-power-plug: **extension point**

A runtime adapter serves an AG-UI app; a consumer harness starts one portable run while the provider SDK keeps ownership of its model and tool loop. DNA owns the request, lifecycle events, cancellation and session metadata around that loop.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `start` | <code>async def start(self, definition: ResolvedAgent, request: RunRequest) -> RunHandle</code> |  |

**Swap it when** — You want `dna run` or another DNA consumer to execute through a provider SDK that has no shipped harness.

**The minimum that works** — A `provider` id and `start(definition, request)` returning a `RunHandle`. Register it with `register_harness(...)`.

**What it lights up** — `RuntimeBinding.provider: <yours>` and `dna run --provider <yours>`. An unregistered provider fails with the available harness ids instead of silently selecting another execution path.

**How you prove it** — Drive the adapter with its provider SDK fake and assert lifecycle order, streaming, cancellation and session resume. `tests/runtime/test_github_copilot_harness.py` is the reference.

**Shipped implementations** — `GitHubCopilotHarness` (`dna.runtime.adapters.github_copilot_harness`) — provider `github-copilot`, needs the CLI `[harness]` extra

## RuntimePort

`dna.runtime.port.RuntimePort` · `@runtime_checkable` · :material-power-plug: **extension point**

An emitter writes a file; a runtime adapter builds a live app. Two ship — LangChain and Microsoft Agent Framework — behind their own extras, and each import is independently guarded so a missing extra removes one backend instead of breaking the registry.

!!! quote "From the source"

    A framework adapter — builds a live :class:`AGUIApp` from a neutral
    :class:`~dna.emit.EmitContext` + :class:`RuntimeHooks`. Implement this +
    call :func:`register_runtime` to add a backend.

    ``target``
        Stable id used by ``serving.framework`` (e.g. ``"langchain"``,
        ``"maf"``) to select this backend.

    :meth:`build`
        The construction — reads the neutral context and hooks, wires the
        four DNA disciplines into the framework's native mechanism, and
        returns an :class:`AGUIApp`. Performs NO network I/O (the lazy-MCP
        invariant holds through every adapter).

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `build` | <code>async def build(self, ctx: Any, hooks: RuntimeHooks) -> AGUIApp</code> | Build a live :class:`AGUIApp` from ``ctx`` + ``hooks``. |

**Swap it when** — You want to serve DNA agents on a framework neither shipped adapter covers.

**The minimum that works** — `build(ctx, hooks)` returning an `AGUIApp`, and a `target` id. Register with `register_runtime(...)`.

**What it lights up** — `serving.framework: <yours>` becoming a valid declaration, and the copilot serving on your backend. An unregistered target fails with the list of available ones — which will be short if an extra is missing, so check what is installed before concluding a target is unsupported.

**How you prove it** — Serve a real agent and drive it over AG-UI. There is no unit-level battery here; `dna.runtime.adapters.langchain_rt` is the reference to read.

**Shipped implementations** — `LangChainRuntime` (`dna.runtime.adapters.langchain_rt`) — target `langchain`, needs the `[runtime]` extra; `MafRuntime` (`dna.runtime.adapters.maf_rt`) — target `maf`, needs the `[maf]` extra

## ThreadIndexPort

`dna.runtime.thread_store.ThreadIndexPort` · `@runtime_checkable` · :material-power-plug: **extension point**

The half the framework **cannot** answer. A checkpointer knows messages; it does not know users. This index is the only place ownership is written down.

!!! quote "From the source"

    De QUEM é a conversa, e quais são as de alguém. É a metade que o
    framework não sabe responder e que o host guarda num índice ao lado — o
    único lugar onde há escrita, e ela é por turno, barata e sem transcript.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `index_thread` | <code>async def index_thread(self, *, owner: str \| None, thread_id: str \| None, workspace: str \| None=None, tenant: str \| None=None, messages: Sequence[Any]=(), copilot: str \| None=None, surface: str \| None=None) -> ThreadRef \| None</code> | Registra/atualiza a conversa e ENFORCE a posse. |
| `fetch_threads` | <code>async def fetch_threads(self, *, owner: str, workspace: str \| None=None, copilot: str \| None=None, limit: int=50) -> Sequence[ThreadRef]</code> | As conversas de ``owner``, mais recentes primeiro por atividade real. Os filtros COMPÕEM com o dono, nunca o substituem — sem ``owner`` a resposta é vazia, jamais "todas". |
| `thread_owner` | <code>async def thread_owner(self, thread_id: str) -> str \| None</code> | O dono indexado de ``thread_id``, ou ``None`` se desconhecido. A metade de leitura da guarda de posse — combine com :func:`can_read_thread`, não com uma segunda regra. |

**Swap it when** — Always, if conversations belong to people. Ownership is an authorization input, not a display convenience.

**The minimum that works** — `index_thread`, `fetch_threads`, `thread_owner`.

**What it lights up** — "My conversations" lists, and the ownership check that stops one user reading another's thread. Skip it and there is nothing to check against — which is the failure mode to think hardest about on this page.

**How you prove it** — `InMemoryThreadStore` is the reference; test ownership with two distinct users, not one.

**Shipped implementations** — `InMemoryThreadStore` (`dna.runtime.thread_store`)

## ThreadPurgePort

`dna.runtime.thread_store.ThreadPurgePort` · `@runtime_checkable` · :material-power-plug: **extension point**

The two primitives only the party holding the connection can perform, and everything the retention sweep needs from the host.

!!! quote "From the source"

    As duas primitivas que **só quem tem a conexão** consegue cumprir, e que
    são tudo o que :func:`sweep_retention` precisa do host.

    São duas, e não uma varredura inteira, de propósito: o ALGORITMO (qual é o
    corte, quem venceu, em que ordem apagar, o que reportar) é do SDK, para que
    dois hosts não interpretem a mesma política de dois jeitos; o que sobra para
    o host é uma consulta e um delete — o que ele já sabe escrever no seu
    dialeto. Um host que implementasse a varredura inteira reescreveria a
    política, e é aí que "30 dias" vira dois números diferentes.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `expired_threads` | <code>async def expired_threads(self, *, cutoff: datetime, copilot: str \| None=None, limit: int=100) -> Sequence[ThreadRef]</code> | As conversas com ``updated_at`` anterior a ``cutoff``, mais antigas primeiro, no máximo ``limit``. |
| `delete_thread` | <code>async def delete_thread(self, thread_id: str) -> bool</code> | Apaga a linha de ÍNDICE da conversa. ``True`` = havia algo e sumiu. |

**Swap it when** — You have a retention policy — which, for conversation data, is usually a legal position rather than a preference.

**The minimum that works** — `expired_threads` and `delete_thread`.

**What it lights up** — `sweep_retention`. Without it the sweep has nothing to call and conversations are kept forever — silently, because nothing errors when deletion simply never happens.

**How you prove it** — Run `sweep_retention` against seeded expired threads and assert they are gone.

**Shipped implementations** — `InMemoryThreadStore` (`dna.runtime.thread_store`)

## ThreadStorePort

`dna.runtime.thread_store.ThreadStorePort` · `@runtime_checkable` · :material-power-plug: **extension point**

Composes [`ThreadTranscriptPort`](#threadtranscriptport), [`ThreadIndexPort`](#threadindexport).

Index plus transcript plus the portability write. Implement this when one component can honestly answer all three; implement the halves separately when it cannot — which is the usual case, and the reason the halves exist.

!!! quote "From the source"

    O contrato INTEIRO: índice + transcript + a escrita de portabilidade.

    Uma implementação disto é o que um host injeta quando quer que conversa seja
    dado do DNA de ponta a ponta. Um adapter de framework normalmente cumpre só
    :class:`ThreadTranscriptPort`; o host compõe as duas metades.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `import_transcript` | <code>async def import_transcript(self, export: TranscriptExport, *, owner: str, thread_id: str \| None=None, workspace: str \| None=None, tenant: str \| None=None, copilot: str \| None=None, surface: str \| None=None) -> ThreadRef</code> | Importa um envelope como conversa de ``owner``. |

**Swap it when** — You are backing conversations with a store that owns both the index and the messages.

**The minimum that works** — Both parent Protocols, plus `import_transcript`.

**What it lights up** — Conversation history, ownership checks, and thread export/import end to end.

**How you prove it** — `InMemoryThreadStore` (`dna.runtime.thread_store`) implements the whole port and is the readable reference.

**Shipped implementations** — `InMemoryThreadStore` (`dna.runtime.thread_store`) — the only complete implementation; satisfies the port structurally

## ThreadTranscriptPort

`dna.runtime.thread_store.ThreadTranscriptPort` · `@runtime_checkable` · :material-power-plug: **extension point**

The half the **framework** can answer. The transcript lives inside the framework's own mechanism — LangGraph checkpoints, say — so this port is a projection of it, not a second copy.

!!! quote "From the source"

    LER a conversa. É o que um adapter de framework consegue prometer: o
    transcript vive no mecanismo do framework, e esta metade da porta é uma
    PROJEÇÃO DE LEITURA sobre ele — nenhuma escrita, nenhum turno mais caro.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `fetch_transcript` | <code>async def fetch_transcript(self, thread_id: str, *, state_keys: Sequence[str] \| None=None) -> Transcript</code> | O transcript de ``thread_id`` em mensagens AG-UI. ``state_keys`` é a allowlist do state que a UI reidrata (``None`` = o default declarado pela implementação, normalmente nenhum; vazia = só as mensagens). Um thread inexistente devolve um :class:`Transcript` VAZIO, nunca um erro — é o que uma conversa recém-criada legitimamente parece. |
| `export_transcript` | <code>async def export_transcript(self, thread_id: str, *, state_keys: Sequence[str] \| None=None) -> TranscriptExport</code> | O envelope portátil do thread. Carrega o histórico visível e SINALIZA (``pending_state_dropped``) quando deixa um run pendente para trás. |

**Swap it when** — You are adapting a new agent framework and want its conversation history readable through DNA.

**The minimum that works** — `fetch_transcript`; `export_transcript` for portability.

**What it lights up** — History in the console, and thread export. Without it a conversation runs fine and is simply unreadable afterwards.

**How you prove it** — `LangGraphTranscriptStore` (`dna.runtime.adapters.langgraph_threads`) is the worked example of projecting a framework's own store.

**Shipped implementations** — `LangGraphTranscriptStore` (`dna.runtime.adapters.langgraph_threads`); `InMemoryThreadStore` (`dna.runtime.thread_store`)

## TranscriptPurgePort

`dna.runtime.thread_store.TranscriptPurgePort` · `@runtime_checkable` · :material-power-plug: **extension point**

Deleting the thread row is not deleting the conversation. The messages live in the framework's store, and only the framework adapter can make them go.

!!! quote "From the source"

    A metade do apagamento que só o FRAMEWORK consegue: sumir com o
    transcript de fato (no LangGraph, as linhas de checkpoint do thread).

    Protocol separado pela mesma razão que separa leitura de índice: um adapter
    de framework não sabe de quem é a conversa nem quando ela venceu, e um
    índice não alcança o checkpoint. Juntar os dois num tipo só obrigaria
    alguém a stubar metade.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `delete_transcript` | <code>async def delete_transcript(self, thread_id: str) -> None</code> | Apaga o que o framework guarda do thread. Idempotente: um thread sem checkpoint não é erro. |

**Swap it when** — You implement `ThreadPurgePort`. These two are a pair: index-side deletion without transcript-side deletion leaves the content on disk while the system reports it deleted, and that gap is the one worth being paranoid about.

**The minimum that works** — `delete_transcript` — really deleting, not tombstoning.

**What it lights up** — Deletion that is true when someone asks whether the data is gone.

**How you prove it** — `LangGraphTranscriptPurge` (`dna.runtime.adapters.langgraph_threads`) removes the thread's checkpoint rows; assert at the store, not through the API that just told you it worked.

**Shipped implementations** — `LangGraphTranscriptPurge` (`dna.runtime.adapters.langgraph_threads`)

