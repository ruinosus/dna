"""Typed model for the ``AgentDefinition`` Kind (agents.md/v1).

Owned by the extension that REGISTERS the Kind (i-109) — see
``dna/extensions/soulspec/models.py`` for the argument. Only
:class:`~dna.kernel.models.Metadata` comes from the kernel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dna.kernel.models import Metadata


@dataclass
class AgentDefinitionSpec:
    content: str = ""

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> AgentDefinitionSpec:
        return cls(content=raw.get("content", ""))


@dataclass
class TypedAgentDefinition:
    metadata: Metadata
    spec: AgentDefinitionSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedAgentDefinition:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=AgentDefinitionSpec.from_raw(raw.get("spec", {})),
        )


__all__ = ["AgentDefinitionSpec", "TypedAgentDefinition"]
