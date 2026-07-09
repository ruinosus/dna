"""i-006 regression — `dna source diff/push` against REAL adapters.

The bug: ``digest_manifest`` read the base layer via
``load_layer(scope, "tenant", "__base__")``, but the real adapters
(FilesystemSource, SqliteSource) treat ``load_layer`` strictly as a tenant
OVERLAY read — the ``"__base__"`` sentinel never maps to the base scope docs.
Both sides of a diff therefore digested ``{}`` and diff/push were no-ops by
construction. The duck-typed fakes in test_digest_manifest / test_source_diff /
test_source_push masked it by returning base docs regardless of layer_value.

These tests reproduce the bug against the real adapters (RED before the fix):
two sources with DIVERGENT BASE content must produce a non-empty diff, and
push must converge them. The tenant-overlay contract (explicit ``tenant=``
still reads the overlay via ``load_layer``) is pinned too.
"""
from __future__ import annotations

import asyncio

import yaml

from dna.adapters.filesystem import FilesystemSource
from dna.adapters.sqlite import SqliteSource
from dna.kernel import Kernel


def _agent(name: str, instruction: str) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/helix/v1", "kind": "Agent",
        "metadata": {"name": name},
        "spec": {"model": "m", "instruction": instruction},
    }


def _write_fs_scope(root, scope: str, docs: list[dict]) -> None:
    scope_dir = root / scope
    scope_dir.mkdir(parents=True, exist_ok=True)
    for d in docs:
        (scope_dir / f"{d['metadata']['name']}.yaml").write_text(
            yaml.safe_dump(d, sort_keys=False)
        )


async def _sqlite_source(db_path, docs: list[dict], scope: str) -> SqliteSource:
    src = SqliteSource(str(db_path))
    await src.connect()
    for d in docs:
        await src.save_document(scope, d["kind"], d["metadata"]["name"], d)
    return src


# ── diff: FS base divergence (the i-006 repro) ────────────────────────


def test_fs_diff_detects_base_divergence(tmp_path):
    """Two FS sources whose BASE scopes diverge → diff must detect it.

    Pre-fix: load_layer(scope,'tenant','__base__') found no
    tenants/__base__/scopes/<s> dir on either side → both manifests {} →
    'in sync' even though the trees differ (the cli-tour repro)."""
    _write_fs_scope(tmp_path / "a", "scope-x",
                    [_agent("code-reviewer", "Review code v2."),
                     _agent("new-one", "hi")])
    _write_fs_scope(tmp_path / "b", "scope-x",
                    [_agent("code-reviewer", "Review code v1.")])

    k = Kernel.auto()
    k.source(FilesystemSource(tmp_path / "a"))

    async def _run():
        man_a = await k.digest_manifest("scope-x")
        man_b = await k.digest_manifest(
            "scope-x", source=FilesystemSource(tmp_path / "b"))
        return man_a, man_b

    man_a, man_b = asyncio.run(_run())
    assert man_a, "base manifest of source A must not be empty (i-006)"
    diff = Kernel.diff_manifests(man_a, man_b)
    assert ("Agent", "new-one") in diff["added"]
    assert ("Agent", "code-reviewer") in diff["changed"]
    assert diff["removed"] == []


def test_fs_diff_in_sync_is_empty_but_manifest_is_not(tmp_path):
    """In-sync sources → empty diff, but because the manifests MATCH,
    not because both are empty (the pre-fix failure mode)."""
    docs = [_agent("code-reviewer", "Review code.")]
    _write_fs_scope(tmp_path / "a", "scope-x", docs)
    _write_fs_scope(tmp_path / "b", "scope-x", docs)

    k = Kernel.auto()
    k.source(FilesystemSource(tmp_path / "a"))

    async def _run():
        return (await k.digest_manifest("scope-x"),
                await k.digest_manifest(
                    "scope-x", source=FilesystemSource(tmp_path / "b")))

    man_a, man_b = asyncio.run(_run())
    assert man_a == man_b
    assert man_a != {}, "manifests must reflect real base content (i-006)"


