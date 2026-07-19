"""Derived journey (s-journey-derived).

The journey of a Story is a PURE FUNCTION of its own state (timeline + status +
created/closed timestamps) plus its linked artifacts (Spec via ``spec_refs``,
Plan via a story ref, Engram via ``source_refs``). It is computed on read
— never written — so the per-Story phase trajectory auto-fills as the Story
progresses, with zero manual upkeep.

Consumers (single source of truth, no drift):
  - ``GET /scopes/{scope}/journey`` (kinds-api) computes derived trajectories and
    overlays any explicit WorkflowEvent docs (methodology/gates) on top.
  - ``dna sdlc journey show/list`` (CLI) calls the same function.
  - Studio JourneyMiniSection / JourneyView render the endpoint output.

The 5 phases are the universal SDLC arc; ``skipped`` marks a phase with no signal
that nonetheless sits before a phase that DID happen (honest record of a jump).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .work_item_outputs import resolve_work_item_outputs

# Mirror of JOURNEY_PHASES in the SDLC extension; kept local so this module has
# no import cycle with the heavy extension package. ``verify`` (s-decompose-jarvis
# follow-up) sits between build and reflect: a linked TestRun lights it.
JOURNEY_PHASES: tuple[str, ...] = ("discover", "specify", "plan", "build", "verify", "reflect")


@dataclass
class DerivedPhase:
    phase: str
    present: bool
    at: str | None = None
    evidence: str = ""
    source_ref: str | None = None
    skipped: bool = False


@dataclass
class DerivedJourney:
    ref: str
    phases: list[DerivedPhase] = field(default_factory=list)
    active_phase: str | None = None
    methodology: str | None = None


def _spec_of(doc: Mapping[str, Any]) -> Mapping[str, Any]:
    inner = doc.get("spec")
    return inner if isinstance(inner, Mapping) else {}


def _as_list(v: Any) -> list[Any]:
    if isinstance(v, list):
        return v
    if v:
        return [v]
    return []


def _first_timeline_at(timeline: Sequence[Any], *to_statuses: str) -> str | None:
    """Earliest timeline status_change `at` whose `to` is one of to_statuses."""
    hits: list[str] = []
    for ev in timeline:
        if not isinstance(ev, Mapping):
            continue
        if ev.get("type") == "status_change" and ev.get("to") in to_statuses:
            at = ev.get("at")
            if isinstance(at, str) and at:
                hits.append(at)
    return min(hits) if hits else None


def derive_story_journey(
    story_name: str,
    story_spec: Mapping[str, Any],
    *,
    specs: Sequence[Mapping[str, Any]] = (),
    plans: Sequence[Mapping[str, Any]] = (),
    lessons: Sequence[Mapping[str, Any]] = (),
    test_runs: Sequence[Mapping[str, Any]] = (),
) -> DerivedJourney:
    """Compute the 6-phase derived journey for one Story.

    ``story_spec`` is the Story's ``spec`` dict. ``specs``/``plans``/``lessons``/
    ``test_runs`` are candidate linked docs, each shaped ``{"name": str, "spec":
    dict}``; only the ones that actually reference this Story contribute.
    """
    ref = f"Story/{story_name}"
    status = str(story_spec.get("status") or "")
    created_at = story_spec.get("created_at") if isinstance(story_spec.get("created_at"), str) else None
    closed_at = story_spec.get("closed_at") if isinstance(story_spec.get("closed_at"), str) else None
    updated_at = story_spec.get("updated_at") if isinstance(story_spec.get("updated_at"), str) else None
    timeline = _as_list(story_spec.get("timeline"))

    # Unified outputs (produces[] ∪ legacy) — the hub view feeds phase signals.
    outputs = resolve_work_item_outputs(story_name, story_spec, plans=plans, lessons=lessons)

    def _output(*kinds: str, role: str | None = None) -> dict[str, Any] | None:
        for o in outputs:
            if o["kind"] in kinds and (role is None or o.get("role") == role):
                return o
        return None

    # ── discover ─────────────────────────────────────────────────────
    disc_at = created_at or _first_timeline_at(timeline, "todo", "needs-triage") or None
    discover = DerivedPhase(
        phase="discover",
        present=True,  # the Story exists → discovery happened
        at=disc_at,
        evidence=f"criada {disc_at[:10]}" if disc_at else "story criada",
    )

    # ── specify ──────────────────────────────────────────────────────
    ac = _as_list(story_spec.get("acceptance_criteria"))
    dod = _as_list(story_spec.get("definition_of_done"))
    spec_refs = [s for s in _as_list(story_spec.get("spec_refs")) if isinstance(s, str)]
    linked_spec_name = spec_refs[0] if spec_refs else None
    spec_at: str | None = None
    if linked_spec_name:
        for sd in specs:
            if sd.get("name") == linked_spec_name:
                c = _spec_of(sd).get("created_at")
                spec_at = c if isinstance(c, str) else None
                break
    # produces[] fallback: a spec-like output (Spec/ADR/Research, or an
    # HtmlArtifact acting as a visual spec) lights specify too.
    spec_out = _output("Spec", "ADR", "Research") or next(
        (o for o in outputs if o["kind"] == "HtmlArtifact" and o.get("role") in (None, "visual-spec")),
        None,
    )
    if spec_refs:
        specify = DerivedPhase(
            phase="specify", present=True, at=spec_at,
            evidence=f"Spec/{linked_spec_name}", source_ref=f"Spec/{linked_spec_name}",
        )
    elif ac or dod:
        specify = DerivedPhase(
            phase="specify", present=True, at=None,
            evidence=f"{len(ac)} AC + {len(dod)} DoD",
        )
    elif spec_out is not None:
        _ref = f"{spec_out['kind']}/{spec_out['name']}"
        specify = DerivedPhase(
            phase="specify", present=True, at=spec_out.get("at"),
            evidence=_ref, source_ref=_ref,
        )
    else:
        specify = DerivedPhase(phase="specify", present=False, evidence="sem AC/DoD nem Spec")

    # ── plan ─────────────────────────────────────────────────────────
    linked_plan: Mapping[str, Any] | None = None
    for pd in plans:
        ps = _spec_of(pd)
        if story_name in {ps.get("story_ref"), ps.get("story"), ps.get("parent_ref")}:
            linked_plan = pd
            break
    # produces[] fallback: an explicit Plan output, or an HtmlArtifact tagged
    # role=plan, lights plan even without the `plans` param.
    plan_out = _output("Plan") or _output("HtmlArtifact", role="plan")
    plan_skip_reason = story_spec.get("plan_skip_reason")
    if linked_plan is not None:
        _lps = _spec_of(linked_plan)
        plan_at = _lps.get("created_at")
        _meth = _lps.get("methodology")
        _ev = f"Plan/{linked_plan.get('name')}"
        if isinstance(_meth, str) and _meth:
            _ev += f" · via {_meth}"
        plan = DerivedPhase(
            phase="plan", present=True,
            at=plan_at if isinstance(plan_at, str) else None,
            evidence=_ev,
            source_ref=f"Plan/{linked_plan.get('name')}",
        )
    elif plan_out is not None:
        _pref = f"{plan_out['kind']}/{plan_out['name']}"
        plan = DerivedPhase(
            phase="plan", present=True, at=plan_out.get("at"),
            evidence=_pref, source_ref=_pref,
        )
    elif isinstance(plan_skip_reason, str) and plan_skip_reason:
        # Conscious skip recorded at `story start --no-plan --skip-reason`.
        # Stays absent (skipped) but the journey shows WHY — honest, not silent.
        plan = DerivedPhase(
            phase="plan", present=False,
            evidence=f"pulada conscientemente: {plan_skip_reason}",
        )
    else:
        plan = DerivedPhase(phase="plan", present=False, evidence="sem Plan linkado")

    # ── build ────────────────────────────────────────────────────────
    in_prog_at = _first_timeline_at(timeline, "in-progress", "review")
    commit = story_spec.get("commit_ref")
    commit = commit if isinstance(commit, str) and commit else None
    built = bool(in_prog_at) or bool(commit) or status in {"in-progress", "review", "done"}
    if built:
        if commit:
            build_ev = f"commit {commit[:7]}"
        elif in_prog_at:
            build_ev = "em desenvolvimento"
        else:
            build_ev = "em desenvolvimento"
        build = DerivedPhase(
            phase="build", present=True,
            at=in_prog_at or updated_at,
            evidence=build_ev,
            source_ref=None,
        )
    else:
        build = DerivedPhase(phase="build", present=False, evidence="não iniciada")

    # ── reflect ──────────────────────────────────────────────────────
    linked_lesson: Mapping[str, Any] | None = None
    for ld in lessons:
        refs = [r for r in _as_list(_spec_of(ld).get("source_refs")) if isinstance(r, str)]
        if ref in refs:
            linked_lesson = ld
            break
    is_done = status == "done" or bool(closed_at)
    if linked_lesson is not None:
        lesson_at = _spec_of(linked_lesson).get("created_at")
        reflect = DerivedPhase(
            phase="reflect", present=True,
            at=closed_at or (lesson_at if isinstance(lesson_at, str) else None),
            evidence=f"Engram/{linked_lesson.get('name')}",
            source_ref=f"Engram/{linked_lesson.get('name')}",
        )
    elif is_done:
        reflect = DerivedPhase(
            phase="reflect", present=True, at=closed_at,
            evidence=f"fechada {closed_at[:10]}" if closed_at else "concluída",
        )
    else:
        reflect = DerivedPhase(phase="reflect", present=False, evidence="ainda aberta")

    # ── verify ───────────────────────────────────────────────────────
    # A TestRun lights verify — linked via produces[] OR via the run's own
    # `verifies` back-ref to this Story. Outcome (pass/fail/partial/blocked)
    # comes from the run's spec (outputs[] carry only kind/name/role/at).
    run_out = _output("TestRun")
    verify_run: Mapping[str, Any] | None = None
    if run_out is not None:
        verify_run = next((tr for tr in test_runs if tr.get("name") == run_out["name"]), None)
    if verify_run is None:
        verify_run = next(
            (tr for tr in test_runs
             if ref in [v for v in _as_list(_spec_of(tr).get("verifies")) if isinstance(v, str)]),
            None,
        )
    if verify_run is not None or run_out is not None:
        _vname = (verify_run.get("name") if verify_run else None) or (run_out["name"] if run_out else "?")
        _outcome = str(_spec_of(verify_run).get("outcome") or "") if verify_run else ""
        _vat = run_out.get("at") if run_out else None
        if not _vat and verify_run is not None:
            _ea = _spec_of(verify_run).get("executed_at")
            _vat = _ea if isinstance(_ea, str) else None
        verify = DerivedPhase(
            phase="verify", present=True, at=_vat,
            evidence=f"TestRun/{_vname}" + (f" → {_outcome}" if _outcome else ""),
            source_ref=f"TestRun/{_vname}",
        )
    else:
        verify = DerivedPhase(phase="verify", present=False, evidence="sem TestRun")

    phases = [discover, specify, plan, build, verify, reflect]

    # ── skipped: an absent phase that precedes a present one ─────────
    last_present_idx = max((i for i, p in enumerate(phases) if p.present), default=-1)
    for i, p in enumerate(phases):
        if not p.present and i < last_present_idx:
            p.skipped = True

    # ── active phase: latest present phase while the story is open ───
    active_phase: str | None = None
    if not is_done and last_present_idx >= 0:
        active_phase = phases[last_present_idx].phase

    return DerivedJourney(ref=ref, phases=phases, active_phase=active_phase)


# ── Issue lifecycle arc (distinct from the Story 5-phase arc) ────────
# Issues don't have specify/plan; they have a market-aligned ticket
# lifecycle. Derived from the issue's own signals.
ISSUE_PHASES: tuple[str, ...] = ("report", "triage", "fix", "resolve")

_ISSUE_OPEN = {"open"}
_ISSUE_PAST_OPEN = {"triaged", "in-progress", "resolved", "wont-fix", "duplicate"}
_ISSUE_FIXING = {"in-progress", "resolved"}
_ISSUE_RESOLVED = {"resolved", "wont-fix", "duplicate"}


def derive_issue_journey(issue_name: str, issue_spec: Mapping[str, Any]) -> DerivedJourney:
    """Compute the report→triage→fix→resolve arc for one Issue."""
    ref = f"Issue/{issue_name}"
    status = str(issue_spec.get("status") or "")
    created_at = issue_spec.get("created_at") if isinstance(issue_spec.get("created_at"), str) else None
    closed_at = issue_spec.get("closed_at") if isinstance(issue_spec.get("closed_at"), str) else None
    updated_at = issue_spec.get("updated_at") if isinstance(issue_spec.get("updated_at"), str) else None
    timeline = _as_list(issue_spec.get("timeline"))

    # report — the issue exists.
    report = DerivedPhase(
        phase="report", present=True, at=created_at,
        evidence=f"reportada {created_at[:10]}" if created_at else "reportada",
    )

    # triage — assessed: moved past open, OR severity+type set, OR a repro /
    # expected/actual described (that's the issue's specification).
    sev = issue_spec.get("severity")
    typ = issue_spec.get("type")
    repro = _as_list(issue_spec.get("reproduction_steps"))
    described = bool(repro) or bool(issue_spec.get("expected_behavior")) or bool(issue_spec.get("actual_behavior"))
    if status in _ISSUE_PAST_OPEN:
        triage = DerivedPhase(phase="triage", present=True, evidence="triada")
    elif sev and typ:
        triage = DerivedPhase(phase="triage", present=True, evidence=f"{sev}/{typ}")
    elif described:
        triage = DerivedPhase(phase="triage", present=True, evidence="repro/comportamento descrito")
    else:
        triage = DerivedPhase(phase="triage", present=False, evidence="sem triagem")

    # fix — being worked: in-progress/resolved, OR a commit, OR timeline flip.
    commit = issue_spec.get("commit_ref")
    commit = commit if isinstance(commit, str) and commit else None
    in_prog_at = _first_timeline_at(timeline, "in-progress")
    fixing = status in _ISSUE_FIXING or bool(commit) or bool(in_prog_at)
    if fixing:
        fix = DerivedPhase(
            phase="fix", present=True, at=in_prog_at or updated_at,
            evidence=f"commit {commit[:7]}" if commit else "em correção",
        )
    else:
        fix = DerivedPhase(phase="fix", present=False, evidence="não iniciada")

    # resolve — resolved/wont-fix/duplicate, OR closed_at, OR a resolution.
    resolution = issue_spec.get("resolution")
    resolution = resolution if isinstance(resolution, str) and resolution else None
    is_resolved = status in _ISSUE_RESOLVED or bool(closed_at)
    if resolution or is_resolved:
        resolve = DerivedPhase(
            phase="resolve", present=True, at=closed_at,
            evidence=resolution or (f"{status}" if status else "resolvida"),
        )
    else:
        resolve = DerivedPhase(phase="resolve", present=False, evidence="aberta")

    phases = [report, triage, fix, resolve]
    last_present = max((i for i, p in enumerate(phases) if p.present), default=-1)
    for i, p in enumerate(phases):
        if not p.present and i < last_present:
            p.skipped = True
    active_phase = None
    if not is_resolved and last_present >= 0:
        active_phase = phases[last_present].phase
    return DerivedJourney(ref=ref, phases=phases, active_phase=active_phase)


# ── Spike investigation arc (distinct from Story + Issue) ───────────
# A Spike is a time-boxed investigation, NOT shippable work — it has no
# specify/plan/build. Its arc: propose → investigate → findings → handoff.
SPIKE_PHASES: tuple[str, ...] = ("propose", "investigate", "findings", "handoff")

_SPIKE_STARTED = {"in-progress", "answered", "abandoned"}
_SPIKE_TERMINAL = {"answered", "abandoned"}


def derive_spike_journey(spike_name: str, spike_spec: Mapping[str, Any]) -> DerivedJourney:
    """Compute the propose→investigate→findings→handoff arc for one Spike."""
    ref = f"Spike/{spike_name}"
    status = str(spike_spec.get("status") or "")
    created_at = spike_spec.get("created_at") if isinstance(spike_spec.get("created_at"), str) else None
    completed_at = spike_spec.get("completed_at") if isinstance(spike_spec.get("completed_at"), str) else None
    timeline = _as_list(spike_spec.get("timeline"))

    # propose — the spike exists.
    propose = DerivedPhase(
        phase="propose", present=True, at=created_at,
        evidence=f"proposta {created_at[:10]}" if created_at else "proposta",
    )

    # investigate — started: in-progress (or beyond), OR time logged, OR a
    # comment/decision on the timeline, OR linked research/artifacts (work
    # that happened even if the status lags).
    logged = spike_spec.get("logged_hours")
    logged = float(logged) if isinstance(logged, (int, float)) else 0.0
    has_notes = any(
        isinstance(e, Mapping) and e.get("type") in ("comment", "decision")
        for e in timeline
    )
    has_artifacts = bool(
        _as_list(spike_spec.get("research_refs"))
        or _as_list(spike_spec.get("html_artifacts"))
        or _as_list(spike_spec.get("references"))
    )
    in_prog_at = _first_timeline_at(timeline, "in-progress")
    investigating = (
        status in _SPIKE_STARTED or logged > 0 or has_notes or has_artifacts
    )
    if investigating:
        if logged > 0:
            ev = f"{logged:g}h investigadas"
        elif has_artifacts:
            ev = "evidências anexadas"
        else:
            ev = "investigando"
        investigate = DerivedPhase(
            phase="investigate", present=True, at=in_prog_at, evidence=ev,
        )
    else:
        investigate = DerivedPhase(phase="investigate", present=False, evidence="não iniciada")

    # findings — answered, OR a findings/recommendation written.
    findings_text = spike_spec.get("findings")
    findings_text = findings_text if isinstance(findings_text, str) and findings_text else None
    recommendation = spike_spec.get("recommendation")
    has_recommendation = isinstance(recommendation, str) and bool(recommendation)
    if findings_text or has_recommendation or status == "answered":
        findings = DerivedPhase(
            phase="findings", present=True, at=completed_at,
            evidence=(findings_text[:60] if findings_text else "respondida"),
        )
    else:
        findings = DerivedPhase(phase="findings", present=False, evidence="sem findings")

    # handoff — points at a follow-up Spec / ADR / Story (the spike's outcome).
    def _ref(key: str) -> str | None:
        v = spike_spec.get(key)
        return v if isinstance(v, str) and v else None

    fu = _ref("follow_up_spec") or _ref("follow_up_adr") or _ref("follow_up_story")
    if fu:
        handoff = DerivedPhase(phase="handoff", present=True, evidence=f"→ {fu}")
    else:
        handoff = DerivedPhase(phase="handoff", present=False, evidence="sem handoff")

    phases = [propose, investigate, findings, handoff]
    last_present = max((i for i, p in enumerate(phases) if p.present), default=-1)
    for i, p in enumerate(phases):
        if not p.present and i < last_present:
            p.skipped = True
    active_phase = None
    if status not in _SPIKE_TERMINAL and last_present >= 0:
        active_phase = phases[last_present].phase
    return DerivedJourney(ref=ref, phases=phases, active_phase=active_phase)


# ── dispatcher: the one place that maps a work-item Kind to its arc ──
def derive_journey(
    kind: str,
    name: str,
    spec: Mapping[str, Any],
    *,
    specs: Sequence[Mapping[str, Any]] = (),
    plans: Sequence[Mapping[str, Any]] = (),
    lessons: Sequence[Mapping[str, Any]] = (),
    test_runs: Sequence[Mapping[str, Any]] = (),
) -> DerivedJourney:
    """Kind-aware journey: Issue → report/triage/fix/resolve;
    Spike → propose/investigate/findings/handoff; Story/etc.
    → discover/specify/plan/build/verify/reflect. Single source so every surface
    (FOCUS, /journey ledger, CLI) renders the right arc with no drift."""
    if kind == "Issue":
        return derive_issue_journey(name, spec)
    if kind == "Spike":
        return derive_spike_journey(name, spec)
    return derive_story_journey(
        name, spec, specs=specs, plans=plans, lessons=lessons, test_runs=test_runs,
    )
