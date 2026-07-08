"""Tests for Kind.schema() and Kind.dependencies() -- Python parity."""
from dna import Kernel


class TestKindSchema:
    def setup_method(self):
        self.k = Kernel.auto()

    def _find_kind(self, name):
        for kp in self.k._kinds.values():
            if kp.kind == name:
                return kp
        return None

    def test_agent_has_schema(self):
        kp = self._find_kind("Agent")
        assert kp is not None
        s = kp.schema()
        assert s is not None
        assert s["type"] == "object"
        assert "properties" in s

    def test_agent_schema_has_known_fields(self):
        kp = self._find_kind("Agent")
        s = kp.schema()
        props = s["properties"]
        assert "instruction" in props
        assert "soul" in props
        assert "skills" in props

    def test_agent_has_dependencies(self):
        kp = self._find_kind("Agent")
        deps = kp.dependencies()
        assert deps is not None
        assert deps.get("soul") == "soulspec-soul"
        assert deps.get("skills") == "agentskills-skill"

    def test_package_has_no_dep_filters(self):
        # Phase 16 — replaces test_module_has_dependencies. GenomeKind
        # has no inventory dep_filters (the legacy ``agents/skills/...``
        # bill-of-materials arrays were dropped from the spec). External
        # dependency resolution still happens via ``spec.dependencies``,
        # but that's a list of resolver URIs, not a Kind reference map.
        kp = self._find_kind("Genome")
        assert kp.dependencies() is None

    def test_skill_has_schema(self):
        kp = self._find_kind("Skill")
        assert kp is not None
        s = kp.schema()
        assert s is not None
        assert "properties" in s
        assert "instruction" in s["properties"]

    def test_soul_has_schema(self):
        kp = self._find_kind("Soul")
        assert kp is not None
        s = kp.schema()
        assert s is not None
        assert "properties" in s

    def test_guardrail_has_schema(self):
        kp = self._find_kind("Guardrail")
        assert kp is not None
        s = kp.schema()
        assert s is not None
        assert "properties" in s
        assert "rules" in s["properties"]

    def test_actor_has_no_dependencies(self):
        kp = self._find_kind("Actor")
        deps = kp.dependencies()
        assert deps is None

    def test_skill_has_no_dependencies(self):
        kp = self._find_kind("Skill")
        deps = kp.dependencies()
        assert deps is None

    def test_dependencies_equals_dep_filters(self):
        """For all registered kinds, dependencies() must match dep_filters()."""
        for kp in self.k._kinds.values():
            if hasattr(kp, "dependencies") and callable(kp.dependencies):
                assert kp.dependencies() == kp.dep_filters(), (
                    f"{kp.kind}: dependencies() != dep_filters()"
                )

    def test_all_kinds_have_schema_method(self):
        """Every registered kind should have a schema() method."""
        for kp in self.k._kinds.values():
            assert hasattr(kp, "schema") and callable(kp.schema), (
                f"{kp.kind} missing schema() method"
            )

    def test_all_kinds_have_dependencies_method(self):
        """Every registered kind should have a dependencies() method."""
        for kp in self.k._kinds.values():
            assert hasattr(kp, "dependencies") and callable(kp.dependencies), (
                f"{kp.kind} missing dependencies() method"
            )
