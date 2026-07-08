"""Tests for the KindDefinition meta-kind pipeline (Chunk 3).

Covers:
  3.1 — TypedKindDefinition parses a full spec (+ rejects malformed)
  3.2 — DeclarativeKindPort validates spec against JSON Schema + storage conversion
  3.3 — KindDefinitionExtension registers and loads from .dna/<scope>/kinds/
  3.4 — End-to-end: manifest with a KindDefinition and an instance doc of the new kind
  3.5 — Conflict: extension-registered kinds win, KindDefinition is skipped + warned
  3.6 — Round-trip: write doc of a declarative kind via the generic writer, reload

All tests use tmp_path (no mocks).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.kernel import Kernel
from dna.kernel.meta import DeclarativeKindPort, storage_dict_to_descriptor
from dna.kernel.models import TypedKindDefinition
from dna.kernel.protocols import StoragePattern


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _full_kinddef_spec() -> dict[str, Any]:
    return {
        "target_api_version": "example.com/v1",
        "target_kind": "Recipe",
        "alias": "example-recipe",
        "origin": "example.com",
        "is_root": False,
        "prompt_target": False,
        "flatten_in_context": False,
        "docs": "A cooking recipe with ingredients and steps.",
        "schema": {
            "type": "object",
            "required": ["title", "ingredients"],
            "properties": {
                "title": {"type": "string"},
                "ingredients": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "minutes": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": True,
        },
        "storage": {
            "type": "bundle",
            "container": "recipes",
            "marker": "RECIPE.md",
            "body_as": "text",
            "body_field": "description",
        },
        "dep_filters": {"example-recipe": "include"},
    }


def _full_kinddef_raw() -> dict[str, Any]:
    return {
        "apiVersion": TypedKindDefinition.API_VERSION,
        "kind": TypedKindDefinition.KIND,
        "metadata": {"name": "recipe"},
        "spec": _full_kinddef_spec(),
    }


def _make_module(scope_dir: Path) -> None:
    scope_dir.mkdir(parents=True, exist_ok=True)
    (scope_dir / "manifest.yaml").write_text(
        yaml.dump(
            {
                "apiVersion": "github.com/ruinosus/dna/v1",
                "kind": "Genome",
                "metadata": {"name": scope_dir.name, "description": "test"},
                "spec": {},
            }
        )
    )


def _kernel_with_all_ext() -> Kernel:
    k = Kernel()
    from dna.extensions.helix import HelixExtension
    from dna.extensions.agentskills import AgentSkillsExtension
    from dna.extensions.soulspec import SoulSpecExtension
    from dna.extensions.agentsmd import AgentsMdExtension
    from dna.extensions.guardrails import GuardrailExtension
    from dna.extensions.kinddef import KindDefinitionExtension

    k.load(HelixExtension())
    k.load(AgentSkillsExtension())
    k.load(SoulSpecExtension())
    k.load(AgentsMdExtension())
    k.load(GuardrailExtension())
    k.load(KindDefinitionExtension())
    return k


# ---------------------------------------------------------------------------
# 3.1 TypedKindDefinition
# ---------------------------------------------------------------------------

class TestTypedKindDefinition:
    def test_from_raw_full_spec_happy(self) -> None:
        typed = TypedKindDefinition.from_raw(_full_kinddef_raw())
        assert typed.metadata.name == "recipe"
        assert typed.spec.target_kind == "Recipe"
        assert typed.spec.alias == "example-recipe"
        assert typed.spec.schema["required"] == ["title", "ingredients"]
        assert typed.spec.storage["type"] == "bundle"
        assert typed.spec.dep_filters == {"example-recipe": "include"}

    def test_from_raw_rejects_missing_fields(self) -> None:
        bad = {
            "apiVersion": TypedKindDefinition.API_VERSION,
            "kind": TypedKindDefinition.KIND,
            "metadata": {"name": "broken"},
            "spec": {"target_kind": "X"},  # missing alias, origin, storage, etc.
        }
        with pytest.raises(ValueError, match="missing required fields"):
            TypedKindDefinition.from_raw(bad)

    def test_from_raw_rejects_wrong_api_version(self) -> None:
        raw = _full_kinddef_raw()
        raw["apiVersion"] = "wrong/v1"
        with pytest.raises(ValueError):
            TypedKindDefinition.from_raw(raw)


# ---------------------------------------------------------------------------
# 3.2 DeclarativeKindPort + storage conversion
# ---------------------------------------------------------------------------

class TestDeclarativeKindPort:
    def test_parse_happy_path(self) -> None:
        typed = TypedKindDefinition.from_raw(_full_kinddef_raw())
        port = DeclarativeKindPort.from_typed(typed)
        assert port.kind == "Recipe"
        assert port.api_version == "example.com/v1"
        assert port.alias == "example-recipe"
        assert port.dep_filters() == {"example-recipe": "include"}
        raw = {
            "apiVersion": "example.com/v1",
            "kind": "Recipe",
            "metadata": {"name": "pasta"},
            "spec": {"title": "Pasta", "ingredients": ["flour", "water"]},
        }
        out = port.parse(raw)
        assert out["spec"]["title"] == "Pasta"

    def test_parse_rejects_missing_required(self) -> None:
        typed = TypedKindDefinition.from_raw(_full_kinddef_raw())
        port = DeclarativeKindPort.from_typed(typed)
        raw = {
            "apiVersion": "example.com/v1",
            "kind": "Recipe",
            "metadata": {"name": "broken"},
            "spec": {"title": "Only title"},  # missing ingredients
        }
        with pytest.raises(ValueError, match="spec validation failed"):
            port.parse(raw)

    def test_storage_bundle_conversion(self) -> None:
        sd = storage_dict_to_descriptor(
            {"type": "bundle", "container": "recipes", "marker": "RECIPE.md"}
        )
        assert sd.pattern == StoragePattern.BUNDLE
        assert sd.container == "recipes"
        assert sd.marker == "RECIPE.md"

    def test_storage_yaml_conversion(self) -> None:
        sd = storage_dict_to_descriptor({"type": "yaml", "container": "recipes"})
        assert sd.pattern == StoragePattern.YAML
        assert sd.container == "recipes"

    def test_storage_standalone_conversion(self) -> None:
        sd = storage_dict_to_descriptor({"type": "standalone", "path": "FOO.md"})
        assert sd.pattern == StoragePattern.STANDALONE
        assert sd.marker == "FOO.md"

    def test_storage_unknown_type_is_loud(self) -> None:
        with pytest.raises(ValueError, match="unknown storage type"):
            storage_dict_to_descriptor({"type": "weird", "container": "x"})

    def test_storage_missing_type_is_loud(self) -> None:
        with pytest.raises(ValueError, match="type"):
            storage_dict_to_descriptor({"container": "x"})


# ---------------------------------------------------------------------------
# 3.3 KindDefinitionExtension loads from filesystem
# ---------------------------------------------------------------------------

class TestKindDefinitionExtension:
    def test_extension_registers_kind(self) -> None:
        k = _kernel_with_all_ext()
        key = (TypedKindDefinition.API_VERSION, TypedKindDefinition.KIND)
        assert key in k._kinds
        assert k._kinds[key].alias == "kinddef-kinddefinition"

    def test_loads_kinddef_from_disk(self, tmp_path: Path) -> None:
        scope_dir = tmp_path / ".dna" / "demo"
        _make_module(scope_dir)

        bundle = scope_dir / "kinds" / "recipe"
        bundle.mkdir(parents=True)
        (bundle / "KIND.yaml").write_text(yaml.dump(_full_kinddef_raw()))

        from dna.adapters.filesystem import FilesystemCache, FilesystemSource

        k = _kernel_with_all_ext()
        k.source(FilesystemSource(tmp_path / ".dna"))
        k.cache(FilesystemCache(tmp_path / ".dna"))

        mi = k.instance("demo")
        kinddefs = mi.all("KindDefinition")
        assert len(kinddefs) == 1
        assert kinddefs[0].name == "recipe"


# ---------------------------------------------------------------------------
# 3.4 End-to-end 2-phase loading
# ---------------------------------------------------------------------------

class TestTwoPhaseLoading:
    @pytest.mark.asyncio
    async def test_kinddef_then_instance_doc(self, tmp_path: Path) -> None:
        scope_dir = tmp_path / ".dna" / "demo"
        _make_module(scope_dir)

        # 1. Define the Recipe kind
        bundle = scope_dir / "kinds" / "recipe"
        bundle.mkdir(parents=True)
        (bundle / "KIND.yaml").write_text(yaml.dump(_full_kinddef_raw()))

        # 2. Drop an instance doc under recipes/pasta/RECIPE.md
        recipe_dir = scope_dir / "recipes" / "pasta"
        recipe_dir.mkdir(parents=True)
        (recipe_dir / "RECIPE.md").write_text(
            "---\n"
            "name: pasta\n"
            "title: Simple Pasta\n"
            "ingredients:\n"
            "  - flour\n"
            "  - water\n"
            "---\n\n"
            "Boil water, cook pasta."
        )

        from dna.adapters.filesystem import FilesystemCache, FilesystemSource

        k = _kernel_with_all_ext()
        k.source(FilesystemSource(tmp_path / ".dna"))
        k.cache(FilesystemCache(tmp_path / ".dna"))

        mi = await k.instance_async("demo")

        # Declarative port should now be registered
        key = ("example.com/v1", "Recipe")
        assert key in k._kinds
        assert getattr(k._kinds[key], "__declarative__", False)

        recipes = mi.all("Recipe")
        assert len(recipes) == 1
        doc = recipes[0]
        assert doc.name == "pasta"
        assert doc.spec.get("title") == "Simple Pasta"
        assert doc.spec.get("ingredients") == ["flour", "water"]


# ---------------------------------------------------------------------------
# 3.5 Conflict resolution — extension wins
# ---------------------------------------------------------------------------

class TestConflictResolution:
    def test_extension_wins_over_kinddef(self, tmp_path: Path) -> None:
        scope_dir = tmp_path / ".dna" / "demo"
        _make_module(scope_dir)

        # Colliding KindDefinition that claims (soulspec.org/v1, Soul)
        colliding = {
            "apiVersion": TypedKindDefinition.API_VERSION,
            "kind": TypedKindDefinition.KIND,
            "metadata": {"name": "soul-override"},
            "spec": {
                "target_api_version": "soulspec.org/v1",
                "target_kind": "Soul",
                "alias": "fake-soul",
                "origin": "evil.example.com",
                "schema": {"type": "object"},
                "storage": {
                    "type": "bundle",
                    "container": "fake-souls",
                    "marker": "FAKE.md",
                },
            },
        }
        bundle = scope_dir / "kinds" / "soul-override"
        bundle.mkdir(parents=True)
        (bundle / "KIND.yaml").write_text(yaml.dump(colliding))

        from dna.adapters.filesystem import FilesystemCache, FilesystemSource
        from dna.kernel.hooks import HookContext

        events: list[HookContext] = []
        k = _kernel_with_all_ext()
        k.on("kinddef_conflict", lambda ctx: events.append(ctx))
        k.source(FilesystemSource(tmp_path / ".dna"))
        k.cache(FilesystemCache(tmp_path / ".dna"))

        mi = k.instance("demo")

        # Extension-backed SoulKind is still the one registered
        soul_port = k._kinds[("soulspec.org/v1", "Soul")]
        assert not getattr(soul_port, "__declarative__", False)
        assert soul_port.alias == "soulspec-soul"

        # A warning event should have fired
        assert any(e.kind == "Soul" for e in events), (
            f"expected kinddef_conflict event, got {events!r}"
        )

        # KindDefinition doc still loaded fine
        assert len(mi.all("KindDefinition")) == 1


# ---------------------------------------------------------------------------
# 3.6 Round-trip via the kernel's serialize_document path
# ---------------------------------------------------------------------------

class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_write_and_reload(self, tmp_path: Path) -> None:
        scope_dir = tmp_path / ".dna" / "demo"
        _make_module(scope_dir)

        # Define the kind
        bundle = scope_dir / "kinds" / "recipe"
        bundle.mkdir(parents=True)
        (bundle / "KIND.yaml").write_text(yaml.dump(_full_kinddef_raw()))

        from dna.adapters.filesystem import FilesystemCache, FilesystemSource

        k = _kernel_with_all_ext()
        k.source(FilesystemSource(tmp_path / ".dna"))
        k.cache(FilesystemCache(tmp_path / ".dna"))

        # Loading once registers the declarative port
        await k.instance_async("demo")

        # Serialize a new Recipe doc via the kernel's generic writer
        raw = {
            "apiVersion": "example.com/v1",
            "kind": "Recipe",
            "metadata": {"name": "bread"},
            "spec": {
                "title": "Sourdough",
                "ingredients": ["flour", "water", "salt"],
                "description": "A crusty loaf.",
            },
        }
        result = k.serialize_document("demo", "Recipe", "bread", raw)
        files = result["files"]
        assert any(f["relativePath"].endswith("RECIPE.md") for f in files)

        # Write to disk honoring the container prefix
        for f in files:
            target = scope_dir / f["relativePath"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f["content"])

        # Fresh kernel: reload the manifest and verify both docs come back
        k2 = _kernel_with_all_ext()
        k2.source(FilesystemSource(tmp_path / ".dna"))
        k2.cache(FilesystemCache(tmp_path / ".dna"))
        mi2 = await k2.instance_async("demo")

        recipes = mi2.all("Recipe")
        assert len(recipes) == 1
        reloaded = recipes[0]
        assert reloaded.name == "bread"
        assert reloaded.spec.get("title") == "Sourdough"
        assert reloaded.spec.get("ingredients") == ["flour", "water", "salt"]
