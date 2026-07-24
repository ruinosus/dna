"""Generic per-tenant bundle-entry list/delete primitives (s-strain-bundle-fork B1).

Backed by the filesystem writable source (no pg needed); the pg dialect is proven
in test_bundle_entry_overlay_pg.py. Uses a minimal bundle Kind via the Skill Kind
(a real bundle Kind), asserting the primitives are generic (routed by kind/container).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.kernel import Kernel

_SCOPE = "test-bundle"
_WID = "ws-bundle0000000000000001"


@pytest.fixture()
def kernel(tmp_path: Path) -> Kernel:
    base = tmp_path / ".dna"
    (base / _SCOPE / "skills" / "greeter").mkdir(parents=True)
    (base / _SCOPE / "skills" / "greeter" / "SKILL.md").write_text(
        "---\nname: greeter\n---\nBase greeter skill.\n")
    (base / _SCOPE / "skills" / "greeter" / "scripts").mkdir()
    (base / _SCOPE / "skills" / "greeter" / "scripts" / "hello.py").write_text("print('base')\n")
    (base / "_lib").mkdir(parents=True, exist_ok=True)
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    return k


@pytest.mark.asyncio
async def test_list_composes_base_and_tenant(kernel: Kernel) -> None:
    base_list = kernel.list_bundle_entries(_SCOPE, "Skill", "greeter")
    assert "scripts/hello.py" in base_list
    # tenant adds a new entry
    await kernel.write_bundle_entry_async(
        _SCOPE, "Skill", "greeter", "scripts/extra.py", "print('mine')\n", tenant=_WID)
    composed = kernel.list_bundle_entries(_SCOPE, "Skill", "greeter", tenant=_WID)
    assert "scripts/hello.py" in composed and "scripts/extra.py" in composed
    # base list is unaffected
    assert "scripts/extra.py" not in kernel.list_bundle_entries(_SCOPE, "Skill", "greeter")


@pytest.mark.asyncio
async def test_list_only_tenant_returns_override_subset(kernel: Kernel) -> None:
    await kernel.write_bundle_entry_async(
        _SCOPE, "Skill", "greeter", "scripts/hello.py", "print('mine')\n", tenant=_WID)
    only = kernel.list_bundle_entries(_SCOPE, "Skill", "greeter", tenant=_WID, only_tenant=True)
    assert only == ["scripts/hello.py"]


@pytest.mark.asyncio
async def test_delete_reverts_to_base(kernel: Kernel) -> None:
    await kernel.write_bundle_entry_async(
        _SCOPE, "Skill", "greeter", "scripts/hello.py", "print('mine')\n", tenant=_WID)
    assert kernel.fetch_bundle_entry(_SCOPE, "Skill", "greeter", "scripts/hello.py", tenant=_WID) \
        == b"print('mine')\n"
    existed = kernel.delete_bundle_entry(_SCOPE, "Skill", "greeter", "scripts/hello.py", tenant=_WID)
    assert existed is True
    # falls back to base
    assert kernel.fetch_bundle_entry(_SCOPE, "Skill", "greeter", "scripts/hello.py", tenant=_WID) \
        == b"print('base')\n"


@pytest.mark.asyncio
async def test_write_bundle_entry_traversal_blocked(kernel: Kernel, tmp_path: Path) -> None:
    """A crafted `entry` with '..' segments must never write outside the
    bundle root — regression for the write/delete guard that previously only
    checked against `base_dir` as a whole (letting a tenant clobber a
    DIFFERENT bundle, including the shared base other tenants inherit).

    bundle_root for (scope, "Skill", "greeter") is `<base>/test-bundle/skills
    /greeter`; `../../victim/SKILL.md` resolves to `<base>/test-bundle/victim
    /SKILL.md` — a sibling bundle dir, which must remain untouched."""
    victim_dir = tmp_path / ".dna" / _SCOPE / "victim"
    victim_dir.mkdir(parents=True)
    victim_file = victim_dir / "SKILL.md"
    victim_file.write_text("original\n")

    traversal_entry = "../../victim/SKILL.md"
    with pytest.raises(FileNotFoundError):
        await kernel.write_bundle_entry_async(
            _SCOPE, "Skill", "greeter", traversal_entry, "pwned\n")
    assert victim_file.read_text() == "original\n"
    assert not (tmp_path / ".dna" / _SCOPE / "victim" / "SKILL.md.tmp").exists()


@pytest.mark.asyncio
async def test_delete_bundle_entry_traversal_blocked(kernel: Kernel, tmp_path: Path) -> None:
    """Same guard, delete side: a traversal `entry` must raise rather than
    deleting a file outside the bundle root."""
    victim_dir = tmp_path / ".dna" / _SCOPE / "victim"
    victim_dir.mkdir(parents=True)
    victim_file = victim_dir / "SKILL.md"
    victim_file.write_text("original\n")

    traversal_entry = "../../victim/SKILL.md"
    with pytest.raises(FileNotFoundError):
        kernel.delete_bundle_entry(_SCOPE, "Skill", "greeter", traversal_entry)
    assert victim_file.exists()
    assert victim_file.read_text() == "original\n"
