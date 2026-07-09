"""Automation Kind (s-tier-a-automation) — descriptor registration,
write-time validation and the host query helpers.

Tier A port from the internal SDK's automation extension: one Automation
doc declares WHEN background work fires (``on: {type: cron|hook|tool}``)
and WHAT runs (``runner`` + directive). The SDK owns declaration +
validation + listing; EXECUTION is the host's (extension point in
docs/concepts/builtin-kinds.md). These tests pin:

- the descriptor registration surface (alias, plane, permissive tenancy —
  Automation is in ``DEFAULT_INHERITABLE_KINDS_V1``, so the máxima
  "inheritable ⇒ never TENANTED" applies);
- the two validation layers: JSON Schema shape (conditional per-trigger
  requireds) at parse, and the ``pre_save`` veto guard for what schema
  cannot say (cron grammar, hook-name vocabulary);
- the query helpers a host executor reads (``automations_for`` /
  ``trigger_key``).
"""
from __future__ import annotations

import pytest

from dna.extensions.automation import (
    TRIGGER_TYPES,
    automations_for,
    trigger_key,
    validate_cron_expression,
)
from dna.kernel import Kernel
from dna.kernel.hooks import KNOWN_HOOK_NAMES
from dna.kernel.resolver import DEFAULT_INHERITABLE_KINDS_V1
from tests.test_kernel_invalidate_modes import _FakeWritableSource

_KEY = ("github.com/ruinosus/dna/automation/v1", "Automation")


def _raw(spec: dict, name: str = "t") -> dict:
    return {
        "apiVersion": _KEY[0],
        "kind": "Automation",
        "metadata": {"name": name},
        "spec": spec,
    }


def _cron_spec(**over) -> dict:
    return {
        "on": {"type": "cron", "cron": "0 10 * * 1,3,5"},
        "runner": {"kind": "agent", "ref": "reporter"},
        **over,
    }


@pytest.fixture(scope="module")
def port():
    k = Kernel.auto()
    p = k._kinds.get(_KEY)
    assert p is not None, "Automation must register from the builtin descriptor"
    return p


@pytest.fixture()
def kernel() -> Kernel:
    k = Kernel.auto()
    k.source(_FakeWritableSource())
    return k


# --- registration surface -----------------------------------------------------


def test_identity_and_plane(port):
    assert port.alias == "dna-automation"
    assert port.plane == "record"
    assert getattr(port, "__declarative__", False), (
        "Automation is a record Kind — descriptor, not class (F3 ratchet)"
    )
    assert getattr(port, "__builtin_descriptor__", False)
    assert port.is_prompt_target is False
    assert port.storage.container == "automations"


def test_tenancy_is_permissive_because_inheritable(port):
    # Automation is an inheritable `_lib` default — the máxima "inheritable
    # ⇒ never TENANTED" demands a writable base: tenant_scope undeclared.
    assert "Automation" in DEFAULT_INHERITABLE_KINDS_V1
    assert getattr(port, "scope", None) is None


def test_trigger_types_mirror_the_descriptor_enum(port):
    schema_enum = port.schema()["properties"]["on"]["properties"]["type"]["enum"]
    assert tuple(schema_enum) == TRIGGER_TYPES == ("cron", "hook", "tool")


# --- layer 1: JSON Schema shape (strict + conditional requireds) ---------------


def test_schema_is_strict(port):
    schema = port.schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["on"]["additionalProperties"] is False
    assert schema["properties"]["runner"]["additionalProperties"] is False


def test_parse_valid_docs_per_trigger(port):
    port.parse(_raw(_cron_spec()))
    port.parse(_raw({
        "on": {"type": "hook", "hook": "post_save"},
        "runner": {"kind": "agent", "ref": "auditor"},
    }))
    port.parse(_raw({
        "on": {
            "type": "tool",
            "tool_name": "deep_research_async",
            "input_schema": [{"name": "topic"}],
            "primary_input": "topic",
        },
        "runner": {"kind": "agent", "ref": "researcher"},
        "agent_directive": "Research {topic} and synthesize.",
    }))


@pytest.mark.parametrize("spec, missing", [
    ({"on": {"type": "cron"},
      "runner": {"kind": "agent", "ref": "x"}}, "cron"),
    ({"on": {"type": "hook"},
      "runner": {"kind": "agent", "ref": "x"}}, "hook"),
    ({"on": {"type": "tool"},
      "runner": {"kind": "agent", "ref": "x"}}, "tool_name"),
])
def test_parse_rejects_trigger_without_its_field(port, spec, missing):
    with pytest.raises(ValueError, match=missing):
        port.parse(_raw(spec))


