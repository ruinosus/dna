"""Feature ``f-mcp-sdlc-write`` — the DNA SDLC board as **write** tools over MCP.

Closes the dogfood loop: the board is not just READABLE over MCP (sdlc_digest /
list_stories / get_adr) but WRITABLE — create_story / create_issue / set_status /
comment / create_feature — so any MCP client (Copilot, an agent, a bare client)
can create + manage the board over its own interface.

Four properties, mirroring ``test_mcp_memory.py`` / ``test_mcp_quota.py``:

1. **pure builders + transition rules** — the spec shape, timeline event, and the
   valid-target-status guard are pure (no clock/env), shared verbatim with the CLI.

2. **write cores go through ``write_document``** — each core creates/transitions
   the right Kind and the write is a real kernel write (a timeline event lands, the
   doc is queryable) — proven at the impl level (data layer, no server/auth).

3. **integration round-trip** — a Story created via ``create_story`` APPEARS in
   ``list_stories``; a ``set_status`` transition is reflected; a ``comment`` lands
   on the timeline — the read + write faces agree over the same live kernel.

4. **tenant-scoping + plan-guard** — over a real token: a write lands in the
   token's tenant overlay (never base blindly), and a Free (sdlc_mode=read) token
   writing is DENIED while its reads stay allowed; a Pro (sdlc_mode=write) token
   writes fine. Stdio/OSS (no token) is untouched.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

from dna.application import sdlc as W
from dna_cli import _mcp_quota as Q

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_ISSUER = "https://dna.test/"
_AUDIENCE = "dna-mcp"


# ── 1. pure builders + transition rules (no I/O) ────────────────────────────


def test_build_story_spec_shape():
    spec = W.build_story_spec(
        title=None, description="First line here\nsecond", feature="f-x",
        status="todo", priority="high", labels=["a", "b"],
        acceptance_criteria=["Given X"], definition_of_done=["Merged"],
        now="2026-07-15T00:00:00+00:00", actor="mcp", source="mcp",
    )
    assert spec["title"] == "First line here"  # title derived from 1st desc line
    assert spec["status"] == "todo"
    assert spec["feature"] == "f-x"
    assert spec["priority"] == "high"
    assert spec["labels"] == ["a", "b"]
    assert spec["acceptance_criteria"] == ["Given X"]
    assert spec["definition_of_done"] == ["Merged"]
    # first timeline event is the create — a status_change with `to`, no `from`.
    ev = spec["timeline"][0]
    assert ev["type"] == "status_change" and ev["to"] == "todo"
    assert "from" not in ev  # falsy extras dropped
    assert ev["source"] == "mcp"


def test_build_issue_spec_shape():
    spec = W.build_issue_spec(
        description="bug here", issue_type="bug", severity="high",
        now="2026-07-15T00:00:00+00:00", actor="mcp", source="mcp",
    )
    assert spec["type"] == "bug" and spec["severity"] == "high"
    assert spec["status"] == "open"
    assert spec["timeline"][0]["to"] == "open"


def test_next_issue_number_pure():
    assert W.next_issue_number([]) == 1
    assert W.next_issue_number(["i-003-foo", "i-007-bar", "s-x"]) == 8


def test_validate_transition_accepts_valid():
    W.validate_transition("Story", "in-progress")
    W.validate_transition("Issue", "resolved")
    W.validate_transition("Feature", "in-development")


def test_validate_transition_rejects_invalid_status():
    with pytest.raises(W.InvalidTransition, match="not a valid Story status"):
        W.validate_transition("Story", "bogus")
    # a valid Issue status is NOT a valid Story status → rejected for Story.
    with pytest.raises(W.InvalidTransition):
        W.validate_transition("Story", "resolved")


def test_validate_transition_rejects_unknown_kind():
    with pytest.raises(W.InvalidTransition, match="not a status-bearing"):
        W.validate_transition("Soul", "done")


def test_looks_like_decision():
    assert W.looks_like_decision("Decidi usar X porque Y")
    assert W.looks_like_decision("Decided to ship it")
    assert not W.looks_like_decision("just a note about progress")


# ── 2 + 3. write cores + integration round-trip (real kernel, no server) ────


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def test_create_story_appears_in_list_stories(dna_dir):
    """A Story created via ``create_story_impl`` APPEARS in ``list_stories_impl`` —
    the write + read faces agree over the same live kernel (the dogfood loop)."""
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        out = await W.create_story_impl(
            live, "s-mcp-made-me", feature="f-demo",
            description="Created entirely over MCP", priority="high",
            acceptance_criteria=["Given MCP, then a Story exists"],
            definition_of_done=["Appears in list_stories"], scope=_SCOPE,
        )
        listed = await M.list_stories_impl(live, scope=_SCOPE)
        return out, listed

    out, listed = asyncio.run(scenario())
    assert out == {"kind": "Story", "name": "s-mcp-made-me", "status": "todo",
                   "feature": "f-demo"}
    names = {s["name"] for s in listed["stories"]}
    assert "s-mcp-made-me" in names, names


def test_set_status_transitions_and_reflects(dna_dir):
    """``set_status`` transitions a Story and the new status is reflected in
    ``list_stories`` (+ a status_change event with `from`/`to` lands)."""
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await W.create_story_impl(
            live, "s-transition-me", feature="f-demo", description="x",
            acceptance_criteria=["a"], definition_of_done=["b"], scope=_SCOPE)
        res = await W.set_status_impl(live, "Story", "s-transition-me",
                                      "in-progress", scope=_SCOPE)
        doc = await live.kernel.get_document(_SCOPE, "Story", "s-transition-me")
        listed = await M.list_stories_impl(live, status="in-progress", scope=_SCOPE)
        return res, doc, listed

    res, doc, listed = asyncio.run(scenario())
    assert res == {"kind": "Story", "name": "s-transition-me",
                   "from": "todo", "to": "in-progress"}
    assert doc["spec"]["status"] == "in-progress"
    # a status_change event carrying from/to landed on the timeline.
    evs = [e for e in doc["spec"]["timeline"] if e["type"] == "status_change"]
    assert any(e.get("from") == "todo" and e.get("to") == "in-progress" for e in evs)
    assert "s-transition-me" in {s["name"] for s in listed["stories"]}


def test_set_status_terminal_stamps_closed_at(dna_dir):
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await W.create_story_impl(
            live, "s-finish-me", feature="f-demo", description="x",
            acceptance_criteria=["a"], definition_of_done=["b"], scope=_SCOPE)
        await W.set_status_impl(live, "Story", "s-finish-me", "done", scope=_SCOPE)
        return await live.kernel.get_document(_SCOPE, "Story", "s-finish-me")

    doc = asyncio.run(scenario())
    assert doc["spec"]["status"] == "done"
    assert doc["spec"].get("closed_at")  # terminal → closed_at stamped


def test_set_status_invalid_rejected_no_write(dna_dir):
    """An invalid target status raises InvalidTransition and NEVER writes a bad
    status (the doc keeps its prior status)."""
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await W.create_story_impl(
            live, "s-guard-me", feature="f-demo", description="x",
            acceptance_criteria=["a"], definition_of_done=["b"], scope=_SCOPE)
        with pytest.raises(W.InvalidTransition):
            await W.set_status_impl(live, "Story", "s-guard-me", "bogus", scope=_SCOPE)
        return await live.kernel.get_document(_SCOPE, "Story", "s-guard-me")

    doc = asyncio.run(scenario())
    assert doc["spec"]["status"] == "todo"  # unchanged — no bad write


def test_set_status_missing_doc_raises(dna_dir):
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        with pytest.raises(LookupError):
            await W.set_status_impl(live, "Story", "s-nope", "done", scope=_SCOPE)

    asyncio.run(scenario())


def test_create_issue_autonumbers(dna_dir):
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        a = await W.create_issue_impl(
            live, "first-bug", description="boom", issue_type="bug",
            severity="high", scope=_SCOPE)
        b = await W.create_issue_impl(
            live, "second-task", description="todo", issue_type="task",
            severity="low", scope=_SCOPE)
        digest = await M.sdlc_digest_impl(live, since="99d", scope=_SCOPE)
        return a, b, digest

    a, b, _digest = asyncio.run(scenario())
    assert a["kind"] == "Issue" and a["name"].startswith("i-")
    assert b["name"] != a["name"]  # auto-incremented
    # both numbers are distinct + zero-padded i-NNN-<slug>.
    assert a["name"].split("-")[1] != b["name"].split("-")[1]


def test_comment_lands_on_timeline_without_status_change(dna_dir):
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await W.create_story_impl(
            live, "s-narrate-me", feature="f-demo", description="x",
            acceptance_criteria=["a"], definition_of_done=["b"], scope=_SCOPE)
        note = await W.comment_impl(
            live, "Story", "s-narrate-me", "agora vou fazer X", scope=_SCOPE)
        decision = await W.comment_impl(
            live, "Story", "s-narrate-me", "Decidi Y porque Z", scope=_SCOPE)
        doc = await live.kernel.get_document(_SCOPE, "Story", "s-narrate-me")
        return note, decision, doc

    note, decision, doc = asyncio.run(scenario())
    assert note["event_type"] == "comment"
    assert decision["event_type"] == "decision"  # auto-promoted
    types = [e["type"] for e in doc["spec"]["timeline"]]
    assert "comment" in types and "decision" in types
    assert doc["spec"]["status"] == "todo"  # status untouched by a comment


def test_create_feature_impl(dna_dir):
    from dna_cli import _mcp_server as M

    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        out = await W.create_feature_impl(
            live, "f-made-over-mcp", title="Made over MCP",
            description="a feature filed by an agent", priority="high",
            scope=_SCOPE)
        doc = await live.kernel.get_document(_SCOPE, "Feature", "f-made-over-mcp")
        return out, doc

    out, doc = asyncio.run(scenario())
    assert out == {"kind": "Feature", "name": "f-made-over-mcp", "status": "discovery"}
    assert doc["spec"]["title"] == "Made over MCP"
    assert doc["spec"]["reporter"] == "mcp"


def test_write_is_workspace_scope_isolated(dna_dir):
    """The SDLC board Kinds are TenantScope.GLOBAL — isolation is by SCOPE, not a
    tenant overlay (writing with a tenant would raise TenantNotAllowed). Under
    Model B a workspace's scope-less write routes into its OWN scope
    (``default_scope(workspace)``), so workspace A's board never lands in workspace
    B's scope, and the reserved vendor workspace still routes to the base scope."""
    from dna.application import LiveDna
    from dna_cli import _mcp_server as M

    async def scenario():
        booted = await M.boot_live(base_dir=str(dna_dir))
        # Model B multi-workspace: vendor workspace #1 → base scope; others → own.
        live = LiveDna(
            base_scope=booted.base_scope, kernel=booted.kernel,
            provider=booted.provider, vendor_workspace="vendor-1",
            workspace_scope_prefix="tenant-",
        )
        # workspace "acme" → scope "tenant-acme"; scope-less, tenant selects it.
        await W.create_story_impl(
            live, "s-acme-board", feature="f-demo", description="x",
            acceptance_criteria=["a"], definition_of_done=["b"], tenant="acme")
        # the reserved vendor workspace → base scope.
        await W.create_story_impl(
            live, "s-vendor-board", feature="f-demo", description="y",
            acceptance_criteria=["a"], definition_of_done=["b"], tenant="vendor-1")
        acme = await M.list_stories_impl(live, tenant="acme")     # scope tenant-acme
        vendor = await M.list_stories_impl(live, tenant="vendor-1")  # base scope
        return acme, vendor

    acme, vendor = asyncio.run(scenario())
    assert acme["scope"] == "tenant-acme"
    assert "s-acme-board" in {s["name"] for s in acme["stories"]}
    # acme's board is in its own scope — the vendor/base scope never sees it.
    assert "s-acme-board" not in {s["name"] for s in vendor["stories"]}
    # the vendor workspace routed to the base scope.
    assert vendor["scope"] == _SCOPE
    assert "s-vendor-board" in {s["name"] for s in vendor["stories"]}


