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
        # Initiative never declared `produces` in its own `relations` and never
        # will: it arrived when `sdlc.work-item` started CARRYING the relation
        # (a0822a34), and stays after the seven hand-written copies were
        # deleted. Same reason as its siblings — an Initiative is a rollup work
        # item, so it authors artifacts of any Kind.
        ("Initiative", "produces"): "the produces hub — any Kind",
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


class TestTheGapListIsFiniteAndExplained:
    """The other half of i-108. A reference-SHAPED field with no relation is
    reported as an ``undeclared`` gap — an honest invitation that, until
    ``spec.identifiers`` existed, could never be ANSWERED. Two thirds of the 25
    rows on 06/08/2026 were not references at all (an OAuth ``client_id``, a
    Stripe customer id, ``Sprint.sprint_id`` naming its own instance), so the
    list was permanent by construction and a screen could not tell a real
    broken reference from an id.

    The invariant this class holds: **every remaining row is a row somebody
    decided to leave**, and the decision is written down."""

    #: The gaps that stay, and why each is NOT answerable today. A row leaves
    #: this list by being declared (a relation or an identifier) or by the
    #: reason ceasing to hold — and either way somebody has to come here and
    #: say so. Two, and the reasons are two different kinds of honest.
    #:
    #: ``("PlanBinding", "tier_id")`` LEFT this list on 06/08/2026 (i-119,
    #: founder decision 2), and the test below going red is how it left. Its
    #: reason used to read "a relation honouring only `tier_id` would be a
    #: second rule free to veto a valid alias" — which described a mechanism
    #: ``by:`` does not have. A non-``name`` ``by`` is never
    #: ``Relation.resolved``, so it draws an edge, runs no lookup and can veto
    #: nothing; the alias fallback stays a search path. It is declared
    #: ``to: PricingPlan, by: tier_id``, and the alias is held open by
    #: ``TestKeyAddressedRelationsAreNotFollowed`` in
    #: ``test_write_path_reference_validation.py``.
    KNOWN_GAPS = {
        ("Initiative", "theme_ref"): (
            "a real reference to a Kind that does not exist. The registered "
            "`Theme` is the Studio COLOUR PALETTE (`helix-theme`), not the "
            "Jira-Align strategic Theme/OKR this field means — declaring it "
            "would draw the same false line the retired name-shape guess drew "
            "for `StatusReport.insight -> IntelInsight`"
        ),
        ("LayerPolicy", "layer_id"): (
            "not a reference and not expressible as an identifier either: it "
            "names a layer DIMENSION from a controlled vocabulary, matched by "
            "string equality. No authority mints it, so `external` would need "
            "a `system` that does not exist, and it is not this instance's "
            "key either. A third role is a decision, not a workaround"
        ),
    }

    def test_the_gap_list_holds_only_rows_somebody_decided_to_leave(self, graph):
        gaps = {(u["kind"], u["field"]) for u in graph["unresolved"]
                if u["origin"] == "undeclared"}
        unexplained = sorted(gaps - set(self.KNOWN_GAPS))
        assert unexplained == [], (
            "reference-shaped fields nobody has classified. Declare a relation "
            "(it points somewhere), or `spec.identifiers` (it does not), or "
            f"add it to KNOWN_GAPS with the reason it can be neither: {unexplained}"
        )

    def test_no_known_gap_row_has_quietly_been_fixed(self, graph):
        """The direction enumerated tables always miss. A row that gets
        declared must LEAVE this list, or it slowly becomes a record of a
        registry that no longer exists — how ``UNDECLARABLE`` came to cite a
        Kind called ``Tier``."""
        gaps = {(u["kind"], u["field"]) for u in graph["unresolved"]
                if u["origin"] == "undeclared"}
        stale = sorted(set(self.KNOWN_GAPS) - gaps)
        assert stale == [], f"KNOWN_GAPS rows that are no longer gaps: {stale}"

    def test_the_identifiers_travel_on_the_wire_with_their_reason(self, graph):
        """A screen must be able to render "this is an id, not a broken
        reference" without parsing English, so `role` and `system` ride along.
        Asserted by SHAPE and by two named rows, because a length check would
        pass on any seventeen."""
        rows = {(i["kind"], i["field"]): i for i in graph["identifiers"]}
        assert rows, "no Kind declares an identifier — the block is inert"
        for key, ident in rows.items():
            assert ident["role"] in ("self", "external"), key
            # `system` present as None on a `self`, never absent: a stable key
            # set is what lets a consumer type this without probing.
            assert "system" in ident, key
            assert (ident["system"] is not None) == (ident["role"] == "external"), key
        assert rows[("Sprint", "sprint_id")]["role"] == "self"
        assert rows[("PlanBinding", "stripe_customer_id")]["system"] == "stripe"

    def test_the_identifier_count_is_derived_from_the_rows(self, graph):
        """A counter that reports intentions is the enumeration failure wearing
        a derivation's name — the defect ``coverage.suppressed`` had."""
        assert graph["coverage"]["identifiers"] == len(graph["identifiers"])

    def test_no_field_is_both_an_edge_and_an_identifier(self, ports):
        """One field, one classification — across the WHOLE registry, which is
        the only place a class Kind and a descriptor Kind are both in hand.
        ``from_raw`` catches a descriptor declaring both; a hand-written Kind
        has no ``from_raw`` at all."""
        from dna.kernel.kinds.identifiers import (
            identifiers_of,
            schema_contradictions as identifier_contradictions,
        )

        problems = []
        for port in ports:
            try:
                schema = port.schema() or {}
            except Exception:  # pragma: no cover - defensive
                continue
            problems += [
                f"{getattr(port, 'kind', '?')}: {p}"
                for p in identifier_contradictions(
                    identifiers_of(port), relations_of(port), schema,
                )
            ]
        assert problems == [], problems


