"""Story ``s-ws-res-mcp-auth`` / ``s-ws-res-source`` — Model B workspace
isolation, END-TO-END over real JWT + HTTP.

The security acceptance test: with WorkspaceMembership grants seeded and
``DNA_VENDOR_WORKSPACE`` set, prove there is **no cross-workspace leakage** —

* an identity resolves to the workspace it holds an ACTIVE membership in (from
  the verified oid/email, NOT the Azure tid);
* a member of workspace A that requests workspace B (a workspace it is NOT a
  member of) is DENIED (fail-closed);
* a member of B naming A's SCOPE explicitly is DENIED (cross-workspace scope
  binding) — even the physical scope key is bound;
* a member of B reading its own default scope sees NONE of A's data;
* an authenticated identity with NO active membership gets NOTHING.

Plus the legacy-fallback guard: with NO memberships configured the source runs
the pre-Model-B tid tenancy unchanged (proved by the existing test_mcp_auth.py
suite — a token's ``tenant`` claim still scopes it — so this file only asserts
the Model-B-engaged path).

The token here carries Entra IDENTITY claims (``oid`` + ``email``) — the tid is
provenance only and is deliberately NOT the tenant. Reuses the s-mcp-oauth-auth
HTTP harness (``http_server``, ``dna_dir``).
"""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the 'fastmcp' extra")

from dna_cli import _mcp_server as M  # noqa: E402
from test_mcp_auth import _AGENT, _SCOPE, dna_dir  # noqa: E402,F401,F811

# Workspace #1 (the vendor) — its id maps to the base scope (`concierge` here,
# the example source's base). A second, outside workspace gets its OWN scope.
_WS_VENDOR = "ws-vendor"
_WS_OUTSIDE = "ws-outside"
_ISSUER = "https://dna.test/"
_AUDIENCE = "dna-mcp"


# bob's OWN workspace scope (default_scope(ws-outside) with prefix `tenant-`).
_OUTSIDE_SCOPE = f"tenant-{_WS_OUTSIDE}"
_BOB_AGENT = "outside-bot"


def _seed(dna_dir):
    """Seed the identity→workspace boundary + a distinct agent in bob's own
    workspace scope, so isolation is OBSERVABLE both ways.

    * two ACTIVE WorkspaceMembership grants (GLOBAL, `_lib`): alice→vendor,
      bob→outside;
    * one Agent in bob's own scope (`tenant-ws-outside`) that is NOT `_AGENT` —
      so bob's default read returns HIS agent, never the vendor's.
    """
    async def go():
        # Pin the base scope to the example source's own scope — seeding grants
        # into `_lib` (and bob's agent into his scope) would otherwise make the
        # "sole scope" resolution ambiguous.
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        grants = [
            (_WS_VENDOR, "alice@a.com", "oid-alice", "owner"),
            (_WS_OUTSIDE, "bob@b.com", "oid-bob", "owner"),
        ]
        for ws, email, oid, role in grants:
            name = f"{ws}--{email.replace('@', '-at-').replace('.', '-')}"
            doc = {
                "apiVersion": "github.com/ruinosus/dna/tenant/v1",
                "kind": "WorkspaceMembership",
                "metadata": {"name": name},
                "spec": {
                    "workspace_id": ws,
                    "identity_email": email,
                    "identity_oid": oid,
                    "identity_tid": "some-azure-org",  # provenance only
                    "role": role,
                    "status": "active",
                },
            }
            await live.kernel.write_document("_lib", "WorkspaceMembership", name, doc)

        # A distinct agent in bob's own workspace scope — proves bob reads HIS
        # data, never the vendor's, on a scope-less default read.
        await live.kernel.write_document(
            _OUTSIDE_SCOPE, "Agent", _BOB_AGENT,
            {
                "apiVersion": "github.com/ruinosus/dna/v1",
                "kind": "Agent",
                "metadata": {"name": _BOB_AGENT},
                "spec": {"instruction": "I am the outside workspace's own agent."},
            },
        )

    asyncio.run(go())


def _verifier_and_identity_tokens():
    """A JWTVerifier + a minter that stamps Entra IDENTITY claims (oid + email),
    NOT a tenant claim — Model B resolves the workspace from membership."""
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer=_ISSUER, audience=_AUDIENCE)

    def mint(oid: str | None, email: str | None):
        claims: dict[str, str] = {"tid": "some-azure-org"}  # provenance, not tenant
        if oid:
            claims["oid"] = oid
        if email:
            claims["email"] = email
        return kp.create_token(
            issuer=_ISSUER, audience=_AUDIENCE, subject=oid or "anon",
            scopes=["dna.read"], additional_claims=claims,
        )

    return verifier, mint


def _build(dna_dir, monkeypatch, verifier):
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", _WS_VENDOR)  # engage Model B.
    return M.build_server(base_dir=str(dna_dir), scope=_SCOPE, auth=verifier)


