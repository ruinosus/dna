"""s-dna-source-conformance-kit — the public kit × ALL 7 source adapters.

The audit's index case: only FS/SQLite/PG were in any conformance matrix;
S3Source, CompositeFilesystemSource and AsyncSourceAdapter had NO coverage.
This suite consumes the public kit (``dna.testing``) — the same
suite an external adapter author runs — parametrized over every in-repo
adapter:

  1. FilesystemSource (read-only; factory pre-seeds the fixture tree)
  2. FilesystemWritableSource
  3. CompositeFilesystemSource (multi-base routing)
  4. SqliteSource
  5. PostgresSource               (skips when DATABASE_URL unset)
  6. AsyncSourceAdapter(sync src) (transparent-proxy semantics for real)
  7. AsyncSourceAdapter(S3Source) (moto in-process fake S3; skips w/o moto)
  8. SqlAlchemySource[sqlite]     (skips when the `sql` extra is absent)
  9. SqlAlchemySource[postgres]   (skips w/o `sql` extra or DATABASE_URL)

Known, tracked divergences (documented — not silently green):
  - sqlite × tenant_overlay_shadows_base → strict xfail (i-092: SQLite
    publish() ignores tenant, the overlay draft clobbers the base row).
  - postgres × bundle_entry_round_trip → skip (i-093: PG
    write_bundle_entry hangs under the asyncpg test pool — the
    SqlAlchemySource[postgres] row PASSES this case, evidence i-093 is a
    raw-pool artifact).
  - sqlalchemy-sqlite × tenant_overlay_shadows_base → strict xfail: the
    adapter binds to the EXISTING SQLite schema, whose documents PK lacks
    tenant — the same i-092 schema debt (the pg dialect passes: same
    logic, tenant-aware PK).
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.testing import FIXTURE_SCOPE, fixture_docs, source_conformance_suite


# ---------------------------------------------------------------------------
# Factories — one per adapter. Each returns (source, async cleanup).
# ---------------------------------------------------------------------------

async def _fs_readonly_factory():
    """Read-only FS source. The kit can't seed it through a write surface,
    so the factory pre-seeds fixture_docs() as YAML files (the documented
    read-only-factory contract)."""
    from dna.adapters.filesystem.source import FilesystemSource

    tmp = tempfile.mkdtemp(prefix="dna-kit-fsro-")
    scope_dir = Path(tmp) / FIXTURE_SCOPE
    scope_dir.mkdir(parents=True)
    for raw in fixture_docs():
        fname = "Genome.yaml" if raw["kind"] == "Genome" \
            else f"{raw['metadata']['name']}.yaml"
        (scope_dir / fname).write_text(
            yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8",
        )
    src = FilesystemSource(tmp)

    async def cleanup() -> None:
        shutil.rmtree(tmp, ignore_errors=True)

    return src, cleanup


async def _fs_writable_factory():
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.kernel import Kernel

    tmp = tempfile.mkdtemp(prefix="dna-kit-fsrw-")
    src = FilesystemWritableSource(base_dir=tmp)
    Kernel.auto(source=src)  # wires writers/readers + kernel back-ref

    async def cleanup() -> None:
        shutil.rmtree(tmp, ignore_errors=True)

    return src, cleanup


async def _composite_factory():
    """Composite over one child project tree. The child scope must exist
    (Genome.yaml marker) BEFORE construction — discovery is boot-time."""
    from dna.adapters.filesystem.composite import CompositeFilesystemSource
    from dna.kernel import Kernel

    tmp = tempfile.mkdtemp(prefix="dna-kit-comp-")
    scope_dir = Path(tmp) / "proj1" / ".dna" / FIXTURE_SCOPE
    scope_dir.mkdir(parents=True)
    package = fixture_docs()[0]
    (scope_dir / "Genome.yaml").write_text(
        yaml.safe_dump(package, allow_unicode=True), encoding="utf-8",
    )
    k = Kernel.auto()  # children need the kernel for storage routing
    src = CompositeFilesystemSource(tmp, kernel=k)
    k.source(src)

    async def cleanup() -> None:
        shutil.rmtree(tmp, ignore_errors=True)

    return src, cleanup


async def _sqlite_factory():
    from dna.adapters.sqlite.source import SqliteSource
    from dna.kernel import Kernel

    fd, tmp = tempfile.mkstemp(prefix="dna-kit-sqlite-", suffix=".db")
    os.close(fd)
    src = SqliteSource(db_path=tmp)
    await src.connect()
    Kernel.auto(source=src)

    async def cleanup() -> None:
        await src.close()
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass

    return src, cleanup


async def _postgres_factory():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set — skipping Postgres adapter")

    import asyncpg
    from dna.adapters.postgres import PostgresSource
    from dna.kernel import Kernel

    schema = f"dna_kit_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    pool = await asyncpg.create_pool(dsn)
    src = PostgresSource(pool, schema=schema)
    await src.init()
    Kernel.auto(source=src)

    async def cleanup() -> None:
        import contextlib
        with contextlib.suppress(Exception):
            c = await asyncpg.connect(dsn)
            await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            await c.close()
        with contextlib.suppress(Exception):
            await pool.close()

    return src, cleanup


class _SyncFixtureSource:
    """Minimal SYNC read-only source (core surface only) — what
    AsyncSourceAdapter exists to wrap. Serves fixture_docs()."""

    supports_readers = False

    def load_bootstrap_docs(self, scope: str, *, tenant: str | None = None):
        return [d for d in self.load_all(scope) if d["kind"] == "Genome"]

    def load_all(self, scope: str, readers: list | None = None):
        return fixture_docs() if scope == FIXTURE_SCOPE else []

    def resolve_ref(self, scope: str, ref: str) -> str:
        return ""

    def load_layer(self, scope, layer_id, layer_value, readers=None):
        return []

    def close(self) -> None:
        return None


async def _async_adapter_factory():
    from dna.adapters.async_adapter import AsyncSourceAdapter

    return AsyncSourceAdapter(_SyncFixtureSource()), None


async def _s3_moto_factory():
    """S3Source over moto's in-process fake S3, wrapped the way production
    must wrap it (AsyncSourceAdapter — S3Source is sync)."""
    try:
        import boto3
        from moto import mock_aws
    except ImportError:
        pytest.skip(
            "boto3/moto not installed — S3Source can't enter the matrix "
            "(install the sdk-py dev extras)"
        )

    from dna.adapters.async_adapter import AsyncSourceAdapter
    from dna.adapters.s3.source import S3Source

    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                "AWS_SECURITY_TOKEN", "AWS_SESSION_TOKEN"):
        os.environ.setdefault(var, "testing")
    m = mock_aws()
    m.start()
    try:
        bucket = "dna-conformance-kit"
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=bucket)
        inner = S3Source(bucket=bucket, prefix="dna", region="us-east-1")
        for raw in fixture_docs():
            key = f"dna/{FIXTURE_SCOPE}/documents/{raw['metadata']['name']}.json"
            inner._s3.put_object(
                Bucket=bucket, Key=key,
                Body=json.dumps(raw).encode("utf-8"),
            )
    except BaseException:
        m.stop()
        raise

    async def cleanup() -> None:
        m.stop()

    return AsyncSourceAdapter(inner), cleanup


async def _sqlalchemy_sqlite_factory():
    """SqlAlchemySource over aiosqlite — same tables as SqliteSource
    (s-sqlalchemy-source-production). Skips when the `sql` extra is
    absent (sqlalchemy is never a default dependency)."""
    try:
        import sqlalchemy  # noqa: F401
    except ImportError:
        pytest.skip("`sql` extra not installed — skipping SqlAlchemySource")

    from dna.adapters.sqlalchemy_ import SqlAlchemySource
    from dna.kernel import Kernel

    fd, tmp = tempfile.mkstemp(prefix="dna-kit-sa-", suffix=".db")
    os.close(fd)
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp}")
    await src.connect()
    Kernel.auto(source=src)

    async def cleanup() -> None:
        await src.close()
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass

    return src, cleanup


async def _sqlalchemy_postgres_factory():
    """SqlAlchemySource over asyncpg — same tables as PostgresSource,
    one throwaway schema per factory build."""
    try:
        import sqlalchemy  # noqa: F401
    except ImportError:
        pytest.skip("`sql` extra not installed — skipping SqlAlchemySource")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set — skipping SqlAlchemySource[postgres]")

    import asyncpg
    from dna.adapters.sqlalchemy_ import SqlAlchemySource
    from dna.kernel import Kernel

    schema = f"dna_kit_sa_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(dsn)
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    sa_url = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    src = SqlAlchemySource(sa_url, schema=schema)
    await src.connect()
    Kernel.auto(source=src)

    async def cleanup() -> None:
        import contextlib
        with contextlib.suppress(Exception):
            await src.close()
        with contextlib.suppress(Exception):
            c = await asyncpg.connect(dsn)
            await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            await c.close()

    return src, cleanup


_FACTORIES: dict[str, Any] = {
    "fs-readonly": _fs_readonly_factory,
    "fs-writable": _fs_writable_factory,
    "composite": _composite_factory,
    "sqlite": _sqlite_factory,
    "postgres": _postgres_factory,
    "async-adapter": _async_adapter_factory,
    "s3-via-async-adapter": _s3_moto_factory,
    "sqlalchemy-sqlite": _sqlalchemy_sqlite_factory,
    "sqlalchemy-postgres": _sqlalchemy_postgres_factory,
}

# (adapter id, case name) → mark; tracked divergences stay CI-visible.
_KNOWN = {
    ("sqlite", "tenant_overlay_shadows_base"): pytest.mark.xfail(
        reason="i-092: SQLite publish() ignores tenant — the overlay draft "
               "clobbers the base row (same xfail as the adapter matrix).",
        strict=True,
    ),
    ("postgres", "bundle_entry_round_trip"): pytest.mark.skip(
        reason="i-093: PG write_bundle_entry hangs under the asyncpg test pool",
    ),
    ("sqlalchemy-sqlite", "tenant_overlay_shadows_base"): pytest.mark.xfail(
        reason="i-092 (inherited schema debt, not a Core limitation): the "
               "SQLite documents PK is (scope, kind, name) without tenant — "
               "an overlay publish clobbers the base row. The pg dialect "
               "passes with the same logic (tenant-aware PK).",
        strict=True,
    ),
}


def _all_params():
    params = []
    for fid, factory in _FACTORIES.items():
        for case in source_conformance_suite(factory):
            marks = [_KNOWN[k] for k in ((fid, case.name),) if k in _KNOWN]
            params.append(pytest.param(case, id=f"{fid}-{case.name}", marks=marks))
    return params


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _all_params())
async def test_source_conformance(case):
    """The kit is the assertion body — a fresh adapter per case; skips are
    capability-driven (CaseNotApplicable → unittest.SkipTest → pytest skip)."""
    await case.run()


# ---------------------------------------------------------------------------
# Programmatic runner (the non-pytest consumption path) — smoke it once.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_source_conformance_report():
    from dna.testing import run_source_conformance

    report = await run_source_conformance(_fs_writable_factory)
    assert report.ok, f"failed: {report.failed}"
    assert "load_all_round_trip" in report.passed
    # read-only capabilities are honestly skipped, never silently passed
    skipped_names = {n for n, _ in report.skipped}
    assert "port_surface" not in skipped_names
    report.raise_if_failed()
