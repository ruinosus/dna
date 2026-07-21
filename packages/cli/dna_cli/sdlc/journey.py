"""``dna sdlc journey`` — the phase-aware journey ledger + ``demand``.

Extracted verbatim from ``sdlc_cmd.py`` (the sdlc_cmd decomposition).
WorkflowEvent trail from idea→ship, additive over Superpowers/BMAD/
Spec Kit; ``demand`` opens the Story + journey-discover pair.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

import click

from dna.application.sdlc import VALID_PRIORITIES

from dna_cli._ctx import fail, open_session, print_json
from dna_cli.sdlc._common import (
    VALID_JOURNEY_METHODOLOGIES,
    VALID_JOURNEY_PHASES,
    _append_timeline,
    _build_raw,
    _cli_actor,
    _now_iso,
    _scope_option,
)
from dna_cli.sdlc._root import sdlc

# ---------------------------------------------------------------------------
# Journey ledger — phase transitions across Spec/Plan/Story/AgentSession/Narrative
# ---------------------------------------------------------------------------

@sdlc.group("journey")
def journey_group() -> None:
    """Phase-aware journey ledger — additive over Superpowers/BMAD/Spec Kit.

    Records the trail from idea→ship as a sequence of WorkflowEvent
    docs pinned to (phase, artifact) pairs. Companion to the Skill at
    `.claude/skills/dna-journey/SKILL.md`.
    """


def _entry_name(parent_ref: str, phase: str) -> str:
    """Stable name for a WorkflowEvent. <parent-slug>-<phase>-<idx> — idx is
    1-based count among siblings sharing (parent_ref, phase)."""
    safe = parent_ref.replace("/", "-").lower()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{safe}-{phase}-{ts}"


def _write_feature_reflect_workflow_event(
    scope: str, feature_name: str, *, summary: str | None = None,
) -> str | None:
    """Auto-write a reflect-phase WorkflowEvent for a Feature being shipped.

    Bug fix: Narrative close hook requires a reflect entry to exist
    for the Feature. `dna sdlc feature ship` cascade-closed Stories
    but didn't transition the FEATURE's own journey — the hook
    silently skipped, the cycle Narrative disappeared.

    Idempotent: if a reflect entry already exists for this parent,
    skip (returns None). Fail-soft: never raises.
    """
    parent_ref = f"Feature/{feature_name}"
    try:
        now = _now_iso()
        with open_session(scope) as s:
            prev_entries = _list_entries_for_parent(s, parent_ref)
            # Already has a reflect entry? Don't double-write.
            has_reflect = any(
                (e.spec or {}).get("phase") == "reflect"
                for e in prev_entries
            )
            if has_reflect:
                return None
            prev_open = next(
                (e for e in reversed(prev_entries) if not (e.spec or {}).get("ended_at")),
                None,
            )
            name = _entry_name(parent_ref, "reflect")
            spec: dict[str, Any] = {
                "phase": "reflect",
                "ref": parent_ref,
                "parent_ref": parent_ref,
                "methodology": "ad-hoc",
                "started_at": now,
                "actor": _cli_actor(),
                "created_at": now,
            }
            if summary:
                spec["summary"] = summary
            if prev_open is not None:
                psp = dict(prev_open.spec) if isinstance(prev_open.spec, dict) else {}
                psp["ended_at"] = now
                praw = _build_raw("WorkflowEvent", prev_open.name, psp)
                s.run(s.kernel.write_document(scope, "WorkflowEvent", prev_open.name, praw))
                spec["transitioned_from"] = prev_open.name
            raw = _build_raw("WorkflowEvent", name, spec)
            s.run(s.kernel.write_document(scope, "WorkflowEvent", name, raw))
        return name
    except Exception:  # noqa: BLE001 — best-effort observability
        return None




def _list_entries_for_parent(holder_or_session: Any, parent_ref: str) -> list[Any]:
    """All WorkflowEvent docs in scope filtered by parent_ref, oldest first.

    Accepts either:
      - a kernel-backed ``holder`` (legacy dna_session path: has
        ``query_list`` method directly), OR
      - an dna-client ``ClientSession`` (the new default): we go through
        ``session.query_list`` since ``_ClientHolder`` is reload-only.

    2026-05-26 fix — previously hardcoded ``holder.query_list`` which
    silently returned [] under dna-client (ClientHolder has no
    query_list), causing ``transition`` to report "no journey entries"
    for valid parents.
    """
    src: Any = holder_or_session
    # Detect ClientSession passed by accident (the legacy callers pass
    # s.holder; new callers may pass the session itself for clarity).
    if not hasattr(src, "query_list"):
        # Caller probably passed s.holder which is _ClientHolder — try
        # to recover by walking up to the session that owns it.
        owner = getattr(src, "_session", None)
        if owner is not None and hasattr(owner, "query_list"):
            src = owner
        else:
            # Final fallback: empty (preserves old fail-soft behavior).
            return []
    try:
        entries = src.query_list("WorkflowEvent")
    except Exception:  # noqa: BLE001
        entries = []
    matching = [
        e for e in entries
        if (e.spec or {}).get("parent_ref") == parent_ref
    ]
    matching.sort(key=lambda e: (e.spec or {}).get("started_at") or "")
    return matching


def _resolve_cycle_index(
    entries: list[Any], phase: str,
    new_cycle: bool = False, prev_open: Any = None,
) -> int:
    """Compute the cycle_index for a NEW WorkflowEvent being opened.

    Rules:
      - If `new_cycle` is True (close-cycle path), latest cycle_index + 1.
      - If `prev_open` exists with explicit cycle_index, inherit it.
      - Else fall back to the latest entry's cycle_index, or 1 when empty.
      - Heuristic for back-compat (entries without cycle_index): treat
        the count of `discover-after-reflect` boundaries as cycle - 1.
    """
    if new_cycle:
        max_idx = 0
        for e in entries:
            ci = (e.spec or {}).get("cycle_index")
            if isinstance(ci, int) and ci > max_idx:
                max_idx = ci
        if max_idx > 0:
            return max_idx + 1
        # Heuristic on legacy entries: count phase=discover-after-reflect boundaries.
        cnt = 1
        prev_phase = None
        for e in entries:
            ph = (e.spec or {}).get("phase")
            if ph == "discover" and prev_phase == "reflect":
                cnt += 1
            prev_phase = ph or prev_phase
        return cnt + 1  # +1 because we're opening the NEXT cycle

    # Same-cycle continuation.
    if prev_open is not None:
        ci = (prev_open.spec or {}).get("cycle_index")
        if isinstance(ci, int):
            return ci
    if entries:
        latest = entries[-1]
        ci = (latest.spec or {}).get("cycle_index")
        if isinstance(ci, int):
            return ci
        # Heuristic: count discover-after-reflect transitions.
        cnt = 1
        prev_phase = None
        for e in entries:
            ph = (e.spec or {}).get("phase")
            if ph == "discover" and prev_phase == "reflect":
                cnt += 1
            prev_phase = ph or prev_phase
        return cnt
    return 1


_SKILL_HINTS_BY_PHASE = {
    "specify": "superpowers:writing-plans",
    "plan": "superpowers:writing-plans",
    "build": "superpowers:test-driven-development",
    "reflect": "superpowers:verification-before-completion",
}


def _tdd_since_sha_for_parent(s: Any, parent_ref: str) -> str | None:
    """Return the commit SHA captured at the start of the most recent
    ``build`` phase entry for this parent. Used by tdd_gate to compute
    the git diff window. Returns None when no build entry has the field
    (older entries before this feature shipped) — in which case
    tdd_gate.SKIPs honestly.
    """
    try:
        entries = _list_entries_for_parent(s, parent_ref)
    except Exception:  # noqa: BLE001
        return None
    for e in reversed(entries):
        sp = e.spec or {}
        if sp.get("phase") == "build":
            return sp.get("commit_ref_at_phase_start")
    return None


def _capture_head_sha() -> str | None:
    """Capture current HEAD SHA. Returns None on any git error."""
    import subprocess
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _recent_cycle_methodologies(entries: list[Any]) -> list[str]:
    """Reconstruct cycle-level methodology from entries.

    A "cycle" is the run between two ``discover`` phases (inclusive of
    the opener). Within a cycle, methodology may shift phase by phase;
    we capture the methodology of the cycle's ``discover`` entry as
    the canonical cycle methodology (or the first methodology seen if
    the cycle skipped discover).

    Returns a list of methodology strings in chronological order, one
    per cycle. Consumers typically take ``[-5:]`` for the recent window.
    """
    cycle_methods: list[str] = []
    current: str | None = None
    for e in entries:
        sp = e.spec or {}
        if sp.get("phase") == "discover":
            if current is not None:
                cycle_methods.append(current)
            current = str(sp.get("methodology") or "")
        elif current is None and sp.get("methodology"):
            current = str(sp.get("methodology"))
    if current is not None:
        cycle_methods.append(current)
    return cycle_methods


def _print_skill_hint(phase: str) -> None:
    """Emit a skill invocation hint when running under a Claude Code session.

    Hint-only — CLI cannot force the agent to actually invoke the skill.
    Skip silently if the phase has no canonical skill mapping.
    """
    skill = _SKILL_HINTS_BY_PHASE.get(phase)
    if not skill:
        return
    click.secho(
        f"→ Skill hint: invoke Skill('{skill}') antes desta phase.",
        fg="cyan",
    )


@journey_group.command("enter")
@click.argument("phase", type=click.Choice(VALID_JOURNEY_PHASES))
@click.option("--ref", required=True,
              help="Doc representing this phase (Kind/name, e.g. Plan/foo).")
@click.option("--parent", "parent_ref", required=True,
              help="Anchor doc (Feature/f-X or Epic/e-X) grouping siblings.")
@click.option("--methodology",
              type=click.Choice(VALID_JOURNEY_METHODOLOGIES),
              default="ad-hoc", show_default=True)
@click.option("--artifact", default=None,
              help="External methodology artifact path/URL (e.g. "
                   "docs/superpowers/plans/foo-plan.md).")
@click.option("--skip-from", "skip_from", default=None,
              help="Previous phase you skipped to land here (honest "
                   "about cut corners, e.g. --skip-from discover).")
@click.option("--summary", default=None,
              help="1-2 sentence note about what's happening here.")
@click.option("--force", is_flag=True, default=False,
              help="Override methodology gates. Requires --reason for "
                   "honest justification.")
@click.option("--reason", default=None,
              help="Reason for --force override. Stored in "
                   "entry.spec.force_reason for audit.")
@_scope_option
def cmd_journey_enter(
    phase: str, ref: str, parent_ref: str, methodology: str,
    artifact: str | None, skip_from: str | None, summary: str | None,
    force: bool, reason: str | None, scope: str,
) -> None:
    """Open a new WorkflowEvent pinning a doc to a phase. The previous
    entry for this parent (if any) gets ``ended_at`` stamped.
    """
    # Methodology gates (Spec: 2026-05-11-f-superpowers-skill-integration.md).
    # Translate GateResult.FAIL → exit 2 unless --force --reason was passed.
    from dna_cli._methodology_gates import GateResult, spec_gate
    force_reason: str | None = None
    if force:
        if not reason:
            click.secho("❌ --force exige --reason (justificativa honesta).", fg="red")
            sys.exit(2)
        force_reason = reason
    gate = spec_gate(methodology=methodology, phase=phase, artifact=artifact)
    if gate == GateResult.FAIL and not force:
        click.secho(
            f"❌ Gate spec: methodology=superpowers + phase=specify exige "
            f"--artifact apontando para Spec doc existente em "
            f"docs/superpowers/specs/. Use --force --reason '<motivo>' "
            f"se honest skip.",
            fg="red",
        )
        sys.exit(2)
    if gate == GateResult.FAIL and force:
        click.secho(
            f"⚠ Spec gate forced: {force_reason}", fg="yellow")
    # Skill hint under Claude Code session — methodology+phase aware.
    if os.environ.get("CLAUDE_CODE_SESSION") and methodology == "superpowers":
        _print_skill_hint(phase)

    now = _now_iso()
    name = _entry_name(parent_ref, phase)
    skipped: list[str] = []
    if skip_from:
        # Phases between skip_from and the new phase (exclusive on both ends).
        order = list(VALID_JOURNEY_PHASES)
        try:
            i_from = order.index(skip_from)
            i_to = order.index(phase)
            if i_from < i_to - 1:
                skipped = order[i_from + 1:i_to]
        except ValueError:
            pass
    spec: dict[str, Any] = {
        "phase": phase,
        "ref": ref,
        "parent_ref": parent_ref,
        "methodology": methodology,
        "started_at": now,
        "actor": _cli_actor(),
        "created_at": now,
    }
    if artifact:
        spec["methodology_artifact"] = artifact
    if skipped:
        spec["skipped_phases"] = skipped
    if summary:
        spec["summary"] = summary
    if force_reason:
        spec["force_reason"] = force_reason

    with open_session(scope) as s:
        # Close the previous open entry (no ended_at) for the same parent.
        prev_entries = _list_entries_for_parent(s, parent_ref)
        prev_open = next(
            (e for e in reversed(prev_entries) if not (e.spec or {}).get("ended_at")),
            None,
        )
        if prev_open is not None:
            psp = dict(prev_open.spec) if isinstance(prev_open.spec, dict) else {}
            psp["ended_at"] = now
            praw = _build_raw("WorkflowEvent", prev_open.name, psp)
            s.run(s.kernel.write_document(scope, "WorkflowEvent", prev_open.name, praw))
            spec["transitioned_from"] = prev_open.name
        # Write the new entry.
        raw = _build_raw("WorkflowEvent", name, spec)
        s.run(s.kernel.write_document(scope, "WorkflowEvent", name, raw))
    click.secho(
        f"ENTERED {phase} → WorkflowEvent/{name} (ref={ref}, parent={parent_ref}, methodology={methodology})",
        fg="cyan",
    )
    if not summary and phase != "discover":
        click.secho(
            f"⚠ no --summary on `{phase}` — auto-Narrative will render "
            f"this phase as 'fase atravessada sem nota explícita'. "
            f"Pass `--summary \"<...>\"` to enrich it.",
            fg="yellow",
        )


def _write_plan_stub(
    parent_ref: str, ref: str, summary: str | None,
) -> str:
    """Write a minimal Plan doc to ``docs/superpowers/plans/<date>-<slug>-plan.md``
    and return the relative path. Slug derives from parent + ref; the
    template seeds H1 + Context + Plan + Out-of-scope sections so the
    agent only fills the meat.
    """
    from pathlib import Path
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    # parent_ref like "Feature/f-X", ref like "Story/s-Y" — derive slug
    parent_slug = parent_ref.split("/", 1)[-1] if "/" in parent_ref else parent_ref
    ref_slug = ref.split("/", 1)[-1] if "/" in ref else ref
    # strip common SDLC prefixes for cleaner filename
    parent_clean = _re_demand.sub(r"^(f|e|s|i|vs|dna-roadmap)-", "", parent_slug)
    ref_clean = _re_demand.sub(r"^(f|e|s|i|vs|dna-roadmap)-", "", ref_slug)
    slug = f"{parent_clean}-{ref_clean}"[:60].rstrip("-")
    filename = f"{date_str}-{slug}-plan.md"
    target_dir = Path("docs") / "superpowers" / "plans"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename

    body = (
        f"# Plan: {ref_clean.replace('-', ' ').title()}\n\n"
        f"_Auto-stubbed by `dna sdlc journey transition plan --auto-stub` "
        f"on {date_str}._\n\n"
        f"## Context\n\n"
        f"- Parent: `{parent_ref}`\n"
        f"- Ref:    `{ref}`\n"
        f"- Summary: {summary or '_(pending)_'}\n\n"
        f"## Plan\n\n"
        f"_(replace this section with 3-7 concrete steps; one per "
        f"deliverable. Each step should be executable and verifiable.)_\n\n"
        f"1. ...\n"
        f"2. ...\n"
        f"3. ...\n\n"
        f"## Out of scope\n\n"
        f"_(what we explicitly DON'T do in this cycle; prevents scope creep.)_\n\n"
        f"- ...\n\n"
        f"## Done when\n\n"
        f"_(acceptance criteria; reflect entry will check against these.)_\n\n"
        f"- ...\n"
    )
    target_path.write_text(body, encoding="utf-8")
    return str(target_path)


@journey_group.command("transition")
@click.argument("next_phase", type=click.Choice(VALID_JOURNEY_PHASES))
@click.option("--parent", "parent_ref", required=True,
              help="Anchor doc grouping siblings (must match the open entry).")
@click.option("--ref", "new_ref", default=None,
              help="Doc representing the NEXT phase. Defaults to "
                   "previous entry's ref if --keep-ref.")
@click.option("--keep-ref", is_flag=True,
              help="Reuse the previous entry's ref for the next entry.")
@click.option("--methodology",
              type=click.Choice(VALID_JOURNEY_METHODOLOGIES),
              default="ad-hoc", show_default=True)
@click.option("--artifact", default=None)
@click.option("--summary", default=None)
@click.option("--skip-from", "skip_from", default=None,
              type=click.Choice(VALID_JOURNEY_PHASES),
              help="Override the auto-detected skip-from phase. Use when "
                   "you want to mark MORE skipped phases than the prev "
                   "entry implies (e.g. honest self-assessment of cut "
                   "corners). By default, skipped_phases is computed "
                   "from prev_phase → next_phase.")
@click.option("--inline", "inline_plan", default=None,
              help="Inline plan text (1-3 lines describing the sequence). "
                   "Stored in entry.inline_plan — cheap alternative to "
                   "writing a full Plan doc. Use for small demands.")
@click.option("--auto-stub", is_flag=True,
              help="Generate a Plan doc stub at "
                   "docs/superpowers/plans/<date>-<slug>-plan.md and set "
                   "entry.methodology_artifact to its path. Use for "
                   "medium demands deserving a real Plan but not a long "
                   "design ceremony.")
@click.option("--force", is_flag=True, default=False,
              help="Override methodology gates. Requires --reason.")
@click.option("--reason", default=None,
              help="Reason for --force override. Stored in "
                   "entry.spec.force_reason for audit.")
@_scope_option
def cmd_journey_transition(
    next_phase: str, parent_ref: str, new_ref: str | None,
    keep_ref: bool, methodology: str, artifact: str | None,
    summary: str | None, skip_from: str | None,
    inline_plan: str | None, auto_stub: bool,
    force: bool, reason: str | None, scope: str,
) -> None:
    """Close the current entry for ``--parent`` and open one in
    ``next_phase``. Sugar over `journey enter` that auto-fills
    skip_from + transitioned_from from the previous entry. Pass
    --skip-from explicitly to widen the skip range beyond the
    prev entry's phase.
    """
    # --force requires --reason for honest override.
    force_reason: str | None = None
    if force:
        if not reason:
            click.secho("❌ --force exige --reason (justificativa honesta).", fg="red")
            sys.exit(2)
        force_reason = reason

    # Tracks whether the LLM cronista populated spec["summary"] during
    # the synth fallback path (line ~3133). Read OUTSIDE the with block
    # by the post-write nudge to avoid the misleading "vai ficar sem
    # nota" warning when the cronista already wrote one.
    summary_was_synthesized = False

    with open_session(scope) as s:  # local kernel — KernelSource needs _loop
        entries = _list_entries_for_parent(s, parent_ref)
        if not entries:
            raise fail(
                f"no journey entries for parent_ref={parent_ref!r}; "
                f"use `journey enter` first."
            )
        prev = entries[-1]
        prev_phase = (prev.spec or {}).get("phase")
        prev_ref = (prev.spec or {}).get("ref")

        # Methodology gates (plan_gate + tdd_gate + auditor_gate).
        # Spec: 2026-05-11-f-superpowers-skill-integration.md.
        from dna_cli._methodology_gates import (
            GateResult, auditor_gate, plan_gate, tdd_gate,
        )

        # auditor_gate: block 3+ ad-hoc streak without --methodology=superpowers.
        recent_methods = _recent_cycle_methodologies(entries)
        ag = auditor_gate(
            recent_methodologies=recent_methods,
            next_methodology=methodology,
        )
        if ag == GateResult.FAIL and not force:
            ad_hoc_n = sum(1 for m in recent_methods[-5:] if m == "ad-hoc")
            click.secho(
                f"❌ Auditor: {ad_hoc_n}/{len(recent_methods[-5:])} ciclos "
                f"recentes são ad-hoc. Próximo phase exige "
                f"`--methodology superpowers` para quebrar o streak. "
                f"Use --force --reason '<motivo honest>' se hotfix/emergência.",
                fg="red",
            )
            sys.exit(2)
        if ag == GateResult.FAIL and force:
            click.secho(f"⚠ Auditor gate forced: {force_reason}", fg="yellow")

        # plan_gate: phase=plan under superpowers requires Plan artifact or --auto-stub.
        pg = plan_gate(
            methodology=methodology,
            phase=next_phase,
            artifact=artifact,
            auto_stub=auto_stub,
        )
        if pg == GateResult.FAIL and not force:
            click.secho(
                "❌ Gate plan: methodology=superpowers + phase=plan exige "
                "--artifact apontando para Plan doc existente em "
                "docs/superpowers/plans/ OU --auto-stub. Use --force --reason "
                "'<motivo>' se honest skip.",
                fg="red",
            )
            sys.exit(2)
        if pg == GateResult.FAIL and force:
            click.secho(f"⚠ Plan gate forced: {force_reason}", fg="yellow")

        # tdd_gate: build → reflect under superpowers requires tests in git diff.
        if methodology == "superpowers" and prev_phase == "build" and next_phase == "reflect":
            since_sha = _tdd_since_sha_for_parent(s, parent_ref)
            tg = tdd_gate(
                methodology=methodology,
                prev_phase=prev_phase,
                next_phase=next_phase,
                since_sha=since_sha,
            )
            if tg == GateResult.FAIL and not force:
                click.secho(
                    "❌ Gate TDD: methodology=superpowers + build → reflect "
                    "exige pelo menos 1 arquivo de teste no git diff desde o "
                    "início da phase build. Use --force --reason "
                    "'<motivo>' se honest skip (ex: 'docs only').",
                    fg="red",
                )
                sys.exit(2)
            if tg == GateResult.FAIL and force:
                click.secho(f"⚠ TDD gate forced: {force_reason}", fg="yellow")

        # Skill hint under Claude Code session.
        if os.environ.get("CLAUDE_CODE_SESSION") and methodology == "superpowers":
            _print_skill_hint(next_phase)

        # Oracle verdict injection (Story s-oracle-verdict-prompt-inject,
        # f-cognitive-context-injection). When methodology=superpowers and
        # phase is specify/plan/build, stamp top-3 recent oracle verdicts
        # on the entry.spec.oracle_warnings so the next agent invocation
        # (or human reader) sees the council's current snapshot inline.
        oracle_warnings_text: str | None = None
        if methodology == "superpowers" and next_phase in ("specify", "plan", "build"):
            try:
                # Exclude digest StatusReports (insight='sdlc-digest',
                # f-sdlc-digest) — those are retrospective summaries, not
                # oracle verdicts, and must not leak into the council snapshot.
                verdicts = sorted(
                    (
                        v for v in s.query_list("StatusReport")
                        if not v.name.startswith("digest-")
                        and (v.spec.get("insight") if isinstance(v.spec, dict) else None)
                        != "sdlc-digest"
                    ),
                    key=lambda v: v.name, reverse=True,
                )[:3]
                if verdicts:
                    lines = []
                    for v in verdicts:
                        vsp = v.spec if isinstance(v.spec, dict) else {}
                        oracle = vsp.get("insight") or vsp.get("oracle") or "?"
                        verdict_body = (vsp.get("verdict") or vsp.get("verdict_body") or "")[:140]
                        lines.append(f"- {oracle}: {verdict_body}")
                    oracle_warnings_text = "\n".join(lines)
            except Exception:  # noqa: BLE001 — fail-soft (oracle snapshot is best-effort)
                pass

        ref = new_ref or (prev_ref if keep_ref else None)
        if not ref:
            raise fail(
                "--ref required (or pass --keep-ref to reuse the "
                f"previous entry's ref={prev_ref!r})."
            )

        # Close prev.
        now = _now_iso()
        psp = dict(prev.spec) if isinstance(prev.spec, dict) else {}
        if not psp.get("ended_at"):
            psp["ended_at"] = now
            praw = _build_raw("WorkflowEvent", prev.name, psp)
            s.run(s.kernel.write_document(scope, "WorkflowEvent", prev.name, praw))

        # Open next. Compute skipped_phases — by default from prev_phase
        # → next_phase; --skip-from override widens the window when the
        # user wants to mark cut corners that pre-date the prev entry.
        name = _entry_name(parent_ref, next_phase)
        skipped: list[str] = []
        from_phase = skip_from or prev_phase
        if from_phase:
            order = list(VALID_JOURNEY_PHASES)
            try:
                i_from = order.index(from_phase)
                i_to = order.index(next_phase)
                if i_from < i_to - 1:
                    skipped = order[i_from + 1:i_to]
            except ValueError:
                pass
        spec: dict[str, Any] = {
            "phase": next_phase,
            "ref": ref,
            "parent_ref": parent_ref,
            "methodology": methodology,
            "started_at": now,
            "actor": _cli_actor(),
            "created_at": now,
            "transitioned_from": prev.name,
        }
        # Capture commit SHA at the start of build phases so a later
        # build→reflect transition's tdd_gate can compute a git diff.
        if next_phase == "build":
            head_sha = _capture_head_sha()
            if head_sha:
                spec["commit_ref_at_phase_start"] = head_sha
        if force_reason:
            spec["force_reason"] = force_reason
        if oracle_warnings_text:
            spec["oracle_warnings"] = oracle_warnings_text
        # --auto-stub: write a Plan stub on disk + set artifact path.
        # Only meaningful for plan-phase transitions; harmless elsewhere
        # but emit a yellow note if used outside.
        stub_path: str | None = None
        if auto_stub:
            if next_phase != "plan":
                click.secho(
                    f"⚠ --auto-stub on `{next_phase}` (not plan) — stub "
                    f"written anyway but conceptually only fits plan.",
                    fg="yellow",
                )
            stub_path = _write_plan_stub(parent_ref, ref, summary)
            # --artifact wins if explicitly provided; otherwise stub path.
            if not artifact:
                artifact = stub_path

        if artifact:
            spec["methodology_artifact"] = artifact
        if skipped:
            spec["skipped_phases"] = skipped
        if summary:
            spec["summary"] = summary
        # (LLM cronista summary synthesis is a host-platform surface —
        # without --summary the entry simply carries none.)
        # --inline: short plan text in entry itself (no separate doc).
        if inline_plan:
            spec["inline_plan"] = inline_plan
        raw = _build_raw("WorkflowEvent", name, spec)
        s.run(s.kernel.write_document(scope, "WorkflowEvent", name, raw))

    click.secho(
        f"TRANSITIONED {prev_phase} → {next_phase} for {parent_ref}",
        fg="cyan",
    )
    if stub_path:
        click.secho(
            f"📝 Plan stub written: {stub_path} — fill the sections.",
            fg="green",
        )
    # Plan-phase nudge: if entering plan and NEITHER inline NOR artifact
    # NOR auto-stub were used, the plan is invisible. Surface as a
    # friendly nudge so downstream auto-Narratives don't render
    # "Planejamento: fase atravessada sem nota".
    if (
        next_phase == "plan"
        and not inline_plan
        and not artifact
        and not auto_stub
    ):
        click.secho(
            "⚠ plan phase entered without --inline, --artifact, or "
            "--auto-stub. The Plan will be invisible in the cycle's "
            "Narrative. Cheapest fix: rerun with "
            "`--inline \"<sequence in 1-3 lines>\"`.",
            fg="yellow",
        )
    # NOTE: cycle-level auditor was previously a post-write nudge here.
    # It is now a pre-write blocking gate via auditor_gate (see top of
    # this function). Cycle methodology reconstruction lives in
    # _recent_cycle_methodologies helper for reuse + testability.

    # Nudge: phases past discover should usually carry a one-line note
    # — silent transitions become opaque "fase atravessada sem nota"
    # paragraphs in auto-generated Narratives downstream.
    # Only warn if neither the explicit --summary nor the LLM cronista
    # populated the entry; the synth path already prints nothing on
    # success, so the user would otherwise see a misleading "vai ficar
    # sem nota" warning AFTER the cronista already filled it.
    if not summary and not summary_was_synthesized and next_phase != "discover":
        click.secho(
            f"⚠ no --summary on `{next_phase}` and LLM cronista unavailable "
            f"— auto-Narrative will render this phase as 'fase atravessada "
            f"sem nota explícita'. Add `--summary \"<o que aconteceu nesta "
            f"fase>\"` or configure an LLM to enable the cronista.",
            fg="yellow",
        )


@journey_group.command("current")
@click.option("--parent", "parent_ref", default=None,
              help="Filter to a specific anchor doc.")
@_scope_option
def cmd_journey_current(parent_ref: str | None, scope: str) -> None:
    """Show the latest open WorkflowEvent. Without --parent, shows the
    latest open entry across the whole scope.
    """
    with open_session(scope) as s:
        try:
            entries = s.query_list("WorkflowEvent")
        except Exception:  # noqa: BLE001
            entries = []
        if parent_ref:
            entries = [e for e in entries if (e.spec or {}).get("parent_ref") == parent_ref]
        # Open = ended_at is None.
        open_entries = [e for e in entries if not (e.spec or {}).get("ended_at")]
        open_entries.sort(
            key=lambda e: (e.spec or {}).get("started_at") or "", reverse=True,
        )
        if not open_entries:
            click.secho("(no open journey entries)", fg="yellow")
            if entries:
                latest = sorted(
                    entries,
                    key=lambda e: (e.spec or {}).get("started_at") or "",
                    reverse=True,
                )[0]
                spec = latest.spec or {}
                click.echo(
                    f"  most recent (closed): {latest.name} "
                    f"phase={spec.get('phase')} ref={spec.get('ref')} "
                    f"ended={spec.get('ended_at')}"
                )
            return
        click.secho(f"🧭 open journey entries — scope: {scope}", bold=True)
        for e in open_entries:
            sp = e.spec or {}
            # 2026-05-26 fix — phase/ref can be None on malformed entries;
            # str() coerces before format-spec so we don't crash with
            # "unsupported format string passed to NoneType.__format__".
            parent = str(sp.get("parent_ref") or "?")
            phase = str(sp.get("phase") or "?")
            ref = str(sp.get("ref") or "?")
            methodology = str(sp.get("methodology") or "?")
            click.echo(
                f"  {parent:40} {phase:8} ref={ref:30} methodology={methodology}"
            )
            if sp.get("summary"):
                click.echo(f"    └ {sp['summary']}")


@journey_group.command("list")
@click.option("--parent", "parent_ref", required=True,
              help="Anchor doc to show the trajectory of.")
@click.option("--json", "as_json", is_flag=True)
@_scope_option
def cmd_journey_list(parent_ref: str, as_json: bool, scope: str) -> None:
    """List the full trajectory (oldest first) for a parent ref. Useful
    to see "how did we get here" for a Feature/Epic.

    For a ``Story/<name>`` parent the trajectory is DERIVED server-side
    (s-journey-derived) from the Story's own state + linked artifacts —
    the same computation the Studio bar renders. Feature/Epic parents
    still list explicit WorkflowEvents (methodology ledger).
    """
    if parent_ref.split("/", 1)[0] in {"Story", "Spike", "Issue"}:
        # Kernel-local derivation — the same journey_derive computation the
        # upstream server route runs (s-journey-derived), no service needed.
        from dataclasses import asdict as _asdict
        from dna.extensions.sdlc.journey_derive import derive_journey
        _kind_p, _, _name_p = parent_ref.partition("/")
        story_journey: dict | None = None
        try:
            with open_session(scope) as _js:
                _doc = _js.get_doc(_kind_p, _name_p)
                if _doc is not None:
                    def _rows(k: str) -> list[dict]:
                        return [
                            {"name": d.name, "spec": dict(d.spec or {})}
                            for d in _js.query_list(k)
                        ]
                    _dj = derive_journey(
                        _kind_p, _name_p, dict(_doc.spec or {}),
                        specs=_rows("Spec"), plans=_rows("Plan"),
                        lessons=_rows("Engram"),
                        test_runs=_rows("TestRun"),
                    )
                    story_journey = {
                        "ref": _dj.ref,
                        "active_phase": _dj.active_phase,
                        "methodology": _dj.methodology,
                        "phases": [_asdict(p) for p in _dj.phases],
                    }
        except Exception as e:  # noqa: BLE001
            click.secho(f"warn: derived journey failed: {e}", fg="yellow")
        if as_json:
            print_json(story_journey or {})
            return
        if not story_journey:
            click.secho(f"(no story for {parent_ref!r})", fg="yellow")
            return
        click.secho(f"🧭 journey for {parent_ref} (derived)", bold=True)
        active = story_journey.get("active_phase")
        for p in story_journey.get("phases", []):
            if active == p["phase"]:
                mark = "▶"
            elif p["present"]:
                mark = "✓"
            elif p["skipped"]:
                mark = "⤳"
            else:
                mark = "·"
            click.echo(f"  {mark} {p['phase']:9} {p.get('evidence', '')}")
        if story_journey.get("methodology"):
            click.echo(f"  methodology: {story_journey['methodology']}")
        return

    with open_session(scope) as s:
        entries = _list_entries_for_parent(s, parent_ref)
    if as_json:
        rows = []
        for e in entries:
            sp = e.spec or {}
            rows.append({
                "name": e.name,
                "phase": sp.get("phase"),
                "ref": sp.get("ref"),
                "methodology": sp.get("methodology"),
                "started_at": sp.get("started_at"),
                "ended_at": sp.get("ended_at"),
                "skipped_phases": sp.get("skipped_phases", []),
            })
        print_json(rows)
        return

    if not entries:
        click.secho(f"(no entries for parent_ref={parent_ref!r})", fg="yellow")
        return
    click.secho(f"🧭 journey for {parent_ref}", bold=True)
    for e in entries:
        sp = e.spec or {}
        marker = "▶" if not sp.get("ended_at") else "·"
        skipped = sp.get("skipped_phases") or []
        skip_label = (
            " skipped=" + ",".join(skipped) if skipped else ""
        )
        click.echo(
            f"  {marker} {sp.get('phase'):8} {sp.get('ref'):35} "
            f"[{sp.get('methodology'):11}]{skip_label}"
        )
        if sp.get("summary"):
            click.echo(f"      └ {sp['summary']}")


# ---------------------------------------------------------------------------
# Ouroboros — close one cycle, seed the next discover
# ---------------------------------------------------------------------------

def _build_cycle_seed(holder: Any, reflect_entry: Any) -> str:
    """Build the seed prompt for the next cycle's discover from the
    prior reflect's referenced doc.

    Resolution order:
      1. If reflect.ref points to a Narrative, pull its layered fields
         (paragraphs / decisions / open_items) into a structured
         Portuguese seed block.
      2. If ref points to anything else (Spec/Plan/Story/...), use the
         reflect's `summary` as a one-line seed.
      3. If neither, return a minimal "no prior reflection" placeholder.
    """
    rsp = reflect_entry.spec or {}
    ref = rsp.get("ref") or ""
    summary = rsp.get("summary") or ""

    parts: list[str] = [
        f"=== seed do ciclo anterior (reflect: {reflect_entry.name}) ===",
    ]

    nar_kind = "Narrative"
    if "/" in ref and ref.split("/", 1)[0] == nar_kind:
        nar_name = ref.split("/", 1)[1]
        nar = None
        try:
            nar = holder.get_doc(nar_kind, nar_name)
        except Exception:  # noqa: BLE001
            nar = None
        if nar is not None:
            nspec = nar.spec or {}
            parts.append(f"narrative: {nspec.get('title') or nar.name}")
            paragraphs = nspec.get("paragraphs") or []
            if paragraphs:
                parts.append("")
                parts.append("o que shipou:")
                for p in paragraphs[:3]:
                    parts.append(f"  • {p}")
            decisions = nspec.get("decisions") or []
            if decisions:
                parts.append("")
                parts.append("decisões ratificadas:")
                for d in decisions[:5]:
                    if isinstance(d, dict):
                        line = f"  • {d.get('summary','')}"
                        if d.get("reason"):
                            line += f" — {d['reason']}"
                        parts.append(line)
            open_items = nspec.get("open_items") or []
            if open_items:
                parts.append("")
                parts.append("ainda em aberto (esses estão te caçando):")
                for it in open_items[:10]:
                    if isinstance(it, dict):
                        line = f"  • {it.get('title','')}"
                        if it.get("blocker"):
                            line += f" [blocker: {it['blocker']}]"
                        parts.append(line)

    if len(parts) == 1:
        # Fallback to the reflect entry's own summary.
        if summary:
            parts.append(f"reflexão: {summary}")
        else:
            parts.append("(sem reflexão estruturada do ciclo anterior)")

    parts.append("")
    parts.append("=== começa o próximo ciclo ===")
    return "\n".join(parts)


def _smart_truncate(s: str, max_len: int) -> str:
    """Trim `s` to at most `max_len` chars, breaking on the last
    whitespace before the limit so we don't slice mid-word. Appends
    a single ellipsis when truncation actually happened.
    """
    if len(s) <= max_len:
        return s
    cutoff = s.rfind(" ", 0, max_len)
    if cutoff < max_len // 2:
        # No good word boundary — fall back to hard slice but still
        # mark with ellipsis so the reader knows it's truncated.
        cutoff = max_len
    return s[:cutoff].rstrip(" ,;:.-") + "…"


def _split_first_sentence(text: str) -> tuple[str, str]:
    """Split `text` into (first_sentence, rest) using a sentence-end
    heuristic: a period FOLLOWED BY whitespace (or end-of-string).
    Bare periods inside identifiers like ``reflect.summary`` no longer
    get split. Returns (text, "") when no sentence boundary is found.
    """
    # Match ".", "!", "?" followed by whitespace OR end-of-string.
    m = _re_demand.search(r"[.!?](\s+|$)", text)
    if not m:
        return text.strip(), ""
    end = m.start() + 1  # include the punctuation
    first = text[:end].strip()
    rest = text[m.end():].strip()
    return first, rest


def _collect_closing_cycle(
    entries: list[Any], latest_reflect: Any,
) -> list[Any]:
    """Return the entries that belong to the cycle being closed —
    walks backward from `latest_reflect` (inclusive) until it hits
    the discover that opened this cycle (also inclusive). Mirrors
    the TS `detectCycles` heuristic: a cycle is `[discover ... reflect]`
    bounded by either the start of the list or the previous reflect.
    """
    if latest_reflect not in entries:
        return [latest_reflect]
    end_idx = entries.index(latest_reflect)
    start_idx = 0
    # Walk back: stop at first discover. If we cross another reflect,
    # the cycle starts AFTER that reflect (one step forward).
    crossed_prev_reflect = False
    for i in range(end_idx - 1, -1, -1):
        ph = (entries[i].spec or {}).get("phase")
        if ph == "discover":
            start_idx = i
            break
        if ph == "reflect":
            # We crossed an earlier reflect — cycle starts at i+1.
            start_idx = i + 1
            crossed_prev_reflect = True
            break
    if not crossed_prev_reflect and start_idx == 0 and entries[0] is not entries[end_idx]:
        # No discover found before this reflect — include from start.
        start_idx = 0
    return entries[start_idx:end_idx + 1]


def _synthesize_narrative_from_cycle(
    cycle_entries: list[Any], parent_ref: str,
    insights_snapshot: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build a Narrative doc spec from a list of journey entries forming
    one cycle. Returns (narrative_name, spec_dict).

    The narrative captures the loop biographically: paragraphs derived
    from each phase's summary, decisions extracted from the reflect
    entry, open_items synthesized from skipped phases, period dates
    pulled from first/last entry. covers_features set from parent_ref;
    covers_stories collected from each entry's ref.
    """
    if not cycle_entries:
        raise ValueError("cycle_entries is empty")

    # Order phases for paragraph rendering.
    phase_order = list(VALID_JOURNEY_PHASES)
    by_phase: dict[str, Any] = {}
    for e in cycle_entries:
        ph = (e.spec or {}).get("phase")
        if ph and ph not in by_phase:
            by_phase[ph] = e

    reflect_entry = by_phase.get("reflect")
    first_entry = cycle_entries[0]
    last_entry = cycle_entries[-1]

    # Parse parent_ref ("Feature/f-X" → ("Feature", "f-X"))
    parent_kind = "Feature"
    parent_name = parent_ref
    if "/" in parent_ref:
        parent_kind, parent_name = parent_ref.split("/", 1)

    # Cycle index — count discover-after-reflect transitions in the
    # cycle's first entry's whole-history context. For now, we don't
    # have that context here so use a date-based stamp.
    started_at = (first_entry.spec or {}).get("started_at") or _now_iso()
    ended_at = (
        (reflect_entry.spec or {}).get("ended_at") if reflect_entry else None
    ) or (last_entry.spec or {}).get("ended_at") or _now_iso()

    # Generate name from parent + date.
    date_stamp = started_at[:10].replace("-", "")
    safe_parent = parent_name.replace("/", "-")
    name = f"cycle-{safe_parent}-{date_stamp}"

    # Title: drawn from reflect summary if present, else generic.
    # A "mini-loop" is one where most phases were skipped or silent —
    # render with a different title prefix so the reader knows not to
    # expect a full biographical narrative.
    reflect_summary = (
        (reflect_entry.spec or {}).get("summary") if reflect_entry else None
    )
    feature_label = parent_name.replace("-", " ").replace("f ", "")
    # Count phases that have a non-empty entry summary — those are the
    # ones that will produce a useful paragraph downstream.
    rich_phases = sum(
        1 for e in cycle_entries
        if (e.spec or {}).get("summary") and (e.spec or {}).get("phase")
    )
    is_mini_loop = rich_phases < 3
    cycle_kind_pt = "Mini-loop" if is_mini_loop else "Ciclo"
    if reflect_summary:
        first_sentence, _ = _split_first_sentence(reflect_summary)
        title = _smart_truncate(
            f"{cycle_kind_pt} de {feature_label}: {first_sentence}", 160,
        )
    else:
        title = f"{cycle_kind_pt} de {feature_label} ({started_at[:10]})"

    # paragraphs[] — 1 per phase that has an entry, in canonical order.
    paragraphs: list[str] = []
    methodology_seen: set[str] = set()
    covers_stories: set[str] = set()
    for ph in phase_order:
        e = by_phase.get(ph)
        if not e:
            continue
        spec = e.spec or {}
        method = spec.get("methodology")
        if method:
            methodology_seen.add(method)
        ref = spec.get("ref")
        if ref and isinstance(ref, str) and ref.startswith("Story/"):
            covers_stories.add(ref.split("/", 1)[1])
        summary = spec.get("summary") or ""
        ph_label = {
            "discover": "Descoberta",
            "specify":  "Especificação",
            "plan":     "Planejamento",
            "build":    "Construção",
            "reflect":  "Reflexão",
        }.get(ph, ph)
        if summary:
            paragraphs.append(f"**{ph_label}** — {summary}")
        else:
            paragraphs.append(
                f"**{ph_label}** — fase atravessada sem nota explícita."
            )

    # decisions[] — for v1, the reflect.summary itself is treated as
    # the headline decision of the cycle.
    decisions: list[dict[str, str]] = []
    if reflect_summary:
        first_sent, rest = _split_first_sentence(reflect_summary)
        decisions.append({
            "summary": _smart_truncate(first_sent, 200),
            "reason": _smart_truncate(rest, 400) if rest else "",
        })

    # open_items[] — synthesized from skipped phases across all entries.
    skipped: set[str] = set()
    for e in cycle_entries:
        for sk in (e.spec or {}).get("skipped_phases") or []:
            skipped.add(sk)
    open_items: list[dict[str, str]] = []
    for sk in sorted(skipped):
        ph_label = {
            "discover": "Descoberta", "specify": "Especificação",
            "plan": "Planejamento", "build": "Construção", "reflect": "Reflexão",
        }.get(sk, sk)
        open_items.append({
            "title": f"Fase {ph_label} foi pulada — revisitar se valeu a pena",
            "blocker": "skipped phase",
        })

    # body — markdown rendering. Layout differs for mini-loops: when
    # most phases lacked summaries, rendering 1-2 paragraphs amid 3
    # placeholders ("fase atravessada sem nota") looks padded. We omit
    # the paragraphs section entirely and surface only what's real.
    body_lines: list[str] = []
    body_lines.append(f"# {title}")
    body_lines.append("")
    body_lines.append(
        f"_{'Mini-loop' if is_mini_loop else 'Ciclo'} automático "
        f"de `{parent_ref}` "
        f"({started_at[:10]} → {ended_at[:10]})._"
    )
    body_lines.append("")

    if is_mini_loop:
        # Compact layout: list ONLY the rich phases inline, no headers.
        for ph in phase_order:
            e = by_phase.get(ph)
            if not e:
                continue
            spec_e = e.spec or {}
            summary_e = spec_e.get("summary")
            if not summary_e:
                continue
            ph_label = {
                "discover": "Descoberta", "specify":  "Especificação",
                "plan":     "Planejamento", "build":  "Construção",
                "reflect":  "Reflexão",
            }.get(ph, ph)
            body_lines.append(f"**{ph_label}.** {summary_e}")
            body_lines.append("")
    else:
        # Full layout: every phase as a paragraph (with placeholder fallback).
        for p in paragraphs:
            body_lines.append(p)
            body_lines.append("")

    # Pattern #4 — oracle snapshot inline. When close-cycle pre-fetched
    # current verdicts, render them as a council section so the
    # narrative captures not just what happened but what the system
    # KNEW at close-time. Asimovian: each cycle's record carries the
    # state of ReasoningEngine's wisdom in that moment.
    if insights_snapshot:
        body_lines.append("## Como o Conselho viu este ciclo")
        body_lines.append("")
        for vd in insights_snapshot:
            if vd.get("error") or vd.get("skipped"):
                continue
            verdict_text = vd.get("verdict") or ""
            if not verdict_text:
                continue
            conf = vd.get("confidence") or "?"
            badge_pt = {
                "certain": "✓ certo",
                "guess": "⚠ palpite",
                "insufficient": "❌ sem dados",
            }.get(conf, conf)
            insight_name = vd.get("insight") or vd.get("oracle") or "?"
            # Surface label = market-friendly Insights product names.
            # The persona (O Médico, O Tático, ...) lives in INSIGHT.md
            # body as the VOICE for verdict synthesis; the LABEL here
            # matches the product surface so the narrative reads
            # consistently with /sdlc?g=insights.
            insight_human = {
                # New slugs
                "next-action":       "🎯 Next Best Action",
                "health":            "🩺 Project Health",
                "friction":          "⏱ Time & Friction",
                "focus":             "🪞 Project Focus",
                "risk":              "🌪 Risk Radar",
                "parity":              "🔁 Cross-Stack Parity",
                "docs-drift":          "📚 Documentation Drift",
                "learning-patterns":   "🧠 Retention & Patterns",
                "knowledge-risk":      "🧑‍🤝‍🧑 Knowledge Risk",
                "architecture-drift":  "🏛 Architecture Drift",
                "cleanup-suggestions": "🪦 Cleanup Suggestions",
                "future-scenarios":    "🔮 Future Scenarios",
                # Legacy slugs (pre-rename Narratives, same product label)
                "tactical":    "🎯 Next Best Action",
                "medical":     "🩺 Project Health",
                "auditor":     "⏱ Time & Friction",
                "mirror":      "🪞 Project Focus",
                "oracle":      "🌪 Risk Radar",
            }.get(insight_name, insight_name)
            body_lines.append(f"- **{insight_human}** _{badge_pt}_ — {verdict_text}")
        body_lines.append("")

    if decisions:
        body_lines.append("## Decisões")
        body_lines.append("")
        for d in decisions:
            body_lines.append(f"- **{d['summary']}**")
            if d.get("reason"):
                body_lines.append(f"  _{d['reason']}_")
        body_lines.append("")
    if open_items:
        body_lines.append("## Em aberto")
        body_lines.append("")
        for it in open_items:
            body_lines.append(f"- {it['title']}")
        body_lines.append("")
    body = "\n".join(body_lines)

    spec: dict[str, Any] = {
        "title": title,
        "body": body,
        "period_start": started_at,
        "period_end": ended_at,
        "actor": "claude-code",
        "auto_generated": True,
        "summary": _smart_truncate(reflect_summary, 200) if reflect_summary else (
            f"Ciclo de {feature_label} fechado em {ended_at[:10]}"
        ),
        "covers_features": [parent_name] if parent_kind == "Feature" else [],
        "covers_epics":    [parent_name] if parent_kind == "Epic" else [],
        "covers_stories":  sorted(covers_stories),
        "paragraphs":  paragraphs,
        "decisions":   decisions,
        "open_items":  open_items,
        "author_intent": "retro",
        "tags": sorted({
            "auto-generated", "cycle-close",
            *(["mini-loop"] if is_mini_loop else []),
            *(["with-insights-snapshot"] if insights_snapshot else []),
            *methodology_seen,
        }),
    }
    # insights_snapshot is dropped from spec; lives inline in body markdown
    # AND as raw spec field for programmatic consumers (Studio could
    # render it specially later).
    if insights_snapshot:
        spec["insights_snapshot"] = [
            {
                "insight": v.get("oracle") or v.get("insight"),
                "verdict": v.get("verdict"),
                "confidence": v.get("confidence"),
            }
            for v in insights_snapshot
            if not v.get("error") and not v.get("skipped")
        ]
    return name, spec


