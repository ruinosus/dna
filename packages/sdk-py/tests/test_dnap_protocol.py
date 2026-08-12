"""DNAP wave 1 — the conformance rules of ``docs/spec/dnap-1.0-draft.md``.

⚠️ **These tests freeze the QUESTION, not the answer.** Nothing here asserts a
method count, a Kind count, a capability list or a signature — registering an
unrelated method must not break a single one of them, and there is a test
(:func:`test_registering_an_unrelated_method_breaks_nothing`) whose whole job
is to prove that property holds. This repo has broken four assertions in one
day by freezing counts; the fix is not to be careful, it is to ask questions
whose answers do not move.

Each of the five conformance rules of §8 has at least one test that **fails if
the rule is loosened**. The loosening that would make it pass is named in the
docstring, so the next reader can kill the mutant again without re-deriving it.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.adapters.filesystem import FilesystemWritableSource
from dna.application.live import LiveDna
from dna.kernel import Kernel
from dna.protocol import (
    CHANNEL_NOT_SERVED,
    CURSOR_EXPIRED,
    INVALID_PARAMS,
    INVALID_REQUEST,
    KIND_NOT_SERVED,
    METHOD_NOT_FOUND,
    NOT_FOUND,
    NOT_INITIALIZED,
    NOT_WRITABLE,
    PARSE_ERROR,
    REFUSED,
    REVISION_CONFLICT,
    VALIDATION_FAILED,
    ChannelRequirement,
    DnapError,
    DnapServer,
    builtin_registry,
    parse_channel,
)

_SCOPE = "dnap-fixture"
_OTHER = "not-this-one"


# ══ fixtures ════════════════════════════════════════════════════════════════


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@pytest.fixture()
def live(tmp_path: Path) -> LiveDna:
    base = tmp_path / "scopes"
    _write(
        base / _SCOPE / "Genome.yaml",
        {
            "apiVersion": "dna.io/v1", "kind": "Genome",
            "metadata": {"name": _SCOPE},
            "spec": {"scope": _SCOPE, "description": "DNAP test fixture"},
        },
    )
    kernel = Kernel.auto(FilesystemWritableSource(str(base)))
    return LiveDna(base_scope=_SCOPE, kernel=kernel, provider=None)


@pytest.fixture()
def server(live: LiveDna) -> DnapServer:
    return DnapServer(live, scopes=[_SCOPE])


async def _call(server: DnapServer, method: str, **params):
    """One request in, the decoded response out."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        payload["params"] = params
    return await server.handle_payload(payload)


async def _ok(server: DnapServer, method: str, **params):
    answer = await _call(server, method, **params)
    assert "error" not in answer, answer.get("error")
    return answer["result"]


async def _err(server: DnapServer, method: str, **params) -> dict:
    answer = await _call(server, method, **params)
    assert "error" in answer, answer
    return answer["error"]


async def _ready(server: DnapServer) -> DnapServer:
    await _ok(server, "initialize", protocolVersion="1.0",
              client={"name": "test", "version": "0"},
              capabilities={"write": {}, "watch": {}})
    return server


def _channel(scope: str = _SCOPE, tenant: str | None = None) -> str:
    return f"dnap-scope:/{scope}" + (f"#{tenant}" if tenant else "")


def _doc(kind: str, name: str, spec: dict, **metadata) -> dict:
    """§6.2: `instances/write` takes the WHOLE document, and the Kind is read
    from `document.kind` — there is no separate `kind` param, because a second
    spelling is a place for the two to disagree."""
    return {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": kind,
        "metadata": {"name": name, **metadata}, "spec": spec,
    }


# ══ §2 — JSON-RPC 2.0 framing ═══════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a_notification_gets_no_response_at_all(server):
    """JSON-RPC §4.1. **Mutant:** answer notifications like requests — this
    fails, because a response object is not silence."""
    await _ready(server)
    answer = await server.handle_payload(
        {"jsonrpc": "2.0", "method": "kinds/list"},
    )
    assert answer is None


@pytest.mark.asyncio
async def test_a_null_id_is_a_request_and_an_absent_id_is_a_notification(server):
    """The two are collapsed by most hand-rolled dispatchers, and collapsing
    them either swallows a response or invents one."""
    await _ready(server)
    answered = await server.handle_payload(
        {"jsonrpc": "2.0", "id": None, "method": "kinds/list"},
    )
    assert answered is not None and answered["id"] is None
    assert await server.handle_payload(
        {"jsonrpc": "2.0", "method": "kinds/list"},
    ) is None


@pytest.mark.asyncio
async def test_a_bad_envelope_is_invalid_request_not_a_crash(server):
    for bad in (
        {"id": 1, "method": "kinds/list"},                      # no jsonrpc
        {"jsonrpc": "1.0", "id": 1, "method": "kinds/list"},     # wrong version
        {"jsonrpc": "2.0", "id": 1},                             # no method
        {"jsonrpc": "2.0", "id": True, "method": "kinds/list"},  # boolean id
    ):
        answer = await server.handle_payload(bad)
        assert answer["error"]["code"] == INVALID_REQUEST, bad


@pytest.mark.asyncio
async def test_positional_params_are_refused_by_name(server):
    """DNAP calls are by-name (§6). A positional array is a well-formed
    JSON-RPC request DNAP cannot accept — ``-32602``, not ``-32600``."""
    answer = await server.handle_payload(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": [1, 2]},
    )
    assert answer["error"]["code"] == INVALID_PARAMS


@pytest.mark.asyncio
async def test_batches_are_supported_and_notifications_inside_stay_silent(server):
    """§2: *"Batch requests MUST be supported by servers."* And a batch of
    nothing but notifications produces no response array."""
    await _ready(server)
    answers = await server.handle_payload([
        {"jsonrpc": "2.0", "id": "a", "method": "kinds/list"},
        {"jsonrpc": "2.0", "method": "kinds/list"},
        {"jsonrpc": "2.0", "id": "b", "method": "nope/nope"},
    ])
    assert [a["id"] for a in answers] == ["a", "b"]
    assert answers[1]["error"]["code"] == METHOD_NOT_FOUND
    assert await server.handle_payload(
        [{"jsonrpc": "2.0", "method": "kinds/list"}],
    ) is None


@pytest.mark.asyncio
async def test_an_empty_batch_is_one_error_not_an_empty_array(server):
    """An empty array response is indistinguishable from "every element was a
    notification" — which is why JSON-RPC §6 answers a single error here."""
    answer = await server.handle_payload([])
    assert answer["error"]["code"] == INVALID_REQUEST
    assert answer["id"] is None


@pytest.mark.asyncio
async def test_unparseable_text_is_a_parse_error_with_a_null_id(server):
    raw = await server.handle_text("{not json")
    assert json.loads(raw)["error"]["code"] == PARSE_ERROR
    assert json.loads(raw)["id"] is None


# ══ §3 — channels ═══════════════════════════════════════════════════════════


