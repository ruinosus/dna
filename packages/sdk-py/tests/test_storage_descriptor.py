"""Tests for StorageDescriptor, StoragePattern, and BodyMode in kernel protocols."""
import pytest

from dna.kernel.protocols import (
    BodyMode,
    StorageDescriptor,
    StoragePattern,
)
from dna.kernel import Kernel


# ---------------------------------------------------------------------------
# Enum value tests
# ---------------------------------------------------------------------------

class TestStoragePattern:
    def test_bundle_value(self):
        assert StoragePattern.BUNDLE == "bundle"

    def test_yaml_value(self):
        assert StoragePattern.YAML == "yaml"

    def test_root_value(self):
        assert StoragePattern.ROOT == "root"

    def test_standalone_value(self):
        assert StoragePattern.STANDALONE == "standalone"

    def test_is_str(self):
        assert isinstance(StoragePattern.BUNDLE, str)


class TestBodyMode:
    def test_text_value(self):
        assert BodyMode.TEXT == "text"

    def test_list_value(self):
        assert BodyMode.LIST == "list"

    def test_sections_value(self):
        assert BodyMode.SECTIONS == "sections"

    def test_is_str(self):
        assert isinstance(BodyMode.TEXT, str)


# ---------------------------------------------------------------------------
# StorageDescriptor convenience constructors
# ---------------------------------------------------------------------------

class TestBundleConstructor:
    def test_defaults(self):
        sd = StorageDescriptor.bundle("skills", "SKILL.md")
        assert sd.container == "skills"
        assert sd.pattern == StoragePattern.BUNDLE
        assert sd.marker == "SKILL.md"
        assert sd.body_as == BodyMode.TEXT
        assert sd.body_field == "instruction"
        assert sd.body_parser is None

    def test_custom_body_as_and_field(self):
        sd = StorageDescriptor.bundle(
            "guardrails", "GUARDRAIL.md",
            body_as=BodyMode.LIST,
            body_field="rules",
        )
        assert sd.body_as == BodyMode.LIST
        assert sd.body_field == "rules"

    def test_sections_body_mode(self):
        sd = StorageDescriptor.bundle("souls", "SOUL.md", body_as=BodyMode.SECTIONS)
        assert sd.body_as == BodyMode.SECTIONS


class TestYamlConstructor:
    def test_defaults(self):
        sd = StorageDescriptor.yaml("agents")
        assert sd.container == "agents"
        assert sd.pattern == StoragePattern.YAML
        assert sd.marker is None
        assert sd.body_as is None
        assert sd.body_field is None
        assert sd.body_parser is None

    def test_empty_container(self):
        sd = StorageDescriptor.yaml("")
        assert sd.container == ""


class TestRootConstructor:
    def test_defaults(self):
        sd = StorageDescriptor.root()
        assert sd.container == ""
        assert sd.pattern == StoragePattern.ROOT
        assert sd.marker == "manifest.yaml"
        assert sd.body_as is None
        assert sd.body_field is None

    def test_custom_filename(self):
        sd = StorageDescriptor.root("module.yaml")
        assert sd.marker == "module.yaml"


class TestStandaloneConstructor:
    def test_defaults(self):
        sd = StorageDescriptor.standalone("AGENTS.md")
        assert sd.container == ""
        assert sd.pattern == StoragePattern.STANDALONE
        assert sd.marker == "AGENTS.md"
        assert sd.body_as == BodyMode.TEXT
        assert sd.body_field == "content"
        assert sd.body_parser is None

    def test_custom_body_as(self):
        sd = StorageDescriptor.standalone("CONTEXT.md", body_as=BodyMode.SECTIONS, body_field="sections")
        assert sd.body_as == BodyMode.SECTIONS
        assert sd.body_field == "sections"


# ---------------------------------------------------------------------------
# body_parser field
# ---------------------------------------------------------------------------

class TestBodyParser:
    def test_body_parser_callable(self):
        def my_parser(text: str) -> dict:
            return {"raw": text}

        sd = StorageDescriptor(
            container="skills",
            pattern=StoragePattern.BUNDLE,
            marker="SKILL.md",
            body_parser=my_parser,
        )
        assert sd.body_parser is my_parser
        assert sd.body_parser("hello") == {"raw": "hello"}

    def test_body_parser_lambda(self):
        parser = lambda text: {"lines": text.splitlines()}
        sd = StorageDescriptor.bundle("skills", "SKILL.md")
        sd.body_parser = parser
        assert sd.body_parser("a\nb") == {"lines": ["a", "b"]}

    def test_body_parser_default_none(self):
        sd = StorageDescriptor.yaml("agents")
        assert sd.body_parser is None


# ---------------------------------------------------------------------------
# Direct dataclass construction
# ---------------------------------------------------------------------------

class TestDirectConstruction:
    def test_minimal(self):
        sd = StorageDescriptor(container="agents", pattern=StoragePattern.YAML)
        assert sd.container == "agents"
        assert sd.pattern == StoragePattern.YAML
        assert sd.marker is None
        assert sd.body_as is None
        assert sd.body_field is None
        assert sd.body_parser is None

    def test_all_fields(self):
        sd = StorageDescriptor(
            container="skills",
            pattern=StoragePattern.BUNDLE,
            marker="SKILL.md",
            body_as=BodyMode.TEXT,
            body_field="instruction",
        )
        assert sd.container == "skills"
        assert sd.pattern == StoragePattern.BUNDLE
        assert sd.marker == "SKILL.md"
        assert sd.body_as == BodyMode.TEXT
        assert sd.body_field == "instruction"


# ---------------------------------------------------------------------------
# KindPort storage declarations
# ---------------------------------------------------------------------------

