"""Tests for GenericBundleReader and GenericBundleWriter."""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.kernel.generic_rw import GenericBundleReader, GenericBundleWriter
from dna.kernel.protocols import BodyMode, StorageDescriptor
from dna.kernel.bundle_handle import FilesystemBundleHandle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skill_sd() -> StorageDescriptor:
    return StorageDescriptor.bundle("skills", "SKILL.md", body_as=BodyMode.TEXT, body_field="instruction")


def _guardrail_sd() -> StorageDescriptor:
    return StorageDescriptor.bundle("guardrails", "GUARDRAIL.md", body_as=BodyMode.LIST, body_field="rules")


def _section_sd() -> StorageDescriptor:
    return StorageDescriptor.bundle("docs", "DOC.md", body_as=BodyMode.SECTIONS, body_field="sections")


# ---------------------------------------------------------------------------
# TestGenericBundleReader
# ---------------------------------------------------------------------------

class TestGenericBundleReader:

    def test_detect_finds_marker(self, tmp_path: Path) -> None:
        sd = _skill_sd()
        reader = GenericBundleReader(sd, "test.io/v1", "MyKind")
        bundle = tmp_path / "my-bundle"
        bundle.mkdir()
        (bundle / "SKILL.md").write_text("---\nname: test\n---\n\nInstruction body.")
        assert reader.detect(FilesystemBundleHandle(bundle)) is True

    def test_detect_rejects_missing_marker(self, tmp_path: Path) -> None:
        sd = _skill_sd()
        reader = GenericBundleReader(sd, "test.io/v1", "MyKind")
        bundle = tmp_path / "empty-bundle"
        bundle.mkdir()
        assert reader.detect(FilesystemBundleHandle(bundle)) is False

    def test_read_text_body_metadata_and_spec(self, tmp_path: Path) -> None:
        sd = _skill_sd()
        reader = GenericBundleReader(sd, "test.io/v1", "MyKind")
        bundle = tmp_path / "my-skill"
        bundle.mkdir()
        (bundle / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A test skill\n---\n\nDo something useful."
        )

        doc = reader.read(FilesystemBundleHandle(bundle))

        assert doc["apiVersion"] == "test.io/v1"
        assert doc["kind"] == "MyKind"
        assert doc["metadata"]["name"] == "my-skill"
        assert doc["metadata"]["description"] == "A test skill"
        assert doc["spec"]["instruction"] == "Do something useful."

    def test_read_envelope_marker_unwraps_inner_spec(self, tmp_path: Path) -> None:
        # Regression (2026-06-07): the Postgres source re-parses bundle markers
        # via THIS generic reader, and envelope-emitting writers (e.g.
        # HtmlArtifactWriter) produce markers shaped
        # ``{apiVersion, kind, metadata, spec: {...}}``. Without envelope-unwrap
        # the reader treated the envelope keys as spec fields, yielding
        # spec={apiVersion, kind, metadata, spec, ...} (the envelope-as-spec bug
        # — intermittent in prod because the granular cache masked it until a
        # TTL miss re-read from source).
        sd = _skill_sd()
        reader = GenericBundleReader(sd, "test.io/v1", "MyKind")
        bundle = tmp_path / "env-doc"
        bundle.mkdir()
        (bundle / "SKILL.md").write_text(
            "---\n"
            "apiVersion: test.io/v1\n"
            "kind: MyKind\n"
            "metadata:\n  name: kept\n"
            "spec:\n  foo: 1\n  bar: hi\n"
            "---\n\nbody text\n"
        )

        doc = reader.read(FilesystemBundleHandle(bundle))

        assert doc["metadata"]["name"] == "kept"
        # spec is the INNER spec — NOT the envelope keys.
        assert doc["spec"]["foo"] == 1
        assert doc["spec"]["bar"] == "hi"
        assert "apiVersion" not in doc["spec"]
        assert "kind" not in doc["spec"]
        assert "spec" not in doc["spec"]
        # body still lands in the body_field (instruction for skills).
        assert doc["spec"]["instruction"] == "body text"

    def test_read_text_body_defaults_name_to_dir(self, tmp_path: Path) -> None:
        sd = _skill_sd()
        reader = GenericBundleReader(sd, "test.io/v1", "MyKind")
        bundle = tmp_path / "inferred-name"
        bundle.mkdir()
        (bundle / "SKILL.md").write_text("---\n---\n\nBody here.")

        doc = reader.read(FilesystemBundleHandle(bundle))
        assert doc["metadata"]["name"] == "inferred-name"

    def test_read_text_body_no_frontmatter(self, tmp_path: Path) -> None:
        sd = _skill_sd()
        reader = GenericBundleReader(sd, "test.io/v1", "MyKind")
        bundle = tmp_path / "no-fm"
        bundle.mkdir()
        (bundle / "SKILL.md").write_text("Just plain body text.")

        doc = reader.read(FilesystemBundleHandle(bundle))
        assert doc["spec"]["instruction"] == "Just plain body text."

    def test_read_list_body(self, tmp_path: Path) -> None:
        sd = _guardrail_sd()
        reader = GenericBundleReader(sd, "github.com/ruinosus/dna/v1", "Guardrail")
        bundle = tmp_path / "my-guardrail"
        bundle.mkdir()
        (bundle / "GUARDRAIL.md").write_text(
            "---\nname: my-guardrail\n---\n\n- Rule one\n- Rule two\n- Rule three"
        )

        doc = reader.read(FilesystemBundleHandle(bundle))
        assert doc["spec"]["rules"] == ["Rule one", "Rule two", "Rule three"]

    def test_read_list_body_with_indented_items(self, tmp_path: Path) -> None:
        sd = _guardrail_sd()
        reader = GenericBundleReader(sd, "github.com/ruinosus/dna/v1", "Guardrail")
        bundle = tmp_path / "indented"
        bundle.mkdir()
        (bundle / "GUARDRAIL.md").write_text(
            "---\nname: indented\n---\n\n  - Indented rule A\n- Normal rule B\n    - Deeper rule C"
        )

        doc = reader.read(FilesystemBundleHandle(bundle))
        assert doc["spec"]["rules"] == ["Indented rule A", "Normal rule B", "Deeper rule C"]

    def test_read_sections_body(self, tmp_path: Path) -> None:
        sd = _section_sd()
        reader = GenericBundleReader(sd, "docs.io/v1", "Doc")
        bundle = tmp_path / "my-doc"
        bundle.mkdir()
        (bundle / "DOC.md").write_text(
            "---\nname: my-doc\n---\n\nPreamble text here.\n\n## Section One\n\nContent of section one.\n\n## Section Two\n\nContent of section two."
        )

        doc = reader.read(FilesystemBundleHandle(bundle))
        sections = doc["spec"]["sections"]
        assert sections["_preamble"] == "Preamble text here."
        assert sections["Section One"] == "Content of section one."
        assert sections["Section Two"] == "Content of section two."

    def test_read_sections_no_preamble(self, tmp_path: Path) -> None:
        sd = _section_sd()
        reader = GenericBundleReader(sd, "docs.io/v1", "Doc")
        bundle = tmp_path / "doc-no-preamble"
        bundle.mkdir()
        (bundle / "DOC.md").write_text(
            "---\nname: doc-no-preamble\n---\n\n## Section A\n\nContent A.\n\n## Section B\n\nContent B."
        )

        doc = reader.read(FilesystemBundleHandle(bundle))
        sections = doc["spec"]["sections"]
        assert "_preamble" not in sections
        assert sections["Section A"] == "Content A."
        assert sections["Section B"] == "Content B."

    def test_read_sections_subheadings_stay_in_parent(self, tmp_path: Path) -> None:
        sd = _section_sd()
        reader = GenericBundleReader(sd, "docs.io/v1", "Doc")
        bundle = tmp_path / "doc-subheadings"
        bundle.mkdir()
        (bundle / "DOC.md").write_text(
            "---\nname: doc-subheadings\n---\n\n## Main Section\n\nIntro line.\n\n### Sub heading\n\nSub content."
        )

        doc = reader.read(FilesystemBundleHandle(bundle))
        sections = doc["spec"]["sections"]
        assert "Main Section" in sections
        # ### should not split into its own key
        assert "Sub heading" not in sections
        assert "### Sub heading" in sections["Main Section"]

    def test_read_with_custom_body_parser(self, tmp_path: Path) -> None:
        def custom_parser(body: str) -> dict:
            return {"custom_field": body.upper(), "line_count": len(body.splitlines())}

        sd = StorageDescriptor.bundle("custom", "CUSTOM.md", body_as=BodyMode.TEXT, body_field="unused")
        sd.body_parser = custom_parser

        reader = GenericBundleReader(sd, "custom.io/v1", "Custom")
        bundle = tmp_path / "custom-bundle"
        bundle.mkdir()
        (bundle / "CUSTOM.md").write_text("---\nname: custom-bundle\n---\n\nhello world")

        doc = reader.read(FilesystemBundleHandle(bundle))
        assert "custom_field" in doc["spec"]
        assert "HELLO WORLD" in doc["spec"]["custom_field"]
        assert "line_count" in doc["spec"]
        # body_as / body_field should NOT appear since parser overrides them
        assert "unused" not in doc["spec"]

    def test_frontmatter_fields_split_correctly(self, tmp_path: Path) -> None:
        """name/description/labels go to metadata; everything else to spec."""
        sd = _skill_sd()
        reader = GenericBundleReader(sd, "test.io/v1", "MyKind")
        bundle = tmp_path / "split-fields"
        bundle.mkdir()
        (bundle / "SKILL.md").write_text(
            "---\nname: split-fields\ndescription: desc\nlabels:\n  - tag1\nextra_field: extra_value\n---\n\nBody."
        )

        doc = reader.read(FilesystemBundleHandle(bundle))
        assert doc["metadata"]["name"] == "split-fields"
        assert doc["metadata"]["description"] == "desc"
        assert doc["metadata"]["labels"] == ["tag1"]
        assert doc["spec"]["extra_field"] == "extra_value"
        assert "extra_field" not in doc["metadata"]
        assert "name" not in doc["spec"]
        assert "description" not in doc["spec"]


