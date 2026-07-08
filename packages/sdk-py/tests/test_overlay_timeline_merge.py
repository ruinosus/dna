"""Tests for cross-overlay timeline merging in DefaultLayerResolver.

ADR ``docs/superpowers/specs/2026-05-10-tenant-overlay-timeline-adr.md``.
``spec.timeline[]`` is append-only — events recorded against an overlay
must concat with base events (sorted newest-first), not replace them.
This is orthogonal to the regular spec deep-merge and applies even
under LOCKED policy.
"""
from __future__ import annotations

import warnings

from dna.kernel.layer_resolver import (
    DefaultLayerResolver,
    _merge_timeline_arrays,
)
from dna.kernel.protocols import LayerPolicy


class FakeSource:
    def __init__(self, layers: dict[tuple[str, str], list[dict]]) -> None:
        self._layers = layers

    def load_layer(self, scope: str, layer_id: str, value: str) -> list[dict]:
        return self._layers.get((layer_id, value), [])


def _ev(at: str, type_: str, **kw: object) -> dict:
    e: dict = {"at": at, "actor": "claude-code", "type": type_}
    e.update(kw)
    return e


def _story(name: str = "s-foo", *, timeline: list[dict] | None = None,
           extra_spec: dict | None = None) -> dict:
    spec: dict = {"description": "x", "status": "todo", "feature": "f-bar"}
    if timeline is not None:
        spec["timeline"] = timeline
    if extra_spec:
        spec.update(extra_spec)
    return {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "Story",
        "metadata": {"name": name},
        "spec": spec,
    }


# ──────────────────────────────────────────────────────────────────────
# _merge_timeline_arrays helper
# ──────────────────────────────────────────────────────────────────────


class TestMergeHelper:
    def test_returns_none_when_neither_side_has_timeline(self) -> None:
        assert _merge_timeline_arrays({}, {}) is None
        assert _merge_timeline_arrays({"x": 1}, {"y": 2}) is None

    def test_concats_sorted_descending_by_at(self) -> None:
        base = {"timeline": [_ev("2026-05-09T10:00:00Z", "groom")]}
        overlay = {"timeline": [_ev("2026-05-10T12:00:00Z", "comment")]}
        merged = _merge_timeline_arrays(base, overlay)
        assert merged is not None
        assert [e["at"] for e in merged] == [
            "2026-05-10T12:00:00Z",
            "2026-05-09T10:00:00Z",
        ]

    def test_dedups_identical_events(self) -> None:
        ev = _ev("2026-05-10T10:00:00Z", "status_change", **{"from": "todo", "to": "done"})
        merged = _merge_timeline_arrays(
            {"timeline": [ev]}, {"timeline": [dict(ev)]}
        )
        assert merged is not None
        assert len(merged) == 1

    def test_passes_through_when_only_one_side_has_timeline(self) -> None:
        events = [_ev("2026-05-10T10:00:00Z", "groom")]
        # Overlay-only.
        merged = _merge_timeline_arrays({}, {"timeline": events})
        assert merged is not None
        assert len(merged) == 1
        # Base-only.
        merged = _merge_timeline_arrays({"timeline": events}, {})
        assert merged is not None
        assert len(merged) == 1

    def test_ignores_non_dict_entries(self) -> None:
        base = {"timeline": [_ev("2026-05-10T10:00:00Z", "groom"), "garbage"]}
        merged = _merge_timeline_arrays(base, {})
        assert merged is not None
        assert len(merged) == 1


# ──────────────────────────────────────────────────────────────────────
# OPEN policy — timeline concats, has_overlay reflects only override fields
# ──────────────────────────────────────────────────────────────────────


