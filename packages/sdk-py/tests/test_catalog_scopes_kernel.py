"""Phase 3b ch1 (i-112) — kernel ``_catalog_scopes(tenant)`` cached+invalidated.

Wraps the pure ``resolve_catalog_scopes`` with the kernel's data-gathering
(Genome scan across all scopes + tenant lockfile) and a dedicated TTL cache
invalidated on Genome/lock writes. Fail-soft: any error → ``[]``.
"""
from __future__ import annotations

import asyncio

import pytest

from dna.kernel import Kernel
from dna.kernel.lock.module import (
    GenomeEntry,
    GenomeLockfile,
    resolve_lockfile_root,
    write_lockfile,
)


def _pkg_row(name, *, owner_tenant=None, mandatory=False):
    return {
        "kind": "Genome",
        "metadata": {"name": name},
        "spec": {
            "owner_tenant": owner_tenant,
            "mandatory": mandatory,
            "default_agent": "x",
        },
    }


def _make_kernel(scope_to_pkgs):
    """Kernel whose mock source yields ``scope_to_pkgs[scope]`` Genome rows and
    counts how many times ``query`` is invoked (cache-hit assertions)."""
    from unittest.mock import MagicMock

    calls = {"query": 0, "scopes": 0}

    async def _fake_query(scope, kind, **kwargs):
        calls["query"] += 1
        for r in scope_to_pkgs.get(scope, []):
            if r.get("kind") == kind:
                yield r

    async def _list_scopes():
        calls["scopes"] += 1
        return list(scope_to_pkgs)

    src = MagicMock()
    src.query = _fake_query
    src.list_scopes = _list_scopes

    k = Kernel()
    k._source = src  # type: ignore[assignment]
    return k, calls


def _write_lock(tmp_path, tenant, entries):
    root = resolve_lockfile_root(str(tmp_path))
    lock = GenomeLockfile(tenant=tenant, packages=entries)
    write_lockfile(lock, root)


@pytest.fixture(autouse=True)
def _lockdir(tmp_path, monkeypatch):
    monkeypatch.setenv("DNA_LOCKFILE_DIR", str(tmp_path / "locks"))
    yield


def test_mandatory_platform_plus_lock(tmp_path):
    _write_lock(
        tmp_path, "acme",
        [GenomeEntry(
            source="acme/hr", version_constraint="*",
            resolved_version="1.0.0", resolved_sha256="x",
            installed_at="now", target_tenant="acme",
        )],
    )
    k, _calls = _make_kernel({
        "voice-core": [_pkg_row("voice-core", mandatory=True)],
        "hr": [_pkg_row("hr", owner_tenant="acme")],
        "proj": [],
    })
    out = asyncio.run(k._catalog_scopes("acme", exclude={"proj"}))
    assert out == [("hr", "acme"), ("voice-core", None)]


def test_second_call_hits_cache(tmp_path):
    k, calls = _make_kernel({
        "voice-core": [_pkg_row("voice-core", mandatory=True)],
    })
    out1 = asyncio.run(k._catalog_scopes("acme"))
    n_after_first = calls["query"]
    assert n_after_first > 0
    out2 = asyncio.run(k._catalog_scopes("acme"))
    assert out1 == out2 == [("voice-core", None)]
    # No new source queries on the 2nd call — served from cache.
    assert calls["query"] == n_after_first


def test_write_package_invalidates_cache(tmp_path):
    k, calls = _make_kernel({
        "voice-core": [_pkg_row("voice-core", mandatory=True)],
    })
    asyncio.run(k._catalog_scopes("acme"))
    n = calls["query"]
    # Explicit invalidation (what write_document(kind=Genome) calls).
    k._invalidate_catalog_cache()
    asyncio.run(k._catalog_scopes("acme"))
    assert calls["query"] > n  # cache was dropped → re-read


def test_tenant_isolation(tmp_path):
    _write_lock(
        tmp_path, "acme",
        [GenomeEntry(
            source="acme/hr", version_constraint="*",
            resolved_version="1.0.0", resolved_sha256="x",
            installed_at="now", target_tenant="acme",
        )],
    )
    # innovec has no lock → only mandatory platform package surfaces.
    k, _ = _make_kernel({
        "voice-core": [_pkg_row("voice-core", mandatory=True)],
        "hr": [_pkg_row("hr", owner_tenant="acme")],
    })
    acme = asyncio.run(k._catalog_scopes("acme"))
    innovec = asyncio.run(k._catalog_scopes("innovec"))
    assert ("hr", "acme") in acme
    assert ("hr", "acme") not in innovec
    assert innovec == [("voice-core", None)]


def test_fail_soft_on_source_error(tmp_path):
    k = Kernel()

    class _Boom:
        def list_scopes(self):
            raise RuntimeError("boom")

    k._source = _Boom()  # type: ignore[assignment]
    out = asyncio.run(k._catalog_scopes("acme"))
    assert out == []


def test_invalidate_single_tenant_leaves_others(tmp_path):
    k, calls = _make_kernel({
        "voice-core": [_pkg_row("voice-core", mandatory=True)],
    })
    asyncio.run(k._catalog_scopes("acme"))
    asyncio.run(k._catalog_scopes("innovec"))
    n = calls["query"]
    k._invalidate_catalog_cache("acme")
    # innovec still cached.
    asyncio.run(k._catalog_scopes("innovec"))
    assert calls["query"] == n
    # acme re-reads.
    asyncio.run(k._catalog_scopes("acme"))
    assert calls["query"] > n
