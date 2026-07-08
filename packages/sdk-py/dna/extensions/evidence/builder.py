"""Evidence builder — re-export shim.

``compute_content_hash`` and ``build_evidence`` are generic (stdlib + plain
dicts) and now live in the kernel at
``dna.kernel.evidence_capture`` so the microkernel's evidence-capture
handler doesn't have to import an extension (s-invert-evidence-capture-dep;
mirrors the TS twin where these live in ``kernel/evidence-capture.ts``).

This module is kept as a thin re-export so existing callers keep working.
"""
from __future__ import annotations

from dna.kernel.evidence_capture import build_evidence, compute_content_hash

__all__ = ["build_evidence", "compute_content_hash"]
