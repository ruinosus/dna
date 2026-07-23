"""s-mif-passthrough-kind (feature f-portable-memory) — the MIF Memory
passthrough Kind (`mif-spec.dev/v1 · Memory`, record plane).

Market-fidelity conformance (see docs/concepts/market-fidelity.md — "the
owner names the schema"): subjects are REAL examples lifted verbatim (or
lightly extended, noted inline) from the actual MIF spec
(github.com/modeled-information-format/MIF, SPECIFICATION.md §16), not
invented data — an invented fixture would not prove anything about fidelity
to an external format DNA does not own.

Reads go through ``GenericBundleReader``/``GenericBundleWriter`` constructed
straight from the registered Kind's own ``StorageDescriptor`` — the same
classes ``kernel._ensure_generic_readers_writers()`` wires in for every
bundle-storage descriptor Kind at boot (test_generic_rw.py is the existing
precedent for this pattern). This Kind is ``plane: record`` by design (task
requirement), so it deliberately never enters ``ManifestInstance.documents``
(the F2.5 two-planes split — record Kinds go through
``kernel.query``/``get_document`` instead); exercising the Reader/Writer
directly is the most direct proof of the parse/schema/serialize behavior
without wrestling with the query-pushdown source's lazy reader-list wiring
(a pre-existing kernel/adapter nuance, out of scope here).

  1. Kind registration — descriptor-backed, record plane, strict schema
     (additionalProperties: false) except the `extensions` vault (Level 3,
     additionalProperties: true — where DNA's own physics rides along).
  2. A Level 1 fixture (SPECIFICATION.md §16.1 "Minimal Memory", verbatim)
     validates against the registered schema with ZERO deformation: the
     parsed spec is byte-for-byte the frontmatter + body MIF wrote.
  3. A Level 2 fixture (SPECIFICATION.md §16.2 "Decision Memory", frontmatter
     `relationships:` array added for schema coverage — §5.3 says the
     frontmatter array is authoritative and the body links are its mirror,
     but the spec's own inline example omits the frontmatter array; noted at
     the fixture) validates, preserves namespace/tags/entities/relationships
     exactly, and proves the `extensions` vault carries an arbitrary
     `x-dna.*` bag through unexamined.
  4. Field-level round-trip via GenericBundleWriter.serialize(): byte-
     identical round-trip is explicitly NOT the bar yet (see the
     descriptor's "KNOWN OPEN ITEM" comment — MIF's real file naming is
     `{id}.md`, not the fixed bundle marker DNA uses); field fidelity is.

TS twin: tests/mif-memory-kind.test.ts.
"""
from __future__ import annotations

import re
from pathlib import Path

import jsonschema
import pytest

import yaml

from dna.kernel import Kernel
from dna.kernel.bundle.handle import FilesystemBundleHandle
from dna.kernel.source.generic_rw import GenericBundleReader, GenericBundleWriter

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_BASE = REPO_ROOT / "tests" / "golden-fixtures" / "mif" / "memories"


def _split_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "expected a frontmatter block"
    return yaml.safe_load(m.group(1)) or {}, text[m.end():]


@pytest.fixture(scope="module")
def kp():
    k = Kernel.auto()
    return k.kind_port_for("Memory")


@pytest.fixture(scope="module")
def reader(kp):
    return GenericBundleReader(kp.storage, kp.api_version, kp.kind)


@pytest.fixture(scope="module")
def writer(kp):
    return GenericBundleWriter(kp.storage, kp.kind)


# ---------------------------------------------------------------------------
# 1. Kind registration
# ---------------------------------------------------------------------------


def test_mif_memory_kind_registered_from_descriptor(kp):
    assert kp is not None
    assert kp.alias == "mif-memory"
    assert kp.api_version == "mif-spec.dev/v1"
    assert kp.kind == "Memory"
    assert kp.origin == "mif-spec.dev"
    assert kp.plane == "record"
    assert kp.storage.container == "memories"
    assert kp.storage.marker == "MEMORY.md"
    assert kp.storage.body_field == "content"
    assert getattr(kp, "__declarative__", False) is True


def test_schema_is_strict_except_the_extensions_vault(kp):
    """New descriptor Kinds must be strict (s-strict-schema-lint) EXCEPT the
    one field that is deliberately the MIF-defined escape hatch."""
    schema = kp.schema()
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["id", "type", "content", "created"]
    assert schema["properties"]["extensions"]["additionalProperties"] is True


def test_no_dna_flavored_field_injected(kp):
    """Every top-level schema property must be traceable to the real MIF
    spec (SPECIFICATION.md §4.1/§5/§7.5/§8/§9/§13) — nothing DNA invented."""
    props = set(kp.schema()["properties"])
    mif_fields = {
        "id", "type", "content", "created", "title", "modified", "ontology",
        "namespace", "tags", "aliases", "entities", "relationships",
        "temporal", "provenance", "embedding", "citations", "summary",
        "compressed_at", "extensions",
    }
    assert props == mif_fields