# ---------------------------------------------------------------------------
# TestGenericBundleWriter
# ---------------------------------------------------------------------------

class TestGenericBundleWriter:

    def test_can_write_matches_kind(self) -> None:
        sd = _skill_sd()
        writer = GenericBundleWriter(sd, "MyKind")
        assert writer.can_write({"kind": "MyKind"}) is True

    def test_can_write_rejects_other_kinds(self) -> None:
        sd = _skill_sd()
        writer = GenericBundleWriter(sd, "MyKind")
        assert writer.can_write({"kind": "OtherKind"}) is False
        assert writer.can_write({}) is False

    def test_write_text_body(self, tmp_path: Path) -> None:
        sd = _skill_sd()
        writer = GenericBundleWriter(sd, "MyKind")
        bundle = tmp_path / "my-skill"
        raw = {
            "apiVersion": "test.io/v1",
            "kind": "MyKind",
            "metadata": {"name": "my-skill", "description": "A skill"},
            "spec": {"instruction": "Do the thing."},
        }

        writer.write(FilesystemBundleHandle(bundle), raw)

        content = (bundle / "SKILL.md").read_text()
        assert "name: my-skill" in content
        assert "description: A skill" in content
        assert "Do the thing." in content
        assert content.startswith("---\n")
        assert "---\n\n" in content  # separator before body

    def test_write_list_body(self, tmp_path: Path) -> None:
        sd = _guardrail_sd()
        writer = GenericBundleWriter(sd, "Guardrail")
        bundle = tmp_path / "my-guardrail"
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Guardrail",
            "metadata": {"name": "my-guardrail"},
            "spec": {"rules": ["Rule A", "Rule B", "Rule C"]},
        }

        writer.write(FilesystemBundleHandle(bundle), raw)

        content = (bundle / "GUARDRAIL.md").read_text()
        assert "- Rule A" in content
        assert "- Rule B" in content
        assert "- Rule C" in content

    def test_write_creates_directory(self, tmp_path: Path) -> None:
        sd = _skill_sd()
        writer = GenericBundleWriter(sd, "MyKind")
        bundle = tmp_path / "new" / "nested" / "skill"
        raw = {
            "kind": "MyKind",
            "metadata": {"name": "nested"},
            "spec": {"instruction": "body"},
        }

        writer.write(FilesystemBundleHandle(bundle), raw)

        assert bundle.is_dir()
        assert (bundle / "SKILL.md").exists()

    def test_roundtrip_text(self, tmp_path: Path) -> None:
        sd = _skill_sd()
        writer = GenericBundleWriter(sd, "MyKind")
        reader = GenericBundleReader(sd, "test.io/v1", "MyKind")

        bundle = tmp_path / "roundtrip-text"
        raw = {
            "apiVersion": "test.io/v1",
            "kind": "MyKind",
            "metadata": {"name": "roundtrip-text", "description": "Round trip test"},
            "spec": {"instruction": "This is the instruction body."},
        }

        writer.write(FilesystemBundleHandle(bundle), raw)
        doc = reader.read(FilesystemBundleHandle(bundle))

        assert doc["metadata"]["name"] == "roundtrip-text"
        assert doc["metadata"]["description"] == "Round trip test"
        assert doc["spec"]["instruction"] == "This is the instruction body."

    def test_roundtrip_list(self, tmp_path: Path) -> None:
        sd = _guardrail_sd()
        writer = GenericBundleWriter(sd, "Guardrail")
        reader = GenericBundleReader(sd, "github.com/ruinosus/dna/v1", "Guardrail")

        bundle = tmp_path / "roundtrip-list"
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Guardrail",
            "metadata": {"name": "roundtrip-list"},
            "spec": {"rules": ["Do not lie", "Be concise", "Stay on topic"]},
        }

        writer.write(FilesystemBundleHandle(bundle), raw)
        doc = reader.read(FilesystemBundleHandle(bundle))

        assert doc["spec"]["rules"] == ["Do not lie", "Be concise", "Stay on topic"]

    def test_roundtrip_sections(self, tmp_path: Path) -> None:
        sd = _section_sd()
        writer = GenericBundleWriter(sd, "Doc")
        reader = GenericBundleReader(sd, "docs.io/v1", "Doc")

        bundle = tmp_path / "roundtrip-sections"
        raw = {
            "apiVersion": "docs.io/v1",
            "kind": "Doc",
            "metadata": {"name": "roundtrip-sections"},
            "spec": {
                "sections": {
                    "_preamble": "Intro text.",
                    "First Section": "Content of first.",
                    "Second Section": "Content of second.",
                }
            },
        }

        writer.write(FilesystemBundleHandle(bundle), raw)
        doc = reader.read(FilesystemBundleHandle(bundle))

        sections = doc["spec"]["sections"]
        assert sections["_preamble"] == "Intro text."
        assert sections["First Section"] == "Content of first."
        assert sections["Second Section"] == "Content of second."

    def test_body_field_excluded_from_frontmatter(self, tmp_path: Path) -> None:
        """The body_field should not appear in YAML frontmatter."""
        sd = _skill_sd()
        writer = GenericBundleWriter(sd, "MyKind")
        bundle = tmp_path / "no-body-in-fm"
        raw = {
            "kind": "MyKind",
            "metadata": {"name": "test"},
            "spec": {"instruction": "The body.", "extra": "value"},
        }

        writer.write(FilesystemBundleHandle(bundle), raw)

        content = (bundle / "SKILL.md").read_text()
        # Find the frontmatter section
        fm_end = content.index("---\n\n")
        frontmatter = content[:fm_end]
        assert "instruction:" not in frontmatter
        assert "extra: value" in frontmatter


