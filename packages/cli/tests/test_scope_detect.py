"""``dna scope detect`` — scope-marker detection (i-007).

The detect walk used to look ONLY for the legacy pre-Genome marker
``.dna/<scope>/manifest.yaml``. Every current scope is rooted by
``Genome.yaml`` (Phase 16), so the command always printed
"(no DNA scope found)" and exited 1. These tests pin the fixed
contract: Genome.yaml is the canonical marker, manifest.yaml is
still accepted for legacy trees.
"""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from dna_cli.scope_cmd import scope


def _make_scope(root: Path, name: str, marker: str) -> Path:
    scope_dir = root / ".dna" / name
    scope_dir.mkdir(parents=True)
    (scope_dir / marker).write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        f"metadata:\n  name: {name}\n"
        "spec: {}\n",
        encoding="utf-8",
    )
    return scope_dir


class TestScopeDetect:
    def test_detects_genome_yaml_scope(self, tmp_path: Path) -> None:
        """A scope rooted by Genome.yaml (all current scopes) is detected."""
        _make_scope(tmp_path, "hello-genome", "Genome.yaml")
        result = CliRunner().invoke(scope, ["detect", "--cwd", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "hello-genome"

    def test_detects_genome_yaml_walking_up(self, tmp_path: Path) -> None:
        """Detection walks upward from a nested cwd to the scope root."""
        _make_scope(tmp_path, "hello-genome", "Genome.yaml")
        nested = tmp_path / "src" / "deep" / "inner"
        nested.mkdir(parents=True)
        result = CliRunner().invoke(scope, ["detect", "--cwd", str(nested)])
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "hello-genome"

    def test_detects_legacy_manifest_yaml_scope(self, tmp_path: Path) -> None:
        """Legacy trees rooted by manifest.yaml keep working."""
        _make_scope(tmp_path, "old-scope", "manifest.yaml")
        result = CliRunner().invoke(scope, ["detect", "--cwd", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "old-scope"

    def test_no_scope_found_exits_1(self, tmp_path: Path) -> None:
        """No marker anywhere up the walk → message on stderr + exit 1."""
        lonely = tmp_path / "just-a-dir"
        lonely.mkdir()
        result = CliRunner().invoke(scope, ["detect", "--cwd", str(lonely)])
        assert result.exit_code == 1
        assert "no DNA scope found" in result.output

    def test_dna_dir_without_marker_is_not_a_scope(self, tmp_path: Path) -> None:
        """A .dna/<dir> without either marker (e.g. active-story.txt noise)
        does not count as a scope."""
        (tmp_path / ".dna" / "not-a-scope").mkdir(parents=True)
        (tmp_path / ".dna" / "active-story.txt").write_text("x", encoding="utf-8")
        result = CliRunner().invoke(scope, ["detect", "--cwd", str(tmp_path)])
        assert result.exit_code == 1
