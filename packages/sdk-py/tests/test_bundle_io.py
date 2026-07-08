"""Unit tests for the BundleIO collaborator (kernel-decompose-continue).

Covers serialize() output shapes + the fetch/write error paths (unknown kind,
non-capable source) in isolation. End-to-end bundle round-trips through real
adapters are covered by test_generic_rw / test_adapter_conformance_matrix via
the kernel delegators.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.bundle_io import BundleIO


def _kernel():
    # Kernel with all extensions registered (so storage_for_kind resolves real
    # kinds) — entry-point discovery, same as the rest of the suite.
    return Kernel.auto()


def test_serialize_returns_files_with_doc_path():
    k = _kernel()
    out = k._bundleio.serialize(
        "s", "Agent", "bot",
        {"kind": "Agent", "metadata": {"name": "bot"}, "spec": {"model": "x"}},
    )
    files = out["files"]
    assert files and all("relativePath" in f and "content" in f for f in files)
    # Agent is a bundle kind → the doc serializes under its own name.
    assert any("bot" in f["relativePath"] for f in files)


def test_serialize_unknown_kind_raises():
    k = _kernel()
    with pytest.raises(ValueError, match="Unknown kind"):
        k._bundleio.serialize("s", "NotARealKind", "x", {"spec": {}})


def test_fetch_sync_unknown_kind_raises():
    k = _kernel()
    with pytest.raises(ValueError, match="not registered or has no bundle container"):
        k._bundleio.fetch_sync("s", "NotARealKind", "n", "entry")


def test_kernel_delegators_point_at_bundleio():
    k = _kernel()
    assert isinstance(k._bundleio, BundleIO)
    # The public kernel methods delegate to the same collaborator.
    out_kernel = k.serialize_document(
        "s", "Agent", "bot",
        {"kind": "Agent", "metadata": {"name": "bot"}, "spec": {"model": "x"}},
    )
    out_collab = k._bundleio.serialize(
        "s", "Agent", "bot",
        {"kind": "Agent", "metadata": {"name": "bot"}, "spec": {"model": "x"}},
    )
    assert out_kernel == out_collab