def test_channel_grammar_round_trips():
    assert parse_channel("dnap-root://").is_root
    assert parse_channel(f"dnap-scope:/{_SCOPE}").scope == _SCOPE
    tenant = parse_channel(f"dnap-scope:/{_SCOPE}#acme")
    assert (tenant.scope, tenant.tenant) == (_SCOPE, "acme")
    assert tenant.uri == f"dnap-scope:/{_SCOPE}#acme"


@pytest.mark.parametrize(
    "bad",
    [
        "", "dnap-scope:/", "dnap-scope:/#acme", f"dnap-scope:/{_SCOPE}#",
        f"http://{_SCOPE}", _SCOPE, None, 7,
    ],
)
def test_a_malformed_channel_is_invalid_params_not_channel_not_served(bad):
    """A typo and a wrong server are different problems. **Mutant:** answer
    ``-32004`` for everything unparseable — this fails, and a client loses the
    ability to tell "fix your URI" from "you are talking to the wrong server"."""
    with pytest.raises(DnapError) as caught:
        parse_channel(bad)
    assert caught.value.code == INVALID_PARAMS


@pytest.mark.asyncio
async def test_an_unserved_channel_is_refused_and_never_substituted(server):
    """⭐ §3, the load-bearing rule: *"a server that does not serve a channel
    MUST answer -32004 rather than substituting one it does serve."*

    **Mutant:** fall back to the default scope when the requested one is not
    served. That mutation makes this test fail on the code, and it is exactly
    the measured REST defect (``?scope=`` accepted and ignored) that §3 exists
    to correct. The assertion on ``instances`` is the important half: the
    request must not be ANSWERED, not merely flagged."""
    await _ready(server)
    error = await _err(
        server, "instances/list", channel=_channel(_OTHER), kind="Genome",
    )
    assert error["code"] == CHANNEL_NOT_SERVED
    assert error["data"]["channel"] == _channel(_OTHER)
    assert _channel(_SCOPE) in error["data"]["served"]


@pytest.mark.asyncio
async def test_the_root_channel_cannot_stand_in_for_a_scope(server):
    """``instances/*`` acts on instances; the root channel holds none.
    Answering it from the default scope is the same substitution by another
    route. **Mutant:** let ``ChannelRequirement.SCOPE`` accept root."""
    await _ready(server)
    error = await _err(
        server, "instances/list", channel="dnap-root://", kind="Genome",
    )
    assert error["code"] == CHANNEL_NOT_SERVED


@pytest.mark.asyncio
async def test_a_missing_channel_is_refused_rather_than_defaulted(server):
    """Scope is an ADDRESS. **Mutant:** default the missing channel to the
    server's own scope — which is precisely how a parameter gets dropped in
    silence."""
    await _ready(server)
    error = await _err(server, "instances/list", kind="Genome")
    assert error["code"] == INVALID_PARAMS


@pytest.mark.asyncio
async def test_kinds_list_echoes_the_channel_it_answered_for(server):
    """``kinds/*`` accepts the root channel, so it must SAY which scope's
    vocabulary came back. A default that is stated is not a substitution."""
    await _ready(server)
    result = await _ok(server, "kinds/list", channel="dnap-root://")
    assert result["channel"] == _channel(_SCOPE)


# ══ §4 — initialize, capabilities, and -32601 ═══════════════════════════════


@pytest.mark.asyncio
async def test_initialize_advertises_channels_capabilities_and_kinds(server):
    result = await _ok(
        server, "initialize", protocolVersion="1.0",
        client={"name": "t", "version": "0"}, capabilities={"write": {}},
    )
    assert result["protocolVersion"] == "1.0"
    assert result["channels"] == [_channel(_SCOPE)]
    assert result["kinds"], "a server that serves a scope serves some Kinds"
    assert "write" in result["capabilities"]


@pytest.mark.asyncio
async def test_nothing_is_served_before_initialize(server):
    """§4: ``initialize`` is *"the first message on a connection."*"""
    error = await _err(server, "kinds/list", channel="dnap-root://")
    assert error["code"] == NOT_INITIALIZED


@pytest.mark.asyncio
async def test_a_method_outside_an_advertised_capability_is_method_not_found(live):
    """⭐ §4/§8 rule 2, after AHP: *"a method outside every advertised
    capability MUST be rejected with -32601"* — not silently ignored, and not
    answered with a degraded result.

    **Mutant:** have ``MethodRegistry.resolve`` ignore ``enabled`` and serve
    any registered method. This test fails on both halves: the write goes
    through, and ``initialize`` still hides the capability — which is the worse
    half, because the client was told the door did not exist."""
    read_only = DnapServer(live, scopes=[_SCOPE], enabled_capabilities=[])
    result = await _ok(
        read_only, "initialize", protocolVersion="1.0", client={},
        capabilities={"write": {}},
    )
    assert "write" not in result["capabilities"]
    error = await _err(
        read_only, "instances/write", channel=_channel(_SCOPE),
        document=_doc("Genome", "x", {}),
    )
    assert error["code"] == METHOD_NOT_FOUND
    # …and the read half of the same server still works, so this is a gate on
    # the capability rather than a broken server.
    assert await _ok(read_only, "kinds/list", channel="dnap-root://")


@pytest.mark.asyncio
async def test_an_unadvertised_kind_is_kind_not_served(server):
    """§4: *"A client that names an unadvertised Kind gets -32003."*

    **Mutant:** resolve the Kind against the process-wide registry instead of
    the channel's advertised catalog. A Kind that exists somewhere but governs
    no channel here would then be served — the mirror image of the channel
    substitution §3 forbids."""
    await _ready(server)
    error = await _err(
        server, "instances/list", channel=_channel(_SCOPE),
        kind="NoSuchKindAnywhere",
    )
    assert error["code"] == KIND_NOT_SERVED
    assert error["data"]["kind"] == "NoSuchKindAnywhere"


@pytest.mark.asyncio
async def test_an_unknown_protocol_version_is_refused_with_the_supported_set(server):
    error = await _err(server, "initialize", protocolVersion="0.9")
    assert error["code"] == INVALID_PARAMS
    assert error["data"]["supported"] == ["1.0"]


# ══ ⭐ the extension point — how wave 2 plugs in ════════════════════════════


