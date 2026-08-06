"""The declared relations, checked against the LIVE registry.

``test_kind_graph.py`` is pure — it builds fake ports and never a Kernel, which
is what makes it fast and total. Purity cannot see a rename, though: a fake
port called ``Tier`` exists because the test made it.

It happened. The metering rename turned ``Tier`` into ``PricingPlan``
(dna 0.29.0) and the graph's hand-kept ``UNDECLARABLE`` table went on answering
``{"kind": "Organization", "field": "plan_ref", "target": "Tier"}`` while
``GET /v1/kinds/registry/Tier`` returned 404 — a graph citing a Kind the same
deployment says does not exist. Nothing failed, because nothing compared the
table to the registry. The docs guard could not: it regenerates the page FROM
the table, so both sides carried the same dead name and agreed.

**Those two tables are gone.** ``UNDECLARABLE`` and ``INFERENCE_DENYLIST`` were
enumerations of what the declaration could not express, and the declaration
expresses it now — ``Organization.plan_ref`` says ``to: PricingPlan, by:
tier_id`` on the Kind itself. The class of defect does not leave with them, it
MOVES: a relation's ``to`` is still a Kind name typed by a human, and a rename
can still miss it. So this file keeps its job and changes its oracle.

The oracle is the registry, so these tests have no vocabulary of their own to
drift, and a rename that misses a relation fails HERE — before the wire, not on
somebody's screen.
"""
from __future__ import annotations

import re

import pytest

from dna.kernel.kinds.relations import ANY_TARGET, inverse_gaps, relations_of
from dna.kernel.query.kind_graph import (
    COVERAGE_LIMITS,
    POLYMORPHIC_TARGET,
    UNRESOLVED_ORIGINS,
    build_kind_graph,
    kind_rows,
)

#: A backticked token that LOOKS like a Kind name: CamelCase, no separators.
#: Deliberately narrow — `tier_id` and `Kind:name` are not Kind names and must
#: not be accused of being retired ones.
_KIND_LIKE = re.compile(r"`([A-Z][A-Za-z]*)`")


@pytest.fixture(scope="module")
def ports():
    from dna.kernel import Kernel

    return list(Kernel.auto().kind_ports())


@pytest.fixture(scope="module")
def rows(ports):
    return kind_rows(ports)


@pytest.fixture(scope="module")
def registered(rows):
    return {r["kind"] for r in rows}


@pytest.fixture(scope="module")
def graph(ports):
    return build_kind_graph(ports)


class TestEveryDeclarationResolves:
    def test_every_relation_target_is_a_registered_kind(self, rows, registered):
        """THE mutant this file exists to kill, in its new home: the target
        used to be typed into a table in ``kind_graph.py`` and is now typed
        into the Kind. A rename still has to reach it."""
        dead = [
            f"{r['kind']}.{name} -> {target}"
            for r in rows
            for name, rel in sorted(r["relations"].items())
            for target in rel.to
            if target not in registered
        ]
        assert dead == [], (
            "a relation names Kinds no registry provides — a rename passed "
            f"the declaration by: {dead}"
        )

    def test_the_graph_reports_no_unresolvable_declaration(self, graph):
        """The same fact through the WIRE, which is where a consumer sees it.
        Two readings of one truth, deliberately: this one also catches a
        ``dep_filters`` alias nobody claims."""
        claims = [
            u for u in graph["unresolved"]
            if u["origin"] in ("declared", "composition")
        ]
        assert claims == [], f"declarations the model cannot honour: {claims}"

    def test_every_relation_agrees_with_its_own_schema(self, ports):
        """The contradiction check, run across the MERGED schema.

        ``KindDefinitionSpec.from_raw`` cannot do this completely — a
        descriptor pulling in ``schema_fragments`` is looking at an incomplete
        schema there — and a hand-written class Kind has no ``from_raw`` at
        all. This is the one place both halves are final."""
        from dna.kernel.kinds.relations import schema_contradictions

        problems = []
        for port in ports:
            kind = getattr(port, "kind", None)
            try:
                schema = port.schema() or {}
            except Exception:  # pragma: no cover - defensive
                continue
            problems += [
                f"{kind}: {p}"
                for p in schema_contradictions(relations_of(port), schema)
            ]
        assert problems == [], problems


