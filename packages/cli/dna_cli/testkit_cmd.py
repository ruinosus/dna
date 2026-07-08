"""`dna sdlc test-guide` + `dna sdlc test-run` — CLI for the testkit Kinds.

Phase C of the TESTS-as-first-class-SDLC work. Registers two subgroups on the
existing ``sdlc`` group (kept in its own module so the 7k-line sdlc_cmd.py
god-file doesn't grow):

  - ``dna sdlc test-guide create`` — author a TestGuide (manual, or stub the
    steps from a Story's acceptance_criteria via ``--from-ac``).
  - ``dna sdlc test-run record`` — record a TestRun execution. This is the
    FOCUS-visible moment: it stamps an ``artifact_produced`` event on each
    verified Story's timeline + appends to its ``produces[]`` hub, so the run
    shows in FOCUS and lights the journey's ``verify`` phase.

The ``story done`` test-gate WARNING lives inline in sdlc_cmd.py (avoids an
import cycle); ``passing_run_for_story`` here is the shared predicate.
"""
from __future__ import annotations

from typing import Any

import click

from dna_cli._ctx import dna_session, fail
from dna_cli.sdlc_cmd import (
    DEFAULT_SCOPE,
    _append_produces,
    _append_timeline,
    _cli_actor,
    _now_iso,
    _scope_option,
    sdlc,
)

TESTKIT_API_VERSION = "github.com/ruinosus/dna/testkit/v1"

_TEST_KINDS = ["manual", "smoke", "e2e", "regression", "integration"]
_OUTCOMES = ["pass", "fail", "partial", "blocked"]


def _build_testkit_raw(kind: str, name: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "apiVersion": TESTKIT_API_VERSION,
        "kind": kind,
        "metadata": {"name": name},
        "spec": spec,
    }


def _ac_text(ac: Any) -> str:
    """Acceptance-criteria entries are either ``{"text": ...}`` dicts or bare
    strings — normalize to the text."""
    if isinstance(ac, dict):
        return str(ac.get("text") or ac.get("criterion") or "").strip()
    return str(ac or "").strip()


def _ref_story_name(ref: str) -> str | None:
    """``Story/s-x`` → ``s-x``; a bare ``s-x`` passes through; non-Story refs
    (Issue/...) return None (only Stories carry the produces/timeline hub here)."""
    ref = ref.strip()
    if "/" in ref:
        kind, _, nm = ref.partition("/")
        return nm if kind == "Story" else None
    return ref or None


# ── passing-run predicate (shared with the story-done gate) ─────────────────

def passing_run_for_story(scope: str, story_name: str) -> str | None:
    """Return the name of a PRODUCT-lane TestRun with outcome=pass that verifies
    this Story, or None.

    s-testkit-done-requires-product-smoke: the ``story done`` gate counts only
    the HUMAN product lane (a TestRun whose guide is ``smoke`` or ``manual``).
    The automated lane (integration/e2e/regression) is proven by CI on the PR,
    not by a hand-recorded run — so an integration ``pass`` does NOT satisfy the
    gate. A run whose guide can't be resolved is treated as non-product (the
    gate stays honest)."""
    from dna.extensions.testkit import PRODUCT_TEST_KINDS

    ref = f"Story/{story_name}"
    try:
        with dna_session(scope) as s:
            runs = s.query_list("TestRun")
            guides = s.query_list("TestGuide")
    except Exception:  # noqa: BLE001 — gate is best-effort
        return None
    product_guides = {
        g.name for g in guides
        if str(((g.spec if isinstance(getattr(g, "spec", None), dict) else {}) or {}).get("kind_of_test"))
        in PRODUCT_TEST_KINDS
    }
    for r in runs:
        sp = r.spec if isinstance(getattr(r, "spec", None), dict) else {}
        if str(sp.get("outcome")) != "pass":
            continue
        verifies = sp.get("verifies") or []
        if ref not in verifies and story_name not in verifies:
            continue
        if sp.get("guide_ref") in product_guides:
            return r.name
    return None


# ── test-guide ──────────────────────────────────────────────────────────────

def _step_stub(ac: str, *, product: bool) -> dict[str, str]:
    """Stub one step from an acceptance criterion.

    s-testkit-product-guide-authoring: ``--product`` makes it UI-first and
    leigo-proof — an action a non-dev can do in the Studio, a ``where`` route
    placeholder, and an ``expected`` that describes the CORRECT behavior. The
    tester marks ✗ ONLY if the product is actually broken — a product smoke is
    never authored to force a failure."""
    if product:
        return {
            "action": f"No Studio, valide: {ac}",
            "where": "<rota/tela — ex. /scopes/:scope/...>",
            "expected": "<o que você VÊ quando está certo (marque ✗ SÓ se estiver quebrado)>",
        }
    return {"action": f"Validar: {ac}", "expected": "<descreva o resultado esperado>"}


@sdlc.group("test-guide")
def test_guide_group() -> None:
    """Test guides (roteiros) — declarative test scripts that verify work items."""


