"""i-144 — WorkflowEvent descriptor accepts the pre-redesign (legacy) journey
shape so the ~1574 historical entries stop spamming parse errors on load.

The journey ledger predates the phase+ref model: old entries use
artifact_kind/artifact_name (instead of ``ref``), auto_emitted_by (instead of
``actor``), timestamp (instead of ``created_at``), feature_ref/epic_ref (instead
of ``parent_ref``). The descriptor now keeps those OPTIONAL under the strict
additionalProperties:false, and ``ref`` is no longer required — so both shapes
validate. NEW entries still use the canonical fields.
"""
from __future__ import annotations

import jsonschema
import pytest

from dna.kernel import Kernel


def _schema():
    k = Kernel.auto()
    port = next(kp for kp in k.kind_ports()
                if getattr(kp, "kind", "") == "WorkflowEvent")
    return port.schema()


def test_legacy_shape_validates():
    legacy = {
        "phase": "discover", "methodology": "ad-hoc",
        "timestamp": "2026-05-21T17:14:35+00:00", "auto_emitted_by": "sdlc",
        "artifact_kind": "Story", "artifact_name": "s-foo", "summary": "...",
        "decision_text": "d", "tags": ["t"], "rationale": "r", "owner": "o",
        "feature_ref": "f-x", "epic_ref": "e-y", "decisions": "dd",
    }
    jsonschema.validate(legacy, _schema())   # must not raise


def test_new_shape_still_validates():
    jsonschema.validate({"phase": "build", "ref": "Story/s-foo"}, _schema())


def test_ref_no_longer_required_but_phase_is():
    schema = _schema()
    assert schema["required"] == ["phase"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"ref": "Story/x"}, schema)   # missing phase


def test_still_strict_additional_properties_false():
    # the strict-anchor contract (test_strict_schema_lint) is preserved
    schema = _schema()
    assert schema["additionalProperties"] is False
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"phase": "build", "ref": "Story/x", "totally_unknown": 1}, schema)
