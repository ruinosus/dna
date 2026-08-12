"""The DNAP dispatcher — transport-independent, method-agnostic.

:class:`DnapServer` owns one connection's worth of state (the session opened by
``initialize``) and turns a decoded JSON-RPC payload into a decoded JSON-RPC
response. It does **five** things and nothing else:

1. validate the envelope (:mod:`dna.protocol.jsonrpc`);
2. look the method up in the registry, refusing anything outside an advertised
   capability with ``-32601`` (spec §4);
3. resolve and refuse the ``channel`` (spec §3) — never substituting one;
4. call the handler;
5. translate a failure into a JSON-RPC ``error`` object.

It **never names a method.** ``initialize``, ``kinds/*`` and ``instances/*``
are registered in :mod:`dna.protocol.methods` exactly the way ``resolve/*`` and
``search/*`` will be — so adding them is a registration, not an edit here.

⛔ **The catch-all is an error, never a value.** Step 5 has one branch for a
:class:`~dna.protocol.errors.DnapError` and one for everything else, and the
second answers ``-32603``. There is no path in this file from an exception to
an empty list, a null result, or a default — spec §7: *"an empty result and an
unanswerable question are different values, and a server MUST NOT collapse
them."*
"""
from __future__ import annotations

import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from dna.protocol.channels import ROOT, Channel, ChannelSet, parse_channel
from dna.protocol.errors import (
    INTERNAL_ERROR,
    NOT_INITIALIZED,
    DnapError,
)
from dna.protocol.jsonrpc import (
    Request,
    decode_json,
    error_response,
    parse_message,
    split_batch,
    success_response,
)
from dna.protocol.registry import ChannelRequirement, MethodRegistry

logger = logging.getLogger(__name__)

__all__ = ["DnapServer", "RequestContext", "Session"]

PROTOCOL_VERSION = "1.0"


