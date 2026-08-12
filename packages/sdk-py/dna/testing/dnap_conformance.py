"""DNAP 1.0 conformance suite — derived from the SPEC, never from a server.

The suite in this module was written against ``docs/spec/dnap-1.0-draft.md``
**while a server was being implemented in parallel, without reading it.** That
order is the whole value: a suite derived from an implementation passes by
construction and proves nothing. Every case below cites the section of the spec
it enforces, and every case exists because the spec makes a claim that a server
can violate.

Consumption contract
--------------------

``dnap_conformance_suite(factory)`` returns a list of :class:`DnapCase`. Each
``case.run()`` builds a FRESH server via ``factory``, opens a connection
(``initialize``), runs its assertions, and always awaits the harness cleanup.

``factory`` is an async zero-arg callable returning ONE of:

* a bare async ``endpoint(request) -> response`` callable;
* ``(server, cleanup)`` where ``server`` is such a callable or an object
  exposing one of ``handle`` / ``dispatch`` / ``call`` / ``request`` /
  ``__call__``;
* a :class:`DnapHarness`, which is the same thing plus the optional hooks the
  hard cases need.

⭐ **The seam is the WIRE, not your code.** ``endpoint`` takes a decoded
JSON-RPC request (a dict, or a list for a batch) and returns the decoded
response (a dict, a list, or ``None`` for a notification). Nothing above the
JSON-RPC envelope is assumed, so a server behind stdio, HTTP or an in-process
call all plug in the same way. The suite builds and reads envelopes with the
stdlib on purpose — a JSON-RPC helper library would normalise away exactly the
framing defects §2 exists to catch.

Four outcomes, not two
----------------------

A conformance suite whose only outcomes are pass and skip lies twice: it lets
"never ran" read as "passed", and it lets "cannot be seen from outside" read as
"is fine". So a case ends in one of four states:

``pass``
    the obligation was observed to hold.
``fail``
    the obligation was observed to be violated.
``NOT RUN`` (:class:`DnapCaseNotApplicable`)
    the server honestly does not advertise the capability the case needs. The
    exception CANNOT be constructed without naming both what was missing and
    what consequently went unchecked — a bare skip is a ``ValueError``.
``unverified`` (:class:`DnapRuleUnverified`)
    the obligation is not observable through the wire and the harness offered
    no hook to induce it. This is **not** a skip: it is an AssertionError, it
    fails a pytest run, and :attr:`DnapConformanceReport.ok` is False while any
    exist. Unverified is not conformant.

A fifth outcome, :class:`DnapSpecGap`, reports a case that cannot be written
because the *specification* is underdetermined. It is a finding against the
spec rather than the server — and it is still never a pass.

The empty-collection rule, and how it is actually tested
--------------------------------------------------------

§7's rule ("an empty result and an unanswerable question are different values")
outranks the error table, and it is the easiest rule in the document to test
uselessly. Asking a healthy server a healthy question and observing that it did
not lie proves nothing. So it is tested in four layers, from cheapest to
strongest:

1. **A positive control.** Every negative probe first asserts that the SAME
   request shape, on a served channel with a served Kind, SUCCEEDS. Without
   this, a server that errors on absolutely everything passes every negative
   probe in the suite. (:func:`_positive_control`)
2. **Falsifiability of ``[]``.** An empty collection must be a reading of a
   store, not a constant: the suite writes an instance and requires the same
   listing to stop being empty. A server whose ``[]`` cannot be falsified was
   never reading anything.
3. **The three refusals that servers turn into ``[]``** — an unserved channel,
   an unadvertised Kind, and a cursor the server never minted. Each must be an
   error; each is separately asserted NOT to be an empty collection, so the
   report names which shape of the rule broke.
4. **Induced failure.** If the harness supplies ``break_store``, the suite
   breaks the store and requires an error. If it does not, the case ends
   ``unverified`` — the rule that cost the reference implementation the most is
   not something a server gets a green on by declining to be tested.
"""
from __future__ import annotations

import unittest
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Sequence

__all__ = [
    "CHANNEL_NOT_SERVED",
    "CURSOR_EXPIRED",
    "DNAP_PROTOCOL_VERSION",
    "DnapCase",
    "DnapCaseNotApplicable",
    "DnapConformanceReport",
    "DnapHarness",
    "DnapRuleUnverified",
    "DnapSpecGap",
    "INVALID_PARAMS",
    "KIND_NOT_SERVED",
    "METHOD_NOT_FOUND",
    "RESOLUTION_INCOMPLETE",
    "REVISION_CONFLICT",
    "SEARCH_UNAVAILABLE",
    "VALIDATION_FAILED",
    "dnap_conformance_suite",
    "run_dnap_conformance",
]

#: The protocol version this suite speaks (§4).
DNAP_PROTOCOL_VERSION = "1.0"

# -- §7 error table. These are the answers the spec froze; they are constants,
#    not a count of anything, so pinning them does not freeze the surface.
KIND_NOT_SERVED = -32003
CHANNEL_NOT_SERVED = -32004
CURSOR_EXPIRED = -32005
VALIDATION_FAILED = -32010
REVISION_CONFLICT = -32011
RESOLUTION_INCOMPLETE = -32020
SEARCH_UNAVAILABLE = -32030
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

#: §3 — the connection-level channel.
ROOT_CHANNEL = "dnap-root://"

#: §5 — derived metadata, which a client MUST NOT supply on write.
DERIVED_METADATA_MEMBERS = ("id", "revision")

#: §6.3 — the members deliberately ABSENT from a resolution. Each of these
#: leaked into a definition contract in the reference implementation and became
#: a runtime the definition could no longer leave. Matched case-insensitively
#: against the resolved object's own keys, so ``checkpointer`` and
#: ``checkPointer`` are the same finding.
HOST_CONCERNS = (
    "checkpointer", "checkpoint", "store", "threadindex", "threads",
    "telemetry", "tracing", "costtable", "costs", "sink",
)

Cleanup = Callable[[], Awaitable[None]]
Endpoint = Callable[[Any], Awaitable[Any]]


# ---------------------------------------------------------------------------
# outcomes
# ---------------------------------------------------------------------------

class DnapCaseNotApplicable(unittest.SkipTest):
    """The server honestly does not advertise what this case needs.

    ⚠️ The constructor REFUSES a bare reason. "Did not run" must never be
    readable as "passed", so a skip has to name two things: what was missing,
    and what obligation therefore went unchecked. A caller that has nothing to
    say for the second is a caller who should not be skipping.
    """

    def __init__(self, *, missing: str, unchecked: str) -> None:
        if not (missing or "").strip():
            raise ValueError("a DNAP skip must name what was missing")
        if not (unchecked or "").strip():
            raise ValueError(
                "a DNAP skip must name the obligation that went unchecked — "
                "an unexplained skip reads as a pass, which is the failure mode "
                "this suite exists to refuse"
            )
        self.missing = missing
        self.unchecked = unchecked
        super().__init__(f"NOT RUN — {missing}. UNCHECKED: {unchecked}")


class DnapRuleUnverified(AssertionError):
    """The obligation is not observable through the wire, and the harness gave
    no hook to induce it.

    Deliberately an ``AssertionError`` and not a skip. A server does not earn a
    green on §7's central rule by being un-testable; the report counts this
    against conformance and ``raise_if_failed`` raises on it.
    """

    def __init__(self, *, rule: str, needs: str) -> None:
        self.rule = rule
        self.needs = needs
        super().__init__(
            f"UNVERIFIED — {rule} cannot be observed from outside. "
            f"Supply {needs} on the DnapHarness to make it testable. "
            f"Unverified is not conformant."
        )


class DnapSpecGap(AssertionError):
    """The specification does not determine what this case would have to assert.

    A finding against the SPEC, not against the server — and still never a pass.
    Reported in its own bucket so the holes are readable as a list.
    """

    def __init__(self, *, section: str, question: str) -> None:
        self.section = section
        self.question = question
        super().__init__(f"SPEC GAP ({section}) — {question}")


class DnapViolation(AssertionError):
    """A conformance failure. Carries the section so the report reads as a
    verdict against the document rather than against a test file."""

    def __init__(self, section: str, message: str) -> None:
        self.section = section
        super().__init__(f"[{section}] {message}")


def _violation(section: str, message: str) -> DnapViolation:
    return DnapViolation(section, message)


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------

@dataclass
class DnapHarness:
    """What a factory hands the suite. Only ``endpoint`` is required.

    The optional members are the hooks for obligations that cannot be observed
    from outside. Every one of them, when absent, turns its case ``unverified``
    or ``NOT RUN`` with a message that names what it would have checked — so
    the cost of not wiring a hook is visible rather than silent.
    """

    #: The wire: ``await endpoint(request_json) -> response_json | None``.
    endpoint: Endpoint
    #: Released after every case.
    cleanup: Cleanup | None = None
    #: Put the backing store into a failing state. The suite then requires an
    #: ERROR from ``instances/list`` — never ``{"instances": []}`` (§7).
    break_store: Callable[[], Awaitable[None]] | None = None
    #: Make every search plane unavailable. The suite then requires
    #: ``-32030 SEARCH_UNAVAILABLE`` — never empty ``hits`` (§6.4 rule 5).
    break_search: Callable[[], Awaitable[None]] | None = None
    #: Leave a definition resolvable-but-incomplete under the returned name.
    #: The suite then requires ``-32020`` — never a result with filled gaps.
    break_resolution: Callable[[], Awaitable[str]] | None = None
    #: Expire every outstanding cursor. Without it the suite can only probe a
    #: cursor the server never minted, which is a weaker question.
    expire_cursors: Callable[[], Awaitable[None]] | None = None
    #: Drain server→client notifications observed since the connection opened.
    #: A request/response callable cannot express a server-initiated message,
    #: so §6.5 is unreachable without this.
    drain_notifications: Callable[[], Awaitable[Sequence[dict]]] | None = None
    #: Seed ``count`` instances of ``kind`` on ``channel`` out of band, for a
    #: server that serves a Kind the suite cannot synthesise a valid spec for.
    #: Returns the names it created.
    seed: Callable[..., Awaitable[Sequence[str]]] | None = None
    #: A name this suite may resolve when ``resolve`` is advertised. Without it
    #: the suite resolves the first prompt-target instance it can find.
    resolvable_name: str | None = None


async def _harness(factory: Callable[[], Awaitable[Any]]) -> DnapHarness:
    built = await factory()
    if isinstance(built, DnapHarness):
        return built
    server, cleanup = built if isinstance(built, tuple) else (built, None)
    return DnapHarness(endpoint=_as_endpoint(server), cleanup=cleanup)


def _as_endpoint(server: Any) -> Endpoint:
    """Duck-type an endpoint out of whatever the factory returned.

    The suite and the server agree on the WIRE, so the suite must not care what
    the method that carries it is called. Tried in order; the first that is
    callable wins.
    """
    if callable(server) and not isinstance(server, type):
        for name in ("handle", "dispatch", "call", "request"):
            fn = getattr(server, name, None)
            if callable(fn):
                return fn
        return server
    for name in ("handle", "dispatch", "call", "request", "__call__"):
        fn = getattr(server, name, None)
        if callable(fn):
            return fn
    raise TypeError(
        f"{type(server).__name__} exposes no DNAP endpoint. The suite needs an "
        f"async callable taking a decoded JSON-RPC request and returning the "
        f"decoded response — as the object itself, or as .handle/.dispatch/"
        f".call/.request."
    )


# ---------------------------------------------------------------------------
# session
# ---------------------------------------------------------------------------