class TestEveryPairPairs:
    def test_the_registry_has_no_inverse_gap(self, ports):
        """Dor 1, as an assertion. A declared ``inverse_of`` whose other half
        is missing, points elsewhere, or names a different relation is an
        authoring error the registry can prove WITHOUT reading an instance."""
        gaps = inverse_gaps({
            str(getattr(p, "kind", "")): relations_of(p) for p in ports
            if getattr(p, "kind", None)
        })
        assert gaps == [], [g["reason"] for g in gaps]

    def test_the_model_actually_HAS_pairs(self, rows):
        """Guards the assertion above from being green because nothing declares
        an inverse at all — the failure mode that made three denylist entries
        inert while still being counted."""
        pairs = [
            (r["kind"], name)
            for r in rows
            for name, rel in sorted(r["relations"].items())
            if rel.inverse_of
        ]
        assert len(pairs) >= 4, (
            f"only {len(pairs)} relation(s) declare an inverse — the pairing "
            "guard above is passing vacuously"
        )

    def test_the_measured_pairs_are_the_two_the_model_has(self, rows):
        """Named, because these are the two the founder measured as broken:
        Epic⇄Feature and Feature⇄Story, each expressed as two edges with
        nothing saying they were halves of one relation."""
        by_kind = {r["kind"]: r["relations"] for r in rows}
        assert by_kind["Epic"]["features"].inverse_of == "epic"
        assert by_kind["Feature"]["epic"].inverse_of == "features"
        assert by_kind["Feature"]["stories"].inverse_of == "feature"
        assert by_kind["Story"]["feature"].inverse_of == "stories"


class TestTheLiveAnswerIsWellFormed:
    def test_every_unresolved_row_carries_a_known_origin(self, graph):
        assert graph["unresolved"], "the gap list is not empty in this registry"
        assert {u["origin"] for u in graph["unresolved"]} <= set(UNRESOLVED_ORIGINS)

    def test_the_origin_counts_match_the_rows_they_describe(self, graph):
        counted = graph["coverage"]["unresolved_by_origin"]
        for origin in UNRESOLVED_ORIGINS:
            actual = sum(1 for u in graph["unresolved"] if u["origin"] == origin)
            assert counted[origin] == actual

    def test_no_field_is_both_a_gap_and_a_declared_relation(self, graph):
        """One field, one classification. ``Engram.source_refs`` was reported
        as a gap while being a real reference; it must not now be both."""
        gaps = {(u["kind"], u["field"]) for u in graph["unresolved"]
                if u["origin"] == "undeclared"}
        drawn = {(e["from_kind"], e["field"]) for e in graph["edges"]}
        assert gaps & drawn == set()

    def test_the_composite_family_is_classified_together(self, graph):
        """The three fields the hand table split: one was undeclarable, two
        were gaps, one rule. They are three DECLARED relations now, drawn with
        the same target token and the same honesty about not being enforced."""
        edges = {(e["from_kind"], e["field"]): e for e in graph["edges"]}
        for pair in [("Comment", "target_ref"), ("Engram", "source_refs"),
                     ("SourceArtifact", "derived_refs")]:
            assert pair in edges, f"{pair} is not declared as a relation"
            assert edges[pair]["to_kind"] == POLYMORPHIC_TARGET == ANY_TARGET
            assert edges[pair]["enforced"] is False

    def test_the_produces_family_left_the_inexpressible_bucket(self, graph):
        """Eight ``produces``/``produced_artifacts`` fields were reported as
        references the model could not express. They were merely undeclared;
        every one is a first-class relation now."""
        declared = {
            e["from_kind"] for e in graph["edges"] if e["field"] == "produces"
        }
        assert {"Epic", "Feature", "Story", "Issue", "Bug", "Task",
                "Spike"} <= declared

    def test_the_enforced_count_is_derived_from_the_edges(self, graph):
        """A counter that reports intentions is the enumeration failure wearing
        a derivation's name — the exact defect ``coverage.suppressed`` had
        (8 reported, 5 performed)."""
        assert graph["coverage"]["enforced"] == sum(
            1 for e in graph["edges"] if e["enforced"]
        )

    def test_the_key_addressed_relations_are_drawn_and_NOT_enforced(self, graph):
        """The five rows of the retired ``UNDECLARABLE`` table. They are edges
        now — declared, drawable, with a named target — and the ``enforced``
        flag is what keeps that from over-claiming."""
        edges = {(e["from_kind"], e["field"]): e for e in graph["edges"]}
        for pair, target, key in [
            (("Project", "workspace_id"), "Workspace", "workspace_id"),
            (("WorkspaceMembership", "workspace_id"), "Workspace", "workspace_id"),
            (("WorkspaceMembership", "role"), "Role", "role_id"),
            (("Membership", "role"), "Role", "role_id"),
            (("Organization", "plan_ref"), "PricingPlan", "tier_id"),
        ]:
            assert pair in edges, f"{pair} left the graph entirely"
            assert edges[pair]["to_kind"] == target
            assert edges[pair]["by"] == key
            assert edges[pair]["enforced"] is False


