"""``graph_refs`` — the traversal, THROUGH the MCP door, measured against REST.

The defect this closes is the one this house keeps re-finding under the name
*capability exists, port does not*: the derived reference graph was reachable
from the CLI (``dna graph refs``) and from REST
(``GET /v1/kinds/{kind}/instances/{name}/refs``) and from nowhere an agent could
speak to. The console copilot dials the broker MCP door, so "what points at this
Feature" was a question it could not ask at all — while the walk itself sat in
the kernel, wired, tested and serving two other faces.

**THE ASSERTION IS A COMPARISON, NOT A LITERAL.** Every interesting test here
calls the REST route and the MCP tool against THE SAME STORE and requires the
same edges back. A hand-written expected list would pass on a tool that had
quietly grown its own shape — a different default direction, an edge dict with
different keys, a depth that means something else — which is precisely the debt
a third face of one verb is at risk of creating. Comparing the faces cannot: it
is red the moment they disagree, whichever one is wrong.

Two stores, deliberately, exactly like the REST suite next door:

* the **filesystem** store, which records no edges and must therefore REFUSE.
  ``{"edges": []}`` would tell an agent nothing points at this instance, and the
  filesystem adapter has no idea whether that is true;
* a **SQLite** store, where a real write through the real producer makes a real
  edge, so the walk has something to return.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"

_SQL_SKIP = (
    "the SQL adapter's async driver stack is an SDK extra the CLI does not "
    "pull; the refusal lane — the one only this suite can prove — still runs."
)


@pytest.fixture
def fs_dir(tmp_path, monkeypatch):
    """A filesystem store — the adapter that keeps no edges."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    return dst


@pytest.fixture
def sql_dir(tmp_path, monkeypatch):
    """A SQLite store seeded through the REAL write path.

    Seeded by the kernel rather than by inserting edge rows: an edge exists in
    this product because somebody wrote an instance whose reference resolved,
    and a fixture that forged the row would let both faces pass with no producer
    behind either — the exact failure that left the first edge table empty for
    fourteen months.

    ``s-x`` and ``s-z`` both point at ``f-y``; ``s-x`` also points at a Feature
    that does not exist, so the DANGLING half of the answer is real too.
    """
    for _module in ("aiosqlite", "greenlet", "alembic"):
        pytest.importorskip(_module, reason=_SQL_SKIP)
    url = f"sqlite+aiosqlite:///{tmp_path / 'graph.db'}"
    monkeypatch.setenv("DNA_SOURCE_URL", url)
    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)

    def _doc(kind, name, **spec):
        base = {"description": "d", "status": "todo"}
        base.update(spec)
        return {
            "apiVersion": _SDLC_API, "kind": kind,
            "metadata": {"name": name}, "spec": base,
        }

    async def seed():
        from dna.adapters.sqlalchemy_ import SqlAlchemySource
        from dna.kernel import Kernel

        src = SqlAlchemySource(url)
        await src.connect()
        k = Kernel.auto()
        k.source(src)
        await k.write_instance(_SCOPE, "Epic", "e-1", _doc("Epic", "e-1"))
        await k.write_instance(
            _SCOPE, "Feature", "f-y", _doc("Feature", "f-y", epic="e-1"))
        await k.write_instance(
            _SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"))
        await k.write_instance(
            _SCOPE, "Story", "s-z", _doc("Story", "s-z", feature="f-y"))
        await src.close()

    asyncio.run(seed())
    return url


# ── the two faces, side by side ─────────────────────────────────────────────


def _mcp(args, **build):
    """Call the ``graph_refs`` TOOL over a real ``fastmcp.Client``.

    Through the door, never through ``graph_refs_impl``: the whole defect was
    the boundary. A test that called the use-case would have been green on every
    build that had no tool at all.
    """
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, **build)

    async def go():
        async with Client(server) as client:
            return await client.call_tool("graph_refs", args)

    return asyncio.run(go()).structured_content


def _mcp_refused(args, **build) -> str:
    with pytest.raises(Exception) as ei:  # noqa: PT011 — FastMCP ToolError
        _mcp(args, **build)
    return str(ei.value)


def _rest(path, params=None, **build):
    pytest.importorskip(
        "fastapi", reason="the REST read-API needs the optional 'fastapi' extra")
    from fastapi.testclient import TestClient

    from dna_cli import _rest_api as R

    with TestClient(R.build_app(scope=_SCOPE, **build)) as c:
        return c.get(path, params=params or {})


def _rest_refs(kind, name, params=None, **build):
    return _rest(
        f"/v1/kinds/{kind}/instances/{name}/refs", params=params, **build)