def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class _Session:
    """One connection: sends ``initialize`` once and remembers what came back.

    Deliberately thin. It never interprets a result beyond the JSON-RPC
    envelope, because every interpretation it made would be a rule the suite
    stopped testing.
    """

    def __init__(self, harness: DnapHarness) -> None:
        self.h = harness
        self._id = 0
        self.hello: dict[str, Any] = {}

    # -- wire ------------------------------------------------------------

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def raw(self, method: str, params: Any = None) -> dict:
        """Send one request; return the decoded response envelope."""
        rid = self._next_id()
        req: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            req["params"] = params
        resp = await self.h.endpoint(req)
        if not isinstance(resp, dict):
            raise _violation(
                "§2", f"{method} answered {type(resp).__name__}, not a JSON-RPC "
                f"response object: {resp!r}"
            )
        if resp.get("jsonrpc") != "2.0":
            raise _violation("§2", f"{method} response lacks jsonrpc:'2.0': {resp!r}")
        if resp.get("id") != rid:
            raise _violation(
                "§2", f"{method} response id {resp.get('id')!r} does not echo the "
                f"request id {rid!r} — a client cannot pair it"
            )
        has_result, has_error = "result" in resp, "error" in resp
        if has_result == has_error:
            raise _violation(
                "§2", f"{method} response carries "
                f"{'both result and error' if has_result else 'neither result nor error'}"
                f": {resp!r}"
            )
        return resp

    async def notify(self, method: str, params: Any = None) -> Any:
        req: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            req["params"] = params
        return await self.h.endpoint(req)

    async def batch(self, requests: list[dict]) -> Any:
        return await self.h.endpoint(requests)

    async def result(self, method: str, params: Any = None, *, why: str = "") -> Any:
        resp = await self.raw(method, params)
        if "error" in resp:
            raise _violation(
                "§8", f"{method} was expected to succeed{(' — ' + why) if why else ''}, "
                f"and answered error {resp['error']!r}. params={params!r}"
            )
        return resp["result"]

    async def error(self, method: str, params: Any = None, *, why: str = "") -> dict:
        resp = await self.raw(method, params)
        if "error" not in resp:
            raise _violation(
                "§8", f"{method} was required to fail{(' — ' + why) if why else ''} "
                f"and answered a RESULT instead: {resp['result']!r}. params={params!r}"
            )
        err = resp["error"]
        if not isinstance(err, dict) or "code" not in err:
            raise _violation("§2", f"{method} error member is not a JSON-RPC error: {err!r}")
        return err

    # -- lifecycle -------------------------------------------------------

    async def initialize(self) -> dict:
        self.hello = await self.result(
            "initialize",
            {
                "protocolVersion": DNAP_PROTOCOL_VERSION,
                "client": {"name": "dna-dnap-conformance", "version": "1.0"},
                # Advertise everything: the suite must learn what the SERVER
                # serves, and a client that asked for less would let a server
                # hide behind the client's modesty.
                "capabilities": {"resolve": {}, "search": {}, "watch": {}, "write": {}},
            },
            why="initialize is the first message of every connection (§4)",
        )
        if not isinstance(self.hello, dict):
            raise _violation("§4", f"initialize result is not an object: {self.hello!r}")
        return self.hello

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(self.hello.get("kinds") or ())

    @property
    def channels(self) -> tuple[str, ...]:
        return tuple(self.hello.get("channels") or ())

    @property
    def caps(self) -> dict[str, Any]:
        c = self.hello.get("capabilities")
        return c if isinstance(c, dict) else {}

    def has(self, family: str) -> bool:
        return family in self.caps

    def channel(self) -> str:
        if not self.channels:
            raise _violation(
                "§4/§8.1", "initialize advertised no channels — every request "
                "carries a channel (§3), so this server can serve nothing"
            )
        return self.channels[0]

    def unserved_channel(self) -> str:
        """A channel this server provably does not serve.

        Synthesised rather than asked for, and then checked against the
        advertised list, so the probe cannot accidentally hit a served one.
        """
        candidate = f"dnap-scope:/{_unique('dnap-conformance-unserved')}"
        if candidate in self.channels:  # pragma: no cover — 96 bits of entropy
            raise _violation("§4", "the server claims to serve a random channel name")
        return candidate

    def unserved_kind(self) -> str:
        candidate = _unique("DnapConformanceUnservedKind")
        if candidate in self.kinds:  # pragma: no cover
            raise _violation("§4", "the server claims to serve a random Kind name")
        return candidate

    # -- vocabulary ------------------------------------------------------

    async def kinds_on(self, channel: str) -> list[dict]:
        result = await self.result(
            "kinds/list", {"channel": channel},
            why="kinds/list is how a channel reports the Kinds it serves (§6.1)",
        )
        entries = result.get("kinds") if isinstance(result, dict) else None
        if not isinstance(entries, list):
            raise _violation("§6.1", f"kinds/list result has no 'kinds' list: {result!r}")
        return [e for e in entries if isinstance(e, dict)]

    async def a_kind(self, channel: str, *, writable: bool | None = None) -> dict:
        """One Kind descriptor off this channel, optionally a writable one."""
        entries = await self.kinds_on(channel)
        pool = entries if writable is None else [
            e for e in entries if bool(e.get("writable")) is writable
        ]
        if not pool:
            raise DnapCaseNotApplicable(
                missing=(
                    f"channel {channel} serves no "
                    f"{'writable ' if writable else ''}Kind "
                    f"(kinds/list returned {len(entries)} descriptor(s))"
                ),
                unchecked=(
                    "the obligation this case enforces was not exercised against "
                    "any Kind on this server"
                ),
            )
        return pool[0]


# ---------------------------------------------------------------------------
# fixtures — getting instances to talk about, honestly
# ---------------------------------------------------------------------------

_UNSATISFIABLE = object()


def _sample_for(schema: Any, key: str) -> Any:
    """A value the given JSON Schema fragment should accept, or _UNSATISFIABLE.

    Deliberately conservative: when the schema constrains a string by pattern or
    by a format this function cannot forge, it gives up rather than guessing, so
    a rejected write is a real finding instead of the suite's own sloppiness.
    """
    if not isinstance(schema, dict):
        return _UNSATISFIABLE
    if "const" in schema:
        return schema["const"]
    if schema.get("enum"):
        return schema["enum"][0]
    if "default" in schema:
        return schema["default"]
    for combinator in ("anyOf", "oneOf"):
        for branch in schema.get(combinator) or ():
            candidate = _sample_for(branch, key)
            if candidate is not _UNSATISFIABLE:
                return candidate
    typ = schema.get("type")
    if isinstance(typ, list):
        typ = next((t for t in typ if t != "null"), None)
    if typ in ("integer", "number"):
        return schema.get("minimum", 1)
    if typ == "boolean":
        return False
    if typ == "null":
        return None
    if typ == "array":
        n = int(schema.get("minItems") or 0)
        if n == 0:
            return []
        item = _sample_for(schema.get("items") or {}, key)
        return _UNSATISFIABLE if item is _UNSATISFIABLE else [item] * n
    if typ == "object" or "properties" in schema:
        return _minimal_spec(schema)
    if typ == "string" or typ is None:
        if "pattern" in schema:
            return _UNSATISFIABLE
        fmt = schema.get("format")
        if fmt in ("date-time",):
            return "2026-01-01T00:00:00+00:00"
        if fmt in ("date",):
            return "2026-01-01"
        if fmt is not None and fmt not in ("", "text"):
            return _UNSATISFIABLE
        return f"dnap conformance {key}"
    return _UNSATISFIABLE


def _minimal_spec(schema: Any) -> Any:
    """The smallest object satisfying ``schema``'s ``required``, or _UNSATISFIABLE."""
    if not isinstance(schema, dict):
        return _UNSATISFIABLE
    props = schema.get("properties") or {}
    out: dict[str, Any] = {}
    for key in schema.get("required") or ():
        value = _sample_for(props.get(key, {}), key)
        if value is _UNSATISFIABLE:
            return _UNSATISFIABLE
        out[key] = value
    return out


@dataclass
class _Fixture:
    """Instances the suite may talk about, and how it got them."""

    channel: str
    kind: str
    api_version: str
    names: list[str] = field(default_factory=list)
    seeded: list[str] = field(default_factory=list)


async def _existing(session: _Session, channel: str, kind: str, want: int) -> list[str]:
    result = await session.result(
        "instances/list", {"channel": channel, "kind": kind, "limit": want},
        why="listing a served Kind on a served channel is the positive control",
    )
    out = []
    for inst in (result.get("instances") or []) if isinstance(result, dict) else []:
        name = _name_of(inst)
        if name:
            out.append(name)
    return out


def _name_of(instance: Any) -> str | None:
    if isinstance(instance, str):
        return instance
    if not isinstance(instance, dict):
        return None
    meta = instance.get("metadata")
    if isinstance(meta, dict) and isinstance(meta.get("name"), str):
        return meta["name"]
    return instance.get("name") if isinstance(instance.get("name"), str) else None


async def _fixture(session: _Session, *, count: int, obligation: str) -> _Fixture:
    """``count`` instances of some served Kind, by whatever honest means.

    Order: instances that already exist, then the harness ``seed`` hook, then
    synthesis through the protocol's own ``instances/write``. If none of the
    three can produce them, the case does NOT quietly pass — it raises a skip
    that names every avenue tried and the obligation left unchecked.
    """
    channel = session.channel()
    entries = await session.kinds_on(channel)
    tried: list[str] = []

    for entry in entries:
        kind = entry.get("kind")
        if not isinstance(kind, str):
            continue
        api_version = entry.get("apiVersion") or ""
        have = await _existing(session, channel, kind, count)
        if len(have) >= count:
            return _Fixture(channel=channel, kind=kind, api_version=api_version, names=have)

    if session.h.seed is not None:
        entry = entries[0] if entries else {}
        kind = entry.get("kind")
        if isinstance(kind, str):
            names = list(await session.h.seed(channel=channel, kind=kind, count=count))
            if len(names) >= count:
                return _Fixture(
                    channel=channel, kind=kind,
                    api_version=entry.get("apiVersion") or "",
                    names=names, seeded=names,
                )
            tried.append(f"harness seed() produced {len(names)} of {count}")

    if not session.has("write"):
        tried.append("the server advertises no 'write' capability, so the suite "
                     "cannot create instances of its own")
        raise DnapCaseNotApplicable(
            missing=f"{count} instance(s) to talk about ({'; '.join(tried)})",
            unchecked=obligation,
        )

    for entry in entries:
        kind = entry.get("kind")
        if not isinstance(kind, str) or not entry.get("writable"):
            continue
        api_version = entry.get("apiVersion") or ""
        described = await session.result(
            "kinds/describe", {"channel": channel, "kind": kind},
            why="a client that cannot see the schema writes documents the server rejects (§6.1)",
        )
        schema = described.get("schema") if isinstance(described, dict) else None
        if schema is None and isinstance(described, dict):
            schema = described  # a server MAY return the schema unwrapped
        spec = _minimal_spec(schema)
        if spec is _UNSATISFIABLE:
            tried.append(f"{kind}: its schema constrains a required field in a way "
                         f"this suite will not forge (pattern/format)")
            continue
        created: list[str] = []
        failure: str | None = None
        for i in range(count):
            name = _unique(f"dnap-conformance-{i}")
            resp = await session.raw("instances/write", {
                "channel": channel,
                "instance": {
                    "apiVersion": api_version,
                    "kind": kind,
                    "metadata": {"name": name},
                    "spec": spec,
                },
            })
            if "error" in resp:
                failure = f"{kind}: instances/write refused a minimal instance: {resp['error']!r}"
                break
            created.append(name)
        if failure is None and len(created) >= count:
            return _Fixture(channel=channel, kind=kind, api_version=api_version,
                            names=created, seeded=created)
        if failure:
            tried.append(failure)
        await _cleanup_seeded(session, channel, kind, created)

    raise DnapCaseNotApplicable(
        missing=(
            f"{count} instance(s) to talk about — none existed and none could be "
            f"created ({'; '.join(tried) or 'the channel serves no writable Kind'})"
        ),
        unchecked=obligation,
    )


async def _cleanup_seeded(session: _Session, channel: str, kind: str,
                          names: Iterable[str]) -> None:
    for name in names:
        try:
            await session.raw("instances/delete",
                              {"channel": channel, "kind": kind, "name": name})
        except Exception:  # noqa: BLE001 — cleanup never masks a verdict
            pass


async def _release(session: _Session, fixture: _Fixture | None) -> None:
    if fixture and fixture.seeded:
        await _cleanup_seeded(session, fixture.channel, fixture.kind, fixture.seeded)


# ---------------------------------------------------------------------------
# the positive control — the guard on every negative probe
# ---------------------------------------------------------------------------

async def _positive_control(session: _Session) -> str:
    """Assert a VALID list succeeds, and return the Kind it used.

    ⭐ Without this, every "must be an error" case in this suite passes against
    a server that errors on everything — which is the tautology that makes a
    negative-only conformance suite worthless. Each negative probe calls this
    first, so a blanket-failing server fails HERE, by name, instead of scoring
    a clean sweep.
    """
    channel = session.channel()
    entries = await session.kinds_on(channel)
    kinds = [e["kind"] for e in entries if isinstance(e.get("kind"), str)]
    if not kinds:
        raise _violation(
            "§6.1", f"kinds/list on the advertised channel {channel} named no Kind — "
            "there is nothing this server can be asked about, so no refusal it "
            "gives can be distinguished from refusing everything"
        )
    kind = kinds[0]
    result = await session.result(
        "instances/list", {"channel": channel, "kind": kind},
        why=(
            "POSITIVE CONTROL: a valid listing on a served channel and a served "
            "Kind must succeed, or every negative probe in this suite is a "
            "tautology"
        ),
    )
    if not isinstance(result, dict) or not isinstance(result.get("instances"), list):
        raise _violation(
            "§6.2", f"instances/list result has no 'instances' list: {result!r}"
        )
    return kind


def _is_empty_collection(result: Any) -> bool:
    """Did the server answer 'nothing exists' — the shape §7 forbids for a failure?"""
    if not isinstance(result, dict):
        return False
    for member in ("instances", "hits", "kinds"):
        if isinstance(result.get(member), list) and not result[member]:
            return True
    return False


async def _must_refuse(session: _Session, method: str, params: Any, *,
                       expect: int, section: str, rule: str,
                       also_accept: Sequence[int] = ()) -> dict:
    """The refusal probe, with its positive control and its empty-collection arm.

    Three separate verdicts, phrased separately on purpose:
      * a RESULT where an error was required — and if that result is an empty
        collection, said so explicitly, because that is §7's central rule;
      * an error with the wrong code;
      * (by the caller's positive control) a server that simply refuses all.
    """
    await _positive_control(session)
    resp = await session.raw(method, params)
    if "error" not in resp:
        result = resp["result"]
        if _is_empty_collection(result):
            raise _violation(
                "§7", f"{rule}: {method} answered an EMPTY COLLECTION where it had "
                f"to answer {expect}. An empty result is the claim 'nothing of this "
                f"kind exists here'; a refusal is not that claim, and collapsing "
                f"the two is the one rule this protocol puts above its error "
                f"table. result={result!r} params={params!r}"
            )
        raise _violation(
            section, f"{rule}: {method} answered a result where {expect} was "
            f"required. result={result!r} params={params!r}"
        )
    code = resp["error"].get("code")
    allowed = (expect, *also_accept)
    if code not in allowed:
        wanted = expect if not also_accept else f"one of {list(allowed)}"
        raise _violation(
            section, f"{rule}: {method} answered code {code!r} "
            f"({resp['error'].get('message')!r}) where {wanted} was required. "
            f"params={params!r}"
        )
    return resp["error"]