def test_fs_diff_scope_missing_in_other_is_all_added(tmp_path):
    """Other source has no such scope at all → everything counts as added
    (digest of a missing scope is {}, not an error)."""
    _write_fs_scope(tmp_path / "a", "scope-x", [_agent("solo", "hi")])
    (tmp_path / "b").mkdir()

    k = Kernel.auto()
    k.source(FilesystemSource(tmp_path / "a"))

    async def _run():
        return (await k.digest_manifest("scope-x"),
                await k.digest_manifest(
                    "scope-x", source=FilesystemSource(tmp_path / "b")))

    man_a, man_b = asyncio.run(_run())
    diff = Kernel.diff_manifests(man_a, man_b)
    assert diff["added"] == [("Agent", "solo")]


# ── diff: SQLite base divergence ──────────────────────────────────────


def test_sqlite_diff_detects_base_divergence(tmp_path):
    """Same repro against SqliteSource — its load_layer reads the
    layer_documents table (overlay rows only), so pre-fix both sides
    digested {} too."""
    async def _run():
        a = await _sqlite_source(
            tmp_path / "a.db",
            [_agent("code-reviewer", "Review code v2."), _agent("new-one", "hi")],
            "scope-x")
        b = await _sqlite_source(
            tmp_path / "b.db",
            [_agent("code-reviewer", "Review code v1.")],
            "scope-x")
        try:
            k = Kernel.auto()
            k.source(a)
            man_a = await k.digest_manifest("scope-x")
            man_b = await k.digest_manifest("scope-x", source=b)
            return man_a, man_b
        finally:
            await a.close()
            await b.close()

    man_a, man_b = asyncio.run(_run())
    assert man_a, "base manifest of sqlite source A must not be empty (i-006)"
    diff = Kernel.diff_manifests(man_a, man_b)
    assert ("Agent", "new-one") in diff["added"]
    assert ("Agent", "code-reviewer") in diff["changed"]


# ── push: FS → SQLite converges (same digest, same bug) ───────────────


def test_push_fs_to_sqlite_converges(tmp_path):
    """push_scope from a real FS source-of-truth to a real writable SQLite
    target: pre-fix the diff was empty → applied == [] and the target stayed
    stale forever. Post-fix: writes happen and a re-diff is genuinely in
    sync (matching non-empty manifests)."""
    _write_fs_scope(tmp_path / "fs", "scope-x",
                    [_agent("code-reviewer", "Review code v2."),
                     _agent("new-one", "hi")])

    async def _run():
        to = await _sqlite_source(
            tmp_path / "to.db", [_agent("code-reviewer", "Review code v1.")],
            "scope-x")
        try:
            k = Kernel.auto()
            k.source(FilesystemSource(tmp_path / "fs"))
            out = await k.push_scope("scope-x", to)
            man_fs = await k.digest_manifest("scope-x")
            man_to = await k.digest_manifest("scope-x", source=to)
            return out, man_fs, man_to
        finally:
            await to.close()

    out, man_fs, man_to = asyncio.run(_run())
    assert ("write", "Agent", "new-one") in out["applied"]
    assert ("write", "Agent", "code-reviewer") in out["applied"]
    assert man_fs == man_to
    assert man_fs != {}, "post-push sync must be real content, not {}=={} (i-006)"


# ── tenant overlay contract preserved ─────────────────────────────────


def test_fs_explicit_tenant_still_reads_overlay(tmp_path):
    """The fix is ONLY about the default-base read: an explicit tenant=
    must keep digesting the tenant OVERLAY via load_layer (overlays stay
    diffable)."""
    root = tmp_path / "a"
    _write_fs_scope(root, "scope-x", [_agent("base-doc", "base")])
    overlay_dir = root / "tenants" / "acme" / "scopes" / "scope-x"
    overlay_dir.mkdir(parents=True)
    overlay = _agent("acme-doc", "overlay")
    (overlay_dir / "acme-doc.yaml").write_text(
        yaml.safe_dump(overlay, sort_keys=False))

    k = Kernel.auto()
    k.source(FilesystemSource(root))

    async def _run():
        return (await k.digest_manifest("scope-x"),
                await k.digest_manifest("scope-x", tenant="acme"))

    man_base, man_tenant = asyncio.run(_run())
    assert set(man_base) == {("Agent", "base-doc")}
    assert ("Agent", "acme-doc") in man_tenant
