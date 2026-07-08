"""Tests for the rich-plan-from-file opt-in (s-markdown-explorer-standard-all-viewers).

Motivation: the inline `--plan "1 line"` gate shortcut produces thin plans.
For substantial work you want to pour a rich markdown plan (e.g. the output
of the superpowers writing-plans skill, or BMAD/spec-kit/hand-written) into
the Plan body — WITHOUT making any single methodology the standard. These
flags do exactly that: read a markdown file -> Plan body, opt-in.

- `dna sdlc plan create --body-file <path> [--methodology X]`
- `dna sdlc story start  --plan-file <path> [--methodology X]`

The file-read helper is pure (no source) and tested directly. The gate
rejections (missing file, mutual exclusion) fire BEFORE any source write,
mirroring test_story_start_gate.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from dna_cli import sdlc_cmd


def test_read_body_file_returns_content(tmp_path: Path) -> None:
    f = tmp_path / "plan.md"
    content = "# Plano\n\n## Abordagem\n- passo 1\n- passo 2\n"
    f.write_text(content, encoding="utf-8")
    assert sdlc_cmd._read_body_file(str(f)) == content


def test_read_body_file_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        sdlc_cmd._read_body_file(str(tmp_path / "nope.md"))


def test_read_body_file_rejects_empty(tmp_path: Path) -> None:
    f = tmp_path / "empty.md"
    f.write_text("   \n\t\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        sdlc_cmd._read_body_file(str(f))


def test_plan_create_exposes_body_file_and_methodology() -> None:
    names = {o.name for o in sdlc_cmd.cmd_plan_create.params}
    assert {"body_file", "methodology"} <= names


def test_story_start_exposes_plan_file_and_methodology() -> None:
    names = {o.name for o in sdlc_cmd.cmd_story_start.params}
    assert {"plan_file", "methodology"} <= names


def test_story_start_plan_file_missing_rejected() -> None:
    # A non-existent --plan-file is rejected (the read helper fails) before
    # any source write.
    r = CliRunner().invoke(
        sdlc_cmd.sdlc,
        ["story", "start", "s-x", "--plan-file", "/no/such/file.md",
         "--scope", "dna-development"],
    )
    assert r.exit_code != 0


def test_story_start_plan_text_and_plan_file_mutually_exclusive(tmp_path: Path) -> None:
    # Giving BOTH --plan (inline) and --plan-file is rejected pre-write — the
    # mutual-exclusion guard runs before the file is even read.
    f = tmp_path / "plan.md"
    f.write_text("# real plan body\n", encoding="utf-8")
    r = CliRunner().invoke(
        sdlc_cmd.sdlc,
        ["story", "start", "s-x", "--plan", "inline", "--plan-file", str(f),
         "--scope", "dna-development"],
    )
    assert r.exit_code != 0
    assert "exclus" in r.output.lower() or "apenas um" in r.output.lower()


def test_plan_create_body_and_body_file_mutually_exclusive(tmp_path: Path) -> None:
    f = tmp_path / "plan.md"
    f.write_text("# real plan body\n", encoding="utf-8")
    r = CliRunner().invoke(
        sdlc_cmd.sdlc,
        ["plan", "create", "plan-x", "--title", "P", "--body", "inline",
         "--body-file", str(f), "--scope", "dna-development"],
    )
    assert r.exit_code != 0
    assert "exclus" in r.output.lower() or "apenas um" in r.output.lower()