# ---------------------------------------------------------------------------
# §2 — framing
# ---------------------------------------------------------------------------

async def _case_envelope_is_jsonrpc_2(s: _Session) -> None:
    """§2 — requests, responses and notifications follow JSON-RPC 2.0 exactly.

    Asserted inside :meth:`_Session.raw` for every call the suite makes; this
    case exists so the report names the framing when it is what broke.
    """
    await s.raw("kinds/list", {"channel": s.channel()})


async def _case_notification_gets_no_response(s: _Session) -> None:
    """§2 — a request without ``id`` is a notification and MUST NOT be answered."""
    resp = await s.notify("kinds/list", {"channel": s.channel()})
    if resp not in (None, "", b""):
        raise _violation(
            "§2", f"a notification (no id) was answered with {resp!r}. JSON-RPC 2.0 "
            f"forbids a response to a notification, and a client that pairs "
            f"responses by id has nowhere to put this one"
        )


async def _case_batch_is_supported(s: _Session) -> None:
    """§2 — "Batch requests MUST be supported by servers"."""
    channel = s.channel()
    ids = [s._next_id(), s._next_id()]
    batch = [
        {"jsonrpc": "2.0", "id": ids[0], "method": "kinds/list", "params": {"channel": channel}},
        {"jsonrpc": "2.0", "id": ids[1], "method": "kinds/list", "params": {"channel": channel}},
    ]
    resp = await s.batch(batch)
    if not isinstance(resp, list):
        raise _violation(
            "§2", f"a batch of 2 requests answered {type(resp).__name__} "
            f"({resp!r}); §2 makes batch support a server MUST"
        )
    got = sorted(r.get("id") for r in resp if isinstance(r, dict))
    if got != sorted(ids):
        raise _violation(
            "§2", f"batch response ids {got} do not match the request ids "
            f"{sorted(ids)} — a client cannot pair them"
        )


async def _case_unknown_method_is_method_not_found(s: _Session) -> None:
    """§8.2 — an unadvertised method is rejected with ``-32601``.

    The unconditional arm: a method no version of this protocol defines. The
    capability-derived arm is the next case.
    """
    await _must_refuse(
        s, f"dnap/{_unique('no-such-method')}", {"channel": s.channel()},
        expect=METHOD_NOT_FOUND, section="§8.2",
        rule="an unknown method is -32601, never a degraded answer",
    )


#: family → a method that family owns. The suite asks the SERVER which families
#: it has and probes only the ones it declined; it never asserts how many
#: families or methods the protocol has, so a growing spec does not break it.
_CAPABILITY_METHODS = {
    "resolve": ("resolve/agent", {"name": "anything"}),
    "search": ("search/instances", {"query": "anything", "k": 1}),
    "write": ("instances/write", {"instance": {}}),
}


async def _case_method_outside_capability_is_method_not_found(s: _Session) -> None:
    """§4/§8.2 — following AHP's rule, a method outside every advertised
    capability MUST be ``-32601``: not silently ignored, and not answered with a
    degraded result."""
    declined = [f for f in _CAPABILITY_METHODS if not s.has(f)]
    if not declined:
        raise DnapCaseNotApplicable(
            missing="the server advertises every capability family this suite "
                    "knows how to probe, so none is 'outside' its capabilities",
            unchecked="that a method outside an UNADVERTISED family answers -32601 "
                      "(the unknown-method arm of the same rule is covered by "
                      "unknown_method_is_method_not_found)",
        )
    for family in declined:
        method, extra = _CAPABILITY_METHODS[family]
        await _must_refuse(
            s, method, {"channel": s.channel(), **extra},
            expect=METHOD_NOT_FOUND, section="§4",
            rule=f"'{family}' is not in the advertised capabilities, so {method} "
                 f"is outside them",
        )


# ---------------------------------------------------------------------------
# §4 / §8.1 — the connection advertises what it serves
# ---------------------------------------------------------------------------

async def _case_initialize_advertises_the_connection(s: _Session) -> None:
    """§8.1 — answer ``initialize`` and advertise ``kinds`` and ``capabilities``.

    Asserts the QUESTION and not the ANSWER: presence, type and non-emptiness.
    Nothing here counts methods, Kinds or capabilities, so a server that grows
    a vocabulary does not fail for growing one.
    """
    hello = s.hello
    for member, typ in (("protocolVersion", str), ("server", dict),
                        ("channels", list), ("capabilities", dict), ("kinds", list)):
        if member not in hello:
            raise _violation(
                "§4/§8.1", f"initialize did not advertise '{member}'. A client "
                f"learns what it may say from this message and nowhere else."
            )
        if not isinstance(hello[member], typ):
            raise _violation(
                "§4", f"initialize.{member} is {type(hello[member]).__name__}, "
                f"expected {typ.__name__}: {hello[member]!r}"
            )
    if not hello["channels"]:
        raise _violation("§4", "initialize advertised an empty 'channels' — every "
                               "request carries a channel (§3), so nothing is reachable")
    if not hello["kinds"]:
        raise _violation(
            "§4", "initialize advertised an empty 'kinds'. A conforming client "
            "names no Kind of its own (§8, client rule 1), so an empty vocabulary "
            "leaves it unable to ask a single question."
        )


async def _case_advertised_kinds_are_a_vocabulary(s: _Session) -> None:
    """§4 — the ``kinds`` list is a vocabulary: non-empty unique strings."""
    kinds = s.hello.get("kinds") or []
    bad = [k for k in kinds if not isinstance(k, str) or not k.strip()]
    if bad:
        raise _violation("§4", f"initialize.kinds contains non-name entries: {bad!r}")
    dupes = sorted({k for k in kinds if kinds.count(k) > 1})
    if dupes:
        raise _violation("§4", f"initialize.kinds repeats {dupes!r} — a vocabulary "
                               f"is a set, and a client deduping it is a client "
                               f"guessing")


async def _case_channel_vocabulary_never_exceeds_the_advertised_one(s: _Session) -> None:
    """§4/§6.1 — ``kinds/list`` may narrow the advertised vocabulary, never widen it.

    ⭐ This is the load-bearing half of client rule 1. The client takes its
    vocabulary from ``initialize``; a Kind that a channel serves but
    ``initialize`` never named is a Kind no conforming client can ever ask for,
    which makes it unreachable by construction.
    """
    advertised = set(s.kinds)
    for channel in s.channels:
        entries = await s.kinds_on(channel)
        served = {e["kind"] for e in entries if isinstance(e.get("kind"), str)}
        extra = sorted(served - advertised)
        if extra:
            raise _violation(
                "§4", f"channel {channel} serves {extra!r}, which initialize never "
                f"advertised. A conforming client names no Kind of its own, so it "
                f"can never ask for these — they are served and unreachable."
            )


async def _case_kinds_describe_carries_a_schema(s: _Session) -> None:
    """§6.1 — ``kinds/describe`` returns the JSON Schema of ``spec``.

    "The schema travels because a client that cannot see it must guess, and a
    guessing client writes documents the server will reject."
    """
    channel = s.channel()
    entry = await s.a_kind(channel)
    result = await s.result(
        "kinds/describe", {"channel": channel, "kind": entry["kind"]},
        why="a client with no schema guesses",
    )
    schema = result.get("schema") if isinstance(result, dict) else None
    if schema is None and isinstance(result, dict):
        schema = result
    if not isinstance(schema, dict) or not schema:
        raise _violation(
            "§6.1", f"kinds/describe for {entry['kind']!r} carried no schema: {result!r}"
        )
    # A schema shape, not a particular schema — the question, not the answer.
    if not ({"type", "properties", "$ref", "anyOf", "oneOf", "allOf", "$schema"}
            & set(schema)):
        raise _violation(
            "§6.1", f"kinds/describe for {entry['kind']!r} returned an object with no "
            f"JSON Schema keyword in it: {sorted(schema)!r}"
        )


async def _case_unadvertised_kind_is_kind_not_served(s: _Session) -> None:
    """§8.2 — a Kind outside the advertised vocabulary is ``-32003``."""
    await _must_refuse(
        s, "instances/list", {"channel": s.channel(), "kind": s.unserved_kind()},
        expect=KIND_NOT_SERVED, section="§8.2",
        rule="a Kind the server never advertised is -32003 KIND_NOT_SERVED",
    )


async def _case_unadvertised_kind_is_not_an_empty_collection(s: _Session) -> None:
    """§7 — ...and specifically NOT ``{"instances": []}``.

    Named as its own case so the report distinguishes 'wrong code' from 'the
    failure was collapsed into an empty collection'. They are different bugs
    with different consequences: the first is a client that retries wrongly,
    the second is a client that believes an emptiness that was never observed.
    """
    await _positive_control(s)
    resp = await s.raw("instances/list",
                       {"channel": s.channel(), "kind": s.unserved_kind()})
    if "error" not in resp and _is_empty_collection(resp["result"]):
        raise _violation(
            "§7", "instances/list for an unadvertised Kind answered "
            f"{resp['result']!r}. '[] of Kind X' asserts that no X exists here; "
            f"the server does not serve X at all, so the assertion is a fiction "
            f"the caller cannot detect."
        )


# ---------------------------------------------------------------------------
# §3 — scope is an ADDRESS, and an address cannot be silently ignored
# ---------------------------------------------------------------------------

async def _case_unserved_channel_is_channel_not_served(s: _Session) -> None:
    """§3/§8 — a channel this server does not serve is ``-32004``."""
    await _must_refuse(
        s, "instances/list",
        {"channel": s.unserved_channel(), "kind": (await _positive_control(s))},
        expect=CHANNEL_NOT_SERVED, section="§3",
        rule="an unserved channel is -32004 CHANNEL_NOT_SERVED",
    )


async def _case_unserved_channel_is_never_substituted(s: _Session) -> None:
    """⛔ §3 — a server MUST NOT substitute a channel it does serve.

    The measured defect this rule exists for: DNA's REST face accepted
    ``?scope=`` and silently ignored it, returning one scope's content under
    another scope's name. The probe takes a baseline from a channel the server
    DOES serve, then asks the same question of a channel it does not, and reads
    the answer three ways:

      * an error with the right code — conformant;
      * a result that EQUALS the baseline — substitution, named as such;
      * any other result — still a fabrication, because the server has just
        answered about an address it does not hold.
    """
    served = s.channel()
    kind = await _positive_control(s)
    baseline = await s.result("instances/list", {"channel": served, "kind": kind})
    resp = await s.raw("instances/list",
                       {"channel": s.unserved_channel(), "kind": kind})
    if "error" in resp:
        if resp["error"].get("code") != CHANNEL_NOT_SERVED:
            raise _violation(
                "§3", f"an unserved channel answered code "
                f"{resp['error'].get('code')!r}, not -32004"
            )
        return
    got = resp["result"]
    if isinstance(got, dict) and isinstance(baseline, dict) and \
            got.get("instances") == baseline.get("instances"):
        raise _violation(
            "§3", "SUBSTITUTION: a channel the server does not serve returned "
            "byte-identical content to the channel it does. Scope is an address, "
            "not a parameter — an address cannot be silently ignored, and a caller "
            "reading this answer believes it is holding another tenant's shelf."
        )
    raise _violation(
        "§3", f"an unserved channel answered a result instead of -32004: {got!r}"
    )


async def _case_unserved_tenant_overlay_is_not_the_base(s: _Session) -> None:
    """§3 — ``dnap-scope:/<scope>#<tenant>`` is a DIFFERENT address.

    The tenant form of the same defect, and the more dangerous one: falling back
    to the base scope when a tenant overlay is not served hands a caller the
    shared shelf while it believes it is holding its own.
    """
    served = s.channel()
    if "#" in served:
        raise DnapCaseNotApplicable(
            missing=f"the advertised channel {served} is already a tenant overlay, "
                    f"so the suite has no base channel to append a tenant to",
            unchecked="that an unserved tenant overlay answers -32004 rather than "
                      "falling back to its base scope",
        )
    kind = await _positive_control(s)
    overlay = f"{served}#{_unique('unserved-tenant')}"
    if overlay in s.channels:  # pragma: no cover
        raise _violation("§3", "the server claims to serve a random tenant overlay")
    baseline = await s.result("instances/list", {"channel": served, "kind": kind})
    resp = await s.raw("instances/list", {"channel": overlay, "kind": kind})
    if "error" in resp:
        if resp["error"].get("code") != CHANNEL_NOT_SERVED:
            raise _violation(
                "§3", f"an unserved tenant overlay answered code "
                f"{resp['error'].get('code')!r}, not -32004"
            )
        return
    got = resp["result"]
    if isinstance(got, dict) and isinstance(baseline, dict) and \
            got.get("instances") == baseline.get("instances"):
        raise _violation(
            "§3", f"SUBSTITUTION: the unserved tenant overlay {overlay} returned the "
            f"BASE scope's content. The caller asked for a tenant's shelf and was "
            f"handed the shared one, with nothing in the answer to say so."
        )
    raise _violation(
        "§3", f"the unserved tenant overlay {overlay} answered a result instead of "
        f"-32004: {got!r}"
    )


