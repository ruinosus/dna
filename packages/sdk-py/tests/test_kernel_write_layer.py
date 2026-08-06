"""Tests for layer-routed writes via FilesystemWritableSource."""
from __future__ import annotations

import asyncio
import pytest
from pathlib import Path


def _make_kernel(tmp_path: Path):
    from dna.kernel import Kernel
    from dna.adapters.filesystem import FilesystemCache
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.helix import HelixExtension
    k = Kernel()
    k.load(HelixExtension())
    src = FilesystemWritableSource(tmp_path, kernel=k)
    k.source(src)
    k.cache(FilesystemCache(tmp_path / ".dna-cache"))
    return k


def test_write_to_base_when_layer_none(tmp_path):
    """Backward compat: no layer kwarg → base dir."""
    k = _make_kernel(tmp_path)
    (tmp_path / "s").mkdir()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {},
    }
    asyncio.run(k.write_instance("s", "Agent", "x", raw))
    # Agent serializes to a bundle: <scope>/agents/x/AGENT.md.
    # Doc landed somewhere in base scope, NOT under any layers/ and NOT
    # under tenants/.
    has_tenant = (tmp_path / "tenants").exists() and any((tmp_path / "tenants").rglob("AGENT.md"))
    has_layer = (tmp_path / "s" / "layers").exists() and any((tmp_path / "s" / "layers").rglob("AGENT.md"))
    has_base = (tmp_path / "s" / "agents" / "x" / "AGENT.md").is_file()
    assert not has_tenant
    assert not has_layer
    assert has_base


def test_write_to_tenant_layer(tmp_path):
    """Phase 2b: tenant routes to tenants/<X>/scopes/<S>/ (not layers/tenant/<X>/)."""
    k = _make_kernel(tmp_path)
    (tmp_path / "s").mkdir()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {},
    }
    asyncio.run(k.write_instance("s", "Agent", "x", raw, layer=("tenant", "T1")))
    tenant_dir = tmp_path / "tenants" / "T1" / "scopes" / "s"
    assert tenant_dir.exists()
    assert (tenant_dir / "agents" / "x" / "AGENT.md").is_file()


def test_two_tenants_isolated(tmp_path):
    """Phase 2b: each tenant has its own scope subtree."""
    k = _make_kernel(tmp_path)
    (tmp_path / "s").mkdir()
    # instruction round-trips into the AGENT.md bundle body — the
    # distinguishing per-tenant content. (spec.description is dropped on
    # serialize; only metadata fields land in frontmatter.)
    raw_t1 = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {"instruction": "T1 view"},
    }
    raw_t2 = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {"instruction": "T2 view"},
    }
    asyncio.run(k.write_instance("s", "Agent", "x", raw_t1, layer=("tenant", "T1")))
    asyncio.run(k.write_instance("s", "Agent", "x", raw_t2, layer=("tenant", "T2")))
    t1_files = list((tmp_path / "tenants" / "T1" / "scopes" / "s").rglob("AGENT.md"))
    t2_files = list((tmp_path / "tenants" / "T2" / "scopes" / "s").rglob("AGENT.md"))
    assert len(t1_files) >= 1
    assert len(t2_files) >= 1
    assert "T1 view" in t1_files[0].read_text()
    assert "T2 view" in t2_files[0].read_text()


def test_delete_from_tenant_layer(tmp_path):
    """Phase 2b: delete also routes to tenants/<X>/scopes/<S>/."""
    k = _make_kernel(tmp_path)
    (tmp_path / "s").mkdir()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {},
    }
    asyncio.run(k.write_instance("s", "Agent", "x", raw, layer=("tenant", "T1")))
    tenant_dir = tmp_path / "tenants" / "T1" / "scopes" / "s"
    assert any(tenant_dir.rglob("AGENT.md"))
    asyncio.run(k.delete_instance("s", "Agent", "x", layer=("tenant", "T1")))
    assert not any(tenant_dir.rglob("AGENT.md"))


def test_path_traversal_rejected_in_layer_id(tmp_path):
    k = _make_kernel(tmp_path)
    (tmp_path / "s").mkdir()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {},
    }
    with pytest.raises(ValueError, match="Invalid layer segment"):
        asyncio.run(k.write_instance("s", "Agent", "x", raw, layer=("../up", "val")))


def test_path_traversal_rejected_in_layer_value(tmp_path):
    """The tenant traversal is now refused EARLIER — at the kernel boundary.

    ``layer=("tenant", X)`` is rewritten to ``tenant=X``, and the write
    pipeline calls ``validate_tenant_slug`` before the adapter is touched. That
    validator used to disclaim path safety ("path-traversal safety lives in the
    adapter") and now enforces the traversal rule itself, because ``tenant``
    ALSO becomes ``<base>/tenants/<tenant>/.dna.lock`` in
    ``dna.kernel.lock.module`` — which is not an adapter and had no
    containment. So the refusal type and message changed on purpose:
    ``InvalidTenantSlug`` from the kernel, not the adapter's
    ``ValueError("Invalid layer segment: …")``.

    Still a ``ValueError`` — ``InvalidTenantSlug`` gained that base in the same
    change, precisely so moving the refusal earlier could not stop a face that
    enumerates ``(ValueError, LookupError, PermissionError)`` from relaying it.
    Both assertions below are deliberate: the marker base is what faces catch,
    the ``ValueError`` base is what the older faces catch.
    """
    from dna.kernel.errors import KernelRefusal
    from dna.kernel.protocols import InvalidTenantSlug

    k = _make_kernel(tmp_path)
    (tmp_path / "s").mkdir()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {},
    }
    before = {p for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(InvalidTenantSlug, match="cannot escape") as exc:
        asyncio.run(k.write_instance("s", "Agent", "x", raw, layer=("tenant", "../evil")))
    assert isinstance(exc.value, KernelRefusal)
    assert isinstance(exc.value, ValueError)
    # The property, asserted on the FILESYSTEM rather than on the exception:
    # nothing was written anywhere under the sandbox, inside the store or out.
    assert {p for p in tmp_path.rglob("*") if p.is_file()} == before
    assert not (tmp_path.parent / "evil").exists()


def test_path_traversal_rejected_slashes(tmp_path):
    k = _make_kernel(tmp_path)
    (tmp_path / "s").mkdir()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {},
    }
    with pytest.raises(ValueError, match="Invalid layer segment"):
        asyncio.run(k.write_instance("s", "Agent", "x", raw, layer=("a/b", "c")))
