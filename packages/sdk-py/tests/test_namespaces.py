"""Tests for namespace API — Python parity with TypeScript.

Verifies that mi.prompt.build(), mi.composition.validate(),
mi.nav.describe(), and mi.lock.generate() return identical results
to the original ManifestInstance methods.
"""
from pathlib import Path

import pytest
from dna import Kernel

BASE_DIR = Path(__file__).parent.parent.parent.parent / "scopes" / "open-swe" / ".dna"


class TestNamespaces:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mi = Kernel.quick("open-swe", base_dir=str(BASE_DIR))

    # -- PromptBuilder --------------------------------------------------------

    def test_prompt_build_equals_build_prompt(self):
        old = self.mi.build_prompt()
        new = self.mi.prompt.build()
        assert new == old

    def test_prompt_build_with_agent(self):
        agents = self.mi.all("Agent")
        if agents:
            name = agents[0].name
            old = self.mi.build_prompt(agent=name)
            new = self.mi.prompt.build(agent=name)
            assert new == old

    # -- CompositionEngine ----------------------------------------------------

    def test_composition_validate_equals_composition_result(self):
        old = self.mi.composition_result
        new = self.mi.composition.validate()
        assert new.resolved == old.resolved
        assert new.missing == old.missing
        assert new.warnings == old.warnings

    def test_composition_consumers_of(self):
        skills = self.mi.all("Skill")
        if skills:
            s = skills[0]
            old = self.mi.consumers_of(s.kind, s.name)
            new = self.mi.composition.consumers_of(s.kind, s.name)
            assert new == old

    def test_composition_dependency_tree(self):
        old = self.mi.dependency_tree()
        new = self.mi.composition.dependency_tree()
        assert new == old

    def test_composition_iter_doc_deps(self):
        agents = self.mi.all("Agent")
        if agents:
            a = agents[0]
            old = self.mi.iter_doc_deps(a)
            new = self.mi.composition.iter_doc_deps(a)
            assert new == old

    # -- Navigator ------------------------------------------------------------

    def test_nav_describe(self):
        agents = self.mi.all("Agent")
        if agents:
            a = agents[0]
            assert self.mi.nav.describe(a.kind, a.name) == self.mi.describe(a.kind, a.name)

    def test_nav_summary(self):
        assert self.mi.nav.summary() == self.mi.summary()

    def test_nav_inventory(self):
        assert self.mi.nav.inventory() == self.mi.inventory()

    def test_nav_render_doc(self):
        agents = self.mi.all("Agent")
        if agents:
            a = agents[0]
            assert self.mi.nav.render_doc(a.kind, a.name) == self.mi.render_doc(a.kind, a.name)

    # -- LockManager ----------------------------------------------------------

    def test_lock_generate(self):
        old = self.mi.generate_lock()
        new = self.mi.lock.generate()
        assert new.scope == old.scope
        assert new.documents == old.documents
