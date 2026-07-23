"""DocExtension — the in-product documentation Kind.

Registers 1 Kind:
  - Doc (dna-doc) — one page of in-product documentation: a markdown
    ``body`` + sidebar metadata (icon/subtitle/summary/order/locale/
    enabled/kind_of/category/tags). The corpus ``dna docs list/show``
    reads is made of these.

Pure descriptor extension (F3): the Kind is data — ``kinds/doc.kind.yaml``
— synthesized via ``kernel.kind_from_descriptor``; the bundle storage
(``docs/<name>/DOC.md``, frontmatter + markdown body) is handled by the
generic reader/writer machinery. No models, no port class.

Tier A port from the internal SDK's doc extension (s-tier-a-doc-kind);
see the descriptor header for the honest subset notes — what was cut
(help-center live data/diagram placeholders, spec.assets aggregation,
``featured`` curation, template scaffold, Studio widget hints) and why.
"""
from __future__ import annotations

from dna.kernel.source.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost


class DocExtension:
    name = "doc"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        for raw in load_descriptors("dna.extensions.doc"):
            kernel.kind_from_descriptor(raw)
