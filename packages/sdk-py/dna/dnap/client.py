"""A DNAP 1.0 client, held to §8's four client obligations.

Written from ``docs/spec/dnap-1.0-draft.md`` and from nothing else — in
particular not from a server, which was being built in parallel. The seam is
the wire: the client is handed an async ``endpoint(request) -> response`` and
never learns what is behind it.

The four obligations, and where each one lives
----------------------------------------------

1. ⭐ **Take the type vocabulary from ``initialize`` and name none of your own.**
   Every method that acts on a type takes it as an argument and checks it
   against what the server advertised (:meth:`DnapClient.check_kind`). There is
   no default, no fallback and no built-in list — a client with a fallback
   vocabulary is a client that names types of its own on the day the fallback
   is used. The guard is a scan of this module's AST against the live registry,
   so writing one literal here fails a test rather than earning a review
   comment.

2. **Treat ``revision`` as opaque.** It is carried as ``str`` and only ever
   compared for equality. Nothing here parses it, orders it or increments it —
   ``"4172"`` in the spec's example is a monotonic counter on ONE server and a
   hash on the next, and a client that read the first one's shape would break
   on the second.

3. **Preserve unknown ``metadata`` members on round-trip.** ``write_instance``
   copies metadata forward wholesale and removes exactly two members — ``id``
   and ``revision`` — because §5 says those are derived and MUST NOT be
   supplied. Everything else, known or not, travels back untouched. Dropping a
   member the client did not recognise would silently delete a server's data
   through a client that believed it was only saving.

4. **Restart a listing on ``-32005``.** :meth:`DnapClient.list_all` discards
   the pages it had and starts over, because a cursor that expired means the
   snapshot those pages belonged to is gone. The pages are buffered precisely
   so a restart is invisible to the caller: half a dead snapshot followed by
   half a live one is the quilt of moments §6.2 rule 3 exists to prevent.

A fifth thing this client does, which §8 asks of the SERVER: ``list_all``
verifies that every page it assembled carries the same ``revision`` and raises
:class:`DnapProtocolError` when they do not. A client that silently concatenated
pages from two snapshots would be the reason nobody ever noticed.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping, Sequence

__all__ = [
    "ChannelNotServed",
    "CursorExpired",
    "DERIVED_METADATA_MEMBERS",
    "DnapClient",
    "DnapError",
    "DnapProtocolError",
    "KindNotServed",
    "Page",
    "ResolutionIncomplete",
    "RevisionConflict",
    "SearchUnavailable",
    "ServerHello",
    "UnknownCapability",
    "UnknownKind",
    "ValidationFailed",
]

PROTOCOL_VERSION = "1.0"

#: §5 — server-minted and MUST NOT be supplied on write. Exactly these two:
#: everything else in ``metadata``, including members this client has never
#: heard of, is preserved on round-trip (§8, client rule 3).
DERIVED_METADATA_MEMBERS = ("id", "revision")

Endpoint = Callable[[Any], Awaitable[Any]]


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

class DnapError(Exception):
    """A JSON-RPC error the server sent, kept whole.

    ``data`` travels untouched: §6.2 puts the failing path and rule in there and
    §7 puts the current revision in there, and a client that summarised either
    would be the reason a caller could not recover.
    """

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"[{code}] {message}")


class KindNotServed(DnapError):
    """-32003 — the type is not in the advertised vocabulary."""


class ChannelNotServed(DnapError):
    """-32004 — this server does not serve that scope or tenant.

    Never silently retried against another channel. Scope is an address (§3);
    substituting one is the defect the code exists to make impossible.
    """


class CursorExpired(DnapError):
    """-32005 — restart the listing."""


class ValidationFailed(DnapError):
    """-32010 — with ``path`` and ``rule`` in :attr:`DnapError.data`."""


class RevisionConflict(DnapError):
    """-32011 — the stored revision moved under this write."""


class ResolutionIncomplete(DnapError):
    """-32020 — resolution ran and could not finish."""


class SearchUnavailable(DnapError):
    """-32030 — no plane could run. Distinct from an empty result, on purpose."""


_BY_CODE: dict[int, type[DnapError]] = {
    -32003: KindNotServed,
    -32004: ChannelNotServed,
    -32005: CursorExpired,
    -32010: ValidationFailed,
    -32011: RevisionConflict,
    -32020: ResolutionIncomplete,
    -32030: SearchUnavailable,
}


class DnapProtocolError(Exception):
    """The peer broke the protocol in a way no error code covers."""


class UnknownKind(DnapProtocolError):
    """The caller named a type the server never advertised.

    Raised locally, before anything goes on the wire. The server would answer
    ``-32003`` anyway; catching it here means the message can name the whole
    vocabulary the caller could have used, which the server's refusal cannot.
    """


class UnknownCapability(DnapProtocolError):
    """The caller asked for a family this connection does not carry.

    §4 makes an unadvertised method ``-32601`` at the server; the client refuses
    first for the same reason — a capability was advertised so it could be read.
    """


# ---------------------------------------------------------------------------
# values
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ServerHello:
    """What ``initialize`` came back with, kept whole.

    :attr:`raw` is the untouched result. Members this client version has never
    heard of stay reachable there rather than being dropped at the door.
    """

    protocol_version: str
    server: Mapping[str, Any]
    channels: tuple[str, ...]
    kinds: tuple[str, ...]
    capabilities: Mapping[str, Any]
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Page:
    """One page of a listing, with the snapshot it belongs to.

    ``revision`` is opaque (§8, client rule 2): compare it for equality, never
    parse it.
    """

    instances: tuple[Any, ...]
    revision: str | None
    cursor: str | None
    selected: Any = None

    @property
    def exhausted(self) -> bool:
        """§6.2 — the cursor is absent when the listing is exhausted."""
        return not self.cursor


# ---------------------------------------------------------------------------
# the client
# ---------------------------------------------------------------------------

class DnapClient:
    """Speaks DNAP 1.0 to an endpoint, and knows nothing about what it stores.

    ``endpoint`` is an async callable taking a decoded JSON-RPC request and
    returning the decoded response — stdio, HTTP or an in-process call all look
    the same from here.
    """

    #: How many times :meth:`list_all` restarts before giving up. A cursor that
    #: expires faster than the listing can be walked is a server problem, and
    #: retrying forever would turn it into a hang instead of a report.
    max_cursor_restarts = 3

    def __init__(
        self,
        endpoint: Endpoint,
        *,
        name: str = "dna-dnap-client",
        version: str = "1.0",
        capabilities: Mapping[str, Any] | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._name = name
        self._version = version
        self._requested = dict(
            capabilities if capabilities is not None
            else {"resolve": {}, "search": {}, "watch": {}, "write": {}}
        )
        self._id = 0
        self._hello: ServerHello | None = None

    # -- connection ------------------------------------------------------

    async def connect(self) -> ServerHello:
        """Send ``initialize`` and adopt the vocabulary that comes back."""
        result = await self._call("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "client": {"name": self._name, "version": self._version},
            "capabilities": self._requested,
        })
        if not isinstance(result, dict):
            raise DnapProtocolError(f"initialize returned {result!r}, not an object")
        kinds = result.get("kinds")
        if not isinstance(kinds, list) or not all(isinstance(k, str) for k in kinds):
            raise DnapProtocolError(
                f"initialize advertised kinds={kinds!r}. This client takes its whole "
                f"vocabulary from that member and has no fallback to reach for — a "
                f"fallback would be exactly the thing §8 forbids it to have."
            )
        channels = result.get("channels")
        if not isinstance(channels, list) or not all(isinstance(c, str) for c in channels):
            raise DnapProtocolError(
                f"initialize advertised channels={channels!r}; every request carries "
                f"a channel (§3)"
            )
        caps = result.get("capabilities")
        self._hello = ServerHello(
            protocol_version=str(result.get("protocolVersion") or ""),
            server=dict(result.get("server") or {}),
            channels=tuple(channels),
            kinds=tuple(kinds),
            capabilities=dict(caps if isinstance(caps, dict) else {}),
            raw=result,
        )
        return self._hello

    async def __aenter__(self) -> "DnapClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    @property
    def hello(self) -> ServerHello:
        if self._hello is None:
            raise DnapProtocolError(
                "not connected — call connect() first. Nothing can be asked before "
                "initialize because the vocabulary to ask it in arrives there."
            )
        return self._hello

    @property
    def kinds(self) -> tuple[str, ...]:
        """The type vocabulary, exactly as the server advertised it."""
        return self.hello.kinds

    @property
    def channels(self) -> tuple[str, ...]:
        return self.hello.channels

    @property
    def capabilities(self) -> Mapping[str, Any]:
        return self.hello.capabilities

    @property
    def protocol_version(self) -> str:
        return self.hello.protocol_version

    def supports(self, family: str) -> bool:
        return family in self.hello.capabilities

    # -- the two guards --------------------------------------------------

    def check_kind(self, kind: str) -> str:
        """⭐ Client obligation 1, in one method.

        Everything that acts on a type funnels through here, so "the client
        names no type of its own" has exactly one place it could be violated —
        and that place has no literal in it.
        """
        if kind not in self.hello.kinds:
            raise UnknownKind(
                f"{kind!r} is not in the vocabulary this server advertised. "
                f"It serves: {', '.join(self.hello.kinds) or '(nothing)'}"
            )
        return kind

    def _check_capability(self, family: str, method: str) -> None:
        if not self.supports(family):
            raise UnknownCapability(
                f"{method} belongs to the {family!r} capability, which this "
                f"connection did not advertise. Advertised: "
                f"{', '.join(sorted(self.hello.capabilities)) or '(none)'}"
            )

    # -- wire ------------------------------------------------------------

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def _call(self, method: str, params: Any = None) -> Any:
        rid = self._next_id()
        request: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            request["params"] = params
        response = await self._endpoint(request)
        if not isinstance(response, dict):
            raise DnapProtocolError(
                f"{method} answered {response!r}, not a JSON-RPC response object")
        if response.get("id") != rid:
            raise DnapProtocolError(
                f"{method} answered id {response.get('id')!r} for request {rid!r}")
        if "error" in response:
            err = response["error"] or {}
            code = err.get("code")
            cls = _BY_CODE.get(code, DnapError)
            raise cls(code, str(err.get("message") or ""), err.get("data"))
        if "result" not in response:
            raise DnapProtocolError(
                f"{method} answered neither result nor error: {response!r}")
        return response["result"]

    # -- vocabulary ------------------------------------------------------

    async def list_kinds(self, *, channel: str) -> list[dict[str, Any]]:
        """The descriptors a channel serves (§6.1)."""
        result = await self._call("kinds/list", {"channel": channel})
        entries = result.get("kinds") if isinstance(result, dict) else None
        if not isinstance(entries, list):
            raise DnapProtocolError(f"kinds/list returned {result!r}")
        return entries

    async def describe_kind(self, *, channel: str, kind: str) -> Any:
        """The schema of ``spec`` for one type, plus its declared relations."""
        return await self._call(
            "kinds/describe", {"channel": channel, "kind": self.check_kind(kind)})

    # -- instances -------------------------------------------------------

    async def list_instances(
        self, *, channel: str, kind: str,
        select: Any = None, limit: int | None = None, cursor: str | None = None,
    ) -> Page:
        """One page. Raises :class:`CursorExpired` verbatim — see :meth:`list_all`
        for the restart obligation."""
        params: dict[str, Any] = {"channel": channel, "kind": self.check_kind(kind)}
        if select is not None:
            params["select"] = select
        if limit is not None:
            params["limit"] = limit
        if cursor is not None:
            params["cursor"] = cursor
        result = await self._call("instances/list", params)
        if not isinstance(result, dict) or not isinstance(result.get("instances"), list):
            raise DnapProtocolError(f"instances/list returned {result!r}")
        revision = result.get("revision")
        return Page(
            instances=tuple(result["instances"]),
            revision=str(revision) if revision is not None else None,
            cursor=result.get("cursor") or None,
            selected=result.get("selected"),
        )

    async def iter_pages(
        self, *, channel: str, kind: str,
        select: Any = None, limit: int | None = None,
    ) -> AsyncIterator[Page]:
        """Walk the cursor, raw. Propagates :class:`CursorExpired` to the caller."""
        cursor: str | None = None
        while True:
            page = await self.list_instances(
                channel=channel, kind=kind, select=select, limit=limit, cursor=cursor)
            yield page
            if page.exhausted:
                return
            cursor = page.cursor

    async def list_all(
        self, *, channel: str, kind: str,
        select: Any = None, limit: int | None = None,
    ) -> Page:
        """⭐ Client obligation 4 — the whole listing, from ONE snapshot.

        Pages are buffered and only handed back once the cursor reports
        exhaustion. On ``-32005`` the buffer is thrown away and the walk starts
        over from no cursor: an expired cursor means the snapshot the earlier
        pages came from is gone, so keeping them would assemble the quilt of
        moments §6.2 rule 3 exists to prevent — and assuming exhaustion, which
        is the other tempting reading, would silently drop the tail.

        The returned :class:`Page` is always exhausted, and its ``revision`` is
        the one every page agreed on.
        """
        self.check_kind(kind)
        for attempt in range(self.max_cursor_restarts + 1):
            buffered: list[Any] = []
            revisions: list[str | None] = []
            cursor: str | None = None
            selected: Any = None
            restarted = False
            while True:
                try:
                    page = await self.list_instances(
                        channel=channel, kind=kind, select=select,
                        limit=limit, cursor=cursor)
                except CursorExpired:
                    restarted = True
                    break
                buffered.extend(page.instances)
                revisions.append(page.revision)
                selected = page.selected
                if page.exhausted:
                    break
                cursor = page.cursor
            if restarted:
                continue
            distinct = {r for r in revisions if r is not None}
            if len(distinct) > 1:
                raise DnapProtocolError(
                    f"the pages of one listing reported different revisions "
                    f"{sorted(distinct)!r}. §6.2 rule 3 makes a listing one "
                    f"snapshot; concatenating these would produce a state that "
                    f"never existed, so this client refuses to rather than let "
                    f"the caller find out later."
                )
            return Page(
                instances=tuple(buffered),
                revision=next(iter(distinct), None),
                cursor=None,
                selected=selected,
            )
        raise DnapProtocolError(
            f"the listing cursor expired {self.max_cursor_restarts + 1} times in a "
            f"row. Restarting again would be a hang; this is a report."
        )

    async def get_instance(
        self, *, channel: str, kind: str, name: str,
        if_none_match: str | None = None,
    ) -> Any:
        """One instance, verbatim. With ``if_none_match`` the server may answer
        ``{"notModified": true}`` and no body (§6.2)."""
        params: dict[str, Any] = {
            "channel": channel, "kind": self.check_kind(kind), "name": name,
        }
        if if_none_match is not None:
            params["ifNoneMatch"] = if_none_match
        return await self._call("instances/get", params)

    async def write_instance(
        self, instance: Mapping[str, Any], *, channel: str,
        if_match: str | None = None,
    ) -> Any:
        """⭐ Client obligation 3 — upsert, with unknown metadata preserved.

        The caller's mapping is deep-copied and sent forward whole. Exactly the
        two derived members named in §5 are removed; every other member of
        ``metadata``, including ones this client has never heard of, survives.
        A client that kept only the members it recognised would delete a
        server's data on a read-modify-write, and the caller would see a
        successful save.
        """
        body = copy.deepcopy(dict(instance))
        kind = body.get("kind")
        if not isinstance(kind, str):
            raise DnapProtocolError(
                f"the instance names no type in its 'kind' member: {sorted(body)!r}")
        self.check_kind(kind)
        metadata = body.get("metadata")
        if isinstance(metadata, Mapping):
            body["metadata"] = {
                key: value for key, value in metadata.items()
                if key not in DERIVED_METADATA_MEMBERS
            }
        params: dict[str, Any] = {"channel": channel, "instance": body}
        if if_match is not None:
            params["ifMatch"] = if_match
        return await self._call("instances/write", params)

    async def delete_instance(
        self, *, channel: str, kind: str, name: str, if_match: str | None = None,
    ) -> Any:
        params: dict[str, Any] = {
            "channel": channel, "kind": self.check_kind(kind), "name": name,
        }
        if if_match is not None:
            params["ifMatch"] = if_match
        return await self._call("instances/delete", params)

    # -- resolution ------------------------------------------------------

    async def resolve_agent(self, *, channel: str, name: str) -> Any:
        """§6.3 — the method that justifies this protocol."""
        self._check_capability("resolve", "resolve/agent")
        return await self._call("resolve/agent", {"channel": channel, "name": name})

    async def resolve_copilot(self, *, channel: str, name: str) -> Any:
        """§6.3 — a served surface, resolved into the same neutral shape."""
        self._check_capability("resolve", "resolve/copilot")
        return await self._call("resolve/copilot", {"channel": channel, "name": name})

    # -- search ----------------------------------------------------------

    async def search_instances(
        self, *, channel: str, kind: str, query: str,
        k: int | None = None,
        narrow: Mapping[str, Any] | None = None,
        min_similarity: float | None = None,
    ) -> Any:
        """§6.4 — one search method, over instances of a type the server named.

        ``min_similarity`` is passed only when the CALLER supplies one. There is
        no default here and there must not be: §6.4 rule 2 makes the threshold
        the caller's policy, and a client that shipped a default would be
        inventing the very judgement the server refuses to make.
        """
        self._check_capability("search", "search/instances")
        params: dict[str, Any] = {
            "channel": channel, "kind": self.check_kind(kind), "query": query,
        }
        if k is not None:
            params["k"] = k
        if narrow is not None:
            params["narrow"] = dict(narrow)
        if min_similarity is not None:
            params["minSimilarity"] = min_similarity
        return await self._call("search/instances", params)

    # -- batching --------------------------------------------------------

    async def batch(self, calls: Sequence[tuple[str, Any]]) -> list[Any]:
        """§2 — several requests in one round trip, answers returned in the order
        the calls were given (JSON-RPC does not promise response order, so they
        are paired by id here)."""
        requests = []
        order: list[int] = []
        for method, params in calls:
            rid = self._next_id()
            order.append(rid)
            request: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
            if params is not None:
                request["params"] = params
            requests.append(request)
        responses = await self._endpoint(requests)
        if not isinstance(responses, list):
            raise DnapProtocolError(
                f"a batch of {len(requests)} answered {responses!r}, not a list. "
                f"§2 makes batch support a server MUST.")
        by_id = {r.get("id"): r for r in responses if isinstance(r, dict)}
        out: list[Any] = []
        for rid in order:
            response = by_id.get(rid)
            if response is None:
                raise DnapProtocolError(f"the batch response has no entry for id {rid}")
            if "error" in response:
                err = response["error"] or {}
                cls = _BY_CODE.get(err.get("code"), DnapError)
                out.append(cls(err.get("code"), str(err.get("message") or ""),
                               err.get("data")))
            else:
                out.append(response.get("result"))
        return out
