"""TDD for `dna specify wire` — the DNA MCP → spec-kit agent-config projector
(ADR ADR-spec-kit-adoption, Layer 2: "DNA feeds Spec Kit's agent").

Two layers:
  1. Pure planner (no I/O) — build_server_block per agent schema (stdio + http),
     merge_config preserves/idempotent/force, parse_tools.
  2. CLI over a temp project dir — wire creates the right file per tool with the
     right shape; --dry-run --json writes nothing; re-run skips; --force updates;
     a pre-existing unrelated server is preserved.
"""
from __future__ import annotations

import json
import pathlib

import pytest
from click.testing import CliRunner

from dna_cli._speckit_mcp import (
    TOOL_MCP_TARGETS,
    build_server_block,
    merge_config,
    parse_tools,
)
from dna_cli.specify_cmd import specify


# ─── 1. build_server_block per schema ────────────────────────────────────────


def test_stdio_block_claude_cursor():
    b = build_server_block("claude", source_url="postgresql://dna@localhost:5433/dna")
    assert b == {
        "command": "dna",
        "args": ["mcp", "serve"],
        "env": {"DNA_SOURCE_URL": "postgresql://dna@localhost:5433/dna"},
    }


def test_stdio_block_no_source_url_omits_env():
    b = build_server_block("claude")
    assert b == {"command": "dna", "args": ["mcp", "serve"]}
    assert "env" not in b


def test_stdio_block_vscode_has_type_and_env():
    b = build_server_block("vscode", source_url="file:///tmp/x/.dna")
    assert b["type"] == "stdio"
    assert b["command"] == "dna" and b["args"] == ["mcp", "serve"]
    assert b["env"] == {"DNA_SOURCE_URL": "file:///tmp/x/.dna"}


def test_stdio_block_opencode_local_shape():
    b = build_server_block("opencode", source_url="file:///tmp/x/.dna")
    assert b["type"] == "local"
    assert b["command"] == ["dna", "mcp", "serve"]  # opencode: command is an array
    assert b["enabled"] is True
    assert b["environment"] == {"DNA_SOURCE_URL": "file:///tmp/x/.dna"}


def test_http_block_per_schema():
    url = "https://dna.example.com/mcp/"
    assert build_server_block("claude", http_url=url) == {"type": "http", "url": url}
    assert build_server_block("vscode", http_url=url) == {"type": "http", "url": url}
    assert build_server_block("opencode", http_url=url) == {
        "type": "remote", "url": url, "enabled": True,
    }


def test_http_wins_over_source_url():
    b = build_server_block("claude", source_url="file:///x", http_url="https://h/mcp/")
    assert b == {"type": "http", "url": "https://h/mcp/"}


# ─── 2. merge_config ─────────────────────────────────────────────────────────


CLAUDE = TOOL_MCP_TARGETS["claude"]
VSCODE = TOOL_MCP_TARGETS["copilot"]
OPENCODE = TOOL_MCP_TARGETS["opencode"]


def test_merge_into_empty_creates():
    block = build_server_block("claude", source_url="file:///x")
    cfg, outcome = merge_config(None, CLAUDE, block, force=False)
    assert outcome == "created"
    assert cfg == {"mcpServers": {"dna": block}}


def test_merge_preserves_existing_servers():
    existing = {"mcpServers": {"other": {"command": "other-mcp"}}}
    block = build_server_block("claude", source_url="file:///x")
    cfg, outcome = merge_config(existing, CLAUDE, block, force=False)
    assert outcome == "merged"
    assert cfg["mcpServers"]["other"] == {"command": "other-mcp"}
    assert cfg["mcpServers"]["dna"] == block


def test_merge_idempotent_skips_without_force():
    block = build_server_block("claude", source_url="file:///x")
    existing = {"mcpServers": {"dna": {"command": "dna", "args": ["mcp", "serve"]}}}
    cfg, outcome = merge_config(existing, CLAUDE, block, force=False)
    assert outcome == "skipped"
    # untouched — the pre-existing dna block is kept verbatim
    assert cfg["mcpServers"]["dna"] == {"command": "dna", "args": ["mcp", "serve"]}


def test_merge_force_replaces():
    block = build_server_block("claude", source_url="file:///new")
    existing = {"mcpServers": {"dna": {"command": "old"}}}
    cfg, outcome = merge_config(existing, CLAUDE, block, force=True)
    assert outcome == "updated"
    assert cfg["mcpServers"]["dna"] == block


def test_merge_opencode_seeds_schema():
    block = build_server_block("opencode", source_url="file:///x")
    cfg, _ = merge_config(None, OPENCODE, block, force=False)
    assert cfg["$schema"] == "https://opencode.ai/config.json"
    assert cfg["mcp"]["dna"] == block


def test_merge_vscode_uses_servers_key():
    block = build_server_block("vscode", source_url="file:///x")
    cfg, _ = merge_config(None, VSCODE, block, force=False)
    assert "servers" in cfg and "mcpServers" not in cfg
    assert cfg["servers"]["dna"] == block