@test_guide_group.command("create")
@click.argument("name")
@click.option("--description", default=None, help="What this guide validates.")
@click.option("--kind-of-test", "kind_of_test", type=click.Choice(_TEST_KINDS),
              default="manual", show_default=True)
@click.option("--product", is_flag=True,
              help="Scaffold a UI-first PRODUCT smoke: forces kind_of_test=smoke and "
                   "(with --from-ac) generates leigo-proof steps with a 'where' route + "
                   "observable 'expected'. The tester marks ✗ ONLY if the product is "
                   "broken — never author a step that forces a failure.")
@click.option("--verifies", multiple=True,
              help="Work item this guide verifies, e.g. 'Story/s-x' (repeatable).")
@click.option("--from-ac", "from_ac", default=None,
              help="Story name: stub one step per acceptance_criteria (you fill 'expected').")
@click.option("--step", "steps_in", multiple=True,
              help="A step as 'action :: expected' (repeatable).")
@click.option("--owner", default=None, help="Actor who owns this guide.")
@_scope_option
def cmd_test_guide_create(
    name: str, description: str | None, kind_of_test: str, product: bool,
    verifies: tuple[str, ...], from_ac: str | None,
    steps_in: tuple[str, ...], owner: str | None, scope: str,
) -> None:
    """Create a TestGuide. Manual steps via --step, or stub them from a Story's
    acceptance_criteria via --from-ac (you then fill in each 'expected'). Pass
    --product to scaffold a UI-first product smoke (the lane the done-gate counts)."""
    if product:
        kind_of_test = "smoke"  # --product is the product lane
    steps: list[dict[str, str]] = []
    for raw in steps_in:
        action, sep, expected = raw.partition("::")
        steps.append({"action": action.strip(), "expected": expected.strip() if sep else ""})

    verifies_list = list(verifies)
    if from_ac:
        with dna_session(scope) as s:
            story = s.get_doc("Story", from_ac)
        if story is None:
            raise fail(f"--from-ac: Story '{from_ac}' não encontrada em {scope!r}.")
        sp = story.spec if isinstance(story.spec, dict) else {}
        acs = [_ac_text(a) for a in (sp.get("acceptance_criteria") or [])]
        acs = [a for a in acs if a]
        if not acs:
            click.secho(f"⚠ Story '{from_ac}' não tem acceptance_criteria — guide criado sem steps stub.", fg="yellow")
        for a in acs:
            steps.append(_step_stub(a, product=product))
        sref = f"Story/{from_ac}"
        if sref not in verifies_list:
            verifies_list.append(sref)
        if description is None:
            description = f"Roteiro de teste de {from_ac} (derivado das acceptance_criteria)."

    if not steps:
        raise fail("nenhum step — passe --step 'ação :: esperado' ou --from-ac <story>.")
    if description is None:
        raise fail("--description é obrigatório (ou use --from-ac pra derivar).")

    now = _now_iso()
    spec: dict[str, Any] = {
        "description": description,
        "kind_of_test": kind_of_test,
        "status": "active",
        "steps": steps,
        "verifies": verifies_list,
        "created_at": now,
        "updated_at": now,
    }
    if owner:
        spec["owner"] = owner

    with dna_session(scope) as s:
        raw = _build_testkit_raw("TestGuide", name, spec)
        s.run(s.kernel.write_document(scope, "TestGuide", name, raw))
    click.secho(f"CREATED TestGuide/{name} ({kind_of_test}, {len(steps)} steps) in {scope}", fg="green")
    if verifies_list:
        click.secho(f"  verifies: {', '.join(verifies_list)}", fg="cyan")
        # i-100 — surface the guide on each verified Story's produces[] too, so
        # FOCUS shows the guide alongside its run (symmetric with test-run record).
        _stamp_verified_stories(
            scope, verifies_list,
            produced_kind="TestGuide", produced_name=name, role="test-guide",
            timeline_summary=f"TestGuide {name} ({kind_of_test})",
        )