@journey_group.command("close-cycle")
@click.argument("parent_ref")
@click.option("--next-summary", default=None,
              help="Optional summary for the new discover entry.")
@click.option("--show-only", is_flag=True,
              help="Print the seed prompt to stdout without writing a "
                   "new entry. Useful for previewing.")
@click.option("--no-narrative", is_flag=True,
              help="Skip the auto-Narrative synthesis. By default a "
                   "retro Narrative is written summarizing the closed cycle.")
@_scope_option
def cmd_journey_close_cycle(
    parent_ref: str, next_summary: str | None, show_only: bool,
    no_narrative: bool, scope: str,
) -> None:
    """Close the current cycle and open the next discover, seeded with
    the prior reflect's lessons.

    The ouroboros bite — reflect feeds discover. After this command,
    the next ``dna sdlc journey transition`` calls will operate on
    cycle N+1.

    Resolution: looks up the latest ``reflect`` entry for
    ``parent_ref``. Pulls its referenced Narrative (paragraphs +
    decisions + open_items) when available; falls back to the entry
    summary. Prints the seed and (unless --show-only) writes a new
    ``discover`` entry with ``seed_from`` set.
    """
    with open_session(scope) as s:  # local kernel — KernelSource needs _loop
        entries = _list_entries_for_parent(s, parent_ref)
        if not entries:
            raise fail(
                f"no journey entries for parent_ref={parent_ref!r}; "
                f"use `journey enter` first."
            )
        # Find the LATEST reflect entry.
        reflect_entries = [
            e for e in entries if (e.spec or {}).get("phase") == "reflect"
        ]
        if not reflect_entries:
            raise fail(
                f"no `reflect` entry on parent {parent_ref!r}. Transition "
                f"to reflect first via `dna sdlc journey transition reflect "
                f"--parent {parent_ref}`."
            )
        latest_reflect = reflect_entries[-1]

        seed_text = _build_cycle_seed(s.holder, latest_reflect)
        click.secho(seed_text, fg="cyan")

        if show_only:
            click.echo("")
            click.secho("(--show-only: nothing written)", fg="yellow")
            return

        # Close the reflect entry if still open.
        now = _now_iso()
        rsp = dict(latest_reflect.spec) if isinstance(latest_reflect.spec, dict) else {}
        if not rsp.get("ended_at"):
            rsp["ended_at"] = now
            rraw = _build_raw("WorkflowEvent", latest_reflect.name, rsp)
            s.run(s.kernel.write_document(scope, "WorkflowEvent", latest_reflect.name, rraw))

        # Build the new discover entry seeded from this reflect.
        next_name = _entry_name(parent_ref, "discover")
        # The new discover ref defaults to the parent itself — until the
        # next phase work picks up a concrete AgentSession / Spec, the
        # parent is a stable anchor.
        next_ref = parent_ref
        summary = next_summary or (
            f"seeded from {latest_reflect.name}; ouroboros bite"
        )
        next_spec: dict[str, Any] = {
            "phase": "discover",
            "ref": next_ref,
            "parent_ref": parent_ref,
            "methodology": "ad-hoc",
            "started_at": now,
            "actor": _cli_actor(),
            "created_at": now,
            "transitioned_from": latest_reflect.name,
            "seed_from": latest_reflect.name,
            "summary": summary,
            "tags": ["seeded"],
        }
        nraw = _build_raw("WorkflowEvent", next_name, next_spec)
        s.run(s.kernel.write_document(scope, "WorkflowEvent", next_name, nraw))

        # Auto-Narrative — synthesize a retro Narrative summarizing the
        # cycle that just closed. Skipped when --no-narrative is passed.
        narrative_written: str | None = None
        if not no_narrative:
            cycle_entries = _collect_closing_cycle(entries, latest_reflect)
            # Pattern #4 — pre-fetch oracle verdicts BEFORE synthesizing
            # the narrative, so the Narrative captures the council's
            # snapshot at close-time. Soft-fail: if insights errors,
            # close-cycle still succeeds; narrative just lacks the
            # oracle section.
            # (oracle snapshot is a host-platform surface)
            insights_snapshot: list[dict] | None = None
            try:
                nname, nspec = _synthesize_narrative_from_cycle(
                    cycle_entries, parent_ref,
                    insights_snapshot=insights_snapshot,
                )
                # Avoid clobbering an existing Narrative with same name —
                # if it exists, suffix with -2, -3, etc.
                existing = s.get_doc("Narrative", nname)
                if existing is not None:
                    suffix = 2
                    while s.get_doc("Narrative", f"{nname}-{suffix}") is not None:
                        suffix += 1
                    nname = f"{nname}-{suffix}"
                nraw = _build_raw("Narrative", nname, nspec)
                s.run(s.kernel.write_document(scope, "Narrative", nname, nraw))
                narrative_written = nname
            except Exception as exc:  # noqa: BLE001
                # Soft-fail: cycle close succeeded, narrative is best-effort.
                click.secho(
                    f"⚠ Narrative auto-write failed: {exc} "
                    f"(cycle was still closed and seeded)",
                    fg="yellow",
                )

    click.echo("")
    click.secho(
        f"CLOSED-AND-SEEDED: cycle ended, next discover opened at "
        f"WorkflowEvent/{next_name} (seed_from={latest_reflect.name})",
        fg="green",
    )
    if narrative_written:
        click.secho(
            f"📜 Narrative written: Narrative/{narrative_written}",
            fg="green",
        )

    # (S7 dream verification is a host-platform surface)

    click.echo("")
    click.echo("Hint: paste the seed above into your next chat / AgentSession")
    click.echo("to inherit the prior cycle's lessons mechanically.")


