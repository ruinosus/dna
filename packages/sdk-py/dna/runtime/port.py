"""RuntimePort — the declarative contract a framework adapter implements to
turn a neutral :class:`~dna.emit.EmitContext` into a servable AG-UI app.

Mirrors :mod:`dna.emit`'s ``EmitterPort``/registry shape one layer over: where
an emitter materializes a context into a *static artifact* (a file), a runtime
*builds a live app* (a graph/agent wired to a framework's AG-UI bridge). Same
discipline — pure construction from the neutral context + host-supplied hooks,
no kernel I/O, no network at build time (the lazy-MCP invariant).

Heavy framework deps (langchain, agent-framework) are NEVER imported at this
module's top level — only inside :func:`_ensure_runtimes`, and only guarded by
``try/except ImportError`` since the adapter modules themselves are optional
extras that may not be installed (or may not exist yet during bring-up).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class RuntimeHooks:
    """Host-supplied hooks a :class:`RuntimePort` wires into the framework's
    native mechanism for each of the four DNA disciplines (allowlist i-038 /
    compose i-040 / HITL / lazy-MCP), plus host-owned persistence and an
    escape hatch for backend-specific extras."""

    #: httpx.Auth-style per-request bearer provider for the lazy MCP tool.
    mcp_auth: Any
    #: async compose(headers) -> str — the i-040 live prompt composition.
    compose: Any
    #: Backend-specific escape hatch, e.g. LangChain's
    #: {"middleware": [...], "tools": [...]}. Adapters that don't understand a
    #: key ignore it; there is no neutral extensions contract.
    extensions: Any = None
    #: Host-injected checkpointer, or None to let the adapter resolve one from
    #: ctx.persistence.
    checkpointer: Any = None
    #: Host-injected store, or None to let the adapter resolve one from
    #: ctx.persistence.
    store: Any = None
    #: `Callable[[Turn], None]` — onde o registro de cada turno e GRAVADO.
    #: `None` (o default) deixa a telemetria sem destino de produto; o OTLP,
    #: se configurado, continua exportando. E o host que injeta porque e ele
    #: quem tem a conexao — a mesma fronteira do `checkpointer`.
    turn_sink: Any = None
    #: `async (consulta, limite) -> Sequence` — a busca de memoria. O HOST a
    #: fornece porque e ele que tem o cliente MCP, a credencial e o tenant.
    #: `None` (o default) deixa o agente dependendo de CHAMAR `recall`, que e
    #: exatamente o que ele esquece de fazer.
    recall: Any = None
    #: `async (texto, nome_da_tool) -> str | None` — onde uma saida GRANDE de
    #: tool e guardada, devolvendo o endereco. `None` corta mesmo assim e diz
    #: que nao guardou: um deployment sem storage prefere uma janela honesta a
    #: um contexto que cresce sem fim.
    offload_store: Any = None
    #: `async (nome) -> str | None` — o corpo de um PromptTemplate do
    #: workspace (overlay do tenant vence). O HOST fornece pela mesma razão do
    #: `recall`: é ele que tem o cliente MCP, a credencial e o tenant. `None`
    #: deixa cada voz no seu default de fallback — a voz é DADO, nunca código
    #: (regra do fundador, 03/08/2026).
    template_source: Any = None
    #: `async () -> dict | None` — o SPEC do CognitivePolicy do workspace
    #: (overlay do tenant). Mesma fronteira: o host tem o canal e o tenant.
    #: `None` deixa cada knob no default de código (E1 do épico das nove
    #: seções: `recall.retrieval.k` substitui o MAX_MEMORIES fixo).
    policy_source: Any = None


@runtime_checkable
class AGUIApp(Protocol):
    """The handle a :class:`RuntimePort` returns — a framework-agnostic AG-UI
    app the host can mount and, where the backend is LangGraph-shaped,
    rehydrate against.

    **Optional member — ``thread_store``.** An adapter MAY expose the read half
    of :mod:`dna.runtime.thread_store` over its own backend (the LangGraph one
    does; MAF has no thread store yet and says so with ``None``). It is
    deliberately NOT a required member of this Protocol: making it one would
    flip ``isinstance`` for every adapter written before it existed. Probe it
    with ``getattr(app, "thread_store", None)``.
    """

    #: The servable object for host rehydration (e.g. a LangGraph graph).
    #: May be None for backends without LangGraph-shaped state (e.g. MAF).
    graph: Any

    def attach(self, app: Any, path: str = "/agui") -> None:
        """Mount this app's native AG-UI endpoint onto ``app`` at ``path``."""
        ...


@runtime_checkable
class RuntimePort(Protocol):
    """A framework adapter — builds a live :class:`AGUIApp` from a neutral
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
    """

    #: Stable backend id used on ``serving.framework``.
    target: str

    async def build(self, ctx: Any, hooks: RuntimeHooks) -> AGUIApp:
        """Build a live :class:`AGUIApp` from ``ctx`` + ``hooks``."""
        ...


class UnknownRuntime(Exception):
    """``serving.framework`` named a backend with no registered adapter."""

    def __init__(self, target: str, available: list[str]) -> None:
        self.target = target
        self.available = available
        super().__init__(
            f"no runtime registered for target {target!r}; "
            f"available: {', '.join(available) or '(none)'}"
        )


# ── registry ────────────────────────────────────────────────────────────

RUNTIME_REGISTRY: dict[str, RuntimePort] = {}


def register_runtime(runtime: RuntimePort) -> RuntimePort:
    """Register a runtime adapter under its ``target``. Last registration
    wins, so a host may override a built-in backend. Returns the runtime
    (an adapter is an instance, not a class, so hosts can parametrize it)."""
    RUNTIME_REGISTRY[runtime.target] = runtime
    return runtime


def get_runtime(target: str) -> RuntimePort:
    """Look up a registered runtime adapter or raise :class:`UnknownRuntime`."""
    _ensure_runtimes()
    try:
        return RUNTIME_REGISTRY[target]
    except KeyError:
        raise UnknownRuntime(target, available_runtimes()) from None


def available_runtimes() -> list[str]:
    """Sorted list of registered runtime target ids."""
    _ensure_runtimes()
    return sorted(RUNTIME_REGISTRY)


_BUILTINS_WIRED = False


def _ensure_runtimes() -> None:
    """Lazily register the in-tree runtime adapters on first registry access.
    Kept lazy so ``import dna.runtime.port`` stays cheap (no langchain / no
    agent-framework) and a host can register BEFORE the built-ins if it wants
    to shadow one.

    Each built-in import is independently guarded: the adapter modules
    (``dna.runtime.adapters.langchain_rt`` / ``.maf_rt``) may not exist yet
    (bring-up) or their extra may not be installed (``[runtime]`` / ``[maf]``)
    — either way we skip that one built-in rather than fail the whole
    registry, so ``available_runtimes()`` degrades gracefully to whatever is
    actually usable.
    """
    global _BUILTINS_WIRED
    if _BUILTINS_WIRED:
        return
    _BUILTINS_WIRED = True

    try:
        from dna.runtime.adapters.langchain_rt import LangChainRuntime

        RUNTIME_REGISTRY.setdefault("langchain", LangChainRuntime())
    except ImportError:
        pass

    try:
        from dna.runtime.adapters.maf_rt import MafRuntime

        RUNTIME_REGISTRY.setdefault("maf", MafRuntime())
    except ImportError:
        pass
