"""The DnapClient against §8's four client obligations.

Rule 1 gets a guard rather than a test of behaviour, because behaviour cannot
express it: a client can pass every functional test while carrying a literal
type name that only fires on one branch. So the guard reads the client's own
AST and asks the LIVE registry whether any string in it is a Kind — and
``test_the_kind_scan_actually_bites`` plants one to prove the guard is not
merely green.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.dnap import (
    DERIVED_METADATA_MEMBERS,
    CursorExpired,
    DnapClient,
    DnapProtocolError,
    KindNotServed,
    UnknownCapability,
    UnknownKind,
)

from dnap_stub import CHANNEL, DnapStubServer  # noqa: E402


async def _connected(*mutations, **kwargs) -> tuple[DnapClient, DnapStubServer]:
    server = DnapStubServer(mutations, **kwargs)
    client = DnapClient(server.handle)
    await client.connect()
    return client, server


# ---------------------------------------------------------------------------
# ⭐ obligation 1 — the vocabulary comes from the wire, and only from there
# ---------------------------------------------------------------------------

_CLIENT_PACKAGE = Path(__file__).resolve().parents[1] / "dna" / "dnap"


def _registered_kind_names() -> set[str]:
    from dna.kernel import Kernel

    names = {port.kind for port in Kernel.auto().kind_ports()}
    assert len(names) > 50, (
        "the registry oracle looks empty — this guard would be blind, which is "
        "worse than absent because it reads as a pass")
    return names


def test_the_client_names_no_kind():
    """⭐ §8, client rule 1 — "name no Kind of its own".

    *"It is the difference between 'Kind-agnostic' as a claim and as a property
    a test can fail on."* The oracle is the live registry, so this guard has no
    vocabulary of its own to drift and it sees a violation the moment somebody
    writes one.
    """
    from dna.testing.kind_literal_scan import scan_kind_name_constants

    names = _registered_kind_names()
    scanned = sorted(_CLIENT_PACKAGE.rglob("*.py"))
    assert len(scanned) >= 2, (
        f"the scan found {len(scanned)} file(s) under {_CLIENT_PACKAGE} — a guard "
        f"that reads nothing is green for the wrong reason")
    offenders = []
    for path in scanned:
        offenders += [
            (path.name, f.lineno, f.symbol, f.members[0])
            for f in scan_kind_name_constants(
                path.read_text(encoding="utf-8"),
                module=path.name, kind_names=names)
        ]
    assert not offenders, (
        f"the DNAP client names {len(offenders)} Kind(s) of its own: {offenders}. "
        f"Its whole vocabulary must arrive at initialize (§8, client rule 1); a "
        f"literal here is a type this client would keep believing in after the "
        f"server stopped serving it."
    )


def test_the_kind_scan_actually_bites():
    """The guard above is worthless if it cannot fail. Plant one and watch.

    A guard nobody has seen go red is a guard nobody has tested — and this repo
    has shipped three of those.
    """
    from dna.testing.kind_literal_scan import scan_kind_name_constants

    names = _registered_kind_names()
    victim = sorted(names)[0]
    planted = (
        f'"""A docstring naming {victim} — prose, not a name."""\n'
        f"def resolve(client, channel):\n"
        f"    return client.get_instance(channel=channel, kind={victim!r},\n"
        f"                               name='x')\n"
    )
    found = scan_kind_name_constants(planted, module="m.py", kind_names=names)
    assert [f.members[0] for f in found] == [victim], (
        f"the scan did not see the planted literal {victim!r}: {found}")
    assert found[0].symbol == "resolve"

    # ...and does NOT fire on the docstring, which is describing rather than naming.
    prose_only = f'"""This client can resolve a {victim}."""\nX = 1\n'
    assert scan_kind_name_constants(prose_only, module="m.py", kind_names=names) == []


@pytest.mark.asyncio
async def test_the_vocabulary_comes_from_initialize():
    client, server = await _connected()
    assert client.kinds == tuple(server._initialize()["kinds"])
    assert client.channels == (CHANNEL,)
    assert client.protocol_version == "1.0"


@pytest.mark.asyncio
async def test_naming_an_unadvertised_kind_is_refused_before_the_wire():
    client, _ = await _connected()
    with pytest.raises(UnknownKind) as excinfo:
        await client.list_instances(channel=CHANNEL, kind="NotAdvertisedHere")
    # The refusal names the vocabulary the caller could have used, which the
    # server's own -32003 cannot.
    assert "ConformanceWidget" in str(excinfo.value)


@pytest.mark.asyncio
async def test_nothing_can_be_asked_before_initialize():
    client = DnapClient(DnapStubServer(()).handle)
    with pytest.raises(DnapProtocolError, match="not connected"):
        _ = client.kinds


@pytest.mark.asyncio
async def test_a_server_with_no_vocabulary_is_a_protocol_error_not_a_fallback():
    """The client has no built-in list to fall back to, and must say so rather
    than quietly acquiring one."""
    class _Mute(DnapStubServer):
        def _initialize(self):
            hello = super()._initialize()
            hello["kinds"] = None
            return hello

    client = DnapClient(_Mute(()).handle)
    with pytest.raises(DnapProtocolError, match="fallback"):
        await client.connect()


# ---------------------------------------------------------------------------
# obligation 2 — revision is opaque
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_revision_is_carried_opaquely():
    """A revision that is not a number, not ordered and not parseable must move
    through the client untouched. §5 calls it opaque and monotonic PER CHANNEL —
    the shape is the server's business, and a client that read it would break on
    the next server."""
    class _OpaqueRevisions(DnapStubServer):
        def _instances_list(self, params):
            out = super()._instances_list(params)
            out["revision"] = "sha256:9f2b…/gen-7"
            return out

    server = _OpaqueRevisions(())
    client = DnapClient(server.handle)
    await client.connect()
    page = await client.list_instances(channel=CHANNEL, kind="ConformanceWidget")
    assert page.revision == "sha256:9f2b…/gen-7"
    whole = await client.list_all(channel=CHANNEL, kind="ConformanceWidget")
    assert whole.revision == "sha256:9f2b…/gen-7"


@pytest.mark.asyncio
async def test_list_all_refuses_a_quilt_of_moments():
    """The client enforces §6.2 rule 3 on the SERVER: pages from two snapshots
    are not a listing, and concatenating them silently is how nobody notices."""
    from dnap_stub import REVISION_MOVES_BETWEEN_PAGES

    client, _ = await _connected(REVISION_MOVES_BETWEEN_PAGES)
    with pytest.raises(DnapProtocolError, match="different revisions"):
        await client.list_all(channel=CHANNEL, kind="ConformanceWidget", limit=2)


# ---------------------------------------------------------------------------
# obligation 3 — unknown metadata survives the round trip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_metadata_members_survive_a_round_trip():
    """⭐ §5/§8 rule 3. A client that kept only the members it recognised would
    delete a server's data on a read-modify-write, and the caller would see a
    successful save."""
    sent: list[dict] = []

    class _Recording(DnapStubServer):
        def _instances_write(self, params):
            sent.append(params["instance"])
            return super()._instances_write(params)

    server = _Recording(())
    server.store[(CHANNEL, "ConformanceWidget", "carrier")] = {
        "apiVersion": "example.test/dnap/v1", "kind": "ConformanceWidget",
        "metadata": {
            "name": "carrier", "id": "01JCARRIER", "revision": "1200",
            "description": "a known member",
            # members no version of this client has heard of
            "labels": {"team": "platform"},
            "x-provenance": {"importedFrom": "elsewhere"},
        },
        "spec": {"title": "conformance carrier"},
    }
    client = DnapClient(server.handle)
    await client.connect()

    got = await client.get_instance(
        channel=CHANNEL, kind="ConformanceWidget", name="carrier")
    instance = got["instance"]
    await client.write_instance(instance, channel=CHANNEL)

    written = sent[-1]["metadata"]
    assert written["labels"] == {"team": "platform"}
    assert written["x-provenance"] == {"importedFrom": "elsewhere"}
    assert written["description"] == "a known member"
    # ...and EXACTLY the two derived members are the ones dropped (§5).
    assert set(instance["metadata"]) - set(written) == set(DERIVED_METADATA_MEMBERS)


@pytest.mark.asyncio
async def test_write_does_not_mutate_the_callers_instance():
    """Stripping the derived members must not reach back into the caller's dict:
    a round trip that quietly edits its input is a round trip nobody can repeat."""
    server = DnapStubServer(())
    client = DnapClient(server.handle)
    await client.connect()
    mine = {
        "apiVersion": "example.test/dnap/v1", "kind": "ConformanceWidget",
        "metadata": {"name": "mine", "id": "01JMINE", "revision": "7",
                     "labels": {"a": "b"}},
        "spec": {"title": "conformance mine"},
    }
    await client.write_instance(mine, channel=CHANNEL)
    assert mine["metadata"]["id"] == "01JMINE"
    assert mine["metadata"]["revision"] == "7"


@pytest.mark.asyncio
async def test_ifmatch_travels_as_a_parameter_not_as_metadata():
    """§6.2 puts optimistic concurrency in ``ifMatch``; §5 keeps ``revision`` out
    of the written body. Both at once, or the write is refused for the wrong
    reason and the conflict never surfaces."""
    server = DnapStubServer(())
    client = DnapClient(server.handle)
    await client.connect()
    got = await client.get_instance(
        channel=CHANNEL, kind="ConformanceWidget", name="alpha-0")
    instance = got["instance"]
    revision = instance["metadata"]["revision"]

    await client.write_instance(instance, channel=CHANNEL, if_match=revision)
    from dna.dnap import RevisionConflict
    with pytest.raises(RevisionConflict) as excinfo:
        await client.write_instance(instance, channel=CHANNEL, if_match=revision)
    assert excinfo.value.data["revision"] != revision


# ---------------------------------------------------------------------------
# obligation 4 — restart on -32005
# ---------------------------------------------------------------------------

class _ExpiresOnce(DnapStubServer):
    """Expires the cursor exactly once, mid-walk."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.expired_once = False

    def _instances_list(self, params):
        if params.get("cursor") and not self.expired_once:
            self.expired_once = True
            from dnap_stub import _Refusal, _err
            raise _Refusal(_err(-32005, "cursor expired; restart the listing"))
        return super()._instances_list(params)