class TestTheTwoFacesAgree:
    """AC 1, and it is stated as a comparison because that is the only form
    that can catch a third shape of the same verb being invented here."""

    def test_the_default_walk_is_the_same_answer_on_both_faces(self, sql_dir):
        """No parameters at all: both faces must default to the same question.

        ``direction`` and ``depth`` have defaults on both sides, and a default
        that drifted would be invisible to any test that passed them explicitly.
        """
        rest = _rest_refs("Feature", "f-y").json()
        mcp = _mcp({"kind": "Feature", "name": "f-y"})

        assert mcp["edges"], "the walk found nothing — the fixture, not the faces"
        assert mcp == rest, (
            "the MCP tool and the REST route disagree about the same instance "
            "in the same store — a third shape of one verb is exactly what this "
            "tool exists not to create"
        )

    @pytest.mark.parametrize("direction", ["in", "out", "both"])
    @pytest.mark.parametrize("depth", [1, 2, 3])
    def test_every_direction_and_depth_agrees(self, sql_dir, direction, depth):
        """The two coordinate parameters, across their whole range.

        ``out`` at depth 3 from ``s-x`` walks Story → Feature → Epic, so this
        also proves the depth means HOPS on both faces and not something else.
        """
        rest = _rest_refs(
            "Story", "s-x", {"direction": direction, "depth": depth}).json()
        mcp = _mcp({
            "kind": "Story", "name": "s-x",
            "direction": direction, "depth": depth,
        })
        assert mcp == rest, f"{direction}/{depth}: the faces disagree"

    def test_the_honesty_fields_travel_over_MCP_too(self, sql_dir):
        """``stop`` / ``graph_producer`` / ``resolved`` are not decoration.

        Asserted here as well as in the comparison because a face that dropped
        all three would still be EQUAL to a REST face that dropped them — the
        comparison is a strong test of drift and a weak one of content.
        """
        mcp = _mcp({"kind": "Feature", "name": "f-y"})
        assert mcp["stop"] in ("complete", "depth_reached", "truncated")
        assert mcp["graph_producer"] == "warn"
        assert sorted(
            (e["from_kind"], e["from_name"], e["field"]) for e in mcp["edges"]
        ) == [("Story", "s-x", "feature"), ("Story", "s-z", "feature")]
        assert all(e["resolved"] is True for e in mcp["edges"])


# ── the refusals ────────────────────────────────────────────────────────────


class TestTheRefusals:
    def test_a_store_without_edges_is_refused_by_name_not_answered_empty(
        self, fs_dir,
    ):
        """⚠️ AC 3, and the assertion that matters most on this whole tool.

        ``{"edges": []}`` would tell an agent that NOTHING points at this
        instance. The filesystem adapter has no idea whether that is true, and
        an agent handed a confident empty list will act on it — which is worse
        than being told the deployment cannot answer.

        The NAME travels because an agent acts on it: ``GraphUnsupported`` means
        "stop asking this deployment about the graph", a different remedy from
        every other way this call can fail.
        """
        msg = _mcp_refused(
            {"kind": "Agent", "name": "concierge"}, base_dir=str(fs_dir))
        assert "GraphUnsupported" in msg, msg
        assert "not the same as" in msg, msg

        # ...and REST refuses the SAME call with its own 501, so the two faces
        # agree about the refusal exactly as they agree about the answer.
        assert _rest_refs(
            "Agent", "concierge", base_dir=str(fs_dir)).status_code == 501

    def test_the_refusal_survives_mask_error_details(self, fs_dir, monkeypatch):
        """The setting an operator is invited to turn on erases the message of
        anything that is not a ``ToolError``. Under it, an untranslated refusal
        reaches the agent as ``Error calling tool 'graph_refs'`` — no name, no
        reason, indistinguishable from a crash."""
        pytest.importorskip("fastmcp")
        import fastmcp

        monkeypatch.setattr(fastmcp.settings, "mask_error_details", True)
        msg = _mcp_refused(
            {"kind": "Agent", "name": "concierge"}, base_dir=str(fs_dir))
        assert "GraphUnsupported" in msg, msg
        assert "edge_graph" in msg, msg

    def test_a_nonsense_direction_is_refused_on_both_faces(self, sql_dir):
        msg = _mcp_refused({
            "kind": "Feature", "name": "f-y", "direction": "sideways"})
        assert "sideways" in msg, msg
        assert _rest_refs(
            "Feature", "f-y", {"direction": "sideways"}).status_code == 400

    def test_an_unknown_kind_is_refused_naming_it(self, sql_dir):
        msg = _mcp_refused({"kind": "NaoExiste", "name": "x"})
        assert "NaoExiste" in msg, msg
        assert _rest_refs("NaoExiste", "x").status_code == 404

    def test_depth_below_one_is_refused_rather_than_clamped(self, sql_dir):
        """REST answers 422 (``ge=1``); the kernel would CLAMP to 1.

        Clamping is fine for a CLI flag and wrong here: the answer carries a
        ``depth`` field, so a silently-corrected request comes back looking like
        the request that was made.
        """
        msg = _mcp_refused({"kind": "Feature", "name": "f-y", "depth": 0})
        assert "depth" in msg, msg
        assert _rest_refs(
            "Feature", "f-y", {"depth": 0}).status_code == 422


# ── the tool is REGISTERED, which is what makes it reachable ────────────────


def test_the_tool_is_listed_on_the_face(fs_dir):
    """i-106's lesson generalised: a capability nobody can DISCOVER is not a
    port. The tool list is where an agent learns this exists at all."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(fs_dir))

    async def go():
        async with Client(server) as client:
            return await client.list_tools()

    tools = {t.name: t for t in asyncio.run(go())}
    assert "graph_refs" in tools, sorted(tools)
    described = (tools["graph_refs"].description or "")
    # The refusal is part of the contract an agent reads BEFORE calling.
    assert "never" in described.lower()