# ─────────────────────────────────────────────────────────────────────
# `dna sdlc demand` — one-shot demand intake.
#
# Replaces the manual: story create → journey enter discover → story start
# (3 commands) with a single call. The agent's `dna-demand-flow` skill
# uses this as the entry point of every demand-driven session, so the
# Board / Journey / Narrative are wired up at the same instant.
# ─────────────────────────────────────────────────────────────────────

import re as _re_demand
import hashlib as _hashlib_demand


_DEMAND_STOPWORDS = {
    # pt-BR connective noise that fattens slugs without semantic value
    "do", "da", "de", "dos", "das", "no", "na", "nos", "nas",
    "em", "para", "pra", "pro", "com", "por", "o", "a", "os", "as",
    "e", "ou", "um", "uma", "uns", "umas", "que", "se", "ao",
    # English equivalents (mixed pt/en titles are common)
    "the", "of", "in", "on", "at", "to", "for", "and", "or",
    "a", "an", "is", "be",
}


def _slugify_demand_title(title: str) -> str:
    """Lowercase, strip non-alnum, hyphenate, drop pt-BR/en stopwords.
    Caps the meaningful portion at ~28 chars and appends a 3-char hash
    so two near-identical titles still resolve to distinct slugs.
    """
    # Hyphenate non-alnum runs.
    base = _re_demand.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    # Drop stopwords token by token, preserving order.
    tokens = [t for t in base.split("-") if t and t not in _DEMAND_STOPWORDS]
    cleaned = "-".join(tokens)
    cleaned = cleaned[:28].rstrip("-")
    # 3-char hash is plenty for typical session-scope uniqueness.
    h = _hashlib_demand.sha1(title.encode("utf-8")).hexdigest()[:3]
    return f"s-{cleaned}-{h}" if cleaned else f"s-demand-{h}"


