"""``dna sdlc initiative`` — Jira Align level (Theme/OKR → Initiative → Epic).

Extracted verbatim from ``sdlc_cmd.py`` (the sdlc_cmd decomposition).
"""
from __future__ import annotations

import os
from typing import Any

import click

from dna.application.sdlc import VALID_PRIORITIES

from dna_cli._ctx import fail, open_session
from dna_cli.sdlc._common import (
    _append_timeline,
    _build_raw,
    _csv,
    _now_iso,
    _scope_option,
    _transition_workitem,
)
from dna_cli.sdlc._root import sdlc

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
