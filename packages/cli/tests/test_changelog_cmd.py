"""`dna sdlc changelog` — release-notes authoring (s-semver-changelog-on-publish).

Keep a Changelog 1.1.0: accumulate under [Unreleased], then `release` cuts them
into a SemVer version and reopens a fresh [Unreleased]. The pure helpers carry
the logic; the live write is verified against the stack separately.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from dna_cli.sdlc_cmd import (
    _CHANGELOG_CATEGORIES,
    _changelog_unreleased_entry,
    _merge_changelog_items,
    changelog_unreleased,
)


@pytest.fixture
def runner():
    return CliRunner()


def test_unreleased_entry_created_at_top():
    spec: dict = {"versions": []}
    e = _changelog_unreleased_entry(spec)
    assert e["version"] == "[Unreleased]"
    assert spec["versions"][0] is e


def test_unreleased_entry_reused_not_duplicated():
    spec = {"versions": [{"version": "[Unreleased]", "added": ["x"]}]}
    e = _changelog_unreleased_entry(spec)
    assert e["added"] == ["x"]  # same entry, not a new one
    assert sum(v["version"] == "[Unreleased]" for v in spec["versions"]) == 1


def test_unreleased_entry_inserted_above_released_versions():
    spec = {"versions": [{"version": "1.0.0", "added": ["old"]}]}
    e = _changelog_unreleased_entry(spec)
    assert spec["versions"][0] is e
    assert spec["versions"][1]["version"] == "1.0.0"


def test_merge_appends_per_category_and_counts():
    e: dict = {}
    n = _merge_changelog_items(e, {"added": ("a", "b"), "fixed": ("c",), "changed": ()})
    assert n == 3
    assert e["added"] == ["a", "b"]
    assert e["fixed"] == ["c"]
    assert "changed" not in e  # empty category not materialized


def test_release_cut_stamps_version_and_reopens_unreleased():
    # Mirrors changelog_release: accumulate → stamp [Unreleased] as the version
    # → open a fresh [Unreleased] on top.
    spec: dict = {"versions": []}
    entry = _changelog_unreleased_entry(spec)
    _merge_changelog_items(entry, {"added": ("feature x",)})
    entry["version"] = "1.0.0"
    entry["date"] = "2026-06-16"
    spec["versions"].insert(0, {"version": "[Unreleased]"})

    assert spec["versions"][0]["version"] == "[Unreleased]"
    assert spec["versions"][1]["version"] == "1.0.0"
    assert spec["versions"][1]["added"] == ["feature x"]
    assert spec["versions"][1]["date"] == "2026-06-16"


def test_categories_are_keep_a_changelog():
    assert _CHANGELOG_CATEGORIES == (
        "added", "changed", "deprecated", "removed", "fixed", "security",
    )


def test_unreleased_rejects_empty_offline(runner):
    # The "nothing to add" guard fires BEFORE any session/DB is opened.
    r = runner.invoke(changelog_unreleased, ["--scope", "x"])
    assert r.exit_code != 0
    assert "nothing to add" in r.output
