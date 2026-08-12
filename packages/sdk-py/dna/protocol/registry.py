"""The method registry — ⭐ **the extension point**.

A DNAP server is a dispatcher plus a ``{name: handler}`` table. Everything the
dispatcher does — envelope validation, channel resolution, capability gating,
error translation — reads the table; it never names a method. So a new family
of methods is **registered**, never wired:

.. code-block:: python

    from dna.protocol import MethodRegistry, builtin_registry

    registry = builtin_registry().extended()      # a copy; the builtin is frozen

    @registry.method("resolve/agent", capability="resolve")
    async def resolve_agent(ctx, params):
        ...

    registry.declare_capability(
        "resolve", lambda ctx: {"agent": True, "copilot": True},
    )

    server = DnapServer(live, scopes=["dna-cloud"], registry=registry)

That is the whole contract for wave 2 (``resolve/*``, ``search/*``). Nothing in
:mod:`dna.protocol.server` changes, and nothing in :mod:`dna.protocol.methods`
is touched.

⭐ **Capabilities are DERIVED from the table, never enumerated beside it.** The
``capabilities`` block of the ``initialize`` result is
``{spec.capability for spec in registry}`` — so registering ``resolve/agent``
is what makes the server advertise ``resolve``, and a capability can never be
advertised with no method behind it (nor a method served outside an advertised
capability, which spec §4 requires to answer ``-32601``). A hand-typed list
beside the table is the shape that goes stale, and this repo has paid for that
shape before (the guards that stayed green while going blind).

``declare_capability`` supplies the *detail* object a capability advertises
(``{"planes": ["lexical","semantic"]}`` for search, ``{}`` by default). It
cannot bring a capability into existence on its own — declaring detail for a
capability no method claims raises, because that would be exactly the
enumeration this design removes.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from dna.protocol.errors import DnapError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from dna.protocol.server import RequestContext

__all__ = ["ChannelRequirement", "MethodRegistry", "MethodSpec"]

Handler = Callable[["RequestContext", Mapping[str, Any]], Awaitable[Any]]
DetailProvider = Callable[["RequestContext"], Mapping[str, Any]]


class ChannelRequirement(str, Enum):
    """What a method wants from the ``channel`` parameter (spec §3).

    ``SCOPE`` — the method acts on instances and needs a scope channel; the
    root channel is refused with ``-32004`` rather than resolved to a default.

    ``ROOT_OR_SCOPE`` — ``kinds/*``: the vocabulary is a property of a channel,
    and the root channel means *"the connection's default"*. The result always
    echoes the channel it answered for, so a default is stated, not assumed.

    ``NONE`` — ``initialize``, which is what establishes the channels.
    """

    SCOPE = "scope"
    ROOT_OR_SCOPE = "root_or_scope"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class MethodSpec:
    name: str
    handler: Handler
    capability: str | None = None
    channel: ChannelRequirement = ChannelRequirement.SCOPE
    #: Whether the connection must have completed ``initialize`` first.
    requires_session: bool = True


class MethodRegistry:
    """``{name: MethodSpec}`` plus the capability detail providers.

    Freeze a registry (:meth:`frozen`) to publish it as a shared default;
    :meth:`extended` hands back a mutable copy so one server's additions never
    leak into another's.
    """

    def __init__(self) -> None:
        self._methods: dict[str, MethodSpec] = {}
        self._details: dict[str, DetailProvider] = {}
        self._frozen = False

    # ── writing ─────────────────────────────────────────────────────────────

    def register(self, spec: MethodSpec) -> MethodSpec:
        self._assert_mutable()
        if spec.name in self._methods:
            raise ValueError(
                f"method {spec.name!r} is already registered — a second "
                f"registration would silently shadow the first"
            )
        self._methods[spec.name] = spec
        return spec

    def method(
        self,
        name: str,
        *,
        capability: str | None = None,
        channel: ChannelRequirement = ChannelRequirement.SCOPE,
        requires_session: bool = True,
    ) -> Callable[[Handler], Handler]:
        """Decorator form of :meth:`register`."""

        def decorate(handler: Handler) -> Handler:
            self.register(MethodSpec(
                name=name, handler=handler, capability=capability,
                channel=channel, requires_session=requires_session,
            ))
            return handler

        return decorate

    def declare_capability(self, name: str, detail: DetailProvider) -> None:
        """Attach the detail object a capability advertises.

        Raises when no registered method claims ``name`` — see the module
        docstring: detail describes a capability, it cannot conjure one.
        """
        self._assert_mutable()
        if name not in self.capability_names():
            raise ValueError(
                f"cannot declare detail for capability {name!r}: no registered "
                f"method claims it. Register the method first — capabilities "
                f"are derived from the method table, not listed beside it."
            )
        self._details[name] = detail

    # ── reading ─────────────────────────────────────────────────────────────

    def get(self, name: str) -> MethodSpec | None:
        return self._methods.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._methods))

    def capability_names(self) -> frozenset[str]:
        """Every capability claimed by at least one registered method."""
        return frozenset(
            spec.capability for spec in self._methods.values()
            if spec.capability
        )

    def capabilities(
        self, ctx: RequestContext, *, enabled: frozenset[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """The ``capabilities`` block of the ``initialize`` result."""
        names = self.capability_names()
        if enabled is not None:
            names = frozenset(n for n in names if n in enabled)
        out: dict[str, dict[str, Any]] = {}
        for name in sorted(names):
            provider = self._details.get(name)
            out[name] = dict(provider(ctx)) if provider else {}
        return out

    def resolve(
        self,
        name: str,
        *,
        enabled: frozenset[str] | None,
        client: frozenset[str] | None = None,
    ) -> MethodSpec:
        """The spec for ``name``, or ``-32601``.

        ⭐ Spec §4, following AHP: *"a method outside every advertised
        capability MUST be rejected with -32601 Method not found"* — not
        silently ignored, and not answered with a degraded result. A registered
        method whose capability is out of reach is therefore indistinguishable
        from a method that does not exist, which is the point: the client's
        picture of the server comes from ``initialize``, and nothing outside it
        is reachable.

        ⭐ **Out of reach means out of the INTERSECTION** (§4, closing clean-room
        gap A6): *"The effective capability set is the INTERSECTION of what the
        client sent and what the server answered. A client that did not ask for
        `write` cannot write, even against a server that offers it."* The two
        readings — the client's field is a declaration, or it is decorative —
        *disagree about whether a call succeeds*, which is why the spec fixed
        one. ``client`` is ``None`` only before ``initialize`` has run, and no
        capability-bearing method is reachable then anyway.
        """
        spec = self._methods.get(name)
        if spec is None:
            raise DnapError.method_not_found(name)
        if spec.capability is None:
            return spec
        if enabled is not None and spec.capability not in enabled:
            raise DnapError.method_not_found(
                name,
                reason=(
                    f"the {spec.capability!r} capability is not advertised by "
                    f"this server"
                ),
            )
        if client is not None and spec.capability not in client:
            raise DnapError.method_not_found(
                name,
                reason=(
                    f"this connection did not declare the {spec.capability!r} "
                    f"capability at `initialize`; the effective set is the "
                    f"intersection of the client's and the server's (spec §4). "
                    f"Reconnect declaring it."
                ),
            )
        return spec

    def __iter__(self) -> Iterator[MethodSpec]:
        return iter(self._methods.values())

    def __len__(self) -> int:
        return len(self._methods)

    # ── lifecycle ───────────────────────────────────────────────────────────

    def frozen(self) -> MethodRegistry:
        self._frozen = True
        return self

    def extended(self) -> MethodRegistry:
        """A mutable copy — the way a caller adds methods to a shared default."""
        clone = MethodRegistry()
        clone._methods = dict(self._methods)
        clone._details = dict(self._details)
        return clone

    def _assert_mutable(self) -> None:
        if self._frozen:
            raise RuntimeError(
                "this registry is frozen (it is a shared default). Call "
                "`.extended()` for a mutable copy."
            )