# ── 4. plan-guard over a real token (sdlc_mode: read vs write) ──────────────


def _reset_store() -> None:
    Q.DEFAULT_STORE._day_counts.clear()  # type: ignore[attr-defined]
    Q.DEFAULT_STORE._calls.clear()  # type: ignore[attr-defined]


def _tier_doc(tier_id: str, *, families: list[str], sdlc_mode: str,
              memory_mode: str = "read") -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/cloud/v1",
        "kind": "Tier",
        "metadata": {"name": tier_id},
        "spec": {
            "tier_id": tier_id,
            "display_name": tier_id.title(),
            "price_usd_month": 0,
            "calls_per_day": 10000,
            "rate_per_sec": 100,
            "max_tenants": 1,
            "feature_families": families,
            "memory_mode": memory_mode,
            "sdlc_mode": sdlc_mode,
        },
    }


async def _seed_tiers(dna_dir) -> None:
    from dna_cli import _mcp_server as M

    live = await M.boot_live(base_dir=str(dna_dir))
    # Free KEEPS `sdlc` in families (reads pass the family gate) but sdlc_mode=read
    # → a WRITE is denied by the finer gate, not the family gate.
    await live.kernel.write_document(
        "_lib", "Tier", "free",
        _tier_doc("free", families=["definitions", "sdlc", "memory"],
                  sdlc_mode="read"))
    await live.kernel.write_document(
        "_lib", "Tier", "pro",
        _tier_doc("pro", families=["definitions", "sdlc", "memory", "emit"],
                  sdlc_mode="write", memory_mode="write"))


