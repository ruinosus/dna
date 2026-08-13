"""Typed model for the ``Soul`` Kind (soulspec.org/v1).

Owned by the extension that REGISTERS the Kind (i-109). It used to live in
``dna.kernel.models``, which made the kernel carry the schema of a Kind it does
not know exists — and made this extension import back from the kernel to
register its own Kind. The edge now points one way: extension → kernel.

Only :class:`~dna.kernel.models.Metadata` comes from the kernel, and it is
generic envelope structure (``metadata:`` is in every instance of every Kind),
not knowledge of any particular Kind.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dna.kernel.models import Metadata


@dataclass
class SoulSpec:
    soul_content: str = ""
    soul_json: dict[str, Any] | None = None
    style_content: str = ""
    agents_content: str = ""

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> SoulSpec:
        return cls(
            soul_content=raw.get("soul_content", ""),
            soul_json=raw.get("soul_json"),
            style_content=raw.get("style_content", ""),
            agents_content=raw.get("agents_content", ""),
        )


@dataclass
class TypedSoul:
    metadata: Metadata
    spec: SoulSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedSoul:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=SoulSpec.from_raw(raw.get("spec", {})),
        )


__all__ = ["SoulSpec", "TypedSoul"]
