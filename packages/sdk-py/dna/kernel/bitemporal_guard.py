"""Bi-temporal invalidation guard (i-046).

A superseded memory must STAY superseded. Maintenance write paths in the
cognitive autopilot (decay / cue / allocation hooks) re-write a Engram by
name via read-modify-write and don't carry ``valid_to`` — without this guard a
superseded episodic silently returns to recall (resurrection).

The guard is the single chokepoint: ``kernel.write_document`` calls it for every
Engram write. If the EXISTING persisted doc is invalidated (``valid_to``
set) and the incoming write lacks it, the incoming spec inherits
``valid_to`` + ``superseded_by_memory``. Pure + mutating-in-place on the incoming
spec (which is about to be persisted). Never blocks a write.

Re-validation (un-superseding) stays possible by passing an EXPLICIT ``valid_to``
of ``None``/empty is NOT enough (that's the resurrection we prevent); a caller
that genuinely wants to revive a memory clears ``superseded_by_memory`` and sets
a fresh ``valid_from`` — handled above this guard, out of scope here.
"""
from __future__ import annotations

from typing import Any


def preserve_bitemporal_invalidation(
    incoming_spec: dict[str, Any], existing_spec: dict[str, Any] | None,
) -> bool:
    """If the existing doc is invalidated and the incoming write would drop it,
    carry ``valid_to`` + ``superseded_by_memory`` forward. Mutates
    ``incoming_spec`` in place. Returns True iff it preserved something.
    """
    if not isinstance(incoming_spec, dict) or not isinstance(existing_spec, dict):
        return False
    existing_valid_to = existing_spec.get("valid_to")
    if not existing_valid_to:
        return False  # existing not invalidated — nothing to protect
    if incoming_spec.get("valid_to"):
        return False  # incoming carries its own valid_to — respect it
    incoming_spec["valid_to"] = existing_valid_to
    sup = existing_spec.get("superseded_by_memory")
    if sup and not incoming_spec.get("superseded_by_memory"):
        incoming_spec["superseded_by_memory"] = sup
    return True
