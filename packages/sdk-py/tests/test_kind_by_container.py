"""Tests for Kernel.kind_by_container — O(1) container→kind index."""
from dna.kernel import Kernel
from dna.extensions.helix import HelixExtension
from dna.extensions.agentskills import AgentSkillsExtension


def test_returns_kind_for_registered_container():
    k = Kernel()
    k.load(HelixExtension())
    k.load(AgentSkillsExtension())
    assert k.kind_by_container("agents") == "Agent"
    assert k.kind_by_container("skills") == "Skill"


def test_returns_none_for_unknown_container():
    k = Kernel()
    k.load(HelixExtension())
    assert k.kind_by_container("does-not-exist") is None


def test_empty_container_returns_none():
    """ROOT kinds (Module) have empty container — lookup with "" must return None,
    not accidentally match."""
    k = Kernel()
    k.load(HelixExtension())
    assert k.kind_by_container("") is None
