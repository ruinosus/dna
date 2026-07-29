"""ArtifactExtension — the ORIGINAL behind a typed document.

Registers one record Kind, ``SourceArtifact``, from a descriptor.

The DNA Cloud assistant converts unstructured input into typed documents: a
file arrives, an agent reads it, authors or matches a Kind, and writes what it
found. Those documents are a PROJECTION — lossy and interpreted. This Kind is
what makes that word mean something: it records the original's content address
and where its bytes live, so "derived from" becomes a claim anyone holding the
file can check, rather than one they have to take on trust.

The edge points FROM the artifact TO its derivations, never the reverse. See
the descriptor's header for why that direction is the load-bearing choice.

Vendor-neutral on purpose. "This document came from that artifact" is a fact
about provenance, not about hosting — the Kind belongs here, in the OSS SDK,
while the blob store that actually holds the bytes is a deployment's own
concern (Azure Blob in dna-cloud, a directory in a self-host, S3 elsewhere).
The ``uri`` is opaque to the kernel precisely so that stays true.
"""
from __future__ import annotations

from dna.kernel.source.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost


class ArtifactExtension:
    """Registers ``SourceArtifact`` (descriptor-backed)."""

    name = "artifact"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        for raw in load_descriptors("dna.extensions.artifact"):
            kernel.kind_from_descriptor(raw)
