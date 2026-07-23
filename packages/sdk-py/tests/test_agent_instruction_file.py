"""Schema tests for AgentSpec.instruction_file (Phase 8 Option A —
bundles are atomic; instruction_file must stay within the bundle)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from dna.extensions.helix import AgentReader, AgentWriter
from dna.kernel.bundle.handle import FilesystemBundleHandle
from dna.kernel.models import AgentSpec


def test_agent_spec_accepts_instruction_file():
    spec = AgentSpec.from_raw({
        "instruction": "",
        "instruction_file": "prompts/x.md",
    })
    assert spec.instruction == ""
    assert spec.instruction_file == "prompts/x.md"


def test_agent_spec_instruction_file_default_none():
    spec = AgentSpec.from_raw({"instruction": "hello"})
    assert spec.instruction_file is None


def _write_agent_md(bundle_dir: Path, frontmatter: str, body: str = "") -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "AGENT.md").write_text(f"---\n{frontmatter}---\n\n{body}")


def test_instruction_file_within_bundle_roundtrip(tmp_path: Path):
    """Round-trip: frontmatter → Reader → Writer → Reader preserves instruction_file."""
    bundle = tmp_path / "agents" / "a"
    bundle.mkdir(parents=True)
    (bundle / "instruction.md").write_text("PROMPT BODY")
    _write_agent_md(bundle, "name: a\ninstruction_file: instruction.md\n")

    raw = AgentReader().read(FilesystemBundleHandle(bundle))
    assert raw["spec"].get("instruction_file") == "instruction.md", raw["spec"]

    out = tmp_path / "out" / "agents" / "a"
    out.mkdir(parents=True)
    AgentWriter().write(FilesystemBundleHandle(out), raw)
    written = (out / "AGENT.md").read_text()
    assert "instruction_file:" in written, written


def test_instruction_file_populates_instruction(tmp_path: Path):
    bundle = tmp_path / "agents" / "a"
    bundle.mkdir(parents=True)
    (bundle / "instruction.md").write_text("CANONICAL PROMPT BODY")
    _write_agent_md(bundle, "name: a\ninstruction_file: instruction.md\n")

    raw = AgentReader().read(FilesystemBundleHandle(bundle))
    assert raw["spec"]["instruction"] == "CANONICAL PROMPT BODY"
    assert raw["spec"]["instruction_file"] == "instruction.md"


def test_instruction_file_nested_within_bundle(tmp_path: Path):
    """instruction_file may live in a subdirectory of the bundle."""
    bundle = tmp_path / "agents" / "a"
    nested = bundle / "prompts"
    nested.mkdir(parents=True)
    (nested / "system.md").write_text("NESTED PROMPT")
    _write_agent_md(bundle, "name: a\ninstruction_file: prompts/system.md\n")

    raw = AgentReader().read(FilesystemBundleHandle(bundle))
    assert raw["spec"]["instruction"] == "NESTED PROMPT"


def test_instruction_file_body_must_be_empty(tmp_path: Path):
    bundle = tmp_path / "agents" / "a"
    bundle.mkdir(parents=True)
    (bundle / "p.md").write_text("X")
    _write_agent_md(bundle, "name: a\ninstruction_file: p.md\n", body="ILLEGAL INLINE BODY")
    with pytest.raises(ValueError, match="instruction_file"):
        AgentReader().read(FilesystemBundleHandle(bundle))


def test_instruction_file_rejects_legacy_frontmatter_instruction(tmp_path: Path):
    """Both frontmatter `instruction:` AND `instruction_file:` → ValueError."""
    bundle = tmp_path / "agents" / "a"
    bundle.mkdir(parents=True)
    (bundle / "p.md").write_text("X")
    _write_agent_md(bundle, "name: a\ninstruction: LEGACY\ninstruction_file: p.md\n")
    with pytest.raises(ValueError, match="frontmatter"):
        AgentReader().read(FilesystemBundleHandle(bundle))


def test_instruction_file_absolute_path_rejected(tmp_path: Path):
    bundle = tmp_path / "agents" / "a"
    _write_agent_md(bundle, "name: a\ninstruction_file: /etc/passwd\n")
    with pytest.raises(ValueError, match="relative"):
        AgentReader().read(FilesystemBundleHandle(bundle))


def test_instruction_file_parent_traversal_rejected(tmp_path: Path):
    """Phase 8 Option A — bundles are atomic; '..' is forbidden in instruction_file."""
    bundle = tmp_path / "agents" / "a"
    _write_agent_md(bundle, "name: a\ninstruction_file: ../shared.md\n")
    with pytest.raises(ValueError, match=r"\.\."):
        AgentReader().read(FilesystemBundleHandle(bundle))


def test_instruction_file_dot_dot_in_middle_rejected(tmp_path: Path):
    """Even nested '..' segments are rejected — the bundle is the boundary."""
    bundle = tmp_path / "agents" / "a"
    _write_agent_md(bundle, "name: a\ninstruction_file: prompts/../../escape.md\n")
    with pytest.raises(ValueError, match=r"\.\."):
        AgentReader().read(FilesystemBundleHandle(bundle))


def test_instruction_file_missing_raises(tmp_path: Path):
    bundle = tmp_path / "agents" / "a"
    _write_agent_md(bundle, "name: a\ninstruction_file: missing.md\n")
    with pytest.raises(FileNotFoundError):
        AgentReader().read(FilesystemBundleHandle(bundle))


def test_writer_emits_instruction_file_with_empty_body(tmp_path: Path):
    src_bundle = tmp_path / "in" / "agents" / "a"
    src_bundle.mkdir(parents=True)
    (src_bundle / "p.md").write_text("X")
    _write_agent_md(src_bundle, "name: a\ninstruction_file: p.md\n")
    raw = AgentReader().read(FilesystemBundleHandle(src_bundle))

    out_bundle = tmp_path / "out" / "agents" / "a"
    out_bundle.mkdir(parents=True)
    AgentWriter().write(FilesystemBundleHandle(out_bundle), raw)

    text = (out_bundle / "AGENT.md").read_text()
    assert "instruction_file:" in text
    body = re.sub(r"^---\n.*?---\n?", "", text, flags=re.DOTALL).strip()
    assert body == "", f"Writer emitted inline body despite instruction_file: {body!r}"