@pytest.mark.asyncio
async def test_list_all_restarts_on_cursor_expired():
    """⭐ §8, client rule 4 — restart, not "assume exhaustion".

    The tempting wrong reading is that a dead cursor means the end of the
    listing: it costs nothing, raises nothing, and silently drops the tail.
    """
    server = _ExpiresOnce(())
    client = DnapClient(server.handle)
    await client.connect()
    page = await client.list_all(channel=CHANNEL, kind="ConformanceWidget", limit=2)
    assert server.expired_once
    names = sorted(i["metadata"]["name"] for i in page.instances)
    assert len(names) == 13, names          # nothing dropped
    assert len(set(names)) == 13, names     # and nothing doubled by the restart
    assert page.exhausted


@pytest.mark.asyncio
async def test_iter_pages_leaves_the_expiry_to_the_caller():
    """The raw walk does not decide for anyone: it raises, and ``list_all`` is
    where the restart policy lives."""
    server = _ExpiresOnce(())
    client = DnapClient(server.handle)
    await client.connect()
    with pytest.raises(CursorExpired):
        async for _ in client.iter_pages(
            channel=CHANNEL, kind="ConformanceWidget", limit=2):
            pass


@pytest.mark.asyncio
async def test_endless_expiry_is_reported_rather_than_retried_forever():
    class _AlwaysExpires(DnapStubServer):
        def _instances_list(self, params):
            if params.get("cursor"):
                from dnap_stub import _Refusal, _err
                raise _Refusal(_err(-32005, "expired"))
            return super()._instances_list(params)

    client = DnapClient(_AlwaysExpires(()).handle)
    await client.connect()
    with pytest.raises(DnapProtocolError, match="would be a hang"):
        await client.list_all(channel=CHANNEL, kind="ConformanceWidget", limit=2)


