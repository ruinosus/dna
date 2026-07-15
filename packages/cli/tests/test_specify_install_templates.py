"""TDD for `dna specify install-templates` / `export-templates` — the Layer 3
Spec Kit **toolkit** ingester (ADR ADR-spec-kit-adoption §5, Layer 3).

Where `dna specify import` (#116) ingests a *run* (constitution/spec/plan/tasks),
Layer 3 ingests the *toolkit itself* — `.specify/templates/`, the slash-command
definitions, `.specify/scripts/`, and the constitution — into durable, servable,
overridable Kinds:

    .specify/templates/*.md      → PromptTemplate  speckit-<stem>
    templates/commands/*.md      → Skill           speckit-<cmd>
    .specify/scripts/**          → Skill           speckit-scripts (bundle)
    .specify/memory/constitution → Guardrail(+Soul) speckit-constitution

Three layers, mirroring test_specify_import.py:
  1. Pure scan/mapping (no I/O).
  2. Dry-run CLI over the committed fixture toolkit — writes nothing.
  3. Real-kernel integration + byte-faithful round-trip (install → export).
"""
from __future__ import annotations

import json
import pathlib

import pytest
from click.testing import CliRunner

from dna_cli.specify_cmd import specify
from dna_cli.specify_toolkit import (
    build_toolkit_plan,
    scan_toolkit,
)

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "speckit"


# ─── 1. pure scan ────────────────────────────────────────────────────────────


@pytest.fixture
def scan():
    return scan_toolkit(FIXTURE)


def test_scan_finds_templates(scan):
    stems = sorted(a.rel.rsplit("/", 1)[-1] for a in scan.templates)
    assert stems == [
        "agent-file-template.md",
        "plan-template.md",
        "spec-template.md",
        "tasks-template.md",
    ]


def test_scan_finds_commands(scan):
    cmds = sorted(scan.command_name(a) for a in scan.commands)
    assert cmds == ["plan", "specify", "tasks"]


def test_scan_finds_scripts_and_constitution(scan):
    rels = sorted(a.rel for a in scan.scripts)
    assert ".specify/scripts/bash/common.sh" in rels
    assert ".specify/scripts/bash/create-new-feature.sh" in rels
    assert ".specify/scripts/powershell/create-new-feature.ps1" in rels
    assert scan.constitution is not None


# ─── 2. mapping plan (pure) ──────────────────────────────────────────────────


def test_plan_maps_templates_to_prompttemplates(scan):
    writes = build_toolkit_plan(scan, constitution_as="guardrail")
    pts = {w.name: w for w in writes if w.kind == "PromptTemplate"}
    assert {
        "speckit-spec-template",
        "speckit-plan-template",
        "speckit-tasks-template",
        "speckit-agent-file-template",
    } <= set(pts)
    # the constitution is ALSO servable/overridable as a template (scope #3)
    assert "speckit-constitution-template" in pts
    # body is verbatim (byte-source for export)
    spec_pt = pts["speckit-spec-template"]
    src = next(a for a in scan.templates if a.rel.endswith("spec-template.md"))
    assert spec_pt.spec["body"] == src.content
    assert spec_pt.spec["origin"] == src.rel
    assert spec_pt.spec.get("tags") == ["spec-kit"]


def test_plan_maps_commands_to_skills(scan):
    writes = build_toolkit_plan(scan, constitution_as="guardrail")
    skills = {w.name: w for w in writes if w.kind == "Skill"}
    assert "speckit-specify" in skills
    assert "speckit-plan" in skills
    assert "speckit-tasks" in skills
    # frontmatter description → Skill metadata.description; body → instruction
    specify_skill = skills["speckit-specify"]
    assert "feature specification" in specify_skill.spec["instruction"].lower()
    assert specify_skill.raw()["metadata"]["description"].startswith(
        "Create or update the feature specification"
    )


def test_plan_bundles_scripts_into_one_skill(scan):
    writes = build_toolkit_plan(scan, constitution_as="guardrail")
    scripts_skill = next(w for w in writes if w.name == "speckit-scripts")
    assert scripts_skill.kind == "Skill"
    files = scripts_skill.spec["scripts"]
    assert "bash/common.sh" in files
    assert "powershell/create-new-feature.ps1" in files
    assert files["bash/common.sh"] == next(
        a.content for a in scan.scripts if a.rel.endswith("bash/common.sh")
    )


def test_plan_maps_constitution_to_guardrail(scan):
    writes = build_toolkit_plan(scan, constitution_as="both")
    guard = next(w for w in writes if w.kind == "Guardrail")
    assert guard.name == "speckit-constitution"
    assert guard.spec["pattern"] == "spec-kit"
    assert guard.spec["rules"]  # harvested bullets
    soul = next(w for w in writes if w.kind == "Soul")
    assert soul.name == "speckit-constitution"


# ─── 3. dry-run CLI ──────────────────────────────────────────────────────────


def test_install_templates_dry_run_writes_nothing():
    r = CliRunner().invoke(
        specify, ["install-templates", str(FIXTURE), "--dry-run", "--json"]
    )
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["dry_run"] is True
    kinds = {d["kind"] for d in payload["documents"]}
    assert {"PromptTemplate", "Skill", "Guardrail"} <= kinds
    names = {d["name"] for d in payload["documents"]}
    assert "speckit-spec-template" in names
    assert "speckit-specify" in names
    assert "speckit-scripts" in names


# ─── 4. real-kernel integration + round-trip ─────────────────────────────────


@pytest.fixture
def fs_scope(tmp_path, monkeypatch):
    base = tmp_path / ".dna"
    (base / "toolkit").mkdir(parents=True)
    # A Package.yaml makes it a real scope root the kernel will load.
    (base / "toolkit" / "Package.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Package\n"
        "metadata:\n  name: toolkit\nspec:\n  description: toolkit test scope\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(base))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return base


def test_install_then_export_round_trips(fs_scope, tmp_path):
    # install the toolkit into the fs scope
    r = CliRunner().invoke(
        specify,
        ["install-templates", str(FIXTURE), "--scope", "toolkit",
         "--constitution-as", "guardrail"],
    )
    assert r.exit_code == 0, r.output

    # export it back out to a fresh dir
    out = tmp_path / "reprojected"
    r2 = CliRunner().invoke(
        specify, ["export-templates", "--scope", "toolkit", "--out", str(out)]
    )
    assert r2.exit_code == 0, r2.output

    # byte-identical round-trip for every ingested file
    for rel in [
        ".specify/templates/spec-template.md",
        ".specify/templates/plan-template.md",
        ".specify/templates/commands/specify.md",
        ".specify/scripts/bash/common.sh",
        ".specify/scripts/powershell/create-new-feature.ps1",
        ".specify/memory/constitution.md",
    ]:
        assert (out / rel).read_text(encoding="utf-8") == (
            FIXTURE / rel
        ).read_text(encoding="utf-8"), f"round-trip drift on {rel}"
