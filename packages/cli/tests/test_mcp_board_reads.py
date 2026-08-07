"""Reading the board costs ONE call, not 1 + N.

Two gaps, same shape:

* ``list_instances`` returned names and nothing else, so "show me the open
  issues" was 1 call to list 51 Issues plus 51 ``get_instance`` calls to find out
  which ones are open — 50 of them thrown away, every one of them metered.
  ``kernel.query`` has taken ``filter`` / ``projection`` / ``order_by`` since
  Marco A and the REST list surfaces already push them down; the MCP tool simply
  never exposed them.
* ``board_summary_impl`` / ``board_item_impl`` have been in the shared core, and
  served over REST, for a long time. Nobody wired them as MCP tools — so the one
  question an agent asks most ("what is on the board?") had no single-call answer
  over the face that is supposed to BE the board's interface.

The quota model is respected rather than routed around: each of these is one
metered call gated by the TARGET Kind's family and its read mode, exactly like
``get_instance``. A projection reaches no field the same caller could not already
read one instance at a time; what it changes is the number of round trips.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil
from typing import Any

import pytest

from dna.application import instances as D
from dna.application import sdlc as S

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


async def _seed_board(live: Any) -> None:
    await S.create_feature(
        live.kernel, _SCOPE, "f-board", title="Board", description="d")
    for name, status in (("s-open-a", "todo"), ("s-open-b", "in-progress"),
                         ("s-shut", "done")):
        await S.create_story(
            live.kernel, _SCOPE, name, feature="f-board",
            description=f"desc of {name}", title=name.upper(),
            acceptance_criteria=["Given X, when Y, then Z"],
            definition_of_done=["code+tests"])
        if status != "todo":
            await S.set_status(
                live.kernel, _SCOPE, "Story", name, status,
                no_code=True, gate_reason="read-face fixture, no product surface")


class _CountingKernel:
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.get_document_calls = 0
        self.query_calls = 0

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)

    async def get_instance(self, *a: Any, **kw: Any):
        self.get_document_calls += 1
        return await self._inner.get_instance(*a, **kw)

    async def query(self, *a: Any, **kw: Any):
        self.query_calls += 1
        async for row in self._inner.query(*a, **kw):
            yield row


# ── projection + filter, in the core ───────────────────────────────────────


def test_names_only_is_the_unchanged_default(dna_dir):
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        await _seed_board(live)
        return await D.list_instances_impl(live, kind="Story", scope=_SCOPE)

    out = asyncio.run(go())
    assert out["projected"] is None
    assert all(set(d) == {"name"} for d in out["instances"])
    assert {"s-open-a", "s-open-b", "s-shut"} <= {d["name"] for d in out["instances"]}


def test_one_call_answers_which_stories_are_open(dna_dir):
    """THE payoff, counted: a filtered projection needs ZERO per-instance reads."""
    from dna.application import LiveDna
    from dna_cli import _mcp_server as M

    async def go():
        booted = await M.boot_live(base_dir=str(dna_dir))
        await _seed_board(booted)
        counting = _CountingKernel(booted.kernel)
        live = LiveDna(
            base_scope=booted.base_scope, kernel=counting,
            provider=booted.provider, vendor_workspace=None,
        )
        out = await D.list_instances_impl(
            live, kind="Story", scope=_SCOPE,
            filter={"status": {"in": ["todo", "in-progress"]}},
            fields=["spec.title", "spec.status"],
            order_by=["name"],
        )
        return out, counting

    out, counting = asyncio.run(go())
    assert counting.get_document_calls == 0
    assert counting.query_calls == 1
    names = [d["name"] for d in out["instances"]]
    assert names == ["s-open-a", "s-open-b"]     # the closed one is filtered out
    assert out["instances"][0]["spec"] == {"title": "S-OPEN-A", "status": "todo"}
    assert out["projected"] == ["spec.title", "spec.status"]


def test_an_unprefixed_field_path_resolves_under_spec(dna_dir):
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        await _seed_board(live)
        return await D.list_instances_impl(
            live, kind="Story", scope=_SCOPE, filter={"status": "done"},
            fields=["title"])

    out = asyncio.run(go())
    assert [d["name"] for d in out["instances"]] == ["s-shut"]
    assert out["instances"][0]["spec"]["title"] == "S-SHUT"


def test_a_bad_filter_operator_is_a_named_refusal_not_a_500(dna_dir):
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        await _seed_board(live)
        with pytest.raises(ValueError, match="nope"):
            await D.list_instances_impl(
                live, kind="Story", scope=_SCOPE,
                filter={"status": {"nope": "x"}})

    asyncio.run(go())


# ── over the face ──────────────────────────────────────────────────────────


def _call(server, tool, args):
    from fastmcp import Client

    async def go():
        async with Client(server) as client:
            return await client.call_tool(tool, args)

    return asyncio.run(go())


def test_the_board_tools_are_registered(dna_dir):
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))

    async def go():
        async with Client(server) as client:
            return {t.name for t in await client.list_tools()}

    assert {"board_summary", "board_item"} <= asyncio.run(go())


def test_board_summary_answers_the_whole_board_in_one_call(dna_dir):
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    async def seed():
        live = await M.boot_live(base_dir=str(dna_dir))
        await _seed_board(live)

    asyncio.run(seed())
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    out = _call(server, "board_summary", {"scope": _SCOPE}).structured_content
    assert out["totals"]["stories"] >= 3
    assert out["counts"]["stories"]["done"] == 1
    assert out["counts"]["stories"]["in-progress"] == 1
    assert {"s-open-a", "s-shut"} <= {i["name"] for i in out["items"]}


def test_board_item_returns_the_full_work_item(dna_dir):
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    async def seed():
        live = await M.boot_live(base_dir=str(dna_dir))
        await _seed_board(live)

    asyncio.run(seed())
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    out = _call(server, "board_item",
                {"name": "s-open-b", "scope": _SCOPE}).structured_content
    assert out["kind"] == "Story"
    assert out["status"] == "in-progress"
    assert out["description"] == "desc of s-open-b"
    assert out["timeline"], "the drawer needs the activity feed"


def test_board_item_names_what_it_could_not_find(dna_dir):
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    with pytest.raises(Exception) as ei:  # noqa: PT011 — FastMCP ToolError
        _call(server, "board_item", {"name": "s-nope", "scope": _SCOPE})
    assert "s-nope" in str(ei.value)


def test_list_documents_over_the_face_projects_and_filters(dna_dir):
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    async def seed():
        live = await M.boot_live(base_dir=str(dna_dir))
        await _seed_board(live)

    asyncio.run(seed())
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    out = _call(server, "list_instances", {
        "kind": "Story", "scope": _SCOPE,
        "filter": {"status": "done"}, "fields": ["spec.title"],
    }).structured_content
    assert [d["name"] for d in out["instances"]] == ["s-shut"]
    assert out["instances"][0]["spec"]["title"] == "S-SHUT"


def test_the_board_reads_still_pass_the_plan_guard(dna_dir, http_server):
    """A projection must not be a way to read the board OUTSIDE the quota model:
    both board tools ride the same ``_guard`` seam, so a plan that does not unlock
    the ``sdlc`` family is denied — the read is cheaper, not ungated."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    from dna_cli import _mcp_quota as Q
    from dna_cli import _mcp_server as M

    Q.DEFAULT_STORE.reset()

    async def seed():
        live = await M.boot_live(base_dir=str(dna_dir))
        await live.kernel.write_instance("_lib", "PricingPlan", "free", {
            "apiVersion": "github.com/ruinosus/dna/cloud/v1",
            "kind": "PricingPlan", "metadata": {"name": "free"},
            "spec": {"tier_id": "free", "display_name": "Free",
                     "price_usd_month": 0, "calls_per_day": 10000,
                     "rate_per_sec": 100, "max_tenants": 1,
                     "feature_families": ["definitions"], "sdlc_mode": "read"},
        })

    asyncio.run(seed())
    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer="https://dna.test/",
                           audience="dna-mcp")
    token = kp.create_token(
        issuer="https://dna.test/", audience="dna-mcp", subject="user-1",
        scopes=["dna.read"], additional_claims={"tenant": "acme", "plan": "free"})
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir), auth=verifier)

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            for tool, args in (("board_summary", {"scope": _SCOPE}),
                               ("board_item", {"name": "s-x", "scope": _SCOPE})):
                with pytest.raises(Exception) as ei:  # noqa: PT011
                    await client.call_tool(tool, args)
                assert "sdlc" in str(ei.value).lower(), (tool, str(ei.value))

    with http_server(server) as url:
        asyncio.run(go(url))
