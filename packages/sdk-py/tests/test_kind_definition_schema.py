"""s-dna-kindport-descriptor-schema — published KindDefinition JSON Schema.

The `.kind.yaml` / per-scope KIND.yaml descriptor format now has a
machine-readable contract: ``docs/schemas/kind-definition.schema.json``
(draft 2020-12), with a byte-identical runtime copy shipped as sdk-py
package data (``dna/kernel/schemas/``). This suite locks:

- the schema is itself valid draft 2020-12;
- the published copy and the packaged runtime copy are byte-identical;
- EVERY descriptor in the repo (builtin ``kinds/*.kind.yaml`` on both
  SDK sides + per-scope ``kinds/*/KIND.yaml``) validates against it AND
  parses through the hand-rolled ``TypedKindDefinition.from_raw`` — the
  two validators agree on the whole real corpus;
- the schema backstop catches what the hand-rolled checks silently
  ignored (typo'd/unknown spec fields, wrong types);
- the strict ``spec.ui`` key set stays derived from StudioUIMetadata
  (single source of truth — the schema can't drift from the dataclass).

TS twin: ``packages/sdk-ts/tests/kind-definition-schema.test.ts`` locks
the Zod ``KindDefinitionSpecSchema`` key set against the same file.
"""
from __future__ import annotations

import copy
import hashlib
import pathlib
from typing import Any

import pytest
import yaml

from dna.kernel.kind_definition_schema import (
    kind_definition_schema,
    validate_kind_definition,
)
from dna.kernel.models import TypedKindDefinition

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_PACKAGED = (
    pathlib.Path(__file__).resolve().parents[1]
    / "dna" / "kernel" / "schemas" / "kind-definition.schema.json"
)
_PUBLISHED = _REPO_ROOT / "docs" / "schemas" / "kind-definition.schema.json"

# Runtime-stamped volatile fields allowed by the schema but not part of
# the authored surface (KindBase.VOLATILE_SPEC_FIELDS).
_VOLATILE = {"updated_at", "created_at", "version"}


def _repo_descriptors() -> list[tuple[pathlib.Path, dict[str, Any]]]:
    files = sorted(
        set(_REPO_ROOT.glob("packages/sdk-py/**/kinds/*.kind.yaml"))
        | set(_REPO_ROOT.glob("packages/sdk-ts/**/kinds/*.kind.yaml"))
        | set(_REPO_ROOT.glob("scopes/*/.dna/*/kinds/*/KIND.yaml"))
    )
    return [(f, yaml.safe_load(f.read_text(encoding="utf-8"))) for f in files]


def _minimal_valid() -> dict[str, Any]:
    return {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "schema-test"},
        "spec": {
            "target_api_version": "schematest.example/v1",
            "target_kind": "SchemaTest",
            "alias": "schematest-schema-test",
            "origin": "schematest.example",
            "storage": {"type": "yaml", "container": "schema-tests"},
        },
    }


def test_schema_is_valid_draft_2020_12():
    import jsonschema

    schema = kind_definition_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    jsonschema.Draft202012Validator.check_schema(schema)


def test_packaged_copy_is_byte_identical_to_published_copy():
    """The docs/schemas copy is the canonical published contract; the
    package-data copy is what the runtime loads. Edit one → copy to the
    other byte-for-byte (same rule as the parity-critical descriptors)."""
    if not _PUBLISHED.exists():
        pytest.skip(
            "docs/schemas/ not present (extracted-repo layout) — the "
            "packaged copy is the runtime source of truth there"
        )
    pkg = hashlib.sha256(_PACKAGED.read_bytes()).hexdigest()
    pub = hashlib.sha256(_PUBLISHED.read_bytes()).hexdigest()
    assert pkg == pub, (
        "kind-definition.schema.json diverged between the packaged runtime "
        "copy (dna/kernel/schemas/) and the published copy "
        "(docs/schemas/) — copy byte-for-byte"
    )


def test_every_repo_descriptor_validates():
    """Both validators (JSON Schema backstop + hand-rolled from_raw) accept
    every real descriptor in the repo. Positive control: the corpus must
    not be empty (an empty glob would pass vacuously)."""
    descriptors = _repo_descriptors()
    assert len(descriptors) >= 1, "no descriptors found — glob broke?"
    for path, raw in descriptors:
        validate_kind_definition(raw)          # schema
        TypedKindDefinition.from_raw(raw)      # hand-rolled + schema wired in