# ---------------------------------------------------------------------------
# §6.2 rule 1 / §8.3 — select is a CONTRACT, not a hint
# ---------------------------------------------------------------------------

def _instances_of(result: Any) -> list:
    return result.get("instances") or [] if isinstance(result, dict) else []


async def _select_or_refusal(s: _Session, fixture: _Fixture, select: Any) -> Any | None:
    """Ask for a projection; ``None`` means the server rejected it, which §8.3
    explicitly permits."""
    resp = await s.raw("instances/list", {
        "channel": fixture.channel, "kind": fixture.kind, "select": select,
    })
    if "error" in resp:
        if resp["error"].get("code") != INVALID_PARAMS:
            raise _violation(
                "§6.2/§8.3", f"select={select!r} was refused with code "
                f"{resp['error'].get('code')!r}. A server that cannot honour a "
                f"projection MUST answer -32602; any other code tells the client "
                f"the wrong thing to do next."
            )
        return None
    return resp["result"]


async def _case_select_names_is_honoured_or_rejected(s: _Session) -> None:
    """§8.3 — honour ``select`` exactly, or reject it."""
    fixture = await _fixture(s, count=1, obligation=(
        "that select:'names' is either honoured exactly or refused with -32602"))
    try:
        result = await _select_or_refusal(s, fixture, "names")
        if result is None:
            return
        if result.get("selected") not in (None, "names"):
            raise _violation(
                "§6.2", f"select:'names' was answered with selected="
                f"{result.get('selected')!r} — the echo must describe what was "
                f"actually returned"
            )
        for inst in _instances_of(result):
            if isinstance(inst, dict) and "spec" in inst:
                raise _violation(
                    "§6.2", f"select:'names' returned an instance carrying 'spec': "
                    f"{sorted(inst)!r}. Honouring a projection EXACTLY cuts both "
                    f"ways — a wider shape than asked for is as much a broken "
                    f"contract as a narrower one, and it is the one that costs "
                    f"bandwidth silently."
                )
    finally:
        await _release(s, fixture)


async def _case_select_full_never_echoes_a_narrower_shape(s: _Session) -> None:
    """⛔ §6.2 rule 1 — the measured defect, stated exactly.

    *"Measured: ``?fields=spec`` returned ``[{"name": …}]`` and echoed
    ``"projected":["spec"]``."* A server may refuse a projection. What it may
    not do is claim to have honoured one while returning something narrower —
    because the echo is the only thing the client can check, and a lying echo
    turns an unreadable answer into an unquestionable one.
    """
    fixture = await _fixture(s, count=1, obligation=(
        "that a server never echoes select:'full' while returning a narrower shape"))
    try:
        result = await _select_or_refusal(s, fixture, "full")
        if result is None:
            return
        instances = _instances_of(result)
        if not instances:
            raise _violation(
                "§6.2", f"select:'full' returned no instances although "
                f"{len(fixture.names)} exist under kind {fixture.kind!r} "
                f"({fixture.names!r})"
            )
        selected = result.get("selected")
        if selected not in (None, "full"):
            raise _violation(
                "§6.2", f"select:'full' was answered with selected={selected!r}"
            )
        for inst in instances:
            if not isinstance(inst, dict):
                raise _violation(
                    "§6.2", f"select:'full' returned {inst!r} — a full projection is "
                    f"the document (§5), not a name"
                )
            missing = [m for m in ("kind", "metadata", "spec") if m not in inst]
            if missing:
                raise _violation(
                    "§6.2", f"select:'full' echoed selected={selected!r} while "
                    f"returning instances missing {missing!r} (keys: {sorted(inst)!r}). "
                    f"This is the measured defect verbatim: a narrower shape "
                    f"delivered under the requested name."
                )
    finally:
        await _release(s, fixture)


async def _case_select_field_paths_is_honoured_or_rejected(s: _Session) -> None:
    """§6.2 rule 1 — the field-list form, with a path every document has.

    ``metadata.name`` is used precisely because it is Kind-agnostic: the suite
    must not need to know a Kind's fields to test that projections are honoured.
    """
    fixture = await _fixture(s, count=1, obligation=(
        "that a field-path projection is honoured exactly or refused with -32602"))
    try:
        result = await _select_or_refusal(s, fixture, ["metadata.name"])
        if result is None:
            return
        for inst in _instances_of(result):
            if isinstance(inst, dict) and "spec" in inst:
                raise _violation(
                    "§6.2", f"select:['metadata.name'] returned an instance carrying "
                    f"'spec' ({sorted(inst)!r}) — the projection was not honoured, "
                    f"and it was not refused either"
                )
    finally:
        await _release(s, fixture)


async def _case_unhonourable_select_is_invalid_params(s: _Session) -> None:
    """§6.2 rule 1 — a projection outside the defined union cannot be honoured,
    so it MUST be ``-32602`` rather than quietly reinterpreted."""
    fixture = await _fixture(s, count=1, obligation=(
        "that a malformed 'select' is refused with -32602 rather than reinterpreted"))
    try:
        await _must_refuse(
            s, "instances/list",
            {"channel": fixture.channel, "kind": fixture.kind,
             "select": _unique("not-a-projection")},
            expect=INVALID_PARAMS, section="§6.2",
            rule="select is 'names' | 'full' | [paths]; anything else cannot be "
                 "honoured and so must be refused",
        )
    finally:
        await _release(s, fixture)


# ---------------------------------------------------------------------------
# §6.2 rules 2 & 3 / §8.4 — pagination
# ---------------------------------------------------------------------------

async def _case_list_carries_an_opaque_revision(s: _Session) -> None:
    """§6.2 rule 3 — a listing names the snapshot it belongs to."""
    fixture = await _fixture(s, count=1, obligation=(
        "that instances/list reports the revision its results belong to"))
    try:
        result = await s.result(
            "instances/list", {"channel": fixture.channel, "kind": fixture.kind})
        if "revision" not in result:
            raise _violation(
                "§6.2", "instances/list carried no 'revision'. Without it a client "
                "cannot say which moment its picture is of, and watch (§6.5) has "
                "nothing to follow from."
            )
        if not isinstance(result["revision"], str):
            raise _violation(
                "§6.2", f"revision is {type(result['revision']).__name__} "
                f"({result['revision']!r}). Clients MUST treat it as opaque (§8, "
                f"client rule 2), which a non-string invites them not to."
            )
    finally:
        await _release(s, fixture)


async def _case_revision_is_constant_across_pages(s: _Session) -> None:
    """⭐ §6.2 rule 3 / §8.4 — all pages of one listing belong to one snapshot.

    *"Without this a client assembles a quilt of moments and calls it a state."*
    Needs two pages, so it needs two instances; a server that cannot be made to
    hold two says so in the skip rather than passing on one page.
    """
    fixture = await _fixture(s, count=3, obligation=(
        "that 'revision' is constant across the pages of one paginated listing — "
        "the rule that keeps a client from assembling a quilt of moments"))
    try:
        revisions: list[Any] = []
        pages = 0
        cursor = None
        while pages < 12:
            params: dict[str, Any] = {
                "channel": fixture.channel, "kind": fixture.kind, "limit": 1,
            }
            if cursor is not None:
                params["cursor"] = cursor
            result = await s.result("instances/list", params)
            pages += 1
            revisions.append(result.get("revision"))
            cursor = result.get("cursor")
            if not cursor:
                break
        if pages < 2:
            raise DnapCaseNotApplicable(
                missing=f"the server returned everything in one page for limit=1 "
                        f"with {len(fixture.names)} instance(s) present, so no "
                        f"second page exists to compare a revision against",
                unchecked="that 'revision' stays constant across the pages of one "
                          "listing",
            )
        if len(set(map(repr, revisions))) != 1:
            raise _violation(
                "§6.2/§8.4", f"revision changed across the pages of ONE listing: "
                f"{revisions!r}. Each page then belongs to a different moment, and "
                f"the client that concatenates them holds a state that never existed."
            )
    finally:
        await _release(s, fixture)


async def _case_pages_neither_duplicate_nor_drop(s: _Session) -> None:
    """§6.2 rules 2 & 3 — what a stable revision is FOR.

    A constant ``revision`` with a cursor that skips rows is a constant lie, so
    the snapshot claim is checked against its consequence: walking the cursor
    must yield exactly the set a single unpaginated read yields.
    """
    fixture = await _fixture(s, count=3, obligation=(
        "that walking the cursor yields every instance exactly once"))
    try:
        whole = await s.result(
            "instances/list", {"channel": fixture.channel, "kind": fixture.kind,
                               "limit": 1000})
        expected = [n for n in (_name_of(i) for i in _instances_of(whole)) if n]
        walked: list[str] = []
        cursor = None
        for _ in range(200):
            params: dict[str, Any] = {
                "channel": fixture.channel, "kind": fixture.kind, "limit": 1,
            }
            if cursor is not None:
                params["cursor"] = cursor
            result = await s.result("instances/list", params)
            walked += [n for n in (_name_of(i) for i in _instances_of(result)) if n]
            cursor = result.get("cursor")
            if not cursor:
                break
        else:
            raise _violation(
                "§6.2", "the cursor never reported exhaustion in 200 pages — "
                "'cursor absent when exhausted' has no terminating case here"
            )
        dupes = sorted({n for n in walked if walked.count(n) > 1})
        if dupes:
            raise _violation("§6.2", f"the paginated walk returned {dupes!r} more "
                                     f"than once")
        missed = sorted(set(expected) - set(walked))
        if missed:
            raise _violation(
                "§6.2", f"the paginated walk silently skipped {missed!r}. This is "
                f"the failure a cursor exists to prevent, and it is invisible to "
                f"the client — every page looked healthy."
            )
    finally:
        await _release(s, fixture)


async def _case_expired_cursor_is_cursor_expired(s: _Session) -> None:
    """§6.2 rule 2 / §8 — an expired cursor MUST be ``-32005``, so the client
    restarts rather than silently skipping.

    With ``expire_cursors`` the suite expires a cursor the server really minted.
    Without it, the probe falls back to a cursor the server never minted —
    weaker, and reported as such, because the spec does not say what a
    *malformed* cursor gets (see the module docstring's spec-gap note).
    """
    fixture = await _fixture(s, count=3, obligation=(
        "that an expired cursor answers -32005 CURSOR_EXPIRED"))
    try:
        first = await s.result(
            "instances/list",
            {"channel": fixture.channel, "kind": fixture.kind, "limit": 1})
        cursor = first.get("cursor")
        if s.h.expire_cursors is not None and cursor:
            await s.h.expire_cursors()
            await _must_refuse(
                s, "instances/list",
                {"channel": fixture.channel, "kind": fixture.kind,
                 "limit": 1, "cursor": cursor},
                expect=CURSOR_EXPIRED, section="§6.2",
                rule="a cursor the server has expired is -32005, so the client "
                     "restarts instead of assuming exhaustion",
            )
            return
        raise DnapRuleUnverified(
            rule="that a genuinely EXPIRED cursor answers -32005 (a foreign cursor "
                 "is probed separately, but expiry is a lifecycle this suite cannot "
                 "reach from outside)",
            needs="expire_cursors",
        )
    finally:
        await _release(s, fixture)


async def _case_foreign_cursor_is_an_error_not_exhaustion(s: _Session) -> None:
    """⭐ §6.2 rule 2 + §7 — a cursor the server never minted is not "the end".

    The dangerous shape is not the wrong error code; it is
    ``{"instances": [], "cursor": absent}``, which reads to every client as a
    clean, complete, empty listing. The failure and the finding become the same
    value, which is exactly what §7 forbids.
    """
    fixture = await _fixture(s, count=1, obligation=(
        "that an uninterpretable cursor is an error and not an empty final page"))
    try:
        await _positive_control(s)
        params = {"channel": fixture.channel, "kind": fixture.kind,
                  "limit": 1, "cursor": _unique("not-a-cursor-this-server-minted")}
        resp = await s.raw("instances/list", params)
        if "error" in resp:
            code = resp["error"].get("code")
            if code not in (CURSOR_EXPIRED, INVALID_PARAMS):
                raise _violation(
                    "§6.2", f"a foreign cursor answered code {code!r}; the spec "
                    f"defines -32005 for a cursor the server will not honour and "
                    f"-32602 for a malformed parameter, and a client keys its "
                    f"restart on those"
                )
            return
        result = resp["result"]
        if _is_empty_collection(result) and not result.get("cursor"):
            raise _violation(
                "§7", "a cursor this server never minted was answered with an empty, "
                "cursor-less page — which is the wire shape of 'the listing is "
                "complete and contains nothing'. The client cannot tell that it "
                "just lost the whole collection."
            )
        raise _violation(
            "§6.2", f"a foreign cursor was answered with a result instead of an "
            f"error: {result!r}"
        )
    finally:
        await _release(s, fixture)


