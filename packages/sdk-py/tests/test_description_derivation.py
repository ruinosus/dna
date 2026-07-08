"""Tests for kernel-driven description derivation via description_fallback_field."""
from __future__ import annotations

import pytest

from dna.kernel._text import derive_first_line


# ---------------------------------------------------------------------------
# derive_first_line unit tests
# ---------------------------------------------------------------------------


class TestDeriveFirstLine:
    def test_none(self):
        assert derive_first_line(None) is None

    def test_empty(self):
        assert derive_first_line("") is None

    def test_whitespace_only(self):
        assert derive_first_line("   \n   \n") is None

    def test_plain_first_line(self):
        assert derive_first_line("hello world\nsecond line") == "hello world"

    def test_strips_heading_marker(self):
        assert derive_first_line("# Title\nbody") == "Title"

    def test_strips_multiple_hashes(self):
        assert derive_first_line("### Sub Title\nbody") == "Sub Title"

    def test_skips_empty_then_uses_next(self):
        assert derive_first_line("\n\n  \nactual content") == "actual content"

    def test_skips_divider(self):
        assert derive_first_line("---\nreal text") == "real text"

    def test_skips_equals_divider(self):
        assert derive_first_line("====\nreal text") == "real text"

    def test_truncates_long_line(self):
        text = "x" * 200
        result = derive_first_line(text, max_len=50)
        assert result is not None
        assert len(result) == 53
        assert result.endswith("...")

    def test_no_truncate_when_under_limit(self):
        assert derive_first_line("short line", max_len=50) == "short line"


# ---------------------------------------------------------------------------
# Kernel pipeline tests — _fill_derived_description honors per-kind attribute
# ---------------------------------------------------------------------------


def _fill(raw, kind_port):
    from dna.kernel import Kernel
    Kernel._fill_derived_description(raw, kind_port)


class _FakeKind:
    def __init__(self, field):
        self.description_fallback_field = field


class _NoFieldKind:
    pass


class TestKernelDerivation:
    def test_derives_when_description_missing(self):
        raw = {"metadata": {"name": "x"}, "spec": {"body": "# Hello\nworld"}}
        _fill(raw, _FakeKind("body"))
        assert raw["metadata"]["description"] == "Hello"

    def test_derives_when_description_empty_string(self):
        raw = {"metadata": {"name": "x", "description": ""}, "spec": {"body": "# Hi"}}
        _fill(raw, _FakeKind("body"))
        assert raw["metadata"]["description"] == "Hi"

    def test_preserves_authored_description(self):
        raw = {"metadata": {"name": "x", "description": "Authored"}, "spec": {"body": "# Other"}}
        _fill(raw, _FakeKind("body"))
        assert raw["metadata"]["description"] == "Authored"

    def test_no_attribute_no_op(self):
        raw = {"metadata": {"name": "x"}, "spec": {"body": "# Hello"}}
        _fill(raw, _NoFieldKind())
        assert "description" not in raw["metadata"]

    def test_field_missing_in_spec_no_op(self):
        raw = {"metadata": {"name": "x"}, "spec": {}}
        _fill(raw, _FakeKind("body"))
        assert "description" not in raw["metadata"]

    def test_creates_metadata_if_missing(self):
        raw = {"spec": {"body": "# Hello"}}
        _fill(raw, _FakeKind("body"))
        assert raw["metadata"]["description"] == "Hello"


# ---------------------------------------------------------------------------
# End-to-end: real KindPort instances declare the attribute correctly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind_cls,field", [
    ("dna.extensions.soulspec:SoulKind", "soul_content"),
    ("dna.extensions.agentskills:SkillKind", "instruction"),
    ("dna.extensions.guardrails:GuardrailKind", "instruction"),
    ("dna.extensions.agentsmd:AgentDefinitionKind", "content"),
])
def test_kind_declares_fallback_field(kind_cls, field):
    import importlib
    module_path, class_name = kind_cls.split(":")
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    assert getattr(cls, "description_fallback_field", None) == field


def test_full_parse_pipeline_soul():
    """Loading a Soul through the kernel should populate metadata.description."""
    from dna.kernel import Kernel
    from dna.extensions.soulspec import SoulKind, SoulSpecExtension

    kernel = Kernel()
    kernel.load(SoulSpecExtension())
    raw = {
        "apiVersion": "soulspec.org/v1",
        "kind": "Soul",
        "metadata": {"name": "test"},
        "spec": {"soul_content": "# Test Soul\n\nDoes things."},
    }
    doc = kernel._parse_doc(raw)
    assert doc.metadata.description == "Test Soul"
