"""TDD for `dna specify import` — the Spec Kit → DNA ingester (ADR §4).

Three layers:
  1. Pure parsers/mapping (no I/O) — parse_tasks, parse_constitution_rules,
     build_feature_plan produces the right Kinds/refs/tags.
  2. Dry-run CLI over the committed fixture .specify/ tree — prints the full
     mapping, writes nothing.
  3. Real-kernel integration — import into a temp filesystem scope and assert
     the persisted docs (schema validation fires for real).
"""
from __future__ import annotations

import json
import pathlib

import pytest
import yaml
from click.testing import CliRunner

from dna_cli.specify_cmd import (
    build_feature_plan,
    parse_constitution_rules,
    parse_tasks,
    scan_specify,
    specify,
    _slugify,
)

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "speckit"


# ─── 1. pure parsers ─────────────────────────────────────────────────────────


def test_slugify_strips_ordinal():
    assert _slugify("001-taskify") == "taskify"
    assert _slugify("taskify") == "taskify"
    assert _slugify("042-multi-word-thing") == "multi-word-thing"


def test_parse_tasks_ids_and_parallel():
    text = (
        "## Phase 1\n"
        "- [ ] T001 Scaffold the project\n"
        "- [ ] T002 [P] Configure linting\n"
        "* [x] T003 Already done task\n"
        "not a task line\n"
    )
    tasks = parse_tasks(text)
    assert [t["id"] for t in tasks] == ["T001", "T002", "T003"]
    assert [t["parallel"] for t in tasks] == [False, True, False]
    assert tasks[0]["desc"] == "Scaffold the project"
    assert tasks[1]["desc"] == "Configure linting"


def test_parse_tasks_skips_non_tasks():
    assert parse_tasks("# Heading\n\nsome prose\n\n## Phase\n") == []


def test_parse_constitution_rules_harvests_bullets():
    text = "# C\n\n## Principles\n\n- Rule one.\n- Rule two.\n\n## Voice\n\nprose\n"
    rules = parse_constitution_rules(text)
    assert rules == ["Rule one.", "Rule two."]


def test_parse_constitution_rules_fallback_to_whole_body():
    rules = parse_constitution_rules("Just prose, no bullets.")
    assert rules == ["Just prose, no bullets."]


# ─── 2. mapping plan (pure, over the fixture) ────────────────────────────────


@pytest.fixture
def scan():
    return scan_specify(FIXTURE)


def test_scan_finds_constitution_and_feature(scan):
    assert scan.constitution is not None
    assert scan.constitution.rel == ".specify/memory/constitution.md"
    assert len(scan.features) == 1
    run = scan.features[0]
    assert run.slug == "taskify"
    assert run.spec is not None and run.plan is not None and run.tasks is not None
    # research + data-model + quickstart + one contract = 4 references
    roles = sorted(r for r, _ in run.references)
    assert roles == ["contract", "data-model", "quickstart", "research"]


def test_build_plan_constitution_both(scan):
    fp = build_feature_plan(scan, scan.features[0], feature_override=None, constitution_as="both")
    kinds = {(w.kind, w.name) for w in fp.writes}
    assert ("Soul", "speckit-constitution") in kinds
    assert ("Guardrail", "speckit-constitution") in kinds


def test_build_plan_constitution_guardrail_only(scan):
    fp = build_feature_plan(scan, scan.features[0], feature_override=None, constitution_as="guardrail")
    kinds = {w.kind for w in fp.writes}
    assert "Guardrail" in kinds
    assert "Soul" not in kinds
    # With no Soul, the Guardrail becomes the export byte-source.
    guard = next(w for w in fp.writes if w.kind == "Guardrail")
    assert guard.export_source is True


def test_build_plan_spec_and_plan_tags(scan):
    fp = build_feature_plan(scan, scan.features[0], feature_override=None, constitution_as="both")
    spec = next(w for w in fp.writes if w.kind == "Spec")
    plan = next(w for w in fp.writes if w.kind == "Plan")
    assert spec.spec["pattern"] == "spec-kit"
    assert plan.spec["methodology"] == "spec-kit"
    assert plan.spec["spec_ref"] == spec.name
    # research/data-model/quickstart/contract attach to the Plan.produces[]
    produced = {p["role"] for p in plan.spec["produces"]}
    assert produced == {"research", "data-model", "quickstart", "contract"}


def test_build_plan_tasks_to_stories(scan):
    fp = build_feature_plan(scan, scan.features[0], feature_override=None, constitution_as="both")
    stories = [w for w in fp.writes if w.kind == "Story"]
    assert len(stories) == 5  # T001..T005 in the fixture
    # T002 and T004 are [P] → 'parallel' label
    parallel = {w.name for w in stories if "parallel" in w.spec["labels"]}
    assert parallel == {"s-speckit-taskify-t002", "s-speckit-taskify-t004"}
    # every story links the Spec + the Feature
    for w in stories:
        assert w.spec["feature"] == "f-taskify"
        assert w.spec["spec_refs"] == ["speckit-taskify"]
        assert "spec-kit" in w.spec["labels"]


