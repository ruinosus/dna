"""``GET /v1/graph/kinds`` — the SCHEMA graph, served in one call.

The hole measured on 06/08/2026 (dna-cloud, `apps/web/app/dashboard/kinds/
page.tsx`): the Kind catalogue wanted the SET question — *which Kinds
reference which in this workspace?* — and the only door available answered it
one Kind at a time. So the portal ran N calls to ``/v1/kinds/registry/{kind}``
through a queue with concurrency 4, on EVERY render, and rebuilt the graph in
memory. The registry already held the whole answer.

What this module pins:

* the graph arrives WHOLE — nodes, edges, gaps — in a single 200, and its
  declared edges are the ones ``spec.relations`` declares (the same reading the
  write path validates with, asserted against the registry, not re-typed);
* **the answer qualifies itself.** ``coverage`` carries the per-tier counts,
  how many edges the runtime actually ENFORCES, and the ``limits`` that say
  what the graph structurally cannot see. This is the assertion that keeps a
  screen from rendering the edge list as "all the relations";
* **``declared`` and ``enforced`` are different numbers, and the wire says
  which is which.** A relation addressed by a domain key (``by:
  workspace_id``) or carrying its Kind in the value (``to: "*"``) is fully
  declared and deliberately not resolved by the kernel; the per-edge
  ``enforced`` flag is what stops a screen promoting one into the other;
* **the gaps rank themselves.** Every ``unresolved`` row carries an ``origin``
  saying which pass produced it, so a screen separates a broken DECLARATION —
  including an ``inverse`` that does not pair — from a field nobody has
  declared, without reading English prose off a backend. That was i-104: 25
  rows, all of one origin, presented as 25 broken declarations because
  ``reason`` was the only thing to go on;
* it is SCHEMA, never data: no instance read, and the envelope says which
  graph it is;
* ``tenant`` resolves the scope like the registry route, an unknown scope is
  an empty graph rather than a 404, and the route is mounted (and guarded) on
  the shared-secret lane too.

Real app via ``TestClient`` — same pattern as ``test_registered_kind_rest.py``.
"""
from __future__ import annotations

import pathlib
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _client(dna_dir, **kwargs) -> TestClient:
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE, **kwargs))


@pytest.fixture
def graph(dna_dir):
    with _client(dna_dir) as c:
        r = c.get("/v1/graph/kinds")
        assert r.status_code == 200, r.text
        return r.json()


# --- the graph arrives whole -------------------------------------------------


def test_the_whole_graph_comes_back_in_one_call(graph):
    """One request, every node and every edge. The N+1 this route exists to
    kill is not a performance detail: the portal's latency GREW with the
    workspace, for a fact the registry holds whole."""
    assert graph["kinds"], "no Kinds in the graph — the registry did not resolve"
    assert graph["edges"], "no edges — the projection stopped seeing declarations"
    kinds = {k["kind"] for k in graph["kinds"]}
    # Every edge connects two REGISTERED Kinds: a declaration naming an
    # unregistered Kind is a gap (``unresolved``), never a node nobody has.
    for edge in graph["edges"]:
        assert edge["from_kind"] in kinds
        # ``*`` is the one non-Kind target: the value names its own Kind.
        assert edge["to_kind"] in kinds or edge["to_kind"] == "*"


def test_the_declared_spine_of_the_board_is_present_and_marked_declared(graph):
    """``Story.feature → Feature`` is the enforced work-item spine — the edge
    ``DNA_REF_VALIDATION`` resolves at write time. If it stops arriving at the
    ``declared`` tier, the route is no longer serving what the kernel enforces."""
    declared = {
        (e["from_kind"], e["field"], e["to_kind"])
        for e in graph["edges"] if e["tier"] == "declared"
    }
    assert ("Story", "feature", "Feature") in declared
    assert ("Story", "spec_refs", "Spec") in declared


def test_an_array_declaration_arrives_as_many(graph):
    spec_refs = [e for e in graph["edges"]
                 if e["from_kind"] == "Story" and e["field"] == "spec_refs"]
    assert spec_refs and all(e["cardinality"] == "many" for e in spec_refs)


