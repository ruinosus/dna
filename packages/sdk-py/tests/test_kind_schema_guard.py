"""i-080 item 4 — a tenant's JSON Schema is validated AT AUTHOR TIME.

Before this guard ``spec.schema`` was only checked to be a dict
(``models.KindDefinitionSpec.from_raw``); ``Draft202012Validator.check_schema``
ran only on DNA's OWN descriptor meta-schema (``kinds/schema.py``). A tenant
could therefore store a schema that is not a schema, and every document of that
Kind failed later, per document, through the fail-soft ``parse_error`` channel —
a warning far from the author.

Two further hazards are covered here, both MEASURED rather than assumed (the
prior audit flagged them as plausible-but-unverified):

* remote ``$ref`` — jsonschema 4.26 does NOT fetch it (``referencing`` needs an
  explicit retrieve function), so it is not an SSRF today. It IS a crash: the
  raised ``_WrappedReferencingError`` is NOT a ``ValidationError``, so it
  escapes the write path's handler (``WritePipeline._validate_spec_schema``
  catches ``jsonschema.ValidationError`` only). Refused at author time.
* catastrophic ``pattern`` backtracking (ReDoS) — measured exponential:
  ``^(a+)+$`` against 26 'a's takes ~1.5s, and each extra character multiplies.
  The detectable shapes are refused at author time.
"""
from __future__ import annotations

import re
import time

import pytest

from dna.kernel.kinds.schema_guard import (
    SchemaGuardError,
    validate_authored_schema,
)


# ── the schema must actually be a schema ────────────────────────────────────


def test_malformed_schema_is_refused_at_author_time():
    with pytest.raises(SchemaGuardError) as e:
        validate_authored_schema(
            {"type": "object", "properties": {"x": {"type": "not-a-type"}}}
        )
    assert "not-a-type" in str(e.value)


def test_valid_schema_passes():
    validate_authored_schema({
        "type": "object",
        "additionalProperties": False,
        "required": ["title"],
        "properties": {
            "title": {"type": "string"},
            "amount": {"type": "number"},
            "host": {"type": "string", "pattern": r"^([a-z]+\.)+[a-z]+$"},
        },
    })


def test_empty_schema_is_permissive():
    validate_authored_schema({})
    validate_authored_schema(None)


# ── $ref must be a local fragment ───────────────────────────────────────────


@pytest.mark.parametrize("ref", [
    "http://169.254.169.254/latest/meta-data/",
    "https://example.com/schema.json",
    "file:///etc/passwd",
    "other.json#/$defs/Thing",
])
def test_non_local_ref_is_refused(ref):
    with pytest.raises(SchemaGuardError) as e:
        validate_authored_schema(
            {"type": "object", "properties": {"x": {"$ref": ref}}}
        )
    assert "$ref" in str(e.value)


def test_local_ref_is_allowed():
    validate_authored_schema({
        "type": "object",
        "$defs": {"Money": {"type": "number"}},
        "properties": {"amount": {"$ref": "#/$defs/Money"}},
    })


def test_a_remote_ref_would_escape_the_write_paths_handler():
    """The measurement behind the refusal: the error a remote $ref raises is
    NOT a ValidationError, so the write path would not catch it."""
    import jsonschema

    with pytest.raises(Exception) as e:
        jsonschema.validate(
            {"x": 1},
            {"type": "object", "properties": {"x": {"$ref": "http://127.0.0.1:9/e"}}},
        )
    assert not isinstance(e.value, jsonschema.ValidationError)


# ── pattern: catastrophic backtracking ──────────────────────────────────────


@pytest.mark.parametrize("pattern", [
    "^(a+)+$",            # nested unbounded quantifier
    "^(a*)*$",            # nested, inner nullable
    "^([a-z]+)*$",        # nested with a class
    "^(a|a?)+$",          # a nullable branch under an unbounded quantifier
    "^(a|aa)+$",          # ambiguous alternation: one branch prefixes the other
    "^(?:x+)+$",          # non-capturing groups are not an escape hatch
])
def test_catastrophic_patterns_are_refused(pattern):
    with pytest.raises(SchemaGuardError) as e:
        validate_authored_schema(
            {"type": "object", "properties": {"x": {"type": "string",
                                                    "pattern": pattern}}}
        )
    assert "pattern" in str(e.value)


@pytest.mark.parametrize("pattern", [
    r"^[a-z0-9-]+$",
    r"^(\d{4})-(\d{2})-(\d{2})$",
    r"^([a-z]+\.)+[a-z]+$",       # measured FAST — a mandatory literal separates
    r"^(?:[a-z]+@)+[a-z]+$",      # measured FAST — same reason
    r"^(foo|bar)+$",              # disjoint literal branches
])
def test_safe_patterns_are_allowed(pattern):
    validate_authored_schema(
        {"type": "object", "properties": {"x": {"type": "string",
                                                "pattern": pattern}}}
    )


def test_uncompilable_pattern_is_refused():
    with pytest.raises(SchemaGuardError) as e:
        validate_authored_schema(
            {"type": "object", "properties": {"x": {"pattern": "^(unclosed"}}}
        )
    assert "pattern" in str(e.value)


