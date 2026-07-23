"""Tests for Phase 2 overlay-metadata stamping in DefaultLayerResolver.

Studio surfaces ``metadata.has_overlay`` + ``metadata.overlay_fields`` on
the editors so the user knows whether they're seeing a base+overlay
merge and which fields are tenant-specific.
"""
from __future__ import annotations

from dna.kernel.compose.layer_resolver import (
    DefaultLayerResolver,
    _stamp_overlay_metadata,
)
from dna.kernel.protocols import LayerPolicy


class FakeSource:
    """Minimal source stub returning a fixed overlay set per layer dim."""

    def __init__(self, layers: dict[tuple[str, str], list[dict]]) -> None:
        self._layers = layers

    def load_layer(self, scope: str, layer_id: str, value: str) -> list[dict]:
        return self._layers.get((layer_id, value), [])


# ──────────────────────────────────────────────────────────────────────
# _stamp_overlay_metadata helper
# ──────────────────────────────────────────────────────────────────────


class TestStamp:
    def test_marks_doc_as_overlaid_with_field_list(self) -> None:
        doc: dict = {"metadata": {"name": "x"}, "spec": {}}
        _stamp_overlay_metadata(doc, overlay_fields=["a", "b"])
        assert doc["metadata"]["has_overlay"] is True
        assert doc["metadata"]["overlay_fields"] == ["a", "b"]

    def test_overlay_only_sets_fields_to_none(self) -> None:
        doc: dict = {"metadata": {"name": "x"}, "spec": {}}
        _stamp_overlay_metadata(doc, overlay_fields=None)
        assert doc["metadata"]["has_overlay"] is True
        assert doc["metadata"]["overlay_fields"] is None

    def test_unions_fields_across_calls(self) -> None:
        # Multiple layer dimensions hitting the same doc should accumulate
        # their fields, not clobber.
        doc: dict = {"metadata": {"name": "x"}}
        _stamp_overlay_metadata(doc, overlay_fields=["a"])
        _stamp_overlay_metadata(doc, overlay_fields=["b", "a"])
        assert doc["metadata"]["overlay_fields"] == ["a", "b"]

    def test_creates_metadata_if_absent(self) -> None:
        doc: dict = {"kind": "X"}
        _stamp_overlay_metadata(doc, overlay_fields=["a"])
        assert doc["metadata"] == {
            "has_overlay": True,
            "overlay_fields": ["a"],
        }


# ──────────────────────────────────────────────────────────────────────
# OPEN policy — deep merge stamps overlay_fields = top-level overlay keys
# ──────────────────────────────────────────────────────────────────────


def _base_doc() -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/eval/v1",
        "kind": "EvalCase",
        "metadata": {"name": "fairness-bias"},
        "spec": {
            "prompt": "base prompt",
            "expected_keywords": ["fairness", "bias"],
            "forbidden_keywords": ["gender"],
        },
    }


class TestOpenPolicyMerge:
    def test_overlay_fields_lists_overridden_keys(self) -> None:
        resolver = DefaultLayerResolver()
        overlay = {
            "kind": "EvalCase",
            "metadata": {"name": "fairness-bias"},
            "spec": {
                "forbidden_keywords": ["gender", "pronoun"],
                "prompt": "tenant prompt",
            },
        }
        src = FakeSource({("tenant", "acme"): [overlay]})
        result = resolver.resolve(
            [_base_doc()], {"tenant": "acme"}, src, "hr-screening", {}
        )
        assert len(result) == 1
        md = result[0]["metadata"]
        assert md["has_overlay"] is True
        assert sorted(md["overlay_fields"]) == ["forbidden_keywords", "prompt"]
        # Spec actually merged.
        assert result[0]["spec"]["forbidden_keywords"] == ["gender", "pronoun"]
        assert result[0]["spec"]["prompt"] == "tenant prompt"
        # Untouched fields preserved.
        assert result[0]["spec"]["expected_keywords"] == ["fairness", "bias"]

    def test_no_overlay_doc_means_no_metadata_stamp(self) -> None:
        resolver = DefaultLayerResolver()
        src = FakeSource({})  # no overlays
        result = resolver.resolve(
            [_base_doc()], {"tenant": "acme"}, src, "hr-screening", {}
        )
        md = result[0]["metadata"]
        assert "has_overlay" not in md or md["has_overlay"] is not True
        assert "overlay_fields" not in md or not md.get("overlay_fields")


