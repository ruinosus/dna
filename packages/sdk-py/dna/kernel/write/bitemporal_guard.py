"""Bi-temporal invalidation guard (i-046) — and the ONE way past it (i-139).

A superseded memory must STAY superseded. Maintenance write paths in the
cognitive autopilot (decay / cue / allocation hooks) re-write a Engram by
name via read-modify-write and don't carry ``valid_to`` — without this guard a
superseded episodic silently returns to recall (resurrection).

The guard is the single chokepoint: ``kernel.write_instance`` calls it for every
Engram write. If the EXISTING persisted doc is invalidated (``valid_to``
set) and the incoming write lacks it, the incoming spec inherits
``valid_to`` + ``superseded_by_memory``. Pure + mutating-in-place on the incoming
spec (which is about to be persisted). Never blocks a write.

The revive that this module predicted and nothing performed
---------------------------------------------------------
This docstring used to end: *"a caller that genuinely wants to revive a memory
clears ``superseded_by_memory`` and sets a fresh ``valid_from`` — handled above
this guard, out of scope here."* Nothing above it did. Measured for i-139:
``unforget|restore|revive|undelete|recover`` across ``dna/`` and ``dna_cli/``
returned **zero**, so for as long as this guard existed there was no caller it
could let through — and ``forget``'s promise of *"revivable"* had nothing behind
it. The escape hatch was described, never built, and never exercised.

It is also not the hatch that got built, and the difference is worth stating
because the described one is the tempting one. *"Clears ``superseded_by_memory``
and sets a fresh ``valid_from``"* fails on both halves: a maintenance write that
happens to carry neither field would match it by accident — which is precisely
the resurrection this guard exists to stop — and moving ``valid_from`` rewrites
when the memory STARTED being true, which is false. The memory was true from the
beginning; it was retired in the middle.

What the guard actually protects, and therefore what may pass
------------------------------------------------------------
The invariant is not *"``valid_to`` must be present"*. It is **an invalidation
must never be dropped on the floor**. A write that FILES the invalidation has
not dropped it — it has moved it, verbatim, into the append-only
``spec.revivals`` where it stays readable forever.

So the exemption is evidence-based and self-evidencing: the incoming spec must
carry a ``revivals`` entry whose ``valid_to`` is **exactly** the one being
retired. A maintenance write cannot produce that by accident or by omission — it
would have to quote the very timestamp it is dropping, which is the opposite of
forgetting to carry it. Nothing is trusted about the caller's intent; the
payload proves it.

That also keeps the guard DERIVED rather than enumerated. There is no list of
blessed callers and no flag threaded down the write path for the guard to
believe: any writer that files the interval correctly may revive, including one
written after this file, and one that does not, cannot.
"""
from __future__ import annotations

from typing import Any


def filed_the_invalidation(
    incoming_spec: dict[str, Any], existing_valid_to: Any,
) -> bool:
    """Whether ``incoming_spec`` has FILED ``existing_valid_to`` into its
    append-only ``revivals`` log — the one honest reason to let an invalidation
    be lifted.

    Exact match on the timestamp, deliberately: a near-miss is either a
    different retirement or a fabricated one, and both are worse than refusing.
    An entry whose ``valid_to`` merely *exists* would let any write with a
    non-empty ``revivals`` resurrect any memory.
    """
    if not existing_valid_to or not isinstance(incoming_spec, dict):
        return False
    revivals = incoming_spec.get("revivals")
    if not isinstance(revivals, list):
        return False
    return any(
        isinstance(entry, dict) and entry.get("valid_to") == existing_valid_to
        for entry in revivals
    )


def preserve_bitemporal_invalidation(
    incoming_spec: dict[str, Any], existing_spec: dict[str, Any] | None,
) -> bool:
    """If the existing doc is invalidated and the incoming write would drop it,
    carry ``valid_to`` + ``superseded_by_memory`` forward. Mutates
    ``incoming_spec`` in place. Returns True iff it preserved something.

    Returns False — letting the lift stand — when the incoming write has filed
    that exact invalidation into ``revivals`` (:func:`filed_the_invalidation`).
    That is ``dna.memory.revive`` and anything else that keeps the record.
    """
    if not isinstance(incoming_spec, dict) or not isinstance(existing_spec, dict):
        return False
    existing_valid_to = existing_spec.get("valid_to")
    if not existing_valid_to:
        return False  # existing not invalidated — nothing to protect
    if incoming_spec.get("valid_to"):
        return False  # incoming carries its own valid_to — respect it
    if filed_the_invalidation(incoming_spec, existing_valid_to):
        # A DELIBERATE revive (i-139): the invalidation is not lost, it is
        # archived. Restoring `valid_to` here would make the memory eternally
        # unrevivable — the guard against losing history turned into a guard
        # against having any.
        return False
    incoming_spec["valid_to"] = existing_valid_to
    sup = existing_spec.get("superseded_by_memory")
    if sup and not incoming_spec.get("superseded_by_memory"):
        incoming_spec["superseded_by_memory"] = sup
    return True
