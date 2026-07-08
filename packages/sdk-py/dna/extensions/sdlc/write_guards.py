"""SDLC-owned write-path guards (s-write-path-despecialize).

The bi-temporal LessonLearned guard used to live inline in
``Kernel._write_document_inner`` as a ``kind == "LessonLearned"``
special-case. It is now a ``pre_save`` veto hook registered by
``SdlcExtension.register`` (the extension that owns LessonLearned).

This guard never vetoes — it MUTATES ``ctx.raw`` in place (preserving
``valid_to``/``superseded_by_memory``) so the write proceeds with the
corrected payload. The pure helper stays in
``dna.kernel.bitemporal_guard`` (generic bitemporal utility).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dna.kernel.hooks import PreSaveContext

logger = logging.getLogger(__name__)

_KIND = "LessonLearned"

# After the Helix guards (10/20/30) — independent rules, stable order.
PRIORITY_BITEMPORAL = 40


async def bitemporal_lessonlearned_guard(ctx: PreSaveContext) -> None:
    """Never resurrect a superseded memory (i-046).

    Maintenance write paths (decay/cue/allocation hooks) re-write a
    LessonLearned by name WITHOUT carrying ``valid_to``; without this guard
    a superseded episodic silently returns to recall. Single chokepoint for
    every write path (hooks via kinds-api PUT, create_remembrance, CLI).
    Fail-open: never block a write on the guard read.
    """
    if ctx.kind != _KIND or not isinstance(ctx.raw, dict):
        return
    spec = ctx.raw.get("spec")
    if not isinstance(spec, dict) or spec.get("valid_to"):
        return
    try:
        existing = await ctx.kernel.get_document(
            ctx.scope, ctx.kind, ctx.name, tenant=ctx.tenant,
        )
    except Exception:  # noqa: BLE001 — guard read must never block a write
        existing = None
    if isinstance(existing, dict):
        from dna.kernel.bitemporal_guard import (  # noqa: PLC0415
            preserve_bitemporal_invalidation,
        )
        if preserve_bitemporal_invalidation(spec, existing.get("spec")):
            logger.info(
                "[bitemporal-guard] preserved valid_to on '%s' "
                "(maintenance write would have resurrected it)", ctx.name,
            )


def register_write_guards(kernel: Any) -> None:
    """Wire the SDLC write guards as ``pre_save`` veto hooks (idempotent)."""
    kernel.hooks.on_veto(
        "pre_save", bitemporal_lessonlearned_guard,
        priority=PRIORITY_BITEMPORAL, key="sdlc.bitemporal-lessonlearned",
    )