# ---------------------------------------------------------------------------
# §5 / §6.2 — write, concurrency, validation
# ---------------------------------------------------------------------------

def _requires_write(s: _Session, unchecked: str) -> None:
    if not s.has("write"):
        raise DnapCaseNotApplicable(
            missing="the server does not advertise the 'write' capability",
            unchecked=unchecked,
        )


async def _case_write_then_get_round_trips(s: _Session) -> None:
    """§6.2 — ``instances/get`` returns the document verbatim, incl. ``revision``."""
    _requires_write(s, "that a written instance reads back with its revision")
    fixture = await _fixture(s, count=1, obligation=(
        "that a written instance reads back verbatim with metadata.revision"))
    try:
        got = await s.result("instances/get", {
            "channel": fixture.channel, "kind": fixture.kind,
            "name": fixture.names[0],
        })
        doc = got.get("instance", got) if isinstance(got, dict) else got
        meta = doc.get("metadata") if isinstance(doc, dict) else None
        if not isinstance(meta, dict):
            raise _violation("§5", f"instances/get returned no metadata: {got!r}")
        if meta.get("name") != fixture.names[0]:
            raise _violation(
                "§5", f"instances/get for {fixture.names[0]!r} returned "
                f"metadata.name={meta.get('name')!r}")
        if not meta.get("revision"):
            raise _violation(
                "§6.2", "instances/get returned no metadata.revision. §6.2 says the "
                "document comes back 'including metadata.revision', and without it "
                "a client has nothing to put in ifMatch."
            )
    finally:
        await _release(s, fixture)


async def _case_stale_ifmatch_is_revision_conflict(s: _Session) -> None:
    """⭐ §6.2/§8 — optimistic concurrency: a stale ``ifMatch`` is ``-32011``.

    The write that must be refused is a write whose author believed a revision
    that has since moved. So the suite MOVES it first, with a second write, and
    then presents the stale one — which is the only sequence in which a passing
    result means anything.
    """
    _requires_write(s, "that a stale ifMatch is refused with -32011 REVISION_CONFLICT")
    fixture = await _fixture(s, count=1, obligation=(
        "that a write against a revision that has moved is refused with -32011"))
    try:
        name = fixture.names[0]
        got = await s.result("instances/get", {
            "channel": fixture.channel, "kind": fixture.kind, "name": name})
        doc = got.get("instance", got) if isinstance(got, dict) else got
        stale = (doc.get("metadata") or {}).get("revision")
        if not stale:
            raise DnapCaseNotApplicable(
                missing="instances/get returned no metadata.revision to go stale",
                unchecked="that a stale ifMatch is refused with -32011",
            )
        body = {k: v for k, v in doc.items() if k != "metadata"}
        body["metadata"] = {"name": name}
        # Move the stored revision out from under `stale`.
        resp = await s.raw("instances/write", {
            "channel": fixture.channel, "instance": body, "ifMatch": stale})
        if "error" in resp:
            raise DnapCaseNotApplicable(
                missing=f"a CURRENT ifMatch was itself refused ({resp['error']!r}), "
                        f"so the suite cannot make a revision go stale",
                unchecked="that a stale ifMatch is refused with -32011",
            )
        err = await _must_refuse(
            s, "instances/write",
            {"channel": fixture.channel, "instance": body, "ifMatch": stale},
            expect=REVISION_CONFLICT, section="§6.2",
            rule="the stored revision moved, so the write is based on a document "
                 "its author never saw",
        )
        data = err.get("data")
        if not (isinstance(data, dict) and data.get("revision")):
            raise _violation(
                "§7", f"-32011 carried no current 'revision' in error.data "
                f"({data!r}). §7's table says REVISION_CONFLICT travels 'with the "
                f"current revision' — without it the client's only recovery is a "
                f"re-read it was not told to make."
            )
    finally:
        await _release(s, fixture)


async def _case_validation_failure_names_path_and_rule(s: _Session) -> None:
    """§6.2 — ``-32010`` "carries the failing path and the rule, never a bare
    'invalid'".

    The violation is synthesised from the Kind's OWN schema so the case stays
    Kind-agnostic: a required property is given a value of the wrong type.
    """
    _requires_write(s, "that -32010 names the failing path and the rule it broke")
    channel = s.channel()
    entry = await s.a_kind(channel, writable=True)
    kind = entry["kind"]
    described = await s.result("kinds/describe", {"channel": channel, "kind": kind})
    schema = described.get("schema", described) if isinstance(described, dict) else {}
    props = (schema or {}).get("properties") or {}
    target = None
    for key in (schema or {}).get("required") or ():
        sub = props.get(key) or {}
        typ = sub.get("type")
        if typ == "string" and "enum" not in sub and "const" not in sub:
            target = key
            break
    if target is None:
        raise DnapCaseNotApplicable(
            missing=f"the schema of {kind!r} has no plain required string field the "
                    f"suite can violate by type without guessing at semantics",
            unchecked="that -32010 VALIDATION_FAILED carries the failing path and rule",
        )
    spec = _minimal_spec(schema)
    if spec is _UNSATISFIABLE:
        raise DnapCaseNotApplicable(
            missing=f"the suite cannot build an otherwise-valid instance of {kind!r} "
                    f"to introduce a single violation into",
            unchecked="that -32010 VALIDATION_FAILED carries the failing path and rule",
        )
    spec[target] = 12345  # a number where the schema requires a string
    err = await _must_refuse(
        s, "instances/write",
        {"channel": channel, "instance": {
            "apiVersion": entry.get("apiVersion") or "",
            "kind": kind,
            "metadata": {"name": _unique("dnap-conformance-invalid")},
            "spec": spec,
        }},
        expect=VALIDATION_FAILED, section="§6.2",
        rule=f"spec.{target} is a number where the Kind's schema requires a string",
    )
    data = err.get("data") if isinstance(err.get("data"), dict) else {}
    blob = repr(err).lower()
    if not (data.get("path") or "path" in blob):
        raise _violation(
            "§6.2", f"-32010 named no failing path: {err!r}. 'Never a bare invalid' "
            f"is the whole point — a client told only that something is wrong "
            f"cannot fix it, and a human reading the log cannot either."
        )
    if not (data.get("rule") or "rule" in blob):
        raise _violation(
            "§6.2", f"-32010 named no broken rule: {err!r}"
        )


async def _case_derived_metadata_on_write_is_refused(s: _Session) -> None:
    """§5 — ``metadata.id`` and ``metadata.revision`` "MUST NOT be supplied on write".

    ⚠️ The spec states the prohibition and names no error code for breaking it,
    so the case asserts only what the spec determines: the write must not be
    silently accepted. The missing code is reported as a spec gap by
    ``spec_gaps`` rather than invented here.
    """
    _requires_write(s, "that supplying derived metadata on write is refused")
    channel = s.channel()
    entry = await s.a_kind(channel, writable=True)
    described = await s.result(
        "kinds/describe", {"channel": channel, "kind": entry["kind"]})
    schema = described.get("schema", described) if isinstance(described, dict) else {}
    spec = _minimal_spec(schema)
    if spec is _UNSATISFIABLE:
        raise DnapCaseNotApplicable(
            missing=f"the suite cannot build an otherwise-VALID instance of "
                    f"{entry['kind']!r}, and an invalid one would be refused for "
                    f"the wrong reason",
            unchecked="that a write supplying metadata.id / metadata.revision is "
                      "refused (§5)",
        )
    name = _unique("dnap-conformance-derived")
    resp = await s.raw("instances/write", {
        "channel": channel,
        "instance": {
            "apiVersion": entry.get("apiVersion") or "",
            "kind": entry["kind"],
            # Valid in every other respect, so a refusal can only be about these
            # two members and an acceptance can only be about them either.
            "metadata": {"name": name, "id": "01JCONFORMANCE0000000000",
                         "revision": "999999"},
            "spec": spec,
        },
    })
    if "error" not in resp:
        await _cleanup_seeded(s, channel, entry["kind"], [name])
        raise _violation(
            "§5", "a write supplying metadata.id and metadata.revision was "
            "ACCEPTED, and the instance was otherwise valid — so nothing else "
            "could have carried the refusal. Those members are derived and "
            "server-minted; letting a client author them means a client can mint "
            "an identity or forge a snapshot, and nothing downstream can tell."
        )


async def _case_conditional_read_is_not_modified(s: _Session) -> None:
    """§6.2 — ``ifNoneMatch`` with the current revision → ``{"notModified": true}``
    and no body."""
    fixture = await _fixture(s, count=1, obligation=(
        "that a conditional read at the current revision answers notModified "
        "with no body"))
    try:
        name = fixture.names[0]
        got = await s.result("instances/get", {
            "channel": fixture.channel, "kind": fixture.kind, "name": name})
        doc = got.get("instance", got) if isinstance(got, dict) else got
        revision = (doc.get("metadata") or {}).get("revision")
        if not revision:
            raise DnapCaseNotApplicable(
                missing="instances/get returned no metadata.revision to condition on",
                unchecked="that ifNoneMatch at the current revision answers notModified",
            )
        resp = await s.raw("instances/get", {
            "channel": fixture.channel, "kind": fixture.kind, "name": name,
            "ifNoneMatch": revision,
        })
        if "error" in resp:
            raise _violation(
                "§6.2", f"a conditional read at the current revision errored: "
                f"{resp['error']!r}")
        result = resp["result"]
        if not (isinstance(result, dict) and result.get("notModified") is True):
            raise _violation(
                "§6.2", f"ifNoneMatch at the current revision answered {result!r}; "
                f"§6.2 specifies {{'notModified': true}} with no body")
        if isinstance(result, dict) and ("instance" in result or "spec" in result):
            raise _violation(
                "§6.2", f"notModified came WITH a body ({sorted(result)!r}) — the "
                f"saving is the whole feature")
    finally:
        await _release(s, fixture)


async def _case_deleted_instance_is_a_miss_not_a_blank(s: _Session) -> None:
    """§7 — getting what is not there is an error, not an empty document.

    The get-shaped face of the central rule: a blank document reads as "it
    exists and has nothing in it", which is a different and unfalsifiable claim.
    """
    _requires_write(s, "that reading a deleted instance errors rather than "
                       "returning a blank document")
    fixture = await _fixture(s, count=1, obligation=(
        "that instances/get for a missing name errors rather than returning a "
        "blank document"))
    try:
        await _positive_control(s)
        resp = await s.raw("instances/get", {
            "channel": fixture.channel, "kind": fixture.kind,
            "name": _unique("dnap-conformance-never-written"),
        })
        if "error" in resp:
            return
        result = resp["result"]
        raise _violation(
            "§7", f"instances/get for a name that was never written answered a "
            f"result: {result!r}. 'Absent' and 'present but blank' are different "
            f"values and a caller acts differently on each."
        )
    finally:
        await _release(s, fixture)


# ---------------------------------------------------------------------------
# §7/§8.5 — a failure is NEVER an empty collection
# ---------------------------------------------------------------------------

async def _case_positive_control_a_valid_listing_succeeds(s: _Session) -> None:
    """⭐ The tautology guard, promoted to a case of its own.

    Every "must be an error" case in this suite would pass against a server
    that answers every request with an error. This case is what makes such a
    server fail — by name, first, and in a way that explains why the rest of
    the report cannot be trusted.
    """
    await _positive_control(s)


async def _case_an_empty_collection_is_falsifiable(s: _Session) -> None:
    """⭐ §7/§8.5 — ``[]`` must be a READING of a store, not a constant.

    The strongest hook-free expression of the central rule. If nothing the
    suite does can make the collection stop being empty, the emptiness was
    never an observation, and a server whose failure path returns ``[]`` is
    indistinguishable from one that read an empty shelf.

    Deliberately written as a state CHANGE rather than a state: an assertion
    about one listing can be satisfied by a constant, and an assertion about
    two cannot.
    """
    _requires_write(s, "that an empty collection is falsifiable — i.e. that "
                       "'[] of this Kind' is a reading and not a constant")
    fixture = await _fixture(s, count=1, obligation=(
        "that a listing which was empty stops being empty once an instance "
        "exists — the only way to tell a read from a constant"))
    try:
        result = await s.result("instances/list", {
            "channel": fixture.channel, "kind": fixture.kind, "limit": 1000})
        names = {n for n in (_name_of(i) for i in _instances_of(result)) if n}
        if not names:
            raise _violation(
                "§7/§8.5", f"instances/list returned an EMPTY collection for kind "
                f"{fixture.kind!r} immediately after {len(fixture.names)} instance(s) "
                f"of it were confirmed to exist ({fixture.names!r}). This '[]' is "
                f"not a reading of anything — and a caller has no way to tell it "
                f"apart from a store the server could not open."
            )
        if fixture.seeded and not set(fixture.seeded) & names:
            raise _violation(
                "§7/§8.5", f"the instances written by this suite ({fixture.seeded!r}) "
                f"do not appear in the listing ({sorted(names)!r}). The listing is "
                f"answering from something other than what the writes went into."
            )
    finally:
        await _release(s, fixture)


