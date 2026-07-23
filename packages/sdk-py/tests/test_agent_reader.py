"""Tests for AgentReader and AgentWriter."""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.kernel.bundle.handle import FilesystemBundleHandle


def _make_agent_bundle(tmp: Path, name: str, frontmatter: str, body: str) -> Path:
    agent_dir = tmp / name
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(f"---\n{frontmatter}---\n\n{body}")
    return agent_dir


class TestAgentReader:
    def _reader(self):
        from dna.extensions.helix import AgentReader
        return AgentReader()

    def test_detect_true(self, tmp_path: Path):
        d = _make_agent_bundle(tmp_path, "my-agent", "name: my-agent\n", "Hello")
        assert self._reader().detect(FilesystemBundleHandle(d)) is True

    def test_detect_false_no_marker(self, tmp_path: Path):
        d = tmp_path / "empty-agent"
        d.mkdir()
        assert self._reader().detect(FilesystemBundleHandle(d)) is False

    def test_read_basic(self, tmp_path: Path):
        fm = "name: helper\ndescription: A helper agent\nmodel: gpt-4\nsoul: my-soul\nskills:\n  - search\n  - summarize\n"
        d = _make_agent_bundle(tmp_path, "helper", fm, "You are a helpful agent.")
        raw = self._reader().read(FilesystemBundleHandle(d))

        assert raw["apiVersion"] == "github.com/ruinosus/dna/v1"
        assert raw["kind"] == "Agent"
        assert raw["metadata"]["name"] == "helper"
        assert raw["metadata"]["description"] == "A helper agent"
        assert raw["spec"]["instruction"] == "You are a helpful agent."
        assert raw["spec"]["model"] == "gpt-4"
        assert raw["spec"]["soul"] == "my-soul"
        assert raw["spec"]["skills"] == ["search", "summarize"]

    def test_read_all_spec_fields(self, tmp_path: Path):
        fm = (
            "name: full-agent\n"
            "description: Full spec\n"
            "labels:\n  env: prod\n"
            "objective: Solve problems\n"
            "type: conversational\n"
            "tools:\n  - calculator\n"
            "team_members:\n  - alice\n"
            "tags:\n  - beta\n"
            "promptTemplate: '{{agent.instruction}}'\n"
        )
        d = _make_agent_bundle(tmp_path, "full-agent", fm, "Full body.")
        raw = self._reader().read(FilesystemBundleHandle(d))

        assert raw["metadata"]["labels"] == {"env": "prod"}
        assert raw["spec"]["objective"] == "Solve problems"
        assert raw["spec"]["type"] == "conversational"
        assert raw["spec"]["tools"] == ["calculator"]
        assert raw["spec"]["team_members"] == ["alice"]
        assert raw["spec"]["tags"] == ["beta"]
        assert raw["spec"]["promptTemplate"] == "{{agent.instruction}}"

    def test_read_fallback_name_from_dir(self, tmp_path: Path):
        fm = "description: no name field\n"
        d = _make_agent_bundle(tmp_path, "dir-name-agent", fm, "Body.")
        raw = self._reader().read(FilesystemBundleHandle(d))
        assert raw["metadata"]["name"] == "dir-name-agent"

    def test_read_collects_subdirs(self, tmp_path: Path):
        d = _make_agent_bundle(tmp_path, "ref-agent", "name: ref-agent\n", "Body.")
        refs = d / "references"
        refs.mkdir()
        (refs / "guide.txt").write_text("some guide")
        raw = self._reader().read(FilesystemBundleHandle(d))
        assert raw["spec"]["references"] == {"guide.txt": "some guide"}

    def test_read_collects_extras(self, tmp_path: Path):
        d = _make_agent_bundle(tmp_path, "extra-agent", "name: extra-agent\n", "Body.")
        custom = d / "custom-dir"
        custom.mkdir()
        (custom / "data.txt").write_text("extra data")
        raw = self._reader().read(FilesystemBundleHandle(d))
        assert raw["spec"]["extras"] == {"custom-dir": {"data.txt": "extra data"}}

    def test_read_collects_root_files(self, tmp_path: Path):
        d = _make_agent_bundle(tmp_path, "root-agent", "name: root-agent\n", "Body.")
        (d / "LICENSE.txt").write_text("MIT")
        raw = self._reader().read(FilesystemBundleHandle(d))
        assert raw["spec"]["root_files"] == {"LICENSE.txt": "MIT"}


class TestAgentWriter:
    def _writer(self):
        from dna.extensions.helix import AgentWriter
        return AgentWriter()

    def test_can_write_agent(self):
        assert self._writer().can_write({"kind": "Agent"}) is True

    def test_can_write_rejects_other(self):
        assert self._writer().can_write({"kind": "Skill"}) is False

    def test_write_creates_agent_md(self, tmp_path: Path):
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "writer-agent", "description": "Test writer"},
            "spec": {"instruction": "Be helpful.", "model": "gpt-4"},
        }
        out = tmp_path / "writer-agent"
        self._writer().write(FilesystemBundleHandle(out), raw)
        content = (out / "AGENT.md").read_text()
        assert "name: writer-agent" in content
        assert "description: Test writer" in content
        assert "model: gpt-4" in content
        assert "Be helpful." in content

    def test_round_trip(self, tmp_path: Path):
        from dna.extensions.helix import AgentReader, AgentWriter

        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "round-trip", "description": "Round trip test"},
            "spec": {
                "instruction": "Do the thing.",
                "model": "gpt-4",
                "skills": ["search"],
            },
        }
        out = tmp_path / "round-trip"
        AgentWriter().write(FilesystemBundleHandle(out), raw)
        result = AgentReader().read(FilesystemBundleHandle(out))

        assert result["metadata"]["name"] == "round-trip"
        assert result["metadata"]["description"] == "Round trip test"
        assert result["spec"]["instruction"] == "Do the thing."
        assert result["spec"]["model"] == "gpt-4"
        assert result["spec"]["skills"] == ["search"]
