"""Phase 16 — unit tests for the new Genome + LayerPolicy Kinds.

Verifies:
- ``GenomeKind.parse`` round-trips identity + version + runtime fields.
- ``OVERLAYABLE_FIELDS`` allowlist contains exactly the runtime defaults.
- ``LayerPolicyKind.parse`` normalizes policy strings to lowercase.
- Both Kinds expose JSON schemas via ``schema()``.
- ``preview()`` produces non-empty PreviewBlock for populated specs.
- ``HelixExtension.register`` wires both Kinds into the kernel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dna.extensions.helix import (
    HelixExtension,
    LayerPolicyKind,
    GenomeKind,
)
from dna.kernel.models import (
    LayerPolicySpec,
    GenomeSpec,
    TypedLayerPolicy,
    TypedGenome,
)


@dataclass
class FakeDoc:
    kind: str
    name: str
    spec: dict[str, Any]
    api_version: str = "test/v1"


# ---------------------------------------------------------------------------
# GenomeKind
# ---------------------------------------------------------------------------


class TestGenomeKindParse:
    def setup_method(self) -> None:
        self.kp = GenomeKind()

    def test_parse_round_trip_full_spec(self) -> None:
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Genome",
            "metadata": {"name": "hr-screening", "description": "HR scope"},
            "spec": {
                "owner": "platform-team",
                "owner_tenant": "platform",
                "repository": "https://github.com/example/hr",
                "visibility": "public",
                "version": "1.2.3",
                "changelog_url": "https://example.com/changelog",
                "deprecated": False,
                "deprecated_message": None,
                "default_agent": "talent-screener",
                "default_llm": "gpt-4o",
                "budget": {"daily_usd": 50},
                "tags": ["hr", "screening"],
                "dependencies": [{"source": "github:foo/bar@main"}],
            },
        }
        typed = self.kp.parse(raw)
        assert isinstance(typed, TypedGenome)
        assert typed.metadata.name == "hr-screening"
        assert typed.spec.owner == "platform-team"
        assert typed.spec.owner_tenant == "platform"
        assert typed.spec.version == "1.2.3"
        assert typed.spec.default_agent == "talent-screener"
        assert typed.spec.default_llm == "gpt-4o"
        assert typed.spec.tags == ["hr", "screening"]
        assert typed.spec.dependencies == [{"source": "github:foo/bar@main"}]
        assert typed.spec.deprecated is False

    def test_parse_minimal_spec_uses_defaults(self) -> None:
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Genome",
            "metadata": {"name": "tiny"},
            "spec": {},
        }
        typed = self.kp.parse(raw)
        assert typed.spec.visibility == "public"
        assert typed.spec.version is None
        assert typed.spec.deprecated is False
        assert typed.spec.tags == []
        assert typed.spec.dependencies == []

    def test_deprecated_truthy_coerces(self) -> None:
        raw = {"kind": "Genome", "spec": {"deprecated": "yes", "deprecated_message": "use v2"}}
        typed = self.kp.parse(raw)
        assert typed.spec.deprecated is True
        assert typed.spec.deprecated_message == "use v2"


class TestGenomeKindIdentity:
    def setup_method(self) -> None:
        self.kp = GenomeKind()

    def test_kind_identity_fields(self) -> None:
        assert self.kp.api_version == "github.com/ruinosus/dna/v1"
        assert self.kp.kind == "Genome"
        assert self.kp.alias == "helix-genome"

    def test_storage_descriptor_root_filename(self) -> None:
        assert self.kp.storage.marker == "Genome.yaml"
        assert self.kp.storage.container == ""

    def test_is_root_true_after_examples_migrated(self) -> None:
        # Phase 16 commit 3 — once examples migrated to Genome.yaml,
        # root flag transferred from Module to Genome. The kernel's
        # "exactly one root Kind" invariant is preserved because Module
        # flipped to is_root=False in lockstep. Commit 4 removes
        # is_root from KindPort entirely.
        assert self.kp.is_root is True

    def test_is_not_prompt_target(self) -> None:
        assert self.kp.is_prompt_target is False

    def test_no_dep_filters(self) -> None:
        # Composition validation walks scanner output; Genome has no
        # bill-of-materials inventory arrays.
        assert self.kp.dep_filters() is None


class TestGenomeOverlayableFields:
    def test_allowlist_contains_runtime_defaults(self) -> None:
        kp = GenomeKind()
        expected = frozenset({"default_agent", "default_llm", "budget", "tags"})
        assert kp.OVERLAYABLE_FIELDS == expected

    def test_allowlist_excludes_identity_fields(self) -> None:
        kp = GenomeKind()
        for forbidden in (
            "owner",
            "owner_tenant",
            "repository",
            "visibility",
            "version",
            "changelog_url",
            "deprecated",
            "deprecated_message",
            "dependencies",
        ):
            assert forbidden not in kp.OVERLAYABLE_FIELDS, (
                f"{forbidden} must NOT be tenant-overlayable"
            )


class TestGenomeKindSchema:
    def setup_method(self) -> None:
        self.kp = GenomeKind()

    def test_schema_returns_object_with_properties(self) -> None:
        schema = self.kp.schema()
        assert schema is not None
        assert schema.get("type") == "object"
        props = schema.get("properties", {})
        for required_field in (
            "owner",
            "owner_tenant",
            "visibility",
            "version",
            "default_agent",
            "default_llm",
            "budget",
            "tags",
            "dependencies",
        ):
            assert required_field in props, f"missing field {required_field}"


class TestGenomeKindPreview:
    def setup_method(self) -> None:
        self.kp = GenomeKind()

    def test_preview_renders_populated_fields(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(
                kind="Genome",
                name="hr-screening",
                spec={
                    "owner_tenant": "platform",
                    "visibility": "public",
                    "version": "1.0.0",
                    "default_agent": "talent-screener",
                    "default_llm": "gpt-4o",
                    "dependencies": [{"source": "x"}, {"source": "y"}],
                },
            )
        )
        assert len(blocks) == 1
        assert blocks[0].kind == "fields"
        labels = [f["label"] for f in blocks[0].fields]
        assert "owner_tenant" in labels
        assert "version" in labels
        assert "default_agent" in labels
        assert "dependencies" in labels

    def test_preview_renders_deprecated_message(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(
                kind="Genome",
                name="legacy",
                spec={"deprecated": True, "deprecated_message": "use v2"},
            )
        )
        labels = [f["label"] for f in blocks[0].fields]
        assert "deprecated" in labels

    def test_preview_empty_when_blank(self) -> None:
        blocks = self.kp.preview(FakeDoc(kind="Genome", name="blank", spec={}))
        assert blocks[0].kind == "empty"


class TestGenomeKindDescribe:
    def test_describe_includes_owner_and_version(self) -> None:
        kp = GenomeKind()
        text = kp.describe(
            FakeDoc(
                kind="Genome",
                name="hr",
                spec={"owner_tenant": "acme", "version": "2.0.0", "visibility": "private"},
            )
        )
        assert text is not None
        assert "acme" in text
        assert "2.0.0" in text
        assert "private" in text

    def test_describe_falls_back_to_platform_when_owner_tenant_null(self) -> None:
        kp = GenomeKind()
        text = kp.describe(FakeDoc(kind="Genome", name="x", spec={}))
        assert text is not None
        assert "platform" in text


# ---------------------------------------------------------------------------
# LayerPolicyKind
# ---------------------------------------------------------------------------


class TestLayerPolicyKindParse:
    def setup_method(self) -> None:
        self.kp = LayerPolicyKind()

    def test_parse_round_trip(self) -> None:
        raw = {
            "apiVersion": "github.com/ruinosus/dna/policy/v1",
            "kind": "LayerPolicy",
            "metadata": {"name": "tenant-default"},
            "spec": {
                "layer_id": "tenant",
                "policies": {
                    "helix-agent": "locked",
                    "agentskills-skill": "open",
                },
            },
        }
        typed = self.kp.parse(raw)
        assert isinstance(typed, TypedLayerPolicy)
        assert typed.spec.layer_id == "tenant"
        assert typed.spec.policies == {
            "helix-agent": "locked",
            "agentskills-skill": "open",
        }

    def test_policy_values_normalized_lowercase(self) -> None:
        raw = {
            "kind": "LayerPolicy",
            "spec": {
                "layer_id": "branch",
                "policies": {
                    "helix-genome": "LOCKED",
                    "agentskills-skill": "Restricted",
                },
            },
        }
        typed = self.kp.parse(raw)
        assert typed.spec.policies == {
            "helix-genome": "locked",
            "agentskills-skill": "restricted",
        }

    def test_empty_policies_yield_empty_dict(self) -> None:
        raw = {"kind": "LayerPolicy", "spec": {"layer_id": "tenant"}}
        typed = self.kp.parse(raw)
        assert typed.spec.policies == {}

    def test_falsy_policy_values_dropped(self) -> None:
        raw = {
            "kind": "LayerPolicy",
            "spec": {
                "layer_id": "tenant",
                "policies": {
                    "helix-agent": "open",
                    "blanked": "",
                    "nulled": None,
                },
            },
        }
        typed = self.kp.parse(raw)
        assert "helix-agent" in typed.spec.policies
        assert "blanked" not in typed.spec.policies
        assert "nulled" not in typed.spec.policies


class TestLayerPolicyKindIdentity:
    def setup_method(self) -> None:
        self.kp = LayerPolicyKind()

    def test_kind_identity_fields(self) -> None:
        assert self.kp.api_version == "github.com/ruinosus/dna/policy/v1"
        assert self.kp.kind == "LayerPolicy"
        assert self.kp.alias == "policy-layer-policy"

    def test_storage_descriptor_yaml_in_policies_container(self) -> None:
        assert self.kp.storage.container == "policies"

    def test_not_root_not_prompt_target(self) -> None:
        assert self.kp.is_root is False
        assert self.kp.is_prompt_target is False


class TestLayerPolicyKindSchema:
    def test_schema_has_layer_id_and_policies(self) -> None:
        kp = LayerPolicyKind()
        schema = kp.schema()
        assert schema is not None
        props = schema.get("properties", {})
        assert "layer_id" in props
        assert "policies" in props


class TestLayerPolicyKindPreview:
    def setup_method(self) -> None:
        self.kp = LayerPolicyKind()

    def test_preview_renders_layer_and_each_policy(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(
                kind="LayerPolicy",
                name="tenant-default",
                spec={
                    "layer_id": "tenant",
                    "policies": {
                        "helix-agent": "locked",
                        "agentskills-skill": "open",
                    },
                },
            )
        )
        assert len(blocks) == 1
        assert blocks[0].kind == "fields"
        labels = [f["label"] for f in blocks[0].fields]
        assert "layer_id" in labels
        assert "helix-agent" in labels
        assert "agentskills-skill" in labels

    def test_preview_empty_when_blank(self) -> None:
        blocks = self.kp.preview(
            FakeDoc(kind="LayerPolicy", name="empty", spec={})
        )
        assert blocks[0].kind == "empty"


class TestLayerPolicyKindDescribe:
    def test_describe_includes_layer_and_count(self) -> None:
        kp = LayerPolicyKind()
        text = kp.describe(
            FakeDoc(
                kind="LayerPolicy",
                name="tenant-default",
                spec={
                    "layer_id": "tenant",
                    "policies": {"a": "open", "b": "locked"},
                },
            )
        )
        assert text is not None
        assert "tenant" in text
        assert "2" in text  # rule count


# ---------------------------------------------------------------------------
# HelixExtension wiring
# ---------------------------------------------------------------------------


class FakeKernel:
    def __init__(self) -> None:
        self.kinds: list[Any] = []
        self.readers: list[Any] = []
        self.writers: list[Any] = []
        self.profiles: list[Any] = []
        # s-write-path-despecialize — extensions register pre_save veto
        # hooks on kernel.hooks; the double needs a real registry.
        from dna.kernel.hooks import HookRegistry
        self.hooks = HookRegistry()

    def kind(self, k: Any) -> None:
        self.kinds.append(k)

    def reader(self, r: Any) -> None:
        self.readers.append(r)

    def writer(self, w: Any) -> None:
        self.writers.append(w)

    def composition_profile(self, p: Any) -> None:
        self.profiles.append(p)


class TestHelixExtensionRegister:
    def test_registers_package_and_layer_policy(self) -> None:
        ext = HelixExtension()
        kernel = FakeKernel()
        ext.register(kernel)
        registered_kinds = {type(k).__name__ for k in kernel.kinds}
        assert "GenomeKind" in registered_kinds
        assert "LayerPolicyKind" in registered_kinds
        # Phase 16 cleanup — ModuleKind class deleted, no longer registered.
        assert "ModuleKind" not in registered_kinds


# ---------------------------------------------------------------------------
# Spec-level coverage (independent of Kind classes)
# ---------------------------------------------------------------------------


class TestGenomeSpecDataclass:
    def test_from_raw_handles_none_inputs(self) -> None:
        spec = GenomeSpec.from_raw({})
        assert spec.owner is None
        assert spec.tags == []
        assert spec.dependencies == []
        assert spec.visibility == "public"

    def test_visibility_falls_back_when_blank(self) -> None:
        spec = GenomeSpec.from_raw({"visibility": ""})
        assert spec.visibility == "public"


class TestLayerPolicySpecDataclass:
    def test_from_raw_normalizes_policies(self) -> None:
        spec = LayerPolicySpec.from_raw(
            {"layer_id": "tenant", "policies": {"a": "OPEN", "b": "Restricted"}}
        )
        assert spec.policies == {"a": "open", "b": "restricted"}

    def test_from_raw_drops_non_string_keys(self) -> None:
        spec = LayerPolicySpec.from_raw(
            {"policies": {1: "open", "ok": "open"}}  # type: ignore[dict-item]
        )
        assert 1 not in spec.policies
        assert "ok" in spec.policies
