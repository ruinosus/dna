"""Runtime binding definitions without transport or session lifecycle."""
from __future__ import annotations

from dna.kernel.protocols import ExtensionHost
from dna.kernel.source.descriptor_loader import load_descriptors


class RuntimeExtension:
    """Register descriptor-backed runtime binding Kinds."""

    name = "runtime"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        for raw in load_descriptors("dna.extensions.runtime"):
            kernel.kind_from_descriptor(raw)