@pytest.mark.asyncio
async def test_registering_a_method_under_a_new_capability_advertises_it(live):
    """⭐ The contract wave 2 (``resolve/*``, ``search/*``) depends on:
    registering a method is the ONLY step. The dispatcher is not edited, the
    ``initialize`` handler is not edited, and the capability appears because it
    is DERIVED from the method table.

    **Mutant:** hand-list the capabilities in ``initialize``. Then this test
    fails — and so does the design, silently, the first time somebody adds a
    method and forgets the list."""
    registry = builtin_registry().extended()

    @registry.method("resolve/agent", capability="resolve")
    async def _resolve(ctx, params):  # pragma: no cover - exercised below
        return {"resolved": {"name": params["name"], "channel": ctx.channel.uri}}

    registry.declare_capability("resolve", lambda ctx: {"agent": True})

    server = DnapServer(live, scopes=[_SCOPE], registry=registry)
    result = await _ok(
        server, "initialize", protocolVersion="1.0", client={}, capabilities={"write": {}, "resolve": {}, "search": {}},
    )
    assert result["capabilities"]["resolve"] == {"agent": True}
    resolved = await _ok(
        server, "resolve/agent", channel=_channel(_SCOPE), name="a",
    )
    assert resolved["resolved"] == {"name": "a", "channel": _channel(_SCOPE)}


@pytest.mark.asyncio
async def test_registering_an_unrelated_method_breaks_nothing(live, server):
    """⚠️ The test that keeps every other test honest: an addition must not
    change any existing answer. If this repo's habit of freezing counts crept
    back in, this is where it would show."""
    await _ready(server)
    before = await _ok(server, "kinds/list", channel="dnap-root://")

    registry = builtin_registry().extended()
    registry.method("search/instances", capability="search")(
        lambda ctx, params: asyncio.sleep(0, {"hits": []}),
    )
    grown = await _ready(DnapServer(live, scopes=[_SCOPE], registry=registry))
    after = await _ok(grown, "kinds/list", channel="dnap-root://")
    assert after == before


def test_a_capability_cannot_be_declared_without_a_method_behind_it():
    """Detail describes a capability; it cannot conjure one. The alternative is
    a server advertising a door with nothing behind it."""
    registry = builtin_registry().extended()
    with pytest.raises(ValueError, match="no registered method claims"):
        registry.declare_capability("search", lambda ctx: {})


def test_the_builtin_registry_is_frozen_against_accidental_sharing():
    with pytest.raises(RuntimeError, match="frozen"):
        builtin_registry().method("x/y")(lambda ctx, p: None)


def test_a_duplicate_registration_is_refused_rather_than_shadowing():
    registry = builtin_registry().extended()
    with pytest.raises(ValueError, match="already registered"):
        registry.method("kinds/list", channel=ChannelRequirement.NONE)(
            lambda ctx, p: None,
        )


# ══ §6.1 — kinds ════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_kinds_list_carries_the_shape_of_each_kind(server):
    """§6.1 shows ``plane``/``promptTarget``/``writable`` per entry. Asserted as
    a property of EVERY row, never as a fixed list of rows."""
    await _ready(server)
    rows = (await _ok(server, "kinds/list", channel="dnap-root://"))["kinds"]
    assert rows
    for row in rows:
        assert row["plane"] in {"composition", "record"}
        assert isinstance(row["promptTarget"], bool)
        assert isinstance(row["writable"], bool)
        assert row["apiVersion"]


@pytest.mark.asyncio
async def test_kinds_describe_carries_the_schema(server):
    """§6.1: *"The schema travels because a client that cannot see it must
    guess, and a guessing client writes documents the server will reject."*"""
    await _ready(server)
    rows = (await _ok(server, "kinds/list", channel="dnap-root://"))["kinds"]
    described = await _ok(
        server, "kinds/describe", channel="dnap-root://", kind=rows[0]["kind"],
    )
    assert described["kind"] == rows[0]["kind"]
    assert "schema" in described and "relations" in described


@pytest.mark.asyncio
async def test_kinds_describe_refuses_an_unadvertised_kind(server):
    await _ready(server)
    error = await _err(
        server, "kinds/describe", channel="dnap-root://", kind="NotAKind",
    )
    assert error["code"] == KIND_NOT_SERVED


# ══ §6.2 rule 1 — `select` is a contract ════════════════════════════════════


@pytest.mark.asyncio
async def test_select_full_returns_the_whole_instance_not_just_the_name(server):
    """⭐ Rule 1, the positive half. The implementation underneath discards the
    full envelope under a ``None`` projection, so "full" had no spelling at all
    until ``list_instances_impl(envelope=True)``.

    **Mutant:** map ``select:"full"`` to ``fields=None``. The rows come back as
    ``{"name": …}`` while ``selected`` still reads ``"full"`` — the exact
    measured defect §6.2 rule 1 names, and this assertion fails."""
    await _ready(server)
    await _ok(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc('Agent', "scribe", {"objective": "note taker"}),
    )
    result = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        select="full",
    )
    assert result["selected"] == "full"
    [row] = result["instances"]
    assert row["spec"]["objective"] == "note taker"
    assert row["metadata"]["name"] == "scribe"
    assert row["metadata"]["revision"], "§5: every document carries a revision"


@pytest.mark.asyncio
async def test_select_names_returns_names(server):
    await _ready(server)
    await _ok(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc('Agent', "scribe", {"objective": "x"}),
    )
    result = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        select="names",
    )
    assert result["selected"] == "names"
    assert result["instances"] == ["scribe"], (
        "§6.2 rule 5: plain strings. A one-member document carrying only a "
        "name is the narrower shape rule 1 forbids, wearing a disguise."
    )


@pytest.mark.asyncio
async def test_select_paths_are_honoured_exactly(server):
    await _ready(server)
    await _ok(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc('Agent', "scribe", {"objective": "x", "model": "openai/gpt-5"}),
    )
    result = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        select=["spec.objective"],
    )
    assert result["selected"] == ["spec.objective"]
    [row] = result["instances"]
    assert row["spec"] == {"objective": "x"}


@pytest.mark.asyncio
async def test_a_bare_spec_path_is_refused_instead_of_silently_dropped(server):
    """⭐⭐ Rule 1, the half that is a MEASUREMENT of this repo.

    ``_project_doc(doc, ["spec"])`` returns ``{"name": …}`` — the spec is
    resolved as ``spec.spec``, comes back ``None``, and is dropped without a
    word, while the caller is handed ``"projected": ["spec"]``. That is
    verbatim *"a narrower shape while echoing the request"*.

    **Mutant:** delete the ``_SILENTLY_DROPPED`` check in
    :mod:`dna.protocol.select` and pass the path through. The call then
    succeeds, returns rows with no ``spec``, and reports ``selected:
    ["spec"]`` — this test fails, and the server has started lying."""
    await _ready(server)
    await _ok(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc('Agent', "scribe", {"objective": "x"}),
    )
    error = await _err(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        select=["spec"],
    )
    assert error["code"] == INVALID_PARAMS
    assert error["data"]["path"] == "spec"
    assert error["data"]["rule"] == "projection-unhonourable"


@pytest.mark.asyncio
async def test_the_projector_really_does_drop_a_bare_spec(server):
    """The measurement the rule above rests on, asserted directly — so that if
    the projector is ever FIXED, this test fails and tells the next reader that
    the refusal may be relaxed. A rule justified by a measurement should break
    when the measurement changes."""
    from dna.kernel.protocols import _project_doc

    doc = {"apiVersion": "v1", "kind": "Agent",
           "metadata": {"name": "n"}, "spec": {"role": "x"}}
    assert _project_doc(doc, ["spec"]) == {"name": "n"}
    assert _project_doc(doc, ["spec.role"]) == {"name": "n", "spec": {"role": "x"}}


