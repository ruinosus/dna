"""Tests for Kernel cache invalidation + on_write observer mechanism.

Protects the contract:
- write_document / delete_document invalidate _base_instance_cache for
  base writes (layer is None)
- Registered on_write observers fire after successful writes + deletes
- Observer exceptions are swallowed (don't break the write)
"""
from __future__ import annotations

import asyncio

import pytest

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.helix import HelixExtension
from dna.kernel import Kernel


def _raw_agent(name: str = "alice") -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": name},
        "spec": {"instruction": "be helpful"},
    }


def _raw_module(scope: str) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": scope},
        "spec": {},
    }


@pytest.fixture
def kernel_with_scope(tmp_path):
    """Build a writable Kernel with a minimal filesystem scope ready for writes."""
    scope = "test-scope"
    # Create manifest file so base MI can load.
    scope_dir = tmp_path / scope
    scope_dir.mkdir(parents=True)
    manifest_path = scope_dir / "manifest.yaml"
    manifest_path.write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        f"metadata:\n  name: {scope}\n"
        "spec: {}\n"
    )

    k = Kernel()
    k.load(HelixExtension())
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    k.cache(FilesystemCache(str(tmp_path)))
    return k, scope


def test_write_document_invalidates_base_cache(kernel_with_scope):
    """After a base write, _base_instance_cache[scope] is evicted."""
    k, scope = kernel_with_scope
    # Prime the cache.
    _ = k._base_instance_cached(scope)
    assert scope in k._kcache._base

    # Write a doc at layer=None (base).
    asyncio.run(k.write_document(scope, "Agent", "alice", _raw_agent()))

    # Cache entry for this scope should be gone.
    assert scope not in k._kcache._base


def test_on_write_callback_fires_with_op_write(kernel_with_scope):
    """Registered observer receives (scope, kind, name, 'write') after a write.

    NOTE: kernel intentionally double-fires for local writes — see
    Kernel.invalidate docstring lines 560-569 ("Local writes may
    double-fire — accepted as harmless: the SSE handler is idempotent
    and React Query coalesces within a tick"). The test thus asserts
    payload equivalence + at-least-one fire, tolerating the duplicate.
    """
    k, scope = kernel_with_scope
    events: list = []
    k.on_write(lambda s, kind, name, op: events.append((s, kind, name, op)))

    asyncio.run(k.write_document(scope, "Agent", "alice", _raw_agent()))

    assert len(events) >= 1
    expected = (scope, "Agent", "alice", "write")
    assert all(e == expected for e in events), f"unexpected payload: {events}"


def test_on_write_callback_fires_with_op_delete(kernel_with_scope):
    """Registered observer receives (scope, kind, name, 'delete') after a delete."""
    k, scope = kernel_with_scope
    # Write a doc first so we have something to delete.
    asyncio.run(k.write_document(scope, "Agent", "alice", _raw_agent()))

    events: list = []
    k.on_write(lambda s, kind, name, op: events.append((s, kind, name, op)))

    asyncio.run(k.delete_document(scope, "Agent", "alice"))

    # Kernel double-fires for local writes/deletes (see kernel.invalidate
    # docstring): tolerated, payload must be identical across fires.
    assert len(events) >= 1
    expected = (scope, "Agent", "alice", "delete")
    assert all(e == expected for e in events), f"unexpected payload: {events}"


def test_observer_exception_is_swallowed(kernel_with_scope):
    """A raising observer does not prevent subsequent observers or break the write."""
    k, scope = kernel_with_scope

    def bad(s, kind, name, op):
        raise RuntimeError("observer boom")

    calls: list = []

    def good(s, kind, name, op):
        calls.append((s, kind, name, op))

    k.on_write(bad)
    k.on_write(good)

    # Must not raise.
    asyncio.run(k.write_document(scope, "Agent", "alice", _raw_agent()))

    # good observer still fired (double-fire tolerated; payload must
    # be identical across fires).
    assert len(calls) >= 1
    expected = (scope, "Agent", "alice", "write")
    assert all(c == expected for c in calls), f"unexpected payload: {calls}"
