"""Typed model for the ``Recognizer`` Kind (presidio/v1).

Presidio ad-hoc recognizer for detecting PII entities using regex patterns or
deny lists. Referenced by SafetyPolicy via dep_filters.

Owned by the extension that REGISTERS the Kind (i-109) — see
``dna/extensions/soulspec/models.py`` for the argument. Only
:class:`~dna.kernel.models.Metadata` comes from the kernel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dna.kernel.models import Metadata


@dataclass
class RecognizerPattern:
    name: str = ""
    regex: str = ""
    score: float = 0.5

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> RecognizerPattern:
        return cls(
            name=raw.get("name", ""),
            regex=raw.get("regex", ""),
            score=float(raw.get("score", 0.5)),
        )


@dataclass
class RecognizerSpec:
    entity_type: str = ""
    language: str = "en"
    patterns: list[dict[str, Any]] = field(default_factory=list)
    deny_list: list[str] = field(default_factory=list)
    context: list[str] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> RecognizerSpec:
        return cls(
            entity_type=raw.get("entity_type", ""),
            language=raw.get("language", "en"),
            patterns=raw.get("patterns") or [],
            deny_list=raw.get("deny_list") or [],
            context=raw.get("context") or [],
        )


@dataclass
class TypedRecognizer:
    metadata: Metadata
    spec: RecognizerSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedRecognizer:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=RecognizerSpec.from_raw(raw.get("spec", {})),
        )


__all__ = ["RecognizerPattern", "RecognizerSpec", "TypedRecognizer"]