def test_absurdly_long_pattern_is_refused():
    with pytest.raises(SchemaGuardError) as e:
        validate_authored_schema(
            {"type": "object",
             "properties": {"x": {"pattern": "^(?:" + "a|" * 400 + "z)$"}}}
        )
    assert "pattern" in str(e.value)


def test_pattern_is_checked_everywhere_it_can_appear():
    for schema in (
        {"type": "string", "pattern": "^(a+)+$"},
        {"type": "object", "patternProperties": {"^(a+)+$": {"type": "string"}}},
        {"type": "object", "propertyNames": {"pattern": "^(a+)+$"}},
        {"type": "array", "items": {"type": "string", "pattern": "^(a+)+$"}},
        {"$defs": {"D": {"type": "string", "pattern": "^(a+)+$"}}},
    ):
        with pytest.raises(SchemaGuardError):
            validate_authored_schema(schema)


def test_the_refused_shape_is_actually_catastrophic():
    """Evidence, not folklore: the shape the guard refuses really is
    exponential in this interpreter."""
    rx = re.compile("^(a+)+$")
    t0 = time.perf_counter()
    rx.match("a" * 24 + "!")
    small = time.perf_counter() - t0
    t0 = time.perf_counter()
    rx.match("a" * 27 + "!")
    bigger = time.perf_counter() - t0
    assert bigger > small * 4, (small, bigger)


def test_a_property_named_pattern_is_not_mistaken_for_the_keyword():
    """DNA's own Plan Kind declares a property literally called ``pattern``. A
    blind walk read it as the ``pattern`` KEYWORD and refused every Plan."""
    validate_authored_schema({
        "type": "object",
        "properties": {
            "pattern": {"type": "object", "description": "the plan's pattern"},
            "$ref": {"type": "string"},
        },
    })


def test_instance_data_is_not_walked_as_schema():
    """``default`` / ``const`` / ``examples`` hold instance data, not schemas —
    a ``$ref``-shaped value there is a string, not a reference."""
    validate_authored_schema({
        "type": "object",
        "properties": {
            "x": {"type": "object", "default": {"$ref": "http://example.com"}},
            "y": {"const": {"pattern": "^(a+)+$"}},
        },
    })


def test_every_shipped_kind_schema_passes_the_guard():
    """Back-compat, proved rather than asserted: the guard is wired into the
    ONE ``KindDefinition`` parse path, so a builtin it refused would fail the
    boot."""
    from dna.kernel import Kernel

    k = Kernel.auto()
    ports = k.kind_ports()
    assert len(ports) >= 70
    for port in ports:
        try:
            schema = port.schema()
        except Exception:  # noqa: BLE001 — a Kind whose schema errors stays permissive
            continue
        validate_authored_schema(schema)


# ── the guard is WIRED, not merely available ────────────────────────────────


def _kinddef(schema):
    return {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "deal"},
        "spec": {
            "target_api_version": "acme.example/v1",
            "target_kind": "Deal",
            "alias": "acme-deal",
            "origin": "acme.example",
            "storage": {"type": "yaml", "container": "acme-deals"},
            "schema": schema,
        },
    }


def test_from_raw_refuses_a_malformed_authored_schema():
    from dna.kernel.models import TypedKindDefinition

    with pytest.raises(ValueError) as e:
        TypedKindDefinition.from_raw(
            _kinddef({"type": "object",
                      "properties": {"x": {"type": "not-a-type"}}})
        )
    assert "spec.schema" in str(e.value)


def test_from_raw_refuses_a_catastrophic_pattern():
    from dna.kernel.models import TypedKindDefinition

    with pytest.raises(ValueError) as e:
        TypedKindDefinition.from_raw(
            _kinddef({"type": "object",
                      "properties": {"x": {"type": "string",
                                           "pattern": "^(a+)+$"}}})
        )
    assert "pattern" in str(e.value)


def test_from_raw_refuses_a_remote_ref():
    from dna.kernel.models import TypedKindDefinition

    with pytest.raises(ValueError) as e:
        TypedKindDefinition.from_raw(
            _kinddef({"type": "object",
                      "properties": {"x": {"$ref": "https://example.com/s.json"}}})
        )
    assert "$ref" in str(e.value)


def test_from_raw_accepts_a_sane_authored_schema():
    from dna.kernel.models import TypedKindDefinition

    typed = TypedKindDefinition.from_raw(
        _kinddef({"type": "object", "required": ["title"],
                  "properties": {"title": {"type": "string"}}})
    )
    assert typed.spec.target_kind == "Deal"


def test_a_bad_authored_schema_only_warns_on_the_per_scope_funnel():
    """A tenant document never takes the boot down — the funnel's existing
    contract, unchanged by the guard."""
    from dna.kernel import Kernel

    k = Kernel()
    k._register_kind_definitions([_kinddef({"type": "not-a-type"})])
    assert ("acme.example/v1", "Deal") not in k._kinds