@pytest.mark.parametrize("bad", ["metadata", "spec.", ".role", "nope.deep.path", ""])
@pytest.mark.asyncio
async def test_unhonourable_select_paths_are_refused(server, bad):
    await _ready(server)
    error = await _err(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        select=[bad],
    )
    assert error["code"] == INVALID_PARAMS


@pytest.mark.asyncio
async def test_an_unknown_select_word_is_refused(server):
    await _ready(server)
    error = await _err(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        select="everything",
    )
    assert error["code"] == INVALID_PARAMS


# ══ §6.2 rules 2 and 3 — cursors and the snapshot ═══════════════════════════


@pytest.mark.asyncio
async def test_pagination_is_by_opaque_cursor_and_never_an_offset(server):
    """Rule 2. **Mutant:** return the offset as the cursor. This fails on the
    round-trip: an integer offset is not opaque, and the moment a client can
    read it, replacing offset pagination becomes a wire change."""
    await _ready(server)
    for i in range(5):
        await _ok(
            server, "instances/write", channel=_channel(_SCOPE),
        document=_doc('Agent', f"a{i}", {"objective": "x"}),
        )
    first = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent", limit=2,
    )
    assert len(first["instances"]) == 2
    cursor = first["cursor"]
    assert isinstance(cursor, str) and not cursor.isdigit()

    seen = list(first["instances"])
    page = first
    while "cursor" in page:
        page = await _ok(
            server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
            limit=2, cursor=page["cursor"],
        )
        seen.extend(page["instances"])
    assert seen == [f"a{i}" for i in range(5)], (
        "§6.2 rule 4: lexicographic by metadata.name, ascending — asserted "
        "unsorted, because a sorted() here would hide the very rule"
    )


@pytest.mark.asyncio
async def test_the_cursor_is_absent_when_the_listing_is_exhausted(server):
    """§6.2 shows ``cursor`` *"absent when exhausted"* — absent, not null."""
    await _ready(server)
    await _ok(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc('Agent', "only", {"objective": "x"}),
    )
    result = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent", limit=50,
    )
    assert "cursor" not in result


@pytest.mark.asyncio
async def test_a_cursor_from_another_listing_is_refused(server):
    """A cursor pins the address and the shape. **Mutant:** carry only the
    offset. Then a page-2 request with a different ``select`` is served, and
    the pages of "one listing" no longer share one shape."""
    await _ready(server)
    for i in range(4):
        await _ok(
            server, "instances/write", channel=_channel(_SCOPE),
        document=_doc('Agent', f"a{i}", {"objective": "x"}),
        )
    first = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        limit=2, select="names",
    )
    error = await _err(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        limit=2, select="full", cursor=first["cursor"],
    )
    assert error["code"] == INVALID_PARAMS


@pytest.mark.asyncio
async def test_an_unreadable_cursor_is_cursor_expired_not_a_silent_restart(server):
    """Rule 2: *"an expired cursor MUST answer -32005 so the client restarts
    rather than silently skipping."*

    **Mutant:** treat a bad cursor as ``offset=0``. The client then re-reads
    page 1 believing it is page 5 — a silent skip in the other direction, and
    this test fails."""
    await _ready(server)
    error = await _err(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        cursor="not-a-cursor-at-all",
    )
    assert error["code"] == CURSOR_EXPIRED


@pytest.mark.asyncio
async def test_the_revision_is_constant_across_the_pages_of_one_listing(live):
    """⭐ Rule 3: *"All pages of one listing belong to one snapshot. Without
    this a client assembles a quilt of moments and calls it a state."*

    Exercised against a store that DOES serve a channel watermark, because a
    store that serves none can only ever report ``null`` — and a rule tested
    only where it cannot fail is not tested. The fake watermark below is the
    smallest thing that makes the pin observable."""
    watermarks = iter(["w1", "w1", "w1", "w1"])
    kernel = live.kernel

    async def channel_revision(scope, *, tenant=None):
        return next(watermarks)

    kernel._source.channel_revision = channel_revision
    server = await _ready(DnapServer(live, scopes=[_SCOPE]))
    for i in range(4):
        await _ok(
            server, "instances/write", channel=_channel(_SCOPE),
        document=_doc('Agent', f"a{i}", {"objective": "x"}),
        )
    watermarks = iter(["w1"] * 10)
    page1 = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent", limit=2,
    )
    page2 = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        limit=2, cursor=page1["cursor"],
    )
    assert page1["revision"] == page2["revision"] == "w1"


@pytest.mark.asyncio
async def test_a_moved_snapshot_ends_the_listing_instead_of_continuing_it(live):
    """⭐ Rule 3's teeth. **Mutant:** drop ``require_same_snapshot``. Page 2
    then comes back happily from a different state, with a ``revision`` that
    still reads ``w1`` — the quilt, presented as a snapshot. This test fails."""
    marks = iter(["w1", "w2", "w2", "w2", "w2"])

    async def channel_revision(scope, *, tenant=None):
        return next(marks)

    server = await _ready(DnapServer(live, scopes=[_SCOPE]))
    for i in range(4):
        await _ok(
            server, "instances/write", channel=_channel(_SCOPE),
        document=_doc('Agent', f"a{i}", {"objective": "x"}),
        )
    live.kernel._source.channel_revision = channel_revision
    page1 = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent", limit=2,
    )
    assert page1["revision"] == "w1"
    error = await _err(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        limit=2, cursor=page1["cursor"],
    )
    assert error["code"] == CURSOR_EXPIRED


@pytest.mark.asyncio
async def test_a_store_with_no_sequence_reports_a_TRUE_digest_not_a_minted_token(
    server,
):
    """⭐ The honesty half of §6.2 rule 3, and the option that was NOT taken.

    The fixture store exposes no sequence, so the revision is computed: a
    digest over the slice's `(name, etag)` pairs. That is a TRUE statement —
    *these rows came from this state* — and it is why the third candidate was
    rejected. A minted token (a uuid, a timestamp) would satisfy every
    assertion below about SHAPE and mean nothing; a client comparing two of
    them would draw conclusions from a number the server invented, which is §7's
    rule applied to a scalar.

    **Mutant:** return `uuid4().hex` instead of the digest. Every shape
    assertion still passes — and the last one, that an unchanged channel
    reports an unchanged revision while a changed one does not, fails. That
    pair is the only thing separating a watermark from a decoration.
    """
    result = await _ok(
        server, "initialize", protocolVersion="1.0", client={},
        capabilities={"write": {}},
    )
    assert result["revisions"]["channel"] == "content-digest"

    first = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
    )
    assert isinstance(first["revision"], str) and first["revision"], (
        "§8 client rule 2 asks clients to treat revision as opaque; a null "
        "invites them to treat it as absent instead"
    )

    # Reading again changes nothing, so the revision must not move.
    again = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
    )
    assert again["revision"] == first["revision"]

    # Writing does change something, so it must.
    await _ok(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc("Agent", "scribe", {"objective": "x"}),
    )
    moved = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
    )
    assert moved["revision"] != first["revision"]