@dataclass
class Session:
    """What ``initialize`` established for this connection."""

    initialized: bool = False
    protocol_version: str | None = None
    client: dict[str, Any] = field(default_factory=dict)
    #: ⭐ What the CLIENT said it can do — and it is BINDING (§4): *"The
    #: effective capability set is the INTERSECTION of what the client sent and
    #: what the server answered. A client that did not ask for `write` cannot
    #: write, even against a server that offers it."* A declaration, not a
    #: decoration; the gate lives in
    #: :meth:`~dna.protocol.registry.MethodRegistry.resolve`.
    client_capabilities: dict[str, Any] = field(default_factory=dict)

    def wants(self, capability: str) -> bool:
        return capability in self.client_capabilities


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Everything a handler is given. One per request."""

    server: DnapServer
    session: Session
    request: Request
    channel: Channel

    @property
    def params(self) -> Mapping[str, Any]:
        return self.request.params

    @property
    def live(self) -> Any:
        return self.server.live

    @property
    def scope(self) -> str:
        """The scope this request acts on.

        For a scope channel it is the channel's scope. For the root channel it
        is the connection default — and every handler that accepts root echoes
        the channel it answered for, so the default is *stated*. This is not
        the substitution §3 forbids: that one is answering a request for scope
        A out of scope B; this one is answering ``dnap-root://``, which names
        no scope at all.
        """
        return self.channel.scope or self.server.channels.default_scope

    @property
    def tenant(self) -> str | None:
        return self.channel.tenant


class DnapServer:
    """One connection. Feed it decoded JSON, get decoded JSON back.

    ``live`` is a :class:`~dna.application.live.LiveDna` — the same object the
    MCP and REST faces are built on. DNAP is a third face over it, not a
    second implementation.
    """

    def __init__(
        self,
        live: Any,
        *,
        scopes: Collection[str] | None = None,
        tenants: Collection[str] | None = None,
        registry: MethodRegistry | None = None,
        server_info: Mapping[str, Any] | None = None,
        enabled_capabilities: Collection[str] | None = None,
    ) -> None:
        from dna.protocol.methods import builtin_registry

        self.live = live
        base = getattr(live, "base_scope", None)
        served = list(scopes) if scopes else ([base] if base else [])
        # ⚠️ ``tenants`` defaults to none served. A DNAP server does not own
        # the tenant registry, so it cannot know which tenants exist — and
        # the layer resolution underneath reads THROUGH to the base, which
        # means an undeclared tenant would be answered with the base scope's
        # content. See ChannelSet for the measurement.
        self.channels = ChannelSet(
            served, default=base if base in served else None, tenants=tenants,
        )
        self.registry = registry if registry is not None else builtin_registry()
        self._enabled: frozenset[str] | None = (
            frozenset(enabled_capabilities)
            if enabled_capabilities is not None else None
        )
        self.server_info: dict[str, Any] = dict(server_info or _default_server_info())
        self.session = Session()
        #: Bumped to evict every outstanding cursor at once — see
        #: :class:`~dna.protocol.cursor.Cursor`. A real server bumps it on
        #: restart or when it drops the snapshots it was holding; §6.2 rule 3
        #: is only affordable because that eviction is SAYABLE
        #: (``-32005``) rather than silent.
        self.cursor_generation = 0

    def expire_cursors(self) -> None:
        """Evict every outstanding cursor. The next page of any listing in
        flight answers ``-32005 CURSOR_EXPIRED`` and the client restarts."""
        self.cursor_generation += 1

    # ── capability surface ──────────────────────────────────────────────────

    def capabilities(self, ctx: RequestContext) -> dict[str, dict[str, Any]]:
        return self.registry.capabilities(ctx, enabled=self._enabled)

    # ── the dispatch ────────────────────────────────────────────────────────

    async def handle_text(self, text: str | bytes) -> str | None:
        """One framed message in, one framed message out (or ``None``).

        ``None`` means *"there is nothing to send"* — every message in the
        payload was a Notification. JSON-RPC 2.0 §4.1/§6 both require silence
        there, and silence is not an empty response.
        """
        import json

        try:
            payload = decode_json(text)
        except DnapError as exc:
            return json.dumps(error_response(None, exc))
        result = await self.handle_payload(payload)
        return None if result is None else json.dumps(result)

    async def handle_payload(self, payload: Any) -> Any:
        """Dispatch a decoded payload (single message or batch)."""
        try:
            messages, was_batch = split_batch(payload)
        except DnapError as exc:
            return error_response(None, exc)

        responses: list[Any] = []
        for raw in messages:
            answer = await self._handle_one(raw)
            if answer is not None:
                responses.append(answer)
        if not was_batch:
            return responses[0] if responses else None
        return responses or None

    async def _handle_one(self, raw: Any) -> Any | None:
        try:
            request = parse_message(raw)
        except DnapError as exc:
            # The envelope did not parse, so there is no reliable id to echo.
            ident = raw.get("id") if isinstance(raw, dict) else None
            return error_response(ident, exc)

        try:
            result = await self._invoke(request)
        except DnapError as exc:
            if request.is_notification:
                logger.debug(
                    "dnap: notification %s failed: %s", request.method, exc,
                )
                return None
            return error_response(request.response_id, exc)
        except Exception as exc:  # noqa: BLE001 — the catch-all IS the contract
            # ⛔ An unexpected failure is "I could not answer". It is reported
            # as an error, never as an empty or default result (spec §7).
            logger.exception("dnap: %s raised", request.method)
            if request.is_notification:
                return None
            return error_response(
                request.response_id,
                DnapError(
                    INTERNAL_ERROR,
                    f"{type(exc).__name__}: {exc}",
                    method=request.method,
                ),
            )
        if request.is_notification:
            return None
        return success_response(request.response_id, result)

    async def _invoke(self, request: Request) -> Any:
        spec = self.registry.resolve(
            request.method,
            enabled=self._enabled,
            # ``None`` before `initialize` — there is no declaration yet, and
            # no capability-bearing method is reachable anyway (the session
            # gate below fires first).
            client=(
                frozenset(self.session.client_capabilities)
                if self.session.initialized else None
            ),
        )
        if spec.requires_session and not self.session.initialized:
            raise DnapError(
                NOT_INITIALIZED,
                f"`initialize` must be the first message on a connection; "
                f"{request.method!r} arrived before it",
            )
        channel = self._resolve_channel(spec.channel, request.params)
        ctx = RequestContext(
            server=self, session=self.session, request=request, channel=channel,
        )
        return await spec.handler(ctx, request.params)

    def _resolve_channel(
        self, requirement: ChannelRequirement, params: Mapping[str, Any],
    ) -> Channel:
        if requirement is ChannelRequirement.NONE:
            return ROOT
        raw = params.get("channel")
        if raw is None:
            if requirement is ChannelRequirement.ROOT_OR_SCOPE:
                return ROOT
            raise DnapError.invalid_params(
                "`channel` is required: DNAP addresses what it acts on "
                "(spec §3). A scope passed as an option can be dropped in "
                "silence; an address cannot.",
                served=self.channels.advertised(),
            )
        channel = parse_channel(raw)
        if requirement is ChannelRequirement.SCOPE:
            return self.channels.require_scope(channel)
        return self.channels.require(channel)


def _default_server_info() -> dict[str, Any]:
    import importlib.metadata  # noqa: PLC0415

    try:
        version = importlib.metadata.version("dna-sdk")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover
        # Running from a source tree with no installed distribution. The
        # version is genuinely unknown here — ``initialize`` says so rather
        # than reporting a plausible one.
        version = "unknown"
    return {"name": "dna-sdk", "version": version}
