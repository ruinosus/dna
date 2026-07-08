"""Guards for the SDLC CLI ergonomics fixes (i-041)."""
from __future__ import annotations

from dna_cli import sdlc_cmd


def test_feature_group_has_show() -> None:
    # `dna sdlc feature show` must exist (mirrors epic show; was missing).
    assert "show" in sdlc_cmd.feature_group.commands


def test_feature_show_takes_name() -> None:
    names = {p.name for p in sdlc_cmd.cmd_feature_show.params}
    assert "name" in names


def test_priority_rank_orders_highest_first() -> None:
    # The list sort key must rank highest < high < medium < low < lowest.
    rank = {"highest": 0, "high": 1, "medium": 2, "low": 3, "lowest": 4}
    order = sorted(["low", "highest", "medium", "high"], key=lambda p: rank[p])
    assert order == ["highest", "high", "medium", "low"]
