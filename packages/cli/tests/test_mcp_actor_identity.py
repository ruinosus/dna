"""A board timeline records WHO wrote the row, not just HOW it arrived.

Every board write ever made over MCP was attributed to the literal actor
``"mcp"``: ``dna.application.sdlc`` defaults ``actor="mcp", source="mcp"`` and not
one of the five write tools ever overrode it. So the founder, an autonomous agent
and a paying customer were the same author, and the one question a timeline exists
to answer — who did this? — had no answer, on any board, ever.

The two axes are now separate:

* ``source`` stays ``"mcp"`` — the CHANNEL the write arrived through.
* ``actor`` becomes the IDENTITY, resolved SERVER-SIDE from the verified token
  (never a tool argument — attribution a caller can forge is not attribution).

An unauthenticated local call records ``mcp:local`` rather than ``mcp``: it is
honestly unidentified, and saying so is different from claiming the channel is a
person. An operator who declared ``DNA_PERSONAL_ID`` (already the offline identity
knob for personal memory) gets that name instead.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

from dna_cli._mcp_auth import (
    UNIDENTIFIED_LOCAL_ACTOR,
    UNIDENTIFIED_TOKEN_ACTOR,
    actor_from_context,
)

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_ISSUER = "https://dna.test/"
_AUDIENCE = "dna-mcp"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    return dst


# ── the resolver, outside any request ───────────────────────────────────────


def test_no_token_records_an_honestly_unidentified_local_actor(monkeypatch):
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    assert actor_from_context() == UNIDENTIFIED_LOCAL_ACTOR
    assert actor_from_context() != "mcp"  # never the channel name


def test_an_offline_operator_who_named_themselves_is_recorded(monkeypatch):
    """``DNA_PERSONAL_ID`` is already how an offline caller names itself for
    personal memory — reusing it means a self-hosted user's board rows carry their
    name with no second knob to discover."""
    monkeypatch.setenv("DNA_PERSONAL_ID", "barna@example.test")
    assert actor_from_context() == "barna@example.test"


# ── over a real, authenticated request ─────────────────────────────────────


def _verifier_and_mint():
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer=_ISSUER,
                           audience=_AUDIENCE)

    def mint(**claims):
        return kp.create_token(
            issuer=_ISSUER, audience=_AUDIENCE, subject="subject-1",
            scopes=["dna.read"], additional_claims=claims,
        )

    return verifier, mint


async def _seed_pro_plan(dna_dir) -> None:
    from dna_cli import _mcp_server as M

    live = await M.boot_live(base_dir=str(dna_dir))
    await live.kernel.write_document("_lib", "PricingPlan", "pro", {
        "apiVersion": "github.com/ruinosus/dna/cloud/v1",
        "kind": "PricingPlan", "metadata": {"name": "pro"},
        "spec": {"tier_id": "pro", "display_name": "Pro", "price_usd_month": 29,
                 "calls_per_day": 10000, "rate_per_sec": 100, "max_tenants": 1,
                 "feature_families": ["definitions", "sdlc", "memory"],
                 "sdlc_mode": "write", "memory_mode": "write"},
    })


def _timeline(dna_dir, kind: str, name: str) -> list[dict]:
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        doc = await live.kernel.get_document(_SCOPE, kind, name)
        return list((doc or {}).get("spec", {}).get("timeline") or [])

    return asyncio.run(go())


def test_an_authenticated_write_records_the_verified_email(dna_dir, http_server):
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_quota as Q
    from dna_cli import _mcp_server as M

    Q.DEFAULT_STORE.reset()
    asyncio.run(_seed_pro_plan(dna_dir))
    verifier, mint = _verifier_and_mint()
    token = mint(tenant="acme", plan="pro", email="alice@acme.test",
                 oid="oid-alice")
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            await client.call_tool("create_story", {
                "name": "s-attributed", "feature": "f-x",
                "description": "who wrote this?", "scope": _SCOPE,
                "ac": ["Given X, when Y, then Z"], "dod": ["code+tests"]})
            await client.call_tool("comment", {
                "kind": "Story", "name": "s-attributed",
                "body": "narrating as myself", "scope": _SCOPE})
            await client.call_tool("set_status", {
                "kind": "Story", "name": "s-attributed", "status": "in-progress",
                "scope": _SCOPE})

    with http_server(server) as url:
        asyncio.run(go(url))

    events = _timeline(dna_dir, "Story", "s-attributed")
    assert len(events) == 3
    assert {e["actor"] for e in events} == {"alice@acme.test"}
    # the CHANNEL is still recorded, in its own field.
    assert {e["source"] for e in events} == {"mcp"}
    assert "mcp" not in {e["actor"] for e in events}


def test_the_durable_subject_is_used_when_there_is_no_email(dna_dir, http_server):
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_quota as Q
    from dna_cli import _mcp_server as M

    Q.DEFAULT_STORE.reset()
    asyncio.run(_seed_pro_plan(dna_dir))
    verifier, mint = _verifier_and_mint()
    token = mint(tenant="acme", plan="pro", oid="oid-only")
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            await client.call_tool("create_feature", {
                "name": "f-attributed", "title": "T", "description": "d",
                "scope": _SCOPE})

    with http_server(server) as url:
        asyncio.run(go(url))

    events = _timeline(dna_dir, "Feature", "f-attributed")
    assert [e["actor"] for e in events] == ["oid-only"]


def test_a_token_with_no_identity_claim_says_so(dna_dir, http_server):
    """A verified but anonymous token is a different fact from a local call, and
    still not the channel name."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_quota as Q
    from dna_cli import _mcp_server as M

    Q.DEFAULT_STORE.reset()
    asyncio.run(_seed_pro_plan(dna_dir))
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer=_ISSUER,
                           audience=_AUDIENCE)
    # No subject at all: no email, no oid, no sub.
    token = kp.create_token(
        issuer=_ISSUER, audience=_AUDIENCE, subject=None,
        scopes=["dna.read"], additional_claims={"tenant": "acme", "plan": "pro"})
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            await client.call_tool("create_issue", {
                "slug": "anon", "description": "filed by nobody",
                "scope": _SCOPE})

    with http_server(server) as url:
        asyncio.run(go(url))

    from dna.application import documents as D

    async def find():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await D.list_documents_impl(live, kind="Issue", scope=_SCOPE)

    listed = asyncio.run(find())
    names = [d["name"] for d in listed["documents"] if d["name"].endswith("-anon")]
    assert names, listed
    events = _timeline(dna_dir, "Issue", names[0])
    assert [e["actor"] for e in events] == [UNIDENTIFIED_TOKEN_ACTOR]


def test_a_local_stdio_write_is_marked_local_not_mcp(dna_dir):
    """The unauthenticated path keeps working — it just stops claiming to be a
    person called "mcp"."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))

    async def go():
        async with Client(server) as client:
            await client.call_tool("create_story", {
                "name": "s-local", "feature": "f-demo", "description": "d",
                "scope": _SCOPE,
                "ac": ["Given X, when Y, then Z"], "dod": ["code+tests"]})

    asyncio.run(go())
    events = _timeline(dna_dir, "Story", "s-local")
    assert [e["actor"] for e in events] == [UNIDENTIFIED_LOCAL_ACTOR]
    assert [e["source"] for e in events] == ["mcp"]