def _build_screenshot_refs(upload_results: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Map raw ``/assets/upload`` responses → ``TestRun.spec.screenshots[]`` refs.

    Each ref is ``{asset, mime, blob}`` (asset name + mime + blob_path) — the
    blob is required to build the Studio image URL
    (``/scopes/{scope}/docs/Asset/{asset}/files/{blob}``). Asset-backed, NOT
    inline base64. Pure + side-effect-free so it's unit-testable without HTTP.
    """
    refs: list[dict[str, str]] = []
    for r in upload_results:
        refs.append({
            "asset": r["name"],
            "mime": r.get("mime") or "application/octet-stream",
            "blob": r.get("blob_path") or "blob.bin",
        })
    return refs


# ── test-run ──────────────────────────────────────────────────────────────

@sdlc.group("test-run")
def test_run_group() -> None:
    """Test runs — execution records of a TestGuide (the verify-phase signal)."""


@test_run_group.command("record")
@click.argument("guide")
@click.option("--outcome", type=click.Choice(_OUTCOMES), required=True)
@click.option("--by", "executed_by", default=None, help="Actor who ran it (default: CLI actor).")
@click.option("--note", "notes", default=None, help="Free-text notes on the run.")
@click.option("--name", "run_name", default=None,
              help="Run doc name (default: tr-<guide>-<timestamp>).")
@click.option("--evidence", multiple=True,
              help="Ref/link backing the outcome, e.g. 'HtmlArtifact/ha-x' (repeatable).")
@click.option("--screenshot", "screenshots", multiple=True,
              type=click.Path(exists=True, dir_okay=False),
              help="Print de evidência (imagem). Repetível. Uploadado como Asset.")
@_scope_option
def cmd_test_run_record(
    guide: str, outcome: str, executed_by: str | None, notes: str | None,
    run_name: str | None, evidence: tuple[str, ...],
    screenshots: tuple[str, ...], scope: str,
) -> None:
    """Record a TestRun for a TestGuide. Inherits the guide's `verifies`, then
    stamps each verified Story (artifact_produced timeline event + produces[]) —
    so the run shows in FOCUS and lights the journey's `verify` phase."""
    with dna_session(scope) as s:
        gdoc = s.get_doc("TestGuide", guide)
    if gdoc is None:
        raise fail(f"TestGuide '{guide}' não encontrado em {scope!r}. Crie com `dna sdlc test-guide create`.")
    gspec = gdoc.spec if isinstance(gdoc.spec, dict) else {}
    verifies = list(gspec.get("verifies") or [])

    now = _now_iso()
    if not run_name:
        run_name = f"tr-{guide}-{now[:19].replace(':', '').replace('-', '').replace('T', '-')}"
    actor = executed_by or _cli_actor()
    spec: dict[str, Any] = {
        "guide_ref": guide,
        "outcome": outcome,
        "verifies": verifies,
        "executed_by": actor,
        "executed_at": now,
    }
    if notes:
        spec["notes"] = notes
    if evidence:
        spec["evidence"] = list(evidence)

    # s-testrun-cli-screenshot: upload each print as an Asset (NOT base64
    # inline), then reference it on spec.screenshots[] so the Studio can build
    # the blob URL and render it with a lightbox.
    if screenshots:
        click.secho(
            "⚠ --screenshot requires the Asset upload service — not "
            "available in this kernel-local distribution; recording the "
            "run without screenshots (use --evidence to reference files).",
            fg="yellow", err=True,
        )

    with dna_session(scope) as s:
        raw = _build_testkit_raw("TestRun", run_name, spec)
        s.run(s.kernel.write_document(scope, "TestRun", run_name, raw))
    color = "green" if outcome == "pass" else ("red" if outcome == "fail" else "yellow")
    click.secho(f"RECORDED TestRun/{run_name} → {outcome} (guide {guide})", fg=color)

    # FOCUS + verify-phase: stamp each verified Story.
    _stamp_verified_stories(
        scope, verifies,
        produced_kind="TestRun", produced_name=run_name, role="test-run",
        timeline_summary=f"TestRun {run_name} → {outcome}", outcome=outcome,
    )


def _stamp_verified_stories(
    scope: str, verifies: list[str], *,
    produced_kind: str, produced_name: str, role: str,
    timeline_summary: str, **timeline_extra: Any,
) -> None:
    """Stamp each verified Story's ``produces[]`` + an ``artifact_produced``
    timeline event, so the artifact shows in FOCUS and lights the verify phase.

    i-100 — shared by ``test-guide create`` (role=test-guide) and ``test-run
    record`` (role=test-run) so a Story surfaces BOTH its guide and its run.
    Best-effort: a stamping miss never fails the underlying create/record.
    """
    for ref in verifies:
        story_name = _ref_story_name(ref)
        if not story_name:
            continue
        try:
            with dna_session(scope) as s:
                story = s.get_doc("Story", story_name)
                if story is None:
                    continue
                sp = dict(story.spec) if isinstance(story.spec, dict) else {}
                _append_produces(sp, produced_kind, produced_name, role=role)
                _append_timeline(
                    sp, "artifact_produced",
                    kind=produced_kind, name=produced_name,
                    summary=timeline_summary, **timeline_extra,
                )
                sp["updated_at"] = _now_iso()
                s.run(s.kernel.write_document(scope, "Story", story_name, _build_story_raw(story_name, sp)))
            click.secho(f"  → Story/{story_name}: produces + artifact_produced (FOCUS + verify)", fg="cyan")
        except Exception as e:  # noqa: BLE001 — stamping is best-effort
            click.secho(f"  ⚠ não consegui carimbar Story/{story_name}: {e}", fg="yellow", err=True)


def _build_story_raw(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    # Story envelope uses the SDLC apiVersion (not testkit's).
    from dna_cli.sdlc_cmd import _build_raw
    return _build_raw("Story", name, spec)


def register() -> None:
    """No-op: importing this module registers the groups on ``sdlc`` via the
    decorators above. Kept so callers can ``from . import testkit_cmd`` with
    an explicit, greppable intent."""
