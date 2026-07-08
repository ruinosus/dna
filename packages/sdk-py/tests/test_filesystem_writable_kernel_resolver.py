"""Tests for FilesystemWritableSource kernel-resolver binding.

The adapter requires a kernel (bound at construction via ``kernel=`` or
later via ``set_kernel(k)``) to resolve each kind's on-disk container
through ``Kernel.storage_for_kind``. These tests pin:

1. Constructing without a kernel and then writing raises a helpful
   ``RuntimeError`` (the adapter refuses to guess subdirectories).
2. ``set_kernel`` binds the kernel post-construction.
3. Custom kinds (KindDefinition, container="kinds") route via
   ``storage_for_kind`` — not a hardcoded map.
"""
from __future__ import annotations

import pytest

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.kernel import Kernel


@pytest.mark.asyncio
async def test_save_without_kernel_raises_runtime_error(tmp_path):
    """Guessing containers from a hardcoded map is gone. Without a
    bound kernel, the adapter must refuse to save."""
    src = FilesystemWritableSource(str(tmp_path))
    with pytest.raises(RuntimeError, match="no kernel bound"):
        await src.save_document(
            "m", "Agent", "bob",
            {"kind": "Agent", "name": "bob", "spec": {}},
        )


def test_kernel_param_is_stored_for_resolver_use(tmp_path):
    """When a kernel is passed, the adapter stores it for storage_for_kind lookups."""
    k = Kernel()
    src = FilesystemWritableSource(str(tmp_path), kernel=k)
    assert src._kernel is k


def test_set_kernel_binds_post_construction(tmp_path):
    """Factories that build the source before the kernel can bind later."""
    k = Kernel()
    src = FilesystemWritableSource(str(tmp_path))
    assert src._kernel is None
    src.set_kernel(k)
    assert src._kernel is k


@pytest.mark.asyncio
async def test_save_routes_kinddefinition_to_kinds_dir(tmp_path):
    """Custom kind declared by an extension must route via
    ``kernel.storage_for_kind``."""
    from dna.extensions.kinddef import KindDefinitionExtension

    k = Kernel()
    k.load(KindDefinitionExtension())
    src = FilesystemWritableSource(str(tmp_path), kernel=k)

    raw = {
        "apiVersion": "kinddef.github.com/ruinosus/dna/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "ticket"},
        "spec": {"kind": "Ticket", "schema": {}},
    }
    await src.save_document("m", "KindDefinition", "ticket", raw)
    # KindDefinition has storage.container="kinds".
    assert (tmp_path / "m" / "kinds" / "ticket.yaml").is_file()


@pytest.mark.asyncio
async def test_delete_routes_kinddefinition_to_kinds_dir(tmp_path):
    """Parity with save: delete_document must consult storage_for_kind
    so custom kinds can be removed from their real on-disk location."""
    from dna.extensions.kinddef import KindDefinitionExtension

    k = Kernel()
    k.load(KindDefinitionExtension())
    src = FilesystemWritableSource(str(tmp_path), kernel=k)

    raw = {
        "apiVersion": "kinddef.github.com/ruinosus/dna/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "ticket"},
        "spec": {"kind": "Ticket", "schema": {}},
    }
    await src.save_document("m", "KindDefinition", "ticket", raw)
    assert (tmp_path / "m" / "kinds" / "ticket.yaml").is_file()

    await src.delete_document("m", "KindDefinition", "ticket")
    assert not (tmp_path / "m" / "kinds" / "ticket.yaml").exists()