# ─── 3. parse_tools ──────────────────────────────────────────────────────────


def test_parse_tools_all_and_explicit():
    assert parse_tools("all") == list(TOOL_MCP_TARGETS)
    assert parse_tools("claude, cursor") == ["claude", "cursor"]
    assert parse_tools("claude,claude") == ["claude"]  # dedup


def test_parse_tools_unknown_raises():
    with pytest.raises(ValueError):
        parse_tools("emacs")


# ─── 4. CLI over a temp project dir ──────────────────────────────────────────


@pytest.fixture
def runner():
    return CliRunner()


def _read_json(p: pathlib.Path) -> dict:
    return json.loads(p.read_text())


def test_wire_creates_files_per_tool(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("DNA_SOURCE_URL", "postgresql://dna@localhost:5433/dna")
    r = runner.invoke(
        specify,
        ["wire", "--dir", str(tmp_path), "--tools", "claude,copilot,opencode"],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    # claude → .mcp.json (mcpServers)
    claude = _read_json(tmp_path / ".mcp.json")
    assert claude["mcpServers"]["dna"]["command"] == "dna"
    assert claude["mcpServers"]["dna"]["env"]["DNA_SOURCE_URL"] == \
        "postgresql://dna@localhost:5433/dna"
    # copilot → .vscode/mcp.json (servers, type=stdio)
    vscode = _read_json(tmp_path / ".vscode" / "mcp.json")
    assert vscode["servers"]["dna"]["type"] == "stdio"
    # opencode → opencode.json (mcp, type=local, $schema)
    oc = _read_json(tmp_path / "opencode.json")
    assert oc["mcp"]["dna"]["type"] == "local"
    assert oc["$schema"] == "https://opencode.ai/config.json"


def test_wire_dry_run_json_writes_nothing(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("DNA_SOURCE_URL", "file:///tmp/x/.dna")
    r = runner.invoke(
        specify,
        ["wire", "--dir", str(tmp_path), "--tools", "claude", "--dry-run", "--json"],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload["dry_run"] is True
    assert payload["targets"][0]["tool"] == "claude"
    assert payload["targets"][0]["config"] == ".mcp.json"
    # nothing on disk
    assert not (tmp_path / ".mcp.json").exists()


def test_wire_idempotent_rerun_skips(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("DNA_SOURCE_URL", "file:///tmp/x/.dna")
    args = ["wire", "--dir", str(tmp_path), "--tools", "claude"]
    r1 = runner.invoke(specify, args, catch_exceptions=False)
    assert r1.exit_code == 0
    first = (tmp_path / ".mcp.json").read_text()
    r2 = runner.invoke(specify, args, catch_exceptions=False)
    assert r2.exit_code == 0, r2.output
    assert "skipped" in r2.output
    # byte-identical — a re-run never churns the file
    assert (tmp_path / ".mcp.json").read_text() == first


def test_wire_force_updates_and_preserves_other_server(runner, tmp_path, monkeypatch):
    # Seed a config with an unrelated server already present.
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"github": {"command": "gh-mcp"}}}, indent=2) + "\n"
    )
    monkeypatch.setenv("DNA_SOURCE_URL", "file:///tmp/new/.dna")
    r = runner.invoke(
        specify,
        ["wire", "--dir", str(tmp_path), "--tools", "claude"],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    cfg = _read_json(tmp_path / ".mcp.json")
    # the unrelated server survives; dna is added alongside it
    assert cfg["mcpServers"]["github"] == {"command": "gh-mcp"}
    assert cfg["mcpServers"]["dna"]["env"]["DNA_SOURCE_URL"] == "file:///tmp/new/.dna"


def test_wire_http_transport(runner, tmp_path):
    r = runner.invoke(
        specify,
        ["wire", "--dir", str(tmp_path), "--tools", "claude",
         "--http", "https://dna.example.com/mcp/"],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    cfg = _read_json(tmp_path / ".mcp.json")
    assert cfg["mcpServers"]["dna"] == {"type": "http", "url": "https://dna.example.com/mcp/"}


def test_wire_explicit_source_url_overrides_env(runner, tmp_path, monkeypatch):
    monkeypatch.setenv("DNA_SOURCE_URL", "postgresql://dna@localhost:5433/dna")
    r = runner.invoke(
        specify,
        ["wire", "--dir", str(tmp_path), "--tools", "claude",
         "--source-url", "file:///custom/.dna"],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    cfg = _read_json(tmp_path / ".mcp.json")
    assert cfg["mcpServers"]["dna"]["env"]["DNA_SOURCE_URL"] == "file:///custom/.dna"


def test_wire_unknown_tool_fails(runner, tmp_path):
    r = runner.invoke(specify, ["wire", "--dir", str(tmp_path), "--tools", "emacs"])
    assert r.exit_code != 0
    assert "unknown tool" in r.output
