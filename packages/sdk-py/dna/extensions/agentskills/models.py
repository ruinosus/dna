"""Typed model for the ``Skill`` Kind (agentskills.io/v1).

Bundle: SKILL.md (frontmatter + instruction body) + optional ``scripts/``,
``references/``, ``assets/`` directories. Not a prompt target — referenced by
agents via ``spec.skills``.

Owned by the extension that REGISTERS the Kind (i-109) — see
``dna/extensions/soulspec/models.py`` for the argument. Only
:class:`~dna.kernel.models.Metadata` comes from the kernel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dna.kernel.models import Metadata


@dataclass
class SkillSpec:
    instruction: str = ""
    scripts: dict[str, str] = field(default_factory=dict)
    references: dict[str, str] = field(default_factory=dict)
    assets: dict[str, str] = field(default_factory=dict)
    extras: dict[str, dict[str, str]] = field(default_factory=dict)
    root_files: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> SkillSpec:
        return cls(
            instruction=raw.get("instruction", ""),
            scripts=raw.get("scripts", {}) if isinstance(raw.get("scripts"), dict) else {},
            references=raw.get("references", {}) if isinstance(raw.get("references"), dict) else {},
            assets=raw.get("assets", {}) if isinstance(raw.get("assets"), dict) else {},
            extras=raw.get("extras", {}),
            root_files=raw.get("root_files", {}),
        )


@dataclass
class TypedSkill:
    metadata: Metadata
    spec: SkillSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedSkill:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=SkillSpec.from_raw(raw.get("spec", {})),
        )


__all__ = ["SkillSpec", "TypedSkill"]