async def _case_induced_store_failure_is_an_error(s: _Session) -> None:
    """⭐ §7/§8.5 — the rule tested where it actually lives.

    *"Every place a failure was reported as an empty collection, a caller
    eventually read it as an answer."* Only the implementer can make the store
    fail, so this is the one case that needs a hook — and declining the hook
    does NOT yield a skip. It yields ``unverified``, which counts against
    conformance, because a green earned by being untestable is the same green a
    broken server gets.
    """
    if s.h.break_store is None:
        raise DnapRuleUnverified(
            rule="§8.5 — that a server which cannot read its store answers an "
                 "ERROR and not an empty collection (the one rule §7 places above "
                 "its own error table)",
            needs="break_store",
        )
    kind = await _positive_control(s)  # healthy first, so the change is the evidence
    channel = s.channel()
    await s.h.break_store()
    resp = await s.raw("instances/list", {"channel": channel, "kind": kind})
    if "error" in resp:
        return
    result = resp["result"]
    if _is_empty_collection(result):
        raise _violation(
            "§7/§8.5", "with its store broken, instances/list answered "
            f"{result!r}. The same listing was non-failing moments earlier, so "
            f"this '[]' is a FAILURE wearing the shape of a finding. A caller "
            f"reads it as 'nothing of this Kind exists here' and acts on it."
        )
    raise _violation(
        "§7/§8.5", f"with its store broken, instances/list answered a result: "
        f"{result!r}. Whatever this is, it was not read from the store."
    )


# ---------------------------------------------------------------------------
# §6.5 — notifications
# ---------------------------------------------------------------------------

async def _case_change_notification_carries_the_fact_not_the_document(s: _Session) -> None:
    """§6.5 — "A notification carries the fact, not the document."

    Server→client messages are not expressible through a request/response
    callable, so this needs ``drain_notifications``. Without it the case is NOT
    RUN with the obligation named — a skip, not an unverified, because unlike
    §8.5 this is a limitation of the transport seam rather than a server
    declining to be tested.
    """
    if not s.has("watch"):
        raise DnapCaseNotApplicable(
            missing="the server does not advertise the 'watch' capability",
            unchecked="that notifications/instances/changed carries the fact "
                      "(channel, kind, name, change, revision) and not the document",
        )
    if s.h.drain_notifications is None:
        raise DnapCaseNotApplicable(
            missing="the harness supplies no drain_notifications hook, and a "
                    "request/response endpoint cannot express a server-initiated "
                    "message",
            unchecked="that a change notification carries the fact and not the "
                      "document body (§6.5) — pushing bodies would make every "
                      "watcher pay for every writer",
        )
    _requires_write(s, "that a write produces a change notification carrying the fact")
    # Drain first, then cause exactly one change: the notification under test has
    # to be one this case KNOWS happened, or a pass could be somebody else's echo.
    await s.h.drain_notifications()
    fixture = await _fixture(s, count=1, obligation=(
        "that a write produces notifications/instances/changed"))
    try:
        if not fixture.seeded:
            marker = _unique("dnap-conformance-watch")
            got = await s.result("instances/get", {
                "channel": fixture.channel, "kind": fixture.kind,
                "name": fixture.names[0]})
            doc = got.get("instance", got) if isinstance(got, dict) else got
            body = {k: v for k, v in doc.items() if k != "metadata"}
            body["metadata"] = {"name": marker}
            resp = await s.raw("instances/write",
                               {"channel": fixture.channel, "instance": body})
            if "error" in resp:
                raise DnapCaseNotApplicable(
                    missing=f"the suite could not cause a change to watch "
                            f"({resp['error']!r})",
                    unchecked="that a change notification carries the fact and not "
                              "the document body",
                )
            fixture.seeded.append(marker)
        notes = list(await s.h.drain_notifications())
        changed = [n for n in notes
                   if isinstance(n, dict)
                   and n.get("method") == "notifications/instances/changed"]
        if not changed:
            raise _violation(
                "§6.5", f"{len(fixture.seeded)} write(s) produced no "
                f"notifications/instances/changed among {len(notes)} notification(s)")
        for note in changed:
            params = note.get("params") or {}
            missing = [m for m in ("channel", "kind", "name", "change", "revision")
                       if m not in params]
            if missing:
                raise _violation(
                    "§6.5", f"a change notification omitted {missing!r}: {params!r}")
            for body in ("instance", "spec", "document"):
                if body in params:
                    raise _violation(
                        "§6.5", f"a change notification carried the {body!r} body. "
                        f"It carries the FACT; the client re-reads what it cares "
                        f"about, and pushing bodies makes every watcher pay for "
                        f"every writer.")
    finally:
        await _release(s, fixture)


# ---------------------------------------------------------------------------
# §6.3 — resolution (wave 2)
# ---------------------------------------------------------------------------

def _requires_resolve(s: _Session, unchecked: str) -> None:
    if not s.has("resolve"):
        raise DnapCaseNotApplicable(
            missing="the server does not advertise the 'resolve' capability "
                    "(wave 2 — resolve/* is not implemented yet)",
            unchecked=unchecked,
        )


async def _resolved(s: _Session, name: str) -> dict:
    result = await s.result(
        "resolve/agent", {"channel": s.channel(), "name": name},
        why="resolve/agent is the method that justifies this protocol (§6.3)")
    resolved = result.get("resolved") if isinstance(result, dict) else None
    if not isinstance(resolved, dict):
        raise _violation(
            "§6.3", f"resolve/agent returned no 'resolved' object: {result!r}")
    return resolved


async def _a_resolvable_name(s: _Session) -> str:
    if s.h.resolvable_name:
        return s.h.resolvable_name
    channel = s.channel()
    for entry in await s.kinds_on(channel):
        if not entry.get("promptTarget"):
            continue
        names = await _existing(s, channel, entry["kind"], 1)
        if names:
            return names[0]
    raise DnapCaseNotApplicable(
        missing="no instance of a promptTarget Kind exists to resolve, and the "
                "harness named no resolvable_name",
        unchecked="the shape and the honesty of resolve/agent's result (§6.3)",
    )


async def _case_resolve_returns_the_runtime_neutral_shape(s: _Session) -> None:
    """§6.3 — the resolution carries what a binding needs, composed."""
    _requires_resolve(s, "that resolve/agent returns the runtime-neutral shape "
                         "with composed instructions and the revision it is of")
    resolved = await _resolved(s, await _a_resolvable_name(s))
    for member in ("name", "instructions", "revision"):
        if member not in resolved:
            raise _violation(
                "§6.3", f"the resolution omits {member!r}: {sorted(resolved)!r}")
    if not isinstance(resolved.get("instructions"), str):
        raise _violation(
            "§6.3", f"'instructions' is {type(resolved.get('instructions')).__name__}. "
            f"It is COMPOSED, not the raw template — leaving the overlay/persona/"
            f"tenant merge to the client puts the same merge in every binding.")


async def _case_resolve_reports_the_revision_it_is_of(s: _Session) -> None:
    """§6.3 — "a resolution is of a moment, and a client that caches it must be
    able to say which"."""
    _requires_resolve(s, "that a resolution names the revision it was taken at")
    resolved = await _resolved(s, await _a_resolvable_name(s))
    if not resolved.get("revision"):
        raise _violation(
            "§6.3", "the resolution carries no 'revision'. A cached resolution "
            "that cannot say which moment it is of can never be invalidated.")


async def _case_resolved_model_is_a_coordinate(s: _Session) -> None:
    """§6.3 — ``model`` is a coordinate (``provider/name``), never a vendor client id.

    *"Measured precedent: the reference binding does ``model.split('/',1)[-1]``
    in one line."* If the coordinate is not there, that line silently produces a
    vendor identifier the next binding cannot map.
    """
    _requires_resolve(s, "that resolve/* reports model as a provider/name coordinate")
    resolved = await _resolved(s, await _a_resolvable_name(s))
    model = resolved.get("model")
    if model is None:
        raise DnapCaseNotApplicable(
            missing="the resolution carried no 'model' for this definition",
            unchecked="that 'model' is a provider/name coordinate and not a vendor "
                      "client identifier",
        )
    if not isinstance(model, str) or "/" not in model.strip("/"):
        raise _violation(
            "§6.3", f"model={model!r} is not a provider/name coordinate. A binding "
            f"maps a coordinate; it cannot map a vendor client id, and it cannot "
            f"tell the two apart either.")


async def _case_resolution_carries_no_host_concerns(s: _Session) -> None:
    """⛔ §6.3 — checkpointers, stores, thread indexes, telemetry sinks and cost
    tables are ABSENT on purpose.

    *"Every one of them that leaked into a definition contract in the reference
    implementation became a runtime the definition could no longer leave."*
    """
    _requires_resolve(s, "that a resolution carries no host concern "
                         "(checkpointer/store/thread index/telemetry/cost table)")
    resolved = await _resolved(s, await _a_resolvable_name(s))
    leaked = sorted(
        key for key in resolved
        if any(concern in key.lower().replace("_", "") for concern in HOST_CONCERNS)
    )
    if leaked:
        raise _violation(
            "§6.3", f"the resolution carries host concerns {leaked!r}. These belong "
            f"to whoever is hosting, not to the definition; every one that leaked "
            f"into the reference implementation's contract became a runtime the "
            f"definition could no longer leave.")


async def _case_resolving_an_unknown_name_is_an_error(s: _Session) -> None:
    """⭐ §7 at the resolution layer — a definition that is not there is not a
    blank definition."""
    _requires_resolve(s, "that resolving a name that does not exist errors rather "
                         "than returning a blank definition")
    await _positive_control(s)
    resp = await s.raw("resolve/agent", {
        "channel": s.channel(), "name": _unique("dnap-conformance-no-such-agent")})
    if "error" in resp:
        return
    resolved = (resp["result"] or {}).get("resolved") if isinstance(resp["result"], dict) else None
    raise _violation(
        "§7", f"resolving a name that does not exist answered a result: "
        f"{resolved!r}. A blank resolution is handed to a runtime and RUN — "
        f"'no such agent' and 'an agent with no instructions' are different values "
        f"and only one of them is safe.")


async def _case_partial_resolution_is_resolution_incomplete(s: _Session) -> None:
    """§7 — ``-32020``: "a definition that resolved partially is not a definition,
    and returning it with the gaps silently filled is worse than failing, because
    the caller cannot tell"."""
    _requires_resolve(s, "that a partial resolution answers -32020 rather than a "
                         "result with the gaps filled")
    if s.h.break_resolution is None:
        raise DnapRuleUnverified(
            rule="§7 — that a resolution which ran and could not finish answers "
                 "-32020 RESOLUTION_INCOMPLETE rather than a plausible-looking "
                 "definition with silent gaps",
            needs="break_resolution",
        )
    name = await s.h.break_resolution()
    await _must_refuse(
        s, "resolve/agent", {"channel": s.channel(), "name": name},
        expect=RESOLUTION_INCOMPLETE, section="§7",
        rule="the definition could not be fully resolved",
    )


async def _case_resolve_copilot_reports_its_source(s: _Session) -> None:
    """§6.3 — a served surface's resolution says what it was resolved FROM."""
    if not s.has("resolve"):
        raise DnapCaseNotApplicable(
            missing="the server does not advertise the 'resolve' capability "
                    "(wave 2)",
            unchecked="that resolve/copilot reports sourceKind and sourceName",
        )
    caps = s.caps.get("resolve")
    if not (isinstance(caps, dict) and caps.get("copilot")):
        raise DnapCaseNotApplicable(
            missing="the server's 'resolve' capability does not include 'copilot'",
            unchecked="that resolve/copilot reports the surface it resolved and the "
                      "definition it is mounted over (§6.3)",
        )
    name = await _a_resolvable_name(s)
    result = await s.result("resolve/copilot", {"channel": s.channel(), "name": name})
    resolved = result.get("resolved") if isinstance(result, dict) else None
    if not isinstance(resolved, dict):
        raise _violation("§6.3", f"resolve/copilot returned no 'resolved': {result!r}")
    for member in ("sourceKind", "sourceName"):
        if not resolved.get(member):
            raise _violation(
                "§6.3", f"resolve/copilot omitted {member!r}. Two Kinds resolve into "
                f"the same shape, so the shape has to say which one it came from.")


# ---------------------------------------------------------------------------
# §6.4 — search (wave 2). Five rules, every one a measurement.
# ---------------------------------------------------------------------------

def _requires_search(s: _Session, unchecked: str) -> None:
    if not s.has("search"):
        raise DnapCaseNotApplicable(
            missing="the server does not advertise the 'search' capability "
                    "(wave 2 — search/* is not implemented yet)",
            unchecked=unchecked,
        )


async def _search(s: _Session, fixture: _Fixture, **params: Any) -> dict:
    body = {"channel": fixture.channel, "kind": fixture.kind, **params}
    result = await s.result("search/instances", body,
                            why="search over a served Kind on a served channel")
    if not isinstance(result, dict) or not isinstance(result.get("hits"), list):
        raise _violation("§6.4", f"search/instances returned no 'hits' list: {result!r}")
    return result


async def _search_fixture(s: _Session, obligation: str, *, count: int = 3) -> _Fixture:
    _requires_search(s, obligation)
    return await _fixture(s, count=count, obligation=obligation)


