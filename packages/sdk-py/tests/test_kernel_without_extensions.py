"""s-invert-layer-resolver-dep — kernel resolves layers with ZERO extensions.

Functional proof of the inverted boundary: a bare ``Kernel()`` (no
``kernel.load(ext)`` at all) + a filesystem fixture with a root doc, a
LayerPolicy and a branch overlay resolves layers end-to-end. The Kinds
are minimal ``KindBase`` stubs registered directly via ``kernel.kind()``
— nothing from ``dna.extensions`` is imported here.
"""
from __future__ import annotations

import pytest
import yaml

from dna.adapters.filesystem import FilesystemSource
from dna.kernel import Kernel
from dna.kernel.kinds.base import KindBase
from dna.kernel.protocols import StorageDescriptor

API = "coretest.io/v1"


class _RootStub(KindBase):
    api_version = API
    kind = "Genome"
    alias = None
    alias_owner = "coretest"
    storage = StorageDescriptor.root("Genome.yaml")


class _WidgetStub(KindBase):
    api_version = API
    kind = "Widget"
    alias = None
    alias_owner = "coretest"
    storage = StorageDescriptor.yaml("widgets")


class _LayerPolicyStub(KindBase):
    api_version = API
    kind = "LayerPolicy"
    alias = None
    alias_owner = "coretest"
    storage = StorageDescriptor.yaml("policies")


class _NoOpCache:
    async def has(self, scope, key):
        return True

    async def load_all(self, scope, readers=None):
        return []

    async def store(self, scope, key, items):
        pass


def _write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")


@pytest.fixture()
def fs_scope(tmp_path):
    """Minimal scope: Genome + LayerPolicy + 1 widget + branch overlay."""
    scope = tmp_path / "demo"
    _write(scope / "Genome.yaml", {
        "apiVersion": API,
        "kind": "Genome",
        "metadata": {"name": "demo", "description": "no-extensions fixture"},
        "spec": {},
    })
    _write(scope / "policies" / "branch.yaml", {
        "apiVersion": API,
        "kind": "LayerPolicy",
        "metadata": {"name": "branch-policy"},
        "spec": {
            "layer_id": "branch",
            "policies": {"coretest-widget": "open"},
        },
    })
    _write(scope / "widgets" / "hello.yaml", {
        "apiVersion": API,
        "kind": "Widget",
        "metadata": {"name": "hello"},
        "spec": {"color": "red", "size": 1},
    })
    # Overlay: override `size` on hello + add an overlay-only widget.
    _write(scope / "layers" / "branch" / "dev" / "widgets" / "hello.yaml", {
        "apiVersion": API,
        "kind": "Widget",
        "metadata": {"name": "hello"},
        "spec": {"size": 2},
    })
    _write(scope / "layers" / "branch" / "dev" / "widgets" / "extra.yaml", {
        "apiVersion": API,
        "kind": "Widget",
        "metadata": {"name": "extra"},
        "spec": {"color": "blue"},
    })
    return tmp_path


def _bare_kernel(base_dir) -> Kernel:
    k = Kernel()
    k.source(FilesystemSource(base_dir))
    k.cache(_NoOpCache())
    k.kind(_RootStub())
    k.kind(_WidgetStub())
    k.kind(_LayerPolicyStub())
    # The whole point: NO extension was loaded on this kernel.
    assert k._extensions == []
    return k


@pytest.mark.asyncio
async def test_base_instance_without_extensions(fs_scope):
    k = _bare_kernel(fs_scope)
    mi = await k.instance_async("demo")
    hello = await mi.one_async("Widget", "hello")
    assert hello is not None
    assert hello.spec.get("color") == "red"
    assert hello.spec.get("size") == 1
    assert await mi.one_async("Widget", "extra") is None


@pytest.mark.asyncio
async def test_layer_overlay_merges_without_extensions(fs_scope):
    k = _bare_kernel(fs_scope)
    mi = await k.instance_async("demo", layers={"branch": "dev"})

    hello = await mi.one_async("Widget", "hello")
    assert hello is not None
    # OPEN policy → deep merge: overlay wins on `size`, base keeps `color`.
    assert hello.spec.get("size") == 2
    assert hello.spec.get("color") == "red"
    # Phase 2 overlay UX metadata stamped by the kernel-owned resolver.
    assert hello.metadata.get("has_overlay") is True
    assert hello.metadata.get("overlay_fields") == ["size"]

    # Overlay-only add under OPEN policy: whole doc is the overlay.
    extra = await mi.one_async("Widget", "extra")
    assert extra is not None
    assert extra.spec.get("color") == "blue"
    assert extra.metadata.get("has_overlay") is True
    assert extra.metadata.get("overlay_fields") is None


@pytest.mark.asyncio
async def test_resolve_layers_on_existing_mi_without_extensions(fs_scope):
    k = _bare_kernel(fs_scope)
    mi_base = await k.instance_async("demo")
    mi_dev = await k.resolve_layers_async(mi_base, {"branch": "dev"})
    assert (await mi_dev.one_async("Widget", "hello")).spec.get("size") == 2
    # Base MI untouched.
    assert (await mi_base.one_async("Widget", "hello")).spec.get("size") == 1
