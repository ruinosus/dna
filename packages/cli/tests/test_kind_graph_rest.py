"""``GET /v1/graph/kinds`` — the SCHEMA graph, served in one call.

The hole measured on 06/08/2026 (dna-cloud, `apps/web/app/dashboard/kinds/
page.tsx`): the Kind catalogue wanted the SET question — *which Kinds
reference which in this workspace?* — and the only door available answered it
one Kind at a time. So the portal ran N calls to ``/v1/kinds/registry/{kind}``
through a queue with concurrency 4, on EVERY render, and rebuilt the graph in
memory. The registry already held the whole answer.

What this module pins:

* the graph arrives WHOLE — nodes, edges, gaps — in a single 200, and its
  declared edges are the ones ``x-dna-ref`` declares (the same reading the
  write path validates with, asserted against the registry, not re-typed);
* **the answer qualifies itself.** ``coverage`` carries the per-tier counts,
  the tiers the runtime enforces, and the ``limits`` that say what the graph
  structurally cannot see. This is the assertion that keeps a screen from
  rendering the edge list as "all the relations" — 16 of the model's 109
  schema edges are declared, and the wire has to say so;
* it is SCHEMA, never data: no document read, and the envelope says which
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
        assert edge["to_kind"] in kinds


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
    assert cov["undeclarable"] == len(graph["undeclarable"])
    assert cov["declared"] + cov["composition"] + cov["inferred"] == cov["edges"]
    for tier in ("declared", "composition", "inferred"):
        assert cov[tier] == len([e for e in graph["edges"] if e["tier"] == tier])


def test_the_answer_says_only_the_declared_tier_is_enforced(graph):
    """The measurement that forced this block: the model's schema edges are
    mostly NOT enforced (composition + inference outnumber declaration by
    several times). A response that did not say so would let a screen assert a
    completeness this repo does not have."""
    cov = graph["coverage"]
    assert cov["enforced_tiers"] == ["declared"]
    assert cov["declared"] < cov["edges"], (
        "the enforced tier now covers the whole model — if that is genuinely "
        "true this assertion should be retired deliberately, not silently"
    )
    assert cov["composition"] or cov["inferred"]


def test_the_limits_travel_on_the_wire(graph):
    """The caveats ship WITH the answer instead of living in a doc page a
    caller may never read — including the one that matters most, that this is
    the SCHEMA graph and not the data graph."""
    limits = {limit["code"]: limit["detail"] for limit in graph["coverage"]["limits"]}
    assert "schema_not_data" in limits
    assert "declared_tier_only_enforced" in limits
    assert "top_level_properties_only" in limits
    assert "keyed_references_undeclarable" in limits
    for code, detail in limits.items():
        assert detail.strip(), f"limit {code} states no reason"


def test_the_gaps_come_back_named_not_dropped(graph):
    """A graph whose gaps are dropped renders as complete. The two lists that
    keep it honest: fields that point at something unnameable, and real
    references ``x-dna-ref`` cannot declare because they are keyed by an id."""
    assert graph["unresolved"], "no unresolved fields — the gap list went blind"
    undeclarable = {(u["kind"], u["field"]) for u in graph["undeclarable"]}
    assert ("Comment", "target_ref") in undeclarable
    for row in graph["undeclarable"]:
        assert row["target"] and row["reason"]


def test_a_keyed_reference_is_never_also_an_edge(graph):
    """``Comment.target_ref`` really points at a document — by a composite
    ``Kind:name`` string. It is stated as undeclarable, and MUST NOT also be
    drawn: an edge here would be one the write path cannot enforce."""
    assert not [e for e in graph["edges"]
                if e["from_kind"] == "Comment" and e["field"] == "target_ref"]


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
