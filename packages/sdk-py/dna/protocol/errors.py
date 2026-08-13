"""The DNAP error table (spec §7) — one class, one code per named failure.

Every error a DNAP server puts on the wire is a :class:`DnapError`. It carries
the JSON-RPC ``code``/``message``/``data`` triple and nothing else, so the
dispatcher never has to guess how to serialise a failure.

⭐ **The rule that outranks the table** (spec §7): *an empty result and an
unanswerable question are different values, and a server MUST NOT collapse
them.* Nothing in this module — and nothing that catches a :class:`DnapError` —
may turn a failure into an empty collection. That is why the dispatcher's
catch-all answers :data:`INTERNAL_ERROR` rather than a default value: an
unexpected exception is *"I could not answer"*, and the only honest wire shape
for that is an error object.

The reserved JSON-RPC range ``-32000..-32099`` is where DNAP's own codes live.
The four codes below ``-32000`` (``-32700`` … ``-32603``) are JSON-RPC 2.0's
own and are reproduced here so a reader has one table, not two.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "CHANNEL_NOT_SERVED",
    "CURSOR_EXPIRED",
    "DnapError",
    "ERROR_NAMES",
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "KIND_NOT_SERVED",
    "METHOD_NOT_FOUND",
    "NOT_FOUND",
    "NOT_INITIALIZED",
    "NOT_WRITABLE",
    "PARSE_ERROR",
    "REFUSED",
    "RESOLUTION_INCOMPLETE",
    "REVISION_CONFLICT",
    "SEARCH_UNAVAILABLE",
    "VALIDATION_FAILED",
]

# ── JSON-RPC 2.0's own codes (§5.1 of that spec) ─────────────────────────────
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# ── DNAP's codes (spec §7) ──────────────────────────────────────────────────
#: The connection has not been initialized yet. Still NOT in §7's table — §4
#: says ``initialize`` is *"the first message on a connection"* without naming
#: the code for breaking that rule.
#:
#: ⚠️ This was ``-32002`` (what MCP uses for the identical condition) until the
#: clean-room revision assigned ``-32002`` to :data:`NOT_FOUND`. The spec wins,
#: and the collision is itself the argument for reporting a gap rather than
#: filling it quietly: two independent readers had already picked the same free
#: number for two different meanings.
NOT_INITIALIZED = -32000

#: The operation is understood, addressed correctly, and REFUSED by policy that
#: is NOT the Kind's writability — a layer policy that forbids the field, a
#: tenant that may not reach the scope, a store capability the deployment lacks.
#: Kind-level refusals have their own code (:data:`NOT_WRITABLE`); this one
#: exists so the remainder does not land in the dispatcher's catch-all and come
#: back as ``-32603 Internal error``, which tells the client the server broke
#: when in fact the server decided. "I will not" and "I could not" are the same
#: distinction §7 draws between an empty result and an unanswerable question,
#: one layer up. Not in §7's table; reported as a gap.
REFUSED = -32001

#: §7 — no instance by that name on that channel. The most common failure of
#: ``instances/get`` and ``instances/delete``, and it had no code at all until
#: the clean room asked for one (gap A2).
NOT_FOUND = -32002

KIND_NOT_SERVED = -32003
CHANNEL_NOT_SERVED = -32004
CURSOR_EXPIRED = -32005
#: §7 — the Kind is served but ``writable: false``. Answered from the catalog
#: BEFORE the store is touched, so a refusal a client could have predicted from
#: ``kinds/list`` costs it no write attempt.
NOT_WRITABLE = -32006
VALIDATION_FAILED = -32010
REVISION_CONFLICT = -32011
RESOLUTION_INCOMPLETE = -32020
SEARCH_UNAVAILABLE = -32030

#: code → the name the spec gives it. Used for the default ``message`` and for
#: tests that want to talk about a code by name. Derived from here, never
#: retyped: a table typed twice drifts.
ERROR_NAMES: dict[int, str] = {
    PARSE_ERROR: "Parse error",
    INVALID_REQUEST: "Invalid Request",
    METHOD_NOT_FOUND: "Method not found",
    INVALID_PARAMS: "Invalid params",
    INTERNAL_ERROR: "Internal error",
    NOT_INITIALIZED: "NOT_INITIALIZED",
    REFUSED: "REFUSED",
    NOT_FOUND: "NOT_FOUND",
    KIND_NOT_SERVED: "KIND_NOT_SERVED",
    CHANNEL_NOT_SERVED: "CHANNEL_NOT_SERVED",
    CURSOR_EXPIRED: "CURSOR_EXPIRED",
    NOT_WRITABLE: "NOT_WRITABLE",
    VALIDATION_FAILED: "VALIDATION_FAILED",
    REVISION_CONFLICT: "REVISION_CONFLICT",
    RESOLUTION_INCOMPLETE: "RESOLUTION_INCOMPLETE",
    SEARCH_UNAVAILABLE: "SEARCH_UNAVAILABLE",
}


class DnapError(Exception):
    """A failure with a place on the wire.

    ``message`` is the human sentence; ``data`` carries the machine members the
    spec names for a given code (``path``/``rule`` for
    :data:`VALIDATION_FAILED`, ``revision`` for :data:`REVISION_CONFLICT`,
    ``channel`` for :data:`CHANNEL_NOT_SERVED`, …). ``data`` is omitted from the
    wire when empty rather than sent as ``null``, because a member that is
    always present and usually null teaches its reader to skip it.
    """

    __slots__ = ("code", "data", "message")

    def __init__(
        self, code: int, message: str | None = None, /, **data: Any,
    ) -> None:
        self.code = int(code)
        self.message = message or ERROR_NAMES.get(self.code, "Server error")
        self.data: dict[str, Any] = {k: v for k, v in data.items()}
        super().__init__(f"[{self.code}] {self.message}")

    def to_wire(self) -> dict[str, Any]:
        """The JSON-RPC ``error`` object."""
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data:
            out["data"] = dict(self.data)
        return out

    # ── named constructors, one per rule the spec states ────────────────────

    @classmethod
    def channel_not_served(cls, channel: str, served: list[str]) -> DnapError:
        """§3: *"a server that does not serve a channel MUST answer -32004
        rather than substituting one it does serve."*

        ``served`` travels so the client can correct itself — that is the
        opposite of substitution: it names the alternatives instead of
        silently picking one.
        """
        return cls(
            CHANNEL_NOT_SERVED,
            f"this server does not serve the channel {channel!r}",
            channel=channel, served=list(served),
        )

    @classmethod
    def kind_not_served(cls, kind: str, channel: str) -> DnapError:
        """§4: a client that names an unadvertised Kind gets ``-32003``."""
        return cls(
            KIND_NOT_SERVED,
            f"{kind!r} is not in the Kind vocabulary advertised for "
            f"{channel!r} — take the vocabulary from `initialize` / "
            f"`kinds/list` and name no Kind of your own",
            kind=kind, channel=channel,
        )

    @classmethod
    def cursor_expired(cls, why: str) -> DnapError:
        """§6.2 rule 2: an expired cursor MUST say so *"so the client restarts
        rather than silently skipping."*"""
        return cls(CURSOR_EXPIRED, why)

    @classmethod
    def invalid_params(cls, message: str, **data: Any) -> DnapError:
        return cls(INVALID_PARAMS, message, **data)

    @classmethod
    def method_not_found(cls, method: str, **data: Any) -> DnapError:
        return cls(METHOD_NOT_FOUND, f"no such method: {method!r}", **data)