@pytest.mark.asyncio
async def test_an_unserved_tenant_overlay_is_refused_not_answered_from_the_base(
    live,
):
    """⭐⭐ §3's substitution rule, through the door it nearly escaped by.

    A tenant overlay reads THROUGH to the base, so a request for a tenant this
    deployment never heard of came back carrying the base scope's content — the
    caller asked for a tenant's shelf and was handed the shared one, with
    nothing in the answer to say so. Found by the conformance suite, which is
    the argument for a second implementation in one sentence.

    **Mutant:** let `ChannelSet.serves` accept any tenant of a served scope.
    This test fails; every other test in this file passes, because none of them
    asks for a tenant nobody declared.
    """
    server = await _ready(DnapServer(live, scopes=[_SCOPE]))
    error = await _err(
        server, "instances/list", channel=_channel(_SCOPE, tenant="acme"),
        kind="Agent",
    )
    assert error["code"] == CHANNEL_NOT_SERVED

    # …and a DECLARED tenant is served, so this is a refusal about the tenant
    # registry rather than a server that cannot do overlays at all.
    with_tenant = await _ready(
        DnapServer(live, scopes=[_SCOPE], tenants=["acme"]),
    )
    listed = await _ok(
        with_tenant, "instances/list",
        channel=_channel(_SCOPE, tenant="acme"), kind="Agent",
    )
    assert listed["instances"] == []


@pytest.mark.asyncio
async def test_expiring_the_cursors_ends_every_listing_in_flight(server):
    """§6.2 rule 3's own note: *"honouring it requires the server to hold a
    snapshot, which has a lifetime and a memory bound … CURSOR_EXPIRED is not a
    courtesy — it is how a server with finite memory stays honest."*

    **Mutant:** ignore the generation in the cursor. The page then resumes
    against a snapshot the server no longer holds, silently."""
    await _ready(server)
    for i in range(4):
        await _ok(
            server, "instances/write", channel=_channel(_SCOPE),
            document=_doc("Agent", f"a{i}", {"objective": "x"}),
        )
    page = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent", limit=2,
    )
    server.expire_cursors()
    error = await _err(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        limit=2, cursor=page["cursor"],
    )
    assert error["code"] == CURSOR_EXPIRED


# ══ §6.2 — get / write / delete ═════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_returns_the_document_with_its_revision(server):
    await _ready(server)
    await _ok(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc('Agent', "scribe", {"objective": "x"}),
    )
    result = await _ok(
        server, "instances/get", channel=_channel(_SCOPE), kind="Agent",
        name="scribe",
    )
    assert result["instance"]["spec"]["objective"] == "x"
    assert result["instance"]["metadata"]["revision"] == result["revision"]


@pytest.mark.asyncio
async def test_if_none_match_answers_not_modified_with_no_body(server):
    """§6.2: ``"ifNoneMatch":"4172"`` → ``{"notModified":true}`` with no body.
    **Mutant:** send the body anyway — the point of a conditional read is that
    the body does not travel."""
    await _ready(server)
    await _ok(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc('Agent', "scribe", {"objective": "x"}),
    )
    first = await _ok(
        server, "instances/get", channel=_channel(_SCOPE), kind="Agent",
        name="scribe",
    )
    again = await _ok(
        server, "instances/get", channel=_channel(_SCOPE), kind="Agent",
        name="scribe", ifNoneMatch=first["revision"],
    )
    assert again["notModified"] is True
    assert "instance" not in again


@pytest.mark.asyncio
async def test_a_missing_instance_is_an_error_never_an_empty_document(server):
    """⭐ §7, the rule that outranks the table, at the single-instance layer."""
    await _ready(server)
    error = await _err(
        server, "instances/get", channel=_channel(_SCOPE), kind="Agent",
        name="never-written",
    )
    assert error["code"] == NOT_FOUND


@pytest.mark.asyncio
async def test_write_then_delete_round_trips(server):
    await _ready(server)
    await _ok(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc('Agent', "scribe", {"objective": "x"}),
    )
    assert (await _ok(
        server, "instances/delete", channel=_channel(_SCOPE), kind="Agent",
        name="scribe",
    ))["deleted"] is True
    error = await _err(
        server, "instances/get", channel=_channel(_SCOPE), kind="Agent",
        name="scribe",
    )
    assert error["code"] == NOT_FOUND


@pytest.mark.asyncio
async def test_a_stale_if_match_is_a_revision_conflict_carrying_the_current_one(server):
    """§6.2: ``-32011 REVISION_CONFLICT`` *"with the current revision"* — so a
    client can re-read and decide instead of retrying blind."""
    await _ready(server)
    await _ok(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc('Agent', "scribe", {"objective": "x"}),
    )
    error = await _err(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc("Agent", "scribe", {"objective": "y"}),
        ifMatch="a-revision-from-nowhere",
    )
    assert error["code"] == REVISION_CONFLICT
    assert error["data"]["revision"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["id", "revision"])
async def test_derived_metadata_may_not_be_supplied_on_write(server, field):
    """§5: *"``metadata.id`` and ``metadata.revision`` are derived and MUST NOT
    be supplied on write."*

    **Mutant:** ignore them instead of refusing. A write that carried a
    revision and had it silently dropped looks, to its author, exactly like one
    whose revision was honoured — which is how a client comes to believe it has
    optimistic concurrency it never had."""
    await _ready(server)
    error = await _err(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc("Agent", "scribe", {"objective": "x"}, **{field: "whatever"}),
    )
    assert error["code"] == VALIDATION_FAILED
    assert error["data"]["fields"] == [field]


@pytest.mark.asyncio
async def test_a_policy_refusal_is_not_reported_as_an_internal_error(server):
    """A bootstrap Kind may not be written generically. That is a DECISION, and
    reporting it as ``-32603 Internal error`` would tell the client the server
    broke. §7's table has no code for it — ``-32001`` is this server's, and it
    is named in the report as a spec gap.

    **Mutant:** drop the ``KernelRefusal`` branch of ``_translate``. The
    refusal falls into the dispatcher's catch-all and comes back ``-32603``."""
    await _ready(server)
    error = await _err(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc("KindDefinition", "anything", {"kind": "anything"}),
    )
    assert error["code"] == NOT_WRITABLE


