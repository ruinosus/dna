"""Typed model for the ``HtmlArtifact`` Kind (github.com/ruinosus/dna/sdlc/v1).

Bundle: ARTIFACT.html (raw HTML, byte-faithful) + optional artifact.json
(structured metadata: title, description, source, created_at). A first-class
output of a work item (Story/Feature/Epic/Spike) — the roteiro/design doc that
used to live in chat becomes a linkable artifact. Record plane.

Owned by the extension that REGISTERS the Kind (i-109) — see
``dna/extensions/soulspec/models.py`` for the argument. Only
:class:`~dna.kernel.models.Metadata` comes from the kernel.

**HtmlArtifact is the only SDLC Kind with a hand-written typed model.** The
rest of the family is declarative (``kinds/*.kind.yaml`` → DeclarativeKindPort),
which is why this file holds one class pair and not thirty.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dna.kernel.models import Metadata


@dataclass
class HtmlArtifactSpec:
    html: str = ""
    artifact_json: dict[str, Any] | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> HtmlArtifactSpec:
        aj = raw.get("artifact_json")
        return cls(
            html=raw.get("html", ""),
            artifact_json=aj if isinstance(aj, dict) else None,
        )


@dataclass
class TypedHtmlArtifact:
    metadata: Metadata
    spec: HtmlArtifactSpec

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedHtmlArtifact:
        return cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=HtmlArtifactSpec.from_raw(raw.get("spec", {})),
        )


__all__ = ["HtmlArtifactSpec", "TypedHtmlArtifact"]
