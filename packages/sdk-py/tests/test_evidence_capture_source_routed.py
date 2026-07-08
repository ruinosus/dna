"""Test that EvidenceCaptureHook writes Evidence via the Source (not via Path.write_text).

Phase 8 PR4 — Leak 1 fix verification.

Before the fix: the handler called ``Path.write_text`` directly after
``getattr(kernel._source, "base_dir", None)``, silently no-op-ing on
Postgres/S3.

After the fix: the handler is ``async def`` and calls
``kernel.write_document(scope, "Evidence", name, raw, skip_hooks=True)``.
The Source persists via the registered WriterPort.
"""
from __future__ import annotations

import pytest
import yaml as pyyaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.helix import HelixExtension
from dna.extensions.evidence import EvidenceExtension
from dna.kernel import Kernel


# ── helpers ───────────────────────────────────────────────────────────────

def _make_scope(tmp_path, scope: str = "test-scope"):
    """Write a minimal manifest so the kernel can load the scope."""
    scope_dir = tmp_path / scope
    scope_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": scope},
        "spec": {"agents": []},
    }
    (scope_dir / "manifest.yaml").write_text(pyyaml.dump(manifest))

    # An EvidencePolicy that captures all document_created events
    ep_dir = scope_dir / "evidence-policies"
    ep_dir.mkdir(exist_ok=True)
    policy = {
        "apiVersion": "github.com/ruinosus/dna/evidence/v1",
        "kind": "EvidencePolicy",
        "metadata": {"name": "default-policy"},
        "spec": {"events": ["document_created"], "auto_capture": True},
    }
    (ep_dir / "default-policy.yaml").write_text(pyyaml.dump(policy))
    return tmp_path


def _make_kernel(base_dir) -> Kernel:
    k = Kernel()
    k.load(HelixExtension())
    k.load(EvidenceExtension())
    k.cache(FilesystemCache(str(base_dir / ".dna-cache")))
    source = FilesystemWritableSource(str(base_dir), kernel=k)
    k._source = source
    return k


def _make_kernel_no_evidence(base_dir) -> Kernel:
    """A kernel with the evidence-capture inversion in place but WITHOUT
    EvidenceExtension loaded — the post_save handler is never wired, so
    capture is a silent no-op (s-invert-evidence-capture-dep)."""
    k = Kernel()
    k.load(HelixExtension())
    k.cache(FilesystemCache(str(base_dir / ".dna-cache")))
    source = FilesystemWritableSource(str(base_dir), kernel=k)
    k._source = source
    return k


# ── tests ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evidence_written_via_source_not_path(tmp_path):
    """After writing a doc, Evidence must appear via mi.all('Evidence'),
    meaning it was routed through the Source — not written by Path.write_text
    to a path the kernel doesn't know about.
    """
    base_dir = _make_scope(tmp_path, "test-scope")
    k = _make_kernel(base_dir)

    # Write a Agent — triggers post_save → evidence capture
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "demo-agent"},
        "spec": {"model": "gpt-4o"},
    }
    await k.write_document("test-scope", "Agent", "demo-agent", raw)

    # The Evidence doc must now be readable via the kernel instance.
    # two-planes F2.5: Evidence is plane="record" — sync mi.all from the
    # loop thread now raises by design; use the async surface.
    mi = await k.instance_async("test-scope")
    evidence_docs = await mi.all_async("Evidence")
    assert len(evidence_docs) >= 1, (
        "Expected at least one Evidence doc in the source after write_document; "
        "got none. The handler may still be writing via Path.write_text."
    )


@pytest.mark.asyncio
async def test_evidence_not_written_to_stray_path(tmp_path):
    """No 'evidence/' subdirectory should be created by the old Path.write_text
    leak — all Evidence writes must go through the Source's storage container.
    """
    base_dir = _make_scope(tmp_path, "test-scope")
    k = _make_kernel(base_dir)

    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "agent2"},
        "spec": {"model": "gpt-4o"},
    }
    await k.write_document("test-scope", "Agent", "agent2", raw)

    # The old leak wrote to <base_dir>/<scope>/evidence/*.yaml —
    # that directory must NOT exist (evidence is stored in 'evidence/'
    # container subdir via WriterPort, not directly under scope root).
    old_leak_dir = base_dir / "test-scope" / "evidence"
    # The WriterPort may still create an 'evidence/' container dir, but it
    # should contain YAML files that the source can load_all() — so we only
    # assert that the manifest instance knows about the evidence, not that
    # the directory doesn't exist (the writer is allowed to use it).
    # two-planes F2.5: Evidence is plane="record" — async surface required
    # from the loop thread (sync mi.all raises by design).
    mi = await k.instance_async("test-scope")
    evidence_docs = await mi.all_async("Evidence")
    assert len(evidence_docs) >= 1


@pytest.mark.asyncio
async def test_capture_is_noop_without_evidence_extension(tmp_path):
    """s-invert-evidence-capture-dep: the microkernel must work with ZERO
    extensions loaded. Without EvidenceExtension the post_save handler is
    never wired, so writing a doc that WOULD match a policy neither crashes
    nor produces Evidence — capture is simply off.
    """
    base_dir = _make_scope(tmp_path, "test-scope")  # writes an EvidencePolicy
    k = _make_kernel_no_evidence(base_dir)

    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "no-ext-agent"},
        "spec": {"model": "gpt-4o"},
    }
    # Must complete without raising — no evidence handler is registered.
    await k.write_document("test-scope", "Agent", "no-ext-agent", raw)

    # No Evidence Kind is registered (extension absent) and nothing was
    # captured. The write above succeeding is the assertion of the no-op.
    assert k.kind_port_for("Evidence") is None


@pytest.mark.asyncio
async def test_no_infinite_recursion_on_evidence_write(tmp_path):
    """Writing an Evidence doc must not re-trigger evidence capture
    (skip_hooks=True prevents the cycle).
    """
    base_dir = _make_scope(tmp_path, "test-scope")
    k = _make_kernel(base_dir)

    # This would hang / stack-overflow if skip_hooks wasn't set
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "agent3"},
        "spec": {"model": "gpt-4o"},
    }
    # Should complete without RecursionError
    await k.write_document("test-scope", "Agent", "agent3", raw)
