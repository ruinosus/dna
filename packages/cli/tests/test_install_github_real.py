"""``dna install github:...`` against a REAL public repo (requires_network).

Clones a single skill subtree from anthropics/skills — the same repo the
market-integration fixtures came from — and proves the whole arc: fetch →
reader detection → validation → kernel write → provenance pinned to the
resolved commit. Skips offline and under DNA_OFFLINE=1 (CI never clones
external repos — s-public-ci).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from dna_cli import main

_URI = "github:anthropics/skills/skills/pdf@main"

_GENOME_LIB = (
    "apiVersion: github.com/ruinosus/dna/v1\n"
    "kind: Genome\n"
    "metadata: { name: _lib }\n"
    "spec: {}\n"
)


@pytest.mark.requires_network
def test_install_real_anthropic_skill(tmp_path, monkeypatch):
    base = tmp_path / ".dna"
    (base / "_lib").mkdir(parents=True)
    (base / "_lib" / "Genome.yaml").write_text(_GENOME_LIB, encoding="utf-8")
    monkeypatch.setenv("DNA_BASE_DIR", str(base))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)

    runner = CliRunner()
    res = runner.invoke(main, ["install", _URI, "--scope", "market", "--json"])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert "Skill/pdf" in payload["installed"]
    # origin is pinned to the resolved commit, not the moving branch
    assert payload["origin"].startswith("github:anthropics/skills/skills/pdf@")
    assert not payload["origin"].endswith("@main")

    skill_md = base / "market" / "skills" / "pdf" / "SKILL.md"
    assert skill_md.exists()

    lock = yaml.safe_load((base / "market" / "installed.lock").read_text())
    entry = {d["name"]: d for d in lock["documents"]}["pdf"]
    assert entry["kind"] == "Skill"
    assert entry["origin"] == payload["origin"]
