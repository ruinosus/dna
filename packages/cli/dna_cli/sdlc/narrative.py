"""``dna sdlc narrative`` — project narrative (write cadence + arrays).

Extracted verbatim from ``sdlc_cmd.py`` (the sdlc_cmd decomposition).
"""
from __future__ import annotations

from typing import Any

import click

from dna_cli._ctx import fail, open_session
from dna_cli.sdlc._common import (
    DEFAULT_SCOPE,
    _build_raw,
    _cli_actor,
    _now_iso,
    _scope_option,
)
from dna_cli.sdlc._root import sdlc

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