class TestOpenPolicy:
    def test_timeline_concats_base_and_overlay(self) -> None:
        resolver = DefaultLayerResolver()
        base = _story(timeline=[_ev("2026-05-09T10:00:00Z", "groom")])
        overlay = {
            "kind": "Story",
            "metadata": {"name": "s-foo"},
            "spec": {
                "timeline": [_ev("2026-05-10T12:00:00Z", "comment", actor="bob")],
            },
        }
        src = FakeSource({("tenant", "acme"): [overlay]})
        out = resolver.resolve([base], {"tenant": "acme"}, src, "scope", {})
        tl = out[0]["spec"]["timeline"]
        assert [e["at"] for e in tl] == [
            "2026-05-10T12:00:00Z",
            "2026-05-09T10:00:00Z",
        ]

    def test_timeline_only_overlay_does_not_stamp_has_overlay(self) -> None:
        # Timeline is append-only metadata, not a per-field override —
        # an overlay that adds only timeline events shouldn't make
        # Studio show the "this story is forked" banner.
        resolver = DefaultLayerResolver()
        base = _story(timeline=[_ev("2026-05-09T10:00:00Z", "groom")])
        overlay = {
            "kind": "Story",
            "metadata": {"name": "s-foo"},
            "spec": {"timeline": [_ev("2026-05-10T10:00:00Z", "comment")]},
        }
        src = FakeSource({("tenant", "acme"): [overlay]})
        out = resolver.resolve([base], {"tenant": "acme"}, src, "scope", {})
        md = out[0]["metadata"]
        assert md.get("has_overlay") is not True
        assert not md.get("overlay_fields")

    def test_timeline_excluded_from_overlay_fields_when_present_with_overrides(
        self,
    ) -> None:
        resolver = DefaultLayerResolver()
        base = _story()
        overlay = {
            "kind": "Story",
            "metadata": {"name": "s-foo"},
            "spec": {
                "status": "in-progress",
                "timeline": [_ev("2026-05-10T10:00:00Z", "status_change")],
            },
        }
        src = FakeSource({("tenant", "acme"): [overlay]})
        out = resolver.resolve([base], {"tenant": "acme"}, src, "scope", {})
        md = out[0]["metadata"]
        assert md["has_overlay"] is True
        assert md["overlay_fields"] == ["status"]


# ──────────────────────────────────────────────────────────────────────
# RESTRICTED policy — timeline still merges
# ──────────────────────────────────────────────────────────────────────


class TestRestrictedPolicy:
    def test_timeline_merges_under_restricted(self) -> None:
        resolver = DefaultLayerResolver()
        base = _story(timeline=[_ev("2026-05-09T10:00:00Z", "groom")])
        overlay = {
            "kind": "Story",
            "metadata": {"name": "s-foo"},
            "spec": {
                "timeline": [_ev("2026-05-10T12:00:00Z", "comment")],
            },
        }
        src = FakeSource({("tenant", "acme"): [overlay]})
        out = resolver.resolve(
            [base],
            {"tenant": "acme"},
            src,
            "scope",
            {"Story": LayerPolicy.RESTRICTED},
        )
        tl = out[0]["spec"]["timeline"]
        assert len(tl) == 2

    def test_timeline_does_not_trigger_unknown_key_warning(self) -> None:
        # Restricted policy warns on overlay keys absent from base; the
        # timeline-extraction shim must keep that warning silent when
        # only timeline changed.
        resolver = DefaultLayerResolver()
        base = _story()  # no timeline on base
        overlay = {
            "kind": "Story",
            "metadata": {"name": "s-foo"},
            "spec": {"timeline": [_ev("2026-05-10T10:00:00Z", "comment")]},
        }
        src = FakeSource({("tenant", "acme"): [overlay]})
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            out = resolver.resolve(
                [base],
                {"tenant": "acme"},
                src,
                "scope",
                {"Story": LayerPolicy.RESTRICTED},
            )
        assert not any(
            "tried to add key 'timeline'" in str(w.message) for w in captured
        )
        assert len(out[0]["spec"]["timeline"]) == 1


# ──────────────────────────────────────────────────────────────────────
# LOCKED policy — timeline still appends, locked-warning suppressed
# ──────────────────────────────────────────────────────────────────────


class TestLockedPolicy:
    def test_timeline_only_overlay_appends_under_locked(self) -> None:
        resolver = DefaultLayerResolver()
        base = _story(timeline=[_ev("2026-05-09T10:00:00Z", "groom")])
        overlay = {
            "kind": "Story",
            "metadata": {"name": "s-foo"},
            "spec": {"timeline": [_ev("2026-05-10T12:00:00Z", "comment")]},
        }
        src = FakeSource({("tenant", "acme"): [overlay]})
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            out = resolver.resolve(
                [base],
                {"tenant": "acme"},
                src,
                "scope",
                {"Story": LayerPolicy.LOCKED},
            )
        # Two events total — overlay timeline merged in spite of LOCKED.
        assert len(out[0]["spec"]["timeline"]) == 2
        # No "tried to modify locked" warning when overlay only adds timeline.
        assert not any(
            "tried to modify locked" in str(w.message) for w in captured
        )

    def test_locked_still_blocks_non_timeline_field_changes(self) -> None:
        resolver = DefaultLayerResolver()
        base = _story()
        overlay = {
            "kind": "Story",
            "metadata": {"name": "s-foo"},
            "spec": {"status": "done"},  # no timeline; pure override attempt
        }
        src = FakeSource({("tenant", "acme"): [overlay]})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = resolver.resolve(
                [base],
                {"tenant": "acme"},
                src,
                "scope",
                {"Story": LayerPolicy.LOCKED},
            )
        # Override ignored — base value preserved.
        assert out[0]["spec"]["status"] == "todo"
