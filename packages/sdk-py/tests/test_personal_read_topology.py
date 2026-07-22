"""i-069 — personal reads must find the caller's memories in the EXACT
production topology (the test #209 lacked).

Production shape (dna-cloud, 2026-07-21): the console is bound to a per-
workspace scope ``tenant-<ws>`` whose Genome declares ``parent_scope`` →
``dna-development`` (i-058); the caller's personal memories live in the
PARENT scope's ``personal:<oid>`` partition — because every personal WRITE
resolves through ``_resolve_memory_target`` to ``live.base_scope``. Two
distinct read-path defects made those memories invisible while the rows sat
intact in the store:

1. **Scope retargeting** — a face that forwarded its (workspace) scope into a
   personal READ (``GET /v1/memories/personal?scope=…`` since 0.25.0) targeted
   ``(tenant-<ws>, personal:<oid>)``, a pair nothing ever writes to (Engram is
   ``scope_inheritable: false`` — memory never inherits across scopes), and
   got an honest-looking EMPTY result. Fix: ``_resolve_memory_target`` PINS
   personal ops to ``live.base_scope`` — reads and writes structurally resolve
   the same home.

2. **Overlay starvation at the limit** — every tenant-aware source query
   merges ``base_minus_shadow + overlay`` with the overlay APPENDED, then cut
   ``docs[:limit]``: as soon as the base leg alone reached the limit, the
   caller's OWN rows were the ones dropped. Recall's lexical fallback (the
   production mode — no search provider is registered on the hosted MCP,
   ``degraded: true``) scans with ``limit=500``, so a grown base silently
   emptied every personal recall. Fix: ``_page_unordered_union`` — on an
   UNORDERED limited union the overlay survives first (ordered queries keep
   the caller's explicit order end-to-end, unchanged).

Anti-vacuity: each test asserts the exact memory NAME round-trips, and the
starvation tests fail on v0.25.0 (and v0.24.0 — latent) with the fix reverted.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import yaml

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application import LiveDna
from dna.application.runtime import (
    list_memories_impl,
    recall_impl,
    remember_impl,
)
from dna.kernel import Kernel
from dna.memory import recall

BASE = "dna-development"
CHILD = "tenant-ws-child"
OID = "oid-founder"
PERSONAL = f"personal:{OID}"
_REASON = "a concrete reason long enough for the affect validator to accept it in full"


def _write_doc(path: Path, kind: str, name: str, spec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump({
        "apiVersion": "dna/v1", "kind": kind,
        "metadata": {"name": name}, "spec": spec,
    }, default_flow_style=False))


@pytest.fixture()
def live(tmp_path: Path) -> LiveDna:
    """The production topology: base scope + child workspace scope whose
    Genome declares ``parent_scope`` → base (i-058), Model B multi-workspace."""
    src_dir = tmp_path / ".dna"
    _write_doc(src_dir / BASE / "Genome.yaml", "Genome", BASE, {})
    _write_doc(src_dir / CHILD / "Genome.yaml", "Genome", CHILD,
               {"parent_scope": BASE})
    kernel = Kernel.auto()
    kernel.source(FilesystemWritableSource(base_dir=str(src_dir)))
    return LiveDna(
        base_scope=BASE, kernel=kernel, provider=None,
        vendor_workspace="vendor-ws", workspace_scope_prefix="tenant-",
        workspace_definitions_base=BASE,
    )


# ── 1. scope retargeting — personal reads pinned to the personal home ───────


@pytest.mark.asyncio
async def test_personal_read_from_workspace_scope_finds_parent_memories(live):
    """THE regression topology: memory written personal (lands at base_scope),
    read back with the WORKSPACE scope forwarded — as the 0.25.0 REST face
    does. Both the list and recall must find it; before the pin they read the
    (child, personal) pair nothing writes to and returned empty."""
    out = await remember_impl(
        live, "the founder's private note about the genome chain xyzpin",
        None, area="identity", memory_scope="personal", oid=OID,
    )
    name = out["name"]

    lst = await list_memories_impl(
        live, CHILD, memory_scope="personal", oid=OID,
    )
    assert lst["scope"] == BASE  # the personal home, never the forwarded scope
    by_name = {m["name"]: m for m in lst["memories"]}
    assert name in by_name, lst["memories"]
    assert by_name[name]["personal"] is True

    res = await recall_impl(
        live, "genome chain xyzpin", CHILD, 5,
        memory_scope="personal", oid=OID,
    )
    assert res["scope"] == BASE
    hits = {h["name"]: h for h in res["hits"]}
    assert name in hits, res["hits"]
    assert hits[name]["personal"] is True


@pytest.mark.asyncio
async def test_personal_write_and_read_agree_on_home_whatever_scope_faces_pass(live):
    """Reads and writes resolve the SAME home even when different faces
    forward different scopes — the class of drift behind the production
    'write works, read is empty' symptom."""
    out = await remember_impl(
        live, "written under a forwarded workspace scope xyzagree",
        CHILD, memory_scope="personal", oid=OID,
    )
    lst = await list_memories_impl(
        live, None, memory_scope="personal", oid=OID,
    )
    assert out["name"] in {m["name"] for m in lst["memories"]}


@pytest.mark.asyncio
async def test_workspace_memory_scope_still_honors_explicit_scope(live):
    """The pin is personal-only: a WORKSPACE memory op keeps the explicit
    scope exactly as before."""
    out = await remember_impl(live, "workspace note in the child scope", CHILD)
    lst = await list_memories_impl(live, CHILD)
    assert out["name"] in {m["name"] for m in lst["memories"]}
    base_lst = await list_memories_impl(live, BASE)
    assert out["name"] not in {m["name"] for m in base_lst["memories"]}


# ── 2. overlay starvation — the caller's rows survive a limited union ───────


def _engram_spec(i: int, summary: str) -> dict[str, Any]:
    return {
        "area": "general", "surface_when": ["feature_touched"],
        "source_refs": [f"s-{i}"], "affect": "triumph",
        "affect_reason": _REASON, "summary": summary,
        "created_at": "2026-07-01T00:00:00+00:00",
    }


@pytest_asyncio.fixture()
async def sql_kernel_with_big_base(tmp_path: Path):
    """SqlAlchemySource (the production Postgres code path, sqlite driver):
    a base leg LARGER than recall's lexical scan limit (500) + one personal
    overlay memory."""
    from dna.adapters.source_url import source_from_url

    kernel = Kernel.auto()
    src = await source_from_url(f"sqlite:///{tmp_path}/dna.db", kernel=kernel)
    kernel.source(src)
    for i in range(510):
        await src.save_document(
            BASE, "Engram", f"base-{i:04d}",
            {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Engram",
             "metadata": {"name": f"base-{i:04d}"},
             "spec": _engram_spec(i, f"routine board note {i}")},
        )
    await src.save_document(
        BASE, "Engram", "mem-founder",
        {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Engram",
         "metadata": {"name": "mem-founder"},
         "spec": _engram_spec(0, "the founder's personal note xyzstarve")},
        tenant=PERSONAL,
    )
    return kernel


@pytest.mark.asyncio
async def test_limited_union_keeps_the_personal_overlay_row(sql_kernel_with_big_base):
    kernel = sql_kernel_with_big_base
    rows = [
        r async for r in kernel.query(BASE, "Engram", tenant=PERSONAL, limit=500)
    ]
    names = {(r.get("metadata") or {}).get("name") for r in rows}
    assert len(rows) == 500  # the limit still binds
    assert "mem-founder" in names  # the caller's own row survives the cut


@pytest.mark.asyncio
async def test_lexical_personal_recall_survives_a_big_base(sql_kernel_with_big_base):
    """The production failure mode end-to-end: no provider registered →
    recall degrades to the lexical scan (limit=500) — the personal memory
    must still surface."""
    kernel = sql_kernel_with_big_base
    res = await recall(
        kernel, BASE, "founder personal xyzstarve",
        tenant=PERSONAL, reconsolidate=False,
    )
    assert res["degraded"] is True
    hits = {h["name"]: h for h in res["hits"]}
    assert "mem-founder" in hits, res["hits"]
    assert hits["mem-founder"]["personal"] is True


@pytest.mark.asyncio
async def test_ordered_limited_query_keeps_explicit_order(sql_kernel_with_big_base):
    """order_by keeps the caller's explicit order end-to-end — the overlay
    guarantee applies ONLY to the unordered cut (ordered pagination is
    well-defined; later rows are reachable on the next page)."""
    kernel = sql_kernel_with_big_base
    rows = [
        r async for r in kernel.query(
            BASE, "Engram", tenant=PERSONAL, limit=5,
            order_by=["metadata.name"],
        )
    ]
    names = [(r.get("metadata") or {}).get("name") for r in rows]
    assert names == [f"base-{i:04d}" for i in range(5)]


@pytest.mark.asyncio
async def test_fs_fallback_union_keeps_the_personal_overlay_row(tmp_path):
    """Same invariant on the kernel-side load_all fallback (FS sources have
    no query push-down): the overlay row survives a limited unordered union."""
    src_dir = tmp_path / ".dna"
    kernel = Kernel.auto()
    kernel.source(FilesystemWritableSource(base_dir=str(src_dir)))
    for i in range(30):
        await kernel.write_document(
            BASE, "Engram", f"base-{i:02d}",
            {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Engram",
             "metadata": {"name": f"base-{i:02d}"},
             "spec": _engram_spec(i, f"fs base note {i}")},
        )
    personal_kernel = kernel.with_tenant(PERSONAL, allow_personal=True)
    await personal_kernel.write_document(
        BASE, "Engram", "mem-fs-personal",
        {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Engram",
         "metadata": {"name": "mem-fs-personal"},
         "spec": _engram_spec(0, "fs personal note xyzfs")},
    )
    rows = [
        r async for r in kernel.query(BASE, "Engram", tenant=PERSONAL, limit=20)
    ]
    names = {(r.get("metadata") or {}).get("name") for r in rows}
    assert len(rows) == 20
    assert "mem-fs-personal" in names
