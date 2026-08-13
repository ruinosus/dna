"""Typed model for the ``SafetyPolicy`` Kind (github.com/ruinosus/dna/v1).

Owned by the extension that REGISTERS the Kind (i-109) — see
``dna/extensions/soulspec/models.py`` for the argument. Only
:class:`~dna.kernel.models.Metadata` comes from the kernel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dna.kernel.models import Metadata


@dataclass
class SafetyPolicySpec:
    scope: str = "both"       # "input", "output", or "both"
    action: str = "mask"      # "mask", "block", or "log"
    severity: str = "error"   # "error" or "warn"
    rules: list[dict[str, Any]] = field(default_factory=list)
    recognizers: list[str] = field(default_factory=list)
    # Phase 7 — ml-privacy-filter engine. All optional (backward-compatible).
    # Valid engine values: "presidio" (default — Tier-1 regex) or
    # "ml-privacy-filter" (T1 spec lock — openai/privacy-filter ONNX model).
    engine: str = "presidio"
    model: str = "openai/privacy-filter"
    backend: str = "auto"     # "auto" | "transformers" | "onnxruntime"
    threshold: float = 0.8
    # T1 LOCKED — valid values: account_number, private_address,
    # private_email, private_person, private_phone, private_url,
    # private_date, secret. None = all 8 categories.
    categories: list[str] | None = None
    mask_char: str = "[REDACTED]"
    budget_ms: float = 1000.0  # T1 LOCKED: 1000ms (covers ONNX first-call JIT)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> SafetyPolicySpec:
        return cls(
            scope=raw.get("scope", "both"),
            action=raw.get("action", "mask"),
            severity=raw.get("severity", "error"),
            rules=raw.get("rules") or [],
            recognizers=raw.get("recognizers") or [],
            engine=raw.get("engine", "presidio"),
            model=raw.get("model", "openai/privacy-filter"),
            backend=raw.get("backend", "auto"),
            threshold=float(raw.get("threshold", 0.8)),
            categories=raw.get("categories"),
            mask_char=raw.get("mask_char", "[REDACTED]"),
            budget_ms=float(raw.get("budget_ms", 1000.0)),
        )


@dataclass
class TypedSafetyPolicy:
    metadata: Metadata
    spec: SafetyPolicySpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedSafetyPolicy:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=SafetyPolicySpec.from_raw(raw.get("spec", {})),
        )


__all__ = ["SafetyPolicySpec", "TypedSafetyPolicy"]
