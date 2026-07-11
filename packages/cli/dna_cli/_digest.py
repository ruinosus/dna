"""Retrospective digest aggregation — the *pure* core of ``dna sdlc digest``.

``dna sdlc brief`` / ``next`` / ``current`` look FORWARD ("what to do next").
The **digest looks BACKWARD** ("what happened while you were away") — the
surface for the delegator who hands work off and reviews at the end instead of
watching the board live.

This module holds the deterministic, kernel-free aggregation so it can be
unit-tested in isolation: ``build_digest`` takes already-loaded work-item docs
(plus optional open-PR + git-tag context) and a time window, walks every
timeline, and returns a structured digest grouped into

    completed · decided · found · progressed · artifacts · releases
    + attention{ blocked, review_awaiting, owner_decisions, open_questions }

The CLI command (``sdlc_cmd.py``) owns only the impure edges: opening a kernel
session to collect the docs, shelling out to ``gh`` / ``git`` for PRs + tags,
rendering, and persisting the result as a ``StatusReport`` Kind.

Py-only by design: the ``dna`` CLI is Python-only (there is no ``dna`` TS
binary), so this aggregator has no TS twin — the parity contract does not apply
to CLI-only surfaces.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


# ─── window parsing ───────────────────────────────────────────────────

def parse_iso_utc(value: str | None) -> datetime | None:
    """Best-effort parse of an ISO-8601 timestamp into an aware UTC datetime.

    Accepts a trailing ``Z``. Naive inputs are assumed UTC. Returns ``None``
    on anything unparseable (fail-soft — a bad ``at`` field never crashes the
    walk)."""
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        # Date-only (e.g. '2026-07-11') or other short forms.
        try:
            dt = datetime.fromisoformat(raw[:10])
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}


def resolve_since(
    spec: str | None,
    *,
    now: datetime,
    last_digest_at: datetime | None = None,
    default_hours: int = 24,
) -> tuple[datetime, str]:
    """Resolve the ``--since`` argument to a concrete window start.

    Accepts, in order:
      * ``None``               → ``now - default_hours`` (label ``last 24h``)
      * ``"last-digest"``      → the previous digest's ``generated_at``
                                 (or the default window when none exists yet)
      * a relative span        → ``"90m" | "24h" | "3d" | "2w"``
      * an ISO-8601 timestamp  → parsed directly

    Returns ``(since_dt, human_label)``. Raises ``ValueError`` on an
    unparseable span/timestamp so the CLI can surface a clean usage error.
    """
    if spec is None or spec == "":
        return now - timedelta(hours=default_hours), f"last {default_hours}h"

    token = spec.strip()

    if token == "last-digest":
        if last_digest_at is not None:
            return last_digest_at, f"since last digest ({last_digest_at.isoformat()})"
        return (
            now - timedelta(hours=default_hours),
            f"last {default_hours}h (no prior digest)",
        )

    # Relative span: <int><unit> where unit in m/h/d/w.
    if len(token) >= 2 and token[-1] in _UNIT_SECONDS and token[:-1].isdigit():
        secs = int(token[:-1]) * _UNIT_SECONDS[token[-1]]
        return now - timedelta(seconds=secs), f"last {token}"

    # Otherwise: an explicit ISO timestamp.
    dt = parse_iso_utc(token)
    if dt is None:
        raise ValueError(
            f"--since {spec!r} não reconhecido — use ISO-8601, "
            f"um span (ex: 24h, 3d, 2w) ou 'last-digest'."
        )
    return dt, f"since {dt.isoformat()}"


# ─── status vocabularies ──────────────────────────────────────────────

# A status_change whose `to` lands here = the item shipped/closed.
_TERMINAL_TO = {
    "done", "shipped", "resolved", "accepted", "merged", "closed", "answered",
}
# Feature/Epic movement into an active (non-terminal) state = progress.
_PROGRESS_TO = {"in-progress", "in-development", "planning", "triaged", "proposed"}

_PROGRESS_KINDS = {"Feature", "Epic", "Initiative"}


def _title(spec: dict[str, Any], name: str) -> str:
    return str(spec.get("title") or spec.get("description") or name)[:80]


def _in_window(at: datetime | None, since: datetime, until: datetime) -> bool:
    return at is not None and since <= at <= until


def _blocked_reason(spec: dict[str, Any]) -> str:
    """Recover WHY an item is blocked — the last blocked status_change's
    reason/summary, else an explicit spec field, else a stock message."""
    for ev in reversed(list(spec.get("timeline") or [])):
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "status_change" and ev.get("to") == "blocked":
            reason = ev.get("reason") or ev.get("summary")
            if reason:
                return str(reason)
    return str(
        spec.get("block_reason") or spec.get("blocked_reason") or "(motivo não registrado)"
    )


def _match_prs(name: str, spec: dict[str, Any], open_prs: list[dict] | None) -> list[dict]:
    """Match open PRs to a Story by branch/title/timeline pr_url. Fail-soft."""
    if not open_prs:
        return []
    matched: list[dict] = []
    # PR URLs already stamped on the timeline (pr_opened events).
    timeline_urls = {
        ev.get("pr_url")
        for ev in (spec.get("timeline") or [])
        if isinstance(ev, dict) and ev.get("pr_url")
    }
    for pr in open_prs:
        url = pr.get("url") or ""
        branch = (pr.get("headRefName") or "").lower()
        title = (pr.get("title") or "")
        if (
            (url and url in timeline_urls)
            or (name and name.lower() in branch)
            or (name and name in title)
        ):
            matched.append({
                "number": pr.get("number"),
                "title": (title or "")[:70],
                "branch": pr.get("headRefName") or "",
                "url": url,
            })
    return matched


# ─── the aggregator ───────────────────────────────────────────────────

def build_digest(
    *,
    docs: list[dict[str, Any]],
    since: datetime,
    until: datetime,
    since_label: str = "",
    scope: str = "",
    open_prs: list[dict] | None = None,
    tags: list[dict] | None = None,
) -> dict[str, Any]:
    """Aggregate work-item timelines into a retrospective digest.

    ``docs`` is a list of ``{"kind", "name", "spec"}`` dicts (record-plane +
    lifecycle Kinds alike). ``since``/``until`` bound the window (aware UTC).
    ``open_prs`` / ``tags`` are optional context (fail-soft when absent).

    Returns a JSON-safe dict; timestamps are ISO strings. Buckets:

      * ``completed``  — items that reached a terminal status IN the window
      * ``decided``    — ADRs created + ``decision`` timeline events in window
      * ``found``      — Kaizens + Issues filed in window
      * ``progressed`` — Feature/Epic/Initiative movement in window
      * ``artifacts``  — ``artifact_produced`` events in window
      * ``releases``   — git tags dated in window
      * ``attention``  — CURRENT outstanding state (not windowed): what the
                         delegator must act on now
    """
    completed: list[dict] = []
    decided: list[dict] = []
    found: list[dict] = []
    progressed: dict[str, dict] = {}   # keyed by kind/name → keep latest
    artifacts: list[dict] = []
    attention_blocked: list[dict] = []
    attention_review: list[dict] = []
    attention_owner: list[dict] = []
    attention_questions: list[dict] = []

    # Process the canonical Kaizen/Issue docs BEFORE other docs' timelines so a
    # first-class doc (e.g. `kz-001`) wins the found-dedupe over the same
    # observation echoed as a `kaizen` timeline event on a Story.
    docs = sorted(
        docs, key=lambda d: 0 if d.get("kind") in ("Kaizen", "Issue") else 1
    )

    completed_keys: set[str] = set()
    found_seen: set[str] = set()   # dedupe kaizen event vs Kaizen doc twin

    def _add_found(entry: dict) -> None:
        sig = (entry.get("body") or "")[:60].strip().lower()
        if sig and sig in found_seen:
            return
        found_seen.add(sig)
        found.append(entry)

    for doc in docs:
        kind = doc.get("kind", "")
        name = doc.get("name", "")
        spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
        spec = spec or {}
        title = _title(spec, name)
        key = f"{kind}/{name}"
        status = spec.get("status")
        created = parse_iso_utc(spec.get("created_at"))

        # ── doc-level windowed signals ──
        if kind == "ADR" and _in_window(created, since, until):
            decided.append({
                "kind": kind, "name": name, "title": title,
                "at": created.isoformat(),
                "summary": str(spec.get("decision") or spec.get("context") or "")[:160],
            })
        if kind in ("Kaizen", "Issue") and _in_window(created, since, until):
            body = spec.get("body") or spec.get("description") or ""
            _add_found({
                "kind": kind, "name": name, "title": title,
                "at": created.isoformat(), "body": str(body)[:160],
            })

        # ── timeline walk ──
        for ev in spec.get("timeline") or []:
            if not isinstance(ev, dict):
                continue
            at = parse_iso_utc(ev.get("at"))
            if not _in_window(at, since, until):
                continue
            etype = ev.get("type")
            if etype == "status_change":
                to = ev.get("to")
                # ADR acceptance is a DECISION (surfaced in `decided` via the
                # doc-level signal), not a "completed" work item — keep it out
                # of the shipped bucket so it isn't double-counted.
                if to in _TERMINAL_TO and kind != "ADR" and key not in completed_keys:
                    completed_keys.add(key)
                    completed.append({
                        "kind": kind, "name": name, "title": title,
                        "to": to, "at": at.isoformat(),
                        "commit_ref": ev.get("commit_ref"),
                    })
                elif kind in _PROGRESS_KINDS and to in _PROGRESS_TO:
                    progressed[key] = {
                        "kind": kind, "name": name, "title": title,
                        "to": to, "at": at.isoformat(),
                    }
            elif etype == "decision":
                summary = ev.get("summary") or ev.get("body") or ""
                if summary:
                    decided.append({
                        "kind": kind, "name": name, "title": title,
                        "at": at.isoformat(), "summary": str(summary)[:160],
                    })
            elif etype == "kaizen":
                summary = ev.get("summary") or ""
                if summary:
                    _add_found({
                        "kind": kind, "name": name, "title": title,
                        "at": at.isoformat(), "body": str(summary)[:160],
                    })
            elif etype == "artifact_produced":
                artifacts.append({
                    "kind": ev.get("kind") or "?",
                    "name": ev.get("name") or "?",
                    "work_item": key,
                    "at": at.isoformat(),
                })

        # ── attention: CURRENT outstanding state (window-independent) ──
        if status == "blocked":
            attention_blocked.append({
                "kind": kind, "name": name, "title": title,
                "reason": _blocked_reason(spec),
            })
        elif kind == "Story" and status == "review":
            attention_review.append({
                "kind": kind, "name": name, "title": title,
                "prs": _match_prs(name, spec, open_prs),
            })
        elif kind == "ADR" and status == "proposed":
            attention_owner.append({
                "kind": kind, "name": name, "title": title,
                "why": "ADR proposto — aguarda ratificação do dono.",
            })
        elif kind == "Spike" and status in ("proposed", "in-progress"):
            attention_questions.append({
                "kind": kind, "name": name, "title": title,
                "question": str(
                    spec.get("question_to_answer") or spec.get("title") or ""
                )[:120],
            })

    # Drop items from `progressed` that also completed in the window.
    progressed_list = [v for k, v in progressed.items() if k not in completed_keys]

    releases = []
    for t in tags or []:
        at = t.get("at")
        at_dt = at if isinstance(at, datetime) else parse_iso_utc(at)
        if _in_window(at_dt, since, until):
            releases.append({"tag": t.get("name"), "at": at_dt.isoformat()})

    # Stable chronological ordering within each bucket.
    for bucket in (completed, decided, found, progressed_list, artifacts, releases):
        bucket.sort(key=lambda r: r.get("at") or "")

    attention = {
        "blocked": attention_blocked,
        "review_awaiting": attention_review,
        "owner_decisions": attention_owner,
        "open_questions": attention_questions,
    }
    attention_total = sum(len(v) for v in attention.values())

    counts = {
        "completed": len(completed),
        "decided": len(decided),
        "found": len(found),
        "progressed": len(progressed_list),
        "artifacts": len(artifacts),
        "releases": len(releases),
        "attention": attention_total,
    }

    if attention_blocked:
        rag = "red"
    elif attention_total:
        rag = "amber"
    else:
        rag = "green"

    return {
        "scope": scope,
        "since": since.isoformat(),
        "since_label": since_label,
        "until": until.isoformat(),
        "completed": completed,
        "decided": decided,
        "found": found,
        "progressed": progressed_list,
        "artifacts": artifacts,
        "releases": releases,
        "attention": attention,
        "counts": counts,
        "rag_status": rag,
        "verdict": _verdict_line(counts),
    }


def _verdict_line(counts: dict[str, int]) -> str:
    """One-sentence pt-BR summary — the ``StatusReport.verdict`` (embedded for
    semantic recall) and the digest's headline."""
    parts = [
        f"{counts['completed']} concluído(s)",
        f"{counts['decided']} decisão(ões)",
        f"{counts['found']} achado(s)",
    ]
    if counts["releases"]:
        parts.append(f"{counts['releases']} release(s)")
    head = " · ".join(parts)
    if counts["attention"]:
        return f"{head} — {counts['attention']} precisa(m) da sua atenção."
    return f"{head} — nada precisa da sua atenção."
