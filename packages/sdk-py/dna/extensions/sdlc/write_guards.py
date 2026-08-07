"""SDLC-owned write-path guards (s-write-path-despecialize).

The bi-temporal Engram guard used to live inline in
``Kernel._write_instance_inner`` as a ``kind == "LessonLearned"``
special-case. It is now a ``pre_save`` veto hook registered by
``SdlcExtension.register``. s-engram-rename (2026-07-19): the Kind itself
moved to the ``helix`` extension (``/dna/v1``), but this hook stays wired
here — a ``pre_save`` veto is a plain string match on ``ctx.kind``, it does
not require the Kind to be registered by the SAME extension that fires it.

This guard never vetoes — it MUTATES ``ctx.raw`` in place (preserving
``valid_to``/``superseded_by_memory``) so the write proceeds with the
corrected payload. The pure helper stays in
``dna.kernel.write.bitemporal_guard`` (generic bitemporal utility), and since
i-139 it also owns the one exemption: a write that ARCHIVED the invalidation
into ``spec.revivals`` is a revive, not a resurrection.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dna.kernel.hooks import PreSaveContext

logger = logging.getLogger(__name__)

_KIND = "Engram"

# After the Helix guards (10/20/30) — independent rules, stable order.
PRIORITY_BITEMPORAL = 40
PRIORITY_SPRINT_IDENTITY = 50

_SPRINT_KIND = "Sprint"


async def bitemporal_engram_guard(ctx: PreSaveContext) -> None:
    """Never resurrect a superseded memory (i-046).

    Maintenance write paths (decay/cue/allocation hooks) re-write an
    Engram by name WITHOUT carrying ``valid_to``; without this guard
    a superseded episodic silently returns to recall. Single chokepoint for
    every write path (hooks via kinds-api PUT, create_remembrance, CLI).
    Fail-open: never block a write on the guard read.

    ⚠️ A DELIBERATE revive passes (i-139), and that decision is made by the pure
    helper rather than here: a write that FILED the invalidation into the
    append-only ``spec.revivals`` has archived it, not dropped it, and not
    dropping it is the invariant this guard actually protects. See
    :mod:`dna.kernel.write.bitemporal_guard` — the exemption is derived from the
    PAYLOAD (it must quote the exact ``valid_to`` being lifted), never from a
    list of blessed callers or a flag threaded down the write path.
    """
    if ctx.kind != _KIND or not isinstance(ctx.raw, dict):
        return
    spec = ctx.raw.get("spec")
    if not isinstance(spec, dict) or spec.get("valid_to"):
        return
    try:
        existing = await ctx.kernel.get_instance(
            ctx.scope, ctx.kind, ctx.name, tenant=ctx.tenant,
        )
    except Exception:  # noqa: BLE001 — guard read must never block a write
        existing = None
    if isinstance(existing, dict):
        from dna.kernel.write.bitemporal_guard import (  # noqa: PLC0415
            preserve_bitemporal_invalidation,
        )
        if preserve_bitemporal_invalidation(spec, existing.get("spec")):
            logger.info(
                "[bitemporal-guard] preserved valid_to on '%s' "
                "(maintenance write would have resurrected it)", ctx.name,
            )


async def sprint_identity_guard(ctx: PreSaveContext) -> None:
    """A Sprint's ``spec.sprint_id`` MUST equal its instance name.

    ``Story.sprint_ref`` / ``Feature.sprint_ref`` are declared references
    (``relations.sprint_ref.to: Sprint``), and a relation resolves by INSTANCE
    NAME. ``sprint_id`` restates that name inside the spec so it is queryable
    and projectable — which means the two can disagree, and the day they do the
    Kind has two identities: one the graph resolves by and one every human
    reads. ``PricingPlan.tier_id`` shipped that ambiguity as a "SHOULD" and it
    is exactly why ``PlanBinding.tier_id`` cannot be declared today.

    So this VETOES rather than warns, and it vetoes at the one chokepoint every
    write passes through (CLI, REST, MCP ``write_instance``, seeds) — a rule
    enforced only where somebody remembered to call it is a rule that is green
    for the wrong reason.

    Absent ``sprint_id`` is not this guard's business: the schema already
    requires it, and duplicating that check here would make two places disagree
    about the message.
    """
    if ctx.kind != _SPRINT_KIND or not isinstance(ctx.raw, dict):
        return
    spec = ctx.raw.get("spec")
    if not isinstance(spec, dict):
        return
    sprint_id = spec.get("sprint_id")
    if not isinstance(sprint_id, str) or not sprint_id:
        return  # schema's job, not ours
    if sprint_id != ctx.name:
        raise ValueError(
            f"Sprint '{ctx.name}': spec.sprint_id is {sprint_id!r} but the "
            f"instance name is {ctx.name!r}. They must match — Story.sprint_ref "
            f"and Feature.sprint_ref resolve this Sprint by INSTANCE NAME, so a "
            f"mismatch makes the sprint reachable under one identity and "
            f"queryable under the other. Rename the instance to "
            f"{sprint_id!r}, or set sprint_id to {ctx.name!r}."
        )


def register_write_guards(kernel: Any) -> None:
    """Wire the SDLC write guards as ``pre_save`` veto hooks (idempotent)."""
    kernel.hooks.on_veto(
        "pre_save", bitemporal_engram_guard,
        priority=PRIORITY_BITEMPORAL, key="sdlc.bitemporal-engram",
    )
    kernel.hooks.on_veto(
        "pre_save", sprint_identity_guard,
        priority=PRIORITY_SPRINT_IDENTITY, key="sdlc.sprint-identity",
    )
