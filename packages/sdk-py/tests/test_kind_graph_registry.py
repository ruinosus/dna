"""The graph's hand-kept tables, checked against the LIVE registry.

``test_kind_graph.py`` is pure — it builds fake ports and never a Kernel, which
is what makes it fast and total. But two of the projection's inputs are TABLES
somebody types by hand (``UNDECLARABLE``, ``INFERENCE_DENYLIST``), and a table
of Kind names is a set of names that can be renamed somewhere else. Purity
cannot see that: a fake port called ``Tier`` exists because the test made it.

It happened. The metering rename turned ``Tier`` into ``PricingPlan``
(dna 0.29.0) and ``UNDECLARABLE`` went on answering
``{"kind": "Organization", "field": "plan_ref", "target": "Tier"}`` while
``GET /v1/kinds/registry/Tier`` returned 404 — a graph citing a Kind the same
deployment says does not exist. Nothing failed, because nothing compared the
table to the registry. The docs guard could not: it regenerates the page FROM
the table, so both sides carried the same dead name and agreed.

That is what this file is. The oracle is the registry, so these tests have no
vocabulary of their own to drift, and a rename that misses these tables fails
HERE — before the wire, not on somebody's screen.
"""
from __future__ import annotations

import re

import pytest

from dna.kernel.query.kind_graph import (
    COVERAGE_LIMITS,
    INFERENCE_DENYLIST,
    POLYMORPHIC_TARGET,
    UNDECLARABLE,
    UNRESOLVED_ORIGINS,
    _normalize,
    build_kind_graph,
    kind_rows,
    suppressed_for,
    target_index,
)

#: A backticked token that LOOKS like a Kind name: CamelCase, no separators.
#: Deliberately narrow — `tier_id`, `x-dna-ref` and `Kind:name` are not Kind
#: names and must not be accused of being retired ones.
_KIND_LIKE = re.compile(r"`([A-Z][A-Za-z]*)`")


@pytest.fixture(scope="module")
def rows():
    from dna.kernel import Kernel

    return kind_rows(Kernel.auto().kind_ports())


@pytest.fixture(scope="module")
def registered(rows):
    return {r["kind"] for r in rows}


