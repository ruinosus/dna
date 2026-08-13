"""Typed model for the ``Hook`` Kind (github.com/ruinosus/dna/v1).

Declarative hook definition: middleware and event hooks declared as YAML
instances in the manifest, auto-registered on the kernel's HookRegistry.

Owned by the extension that REGISTERS the Kind (i-109) — see
``dna/extensions/soulspec/models.py`` for the argument. Only
:class:`~dna.kernel.models.Metadata` comes from the kernel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dna.kernel.models import Metadata


@dataclass
class HookSpec:
    target: str = "pre_build_prompt"
    type: str = "middleware"       # "middleware" or "event"
    action: str = "inject_fields"  # "inject_fields", "log", "script"
    fields: dict[str, Any] = field(default_factory=dict)
    body: str = ""

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> HookSpec:
        return cls(
            target=raw.get("target", "pre_build_prompt"),
            type=raw.get("type", "middleware"),
            action=raw.get("action", "inject_fields"),
            fields=raw.get("fields") or {},
            body=raw.get("body", ""),
        )


@dataclass
class TypedHook:
    metadata: Metadata
    spec: HookSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedHook:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=HookSpec.from_raw(raw.get("spec", {})),
        )


__all__ = ["HookSpec", "TypedHook"]
