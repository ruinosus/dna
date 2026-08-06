"""Kind traits — the open registry a Kind uses to declare what it PARTICIPATES in.

A trait answers "does this Kind take part in X?" for an X the kernel itself has
no opinion about. It is the third instance of a mechanism the SDK had already
built twice and then declined to generalise:

* :meth:`dna.kernel.Kernel._classify_kinds` — derives a set of Kind names from a
  declared attribute, but only for BOOLEAN attributes the kernel knows by name;
* :func:`dna.kernel.meta.register_schema_fragment` — an OPEN, namespaced,
  process-global registry extensions add to, which is exactly the shape a trait
  vocabulary needs.

Traits are the two joined: an open, namespaced vocabulary, resolved by lookup
(``kernel.kinds_with_trait("sdlc.work-item")``) rather than by a literal list in
whichever module needed one.

**Open, not an enum.** :func:`register_trait` exists for discoverability and
documentation — ``dna kind traits`` lists what the running distribution knows
about — but declaring an unregistered trait is NOT an error. An extension that
ships a Kind and a consumer of that Kind must not have to patch a core enum to
introduce a vocabulary only the two of them share. What registration buys is a
description; what it never buys is a veto.

**Namespaced by convention**, mirroring ``schema_fragments``: ``<owner>/<name>``
or ``<owner>.<name>`` (``sdlc.work-item``, ``memory.recallable``). A trait with
no namespace is legal and reads as core-owned.
"""
from __future__ import annotations

from typing import Any, Iterable

__all__ = [
    "CORE_TRAITS",
    "known_traits",
    "normalize_traits",
    "port_has_trait",
    "port_traits",
    "register_trait",
    "trait_description",
]


#: name → human description. Process-global, exactly like ``_SCHEMA_FRAGMENTS``.
_TRAITS: dict[str, str] = {}


def register_trait(name: str, description: str) -> None:
    """Instance a trait so ``dna kind traits`` can list it.

    Idempotent; a later call replaces the description. Registration is
    DOCUMENTATION — nothing checks a declared trait against this registry, by
    design (see the module docstring)."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("trait name must be a non-empty string")
    _TRAITS[name.strip()] = description


def known_traits() -> dict[str, str]:
    """Every registered trait → its description (a copy; sorted by name)."""
    return {k: _TRAITS[k] for k in sorted(_TRAITS)}


def trait_description(name: str) -> str | None:
    """The registered description for ``name``, or ``None`` if undocumented."""
    return _TRAITS.get(name)


def _reset_traits() -> None:
    """Test-only: clear the registry (mirrors ``_reset_schema_fragments``)."""
    _TRAITS.clear()


def normalize_traits(raw: Any) -> frozenset[str]:
    """A declared ``traits:`` value → a clean frozenset.

    Accepts a list / tuple / set / frozenset of strings (or ``None``). Blank
    entries are dropped and whitespace trimmed, so a YAML author's stray space
    never produces a trait nobody can look up. Anything else raises."""
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        raise ValueError(
            f"traits must be a list of strings, got a bare string {raw!r} — "
            f"write `traits: [{raw}]`"
        )
    if not isinstance(raw, (list, tuple, set, frozenset)):
        raise ValueError(
            f"traits must be a list of strings, got {type(raw).__name__}"
        )
    out: set[str] = set()
    for entry in raw:
        if not isinstance(entry, str):
            raise ValueError(
                f"every trait must be a string, got {type(entry).__name__}: {entry!r}"
            )
        cleaned = entry.strip()
        if cleaned:
            out.add(cleaned)
    return frozenset(out)


def port_traits(port: Any) -> frozenset[str]:
    """The traits a ``KindPort`` declares — ``frozenset()`` for a port that
    declares none.

    ``getattr`` with a default rather than an attribute access: ``KindPort`` is
    a ``runtime_checkable`` Protocol whose ``isinstance`` check tests member
    PRESENCE, so ``traits`` deliberately is not a Protocol member and a
    KindPort-direct implementation is free not to have one."""
    return normalize_traits(getattr(port, "traits", None) or None)


def port_has_trait(port: Any, trait: str) -> bool:
    """Whether ``port`` declares ``trait``."""
    return trait in port_traits(port)


# ── the core vocabulary ─────────────────────────────────────────────────────
#
# Registered here so the descriptions live with the definition rather than in a
# doc that drifts. Extensions register their own in ``register(kernel)``.

CORE_TRAITS: dict[str, str] = {
    "sdlc.work-item": (
        "A board item with a status arc, a timeline and an owner — the thing a "
        "person is assigned and closes. Participates in the digest, the gallery, "
        "status transitions, comments and produces[] links."
    ),
    "sdlc.decision": (
        "A recorded decision (ADR). Walked by the digest and the gallery, and it "
        "may produce outputs, but it is not assigned and does not progress."
    ),
    "sdlc.observation": (
        "A filed observation (Kaizen) — noticed, not planned. Reaches the "
        "digest's `found` bucket; carries no `updated_at` arc."
    ),
    "sdlc.rollup": (
        "A work item that AGGREGATES other work items (Feature / Epic / "
        "Initiative). Movement at this level is roadmap movement, which is what "
        "the digest's `parents_progressed` bucket reports."
    ),
    "sdlc.filed": (
        "Enters the board by being FILED rather than planned — the digest's "
        "`found` bucket (Issue, Kaizen)."
    ),
    "sdlc.journey-derived": (
        "Its journey phases are derived locally from its own spec + timeline "
        "(no WorkflowEvent ledger read)."
    ),
    "sdlc.dated": (
        "Carries `created_at` AND `updated_at`: a read surface dates, sorts or "
        "windows it by both."
    ),
    "sdlc.dated-create-only": (
        "Carries `created_at` but has no `updated_at` arc — an observation is "
        "dated when it is made and does not move."
    ),
    "sdlc.exit-criteria-required": (
        "A create of this Kind is REFUSED without acceptance criteria and a "
        "definition of done — a work item that does not declare what `done` "
        "means cannot be shown to be done."
    ),
    "sdlc.test-gated": (
        "A CLOSE of this Kind is REFUSED without a passing product-lane TestRun "
        "verifying it. The escape hatches require a reason and land on the "
        "timeline."
    ),
    "governance.spec-traced": (
        "A write of this Kind must trace to a Spec when the scope's constitution "
        "demands it (the spec-kit governance guard)."
    ),
    "record.append-only": (
        "An audit / evidence record: it may be WRITTEN and READ but never "
        "deleted through a generic tool. The record is what proves what "
        "happened, so deleting it is the first move of anyone with something "
        "to hide — and unlike a bad write, it is not recoverable by writing a "
        "better one."
    ),
    "memory.recallable": (
        "Participates in `recall` / `remember` / the memory index — the set the "
        "memory verbs search. DISTINCT from `embed:`, which declares WHICH "
        "FIELDS carry an embeddable payload: an ADR should be searchable without "
        "being decay-ranked as a memory."
    ),
}

for _name, _desc in CORE_TRAITS.items():
    register_trait(_name, _desc)


def traits_from_names(names: Iterable[str]) -> frozenset[str]:
    """Convenience for class Kinds: ``traits = traits_from_names([...])``."""
    return normalize_traits(list(names))
