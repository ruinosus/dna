"""Tests for SpecDict and Document unified access."""
from __future__ import annotations

import dataclasses
import pytest

from dna.kernel.document import Document, SpecDict


class TestSpecDict:
    def test_dict_access(self):
        s = SpecDict({"a": 1, "b": "hello"})
        assert s["a"] == 1
        assert s.get("b") == "hello"
        assert s.get("missing") is None
        assert s.get("missing", "default") == "default"

    def test_attribute_access(self):
        s = SpecDict({"soul": "brad", "skills": ["greet"]})
        assert s.soul == "brad"
        assert s.skills == ["greet"]

    def test_missing_attribute_raises(self):
        s = SpecDict({"a": 1})
        with pytest.raises(AttributeError):
            _ = s.nonexistent

    def test_hasattr_correct(self):
        s = SpecDict({"a": 1})
        assert hasattr(s, "a") is True
        assert hasattr(s, "missing") is False

    def test_getattr_with_default(self):
        s = SpecDict({"a": 1})
        assert getattr(s, "a", None) == 1
        assert getattr(s, "missing", "fallback") == "fallback"

    def test_isinstance_dict(self):
        s = SpecDict({"a": 1})
        assert isinstance(s, dict)

    def test_setattr(self):
        s = SpecDict({})
        s.new_key = "value"
        assert s["new_key"] == "value"

    def test_iteration(self):
        s = SpecDict({"a": 1, "b": 2})
        assert dict(s) == {"a": 1, "b": 2}


class TestDocumentSpecDict:
    """Document.spec and .metadata always return SpecDict."""

    def test_spec_from_raw_dict(self):
        doc = Document.from_raw({
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "brad", "description": "test agent"},
            "spec": {"instruction": "Be helpful", "soul": "brad"},
        })
        assert isinstance(doc.spec, SpecDict)
        assert doc.spec.get("instruction") == "Be helpful"
        assert doc.spec.soul == "brad"

    def test_metadata_from_raw_dict(self):
        doc = Document.from_raw({
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "brad", "description": "test agent"},
            "spec": {},
        })
        assert isinstance(doc.metadata, SpecDict)
        assert doc.metadata.get("description") == "test agent"
        assert doc.metadata.name == "brad"

    def test_spec_from_typed_model(self):
        from dna.kernel.models import TypedAgent
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "brad"},
            "spec": {"instruction": "Be helpful", "soul": "brad", "skills": ["greet"]},
        }
        typed = TypedAgent.from_raw(raw)
        doc = Document.from_raw(raw, typed=typed)

        assert isinstance(doc.spec, SpecDict)
        assert doc.spec.instruction == "Be helpful"
        assert doc.spec.soul == "brad"
        assert doc.spec.skills == ["greet"]

    def test_metadata_from_typed_model(self):
        from dna.kernel.models import TypedAgent
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "brad", "description": "A helpful agent"},
            "spec": {"instruction": "x"},
        }
        typed = TypedAgent.from_raw(raw)
        doc = Document.from_raw(raw, typed=typed)

        assert isinstance(doc.metadata, SpecDict)
        assert doc.metadata.description == "A helpful agent"

    def test_nested_dataclass_becomes_dict(self):
        """SkillSpec has FileEntry dataclasses — they should become plain dicts."""
        from dna.kernel.models import TypedSkill
        raw = {
            "apiVersion": "agentskills.io/v1",
            "kind": "Skill",
            "metadata": {"name": "greet"},
            "spec": {"instruction": "Greet users", "scripts": {"hello.py": "print('hi')"}},
        }
        typed = TypedSkill.from_raw(raw)
        doc = Document.from_raw(raw, typed=typed)

        assert isinstance(doc.spec, SpecDict)
        # scripts stays as dict (filename → content) through typed model
        assert isinstance(doc.spec.scripts, dict)
        assert doc.spec.scripts["hello.py"] == "print('hi')"

    def test_spec_cached(self):
        """Spec should return the same object on repeated access."""
        doc = Document.from_raw({
            "apiVersion": "v1", "kind": "Test",
            "metadata": {"name": "t"}, "spec": {"a": 1},
        })
        assert doc.spec is doc.spec

    def test_spec_missing_returns_empty_specdict(self):
        doc = Document.from_raw({"apiVersion": "v1", "kind": "X", "metadata": {"name": "t"}})
        assert isinstance(doc.spec, SpecDict)
        assert dict(doc.spec) == {}

    def test_deepcopy_preserves_spec(self):
        """deepcopy works correctly with cached_property + __slots__."""
        import copy
        doc = Document.from_raw({
            "apiVersion": "v1", "kind": "Test",
            "metadata": {"name": "t"}, "spec": {"a": 1},
        })
        _ = doc.spec  # Trigger cache
        clone = copy.deepcopy(doc)
        assert clone.spec == doc.spec
        assert clone.spec is not doc.spec  # Different objects

    def test_typed_still_accessible(self):
        """doc.typed still returns the original dataclass."""
        from dna.kernel.models import TypedAgent
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "brad"},
            "spec": {"instruction": "x"},
        }
        typed = TypedAgent.from_raw(raw)
        doc = Document.from_raw(raw, typed=typed)

        assert doc.typed is typed
        assert hasattr(doc.typed.spec, "instruction")
