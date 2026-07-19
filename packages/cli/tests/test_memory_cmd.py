"""`dna memory` — end-to-end, offline (s-memory-verbs).

Drives the real CLI (CliRunner, in-process) against a filesystem scope with the
`search-sqlite` extra present: remember → recall hybrid → forget bi-temporal →
consolidate. Proves the verbs wire through the kernel + provider with no server.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

pytest.importorskip("sqlite_vec", reason="search-sqlite extra not installed")

from dna_cli import main  # noqa: E402

_REASON = "a concrete reason long enough for the affect validator to accept in full"


@pytest.fixture
def scoped(tmp_path, monkeypatch):
    base = tmp_path / "src" / "demo"
    base.mkdir(parents=True)
    (base / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/core/v1\n"
        "kind: Package\nmetadata:\n  name: demo\nspec:\n  title: Demo\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(tmp_path / "src"))
    monkeypatch.setenv("DNA_SEARCH_DIR", str(tmp_path / "search"))
    return tmp_path


def _remember(runner, summary, area, affect="triumph"):
    return runner.invoke(main, [
        "memory", "remember", summary, "--scope", "demo",
        "--area", area, "--affect", affect, "--reason", _REASON, "--json",
    ])


def test_remember_then_recall_hybrid(scoped):
    runner = CliRunner()
    assert _remember(runner, "vector embedding recall cognitive memory", "Feature/memory").exit_code == 0
    assert _remember(runner, "banana tropical yellow fruit smoothie", "Feature/food").exit_code == 0
    assert _remember(runner, "hybrid search fusion reciprocal rank bm25", "Feature/search").exit_code == 0

    res = runner.invoke(main, [
        "memory", "recall", "memory recall cognitive", "--scope", "demo",
        "-k", "3", "--no-reconsolidate", "--json",
    ])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.output)
    assert payload["degraded"] is False  # provider present → hybrid
    assert payload["hits"][0]["kind"] == "Engram"
    # the memory hit carries the retention re-score field
    assert "retention" in payload["hits"][0]


def test_forget_is_bitemporal_and_excluded_from_recall(scoped):
    runner = CliRunner()
    r = _remember(runner, "cache dict ref bug always deep copy the L2 cache", "Feature/kernel", "regret")
    name = json.loads(r.output)["name"]

    fg = runner.invoke(main, ["memory", "forget", name, "--scope", "demo", "--json"])
    assert fg.exit_code == 0, fg.output
    assert json.loads(fg.output)["valid_to"]

    # default list hides it; --all shows it as forgotten
    lst = runner.invoke(main, ["memory", "list", "--scope", "demo", "--json"])
    assert name not in [m["name"] for m in json.loads(lst.output)["memories"]]
    lst_all = runner.invoke(main, ["memory", "list", "--scope", "demo", "--all", "--json"])
    forgotten = [m for m in json.loads(lst_all.output)["memories"] if m["name"] == name]
    assert forgotten and forgotten[0]["state"] == "forgotten"

    # recall never resurfaces it
    res = runner.invoke(main, [
        "memory", "recall", "cache deep copy", "--scope", "demo",
        "-k", "5", "--no-reconsolidate", "--json",
    ])
    assert name not in [h["name"] for h in json.loads(res.output)["hits"]]


def test_consolidate_reports_cleanly(scoped):
    runner = CliRunner()
    _remember(runner, "a fresh memory of the search core", "Feature/search")
    res = runner.invoke(main, ["memory", "consolidate", "--scope", "demo", "--json"])
    assert res.exit_code == 0, res.output
    report = json.loads(res.output)
    assert report["evaluated"] >= 1
    assert report["archived"] == 0  # nothing stale yet


def test_recall_semantic_auto_on_and_flag_off(scoped):
    """s-memory-semantic-recall: with the provider present, auto mode blends the
    ecphory×embedding ranking (hits annotated, payload flags semantic:true);
    --no-semantic restores the exact base hit shape."""
    runner = CliRunner()
    assert _remember(runner, "deep-copy before mutating documents", "Feature/kernel").exit_code == 0
    assert _remember(runner, "banana tropical yellow fruit smoothie", "Feature/food").exit_code == 0

    auto = runner.invoke(main, [
        "memory", "recall", "mutating documents safely", "--scope", "demo",
        "-k", "2", "--no-reconsolidate", "--json",
    ])
    assert auto.exit_code == 0, auto.output
    payload = json.loads(auto.output)
    assert payload["semantic"] is True and payload["degraded"] is False
    top = payload["hits"][0]
    assert top["name"].startswith("rem-")
    assert "rank_recall" in top and "score_recall" in top and top["semantic"] > 0

    off = runner.invoke(main, [
        "memory", "recall", "mutating documents safely", "--scope", "demo",
        "-k", "2", "--no-reconsolidate", "--no-semantic", "--json",
    ])
    assert off.exit_code == 0, off.output
    payload_off = json.loads(off.output)
    assert payload_off["semantic"] is False
    assert all("rank_recall" not in h for h in payload_off["hits"])

    # human output labels the mode
    human = runner.invoke(main, [
        "memory", "recall", "mutating documents safely", "--scope", "demo",
        "-k", "2", "--no-reconsolidate",
    ])
    assert "semantic (ecphory×cosine)" in human.output
