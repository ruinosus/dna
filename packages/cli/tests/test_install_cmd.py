"""``dna install`` — offline end-to-end via ``local:`` (s-dna-install).

Drives the real CLI (CliRunner, in-process) against a filesystem source and
a fixture "remote" tree containing the full cast: a valid Skill bundle, a
valid standalone-YAML Skill, a schema-invalid doc, an unknown-Kind doc, a
root Genome (must never install) and a path-traversal name (must never
reach the filesystem adapter). Zero network — the github: path is covered
by ``test_install_github_real.py`` (requires_network).
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from dna_cli import main

_GENOME_LIB = (
    "apiVersion: github.com/ruinosus/dna/v1\n"
    "kind: Genome\n"
    "metadata: { name: _lib }\n"
    "spec: {}\n"
)

_SKILL_MD = """---
name: greeter
description: Greets people warmly
---

# Greeter

Say hello nicely.
"""

_SKILL_YAML = """apiVersion: agentskills.io/v1
kind: Skill
metadata:
  name: standalone-skill
  description: Authored as a bare YAML doc
spec:
  instruction: "Do the standalone thing."
"""

_BAD_SKILL_YAML = """apiVersion: agentskills.io/v1
kind: Skill
metadata:
  name: bad-skill
spec:
  instruction: 42
"""

_UNKNOWN_KIND_YAML = """apiVersion: nowhere.io/v1
kind: Mystery
metadata:
  name: who-knows
spec: {}
"""

_REMOTE_GENOME = (
    "apiVersion: github.com/ruinosus/dna/v1\n"
    "kind: Genome\n"
    "metadata: { name: evil-takeover }\n"
    "spec: {}\n"
)

_TRAVERSAL_YAML = """apiVersion: agentskills.io/v1
kind: Skill
metadata:
  name: ../../escape
spec:
  instruction: "nope"
