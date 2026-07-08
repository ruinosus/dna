"""Tests verifying HookContext carries the layer field on post_save / post_delete."""
from __future__ import annotations


def test_hook_context_has_optional_layer_field():
    from dna.kernel.hooks import HookContext
    ctx = HookContext(
        scope="s",
        kind="K",
        name="n",
        data={},
        layer=("tenant", "T1"),
    )
    assert ctx.layer == ("tenant", "T1")


def test_hook_context_layer_defaults_to_none():
    from dna.kernel.hooks import HookContext
    ctx = HookContext(
        scope="s",
        kind="K",
        name="n",
        data={},
    )
    assert ctx.layer is None


def test_post_save_hook_receives_layer_after_write(tmp_path):
    """End-to-end: Kernel.write_document with layer → subscriber sees it."""
    import asyncio
    from dna.kernel import Kernel
    from dna.adapters.filesystem import FilesystemCache
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.helix import HelixExtension

    k = Kernel()
    k.load(HelixExtension())
    k.source(FilesystemWritableSource(tmp_path, kernel=k))
    k.cache(FilesystemCache(tmp_path / ".dna-cache"))
    (tmp_path / "s").mkdir()

    captured = []
    k.on("post_save", lambda ctx: captured.append(ctx))

    raw = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {},
    }
    asyncio.run(k.write_document("s", "Agent", "x", raw, layer=("tenant", "T1")))

    assert len(captured) == 1
    assert captured[0].layer == ("tenant", "T1")


def test_post_save_hook_layer_none_when_base_write(tmp_path):
    import asyncio
    from dna.kernel import Kernel
    from dna.adapters.filesystem import FilesystemCache
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.helix import HelixExtension

    k = Kernel()
    k.load(HelixExtension())
    k.source(FilesystemWritableSource(tmp_path, kernel=k))
    k.cache(FilesystemCache(tmp_path / ".dna-cache"))
    (tmp_path / "s").mkdir()

    captured = []
    k.on("post_save", lambda ctx: captured.append(ctx))

    raw = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {},
    }
    asyncio.run(k.write_document("s", "Agent", "x", raw))  # no layer

    assert len(captured) == 1
    assert captured[0].layer is None
