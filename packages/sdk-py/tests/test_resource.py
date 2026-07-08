"""Tests for Resource class -- Python parity with TypeScript."""
from dataclasses import dataclass

import pytest
from dna.kernel.resource import Resource, ResourceDep


class TestResource:
    def test_from_raw_basic(self):
        raw = {
            "apiVersion": "agentskills.io/v1",
            "kind": "Skill",
            "metadata": {"name": "search", "description": "Search skill"},
            "spec": {"instruction": "You can search"},
        }
        r = Resource.from_raw(raw, origin="local")
        assert r.api_version == "agentskills.io/v1"
        assert r.kind == "Skill"
        assert r.name == "search"
        assert r.origin == "local"
        assert r.spec.get("instruction") == "You can search"
        assert r.metadata.get("description") == "Search skill"

    def test_spec_prefers_typed(self):
        raw = {
            "apiVersion": "a",
            "kind": "K",
            "metadata": {"name": "x"},
            "spec": {"a": 1},
        }

        @dataclass
        class FakeSpec:
            a: int = 2

        @dataclass
        class FakeMetadata:
            name: str = "x"

        @dataclass
        class FakeTyped:
            metadata: FakeMetadata = None
            spec: FakeSpec = None

        r = Resource.from_raw(raw, typed=FakeTyped(metadata=FakeMetadata(), spec=FakeSpec()), origin="local")
        assert r.spec.get("a") == 2

    def test_spec_falls_back_to_raw_when_no_typed(self):
        raw = {
            "apiVersion": "a",
            "kind": "K",
            "metadata": {"name": "x"},
            "spec": {"a": 1},
        }
        r = Resource.from_raw(raw, origin="local")
        assert r.spec.get("a") == 1

    def test_deps_empty_without_kind_ref(self):
        raw = {
            "apiVersion": "a",
            "kind": "K",
            "metadata": {"name": "x"},
            "spec": {},
        }
        r = Resource.from_raw(raw)
        assert r.deps() == []

    def test_deps_resolves_from_kind_ref(self):
        class MockKind:
            def dep_filters(self):
                return {"skills": "agentskills-skill", "soul": "soulspec-soul"}

            def dependencies(self):
                return self.dep_filters()

        raw = {
            "apiVersion": "a",
            "kind": "K",
            "metadata": {"name": "x"},
            "spec": {"skills": ["search", "code-review"], "soul": "brad"},
        }
        r = Resource.from_raw(raw, kind_ref=MockKind())
        deps = r.deps()
        assert len(deps) == 2
        assert deps[0].field == "skills"
        assert deps[0].target_alias == "agentskills-skill"
        assert deps[0].names == ["search", "code-review"]
        assert deps[1].field == "soul"
        assert deps[1].target_alias == "soulspec-soul"
        assert deps[1].names == ["brad"]

    def test_deps_skips_empty_fields(self):
        class MockKind:
            def dep_filters(self):
                return {"skills": "agentskills-skill", "soul": "soulspec-soul"}

        raw = {
            "apiVersion": "a",
            "kind": "K",
            "metadata": {"name": "x"},
            "spec": {"skills": [], "soul": ""},
        }
        r = Resource.from_raw(raw, kind_ref=MockKind())
        assert r.deps() == []

    def test_deps_falls_back_to_dep_filters_when_no_dependencies(self):
        class MockKind:
            def dep_filters(self):
                return {"soul": "soulspec-soul"}

        raw = {
            "apiVersion": "a",
            "kind": "K",
            "metadata": {"name": "x"},
            "spec": {"soul": "brad"},
        }
        r = Resource.from_raw(raw, kind_ref=MockKind())
        deps = r.deps()
        assert len(deps) == 1
        assert deps[0].names == ["brad"]

    def test_repr(self):
        raw = {
            "apiVersion": "a/v1",
            "kind": "Skill",
            "metadata": {"name": "x"},
            "spec": {},
        }
        r = Resource.from_raw(raw)
        assert repr(r) == "Resource(a/v1/Skill: x)"

    def test_equality(self):
        raw = {
            "apiVersion": "a",
            "kind": "K",
            "metadata": {"name": "x"},
            "spec": {},
        }
        r1 = Resource.from_raw(raw)
        r2 = Resource.from_raw(raw)
        assert r1 == r2
        assert hash(r1) == hash(r2)

    def test_inequality(self):
        r1 = Resource.from_raw(
            {"apiVersion": "a", "kind": "K", "metadata": {"name": "x"}, "spec": {}}
        )
        r2 = Resource.from_raw(
            {"apiVersion": "a", "kind": "K", "metadata": {"name": "y"}, "spec": {}}
        )
        assert r1 != r2

    def test_hash_in_set(self):
        raw = {
            "apiVersion": "a",
            "kind": "K",
            "metadata": {"name": "x"},
            "spec": {},
        }
        r1 = Resource.from_raw(raw)
        r2 = Resource.from_raw(raw)
        s = {r1, r2}
        assert len(s) == 1

    def test_from_raw_missing_fields(self):
        """from_raw handles missing/empty metadata and spec gracefully."""
        raw = {"apiVersion": "a", "kind": "K"}
        r = Resource.from_raw(raw)
        assert r.name == ""
        assert r.spec == {}
        assert r.metadata == {}