def test_a_polymorphic_declaration_arrives_as_several_marked_edges(graph):
    """``Membership.scope_ref`` may name an Organization OR a Project. Both
    edges come back, both flagged — a renderer that drew one would be picking
    a target the model does not pick."""
    poly = [e for e in graph["edges"]
            if e["from_kind"] == "Membership" and e["field"] == "scope_ref"]
    assert {e["to_kind"] for e in poly} == {"Organization", "Project"}
    assert all(e["polymorphic"] for e in poly)


def test_nodes_carry_identity_not_the_schema(graph):
    """The descriptor stays behind ``/v1/kinds/registry/{kind}``: a graph that
    inlined 80 JSON Schemas would be a download, not a graph."""
    node = next(k for k in graph["kinds"] if k["kind"] == "Story")
    assert set(node) == {"kind", "alias", "group", "plane"}
    assert node["group"] == "sdlc"


# --- the answer qualifies itself ---------------------------------------------


def test_coverage_counts_are_derived_from_what_was_returned(graph):
    """Every counter must match the collection it describes. A hand-kept count
    goes stale silently and the screen reading it is then wrong with
    confidence — ``guardas-enumeracao-vs-derivacao``."""
    cov = graph["coverage"]
    assert cov["kinds"] == len(graph["kinds"])
    assert cov["edges"] == len(graph["edges"])
    assert cov["unresolved"] == len(graph["unresolved"])
    assert cov["declared"] + cov["composition"] == cov["edges"]
    for tier in ("declared", "composition"):
        assert cov[tier] == len([e for e in graph["edges"] if e["tier"] == tier])
    assert cov["enforced"] == len([e for e in graph["edges"] if e["enforced"]])
    assert cov["kinds_with_relations"] == len(
        {e["from_kind"] for e in graph["edges"] if e["tier"] == "declared"}
    )
    assert sum(cov["unresolved_by_origin"].values()) == cov["unresolved"]
    for origin, count in cov["unresolved_by_origin"].items():
        assert count == len([u for u in graph["unresolved"]
                             if u["origin"] == origin])


def test_declared_is_not_the_same_as_enforced_and_the_wire_says_so(graph):
    """The measurement that forced this block: most of the model's schema edges
    are NOT resolved at write time — composition edges never are, and a
    relation addressed by a domain key is declared without being followed. A
    response that did not distinguish the two would let a screen tell somebody
    their ``by: workspace_id`` relation is validated. It is not."""
    cov = graph["coverage"]
    assert cov["enforced"] < cov["declared"] < cov["edges"], (
        "declared and enforced have collapsed into one number — if that is "
        "genuinely true this assertion should be retired deliberately, not "
        "silently"
    )
    unenforced = [
        e for e in graph["edges"]
        if e["tier"] == "declared" and not e["enforced"]
    ]
    assert unenforced, "no declared-but-unfollowed relation survived"
    assert all(e["by"] != "name" or e["to_kind"] == "*" for e in unenforced)


def test_followed_arrives_on_the_wire_and_is_WIDER_than_enforced(graph):
    """⚠️ The ``response_model`` trap, applied to the key fatia 5 introduced.

    FastAPI's ``response_model`` FILTERS: a key the impl produces and the model
    does not declare is dropped in silence, and a client cannot tell that apart
    from "the field does not exist". It happened here on 06/08/2026, to three
    fields of the refs route at once.

    ``followed`` is exactly that shape of new key, and it carries the whole
    result of the slice: without it a screen reads ``enforced`` alone and calls
    every ``by: <key>`` relation unchecked while its edges sit in the table.
    So the assertion is not "the key is present" but "present AND disagreeing
    with ``enforced`` somewhere" — a dropped key and a key aliased to its
    neighbour are different bugs, and both are red here.
    """
    declared = [e for e in graph["edges"] if e["tier"] == "declared"]
    assert declared
    for e in declared:
        assert "followed" in e, (
            "the route dropped `followed` — the response_model does not "
            "declare it, so FastAPI filtered it out without a word"
        )
    # ⚠️ ``by != "name"`` alone is NOT "addressed by a key". A composite form
    # (``Kind/name``) is also not ``name``, and since 06/08 a composite MAY
    # declare concrete targets — ``Engram.area`` does — so a filter written as
    # "not name, and to_kind is not *" sweeps composites in and then asserts
    # they are followed, which they are not. The vocabulary is closed, so ask
    # it rather than approximating it.
    from dna.kernel.kinds.relations import COMPOSITE_FORMS

    by_key = [
        e for e in declared
        if e["by"] != "name" and e["by"] not in COMPOSITE_FORMS
    ]
    assert by_key, "no key-addressed relation survived — the fixture, not the guard"
    for e in by_key:
        assert e["followed"] is True, (
            f"{e['from_kind']}.{e['field']} is addressed `by: {e['by']}` and "
            f"the wire says it is not followed — but its edges exist"
        )
        assert e["enforced"] is False, (
            f"{e['from_kind']}.{e['field']} claims to VETO on a key it "
            f"resolves more poorly than the live lookup does"
        )
    cov = graph["coverage"]
    assert cov["followed"] == cov["enforced"] + len(by_key), (
        f"coverage.followed ({cov['followed']}) is not "
        f"enforced ({cov['enforced']}) plus the {len(by_key)} key-addressed "
        f"edges — the counter and the edge list disagree about the same fact, "
        f"which is how a screen and a table end up telling different stories"
    )