@sdlc.command("demand")
@click.argument("title")
@click.option("--feature", required=True,
              help="Parent Feature name (must exist in scope).")
@click.option("--desc", "description", default=None,
              help="Multi-line description. Defaults to TITLE if omitted.")
@click.option("--methodology",
              type=click.Choice(VALID_JOURNEY_METHODOLOGIES),
              default="superpowers", show_default=True,
              help="Method the agent will follow.")
@click.option("--slug", "slug_override", default=None,
              help="Force a specific Story slug (auto-derived from title otherwise).")
@click.option("--owner", default="claude-code", show_default=True)
@click.option("--priority", type=click.Choice(VALID_PRIORITIES), default=None)
@click.option("--reporter", default=None,
              help="Who filed the demand (defaults to actor).")
@click.option("--artifact", default=None,
              help="Optional path/URL to a methodology artifact (e.g. spec/plan).")
@click.option("--epic", "epic_ref", default=None,
              help="Auto-create the Feature under this Epic if missing (else fails loud).")
@click.option("--json", "as_json", is_flag=True,
              help="Emit machine-readable JSON with the created IDs.")
@click.option("--consult", is_flag=True,
              help="Consult the Tático oracle before creating the Story. "
                   "Surfaces divergence between user intent and pattern "
                   "the system observes — doesn't block.")