class TestACompositePointerSaysWhatItPointsAt:
    """``to: "*"`` used to mean two things at once and could only be written for
    one of them. 21 of the 47 declared edges in this registry pointed at ``*``
    on 06/08/2026 — so the graph knew a link existed and could not say WHAT it
    linked to, and *"which TestGuides verify this Story?"* had no answer, only
    *"which TestGuides verify something"*.

    These tests hold the two halves of the fix apart: the pointers that ARE
    typed must stay typed, and the ones that stay open must SAY they are open
    on purpose rather than merely be untyped."""

    #: Every relation that may keep ``to: "*"``, with the reason it is open BY
    #: DESIGN. An allowlist, not a denylist: nothing here is being suppressed —
    #: it is the invariant "a pointer with no declared target owes an
    #: explanation", written where a new one cannot be added in silence. The
    #: reason lives beside each declaration too; this is where a REVIEWER is
    #: made to have read it.
    OPEN_BY_DESIGN = {
        ("AgentSession", "produced_artifacts"): "the produces hub — any Kind",
        ("Bug", "produces"): "the produces hub — any Kind",
        ("Comment", "target_ref"): "a comment can be left on any instance",
        ("Engram", "affect_evidence_refs"): "evidence is whatever was in hand",
        ("Engram", "source_refs"): "a memory derives from anything",
        ("Epic", "produces"): "the produces hub — any Kind",
        ("Evidence", "document_ref"): "post_save fires for every Kind written",
        ("Feature", "produces"): "the produces hub — any Kind",
        ("Issue", "produces"): "the produces hub — any Kind",
        ("Research", "cited_by"): "`dna sdlc cite` joins ANY two Kinds",
        ("SourceArtifact", "derived_refs"): "extraction yields any Kind",
        ("Spike", "produces"): "the produces hub — any Kind",
        ("StatusReport", "evidence_refs"): "evidence for a verdict is anything",
        ("Story", "produces"): "the produces hub — any Kind",
        ("Task", "produces"): "the produces hub — any Kind",
        ("TestRun", "evidence"): "entries are refs OR bare URLs OR prose",
    }

    #: The work-item family, spelled out ONCE here. Not imported from
    #: ``sdlc_family``: this file is the oracle, and an oracle that reads the
    #: same constant the code reads proves only that a name is spelled the same
    #: way twice.
    _WORK_ITEMS = {"Bug", "Epic", "Feature", "Initiative", "Issue", "Spike",
                   "Story", "Task"}
    _JOURNEY_ANCHORS = {"AgentSession", "Epic", "Feature", "Narrative", "Plan",
                        "Roadmap", "Spec", "Story"}

    def test_the_typed_composites_name_their_targets(self, rows):
        """The six that were untyped and are not any more. Named one by one,
        because a COUNT would go green on any six."""
        by_kind = {r["kind"]: r["relations"] for r in rows}
        for kind, field, expected in [
            ("Kaizen", "work_item", self._WORK_ITEMS),
            ("TestGuide", "verifies", self._WORK_ITEMS),
            ("TestRun", "verifies", self._WORK_ITEMS),
            ("Engram", "area", {"Epic", "Feature", "Roadmap"}),
            ("WorkflowEvent", "ref", self._JOURNEY_ANCHORS),
            ("WorkflowEvent", "parent_ref", self._JOURNEY_ANCHORS),
        ]:
            rel = by_kind[kind][field]
            assert set(rel.to) == expected, f"{kind}.{field}"
            # THE mutant: typing a composite must not start RESOLVING it. If
            # `resolved` flips, the write path begins parsing `Story/s-x` as an
            # instance name and vetoes every value already stored.
            assert rel.resolved is False, f"{kind}.{field} became resolved"
            assert rel.carries_kind is True, f"{kind}.{field}"
            assert rel.open_target is False, f"{kind}.{field}"

    def test_a_typed_composite_becomes_REAL_edges_on_the_wire(self, graph):
        """Through the door a consumer actually uses. One `*` edge answered
        "it points at something"; the typed ones answer "which Kaizens came out
        of this Story"."""
        targets = {
            e["to_kind"] for e in graph["edges"]
            if (e["from_kind"], e["field"]) == ("Kaizen", "work_item")
        }
        assert ANY_TARGET not in targets
        assert {"Story", "Issue", "Spike"} <= targets

    def test_every_remaining_star_relation_is_declared_open_on_purpose(self, rows):
        """The invariant, as a guard. A NEW relation pointing at `*` fails here
        until somebody writes down why it is open — which is the whole
        difference between "this can point at anything, by design" and "nobody
        typed it". The two render identically on a screen; this file is what
        tells them apart."""
        undocumented = sorted(self._open(rows) - set(self.OPEN_BY_DESIGN))
        assert undocumented == [], (
            "these relations point at `*` with no recorded reason. If the "
            "target really is unconstrained, add it to OPEN_BY_DESIGN with the "
            "reason; otherwise declare `to: [Kind, ...]` — a composite `by` no "
            f"longer forces `*`: {undocumented}"
        )

    def test_the_allowlist_has_no_row_the_registry_lost(self, rows):
        """The other direction, and the one enumerated tables always miss: a
        relation that gets TYPED (or deleted) must leave this list, or the list
        slowly becomes a record of a registry that no longer exists — which is
        exactly how ``UNDECLARABLE`` came to cite a Kind called ``Tier``."""
        stale = sorted(set(self.OPEN_BY_DESIGN) - self._open(rows))
        assert stale == [], f"OPEN_BY_DESIGN rows nothing declares any more: {stale}"

    @staticmethod
    def _open(rows) -> set:
        return {
            (r["kind"], name)
            for r in rows
            for name, rel in r["relations"].items()
            if rel.open_target
        }


class TestTheCoverageProseStaysTrue:
    def test_no_coverage_prose_names_a_retired_kind(self, registered):
        """The limits travel on the wire, and prose is where a rename hides:
        the retired denylist carried ``Tier`` AND ``AccountPlan`` in prose a
        machine did not read. Every backticked CamelCase token must resolve."""
        dead = sorted({
            token
            for limit in COVERAGE_LIMITS
            for token in _KIND_LIKE.findall(limit["detail"])
            if token not in registered
        })
        assert dead == [], (
            f"kind_graph prose names Kinds the registry does not have: {dead}"
        )
