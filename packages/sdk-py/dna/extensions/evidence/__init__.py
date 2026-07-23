"""EvidenceExtension — audit trail Kinds for the GAIA pipeline.

Registers 2 KindPorts:
  - Evidence       (evidence-evidence)  — immutable audit event record
  - EvidencePolicy (evidence-policy)    — controls which events are auto-captured

All use YAML storage with no custom reader/writer — the generic
machinery handles serialization. This makes evidence a cross-cutting
infrastructure concern (like Guardrail or Eval).
"""
from __future__ import annotations

from typing import Any

from dna.kernel.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost, StorageDescriptor
from dna.kernel.kinds.base import KindBase
# should_capture is generic policy-evaluation logic that now lives in the
# kernel (s-invert-evidence-capture-dep) so the microkernel's evidence-capture
# handler needs no extension import. Re-exported here as the extension's
# public API (the gaia worker + existing callers import it from this module).
from dna.kernel.evidence_capture import should_capture


# ───────────────────────────────────────────────────────────────────────
# Shared
# ───────────────────────────────────────────────────────────────────────

_API_VERSION = "github.com/ruinosus/dna/evidence/v1"
_ORIGIN = "github.com/ruinosus/dna/evidence"


# Evidence — F3 lote-3 (spec 2026-06-10-kinds-descriptor-f3): the twin
# EvidenceKind classes (Py+TS) were DELETED — synthesized from
# kinds/evidence.kind.yaml via the load_descriptors loop in register().
# That descriptor is now the SINGLE source: the sdk-ts mirror and
# test_descriptor_hash_parity.py went away with the TypeScript freeze
# (341e517). This comment used to claim equivalence was frozen in
# tests/test_lote3_descriptor_equivalence.py (golden
# tests/goldens/lote3/Evidence.golden.json) — neither has ever existed in
# this repository's history. No equivalence golden guards Evidence today.


# ───────────────────────────────────────────────────────────────────────
# EvidencePolicy Kind
# ───────────────────────────────────────────────────────────────────────

class EvidencePolicyKind(KindBase):
    api_version = _API_VERSION
    kind = "EvidencePolicy"
    alias = "evidence-policy"
    model = dict
    origin = _ORIGIN
    storage = StorageDescriptor.yaml("evidence-policies")
    graph_style = {"fill": "#0891B2", "stroke": "#0E7490", "text_color": "#fff"}
    ascii_icon = "\U0001f4d1"  # 📑
    display_label = "Evidence Policies"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    docs = (
        "An EvidencePolicy controls which event types are automatically "
        "captured as Evidence documents. Declares the list of event types "
        "to watch, whether auto-capture is enabled, and retention period."
    )

    def schema(self) -> dict[str, Any] | None:
        return {
            "type": "object",
            "required": ["events"],
            "additionalProperties": True,
            "properties": {
                "events": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "auto_capture": {"type": "boolean", "default": True},
                "retention_days": {"type": "integer", "default": 365},
            },
        }

    def summary(self, doc: Any) -> dict[str, Any] | None:
        spec = getattr(doc, "spec", None) or {}
        if not isinstance(spec, dict):
            spec = dict(spec) if spec else {}
        return {
            "events": spec.get("events", []),
            "auto_capture": spec.get("auto_capture", True),
            "retention_days": spec.get("retention_days", 365),
        }


# ───────────────────────────────────────────────────────────────────────
# Extension
# ───────────────────────────────────────────────────────────────────────

class EvidenceExtension:
    name = "evidence"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(EvidencePolicyKind())
        # F3 lote-3: builtin record Kinds as descriptors (Evidence) —
        # kinds/*.kind.yaml package data through the same funnel as
        # per-scope KindDefinitions (plane lint + digest idempotency +
        # builtin conflict marker).
        for raw in load_descriptors("dna.extensions.evidence"):
            kernel.kind_from_descriptor(raw)

        # Register evidence auto-capture on post_save
        from dna.kernel.evidence_capture import make_evidence_capture_handler
        kernel.on("post_save", make_evidence_capture_handler(kernel))
