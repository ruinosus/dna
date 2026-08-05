"""Merge candidates — deterministic overlap detection for ``consolidate``.

``consolidate`` was a retention-only pass: it could expire a stale memory but
had nothing to say about two memories that tell the SAME story twice. This
module adds the OTHER half of consolidation — proposing the fusion of
overlapping memories — while honoring the verbs' contract that the SDK core is
deterministic (NO LLM): candidate DETECTION is pure lexical overlap, the
canonical survivor is picked by a fixed rule, and the default proposal is
``supersede`` (keep the canonical, bi-temporally demote the rest via
``forget(..., superseded_by=canonical)`` — machinery that already exists).

What the SDK deliberately does NOT do is write the fused TEXT: synthesizing
one summary out of N is a scribe's job, and the scribes are "external +
optional" by design (see ``dna.memory.verbs``). The exact seam a scribe plugs
into is :class:`MergeScribe` below — a caller-supplied callable, never a model
bound into the kernel. Without one, each group still ships a complete,
applyable ``supersede`` proposal; with one, the group's ``proposed_spec``
becomes the scribe's synthesis (fail-soft: a scribe error falls back to the
deterministic proposal and says so).

Everything here is pure (no kernel, no IO); the kernel-bound wiring lives in
``dna.memory.verbs.consolidate`` (``dry_run=True``), Py-only like the other
verbs. i-050 (dna-cloud: consolidação com diff), 2026-08-05.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

from dna.memory.decay import confidence_score_numeric, days_since
from dna.memory.semantic import engram_text

#: Jaccard floor (0..1) above which two memories are merge candidates. 0.5 is
#: deliberately conservative — propose fusion only when the two token sets
#: mostly coincide; a portal can lower it per call to cast a wider net.
DEFAULT_OVERLAP_FLOOR = 0.5

#: Tokens shorter than this carry no meaning worth matching on ("a", "of", "is").
_MIN_TOKEN_LEN = 3

#: Function words long enough to pass the length gate but shared by ANY two
#: English sentences — kept out so overlap measures WHAT the memories say, not
#: that both are prose. Deliberately tiny + frozen (deterministic, no NLP dep).
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "was", "were", "are",
    "has", "have", "had", "but", "not", "you", "our", "its", "their",
    "into", "from", "when", "then", "than", "over", "under", "about",
})

#: How many shared terms a pair reports as evidence — enough for a human to see
#: WHY the pair matched, without dumping whole token sets into the report.
_MAX_SHARED_TERMS = 12

_TOKEN_RE = re.compile(r"[^0-9a-zA-Z]+")


class MergeScribe(Protocol):
    """The EXTERNAL synthesis seam — the exact contract a fusion scribe fills.

    Input: the group's member specs, canonical FIRST (each the full memory
    ``spec`` dict, read-only). Output: the proposed FUSED spec — at minimum a
    ``summary`` (the fused text); any other Engram spec fields it returns ride
    along verbatim. The caller (a service, never this SDK) owns the model, the
    prompt and the cost; the kernel only carries the proposal in the report.
    A raising scribe degrades the group to the deterministic ``supersede``
    proposal — it never breaks the pass.
    """

    def __call__(self, group: Sequence[dict[str, Any]]) -> dict[str, Any]: ...


def merge_tokens(spec: dict[str, Any]) -> frozenset[str]:
    """A memory's comparable token set — lowercased alphanumeric tokens of its
    semantic payload (:func:`dna.memory.semantic.engram_text`: area/title/
    summary/body — the SAME planes recall embeds), minus the too-short and the
    function words (:data:`_STOPWORDS`)."""
    return frozenset(
        t for t in _TOKEN_RE.split(engram_text(spec).lower())
        if len(t) >= _MIN_TOKEN_LEN and t not in _STOPWORDS
    )


def overlap_score(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity of two token sets. 0.0 when either is empty — a
    memory with no comparable text overlaps with nothing (never everything)."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def canonical_name(
    names: Sequence[str],
    specs_by_name: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
) -> str:
    """The deterministic survivor of a merge group: highest
    ``confidence_score`` first, then the NEWEST ``created_at`` (a memory with
    no timestamp counts as oldest), then the lexicographically smallest name —
    a total order, so the same group always elects the same canonical."""
    n = now or datetime.now(timezone.utc)

    def _key(name: str) -> tuple[float, float, str]:
        spec = specs_by_name.get(name) or {}
        age = days_since(spec.get("created_at") or spec.get("valid_from"), now=n)
        return (
            -confidence_score_numeric(spec),
            age if age is not None else float("inf"),
            name,
        )

    return min(names, key=_key)


def merge_groups(
    members: Sequence[tuple[str, dict[str, Any]]],
    *,
    overlap_floor: float = DEFAULT_OVERLAP_FLOOR,
) -> list[dict[str, Any]]:
    """Group overlapping memories: every pair at/above ``overlap_floor`` is an
    edge; groups are the connected components (union-find), so A~B and B~C
    land in ONE group even when A and C do not overlap directly. Returns one
    dict per multi-member component — ``{"names": sorted, "pairs": [...]}`` —
    each pair carrying its score + the shared terms as evidence. Deterministic:
    output order follows the smallest member name."""
    names = [name for name, _ in members]
    tokens = {name: merge_tokens(spec) for name, spec in members}

    parent: dict[str, str] = {name: name for name in names}

    def _find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a: str, b: str) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            # smaller root wins — keeps the forest (and the output) deterministic.
            if rb < ra:
                ra, rb = rb, ra
            parent[rb] = ra

    pairs: list[dict[str, Any]] = []
    ordered = sorted(names)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            score = overlap_score(tokens[a], tokens[b])
            if score < overlap_floor:
                continue
            shared = sorted(tokens[a] & tokens[b])[:_MAX_SHARED_TERMS]
            pairs.append({
                "a": a, "b": b,
                "overlap": round(score, 4),
                "shared_terms": shared,
            })
            _union(a, b)

    by_root: dict[str, list[str]] = {}
    for name in ordered:
        by_root.setdefault(_find(name), []).append(name)

    groups: list[dict[str, Any]] = []
    for root in sorted(by_root):
        group_names = sorted(by_root[root])
        if len(group_names) < 2:
            continue
        in_group = set(group_names)
        groups.append({
            "names": group_names,
            "pairs": [p for p in pairs if p["a"] in in_group],
        })
    return groups


def merge_candidates_report(
    members: Sequence[tuple[str, dict[str, Any]]],
    *,
    overlap_floor: float = DEFAULT_OVERLAP_FLOOR,
    scribe: MergeScribe | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """The structured merge-proposal report — the DiffBloco's input (i-050).

    ``members`` are the currently-valid memories as ``(name, spec)`` pairs
    (the caller — ``consolidate(dry_run=True)`` — already holds every spec, so
    this costs no extra IO). Each returned group is a PROPOSAL, strictly
    separated from application (nothing here writes):

    * ``names`` / ``pairs`` — the candidates + the overlap evidence;
    * ``canonical`` / ``superseded`` — the deterministic survivor election
      (:func:`canonical_name`) and who it would replace;
    * ``strategy`` — ``"supersede"`` (deterministic default: keep the
      canonical, ``forget(name, superseded_by=canonical)`` the rest) or
      ``"synthesize"`` (a :class:`MergeScribe` produced a fused spec);
    * ``proposed_spec`` / ``proposed_text`` — what would remain: the
      canonical's spec with the group's tags unioned (supersede), or the
      scribe's fusion (synthesize). ``synthesized`` says which happened; a
      scribe failure adds ``scribe_error`` and falls back — never raises.
    """
    specs_by_name = {name: spec for name, spec in members}
    report: list[dict[str, Any]] = []
    for group in merge_groups(members, overlap_floor=overlap_floor):
        names = group["names"]
        canonical = canonical_name(names, specs_by_name, now=now)
        superseded = [n for n in names if n != canonical]
        member_specs = [specs_by_name[canonical]] + [
            specs_by_name[n] for n in superseded
        ]

        tags: set[str] = set()
        for spec in member_specs:
            tags.update(str(t) for t in (spec.get("tags") or []))
        proposed_spec: dict[str, Any] = dict(specs_by_name[canonical])
        if tags:
            proposed_spec["tags"] = sorted(tags)
        strategy = "supersede"
        synthesized = False
        scribe_error: str | None = None

        if scribe is not None:
            try:
                fused = scribe(member_specs)
                if isinstance(fused, dict) and fused.get("summary"):
                    proposed_spec = dict(fused)
                    strategy = "synthesize"
                    synthesized = True
                else:
                    scribe_error = "scribe returned no summary"
            except Exception as exc:  # noqa: BLE001 — the scribe is optional; never break the pass
                scribe_error = f"{type(exc).__name__}: {exc}"

        entry: dict[str, Any] = {
            "names": names,
            "canonical": canonical,
            "superseded": superseded,
            "pairs": group["pairs"],
            "strategy": strategy,
            "proposed_spec": proposed_spec,
            "proposed_text": proposed_spec.get("summary") or None,
            "synthesized": synthesized,
        }
        if scribe_error is not None:
            entry["scribe_error"] = scribe_error
        report.append(entry)
    return report


__all__ = [
    "DEFAULT_OVERLAP_FLOOR",
    "MergeScribe",
    "merge_tokens",
    "overlap_score",
    "canonical_name",
    "merge_groups",
    "merge_candidates_report",
]
