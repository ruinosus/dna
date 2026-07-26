"""The SDLC work-item family, DERIVED — one trait, not thirteen lists.

Before this module the question "which Kinds are work items?" had thirteen
answers in thirteen modules, with thirteen different memberships: 4
(``_WRITABLE_KINDS``), 5 (``_WORK_ITEM_KINDS``, ``_BOARD_ITEM_KINDS``), 9
(``_GALLERY_WI_KINDS``, duplicated verbatim in ``_gallery.WORK_ITEM_KINDS``), 10
(``_DIGEST_KINDS``), 12 (``DATED_SPEC_FIELDS``). They were not deliberate
variations — they were the same intent, copied and then diverged. The proof is
in the tree: the v1.3 Milestone→Epic rename updated one list and missed another,
and Epic silently inherited across scopes for a release because of it
(``kernel/query/resolver.py``'s tombstone comment says so in full).

So membership moved onto the Kinds themselves as a trait, and every consumer
asks here. Adding a work item is now ONE declaration on ONE Kind:

    traits: [sdlc.work-item, sdlc.dated]

and it appears in the digest, the gallery, ``set_status``, ``comment``,
``produces``, the board probe and the date contract with no list edited. That
claim is a test (``test_sdlc_family_is_declarative``), not a comment.

Every function takes a live ``kernel`` — the registry is the source of truth,
and a family that could be computed without one would be a fourteenth list.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "TRAIT_DATED",
    "TRAIT_DATED_CREATE_ONLY",
    "TRAIT_DECISION",
    "TRAIT_FILED",
    "TRAIT_JOURNEY_DERIVED",
    "TRAIT_OBSERVATION",
    "TRAIT_ROLLUP",
    "TRAIT_WORK_ITEM",
    "board_probe_order",
    "dated_spec_fields",
    "digest_kinds",
    "filed_kinds",
    "journey_derived_kinds",
    "producer_kinds",
    "rollup_kinds",
    "status_enum_for",
    "status_enums",
    "transitionable_kinds",
    "work_item_kinds",
]

TRAIT_WORK_ITEM = "sdlc.work-item"
TRAIT_DECISION = "sdlc.decision"
TRAIT_OBSERVATION = "sdlc.observation"
TRAIT_ROLLUP = "sdlc.rollup"
TRAIT_FILED = "sdlc.filed"
TRAIT_JOURNEY_DERIVED = "sdlc.journey-derived"
TRAIT_DATED = "sdlc.dated"
TRAIT_DATED_CREATE_ONLY = "sdlc.dated-create-only"


def _sorted(names: frozenset[str]) -> tuple[str, ...]:
    """Deterministic order — a digest that walks Kinds in set order would emit
    a different `absent` list on every process."""
    return tuple(sorted(names))


def _with_trait(kernel: Any, trait: str) -> frozenset[str]:
    """``kernel.kinds_with_trait`` for a kernel that HAS one, else empty.

    Not defensiveness for its own sake: the SDK's write core is routinely handed
    a narrow duck-typed kernel (a test double, an adapter shim) that implements
    only ``get_document`` / ``write_document`` / ``query``. Such a caller gets
    the documented static fallback rather than an ``AttributeError`` from a
    module it never asked about — and the fallbacks are the pre-trait behavior
    exactly, so nothing it could do before stops working."""
    ask = getattr(kernel, "kinds_with_trait", None)
    if ask is None:
        return frozenset()
    try:
        return frozenset(ask(trait))
    except Exception:  # noqa: BLE001 — a registry that cannot answer says nothing
        return frozenset()


def work_item_kinds(kernel: Any) -> tuple[str, ...]:
    """The board items: a status arc, a timeline, an owner, a person who closes
    them (Story / Issue / Feature / Epic / Spike / Bug / Task / Initiative)."""
    return _sorted(_with_trait(kernel, TRAIT_WORK_ITEM))


def rollup_kinds(kernel: Any) -> tuple[str, ...]:
    """Work items that AGGREGATE work items (Feature / Epic / Initiative).
    Movement here is roadmap movement — see the digest's ``parents_progressed``."""
    return _sorted(_with_trait(kernel, TRAIT_ROLLUP))


def filed_kinds(kernel: Any) -> tuple[str, ...]:
    """Kinds that enter the board by being FILED rather than planned — the
    digest's ``found`` bucket."""
    return _sorted(_with_trait(kernel, TRAIT_FILED))


