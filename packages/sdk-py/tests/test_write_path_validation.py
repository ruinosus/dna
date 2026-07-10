"""Generic write-path spec↔schema validation (s-write-path-validation, i-008).

The kernel used to validate Kind schemas only at SCAN/read (the fail-soft
``parse_error`` channel) — ``write_document`` would happily persist a
shape-broken spec that exploded later, far from the author. Found live on
the Automation work (#25), which patched it LOCALLY with a write guard;
these tests pin the GENERALIZED mechanism: every ``write_document``
validates the spec against the Kind's declared ``schema()``.

Pinned contract:
- invalid spec for a schema-bearing Kind → ``SpecValidationError`` veto,
  nothing persisted;
- Kinds without a schema stay permissive (opt-in by data, as always);
- the error is didactic (field, violation, ``dna kind show <Kind>`` hint —
  the install #26 pattern);
- ``DNA_WRITE_VALIDATION=warn`` persists + logs; ``off`` skips;
- ``spec_defaults`` (descriptor D5) fill before validation — a doc that
  parses clean also writes clean;
- ordering: the step runs AFTER the ``pre_save`` veto hooks, so Kind-owned
  cures (the Automation YAML-1.1 ``on:`` heal) land before the shape check;
- red→green on the real i-008 shapes (Automation, EvalCase).

Evidence for the ENFORCE default (recorded on the Story): the full sdk-py
suite ran with enforce ON — 2 failures out of 2925, both legitimately
shape-broken fixtures (now fixed), zero legitimate writes vetoed.
"""
from __future__ import annotations

import logging

import pytest

from dna.kernel import Kernel
from dna.kernel.protocols import SpecValidationError
from tests.test_kernel_invalidate_modes import _FakeWritableSource

_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"
_EVAL_API = "github.com/ruinosus/dna/eval/v1"
_AUTOMATION_API = "github.com/ruinosus/dna/automation/v1"


def _raw(api: str, kind: str, name: str, spec: dict) -> dict:
    return {"apiVersion": api, "kind": kind,
            "metadata": {"name": name}, "spec": spec}


def _valid_lesson(name: str = "rem-1") -> dict:
    return _raw(_SDLC_API, "LessonLearned", name, {
        "area": "Feature/write-path",
        "surface_when": ["feature_touched"],
        "source_refs": ["s-write-path-validation"],
        "affect": "triumph",
        "affect_reason": "write-path validation shipped with 2/2925 evidence",
        "summary": "validate at write, not only at scan",
    })


@pytest.fixture()
def source() -> _FakeWritableSource:
    return _FakeWritableSource()


@pytest.fixture()
def kernel(source) -> Kernel:
    k = Kernel.auto()
    k.source(source)
    return k


# --- enforce (the default): invalid vetoed, nothing persisted -------------------


@pytest.mark.asyncio
async def test_invalid_spec_is_vetoed_and_not_persisted(kernel, source):
    bad = _valid_lesson("rem-bad")
    bad["spec"]["confidence_score"] = "faint"  # schema: type number (the i-008 class)
    with pytest.raises(SpecValidationError):
        await kernel.write_document("s", "LessonLearned", "rem-bad", bad)
    assert source.save_calls == [], "a vetoed write must not reach the adapter"


@pytest.mark.asyncio
async def test_missing_required_field_is_vetoed(kernel, source):
    skeletal = _raw(_SDLC_API, "LessonLearned", "rem-skel", {"summary": "no area"})
    with pytest.raises(SpecValidationError, match="'area' is a required property"):
        await kernel.write_document("s", "LessonLearned", "rem-skel", skeletal)
    assert source.save_calls == []


@pytest.mark.asyncio
async def test_valid_spec_persists(kernel, source):
    await kernel.write_document("s", "LessonLearned", "rem-ok", _valid_lesson("rem-ok"))
    assert len(source.save_calls) == 1


@pytest.mark.asyncio
async def test_error_is_didactic(kernel):
    bad = _valid_lesson("rem-bad")
    bad["spec"]["confidence_score"] = "faint"
    with pytest.raises(SpecValidationError) as ei:
        await kernel.write_document("s", "LessonLearned", "rem-bad", bad)
    msg = str(ei.value)
    # The install #26 pattern: WHERE (field), WHAT (violation), HOW (kind show).
    assert "spec.confidence_score" in msg
    assert "not of type 'number'" in msg
    assert "dna kind show LessonLearned" in msg
    assert "s/LessonLearned/rem-bad" in msg


@pytest.mark.asyncio
async def test_veto_is_a_value_error_for_backcompat(kernel):
    # Pre_save guard convention: write-path vetoes read as ValueError.
    bad = _raw(_SDLC_API, "LessonLearned", "x", {"summary": "no area"})
    with pytest.raises(ValueError):
        await kernel.write_document("s", "LessonLearned", "x", bad)


# --- permissive paths ------------------------------------------------------------


@pytest.mark.asyncio
async def test_kind_without_schema_passes(kernel, source):
    # Unknown Kind → no port → no schema → permissive (opt-in by data).
    await kernel.write_document(
        "s", "TotallyUnregisteredKind", "n",
        _raw("example.com/x/v1", "TotallyUnregisteredKind", "n",
             {"anything": ["goes", 1, None]}),
    )
    assert len(source.save_calls) == 1