# ──────────────────────────────────────────────────────────────────────
# Overlay-only add — sentinel overlay_fields=None
# ──────────────────────────────────────────────────────────────────────


class TestOverlayOnlyAdd:
    def test_new_doc_from_overlay_marks_as_full_overlay(self) -> None:
        resolver = DefaultLayerResolver()
        overlay_only = {
            "apiVersion": "github.com/ruinosus/dna/eval/v1",
            "kind": "EvalCase",
            "metadata": {"name": "tenant-only-case"},
            "spec": {"prompt": "acme exclusive"},
        }
        src = FakeSource({("tenant", "acme"): [overlay_only]})
        result = resolver.resolve(
            [_base_doc()], {"tenant": "acme"}, src, "hr-screening", {}
        )
        # 2 docs: base + overlay-only add.
        added = next(
            d for d in result if d["metadata"]["name"] == "tenant-only-case"
        )
        assert added["metadata"]["has_overlay"] is True
        assert added["metadata"]["overlay_fields"] is None
        # And the base doc stays untouched (no overlay metadata).
        base_match = next(
            d for d in result if d["metadata"]["name"] == "fairness-bias"
        )
        assert base_match["metadata"].get("has_overlay") is not True


# ──────────────────────────────────────────────────────────────────────
# RESTRICTED policy — overlay_fields excludes dropped keys
# ──────────────────────────────────────────────────────────────────────


class TestRestrictedPolicy:
    def test_only_existing_keys_stamped(self) -> None:
        resolver = DefaultLayerResolver()
        overlay = {
            "kind": "EvalCase",
            "metadata": {"name": "fairness-bias"},
            "spec": {
                "forbidden_keywords": ["gender", "pronoun"],
                # ``new_field`` doesn't exist on base — restricted drops it.
                "new_field": "value",
            },
        }
        src = FakeSource({("tenant", "acme"): [overlay]})
        result = resolver.resolve(
            [_base_doc()],
            {"tenant": "acme"},
            src,
            "hr-screening",
            {"EvalCase": LayerPolicy.RESTRICTED},
        )
        md = result[0]["metadata"]
        # Only ``forbidden_keywords`` was applied; ``new_field`` was
        # dropped by RESTRICTED policy and must NOT appear in the
        # overlay_fields list.
        assert md["overlay_fields"] == ["forbidden_keywords"]
        assert "new_field" not in result[0]["spec"]


# ──────────────────────────────────────────────────────────────────────
# LOCKED policy — no merge, no metadata stamp
# ──────────────────────────────────────────────────────────────────────


class TestLockedPolicy:
    def test_locked_doc_has_no_overlay_metadata(self) -> None:
        resolver = DefaultLayerResolver()
        overlay = {
            "kind": "EvalCase",
            "metadata": {"name": "fairness-bias"},
            "spec": {"forbidden_keywords": ["gender", "pronoun"]},
        }
        src = FakeSource({("tenant", "acme"): [overlay]})
        # Suppress the warning emitted by locked policy.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = resolver.resolve(
                [_base_doc()],
                {"tenant": "acme"},
                src,
                "hr-screening",
                {"EvalCase": LayerPolicy.LOCKED},
            )
        md = result[0]["metadata"]
        assert md.get("has_overlay") is not True
        # Spec untouched too.
        assert result[0]["spec"]["forbidden_keywords"] == ["gender"]


# ──────────────────────────────────────────────────────────────────────
# Multi-layer dimension union
# ──────────────────────────────────────────────────────────────────────


class TestMultipleLayers:
    def test_overlay_fields_unions_across_dimensions(self) -> None:
        resolver = DefaultLayerResolver()
        tenant_overlay = {
            "kind": "EvalCase",
            "metadata": {"name": "fairness-bias"},
            "spec": {"forbidden_keywords": ["gender", "pronoun"]},
        }
        env_overlay = {
            "kind": "EvalCase",
            "metadata": {"name": "fairness-bias"},
            "spec": {"prompt": "env-specific prompt"},
        }
        src = FakeSource(
            {
                ("tenant", "acme"): [tenant_overlay],
                ("env", "prod"): [env_overlay],
            }
        )
        result = resolver.resolve(
            [_base_doc()],
            {"tenant": "acme", "env": "prod"},
            src,
            "hr-screening",
            {},
        )
        md = result[0]["metadata"]
        assert md["has_overlay"] is True
        assert sorted(md["overlay_fields"]) == ["forbidden_keywords", "prompt"]