# ---------------------------------------------------------------------------
# TestGuardrailGenericRoundtrip
# ---------------------------------------------------------------------------

class TestSerialize:
    def test_generic_writer_serialize_text(self):
        sd = StorageDescriptor.bundle("things", "THING.md")
        writer = GenericBundleWriter(sd, "Thing")
        files = writer.serialize({
            "kind": "Thing",
            "metadata": {"name": "my-thing", "description": "test"},
            "spec": {"instruction": "Do it.", "extra": "val"},
        })
        assert len(files) == 1
        assert files[0]["relativePath"] == "THING.md"
        assert "name: my-thing" in files[0]["content"]
        assert "Do it." in files[0]["content"]

    def test_generic_writer_serialize_list(self):
        sd = StorageDescriptor.bundle("guards", "GUARD.md", body_as=BodyMode.LIST, body_field="rules")
        writer = GenericBundleWriter(sd, "Guard")
        files = writer.serialize({
            "kind": "Guard",
            "metadata": {"name": "safety"},
            "spec": {"rules": ["A", "B"], "severity": "error"},
        })
        assert "- A" in files[0]["content"]
        assert "- B" in files[0]["content"]
        assert "severity: error" in files[0]["content"]


class TestLiteralBlockScalarRoundtrip:
    """Regression for SESSION.md frontmatter corruption — long multi-line
    content was being dumped as double-quoted scalar with \\n + line-
    continuation escapes; on subsequent re-parse the scanner choked and
    fell back to empty frontmatter, silently losing the doc's spec.
    Fix: representer emits multi-line strings as ``|`` literal block.
    """

    def test_roundtrip_markdown_in_quoted_scalar(self) -> None:
        import yaml
        from dna.kernel.generic_rw import safe_yaml_dump

        # Worst-case payload: markdown tables, embedded quotes, the literal
        # two-char sequence `\n` (backslash-n), and many lines.
        content = (
            'Investigação profunda concluída.\n\n'
            '| Camada | Arquivo | O que faz |\n'
            '|---|---|---|\n'
            '| HTTP | harness | Retorna {name, mount_path} |\n\n'
            'Linha com "aspas" e backslash literal \\n aqui.\n'
            'Final.'
        )
        payload = {
            "kind": "AgentSession",
            "metadata": {"name": "vs-test"},
            "spec": {"messages": [{"role": "assistant", "content": content}]},
        }

        dumped = safe_yaml_dump(payload)
        # Must use literal block style — not double-quoted with line escapes.
        assert "content: |" in dumped, dumped

        reloaded = yaml.safe_load(dumped)
        assert reloaded["spec"]["messages"][0]["content"] == content