"""


def _make_base(tmp_path: Path) -> Path:
    base = tmp_path / ".dna"
    (base / "_lib").mkdir(parents=True)
    (base / "_lib" / "Genome.yaml").write_text(_GENOME_LIB, encoding="utf-8")
    return base


def _make_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "remote"
    (remote / "skills" / "greeter").mkdir(parents=True)
    (remote / "skills" / "greeter" / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    (remote / "docs").mkdir()
    (remote / "docs" / "standalone.yaml").write_text(_SKILL_YAML, encoding="utf-8")
    (remote / "docs" / "bad-skill.yaml").write_text(_BAD_SKILL_YAML, encoding="utf-8")
    (remote / "docs" / "mystery.yaml").write_text(_UNKNOWN_KIND_YAML, encoding="utf-8")
    (remote / "Genome.yaml").write_text(_REMOTE_GENOME, encoding="utf-8")
    (remote / "evil.yaml").write_text(_TRAVERSAL_YAML, encoding="utf-8")
    return remote


def _env(tmp_path, monkeypatch) -> tuple[CliRunner, Path, Path]:
    base = _make_base(tmp_path)
    remote = _make_remote(tmp_path)
    monkeypatch.setenv("DNA_BASE_DIR", str(base))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_TENANT", raising=False)
    return CliRunner(), base, remote


def _install(runner, remote, *extra):
    return runner.invoke(
        main, ["install", f"local:{remote}", "--scope", "playground", *extra],
    )


# ─── dry-run ──────────────────────────────────────────────────────────


def test_dry_run_prints_plan_and_writes_nothing(tmp_path, monkeypatch):
    runner, base, remote = _env(tmp_path, monkeypatch)
    res = _install(runner, remote, "--dry-run")
    assert res.exit_code == 0, res.output
    assert "Skill/greeter" in res.output
    assert "Skill/standalone-skill" in res.output
    # rejections are explained, not silent
    assert "not of type 'string'" in res.output          # schema violation
    assert "not registered" in res.output                # unknown Kind
    assert "root Kind" in res.output                     # remote Genome blocked
    assert "not a plain slug" in res.output              # path traversal blocked
    # nothing was written
    assert not (base / "playground").exists()


def test_dry_run_json_shape(tmp_path, monkeypatch):
    runner, _, remote = _env(tmp_path, monkeypatch)
    res = _install(runner, remote, "--dry-run", "--json")
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["dry_run"] is True
    actions = {f"{p['kind']}/{p['name']}": p["action"] for p in payload["plan"]}
    assert actions["Skill/greeter"] == "install"
    assert actions["Skill/standalone-skill"] == "install"
    assert actions["Skill/bad-skill"] == "reject"
    assert actions["Mystery/who-knows"] == "reject"
    assert actions["Genome/evil-takeover"] == "reject"


# ─── install ──────────────────────────────────────────────────────────


def test_install_writes_valid_docs_and_provenance(tmp_path, monkeypatch):
    runner, base, remote = _env(tmp_path, monkeypatch)
    res = _install(runner, remote, "--json")
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert sorted(payload["installed"]) == ["Skill/greeter", "Skill/standalone-skill"]
    assert len(payload["rejected"]) == 4

    # the Skill bundle round-tripped through kernel.write_document → writer
    skill_md = base / "playground" / "skills" / "greeter" / "SKILL.md"
    assert skill_md.exists()
    assert "Say hello nicely." in skill_md.read_text(encoding="utf-8")

    # the scope was born with a Genome of its own (NOT the remote's)
    manifest = yaml.safe_load((base / "playground" / "manifest.yaml").read_text())
    assert manifest["metadata"]["name"] == "playground"
    assert "evil-takeover" not in (base / "playground" / "manifest.yaml").read_text()

    # provenance: installed.lock in the kernel's lockfile-v3 shape
    lock = yaml.safe_load((base / "playground" / "installed.lock").read_text())
    assert lock["lockVersion"] == 3
    assert lock["scope"] == "playground"
    by_name = {d["name"]: d for d in lock["documents"]}
    assert set(by_name) == {"greeter", "standalone-skill"}
    entry = by_name["greeter"]
    assert entry["origin"] == f"local:{remote}"
    assert entry["path"] == "skills/greeter"
    assert len(entry["sha256"]) == 64

    # nothing path-shaped ever landed on disk
    assert not (tmp_path / "escape").exists()
    assert not list(base.rglob("*escape*"))


def test_install_readback_via_doc_show(tmp_path, monkeypatch):
    runner, _, remote = _env(tmp_path, monkeypatch)
    assert _install(runner, remote).exit_code == 0
    res = runner.invoke(main, ["doc", "show", "Skill", "greeter", "--scope", "playground"])
    assert res.exit_code == 0, res.output
    assert "Say hello nicely." in res.output


# ─── mixed trees — a claim consumes its bundle, not the subtree (i-016) ──


_AGENTS_MD = "# Acme conventions\n\nBe excellent to each other.\n"


def test_root_agents_md_does_not_hide_sibling_docs(tmp_path, monkeypatch):
    """i-016: a single-file claim at the tree ROOT (AGENTS.md) must not
    swallow the rest of the tree — the skills/ bundles and the standalone
    YAML docs next to it still install, and the AgentDefinition itself
    lands too (with provenance for every one of them)."""
    runner, base, remote = _env(tmp_path, monkeypatch)
    (remote / "AGENTS.md").write_text(_AGENTS_MD, encoding="utf-8")
    res = _install(runner, remote, "--json")
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert sorted(payload["installed"]) == [
        "AgentDefinition/remote", "Skill/greeter", "Skill/standalone-skill",
    ]
    # the untrusted-input rejections are unchanged by the deeper scan
    assert len(payload["rejected"]) == 4

    # every installed doc carries provenance; the root claim records path "."
    lock = yaml.safe_load((base / "playground" / "installed.lock").read_text())
    by_name = {d["name"]: d for d in lock["documents"]}
    assert set(by_name) == {"remote", "greeter", "standalone-skill"}
    assert by_name["remote"]["kind"] == "AgentDefinition"
    assert by_name["remote"]["path"] == "."


def test_skill_bundle_scans_as_exactly_one_doc(tmp_path, monkeypatch):
    """The inverse guard: a Skill bundle (SKILL.md + companion files +
    subdirs) is ONE doc — the scan must not recurse into the bundle's own
    consumed content and re-collect envelope-shaped YAML companions as
    separate documents."""
    runner, _, remote = _env(tmp_path, monkeypatch)
    greeter = remote / "skills" / "greeter"
    # An envelope-shaped YAML at the bundle root (reader keeps it in
    # spec.root_files) and one nested in references/ (spec.references).
    (greeter / "companion.yaml").write_text(_SKILL_YAML, encoding="utf-8")
    (greeter / "references").mkdir()
    (greeter / "references" / "nested.yaml").write_text(
        _SKILL_YAML.replace("standalone-skill", "nested-skill"), encoding="utf-8",
    )
    res = _install(runner, remote, "--dry-run", "--json")
    assert res.exit_code == 0, res.output
    plan = json.loads(res.output)["plan"]
    greeter_docs = [p for p in plan if p["path"].startswith("skills/greeter")]
    assert [f"{p['kind']}/{p['name']}" for p in greeter_docs] == ["Skill/greeter"]
    # the companions never surfaced as standalone docs anywhere in the plan
    assert not any(p["name"] == "nested-skill" for p in plan)
    assert [p["path"] for p in plan if p["name"] == "standalone-skill"] == [
        "docs/standalone.yaml",
    ]


def test_scan_claim_without_writer_keeps_conservative_subtree(tmp_path):
    """A claimed doc with NO matching writer has an unknowable extent — the
    scan falls back to the pre-i-016 semantics (the whole subtree is the
    bundle) instead of guessing and double-collecting."""
    from dna.extensions.agentskills import SkillReader, SkillWriter
    from dna_cli.install_cmd import _scan_tree

    class MarkerReader:
        def detect(self, bundle):
            return bundle.exists("MARKER.md")

        def read(self, bundle):
            return {
                "apiVersion": "x.test/v1", "kind": "Marker",
                "metadata": {"name": bundle.name}, "spec": {},
            }

    tree = tmp_path / "tree"
    (tree / "skills" / "greeter").mkdir(parents=True)
    (tree / "MARKER.md").write_text("root claim\n", encoding="utf-8")
    (tree / "skills" / "greeter" / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")

    scanned = _scan_tree(tree, [MarkerReader(), SkillReader()], writers=[SkillWriter()])
    assert [d.raw["kind"] for d in scanned] == ["Marker"]

    # and without any writers at all (init's historic call shape) — same
    scanned = _scan_tree(tree, [MarkerReader(), SkillReader()])
    assert [d.raw["kind"] for d in scanned] == ["Marker"]


# ─── conflicts ────────────────────────────────────────────────────────


def test_rerun_skips_existing_by_default(tmp_path, monkeypatch):
    runner, _, remote = _env(tmp_path, monkeypatch)
    assert _install(runner, remote).exit_code == 0
    res = _install(runner, remote, "--json")
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["installed"] == []
    assert sorted(payload["skipped"]) == ["Skill/greeter", "Skill/standalone-skill"]


def test_force_overwrites_existing(tmp_path, monkeypatch):
    runner, base, remote = _env(tmp_path, monkeypatch)
    assert _install(runner, remote).exit_code == 0
    # remote evolves
    (remote / "skills" / "greeter" / "SKILL.md").write_text(
        _SKILL_MD.replace("Say hello nicely.", "Say hello LOUDLY."), encoding="utf-8",
    )
    res = _install(runner, remote, "--force", "--json")
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert "Skill/greeter" in payload["installed"]
    skill_md = base / "playground" / "skills" / "greeter" / "SKILL.md"
    assert "Say hello LOUDLY." in skill_md.read_text(encoding="utf-8")


# ─── degradation ──────────────────────────────────────────────────────


def test_all_rejected_exits_nonzero(tmp_path, monkeypatch):
    runner, base, _ = _env(tmp_path, monkeypatch)
    only_bad = base.parent / "only-bad"
    only_bad.mkdir()
    (only_bad / "bad.yaml").write_text(_BAD_SKILL_YAML, encoding="utf-8")
    res = runner.invoke(main, ["install", f"local:{only_bad}", "--scope", "playground"])
    assert res.exit_code == 1
    assert "not of type 'string'" in res.output


def test_empty_tree_is_a_didactic_error(tmp_path, monkeypatch):
    runner, base, _ = _env(tmp_path, monkeypatch)
    empty = base.parent / "empty"
    empty.mkdir()
    res = runner.invoke(main, ["install", f"local:{empty}", "--scope", "playground"])
    assert res.exit_code == 1
    assert "no DNA documents detected" in res.output


def test_missing_local_path_is_a_didactic_error(tmp_path, monkeypatch):
    runner, _, _ = _env(tmp_path, monkeypatch)
    res = runner.invoke(main, ["install", "local:/definitely/not/here"])
    assert res.exit_code != 0
    assert "does not exist" in res.output
    assert "Traceback" not in res.output


def test_unknown_scheme_is_a_didactic_error(tmp_path, monkeypatch):
    runner, _, _ = _env(tmp_path, monkeypatch)
    res = runner.invoke(main, ["install", "ftp://old.school/skills"])
    assert res.exit_code != 0
    assert "unsupported install URI" in res.output


def test_github_offline_is_a_didactic_error(tmp_path, monkeypatch):
    """A clone failure (offline / bad repo) surfaces the ResolveError with
    guidance, never a traceback. The clone is faked to fail — no network."""
    import subprocess

    def _boom(cmd, **kwargs):
        raise subprocess.CalledProcessError(128, cmd)

    monkeypatch.setattr("dna.adapters.resolvers.github.subprocess.run", _boom)
    runner, _, _ = _env(tmp_path, monkeypatch)
    res = runner.invoke(main, ["install", "github:acme/widgets", "--scope", "playground"])
    assert res.exit_code != 0
    assert "Could not fetch the repository" in res.output
    assert "local:<path>" in res.output
    assert "Traceback" not in res.output


# ─── scope derivation ─────────────────────────────────────────────────


def test_scope_derived_from_local_uri(tmp_path, monkeypatch):
    runner, base, remote = _env(tmp_path, monkeypatch)
    res = runner.invoke(main, ["install", f"local:{remote}", "--json"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.output)["scope"] == "remote"
    assert (base / "remote" / "skills" / "greeter" / "SKILL.md").exists()