def journey_derived_kinds(kernel: Any) -> tuple[str, ...]:
    """Kinds whose journey phases derive from their own spec + timeline."""
    return _sorted(_with_trait(kernel, TRAIT_JOURNEY_DERIVED))


def producer_kinds(kernel: Any) -> tuple[str, ...]:
    """Kinds that may AUTHOR an output (``produces[]``) — work items plus
    recorded decisions. What the gallery walks."""
    return _sorted(
        _with_trait(kernel, TRAIT_WORK_ITEM) | _with_trait(kernel, TRAIT_DECISION)
    )


def digest_kinds(kernel: Any) -> tuple[str, ...]:
    """Every Kind whose timeline the digest walks — work items, decisions and
    observations."""
    return _sorted(
        _with_trait(kernel, TRAIT_WORK_ITEM)
        | _with_trait(kernel, TRAIT_DECISION)
        | _with_trait(kernel, TRAIT_OBSERVATION)
    )


def board_probe_order(kernel: Any) -> tuple[str, ...]:
    """The Kinds a board-card lookup probes when the caller pins no ``kind``.

    Sorted, so the probe is deterministic; a caller that cares which one wins a
    name collision should pin the Kind."""
    return work_item_kinds(kernel)


# ── the date contract (i-078), derived ──────────────────────────────────────


def dated_spec_fields(kernel: Any) -> dict[str, tuple[str, ...]]:
    """Kind → the spec date fields every write path owes the readers.

    Derived from two traits, so a new work item cannot repeat i-078 (an Issue
    that no writer stamped ``created_at`` on never reached the digest's ``found``
    bucket, in any window, permanently). ``sdlc.dated-create-only`` is the
    declared exception: an observation is dated when it is made and has no
    ``updated_at`` arc to report."""
    out: dict[str, tuple[str, ...]] = {
        k: ("created_at", "updated_at") for k in _with_trait(kernel, TRAIT_DATED)
    }
    for k in _with_trait(kernel, TRAIT_DATED_CREATE_ONLY):
        # An explicit create-only declaration WINS over a plain `sdlc.dated`,
        # so a Kind that carries both is not silently given an arc it lacks.
        out[k] = ("created_at",)
    return out


# ── status enums, derived from each Kind's own schema ────────────────────────


def status_enum_for(kernel: Any, kind: str, *, api_version: str | None = None
                    ) -> tuple[str, ...] | None:
    """The valid statuses for ``kind``, read from the Kind's OWN schema.

    ``spec.properties.status.enum`` is where a Kind already declares its arc —
    every board Kind in the tree has one, class and descriptor alike. Reading it
    means ``set_status`` needs no second copy of the vocabulary to drift from the
    schema that validates the write it is about to make.

    ``None`` when the Kind is unregistered, declares no schema, or declares a
    ``status`` without an enum: the caller must then refuse rather than guess."""
    resolve = getattr(kernel, "kind_port_for", None)
    if resolve is None:
        return None
    try:
        port = resolve(kind, api_version=api_version)
    except Exception:  # noqa: BLE001 — an unresolvable name declares no arc
        return None
    if port is None:
        return None
    try:
        schema = port.schema()
    except Exception:  # noqa: BLE001 — a Kind whose schema errors has no arc
        return None
    if not isinstance(schema, dict):
        return None
    props = schema.get("properties")
    if not isinstance(props, dict):
        return None
    status = props.get("status")
    if not isinstance(status, dict):
        return None
    enum = status.get("enum")
    if not isinstance(enum, (list, tuple)) or not enum:
        return None
    values = tuple(str(v) for v in enum)
    return values or None


def status_enums(kernel: Any) -> dict[str, tuple[str, ...]]:
    """Every transitionable board Kind → its declared status enum."""
    out: dict[str, tuple[str, ...]] = {}
    for kind in work_item_kinds(kernel):
        enum = status_enum_for(kernel, kind)
        if enum:
            out[kind] = enum
    return out


def transitionable_kinds(kernel: Any) -> tuple[str, ...]:
    """Work-item Kinds that can actually take a ``set_status`` — i.e. those whose
    schema declares a status enum to validate the target against.

    This is what closes the "six of the ten Kinds the digest reads have no named
    write tool" gap by DECLARATION: a Kind joins the writable set by carrying the
    work-item trait and declaring its own arc, not by being added to a tuple in
    ``dna.application.sdlc``."""
    return tuple(sorted(status_enums(kernel)))
