"""Tests for FilesystemSource.query() — Protocol fallback delegate.

Story s-filesystem-source-query-impl (Feature f-source-as-query).

Decision (documented in the test_module_doc): the filesystem adapter
delegates to the Protocol's default ``query`` fallback (load_all +
Python filter via the shared helpers). This is the correct choice
because:

  1. FS is dev-mode only. Production runs on Postgres (multi-process
     EventBus, tenant overlay, transaction safety).
  2. FS scopes are SMALL (the local examples/ directory tree). 5-50
     docs per scope is typical. A 30-150ms walk is fine.
  3. Adding a kind-specific path optimization would require the FS
     adapter to know the Kind→directory mapping, which lives in the
     KindPort's StorageDescriptor — a cross-layer coupling we don't
     need to introduce.

This file proves the delegate works end-to-end with REAL bundle
directories + readers (the AgentsMd / SkillMd readers parse markers
inside the bundles). Mock-based tests live in
``test_sourceport_query_protocol.py`` (Protocol fallback) — those
don't need to be duplicated here.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from dna.adapters.filesystem.source import FilesystemSource
from dna.kernel.protocols import QueryError


# ---------------------------------------------------------------------------
# Live FS scope fixture
# ---------------------------------------------------------------------------


def _write_story(scope_dir: Path, slug: str, *, status: str, feature: str = "f-foo",
                 priority: int = 3, title: str = "Untitled") -> None:
    """Write a minimal Story YAML at scope_dir/stories/<slug>.yaml.

    The filesystem source's load_all walks the directory tree and
    treats each YAML file as a Document (no bundle/marker required
    for simple Kinds).
    """
    stories_dir = scope_dir / "stories"
    stories_dir.mkdir(parents=True, exist_ok=True)
    body = (
        "apiVersion: github.com/ruinosus/dna/sdlc/v1\n"
        "kind: Story\n"
        "metadata:\n"
        f"  name: {slug}\n"
        "spec:\n"
        f"  title: \"{title}\"\n"
        f"  status: {status}\n"
        f"  feature: {feature}\n"
        f"  priority: {priority}\n"
    )
    (stories_dir / f"{slug}.yaml").write_text(body)


def _write_package(scope_dir: Path, name: str) -> None:
    (scope_dir / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        "metadata:\n"
        f"  name: {name}\n"
        "spec:\n"
        "  owner: platform\n"
    )


@pytest_asyncio.fixture
async def fs_src(tmp_path):
    """FS adapter rooted at tmp_path/ with one scope 'demo'."""
    scope_dir = tmp_path / "demo"
    scope_dir.mkdir()
    _write_package(scope_dir, "demo")
    _write_story(scope_dir, "s-a", status="in-progress", priority=5)
    _write_story(scope_dir, "s-b", status="done", priority=2)
    _write_story(scope_dir, "s-c", status="in-progress", priority=8)
    _write_story(scope_dir, "s-d", status="todo", priority=1, feature="f-bar")

    src = FilesystemSource(base_dir=str(tmp_path))
    yield src


# ---------------------------------------------------------------------------
# Live tests — real FS, real readers, real walk.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_returns_all_kind_docs_when_no_filter(fs_src):
    rows = [r async for r in fs_src.query("demo", "Story")]
    names = sorted(r["metadata"]["name"] for r in rows)
    assert names == ["s-a", "s-b", "s-c", "s-d"]


@pytest.mark.asyncio
async def test_query_filter_status(fs_src):
    rows = [r async for r in fs_src.query(
        "demo", "Story", filter={"status": "in-progress"},
    )]
    names = sorted(r["metadata"]["name"] for r in rows)
    assert names == ["s-a", "s-c"]


@pytest.mark.asyncio
async def test_query_filter_in_operator(fs_src):
    rows = [r async for r in fs_src.query(
        "demo", "Story", filter={"status": {"in": ["todo", "in-progress"]}},
    )]
    names = sorted(r["metadata"]["name"] for r in rows)
    assert names == ["s-a", "s-c", "s-d"]


@pytest.mark.asyncio
async def test_query_filter_and_compound(fs_src):
    rows = [r async for r in fs_src.query(
        "demo", "Story",
        filter={"status": "in-progress", "feature": "f-foo"},
    )]
    names = sorted(r["metadata"]["name"] for r in rows)
    assert names == ["s-a", "s-c"]  # both match


@pytest.mark.asyncio
async def test_query_projection_returns_only_requested_fields(fs_src):
    rows = [r async for r in fs_src.query(
        "demo", "Story",
        projection=["spec.title", "spec.status"],
    )]
    for r in rows:
        assert set(r.keys()) <= {"name", "spec"}
        assert set(r["spec"].keys()) <= {"title", "status"}
        # priority/feature were excluded
        assert "priority" not in r["spec"]
        assert "feature" not in r["spec"]


@pytest.mark.asyncio
async def test_query_order_by_desc_limit(fs_src):
    rows = [r async for r in fs_src.query(
        "demo", "Story",
        order_by=["-spec.priority"],
        limit=2,
    )]
    priorities = [r["spec"]["priority"] for r in rows]
    assert priorities == [8, 5]


@pytest.mark.asyncio
async def test_query_offset_paginates(fs_src):
    rows = [r async for r in fs_src.query(
        "demo", "Story",
        order_by=["spec.priority"],  # asc: 1, 2, 5, 8
        offset=1,
        limit=2,
    )]
    priorities = [r["spec"]["priority"] for r in rows]
    assert priorities == [2, 5]


@pytest.mark.asyncio
async def test_query_unknown_operator_raises(fs_src):
    with pytest.raises(QueryError):
        [_ async for _ in fs_src.query(
            "demo", "Story", filter={"status": {"regex": ".*"}},
        )]


@pytest.mark.asyncio
async def test_query_returns_full_raw_when_no_projection(fs_src):
    rows = [r async for r in fs_src.query("demo", "Story", filter={"status": "todo"})]
    assert len(rows) == 1
    r = rows[0]
    # Full doc shape preserved
    assert r["kind"] == "Story"
    assert r["metadata"]["name"] == "s-d"
    assert r["spec"]["priority"] == 1
    assert r["spec"]["feature"] == "f-bar"


@pytest.mark.asyncio
async def test_query_kind_filter_excludes_other_kinds(fs_src, tmp_path):
    """The Genome doc at scope root must NOT appear when querying Story."""
    rows = [r async for r in fs_src.query("demo", "Story")]
    kinds = {r["kind"] for r in rows}
    assert kinds == {"Story"}