def test_parse_rejects_unknown_runner_kind(port):
    # upstream had an `engine` runner; DNA runners are the real Kinds
    # Agent / Tool only (honest subset).
    with pytest.raises(ValueError, match="engine"):
        port.parse(_raw({
            "on": {"type": "cron", "cron": "0 3 * * *"},
            "runner": {"kind": "engine", "ref": "dreamer"},
        }))


def test_parse_rejects_runner_without_ref(port):
    with pytest.raises(ValueError, match="ref"):
        port.parse(_raw({
            "on": {"type": "cron", "cron": "0 3 * * *"},
            "runner": {"kind": "agent"},
        }))


def test_parse_fills_enabled_default(port):
    parsed = port.parse(_raw(_cron_spec()))
    assert parsed["spec"]["enabled"] is True


# --- layer 2: the pre_save veto guard (semantics schema cannot express) --------


@pytest.mark.parametrize("expr", [
    "0 10 * * 1,3,5",
    "*/15 * * * *",
    "0-30/5 2 1-15 * *",
    "59 23 31 12 7",
    "0 0 1 1 0",
])
def test_cron_validator_accepts_standard_grammar(expr):
    validate_cron_expression(expr)  # must not raise


@pytest.mark.parametrize("expr, detail", [
    ("* * * *", "expected 5 fields"),
    ("* * * * * *", "expected 5 fields"),
    ("60 * * * *", "out of range"),
    ("* 24 * * *", "out of range"),
    ("* * 0 * *", "out of range"),
    ("* * * 13 *", "out of range"),
    ("* * * * 8", "out of range"),
    ("a * * * *", "not a number"),
    ("*/0 * * * *", "positive integer"),
    ("/5 * * * *", "step without a base"),
    ("5-1 * * * *", "inverted range"),
    ("1,,2 * * * *", "empty list item"),
    ("@daily", "expected 5 fields"),
    ("0 10 * * MON", "not a number"),  # name aliases: documented non-goal
])
def test_cron_validator_rejects_bad_grammar(expr, detail):
    with pytest.raises(ValueError, match=detail):
        validate_cron_expression(expr)


@pytest.mark.asyncio
async def test_write_vetoes_shape_broken_doc(kernel):
    # The kernel only schema-validates at scan/read; the guard runs the
    # descriptor's parse at WRITE so a shape-broken doc never persists
    # (found live: a broken doc wrote fine and exploded at scan time).
    with pytest.raises(ValueError, match="'cron' is a required property"):
        await kernel.write_document(
            "s", "Automation", "no-cron",
            _raw({"on": {"type": "cron"},
                  "runner": {"kind": "agent", "ref": "x"}}, "no-cron"),
        )


@pytest.mark.asyncio
async def test_write_heals_pyyaml_on_boolean_key(kernel):
    # YAML 1.1: PyYAML reads a bare `on:` key as boolean True — the doc
    # would silently lose its trigger. The guard heals the key in place
    # (veto-channel mutation contract), THEN validates it.
    raw = _raw({True: {"type": "hook", "hook": "post_save"},
                "runner": {"kind": "agent", "ref": "x"}}, "healed")
    await kernel.write_document("s", "Automation", "healed", raw)
    assert "on" in raw["spec"] and True not in raw["spec"]
    # ... and a healed-but-invalid doc is still vetoed (normalize BEFORE
    # validate, so the bad value cannot hide behind the boolean key).
    with pytest.raises(ValueError, match="invalid cron expression"):
        await kernel.write_document(
            "s", "Automation", "healed-bad",
            _raw({True: {"type": "cron", "cron": "61 * * * *"},
                  "runner": {"kind": "agent", "ref": "x"}}, "healed-bad"),
        )


@pytest.mark.asyncio
async def test_write_vetoes_schema_valid_but_bad_cron(kernel):
    # '61 * * * *' is a perfectly valid STRING for the schema — only the
    # guard's grammar parse catches it.
    with pytest.raises(ValueError, match="invalid cron expression"):
        await kernel.write_document(
            "s", "Automation", "bad-cron",
            _raw({"on": {"type": "cron", "cron": "61 * * * *"},
                  "runner": {"kind": "agent", "ref": "x"}}, "bad-cron"),
        )


