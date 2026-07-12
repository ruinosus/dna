"""Dedup — never surface the same insight twice (pure application logic).

s-intel-dedup-memory. Repetition is the #1 source of noise in an intel feed, so
before the engine writes a surviving candidate as an ``IntelInsight`` it dedups
it against what was ALREADY surfaced for that source (any state — including the
ones the user actioned or dismissed). Two signals, in order:

  1. a deterministic **normalized key** (``source_ref`` + slugged title) — a
     zero-dependency floor that dedups exact/near-exact repeats even when no
     embedding carries meaning (the offline/degraded case);
  2. a **semantic cosine** over the memory co-pillar's embedding space
     (``kernel.embed`` + :func:`dna.memory.semantic.cosine_similarity`) — catches
     a re-worded restatement of the same insight.

Everything here is PURE (no kernel, no IO): the engine owns the one
``kernel.embed`` batch and hands the numeric cosines in, so the decision stays
inspectable and the TypeScript twin (i-027) is a straight mirror.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

# The embed fields the IntelInsight Kind declares (`embed: [title, fact]`). The
# dedup similarity compares exactly this text so a candidate and an already-
# written insight are scored on the same planes the search index would use.
INSIGHT_TEXT_FIELDS: tuple[str, ...] = ("title", "fact")

# A restatement of an already-surfaced insight scores near-identical here; the
# bar is high on purpose so dedup only drops genuine repeats, never a distinct
# insight that merely shares vocabulary (the feedback stage handles "similar,
# not identical"). Inspectable constant.
DEDUP_COSINE_THRESHOLD = 0.97

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def insight_text(item: Mapping[str, Any]) -> str:
    """The text an insight *means*, for cue-side embedding — the same
    ``title``/``fact`` planes the Kind embeds. Missing fields contribute
    nothing."""
    return " ".join(
        str(item.get(f) or "") for f in INSIGHT_TEXT_FIELDS if item.get(f)
    ).strip()


def normalized_title(title: str | None) -> str:
    """Slug a title to a stable dedup token (lower, alnum-collapsed)."""
    return _SLUG_RE.sub(" ", (title or "").lower()).strip()


def normalized_key(item: Mapping[str, Any], source_ref: str | None = None) -> str:
    """Deterministic dedup key: ``<source_ref>::<normalized title>``. The
    zero-dependency floor — two candidates with the same source + title collide
    regardless of any embedding signal."""
    src = source_ref if source_ref is not None else item.get("source_ref", "")
    return f"{src or ''}::{normalized_title(item.get('title'))}"


def dedup_partition(
    candidate_keys: Sequence[str],
    candidate_max_cosines: Sequence[float] | None,
    existing_keys: set[str],
    *,
    cosine_threshold: float = DEDUP_COSINE_THRESHOLD,
) -> tuple[list[int], list[int], dict[int, tuple[str, float]]]:
    """Partition candidate indices into ``(fresh, duplicate, reasons)``.

    A candidate is a duplicate iff its ``normalized_key`` already exists OR its
    max cosine to any existing insight is ``>= cosine_threshold``. Dedup is also
    applied WITHIN the batch — once a candidate is accepted its key joins the
    seen set, so two near-identical candidates in one pass don't both survive.
    ``reasons[i]`` is ``(signal, cosine)`` where signal is ``"key"`` or
    ``"cosine"``. Pure — deterministic given its inputs."""
    seen = set(existing_keys)
    fresh: list[int] = []
    duplicate: list[int] = []
    reasons: dict[int, tuple[str, float]] = {}
    for i, key in enumerate(candidate_keys):
        cos = float(candidate_max_cosines[i]) if candidate_max_cosines else 0.0
        if key in seen:
            duplicate.append(i)
            reasons[i] = ("key", cos)
        elif cos >= cosine_threshold:
            duplicate.append(i)
            reasons[i] = ("cosine", cos)
        else:
            fresh.append(i)
            seen.add(key)
    return fresh, duplicate, reasons


__all__ = [
    "INSIGHT_TEXT_FIELDS",
    "DEDUP_COSINE_THRESHOLD",
    "insight_text",
    "normalized_title",
    "normalized_key",
    "dedup_partition",
]
