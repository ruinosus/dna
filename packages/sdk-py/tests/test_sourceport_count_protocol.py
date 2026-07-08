"""F2 D2: count fallback sobre load_all (query_fallback helpers).

Two-planes F2 (spec docs/superpowers/specs/2026-06-09-kinds-two-planes-design.md
D2). s-sourceport-contract-cleanup: o fallback saiu do corpo do Protocol —
``count_via_query`` (ride ``source.query``) + ``query_via_load_all`` vivem em
``dna.kernel.query_fallback``. SQL adapters fazem override com
``SELECT count(*) … GROUP BY`` nativo (Task 3).

NOTE: ``FilesystemSource`` / ``CompositeFilesystemSource`` carry explicit
``count`` delegators — covered by the integration tests at the bottom.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.kernel.query_fallback import count_via_query, query_via_load_all


# ---------------------------------------------------------------------------
# Harness — mirrors test_sourceport_query_protocol.py (fake source whose
# load_all returns raw docs). Duplicated on purpose: tests/ is not a package.
# ---------------------------------------------------------------------------

class _FakeSource:
    """Minimal SourcePort with load_all + load_layer. Used to exercise
    the Protocol's default `count` fallback (which rides on `query`)."""

    def __init__(self, base_docs, overlay_docs=None):
        self._base = list(base_docs)
        self._overlay = list(overlay_docs or [])

    async def load_all(self, scope, readers=None):
        return list(self._base)

    async def load_layer(self, scope, layer_id, layer_value, readers=None):
        return list(self._overlay)

    async def query(self, scope, kind, **kw):
        # ``count_via_query`` rides on ``self.query`` — real adapters all
        # expose it (FS/Composite via explicit delegators, PG native).
        # The fake mirrors the FS delegator pattern.
        async for row in query_via_load_all(self, scope, kind, **kw):
            yield row


def _doc(kind, name, spec):
    return {"kind": kind, "metadata": {"name": name}, "spec": dict(spec)}


def _make_fake_source(docs, overlay=None):
    return _FakeSource(docs, overlay)


# ---------------------------------------------------------------------------
# Protocol default — total / group_by / ordering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_count_total_with_filter():
    src = _make_fake_source([
        _doc("Story", "s-1", {"status": "todo"}),
        _doc("Story", "s-2", {"status": "done"}),
        _doc("Story", "s-3", {"status": "todo"}),
        _doc("Issue", "i-1", {"status": "open"}),
    ])
    res = await count_via_query(src, "sc", "Story", filter={"status": "todo"})
    assert res == {"total": 2, "groups": None}


@pytest.mark.asyncio
async def test_count_group_by():
    src = _make_fake_source([
        _doc("Story", "s-1", {"status": "todo"}),
        _doc("Story", "s-2", {"status": "done"}),
        _doc("Story", "s-3", {"status": "todo"}),
        _doc("Story", "s-4", {}),  # sem status → key None
    ])
    res = await count_via_query(src, "sc", "Story", group_by="spec.status")
    assert res["total"] == 4
    groups = {g["key"]: g["count"] for g in res["groups"]}
    assert groups == {"todo": 2, "done": 1, None: 1}


@pytest.mark.asyncio
async def test_count_group_none_key_ties_sort_last():
    """Empate de count entre key None e key real → None por último
    (paridade com PG NULLS LAST; pegaria a divergência do review r2)."""
    src = _make_fake_source([
        _doc("Story", "s-1", {"status": "todo"}),
        _doc("Story", "s-2", {"status": "todo"}),
        _doc("Story", "s-3", {"status": "done"}),
        _doc("Story", "s-4", {}),  # None — empata com done
    ])
    res = await count_via_query(src, "sc", "Story", group_by="spec.status")
    assert [g["key"] for g in res["groups"]] == ["todo", "done", None]


@pytest.mark.asyncio
async def test_count_groups_sorted_desc_by_count():
    src = _make_fake_source([
        _doc("Story", f"s-{i}", {"status": "done"}) for i in range(3)
    ] + [_doc("Story", "s-t", {"status": "todo"})])
    res = await count_via_query(src, "sc", "Story", group_by="spec.status")
    assert [g["key"] for g in res["groups"]] == ["done", "todo"]