def _verifier_and_mint():
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer=_ISSUER, audience=_AUDIENCE)

    def mint(*, tenant: str | None, plan: str | None):
        claims: dict = {}
        if tenant:
            claims["tenant"] = tenant
        if plan:
            claims["plan"] = plan
        return kp.create_token(
            issuer=_ISSUER, audience=_AUDIENCE, subject="user-1",
            scopes=["dna.read"], additional_claims=claims,
        )

    return verifier, mint


def test_read_tier_lists_stories_but_write_denied(dna_dir, http_server):
    """A Free (sdlc_mode=read) token: ``list_stories`` is allowed (read), but
    ``create_story`` is DENIED — by ``sdlc_mode`` (sdlc IS in Free's families)."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    asyncio.run(_seed_tiers(dna_dir))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="free")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            res = await client.call_tool("list_stories", {"scope": _SCOPE})
            assert "stories" in res.structured_content
            with pytest.raises(Exception) as ei:  # noqa: PT011
                await client.call_tool(
                    "create_story",
                    {"name": "s-should-be-denied", "feature": "f-x",
                     "description": "nope", "scope": _SCOPE})
            msg = str(ei.value).lower()
            assert "sdlc_mode" in msg or "write" in msg

    with http_server(server) as url:
        asyncio.run(go(url))


def test_write_tier_create_story_ok(dna_dir, http_server):
    """A Pro (sdlc_mode=write) token: ``create_story`` is allowed and the Story
    round-trips through ``list_stories`` (in the caller's tenant overlay)."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    asyncio.run(_seed_tiers(dna_dir))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="pro")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            out = await client.call_tool(
                "create_story",
                {"name": "s-pro-write", "feature": "f-x",
                 "description": "the board is writable over MCP", "scope": _SCOPE})
            assert out.structured_content["name"] == "s-pro-write"
            listed = await client.call_tool("list_stories", {"scope": _SCOPE})
            names = {s["name"] for s in listed.structured_content["stories"]}
            assert "s-pro-write" in names

    with http_server(server) as url:
        asyncio.run(go(url))


def test_set_status_and_comment_denied_on_read_tier(dna_dir, http_server):
    """Both ``set_status`` and ``comment`` are writes → denied on a Free
    (sdlc_mode=read) token."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    asyncio.run(_seed_tiers(dna_dir))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="free")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            for tool, args in (
                ("set_status", {"kind": "Story", "name": "s-x", "status": "done",
                                "scope": _SCOPE}),
                ("comment", {"kind": "Story", "name": "s-x", "body": "hi",
                             "scope": _SCOPE}),
                ("create_issue", {"slug": "x", "description": "y", "scope": _SCOPE}),
                ("create_feature", {"name": "f-x", "title": "t", "description": "d",
                                    "scope": _SCOPE}),
            ):
                with pytest.raises(Exception) as ei:  # noqa: PT011
                    await client.call_tool(tool, args)
                msg = str(ei.value).lower()
                assert "sdlc_mode" in msg or "write" in msg, (tool, msg)

    with http_server(server) as url:
        asyncio.run(go(url))
