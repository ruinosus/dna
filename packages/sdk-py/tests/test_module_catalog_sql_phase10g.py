"""Phase 10g — Module catalog parity across filesystem + SQLite + Postgres.

Filesystem already has implicit coverage via the harness E2E tests
(test_module_versioning_phase10 + the live curl flow we shipped).
This file exercises the SQLite adapter end-to-end (no network) and
sanity-checks the module_lock helper across both kinds of base_dir.

Postgres parity is left for the harness integration suite — requires
a live Postgres at :5434 which the SDK suite shouldn't depend on.
"""
from __future__ import annotations

import asyncio

import pytest

from dna.kernel.lock.module import resolve_lockfile_root


# ── module_lock.resolve_lockfile_root ────────────────────────────────


def test_resolve_lockfile_root_prefers_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DNA_LOCKFILE_DIR", str(tmp_path / "explicit"))
    out = resolve_lockfile_root(source_base_dir=tmp_path / "fs-base")
    assert out == tmp_path / "explicit"


def test_resolve_lockfile_root_falls_back_to_source_base(tmp_path, monkeypatch):
    monkeypatch.delenv("DNA_LOCKFILE_DIR", raising=False)
    out = resolve_lockfile_root(source_base_dir=tmp_path / "fs-base")
    assert out == tmp_path / "fs-base"


def test_resolve_lockfile_root_default_when_nothing(monkeypatch):
    monkeypatch.delenv("DNA_LOCKFILE_DIR", raising=False)
    out = resolve_lockfile_root(source_base_dir=None)
    assert str(out).endswith("/.cache/dna/locks")


# ── SQLite adapter — full Phase 10g surface ──────────────────────────


def _package(name: str, version: str, owner: str = "acme") -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": name},
        "spec": {
            "owner_tenant": owner, "visibility": "private",
            "version": version, "default_agent": "x",
        },
    }


@pytest.fixture
def sqlite_src(tmp_path):
    """Yields a connected sqlite-dialect SqlAlchemySource against a temp DB."""
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    src = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    asyncio.run(src.connect())
    yield src
    asyncio.run(src.close())


def test_sqlite_publish_then_list_returns_in_order(sqlite_src):
    asyncio.run(sqlite_src.save_document(
        "demo", "Genome", "demo", _package("demo", "1.0.0"), tenant="acme",
    ))
    asyncio.run(sqlite_src.save_document(
        "demo", "Genome", "demo", _package("demo", "1.1.0"), tenant="acme",
    ))
    versions = asyncio.run(sqlite_src.list_module_versions("demo", tenant="acme"))
    assert [v["version"] for v in versions] == ["1.0.0", "1.1.0"]
    assert all(v["deprecated"] is False for v in versions)


def test_sqlite_republish_same_version_raises(sqlite_src):
    from dna.kernel.protocols import VersionAlreadyPublished

    asyncio.run(sqlite_src.save_document(
        "demo", "Genome", "demo", _package("demo", "1.0.0"), tenant="acme",
    ))
    with pytest.raises(VersionAlreadyPublished, match="1.0.0"):
        asyncio.run(sqlite_src.save_document(
            "demo", "Genome", "demo", _package("demo", "1.0.0"), tenant="acme",
        ))


def test_sqlite_get_module_version_round_trip(sqlite_src):
    asyncio.run(sqlite_src.save_document(
        "demo", "Genome", "demo", _package("demo", "1.4.2"), tenant="acme",
    ))
    raw = asyncio.run(sqlite_src.get_module_version("demo", "1.4.2", tenant="acme"))
    assert raw is not None
    assert raw["spec"]["version"] == "1.4.2"
    assert raw["spec"]["owner_tenant"] == "acme"


def test_sqlite_get_missing_returns_none(sqlite_src):
    raw = asyncio.run(sqlite_src.get_module_version("demo", "9.9.9", tenant="acme"))
    assert raw is None


def test_sqlite_deprecate_flips_flag_and_persists_message(sqlite_src):
    asyncio.run(sqlite_src.save_document(
        "demo", "Genome", "demo", _package("demo", "1.0.0"), tenant="acme",
    ))
    ok = asyncio.run(sqlite_src.deprecate_module_version(
        "demo", "1.0.0", tenant="acme", message="use 2.x",
    ))
    assert ok is True
    raw = asyncio.run(sqlite_src.get_module_version("demo", "1.0.0", tenant="acme"))
    assert raw["spec"]["deprecated"] is True
    assert raw["spec"]["deprecated_message"] == "use 2.x"


def test_sqlite_deprecate_missing_returns_false(sqlite_src):
    ok = asyncio.run(sqlite_src.deprecate_module_version(
        "nope", "1.0.0", tenant="acme",
    ))
    assert ok is False


def test_sqlite_unversioned_module_does_not_appear_in_versions(sqlite_src):
    """Phase 9 unversioned publish (spec.version=null) must NOT enter the
    Phase 10 catalog timeline — partial unique index would constrain
    it to a single NULL row anyway, but list_module_versions filters
    explicitly with WHERE semver IS NOT NULL."""
    raw = _package("demo", "1.0.0")
    raw["spec"]["version"] = None
    asyncio.run(sqlite_src.save_document(
        "demo", "Genome", "demo", raw, tenant="acme",
    ))
    versions = asyncio.run(sqlite_src.list_module_versions("demo", tenant="acme"))
    assert versions == []


def test_sqlite_tenant_isolation_in_versions(sqlite_src):
    """acme's 1.0.0 must not appear in globex's version listing."""
    asyncio.run(sqlite_src.save_document(
        "demo", "Genome", "demo", _package("demo", "1.0.0", "acme"), tenant="acme",
    ))
    asyncio.run(sqlite_src.save_document(
        "demo", "Genome", "demo", _package("demo", "2.0.0", "globex"), tenant="globex",
    ))
    acme_versions = asyncio.run(sqlite_src.list_module_versions("demo", tenant="acme"))
    globex_versions = asyncio.run(sqlite_src.list_module_versions("demo", tenant="globex"))
    assert [v["version"] for v in acme_versions] == ["1.0.0"]
    assert [v["version"] for v in globex_versions] == ["2.0.0"]
