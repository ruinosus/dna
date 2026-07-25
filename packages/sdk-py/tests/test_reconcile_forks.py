"""``reconcile_forks_impl`` (s-strain-bundle-fork B2 — plane B2/reconcile): for
each of a tenant's forked bundle-entry files, a 2-way diff of the tenant's fork
(``mine``) against the CURRENT base (``base-now``) — READ-only (keep = no-op,
take-base = the existing DELETE, edit = the existing PUT; both already shipped
by B1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application.live import LiveDna
from dna.application.runtime import reconcile_forks_impl, write_bundle_entry_impl
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
async def test_no_forks_yields_empty_files(live: LiveDna) -> None:
    out = await reconcile_forks_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill", name="greeter")
    assert out == {"kind": "Skill", "name": "greeter", "files": []}


@pytest.mark.asyncio
async def test_fork_unchanged_from_base_is_identical(live: LiveDna) -> None:
    await write_bundle_entry_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill",
                                  name="greeter", entry="scripts/hello.py",
                                  content="print('base')\n")
    out = await reconcile_forks_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill", name="greeter")
    assert out["files"] == [{
        "entry": "scripts/hello.py", "status": "identical",
        "base": "print('base')\n", "mine": "print('base')\n", "binary": False,
    }]


@pytest.mark.asyncio
async def test_base_mutated_after_fork_is_diverged(live: LiveDna, tmp_path: Path) -> None:
    """The central case this task exists for: the tenant forked the file when it
    read ``print('base')\\n``; the BASE has since moved on (a later upstream
    edit). The tenant's fork content is unchanged, but it now disagrees with the
    CURRENT base — a 2-way diff against base-NOW, not the base at fork time."""
    await write_bundle_entry_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill",
                                  name="greeter", entry="scripts/hello.py",
                                  content="print('mine')\n")
    # Mutate the base file directly (simulates an upstream release moving the base on).
    base_file = tmp_path / ".dna" / _SCOPE / "skills" / "greeter" / "scripts" / "hello.py"
    base_file.write_text("print('new base')\n")

    out = await reconcile_forks_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill", name="greeter")
    assert out["files"] == [{
        "entry": "scripts/hello.py", "status": "diverged",
        "base": "print('new base')\n", "mine": "print('mine')\n", "binary": False,
    }]


@pytest.mark.asyncio
async def test_tenant_added_file_has_no_base_and_is_diverged(live: LiveDna) -> None:
    """A file the tenant forked that the base bundle never had (a tenant-added
    script) — ``fetch_bundle_entry_async(tenant=None)`` raises FileNotFoundError,
    so ``base`` is reported ``None``, never mangled into an empty string."""
    await write_bundle_entry_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill",
                                  name="greeter", entry="scripts/extra.py",
                                  content="print('mine only')\n")
    out = await reconcile_forks_impl(live, scope=_SCOPE, tenant=_WID, kind="Skill", name="greeter")
    assert out["files"] == [{
        "entry": "scripts/extra.py", "status": "diverged",
        "base": None, "mine": "print('mine only')\n", "binary": False,
    }]


@pytest.mark.asyncio
async def test_rejects_non_bundle_kind(live: LiveDna) -> None:
    with pytest.raises(ValueError, match="not a bundle Kind"):
        await reconcile_forks_impl(live, scope=_SCOPE, tenant=_WID, kind="Story", name="whatever")
