"""Tests for EvidenceExtension — Evidence + EvidencePolicy kinds.

F3 lote-3: EvidenceKind (a classe) foi extinta — o kind é sintetizado de
kinds/evidence.kind.yaml; os asserts leem do PORT registrado pelo funil real
(deep equivalence: test_lote3_descriptor_equivalence.py). O parse do port
opera sobre o ENVELOPE ({apiVersion, kind, metadata, spec}) — a forma que o
kernel sempre passa; o aceite de dicts flat era um acessório da classe.
"""
from dna.extensions.evidence import (
    EvidencePolicyKind,
    EvidenceExtension,
)
from dna.kernel import Kernel


def _env(spec):
    return {"apiVersion": "github.com/ruinosus/dna/evidence/v1", "kind": "Evidence",
            "metadata": {"name": "ev-1"}, "spec": spec}


# ─── Evidence (descriptor-backed port) ───────────────────────────────

class TestEvidenceKind:
    def setup_method(self):
        k = Kernel()
        k.load(EvidenceExtension())
        self.kind = k.kind_port_for("Evidence")
        assert self.kind is not None

    def test_alias(self):
        assert self.kind.alias == "evidence-evidence"

    def test_api_version(self):
        assert self.kind.api_version == "github.com/ruinosus/dna/evidence/v1"

    def test_storage_container(self):
        assert self.kind.storage.container == "evidence"

    def test_graph_style(self):
        assert self.kind.graph_style["fill"] == "#059669"

    def test_schema_required_fields(self):
        schema = self.kind.schema()
        # s-evidence-schema-reconciliation: only event_type is present in ALL
        # 361 real docs — the gaia-event shape (64 docs) has NO sha256/captured_at.
        assert set(schema["required"]) == {"event_type"}

    def test_schema_event_type_enum(self):
        schema = self.kind.schema()
        enum_vals = schema["properties"]["event_type"]["enum"]
        assert "document_created" in enum_vals
        assert "eval_run_completed" in enum_vals
        assert "custom" in enum_vals

    def test_schema_event_type_enum_includes_gaia(self):
        # The 64 gaia-shape docs use gaia.* event types — all must be accepted.
        enum_vals = self.kind.schema()["properties"]["event_type"]["enum"]
        for ev in ("gaia.assessment.started", "gaia.assessment.completed",
                   "gaia.assessment.failed", "gaia.pillar.completed",
                   "gaia.pillar.threshold_breach", "gaia.report.issued"):
            assert ev in enum_vals, ev

    def test_schema_declares_gaia_shape_props(self):
        props = self.kind.schema()["properties"]
        assert props["payload"]["type"] == "object"
        assert props["source_kind"]["type"] == "string"
        assert props["source_name"]["type"] == "string"
        assert props["created_at"]["format"] == "date-time"

    def test_schema_sha256(self):
        schema = self.kind.schema()
        assert schema["properties"]["sha256"]["type"] == "string"

    def test_schema_captured_at(self):
        schema = self.kind.schema()
        assert schema["properties"]["captured_at"]["format"] == "date-time"

    def test_schema_snapshot(self):
        schema = self.kind.schema()
        assert schema["properties"]["snapshot"]["type"] == "object"
        assert schema["properties"]["snapshot"]["additionalProperties"] is True

    def test_parse_returns_raw(self):
        raw = _env({"event_type": "custom", "sha256": "abc",
                    "captured_at": "2026-01-01T00:00:00Z"})
        assert self.kind.parse(raw) is raw

    # ── s-evidence-schema-reconciliation: o port valida ambas as shapes ──

    def test_parse_accepts_provenance_shape(self):
        # shape #1 (kernel evidence_capture) — sha256 + captured_at.
        raw = _env({"event_type": "document_created", "sha256": "deadbeef",
                    "captured_at": "2026-06-07T00:00:00Z", "document_ref": "Story/s-x",
                    "suite": "default"})
        assert self.kind.parse(raw) is raw  # validates, no raise

    def test_parse_accepts_gaia_event_shape(self):
        # shape #2 (gaia worker) — NO sha256/captured_at; gaia.* + payload.
        raw = _env({"event_type": "gaia.pillar.completed", "created_at": "2026-06-07T00:00:00Z",
                    "payload": {"score": 0.9}, "source_kind": "Assessment",
                    "source_name": "asmt-1"})
        assert self.kind.parse(raw) is raw  # the 64 docs that used to fail

    def test_parse_rejects_missing_event_type(self):
        import pytest
        with pytest.raises(ValueError, match="event_type"):
            self.kind.parse(_env({"sha256": "abc", "captured_at": "2026-06-07T00:00:00Z"}))

    def test_parse_rejects_unknown_event_type(self):
        import pytest
        with pytest.raises(ValueError, match="event_type|enum"):
            self.kind.parse(_env({"event_type": "not.a.real.event"}))

    def test_is_not_root(self):
        assert self.kind.is_root is False

    def test_is_not_prompt_target(self):
        assert self.kind.is_prompt_target is False


# ─── EvidencePolicyKind ──────────────────────────────────────────────

class TestEvidencePolicyKind:
    def setup_method(self):
        self.kind = EvidencePolicyKind()

    def test_alias(self):
        assert self.kind.alias == "evidence-policy"

    def test_api_version(self):
        assert self.kind.api_version == "github.com/ruinosus/dna/evidence/v1"

    def test_storage_container(self):
        assert self.kind.storage.container == "evidence-policies"

    def test_graph_style(self):
        assert self.kind.graph_style["fill"] == "#0891B2"

    def test_schema_required_fields(self):
        schema = self.kind.schema()
        assert schema["required"] == ["events"]

    def test_schema_events_is_array(self):
        schema = self.kind.schema()
        assert schema["properties"]["events"]["type"] == "array"

    def test_schema_auto_capture_default(self):
        schema = self.kind.schema()
        assert schema["properties"]["auto_capture"]["default"] is True

    def test_schema_retention_days_default(self):
        schema = self.kind.schema()
        assert schema["properties"]["retention_days"]["default"] == 365

    def test_parse_returns_raw(self):
        raw = {"events": ["eval_run_completed"]}
        assert self.kind.parse(raw) is raw


# ─── EvidenceExtension ───────────────────────────────────────────────

class TestEvidenceExtension:
    def test_registers_both_kinds(self):
        k = Kernel()
        k.load(EvidenceExtension())
        assert k.kind_port_for("Evidence") is not None
        assert k.kind_port_for("EvidencePolicy") is not None

    def test_registers_post_save_hook(self):
        hooks = []
        ext = EvidenceExtension()
        ext.register(type("FakeKernel", (), {
            "kind": lambda self, k: None,
            "kind_from_descriptor": lambda self, raw: None,
            "on": lambda self, hook, fn: hooks.append((hook, fn)),
        })())
        assert len(hooks) == 1
        assert hooks[0][0] == "post_save"
        assert callable(hooks[0][1])

    def test_extension_metadata(self):
        ext = EvidenceExtension()
        assert ext.name == "evidence"
        assert ext.version == "1.0.0"