async def _case_search_envelope_declares_ranked_not_filtered(s: _Session) -> None:
    """§6.4 rule 1 — "a result is RANKED, not FILTERED, and the envelope MUST say so"."""
    fixture = await _search_fixture(s, "that the search envelope declares "
                                       "RANKED_NOT_FILTERED (§6.4 rule 1)")
    try:
        result = await _search(s, fixture, query="conformance", k=5)
        notice = result.get("relevanceNotice")
        if notice != "RANKED_NOT_FILTERED":
            raise _violation(
                "§6.4", f"relevanceNotice={notice!r}. Measured on the reference "
                f"deployment: 8 of 12 irrelevant queries scored above the worst "
                f"genuinely relevant one. The envelope has to SAY that these are "
                f"ranks, because the caller cannot infer it from the numbers.")
        for member in ("mode", "degraded", "revision"):
            if member not in result:
                raise _violation("§6.4", f"the search envelope omits {member!r}: "
                                         f"{sorted(result)!r}")
    finally:
        await _release(s, fixture)


async def _case_search_ships_no_relevance_floor(s: _Session) -> None:
    """⭐ §6.4 rule 1 — the server ships NO relevance floor.

    *"A server that silently dropped low results would be asserting a judgement
    it cannot make."* Expressed falsifiably: over a corpus that is known to be
    non-empty, a query of nonsense must still return hits, because ranking
    without a floor always yields an order. A server with a hidden floor
    returns nothing here — and returns it with ``degraded: false``, which is
    the shape §7 forbids.
    """
    fixture = await _search_fixture(
        s, "that the server ships no hidden relevance floor (§6.4 rule 1)")
    try:
        result = await _search(
            s, fixture, query=_unique("zzqx nonsense vocabulary"), k=len(fixture.names))
        if result.get("degraded"):
            raise DnapCaseNotApplicable(
                missing=f"search answered degraded=true "
                        f"({result.get('degradedReason')!r}), so an empty result "
                        f"here would be a blind spot rather than a floor",
                unchecked="that no relevance floor silently drops low-scoring hits",
            )
        if not result["hits"]:
            raise _violation(
                "§6.4", f"a non-degraded search over a corpus with at least "
                f"{len(fixture.names)} instance(s) of {fixture.kind!r} returned NO "
                f"hits. Ranking without a floor always produces an order; an empty "
                f"result here means the server applied a judgement of relevance it "
                f"has no evidence for — and it reported neither the judgement nor "
                f"how many rows it removed.")
    finally:
        await _release(s, fixture)


async def _case_min_similarity_is_the_callers_policy(s: _Session) -> None:
    """§6.4 rule 2 — the CALLER's threshold is honoured; the protocol invents none."""
    fixture = await _search_fixture(
        s, "that a caller-supplied minSimilarity is honoured (§6.4 rule 2)")
    try:
        base = await _search(s, fixture, query="conformance", k=10)
        if not base["hits"]:
            raise DnapCaseNotApplicable(
                missing="the unfiltered search returned no hits, so there is no "
                        "similarity to threshold against",
                unchecked="that a caller-supplied minSimilarity is honoured",
            )
        sims = [h.get("similarity") for h in base["hits"]
                if isinstance(h.get("similarity"), (int, float))]
        if not sims:
            raise _violation(
                "§6.4", f"no hit carried a numeric 'similarity': {base['hits']!r}")
        floor = max(sims)
        filtered = await _search(s, fixture, query="conformance", k=10,
                                 minSimilarity=floor)
        leaked = [h for h in filtered["hits"]
                  if isinstance(h.get("similarity"), (int, float))
                  and h["similarity"] < floor]
        if leaked:
            raise _violation(
                "§6.4", f"minSimilarity={floor} was supplied and "
                f"{len(leaked)} hit(s) below it came back "
                f"({[h.get('similarity') for h in leaked]!r}). A threshold the "
                f"server accepts and does not apply is worse than one it refuses.")
    finally:
        await _release(s, fixture)


async def _case_min_similarity_discloses_its_effect(s: _Session) -> None:
    """§6.4 rule 2, second half — "the result reports how many hits it removed".

    ⚠️ SPEC GAP. The rule is normative and the envelope in §6.4 names no member
    to carry the count. Two conforming servers would report it under two names
    and no client could read either. The case therefore refuses to invent a
    field name and files the hole instead — a spec gap is never a pass.
    """
    _requires_search(s, "that a server applying minSimilarity reports how many "
                        "hits it removed")
    raise DnapSpecGap(
        section="§6.4 rule 2",
        question=(
            "'When applied, the result reports how many hits it removed' is "
            "normative, but the envelope in §6.4 names no member for the count "
            "(the shown members are mode, degraded, degradedReason, "
            "relevanceNotice, revision). Two conforming servers would pick two "
            "names and no client could read either. The spec needs to name the "
            "field — e.g. 'filtered': {'byMinSimilarity': <n>} — before this "
            "can be tested."
        ),
    )


async def _case_two_notes_travel(s: _Session) -> None:
    """§6.4 rule 3 — ``score`` and ``similarity`` are two quantities, and both travel.

    *"A caller given only the first cannot tell 'first among bad' from 'first
    among good'."*
    """
    fixture = await _search_fixture(
        s, "that every hit carries BOTH the fused rank score and the raw "
           "similarity (§6.4 rule 3)")
    try:
        result = await _search(s, fixture, query="conformance", k=10)
        if not result["hits"]:
            raise DnapCaseNotApplicable(
                missing="the search returned no hits to inspect",
                unchecked="that a hit carries both 'score' and 'similarity'",
            )
        for hit in result["hits"]:
            for member in ("kind", "name", "score", "similarity"):
                if member not in hit:
                    raise _violation(
                        "§6.4", f"a hit omits {member!r}: {sorted(hit)!r}. score is "
                        f"a fused rank comparable only WITHIN one call; similarity "
                        f"is the raw measure and is comparable across calls. One "
                        f"cannot stand in for the other.")
            sim = hit["similarity"]
            if not isinstance(sim, (int, float)) or not (-1.000001 <= sim <= 1.000001):
                raise _violation(
                    "§6.4", f"similarity={sim!r} for {hit.get('name')!r} is not a "
                    f"cosine in [-1, 1] — 'comparable across calls' requires one "
                    f"shared scale, which is exactly the half a single-server test "
                    f"never catches.")
    finally:
        await _release(s, fixture)


async def _case_hits_are_ordered_by_their_score(s: _Session) -> None:
    """§6.4 rule 3 — the fused rank is what orders the envelope."""
    fixture = await _search_fixture(
        s, "that hits arrive ordered by the score they report")
    try:
        result = await _search(s, fixture, query="conformance", k=10)
        scores = [h.get("score") for h in result["hits"]
                  if isinstance(h.get("score"), (int, float))]
        if len(scores) > 1 and scores != sorted(scores, reverse=True):
            raise _violation(
                "§6.4", f"hits are not ordered by their own score: {scores!r}. A "
                f"caller that trusts the order and a caller that trusts the number "
                f"then disagree, and neither can tell which is wrong.")
    finally:
        await _release(s, fixture)


async def _case_narrow_applies_where_candidates_are_chosen(s: _Session) -> None:
    """⭐ §6.4 rule 4 — ``narrow`` applies where candidates are CHOSEN.

    The measured defect: adding 1000 rows of one Kind to a 153-row scope took
    the dense plane's top-40 from ``{Issue:37, Engram:2, App:1}`` to
    ``{Chunk:40}``, *with ``mode`` still reading hybrid and ``degraded`` still
    reading false*. A post-filter is invisible in the envelope, so it has to be
    caught by counting.

    Expressed as a count: with ``k`` no larger than the number of instances the
    prefix matches, a pre-filter returns ``k`` hits. A post-filter returns fewer
    — its fixed candidate budget was spent on rows the narrow then discarded.
    """
    fixture = await _search_fixture(
        s, "that 'narrow' is applied where candidates are chosen and not to the "
           "list already chosen (§6.4 rule 4)", count=3)
    try:
        # Ground truth comes from the LISTING, never from the search whose
        # correctness is in question. Deriving the expected count from the
        # ranking would let a broken ranking define its own pass mark.
        whole = await s.result("instances/list", {
            "channel": fixture.channel, "kind": fixture.kind, "limit": 1000})
        population = [n for n in (_name_of(i) for i in _instances_of(whole)) if n]
        if len(population) < 2:
            raise DnapCaseNotApplicable(
                missing=f"only {len(population)} instance(s) of {fixture.kind!r} "
                        f"exist, so no prefix names a proper subset to narrow to",
                unchecked="that 'narrow' applies at candidate selection",
            )
        unnarrowed = await _search(s, fixture, query="conformance",
                                   k=len(population))
        ranked = [h.get("name") for h in unnarrowed["hits"]]
        # The rows a post-filter would lose are the ones the unnarrowed budget
        # never reached. Target those: it is the only place the defect shows.
        buried = [n for n in population if n not in ranked] or ranked[-1:]
        prefix, matching = _narrow_prefix(buried[0], population)
        if not prefix:
            raise DnapCaseNotApplicable(
                missing=f"no prefix of {buried[0]!r} names a proper non-empty "
                        f"subset of the {len(population)} instance(s) present",
                unchecked="that 'narrow' applies at candidate selection rather than "
                          "as a post-filter over an already-chosen candidate list",
            )
        narrowed = await _search(s, fixture, query="conformance",
                                 k=len(matching), narrow={"namePrefix": prefix})
        stray = [h.get("name") for h in narrowed["hits"]
                 if not str(h.get("name") or "").startswith(prefix)]
        if stray:
            raise _violation(
                "§6.4", f"narrow namePrefix={prefix!r} leaked {stray!r}")
        if len(narrowed["hits"]) < len(matching) and not narrowed.get("degraded"):
            raise _violation(
                "§6.4", f"narrow namePrefix={prefix!r} with k={len(matching)} "
                f"returned {len(narrowed['hits'])} hit(s), although "
                f"{len(matching)} instance(s) carry that prefix "
                f"({matching!r}) — counted from instances/list, not from the "
                f"search. That is the signature of a POST-filter: the candidate "
                f"budget was spent before the narrow was applied, so a voluminous "
                f"slice crowds every other row out. Note what the envelope still "
                f"says while this happens — mode={narrowed.get('mode')!r}, "
                f"degraded={narrowed.get('degraded')!r} — which is exactly why "
                f"this has to be caught by counting."
            )
    finally:
        await _release(s, fixture)


def _narrow_prefix(target: str, population: Sequence[str]) -> tuple[str, list[str]]:
    """The SHORTEST prefix of ``target`` matching a proper, non-empty subset.

    Shortest, so the narrowed group is as large as it can be while still leaving
    rows outside it — a group of one would be a weaker question, and a group of
    all would be no question at all.
    """
    for i in range(1, len(target) + 1):
        prefix = target[:i]
        matching = [n for n in population if n.startswith(prefix)]
        if 0 < len(matching) < len(population):
            return prefix, matching
    return "", []


async def _case_degraded_carries_a_reason(s: _Session) -> None:
    """§6.4 rule 5 — ``degraded`` without a reason is a shrug.

    A caller can act on "the semantic plane is down"; it cannot act on "true".
    """
    fixture = await _search_fixture(
        s, "that a degraded search names why it degraded (§6.4 rule 5)")
    try:
        result = await _search(s, fixture, query="conformance", k=5)
        if "degraded" not in result:
            raise _violation("§6.4", f"the search envelope omits 'degraded': "
                                     f"{sorted(result)!r}")
        if result.get("degraded") and not result.get("degradedReason"):
            raise _violation(
                "§6.4", "degraded=true with degradedReason=null. A caller can act "
                "on a reason and can do nothing with a boolean; and without one, "
                "'degraded' becomes a flag everybody stops reading.")
        if not result.get("degraded") and result.get("degradedReason"):
            raise _violation(
                "§6.4", f"degraded=false with degradedReason="
                f"{result.get('degradedReason')!r} — the pair contradicts itself")
    finally:
        await _release(s, fixture)


async def _case_search_unavailable_is_never_empty_hits(s: _Session) -> None:
    """⭐ §6.4 rule 5 + §7 — ``-32030``, "never an empty ``hits``".

    *"An empty hits with degraded: true is a blind spot, not a finding — this is
    the protocol's central error rule applied where it is easiest to violate."*
    Only the implementer can take every plane down, so this needs a hook and
    ends ``unverified`` without one.
    """
    _requires_search(s, "that a search with no runnable plane answers -32030 and "
                        "not an empty hits list")
    if s.h.break_search is None:
        raise DnapRuleUnverified(
            rule="§6.4 rule 5 / §7 — that a search with NO runnable plane answers "
                 "-32030 SEARCH_UNAVAILABLE and never an empty 'hits'",
            needs="break_search",
        )
    fixture = await _fixture(s, count=1, obligation=(
        "that a search with no runnable plane answers -32030"))
    try:
        await _search(s, fixture, query="conformance", k=5)  # healthy first
        await s.h.break_search()
        resp = await s.raw("search/instances", {
            "channel": fixture.channel, "kind": fixture.kind,
            "query": "conformance", "k": 5})
        if "error" in resp:
            if resp["error"].get("code") != SEARCH_UNAVAILABLE:
                raise _violation(
                    "§7", f"with every plane down, search answered code "
                    f"{resp['error'].get('code')!r}, not -32030")
            return
        result = resp["result"]
        if isinstance(result, dict) and result.get("hits") == []:
            raise _violation(
                "§6.4/§7", f"with every plane down, search answered an EMPTY hits "
                f"list (degraded={result.get('degraded')!r}). 'I searched and found "
                f"nothing' and 'I could not search' are different values; the same "
                f"query returned hits moments earlier, so this emptiness is a blind "
                f"spot being reported as a finding.")
        raise _violation(
            "§6.4/§7", f"with every plane down, search answered a result: {result!r}")
    finally:
        await _release(s, fixture)


