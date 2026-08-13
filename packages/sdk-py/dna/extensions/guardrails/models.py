"""Typed model for the ``Guardrail`` Kind (github.com/ruinosus/dna/v1).

Owned by the extension that REGISTERS the Kind (i-109) — see
``dna/extensions/soulspec/models.py`` for the argument. Only
:class:`~dna.kernel.models.Metadata` comes from the kernel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from dna.kernel.models import Metadata


@dataclass
class GuardrailSpec:
    rules: list[str] = field(default_factory=list)
    # Constrained fields — the documented severity/scope contracts. Typed as
    # Literal so ``_schema_from_model`` emits ``enum`` in the generated JSON
    # Schema (i-validation-shallow): a bare ``str`` mapped to bare
    # ``{"type": "string"}`` and accepted ``severity: critical``/garbage on the
    # write path, which was shallower than a plain Pydantic model. warn lets the
    # turn continue; error fails the turn; hard refuses to answer.
    severity: Literal["warn", "error", "hard"] = "warn"
    scope: Literal["input", "output", "both"] = "both"

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> GuardrailSpec:
        return cls(
            rules=raw.get("rules") or [],
            severity=raw.get("severity", "warn"),
            scope=raw.get("scope", "both"),
        )


@dataclass
class TypedGuardrail:
    metadata: Metadata
    spec: GuardrailSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedGuardrail:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=GuardrailSpec.from_raw(raw.get("spec", {})),
        )


__all__ = ["GuardrailSpec", "TypedGuardrail"]