@pytest.mark.asyncio
async def test_registered_schema_less_kind_passes(kernel, source):
    # A registered port whose schema() is None stays permissive.
    class _NoSchemaPort:
        api_version = "example.com/noschema/v1"
        kind = "NoSchema"
        alias = "example-no-schema"
        model = dict
        plane = "record"

        def schema(self):
            return None

        def parse(self, raw):
            return raw

    kernel._kinds[(_NoSchemaPort.api_version, "NoSchema")] = _NoSchemaPort()
    await kernel.write_document(
        "s", "NoSchema", "n",
        _raw(_NoSchemaPort.api_version, "NoSchema", "n", {"free": "form"}),
    )
    assert len(source.save_calls) == 1


@pytest.mark.asyncio
async def test_spec_defaults_fill_before_validation(kernel, source):
    # Descriptor D5: a required field satisfied by the descriptor's own
    # spec_defaults must NOT be vetoed — validate what parse validates.
    port = kernel.kind_from_descriptor({
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "wpv-defaulted"},
        "spec": {
            "target_api_version": "example.com/wpv/v1",
            "target_kind": "WpvDefaulted",
            "alias": "example-wpv-defaulted",
            "origin": "example.com/wpv",
            "plane": "record",
            "storage": {"type": "yaml", "container": "wpv-defaulted"},
            "spec_defaults": {"mode": "auto"},
            "schema": {
                "type": "object",
                "required": ["mode"],
                "properties": {"mode": {"type": "string"}},
            },
        },
    })
    assert port is not None
    await kernel.write_document(
        "s", "WpvDefaulted", "d",
        _raw("example.com/wpv/v1", "WpvDefaulted", "d", {}),  # mode comes from defaults
    )
    assert len(source.save_calls) == 1


# --- mode knob (DNA_WRITE_VALIDATION) ---------------------------------------------


@pytest.mark.asyncio
async def test_warn_mode_persists_and_logs(kernel, source, monkeypatch, caplog):
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "warn")
    bad = _raw(_SDLC_API, "LessonLearned", "rem-warn", {"summary": "no area"})
    with caplog.at_level(logging.WARNING, logger="dna.kernel"):
        await kernel.write_document("s", "LessonLearned", "rem-warn", bad)
    assert len(source.save_calls) == 1
    assert any("schema validation failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_off_mode_skips_validation(kernel, source, monkeypatch):
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    bad = _raw(_SDLC_API, "LessonLearned", "rem-off", {"summary": "no area"})
    await kernel.write_document("s", "LessonLearned", "rem-off", bad)
    assert len(source.save_calls) == 1


@pytest.mark.asyncio
async def test_unknown_mode_falls_back_to_enforce(kernel, monkeypatch):
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "bananas")
    bad = _raw(_SDLC_API, "LessonLearned", "rem-x", {"summary": "no area"})
    with pytest.raises(SpecValidationError):
        await kernel.write_document("s", "LessonLearned", "rem-x", bad)


# --- red→green: the real i-008 shapes ---------------------------------------------


@pytest.mark.asyncio
async def test_i008_automation_shape_veto_now_generic(kernel, source):
    # The exact gap that spawned i-008: before the Automation write guard,
    # this doc PERSISTED and exploded at scan. The guard fixed it locally;
    # the generic step now owns it (the guard no longer runs port.parse).
    with pytest.raises(SpecValidationError, match="'cron' is a required property"):
        await kernel.write_document(
            "s", "Automation", "no-cron",
            _raw(_AUTOMATION_API, "Automation", "no-cron",
                 {"on": {"type": "cron"},
                  "runner": {"kind": "agent", "ref": "x"}}),
        )
    assert source.save_calls == []


@pytest.mark.asyncio
async def test_automation_yaml11_heal_runs_before_generic_validation(kernel, source):
    # Ordering guarantee: the guard's YAML-1.1 heal (pre_save veto hook)
    # mutates raw BEFORE the generic step validates — a bare `on:` doc
    # (PyYAML reads the key as boolean True) is healed, then passes.
    raw = _raw(_AUTOMATION_API, "Automation", "healed",
               {True: {"type": "hook", "hook": "post_save"},
                "runner": {"kind": "agent", "ref": "x"}})
    await kernel.write_document("s", "Automation", "healed", raw)
    assert "on" in raw["spec"] and True not in raw["spec"]
    assert len(source.save_calls) == 1


@pytest.mark.asyncio
async def test_evalcase_wrong_checks_shape_vetoed(kernel, source):
    # EvalCase.checks must be a non-empty array — a dict (the classic
    # hand-authoring slip) used to persist and break the runner later.
    with pytest.raises(SpecValidationError, match="spec.checks"):
        await kernel.write_document(
            "s", "EvalCase", "bad-checks",
            _raw(_EVAL_API, "EvalCase", "bad-checks",
                 {"checks": {"type": "contains", "value": "x"}}),
        )
    assert source.save_calls == []
    with pytest.raises(SpecValidationError, match="spec.checks"):
        await kernel.write_document(
            "s", "EvalCase", "empty-checks",
            _raw(_EVAL_API, "EvalCase", "empty-checks", {"checks": []}),
        )


@pytest.mark.asyncio
async def test_evalcase_valid_persists(kernel, source):
    await kernel.write_document(
        "s", "EvalCase", "ok",
        _raw(_EVAL_API, "EvalCase", "ok",
             {"checks": [{"type": "contains", "value": "hello"}]}),
    )
    assert len(source.save_calls) == 1
