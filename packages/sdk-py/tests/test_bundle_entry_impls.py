"""Application use-cases for bundle entries (s-strain-bundle-fork B2):
list/read/write/revert a bundle-file entry, generic over any bundle Kind, with
the SAME LayerPolicy governance as plane A's spec overrides (a fork on a
LOCKED Kind must be vetoed).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application.live import LiveDna
from dna.application.runtime import (
    list_bundle_entries_impl, read_bundle_entry_impl,
    revert_bundle_entry_impl, write_bundle_entry_impl,
)
from dna.kernel import Kernel

_SCOPE = "test-bundle"
_WID = "ws-bundle0000000000000001"


@pytest.fixture()
def live(tmp_path: Path) -> LiveDna:
    base = tmp_path / ".dna"
    d = base / _SCOPE / "skills" / "greeter"
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: greeter\n---\nBase.\n")
    (d / "scripts" / "hello.py").write_text("print('base')\n")
    (base / "_lib").mkdir(parents=True, exist_ok=True)
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    return LiveDna(base_scope=_SCOPE, kernel=k, provider=None,
                   vendor_workspace=None, workspace_definitions_base=_SCOPE)


@pytest.mark.asyncio
async def test_list_flags_forked_entries(live: LiveDna) -> None:
    out = await list_bundle_entries_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill", name="greeter")
    assert {"entry": "scripts/hello.py", "overridden": False} in out["entries"]


@pytest.mark.asyncio
async def test_write_then_read_shows_override(live: LiveDna) -> None:
    await write_bundle_entry_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill",
                                  name="greeter", entry="scripts/hello.py", content="print('mine')\n")
    got = await read_bundle_entry_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill",
                                       name="greeter", entry="scripts/hello.py")
    assert got["content"] == "print('mine')\n" and got["overridden"] is True


@pytest.mark.asyncio
async def test_revert_falls_back_to_base(live: LiveDna) -> None:
    await write_bundle_entry_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill",
                                  name="greeter", entry="scripts/hello.py", content="print('mine')\n")
    await revert_bundle_entry_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill",
                                   name="greeter", entry="scripts/hello.py")
    got = await read_bundle_entry_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill",
                                       name="greeter", entry="scripts/hello.py")
    assert got["content"] == "print('base')\n" and got["overridden"] is False


@pytest.mark.asyncio
async def test_write_rejects_non_bundle_kind(live: LiveDna) -> None:
    with pytest.raises(ValueError, match="not a bundle Kind"):
        await write_bundle_entry_impl(live, scope=_SCOPE, tenant=_WID, kind="Story",
                                      name="whatever", entry="x.txt", content="x")


@pytest.mark.asyncio
async def test_write_requires_tenant(live: LiveDna) -> None:
    with pytest.raises(ValueError, match="tenant is required"):
        await write_bundle_entry_impl(live, scope=_SCOPE, tenant=None, kind="Skill",
                                      name="greeter", entry="scripts/hello.py", content="x")


@pytest.mark.asyncio
async def test_write_forbidden_on_locked_skill_layer_policy(tmp_path: Path) -> None:
    """A fork of a bundle-file entry on a LOCKED Kind must be vetoed the SAME way
    a spec-override write is (plane A parity) — LayerPolicy governance applies
    uniformly regardless of which storage pattern the Kind uses."""
    from dna.kernel.protocols import LayerPolicyViolationError

    base = tmp_path / ".dna"
    d = base / _SCOPE / "skills" / "greeter"
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: greeter\n---\nBase.\n")
    (d / "scripts" / "hello.py").write_text("print('base')\n")
    policies_dir = base / _SCOPE / "policies"
    policies_dir.mkdir(parents=True, exist_ok=True)
    (policies_dir / "tenant-default.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/policy/v1\n"
        "kind: LayerPolicy\n"
        "metadata:\n"
        "  name: tenant-default\n"
        "spec:\n"
        "  layer_id: tenant\n"
        "  policies:\n"
        "    agentskills-skill: locked\n"
    )
    (base / "_lib").mkdir(parents=True, exist_ok=True)
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    live = LiveDna(base_scope=_SCOPE, kernel=k, provider=None,
                   vendor_workspace=None, workspace_definitions_base=_SCOPE)

    with pytest.raises(LayerPolicyViolationError, match="LOCKED"):
        await write_bundle_entry_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill",
                                      name="greeter", entry="scripts/hello.py",
                                      content="print('mine')\n")
