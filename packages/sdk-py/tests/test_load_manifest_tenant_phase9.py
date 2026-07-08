"""Phase 9b — Phase 16 — tenant-aware bootstrap-doc lookup.

Resolution: tenant-published Genome shadows the platform Genome of
the same scope name. Falls back to platform when tenant has no overlay.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from dna.adapters.filesystem.source import FilesystemSource
from dna.kernel.protocols import package_doc_for_scope


def _write_manifest(path: Path, name: str, owner_tenant: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        f"metadata:\n  name: {name}\n"
        "spec:\n"
        + (f"  owner_tenant: {owner_tenant}\n" if owner_tenant else "")
        + "  visibility: public\n"
    )


def test_no_tenant_returns_platform(tmp_path):
    """Calling without tenant returns the platform Genome — current behavior."""
    _write_manifest(tmp_path / "demo" / "Genome.yaml", "demo", None)
    src = FilesystemSource(tmp_path)
    raw = asyncio.run(package_doc_for_scope(src, "demo"))
    assert raw is not None
    assert raw["metadata"]["name"] == "demo"
    assert raw["spec"].get("owner_tenant") is None


def test_with_tenant_no_overlay_falls_back_to_platform(tmp_path):
    """Tenant requested, but no tenant-published Genome → platform fallback."""
    _write_manifest(tmp_path / "demo" / "Genome.yaml", "demo", None)
    src = FilesystemSource(tmp_path)
    raw = asyncio.run(package_doc_for_scope(src, "demo", tenant="acme"))
    assert raw is not None
    assert raw["spec"].get("owner_tenant") is None  # platform


def test_with_tenant_overlay_wins(tmp_path):
    """Tenant-published Genome shadows the platform one."""
    _write_manifest(tmp_path / "demo" / "Genome.yaml", "demo", None)
    _write_manifest(
        tmp_path / "tenants" / "acme" / "scopes" / "demo" / "Genome.yaml",
        "demo", "acme",
    )
    src = FilesystemSource(tmp_path)

    # Without tenant → platform
    raw_base = asyncio.run(package_doc_for_scope(src, "demo"))
    assert raw_base is not None
    assert raw_base["spec"].get("owner_tenant") is None

    # With tenant → tenant overlay
    raw_acme = asyncio.run(package_doc_for_scope(src, "demo", tenant="acme"))
    assert raw_acme is not None
    assert raw_acme["spec"]["owner_tenant"] == "acme"


def test_only_tenant_package_exists(tmp_path):
    """Acme publishes a Genome that has NO platform counterpart."""
    _write_manifest(
        tmp_path / "tenants" / "acme" / "scopes" / "private-mod" / "Genome.yaml",
        "private-mod", "acme",
    )
    src = FilesystemSource(tmp_path)
    # acme sees their private Genome
    raw = asyncio.run(package_doc_for_scope(src, "private-mod", tenant="acme"))
    assert raw is not None
    assert raw["spec"]["owner_tenant"] == "acme"
    # platform does NOT see it (scope dir doesn't exist on filesystem)
    try:
        platform_raw = asyncio.run(package_doc_for_scope(src, "private-mod"))
    except FileNotFoundError:
        platform_raw = None
    assert platform_raw is None
    # globex doesn't see it either
    try:
        globex_raw = asyncio.run(
            package_doc_for_scope(src, "private-mod", tenant="globex")
        )
    except FileNotFoundError:
        globex_raw = None
    assert globex_raw is None


def test_kernel_instance_propagates_tenant(tmp_path):
    """Kernel.with_tenant(X).instance(scope) must propagate tenant."""
    from dna.kernel import Kernel
    from dna.adapters.filesystem.cache import FilesystemCache

    _write_manifest(tmp_path / "demo" / "Genome.yaml", "demo", None)
    _write_manifest(
        tmp_path / "tenants" / "acme" / "scopes" / "demo" / "Genome.yaml",
        "demo", "acme",
    )

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    k = Kernel.auto(source=FilesystemSource(tmp_path))
    k.cache(FilesystemCache(str(cache_dir)))

    # Bare kernel → platform
    mi_base = k.instance("demo")
    assert (mi_base.root.spec.get("owner_tenant") if mi_base.root else None) is None

    # Tenant-bound kernel → tenant Genome
    mi_acme = k.with_tenant("acme").instance("demo")
    assert mi_acme.root is not None
    assert mi_acme.root.spec["owner_tenant"] == "acme"