def test_detects_the_marker(reader):
    bundle = FilesystemBundleHandle(FIXTURE_BASE / "minimal-preference")
    assert reader.detect(bundle) is True


# ---------------------------------------------------------------------------
# 2. Level 1 fixture — SPECIFICATION.md §16.1 "Minimal Memory", verbatim
# ---------------------------------------------------------------------------


def test_level1_fixture_validates_without_deformation(kp, reader):
    marker_path = FIXTURE_BASE / "minimal-preference" / "MEMORY.md"
    bundle = FilesystemBundleHandle(marker_path.parent)
    raw = reader.read(bundle)

    assert raw["apiVersion"] == "mif-spec.dev/v1", (
        "market namespace must be the standard owner's, untouched"
    )
    assert raw["kind"] == "Memory"

    spec = raw["spec"]
    jsonschema.validate(spec, kp.schema())

    fm, body = _split_frontmatter(marker_path.read_text())
    assert spec == {
        "id": fm["id"],
        "type": fm["type"],
        "created": fm["created"],
        "content": body.strip(),
    }
    assert spec["id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert spec["type"] == "semantic"
    assert spec["content"] == "User prefers dark mode for all applications."


# ---------------------------------------------------------------------------
# 3. Level 2 fixture — SPECIFICATION.md §16.2 "Decision Memory"
# ---------------------------------------------------------------------------


def test_level2_fixture_validates_without_deformation(kp, reader):
    marker_path = FIXTURE_BASE / "decision-react-over-vue" / "MEMORY.md"
    bundle = FilesystemBundleHandle(marker_path.parent)
    raw = reader.read(bundle)
    spec = raw["spec"]
    jsonschema.validate(spec, kp.schema())

    fm, body = _split_frontmatter(marker_path.read_text())

    # Every frontmatter field the fixture declared round-trips EXACTLY —
    # same keys, same values, no coercion, no drop.
    for key, value in fm.items():
        assert spec[key] == value, f"field {key!r} deformed on read"
    assert spec["content"] == body.strip()

    # Relationship types are real MIF core tokens (Appendix B), not the
    # draft's invented enum — proves the schema's open `type: string` (no
    # closed enum) accepts them.
    rel_types = {r["type"] for r in spec["relationships"]}
    assert rel_types == {"relates-to", "supersedes"}

    # Entities preserve the real EntityReference shape (Appendix C) —
    # nested "@type"/"@id" keys intact, not flattened to bare strings.
    react = next(e for e in spec["entities"] if e["name"] == "React")
    assert react["@type"] == "EntityReference"
    assert react["entity"]["@id"] == "urn:mif:entity:technology:react"
    assert react["entityType"] == "Technology"


def test_extensions_vault_carries_arbitrary_dna_fields(kp, reader):
    """The one deliberate open door (req #3): `extensions` accepts
    additionalProperties so DNA's own physics (x-dna.*) rides along
    unexamined by MIF's schema."""
    marker_path = FIXTURE_BASE / "decision-react-over-vue" / "MEMORY.md"
    bundle = FilesystemBundleHandle(marker_path.parent)
    spec = reader.read(bundle)["spec"]
    assert spec["extensions"] == {
        "x-dna": {"confidence_score": 0.92, "visibility": "shared"}
    }


# ---------------------------------------------------------------------------
# 4. Field-level round-trip (byte-faithful is explicitly out of scope —
#    see the descriptor's KNOWN OPEN ITEM comment)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["minimal-preference", "decision-react-over-vue"])
def test_field_level_round_trip(kp, reader, writer, name, tmp_path):
    marker_path = FIXTURE_BASE / name / "MEMORY.md"
    bundle = FilesystemBundleHandle(marker_path.parent)
    raw = reader.read(bundle)

    files = writer.serialize(raw)
    rel_paths = {f["relativePath"] for f in files}
    assert rel_paths == {"MEMORY.md"}, (
        "MIF has no scripts/references/assets sidecars — a single marker, "
        "unlike Skill/Soul"
    )
    emitted = files[0]["content"]

    # Write the re-emitted marker under the SAME bundle name and re-read it
    # through the real reader (not a hand-rolled frontmatter split) — this
    # is what "re-parses to the same spec" must mean: the production read
    # path, not my own parsing of it. bundle.name feeds metadata.name on
    # read, so reusing `name` keeps that fixed point.
    reemitted_dir = tmp_path / name
    reemitted_dir.mkdir()
    (reemitted_dir / "MEMORY.md").write_text(emitted)
    re_raw = reader.read(FilesystemBundleHandle(reemitted_dir))

    assert re_raw["spec"] == raw["spec"], (
        "re-emitted marker does not re-parse to the same spec"
    )