class TestThePersonStillComesFromTheIdP:
    """i-119, founder decision 1 (06/08/2026): the person is NOT a Kind.

    Five fields across four Kinds hold the same value — the identity provider's
    durable ``sub`` — and none of them points at an instance, because a Kind
    for the person would duplicate the IdP's source of truth and pull personal
    data into our store. They are islands BY DESIGN, and the point of declaring
    them is that "island by design" and "island nobody looked at" stop looking
    identical.

    ⚠️ WHY THIS ONE IS AN ENUMERATION AND THE GAP LIST IS NOT. The undeclared
    gap list is derived from a NAME SHAPE (``_id``/``_ref``/``_slug``), and
    three of these five — ``subject``, ``registered_by``, and ``owner`` next
    door — have no such shape. That invisibility is precisely why the group sat
    unclassified while the gap list read "finite and explained": there was
    nothing for a derivation to catch. So the enumeration here is the ANSWER to
    an invisibility, not a substitute for a derivation, and it is written to
    fail in BOTH directions — a row that loses its declaration, and a row that
    becomes a relation (which is the trigger firing, and somebody has to come
    here and say so).
    """

    #: field → the ``system`` it must name. All ``idp`` except the one that is
    #: ``self``: ``UserRoleAssignment``'s instance name IS the user_id, and
    #: ``system`` is FORBIDDEN beside ``self`` — bolting one on to make the row
    #: "say where it came from" would be inventing a number.
    THE_PERSON = {
        ("UserProfile", "user_id"): "idp",
        ("TenantMembership", "user_id"): "idp",
        ("AgentGrant", "subject"): "idp",
        ("AgentCatalogEntry", "registered_by"): "idp",
        ("UserRoleAssignment", "user_id"): None,   # `self` — see above
    }

    def test_every_person_field_is_classified_and_names_its_system(self, graph):
        rows = {(i["kind"], i["field"]): i for i in graph["identifiers"]}
        missing = sorted(set(self.THE_PERSON) - set(rows))
        assert missing == [], (
            "fields holding the IdP subject that no longer declare what they "
            f"are. The decision was to declare them, not to leave them: {missing}"
        )
        wrong = {
            key: (rows[key]["role"], rows[key]["system"])
            for key, system in self.THE_PERSON.items()
            if rows[key]["system"] != system
        }
        assert wrong == {}, f"person fields naming the wrong minting system: {wrong}"

    def test_no_person_field_became_a_relation_without_anybody_saying_so(
        self, rows,
    ):
        """The trigger that inverts the decision — the day a person carries
        data of OUR OWN, ``UserProfile`` becomes the anchor and these become
        ``to: UserProfile, by: user_id``. That is a good change and it must not
        arrive quietly: it lands here first."""
        by_kind = {r["kind"]: r["relations"] for r in rows}
        turned = sorted(
            f"{kind}.{field}"
            for kind, field in self.THE_PERSON
            if field in by_kind.get(kind, {})
        )
        assert turned == [], (
            "a person field is now a relation. If the trigger fired, say so "
            f"here and in the Kind: {turned}"
        )

    def test_oauth_mints_CLIENTS_and_the_idp_mints_PEOPLE(self, graph):
        """The confusion this group exists to prevent, asserted over the WHOLE
        registry rather than over the five rows above.

        ``AgentGrant`` and ``AgentCatalogEntry`` each hold both words at once —
        a ``client_id`` the authorization server minted and a person the
        identity provider minted — and a single word for both would model the
        third-party app and the human as one namespace, on the very screen
        built to tell them apart."""
        offenders = sorted(
            f"{i['kind']}.{i['field']}"
            for i in graph["identifiers"]
            if i["system"] == "oauth" and i["field"] != "client_id"
        )
        assert offenders == [], (
            "`oauth` mints CLIENTS. A field that is not a client_id claiming "
            f"it is naming the wrong authority: {offenders}"
        )


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
