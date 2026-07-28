"""The PORTFOLIO door at the MCP face — and the bridge from a project to its board.

The Kinds (``Project`` / ``Organization`` / ``Repo``) were always registered and
always reachable through the generic document door; the application seams were
already written and already served REST. What was missing was a NAME, and a
catalog of 78 Kinds with no named tool is discoverable only by luck.

So these tests do NOT re-prove the seams. They prove the three things the door
itself is responsible for:

1. **the tools are offered** — the six names reach a client's ``tools/list``;
2. **THE BRIDGE** — a project's ``board_scope`` really is the scope that
   ``board_summary`` reads. This is the whole reason ``list_projects`` exists:
   without it a caller holds a roster and a board tool and nothing joins them,
   which is exactly how someone reports "I cannot find the boards" about a
   system that has served them all along. Proven end-to-end through the REAL
   protocol: read the roster, take the field, call the board tool with it, and
   see THAT project's item;
3. **identity and scope are not caller inputs on the write** — ``create_project``
   exposes neither ``claims`` nor ``scope``. A ``claims`` argument would be a
   caller-supplied identity, which is not an identity; a caller-chosen scope
   would be a way to write into another workspace. Both are asserted against
   the tool's PUBLISHED schema, which is what a caller can actually reach.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import shutil

import pytest

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the optional 'fastmcp' extra")

from dna_cli import _mcp_server as M  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"

#: The board scope this project declares. Deliberately NOT the conventional
#: ``<slug>-development``: if the bridge silently rebuilt the scope from the
#: slug instead of READING ``board_scope``, a conventional value would let the
#: bug pass. An unconventional one makes the two paths disagree.
_BOARD_SCOPE = "atlas-board-not-the-convention"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope carrying one Project and, in that
    project's declared board scope, one Story to find."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)

    projects = dst / _SCOPE / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    (projects / "atlas.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/portfolio/v1\n"
        "kind: Project\n"
        "metadata:\n"
        "  name: atlas\n"
        "spec:\n"
        "  slug: atlas\n"
        "  workspace_id: ws-test\n"
        f"  board_scope: {_BOARD_SCOPE}\n"
        "  repo_refs: []\n"
        "  visibility: private\n",
        encoding="utf-8",
    )

    stories = dst / _BOARD_SCOPE / "stories"
    stories.mkdir(parents=True, exist_ok=True)
    (stories / "s-only-on-the-project-board.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/sdlc/v1\n"
        "kind: Story\n"
        "metadata:\n"
        "  name: s-only-on-the-project-board\n"
        "spec:\n"
        "  title: only reachable through the project's board_scope\n"
        "  status: todo\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _payload(result):
    """The tool's data, whichever channel carried it."""
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


def _run(dna_dir, body):
    from fastmcp import Client

    async def go():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            return await body(client)

    return asyncio.run(go())


# ── 1. the door is open ────────────────────────────────────────────────────


def test_the_portfolio_tools_are_offered(dna_dir):
    """The six names reach a real client's ``tools/list``. Drop the
    ``register_portfolio_tools`` call and this dies."""
    names = _run(dna_dir, lambda c: c.list_tools())
    offered = {t.name for t in names}
    assert {
        "list_workspaces", "list_projects", "get_project",
        "create_project", "list_repos", "list_orgs",
    } <= offered


# ── 2. THE BRIDGE: board_scope is the board ────────────────────────────────


def test_list_projects_carries_the_board_scope(dna_dir):
    """The roster reports the field that unlocks the board. Remove
    ``board_scope`` from the projected surface and this dies."""
    async def body(client):
        return _payload(await client.call_tool("list_projects", {"scope": _SCOPE}))

    data = _run(dna_dir, body)
    atlas = next(p for p in data["projects"] if p["slug"] == "atlas")
    assert atlas["board_scope"] == _BOARD_SCOPE


def test_the_board_scope_from_the_roster_really_reads_that_board(dna_dir):
    """THE claim this module exists for, proven end-to-end over the real
    protocol: take ``board_scope`` from ``list_projects`` — never a literal —
    hand it to ``board_summary``, and the project's own story is there.

    The board scope is deliberately NOT the conventional ``<slug>-development``,
    so a bridge that rebuilt the scope from the slug instead of reading the
    field would look at an empty scope and this would die."""
    async def body(client):
        roster = _payload(await client.call_tool("list_projects", {"scope": _SCOPE}))
        atlas = next(p for p in roster["projects"] if p["slug"] == "atlas")
        board = _payload(
            await client.call_tool("board_summary", {"scope": atlas["board_scope"]})
        )
        return atlas, board

    atlas, board = _run(dna_dir, body)
    assert atlas["board_scope"] == _BOARD_SCOPE
    assert json.dumps(board).find("s-only-on-the-project-board") != -1, (
        "the project's board_scope did not read the project's board: "
        f"{json.dumps(board)[:400]}"
    )


def test_the_tool_description_tells_the_model_about_the_bridge(dna_dir):
    """The bridge is only useful if the model LEARNS it without being told
    separately — the sentence lives in the published description, which is what
    a client actually reads. Strip it from the docstring and this dies.

    Not decoration: a roster and a board tool that never mention each other are
    two halves nothing joins, and the model is left to guess the join."""
    tools = {t.name: t for t in _run(dna_dir, lambda c: c.list_tools())}
    description = tools["list_projects"].description or ""
    assert "board_scope" in description
    assert "board_summary" in description


# ── 3. the write takes neither identity nor scope ──────────────────────────


@pytest.mark.parametrize("forbidden", ["claims", "scope"])
def test_create_project_does_not_expose_identity_or_scope(dna_dir, forbidden):
    """Asserted against the PUBLISHED schema — what a caller can actually
    reach — not against the Python signature.

    ``claims``: a caller-supplied identity is not an identity. It is read
    server-side from the verified token.
    ``scope``: the write scope and ``board_scope`` are DERIVED from
    (workspace, slug). A caller-chosen scope is a cross-workspace write vector.

    Add either parameter to the tool and this dies."""
    tools = {t.name: t for t in _run(dna_dir, lambda c: c.list_tools())}
    properties = (tools["create_project"].inputSchema or {}).get("properties") or {}
    assert forbidden not in properties, (
        f"create_project publishes {forbidden!r}: {sorted(properties)}"
    )
    # …and the parameters it DOES take are the intended three.
    assert set(properties) == {"workspace_id", "name", "slug"}
