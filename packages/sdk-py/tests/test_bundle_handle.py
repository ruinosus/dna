"""Contract tests for BundleHandle implementations (Phase 8 PR1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.kernel.bundle_handle import (
    BundleHandle,
    DictBundleHandle,
    FilesystemBundleHandle,
)


# ---------------------------------------------------------------------------
# Filesystem implementation
# ---------------------------------------------------------------------------


@pytest.fixture
def fs_bundle(tmp_path: Path) -> FilesystemBundleHandle:
    """Build a temp on-disk bundle with marker + script + nested ref."""
    root = tmp_path / "my-skill"
    root.mkdir()
    (root / "SKILL.md").write_text("---\nname: my-skill\n---\nthe body\n")
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "run.py").write_text("print('hello')\n")
    refs = root / "references"
    refs.mkdir()
    (refs / "spec.md").write_text("# spec\n")
    return FilesystemBundleHandle(root)


def test_fs_satisfies_protocol(fs_bundle: FilesystemBundleHandle) -> None:
    """Structural-typing check: the impl conforms to BundleHandle."""
    assert isinstance(fs_bundle, BundleHandle)


def test_fs_name_is_directory_name(fs_bundle: FilesystemBundleHandle) -> None:
    assert fs_bundle.name == "my-skill"


def test_fs_exists_and_read_text_round_trip(fs_bundle: FilesystemBundleHandle) -> None:
    assert fs_bundle.exists("SKILL.md")
    assert "the body" in fs_bundle.read_text("SKILL.md")
    assert not fs_bundle.exists("does-not-exist.md")


def test_fs_exists_for_nested_directory(fs_bundle: FilesystemBundleHandle) -> None:
    assert fs_bundle.exists("scripts")
    assert fs_bundle.exists("scripts/run.py")
    assert not fs_bundle.exists("scripts/missing.py")


def test_fs_read_text_missing_raises(fs_bundle: FilesystemBundleHandle) -> None:
    with pytest.raises(FileNotFoundError):
        fs_bundle.read_text("missing.md")


def test_fs_iter_entries_top_level(fs_bundle: FilesystemBundleHandle) -> None:
    """Non-recursive enumerates direct children only."""
    entries = sorted(fs_bundle.iter_entries())
    assert entries == ["SKILL.md", "references", "scripts"]


def test_fs_iter_entries_recursive(fs_bundle: FilesystemBundleHandle) -> None:
    """Recursive yields only files (not dirs), with posix-separator paths."""
    entries = sorted(fs_bundle.iter_entries(recursive=True))
    assert entries == ["SKILL.md", "references/spec.md", "scripts/run.py"]


def test_fs_is_file(fs_bundle: FilesystemBundleHandle) -> None:
    assert fs_bundle.is_file("SKILL.md")
    assert not fs_bundle.is_file("scripts")  # subdir, not a file
    assert fs_bundle.is_file("scripts/run.py")


def test_fs_write_text_creates_parent_dirs(fs_bundle: FilesystemBundleHandle) -> None:
    fs_bundle.write_text("new/nested/file.md", "fresh content")
    assert fs_bundle.read_text("new/nested/file.md") == "fresh content"


def test_fs_write_bytes_round_trip(fs_bundle: FilesystemBundleHandle) -> None:
    blob = b"\x00\x01\x02binary"
    fs_bundle.write_bytes("payload.bin", blob)
    assert fs_bundle.read_bytes("payload.bin") == blob


def test_fs_path_returns_real_path(fs_bundle: FilesystemBundleHandle, tmp_path: Path) -> None:
    """The escape-hatch path property returns the real filesystem dir."""
    p = fs_bundle.path
    assert p is not None
    assert p == tmp_path / "my-skill"


# ---------------------------------------------------------------------------
# Dict (in-memory) implementation
# ---------------------------------------------------------------------------


@pytest.fixture
def dict_bundle() -> DictBundleHandle:
    return DictBundleHandle(
        "fake-bundle",
        {
            "SKILL.md": "---\nname: fake-bundle\n---\ndict-backed body",
            "scripts/run.py": "print('from-dict')",
            "references/notes.md": "# notes",
        },
    )


def test_dict_satisfies_protocol(dict_bundle: DictBundleHandle) -> None:
    assert isinstance(dict_bundle, BundleHandle)


def test_dict_name(dict_bundle: DictBundleHandle) -> None:
    assert dict_bundle.name == "fake-bundle"


def test_dict_exists_top_level_and_directory_prefix(dict_bundle: DictBundleHandle) -> None:
    assert dict_bundle.exists("SKILL.md")
    assert dict_bundle.exists("scripts")  # treated as a directory prefix
    assert dict_bundle.exists("scripts/run.py")
    assert not dict_bundle.exists("missing.md")
    assert not dict_bundle.exists("scripts/other.py")


def test_dict_read_text(dict_bundle: DictBundleHandle) -> None:
    assert "dict-backed" in dict_bundle.read_text("SKILL.md")


def test_dict_read_missing_raises(dict_bundle: DictBundleHandle) -> None:
    with pytest.raises(FileNotFoundError):
        dict_bundle.read_text("missing.md")


def test_dict_iter_entries_top_level(dict_bundle: DictBundleHandle) -> None:
    entries = sorted(dict_bundle.iter_entries())
    assert entries == ["SKILL.md", "references", "scripts"]


def test_dict_iter_entries_recursive(dict_bundle: DictBundleHandle) -> None:
    entries = sorted(dict_bundle.iter_entries(recursive=True))
    assert entries == ["SKILL.md", "references/notes.md", "scripts/run.py"]


def test_dict_is_file(dict_bundle: DictBundleHandle) -> None:
    assert dict_bundle.is_file("SKILL.md")
    assert not dict_bundle.is_file("scripts")
    assert dict_bundle.is_file("scripts/run.py")


def test_dict_write_then_read(dict_bundle: DictBundleHandle) -> None:
    dict_bundle.write_text("HEARTBEAT.md", "tick tock")
    assert dict_bundle.read_text("HEARTBEAT.md") == "tick tock"


def test_dict_write_bytes(dict_bundle: DictBundleHandle) -> None:
    dict_bundle.write_bytes("blob.bin", b"\xffhi")
    assert dict_bundle.read_bytes("blob.bin") == b"\xffhi"


def test_dict_path_returns_none(dict_bundle: DictBundleHandle) -> None:
    """In-memory handles have no real path — the escape hatch returns None."""
    assert dict_bundle.path is None


# ---------------------------------------------------------------------------
# Cross-impl: a reader written against the protocol works on both
# ---------------------------------------------------------------------------


def _toy_reader(handle: BundleHandle) -> dict:
    """Tiny reader-shaped function used to prove the protocol abstraction."""
    if not handle.exists("SKILL.md"):
        return {}
    body = handle.read_text("SKILL.md")
    extras = sorted(
        e
        for e in handle.iter_entries(recursive=True)
        if e != "SKILL.md"
    )
    return {"name": handle.name, "body_chars": len(body), "extras": extras}


def test_toy_reader_works_on_filesystem(fs_bundle: FilesystemBundleHandle) -> None:
    out = _toy_reader(fs_bundle)
    assert out["name"] == "my-skill"
    assert out["extras"] == ["references/spec.md", "scripts/run.py"]


def test_toy_reader_works_on_dict(dict_bundle: DictBundleHandle) -> None:
    out = _toy_reader(dict_bundle)
    assert out["name"] == "fake-bundle"
    assert out["extras"] == ["references/notes.md", "scripts/run.py"]
