"""Composite pointers cannot be DERIVED — so derive the QUESTION instead.

WHAT HAPPENED. ``x-dna-ref-composite`` was added and applied by hand to
``Engram.source_refs`` and ``SourceArtifact.derived_refs``. The hand missed
``Engram.affect_evidence_refs`` — the SAME family, in the SAME Kind, nine
fields away — and nothing went red. That is the failure this repo already has
a name for (``guardas-enumeracao-vs-derivacao``): the classification was
correct and the enumeration was incomplete, which is invisible by construction.

CAN THE CLASSIFICATION BE DERIVED? Half of it already is, and the half that
cannot be is precisely the half that got missed:

* **Object-shaped composites ARE derived.** ``_composite_form_from_shape``
  recognizes an object (or array of objects) that REQUIRES both ``kind`` and
  ``name``. Nobody enumerated ``Story.produces`` and its seven siblings; they
  appeared because the shape says what they are. That is why the
  ``undeclarable`` list jumped 6 → 16 without a table growing.

* **String-shaped composites CANNOT be.** ``Engram.affect_evidence_refs`` is
  ``{"type": "array", "items": {"type": "string"}}`` — **byte-identical** to
  ``Story.dependencies`` (a plain by-name reference) and to ``Story.labels``
  (not a reference at all). Three different meanings, one schema. There is
  nothing in the schema to derive from; the only remaining evidence is the
  DESCRIPTION, and classifying from prose is guessing — the exact practice
  ``x-dna-ref`` exists to end. This module measures that too: the same prose
  scan that finds the real ones also produces the false positives enumerated
  in :data:`NOT_A_POINTER`, and there are enough of them that a prose-driven
  classifier would be wrong about a third of the time.

SO: derive the OBLIGATION. This guard scans every registered Kind for a
string-valued field whose description shows a ``Kind/name``-shaped token, and
requires each one to carry either ``x-dna-ref`` (resolvable by name) or
``x-dna-ref-composite`` (carries its own Kind) — or to be listed below with a
reason. Forgetting one is now a red test instead of a silent gap.

:data:`NOT_A_POINTER` is SHRINK-ONLY by convention, like the inference
denylist: an entry leaves when the field gets a real annotation, and never
grows to paper over a guess.
"""
from __future__ import annotations

import re

import pytest

from dna.kernel import Kernel
from dna.kernel.query.references import (
    composite_references,
    declared_references,
)

# --- fields the prose scan flags and that are NOT pointers -------------------
# Each is a false positive of the description heuristic, confirmed against the
# field's own schema. Listing them is what keeps the heuristic honest: a
# classifier that silently dropped its own misses would look more accurate
# than it is.
NOT_A_POINTER: dict[tuple[str, str], str] = {
    **{
        (kind, "journey_phase"): (
            "an ENUM of the five universal phases; the description merely "
            "mentions 'Story/Feature/Epic status' as prose"
        )
        for kind in ("Epic", "Feature", "Issue", "Narrative", "Story")
    },
    ("PricingPlan", "definitions_mode"): (
        "an ENUM (read/write); the description names the `definitions` "
        "feature family in prose"
    ),
    ("Kaizen", "issue"): (
        "a bare SLUG — 'Issue/Story' in the description is an alternation "
        "between two Kinds, not a composite value. A polymorphic "
        "`x-dna-ref: [Issue, Story]` is the right declaration and is tracked "
        "separately"
    ),
    ("Initiative", "theme_ref"): (
        "a bare SLUG — 'Theme/OKR Objective' is prose alternation. A plain "
        "`x-dna-ref: Theme` is the right declaration, tracked separately"
    ),
}


def _kind_names(kernel: Kernel) -> list[str]:
    return sorted({p.kind for p in kernel.kind_ports()})


def _pattern(kinds: list[str]) -> re.Pattern:
    """`Kind/name`, `Kind:name`, or a REGISTERED Kind followed by `/` or `:`.

    Built from the live registry rather than a literal list, so a new Kind is
    covered the day it registers — the derivation this module is about.
    """
    alt = "|".join(re.escape(k) for k in kinds)
    return re.compile(
        r"\bKind\s*[/:]\s*(name|slug)\b"
        r"|\b(" + alt + r")\s*[/:]\s*[<A-Za-z0-9_\-]"
    )


def _stringish(prop: dict) -> bool:
    """String, nullable string, or array-of-string — the underivable shapes.

    Object-shaped composites are excluded on purpose: those the runtime
    already recognizes without help, and re-checking them here would let this
    guard take credit for work the derivation does.
    """
    t = prop.get("type")
    if t == "string" or (isinstance(t, list) and "string" in t):
        return True
    if t == "array":
        items = prop.get("items")
        return isinstance(items, dict) and items.get("type") == "string"
    return False


