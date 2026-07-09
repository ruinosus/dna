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