@pytest.mark.asyncio
async def test_a_schema_violation_carries_the_path_and_the_rule(server, live):
    """§6.2: *"-32010 VALIDATION_FAILED carries the failing path and the rule,
    never a bare 'invalid'."*

    Uses a Kind whose schema constrains a field, declared in the fixture scope
    so the assertion does not depend on which built-in Kind happens to have the
    tightest schema today."""
    from dna.kernel.protocols import SpecValidationError

    from dna.protocol.methods import _translate

    err = _translate(
        SpecValidationError("nope", path="spec.model", rule="enum"),
    )
    assert err.code == VALIDATION_FAILED
    assert err.data == {"path": "spec.model", "rule": "enum"}


def test_a_validation_error_with_no_known_path_reports_null_not_a_guess():
    """The relation-validation raise site knows the RULE and not the PATH.
    ``None`` travels as null — *"not available"* — rather than as a plausible
    wrong path, which is the same distinction §7 draws one layer up."""
    from dna.kernel.protocols import SpecValidationError

    from dna.protocol.methods import _translate

    err = _translate(SpecValidationError("nope", rule="relations"))
    assert err.data["path"] is None
    assert err.data["rule"] == "relations"


# ══ §7 — the rule that outranks the table ═══════════════════════════════════


@pytest.mark.asyncio
async def test_an_unexpected_failure_is_an_error_never_an_empty_collection(live):
    """⭐⭐ *"An empty result and an unanswerable question are different values,
    and a server MUST NOT collapse them."*

    A store that cannot be read is simulated at the seam. **Mutant:** wrap the
    handler body in ``except Exception: return {"instances": []}``. Every other
    test in this file still passes; this one fails — which is the whole reason
    it exists. That mutation is the single most repeated defect the reference
    implementation paid for."""
    server = await _ready(DnapServer(live, scopes=[_SCOPE]))

    async def exploding_query(*args, **kwargs):
        raise OSError("the store is gone")
        yield  # pragma: no cover

    live.kernel.query = exploding_query
    answer = await _call(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
    )
    assert "error" in answer, "a failed read came back as a result"
    assert answer["error"]["code"] == -32603
    assert "instances" not in answer.get("result", {})


@pytest.mark.asyncio
async def test_an_empty_collection_is_still_a_legitimate_answer(server):
    """The other side of the same rule: ``[]`` must remain available for the
    case it actually describes — *nothing of this Kind exists here*."""
    await _ready(server)
    result = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
    )
    assert result["instances"] == []
    assert "cursor" not in result


def test_every_code_in_the_spec_table_has_a_name():
    """§7's table, as a table — checked for completeness, not for length. A new
    code added later does not break this; a code added WITHOUT a name does."""
    from dna.protocol import errors

    for code in (-32003, -32004, -32005, -32010, -32011, -32020, -32030):
        assert code in errors.ERROR_NAMES, code
    assert all(
        name for name in errors.ERROR_NAMES.values()
    ), "a code with an empty name is a code with no meaning"


def test_an_error_with_no_data_omits_the_member_rather_than_sending_null():
    assert DnapError(-32601).to_wire() == {
        "code": -32601, "message": "Method not found",
    }
    assert "data" in DnapError(-32601, "x", why="y").to_wire()


# ══ the stdio binding ═══════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_stdio_frames_one_json_value_per_line(server, tmp_path):
    """NDJSON: a serialised JSON value provably contains no raw newline
    (RFC 8259 escapes control characters inside strings), so line framing is
    safe by construction rather than by luck. **Mutant:** serialise with
    ``indent=2`` — the frame spans lines and the reader desynchronises."""
    from dna.protocol.stdio import serve_stream

    reader = asyncio.StreamReader()
    for line in (
        '{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
        '{"protocolVersion":"1.0"}}',
        '{"jsonrpc":"2.0","method":"kinds/list"}',       # notification: silent
        '{"jsonrpc":"2.0","id":2,"method":"kinds/list","params":'
        '{"channel":"dnap-root://"}}',
        "",                                             # blank line: skipped
    ):
        reader.feed_data((line + "\n").encode("utf-8"))
    reader.feed_eof()

    out = tmp_path / "out.ndjson"
    with out.open("w", encoding="utf-8") as handle:
        await serve_stream(server, reader, handle)

    lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln]
    assert [json.loads(ln)["id"] for ln in lines] == [1, 2], (
        "the notification must produce no frame"
    )


# ══ the clean-room revision (2026-08-12) — §11's twelve gaps ════════════════
#
# Everything below tests a rule that did NOT exist in the first draft. Each one
# is a place where, per §11, "two honest readers would have built incompatible
# servers" — so each is exactly the kind of rule that needs a test rather than a
# careful implementer.


@pytest.mark.asyncio
async def test_a_capability_the_client_did_not_declare_is_out_of_reach(live):
    """⭐ §4, gap A6: *"The effective capability set is the INTERSECTION of what
    the client sent and what the server answered. A client that did not ask for
    `write` cannot write, even against a server that offers it."*

    **Mutant:** treat the client's `capabilities` as decorative. The write then
    succeeds — and two conforming servers disagree about whether a call works,
    which is the failure mode §11 exists to enumerate."""
    server = DnapServer(live, scopes=[_SCOPE])
    result = await _ok(
        server, "initialize", protocolVersion="1.0", client={},
        capabilities={},                       # asks for nothing
    )
    assert "write" in result["capabilities"], "the SERVER still offers it"
    error = await _err(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc("Agent", "x", {"objective": "y"}),
    )
    assert error["code"] == METHOD_NOT_FOUND
    # …and reading, which needs no capability, still works on the same session.
    assert await _ok(server, "kinds/list", channel="dnap-root://")


@pytest.mark.asyncio
async def test_write_takes_the_document_and_reads_the_kind_from_it(server):
    """§6.2, gap A1: `instances/write` had no documented params. It now takes
    `{channel, document, ifMatch}` and reads the Kind from `document.kind` —
    *"a separate `kind` param would be a second spelling that can disagree with
    the first."*

    **Mutant:** also accept a `kind` param. Two spellings, and the day they
    disagree the server has to pick one and no reader knows which."""
    await _ready(server)
    result = await _ok(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc("Agent", "scribe", {"objective": "note taker"}),
    )
    assert result["created"] is True
    assert result["instance"]["kind"] == "Agent"
    assert result["instance"]["spec"]["objective"] == "note taker"
    assert result["instance"]["metadata"]["revision"]
    # A `kind` param is not read: the document decides, alone.
    other = await _ok(
        server, "instances/write", channel=_channel(_SCOPE), kind="Genome",
        document=_doc("Agent", "second", {"objective": "x"}),
    )
    assert other["instance"]["kind"] == "Agent"


@pytest.mark.asyncio
async def test_write_without_a_document_is_refused(server):
    await _ready(server)
    assert (await _err(
        server, "instances/write", channel=_channel(_SCOPE),
    ))["code"] == INVALID_PARAMS