def _candidates(kernel: Kernel) -> list[tuple[str, str, str]]:
    """(Kind, field, description) for every string field that LOOKS composite."""
    pattern = _pattern(_kind_names(kernel))
    out: list[tuple[str, str, str]] = []
    for port in kernel.kind_ports():
        try:
            schema = port.schema() or {}
        except Exception:  # noqa: BLE001 — a broken schema is another test's job
            continue
        for field, prop in sorted((schema.get("properties") or {}).items()):
            if not isinstance(prop, dict) or not _stringish(prop):
                continue
            description = " ".join(str(prop.get("description") or "").split())
            if pattern.search(description):
                out.append((port.kind, field, description))
    return sorted(out)


@pytest.fixture(scope="module")
def kernel() -> Kernel:
    return Kernel.auto()


def test_every_composite_shaped_field_is_annotated_or_justified(kernel):
    """THE guard. A candidate must be declared, composite, or listed."""
    unannotated: list[str] = []
    for kind, field, description in _candidates(kernel):
        if (kind, field) in NOT_A_POINTER:
            continue
        port = kernel.kind_port_for(kind)
        declared = {r.field for r in declared_references(port)}
        composite = {c.field for c in composite_references(port)}
        if field in declared or field in composite:
            continue
        unannotated.append(f"  {kind}.{field} :: {description[:120]}")
    assert not unannotated, (
        "Reference-shaped by its own description, and annotated by neither "
        "`x-dna-ref` nor `x-dna-ref-composite`:\n"
        + "\n".join(unannotated)
        + "\n\nAdd the annotation, or add the field to NOT_A_POINTER in this "
        "module with the reason its description misleads."
    )


def test_the_scan_actually_finds_the_known_composites(kernel):
    """Kills the mutant where the pattern matches nothing and passes.

    A guard whose scan returns an empty candidate list is green forever. These
    five are the ones a human confirmed one by one; if the scan stops seeing
    them, the guard above has stopped guarding.
    """
    found = {(k, f) for k, f, _ in _candidates(kernel)}
    for expected in [
        ("Engram", "affect_evidence_refs"),   # the one the hand missed
        ("Engram", "source_refs"),
        ("Comment", "target_ref"),
        ("WorkflowEvent", "ref"),
        ("TestGuide", "verifies"),
    ]:
        assert expected in found, f"the description scan no longer sees {expected}"


def test_the_missed_sibling_is_annotated_like_its_siblings(kernel):
    """The specific regression, named.

    `Engram.affect_evidence_refs` and `Engram.source_refs` are the same family
    in the same Kind. One was annotated and the other was not, for a week.
    """
    forms = {c.field: c.form for c in composite_references(kernel.kind_port_for("Engram"))}
    assert forms.get("affect_evidence_refs") == "Kind/name"
    assert forms.get("source_refs") == "Kind/name"
    assert forms.get("area") == "Kind/name"


def test_not_a_pointer_entries_still_describe_real_fields(kernel):
    """Shrink-only means the list must not outlive its fields.

    A justification for a field that no longer exists is the same defect as a
    stale denylist row: it reads as a considered decision and describes
    nothing.
    """
    for (kind, field), why in NOT_A_POINTER.items():
        port = kernel.kind_port_for(kind)
        assert port is not None, f"NOT_A_POINTER names unregistered Kind {kind}"
        assert field in (port.schema() or {}).get("properties", {}), (
            f"NOT_A_POINTER[{kind}.{field}] describes a field that is gone"
        )
        assert why.strip(), f"NOT_A_POINTER[{kind}.{field}] has no reason"


def test_object_shaped_composites_need_no_annotation(kernel):
    """The half that IS derived, pinned so nobody 'fixes' it by enumerating.

    `Story.produces` is an array of objects requiring `kind` + `name`. Nothing
    declares it; the SHAPE says what it is. That derivation is why this guard
    only has to cover the string-shaped half.
    """
    port = kernel.kind_port_for("Story")
    produces = {c.field: c for c in composite_references(port)}.get("produces")
    assert produces is not None, "the object-shape derivation stopped working"
    assert produces.declared is False, (
        "Story.produces gained a hand-written annotation — it is DERIVED from "
        "its shape, and hand-annotating it re-creates the enumeration this "
        "module exists to prevent"
    )
    assert produces.form == "{kind, name}"