# ---------------------------------------------------------------------------
# errors, capabilities, batch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_error_codes_become_named_exceptions_with_data_intact():
    client, _ = await _connected()
    with pytest.raises(KindNotServed):
        # the server's own refusal, reached by going around the local guard
        await client._call("instances/list",
                           {"channel": CHANNEL, "kind": "NeverAdvertised"})
    from dna.dnap import ChannelNotServed, ValidationFailed
    with pytest.raises(ChannelNotServed):
        await client.list_instances(
            channel="dnap-scope:/somewhere-else", kind="ConformanceWidget")
    with pytest.raises(ValidationFailed) as excinfo:
        await client.write_instance(
            {"apiVersion": "example.test/dnap/v1", "kind": "ConformanceWidget",
             "metadata": {"name": "bad"}, "spec": {"title": 42}},
            channel=CHANNEL)
    assert excinfo.value.data == {"path": "spec.title", "rule": "type: string"}


@pytest.mark.asyncio
async def test_an_unadvertised_capability_is_refused_locally():
    client, _ = await _connected(capabilities=("write",))
    assert not client.supports("search")
    with pytest.raises(UnknownCapability, match="search"):
        await client.search_instances(
            channel=CHANNEL, kind="ConformanceWidget", query="x")
    with pytest.raises(UnknownCapability, match="resolve"):
        await client.resolve_agent(channel=CHANNEL, name="alpha-0")


