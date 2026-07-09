"""Tests for `dna research` CLI (s-dna-research-kind).

Covers the pure/authoring-boundary pieces without a live kernel source:
  - spec/name extraction helpers,
  - schema validation gate (`_validate_spec_or_die`),
  - `create` argument guards (bad kind / missing name) that fire BEFORE
    any kernel write.

End-to-end list/show/create against a filesystem source is exercised by
the dogfood run (3 real Research docs authored in .dna/dna-development/).
"""
from __future__ import annotations

import pytest

from dna_cli import research_cmd
from dna_cli.research_cmd import _name_of, _spec_of, _validate_spec_or_die


class _Doc:
    def __init__(self, spec, name=None):
        self.spec = spec
        if name is not None:
            self.name = name


def test_spec_of_from_object() -> None:
    assert _spec_of(_Doc({"title": "x"})) == {"title": "x"}


def test_spec_of_from_dict() -> None:
    assert _spec_of({"spec": {"status": "draft"}}) == {"status": "draft"}


def test_spec_of_handles_missing() -> None:
    assert _spec_of(_Doc(None)) == {}


def test_name_of_prefers_attr() -> None:
    assert _name_of(_Doc({}, name="rsh-a")) == "rsh-a"


def test_name_of_from_metadata_dict() -> None:
    assert _name_of({"metadata": {"name": "rsh-b"}}) == "rsh-b"


def test_validate_ok_spec_passes() -> None:
    good = {
        "title": "T",
        "objective": "O",
        "methodology": "synthesis",
        "status": "published",
        "findings": [
            {"id": "f-a", "title": "A", "evidence_rating": "evidence-based"},
        ],
        "recommendations": [
            {"id": "rec-a", "priority": "high", "summary": "do it"},
        ],
    }
    # Should not raise.
    _validate_spec_or_die("mem.yaml", good)


def test_validate_bad_finding_id_raises() -> None:
    bad = {
        "title": "T",
        "objective": "O",
        "methodology": "synthesis",
        "status": "published",
        # id must match ^f-...; also missing evidence_rating
        "findings": [{"id": "BADID", "title": "A"}],
    }
    with pytest.raises(SystemExit):
        _validate_spec_or_die("mem.yaml", bad)


def test_validate_missing_required_raises() -> None:
    with pytest.raises(SystemExit):
        _validate_spec_or_die("mem.yaml", {"title": "only"})


def test_create_rejects_non_research_kind(runner, tmp_path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text("kind: Story\nmetadata:\n  name: s-x\nspec: {}\n")
    res = runner.invoke(research_cmd.research, ["create", str(p)])
    assert res.exit_code != 0
    assert "kind must be 'Research'" in res.output


def test_create_rejects_missing_name(runner, tmp_path) -> None:
    p = tmp_path / "x.yaml"
    p.write_text("kind: Research\nmetadata: {}\nspec:\n  title: t\n")
    res = runner.invoke(research_cmd.research, ["create", str(p)])
    assert res.exit_code != 0
    assert "missing metadata.name" in res.output
