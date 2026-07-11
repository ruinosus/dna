"""Tests for ``dna new`` — scaffold a valid Kind skeleton (s-dx-new-scaffolding).

Exercises the REAL write path (dna_session → kernel.write_document → the
registered readers/writers) against a filesystem scope: the scaffolded doc
must land on disk in the right bundle shape, read back valid, be idempotent
(no clobber without --force), and — the whole point — an author scaffolds an
agent + soul with a named layout and gets a composing prompt WITHOUT ever
writing Mustache.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from dna_cli.new_cmd import new


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def scope(tmp_path, monkeypatch):
    """A filesystem .dna/demo scope with just a Genome, pinned via env."""
    root = tmp_path / ".dna" / "demo"
    root.mkdir(parents=True)
    (root / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        "metadata:\n  name: demo\n"
        "spec:\n  default_agent: concierge\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DNA_SOURCE_URL", f"file://{(tmp_path / '.dna').resolve()}")
    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    return tmp_path


def _run(runner, *args):
    return runner.invoke(new, list(args), catch_exceptions=False)


class TestScaffoldSoul:
    def test_soul_is_single_file(self, runner, scope):
        r = _run(runner, "soul", "warm-host", "--scope", "demo", "-d", "Warm voice")
        assert r.exit_code == 0, r.output
        base = scope / ".dna" / "demo" / "souls" / "warm-host"
        assert (base / "SOUL.md").exists()
        # s-dx-single-file-soul: no soul.json ceremony.
        assert not (base / "soul.json").exists()
        text = (base / "SOUL.md").read_text()
        assert "warm-host" in text and "{{" not in text

    def test_json_output(self, runner, scope):
        r = _run(runner, "soul", "warm-host", "--scope", "demo", "--json")
        payload = json.loads(r.output)
        assert payload["created"] is True
        assert payload["kind"] == "Soul"
        assert "soul_content" in payload["spec_fields"]


class TestScaffoldAgent:
    def test_agent_bundle_with_layout(self, runner, scope):
        r = _run(
            runner, "agent", "concierge", "--scope", "demo",
            "--soul", "warm-host", "--layout", "persona-first",
            "--model", "openai:gpt-4o-mini",
        )
        assert r.exit_code == 0, r.output
        agent_md = scope / ".dna" / "demo" / "agents" / "concierge" / "AGENT.md"
        assert agent_md.exists()
        text = agent_md.read_text()
        assert "layout: persona-first" in text
        assert "soul: warm-host" in text
        # The author scaffolds a persona-first agent with NO raw Mustache.
        assert "{{" not in text and "promptTemplate" not in text

    def test_bad_layout_rejected(self, runner, scope):
        r = runner.invoke(
            new,
            ["agent", "x", "--scope", "demo", "--layout", "persona_first"],
        )
        assert r.exit_code != 0  # click.Choice rejects the typo


class TestScaffoldGuardrail:
    def test_guardrail_scaffold(self, runner, scope):
        r = _run(
            runner, "guardrail", "no-pii", "--scope", "demo",
            "--severity", "error", "--guard-scope", "output",
        )
        assert r.exit_code == 0, r.output
        # Guardrail persisted + reads back with the right severity/scope.
        from dna_cli._ctx import dna_session
        with dna_session("demo") as s:
            doc = s.get_doc("Guardrail", "no-pii")
            assert doc is not None
            assert doc.spec["severity"] == "error"
            assert doc.spec["scope"] == "output"


class TestIdempotency:
    def test_no_clobber_without_force(self, runner, scope):
        assert _run(runner, "soul", "s1", "--scope", "demo").exit_code == 0
        r2 = runner.invoke(new, ["soul", "s1", "--scope", "demo"])
        assert r2.exit_code != 0
        assert "already exists" in r2.output

    def test_force_overwrites(self, runner, scope):
        assert _run(runner, "soul", "s1", "--scope", "demo").exit_code == 0
        r2 = _run(runner, "soul", "s1", "--scope", "demo", "--force")
        assert r2.exit_code == 0

    def test_bad_name_rejected(self, runner, scope):
        r = runner.invoke(new, ["soul", "Not A Slug", "--scope", "demo"])
        assert r.exit_code != 0
        assert "slug" in r.output.lower()


class TestZeroToComposedPrompt:
    """The headline flow: scaffold soul + persona-first agent, then compose —
    a real prompt with the Soul BEFORE the instruction, no Mustache authored."""

    def test_scaffold_then_compose_persona_first(self, runner, scope):
        assert _run(runner, "soul", "host", "--scope", "demo").exit_code == 0
        assert _run(
            runner, "agent", "concierge", "--scope", "demo",
            "--soul", "host", "--layout", "persona-first",
        ).exit_code == 0

        from dna.kernel import Kernel
        mi = Kernel.quick("demo", base_dir=str(scope / ".dna"))
        _ = mi.documents
        prompt = mi.build_prompt(agent="concierge")
        assert "voice, values" in prompt  # soul prose landed
        assert "what this agent does" in prompt  # instruction landed
        assert prompt.index("voice, values") < prompt.index("what this agent does"), (
            "persona-first: the Soul must precede the instruction"
        )


class TestScaffoldTool:
    """`dna new tool` — tools as data (s-dna-new-tool). Scaffolds a valid Tool
    doc through the real write path; the agent-facing surface is readable via
    `dna.load_tools`."""

    def test_tool_scaffold_is_valid_and_readable(self, runner, scope):
        r = _run(
            runner, "tool", "weather", "--scope", "demo",
            "-d", "Get the current weather for a city.", "--type", "http",
        )
        assert r.exit_code == 0, r.output
        doc = scope / ".dna" / "demo" / "tools" / "weather.yaml"
        assert doc.exists(), "Tool stored as tools/<name>.yaml"
        text = doc.read_text()
        assert "kind: Tool" in text
        assert "Get the current weather" in text

        # The whole point: the agent-facing surface reads back via load_tools.
        from dna import load_tools
        tools = load_tools("demo", base_dir=str(scope / ".dna"))
        assert "weather" in tools.names()
        surface = tools["weather"]
        assert surface.description == "Get the current weather for a city."
        assert "properties" in surface.parameters

    def test_tool_json_output(self, runner, scope):
        r = _run(runner, "tool", "weather", "--scope", "demo", "--json")
        payload = json.loads(r.output)
        assert payload["created"] is True
        assert payload["kind"] == "Tool"
        assert "type" in payload["spec_fields"]

    def test_tool_idempotent_without_force(self, runner, scope):
        assert _run(runner, "tool", "weather", "--scope", "demo").exit_code == 0
        r = _run(runner, "tool", "weather", "--scope", "demo", "--json")
        assert json.loads(r.output)["created"] is False  # no clobber

    def test_tool_force_overwrites(self, runner, scope):
        assert _run(runner, "tool", "weather", "--scope", "demo").exit_code == 0
        r = _run(
            runner, "tool", "weather", "--scope", "demo",
            "-d", "New description.", "--force", "--json",
        )
        assert json.loads(r.output)["created"] is True