def test_the_limits_travel_on_the_wire(graph):
    """The caveats ship WITH the answer instead of living in a doc page a
    caller may never read — including the one that matters most, that this is
    the SCHEMA graph and not the data graph."""
    limits = {limit["code"]: limit["detail"] for limit in graph["coverage"]["limits"]}
    assert "schema_not_data" in limits
    assert "enforced_is_per_edge" in limits
    assert "top_level_properties_only" in limits
    assert "unresolved_is_not_all_broken" in limits
    assert "inverse_is_declaration_only" in limits
    for code, detail in limits.items():
        assert detail.strip(), f"limit {code} states no reason"


def test_the_gaps_come_back_named_not_dropped(graph):
    """A graph whose gaps are dropped renders as complete. What keeps it honest
    is the ``unresolved`` list — and every row still carries a reason a human
    can read, next to the ``origin`` a screen switches on."""
    assert graph["unresolved"], "no unresolved fields — the gap list went blind"
    for row in graph["unresolved"]:
        assert row["origin"] and row["reason"]


def test_a_key_addressed_reference_IS_an_edge_and_says_it_is_not_enforced(graph):
    """``Comment.target_ref`` really points at an instance — by a composite
    ``Kind:name`` string. It used to be filtered OUT of the edges into an
    "undeclarable" bucket, which is how eight ``produces`` fields ended up
    described as inexpressible when they were merely undeclared. It is an edge
    now, and ``enforced: false`` is what keeps that from over-claiming."""
    drawn = [e for e in graph["edges"]
             if e["from_kind"] == "Comment" and e["field"] == "target_ref"]
    assert len(drawn) == 1
    assert drawn[0]["to_kind"] == "*"
    assert drawn[0]["by"] == "Kind:name"
    assert drawn[0]["enforced"] is False


# --- i-104: the gap list ranks itself, through the door ----------------------


def test_every_gap_arrives_with_a_machine_readable_origin(graph):
    """The portal is EN/PT and must not render ``reason``. ``origin`` is the
    half it CAN switch on, and no row may arrive without one."""
    assert graph["unresolved"]
    for row in graph["unresolved"]:
        assert row["origin"] in {
            "declared", "composition", "inverse", "undeclared",
        }, row
        assert row["reason"], row
        # Present on every row, ``null`` where there is no sub-code — a stable
        # key set is what lets a consumer type the shape once.
        assert "code" in row, row


def test_the_wire_names_which_origins_deserve_alarm(graph):
    """Derived, like ``enforced_tiers`` — a screen must not re-type the
    ranking, and the answer must be able to grow without a client release."""
    cov = graph["coverage"]
    assert cov["declared_origins"] == ["declared", "composition", "inverse"]
    assert "undeclared" not in cov["declared_origins"]
    assert set(cov["declared_origins"]) <= set(cov["unresolved_by_origin"])


def test_a_screen_can_separate_the_noise_from_the_alarms_without_prose(graph):
    """The whole point, stated as the consumer would write it: filter by
    ``origin`` against ``declared_origins``, never by reading English."""
    declared_origins = set(graph["coverage"]["declared_origins"])
    alarms = [u for u in graph["unresolved"] if u["origin"] in declared_origins]
    noise = [u for u in graph["unresolved"] if u["origin"] not in declared_origins]
    assert noise, "the field-name guesses vanished — the split stopped working"
    assert len(alarms) + len(noise) == len(graph["unresolved"])
    # And the measured truth of this registry: every gap is a guess. A screen
    # that shows this list as "declarations that do not resolve" is wrong about
    # every row, which is exactly what the portal was doing.
    assert alarms == [], f"a DECLARED reference is dangling: {alarms}"