class TestTheTablesCiteLiveKinds:
    def test_every_undeclarable_target_is_a_registered_kind(self, registered):
        """THE mutant this file exists to kill: ``Organization.plan_ref ->
        Tier`` after ``Tier`` became ``PricingPlan``."""
        dead = [
            f"{kind}.{field} -> {target}"
            for (kind, field), (target, _) in sorted(UNDECLARABLE.items())
            if target != POLYMORPHIC_TARGET and target not in registered
        ]
        assert dead == [], (
            "UNDECLARABLE names Kinds no registry provides — a rename passed "
            f"this table by: {dead}"
        )

    def test_every_undeclarable_source_is_a_registered_kind(self, registered):
        """A row whose OWN Kind is gone is dead weight that still costs a
        reader's attention. The table only shrinks."""
        orphans = [f"{kind}.{field}" for (kind, field) in sorted(UNDECLARABLE)
                   if kind not in registered]
        assert orphans == [], f"UNDECLARABLE rows for retired Kinds: {orphans}"

    def test_every_undeclarable_field_still_exists_on_its_kind(self, rows):
        """Suppressing a field that was removed suppresses nothing, and the
        row's justification quietly stops being about anything."""
        props = {r["kind"]: r["properties"] for r in rows}
        gone = [f"{kind}.{field}" for (kind, field) in sorted(UNDECLARABLE)
                if kind in props and field not in props[kind]]
        assert gone == [], f"UNDECLARABLE names fields that are gone: {gone}"

    def test_every_denylist_source_is_a_registered_kind(self, registered):
        orphans = [f"{kind}.{field}"
                   for (kind, field) in sorted(INFERENCE_DENYLIST)
                   if kind not in registered]
        assert orphans == [], f"INFERENCE_DENYLIST rows for retired Kinds: {orphans}"

    def test_every_denylist_entry_is_still_about_a_live_field(self, rows):
        """An entry naming a field that no longer exists suppresses nothing and
        can never fire again — dead weight, unlike an inert-but-live one."""
        props = {r["kind"]: r["properties"] for r in rows}
        gone = [f"{kind}.{field}"
                for (kind, field) in sorted(INFERENCE_DENYLIST)
                if kind in props and field not in props[kind]]
        assert gone == [], f"INFERENCE_DENYLIST names fields that are gone: {gone}"

    def test_the_suppressed_count_is_what_the_pass_did_not_what_the_table_says(
        self, rows,
    ):
        """The second-order casualty of the same rename, measured 06/08/2026.

        ``plan`` became AMBIGUOUS when ``PricingPlan`` joined ``Plan``, so the
        three ``plan``/``plan_ref`` denylist entries stopped firing — ambiguity
        stops those matches now. The table still listed them and
        ``coverage.suppressed`` still counted them: 8 reported, 5 performed. A
        counter that reports intentions is the enumeration failure wearing a
        derivation's name.
        """
        _, by_token = target_index(rows)
        props = {r["kind"]: r["properties"] for r in rows}
        live = {
            (kind, field) for (kind, field) in INFERENCE_DENYLIST
            if field in props.get(kind, {}) and by_token.get(_normalize(field))
        }
        reported = {(s["source"], s["field"]) for s in suppressed_for(rows)}
        assert reported == live
        assert len(live) < len(INFERENCE_DENYLIST), (
            "this registry no longer has an inert entry — good, but then the "
            "assertion below is testing nothing; check before deleting it"
        )
        assert build_kind_graph(_ports(rows))["coverage"]["suppressed"] == len(live)

    def test_no_table_prose_names_a_retired_kind(self, registered):
        """The justifications name Kinds too, and prose is where a rename hides.

        ``UNDECLARABLE`` carried ``Tier`` in a field a machine reads; the
        denylist carried ``Tier`` AND ``AccountPlan`` in prose a machine did
        not. Both were dead. Every backticked CamelCase token in these tables
        (and in the coverage limits, which travel on the wire) must resolve.
        """
        prose = (
            list(INFERENCE_DENYLIST.values())
            + [why for _, why in UNDECLARABLE.values()]
            + [limit["detail"] for limit in COVERAGE_LIMITS]
        )
        dead = sorted({
            token for text in prose for token in _KIND_LIKE.findall(text)
            if token not in registered
        })
        assert dead == [], (
            f"kind_graph prose names Kinds the registry does not have: {dead}"
        )


class TestTheLiveAnswerIsWellFormed:
    def test_every_unresolved_row_carries_a_known_origin(self, rows):
        graph = build_kind_graph(_ports(rows))
        assert graph["unresolved"], "the gap list is not empty in this registry"
        assert {u["origin"] for u in graph["unresolved"]} <= set(UNRESOLVED_ORIGINS)

    def test_the_origin_counts_match_the_rows_they_describe(self, rows):
        graph = build_kind_graph(_ports(rows))
        counted = graph["coverage"]["unresolved_by_origin"]
        for origin in UNRESOLVED_ORIGINS:
            actual = sum(1 for u in graph["unresolved"] if u["origin"] == origin)
            assert counted[origin] == actual

    def test_no_field_is_both_a_gap_and_an_undeclarable_reference(self, rows):
        """One field, one classification. ``Engram.source_refs`` was a gap
        while being a real reference; it must not now be both."""
        graph = build_kind_graph(_ports(rows))
        gaps = {(u["kind"], u["field"]) for u in graph["unresolved"]}
        known = {(u["kind"], u["field"]) for u in graph["undeclarable"]}
        assert gaps & known == set()

    def test_the_composite_family_is_classified_together(self, rows):
        """The three fields the hand table split: one was undeclarable, two
        were gaps. Same rule, same bucket, and the shape is what says so."""
        graph = build_kind_graph(_ports(rows))
        known = {(u["kind"], u["field"]): u for u in graph["undeclarable"]}
        for pair in [("Comment", "target_ref"), ("Engram", "source_refs"),
                     ("SourceArtifact", "derived_refs")]:
            assert pair in known, f"{pair} is not classified as undeclarable"
            assert known[pair]["target"] == POLYMORPHIC_TARGET


def _ports(rows):
    """Replay the measured rows as ports — the graph's own input, once."""
    class _Row:
        def __init__(self, row):
            self.kind = row["kind"]
            self.alias = row["alias"]
            self.plane = row["plane"]
            self.dep_filters = row["dep_filters"]
            self._schema = {"properties": row["properties"]}

        def schema(self):
            return self._schema

    return [_Row(r) for r in rows]