async def _compose(url, token, *, tenant=None):
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    args = {"agent": _AGENT, "scope": _SCOPE}
    if tenant is not None:
        args["tenant"] = tenant
    async with Client(url, auth=BearerAuth(token)) as client:
        res = await client.call_tool("compose_prompt", args)
        return res.structured_content


async def _list_agents(url, token, *, scope=None, tenant=None):
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    args: dict = {}
    if scope is not None:
        args["scope"] = scope
    if tenant is not None:
        args["tenant"] = tenant
    async with Client(url, auth=BearerAuth(token)) as client:
        res = await client.call_tool("list_agents", args)
        return res.structured_content


def test_identity_resolves_to_its_workspace(dna_dir, http_server, monkeypatch):
    """Alice (verified oid/email, member of the vendor workspace) resolves to it
    and reads the vendor's base scope — the workspace came from her MEMBERSHIP,
    not from the token's tid."""
    _seed(dna_dir)
    verifier, mint = _verifier_and_identity_tokens()
    server = _build(dna_dir, monkeypatch, verifier)
    alice = mint("oid-alice", "alice@a.com")

    with http_server(server) as url:
        # No `tenant` arg — resolved purely from her identity's sole membership.
        out = asyncio.run(_compose(url, alice))
        assert out["tenant"] == _WS_VENDOR  # resolved workspace, not the tid.
        assert "Helpdesk Concierge" in out["prompt"]  # vendor base-scope data.


def test_member_denied_requesting_foreign_workspace(dna_dir, http_server, monkeypatch):
    """ISOLATION: alice (member of the vendor workspace) asking for the OUTSIDE
    workspace she is not a member of is DENIED (fail-closed)."""
    _seed(dna_dir)
    verifier, mint = _verifier_and_identity_tokens()
    server = _build(dna_dir, monkeypatch, verifier)
    alice = mint("oid-alice", "alice@a.com")

    async def go(url):
        from fastmcp import Client
        from fastmcp.client.auth import BearerAuth

        async with Client(url, auth=BearerAuth(alice)) as client:
            with pytest.raises(Exception) as ei:  # noqa: PT011
                await client.call_tool(
                    "compose_prompt",
                    {"agent": _AGENT, "scope": _SCOPE, "tenant": _WS_OUTSIDE},
                )
            assert "not an active member" in str(ei.value).lower() \
                or "workspace" in str(ei.value).lower()

    with http_server(server) as url:
        asyncio.run(go(url))


def test_outside_member_cannot_reach_vendor_scope(dna_dir, http_server, monkeypatch):
    """ISOLATION (scope binding): bob (member of the OUTSIDE workspace) naming the
    vendor's SCOPE explicitly is DENIED — the physical scope key is bound to his
    workspace, so he cannot read the vendor's rows even by scope."""
    _seed(dna_dir)
    verifier, mint = _verifier_and_identity_tokens()
    server = _build(dna_dir, monkeypatch, verifier)
    bob = mint("oid-bob", "bob@b.com")

    async def go(url):
        from fastmcp import Client
        from fastmcp.client.auth import BearerAuth

        async with Client(url, auth=BearerAuth(bob)) as client:
            with pytest.raises(Exception) as ei:  # noqa: PT011
                await client.call_tool("list_agents", {"scope": _SCOPE})  # vendor's scope
            assert "cross-workspace" in str(ei.value).lower()

    with http_server(server) as url:
        asyncio.run(go(url))


def test_outside_member_default_scope_sees_no_vendor_data(dna_dir, http_server, monkeypatch):
    """ISOLATION: bob reading his OWN default scope (tenant-ws-outside, empty)
    sees NONE of the vendor's agents — no leakage across workspaces."""
    _seed(dna_dir)
    verifier, mint = _verifier_and_identity_tokens()
    server = _build(dna_dir, monkeypatch, verifier)
    bob = mint("oid-bob", "bob@b.com")

    with http_server(server) as url:
        out = asyncio.run(_list_agents(url, bob))  # no scope → his own default.
        assert out["scope"] == _OUTSIDE_SCOPE  # routed to HIS scope, not vendor.
        names = [a["name"] for a in out["agents"]]
        assert _BOB_AGENT in names            # bob sees HIS own agent.
        assert _AGENT not in names            # and NONE of the vendor's data.


def test_no_membership_denied(dna_dir, http_server, monkeypatch):
    """An authenticated identity with NO active membership gets NOTHING
    (fail-closed) once workspaces are configured."""
    _seed(dna_dir)
    verifier, mint = _verifier_and_identity_tokens()
    server = _build(dna_dir, monkeypatch, verifier)
    carol = mint("oid-carol", "carol@nowhere.com")  # not seeded anywhere.

    async def go(url):
        from fastmcp import Client
        from fastmcp.client.auth import BearerAuth

        async with Client(url, auth=BearerAuth(carol)) as client:
            with pytest.raises(Exception) as ei:  # noqa: PT011
                await client.call_tool("compose_prompt", {"agent": _AGENT, "scope": _SCOPE})
            assert "no active workspace membership" in str(ei.value).lower()

    with http_server(server) as url:
        asyncio.run(go(url))
