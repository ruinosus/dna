"""``dna explain`` / ``mi.explain_prompt`` — per-section prompt provenance.

Proves (s-dna-explain-provenance):
  - explain mode returns the composed prompt PLUS a section→provenance map;
  - the prompt is BYTE-IDENTICAL to plain build_prompt (the byte-equal gate);
  - each composed section (instruction / soul / skill / guardrail) is
    attributed to its source artifact, content hash, and layer origin;
  - a TENANT overlay that wins a section is flagged overridden_by_tenant.
"""
from __future__ import annotations

from pathlib import Path

import yaml
import pytest

from dna.kernel import Kernel
from dna.adapters.filesystem import FilesystemSource, FilesystemCache


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_scope(tmp_path: Path) -> Path:
    """A self-contained scope: agent + soul + skill + guardrail, all local."""
    base = tmp_path / ".dna"
    scope = base / "demo"

    _write(scope / "Genome.yaml", yaml.dump({
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": "demo"},
        "spec": {"default_agent": "greeter"},
    }))
    _write(scope / "agents" / "greeter.yaml", yaml.dump({
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "greeter"},
        "spec": {
            "instruction": "You greet users.",
            "soul": "warm",
            "skills": ["greeting"],
            "guardrails": ["polite"],
        },
    }))
    _write(scope / "souls" / "warm" / "SOUL.md", "# Warm Soul\nBe kind and welcoming.")
    _write(scope / "skills" / "greeting" / "SKILL.md",
           "---\nname: greeting\n---\nBASE greeting procedure: say hello.")
    _write(scope / "guardrails" / "polite" / "GUARDRAIL.md",
           "---\nseverity: warn\nrules:\n  - Never insult the user\n---\n")
    return base


def _make_tenant_overlay(base: Path) -> None:
    """acme overlays the greeting skill with its own procedure."""
    overlay = base / "tenants" / "acme" / "scopes" / "demo"
    _write(overlay / "skills" / "greeting" / "SKILL.md",
           "---\nname: greeting\n---\nACME greeting procedure: welcome warmly to Acme.")


def _kernel(base: Path) -> Kernel:
    k = Kernel.auto()
    k.source(FilesystemSource(str(base)))
    k.cache(FilesystemCache(str(base)))
    return k


# ---------------------------------------------------------------------------


class TestExplainProvenance:
    @pytest.fixture
    def kernel(self, tmp_path):
        base = _make_scope(tmp_path)
        _make_tenant_overlay(base)
        return _kernel(base)

    def test_prompt_byte_equals_build(self, kernel):
        """The byte-equal gate: explain mode never re-renders."""
        mi = kernel.instance("demo")
        exp = mi.explain_prompt("greeter")
        assert exp.prompt == mi.build_prompt("greeter")

    def test_sections_cover_all_composition_inputs(self, kernel):
        mi = kernel.instance("demo")
        exp = mi.explain_prompt("greeter")
        by_label = {s.section: s for s in exp.sections}
        # instruction + soul + skill + guardrail all attributed.
        assert "instruction" in by_label
        assert "soul" in by_label
        assert "skill:greeting" in by_label
        assert "guardrail:polite" in by_label
        # Non-prompt deps (tools/actors) are NOT sections.
        assert not any(s.section.startswith("tool") for s in exp.sections)

    def test_section_carries_source_hash_origin(self, kernel):
        mi = kernel.instance("demo")
        exp = mi.explain_prompt("greeter")
        skill = next(s for s in exp.sections if s.section == "skill:greeting")
        assert skill.kind == "Skill"
        assert skill.source == "skills/greeting/SKILL.md"
        assert skill.hash and len(skill.hash) == 64  # sha256 hex
        assert skill.origin == "demo"
        assert skill.is_inherited is False
        assert skill.overridden_by_tenant is False

    def test_tenant_overlay_marked_overridden(self, kernel):
        """When acme overlays the greeting skill, the section is flagged."""
        mi = kernel.with_tenant("acme").instance("demo")
        exp = mi.explain_prompt("greeter", tenant="acme")
        # The overlay body composed into the prompt (byte-equal gate holds).
        assert exp.prompt == mi.build_prompt("greeter")
        assert "ACME greeting procedure" in exp.prompt
        assert "BASE greeting procedure" not in exp.prompt
        # The greeting skill is flagged as tenant-overridden; the soul (no
        # overlay) is not.
        skill = next(s for s in exp.sections if s.section == "skill:greeting")
        soul = next(s for s in exp.sections if s.section == "soul")
        assert skill.overridden_by_tenant is True
        assert soul.overridden_by_tenant is False

    def test_serialize_roundtrips(self, kernel):
        mi = kernel.instance("demo")
        payload = mi.explain_prompt("greeter").serialize()
        assert "prompt" in payload and isinstance(payload["sections"], list)
        assert {"section", "source", "hash", "origin", "overridden_by_tenant"} <= set(
            payload["sections"][0]
        )