# User-story slots (2026-05-11 UX audit). When all three of as/want/so-that
# are provided, `description` is auto-composed unless --desc is also given.
@click.option("--as", "as_a", default=None,
              help="User-story 'As a <role>' slot.")
@click.option("--want", "i_want", default=None,
              help="User-story 'I want <goal>' slot.")
@click.option("--so-that", "so_that", default=None,
              help="User-story 'so that <benefit>' slot.")
@click.option("--accept", "acceptance_criteria", multiple=True,
              help="Acceptance criterion (repeatable). One bullet per --accept.")
@click.option("--dod", "definition_of_done", multiple=True,
              help="Definition-of-Done check (repeatable). One bullet per --dod.")
@_scope_option
def cmd_demand(
    title: str, feature: str, description: str | None, methodology: str,
    slug_override: str | None, owner: str, priority: str | None,
    reporter: str | None, artifact: str | None,
    epic_ref: str | None, as_json: bool, consult: bool,
    as_a: str | None, i_want: str | None, so_that: str | None,
    acceptance_criteria: tuple[str, ...], definition_of_done: tuple[str, ...],
    scope: str,
) -> None:
    """Open a demand: Story + journey-discover + status=in-progress, atomic.

    The single entry point the agent's `dna-demand-flow` skill uses to
    file new work. Equivalent to running `story create` → `story start`
    → `journey enter discover` in one shot, with consistent IDs and a
    single timestamp for the trail across Board / Journey.
    """
    now = _now_iso()
    story_slug = slug_override or _slugify_demand_title(title)

    # Compose the user-story sentence from slots when at least two are
    # provided. If --desc is ALSO given, prepend the sentence and keep
    # --desc as the "Detalhes" block below.
    user_story_sentence: str | None = None
    if as_a or i_want or so_that:
        parts = []
        if as_a:
            parts.append(f"**Como** {as_a}")
        if i_want:
            parts.append(f"**eu quero** {i_want}")
        if so_that:
            parts.append(f"**para** {so_that}")
        user_story_sentence = ", ".join(parts) + "."

    if user_story_sentence and description:
        desc = f"{user_story_sentence}\n\n{description}"
    elif user_story_sentence:
        desc = user_story_sentence
    elif description:
        desc = description
    else:
        desc = title

    # Pattern #1 — pre-INTAKE consultation. Asks the Tático oracle for
    # its current suggestion BEFORE creating the Story. Doesn't block;
    # just surfaces divergence so the user knows what the system
    # observed vs what they're now asking for.
    if consult:
        click.secho(
            "  (--consult is a host-platform surface — seguindo sem consulta.)",
            fg="yellow",
        )

    with open_session(scope) as s:
        # 0) Verify (or auto-create) the Feature.
        feat = s.get_doc("Feature", feature)
        if feat is None:
            if not epic_ref:
                raise fail(
                    f"Feature/{feature!r} not found in scope {scope!r}. "
                    f"Pass --epic <e-id> to auto-create, or run "
                    f"`dna sdlc list Feature` to find the right one."
                )
            feat_spec: dict[str, Any] = {
                "title": feature.replace("-", " ").title(),
                "description": f"Auto-created by `sdlc demand` for {story_slug}.",
                "status": "discovery",
                "epic": epic_ref,
                "owner": owner,
                "created_at": now,
                "updated_at": now,
            }
            _append_timeline(feat_spec, "status_change", to="discovery")
            feat_raw = _build_raw("Feature", feature, feat_spec)
            s.run(s.kernel.write_document(scope, "Feature", feature, feat_raw))
            click.secho(
                f"AUTO-CREATED Feature/{feature} (epic: {epic_ref})",
                fg="yellow",
            )

        # 1) Create the Story directly in `in-progress` — the agent is
        #    actively working on it the moment `demand` is called.
        story_spec: dict[str, Any] = {
            "title": title[:80],
            "description": desc,
            "status": "in-progress",
            "feature": feature,
            "owner": owner,
            "created_at": now,
            "updated_at": now,
        }
        # Persist user-story slots so the Studio Board can render them
        # as their own labelled sections (not just embedded in description).
        if as_a:
            story_spec["as_a"] = as_a
        if i_want:
            story_spec["i_want"] = i_want
        if so_that:
            story_spec["so_that"] = so_that
        if acceptance_criteria:
            story_spec["acceptance_criteria"] = list(acceptance_criteria)
        if definition_of_done:
            story_spec["definition_of_done"] = list(definition_of_done)
        # 2026-05-11 UX audit: when user-story slots provided but AC/DoD
        # omitted, ask the analyst scribe to infer them. Falls back to
        # empty when no LLM (test envs); user can always pass explicit
        # --accept/--dod to override.
        # (LLM AC/DoD synthesis is a host-platform surface — pass
        # explicit --accept/--dod.)
        if priority:
            story_spec["priority"] = priority
        if reporter:
            story_spec["reporter"] = reporter
        # Two timeline events: file (todo) → start (in-progress), so the
        # board sees both transitions even though we collapse into one call.
        _append_timeline(story_spec, "status_change", to="todo")
        story_spec["timeline"][-1]["at"] = now
        _append_timeline(story_spec, "status_change", **{"from": "todo", "to": "in-progress"})

        story_raw = _build_raw("Story", story_slug, story_spec)
        s.run(s.kernel.write_document(scope, "Story", story_slug, story_raw))

        # 2) Open the discover WorkflowEvent referencing the new Story.
        parent_ref = f"Feature/{feature}"
        story_ref = f"Story/{story_slug}"
        entry_name = _entry_name(parent_ref, "discover")
        entry_spec: dict[str, Any] = {
            "phase": "discover",
            "ref": story_ref,
            "parent_ref": parent_ref,
            "methodology": methodology,
            "started_at": now,
            "actor": _cli_actor(),
            "created_at": now,
            "summary": f"Demanda aberta: {title}",
        }
        if artifact:
            entry_spec["methodology_artifact"] = artifact

        # If a previous entry on this parent was open (last cycle's reflect
        # not yet closed), close it now — keeps the ledger linked.
        prev_entries = _list_entries_for_parent(s, parent_ref)
        prev_open = next(
            (e for e in reversed(prev_entries) if not (e.spec or {}).get("ended_at")),
            None,
        )
        if prev_open is not None:
            psp = dict(prev_open.spec) if isinstance(prev_open.spec, dict) else {}
            psp["ended_at"] = now
            praw = _build_raw("WorkflowEvent", prev_open.name, psp)
            s.run(s.kernel.write_document(scope, "WorkflowEvent", prev_open.name, praw))
            entry_spec["transitioned_from"] = prev_open.name

        entry_raw = _build_raw("WorkflowEvent", entry_name, entry_spec)
        s.run(s.kernel.write_document(scope, "WorkflowEvent", entry_name, entry_raw))

    if as_json:
        import json
        click.echo(json.dumps({
            "story": story_slug,
            "story_ref": story_ref,
            "feature": feature,
            "feature_ref": parent_ref,
            "workflow_event": entry_name,
            "methodology": methodology,
            "phase": "discover",
            "started_at": now,
        }, indent=2))
        return

    click.secho("─" * 60, fg="cyan")
    click.secho("DEMAND OPENED", fg="green", bold=True)
    click.secho("─" * 60, fg="cyan")
    click.echo(f"  Story         Story/{story_slug}")
    click.echo(f"  Status        in-progress")
    click.echo(f"  Feature       Feature/{feature}")
    click.echo(f"  Phase         discover")
    click.echo(f"  Methodology   {methodology}")
    click.echo(f"  Journey Entry WorkflowEvent/{entry_name}")
    click.echo("")
    click.secho("Next steps for the agent (see skill `dna-demand-flow`):", fg="yellow")
    click.echo(
        "  1. specify  — define o quê / critérios de aceite\n"
        "  2. plan     — desenhe o passo-a-passo (docs/superpowers/plans/...)\n"
        "  3. build    — código + testes\n"
        "  4. reflect  — o que aprendeu, o que muda no próximo loop\n"
        "  5. close-cycle — fecha o ouroboros, semeia próximo discover\n"
    )
    click.echo("Move via: dna sdlc journey transition <next_phase> "
               f"--parent {parent_ref}")


# (The cognitive verbs — insights / deep-sleep / forget / remember /
# reflect — are host-platform surfaces backed by the cognition engine
# family and do not ship in this kernel-local distribution.)