@pytest.mark.asyncio
async def test_search_sends_no_threshold_the_caller_did_not_ask_for():
    """§6.4 rule 2 — minSimilarity is the CALLER's policy. A client with a
    default would be inventing the judgement the server refuses to make."""
    seen: list[dict] = []

    class _Recording(DnapStubServer):
        def _search(self, params):
            seen.append(params)
            return super()._search(params)

    server = _Recording(())
    client = DnapClient(server.handle)
    await client.connect()
    await client.search_instances(channel=CHANNEL, kind="ConformanceWidget",
                                  query="conformance")
    assert "minSimilarity" not in seen[-1]
    await client.search_instances(channel=CHANNEL, kind="ConformanceWidget",
                                  query="conformance", min_similarity=0.4)
    assert seen[-1]["minSimilarity"] == 0.4


@pytest.mark.asyncio
async def test_batch_answers_are_paired_by_id_not_by_arrival():
    class _Shuffles(DnapStubServer):
        async def handle(self, request):
            out = await super().handle(request)
            return list(reversed(out)) if isinstance(out, list) else out

    client = DnapClient(_Shuffles(()).handle)
    await client.connect()
    first, second = await client.batch([
        ("kinds/list", {"channel": CHANNEL}),
        ("instances/list", {"channel": CHANNEL, "kind": "ConformanceWidget"}),
    ])
    assert "kinds" in first
    assert "instances" in second


@pytest.mark.asyncio
async def test_the_client_never_retries_a_refused_channel_elsewhere():
    """§3 — an unserved channel is an address the server does not hold. A client
    that fell back to one it does hold would recreate, on its own side, the
    substitution the protocol went out of its way to forbid."""
    attempted: list[str] = []

    class _Watching(DnapStubServer):
        def _channel(self, params):
            attempted.append(params.get("channel"))
            return super()._channel(params)

    client = DnapClient(_Watching(()).handle)
    await client.connect()
    from dna.dnap import ChannelNotServed
    with pytest.raises(ChannelNotServed):
        await client.list_all(channel="dnap-scope:/not-ours",
                              kind="ConformanceWidget")
    assert attempted == ["dnap-scope:/not-ours"]
