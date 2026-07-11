"""i-006 companion — build_source_from_env must resolve relative fs:// URLs.

``urlparse("fs://./copy")`` puts ``.`` in netloc and ``/copy`` in path;
dropping the netloc silently produced the ABSOLUTE ``/copy``, so
``dna source diff fs://./copy`` digested a nonexistent dir as ``{}`` and
reported a bogus "in sync". The netloc must be re-joined to the path —
the same rule ``source_cmd._resolve_url_to_path`` already applies.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from dna.kernel import Kernel

from dna_cli._ctx import build_source_from_env


def _resolved_base(url: str) -> Path:
    src = asyncio.run(build_source_from_env(Kernel.auto(), _source_url=url))
    return Path(src.base_dir)


def test_fs_url_with_relative_dot_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "copy").mkdir()
    assert _resolved_base("fs://./copy") == (tmp_path / "copy").resolve()


def test_fs_url_with_absolute_path(tmp_path):
    assert _resolved_base(f"fs://{tmp_path}/scopes") == (
        (tmp_path / "scopes").resolve()
    )


def test_file_url_bare_netloc(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _resolved_base("file://scopes") == (tmp_path / "scopes").resolve()


def test_plain_relative_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _resolved_base("./scopes") == (tmp_path / "scopes").resolve()


# ── the public factory now ACTUALLY supports sqlite/postgres (s-dx-kernel-from-config)

def test_public_factory_builds_and_connects_sqlite(tmp_path):
    """`source_from_url("sqlite://…")` returns a live, migrated SqlAlchemySource
    — the scheme the CLI used to reject with 'unsupported'."""
    import asyncio

    # The sqlite adapter rides the optional `sqlite` extra (sqlalchemy +
    # aiosqlite); skip where it isn't installed (e.g. the bare CLI CI job).
    import pytest
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("aiosqlite")

    from dna.adapters.source_url import source_from_url
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    db = tmp_path / "dev.db"
    src = asyncio.run(source_from_url(f"sqlite:///{db}"))
    assert isinstance(src, SqlAlchemySource)
    # connect() ran the migrations → the schema-control table exists.
    scopes = asyncio.run(src.list_scopes())
    assert isinstance(scopes, list)
    asyncio.run(src.close())


def test_public_factory_rejects_unknown_scheme():
    import asyncio

    from dna.adapters.source_url import UnsupportedSourceScheme, source_from_url

    try:
        asyncio.run(source_from_url("mysql://nope"))
        assert False, "expected UnsupportedSourceScheme"
    except UnsupportedSourceScheme as exc:
        assert "mysql" in str(exc)


def test_cli_source_from_env_now_accepts_sqlite(tmp_path):
    """The CLI boot path delegates to the public factory, so sqlite:// no longer
    raises the old ClickException."""
    import pytest
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("aiosqlite")

    src = asyncio.run(
        build_source_from_env(Kernel.auto(), _source_url=f"sqlite:///{tmp_path/'x.db'}")
    )
    from dna.adapters.sqlalchemy_ import SqlAlchemySource
    assert isinstance(src, SqlAlchemySource)
    asyncio.run(src.close())