class TestKernelSerializeDocument:
    def test_serialize_agent(self):
        from dna.kernel import Kernel
        from pathlib import Path
        base = Path(__file__).parent.parent.parent.parent / "scopes/open-swe/.dna"
        mi = Kernel.quick("open-swe", base_dir=str(base))
        agent = next((d for d in mi.documents if d.kind == "Agent" and d.name == "swe-agent"), None)
        assert agent is not None
        k = mi._kernel
        result = k.serialize_document("open-swe", "Agent", "swe-agent", agent.raw)
        assert len(result["files"]) > 0
        assert result["files"][0]["relativePath"].startswith("agents/swe-agent/")

    def test_serialize_package(self):
        # Phase 16 — replaces test_serialize_module. Module Kind deleted.
        from dna.kernel import Kernel
        from pathlib import Path
        base = Path(__file__).parent.parent.parent.parent / "scopes/open-swe/.dna"
        mi = Kernel.quick("open-swe", base_dir=str(base))
        root = mi.root
        k = mi._kernel
        result = k.serialize_document("open-swe", "Genome", root.name, root.raw)
        assert result["files"][0]["relativePath"] == "Genome.yaml"


class TestGuardrailGenericRoundtrip:
    def test_guardrail_loads_via_generic(self, tmp_path):
        """After removing GuardrailReader, generic reader handles GUARDRAIL.md bundles."""
        from dna.kernel import Kernel
        from dna.adapters.filesystem import FilesystemSource, FilesystemCache

        scope = tmp_path / "mod"
        scope.mkdir()
        (scope / "manifest.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\nmetadata:\n  name: mod\nspec: {}\n"
        )
        g = scope / "guardrails" / "safety"
        g.mkdir(parents=True)
        (g / "GUARDRAIL.md").write_text(
            "---\nname: safety\ndescription: Safety guardrail\nseverity: error\n---\n\n- No harm\n- Be safe\n"
        )

        k = Kernel.auto(source=FilesystemSource(str(tmp_path)))
        mi = k.instance("mod")
        guards = [d for d in mi.documents if d.kind == "Guardrail"]
        assert len(guards) == 1
        assert guards[0].name == "safety"
        assert guards[0].spec.get("rules") == ["No harm", "Be safe"]
        assert guards[0].spec.get("severity") == "error"