@pytest.mark.asyncio
async def test_count_group_by_name_survives_projection_trim():
    """F2 T3 review carry-over: the default ``count`` projects only the
    group_by field (payload trim). ``group_by="name"`` must still resolve
    on the projected row shape (normalized to ``metadata.name``)."""
    src = _make_fake_source([
        _doc("Story", "s-1", {"status": "todo"}),
        _doc("Story", "s-2", {"status": "done"}),
    ])
    res = await count_via_query(src, "sc", "Story", group_by="name")
    assert res["total"] == 2
    groups = {g["key"]: g["count"] for g in res["groups"]}
    assert groups == {"s-1": 1, "s-2": 1}


@pytest.mark.asyncio
async def test_count_default_projects_only_needed_fields():
    """F2 T3 review carry-over: the default ``count`` passes
    ``projection=[group_by]`` (or ``["name"]``) to ``self.query`` so the
    sqlite delegator's long-lived path doesn't haul full docs."""
    captured: list = []

    class _SpySource(_FakeSource):
        async def query(self, scope, kind, **kw):
            captured.append(kw.get("projection"))
            async for row in query_via_load_all(self, scope, kind, **kw):
                yield row

    src = _SpySource([_doc("Story", "s-1", {"status": "todo"})])
    await count_via_query(src, "sc", "Story")
    await count_via_query(src, "sc", "Story", group_by="spec.status")
    await count_via_query(src, "sc", "Story", group_by="name")
    assert captured == [["name"], ["spec.status"], ["metadata.name"]]


@pytest.mark.asyncio
async def test_count_tenant_overlay_shadows_base():
    """Tenant kwarg rides the query() default: overlay shadows base on
    (kind, name) — counted once."""
    base = [_doc("Story", "s-shared", {"status": "todo"}),
            _doc("Story", "s-only-base", {"status": "todo"})]
    overlay = [_doc("Story", "s-shared", {"status": "done"}),
               _doc("Story", "s-only-overlay", {"status": "done"})]
    src = _make_fake_source(base, overlay)
    res = await count_via_query(src, "sc", "Story", group_by="spec.status", tenant="acme")
    assert res["total"] == 3
    groups = {g["key"]: g["count"] for g in res["groups"]}
    assert groups == {"done": 2, "todo": 1}


# ---------------------------------------------------------------------------
# Explicit delegators — FilesystemSource + CompositeFilesystemSource are
# plain classes (no Protocol inheritance): without their explicit `count`
# delegators, kernel.count() on the dev-default FS source would
# AttributeError.
# ---------------------------------------------------------------------------

def _write_story(scope_dir: Path, name: str, status: str | None) -> None:
    spec = f"spec:\n  status: {status}\n" if status is not None else "spec: {}\n"
    (scope_dir / f"{name}.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Story\n"
        f"metadata:\n  name: {name}\n"
        f"{spec}",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_filesystem_source_count_real(tmp_path: Path):
    from dna.adapters.filesystem.source import FilesystemSource

    scope_dir = tmp_path / "sc"
    scope_dir.mkdir()
    _write_story(scope_dir, "s-1", "todo")
    _write_story(scope_dir, "s-2", "done")
    _write_story(scope_dir, "s-3", "todo")
    _write_story(scope_dir, "s-4", None)

    src = FilesystemSource(tmp_path)
    res = await src.count("sc", "Story", filter={"status": "todo"})
    assert res == {"total": 2, "groups": None}

    res = await src.count("sc", "Story", group_by="spec.status")
    assert res["total"] == 4
    assert [g["key"] for g in res["groups"]] == ["todo", "done", None]


@pytest.mark.asyncio
async def test_composite_filesystem_source_count_routes_to_child(tmp_path: Path):
    from dna.adapters.filesystem.composite import CompositeFilesystemSource

    scope_dir = tmp_path / "ex-one" / ".dna" / "alpha"
    scope_dir.mkdir(parents=True)
    (scope_dir / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\nmetadata:\n  name: alpha\nspec: {}\n"
    )
    _write_story(scope_dir, "s-1", "todo")
    _write_story(scope_dir, "s-2", "done")
    _write_story(scope_dir, "s-3", "todo")

    src = CompositeFilesystemSource(tmp_path)
    res = await src.count("alpha", "Story", group_by="spec.status")
    assert res["total"] == 3
    assert res["groups"] == [
        {"key": "todo", "count": 2},
        {"key": "done", "count": 1},
    ]
