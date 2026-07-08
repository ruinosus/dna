"""Tests for Kernel.build() — sync computation from pre-loaded docs."""
import pytest
from dna.kernel import Kernel
from dna.extensions.helix import HelixExtension
from dna.extensions.agentskills import AgentSkillsExtension
from dna.extensions.guardrails import GuardrailExtension


@pytest.fixture
def kernel():
    k = Kernel()
    k.load(HelixExtension())
    k.load(AgentSkillsExtension())
    k.load(GuardrailExtension())
    return k


class TestKernelBuild:
    def test_build_returns_manifest_instance(self, kernel):
        raw_docs = [
            {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome", "metadata": {"name": "test"}, "spec": {"agents": ["bot"]}},
            {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent", "metadata": {"name": "bot"}, "spec": {"model": "gpt-4o"}},
        ]
        mi = kernel.build(raw_docs, scope="test")
        assert mi.scope == "test"
        assert len(mi.documents) >= 2

    def test_build_parses_all_kinds(self, kernel):
        raw_docs = [
            {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome", "metadata": {"name": "test"}, "spec": {"agents": ["bot"]}},
            {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent", "metadata": {"name": "bot"}, "spec": {"model": "gpt-4o"}},
            {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Guardrail", "metadata": {"name": "safety"}, "spec": {"rules": ["no harm"]}},
        ]
        mi = kernel.build(raw_docs, scope="test")
        kinds = {d.kind for d in mi.documents}
        assert "Genome" in kinds
        assert "Agent" in kinds
        assert "Guardrail" in kinds

    def test_build_with_dep_docs(self, kernel):
        raw_docs = [
            {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome", "metadata": {"name": "test"}, "spec": {"agents": ["bot"]}},
        ]
        dep_docs = [
            {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Agent", "metadata": {"name": "bot"}, "spec": {"model": "gpt-4o"}},
        ]
        mi = kernel.build(raw_docs, scope="test", dep_docs=dep_docs)
        assert len(mi.documents) >= 2

    def test_build_is_pure_no_source_needed(self, kernel):
        """Kernel.build() should work without a source configured."""
        raw_docs = [
            {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome", "metadata": {"name": "test"}, "spec": {}},
        ]
        mi = kernel.build(raw_docs, scope="test")
        assert mi is not None

    def test_auto_loads_all_extensions(self):
        k = Kernel.auto()
        kind_names = [kp.kind for kp in k._kinds.values()]
        assert "Genome" in kind_names
        assert "Skill" in kind_names
        assert "Guardrail" in kind_names
        assert "Soul" in kind_names