class TestKindStorageDeclarations:
    """All registered KindPort implementations must declare a storage attribute."""

    def _kinds(self):
        kernel = Kernel.auto()
        return list(kernel._kinds.values())

    def test_all_kinds_have_storage(self):
        """Every registered kind must have a storage attribute of type StorageDescriptor."""
        kinds = self._kinds()
        assert len(kinds) > 0, "Expected at least one registered kind"
        for kind in kinds:
            assert hasattr(kind, "storage"), (
                f"KindPort '{kind.alias}' is missing the 'storage' attribute"
            )
            assert isinstance(kind.storage, StorageDescriptor), (
                f"KindPort '{kind.alias}'.storage must be a StorageDescriptor instance"
            )

    def test_package_kind_storage(self):
        # Phase 16 — replaces test_module_kind_storage. Module deleted.
        kind = next(k for k in self._kinds() if k.alias == "helix-genome")
        sd = kind.storage
        assert sd.pattern == StoragePattern.ROOT
        assert sd.container == ""
        assert sd.marker == "Genome.yaml"

    def test_agent_kind_storage(self):
        kind = next(k for k in self._kinds() if k.alias == "helix-agent")
        sd = kind.storage
        assert sd.pattern == StoragePattern.BUNDLE
        assert sd.container == "agents"
        assert sd.marker == "AGENT.md"

    def test_actor_kind_storage(self):
        kind = next(k for k in self._kinds() if k.alias == "helix-actor")
        sd = kind.storage
        assert sd.pattern == StoragePattern.YAML
        assert sd.container == "actors"
        assert sd.marker is None

    def test_skill_kind_storage(self):
        kind = next(k for k in self._kinds() if k.alias == "agentskills-skill")
        sd = kind.storage
        assert sd.pattern == StoragePattern.BUNDLE
        assert sd.container == "skills"
        assert sd.marker == "SKILL.md"

    def test_soul_kind_storage(self):
        kind = next(k for k in self._kinds() if k.alias == "soulspec-soul")
        sd = kind.storage
        assert sd.pattern == StoragePattern.BUNDLE
        assert sd.container == "souls"
        assert sd.marker == "SOUL.md"

    def test_guardrail_kind_storage(self):
        kind = next(k for k in self._kinds() if k.alias == "guardrails-guardrail")
        sd = kind.storage
        assert sd.pattern == StoragePattern.BUNDLE
        assert sd.container == "guardrails"
        assert sd.marker == "GUARDRAIL.md"
        assert sd.body_as == BodyMode.LIST
        assert sd.body_field == "rules"

    def test_agent_definition_kind_storage(self):
        kind = next(k for k in self._kinds() if k.alias == "agentsmd-agent")
        sd = kind.storage
        assert sd.pattern == StoragePattern.STANDALONE
        assert sd.container == ""
        assert sd.marker == "AGENTS.md"


# ---------------------------------------------------------------------------
# Kernel storage helpers
# ---------------------------------------------------------------------------

class TestKernelStorageHelpers:
    @classmethod
    def setup_class(cls):
        cls.kernel = Kernel.auto()

    def test_container_for_kind_skill(self):
        assert self.kernel.container_for_kind("Skill") == "skills"

    def test_container_for_kind_agent(self):
        assert self.kernel.container_for_kind("Agent") == "agents"

    def test_container_for_kind_module(self):
        assert self.kernel.container_for_kind("Genome") == ""

    def test_container_for_kind_actor(self):
        assert self.kernel.container_for_kind("Actor") == "actors"

    def test_storage_for_kind(self):
        sd = self.kernel.storage_for_kind("Guardrail")
        assert sd is not None
        assert sd.container == "guardrails"
        assert sd.body_as == BodyMode.LIST

    def test_unknown_kind_returns_none(self):
        assert self.kernel.container_for_kind("Nonexistent") is None
        assert self.kernel.storage_for_kind("Nonexistent") is None


# ---------------------------------------------------------------------------
# Deferred generic reader/writer auto-registration
# ---------------------------------------------------------------------------

class TestDeferredGenericRegistration:
    def test_custom_kind_gets_generic_reader(self, tmp_path):
        """A custom kind with StorageDescriptor but no custom Reader gets a generic one."""
        from dna.kernel import Kernel
        from dna.kernel.kind_base import KindBase
        from dna.kernel.protocols import StorageDescriptor, BodyMode
        from dna.adapters.filesystem import FilesystemSource, FilesystemCache

        class CustomKind(KindBase):
            api_version = "test.io/v1"
            kind = "CustomThing"
            alias = "test-custom"
            storage = StorageDescriptor.bundle("customs", "CUSTOM.md",
                                               body_as=BodyMode.LIST, body_field="items")

        class CustomExt:
            name = "test-custom"
            version = "1.0"
            def register(self, kernel):
                kernel.kind(CustomKind())

        # Create filesystem layout
        scope = tmp_path / "mod"
        scope.mkdir()
        (scope / "manifest.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\nmetadata:\n  name: mod\nspec: {}\n"
        )
        customs = scope / "customs" / "my-custom"
        customs.mkdir(parents=True)
        (customs / "CUSTOM.md").write_text(
            "---\nname: my-custom\ndescription: test\n---\n\n- Item A\n- Item B\n"
        )

        k = Kernel()
        k.source(FilesystemSource(str(tmp_path)))
        k.cache(FilesystemCache(str(tmp_path)))
        from dna.extensions.helix import HelixExtension
        k.load(HelixExtension())
        k.load(CustomExt())

        mi = k.instance("mod")
        docs = [d for d in mi.documents if d.kind == "CustomThing"]
        assert len(docs) == 1
        assert docs[0].name == "my-custom"
        assert docs[0].spec.get("items") == ["Item A", "Item B"]