def test_build_plan_feature_manifest(scan):
    fp = build_feature_plan(scan, scan.features[0], feature_override=None, constitution_as="both")
    feat = next(w for w in fp.writes if w.kind == "Feature")
    manifest = feat.spec["specify_run"]
    assert manifest["feature_dir"] == "specs/001-taskify"
    paths = {f["path"] for f in manifest["files"]}
    assert ".specify/memory/constitution.md" in paths
    assert "specs/001-taskify/spec.md" in paths
    assert "specs/001-taskify/plan.md" in paths
    assert "specs/001-taskify/tasks.md" in paths


def test_build_plan_workflow_events(scan):
    fp = build_feature_plan(scan, scan.features[0], feature_override=None, constitution_as="both")
    phases = [e.spec["phase"] for e in fp.workflow_events]
    assert phases == ["specify", "plan", "build"]
    for e in fp.workflow_events:
        assert e.spec["methodology"] == "spec-kit"
        assert e.spec["methodology_artifact"].startswith("specs/001-taskify/")
        assert e.spec["parent_ref"] == "Feature/f-taskify"
    # linked list
    assert "transitioned_from" not in fp.workflow_events[0].spec
    assert fp.workflow_events[1].spec["transitioned_from"] == fp.workflow_events[0].name


def test_feature_override_reuse(scan):
    fp = build_feature_plan(scan, scan.features[0], feature_override="f-existing", constitution_as="both")
    assert fp.feature_name == "f-existing"
    assert fp.reuse_feature is True
    stories = [w for w in fp.writes if w.kind == "Story"]
    assert all(w.spec["feature"] == "f-existing" for w in stories)


# ─── 3. dry-run CLI over the fixture (no writes) ─────────────────────────────


@pytest.fixture
def runner():
    return CliRunner()


def test_dry_run_json_prints_mapping_writes_nothing(runner, monkeypatch):
    # No source configured → a dry-run must never need a kernel.
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    r = runner.invoke(specify, ["import", str(FIXTURE), "--dry-run", "--json"],
                      catch_exceptions=False)
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["dry_run"] is True
    assert payload["constitution"] == ".specify/memory/constitution.md"
    feat = payload["features"][0]
    assert feat["feature"] == "f-taskify"
    kinds = [d["kind"] for d in feat["documents"]]
    assert "Soul" in kinds and "Guardrail" in kinds and "Spec" in kinds
    assert "Plan" in kinds and "Story" in kinds and "Feature" in kinds
    assert [e["phase"] for e in feat["workflow_events"]] == ["specify", "plan", "build"]


def test_dry_run_human_readable(runner, monkeypatch):
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    r = runner.invoke(specify, ["import", str(FIXTURE), "--dry-run"], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    assert "Feature/f-taskify" in r.output
    assert "nothing persisted" in r.output


# ─── 4. real-kernel integration (writes into a temp filesystem scope) ────────


@pytest.fixture
def temp_scope(tmp_path, monkeypatch):
    base = tmp_path / ".dna"
    scope = "proj"
    (base / scope).mkdir(parents=True)
    (base / scope / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        "metadata:\n  name: proj\nspec:\n  owner: dna\n"
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(base))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return base, scope


def test_import_persists_docs(runner, temp_scope):
    base, scope = temp_scope
    r = runner.invoke(specify, ["import", str(FIXTURE), "--scope", scope],
                      catch_exceptions=False)
    assert r.exit_code == 0, r.output
    # Assert the docs actually landed (the FS source picks yaml/bundle storage
    # per Kind — Spec/Plan/Guardrail flat yaml, Soul as a SOUL.md bundle).
    proj = base / scope
    assert (proj / "specs" / "speckit-taskify.yaml").exists()
    assert (proj / "plans" / "speckit-taskify.yaml").exists()
    assert (proj / "souls" / "speckit-constitution" / "SOUL.md").exists()
    assert (proj / "guardrails" / "speckit-constitution.yaml").exists()
    # 5 task stories
    stories = list((proj / "stories").glob("s-speckit-taskify-*.yaml"))
    assert len(stories) == 5
    # 3 journey WorkflowEvents (specify/plan/build)
    assert len(list((proj / "journey").glob("f-taskify-*.yaml"))) == 3
    # Feature carries the specify_run manifest
    feat = yaml.safe_load((proj / "features" / "f-taskify.yaml").read_text())
    assert feat["spec"]["specify_run"]["feature_dir"] == "specs/001-taskify"


def test_import_spec_pattern_and_body_faithful(runner, temp_scope):
    base, scope = temp_scope
    r = runner.invoke(specify, ["import", str(FIXTURE), "--scope", scope],
                      catch_exceptions=False)
    assert r.exit_code == 0, r.output
    original = (FIXTURE / "specs" / "001-taskify" / "spec.md").read_text()
    spec_doc = yaml.safe_load((base / scope / "specs" / "speckit-taskify.yaml").read_text())
    assert spec_doc["spec"]["pattern"] == "spec-kit"
    # The persisted body must equal the source spec.md byte-for-byte.
    assert spec_doc["spec"]["body"] == original
    plan_doc = yaml.safe_load((base / scope / "plans" / "speckit-taskify.yaml").read_text())
    assert plan_doc["spec"]["methodology"] == "spec-kit"
    assert plan_doc["spec"]["spec_ref"] == "speckit-taskify"
