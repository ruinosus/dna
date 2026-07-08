"""Regression — Story s-mi-tenant-kwarg-eager-bug (2026-05-15).

Eager-loaded MI silently dropped the ``tenant`` kwarg on read APIs
(`mi.all_async`, `mi.one_async`), returning only base-layer docs even
when overlay storage had rows. Symptom: harness `/eval/summary` saw
zero EvalRuns despite Postgres holding N at `tenant=dev-tenant`.

Fix: eager MI falls back to ``kernel.query`` / ``kernel.get_document``
when the requested ``tenant`` differs from this MI's resolved tenant
(`self._tenant`). The fallback path also bypasses ``_lazy_kind_cache``
because it's keyed by ``kind`` only — two tenants would alias.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from dna.kernel import Kernel
from dna.extensions.helix import HelixExtension
from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource


def _make_kernel(tmp: Path) -> Kernel:
    (tmp / "scope").mkdir(exist_ok=True)
    (tmp / "scope" / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        "metadata: {name: scope}\nspec: {}\n"
    )
    # Phase 17 / V1 inheritance (s-comp-f2-resolver): scopes without an
    # explicit parent_scope escalate to the legacy `_lib` parent.
    # kernel.query walks that chain and loads `_lib`, so the scope
    # must exist on the source (empty is fine) or load_all raises
    # FileNotFoundError mid-walk. The cross-tenant fallback under test
    # routes through kernel.query, hence this prerequisite.
    (tmp / "_lib").mkdir(exist_ok=True)
    (tmp / "_lib" / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        "metadata: {name: _lib}\nspec: {}\n"
    )
    k = Kernel()
    k.load(HelixExtension())
    src = FilesystemWritableSource(str(tmp), writers=list(k._writers), kernel=k)
    k.source(src)
    k.cache(FilesystemCache(tmp / ".dna-cache"))
    return k


async def _write_agent(
    k: Kernel, name: str, tenant: str | None, *, instruction: str = "x"
) -> None:
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": name},
        "spec": {"description": "d", "instruction": instruction},
    }
    await k.write_document("scope", "Agent", name, raw, tenant=tenant)


def test_all_async_cross_tenant_reads_overlay_from_eager_mi(tmp_path: Path):
    """Eager-loaded MI with _tenant=None reads tenant overlay via fallback."""
    async def run():
        k = _make_kernel(tmp_path)
        await _write_agent(k, "base-only", tenant=None)
        await _write_agent(k, "acme-only", tenant="acme")
        await _write_agent(k, "beta-only", tenant="beta")

        # Eager MI, no tenant binding.
        mi = await k.instance_async("scope", lazy=False)
        assert getattr(mi, "_tenant", None) is None

        # tenant=None → only base.
        base = await mi.all_async("Agent", tenant=None)
        base_names = {d.name for d in base}
        assert "base-only" in base_names
        # acme/beta should NOT be in base file walk (live in overlay dirs).
        assert "acme-only" not in base_names
        assert "beta-only" not in base_names

        # tenant="acme" → union base + acme overlay.
        acme = await mi.all_async("Agent", tenant="acme")
        acme_names = {d.name for d in acme}
        assert "acme-only" in acme_names, (
            f"eager MI must fall back to kernel.query for cross-tenant "
            f"reads — got names {acme_names!r}"
        )

        # tenant="beta" → must NOT be aliased by previous acme call.
        beta = await mi.all_async("Agent", tenant="beta")
        beta_names = {d.name for d in beta}
        assert "beta-only" in beta_names
        assert "acme-only" not in beta_names, (
            f"_lazy_kind_cache poisoned across tenants: beta read returned "
            f"acme docs {beta_names!r}"
        )

    asyncio.run(run())


def test_one_async_cross_tenant_lookup_from_eager_mi(tmp_path: Path):
    """mi.one_async with tenant kwarg resolves overlay doc on eager MI."""
    async def run():
        k = _make_kernel(tmp_path)
        await _write_agent(k, "shared", tenant="acme", instruction="acme-body")

        mi = await k.instance_async("scope", lazy=False)
        assert getattr(mi, "_tenant", None) is None

        # No tenant → no doc in base.
        assert await mi.one_async("Agent", "shared", tenant=None) is None

        # tenant="acme" → overlay doc returned.
        doc = await mi.one_async("Agent", "shared", tenant="acme")
        assert doc is not None, (
            "eager MI must fall back to kernel.get_document for cross-tenant "
            "one_async lookups"
        )
        assert doc.name == "shared"

    asyncio.run(run())


def test_eager_same_tenant_keeps_in_memory_fast_path(tmp_path: Path):
    """When tenant matches MI._tenant, eager fast-path stays in use."""
    async def run():
        k = _make_kernel(tmp_path)
        await _write_agent(k, "a", tenant=None)
        await _write_agent(k, "b", tenant=None)

        mi = await k.instance_async("scope", lazy=False)
        # tenant=None matches MI._tenant=None → walk self._documents only.
        docs = await mi.all_async("Agent", tenant=None)
        names = {d.name for d in docs}
        assert names >= {"a", "b"}

    asyncio.run(run())
