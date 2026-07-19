"""MifExtension — the MIF (Memory Interchange Format, mif-spec.dev)
passthrough Kind (s-mif-passthrough-kind, feature f-portable-memory).

Registers `mif-spec.dev/v1 · Memory` from a descriptor (F3 — record Kinds are
data, not classes; docs/guides/add-a-kind.md). A dedicated extension, not a
Kind bolted onto an existing one, following the precedent set by the other
two foreign-namespace passthrough Kinds:

  - `dna.extensions.agentskills` — agentskills.io/v1 · Skill
  - `dna.extensions.soulspec`    — soulspec.org/v1 · Soul

Those two ship as hand-written KindPort classes (their bundles carry sidecar
files — scripts/references/assets, SOUL.md+IDENTITY.md+HEARTBEAT.md — that
need custom Reader/Writer logic). MIF Memory is a single frontmatter+body
marker with no sidecars, so per "record-style Kinds don't need a class at
all" it ships as `kinds/memory.kind.yaml` instead (the same choice
`dna.extensions.doc` made for its own single-marker bundle) — same market-
fidelity mechanic (origin = the owner's domain, target_api_version = the
owner's namespace, schema = the owner's fields, unchanged), different
registration mechanism because the bundle shape is simpler.

This is the interchange face only — see `dna.extensions.helix` for Engram
(the native memory engine). `dna memory export`/`import` (a later story)
projects between the two.
"""
from __future__ import annotations

from dna.kernel.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost


class MifExtension:
    """Registers the MIF Memory Kind (descriptor-backed)."""

    name = "mif"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        # F3: ships as kinds/*.kind.yaml package data (byte-identical Py↔TS
        # mirror), registered through the SAME funnel as per-scope
        # KindDefinitions (plane lint + digest idempotency + builtin
        # conflict marker).
        for raw in load_descriptors("dna.extensions.mif"):
            kernel.kind_from_descriptor(raw)