async def _case_search_unadvertised_kind_is_kind_not_served(s: _Session) -> None:
    """§8.2 — the Kind rule holds on the search face too."""
    _requires_search(s, "that searching an unadvertised Kind answers -32003 and "
                        "not an empty hits list")
    await _must_refuse(
        s, "search/instances",
        {"channel": s.channel(), "kind": s.unserved_kind(), "query": "x", "k": 5},
        expect=KIND_NOT_SERVED, section="§8.2",
        rule="a Kind outside the advertised vocabulary is -32003 on every face "
             "that takes a Kind",
    )


# ---------------------------------------------------------------------------
# the roster
# ---------------------------------------------------------------------------

#: ``(name, section, protects, fn)``. ``protects`` is the one-line statement of
#: what the case is for, and it is what the report prints — a failing case has
#: to be readable as a broken promise, not as a broken test.
_CASES: list[tuple[str, str, str, Callable[[_Session], Awaitable[None]]]] = [
    # framing
    ("envelope_is_jsonrpc_2", "§2",
     "responses follow JSON-RPC 2.0 exactly and echo the request id",
     _case_envelope_is_jsonrpc_2),
    ("notification_gets_no_response", "§2",
     "a notification is not answered",
     _case_notification_gets_no_response),
    ("batch_is_supported", "§2",
     "batch requests MUST be supported by servers",
     _case_batch_is_supported),
    ("unknown_method_is_method_not_found", "§8.2",
     "an unknown method is -32601, never a degraded answer",
     _case_unknown_method_is_method_not_found),
    ("method_outside_capability_is_method_not_found", "§4/§8.2",
     "a method outside every advertised capability is -32601",
     _case_method_outside_capability_is_method_not_found),
    # lifecycle + vocabulary
    ("initialize_advertises_the_connection", "§8.1",
     "initialize advertises kinds, channels and capabilities",
     _case_initialize_advertises_the_connection),
    ("advertised_kinds_are_a_vocabulary", "§4",
     "the advertised Kind vocabulary is a set of names, not a bag",
     _case_advertised_kinds_are_a_vocabulary),
    ("channel_vocabulary_never_exceeds_the_advertised_one", "§4/§6.1",
     "a channel serves no Kind the client was never told about",
     _case_channel_vocabulary_never_exceeds_the_advertised_one),
    ("kinds_describe_carries_a_schema", "§6.1",
     "the schema travels, so a client never has to guess",
     _case_kinds_describe_carries_a_schema),
    ("unadvertised_kind_is_kind_not_served", "§8.2",
     "a Kind outside the vocabulary is -32003",
     _case_unadvertised_kind_is_kind_not_served),
    ("unadvertised_kind_is_not_an_empty_collection", "§7",
     "...and specifically not an empty collection",
     _case_unadvertised_kind_is_not_an_empty_collection),
    # channels
    ("unserved_channel_is_channel_not_served", "§3",
     "an unserved channel is -32004",
     _case_unserved_channel_is_channel_not_served),
    ("unserved_channel_is_never_substituted", "§3",
     "⛔ an unserved channel is NEVER answered from one the server does serve",
     _case_unserved_channel_is_never_substituted),
    ("unserved_tenant_overlay_is_not_the_base", "§3",
     "⛔ an unserved tenant overlay never falls back to its base scope",
     _case_unserved_tenant_overlay_is_not_the_base),
    # select
    ("select_names_is_honoured_or_rejected", "§8.3",
     "select is honoured exactly or refused with -32602",
     _case_select_names_is_honoured_or_rejected),
    ("select_full_never_echoes_a_narrower_shape", "§6.2",
     "⛔ a server never echoes the requested projection over a narrower payload",
     _case_select_full_never_echoes_a_narrower_shape),
    ("select_field_paths_is_honoured_or_rejected", "§6.2",
     "a field-path projection is honoured exactly or refused",
     _case_select_field_paths_is_honoured_or_rejected),
    ("unhonourable_select_is_invalid_params", "§6.2",
     "a projection outside the defined union is refused, not reinterpreted",
     _case_unhonourable_select_is_invalid_params),
    # pagination
    ("list_carries_an_opaque_revision", "§6.2",
     "a listing names the snapshot it belongs to",
     _case_list_carries_an_opaque_revision),
    ("revision_is_constant_across_pages", "§8.4",
     "⭐ all pages of one listing belong to one snapshot",
     _case_revision_is_constant_across_pages),
    ("pages_neither_duplicate_nor_drop", "§6.2",
     "walking the cursor yields every instance exactly once",
     _case_pages_neither_duplicate_nor_drop),
    ("expired_cursor_is_cursor_expired", "§6.2",
     "an expired cursor is -32005, so the client restarts",
     _case_expired_cursor_is_cursor_expired),
    ("foreign_cursor_is_an_error_not_exhaustion", "§6.2/§7",
     "⭐ an uninterpretable cursor is never an empty final page",
     _case_foreign_cursor_is_an_error_not_exhaustion),
    # write
    ("write_then_get_round_trips", "§6.2",
     "a written instance reads back with its revision",
     _case_write_then_get_round_trips),
    ("stale_ifmatch_is_revision_conflict", "§6.2",
     "⭐ a write against a moved revision is -32011, with the current revision",
     _case_stale_ifmatch_is_revision_conflict),
    ("validation_failure_names_path_and_rule", "§6.2",
     "-32010 carries the failing path and the rule, never a bare 'invalid'",
     _case_validation_failure_names_path_and_rule),
    ("derived_metadata_on_write_is_refused", "§5",
     "metadata.id and metadata.revision are derived and cannot be authored",
     _case_derived_metadata_on_write_is_refused),
    ("conditional_read_is_not_modified", "§6.2",
     "ifNoneMatch at the current revision answers notModified with no body",
     _case_conditional_read_is_not_modified),
    ("deleted_instance_is_a_miss_not_a_blank", "§7",
     "absent and present-but-blank are different values",
     _case_deleted_instance_is_a_miss_not_a_blank),
    # the central rule
    ("positive_control_a_valid_listing_succeeds", "§8",
     "⭐ a valid listing succeeds — without which every refusal case is a tautology",
     _case_positive_control_a_valid_listing_succeeds),
    ("an_empty_collection_is_falsifiable", "§8.5",
     "⭐ '[]' is a reading of a store, not a constant",
     _case_an_empty_collection_is_falsifiable),
    ("induced_store_failure_is_an_error", "§8.5",
     "⭐ a server that cannot read its store errors — it never answers '[]'",
     _case_induced_store_failure_is_an_error),
    # watch
    ("change_notification_carries_the_fact_not_the_document", "§6.5",
     "a change notification carries the fact; the client re-reads the body",
     _case_change_notification_carries_the_fact_not_the_document),
    # resolution — wave 2
    ("resolve_returns_the_runtime_neutral_shape", "§6.3",
     "a resolution is composed and runtime-neutral",
     _case_resolve_returns_the_runtime_neutral_shape),
    ("resolve_reports_the_revision_it_is_of", "§6.3",
     "a resolution is of a moment, and says which",
     _case_resolve_reports_the_revision_it_is_of),
    ("resolved_model_is_a_coordinate", "§6.3",
     "model is provider/name, never a vendor client id",
     _case_resolved_model_is_a_coordinate),
    ("resolution_carries_no_host_concerns", "§6.3",
     "⛔ checkpointers, stores, telemetry and cost tables stay with the host",
     _case_resolution_carries_no_host_concerns),
    ("resolving_an_unknown_name_is_an_error", "§7",
     "⭐ a definition that is not there is not a blank definition",
     _case_resolving_an_unknown_name_is_an_error),
    ("partial_resolution_is_resolution_incomplete", "§7",
     "a partial resolution is -32020, never a result with the gaps filled",
     _case_partial_resolution_is_resolution_incomplete),
    ("resolve_copilot_reports_its_source", "§6.3",
     "a resolved surface says what it was resolved from",
     _case_resolve_copilot_reports_its_source),
    # search — wave 2
    ("search_envelope_declares_ranked_not_filtered", "§6.4 r1",
     "the envelope says these are ranks, because the numbers do not",
     _case_search_envelope_declares_ranked_not_filtered),
    ("search_ships_no_relevance_floor", "§6.4 r1",
     "⭐ the server asserts no judgement of relevance it cannot make",
     _case_search_ships_no_relevance_floor),
    ("min_similarity_is_the_callers_policy", "§6.4 r2",
     "a caller-supplied threshold is applied; the protocol invents none",
     _case_min_similarity_is_the_callers_policy),
    ("min_similarity_discloses_its_effect", "§6.4 r2",
     "a filter that hides its own effect turns a policy into a fact",
     _case_min_similarity_discloses_its_effect),
    ("two_notes_travel", "§6.4 r3",
     "score and similarity are two quantities, and both travel",
     _case_two_notes_travel),
    ("hits_are_ordered_by_their_score", "§6.4 r3",
     "the order and the numbers agree",
     _case_hits_are_ordered_by_their_score),
    ("narrow_applies_where_candidates_are_chosen", "§6.4 r4",
     "⭐ narrow is applied at selection, never over an already-chosen list",
     _case_narrow_applies_where_candidates_are_chosen),
    ("degraded_carries_a_reason", "§6.4 r5",
     "a degraded search names why",
     _case_degraded_carries_a_reason),
    ("search_unavailable_is_never_empty_hits", "§6.4 r5",
     "⭐ 'I could not search' never wears the shape of 'I found nothing'",
     _case_search_unavailable_is_never_empty_hits),
    ("search_unadvertised_kind_is_kind_not_served", "§8.2",
     "the Kind rule holds on the search face too",
     _case_search_unadvertised_kind_is_kind_not_served),
]


@dataclass(frozen=True)
class DnapCase:
    """One runnable conformance case bound to a server factory."""

    name: str
    section: str
    protects: str
    factory: Callable[[], Awaitable[Any]]
    _fn: Callable[[_Session], Awaitable[None]]

    async def run(self) -> None:
        harness = await _harness(self.factory)
        session = _Session(harness)
        try:
            await session.initialize()
            await self._fn(session)
        finally:
            if harness.cleanup is not None:
                await harness.cleanup()

    def __repr__(self) -> str:
        return f"DnapCase({self.name} · {self.section})"


def dnap_conformance_suite(
    factory: Callable[[], Awaitable[Any]],
) -> list[DnapCase]:
    """THE conformance suite for a DNAP 1.0 server.

    Args:
        factory: async zero-arg callable returning an endpoint, an
            ``(endpoint, cleanup)`` pair, or a :class:`DnapHarness`. Called
            once PER CASE, so cases cannot contaminate each other.

    Returns:
        list of :class:`DnapCase` — parametrize in pytest and ``await
        case.run()``, or use :func:`run_dnap_conformance` for a report.
    """
    return [
        DnapCase(name=name, section=section, protects=protects,
                 factory=factory, _fn=fn)
        for name, section, protects, fn in _CASES
    ]


@dataclass
class DnapConformanceReport:
    """The verdict, in five buckets rather than two.

    ``ok`` is False while anything is failed OR unverified. An obligation that
    could not be observed is not an obligation that was met, and a report that
    conflated the two would reproduce, in its own summary, the exact confusion
    §7 forbids servers to make between an empty answer and an unanswerable
    question.
    """

    passed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    unverified: list[tuple[str, str]] = field(default_factory=list)
    spec_gaps: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed and not self.unverified

    def summary(self) -> str:
        return (
            f"{len(self.passed)} passed · {len(self.failed)} failed · "
            f"{len(self.unverified)} unverified · {len(self.skipped)} not run · "
            f"{len(self.spec_gaps)} spec gap(s)"
        )

    def raise_if_failed(self) -> None:
        if self.ok:
            return
        lines = [f"DNAP conformance: {self.summary()}"]
        if self.failed:
            lines.append("FAILED — the server violates the specification:")
            lines += [f"  - {n}: {e}" for n, e in self.failed]
        if self.unverified:
            lines.append(
                "UNVERIFIED — the obligation could not be observed and the harness "
                "offered no hook. Unverified is not conformant:")
            lines += [f"  - {n}: {e}" for n, e in self.unverified]
        raise AssertionError("\n".join(lines))


async def run_dnap_conformance(
    factory: Callable[[], Awaitable[Any]],
) -> DnapConformanceReport:
    """Run the whole suite programmatically (scripts, CI without pytest)."""
    report = DnapConformanceReport()
    for case in dnap_conformance_suite(factory):
        try:
            await case.run()
        except DnapSpecGap as gap:
            report.spec_gaps.append((case.name, str(gap)))
        except DnapRuleUnverified as unver:
            report.unverified.append((case.name, str(unver)))
        except DnapCaseNotApplicable as skip:
            report.skipped.append((case.name, str(skip)))
        except Exception as exc:  # noqa: BLE001
            report.failed.append((case.name, f"{type(exc).__name__}: {exc}"))
        else:
            report.passed.append(case.name)
    return report