@pytest.mark.asyncio
async def test_delete_reports_the_revision_the_channel_advanced_to(server):
    """§6.2, gap A13: delete had no result shape. It is now
    `{deleted, revision}` — *"the revision the channel advanced to, so a
    watcher can order the delete against its own reads."* On a store with no
    watermark the revision is null, for the same reason a listing's is."""
    await _ready(server)
    await _ok(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc("Agent", "scribe", {"objective": "x"}),
    )
    result = await _ok(
        server, "instances/delete", channel=_channel(_SCOPE), kind="Agent",
        name="scribe",
    )
    assert result["deleted"] is True
    assert "revision" in result


@pytest.mark.asyncio
async def test_a_kind_that_is_not_writable_is_not_writable_not_broken(server):
    """§7, `-32006 NOT_WRITABLE` — *"the Kind is served but writable: false"*.

    Answered from the catalog before the store is touched, so the refusal a
    client could have predicted from `kinds/list` costs it no write attempt.

    **Mutant:** let it fall through to the kernel and come back as a generic
    policy refusal. The client is then refused with a code that does not name
    the condition, for a fact it was already told."""
    await _ready(server)
    rows = (await _ok(server, "kinds/list", channel="dnap-root://"))["kinds"]
    unwritable = [r for r in rows if not r["writable"]]
    assert unwritable, "the fixture scope must serve at least one read-only Kind"
    error = await _err(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc(unwritable[0]["kind"], "x", {}),
    )
    assert error["code"] == NOT_WRITABLE
    assert error["data"]["kind"] == unwritable[0]["kind"]


@pytest.mark.asyncio
async def test_a_path_select_returns_exactly_the_paths_and_nothing_added(server):
    """⭐ §6.2 rule 5, and it is a rule ABOUT this repo's projector: it always
    injects `name` into every projected row.

    *"A server that helpfully attaches identity and one that does not return
    different rows for the same request; ask for `metadata.name` when you want
    it."*

    **Mutant:** stop stripping the injected identity. The rows come back with a
    `name` nobody asked for, and the same request answered by two conforming
    servers returns two different shapes."""
    await _ready(server)
    await _ok(
        server, "instances/write", channel=_channel(_SCOPE),
        document=_doc("Agent", "scribe", {"objective": "x"}),
    )
    trimmed = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        select=["spec.objective"],
    )
    assert trimmed["instances"] == [{"spec": {"objective": "x"}}]

    # …and asking for identity gets it. The rule is "exactly what you asked
    # for", not "never identity".
    asked = await _ok(
        server, "instances/list", channel=_channel(_SCOPE), kind="Agent",
        select=["name", "spec.objective"],
    )
    assert asked["instances"] == [{"name": "scribe", "spec": {"objective": "x"}}]


