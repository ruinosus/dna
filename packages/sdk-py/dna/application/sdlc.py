"""``dna.application.sdlc`` — the transport-agnostic SDLC **write** core.

The shared write logic for the DNA SDLC board (Story / Issue / Feature), factored
out of the CLI (``dna_cli.sdlc_cmd``) so BOTH faces call ONE core — exactly the
``dna.memory.remember`` pattern (a kernel-level verb the CLI *and* the MCP server
share), applied to the board.

Two layers, mirroring the rest of :mod:`dna.application`:

* **pure builders** (no I/O, no clock/env access — the caller injects ``now`` /
  ``actor`` / ``source``): :func:`build_raw`, :func:`append_event`,
  :func:`build_story_spec` / :func:`build_issue_spec` / :func:`build_feature_spec`,
  :func:`next_issue_number`, :func:`validate_transition`. The CLI's own
  ``_build_raw`` / ``_append_timeline`` / ``_next_issue_number`` now delegate here,
  so the envelope + timeline + spec shape + transition rules live in ONE place.

* **async kernel-level cores** — :func:`create_story` / :func:`create_issue` /
  :func:`create_feature` / :func:`set_status` / :func:`add_comment`. Each takes a
  bare ``kernel`` + ``scope`` (like ``dna.memory.remember``) and routes the write
  through ``kernel.write_document`` (so cache invalidation, hooks + validation
  fire) — into the caller's tenant overlay via ``kernel.with_tenant(tenant)`` when
  ``tenant`` is set (the MCP auth bridge injects it), or the base board otherwise.

The MCP server (``dna_cli._mcp_server``) wires these as write TOOLS through the
same ``_guard`` tenancy + quota seam every other tool passes through; the LiveDna
``*_impl`` wrappers at the bottom resolve the scope + delegate, matching the
``recall_impl`` / ``remember_impl`` convention.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from dna.application.live import LiveDna

# ── constants (single source of truth — the CLI imports these) ─────────────

SDLC_API_VERSION = "github.com/ruinosus/dna/sdlc/v1"

VALID_STORY_STATUS = (
    "needs-triage", "todo", "in-progress", "review",
    "done", "blocked", "deferred", "cancelled",
)
VALID_FEATURE_STATUS = ("discovery", "in-development", "done", "cancelled", "blocked")
VALID_EPIC_STATUS = ("planning", "in-progress", "done", "cancelled", "deprecated")
VALID_ISSUE_STATUS = (
    "open", "triaged", "in-progress", "resolved", "wont-fix", "duplicate",
)
VALID_ISSUE_TYPE = ("bug", "enhancement", "question", "task")
VALID_ISSUE_SEVERITY = ("low", "medium", "high", "critical")
VALID_PRIORITIES = ("highest", "high", "medium", "low", "lowest")

# The valid target-status set per board Kind — the ``set_status`` tool refuses a
# transition to any status outside its Kind's enum (the "don't allow invalid
# transitions" invariant). Kept as a mapping so the tool is Kind-generic.
_STATUS_ENUMS: dict[str, tuple[str, ...]] = {
    "Story": VALID_STORY_STATUS,
    "Issue": VALID_ISSUE_STATUS,
    "Feature": VALID_FEATURE_STATUS,
    "Epic": VALID_EPIC_STATUS,
}

# Statuses that close a work item — the core auto-stamps ``closed_at`` on entry
# (mirrors the CLI's ``story done`` / ``issue resolve`` / ``feature ship``).
_TERMINAL_STATUS: frozenset[str] = frozenset(
    {"done", "resolved", "cancelled", "wont-fix", "duplicate", "deprecated"}
)

_WRITABLE_KINDS: frozenset[str] = frozenset(_STATUS_ENUMS)


class InvalidTransition(ValueError):
    """A requested ``set_status`` target is not a valid status for the Kind.

    Raised by :func:`validate_transition`. The MCP edge maps it to a clean
    ``ToolError`` so a client sees the honest denial, never a masked 500 / a bad
    write. The message names the Kind, the rejected status, and the valid set."""


# ── pure helpers ────────────────────────────────────────────────────────────


def now_iso(now: datetime | None = None) -> str:
    """UTC ISO-8601 timestamp (seconds precision) — the board's ``at`` stamp."""
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def build_raw(kind: str, name: str, spec: dict[str, Any]) -> dict[str, Any]:
    """The kernel document envelope for a board write (apiVersion + metadata)."""
    return {
        "apiVersion": SDLC_API_VERSION,
        "kind": kind,
        "metadata": {"name": name},
        "spec": spec,
    }


