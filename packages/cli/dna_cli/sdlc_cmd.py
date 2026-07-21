"""``dna sdlc`` — declarative SDLC tracking via SdlcExtension Kinds.

Replaces the multi-step protocol (edit YAML → DELETE Postgres rows →
reseed → restart harness → curl) with one-line commands that go through
the kernel's write_document path. The kernel handles cache invalidation
via the EventBus (Phase 15.1 on Postgres) so subscribers see writes
immediately — no reseed, no restart.

Subcommands::

    dna sdlc next                                              # what to do
    dna sdlc list <Kind> [--status X] [--owner Y]             # filtered table
    dna sdlc story create <name> --feature F --desc "..."      # create
    dna sdlc story start <name>                                # → in-progress
    dna sdlc story done <name>                                 # → done + closed_at
    dna sdlc story block <name> --reason "..."                 # → blocked
    dna sdlc issue file <name> --type bug --severity high ...  # create
    dna sdlc epic show <name>                             # burndown
    dna sdlc epic ship <name>                             # → done + cascade

Scope resolution (i-012) — every verb resolves its scope with the same
precedence: ``--scope`` flag > env ``DNA_SDLC_SCOPE`` > auto-detected
sole SDLC scope in the source > ``dna-development`` (compat fallback).
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

import click

from dna_cli import _git_symbiosis as _gitsym
from dna_cli._active_story import (
    clear_if_matches as _active_story_clear_if_matches,
    write_active_story as _active_story_write,
)
from dna_cli._ctx import (
    fail,
    open_session,
    print_json,
    print_table,
)


# The SDLC write PRIMITIVES + enums live in the transport-agnostic core
# ``dna.application.sdlc`` (adr-faces-reorg) so the CLI + the MCP server share ONE
# write path — the doc envelope, the timeline event, the issue numbering, and the
# valid-status enums are defined ONCE. The CLI imports them here and its thin
# ``_build_raw`` / ``_append_timeline`` / ``_next_issue_number`` wrappers below
# adapt them to the CLI's clock + actor + ``source="cli"``.
from dna.application.sdlc import (  # noqa: E402, F401 — enums re-exported for back-compat
    SDLC_API_VERSION,
    VALID_EPIC_STATUS,
    VALID_FEATURE_STATUS,
    VALID_ISSUE_SEVERITY,
    VALID_ISSUE_STATUS,
    VALID_ISSUE_TYPE,
    VALID_PRIORITIES,
    VALID_STORY_STATUS,
    append_event as _core_append_event,
    build_raw as _core_build_raw,
    next_issue_number as _core_next_issue_number,
)

# The shared spine (clock, actor, git/gh probes, timeline appender, document
# envelope, post-transition hooks, scope resolution) moved to the decomposed
# package in ``dna_cli.sdlc._common``. Re-exported here so that
# ``from dna_cli.sdlc_cmd import X`` — the path tests and host platforms use —
# keeps resolving, the same idiom kernel/__init__.py adopted during its own
# decomposition.
from dna_cli.sdlc._common import (  # noqa: F401 — re-exported for back-compat
    DEFAULT_SCOPE,
    VALID_JOURNEY_METHODOLOGIES,
    VALID_JOURNEY_PHASES,
    _POST_TRANSITION_HOOKS,
    _SDLC_CONTAINERS,
    _append_timeline,
    _autodetect_sdlc_scope,
    _build_raw,
    _cli_actor,
    _fire_post_transition,
    _gh_open_prs,
    _gh_open_prs_for_branch,
    _git_current_branch,
    _git_head_sha,
    _now_iso,
    _parse_iso_utc,
    _resolve_scope_default,
    _scope_callback,
    _scope_option,
    register_post_transition_hook,
    review_pr_guard,
)


def _build_kaizen_event(
    *, body: str, issue: str | None, actor: str, now: str,
    kaizen_doc: str | None = None,
) -> dict[str, Any]:
    """Build a ``kaizen`` timeline entry (pure — no clock/env access).

    Phase B (f-sdlc-realtime-observability): a flagged kaizen observation
    surfaces live in the FOCUS feed (``_FEED_TYPES`` includes ``kaizen``).
    ``issue`` links the Issue/Story that captured the improvement and is
    dropped when falsy. ``kaizen_doc`` (s-kaizen-kind) refs the Kaizen
    doc twin so the event ↔ doc linkage is traversable both ways.
    """
    entry: dict[str, Any] = {
        "type": "kaizen",
        "summary": body,
        "actor": actor,
        "at": now,
        "source": "cli",
    }
    if issue:
        entry["issue"] = issue
    if kaizen_doc:
        entry["kaizen_doc"] = kaizen_doc
    return entry


def _kaizen_slug(body: str) -> str:
    """Kebab slug from the observation body for the kz-NNN-<slug> name.

    Lowercase, non-alnum runs → hyphen, capped at ~28 chars (the NNN
    counter already guarantees uniqueness — no hash needed).
    """
    base = re.sub(r"[^a-z0-9]+", "-", body.lower()).strip("-")
    return base[:28].rstrip("-") or "obs"


def _next_kaizen_number(s: Any) -> int:
    """Next available kz-NNN number (mirror of ``_next_issue_number``,
    but reuses the caller's open session)."""
    max_n = 0
    for d in s.query_list("Kaizen"):
        m = re.match(r"^kz-(\d+)", d.name)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def _build_kaizen_doc_spec(
    *, body: str, work_item: str, issue: str | None, actor: str, now: str,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Spec for the first-class Kaizen doc (s-kaizen-kind, pure).

    Status arc: ``observed`` (just noticed) or ``routed`` straight away
    when ``--issue`` already names the Issue/Story tracking the fix.
    ``labels`` (optional, repeatable via ``--label``) are free-form theme
    tags weighted into semantic-search source text.
    """
    spec: dict[str, Any] = {
        "body": body,
        "work_item": work_item,
        "status": "routed" if issue else "observed",
        "actor": actor,
        "created_at": now,
    }
    if issue:
        spec["issue"] = issue
    if labels:
        spec["labels"] = list(labels)
    return spec


# ---------------------------------------------------------------------------
# Group root — moved to the decomposed package (dna_cli/sdlc/_root.py) so
# group modules can attach to it without a cycle through this module.
# Re-exported: `from dna_cli.sdlc_cmd import sdlc` keeps resolving.
# ---------------------------------------------------------------------------

from dna_cli.sdlc._root import sdlc  # noqa: E402, F401 — re-exported for back-compat


# ---------------------------------------------------------------------------
# `dna sdlc next` — what should I do now?
# ---------------------------------------------------------------------------

@sdlc.command("current")
@click.option("--json", "as_json", is_flag=True)
@_scope_option
def cmd_current(scope: str, as_json: bool) -> None:
    """Show every SDLC doc currently in-progress (across Stories,
    Features, Epics, Issues). Designed for one-line surface in
    Claude Code chat — pipe the IDs into the Studio search (⌘K) to
    confirm visually.

    Output format (compact, copy-paste-friendly):

        🚧 in-progress now (scope: dna-development)
          📖 s-vibe-commit-trace                "Studio commit_ref link..."
          🚀 f-activity-timeline                "Activity Timeline..."

    With ``--json`` returns a structured list for programmatic use.
    """
    rows: list[dict[str, Any]] = []
    with open_session(scope) as s:
        for kind, icon, statuses in (
            ("Story", "📖", {"in-progress"}),
            ("Feature", "🚀", {"in-development"}),
            ("Epic", "🎯", {"in-progress"}),
            ("Issue", "🐞", {"in-progress", "triaged"}),
        ):
            for d in s.query_list(kind):
                spec = d.spec if isinstance(d.spec, dict) else dict(d.spec)
                if spec.get("status") in statuses:
                    rows.append({
                        "kind": kind,
                        "icon": icon,
                        "name": d.name,
                        "title": (spec.get("title") or spec.get("description") or "")[:60],
                        "status": spec.get("status"),
                        "owner": spec.get("owner") or "",
                    })
    if as_json:
        print_json(rows)
        return
    if not rows:
        click.secho(
            f"✓ no in-progress docs in scope {scope!r} — clean slate",
            fg="green",
        )
        return
    click.secho(f"🚧 in-progress now (scope: {scope})", fg="yellow", bold=True)
    for r in rows:
        click.echo(
            f"  {r['icon']} "
            f"{click.style(r['name'], fg='cyan', bold=True):40s}  "
            f"\"{r['title']}\""
        )


@sdlc.command("brief")
@_scope_option
@click.option("--limit", default=5, show_default=True,
              help="Max items in the recent-sessions / recent-lessons sections.")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Structured output for programmatic use.")
def cmd_brief(scope: str, limit: int, as_json: bool) -> None:
    """Session-start briefing — one screen with everything the next session
    needs to bootstrap context: in-progress work, open spikes, recent
    AgentSessions, recent Engram, and open high/critical Issues.

    The cross-session "recall in" command: run it at the START of a session
    (yours or another agent's) instead of `current` + `session list` +
    `remember` separately. Read-only.
    """
    def _spec(d: Any) -> dict:
        return d.spec if isinstance(d.spec, dict) else dict(d.spec or {})

    def _ts(spec: dict, *keys: str) -> str:
        for k in keys:
            v = spec.get(k)
            if v:
                return str(v)
        return ""

    sections: dict[str, list] = {}
    with open_session(scope) as s:
        in_progress: list[dict] = []
        for kind, icon, statuses in (
            ("Story", "📖", {"in-progress"}),
            ("Feature", "🚀", {"in-development"}),
            ("Epic", "🎯", {"in-progress"}),
        ):
            for d in s.query_list(kind):
                spec = _spec(d)
                if spec.get("status") in statuses:
                    in_progress.append({
                        "icon": icon, "name": d.name,
                        "title": (spec.get("title") or spec.get("description") or "")[:60],
                    })
        sections["in_progress"] = in_progress

        spikes: list[dict] = []
        for d in s.query_list("Spike"):
            spec = _spec(d)
            if spec.get("status") in ("proposed", "in-progress"):
                spikes.append({
                    "name": d.name, "status": spec.get("status"),
                    "q": (spec.get("question_to_answer") or spec.get("title") or "")[:70],
                })
        sections["spikes"] = spikes

        sessions = [
            {"name": d.name, "when": _ts(_spec(d), "started_at", "created_at", "period_start")[:10]}
            for d in s.query_list("AgentSession")
        ]
        sessions.sort(key=lambda x: x["when"], reverse=True)
        sections["sessions"] = sessions[:limit]

        lessons = [
            {
                "name": d.name,
                "summary": (_spec(d).get("summary") or "")[:70],
                "affect": _spec(d).get("affect") or "",
                "when": _ts(_spec(d), "created_at"),
            }
            for d in s.query_list("Engram")
        ]
        lessons.sort(key=lambda x: x["when"], reverse=True)
        sections["lessons"] = lessons[:limit]

        issues: list[dict] = []
        for d in s.query_list("Issue"):
            spec = _spec(d)
            if spec.get("status") in ("open", "triaged") and spec.get("severity") in ("high", "critical"):
                issues.append({
                    "name": d.name, "severity": spec.get("severity"),
                    "desc": (spec.get("description") or "")[:60],
                })
        sections["issues"] = issues

    # Open GitHub PRs (i-127) — the inverse radar: a PR aberto e esquecido
    # não aparece no board (caso real: #278 órfão por 1 dia). Fail-soft.
    open_prs = _gh_open_prs()
    if open_prs is None:
        sections["open_prs"] = None
    else:
        now = datetime.now(timezone.utc)
        rows = []
        for pr in open_prs:
            created = _parse_iso_utc(pr.get("createdAt"))
            age_h = (now - created).total_seconds() / 3600 if created else None
            rows.append({
                "number": pr.get("number"),
                "title": (pr.get("title") or "")[:60],
                "branch": pr.get("headRefName") or "",
                "created_at": pr.get("createdAt") or "",
                "stale_24h": bool(age_h is not None and age_h > 24),
            })
        sections["open_prs"] = rows

    if as_json:
        print_json(sections)
        return

    click.secho(f"\n🧭 Session brief — scope {scope}", fg="cyan", bold=True)
    click.secho(f"\n🚧 In progress ({len(sections['in_progress'])})", fg="yellow", bold=True)
    for r in sections["in_progress"]:
        click.echo(f"  {r['icon']} {r['name']}  {r['title']}")
    if not sections["in_progress"]:
        click.echo("  (clean slate)")
    click.secho(f"\n🔬 Open spikes ({len(sections['spikes'])})", fg="magenta", bold=True)
    for r in sections["spikes"]:
        click.echo(f"  • {r['name']}  [{r['status']}]  {r['q']}")
    if not sections["spikes"]:
        click.echo("  (none)")
    click.secho(f"\n🗒️  Recent sessions (top {limit})", fg="blue", bold=True)
    for r in sections["sessions"]:
        click.echo(f"  • {r['when']}  {r['name']}")
    click.secho(f"\n💭 Recent lessons (top {limit})", fg="green", bold=True)
    for r in sections["lessons"]:
        click.echo(f"  • [{r['affect']}] {r['name']}  {r['summary']}")
    click.secho(f"\n🐞 Open high/critical issues ({len(sections['issues'])})", fg="red", bold=True)
    for r in sections["issues"]:
        click.echo(f"  • {r['name']}  [{r['severity']}]  {r['desc']}")
    prs = sections["open_prs"]
    if prs is None:
        click.secho("\n🔀 Open PRs", fg="cyan", bold=True)
        click.echo("  (gh indisponível)")
    else:
        click.secho(f"\n🔀 Open PRs ({len(prs)})", fg="cyan", bold=True)
        for r in prs:
            stale = "  ⚠ >24h" if r["stale_24h"] else ""
            click.echo(f"  • #{r['number']}  {r['title']}  [{r['branch']}]{stale}")
        if not prs:
            click.echo("  (none)")
    click.echo("")


@sdlc.command("next")
@_scope_option
def cmd_next(scope: str) -> None:
    """Snapshot of active work — in-progress epic, pending stories, open issues."""
    with open_session(scope) as s:
        mi = s.mi
        in_progress_ms = [
            m for m in s.query_list("Epic")
            if m.spec.get("status") == "in-progress"
        ]
        planning_ms = [
            m for m in s.query_list("Epic")
            if m.spec.get("status") == "planning"
        ]
        pending_stories = [
            st for st in s.query_list("Story")
            if st.spec.get("status") in ("todo", "in-progress")
        ]
        open_issues = [
            i for i in s.query_list("Issue")
            if i.spec.get("status") in ("open", "triaged")
        ]

        click.secho(f"\nScope: {scope}", fg="cyan", bold=True)

        click.secho("\nActive Epics:", fg="yellow", bold=True)
        if in_progress_ms:
            for m in in_progress_ms:
                target = m.spec.get("target_date", "?")
                pkg = m.spec.get("target_package", "")
                ver = m.spec.get("target_version", "")
                pkg_str = f" → {pkg}@{ver}" if pkg else ""
                click.echo(f"  ● {m.name} (target: {target}){pkg_str}")
        else:
            click.echo("  (none in-progress)")

        click.secho("\nPlanning Epics (next up):", fg="blue")
        if planning_ms:
            for m in planning_ms[:5]:
                click.echo(
                    f"  ○ {m.name} (target: {m.spec.get('target_date','?')})"
                )
        else:
            click.echo("  (none planning)")

        click.secho("\nPending Stories:", fg="yellow", bold=True)
        if pending_stories:
            for st in pending_stories:
                status = st.spec.get("status", "?")
                feature = st.spec.get("feature", "")
                est = st.spec.get("estimate")
                color = "green" if status == "in-progress" else None
                click.secho(
                    f"  [{status}] {st.name} (feature: {feature}, est: {est})",
                    fg=color,
                )
        else:
            click.echo("  (no pending stories)")

        click.secho("\nOpen Issues:", fg="red", bold=True)
        if open_issues:
            for i in open_issues:
                t = i.spec.get("type", "?")
                sev = i.spec.get("severity", "?")
                st = i.spec.get("status", "?")
                click.echo(f"  [{sev}/{st}] {i.name} ({t})")
        else:
            click.echo("  (no open issues)")
        click.echo("")


# ---------------------------------------------------------------------------
# `dna sdlc list <Kind>`
# ---------------------------------------------------------------------------

@sdlc.command("list")
@click.argument("kind", type=click.Choice(["Roadmap", "Epic", "Feature", "Story", "Issue", "Spec", "Plan"]))
@click.option("--status", default=None, help="Filter by spec.status.")
@click.option("--owner", default=None, help="Filter by spec.owner.")
@click.option("--feature", default=None, help="Filter Stories by spec.feature.")
@click.option("--epic", default=None, help="Filter Features by spec.epic.")
@_scope_option
@click.option("--json", "as_json", is_flag=True)
def cmd_list(
    kind: str, status: str | None, owner: str | None,
    feature: str | None, epic: str | None,
    scope: str, as_json: bool,
) -> None:
    """Tabular list of SDLC docs filtered by status/owner/parent ref."""
    with open_session(scope) as s:
        items = s.query_list(kind)
        if status:
            items = [i for i in items if i.spec.get("status") == status]
        if owner:
            items = [i for i in items if i.spec.get("owner") == owner]
        if feature and kind == "Story":
            items = [i for i in items if i.spec.get("feature") == feature]
        if epic and kind == "Feature":
            items = [i for i in items if i.spec.get("epic") == epic]

        if as_json:
            print_json([
                {"name": i.name, "kind": kind, **(i.spec if isinstance(i.spec, dict) else {})}
                for i in items
            ])
            return

        if not items:
            click.secho(f"(no {kind}s match)", fg="yellow", err=True)
            return

        cols = ["name", "status"]
        if kind == "Epic":
            cols += ["target_date", "target_package", "target_version"]
        elif kind == "Feature":
            cols += ["priority", "epic", "owner"]
        elif kind == "Story":
            cols += ["priority", "feature", "owner", "estimate"]
        elif kind == "Issue":
            cols = ["name", "status", "type", "severity", "owner"]
        elif kind == "Spec":
            cols = ["name", "status", "date", "pattern", "title"]
        elif kind == "Plan":
            cols = ["name", "status", "date", "pattern", "spec_ref", "title"]
        else:  # Roadmap
            cols = ["name", "owner_team"]

        # i-041: surface priority. Sort Story/Feature by priority so "what's
        # prioritized" is obvious at a glance (highest first; unset sinks).
        if "priority" in cols:
            _rank = {"highest": 0, "high": 1, "medium": 2, "low": 3, "lowest": 4}
            items = sorted(
                items,
                key=lambda i: _rank.get(
                    (i.spec.get("priority") if isinstance(i.spec, dict) else None) or "medium", 2,
                ),
            )

        rows = []
        for i in items:
            row = {"name": i.name}
            for c in cols[1:]:
                row[c] = i.spec.get(c, "") if isinstance(i.spec, dict) else ""
            rows.append(row)
        print_table(rows, cols)


# ---------------------------------------------------------------------------
# Story subgroup
# ---------------------------------------------------------------------------

@sdlc.group("story")
def story_group() -> None:
    """Story-level operations."""


# VALID_PRIORITIES is imported from the shared core (dna.application.sdlc) at the
# top of this module — the single source of truth shared with the MCP write tools.


def _csv(value: str | None) -> list[str] | None:
    """Parse comma-separated CLI input. None/empty → None (not stamped)."""
    if value is None:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts or None


@story_group.command("create")
@click.argument("name")
@click.option("--feature", required=True, help="Parent Feature name.")
@click.option(
    "--allow-no-ac-dod",
    is_flag=True,
    default=False,
    help="Skip the AC + DoD guard. Use ONLY for back-compat backfills or "
         "exceptional grooming. Stories filed without acceptance_criteria + "
         "definition_of_done are blocked by default because they ship without "
         "exit criteria — see chat 2026-05-14 + memory feedback_story_ac_dod_required.",
)
@click.option("--title", default=None,
              help="Short Jira-style title shown on cards. Falls back to "
                   "first line of --desc (truncated to 80 chars) when omitted.")
@click.option("--desc", "description", required=True, help="One-line description.")
@click.option("--owner", default=None)
@click.option("--estimate", type=int, default=None)
@click.option("--status", type=click.Choice(VALID_STORY_STATUS), default="todo")
# v1.5 — board-grade fields.
@click.option("--priority", type=click.Choice(VALID_PRIORITIES), default=None,
              help="Board priority (default: medium when set; else field omitted).")
@click.option("--labels", default=None, help="Comma-separated labels.")
@click.option("--reporter", default=None, help="Actor who filed it.")
@click.option("--sprint", "sprint_ref", default=None, help="Sprint identifier.")
@click.option("--business-value", "business_value", type=int, default=None,
              help="WSJF-style scalar (0-1000).")
@click.option("--ac", "acceptance_criteria", multiple=True,
              help="Acceptance criterion (repeatable). Each --ac adds one bullet "
                   "to spec.acceptance_criteria. Use Given/When/Then prose.")
@click.option("--dod", "definition_of_done", multiple=True,
              help="Definition of Done item (repeatable). Each --dod adds one "
                   "bullet to spec.definition_of_done. Cover Code/Tests/Docs/CI/UX.")
@click.option("--ac-source", "ac_source", default=None,
              help="Provenance tag for acceptance_criteria (e.g. claude-code, "
                   "llm-analyst-backfill, human).")
@click.option("--dod-source", "dod_source", default=None,
              help="Provenance tag for definition_of_done.")
@_scope_option
def cmd_story_create(
    name: str, feature: str, title: str | None, description: str,
    owner: str | None, estimate: int | None, status: str,
    priority: str | None, labels: str | None, reporter: str | None,
    sprint_ref: str | None, business_value: int | None,
    acceptance_criteria: tuple[str, ...], definition_of_done: tuple[str, ...],
    ac_source: str | None, dod_source: str | None, scope: str,
    allow_no_ac_dod: bool = False,
) -> None:
    """Create a new Story.

    AC + DoD guard (2026-05-14): without --ac and --dod the command
    refuses. Stories that ship "todo" but don't declare exit criteria
    are the root of the silent-skip-DoD pattern user flagged in chat.
    Override with --allow-no-ac-dod only for back-compat backfills.
    """
    if not allow_no_ac_dod:
        missing = []
        if not acceptance_criteria:
            missing.append("--ac (acceptance criterion, repeatable)")
        if not definition_of_done:
            missing.append("--dod (definition-of-done item, repeatable)")
        if missing:
            raise click.UsageError(
                "Story create rejected — missing exit criteria:\n"
                + "\n".join(f"  • {m}" for m in missing)
                + "\n\nFill with --ac / --dod (each repeatable). Examples:\n"
                  "  --ac 'Given X, when Y, then Z'\n"
                  "  --dod 'Code merged + tests >90% coverage'\n"
                  "  --dod 'Docs updated in CLAUDE.md'\n\n"
                  "Backfill / exception: pass --allow-no-ac-dod (rare; use for\n"
                  "back-compat scripts only, not for new dev work)."
            )
    # Derive title from description when omitted — Studio's StoryCard
    # falls back to truncated description otherwise, which makes cards
    # nearly unreadable. ALWAYS populate title so the board surfaces a
    # human-readable label.
    effective_title = title
    if effective_title is None:
        first_line = description.splitlines()[0] if description else ""
        effective_title = first_line[:80] if first_line else name
    spec: dict[str, Any] = {
        "title": effective_title,
        "description": description,
        "status": status,
        "feature": feature,
    }
    if owner:
        spec["owner"] = owner
    if estimate is not None:
        spec["estimate"] = estimate
    if priority:
        spec["priority"] = priority
    labels_list = _csv(labels)
    if labels_list:
        spec["labels"] = labels_list
    if reporter:
        spec["reporter"] = reporter
    if sprint_ref:
        spec["sprint_ref"] = sprint_ref
    if business_value is not None:
        spec["business_value"] = business_value
    # v1.7 — gapless DoD: AC and DoD as first-class structured fields
    # so Studio surfaces them on Story cards. Repeatable --ac / --dod.
    if acceptance_criteria:
        spec["acceptance_criteria"] = list(acceptance_criteria)
        spec["acceptance_criteria_source"] = ac_source or "cli-create"
    if definition_of_done:
        spec["definition_of_done"] = list(definition_of_done)
        spec["definition_of_done_source"] = dod_source or "cli-create"
    # v1.5: auto-stamp created_at + updated_at on every create.
    now = _now_iso()
    spec["created_at"] = now
    spec["updated_at"] = now
    # v1.6: first timeline event = the create itself (no `from`).
    _append_timeline(spec, "status_change", to=status)

    raw = _build_raw("Story", name, spec)
    with open_session(scope) as s:
        s.run(s.kernel.write_document(scope, "Story", name, raw))
    click.secho(f"CREATED Story/{name} (feature: {feature}, status: {status})", fg="green")


def _update_story_status(
    scope: str, name: str, new_status: str,
    extras: dict[str, Any] | None = None,
    produces_add: tuple[str, str, str | None] | None = None,
    **timeline_extras: Any,
) -> None:
    """Mutate Story status + write. ``timeline_extras`` are extra
    fields appended to the timeline event (e.g. ``commit_ref``,
    ``summary`` from ``story done``). Spec-level extras (closed_at,
    blocked_reason) go through ``extras`` instead. ``produces_add``
    (kind, name, role) appends to the Story's produces[] hub in the same
    load-modify-write (e.g. the start-gate's Plan)."""
    with open_session(scope) as s:
        existing = s.get_doc("Story", name)
        if existing is None:
            raise fail(f"Story '{name}' not found in scope {scope!r}")
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        prev_status = spec.get("status")
        spec["status"] = new_status
        if extras:
            spec.update(extras)
        if produces_add is not None:
            _append_produces(spec, produces_add[0], produces_add[1], produces_add[2])
        # v1.5: auto-stamp updated_at on every status change.
        spec["updated_at"] = _now_iso()
        # v1.6: append timeline event for the flip.
        _append_timeline(
            spec, "status_change",
            **{"from": prev_status, "to": new_status, **timeline_extras},
        )
        raw = _build_raw("Story", name, spec)
        s.run(s.kernel.write_document(scope, "Story", name, raw))
    click.secho(f"UPDATED Story/{name} → {new_status}", fg="green")


def _post_story_note(scope: str, name: str, note: str) -> None:
    """Append a comment event to a Story timeline (the inline ``--note`` of a
    transition). Persisted as its OWN load-modify-write so it survives the
    subsequent ``_update_story_status`` re-read. Auto-promotes decision-shaped
    notes (mirrors ``story comment``). Raises (fail) if the Story is missing."""
    event_type = "decision" if _looks_like_decision(note) else "comment"
    with open_session(scope) as s:
        existing = s.get_doc("Story", name)
        if existing is None:
            raise fail(f"Story '{name}' not found in scope {scope!r}")
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        _append_timeline(spec, event_type, summary=note)
        spec["updated_at"] = _now_iso()
        raw = _build_raw("Story", name, spec)
        s.run(s.kernel.write_document(scope, "Story", name, raw))


def _load_story_spec(scope: str, name: str) -> dict[str, Any]:
    """Read a Story's current spec dict (empty dict if absent). Used to feed the
    WARN-only FOCUS guards the state BEFORE a transition flips status."""
    with open_session(scope) as s:
        existing = s.get_doc("Story", name)
        if existing is None or not isinstance(existing.spec, dict):
            return {}
        return dict(existing.spec)


def _warn_narration(scope: str, name: str) -> None:
    """Emit the WARN-only narration guard for a Story about to transition
    (i-114). Reads the current spec so a freshly-posted ``--note`` silences it.
    NEVER blocks."""
    spec = _load_story_spec(scope, name)
    for w in narration_guard(spec):
        click.secho(f"⚠ {w}", fg="yellow", err=True)


def build_start_beat_payload(name: str, kind: str = "Story") -> dict[str, Any]:
    """Pure: the presence-beat body emitted by ``story/issue/spike start`` so
    the FOCUS view has a live pointer at the just-started item even before the
    activity hook fires. ``work_item=name`` (route strips any ``Kind/``
    prefix). Actor follows the CLI reporter convention (``$DNA_CLI_REPORTER``
    → ``claude-code``)."""
    return {
        "actor": os.getenv("DNA_CLI_REPORTER") or "claude-code",
        "work_item": name,
        "kind": kind,
        "step": "iniciada",
    }


def build_done_beat_payload(kind: str, name: str) -> dict[str, Any]:
    """Pure: the CLOSING presence beat emitted by ``story done`` / ``issue
    resolve`` (i-126). ``work_item_done`` tells the presence store to
    EXPLICITLY clear the merged anchor (instead of letting it linger on a
    closed item) and to remember "último entregue" for the between-items
    FOCUS state. Carries NO ``work_item``."""
    return {
        "actor": os.getenv("DNA_CLI_REPORTER") or "claude-code",
        "work_item_done": f"{kind}/{name}",
        "step": f"entregue: {name}",
    }


def _post_presence_beat(scope: str, payload: dict, label: str) -> None:
    """Presence/FOCUS beats are a service surface upstream — in this
    kernel-local distribution the anchor is the filesystem pointer
    (active-story.txt) written by ``story start``; beats are a
    silent no-op."""
    del scope, payload, label


def _post_start_beat(scope: str, name: str, kind: str = "Story") -> None:
    """Best-effort anchor beat: sets the FOCUS pointer the instant a work item
    starts — over the API, not via the local ``.dna/active-story.txt``."""
    _post_presence_beat(scope, build_start_beat_payload(name, kind=kind), "beat")


def _post_done_beat(scope: str, kind: str, name: str) -> None:
    """Best-effort closing beat (i-126): explicitly clears the FOCUS anchor
    the instant a done/resolve/cancel lands — no lingering pointer."""
    _post_presence_beat(scope, build_done_beat_payload(kind, name), "done-beat")


# ── Plan gate (s-journey-derived → s-story-start-plan-gate) ──────────
# "Obrigatório, mas real": you can't `story start` without deciding HOW —
# an inline plan, a linked Plan doc, or a conscious skip-with-reason. The
# plan artifact is created on the critical path, so neither human nor AI
# vibe coder can forget it. The derived `plan` phase lights up from the
# Plan→story link (or shows the honest skip reason).

def _read_body_file(path: str) -> str:
    """Read a markdown plan body from a file (rich-plan opt-in). Pure helper
    so the gate can pour the output of ANY planning methodology (superpowers
    writing-plans, BMAD, spec-kit, hand-written) into the Plan body without
    coupling the SDLC to any one of them. Fails (exits) on missing/empty file."""
    from pathlib import Path
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise fail(f"--plan-file/--body-file: arquivo não encontrado: {path}")
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        raise fail(f"--plan-file/--body-file: arquivo vazio: {path}")
    return text


def _create_minimal_plan(
    scope: str, story_name: str, approach: str, *, methodology: str | None = None,
) -> str:
    """Create a Plan doc linked to a Story. Lights up the derived `plan` phase
    (the resolver reads Plan.spec.story_ref). The body can be a 1-3 line inline
    approach OR a rich markdown plan read from a file (see _read_body_file).
    Optional `methodology` records WHICH planning method produced it so the
    journey can show it honestly. Returns the name."""
    plan_name = f"plan-{story_name}"
    now = _now_iso()
    spec = {
        "title": f"Plano: {story_name}",
        "date": now[:10],
        "status": "accepted",
        "story_ref": story_name,
        "journey_phase": "plan",
        "body": approach,
        "created_at": now,
        "updated_at": now,
    }
    if methodology:
        spec["methodology"] = methodology
    with open_session(scope) as s:
        raw = _build_raw("Plan", plan_name, spec)
        s.run(s.kernel.write_document(scope, "Plan", plan_name, raw))
    return plan_name


def _link_plan_to_story(scope: str, plan_name: str, story_name: str) -> None:
    """Ensure an existing Plan declares ``story_ref=<story>`` so the derived
    journey links it. Raises (fail) if the Plan doesn't exist."""
    with open_session(scope) as s:
        existing = s.get_doc("Plan", plan_name)
        if existing is None:
            raise fail(
                f"Plan '{plan_name}' não encontrado em {scope!r}. "
                f"Crie com `dna sdlc plan create {plan_name} --story {story_name}`.",
            )
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        if spec.get("story_ref") != story_name:
            spec["story_ref"] = story_name
            spec["updated_at"] = _now_iso()
            raw = _build_raw("Plan", plan_name, spec)
            s.run(s.kernel.write_document(scope, "Plan", plan_name, raw))


@story_group.command("start")
@click.argument("name")
@click.option("--plan", "plan_text", default=None,
              help="Plano de ataque (1-3 linhas). Cria Plan/plan-<story> linkado → fase `plan` acende.")
@click.option("--plan-doc", "plan_doc", default=None,
              help="Linka um Plan existente (trabalho grande) em vez de criar inline.")
@click.option("--plan-file", "plan_file", default=None,
              help="Cria Plan/plan-<story> com o body = conteúdo deste markdown "
                   "(plano RICO de qualquer metodologia: superpowers, bmad, à mão).")
@click.option("--methodology", "methodology", default=None,
              type=click.Choice(VALID_JOURNEY_METHODOLOGIES),
              help="Metodologia que produziu o plano (carimba Plan.spec.methodology "
                   "→ jornada mostra a origem). Opt-in.")
@click.option("--no-plan", is_flag=True,
              help="Pular o `plan` conscientemente (exige --skip-reason).")
@click.option("--skip-reason", "skip_reason", default=None,
              help="Motivo do skip (com --no-plan) — registrado honestamente na jornada.")
@click.option("--note", "note", default=None,
              help="Narra esta transição (appenda comment inline na MESMA chamada).")
@click.option("--no-narrate", "no_narrate", is_flag=True,
              help="Silencia o warn de narração.")
@_scope_option
def cmd_story_start(
    name: str, plan_text: str | None, plan_doc: str | None,
    plan_file: str | None, methodology: str | None,
    no_plan: bool, skip_reason: str | None,
    note: str | None, no_narrate: bool, scope: str,
) -> None:
    """Mark Story status: in-progress.

    Plan gate (s-story-start-plan-gate): você não começa sem decidir o
    plano de ataque — ``--plan "1-3 linhas"`` (cria Plan inline),
    ``--plan-doc <nome>`` (linka Plan existente), ou
    ``--no-plan --skip-reason "..."`` (skip honesto, registrado). Em TTY
    interativo sem flag, o CLI pergunta. O artefato nasce no caminho
    crítico — ninguém esquece, e a fase `plan` derivada acende sozinha.

    Side-effect: stamps ``.dna/active-story.txt`` with ``<scope>:<name>``
    so external tools (Claude Code hooks, IDE plugins) can attribute
    out-of-band events to the Story currently being worked on.
    """
    # At most one plan source. Guard runs BEFORE any file read or source write
    # so conflicting flags fail fast with a clear message.
    _chosen = [
        flag for flag, on in (
            ("--plan", bool(plan_text)), ("--plan-doc", bool(plan_doc)),
            ("--plan-file", bool(plan_file)), ("--no-plan", no_plan),
        ) if on
    ]
    if len(_chosen) > 1:
        raise fail(
            f"apenas um plano por start — mutuamente exclusivos: {', '.join(_chosen)}.",
        )

    plan_extras: dict[str, Any] | None = None
    plan_msg: str | None = None
    if no_plan:
        if not skip_reason:
            raise fail('--no-plan exige --skip-reason "motivo" (skip honesto, registrado na jornada).')
        plan_extras = {"plan_skip_reason": skip_reason}
        plan_msg = f"plan PULADO conscientemente: {skip_reason}"
    # The Plan (created or linked) is appended to the Story's produces[] hub.
    plan_ref: tuple[str, str, str | None] | None = None
    if no_plan:
        pass
    elif plan_doc:
        _link_plan_to_story(scope, plan_doc, name)
        plan_msg = f"plan linkado: Plan/{plan_doc}"
        plan_ref = ("Plan", plan_doc, "implementation")
    elif plan_file:
        _body = _read_body_file(plan_file)
        _pn = _create_minimal_plan(scope, name, _body, methodology=methodology)
        _meth = f" ({methodology})" if methodology else ""
        plan_msg = f"plan RICO criado de {plan_file}: Plan/{_pn}{_meth}"
        plan_ref = ("Plan", _pn, "implementation")
    elif plan_text:
        _pn = _create_minimal_plan(scope, name, plan_text, methodology=methodology)
        plan_msg = f"plan criado: Plan/{_pn}"
        plan_ref = ("Plan", _pn, "implementation")
    elif sys.stdin.isatty() and not os.getenv("CI"):
        entered = click.prompt(
            "🗺️  Plano de ataque (1-3 linhas)", default="", show_default=False,
        ).strip()
        if not entered:
            raise fail("plano obrigatório — start cancelado. Use --plan/--plan-doc/--no-plan.")
        _pn = _create_minimal_plan(scope, name, entered)
        plan_msg = f"plan criado: Plan/{_pn}"
        plan_ref = ("Plan", _pn, "implementation")
    else:
        raise fail(
            "plano obrigatório pra começar — escolha um:\n"
            '  --plan "abordagem 1-3 linhas"      (cria Plan inline)\n'
            "  --plan-file <plano.md>             (plano RICO de um arquivo)\n"
            "  --plan-doc <nome>                  (linka Plan existente)\n"
            '  --no-plan --skip-reason "motivo"   (skip honesto, registrado)',
        )

    # Narração inline (i-114): persiste o --note ANTES da transição para contar
    # como narração; o guard (WARN-only) lê o estado pós-note e some quando há nota.
    if note:
        _post_story_note(scope, name, note)
    if not no_narrate:
        _warn_narration(scope, name)
    _update_story_status(scope, name, "in-progress", extras=plan_extras, produces_add=plan_ref)
    try:
        _active_story_write(scope, name)
    except Exception as e:  # noqa: BLE001 — pointer is best-effort
        click.secho(f"warn: active-story pointer not written: {e}", fg="yellow")
    # Emit a presence beat over the API so the FOCUS pointer is live immediately
    # (prod has no shared FS — the kinds-api can't read the local pointer). The
    # local .dna/active-story.txt above is still written, but ONLY for the
    # workstation hook to read (Chunk 2). Best-effort — never breaks the start.
    _post_start_beat(scope, name, kind="Story")
    if plan_msg:
        click.secho(f"  🗺️  {plan_msg}", fg="cyan")
    # Journey is DERIVED (s-journey-derived): discover + specify + plan now
    # all derive from real signals (created_at / AC-DoD / linked Plan).
    click.secho(f"📍 journey: Story/{name} → in-progress (derived)", fg="cyan")


def story_done_guard(
    prev_status: str | None, commit_ref: str | None, no_commit: bool,
) -> list[str]:
    """Honest warnings for `story done` (i-034). done = shipped + accepted:
    (a) no shipping commit, (b) skipping review (the review→done flow that
    keeps work-in-review out of limbo). Warns — does not hard-block."""
    warns: list[str] = []
    if not no_commit and not commit_ref:
        warns.append(
            'done sem commit de entrega — done = shipped. '
            'Passe --commit-ref <sha> (pós-merge) ou --no-commit (story sem código).'
        )
    if prev_status and prev_status != "review":
        warns.append(
            f'done sem passar por review (estava "{prev_status}") — '
            'fluxo de mercado: PR aberto → review → done (pós-merge).'
        )
    return warns


def done_blocks_on_missing_tests(
    *, no_commit: bool, allow_no_tests: bool, has_passing_run: bool,
) -> bool:
    """s-sdlc-tests-required-on-done: whether ``story done`` must REFUSE for
    missing tests. Blocks ONLY when the Story has code (not ``--no-commit``), the
    escape hatch is off (``--allow-no-tests``), and no passing TestRun verifies
    it. Mirrors the AC/DoD guard on ``story create``."""
    return (not no_commit) and (not allow_no_tests) and (not has_passing_run)


# ── FOCUS feed completeness guards (WARN-only, mirror story_done_guard) ───────
# Two additive warnings that keep the FOCUS feed honest WITHOUT hard-blocking
# any transition. They mirror ``story_done_guard`` (return list[str] of warns),
# NOT the test-gate (which raises). Wired into start/review/done (narration) and
# done/ship/resolve (produces).

def _has_narration_since_last_status_change(timeline: list[dict[str, Any]] | None) -> bool:
    """True se há comment/decision DEPOIS do último status_change na timeline."""
    if not isinstance(timeline, list):
        return False
    last_status_idx = None
    for i in range(len(timeline) - 1, -1, -1):
        ev = timeline[i]
        if isinstance(ev, dict) and ev.get("type") == "status_change":
            last_status_idx = i
            break
    if last_status_idx is None:
        return False
    for ev in timeline[last_status_idx + 1:]:
        if isinstance(ev, dict) and ev.get("type") in ("comment", "decision"):
            return True
    return False


def narration_guard(spec: dict[str, Any]) -> list[str]:
    """WARN se não há narração (comment/decision) desde o último status_change.
    Feed FOCUS fica mudo ('start→silêncio→done') sem isso (i-114)."""
    warns: list[str] = []
    timeline = spec.get("timeline") if isinstance(spec, dict) else None
    if not _has_narration_since_last_status_change(timeline if isinstance(timeline, list) else []):
        warns.append(
            "nenhuma narração (comment/decision) desde a última mudança de status — "
            "o feed FOCUS fica mudo. Narre o porquê: `story comment <id> --body \"...\"` "
            "ou use --note \"...\" aqui."
        )
    return warns


_OUTPUT_BACKREF_FIELDS = (
    "spec_refs", "research_refs", "html_artifacts", "references",
    "follow_up_story", "follow_up_adr", "follow_up_spec",
)


def _has_linked_outputs(spec: dict[str, Any]) -> bool:
    """True se o work item tem QUALQUER output linkado: produces[] não-vazio
    OU algum back-ref on-spec. (Sem I/O — não busca plans/lessons reversos.)"""
    if not isinstance(spec, dict):
        return False
    produces = spec.get("produces")
    if isinstance(produces, list) and len(produces) > 0:
        return True
    for f in _OUTPUT_BACKREF_FIELDS:
        v = spec.get(f)
        if v:
            return True
    return False


def produces_guard(spec: dict[str, Any]) -> list[str]:
    """WARN se o item fecha sem nenhum output linkado (i-113). O painel de
    outputs do FOCUS fica vazio."""
    warns: list[str] = []
    if not _has_linked_outputs(spec):
        warns.append(
            "fechando sem nenhum output linkado (produces[] + back-refs vazios) — "
            "o painel de outputs do FOCUS fica vazio. Linke: "
            "`sdlc produces add <Kind>/<wi> <Kind>/<ref>` (Spec/Plan/HtmlArtifact/...)."
        )
    return warns


@story_group.command("done")
@click.argument("name")
@click.option("--commit-ref", "commit_ref", default=None,
              help="Git SHA shipped with this Story. Auto-detected from HEAD when omitted.")
@click.option("--no-commit", is_flag=True,
              help="Story sem código (silencia o aviso de commit de entrega + isenta o test gate).")
@click.option("--allow-no-tests", is_flag=True,
              help="Pula o test gate (s-sdlc-tests-required-on-done). Use SÓ para exceções "
                   "registradas — por padrão `story done` exige um TestRun outcome=pass que "
                   "verifica a Story, espelhando o guard de --ac/--dod do `story create`.")
@click.option("--summary", default=None,
              help="One-line description of what shipped (lands on the timeline event).")
@click.option("--note", "note", default=None,
              help="Narra esta transição (appenda comment inline na MESMA chamada).")
@click.option("--no-narrate", "no_narrate", is_flag=True,
              help="Silencia o warn de narração.")
@click.option("--allow-no-produces", "allow_no_produces", is_flag=True,
              help="Silencia o warn de outputs vazios (produces[] + back-refs).")
@_scope_option
def cmd_story_done(
    name: str, commit_ref: str | None, no_commit: bool, allow_no_tests: bool,
    summary: str | None, note: str | None, no_narrate: bool,
    allow_no_produces: bool, scope: str,
) -> None:
    """Mark Story status: done; auto-stamp commit_ref + optional summary."""
    # Auto-detect HEAD when --commit-ref not passed and we're inside
    # a git working tree. Failure to detect is silent (test fixtures
    # in /tmp aren't repos).
    if commit_ref is None:
        commit_ref = _git_head_sha()
    extras: dict[str, Any] = {"closed_at": _now_iso()}
    timeline_extras: dict[str, Any] = {}
    if commit_ref:
        timeline_extras["commit_ref"] = commit_ref
    if summary:
        timeline_extras["summary"] = summary
    prev_status: str | None = None
    # Backfill AC + DoD as done before status flip — keeps data
    # aligned with status=done (Story s-checklist-readonly-on-closed-
    # stories). Idempotent: items already done preserve their stamps.
    try:
        now_iso = _now_iso()
        with open_session(scope) as _s:
            existing = _s.get_doc("Story", name)
            if existing is not None and isinstance(existing.spec, dict):
                story_spec = dict(existing.spec)
                prev_status = story_spec.get("status")
                changed = False
                for field in ("acceptance_criteria", "definition_of_done"):
                    backfilled = _backfill_checklist(
                        story_spec.get(field),
                        done_at=now_iso,
                        done_by="story-done-auto",
                    )
                    if backfilled is not None and backfilled != story_spec.get(field):
                        story_spec[field] = backfilled
                        changed = True
                if changed:
                    raw_doc = _build_raw("Story", name, story_spec)
                    _s.run(_s.kernel.write_document(scope, "Story", name, raw_doc))
    except Exception:  # noqa: BLE001 — backfill is best-effort
        pass
    # Narração inline (i-114): persiste o --note ANTES dos warns/transição.
    if note:
        _post_story_note(scope, name, note)
    # i-034 guard: done = shipped + accepted. Surface honest warnings (no commit
    # of record / skipping review) so a premature done doesn't leave work in limbo.
    for w in story_done_guard(prev_status, commit_ref, no_commit):
        click.secho(f"⚠ {w}", fg="yellow", err=True)
    # FOCUS feed guards (WARN-only, never block): narração (i-114) + outputs (i-113).
    # Read the current spec so a freshly-posted --note silences the narração warn.
    _done_spec = _load_story_spec(scope, name)
    if not no_narrate:
        for w in narration_guard(_done_spec):
            click.secho(f"⚠ {w}", fg="yellow", err=True)
    if not allow_no_produces:
        for w in produces_guard(_done_spec):
            click.secho(f"⚠ {w}", fg="yellow", err=True)
    # Test gate (testkit) — HARD BLOCK (s-sdlc-tests-required-on-done): `done`
    # requires a passing TestRun that verifies this Story, mirroring the AC/DoD
    # guard on `story create`. ``--allow-no-tests`` escapes (registered
    # exceptions); ``--no-commit`` (Story without code) is exempt. Fail-open on a
    # registry error so a query hiccup never blocks a legitimate done.
    try:
        from dna_cli.testkit_cmd import passing_run_for_story
        has_passing_run = passing_run_for_story(scope, name) is not None
    except Exception:  # noqa: BLE001 — never crash the gate; fail-open
        has_passing_run = True
    if done_blocks_on_missing_tests(
        no_commit=no_commit, allow_no_tests=allow_no_tests, has_passing_run=has_passing_run,
    ):
        click.secho(
            f"✗ Story '{name}' não tem um SMOKE DE PRODUTO (TestRun pass de guide "
            f"smoke|manual) que a verifica — `story done` exige a validação humana do "
            f"produto. (O automatizado já é provado pelo CI no PR.)\n"
            f"  Rode pelo runner do Studio (TestGuide → Executar) OU pelo CLI:\n"
            f"     dna sdlc test-guide create tg-{name} --product --from-ac {name} --owner <você>\n"
            f"     dna sdlc test-run record tg-{name} --outcome pass --evidence test:<arquivo>\n"
            f"  Escapes:   --allow-no-tests (exceção registrada)  ·  --no-commit (Story sem código).",
            fg="red", err=True,
        )
        raise SystemExit(1)
    _update_story_status(scope, name, "done", extras, **timeline_extras)
    # Clear the active-story pointer if it referenced this Story.
    # Closing some other Story in parallel must not blank the pointer.
    try:
        _active_story_clear_if_matches(scope, name)
    except Exception:  # noqa: BLE001 — pointer is best-effort
        pass
    # Closing beat (i-126): explicitly clear the merged FOCUS anchor over the
    # API — without it the presence store keeps pointing at this (now done)
    # Story and every gap renders the "não ancorado" anomaly. Best-effort.
    _post_done_beat(scope, "Story", name)
    # Journey derived (s-journey-derived): `reflect` is computed from
    # status=done / closed_at (or a linked Engram) — no WorkflowEvent.
    click.secho(f"📍 journey: Story/{name} → reflect (derived)", fg="cyan")
    # Post-transition hook point (fail-soft) — hooks registered by the
    # host platform fire here.
    try:
        with open_session(scope) as _s:
            _story_doc = _s.get_doc("Story", name)
            _story_spec = dict(_story_doc.spec) if _story_doc and _story_doc.spec else {}
    except Exception:  # noqa: BLE001 — doc reload is best-effort
        _story_spec = {}
    _fire_post_transition("Story", name, "done", _story_spec, {"scope": scope})


@story_group.command("block")
@click.argument("name")
@click.option("--reason", required=True, help="Why is it blocked?")
@_scope_option
def cmd_story_block(name: str, reason: str, scope: str) -> None:
    """Mark Story status: blocked, set blocked_reason."""
    _update_story_status(scope, name, "blocked", {"blocked_reason": reason})
    try:
        _active_story_clear_if_matches(scope, name)
    except Exception:  # noqa: BLE001
        pass


@story_group.command("review")
@click.argument("name")
@click.option("--note", "note", default=None,
              help="Narra esta transição (appenda comment inline na MESMA chamada).")
@click.option("--no-narrate", "no_narrate", is_flag=True,
              help="Silencia o warn de narração.")
@click.option("--no-pr", "no_pr", is_flag=True,
              help="Escape do guard de PR (i-133): marca review mesmo sem PR "
                   "aberto na branch corrente. Exige --reason.")
@click.option("--reason", "no_pr_reason", default=None,
              help="Por que está marcando review sem PR aberto (vai pro timeline).")
@_scope_option
def cmd_story_review(name: str, note: str | None, no_narrate: bool,
                     no_pr: bool, no_pr_reason: str | None, scope: str) -> None:
    """Mark Story status: review.

    Also emits a ``build`` journey event — submitting for review means the
    implementation is complete. The journey is now DERIVED (s-journey-derived):
    ``build`` is computed from the timeline status_change to in-progress/review
    (or a commit_ref), and finer phases (specify/plan) light up automatically
    from AC/DoD + linked Spec/Plan. No WorkflowEvent write needed.

    Guard (i-133): review = PR aberto. Checa ``gh pr list --head <branch>``
    (fail-soft, ≤3s); sem PR aberto exige ``--no-pr --reason "<por quê>"``.
    """
    # PR guard (i-133) — antes de qualquer escrita.
    branch = _git_current_branch()
    if branch is None:
        # git indisponível/fora de worktree — distinto de "gh indisponível"
        # (review follow-up): o guard pula fail-soft, mas diz o porquê certo.
        prs = None
        allowed, warnings = True, [
            "branch git indetectável (fora de um worktree?) — guard de PR "
            "pulado, fail-soft.",
        ]
    else:
        prs = _gh_open_prs_for_branch(branch)
        allowed, warnings = review_pr_guard(prs, no_pr=no_pr, reason=no_pr_reason)
    for w in warnings:
        click.secho(f"⚠ {w}", fg="yellow")
    if not allowed:
        raise fail(f"review bloqueado pra Story '{name}'.")
    if no_pr and no_pr_reason and not prs:
        # Escape exercido (sem PR confirmado OU gh/git indisponível) —
        # registra a razão no timeline (auditável) em todos os casos.
        _post_story_note(scope, name, f"review sem PR aberto (--no-pr): {no_pr_reason}")
    # Narração inline (i-114): persiste o --note antes do warn/transição.
    if note:
        _post_story_note(scope, name, note)
    if not no_narrate:
        _warn_narration(scope, name)
    _update_story_status(scope, name, "review")
    # Journey derived — `build` is computed from status/timeline/commit_ref.
    click.secho(f"📍 journey: Story/{name} → build (derived)", fg="cyan")


# Patterns that promote a comment to a decision event automatically.
# Pure regex, zero LLM cost — catches the common phrasings the agent
# uses while reasoning. The user can always force `--type comment` or
# `--type decision` to override.
_DECISION_PATTERNS = (
    re.compile(r"\b(decid[ií]|optei|escolhi|optamos|escolhemos)\b", re.IGNORECASE),
    re.compile(r"\b(decided|chose|opted|picked)\b", re.IGNORECASE),
    re.compile(r"\b(porque|because|since|pq)\b.*\b(prefer|melhor|better|escolh)", re.IGNORECASE),
    re.compile(r"\b(pivot[áa]ei|switching to|trocando para)\b", re.IGNORECASE),
)


def _looks_like_decision(body: str) -> bool:
    """Heuristic: does this comment text describe a ratified choice?"""
    return any(p.search(body) for p in _DECISION_PATTERNS)


@story_group.command("comment")
@click.argument("name")
@click.option("--body", required=True, help="Comment text (lands on the timeline event).")
@click.option("--type", "event_type", default=None,
              type=click.Choice(("comment", "decision")),
              help="Event type — 'comment' or 'decision'. When omitted, "
                   "auto-detected: comments matching decision patterns "
                   "('decidi X porque Y', 'optei por...') are promoted "
                   "to decisions automatically.")
@click.option("--commit-ref", "commit_ref", default=None,
              help="Optional Git SHA to associate. Auto-detected from HEAD when omitted.")
@_scope_option
def cmd_story_comment(
    name: str, body: str, event_type: str | None,
    commit_ref: str | None, scope: str,
) -> None:
    """Append a comment / decision event to a Story timeline without
    mutating its status. Useful when shipping a Story produces
    artifacts beyond the status flip itself.

    Auto-promotes comments matching decision patterns to decision
    events so the morning narrative drawer's "🧠 decisions" section
    captures the WHY without the agent needing to remember --type.
    """
    if commit_ref is None:
        commit_ref = _git_head_sha()
    # Auto-detect decision when --type omitted.
    promoted = False
    if event_type is None:
        if _looks_like_decision(body):
            event_type = "decision"
            promoted = True
        else:
            event_type = "comment"
    with open_session(scope) as s:
        existing = s.get_doc("Story", name)
        if existing is None:
            raise fail(f"Story '{name}' not found in scope {scope!r}")
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        extras: dict[str, Any] = {"summary": body}
        if commit_ref:
            extras["commit_ref"] = commit_ref
        _append_timeline(spec, event_type, **extras)
        spec["updated_at"] = _now_iso()
        raw = _build_raw("Story", name, spec)
        s.run(s.kernel.write_document(scope, "Story", name, raw))
    suffix = " (auto-promoted from comment)" if promoted else ""
    click.secho(
        f"COMMENTED Story/{name} ({event_type}){suffix}", fg="green",
    )
# ─── Story checklist (AC/DoD) — granular check + close-time backfill ──
# Untangled from the journey block (sdlc_cmd decomposition): these are
# STORY concerns — cmd_story_done calls _backfill_checklist, and
# `story check` registers on story_group — so they live with the story
# section, clearing the way for the journey group to move out as a unit.

def _backfill_checklist(
    raw: Any, *, done_at: str, done_by: str,
) -> list[dict[str, Any]] | None:
    """Stamp every checklist item as done — backfill at story close.

    Story s-checklist-readonly-on-closed-stories. Accepts the same
    union shape as the TS twin (string | {text, done?, done_at?,
    done_by?}). Returns canonical object list with done=true on every
    item; items already done are preserved (idempotent — keeps their
    original done_at/done_by). Returns None when input is empty/
    invalid (caller leaves the field alone).
    """
    if not isinstance(raw, list) or not raw:
        return None
    out: list[dict[str, Any]] = []
    for r in raw:
        if isinstance(r, str):
            text = r.strip()
            if not text:
                continue
            out.append({"text": text, "done": True, "done_at": done_at, "done_by": done_by})
        elif isinstance(r, dict):
            text = str(r.get("text", "")).strip()
            if not text:
                continue
            already_done = r.get("done") is True
            if already_done:
                item: dict[str, Any] = {"text": text, "done": True}
                if r.get("done_at"):
                    item["done_at"] = r["done_at"]
                if r.get("done_by"):
                    item["done_by"] = r["done_by"]
                if r.get("evidence"):  # preserve granular evidence from `story check`
                    item["evidence"] = r["evidence"]
                out.append(item)
            else:
                out.append({"text": text, "done": True, "done_at": done_at, "done_by": done_by})
    return out


def _normalize_checklist(raw: Any) -> list[dict[str, Any]]:
    """String|dict checklist → canonical ``{text, ...}`` dict list (preserves
    existing done/evidence). Used by ``story check`` for granular marking."""
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for r in raw:
        if isinstance(r, str):
            t = r.strip()
            if t:
                out.append({"text": t})
        elif isinstance(r, dict) and str(r.get("text", "")).strip():
            out.append(dict(r))
    return out


def _mark_checklist_items(
    items: list[dict[str, Any]], selectors: tuple[str, ...], *,
    mark_all: bool, done_at: str, done_by: str, evidence: str,
) -> int:
    """Mark selected checklist items done + evidence. Selectors match by
    1-based index (digit selectors — EXACT int match, never substring) OR
    case-insensitive substring of the item text (non-digit selectors).
    Returns the number of items marked.

    i-014: a digit selector must NOT fall through to the substring branch —
    ``--ac 1`` used to also mark any item whose TEXT contained "1"
    ("API v1", "10 retries", ...), over-marking checklists in the field.
    """
    n = 0
    for i, it in enumerate(items, start=1):
        match = mark_all
        if not match:
            for sel in selectors:
                if sel.isdigit():
                    if int(sel) == i:
                        match = True
                        break
                    continue  # index selector: exact match only (i-014)
                if sel and sel.lower() in str(it.get("text", "")).lower():
                    match = True
                    break
        if match:
            it["done"] = True
            it["done_at"] = done_at
            it["done_by"] = done_by
            it["evidence"] = evidence
            n += 1
    return n


@story_group.command("check")
@click.argument("name")
@click.option("--ac", "ac_sel", multiple=True,
              help="Acceptance-criterion to mark done: 1-based index (exact) or text substring (repeatable).")
@click.option("--dod", "dod_sel", multiple=True,
              help="Definition-of-done item to mark done: 1-based index (exact) or text substring (repeatable).")
@click.option("--all", "mark_all", is_flag=True, default=False,
              help="Mark ALL acceptance_criteria + definition_of_done items done.")
@click.option("--evidence", required=True,
              help="Evidence the item is satisfied (PR #, commit sha, link, or prose). Stored per-item.")
@click.option("--by", "by_actor", default=None,
              help="Actor crediting the check (default: DNA_AGENT_OWNER or claude-code).")
@_scope_option
def cmd_story_check(
    name: str, ac_sel: tuple[str, ...], dod_sel: tuple[str, ...],
    mark_all: bool, evidence: str, by_actor: str | None, scope: str,
) -> None:
    """Mark specific AC / DoD items DONE **with evidence** — granular
    Gapless-DoD closure, vs ``story done``'s blanket auto-backfill (which
    stamps ``done_by=story-done-auto`` and no evidence). Select items by
    1-based index or text substring; ``--all`` marks every AC + DoD item.

    Example:
        dna sdlc story check s-foo --ac 1 --dod "tests" --evidence "PR #42"
    """
    import os as _os
    if not (ac_sel or dod_sel or mark_all):
        raise click.UsageError("pass --ac/--dod selectors (index or substring) or --all")
    actor = by_actor or _os.environ.get("DNA_AGENT_OWNER", "claude-code")
    now = _now_iso()
    with open_session(scope) as s:
        existing = s.get_doc("Story", name)
        if existing is None:
            raise fail(f"Story '{name}' not found in scope {scope!r}")
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        ac = _normalize_checklist(spec.get("acceptance_criteria"))
        dod = _normalize_checklist(spec.get("definition_of_done"))
        n_ac = (
            _mark_checklist_items(ac, ac_sel, mark_all=mark_all, done_at=now, done_by=actor, evidence=evidence)
            if (ac_sel or mark_all) else 0
        )
        n_dod = (
            _mark_checklist_items(dod, dod_sel, mark_all=mark_all, done_at=now, done_by=actor, evidence=evidence)
            if (dod_sel or mark_all) else 0
        )
        if n_ac == 0 and n_dod == 0:
            raise fail("no AC/DoD items matched the selectors (check indices/substrings)")
        if n_ac:
            spec["acceptance_criteria"] = ac
        if n_dod:
            spec["definition_of_done"] = dod
        spec["updated_at"] = now
        _append_timeline(
            spec, "checklist_check",
            marked_ac=n_ac, marked_dod=n_dod, evidence=evidence, by=actor,
        )
        raw = _build_raw("Story", name, spec)
        s.run(s.kernel.write_document(scope, "Story", name, raw))
    click.secho(
        f"✓ checked {n_ac} AC + {n_dod} DoD on Story/{name} "
        f"(evidence: {evidence[:60]})",
        fg="green",
    )




class _KaizenGroup(click.Group):
    """Group with a default subcommand (i-125).

    ``dna sdlc kaizen <wi> --body "…"`` (the historical observation form)
    keeps working: when the first token isn't a known subcommand
    (``flag``/``route``/``resolve``), fall back to ``flag`` with the full
    arg list untouched.
    """

    default_cmd = "flag"

    def resolve_command(self, ctx, args):  # noqa: ANN001 — click signature
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            cmd = self.get_command(ctx, self.default_cmd)
            if cmd is None:  # pragma: no cover — defensive
                raise
            return cmd.name, cmd, args


# Transition map for the Kaizen arc (i-125). The status VALUES mirror the
# descriptor enum (packages/sdk-py/dna/extensions/sdlc/kinds/
# kaizen.kind.yaml: observed → routed → resolved) — only the transitions
# themselves live here.
_KAIZEN_TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "route": (frozenset({"observed"}), "routed"),
    "resolve": (frozenset({"observed", "routed"}), "resolved"),
}


def kaizen_transition_guard(current: str | None, command: str) -> str | None:
    """Validate a Kaizen status transition (pure). Returns an error
    message (str) when the transition is invalid, None when OK.

    ``current=None`` is treated as the descriptor default ``observed``.
    """
    allowed, target = _KAIZEN_TRANSITIONS[command]
    cur = current or "observed"
    if cur == target:
        return f"Kaizen já está '{target}' — nada a fazer."
    if cur not in allowed:
        return (
            f"transição inválida: '{cur}' → '{target}' "
            f"(`{command}` exige status em {sorted(allowed)})."
        )
    return None


@sdlc.group("kaizen", cls=_KaizenGroup)
def kaizen_group() -> None:
    """Kaizen — observação de melhoria contínua (arco observed→routed→resolved).

    Forma histórica `dna sdlc kaizen <wi> --body "…"` continua valendo
    (alias do subcomando `flag`).
    """


@kaizen_group.command("flag")
@click.argument("work_item")
@click.option("--body", required=True,
              help="The kaizen observation (lands on the timeline event).")
@click.option("--issue", default=None,
              help="Optional Issue/Story slug that captured the improvement "
                   "(e.g. i-042). Linked on the event so it's traceable.")
@click.option("--label", "labels", multiple=True,
              help="Free-form theme tag (repeatable). Lands on the Kaizen doc "
                   "and is weighted into semantic-search source text.")
@_scope_option
def cmd_kaizen(work_item: str, body: str, issue: str | None,
               labels: tuple[str, ...], scope: str) -> None:
    """Post a ``kaizen`` event onto a work item's timeline AND create
    the first-class Kaizen doc twin (s-kaizen-kind).

    A flagged kaizen observation shows up live in the FOCUS feed (the
    ``kaizen`` event-type is part of the unified feed). Does NOT change the
    work item's status — it's a running improvement note, optionally linking
    the Issue/Story that tracks the fix.

    Dual-write: the observation is ALSO persisted as a ``Kaizen`` doc
    (``kz-NNN-<slug>``, record plane) so the improvement backlog is
    queryable + semantically searchable; the timeline event carries a
    ``kaizen_doc`` ref back to it.

    ``<work_item>`` accepts ``Kind/slug`` (e.g. ``Story/s-x``, ``Issue/i-1``)
    or a bare slug, which is treated as a Story.
    """
    if "/" in work_item:
        wi_kind, wi_name = _split_ref(work_item)
    else:
        wi_kind, wi_name = "Story", work_item
    if wi_kind not in _WORK_ITEM_KINDS:
        raise fail(f"{wi_kind} não é work item ({', '.join(sorted(_WORK_ITEM_KINDS))}).")
    with open_session(scope) as s:
        existing = s.get_doc(wi_kind, wi_name)
        if existing is None:
            raise fail(f"{wi_kind}/{wi_name} não encontrado em {scope!r}.")
        actor = _cli_actor()
        now = _now_iso()
        # 1) First-class Kaizen doc (record plane — cacheless, fast write).
        kz_name = f"kz-{_next_kaizen_number(s):03d}-{_kaizen_slug(body)}"
        kz_spec = _build_kaizen_doc_spec(
            body=body, work_item=f"{wi_kind}/{wi_name}", issue=issue,
            actor=actor, now=now, labels=list(labels) if labels else None,
        )
        s.run(s.kernel.write_document(
            scope, "Kaizen", kz_name, _build_raw("Kaizen", kz_name, kz_spec),
        ))
        # 2) Timeline event on the work item (FOCUS feed), ref'ing the doc.
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        event = _build_kaizen_event(
            body=body, issue=issue, actor=actor, now=now, kaizen_doc=kz_name,
        )
        timeline = list(spec.get("timeline", []) or [])
        timeline.append(event)
        spec["timeline"] = timeline
        spec["updated_at"] = _now_iso()
        raw = _build_raw(wi_kind, wi_name, spec)
        s.run(s.kernel.write_document(scope, wi_kind, wi_name, raw))
    suffix = f" → {issue}" if issue else ""
    click.secho(
        f"KAIZEN registrado em {wi_kind}/{wi_name}{suffix} · doc `{kz_name}`",
        fg="green",
    )


def _kaizen_transition(scope: str, name: str, command: str,
                       extras: dict[str, Any] | None = None) -> str:
    """Shared write path for `kaizen route|resolve` (i-125).

    Copies the sibling pattern (`_update_story_status` & co): load the doc
    via the client session, validate the transition against
    ``_KAIZEN_TRANSITIONS``, then persist through ``kernel.write_document``
    so cache invalidation / hooks / schema validation fire. Returns the
    new status.
    """
    _, target = _KAIZEN_TRANSITIONS[command]
    with open_session(scope) as s:
        existing = s.get_doc("Kaizen", name)
        if existing is None:
            raise fail(f"Kaizen '{name}' not found in scope {scope!r}")
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        err = kaizen_transition_guard(spec.get("status"), command)
        if err:
            raise fail(err)
        spec["status"] = target
        if extras:
            spec.update(extras)
        spec["updated_at"] = _now_iso()
        raw = _build_raw("Kaizen", name, spec)
        s.run(s.kernel.write_document(scope, "Kaizen", name, raw))
    return target


@kaizen_group.command("route")
@click.argument("name")
@click.option("--issue", required=True,
              help="Issue/Story slug que rastreia o fix (e.g. i-042).")
@_scope_option
def cmd_kaizen_route(name: str, issue: str, scope: str) -> None:
    """Mark Kaizen status: routed (um Issue/Story rastreia o fix).

    Transição válida só a partir de ``observed`` (arco do descriptor:
    observed → routed → resolved). Grava ``issue`` no doc.
    """
    _kaizen_transition(scope, name, "route", {"issue": issue})
    click.secho(f"ROUTED Kaizen/`{name}` → {issue}", fg="green")


@kaizen_group.command("resolve")
@click.argument("name")
@_scope_option
def cmd_kaizen_resolve(name: str, scope: str) -> None:
    """Mark Kaizen status: resolved (fix shipped).

    Transição válida a partir de ``observed`` ou ``routed``.
    """
    _kaizen_transition(scope, name, "resolve")
    click.secho(f"RESOLVED Kaizen/`{name}`", fg="green")


@story_group.command("commits")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@_scope_option
def cmd_story_commits(name: str, as_json: bool, scope: str) -> None:
    """List every commit tied to a Story — trailers + timeline, merged.

    Closes the rastreabilidade loop: "que commits fecharam Story X?"
    Two sources, deduped by sha (trailer wins — it carries the subject):

    - ``git log --grep "Work-Item: Story/<name>"`` — commits stamped by
      the prepare-commit-msg hook (``dna sdlc hooks install``). This is
      the zero-bookkeeping path; fail-soft when git/repo is unavailable.
    - ``spec.timeline[].commit_ref`` (auto-stamped by `story done`) +
      ``spec.timeline[].session_ref`` (linkback to the AgentSession).
    """
    with open_session(scope) as s:
        story = s.get_doc("Story", name)
        if story is None:
            raise fail(f"Story '{name}' not found in scope {scope!r}")
        spec = story.spec if isinstance(story.spec, dict) else dict(story.spec)
        timeline = spec.get("timeline", []) or []
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        # 1) commits stamped with the Work-Item trailer (source of truth).
        for c in _gitsym.commits_for_work_item("Story", name) or []:
            seen.add(c["full_sha"])
            rows.append({
                "sha": c["sha"],
                "full_sha": c["full_sha"],
                "source": "trailer",
                "at": c["date"],
                "summary": c["subject"][:80],
                "session_ref": "",
            })
        # 2) commit_refs recorded in the timeline (manual / story-done stamp).
        for ev in timeline:
            if not isinstance(ev, dict):
                continue
            sha = (ev.get("commit_ref") or "").strip()
            if not sha or sha in seen or any(f.startswith(sha) for f in seen):
                continue
            seen.add(sha)
            rows.append({
                "sha": sha[:8],
                "full_sha": sha,
                "source": f"timeline:{ev.get('type', '')}",
                "at": ev.get("at", ""),
                "summary": (ev.get("summary") or "")[:80],
                "session_ref": ev.get("session_ref", "") or "",
            })

    if as_json:
        print_json(rows)
    elif not rows:
        click.echo(
            f"Story/{name}: no commits found (no 'Work-Item: Story/{name}' "
            f"trailer in git log, no commit_ref in timeline)"
        )
    else:
        print_table(rows, ["sha", "source", "at", "summary", "session_ref"])


@story_group.command("show")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, help="Emit the raw spec as JSON.")
@_scope_option
def cmd_story_show(name: str, as_json: bool, scope: str) -> None:
    """Show a Story's full detail — header + AC/DoD + plan + recent timeline.

    Reads via the API client (NOT the DB), so it works against any source
    (filesystem / Postgres / remote) without local Postgres access. Closes the
    gap where agents fell back to raw YAML / direct SQL to read a Story (i-070).
    """
    def _items(raw: Any) -> list[str]:
        """Normalize an AC/DoD list whose items may be strings or
        ``{text/criterion/item, done}`` dicts."""
        out: list[str] = []
        for it in raw or []:
            if isinstance(it, str):
                out.append(it)
            elif isinstance(it, dict):
                text = it.get("text") or it.get("criterion") or it.get("item") or it.get("desc") or ""
                done = it.get("done") or it.get("checked")
                out.append(f"[{'x' if done else ' '}] {text}")
        return out

    with open_session(scope) as s:
        story = s.get_doc("Story", name)
        if story is None:
            raise fail(f"Story '{name}' not found in scope {scope!r}")
        spec = story.spec if isinstance(story.spec, dict) else dict(story.spec)

        if as_json:
            print_json(spec)
            return

        click.secho(f"\nStory: {story.name}", fg="cyan", bold=True)
        if spec.get("title"):
            click.echo(f"  {spec['title']}")
        click.echo(f"  status: {spec.get('status', '?')}"
                   + (f" · priority: {spec['priority']}" if spec.get("priority") else "")
                   + (f" · points: {spec['points']}" if spec.get("points") else ""))
        for k in ("feature", "owner", "reporter"):
            if spec.get(k):
                click.echo(f"  {k}: {spec[k]}")
        if spec.get("description"):
            click.secho("\nDescription", fg="yellow")
            click.echo(f"  {spec['description']}")

        ac = _items(spec.get("acceptance_criteria"))
        if ac:
            click.secho(f"\nAcceptance criteria ({len(ac)})", fg="yellow")
            for a in ac:
                click.echo(f"  - {a}")
        dod = _items(spec.get("definition_of_done"))
        if dod:
            click.secho(f"\nDefinition of done ({len(dod)})", fg="yellow")
            for d in dod:
                click.echo(f"  - {d}")

        plan = spec.get("plan_ref") or spec.get("plan")
        if plan:
            click.echo(f"\n  plan: {plan}")

        timeline = spec.get("timeline", []) or []
        if timeline:
            click.secho(f"\nTimeline (last {min(5, len(timeline))} of {len(timeline)})", fg="yellow")
            for ev in timeline[-5:]:
                if not isinstance(ev, dict):
                    continue
                at = (ev.get("at") or "")[:19]
                body = (ev.get("summary") or ev.get("body") or "")[:100]
                click.echo(f"  · {at} [{ev.get('type', '')}] {body}")

        # Commits stamped with the Work-Item trailer (prepare-commit-msg hook,
        # `dna sdlc hooks install`). git log --grep does the bookkeeping;
        # fail-soft (None) when git / a repo isn't available.
        commits = _gitsym.commits_for_work_item("Story", name)
        if commits:
            click.secho(f"\nCommits ({len(commits)}, via Work-Item trailer)", fg="yellow")
            for c in commits:
                click.echo(f"  {c['sha']}  {c['date']}  {c['subject']}")


@story_group.command("groom")
@click.argument("name")
@click.option("--title", default=None,
              help="Retitle the Story (e.g. a cli-create title that came in "
                   "truncated/desc-shaped — `story pr` builds the PR title from it).")
@click.option("--priority", type=click.Choice(VALID_PRIORITIES), default=None)
@click.option("--labels", default=None, help="Comma-separated. Replaces existing.")
@click.option("--reporter", default=None)
@click.option("--sprint", "sprint_ref", default=None)
@click.option("--business-value", "business_value", type=int, default=None)
@click.option("--release-target", "release_target", default=None,
              help="Epic name OR 'owner/pkg@semver'.")
@click.option("--ac", "acceptance_criteria", multiple=True,
              help="Acceptance criterion (repeatable). REPLACES existing list.")
@click.option("--dod", "definition_of_done", multiple=True,
              help="DoD item (repeatable). REPLACES existing list.")
@click.option("--ac-source", "ac_source", default=None)
@click.option("--dod-source", "dod_source", default=None)
@_scope_option
def cmd_story_groom(
    name: str, title: str | None, priority: str | None, labels: str | None,
    reporter: str | None, sprint_ref: str | None,
    business_value: int | None, release_target: str | None,
    acceptance_criteria: tuple[str, ...], definition_of_done: tuple[str, ...],
    ac_source: str | None, dod_source: str | None,
    scope: str,
) -> None:
    """Read-modify-write: update only the board-grade fields passed.

    Idempotent — running with no flags is a no-op (other than re-stamping
    updated_at, which we skip when nothing else changed).
    """
    extras: dict[str, Any] = {}
    if title:
        extras["title"] = title
    if priority:
        extras["priority"] = priority
    labels_list = _csv(labels)
    if labels_list is not None:
        extras["labels"] = labels_list
    if reporter:
        extras["reporter"] = reporter
    if sprint_ref:
        extras["sprint_ref"] = sprint_ref
    if business_value is not None:
        extras["business_value"] = business_value
    if release_target:
        extras["release_target"] = release_target
    if acceptance_criteria:
        extras["acceptance_criteria"] = list(acceptance_criteria)
        extras["acceptance_criteria_source"] = ac_source or "cli-groom"
    if definition_of_done:
        extras["definition_of_done"] = list(definition_of_done)
        extras["definition_of_done_source"] = dod_source or "cli-groom"

    if not extras:
        click.secho(f"GROOM Story/{name} — no changes (no flags passed)", fg="yellow")
        return

    with open_session(scope) as s:
        existing = s.get_doc("Story", name)
        if existing is None:
            raise fail(f"Story '{name}' not found in scope {scope!r}")
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        spec.update(extras)
        spec["updated_at"] = _now_iso()
        # v1.6: capture which fields the groom touched so the timeline
        # carries enough context to reconstruct grooming history.
        _append_timeline(spec, "groom", fields=extras)
        raw = _build_raw("Story", name, spec)
        s.run(s.kernel.write_document(scope, "Story", name, raw))
    flag_summary = ", ".join(f"{k}={v}" for k, v in extras.items())
    click.secho(f"GROOMED Story/{name} ({flag_summary})", fg="green")


# ---------------------------------------------------------------------------
# Issue subgroup
# ---------------------------------------------------------------------------

def _next_issue_number(scope: str) -> int:
    """Find the next available i-NNN number — delegates the numbering to the shared
    core ``next_issue_number`` (the same primitive the MCP ``create_issue`` uses)."""
    with open_session(scope) as s:
        existing = [i.name for i in s.query_list("Issue")]
    return _core_next_issue_number(existing)


@sdlc.group("feature")
def feature_group() -> None:
    """Feature-level operations."""


@feature_group.command("create")
@click.argument("name")
@click.option("--title", required=True,
              help="Short title shown on roadmap cards.")
@click.option("--desc", "description", required=True,
              help="Multi-line description of the Feature's scope.")
@click.option("--epic", default=None,
              help="Optional parent Epic name (for hierarchy).")
@click.option("--status", type=click.Choice(VALID_FEATURE_STATUS),
              default="discovery")
@click.option("--owner", default=None)
@click.option("--reporter", default=None,
              help="Actor who filed it. Defaults to DNA_CLI_REPORTER env "
                   "or 'claude-code'.")
@click.option("--priority", type=click.Choice(VALID_PRIORITIES), default=None)
@click.option("--labels", default=None, help="Comma-separated labels.")
@click.option("--business-value", "business_value", type=int, default=None,
              help="WSJF-style scalar (0-1000) — drives roadmap sort.")
@click.option("--target-package", "target_package", default=None,
              help="Owner/name of the Genome this Feature targets "
                   "(for the per-Genome roadmap widget).")
@click.option("--target-milestone", "target_milestone", default=None,
              help="Milestone name this Feature is scheduled into.")
@_scope_option
def cmd_feature_create(
    name: str, title: str, description: str,
    epic: str | None, status: str, owner: str | None, reporter: str | None,
    priority: str | None, labels: str | None, business_value: int | None,
    target_package: str | None, target_milestone: str | None,
    scope: str,
) -> None:
    """Create a new Feature.

    P4 of f-multi-role followups (s-sdlc-feature-create-cli, 2026-05-16).
    Closes the gap where Stories had full CRUD via CLI but Features
    required manual YAML editing. Unlike `story create`, no --ac/--dod
    guard — Features are roadmap nouns, AC + DoD live at the Story
    level.

    \b
    Example:
      dna sdlc feature create f-eval-experiment-pattern \\
        --title "Eval Lab → Experiment (Braintrust pattern)" \\
        --desc "Promote draft to immutable EvalExperiment + diff view." \\
        --priority high --business-value 850 \\
        --labels eval,braintrust-pattern
    """
    spec: dict[str, Any] = {
        "title": title,
        "description": description,
        "status": status,
    }
    if epic:
        spec["epic"] = epic
    if owner:
        spec["owner"] = owner
    if reporter:
        spec["reporter"] = reporter
    else:
        # Match Story create default: env override > "claude-code".
        spec["reporter"] = os.environ.get("DNA_CLI_REPORTER", "claude-code")
    if priority:
        spec["priority"] = priority
    labels_list = _csv(labels)
    if labels_list:
        spec["labels"] = labels_list
    if business_value is not None:
        spec["business_value"] = business_value
    if target_package:
        spec["target_package"] = target_package
    if target_milestone:
        spec["target_milestone"] = target_milestone
    now = _now_iso()
    spec["created_at"] = now
    spec["updated_at"] = now
    # First timeline event = the create itself.
    _append_timeline(spec, "status_change", to=status)

    raw = _build_raw("Feature", name, spec)
    with open_session(scope) as s:
        s.run(s.kernel.write_document(scope, "Feature", name, raw))
    click.secho(
        f"CREATED Feature/{name} (status: {status}"
        + (f", epic: {epic}" if epic else "")
        + ")", fg="green",
    )


@feature_group.command("show")
@click.argument("name")
@_scope_option
def cmd_feature_show(name: str, scope: str) -> None:
    """Show Feature detail — header + child-Story rollup (status counts + list).

    Mirrors `epic show` (i-041) — without it, agents fell back to reading raw
    YAML to understand a Feature's state.
    """
    with open_session(scope) as s:
        f = s.get_doc("Feature", name)
        if f is None:
            raise fail(f"Feature '{name}' not found in scope {scope!r}")
        click.secho(f"\nFeature: {f.name}", fg="cyan", bold=True)
        click.echo(f"  status: {f.spec.get('status')}")
        if f.spec.get("priority"):
            click.echo(f"  priority: {f.spec['priority']}")
        if f.spec.get("epic"):
            click.echo(f"  epic: {f.spec['epic']}")
        if f.spec.get("description"):
            click.echo(f"  {str(f.spec['description'])[:200]}")

        # Reverse lookup by story.spec.feature — robust vs the often-stale
        # forward Feature.spec.stories list (the link is maintained one-way at
        # `story create --feature`).
        children = [
            st for st in s.query_list("Story")
            if isinstance(st.spec, dict) and st.spec.get("feature") == name
        ]
        if not children:
            click.secho("\n  (no stories reference this feature)", fg="yellow")
            return
        counts: dict[str, int] = {}
        rows = []
        for story in children:
            st = story.spec.get("status", "?")
            counts[st] = counts.get(st, 0) + 1
            rows.append({"story": story.name, "status": st,
                         "priority": story.spec.get("priority", "")})
        summary = " · ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
        click.secho(f"\nStories ({len(children)}) — {summary}", fg="yellow")
        print_table(rows, ["story", "status", "priority"])


@feature_group.command("ship")
@click.argument("name")
@click.option("--commit-ref", "commit_ref", default=None,
              help="Git SHA shipped with this Feature. Auto-detected from HEAD when omitted.")
@click.option("--summary", default=None,
              help="One-line description (lands on the timeline event).")
@click.option("--force", is_flag=True,
              help="Mark done even when children Stories aren't all done.")
@click.option("--allow-no-produces", "allow_no_produces", is_flag=True,
              help="Silencia o warn de outputs vazios (produces[] + back-refs).")
@_scope_option
def cmd_feature_ship(
    name: str, commit_ref: str | None, summary: str | None,
    force: bool, allow_no_produces: bool, scope: str,
) -> None:
    """Cascade-close a Feature: verify all children Stories are ``done``,
    then flip ``status`` to ``done`` + auto-stamp commit_ref + summary
    in the timeline. Mirrors ``epic ship`` semantics.
    """
    if commit_ref is None:
        commit_ref = _git_head_sha()
    with open_session(scope) as s:
        ft = s.get_doc("Feature", name)
        if ft is None:
            raise fail(f"Feature '{name}' not found in scope {scope!r}")
        spec = dict(ft.spec) if isinstance(ft.spec, dict) else {}
        prev = spec.get("status")

        # Verify all children Stories are done unless --force.
        if not force:
            children = [
                st for st in s.query_list("Story")
                if (
                    isinstance(st.spec, dict)
                    and st.spec.get("feature") == name
                )
            ]
            non_done = [
                st.name for st in children
                if (st.spec.get("status") if isinstance(st.spec, dict) else None) != "done"
            ]
            if non_done:
                raise fail(
                    f"Feature/{name}: {len(non_done)} non-done children — "
                    f"{', '.join(non_done[:5])}"
                    + (f" (+{len(non_done) - 5} more)" if len(non_done) > 5 else "")
                    + ". Pass --force to override or finish those Stories first."
                )

        # FOCUS outputs guard (i-113, WARN-only): evaluate BEFORE we mutate the
        # spec so we judge the linked-outputs state as it stood at close time.
        if not allow_no_produces:
            for w in produces_guard(spec):
                click.secho(f"⚠ {w}", fg="yellow", err=True)
        spec["status"] = "done"
        spec["closed_at"] = _now_iso()
        spec["updated_at"] = _now_iso()
        timeline_extras: dict[str, Any] = {}
        if commit_ref:
            timeline_extras["commit_ref"] = commit_ref
        if summary:
            timeline_extras["summary"] = summary
        _append_timeline(
            spec, "status_change",
            **{"from": prev, "to": "done", **timeline_extras},
        )
        raw = _build_raw("Feature", name, spec)
        s.run(s.kernel.write_document(scope, "Feature", name, raw))
    click.secho(f"SHIPPED Feature/{name}", fg="green", bold=True)
    # Auto-stamp the Feature's reflect journey entry — the Narrative
    # close hook requires it. Story s-hook-fail-loudly-or-reflect-auto
    # (f-cognitive-honesty bug post-S2): cascade-shipping a Feature
    # didn't write reflect, hook skipped silently, Narrative not
    # synthesized. Mirrors `story done` → reflect-entry behaviour.
    reflect_entry = _write_feature_reflect_workflow_event(
        scope, name,
        summary=summary or f"Feature shipped via cascade: {name}",
    )
    if reflect_entry:
        click.secho(f"📍 journey: Feature/{name} → reflect", fg="cyan")
    # Post-transition hook point (fail-soft) — hooks registered by the
    # host platform fire here.
    _fire_post_transition("Feature", name, "ship", spec, {"scope": scope})


@feature_group.command("cancel")
@click.argument("name")
@click.option("--reason", required=True, help="Why is the Feature cancelled?")
@_scope_option
def cmd_feature_cancel(name: str, reason: str, scope: str) -> None:
    """Mark a Feature as cancelled with an explicit reason. Used when
    scope shifts and the Feature won't ship — preserves the historical
    intent while closing the open-work loop."""
    with open_session(scope) as s:
        ft = s.get_doc("Feature", name)
        if ft is None:
            raise fail(f"Feature '{name}' not found in scope {scope!r}")
        spec = dict(ft.spec) if isinstance(ft.spec, dict) else {}
        prev = spec.get("status")
        spec["status"] = "cancelled"
        spec["closed_at"] = _now_iso()
        spec["updated_at"] = _now_iso()
        spec["cancelled_reason"] = reason
        _append_timeline(
            spec, "status_change",
            **{"from": prev, "to": "cancelled", "summary": reason},
        )
        raw = _build_raw("Feature", name, spec)
        s.run(s.kernel.write_document(scope, "Feature", name, raw))
    click.secho(f"CANCELLED Feature/{name} — {reason}", fg="yellow")


@feature_group.command("start")
@click.argument("name")
@_scope_option
def cmd_feature_start(name: str, scope: str) -> None:
    """Move a Feature `discovery` → `in-development` (read-modify-write).

    Unlike `feature create` (a full overwrite that would clobber the doc),
    this preserves every other field (description, epic, priority,
    business_value, labels, …) and stamps a `status_change` event. Use it
    when work has clearly started on a Feature still parked in `discovery`.
    """
    with open_session(scope) as s:
        ft = s.get_doc("Feature", name)
        if ft is None:
            raise fail(f"Feature '{name}' not found in scope {scope!r}")
        spec = dict(ft.spec) if isinstance(ft.spec, dict) else {}
        # Copy the timeline list so _append_timeline can't mutate the cached
        # doc's list in place (the L2 cache returns the same ref across reads).
        spec["timeline"] = list(spec.get("timeline") or [])
        prev = spec.get("status")
        spec["status"] = "in-development"
        spec["updated_at"] = _now_iso()
        _append_timeline(
            spec, "status_change",
            **{"from": prev, "to": "in-development"},
        )
        raw = _build_raw("Feature", name, spec)
        s.run(s.kernel.write_document(scope, "Feature", name, raw))
    click.secho(
        f"STARTED Feature/{name} ({prev} → in-development)", fg="green",
    )


@story_group.command("cancel")
@click.argument("name")
@click.option("--reason", required=True, help="Why is the Story cancelled?")
@_scope_option
def cmd_story_cancel(name: str, reason: str, scope: str) -> None:
    """Mark a Story as cancelled with an explicit reason. Same intent
    as feature cancel — close the open-work loop without silently
    dropping context."""
    _update_story_status(scope, name, "cancelled", {
        "closed_at": _now_iso(),
        "cancelled_reason": reason,
    }, summary=reason)
    try:
        _active_story_clear_if_matches(scope, name)
    except Exception:  # noqa: BLE001
        pass
    # Closing beat: clear the FOCUS anchor immediately (same as story done /
    # issue resolve). "entregue" is the shared closing-beat label — pragmatically
    # correct: the work item is closed and the pointer should not linger.
    _post_done_beat(scope, "Story", name)


@story_group.command("reopen")
@click.argument("name")
@click.option("--reason", default="reopened", help="Why reopen?")
@click.option("--to", "to_status", default="todo",
              type=click.Choice(VALID_STORY_STATUS),
              help="Status to flip back to (default: todo).")
@_scope_option
def cmd_story_reopen(name: str, reason: str, to_status: str, scope: str) -> None:
    """Reopen a closed/cancelled Story — flip status back to todo
    (or specified) and clear closed_at + cancelled_reason. Stamps a
    status_change event with the reopen reason."""
    with open_session(scope) as s:
        existing = s.get_doc("Story", name)
        if existing is None:
            raise fail(f"Story '{name}' not found in scope {scope!r}")
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        prev = spec.get("status")
        spec["status"] = to_status
        spec.pop("closed_at", None)
        spec.pop("cancelled_reason", None)
        spec["updated_at"] = _now_iso()
        _append_timeline(
            spec, "status_change",
            **{"from": prev, "to": to_status, "summary": f"REOPEN: {reason}"},
        )
        raw = _build_raw("Story", name, spec)
        s.run(s.kernel.write_document(scope, "Story", name, raw))
    click.secho(f"REOPENED Story/{name} ({prev} → {to_status})", fg="cyan")


@feature_group.command("reopen")
@click.argument("name")
@click.option("--reason", default="reopened", help="Why reopen?")
@click.option("--to", "to_status", default="discovery",
              type=click.Choice(VALID_FEATURE_STATUS),
              help="Status to flip back to (default: discovery).")
@_scope_option
def cmd_feature_reopen(name: str, reason: str, to_status: str, scope: str) -> None:
    """Reopen a closed/cancelled Feature — flip status back to
    discovery (or specified). Mirror of feature cancel."""
    with open_session(scope) as s:
        ft = s.get_doc("Feature", name)
        if ft is None:
            raise fail(f"Feature '{name}' not found in scope {scope!r}")
        spec = dict(ft.spec) if isinstance(ft.spec, dict) else {}
        prev = spec.get("status")
        spec["status"] = to_status
        spec.pop("closed_at", None)
        spec.pop("cancelled_reason", None)
        spec["updated_at"] = _now_iso()
        _append_timeline(
            spec, "status_change",
            **{"from": prev, "to": to_status, "summary": f"REOPEN: {reason}"},
        )
        raw = _build_raw("Feature", name, spec)
        s.run(s.kernel.write_document(scope, "Feature", name, raw))
    click.secho(f"REOPENED Feature/{name} ({prev} → {to_status})", fg="cyan")


def _auto_narrate_line(feature_name: str, holder: Any) -> str | None:
    """Heuristic synthesizer for ``Feature.spec.narrative_line``. Walks
    Stories whose ``spec.feature`` matches and assembles a Portuguese
    past-tense summary from the most recent done titles. Returns
    ``None`` when there's nothing notable.

    Pattern: "<N> stories shipped — {top 2 titles}. <K> em andamento.".
    Deterministic (no LLM), zero token cost. Meant as a SEED for
    Features the agent hasn't manually narrated; an explicit
    ``feature narrative --line "..."`` always wins.
    """
    done: list[tuple[str, str]] = []
    in_progress: list[str] = []
    for st in holder.query_list("Story"):
        sp = st.spec or {}
        if sp.get("feature") != feature_name:
            continue
        title = (sp.get("title") or sp.get("description", "") or st.name)[:80]
        status = sp.get("status")
        if status == "done":
            done.append((sp.get("closed_at") or sp.get("updated_at") or "", title))
        elif status in ("in-progress", "review"):
            in_progress.append(title)
    if not done and not in_progress:
        return None
    done.sort(reverse=True)  # newest closed_at first
    parts: list[str] = []
    if done:
        sample = ", ".join(f'"{t}"' for _, t in done[:2])
        if len(done) > 2:
            parts.append(f"{len(done)} stories shippadas (recentes: {sample})")
        else:
            parts.append(f"{len(done)} stor{'ies' if len(done) > 1 else 'y'} shippada{'s' if len(done) > 1 else ''}: {sample}")
    if in_progress:
        parts.append(f"{len(in_progress)} em andamento")
    return ". ".join(parts) + "."


@feature_group.command("narrate-all")
@click.option("--only-empty", is_flag=True, default=True,
              help="Only update Features without an existing narrative_line.")
@click.option("--overwrite", is_flag=True, default=False,
              help="Force overwrite even if Feature already has a narrative_line.")
@_scope_option
def cmd_feature_narrate_all(only_empty: bool, overwrite: bool, scope: str) -> None:
    """Seed `Feature.spec.narrative_line` deterministically across
    every Feature that lacks one. Walks children Stories per Feature
    and synthesizes a Portuguese past-tense summary. Zero LLM cost.

    Default: skip Features that already have a narrative_line
    (avoid clobbering hand-curated prose). Pass --overwrite to
    re-seed everything.
    """
    if overwrite:
        only_empty = False
    updated = 0
    skipped = 0
    with open_session(scope) as s:
        for ft in s.query_list("Feature"):
            sp = dict(ft.spec) if isinstance(ft.spec, dict) else {}
            if only_empty and sp.get("narrative_line"):
                skipped += 1
                continue
            line = _auto_narrate_line(ft.name, s.holder)
            if line is None:
                skipped += 1
                continue
            sp["narrative_line"] = line
            sp["updated_at"] = _now_iso()
            raw = _build_raw("Feature", ft.name, sp)
            s.run(s.kernel.write_document(scope, "Feature", ft.name, raw))
            updated += 1
            click.echo(f"  ✓ {ft.name}: {line[:80]}{'…' if len(line) > 80 else ''}")
    click.secho(
        f"NARRATED {updated} Feature(s); skipped {skipped}.",
        fg="cyan",
    )


@feature_group.command("narrative")
@click.argument("name")
@click.option("--line", "narrative_line", required=True,
              help="One-sentence prose summary of what this Feature has been DOING.")
@_scope_option
def cmd_feature_narrative(name: str, narrative_line: str, scope: str) -> None:
    """Update Feature.spec.narrative_line — agent-curated 1-sentence
    semantic summary shown next to the Feature in Studio's narrative
    swimlane. Past-tense voice ("agent shipou X, descobriu Y").
    """
    with open_session(scope) as s:
        ft = s.get_doc("Feature", name)
        if ft is None:
            raise fail(f"Feature '{name}' not found in scope {scope!r}")
        spec = dict(ft.spec) if isinstance(ft.spec, dict) else {}
        spec["narrative_line"] = narrative_line.strip()
        spec["updated_at"] = _now_iso()
        raw = _build_raw("Feature", name, spec)
        s.run(s.kernel.write_document(scope, "Feature", name, raw))
    click.secho(f"NARRATED Feature/{name}", fg="cyan")


@sdlc.command("epic-reopen")
@click.argument("name")
@click.option("--reason", default="reopened", help="Why reopen?")
@click.option("--to", "to_status", default="planning",
              type=click.Choice(VALID_EPIC_STATUS),
              help="Status to flip back to (default: planning).")
@_scope_option
def cmd_epic_reopen(name: str, reason: str, to_status: str, scope: str) -> None:
    """Reopen a closed Epic — flip status back to planning."""
    with open_session(scope) as s:
        ep = s.get_doc("Epic", name)
        if ep is None:
            raise fail(f"Epic '{name}' not found in scope {scope!r}")
        spec = dict(ep.spec) if isinstance(ep.spec, dict) else {}
        prev = spec.get("status")
        spec["status"] = to_status
        spec.pop("closed_at", None)
        spec["updated_at"] = _now_iso()
        _append_timeline(
            spec, "status_change",
            **{"from": prev, "to": to_status, "summary": f"REOPEN: {reason}"},
        )
        raw = _build_raw("Epic", name, spec)
        s.run(s.kernel.write_document(scope, "Epic", name, raw))
    click.secho(f"REOPENED Epic/{name} ({prev} → {to_status})", fg="cyan")


@sdlc.group("issue")
def issue_group() -> None:
    """Issue-level operations."""


@issue_group.command("file")
@click.option("--slug", required=True, help="Short kebab-case slug, e.g. 'date-postgres-bug'.")
@click.option(
    "--type", "issue_type",
    type=click.Choice(VALID_ISSUE_TYPE), default="bug",
)
@click.option(
    "--severity",
    type=click.Choice(VALID_ISSUE_SEVERITY), default="medium",
)
@click.option("--desc", "description", required=True)
@click.option("--owner", default=None)
@click.option("--related-feature", default=None, help="Feature name (optional).")
@click.option("--related-finding", default=None, help="Finding name (optional, eval-derived).")
@_scope_option
def cmd_issue_file(
    slug: str, issue_type: str, severity: str, description: str,
    owner: str | None, related_feature: str | None, related_finding: str | None,
    scope: str,
) -> None:
    """File a new Issue with auto-incremented i-NNN-<slug> name."""
    n = _next_issue_number(scope)
    name = f"i-{n:03d}-{slug}"
    spec: dict[str, Any] = {
        "description": description,
        "type": issue_type,
        "severity": severity,
        "status": "open",
    }
    if owner:
        spec["owner"] = owner
    if related_feature:
        spec["related_feature"] = related_feature
    if related_finding:
        spec["related_finding"] = related_finding
    # v1.6: timeline event for the file (no `from`, status set to open).
    _append_timeline(spec, "status_change", to="open")

    raw = _build_raw("Issue", name, spec)
    with open_session(scope) as s:
        s.run(s.kernel.write_document(scope, "Issue", name, raw))
    click.secho(
        f"FILED Issue/{name} ({issue_type}/{severity})",
        fg="yellow",
    )


@issue_group.command("triage")
@click.argument("name")
@_scope_option
def cmd_issue_triage(name: str, scope: str) -> None:
    """Mark Issue status: triaged."""
    with open_session(scope) as s:
        existing = s.get_doc("Issue", name)
        if existing is None:
            raise fail(f"Issue '{name}' not found")
        spec = dict(existing.spec)
        prev = spec.get("status")
        spec["status"] = "triaged"
        _append_timeline(spec, "status_change", **{"from": prev, "to": "triaged"})
        raw = _build_raw("Issue", name, spec)
        s.run(s.kernel.write_document(scope, "Issue", name, raw))
    click.secho(f"TRIAGED {name}", fg="green")


@issue_group.command("resolve")
@click.argument("name")
@click.option("--resolution", default=None, help="How was it resolved?")
@click.option("--allow-no-produces", "allow_no_produces", is_flag=True,
              help="Silencia o warn de outputs vazios (produces[] + back-refs).")
@_scope_option
def cmd_issue_resolve(
    name: str, resolution: str | None, allow_no_produces: bool, scope: str,
) -> None:
    """Mark Issue status: resolved, set closed_at + optional resolution text."""
    with open_session(scope) as s:
        existing = s.get_doc("Issue", name)
        if existing is None:
            raise fail(f"Issue '{name}' not found")
        spec = dict(existing.spec)
        prev = spec.get("status")
        # FOCUS outputs guard (i-113, WARN-only): judged pre-mutation.
        if not allow_no_produces:
            for w in produces_guard(spec):
                click.secho(f"⚠ {w}", fg="yellow", err=True)
        spec["status"] = "resolved"
        spec["closed_at"] = _now_iso()
        if resolution:
            spec["resolution"] = resolution
        _append_timeline(
            spec, "status_change",
            **{"from": prev, "to": "resolved", "summary": resolution},
        )
        raw = _build_raw("Issue", name, spec)
        s.run(s.kernel.write_document(scope, "Issue", name, raw))
        # GitHub bridge (s-github-issues-bridge): a published Issue closes
        # its GitHub twin with a comment. Best-effort by contract — the
        # local resolve ALREADY persisted above; a missing gh / dead
        # network degrades to a warning, never a failure.
        if spec.get("github_number"):
            from dna_cli import _github_bridge as gb  # noqa: PLC0415
            warning = gb.close_issue_best_effort(
                int(spec["github_number"]),
                gb.default_repo(),
                gb.close_comment(name, resolution),
            )
            if warning:
                click.secho(f"⚠ {warning}", fg="yellow", err=True)
            else:
                click.secho(
                    f"CLOSED GitHub #{spec['github_number']} (comment posted)",
                    fg="green",
                )
                try:  # provenance refresh — same best-effort contract
                    spec["github_state"] = "closed"
                    spec["github_synced_at"] = _now_iso()
                    raw = _build_raw("Issue", name, spec)
                    s.run(s.kernel.write_document(scope, "Issue", name, raw))
                except Exception as e:  # noqa: BLE001 — fail-soft
                    click.secho(
                        f"⚠ não consegui atualizar github_state no doc "
                        f"(non-fatal): {e}", fg="yellow", err=True,
                    )
    # Closing beat (i-126): explicitly clear the merged FOCUS anchor — same
    # contract as `story done`. Best-effort, never breaks the resolve.
    _post_done_beat(scope, "Issue", name)
    click.secho(f"RESOLVED {name}", fg="green")


@issue_group.command("comment")
@click.argument("name")
@click.option("--body", required=True, help="The comment / finding / decision text.")
@click.option("--type", "event_type", default=None,
              type=click.Choice(("comment", "decision")),
              help="Defaults to 'comment'; decision-shaped bodies auto-promote.")
@_scope_option
def cmd_issue_comment(
    name: str, body: str, event_type: str | None, scope: str,
) -> None:
    """Append a finding / decision to an Issue timeline without changing status.

    Mirrors `story comment` / `spike comment` — bugs accrue investigation notes
    + root-cause decisions over their arc (report→triage→fix→resolve), and that
    running trail belongs on the timeline (the FOCUS feed + audit), not only in
    the final `resolve` resolution text.
    """
    if event_type is None:
        event_type = "decision" if _looks_like_decision(body) else "comment"
    with open_session(scope) as s:
        existing = s.get_doc("Issue", name)
        if existing is None:
            raise fail(f"Issue '{name}' not found in scope {scope!r}")
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        spec["timeline"] = list(spec.get("timeline") or [])
        _append_timeline(spec, event_type, summary=body)
        raw = _build_raw("Issue", name, spec)
        s.run(s.kernel.write_document(scope, "Issue", name, raw))
    click.secho(f"COMMENTED Issue/{name} ({event_type})", fg="green")


# ---------------------------------------------------------------------------
# Epic subgroup (renamed from Milestone in v1.3 — Jira/ADO alignment)
# ---------------------------------------------------------------------------

@sdlc.group("epic")
def epic_group() -> None:
    """Epic-level operations (Jira/ADO terminology; was 'milestone' in v1.2)."""


@epic_group.command("create")
@click.argument("name")
@click.option("--title", required=True,
              help="Short title shown on roadmap cards.")
@click.option("--desc", "description", required=True,
              help="Multi-line description of the Epic's scope.")
@click.option("--status", type=click.Choice(VALID_EPIC_STATUS),
              default="planning", show_default=True)
@click.option("--reporter", default=None,
              help="Actor who filed it. Defaults to DNA_CLI_REPORTER env "
                   "or 'claude-code'.")
@click.option("--priority", type=click.Choice(VALID_PRIORITIES), default=None)
@click.option("--labels", default=None, help="Comma-separated labels.")
@click.option("--business-value", "business_value", type=int, default=None,
              help="WSJF-style scalar (0-1000) — drives roadmap sort.")
@_scope_option
def cmd_epic_create(
    name: str, title: str, description: str, status: str,
    reporter: str | None, priority: str | None, labels: str | None,
    business_value: int | None, scope: str,
) -> None:
    """Create a new Epic.

    Closes the last CRUD gap in the SDLC CLI (s-dx-epic-create): Story and
    Feature had `create`, but an Epic had to be hand-authored via `dna doc
    apply` — an asymmetry the DX epic (e-dna-dx) exists to kill. Mirrors
    `feature create`: same envelope, same write path (`kernel.write_document`),
    same initial-timeline event. Unlike `story create`, no --ac/--dod guard —
    Epics are roadmap nouns; exit criteria live at the Story level.

    \b
    Example:
      dna sdlc epic create e-dna-dx \\
        --title "DNA developer experience" \\
        --desc "Collapse the consumer's prompt plumbing to a one-liner." \\
        --status in-progress --priority high --labels dx,sdk,dogfood
    """
    spec: dict[str, Any] = {
        "title": title,
        "description": description,
        "status": status,
    }
    if reporter:
        spec["reporter"] = reporter
    else:
        spec["reporter"] = os.environ.get("DNA_CLI_REPORTER", "claude-code")
    if priority:
        spec["priority"] = priority
    labels_list = _csv(labels)
    if labels_list:
        spec["labels"] = labels_list
    if business_value is not None:
        spec["business_value"] = business_value
    now = _now_iso()
    spec["created_at"] = now
    spec["updated_at"] = now
    # First timeline event = the create itself (mirrors feature/story create).
    _append_timeline(spec, "status_change", to=status)

    raw = _build_raw("Epic", name, spec)
    with open_session(scope) as s:
        s.run(s.kernel.write_document(scope, "Epic", name, raw))
    click.secho(f"CREATED Epic/{name} (status: {status})", fg="green")


@epic_group.command("show")
@click.argument("name")
@_scope_option
def cmd_epic_show(name: str, scope: str) -> None:
    """Show Epic burndown — features + stories with status counts."""
    with open_session(scope) as s:
        ep = s.get_doc("Epic", name)
        if ep is None:
            raise fail(f"Epic '{name}' not found in scope {scope!r}")
        ms = ep  # local alias to keep diff small below

        click.secho(f"\nEpic: {ms.name}", fg="cyan", bold=True)
        click.echo(f"  status: {ms.spec.get('status')}")
        click.echo(f"  target_date: {ms.spec.get('target_date', '?')}")
        if ms.spec.get("closed_at"):
            click.echo(f"  closed_at: {ms.spec['closed_at']}")
        pkg = ms.spec.get("target_package", "")
        ver = ms.spec.get("target_version", "")
        if pkg:
            click.echo(f"  target: {pkg}@{ver}" if ver else f"  target: {pkg}")

        # Reverse-lookup features by Feature.spec.epic — the forward
        # Epic.spec.features[] list is never populated (`feature create
        # --epic X` maintains only the back-ref), so reading it showed
        # "(no features linked)" even for correctly-linked features
        # (s-epic-show-forward-features). The back-ref is the single source
        # of truth; mirrors how `feature show` finds stories by
        # Story.spec.feature. One scan, sorted by name for stable output.
        features = sorted(
            (
                f for f in s.query_list("Feature")
                if isinstance(f.spec, dict) and f.spec.get("epic") == name
            ),
            key=lambda f: f.name,
        )
        if not features:
            click.secho("\n  (no features linked)", fg="yellow")
            return

        # Reverse-lookup by Story.spec.feature — robust vs the often-stale
        # forward Feature.spec.stories[] list (the link is maintained one-way
        # at `story create --feature`). Mirrors `feature show`. One scan,
        # grouped by feature, so an Epic with N features is still O(stories).
        stories_by_feature: dict[str, list[Any]] = {}
        for st in s.query_list("Story"):
            if not isinstance(st.spec, dict):
                continue
            fref = st.spec.get("feature")
            if fref:
                stories_by_feature.setdefault(fref, []).append(st)

        click.secho("\nFeatures:", fg="yellow")
        total_stories = 0
        done_stories = 0
        for f in features:
            fn = f.name
            f_status = f.spec.get("status", "?")
            children = stories_by_feature.get(fn, [])
            f_total = len(children)
            f_done = sum(
                1 for story in children if story.spec.get("status") == "done"
            )
            total_stories += f_total
            done_stories += f_done
            color = "green" if f_status == "done" else None
            click.secho(
                f"  • {fn} [{f_status}] — {f_done}/{f_total} stories done",
                fg=color,
            )

        if total_stories > 0:
            pct = (done_stories / total_stories) * 100
            click.secho(
                f"\nBurndown: {done_stories}/{total_stories} stories done ({pct:.0f}%)",
                fg="cyan", bold=True,
            )
        click.echo("")


@sdlc.command("extract-decisions")
@click.option("--scope", default=DEFAULT_SCOPE, show_default=True,
              help="Scope to walk.")
@click.option("--dry-run", is_flag=True,
              help="Print matches but don't write.")
def cmd_sdlc_extract_decisions(scope: str, dry_run: bool) -> None:
    """Walk every Story / Feature / Epic / Issue timeline + promote
    pre-existing comments that look like decisions. Pure regex —
    zero LLM cost. Idempotent: events already typed as 'decision'
    or 'status_change' are untouched.

    Useful pra retroativamente capturar o "porquê" das decisões que
    foram comentadas como `comment` em vez de `decision` durante a
    sessão. Output: rows for each promoted event, then a count.
    """
    promoted = 0
    scanned = 0
    with open_session(scope) as s:
        for kind in ("Story", "Feature", "Epic", "Issue"):
            try:
                docs = s.query_list(kind)
            except Exception:  # noqa: BLE001
                continue
            for doc in docs:
                spec = dict(doc.spec) if isinstance(doc.spec, dict) else {}
                timeline = list(spec.get("timeline") or [])
                changed = False
                for ev in timeline:
                    if not isinstance(ev, dict):
                        continue
                    if ev.get("type") != "comment":
                        continue
                    body = ev.get("summary") or ""
                    scanned += 1
                    if not _looks_like_decision(body):
                        continue
                    ev["type"] = "decision"
                    promoted += 1
                    changed = True
                    click.echo(
                        f"  promoted {kind}/{doc.name} @ {ev.get('at','')}: "
                        f"{body[:80]}{'…' if len(body) > 80 else ''}"
                    )
                if changed and not dry_run:
                    spec["timeline"] = timeline
                    spec["updated_at"] = _now_iso()
                    raw = _build_raw(kind, doc.name, spec)
                    s.run(s.kernel.write_document(scope, kind, doc.name, raw))
    suffix = " (dry-run)" if dry_run else ""
    click.secho(
        f"PROMOTED {promoted} of {scanned} comment events{suffix}.",
        fg="cyan",
    )


@sdlc.command("backfill")
@click.argument("pattern")
@click.option(
    "--from", "from_dir", required=True,
    help="Directory containing markdown files to back-fill from.",
)
@click.option(
    "--kind", "target_kind",
    type=click.Choice(["Spec", "Plan", "auto"]), default="auto",
    show_default=True,
    help="Generate Spec or Plan docs (auto: infer from path — specs/ → Spec, plans/ → Plan).",
)
@click.option(
    "--default-status",
    type=click.Choice(["draft", "proposed", "accepted", "deprecated", "superseded"]),
    default="accepted", show_default=True,
)
@click.option("--dry-run", is_flag=True, help="Preview without writing.")
@_scope_option
def cmd_backfill(
    pattern: str, from_dir: str, target_kind: str,
    default_status: str, dry_run: bool, scope: str,
) -> None:
    """Back-fill Spec/Plan docs from a directory of markdown files.

    File naming convention: ``YYYY-MM-DD-<slug>.md`` extracts the date.
    Title is the first ``# Heading`` line. Status is parsed from
    ``**Status**: X`` if present, else uses --default-status.
    Authors from ``**Author**: A, B`` if present.

    PATTERN is the spec-driven methodology label (free-form):
    superpowers, bmad, droid, rfc, adr, custom.
    """
    import re
    from pathlib import Path
    src = Path(from_dir).resolve()
    if not src.is_dir():
        raise fail(f"--from path is not a directory: {src}")

    files = sorted(src.rglob("*.md"))
    if not files:
        click.secho(f"(no .md files under {src})", fg="yellow")
        return

    click.secho(
        f"Back-filling {len(files)} markdown files from {src} (pattern={pattern})",
        fg="cyan",
    )

    NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$")
    STATUS_RE = re.compile(r"^\*\*Status\*\*\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
    AUTHOR_RE = re.compile(r"^\*\*Authors?\*\*\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
    TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)

    # repo root: 4 levels up from this file (cli_dna/_/sdlc_cmd.py → harness root)
    repo_root = Path(__file__).resolve().parents[3]

    created_count = 0
    skipped_count = 0

    with open_session(scope) as s:
        existing_specs = {sp.name for sp in s.query_list("Spec")}
        existing_plans = {pl.name for pl in s.query_list("Plan")}

        for f in files:
            rel = f.relative_to(src)
            m = NAME_RE.match(f.name)
            if not m:
                skipped_count += 1
                continue
            date, slug = m.group(1), m.group(2)
            doc_name = f"{date}-{slug}"

            if target_kind == "auto":
                parent = f.parent.name
                if parent == "specs":
                    kind = "Spec"
                elif parent == "plans":
                    kind = "Plan"
                else:
                    skipped_count += 1
                    continue
            else:
                kind = target_kind

            if kind == "Spec" and doc_name in existing_specs:
                skipped_count += 1
                continue
            if kind == "Plan" and doc_name in existing_plans:
                skipped_count += 1
                continue

            text = f.read_text(encoding="utf-8", errors="replace")
            status_match = STATUS_RE.search(text)
            status_raw = (
                status_match.group(1) if status_match else default_status
            ).strip().lower()
            # ADR-style: legacy "shipped" / "rejected" / etc. map to the
            # canonical {draft, proposed, accepted, deprecated, superseded}.
            status_map = {
                "shipped": "accepted",
                "rejected": "deprecated",
                "wip": "draft",
                "draft": "draft",
                "proposed": "proposed",
                "accepted": "accepted",
                "deprecated": "deprecated",
                "in progress": "draft",
                "in-progress": "draft",
                "superseded": "superseded",
            }
            status = next(
                (v for k, v in status_map.items() if k in status_raw),
                default_status,
            )

            title_match = TITLE_RE.search(text)
            title = title_match.group(1).strip() if title_match else slug.replace("-", " ").title()

            authors_match = AUTHOR_RE.search(text)
            authors: list[str] = []
            if authors_match:
                authors = [
                    a.strip() for a in re.split(r"[,;]|\band\b", authors_match.group(1))
                    if a.strip()
                ]

            # Bundle pattern: body field IS the markdown content read
            # from the source file. The doc is self-contained — kernel
            # serializes it back as SPEC.md / PLAN.md inside the bundle.
            try:
                origin_rel = str(f.resolve().relative_to(repo_root))
            except ValueError:
                origin_rel = str(f.resolve())

            # updated_at = file mtime (ISO-8601). Historically this fed a
            # cognitive deep_sleep orphan scan that needed the doc's age —
            # without it the scan treated the doc as "unknown age" and
            # proposed an ArchiveProposal on the next tick (the bug that
            # produced the 88-skeleton-Plans loop). Neither that scan nor
            # the ArchiveProposal Kind exists any more (censo-12-kinds,
            # 2026-07-20); the stamp stays because it is a useful, honest
            # mtime on the doc.
            try:
                mtime = datetime.fromtimestamp(
                    f.stat().st_mtime, tz=timezone.utc,
                ).isoformat(timespec="seconds")
            except OSError:
                mtime = _now_iso()

            spec_data: dict[str, Any] = {
                "title": title,
                "date": date,
                "status": status,
                "pattern": pattern,
                "body": text,
                "updated_at": mtime,
                # origin = audit trail of where the markdown was harvested
                # from. Optional. Doesn't affect rendering.
                "origin": origin_rel,
            }
            if authors:
                spec_data["authors"] = authors

            raw = _build_raw(kind, doc_name, spec_data)
            if dry_run:
                click.echo(f"  [dry-run] {kind}/{doc_name} ← {rel}  status={status}")
            else:
                try:
                    s.run(s.kernel.write_document(scope, kind, doc_name, raw))
                    created_count += 1
                except Exception as e:
                    click.secho(
                        f"  FAIL {kind}/{doc_name}: {type(e).__name__}: {e}",
                        fg="red", err=True,
                    )

    click.secho(
        f"\nBack-fill complete: {created_count} created, {skipped_count} skipped"
        + (" (dry-run)" if dry_run else ""),
        fg="green" if not dry_run else "yellow",
        bold=True,
    )


@epic_group.command("ship")
@click.argument("name")
@_scope_option
def cmd_epic_ship(name: str, scope: str) -> None:
    """Mark Epic status: done, set closed_at, cascade-close Features whose Stories all done."""
    with open_session(scope) as s:
        ms = s.get_doc("Epic", name)
        if ms is None:
            raise fail(f"Epic '{name}' not found")
        spec = dict(ms.spec) if isinstance(ms.spec, dict) else {}
        spec["status"] = "done"
        spec["closed_at"] = _now_iso()
        raw = _build_raw("Epic", name, spec)
        s.run(s.kernel.write_document(scope, "Epic", name, raw))
        click.secho(f"DONE Epic/{name}", fg="green", bold=True)

        # Reverse-lookup features (by Feature.spec.epic) and their stories
        # (by Story.spec.feature) — the forward Epic.spec.features[] /
        # Feature.spec.stories[] lists are never populated, so the old
        # forward-link cascade silently closed nothing
        # (s-epic-show-forward-features). Back-refs are the single source
        # of truth; mirrors `epic show`.
        stories_by_feature: dict[str, list[Any]] = {}
        for st in s.query_list("Story"):
            if not isinstance(st.spec, dict):
                continue
            fref = st.spec.get("feature")
            if fref:
                stories_by_feature.setdefault(fref, []).append(st)
        cascade = []
        for f in s.query_list("Feature"):
            if not isinstance(f.spec, dict) or f.spec.get("epic") != name:
                continue
            fn = f.name
            if f.spec.get("status") == "done":
                continue
            children = stories_by_feature.get(fn, [])
            all_done = bool(children) and all(
                st.spec.get("status") == "done" for st in children
            )
            if all_done:
                f_spec = dict(f.spec)
                f_spec["status"] = "done"
                f_spec["closed_at"] = _now_iso()
                f_raw = _build_raw("Feature", fn, f_spec)
                s.run(s.kernel.write_document(scope, "Feature", fn, f_raw))
                cascade.append(fn)

        if cascade:
            click.secho(
                f"  Cascade-closed Features: {', '.join(cascade)}",
                fg="cyan",
            )


# (The `sdlc session` capture group — multi-tool AgentSession adapters —
# is a host-platform surface and does not ship here. The AgentSession
# Kind itself IS registered; write sessions via `dna doc apply`.)

# ---------------------------------------------------------------------------
# Narrative — daily/release/retro write cadence + reminder
# ---------------------------------------------------------------------------

@sdlc.group("narrative")
def narrative_group() -> None:
    """Project narrative — write cadence reminders + scaffold helpers.

    The Narrative Kind itself is created via ``dna doc apply`` against
    a NARRATIVE.md bundle (the canonical write path). These commands
    are the operator-side ergonomics: telling you when the last one
    was written, what's pending since then, and stubbing out the next
    one so the friction to write is low.
    """


@narrative_group.command("status")
@click.option("--scope", default=DEFAULT_SCOPE, show_default=True)
def cmd_narrative_status(scope: str) -> None:
    """Report cadence: how long since the last Narrative was written,
    how many SDLC events accumulated since, and a suggestion if it's
    time to write one. Prints a short report and exits 0 always.
    """
    from datetime import datetime, timezone

    with open_session(scope) as s:
        try:
            narratives = s.query_list("Narrative")
        except Exception:  # noqa: BLE001
            narratives = []

        def _sort_key(d: Any):
            sp = d.spec or {}
            return (
                sp.get("period_end") or sp.get("updated_at")
                or sp.get("created_at") or d.name
            )
        narratives.sort(key=_sort_key, reverse=True)

        click.secho(f"📜 narrative status — scope: {scope}", bold=True)
        click.echo(f"   total narratives: {len(narratives)}")

        if not narratives:
            click.secho(
                "   ⚠️  no narratives yet — run `dna sdlc narrative new "
                "<slug>` to scaffold the first one.",
                fg="yellow",
            )
            return

        latest = narratives[0]
        sp = latest.spec or {}
        latest_ts = (
            sp.get("period_end") or sp.get("updated_at")
            or sp.get("created_at")
        )
        click.echo(f"   most recent: {latest.name}")
        click.echo(f"   intent: {sp.get('author_intent') or '(unset)'}")
        click.echo(f"   last write: {latest_ts or '(unknown)'}")

        # Days since last narrative
        days = 0
        age = "(unknown)"
        if latest_ts:
            try:
                ts_clean = str(latest_ts).replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts_clean)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                delta = datetime.now(timezone.utc) - dt
                days = delta.days
                hours = int(delta.total_seconds() / 3600)
                if days >= 1:
                    age = f"{days} day{'s' if days != 1 else ''} ago"
                elif hours >= 1:
                    age = f"{hours} hour{'s' if hours != 1 else ''} ago"
                else:
                    age = "earlier today"
                click.echo(f"   age: {age}")
            except (ValueError, TypeError):
                days = 0

            # Count SDLC events newer than the last narrative.
            event_count = 0
            for kind in ("Story", "Feature", "Epic", "Issue"):
                try:
                    docs = s.query_list(kind)
                except Exception:  # noqa: BLE001
                    continue
                for doc in docs:
                    for ev in (doc.spec or {}).get("timeline") or []:
                        if not isinstance(ev, dict):
                            continue
                        ev_ts = ev.get("at")
                        if ev_ts and ev_ts > latest_ts:
                            event_count += 1
            click.echo(f"   events since: {event_count}")

            # Suggestion based on cadence.
            click.echo("")
            if days >= 7:
                click.secho(
                    f"   💡 it's been {days} day(s) — overdue for a "
                    f"weekly narrative. Run `dna sdlc narrative new "
                    f"$(date +%Y-%m-%d)-weekly`.",
                    fg="yellow",
                )
            elif event_count >= 30:
                click.secho(
                    f"   💡 {event_count} events since last narrative — "
                    f"good time to write a new one.",
                    fg="cyan",
                )
            elif days >= 1:
                click.secho(
                    f"   ℹ️  {age}, {event_count} event(s) since. "
                    f"Light day — narrative optional.",
                    fg="blue",
                )
            else:
                click.echo("   ✓ narrative fresh; carry on.")


@narrative_group.command("new")
@click.argument("slug")
@click.option("--title", default=None, help="Optional title; falls back to slug.")
@click.option("--intent", "author_intent", default="daily",
              type=click.Choice(["daily", "weekly", "release", "retro", "incident", "freeform"]),
              help="Author intent (drives Studio grouping).")
@click.option("--scope", default=DEFAULT_SCOPE, show_default=True)
def cmd_narrative_new(
    slug: str, title: str | None, author_intent: str, scope: str,
) -> None:
    """Scaffold a NARRATIVE.md bundle for a new Narrative doc. Writes
    the file with FLAT frontmatter (the format the bundle reader
    expects) + a body skeleton with the structured-fields headings.
    Does NOT apply — review/edit, then run `dna doc apply`.
    """
    import re as _re
    if not _re.match(r"^[a-z0-9][a-z0-9-]*$", slug):
        raise fail(
            f"slug {slug!r} must be kebab-case ([a-z0-9-]+, starting with [a-z0-9])"
        )

    # Bundle dir relative to repo root — examples/<scope>/.dna/<scope>/narratives/<slug>/
    from pathlib import Path
    cwd = Path.cwd()
    if (cwd / "examples").is_dir():
        base = cwd / "examples" / scope / ".dna" / scope / "narratives" / slug
    else:
        base = cwd / ".dna" / scope / "narratives" / slug
    if base.exists():
        raise fail(f"bundle dir already exists: {base}")
    base.mkdir(parents=True, exist_ok=True)
    marker = base / "NARRATIVE.md"

    title_val = title or slug.replace("-", " ").title()
    actor = _cli_actor()
    now_iso = _now_iso()
    template = f"""---
apiVersion: github.com/ruinosus/dna/sdlc/v1
kind: Narrative
name: {slug}
title: "{title_val}"
period_start: "{now_iso}"
period_end: "{now_iso}"
actor: {actor}
auto_generated: false
author_intent: {author_intent}
summary: "TL;DR: <preencher>"
covers_features: []
covers_epics: []
covers_stories: []
tags:
  - {author_intent}
paragraphs:
  - "<paragraph 1 — past-tense, what shipped>"
decisions: []
open_items: []
---

# {title_val}

<!-- Free-form markdown body. Studio prefers the structured fields above when
     they are present; this body is the fallback. -->
"""
    marker.write_text(template, encoding="utf-8")
    click.secho(f"CREATED {marker}", fg="green")
    click.echo("")
    click.echo("Edit the structured fields (paragraphs / decisions / open_items),")
    click.echo("then run:")
    click.echo("")
    click.echo(f"  dna doc apply --scope {scope} {marker.parent}")


# ---------------------------------------------------------------------------
# Narrative mutate helpers — append-only edits on existing Narrative docs.
# Implements the contract the `dna-demand-flow` skill assumes since v1:
# capturing decisions / paragraphs / open-items WITHOUT regenerating the
# whole Narrative through LLM. Each command is a thin wrapper around the
# `_append_to_narrative_array` helper.
# ---------------------------------------------------------------------------


def _append_to_narrative_array(
    scope: str, name: str, field: str, item: Any,
) -> None:
    """Read Narrative <name> in <scope>, append `item` to spec[field]
    list (creating it if absent), bump updated_at, write back.

    Fails loud if the Narrative doesn't exist — `dna-demand-flow`
    Step 5 calls these AFTER `journey close-cycle` has auto-created a
    cycle Narrative, so a missing target usually means a typo.
    """
    with open_session(scope) as s:
        existing = s.get_doc("Narrative", name)
        if existing is None:
            raise fail(
                f"Narrative/{name!r} not found in scope {scope!r}. "
                f"Use `dna doc list Narrative --scope {scope}` to find "
                f"the right slug, or close a cycle to create one auto."
            )
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        arr = list(spec.get(field) or [])
        arr.append(item)
        spec[field] = arr
        spec["updated_at"] = _now_iso()
        raw = _build_raw("Narrative", name, spec)
        s.run(s.kernel.write_document(scope, "Narrative", name, raw))


@narrative_group.command("add-decision")
@click.argument("name")
@click.option("--decision", required=True,
              help="1-sentence summary of WHAT was decided.")
@click.option("--reason", default=None,
              help="WHY — the tradeoff or driving constraint.")
@click.option("--trade-offs", "trade_offs", default=None,
              help="Optional: what we gave up to make this choice.")
@_scope_option
def cmd_narrative_add_decision(
    name: str, decision: str, reason: str | None,
    trade_offs: str | None, scope: str,
) -> None:
    """Append a structured decision to an existing Narrative. The
    decision goes into `spec.decisions[]` so Studio renders it in the
    yellow callout strip, not just in body markdown.

    Use this AT REFLECT TIME (or right after close-cycle) to capture
    the WHY of choices the cycle made.
    """
    item: dict[str, str] = {"summary": decision}
    if reason:
        item["reason"] = reason
    if trade_offs:
        item["trade_offs"] = trade_offs
    _append_to_narrative_array(scope, name, "decisions", item)
    click.secho(
        f"APPENDED decision to Narrative/{name}: {decision}",
        fg="green",
    )


@narrative_group.command("add-paragraph")
@click.argument("name")
@click.option("--text", required=True,
              help="Past-tense paragraph of what shipped (no bullets).")
@_scope_option
def cmd_narrative_add_paragraph(
    name: str, text: str, scope: str,
) -> None:
    """Append a paragraph to an existing Narrative. Stored in
    `spec.paragraphs[]` so Studio renders it as the lead block in
    order.

    Use this when shipping mid-cycle progress that deserves a line
    on the narrative without waiting for close-cycle synthesis.
    """
    _append_to_narrative_array(scope, name, "paragraphs", text)
    click.secho(
        f"APPENDED paragraph to Narrative/{name}",
        fg="green",
    )


@narrative_group.command("add-open-item")
@click.argument("name")
@click.option("--title", required=True,
              help="Short description of the open work item.")
@click.option("--owner", default=None,
              help="Who's on this (actor name).")
@click.option("--blocker", default=None,
              help="What's blocking it (1-liner).")
@_scope_option
def cmd_narrative_add_open_item(
    name: str, title: str, owner: str | None,
    blocker: str | None, scope: str,
) -> None:
    """Append an open work item to an existing Narrative. Surfaces in
    Studio's sidebar 'ainda em aberto' section.

    Use this when reflecting on a cycle that didn't fully close —
    something started but didn't ship, a follow-up the next cycle
    should pick up, a debt acknowledged.
    """
    item: dict[str, str] = {"title": title}
    if owner:
        item["owner"] = owner
    if blocker:
        item["blocker"] = blocker
    _append_to_narrative_array(scope, name, "open_items", item)
    click.secho(
        f"APPENDED open-item to Narrative/{name}: {title}",
        fg="green",
    )


# ---------------------------------------------------------------------------
# Journey ledger — moved to dna_cli/sdlc/journey.py (sdlc_cmd decomposition).
# Importing the module REGISTERS journey + demand on the shared root; the
# re-exports keep `from dna_cli.sdlc_cmd import X` working.
# ---------------------------------------------------------------------------

from dna_cli.sdlc.journey import (  # noqa: E402, F401 — re-exported for back-compat
    _DEMAND_STOPWORDS,
    _SKILL_HINTS_BY_PHASE,
    _build_cycle_seed,
    _capture_head_sha,
    _collect_closing_cycle,
    _entry_name,
    _list_entries_for_parent,
    _print_skill_hint,
    _recent_cycle_methodologies,
    _resolve_cycle_index,
    _slugify_demand_title,
    _smart_truncate,
    _split_first_sentence,
    _synthesize_narrative_from_cycle,
    _tdd_since_sha_for_parent,
    _write_feature_reflect_workflow_event,
    _write_plan_stub,
    cmd_demand,
    cmd_journey_close_cycle,
    cmd_journey_current,
    cmd_journey_enter,
    cmd_journey_list,
    cmd_journey_transition,
    journey_group,
)



# ─── Reference Kind — citation graph ──────────────────────────────────
# Moved to dna_cli/sdlc/reference.py (sdlc_cmd decomposition). Importing
# the module REGISTERS the group + cite/uncite on the shared root; the
# names re-exported here keep `from dna_cli.sdlc_cmd import X` working.

from dna_cli.sdlc.reference import (  # noqa: E402, F401 — re-exported for back-compat
    _CITE_DEFAULT_KIND,
    _split_cited,
    cmd_cite,
    cmd_reference_create,
    cmd_reference_list,
    cmd_reference_show,
    cmd_uncite,
    reference_group,
)


# ─────────────────────────────────────────────────────────────────
# Initiative group — Jira Align level (Theme/OKR → Initiative → Epic)
# 2026-05-26 — closes gap "no CLI for Initiative" reported during the
# design-system overhaul cycle.
# ─────────────────────────────────────────────────────────────────

VALID_INITIATIVE_STATUS = ("proposed", "in-flight", "done", "cancelled", "deferred")


@sdlc.group("initiative")
def initiative_group() -> None:
    """Initiative-level operations (1-2 quarter investment unit).

    Atlassian Jira Align hierarchy: Theme/OKR → **Initiative** → Epic →
    Feature → Story → Task. For roadmaps where Epic is granular too far
    for C-level strategy review.
    """


@initiative_group.command("create")
@click.argument("name")
@click.option("--title", required=True,
              help="Headline shown on roadmap / cards.")
@click.option("--desc", "description", required=True,
              help="Multi-paragraph description of the Initiative goal.")
@click.option("--owner", default=None,
              help="Actor name accountable (typically PM or Product Lead).")
@click.option("--status", type=click.Choice(VALID_INITIATIVE_STATUS),
              default="proposed")
@click.option("--horizon-start", "horizon_start", default=None,
              help="Start of horizon, ISO date (e.g. 2026-Q3 start).")
@click.option("--horizon-end", "horizon_end", default=None,
              help="End of horizon, ISO date.")
@click.option("--outcome-metric", "outcome_metric", default=None,
              help="The KR / metric this initiative is targeted at.")
@click.option("--target-value", "target_value", default=None,
              help="e.g. '+30% MAU' or '<200ms p95'.")
@click.option("--epic", "epics", multiple=True,
              help="Epic name this Initiative groups. Repeatable.")
@click.option("--theme-ref", "theme_ref", default=None,
              help="Optional Theme/OKR Objective slug (upstream OKR).")
@click.option("--priority", type=click.Choice(VALID_PRIORITIES), default=None,
              help="Board priority.")
@click.option("--business-value", "business_value", type=int, default=None,
              help="WSJF-style scalar 0-1000 — drives roadmap sort.")
@click.option("--labels", default=None, help="Comma-separated labels.")
@click.option("--reporter", default=None,
              help="Actor who filed it. Defaults to DNA_CLI_REPORTER or claude-code.")
@_scope_option
def cmd_initiative_create(
    name: str, title: str, description: str,
    owner: str | None, status: str,
    horizon_start: str | None, horizon_end: str | None,
    outcome_metric: str | None, target_value: str | None,
    epics: tuple[str, ...], theme_ref: str | None,
    priority: str | None, business_value: int | None,
    labels: str | None, reporter: str | None,
    scope: str,
) -> None:
    """Create a new Initiative.

    \b
    Example:
      dna sdlc initiative create i-design-system-overhaul-20260526 \\
        --title "DNA Studio Design System Overhaul" \\
        --desc "Theme Kind + 22 viewers + Cmd+K + cross-device sync." \\
        --status done \\
        --epic e-helix-extras --epic e-theme-system \\
        --outcome-metric "Studio usability score" \\
        --target-value "5 Features done · 26 Stories" \\
        --priority highest --business-value 850
    """
    spec: dict[str, Any] = {
        "title": title,
        "description": description,
        "status": status,
    }
    if owner:
        spec["owner"] = owner
    if horizon_start:
        spec["horizon_start"] = horizon_start
    if horizon_end:
        spec["horizon_end"] = horizon_end
    if outcome_metric:
        spec["outcome_metric"] = outcome_metric
    if target_value:
        spec["target_value"] = target_value
    if epics:
        spec["epics"] = list(epics)
    if theme_ref:
        spec["theme_ref"] = theme_ref
    if priority:
        spec["priority"] = priority
    if business_value is not None:
        spec["business_value"] = business_value
    labels_list = _csv(labels)
    if labels_list:
        spec["labels"] = labels_list
    if reporter:
        spec["reporter"] = reporter
    else:
        spec["reporter"] = os.environ.get("DNA_CLI_REPORTER", "claude-code")
    now = _now_iso()
    spec["created_at"] = now
    spec["updated_at"] = now

    raw = _build_raw("Initiative", name, spec)
    with open_session(scope) as s:
        s.run(s.kernel.write_document(scope, "Initiative", name, raw))
    click.secho(
        f"CREATED Initiative/{name} (status: {status}"
        + (f", epics: {len(epics)}" if epics else "")
        + ")",
        fg="green",
    )


@initiative_group.command("ship")
@click.argument("name")
@_scope_option
def cmd_initiative_ship(name: str, scope: str) -> None:
    """Mark an Initiative as done."""
    with open_session(scope) as s:
        doc = s.get_doc("Initiative", name)
        # i-063 — s.get_doc returns a _DocView (has `.spec`, not `.get`).
        if doc is None:
            raise fail(f"Initiative/{name!r} not found in scope {scope!r}")
        spec = dict(doc.spec) if doc.spec else {}
        spec["status"] = "done"
        spec["closed_at"] = _now_iso()
        spec["updated_at"] = spec["closed_at"]
        raw = _build_raw("Initiative", name, spec)
        s.run(s.kernel.write_document(scope, "Initiative", name, raw))
    click.secho(f"SHIPPED Initiative/{name}", fg="green", bold=True)


@initiative_group.command("cancel")
@click.argument("name")
@click.option("--reason", required=True, help="Short cancel reason (mandatory).")
@_scope_option
def cmd_initiative_cancel(name: str, reason: str, scope: str) -> None:
    """Cancel an Initiative with a reason."""
    with open_session(scope) as s:
        doc = s.get_doc("Initiative", name)
        spec = dict(doc.get("spec") or {})
        spec["status"] = "cancelled"
        spec["cancelled_reason"] = reason
        spec["updated_at"] = _now_iso()
        raw = _build_raw("Initiative", name, spec)
        s.run(s.kernel.write_document(scope, "Initiative", name, raw))
    click.secho(f"CANCELLED Initiative/{name} ({reason})", fg="yellow")


# ===========================================================================
# Work-item + artifact Kinds — Spike / Bug / Task / ADR / Spec / Plan
# ===========================================================================
#
# These Kinds have schemas (SdlcExtension) + Studio screens but had no CLI
# until now. They are all bundle Kinds (body markdown → spec.body →
# serialized to the marker file by write_document). `create` builds the
# spec (incl. optional body) + writes via _build_raw + write_document,
# exactly like Story; transitions reuse the generic _transition_workitem.

SPIKE_STATUSES = ("proposed", "in-progress", "answered", "abandoned")
BUG_STATUSES = (
    "open", "triaged", "in-progress", "resolved",
    "wont-fix", "duplicate", "regression",
)
TASK_STATUSES = ("todo", "in-progress", "done", "blocked", "cancelled")
BUG_SEVERITY = ("low", "medium", "high", "critical")
ARTIFACT_STATUSES = ("draft", "proposed", "accepted", "deprecated", "superseded")
# ADR omits "draft" — a decision is proposed, not drafted (matches ADRKind.schema).
ADR_STATUSES = ("proposed", "accepted", "deprecated", "superseded")


def _transition_workitem(
    scope: str, kind: str, name: str, new_status: str,
    *, extras: dict[str, Any] | None = None, **timeline_extras: Any,
) -> None:
    """Generic status transition for any work-item / artifact Kind.

    Mirror of ``_update_story_status`` but Kind-agnostic: read via
    ``s.get_doc(kind, name)`` (fail if missing), copy the spec, set
    ``status``, apply spec-level ``extras`` (closed_at, resolution, ...),
    stamp ``updated_at``, append a ``status_change`` timeline event with
    ``from``/``to`` + any ``timeline_extras``, write, and report.
    """
    with open_session(scope) as s:
        existing = s.get_doc(kind, name)
        if existing is None:
            raise fail(f"{kind} '{name}' not found in scope {scope!r}")
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        prev_status = spec.get("status")
        spec["status"] = new_status
        if extras:
            spec.update(extras)
        spec["updated_at"] = _now_iso()
        _append_timeline(
            spec, "status_change",
            **{"from": prev_status, "to": new_status, **timeline_extras},
        )
        raw = _build_raw(kind, name, spec)
        s.run(s.kernel.write_document(scope, kind, name, raw))
    click.secho(f"UPDATED {kind}/{name} → {new_status}", fg="green")


def _derive_title(title: str | None, source_text: str, fallback: str) -> str:
    """Title from --title, else first line of source_text (≤80 chars), else fallback."""
    if title:
        return title
    first_line = source_text.splitlines()[0] if source_text else ""
    return first_line[:80] if first_line else fallback


def _stamp_create(spec: dict[str, Any], status: str) -> None:
    """Stamp created_at/updated_at + the first status_change timeline event."""
    now = _now_iso()
    spec["created_at"] = now
    spec["updated_at"] = now
    _append_timeline(spec, "status_change", to=status)


# ---------------------------------------------------------------------------
# Spike
# ---------------------------------------------------------------------------

@sdlc.group("spike")
def spike_group() -> None:
    """Spike-level operations (time-boxed technical investigations)."""


@spike_group.command("create")
@click.argument("name")
@click.option("--question", "question_to_answer", required=True,
              help="The ONE question this spike answers (→ spec.question_to_answer).")
@click.option("--title", default=None,
              help="Short title. Derived from --question first line (≤80) when omitted.")
@click.option("--status", type=click.Choice(SPIKE_STATUSES), default="proposed")
@click.option("--feature", default=None, help="Parent Feature name.")
@click.option("--owner", default=None)
@click.option("--time-box", "time_box_hours", type=int, default=None,
              help="Time budget in hours (→ spec.time_box_hours).")
@click.option("--research-refs", "research_refs", default=None,
              help="Comma-separated Research names (→ spec.research_refs).")
@click.option("--references", default=None,
              help="Comma-separated Reference names (→ spec.references).")
@click.option("--follow-up-story", "follow_up_story", default=None,
              help="Story this spike hands off to (→ spec.follow_up_story).")
@click.option("--labels", default=None, help="Comma-separated labels.")
@click.option("--body", default=None, help="Markdown body (→ spec.body / SPIKE.md).")
@_scope_option
def cmd_spike_create(
    name: str, question_to_answer: str, title: str | None, status: str,
    feature: str | None, owner: str | None, time_box_hours: int | None,
    research_refs: str | None, references: str | None,
    follow_up_story: str | None, labels: str | None, body: str | None,
    scope: str,
) -> None:
    """Create a new Spike (time-boxed technical investigation)."""
    spec: dict[str, Any] = {
        "title": _derive_title(title, question_to_answer, name),
        "question_to_answer": question_to_answer,
        "status": status,
    }
    if feature:
        spec["feature"] = feature
    if owner:
        spec["owner"] = owner
    if time_box_hours is not None:
        spec["time_box_hours"] = time_box_hours
    research_list = _csv(research_refs)
    if research_list:
        spec["research_refs"] = research_list
    references_list = _csv(references)
    if references_list:
        spec["references"] = references_list
    if follow_up_story:
        spec["follow_up_story"] = follow_up_story
    labels_list = _csv(labels)
    if labels_list:
        spec["labels"] = labels_list
    if body:
        spec["body"] = body
    _stamp_create(spec, status)
    raw = _build_raw("Spike", name, spec)
    with open_session(scope) as s:
        s.run(s.kernel.write_document(scope, "Spike", name, raw))
    click.secho(f"CREATED Spike/{name} (status: {status})", fg="green")


@spike_group.command("start")
@click.argument("name")
@_scope_option
def cmd_spike_start(name: str, scope: str) -> None:
    """Mark Spike status: in-progress."""
    _transition_workitem(scope, "Spike", name, "in-progress")
    # Anchor beat (i-126): same live FOCUS pointer `story start` posts —
    # a started Spike is anchored work too. Best-effort, after the transition
    # (a failed transition raises before this line).
    _post_start_beat(scope, name, kind="Spike")


@spike_group.command("answer")
@click.argument("name")
@click.option("--findings", default=None, help="What the spike found (→ spec.findings).")
@click.option("--recommendation", default=None,
              help="Recommended next step (→ spec.recommendation).")
@click.option("--follow-up-story", "follow_up_story", default=None,
              help="Story this spike hands off to (→ spec.follow_up_story).")
@_scope_option
def cmd_spike_answer(
    name: str, findings: str | None, recommendation: str | None,
    follow_up_story: str | None, scope: str,
) -> None:
    """Mark Spike status: answered; stamp completed_at + findings/recommendation."""
    extras: dict[str, Any] = {"completed_at": _now_iso()}
    if findings:
        extras["findings"] = findings
    if recommendation:
        extras["recommendation"] = recommendation
    if follow_up_story:
        extras["follow_up_story"] = follow_up_story
    _transition_workitem(scope, "Spike", name, "answered", extras=extras)
    _post_done_beat(scope, "Spike", name)


@spike_group.command("abandon")
@click.argument("name")
@_scope_option
def cmd_spike_abandon(name: str, scope: str) -> None:
    """Mark Spike status: abandoned."""
    _transition_workitem(scope, "Spike", name, "abandoned")
    _post_done_beat(scope, "Spike", name)


@spike_group.command("comment")
@click.argument("name")
@click.option("--body", required=True, help="The comment / finding / decision text.")
@click.option("--type", "event_type", default=None,
              type=click.Choice(("comment", "decision")),
              help="Defaults to 'comment'; decision-shaped bodies auto-promote.")
@_scope_option
def cmd_spike_comment(
    name: str, body: str, event_type: str | None, scope: str,
) -> None:
    """Append a finding / decision to a Spike timeline without changing status.

    Mirrors `story comment` — Spikes accrue findings + decisions over their
    investigation, and the running trail belongs on the timeline (the FOCUS
    feed + audit), not only in the final `answer`.
    """
    if event_type is None:
        event_type = "decision" if _looks_like_decision(body) else "comment"
    with open_session(scope) as s:
        existing = s.get_doc("Spike", name)
        if existing is None:
            raise fail(f"Spike '{name}' not found in scope {scope!r}")
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        spec["timeline"] = list(spec.get("timeline") or [])
        _append_timeline(spec, event_type, summary=body)
        raw = _build_raw("Spike", name, spec)
        s.run(s.kernel.write_document(scope, "Spike", name, raw))
    click.secho(f"COMMENTED Spike/{name} ({event_type})", fg="green")


# Map each --flag to the spec field it feeds + whether it's a list (append)
# or scalar (set). The schema already declares these refs (dep_filters);
# this just exposes them on the CLI so outputs never sit in limbo.
_SPIKE_LINK_LIST_FIELDS = {
    "research": "research_refs",
    "artifact": "html_artifacts",
    "reference": "references",
    "related_spike": "related_spikes",
}
_SPIKE_LINK_SCALAR_FIELDS = {
    "adr": "follow_up_adr",
    "spec": "follow_up_spec",
    "follow_up_story": "follow_up_story",
    "feature": "feature",
}


@spike_group.command("link")
@click.argument("name")
@click.option("--adr", default=None, help="ADR this spike hands off to (→ follow_up_adr).")
@click.option("--spec", default=None, help="Spec this spike produced (→ follow_up_spec).")
@click.option("--research", default=None, help="Research doc to attach (→ research_refs[]).")
@click.option("--artifact", default=None, help="HtmlArtifact to attach (→ html_artifacts[]).")
@click.option("--reference", default=None, help="Reference to attach (→ references[]).")
@click.option("--follow-up-story", "follow_up_story", default=None,
              help="Story this spike hands off to (→ follow_up_story).")
@click.option("--feature", default=None, help="Parent Feature (→ feature).")
@click.option("--related-spike", "related_spike", default=None,
              help="Related Spike (→ related_spikes[]).")
@_scope_option
def cmd_spike_link(
    name: str, adr: str | None, spec: str | None, research: str | None,
    artifact: str | None, reference: str | None, follow_up_story: str | None,
    feature: str | None, related_spike: str | None, scope: str,
) -> None:
    """Attach a Spike's outputs (ADR/Research/HtmlArtifact/Reference) + handoffs
    (Story/Feature) so they show up in FOCUS OUTPUTS and the audit graph — never
    in limbo. List fields append + dedup; scalar fields are set. Idempotent.
    """
    flags = {
        "adr": adr, "spec": spec, "research": research, "artifact": artifact,
        "reference": reference, "follow_up_story": follow_up_story,
        "feature": feature, "related_spike": related_spike,
    }
    if not any(flags.values()):
        raise fail("Nothing to link — pass at least one of "
                   "--adr/--spec/--research/--artifact/--reference/"
                   "--follow-up-story/--feature/--related-spike.")
    with open_session(scope) as s:
        existing = s.get_doc("Spike", name)
        if existing is None:
            raise fail(f"Spike '{name}' not found in scope {scope!r}")
        doc_spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        linked: list[str] = []
        for flag, field in _SPIKE_LINK_LIST_FIELDS.items():
            val = flags[flag]
            if val:
                arr = list(doc_spec.get(field) or [])
                if val not in arr:
                    arr.append(val)
                    linked.append(f"{field}+={val}")
                doc_spec[field] = arr
        for flag, field in _SPIKE_LINK_SCALAR_FIELDS.items():
            val = flags[flag]
            if val:
                doc_spec[field] = val
                linked.append(f"{field}={val}")
        raw = _build_raw("Spike", name, doc_spec)
        s.run(s.kernel.write_document(scope, "Spike", name, raw))
    click.secho(f"LINKED Spike/{name}: {', '.join(linked) or '(no change)'}", fg="green")


# ---------------------------------------------------------------------------
# Bug
# ---------------------------------------------------------------------------

@sdlc.group("bug")
def bug_group() -> None:
    """Bug-level operations (factual defects with severity)."""


@bug_group.command("create")
@click.argument("name")
@click.option("--desc", "description", required=True,
              help="One-line description (→ spec.description; derives title).")
@click.option("--severity", type=click.Choice(BUG_SEVERITY), default="medium")
@click.option("--status", type=click.Choice(BUG_STATUSES), default="open")
@click.option("--owner", default=None)
@click.option("--related-feature", "related_feature", default=None,
              help="Feature name (→ spec.related_feature).")
@click.option("--steps", "steps_to_reproduce", default=None,
              help="Comma-separated repro steps (→ spec.repro_steps).")
@click.option("--labels", default=None, help="Comma-separated labels.")
@click.option("--body", default=None, help="Markdown body (→ spec.body / BUG.md).")
@_scope_option
def cmd_bug_create(
    name: str, description: str, severity: str, status: str,
    owner: str | None, related_feature: str | None,
    steps_to_reproduce: str | None, labels: str | None, body: str | None,
    scope: str,
) -> None:
    """File a new Bug."""
    spec: dict[str, Any] = {
        "title": _derive_title(None, description, name),
        "description": description,
        "severity": severity,
        "status": status,
    }
    if owner:
        spec["owner"] = owner
    if related_feature:
        spec["related_feature"] = related_feature
    steps_list = _csv(steps_to_reproduce)
    if steps_list:
        spec["repro_steps"] = steps_list
    labels_list = _csv(labels)
    if labels_list:
        spec["labels"] = labels_list
    if body:
        spec["body"] = body
    _stamp_create(spec, status)
    raw = _build_raw("Bug", name, spec)
    with open_session(scope) as s:
        s.run(s.kernel.write_document(scope, "Bug", name, raw))
    click.secho(f"CREATED Bug/{name} ({severity}/{status})", fg="green")


@bug_group.command("triage")
@click.argument("name")
@_scope_option
def cmd_bug_triage(name: str, scope: str) -> None:
    """Mark Bug status: triaged."""
    _transition_workitem(scope, "Bug", name, "triaged")


@bug_group.command("start")
@click.argument("name")
@_scope_option
def cmd_bug_start(name: str, scope: str) -> None:
    """Mark Bug status: in-progress."""
    _transition_workitem(scope, "Bug", name, "in-progress")
    _post_start_beat(scope, name, kind="Bug")


@bug_group.command("resolve")
@click.argument("name")
@click.option("--resolution", default=None, help="How was it resolved? (timeline summary).")
@_scope_option
def cmd_bug_resolve(name: str, resolution: str | None, scope: str) -> None:
    """Mark Bug status: resolved; stamp closed_at."""
    _transition_workitem(
        scope, "Bug", name, "resolved",
        extras={"closed_at": _now_iso()}, summary=resolution,
    )


@bug_group.command("wontfix")
@click.argument("name")
@_scope_option
def cmd_bug_wontfix(name: str, scope: str) -> None:
    """Mark Bug status: wont-fix."""
    _transition_workitem(scope, "Bug", name, "wont-fix")


@bug_group.command("regress")
@click.argument("name")
@_scope_option
def cmd_bug_regress(name: str, scope: str) -> None:
    """Mark Bug status: regression (reopened defect)."""
    _transition_workitem(scope, "Bug", name, "regression")


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

@sdlc.group("task")
def task_group() -> None:
    """Task-level operations (granular sub-Story work items)."""


@task_group.command("create")
@click.argument("name")
@click.option("--desc", "description", required=True,
              help="One-line description (→ spec.description; derives title).")
@click.option("--status", type=click.Choice(TASK_STATUSES), default="todo")
@click.option("--owner", default=None)
@click.option("--estimate", "estimate_hours", type=int, default=None,
              help="Estimated hours (→ spec.estimate_hours).")
@click.option("--feature", default=None, help="Parent Feature name.")
@click.option("--labels", default=None, help="Comma-separated labels.")
@click.option("--body", default=None, help="Markdown body (→ spec.body / TASK.md).")
@_scope_option
def cmd_task_create(
    name: str, description: str, status: str, owner: str | None,
    estimate_hours: int | None, feature: str | None,
    labels: str | None, body: str | None, scope: str,
) -> None:
    """Create a new Task."""
    spec: dict[str, Any] = {
        "title": _derive_title(None, description, name),
        "description": description,
        "status": status,
    }
    if owner:
        spec["owner"] = owner
    if estimate_hours is not None:
        spec["estimate_hours"] = estimate_hours
    if feature:
        spec["feature"] = feature
    labels_list = _csv(labels)
    if labels_list:
        spec["labels"] = labels_list
    if body:
        spec["body"] = body
    _stamp_create(spec, status)
    raw = _build_raw("Task", name, spec)
    with open_session(scope) as s:
        s.run(s.kernel.write_document(scope, "Task", name, raw))
    click.secho(f"CREATED Task/{name} (status: {status})", fg="green")


@task_group.command("start")
@click.argument("name")
@_scope_option
def cmd_task_start(name: str, scope: str) -> None:
    """Mark Task status: in-progress."""
    _transition_workitem(scope, "Task", name, "in-progress")
    _post_start_beat(scope, name, kind="Task")


@task_group.command("done")
@click.argument("name")
@_scope_option
def cmd_task_done(name: str, scope: str) -> None:
    """Mark Task status: done; stamp closed_at."""
    _transition_workitem(
        scope, "Task", name, "done", extras={"closed_at": _now_iso()},
    )


@task_group.command("block")
@click.argument("name")
@click.option("--reason", required=True, help="Why is it blocked? (→ spec.blocked_reason).")
@_scope_option
def cmd_task_block(name: str, reason: str, scope: str) -> None:
    """Mark Task status: blocked, with a reason."""
    _transition_workitem(
        scope, "Task", name, "blocked",
        extras={"blocked_reason": reason}, summary=reason,
    )


@task_group.command("cancel")
@click.argument("name")
@_scope_option
def cmd_task_cancel(name: str, scope: str) -> None:
    """Mark Task status: cancelled."""
    _transition_workitem(scope, "Task", name, "cancelled")


# ---------------------------------------------------------------------------
# ADR — Architecture Decision Record
# ---------------------------------------------------------------------------

@sdlc.group("adr")
def adr_group() -> None:
    """ADR-level operations (Architecture Decision Records)."""


@adr_group.command("create")
@click.argument("name")
@click.option("--title", required=True, help="Decision headline (→ spec.title).")
@click.option("--context", required=True, help="WHY we needed to decide (→ spec.context).")
@click.option("--decision", required=True, help="WHAT we decided (→ spec.decision).")
@click.option("--status", type=click.Choice(ADR_STATUSES), default="proposed")
@click.option("--consequences", default=None,
              help="Trade-offs that follow (→ spec.consequences).")
@click.option("--body", default=None, help="Markdown body (→ spec.body / ADR.md).")
@_scope_option
def cmd_adr_create(
    name: str, title: str, context: str, decision: str, status: str,
    consequences: str | None, body: str | None, scope: str,
) -> None:
    """Create a new ADR."""
    spec: dict[str, Any] = {
        "title": title,
        "status": status,
        "context": context,
        "decision": decision,
    }
    if consequences:
        spec["consequences"] = consequences
    if body:
        spec["body"] = body
    _stamp_create(spec, status)
    raw = _build_raw("ADR", name, spec)
    with open_session(scope) as s:
        s.run(s.kernel.write_document(scope, "ADR", name, raw))
    click.secho(f"CREATED ADR/{name} (status: {status})", fg="green")


@adr_group.command("propose")
@click.argument("name")
@_scope_option
def cmd_adr_propose(name: str, scope: str) -> None:
    """Mark ADR status: proposed."""
    _transition_workitem(scope, "ADR", name, "proposed")


@adr_group.command("accept")
@click.argument("name")
@_scope_option
def cmd_adr_accept(name: str, scope: str) -> None:
    """Mark ADR status: accepted; stamp accepted_at."""
    _transition_workitem(
        scope, "ADR", name, "accepted", extras={"accepted_at": _now_iso()},
    )


@adr_group.command("deprecate")
@click.argument("name")
@_scope_option
def cmd_adr_deprecate(name: str, scope: str) -> None:
    """Mark ADR status: deprecated."""
    _transition_workitem(scope, "ADR", name, "deprecated")


@adr_group.command("supersede")
@click.argument("name")
@click.option("--by", "superseded_by", required=True,
              help="ADR name that supersedes this one (→ spec.superseded_by).")
@_scope_option
def cmd_adr_supersede(name: str, superseded_by: str, scope: str) -> None:
    """Mark ADR status: superseded by another ADR."""
    _transition_workitem(
        scope, "ADR", name, "superseded",
        extras={"superseded_by": superseded_by}, superseded_by=superseded_by,
    )


# ---------------------------------------------------------------------------
# Spec + Plan (same artifact shape + transitions)
# ---------------------------------------------------------------------------

def _make_artifact_group(kind: str, group_name: str, help_text: str):
    """Build a Spec/Plan-style group: create + propose/accept/deprecate/supersede.

    Spec and Plan share an identical CLI surface (title/date/status/desc/body
    + the four ARTIFACT_STATUSES transitions), so the group + its commands are
    generated from one factory rather than copy-pasted. Each group is a
    hand-registered click.Group — no metaclass, just a small builder that keeps
    the two parallel surfaces DRY without hiding the command idiom.
    """

    @sdlc.group(group_name, help=help_text)
    def _group() -> None:
        pass

    @_group.command("create")
    @click.argument("name")
    @click.option("--title", required=True, help="Title (→ spec.title).")
    @click.option("--date", default=None,
                  help="Date (ISO-8601; → spec.date). Defaults to now.")
    @click.option("--status", type=click.Choice(ARTIFACT_STATUSES), default="draft")
    @click.option("--desc", "description", default=None,
                  help="Short description (→ spec.description).")
    @click.option("--body", default=None,
                  help=f"Markdown body (→ spec.body / {kind.upper()}.md).")
    @_scope_option
    def _create(
        name: str, title: str, date: str | None, status: str,
        description: str | None, body: str | None, scope: str,
    ) -> None:
        spec: dict[str, Any] = {
            "title": title,
            "date": date or _now_iso(),
            "status": status,
        }
        if description:
            spec["description"] = description
        if body:
            spec["body"] = body
        _stamp_create(spec, status)
        raw = _build_raw(kind, name, spec)
        with open_session(scope) as s:
            s.run(s.kernel.write_document(scope, kind, name, raw))
        click.secho(f"CREATED {kind}/{name} (status: {status})", fg="green")

    _create.__doc__ = f"Create a new {kind}."

    @_group.command("propose")
    @click.argument("name")
    @_scope_option
    def _propose(name: str, scope: str) -> None:
        _transition_workitem(scope, kind, name, "proposed")

    _propose.__doc__ = f"Mark {kind} status: proposed."

    @_group.command("accept")
    @click.argument("name")
    @_scope_option
    def _accept(name: str, scope: str) -> None:
        _transition_workitem(
            scope, kind, name, "accepted", extras={"accepted_at": _now_iso()},
        )

    _accept.__doc__ = f"Mark {kind} status: accepted; stamp accepted_at."

    @_group.command("deprecate")
    @click.argument("name")
    @_scope_option
    def _deprecate(name: str, scope: str) -> None:
        _transition_workitem(scope, kind, name, "deprecated")

    _deprecate.__doc__ = f"Mark {kind} status: deprecated."

    @_group.command("supersede")
    @click.argument("name")
    @click.option("--by", "superseded_by", required=True,
                  help=f"{kind} name that supersedes this one (→ spec.superseded_by).")
    @_scope_option
    def _supersede(name: str, superseded_by: str, scope: str) -> None:
        _transition_workitem(
            scope, kind, name, "superseded",
            extras={"superseded_by": superseded_by}, superseded_by=superseded_by,
        )

    _supersede.__doc__ = f"Mark {kind} status: superseded."

    return _group


spec_group = _make_artifact_group(
    "Spec", "spec", "Spec-level operations (design / spec documents).",
)
# NB: Plan does NOT use _make_artifact_group — the richer `@sdlc.group("plan")`
# below (with the story-gate-aware `create`, --plan-file, etc.) is the canonical
# plan group. A factory call here would be shadowed by it (i-037 name collision:
# `plan accept` silently vanished). The ADR lifecycle is added to it directly.


# ---------------------------------------------------------------------------
# Issue — start transition (Tier 3, mirrors triage)
# ---------------------------------------------------------------------------

@issue_group.command("start")
@click.argument("name")
@_scope_option
def cmd_issue_start(name: str, scope: str) -> None:
    """Mark Issue status: in-progress."""
    with open_session(scope) as s:
        existing = s.get_doc("Issue", name)
        if existing is None:
            raise fail(f"Issue '{name}' not found")
        spec = dict(existing.spec)
        prev = spec.get("status")
        spec["status"] = "in-progress"
        _append_timeline(spec, "status_change", **{"from": prev, "to": "in-progress"})
        raw = _build_raw("Issue", name, spec)
        s.run(s.kernel.write_document(scope, "Issue", name, raw))
    # Anchor beat (i-126): same live FOCUS pointer `story start` posts — a
    # started Issue is anchored work too. Best-effort, never breaks the start.
    _post_start_beat(scope, name, kind="Issue")
    click.secho(f"STARTED {name}", fg="green")


# ── plan group (s-story-start-plan-gate) ────────────────────────────
# First-class Plan authoring. Plans descend from a Spec (`spec_ref`) and/or
# attack a Story (`story_ref`). Linking a Plan to a Story lights up that
# Story's derived `plan` phase (s-journey-derived).
@sdlc.group("plan")
def plan_group() -> None:
    """Manage Plan docs (implementation plans)."""


@plan_group.command("create")
@click.argument("name")
@click.option("--story", "story_ref", default=None,
              help="Story this plan attacks (slug or Story/<slug>) — lights up its `plan` phase.")
@click.option("--spec", "spec_ref", default=None, help="Parent Spec (spec_ref).")
@click.option("--title", required=True, help="Human title (→ spec.title).")
@click.option("--approach", "--body", "body", default=None,
              help="Plan body / approach (markdown, stored in PLAN.md).")
@click.option("--body-file", "body_file", default=None,
              help="Lê o body de um markdown (plano RICO: superpowers/bmad/à mão). "
                   "Mutuamente exclusivo com --body.")
@click.option("--methodology", "methodology", default=None,
              type=click.Choice(VALID_JOURNEY_METHODOLOGIES),
              help="Metodologia que produziu o plano (carimba spec.methodology). Opt-in.")
@click.option("--status", type=click.Choice(ARTIFACT_STATUSES), default="accepted")
@_scope_option
def cmd_plan_create(
    name: str, story_ref: str | None, spec_ref: str | None,
    title: str, body: str | None, body_file: str | None,
    methodology: str | None, status: str, scope: str,
) -> None:
    """Create a Plan doc (optionally linked to a Story and/or Spec).

    Body source: inline ``--body "..."`` for a quick plan, or
    ``--body-file <plano.md>`` to pour a rich markdown plan (e.g. the output
    of the superpowers writing-plans skill) into the Plan body. ``--methodology``
    records which method produced it — opt-in, methodology-agnostic.
    """
    if body and body_file:
        raise fail("--body e --body-file são mutuamente exclusivos — escolha um.")
    if body_file:
        body = _read_body_file(body_file)
    now = _now_iso()
    spec: dict[str, Any] = {
        "title": title,
        "date": now[:10],
        "status": status,
        "created_at": now,
        "updated_at": now,
    }
    if story_ref:
        spec["story_ref"] = story_ref.split("/", 1)[1] if "/" in story_ref else story_ref
        spec["journey_phase"] = "plan"
    if spec_ref:
        spec["spec_ref"] = spec_ref
    if methodology:
        spec["methodology"] = methodology
    if body:
        spec["body"] = body
    # Stamp the first timeline event (i-037) — consistent with the other
    # artifact Kinds; the derived journey + boards read timeline[0].
    _append_timeline(spec, "status_change", **{"from": None, "to": status})
    with open_session(scope) as s:
        raw = _build_raw("Plan", name, spec)
        s.run(s.kernel.write_document(scope, "Plan", name, raw))
    click.secho(f"CREATED Plan/{name} in scope {scope}", fg="green")
    if spec.get("story_ref"):
        click.echo(f"  → lights up the `plan` phase of Story/{spec['story_ref']}")


# ADR lifecycle for Plan (i-037) — Plan is an ARTIFACT_STATUSES Kind
# (draft/proposed/accepted/deprecated/superseded). These mirror the Spec
# factory transitions; they live here because the canonical plan group is the
# rich `@sdlc.group("plan")` above, not the (shadowed) _make_artifact_group one.
@plan_group.command("accept")
@click.argument("name")
@_scope_option
def cmd_plan_accept(name: str, scope: str) -> None:
    """Mark Plan status: accepted; stamp accepted_at."""
    _transition_workitem(scope, "Plan", name, "accepted", extras={"accepted_at": _now_iso()})


@plan_group.command("propose")
@click.argument("name")
@_scope_option
def cmd_plan_propose(name: str, scope: str) -> None:
    """Mark Plan status: proposed."""
    _transition_workitem(scope, "Plan", name, "proposed")


@plan_group.command("deprecate")
@click.argument("name")
@_scope_option
def cmd_plan_deprecate(name: str, scope: str) -> None:
    """Mark Plan status: deprecated."""
    _transition_workitem(scope, "Plan", name, "deprecated")


@plan_group.command("supersede")
@click.argument("name")
@click.option("--by", "superseded_by", required=True,
              help="Plan name that supersedes this one (→ spec.superseded_by).")
@_scope_option
def cmd_plan_supersede(name: str, superseded_by: str, scope: str) -> None:
    """Mark Plan status: superseded."""
    _transition_workitem(
        scope, "Plan", name, "superseded",
        extras={"superseded_by": superseded_by}, superseded_by=superseded_by,
    )


# ── produces group (s-produces-cli) ─────────────────────────────────
# A work item is a HUB: attach artifacts of ANY Kind via spec.produces[].
# resolve_work_item_outputs (sdk-py) unifies produces[] ∪ legacy back-refs;
# the derived journey + FOCUS panel read the same.
_WORK_ITEM_KINDS = {"Story", "Spike", "Feature", "Epic", "Issue"}
# Kinds that can AUTHOR an output via `produces add`. Superset of work items:
# an ADR (a decision record) legitimately produces its decision-visualisation
# HtmlArtifact — the gallery buckets ADR-produced artifacts as "decisões".
_PRODUCER_KINDS = _WORK_ITEM_KINDS | {"ADR"}


def _split_ref(ref: str) -> tuple[str, str]:
    """'Kind/name' → ('Kind', 'name'). Tolerates names containing slashes."""
    if "/" not in ref:
        raise fail(f"esperado 'Kind/name', recebi {ref!r}")
    kind, name = ref.split("/", 1)
    return kind, name


def _append_produces(spec: dict[str, Any], kind: str, name: str, role: str | None = None) -> dict[str, Any]:
    """Append {kind,name,role?,at} to spec.produces[], deduped by (kind,name).
    Backfills role on an existing entry. Mutates + returns spec."""
    produces = spec.get("produces")
    if not isinstance(produces, list):
        produces = []
    for p in produces:
        if isinstance(p, dict) and p.get("kind") == kind and p.get("name") == name:
            if role and not p.get("role"):
                p["role"] = role
            spec["produces"] = produces
            return spec
    entry: dict[str, Any] = {"kind": kind, "name": name}
    if role:
        entry["role"] = role
    entry["at"] = _now_iso()
    produces.append(entry)
    spec["produces"] = produces
    return spec


def _remove_produces(spec: dict[str, Any], kind: str, name: str) -> dict[str, Any]:
    """Remove the (kind,name) entry from spec.produces[] (no-op if absent)."""
    produces = spec.get("produces")
    if isinstance(produces, list):
        spec["produces"] = [
            p for p in produces
            if not (isinstance(p, dict) and p.get("kind") == kind and p.get("name") == name)
        ]
    return spec


@sdlc.group("produces")
def produces_group() -> None:
    """Attach/list artifacts a work item produced (any Kind — the hub)."""


@produces_group.command("add")
@click.argument("work_item")
@click.argument("artifact")
@click.option("--role", default=None, help="Role hint (visual-spec, plan, investigation, ...).")
@_scope_option
def cmd_produces_add(work_item: str, artifact: str, role: str | None, scope: str) -> None:
    """Attach an artifact: dna sdlc produces add <WiKind>/<wi> <Kind>/<name>."""
    wi_kind, wi_name = _split_ref(work_item)
    art_kind, art_name = _split_ref(artifact)
    if wi_kind not in _PRODUCER_KINDS:
        raise fail(f"{wi_kind} não pode produzir outputs ({', '.join(sorted(_PRODUCER_KINDS))}).")
    with open_session(scope) as s:
        existing = s.get_doc(wi_kind, wi_name)
        if existing is None:
            raise fail(f"{wi_kind}/{wi_name} não encontrado em {scope!r}.")
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        _append_produces(spec, art_kind, art_name, role)
        s.run(s.kernel.write_document(scope, wi_kind, wi_name, _build_raw(wi_kind, wi_name, spec)))
    click.secho(f"{wi_kind}/{wi_name} produces → {art_kind}/{art_name}", fg="green")


@produces_group.command("rm")
@click.argument("work_item")
@click.argument("artifact")
@_scope_option
def cmd_produces_rm(work_item: str, artifact: str, scope: str) -> None:
    """Detach an artifact from a work item's produces[]."""
    wi_kind, wi_name = _split_ref(work_item)
    art_kind, art_name = _split_ref(artifact)
    with open_session(scope) as s:
        existing = s.get_doc(wi_kind, wi_name)
        if existing is None:
            raise fail(f"{wi_kind}/{wi_name} não encontrado em {scope!r}.")
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
        _remove_produces(spec, art_kind, art_name)
        s.run(s.kernel.write_document(scope, wi_kind, wi_name, _build_raw(wi_kind, wi_name, spec)))
    click.secho(f"{wi_kind}/{wi_name} ✕ {art_kind}/{art_name}", fg="yellow")


@produces_group.command("list")
@click.argument("work_item")
@click.option("--json", "as_json", is_flag=True)
@_scope_option
def cmd_produces_list(work_item: str, as_json: bool, scope: str) -> None:
    """Resolved outputs of a work item (produces[] ∪ legacy back-refs)."""
    from dna.extensions.sdlc.work_item_outputs import resolve_work_item_outputs
    wi_kind, wi_name = _split_ref(work_item)
    with open_session(scope) as s:
        existing = s.get_doc(wi_kind, wi_name)
        if existing is None:
            raise fail(f"{wi_kind}/{wi_name} não encontrado em {scope!r}.")
        spec = dict(existing.spec) if isinstance(existing.spec, dict) else {}
    outputs = resolve_work_item_outputs(wi_name, spec)
    if as_json:
        print_json(outputs)
        return
    if not outputs:
        click.secho(f"({wi_kind}/{wi_name} sem outputs)", fg="yellow")
        return
    click.secho(f"🧭 {wi_kind}/{wi_name} produces ({len(outputs)})", bold=True)
    for o in outputs:
        role = f" · {o['role']}" if o.get("role") else ""
        src = "" if o["source"] == "produces" else " (legacy)"
        click.echo(f"  {o['kind']:14} {o['name']}{role}{src}")


# ── artifact group (s-dx-html-artifact-kind) ─────────────────────────
# An HtmlArtifact stores an HTML page as a first-class, linkable work-item
# output (a design doc / roteiro / report). Bundle: ARTIFACT.html (verbatim
# HTML) + artifact.json (title/description/source/created_at).
@sdlc.group("artifact")
def artifact_group() -> None:
    """Manage HtmlArtifacts — HTML pages as first-class work-item outputs."""


@artifact_group.command("create")
@click.argument("name")
@click.option("--from", "from_file", required=True,
              type=click.Path(exists=True, dir_okay=False),
              help="Path to the .html file to store (read byte-faithful).")
@click.option("--title", default=None, help="Human title for the artifact.")
@click.option("--description", default=None, help="Short description (promoted to metadata).")
@click.option("--source", default=None, help="Provenance/context (e.g. 'design doc do épico e-dna-dx').")
@click.option("--published-url", "published_url", default=None,
              help="Canonical hosted URL (e.g. a claude.ai artifact link) — the "
                   "gallery renders it as a clickable link.")
@_scope_option
def cmd_artifact_create(
    name: str, from_file: str, title: str | None,
    description: str | None, source: str | None,
    published_url: str | None, scope: str,
) -> None:
    """Create an HtmlArtifact from an HTML file: dna sdlc artifact create <name> --from x.html."""
    import datetime as _dt
    from pathlib import Path as _Path

    html = _Path(from_file).read_text(encoding="utf-8")
    artifact_json: dict[str, Any] = {}
    if title is not None:
        artifact_json["title"] = title
    if description is not None:
        artifact_json["description"] = description
    if source is not None:
        artifact_json["source"] = source
    if published_url is not None:
        artifact_json["published_url"] = published_url
    artifact_json["created_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()

    spec: dict[str, Any] = {"html": html, "artifact_json": artifact_json}
    raw = _build_raw("HtmlArtifact", name, spec)
    if description:
        raw["metadata"]["description"] = description
    with open_session(scope) as s:
        s.run(s.kernel.write_document(scope, "HtmlArtifact", name, raw))
    click.secho(f"CREATED HtmlArtifact/{name} ({len(html)} bytes)", fg="green")
    click.secho(
        f"  link it: dna sdlc produces add <WiKind>/<wi> HtmlArtifact/{name}",
        fg="cyan",
    )


@artifact_group.command("list")
@click.option("--json", "as_json", is_flag=True)
@_scope_option
def cmd_artifact_list(as_json: bool, scope: str) -> None:
    """List HtmlArtifacts in a scope."""
    async def _collect(kernel) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        async for raw in kernel.query(scope, "HtmlArtifact"):
            meta = raw.get("metadata") if isinstance(raw, dict) else {}
            spec = raw.get("spec") if isinstance(raw, dict) else {}
            spec = spec if isinstance(spec, dict) else {}
            aj = spec.get("artifact_json") or {}
            aj = aj if isinstance(aj, dict) else {}
            out.append({
                "name": (meta or {}).get("name", "?"),
                "title": aj.get("title"),
                "source": aj.get("source"),
                "html_bytes": len(spec.get("html") or ""),
            })
        return out

    with open_session(scope) as s:
        rows = s.run(_collect(s.kernel))
    if as_json:
        print_json(rows)
        return
    if not rows:
        click.secho(f"(no HtmlArtifacts in {scope!r})", fg="yellow")
        return
    click.secho(f"📄 HtmlArtifacts in {scope} ({len(rows)})", bold=True)
    for r in rows:
        t = f" · {r['title']}" if r.get("title") else ""
        click.echo(f"  {r['name']:32} {r['html_bytes']:>7}B{t}")


@artifact_group.command("show")
@click.argument("name")
@click.option("--html", "dump_html", is_flag=True, help="Print the raw HTML to stdout.")
@_scope_option
def cmd_artifact_show(name: str, dump_html: bool, scope: str) -> None:
    """Show an HtmlArtifact's metadata (or --html to dump the raw HTML)."""
    with open_session(scope) as s:
        doc = s.get_doc("HtmlArtifact", name)
    if doc is None:
        raise fail(f"HtmlArtifact/{name} não encontrado em {scope!r}.")
    spec = doc.spec if isinstance(doc.spec, dict) else {}
    if dump_html:
        click.echo(spec.get("html") or "")
        return
    aj = spec.get("artifact_json") or {}
    click.secho(f"HtmlArtifact: {name}", bold=True)
    if aj.get("title"):
        click.echo(f"  title:      {aj['title']}")
    if aj.get("description"):
        click.echo(f"  description: {aj['description']}")
    if aj.get("source"):
        click.echo(f"  source:     {aj['source']}")
    if aj.get("published_url"):
        click.echo(f"  published:  {aj['published_url']}")
    if aj.get("created_at"):
        click.echo(f"  created_at: {aj['created_at']}")
    click.echo(f"  html_bytes: {len(spec.get('html') or '')}")


# ── Changelog — release notes per scope (s-semver-changelog-on-publish) ───────
# Keep a Changelog 1.1.0: accumulate changes under [Unreleased], then `release`
# cuts them into a SemVer version. Activates the Changelog Kind (one CHANGELOG
# doc per scope) — the human-facing "what changed, when" the raw version history
# (a firehose of machine snapshots) can't give. Especially for shared scopes
# (_lib): the release log is what makes a default consumable downstream.
_CHANGELOG_CATEGORIES = ("added", "changed", "deprecated", "removed", "fixed", "security")
_CHANGELOG_ICON = {"added": "✨", "changed": "🔧", "deprecated": "⚠", "removed": "🗑",
                   "fixed": "🐛", "security": "🔒"}


def _changelog_category_options(f):
    for cat in reversed(_CHANGELOG_CATEGORIES):
        f = click.option(f"--{cat}", cat, multiple=True,
                         help=f"Keep-a-Changelog '{cat}' entry (repeatable).")(f)
    return f


def _load_changelog(scope: str) -> dict[str, Any]:
    import copy
    with open_session(scope) as s:
        existing = s.get_doc("Changelog", "CHANGELOG")
        if existing is not None and isinstance(existing.spec, dict):
            return copy.deepcopy(existing.spec)  # never mutate the cached doc
    return {
        "title": f"{scope} Changelog",
        "description": "Release notes — Keep a Changelog 1.1.0 + SemVer 2.0.",
        "versions": [],
    }


def _changelog_unreleased_entry(spec: dict[str, Any]) -> dict[str, Any]:
    versions = spec.setdefault("versions", [])
    if not versions or versions[0].get("version") != "[Unreleased]":
        versions.insert(0, {"version": "[Unreleased]"})
    return versions[0]


def _merge_changelog_items(entry: dict[str, Any], items: dict[str, tuple]) -> int:
    n = 0
    for cat, vals in items.items():
        if vals:
            entry.setdefault(cat, []).extend(vals)
            n += len(vals)
    return n


def _write_changelog(scope: str, spec: dict[str, Any]) -> None:
    raw = _build_raw("Changelog", "CHANGELOG", spec)
    with open_session(scope) as s:
        s.run(s.kernel.write_document(scope, "Changelog", "CHANGELOG", raw))


@sdlc.group("changelog", help="Release notes per scope (Keep a Changelog + SemVer).")
def changelog_group() -> None:
    pass


@changelog_group.command("unreleased")
@_scope_option
@_changelog_category_options
def changelog_unreleased(scope, added, changed, deprecated, removed, fixed, security):
    """Accumulate changes under [Unreleased] (cut later with `release`)."""
    items = dict(added=added, changed=changed, deprecated=deprecated,
                 removed=removed, fixed=fixed, security=security)
    if not any(items.values()):
        raise click.UsageError(
            "nothing to add — pass at least one of "
            "--added/--changed/--fixed/--removed/--deprecated/--security")
    spec = _load_changelog(scope)
    n = _merge_changelog_items(_changelog_unreleased_entry(spec), items)
    _write_changelog(scope, spec)
    click.secho(f"+{n} → [Unreleased] de {scope}/CHANGELOG", fg="green")


@changelog_group.command("release")
@_scope_option
@click.option("--version", "version", required=True,
              help="SemVer for this release (e.g. 1.4.0).")
@_changelog_category_options
def changelog_release(scope, version, added, changed, deprecated, removed, fixed, security):
    """Cut a SemVer release: stamp [Unreleased] as <version> (date=today) and
    open a fresh [Unreleased]. Inline --added/... merge in first."""
    spec = _load_changelog(scope)
    entry = _changelog_unreleased_entry(spec)
    _merge_changelog_items(entry, dict(added=added, changed=changed,
        deprecated=deprecated, removed=removed, fixed=fixed, security=security))
    if not any(entry.get(c) for c in _CHANGELOG_CATEGORIES):
        raise click.UsageError(
            f"[Unreleased] de {scope} está vazio — acumule com `changelog "
            "unreleased` ou passe --added/... aqui antes de cortar a release.")
    entry["version"] = version
    entry["date"] = _now_iso()[:10]
    spec["versions"].insert(0, {"version": "[Unreleased]"})
    _write_changelog(scope, spec)
    click.secho(f"RELEASED {scope} {version} ({entry['date']})", fg="green", bold=True)


@changelog_group.command("show")
@_scope_option
def changelog_show(scope):
    """Render the scope's changelog (releases, newest first)."""
    spec = _load_changelog(scope)
    versions = spec.get("versions") or []
    renderable = [v for v in versions
                  if any(v.get(c) for c in _CHANGELOG_CATEGORIES)]
    if not renderable:
        click.secho(
            f"({scope} sem changelog ainda — use `changelog unreleased`/`release`)",
            fg="yellow")
        return
    click.secho(spec.get("title", f"{scope} Changelog"), bold=True)
    for v in renderable:
        date = f"  ({v['date']})" if v.get("date") else ""
        click.secho(f"\n## {v.get('version', '?')}{date}", fg="cyan", bold=True)
        for cat in _CHANGELOG_CATEGORIES:
            for item in v.get(cat) or []:
                click.echo(f"  {_CHANGELOG_ICON[cat]} {cat}: {item}")


# ─── digest — retrospective "what happened while you were away" ────────
# f-sdlc-digest / s-sdlc-delegator-digest. Appended isolated at the end of
# the group so it never touches the neighbouring `cite` / `epic show` work.
# Aggregation lives in the PURE `dna_cli._digest` module (unit-tested without
# a kernel); this command owns only the impure edges: kernel session, gh/git
# context, rendering, and the StatusReport persistence.

# The Kinds whose timelines the digest walks. Some may be absent in a given
# distribution — the walk is fail-soft per kind (like `extract-decisions`).
_DIGEST_KINDS = (
    "Story", "Feature", "Epic", "Issue", "ADR", "Kaizen",
    "Spike", "Bug", "Task", "Initiative",
)


def _gh_open_prs_with_url() -> list[dict[str, Any]] | None:
    """Open PRs incl. ``url`` (superset of ``_gh_open_prs`` — the digest wants
    the clickable link on review items). Fail-soft: None when gh is absent."""
    import json as _json
    import subprocess
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "open",
             "--json", "number,title,headRefName,createdAt,url"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        if result.returncode != 0:
            return None
        parsed = _json.loads(result.stdout or "[]")
        return parsed if isinstance(parsed, list) else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, ValueError):
        return None


def _git_tags_with_dates() -> list[dict[str, Any]]:
    """Repo tags with their creation dates (releases). Fail-soft → []."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "for-each-ref", "--sort=-creatordate",
             "--format=%(refname:short)\t%(creatordate:iso-strict)",
             "refs/tags"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if result.returncode != 0:
            return []
        tags: list[dict[str, Any]] = []
        for line in (result.stdout or "").splitlines():
            if "\t" not in line:
                continue
            nm, _, at = line.partition("\t")
            tags.append({"name": nm.strip(), "at": at.strip()})
        return tags
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


def _find_last_digest_at(s: Any) -> datetime | None:
    """Timestamp of the most recent saved digest StatusReport (for
    ``--since last-digest``). Digests are named ``digest-*`` and carry
    ``spec.insight == 'sdlc-digest'``; ignore oracle reports."""
    from dna_cli._digest import parse_iso_utc as _piso
    latest: datetime | None = None
    try:
        for d in s.query_list("StatusReport"):
            sp = d.spec if isinstance(d.spec, dict) else {}
            if sp.get("insight") != "sdlc-digest" and not d.name.startswith("digest-"):
                continue
            at = _piso(sp.get("generated_at") or sp.get("created_at"))
            if at and (latest is None or at > latest):
                latest = at
    except Exception:  # noqa: BLE001 — no StatusReport kind / query hiccup
        return None
    return latest


def _render_digest(dg: dict[str, Any]) -> None:
    """Print a one-screen digest grouped Concluído / Decidido / Achado /
    Precisa de você — attention section FIRST-CLASS and loud (that's what the
    delegator opens the digest for)."""
    c = dg["counts"]
    rag_color = {"red": "red", "amber": "yellow", "green": "green"}[dg["rag_status"]]
    click.secho(
        f"\n🗞️  Digest — {dg['scope']}  ({dg['since_label']})",
        fg="cyan", bold=True,
    )
    click.secho(f"   {dg['verdict']}", fg=rag_color, bold=True)

    # PRECISA DE VOCÊ — first, because it's the point of the digest.
    att = dg["attention"]
    click.secho(f"\n🔔 PRECISA DE VOCÊ ({c['attention']})", fg="red", bold=True)
    if not c["attention"]:
        click.echo("   (nada pendente — tudo tocou sozinho)")
    for r in att["blocked"]:
        click.echo(f"   🚧 BLOCKED  {click.style(r['name'], fg='cyan')}  — {r['reason'][:70]}")
    for r in att["review_awaiting"]:
        prs = "  ".join(f"#{p['number']}" for p in r["prs"]) or "(sem PR aberto!)"
        click.echo(f"   👀 REVIEW   {click.style(r['name'], fg='cyan')}  {prs}")
    for r in att["owner_decisions"]:
        click.echo(f"   🧭 DECIDIR  {click.style(r['name'], fg='cyan')}  {r['title'][:60]}")
    for r in att["open_questions"]:
        click.echo(f"   ❓ RESPONDER {click.style(r['name'], fg='cyan')}  {r['question'][:60]}")

    click.secho(f"\n✅ Concluído ({c['completed']})", fg="green", bold=True)
    for r in dg["completed"]:
        click.echo(f"   • {click.style(r['name'], fg='cyan')}  {r['title'][:56]}  [→{r['to']}]")
    if not dg["completed"]:
        click.echo("   (nada fechou na janela)")

    click.secho(f"\n🧠 Decidido ({c['decided']})", fg="magenta", bold=True)
    for r in dg["decided"]:
        click.echo(f"   • {click.style(r['name'], fg='cyan')}  {r['summary'][:64]}")
    if not dg["decided"]:
        click.echo("   (sem decisões registradas)")

    click.secho(f"\n🔍 Achado ({c['found']})", fg="yellow", bold=True)
    for r in dg["found"]:
        click.echo(f"   • {click.style(r['name'], fg='cyan')}  {r['body'][:60]}")
    if not dg["found"]:
        click.echo("   (nada filado)")

    if dg["progressed"]:
        click.secho(f"\n📈 Avançou ({c['progressed']})", fg="blue", bold=True)
        for r in dg["progressed"]:
            click.echo(f"   • {click.style(r['name'], fg='cyan')}  {r['title'][:52]}  [→{r['to']}]")
    if dg["releases"]:
        click.secho(f"\n🚀 Releases ({c['releases']})", fg="green", bold=True)
        for r in dg["releases"]:
            click.echo(f"   • {r['tag']}  ({r['at'][:10]})")
    if dg["artifacts"]:
        click.secho(f"\n📎 Artefatos ({c['artifacts']})", fg="blue")
        for r in dg["artifacts"][:12]:
            click.echo(f"   • {r['kind']}/{r['name']}  ← {r['work_item']}")
    click.echo("")


def _save_digest_report(s: Any, scope: str, dg: dict[str, Any]) -> str:
    """Persist the digest as a StatusReport (record plane) — durable +
    queryable via `dna cognitive search`/`recall`. Returns the doc name.

    `insight='sdlc-digest'` is a synthetic marker (NOT an oracle Insight) so
    digests are distinguishable from oracle verdicts sharing the Kind. The
    `verdict` + `heuristic_explanation` fields are `embed`-ed, so a later
    semantic search over "o que aconteceu com X" recalls the digest.
    """
    now = _now_iso()
    name = f"digest-{now[:19].replace(':', '').replace('-', '').replace('T', '-')}"
    c = dg["counts"]
    att = dg["attention"]
    evidence = [
        f"{r['kind']}/{r['name']}"
        for bucket in ("completed", "decided", "found", "progressed")
        for r in dg[bucket]
    ]
    for group in att.values():
        evidence.extend(f"{r['kind']}/{r['name']}" for r in group)
    heuristic = (
        f"Retrospective digest do scope {scope} na janela {dg['since_label']} "
        f"({dg['since']} → {dg['until']}). Varreu as timelines de "
        f"{', '.join(_DIGEST_KINDS)}: {c['completed']} terminais, {c['decided']} "
        f"decisões, {c['found']} achados, {c['progressed']} avanços, "
        f"{c['releases']} releases, {c['artifacts']} artefatos. "
        f"Atenção ({c['attention']}): {len(att['blocked'])} blocked, "
        f"{len(att['review_awaiting'])} em review, {len(att['owner_decisions'])} "
        f"decisões-do-dono, {len(att['open_questions'])} perguntas abertas. "
        f"RAG={dg['rag_status']} (red=blocked; amber=pendências; green=limpo)."
    )
    spec: dict[str, Any] = {
        "insight": "sdlc-digest",
        "question": f"O que aconteceu em {scope} {dg['since_label']}?",
        "verdict": dg["verdict"],
        "confidence": "certain",
        "rag_status": dg["rag_status"],
        "metrics": {**c, "buckets": {
            k: dg[k] for k in
            ("completed", "decided", "found", "progressed", "releases", "artifacts")
        }, "attention": att},
        "heuristic_explanation": heuristic,
        "evidence_refs": evidence[:100],
        "generated_at": now,
        "generated_by": f"dna-sdlc-digest ({_cli_actor()})",
    }
    raw = _build_raw("StatusReport", name, spec)
    s.run(s.kernel.write_document(scope, "StatusReport", name, raw))
    return name


@sdlc.command("digest")
@click.option("--since", "since_spec", default=None,
              help="Janela para trás: ISO-8601, um span (24h/3d/2w) ou "
                   "'last-digest' (desde o último digest salvo). Default: 24h.")
@click.option("--save", is_flag=True,
              help="Persiste o digest como StatusReport 'digest-<data>' "
                   "(durável + queryável via `dna cognitive search`/`recall`).")
@click.option("--json", "as_json", is_flag=True,
              help="Saída estruturada (o dict do agregador).")
@_scope_option
def cmd_digest(since_spec: str | None, save: bool, as_json: bool, scope: str) -> None:
    """Retrospectiva: **o que aconteceu enquanto você estava fora**.

    O inverso do `brief`/`next`/`current` — estes olham PRA FRENTE ("o que
    fazer a seguir"); o **digest olha PRA TRÁS** ("o que já aconteceu"). É a
    superfície de quem DELEGA e revisa no fim, em vez de acompanhar o board ao
    vivo.

    Agrega os eventos das timelines de todos os work items numa janela
    (``--since``) e agrupa em **Concluído / Decidido / Achado / Precisa de
    você** — a seção *Precisa de você* (blocked, stories em review, decisões
    do dono, perguntas abertas) vem primeiro, porque é o que o delegador
    quer ver. Com ``--save`` o digest vira um StatusReport queryável depois.
    """
    from dna_cli._digest import build_digest, resolve_since

    now = datetime.now(timezone.utc)
    with open_session(scope) as s:
        last_digest_at = (
            _find_last_digest_at(s) if since_spec == "last-digest" else None
        )
        try:
            since, since_label = resolve_since(
                since_spec, now=now, last_digest_at=last_digest_at,
            )
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc

        docs: list[dict[str, Any]] = []
        for kind in _DIGEST_KINDS:
            try:
                for d in s.query_list(kind):
                    docs.append({
                        "kind": kind, "name": d.name,
                        "spec": d.spec if isinstance(d.spec, dict) else dict(d.spec or {}),
                    })
            except Exception:  # noqa: BLE001 — kind absent in this distribution
                continue

        open_prs = _gh_open_prs_with_url()
        tags = _git_tags_with_dates()

        dg = build_digest(
            docs=docs, since=since, until=now, since_label=since_label,
            scope=scope, open_prs=open_prs, tags=tags,
        )

        saved_name: str | None = None
        if save:
            saved_name = _save_digest_report(s, scope, dg)

    if as_json:
        if saved_name:
            dg["saved_as"] = f"StatusReport/{saved_name}"
        print_json(dg)
        return

    _render_digest(dg)
    if saved_name:
        click.secho(
            f"💾 salvo como StatusReport/{saved_name} "
            f"(query: `dna cognitive search \"digest {scope}\"`)",
            fg="green",
        )


# ─── gallery — board-native index of the HtmlArtifacts to review ───────
# f-sdlc-digest / s-sdlc-gallery. Sibling of `digest`: the digest surfaces
# EVENTS ("o que aconteceu"); the gallery surfaces the visual ARTIFACTS
# ("os HtmlArtifacts pra revisar"), grouped by the status of the work item
# that produced them. Board-native — regenerated from the board, always
# current — so the delegator stops hunting for artifacts pasted into chat.
# Aggregation lives in the PURE `dna_cli._gallery` module (unit-tested without
# a kernel); this command owns only the impure edges: kernel session, gh PRs,
# rendering, and file output.

# The work-item Kinds whose produces[]/back-refs the gallery walks. Some may
# be absent in a given distribution — the walk is fail-soft per kind.
_GALLERY_WI_KINDS = (
    "Story", "Feature", "Epic", "Issue", "Spike",
    "Bug", "Task", "Initiative", "ADR",
)


def _render_gallery_text(g: dict[str, Any]) -> None:
    """One-screen text panel — the review queue (needs_review) leads."""
    from dna_cli._gallery import BUCKET_ORDER, bucket_label
    c = g["counts"]
    click.secho(f"\n🖼️  Gallery — {g['scope']}  ({c['total']} HtmlArtifacts)", fg="cyan", bold=True)
    click.secho(
        "   artefatos visuais pra revisar, agrupados pelo status do work item "
        "(digest = eventos; gallery = artefatos)",
        fg="white",
    )
    _bucket_color = {
        "needs_review": "yellow", "decisions": "magenta", "shipped": "green",
        "in_progress": "blue", "unlinked": "white",
    }
    _bucket_icon = {
        "needs_review": "👀", "decisions": "🧭", "shipped": "✅",
        "in_progress": "📈", "unlinked": "📎",
    }
    if not c["total"]:
        click.secho("\n   (nenhum HtmlArtifact neste scope — registre com "
                    "`dna sdlc artifact create`)", fg="yellow")
        return
    for b in BUCKET_ORDER:
        entries = g["buckets"].get(b) or []
        if not entries:
            continue
        click.secho(f"\n{_bucket_icon[b]} {bucket_label(b)} ({len(entries)})",
                    fg=_bucket_color[b], bold=True)
        for e in entries:
            wi = e.get("work_item")
            wi_str = f"{wi['kind']}/{wi['name']} [{wi.get('status') or '—'}]" if wi else "(órfão)"
            title = e.get("title") or e.get("name")
            click.echo(f"   • {click.style(e['name'], fg='cyan')}  {title[:52]}")
            click.echo(f"       ← {wi_str}")
            if e.get("published_url"):
                click.echo(f"       🔗 {e['published_url']}")
            for pr in e.get("prs") or []:
                click.echo(f"       👀 PR #{pr.get('number')} {pr.get('url') or ''}")
    click.echo("")


@sdlc.command("gallery")
@click.option("--html", "html_out", type=click.Path(dir_okay=False), default=None,
              help="Gera UM arquivo HTML self-contained (cards por artifact, "
                   "chip de status, link publicado) — o painel que o dono abre.")
@click.option("--open", "open_after", is_flag=True,
              help="Abre o HTML gerado no browser (implica --html se ausente, "
                   "usando um arquivo temporário).")
@click.option("--json", "as_json", is_flag=True,
              help="Saída estruturada (o dict do agregador build_gallery).")
@_scope_option
def cmd_gallery(html_out: str | None, open_after: bool, as_json: bool, scope: str) -> None:
    """Painel board-native dos **HtmlArtifacts pra revisar**.

    Irmão do ``digest``. O ``digest`` mostra **o que aconteceu** (eventos das
    timelines); o **gallery** mostra **os artefatos visuais pra revisar** (os
    ``HtmlArtifact`` do board), agrupados pelo status do work item que os
    produziu (via ``produces[]`` / back-ref):

    \b
      👀 Precisa de avaliação  — Story em review / com PR aberto
      🧭 Decisões              — produzidos por um ADR
      ✅ Shipado               — work item em status terminal
      📈 Em andamento          — work item ainda em curso
      📎 Sem work item         — órfão no board

    Board-native: o índice é **gerado do board**, então está sempre atual —
    mata o "publico artifacts soltos no chat e o dono tem que caçar".
    Com ``--html <out>`` vira UM arquivo navegável (self-contained, sem CDN)
    que o delegador abre pra revisar.
    """
    from dna_cli._gallery import build_gallery, render_gallery_html

    with open_session(scope) as s:
        artifacts: list[dict[str, Any]] = []
        async def _collect() -> None:
            async for raw in s.kernel.query(scope, "HtmlArtifact"):
                meta = raw.get("metadata") if isinstance(raw, dict) else {}
                spec = raw.get("spec") if isinstance(raw, dict) else {}
                spec = spec if isinstance(spec, dict) else {}
                aj = spec.get("artifact_json") or {}
                aj = aj if isinstance(aj, dict) else {}
                artifacts.append({
                    "name": (meta or {}).get("name", "?"),
                    "title": aj.get("title"),
                    "description": aj.get("description") or (meta or {}).get("description"),
                    "source": aj.get("source"),
                    "published_url": aj.get("published_url"),
                    "html_bytes": len(spec.get("html") or ""),
                })
        s.run(_collect())

        work_items: list[dict[str, Any]] = []
        for kind in _GALLERY_WI_KINDS:
            try:
                for d in s.query_list(kind):
                    work_items.append({
                        "kind": kind, "name": d.name,
                        "spec": d.spec if isinstance(d.spec, dict) else dict(d.spec or {}),
                    })
            except Exception:  # noqa: BLE001 — kind absent in this distribution
                continue

        open_prs = _gh_open_prs_with_url()
        g = build_gallery(
            artifacts=artifacts, work_items=work_items, scope=scope, open_prs=open_prs,
        )

    if as_json:
        print_json(g)
        return

    # HTML output (explicit path, or a temp file when only --open is passed).
    if html_out or open_after:
        html = render_gallery_html(g, generated_at=_now_iso())
        if html_out:
            from pathlib import Path as _Path
            _Path(html_out).write_text(html, encoding="utf-8")
            target = html_out
            click.secho(f"🖼️  painel salvo em {html_out} "
                        f"({g['counts']['total']} artifacts)", fg="green")
        else:
            import tempfile
            fd = tempfile.NamedTemporaryFile(
                "w", suffix="-dna-gallery.html", delete=False, encoding="utf-8")
            fd.write(html)
            fd.close()
            target = fd.name
            click.secho(f"🖼️  painel em {target}", fg="green")
        if open_after:
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(target)}")
        if not as_json:
            _render_gallery_text(g)
        return

    _render_gallery_text(g)
