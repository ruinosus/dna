"""s-sync-s1 — KindBase.canonical_digest: a stable, semantic hash of a doc's
authored identity. The basis for the Source Sync Engine's diff/sync, so it must
be invariant to formatting / key order / volatile stamps / instruction_file-vs-
inline, but sensitive to real content changes.
"""
from __future__ import annotations

from types import SimpleNamespace

from dna.kernel.kinds.base import KindBase


class _K(KindBase):
    api_version = "github.com/ruinosus/dna/test/v1"
    kind = "TestKind"
    alias = "test-testkind"


def _doc(spec, *, kind="TestKind", name="a"):
    return SimpleNamespace(kind=kind, name=name, spec=spec)


K = _K()


def test_invariant_to_key_order():
    d1 = _doc({"b": 1, "a": 2, "tools": ["x", "y"]})
    d2 = _doc({"tools": ["x", "y"], "a": 2, "b": 1})
    assert K.canonical_digest(d1) == K.canonical_digest(d2)


def test_ignores_volatile_fields():
    base = {"model": "gpt-5-mini", "instruction": "hi"}
    d1 = _doc({**base, "updated_at": "2026-06-03T10:00:00Z", "version": 1})
    d2 = _doc({**base, "updated_at": "2026-06-03T23:59:59Z", "version": 27,
               "created_at": "2026-01-01T00:00:00Z"})
    assert K.canonical_digest(d1) == K.canonical_digest(d2)


def test_sensitive_to_real_content():
    d1 = _doc({"model": "gpt-5-mini", "instruction": "review code"})
    d2 = _doc({"model": "gpt-5-mini", "instruction": "screen candidates"})
    assert K.canonical_digest(d1) != K.canonical_digest(d2)


def test_name_and_kind_are_part_of_identity():
    spec = {"instruction": "hi"}
    assert K.canonical_digest(_doc(spec, name="a")) != K.canonical_digest(_doc(spec, name="b"))
    assert K.canonical_digest(_doc(spec, kind="X")) != K.canonical_digest(_doc(spec, kind="Y"))


def test_instruction_file_resolved_equals_inline():
    """A file-backed agent (instruction resolved + instruction_file pointer +
    transport source_files) hashes the SAME as the equivalent inline agent."""
    inline = _doc({"model": "m", "instruction": "Review code. Cite file:line."})
    file_backed = _doc({
        "model": "m",
        "instruction": "Review code. Cite file:line.",  # resolved at read
        "instruction_file": "instruction.md",            # pointer (dropped)
        "source_files": {"instruction.md": "Review code. Cite file:line."},  # transport
    })
    assert K.canonical_digest(inline) == K.canonical_digest(file_backed)


def test_source_files_transport_never_affects_digest():
    d1 = _doc({"instruction_file": "instruction.md", "instruction": "x"})
    d2 = _doc({"instruction_file": "instruction.md", "instruction": "x",
               "source_files": {"instruction.md": "x", "logo.png": "...bytes..."}})
    assert K.canonical_digest(d1) == K.canonical_digest(d2)


def test_volatile_fields_overridable_per_kind():
    class _Forecast(KindBase):
        api_version = "github.com/ruinosus/dna/test/v1"
        kind = "Forecast"
        alias = "test-forecast"
        VOLATILE_SPEC_FIELDS = KindBase.VOLATILE_SPEC_FIELDS | {"generated_at"}

    fk = _Forecast()
    d1 = _doc({"summary": "s", "generated_at": "2026-06-03T10:00:00Z"}, kind="Forecast")
    d2 = _doc({"summary": "s", "generated_at": "2026-06-04T10:00:00Z"}, kind="Forecast")
    assert fk.canonical_digest(d1) == fk.canonical_digest(d2)
    # The base kind (no override) WOULD see generated_at as identity:
    assert K.canonical_digest(_doc({"summary": "s", "generated_at": "a"})) != \
        K.canonical_digest(_doc({"summary": "s", "generated_at": "b"}))
