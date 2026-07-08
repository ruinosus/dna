"""Tests for the UseCase kind (github.com/ruinosus/dna/v1)."""
from __future__ import annotations

from dna.kernel import Kernel
from dna.kernel.models import TypedUseCase, UseCaseSpec
from dna.adapters.filesystem import FilesystemSource, FilesystemCache
from dna.extensions.helix import HelixExtension, UseCaseKind


# ── unit: parsing ──

class TestUseCaseSpecParsing:
    def test_full_fields(self):
        raw = {
            "metadata": {"name": "checkout", "description": "Customer checks out"},
            "spec": {
                "primary_actor": "shopper",
                "supporting_actors": ["payment-gateway", "inventory"],
                "agents": ["order-bot"],
                "preconditions": ["cart not empty"],
                "main_flow": ["select items", "pay", "confirm"],
                "alternate_flows": [
                    {"name": "out of stock", "steps": ["notify", "remove item"]},
                ],
                "postconditions": ["order created"],
                "success_criteria": ["payment captured"],
            },
        }
        uc = TypedUseCase.from_raw(raw)
        assert uc.metadata.name == "checkout"
        assert uc.spec.primary_actor == "shopper"
        assert uc.spec.supporting_actors == ["payment-gateway", "inventory"]
        assert uc.spec.agents == ["order-bot"]
        assert uc.spec.main_flow == ["select items", "pay", "confirm"]
        assert uc.spec.alternate_flows[0]["name"] == "out of stock"
        assert uc.spec.postconditions == ["order created"]
        assert uc.spec.success_criteria == ["payment captured"]

    def test_minimal_fields(self):
        uc = TypedUseCase.from_raw({"metadata": {"name": "u1"}, "spec": {}})
        assert uc.metadata.name == "u1"
        assert uc.spec.primary_actor is None
        assert uc.spec.supporting_actors == []
        assert uc.spec.main_flow == []


# ── kind properties ──

class TestUseCaseKindProperties:
    def test_kind_metadata(self):
        kp = UseCaseKind()
        assert kp.api_version == "github.com/ruinosus/dna/v1"
        assert kp.kind == "UseCase"
        assert kp.alias == "helix-usecase"
        assert kp.is_root is False
        assert kp.is_prompt_target is False
        assert kp.flatten_in_context is False
        # UseCase composes Actor + Agent + Soul + Skills + Tools + Guardrails
        filters = kp.dep_filters()
        assert filters is not None
        assert filters["primary_actor"] == "helix-actor"
        assert filters["supporting_actors"] == "helix-actor"
        assert filters["agents"] == "helix-agent"
        assert filters["soul"] == "soulspec-soul"
        assert filters["skills"] == "agentskills-skill"
        assert filters["tools"] == "helix-tool"
        assert filters["guardrails"] == "guardrails-guardrail"
        assert kp.storage.container == "use_cases"

    def test_registered_in_helix(self):
        k = Kernel()
        k.load(HelixExtension())
        assert ("github.com/ruinosus/dna/v1", "UseCase") in k._kinds

    def test_package_has_no_inventory_dep_filters(self):
        # Phase 16 — replaces test_module_dep_filters_includes_use_cases.
        # GenomeKind dropped the bill-of-materials arrays (agents,
        # skills, actors, use_cases, tools, guardrails) from spec.
        k = Kernel()
        k.load(HelixExtension())
        kp = k._kinds[("github.com/ruinosus/dna/v1", "Genome")]
        assert kp.dep_filters() is None


# ── integration: load from filesystem ──

class TestUseCaseFilesystemLoad:
    def test_loads_usecase_from_manifest(self, tmp_path):
        scope = tmp_path / "mod"
        scope.mkdir()
        (scope / "manifest.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\nmetadata:\n  name: mod\nspec: {}\n"
        )
        ucdir = scope / "use_cases"
        ucdir.mkdir()
        (ucdir / "checkout.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\n"
            "kind: UseCase\n"
            "metadata:\n  name: checkout\n"
            "spec:\n"
            "  primary_actor: shopper\n"
            "  main_flow:\n    - select\n    - pay\n"
        )

        k = Kernel()
        k.source(FilesystemSource(str(tmp_path)))
        k.cache(FilesystemCache(str(tmp_path)))
        k.load(HelixExtension())

        mi = k.instance("mod")
        ucs = [d for d in mi.documents if d.kind == "UseCase"]
        assert len(ucs) == 1
        assert ucs[0].name == "checkout"
        assert ucs[0].spec.get("primary_actor") == "shopper"
        assert ucs[0].spec.get("main_flow") == ["select", "pay"]