def append_event(
    spec: dict[str, Any], event_type: str, *,
    now: str, actor: str, source: str, **fields: Any,
) -> None:
    """Append an event to ``spec.timeline[]`` (creating the list if absent).

    Mutates ``spec`` in place — the shared timeline-append the CLI's
    ``_append_timeline`` now delegates to. Stamps ``at`` / ``actor`` / ``type`` /
    ``source``; per-event extras come via ``fields`` and FALSY extras are dropped
    (so a brand-new doc never stamps an empty ``from``), byte-for-byte matching the
    CLI's prior behavior."""
    timeline = list(spec.get("timeline", []) or [])
    entry: dict[str, Any] = {
        "at": now,
        "actor": actor,
        "type": event_type,
        "source": source,
    }
    for k, v in fields.items():
        if v not in (None, "", [], {}):
            entry[k] = v
    timeline.append(entry)
    spec["timeline"] = timeline


def next_issue_number(existing_names: list[str]) -> int:
    """Next free ``i-NNN`` number given the existing Issue doc names (pure)."""
    max_n = 0
    for nm in existing_names:
        m = re.match(r"^i-(\d+)", nm or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def looks_like_decision(body: str) -> bool:
    """Heuristic: a decision-shaped comment auto-promotes to a ``decision`` event.

    Mirrors the CLI's ``_looks_like_decision`` — a body that opens with a decision
    verb ("decidi", "decided", "chose", "vamos", "will") reads as a decision, not a
    plain comment. Kept deliberately small + language-tolerant (pt-BR + en)."""
    head = body.strip().lower()[:40]
    return any(
        head.startswith(v)
        for v in ("decidi", "decided", "decision:", "chose", "escolhi",
                  "vamos ", "we will", "will ", "opt", "optamos")
    )


def validate_transition(kind: str, target: str) -> None:
    """Raise :class:`InvalidTransition` unless ``target`` is a valid status for
    ``kind``. The Kind must itself be a writable board Kind."""
    if kind not in _STATUS_ENUMS:
        raise InvalidTransition(
            f"{kind!r} is not a status-bearing board Kind "
            f"(writable: {sorted(_WRITABLE_KINDS)})"
        )
    valid = _STATUS_ENUMS[kind]
    if target not in valid:
        raise InvalidTransition(
            f"{target!r} is not a valid {kind} status — valid: {list(valid)}"
        )


# ── pure spec builders (shared by the CLI create commands + the async cores) ─


def build_story_spec(
    *, title: str | None, description: str, feature: str,
    status: str = "todo", priority: str | None = None,
    labels: list[str] | None = None, reporter: str | None = None,
    owner: str | None = None,
    acceptance_criteria: list[str] | None = None,
    definition_of_done: list[str] | None = None,
    ac_source: str | None = None, dod_source: str | None = None,
    now: str, actor: str, source: str,
) -> dict[str, Any]:
    """Build a Story ``spec`` (title-fallback, created/updated stamps, initial
    timeline event) — the exact shape ``dna sdlc story create`` writes."""
    effective_title = title
    if effective_title is None:
        first_line = description.splitlines()[0] if description else ""
        effective_title = first_line[:80] if first_line else feature
    spec: dict[str, Any] = {
        "title": effective_title,
        "description": description,
        "status": status,
        "feature": feature,
    }
    if owner:
        spec["owner"] = owner
    if priority:
        spec["priority"] = priority
    if labels:
        spec["labels"] = list(labels)
    if reporter:
        spec["reporter"] = reporter
    if acceptance_criteria:
        spec["acceptance_criteria"] = list(acceptance_criteria)
        spec["acceptance_criteria_source"] = ac_source or "cli-create"
    if definition_of_done:
        spec["definition_of_done"] = list(definition_of_done)
        spec["definition_of_done_source"] = dod_source or "cli-create"
    spec["created_at"] = now
    spec["updated_at"] = now
    append_event(spec, "status_change", to=status, now=now, actor=actor, source=source)
    return spec


def build_issue_spec(
    *, description: str, issue_type: str = "bug", severity: str = "medium",
    status: str = "open", owner: str | None = None,
    related_feature: str | None = None, related_finding: str | None = None,
    now: str, actor: str, source: str,
) -> dict[str, Any]:
    """Build an Issue ``spec`` (type/severity/status + initial timeline event) —
    the shape ``dna sdlc issue file`` writes."""
    spec: dict[str, Any] = {
        "description": description,
        "type": issue_type,
        "severity": severity,
        "status": status,
    }
    if owner:
        spec["owner"] = owner
    if related_feature:
        spec["related_feature"] = related_feature
    if related_finding:
        spec["related_finding"] = related_finding
    append_event(spec, "status_change", to=status, now=now, actor=actor, source=source)
    return spec


def build_feature_spec(
    *, title: str, description: str, status: str = "discovery",
    epic: str | None = None, owner: str | None = None,
    reporter: str | None = None, priority: str | None = None,
    labels: list[str] | None = None, business_value: int | None = None,
    now: str, actor: str, source: str,
) -> dict[str, Any]:
    """Build a Feature ``spec`` (roadmap noun; no AC/DoD guard) — the shape
    ``dna sdlc feature create`` writes."""
    spec: dict[str, Any] = {
        "title": title,
        "description": description,
        "status": status,
    }
    if epic:
        spec["epic"] = epic
    if owner:
        spec["owner"] = owner
    spec["reporter"] = reporter or "mcp"
    if priority:
        spec["priority"] = priority
    if labels:
        spec["labels"] = list(labels)
    if business_value is not None:
        spec["business_value"] = business_value
    spec["created_at"] = now
    spec["updated_at"] = now
    append_event(spec, "status_change", to=status, now=now, actor=actor, source=source)
    return spec


# ── async kernel-level cores (the write goes through kernel.write_document) ──
#
# The SDLC board Kinds (Story / Issue / Feature) are TenantScope.GLOBAL — the
# board is a PROJECT-level artifact, not per-tenant data (SdlcExtension:
# "SDLC primitives are project-level, not per-tenant"). So a write is GLOBAL
# (no ``kernel.with_tenant`` overlay — that would raise TenantNotAllowed). Under
# Model B multi-workspace, isolation is by SCOPE instead: a workspace's board
# lives in its OWN scope (``live.default_scope(workspace)``), and the MCP
# ``_guard`` scope-binding denies a cross-workspace scope. The ``*_impl``
# wrappers below resolve that scope; these cores only take the resolved scope.


async def create_story(
    kernel: Any, scope: str, name: str, *, feature: str, description: str,
    title: str | None = None, status: str = "todo",
    priority: str | None = None, labels: list[str] | None = None,
    reporter: str | None = None, owner: str | None = None,
    acceptance_criteria: list[str] | None = None,
    definition_of_done: list[str] | None = None,
    actor: str = "mcp", source: str = "mcp",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create a Story doc — the shared core behind ``dna sdlc story create`` + the
    MCP ``create_story`` tool. Routes through ``kernel.write_document`` (hooks +
    cache fire) into the resolved (per-workspace) ``scope``."""
    ni = now_iso(now)
    spec = build_story_spec(
        title=title, description=description, feature=feature, status=status,
        priority=priority, labels=labels, reporter=reporter or actor, owner=owner,
        acceptance_criteria=acceptance_criteria,
        definition_of_done=definition_of_done,
        now=ni, actor=actor, source=source,
    )
    raw = build_raw("Story", name, spec)
    await kernel.write_document(scope, "Story", name, raw, invalidate_mode="doc")
    return {"kind": "Story", "name": name, "status": status, "feature": feature}


async def create_issue(
    kernel: Any, scope: str, slug: str, *, description: str,
    issue_type: str = "bug", severity: str = "medium",
    related_feature: str | None = None, owner: str | None = None,
    actor: str = "mcp", source: str = "mcp",
    now: datetime | None = None,
) -> dict[str, Any]:
    """File an Issue with an auto-incremented ``i-NNN-<slug>`` name — the shared
    core behind ``dna sdlc issue file`` + the MCP ``create_issue`` tool."""
    names: list[str] = []
    async for row in kernel.query(scope, "Issue"):
        meta = row.get("metadata") if isinstance(row, dict) else None
        nm = (meta or {}).get("name") if isinstance(meta, dict) else None
        names.append(nm or (row.get("name") if isinstance(row, dict) else "") or "")
    n = next_issue_number(names)
    name = f"i-{n:03d}-{slug}"
    ni = now_iso(now)
    spec = build_issue_spec(
        description=description, issue_type=issue_type, severity=severity,
        owner=owner, related_feature=related_feature,
        now=ni, actor=actor, source=source,
    )
    raw = build_raw("Issue", name, spec)
    await kernel.write_document(scope, "Issue", name, raw, invalidate_mode="doc")
    return {"kind": "Issue", "name": name, "type": issue_type, "severity": severity}


async def create_feature(
    kernel: Any, scope: str, name: str, *, title: str, description: str,
    epic: str | None = None, status: str = "discovery",
    priority: str | None = None, labels: list[str] | None = None,
    reporter: str | None = None, owner: str | None = None,
    actor: str = "mcp", source: str = "mcp",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create a Feature doc — the shared core behind ``dna sdlc feature create`` +
    the MCP ``create_feature`` tool."""
    ni = now_iso(now)
    spec = build_feature_spec(
        title=title, description=description, status=status, epic=epic,
        owner=owner, reporter=reporter or actor, priority=priority, labels=labels,
        now=ni, actor=actor, source=source,
    )
    raw = build_raw("Feature", name, spec)
    await kernel.write_document(scope, "Feature", name, raw, invalidate_mode="doc")
    return {"kind": "Feature", "name": name, "status": status}


async def set_status(
    kernel: Any, scope: str, kind: str, name: str, status: str, *,
    reason: str | None = None, actor: str = "mcp", source: str = "mcp",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Transition a Story / Issue / Feature to ``status`` (load-modify-write) —
    the shared core behind the CLI's ``start`` / ``done`` / ``block`` / ``review``
    / ``triage`` / ``resolve`` / ``ship`` verbs + the MCP ``set_status`` tool.

    Validates the target against the Kind's status enum (:func:`validate_transition`),
    appends a ``status_change`` timeline event (with the ``from``), auto-stamps
    ``closed_at`` on a terminal status and ``blocked_reason`` when ``reason`` is
    given for a block. Raises ``LookupError`` if the doc is absent."""
    validate_transition(kind, status)
    existing = await kernel.get_document(scope, kind, name)
    if existing is None:
        raise LookupError(f"{kind} {name!r} not found in scope {scope!r}")
    spec = dict(existing.get("spec") or {}) if isinstance(existing, dict) else {}
    prev = spec.get("status")
    ni = now_iso(now)
    spec["status"] = status
    spec["updated_at"] = ni
    if status in _TERMINAL_STATUS:
        spec["closed_at"] = ni
    if reason:
        spec["blocked_reason" if status == "blocked" else "resolution"] = reason
    extra: dict[str, Any] = {"from": prev, "to": status}
    if reason:
        extra["summary"] = reason
    append_event(spec, "status_change", now=ni, actor=actor, source=source, **extra)
    raw = build_raw(kind, name, spec)
    await kernel.write_document(scope, kind, name, raw, invalidate_mode="doc")
    return {"kind": kind, "name": name, "from": prev, "to": status}


async def add_comment(
    kernel: Any, scope: str, kind: str, name: str, body: str, *,
    event_type: str | None = None, actor: str = "mcp", source: str = "mcp",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append a comment / decision to a board item's timeline WITHOUT changing
    status — the FOCUS-feed narration verb (``dna sdlc story comment`` /
    ``issue comment``) + the MCP ``comment`` tool. A decision-shaped body
    auto-promotes to a ``decision`` event unless ``event_type`` is explicit."""
    if kind not in _WRITABLE_KINDS:
        raise InvalidTransition(
            f"{kind!r} is not a commentable board Kind "
            f"(writable: {sorted(_WRITABLE_KINDS)})"
        )
    et = event_type or ("decision" if looks_like_decision(body) else "comment")
    if et not in ("comment", "decision"):
        raise InvalidTransition(f"{et!r} is not a valid comment type (comment/decision)")
    existing = await kernel.get_document(scope, kind, name)
    if existing is None:
        raise LookupError(f"{kind} {name!r} not found in scope {scope!r}")
    spec = dict(existing.get("spec") or {}) if isinstance(existing, dict) else {}
    ni = now_iso(now)
    append_event(spec, et, summary=body, now=ni, actor=actor, source=source)
    spec["updated_at"] = ni
    raw = build_raw(kind, name, spec)
    await kernel.write_document(scope, kind, name, raw, invalidate_mode="doc")
    return {"kind": kind, "name": name, "event_type": et}


# ── LiveDna wrappers (the MCP `*_impl` convention — resolve scope + delegate) ─
#
# The board is GLOBAL, so ``tenant`` (the resolved workspace) selects the SCOPE
# via ``live.default_scope(tenant)`` — it is NOT threaded into the write (that
# would raise TenantNotAllowed on a GLOBAL Kind). Under Model B this routes each
# workspace's board into its own scope; single-workspace / OSS resolves to the
# base scope unchanged.


async def create_story_impl(
    live: LiveDna, name: str, *, feature: str, description: str,
    title: str | None = None, priority: str | None = None,
    labels: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    definition_of_done: list[str] | None = None,
    scope: str | None = None, tenant: str | None = None,
    actor: str = "mcp",
) -> dict[str, Any]:
    """LiveDna wrapper for :func:`create_story` — resolves the (per-workspace)
    scope and writes the GLOBAL board doc there."""
    sc = scope or live.default_scope(tenant)
    return await create_story(
        live.kernel, sc, name, feature=feature, description=description,
        title=title, priority=priority, labels=labels,
        acceptance_criteria=acceptance_criteria,
        definition_of_done=definition_of_done, actor=actor,
    )


async def create_issue_impl(
    live: LiveDna, slug: str, *, description: str, issue_type: str = "bug",
    severity: str = "medium", related_feature: str | None = None,
    scope: str | None = None, tenant: str | None = None, actor: str = "mcp",
) -> dict[str, Any]:
    """LiveDna wrapper for :func:`create_issue`."""
    sc = scope or live.default_scope(tenant)
    return await create_issue(
        live.kernel, sc, slug, description=description, issue_type=issue_type,
        severity=severity, related_feature=related_feature, actor=actor,
    )


async def create_feature_impl(
    live: LiveDna, name: str, *, title: str, description: str,
    epic: str | None = None, priority: str | None = None,
    labels: list[str] | None = None, scope: str | None = None,
    tenant: str | None = None, actor: str = "mcp",
) -> dict[str, Any]:
    """LiveDna wrapper for :func:`create_feature`."""
    sc = scope or live.default_scope(tenant)
    return await create_feature(
        live.kernel, sc, name, title=title, description=description, epic=epic,
        priority=priority, labels=labels, actor=actor,
    )


async def set_status_impl(
    live: LiveDna, kind: str, name: str, status: str, *,
    reason: str | None = None, scope: str | None = None,
    tenant: str | None = None, actor: str = "mcp",
) -> dict[str, Any]:
    """LiveDna wrapper for :func:`set_status`."""
    sc = scope or live.default_scope(tenant)
    return await set_status(
        live.kernel, sc, kind, name, status, reason=reason, actor=actor,
    )


async def comment_impl(
    live: LiveDna, kind: str, name: str, body: str, *,
    event_type: str | None = None, scope: str | None = None,
    tenant: str | None = None, actor: str = "mcp",
) -> dict[str, Any]:
    """LiveDna wrapper for :func:`add_comment`."""
    sc = scope or live.default_scope(tenant)
    return await add_comment(
        live.kernel, sc, kind, name, body, event_type=event_type, actor=actor,
    )
