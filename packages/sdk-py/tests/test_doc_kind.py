"""Doc Kind (s-tier-a-doc-kind) — builtin descriptor registration + contract.

The Doc Kind is a Tier A port from the internal SDK's doc extension,
expressed as a pure descriptor (``dna/extensions/doc/kinds/doc.kind.yaml``,
no class — the F3 archetype for a record Kind of data). These tests pin
the registration surface the ``dna docs`` CLI group depends on, plus the
subset decisions (strict schema, Diátaxis enum, record plane, permissive
tenancy).
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel

_KEY = ("github.com/ruinosus/dna/doc/v1", "Doc")


@pytest.fixture(scope="module")
def doc_port():
    k = Kernel.auto()
    port = k._kinds.get(_KEY)
    assert port is not None, "Doc must register from the builtin descriptor"
    return port


def test_identity_and_plane(doc_port):
    assert doc_port.alias == "dna-doc"
    assert doc_port.plane == "record"
    assert getattr(doc_port, "__declarative__", False), (
        "Doc is the archetypical record-Kind-as-data — descriptor, not class"
    )
    assert getattr(doc_port, "__builtin_descriptor__", False)
    assert doc_port.is_prompt_target is False


def test_bundle_storage_shape(doc_port):
    sd = doc_port.storage
    assert sd.container == "docs"
    assert sd.marker == "DOC.md"
    assert sd.body_field == "body"


def test_schema_is_strict_with_the_cli_fields(doc_port):
    schema = doc_port.schema()
    assert schema["additionalProperties"] is False
    props = set(schema["properties"])
    # exactly what `dna docs list/show` consumes + the retained upstream core
    assert {"body", "icon", "order", "locale", "kind_of", "category"} <= props
    assert {"subtitle", "summary", "enabled", "tags"} <= props


def test_parse_applies_defaults_and_validates(doc_port):
    parsed = doc_port.parse({
        "apiVersion": _KEY[0],
        "kind": "Doc",
        "metadata": {"name": "welcome"},
        "spec": {"body": "# hi"},
    })
    spec = parsed["spec"]
    # spec_defaults mirror the upstream dataclass defaults
    assert spec["locale"] == "pt-BR"
    assert spec["order"] == 999
    assert spec["enabled"] is True


def test_parse_rejects_non_diataxis_kind_of(doc_port):
    with pytest.raises(ValueError, match="kind_of"):
        doc_port.parse({
            "metadata": {"name": "bad"},
            "spec": {"body": "x", "kind_of": "guide"},
        })


def test_describe_projects_subtitle(doc_port):
    class _Doc:
        spec = {"subtitle": "One-liner"}

    assert doc_port.describe(_Doc()) == "One-liner"
    assert doc_port.description_fallback_field == "subtitle"


def test_tenancy_is_permissive(doc_port):
    # tenant_scope deliberately undeclared: base doc + per-tenant overlay.
    # (Inheritable-default content must never be TENANTED.)
    assert getattr(doc_port, "scope", None) is None