@pytest.mark.asyncio
async def test_write_vetoes_unknown_hook_name(kernel):
    # A typo'd hook would be declared, listed, and silently never fire —
    # the guard turns it into a loud veto listing the typed vocabulary.
    with pytest.raises(ValueError, match="not a kernel lifecycle hook"):
        await kernel.write_document(
            "s", "Automation", "bad-hook",
            _raw({"on": {"type": "hook", "hook": "pre_saev"},
                  "runner": {"kind": "agent", "ref": "x"}}, "bad-hook"),
        )


@pytest.mark.asyncio
async def test_write_accepts_every_known_hook_name(kernel):
    for hook in KNOWN_HOOK_NAMES:
        await kernel.write_document(
            "s", "Automation", f"on-{hook.replace('_', '-')}",
            _raw({"on": {"type": "hook", "hook": hook},
                  "runner": {"kind": "agent", "ref": "x"}}),
        )


@pytest.mark.asyncio
async def test_write_accepts_valid_cron(kernel):
    await kernel.write_document(
        "s", "Automation", "ok",
        _raw({"on": {"type": "cron", "cron": "*/15 0-6 * * 1-5"},
              "runner": {"kind": "tool", "ref": "sync-upstream"}}, "ok"),
    )


@pytest.mark.asyncio
async def test_guard_ignores_other_kinds(kernel):
    # A Genome (or any non-Automation doc) with a weird spec sails past.
    await kernel.write_document(
        "s", "Genome", "g",
        {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
         "metadata": {"name": "g"},
         "spec": {"on": {"type": "cron", "cron": "61 * * * *"}}},
    )


# --- query helpers (the host executor's read surface) --------------------------


class _FakeInstance:
    """Duck-typed ManifestInstance: just the blessed ``all`` the helpers use."""

    def __init__(self, docs):
        self._docs = docs

    def all(self, kind):
        return list(self._docs)


class _Doc:
    def __init__(self, name, spec):
        self.name = name
        self.spec = spec


def _fixture_instance():
    return _FakeInstance([
        _Doc("nightly", {"on": {"type": "cron", "cron": "0 3 * * *"},
                         "runner": {"kind": "agent", "ref": "reporter"}}),
        _Doc("paused", {"on": {"type": "cron", "cron": "0 4 * * *"},
                        "runner": {"kind": "agent", "ref": "reporter"},
                        "enabled": False}),
        _Doc("on-save", {"on": {"type": "hook", "hook": "post_save"},
                         "runner": {"kind": "tool", "ref": "indexer"}}),
        _Doc("research", {"on": {"type": "tool",
                                 "tool_name": "deep_research_async"},
                          "runner": {"kind": "agent", "ref": "researcher"}}),
    ])


def test_automations_for_filters_by_trigger_type():
    mi = _fixture_instance()
    assert [d.name for d in automations_for(mi, "cron")] == ["nightly"]
    assert [d.name for d in automations_for(mi, "hook")] == ["on-save"]
    assert [d.name for d in automations_for(mi, "tool")] == ["research"]


def test_automations_for_drops_disabled_by_default():
    mi = _fixture_instance()
    assert [d.name for d in automations_for(mi)] == [
        "nightly", "on-save", "research",
    ]
    assert [d.name for d in automations_for(mi, "cron", enabled_only=False)] == [
        "nightly", "paused",
    ]


def test_automations_for_rejects_unknown_trigger_type():
    with pytest.raises(ValueError, match="unknown trigger_type"):
        automations_for(_fixture_instance(), "event")


def test_trigger_key_per_trigger_type():
    docs = {d.name: d for d in _fixture_instance().all("Automation")}
    assert trigger_key(docs["nightly"]) == "0 3 * * *"
    assert trigger_key(docs["on-save"]) == "post_save"
    assert trigger_key(docs["research"]) == "deep_research_async"
    assert trigger_key(_Doc("empty", {})) is None


# --- projections (D2/D3 — what a listing shows the operator) -------------------


def test_summary_projection(port):
    doc = _Doc("nightly", {
        "on": {"type": "cron", "cron": "0 3 * * *"},
        "runner": {"kind": "agent", "ref": "reporter"},
        "enabled": True,
    })
    assert port.summary(doc) == {
        "on_type": "cron",
        "trigger": {"cron": "0 3 * * *"},
        "runner_kind": "agent",
        "runner_ref": "reporter",
        "enabled": True,
    }


def test_describe_projects_description(port):
    doc = _Doc("nightly", {"description": "nightly status report"})
    assert port.describe(doc) == "nightly status report"
    assert port.description_fallback_field == "description"