def test_from_raw_accepts_minimal_valid_descriptor():
    typed = TypedKindDefinition.from_raw(_minimal_valid())
    assert typed.spec.alias == "schematest-schema-test"


def test_from_raw_rejects_typoed_spec_field():
    """The class of bug the schema exists for: a typo'd optional field
    (`grph_style`) used to be SILENTLY ignored by the hand-rolled
    checks — the author thought they styled their Kind; nothing
    happened. Now it's a loud, path-qualified error."""
    raw = _minimal_valid()
    raw["spec"]["grph_style"] = {"fill": "#000"}
    with pytest.raises(ValueError, match="grph_style"):
        TypedKindDefinition.from_raw(raw)


def test_from_raw_rejects_wrong_type():
    raw = _minimal_valid()
    raw["spec"]["embed"] = "body"  # must be an array of field names
    with pytest.raises(ValueError, match=r"\$\.spec\.embed"):
        TypedKindDefinition.from_raw(raw)


def test_schema_backstop_catches_what_hand_rolled_misses():
    """Direct positive control on validate_kind_definition itself —
    independent of from_raw wiring."""
    raw = _minimal_valid()
    raw["spec"]["storage"] = {"type": "bundle", "container": "xs"}  # no marker
    with pytest.raises(ValueError, match="marker"):
        validate_kind_definition(raw)


def test_hand_rolled_didactic_message_still_wins():
    """The hand-rolled checks run FIRST: their messages are the didactic
    front line; the schema is the backstop. A missing required field
    must surface the hand-rolled wording, not a jsonschema dump."""
    raw = _minimal_valid()
    del raw["spec"]["alias"]
    with pytest.raises(ValueError, match="missing required fields: alias"):
        TypedKindDefinition.from_raw(raw)


def test_volatile_stamp_fields_stay_accepted():
    """Write-stamped volatile spec fields (KindBase.VOLATILE_SPEC_FIELDS)
    must not fail a reload of a stamped document."""
    raw = _minimal_valid()
    raw["spec"]["updated_at"] = "2026-07-08T00:00:00"
    raw["spec"]["created_at"] = "2026-07-08T00:00:00"
    validate_kind_definition(raw)


def test_ui_keys_derive_from_studio_ui_metadata():
    """spec.ui is strict on both validators; the schema's allowed key set
    must BE StudioUIMetadata's dataclass fields (single source of truth,
    D1) — adding a field to the dataclass without updating the schema
    turns this red."""
    from dna.kernel.studio_ui import StudioUIMetadata

    schema = kind_definition_schema()
    ui = schema["properties"]["spec"]["properties"]["ui"]
    assert ui["additionalProperties"] is False
    assert set(ui["properties"]) == set(StudioUIMetadata.__dataclass_fields__)


def test_spec_properties_cover_the_dataclass_surface():
    """Every user-facing KindDefinitionSpec dataclass field appears in the
    schema (and vice versa, modulo the volatile stamps). Internal-only
    fields (tenant_scope_declared) and hand-rolled aliases that are NOT
    dataclass fields are the documented exceptions."""
    import dataclasses

    from dna.kernel.models import KindDefinitionSpec

    schema = kind_definition_schema()
    schema_keys = set(schema["properties"]["spec"]["properties"]) - _VOLATILE
    dataclass_keys = {
        f.name for f in dataclasses.fields(KindDefinitionSpec)
    } - {"tenant_scope_declared"}  # internal, never authored
    assert schema_keys == dataclass_keys, (
        f"schema-only: {sorted(schema_keys - dataclass_keys)} · "
        f"dataclass-only: {sorted(dataclass_keys - schema_keys)}"
    )


def test_registration_funnel_still_warns_and_skips_per_scope():
    """Contract preservation: a per-scope KindDefinition that fails the
    (now schema-backed) parse is warn+skipped — it never raises out of
    register_kind_definitions (per-scope docs never take a boot down)."""
    from dna.kernel import Kernel

    k = Kernel.auto()
    bad = copy.deepcopy(_minimal_valid())
    bad["spec"]["grph_style"] = {"fill": "#000"}
    # Must not raise:
    k._register_kind_definitions([bad])
    key = ("schematest.example/v1", "SchemaTest")
    assert key not in k._kinds, "invalid descriptor must be skipped"