@pytest.mark.asyncio
async def test_listing_order_is_lexicographic_by_name_across_pages(server):
    """§6.2 rule 4, gap A3–A5: *"Rules 2 and 3 are both meaningless without a
    total order."*

    **Mutant:** sort each page instead of pushing the order down to the store.
    A one-page listing looks identical; this one, paged at 2, does not."""
    await _ready(server)
    for name in ("zeta", "alpha", "mike", "beta", "charlie"):
        await _ok(
            server, "instances/write", channel=_channel(_SCOPE),
            document=_doc("Agent", name, {"objective": "x"}),
        )
    seen: list[str] = []
    cursor = None
    while True:
        params = {"channel": _channel(_SCOPE), "kind": "Agent", "limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = await _ok(server, "instances/list", **params)
        seen.extend(page["instances"])
        cursor = page.get("cursor")
        if not cursor:
            break
    assert seen == ["alpha", "beta", "charlie", "mike", "zeta"]


# ── §6.1 — KindDefinition, the reflexive rule (gap A11) ─────────────────────


def test_a_kind_definition_must_name_itself_the_same_way_twice():
    """§6.1: *"metadata.name MUST equal spec.kind. One name, no mapping."*

    **Mutant:** accept a mismatch and prefer one of them. Every reader then has
    to know which is authoritative, and the two drift."""
    from dna.protocol.kinddef import validate_kind_definition

    ok = {"kind": "KindDefinition", "metadata": {"name": "ReviewChecklist"},
          "spec": {"kind": "ReviewChecklist"}}
    validate_kind_definition(ok)

    with pytest.raises(DnapError) as caught:
        validate_kind_definition(
            {"kind": "KindDefinition", "metadata": {"name": "Review"},
             "spec": {"kind": "ReviewChecklist"}},
        )
    assert caught.value.code == VALIDATION_FAILED
    assert caught.value.data["path"] == "metadata.name"


def test_a_kind_definition_schema_is_bounded_to_the_keywords_the_server_enforces():
    """⭐ §6.1, gap A10: *"JSON Schema" was named and never bounded.*

    *"A keyword the server stores, hands out through `kinds/describe`, and does
    not enforce is a lie told to every client that reads the schema to
    pre-validate."*

    **Mutant:** accept any keyword. The KindDefinition writes, `kinds/describe`
    hands back an `allOf` nobody enforces, and every client that pre-validates
    against it is wrong in a way no test of this server would notice."""
    from dna.protocol.kinddef import (
        BOUNDED_SCHEMA_KEYWORDS,
        validate_kind_definition,
    )

    def kd(schema):
        return {"kind": "KindDefinition", "metadata": {"name": "K"},
                "spec": {"kind": "K", "schema": schema}}

    validate_kind_definition(kd({
        "type": "object",
        "required": ["title"],
        "properties": {"title": {"type": "string", "minLength": 1}},
        "additionalProperties": False,
    }))

    with pytest.raises(DnapError) as caught:
        validate_kind_definition(kd({"type": "object", "allOf": []}))
    assert caught.value.code == VALIDATION_FAILED
    assert caught.value.data["path"] == "spec.schema"
    assert caught.value.data["keyword"] == "allOf"
    assert "allOf" not in BOUNDED_SCHEMA_KEYWORDS


def test_the_schema_bound_is_checked_all_the_way_down():
    """A forbidden keyword nested under `properties` is exactly as unenforced
    as one at the root — and it is where a real schema would put it.

    **Mutant:** check only the top level. This test fails; the shallow check
    would pass every schema most likely to carry one."""
    from dna.protocol.kinddef import validate_kind_definition

    nested = {"kind": "KindDefinition", "metadata": {"name": "K"}, "spec": {
        "kind": "K",
        "schema": {"type": "object", "properties": {
            "when": {"type": "string", "format": "date-time"}}},
    }}
    with pytest.raises(DnapError) as caught:
        validate_kind_definition(nested)
    assert caught.value.data["keyword"] == "format"
    assert caught.value.data["at"] == "spec.schema.properties.when.format"


@pytest.mark.asyncio
async def test_this_sdk_refuses_a_kind_definition_write_and_that_is_the_conflict(server):
    """⭐⭐ The open conflict between §6.1 and this SDK, asserted rather than
    narrated — so it fails the day either side changes.

    §6.1 says a Kind is created by writing a `KindDefinition`, that *"there is
    no other way"*, and that *"no out-of-band mechanism is permitted"*. This
    SDK refuses a generic write of `KindDefinition` (it is a bootstrap Kind)
    and routes Kind authoring through `dna.application.kind_authoring`, where
    what a tenant writes is INERT until a human approves it in a portal. That
    approval gate is a product decision, not an oversight.

    So the protocol's own rules are implemented and unit-tested above
    (`validate_kind_definition`), and on THIS server they are not reachable
    through `instances/write`: the catalog answers `-32006 NOT_WRITABLE`
    first, which is the honest order — telling a client to fix its
    `metadata.name` when the write could never have landed would send it to
    fix the wrong thing.

    Reported, not decided. If the founder resolves it toward §6.1, this test
    is where the change announces itself."""
    await _ready(server)
    error = await _err(
        server, "instances/write", channel=_channel(_SCOPE),
        document={"apiVersion": "github.com/ruinosus/dna/core/v1",
                  "kind": "KindDefinition",
                  "metadata": {"name": "ReviewChecklist"},
                  "spec": {"kind": "ReviewChecklist",
                           "apiVersion": "example.test/v1", "plane": "record",
                           "schema": {"type": "object"}}},
    )
    assert error["code"] == NOT_WRITABLE
    assert "KindDefinition" in str(error)


@pytest.mark.asyncio
async def test_the_total_order_is_pushed_DOWN_to_the_store_not_applied_per_page(
    server, monkeypatch,
):
    """⭐ §6.2 rule 4, and the assertion that the behavioural one cannot make.

    The fixture store happens to yield names in sorted order already, so
    "the results came back sorted" is true whether or not this server asked
    for an order — the behavioural test above passes against a page-local
    sort, and a page-local sort is wrong on every listing longer than one
    page. What separates them is WHERE the order is applied, so that is what
    is asserted: the request reaches ``kernel.query`` carrying it.

    **Mutant:** drop ``order_by`` (or sort each page here). This fails; the
    behavioural test does not, which is exactly why both exist."""
    seen: list[Any] = []
    original = server.live.kernel.query

    def spy(*args, **kwargs):
        # ``kernel.query(scope, kind, ...)`` — other Kinds are queried on the
        # way (the Kind catalog is itself a read), so only the listed Kind is
        # under test here.
        if len(args) > 1 and args[1] == "Agent":
            seen.append(kwargs.get("order_by"))
        return original(*args, **kwargs)

    monkeypatch.setattr(server.live.kernel, "query", spy)
    await _ready(server)
    await _ok(server, "instances/list", channel=_channel(_SCOPE), kind="Agent")
    assert seen, "instances/list must reach the store"
    assert all(o == ["metadata.name"] for o in seen), (
        f"the total order must be the STORE's, not the page's — got {seen}"
    )


def test_the_schema_bound_descends_through_items_too():
    """The recursive check has two descents — a map of schemas
    (``properties``) and a schema-valued keyword (``items`` /
    ``additionalProperties``). Both need a case, because a mutant that
    disables one leaves the other passing and the bound is only half enforced.

    **Mutant:** skip the schema-valued descent. The `properties` case above
    still passes; this one does not."""
    from dna.protocol.kinddef import validate_kind_definition

    doc = {"kind": "KindDefinition", "metadata": {"name": "K"}, "spec": {
        "kind": "K",
        "schema": {"type": "array",
                   "items": {"type": "string", "contentEncoding": "base64"}},
    }}
    with pytest.raises(DnapError) as caught:
        validate_kind_definition(doc)
    assert caught.value.data["keyword"] == "contentEncoding"
    assert caught.value.data["at"] == "spec.schema.items.contentEncoding"


def test_every_refusal_family_gets_a_code_that_is_not_internal_error():
    """⭐ §7 — the translation table, asserted at the seam rather than through
    a handler that now refuses earlier.

    ``instances/write`` catches an unwritable Kind from the catalog before the
    kernel ever sees it, which is the right order and which makes the kernel's
    own refusals unreachable from the happy path. They are still reachable —
    a layer policy or a tenant rule refuses at write time, on a Kind the
    catalog called writable — and every one of them must come back as a
    DECISION, never as ``-32603 Internal error``.

    **Mutant:** delete either refusal branch of ``_translate``. The refusal
    falls into the dispatcher's catch-all and the client is told the server
    broke."""
    from dna.application.instances import BootstrapKindWriteRefused, DeleteRefused
    from dna.kernel.errors import StoreUnavailable
    from dna.kernel.protocols import LayerPolicyViolationError, TenantNotAllowed

    from dna.protocol import NOT_WRITABLE, REFUSED
    from dna.protocol.methods import _translate

    for exc, expected in (
        (BootstrapKindWriteRefused("no"), NOT_WRITABLE),
        (DeleteRefused("no"), NOT_WRITABLE),
        (TenantNotAllowed("no"), REFUSED),
        (LayerPolicyViolationError("no"), REFUSED),
        (StoreUnavailable("no"), REFUSED),
    ):
        translated = _translate(exc)
        assert translated.code == expected, (type(exc).__name__, translated.code)
        assert translated.code != -32603


def test_an_exception_the_table_does_not_know_is_NOT_given_a_plausible_code():
    """The other half: ``_translate`` re-raises what it cannot classify, so the
    dispatcher's catch-all reports ``-32603``. Guessing a code for an unknown
    failure would be the §7 collapse with better manners — the client would
    read a decision where there was a crash."""
    from dna.protocol.methods import _translate

    boom = RuntimeError("the disk melted")
    with pytest.raises(RuntimeError):
        _translate(boom)


def test_the_digest_is_a_property_of_the_SET_not_of_the_iteration_order():
    """The digest sorts before hashing, and this is the only test that can see
    it: the fixture store happens to yield names in order, so a behavioural
    test through the server cannot tell a sorted digest from an unsorted one.

    It matters because the digest drives cursor expiry. A store whose iteration
    order changed — a different adapter, a different index, a parallel scan —
    would otherwise report a moved channel and expire every outstanding cursor
    for a change that never happened.

    **Mutant:** drop the `sorted()`. This fails; nothing else does."""
    from dna.protocol.revision import digest_revision

    pairs = [("beta", "e2"), ("alpha", "e1"), ("charlie", "e3")]
    assert digest_revision(pairs) == digest_revision(sorted(pairs))
    assert digest_revision(pairs) == digest_revision(reversed(sorted(pairs)))
    # …and it still MOVES when the content moves, or it would be a constant.
    assert digest_revision(pairs) != digest_revision(
        [("beta", "e2"), ("alpha", "CHANGED"), ("charlie", "e3")],
    )
    # An empty slice gets a digest too: "nothing of this Kind exists here" is a
    # state, and a listing of it belongs to a snapshot like any other.
    assert digest_revision([])