def test_the_composite_family_arrives_together_and_never_as_a_gap(graph):
    """The misclassification i-104 measured: ``Engram.source_refs`` and
    ``SourceArtifact.derived_refs`` carry ``Kind``+``name`` exactly like
    ``Comment.target_ref``, which the runtime already classified right. All
    three are one family, they arrive together, and none of them is a gap."""
    gaps = {(u["kind"], u["field"]) for u in graph["unresolved"]}
    drawn = {(e["from_kind"], e["field"]): e for e in graph["edges"]}
    for pair in [("Comment", "target_ref"), ("Engram", "source_refs"),
                 ("SourceArtifact", "derived_refs")]:
        assert pair in drawn, f"{pair} is not declared as a relation"
        assert pair not in gaps, f"{pair} is BOTH a gap and a declared relation"
        assert drawn[pair]["to_kind"] == "*", (
            "a composite pointer names no single target Kind"
        )


def test_no_declaration_cites_a_kind_the_registry_lacks(graph):
    """``Organization.plan_ref -> Tier`` survived the metering rename that made
    it ``PricingPlan``, and ``/v1/kinds/registry/Tier`` answered 404 while this
    route kept citing it. The citation moved from a hand table in the SDK onto
    the Kind, so the mutant moved with it — and through the door, both sides of
    the contradiction are still visible at once."""
    kinds = {k["kind"] for k in graph["kinds"]}
    dead = [f"{e['from_kind']}.{e['field']} -> {e['to_kind']}"
            for e in graph["edges"]
            if e["to_kind"] != "*" and e["to_kind"] not in kinds]
    assert dead == [], f"an edge cites Kinds this scope does not serve: {dead}"
    claims = [u for u in graph["unresolved"] if u["origin"] != "undeclared"]
    assert claims == [], f"declarations this scope cannot honour: {claims}"


# --- scope, lanes, and what an empty answer means ----------------------------


def test_tenant_derives_the_scope_like_the_registry_route(dna_dir):
    """i-094: the portal knows the WORKSPACE, not the scope. ``tenant``
    resolves it server-side (``live.default_scope``); an explicit ``scope``
    still wins. Here (single-workspace) both reach the same registry."""
    with _client(dna_dir) as c:
        plain = c.get("/v1/graph/kinds")
        by_tenant = c.get("/v1/graph/kinds", params={"tenant": "ws-qualquer"})
        assert by_tenant.status_code == 200, by_tenant.text
        assert by_tenant.json()["edges"] == plain.json()["edges"]

        explicit = c.get("/v1/graph/kinds",
                         params={"scope": _SCOPE, "tenant": "ws-qualquer"})
        assert explicit.status_code == 200
        assert explicit.json()["scope"] == _SCOPE


def test_the_route_echoes_the_scope_it_resolved(dna_dir):
    with _client(dna_dir) as c:
        assert c.get("/v1/graph/kinds").json()["scope"] is None
        assert c.get("/v1/graph/kinds", params={"scope": _SCOPE}
                     ).json()["scope"] == _SCOPE


def test_a_scope_with_nothing_registered_is_an_empty_graph_not_a_404(dna_dir):
    """"Exists and holds nothing" is an answer. Conflating it with "no such
    scope" would make a screen say *error* where it should say *nothing
    registered yet* — and the coverage block still ships, so the caller is
    told it is looking at a SCHEMA graph even when it is empty of edges."""
    with _client(dna_dir) as c:
        r = c.get("/v1/graph/kinds", params={"scope": "nao-existe-este-scope"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["coverage"]["kinds"] == len(body["kinds"])
        assert body["coverage"]["limits"]


def test_the_door_is_mounted_and_guarded_on_the_shared_secret_lane(dna_dir):
    """Mounted is not unguarded, and unguarded is not mounted. Starlette's
    routing 404 and a handler's own 404 are byte-identical, so the 401 with no
    bearer plus the 200 with it is what distinguishes "the route exists and is
    protected" from either failure."""
    with _client(dna_dir, auth="token", token="s3cret") as c:
        assert c.get("/v1/graph/kinds").status_code == 401
        ok = c.get("/v1/graph/kinds", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 200, ok.text
        assert ok.json()["edges"]
