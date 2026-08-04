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
# The story a cross-workspace write would plant in the vendor's scope (i-082).
_PLANTED = "s-planted-by-a-neighbour"


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


# ── i-082: a READ grant is a read grant, over the wire ──────────────────────
#
# `WorkspaceScopeGrant` lets bob's workspace reach the vendor's scope, and its
# Kind schema pins `access` to a one-member enum (`read`) with a comment saying
# widening it must be a deliberate schema change. Nothing enforced it: the binder
# had no read/write axis, so the row an operator wrote believing it was read-only
# also authorized cross-scope BOARD WRITES. These two tests are the promise the
# schema makes, executed end-to-end over real JWT + HTTP — the same grant, the
# same scope, admitting the read and refusing the write.


def _grant_bob_the_vendor_scope(dna_dir, monkeypatch):
    """One ACTIVE WorkspaceScopeGrant row: ws-outside may reach the vendor scope.

    Engages Model B FIRST (`_build` does it too, but this runs earlier): without
    it `default_scope("ws-outside")` is the base scope, and the impl rightly
    refuses to record a grant for a scope the workspace already owns."""
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", _WS_VENDOR)

    async def go():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        from dna.application.runtime import grant_workspace_scope_impl

        await grant_workspace_scope_impl(
            live, workspace_id=_WS_OUTSIDE, scope=_SCOPE,
            reason="the founder reads both boards", granted_by="ops@example.test",
        )

    asyncio.run(go())


def test_a_granted_workspace_reads_the_other_scope(dna_dir, http_server, monkeypatch):
    """The grant WORKS: bob, denied the vendor scope a moment ago, now reads it."""
    _seed(dna_dir)
    _grant_bob_the_vendor_scope(dna_dir, monkeypatch)
    verifier, mint = _verifier_and_identity_tokens()
    server = _build(dna_dir, monkeypatch, verifier)
    bob = mint("oid-bob", "bob@b.com")

    with http_server(server) as url:
        out = asyncio.run(_list_agents(url, bob, scope=_SCOPE))
        assert out["scope"] == _SCOPE
        assert _AGENT in [a["name"] for a in out["agents"]]  # the vendor's data.


def test_a_granted_workspace_is_refused_a_write_to_that_scope(
    dna_dir, http_server, monkeypatch,
):
    """...and it works ONLY as far as the row says. The same bob, the same grant,
    the same scope: a board WRITE is refused, and the refusal names the level."""
    _seed(dna_dir)
    _grant_bob_the_vendor_scope(dna_dir, monkeypatch)
    verifier, mint = _verifier_and_identity_tokens()
    server = _build(dna_dir, monkeypatch, verifier)
    bob = mint("oid-bob", "bob@b.com")

    async def go(url):
        from fastmcp import Client
        from fastmcp.client.auth import BearerAuth

        async with Client(url, auth=BearerAuth(bob)) as client:
            with pytest.raises(Exception) as ei:  # noqa: PT011
                # A FULLY VALID story — exit criteria and all. Without the access
                # axis this call succeeds and the row lands in the vendor's
                # scope; the refusal has to come from the binder, not from the
                # board core rejecting a malformed document for its own reasons.
                await client.call_tool("create_story", {
                    "name": _PLANTED,
                    "feature": "f-whatever",
                    "description": "a cross-workspace write nobody granted",
                    "ac": ["Given a read grant / When a write arrives / Then no"],
                    "dod": ["it never reaches the board"],
                    "scope": _SCOPE,
                })
            msg = str(ei.value).lower()
            assert "'read' access only" in msg  # the level the row records.
            assert "'write'" in msg             # what this call asked for.

    with http_server(server) as url:
        asyncio.run(go(url))

    # ...and nothing was written. The denial is the point, but the ABSENCE of the
    # document is the property — a refusal that still wrote would be worse.
    async def check():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        assert await live.kernel.get_document(_SCOPE, "Story", _PLANTED) is None

    asyncio.run(check())


# ── posse do board (bateria 04/08): o DONO escreve no board do próprio ──────
# projeto, sem grant e sem alargar o schema — a posse deriva do doc Project
# ("the scope is a rendering of (workspace, slug)", decisão A1). O teste da
# recusa cross-workspace acima CONTINUA valendo: o grant segue read-only.


def _plant_bob_project(dna_dir, monkeypatch, board_scope):
    """O Project do workspace do bob, com o ``board_scope`` derivado — o doc
    de onde a posse deriva. Model B engajado ANTES (senão ``default_scope``
    devolve o base scope e o doc nasce no lugar errado)."""
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", _WS_VENDOR)

    async def go():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        sc = live.default_scope(_WS_OUTSIDE)
        await live.kernel.with_tenant(_WS_OUTSIDE).write_document(
            sc, "Project", "projeto-bob",
            {
                "apiVersion": "github.com/ruinosus/dna/portfolio/v1",
                "kind": "Project",
                "metadata": {"name": "projeto-bob"},
                "spec": {
                    "workspace_id": _WS_OUTSIDE,
                    "name": "Projeto do Bob",
                    "slug": "projeto-bob",
                    "board_scope": board_scope,
                },
            },
        )

    asyncio.run(go())


def test_o_dono_escreve_no_board_do_proprio_projeto(dna_dir, http_server, monkeypatch):
    """A posse autoriza o write que o grant nunca poderia: mesmo binder, mesmo
    eixo read/write — mas o scope é o board de um Project DESTE workspace."""
    _seed(dna_dir)
    board = "projeto-bob-development"
    _plant_bob_project(dna_dir, monkeypatch, board)
    verifier, mint = _verifier_and_identity_tokens()
    server = _build(dna_dir, monkeypatch, verifier)
    bob = mint("oid-bob", "bob@b.com")

    async def go(url):
        from fastmcp import Client
        from fastmcp.client.auth import BearerAuth

        async with Client(url, auth=BearerAuth(bob)) as client:
            await client.call_tool("create_story", {
                "name": "story-do-dono",
                "feature": "f-do-dono",
                "description": "o dono escreve no board que criou",
                "ac": ["Given a posse / When o dono escreve / Then entra"],
                "dod": ["o doc existe no board scope"],
                "scope": board,
            })

    with http_server(server) as url:
        asyncio.run(go(url))

    async def check():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        assert await live.kernel.get_document(board, "Story", "story-do-dono") is not None

    asyncio.run(check())


def test_a_posse_nao_vaza_para_o_board_de_outro_workspace(
    dna_dir, http_server, monkeypatch,
):
    """O board do projeto do VENDOR continua negado ao bob: a posse deriva dos
    Projects DELE, e o board alheio não está entre eles."""
    _seed(dna_dir)
    _plant_bob_project(dna_dir, monkeypatch, "projeto-bob-development")
    verifier, mint = _verifier_and_identity_tokens()
    server = _build(dna_dir, monkeypatch, verifier)
    bob = mint("oid-bob", "bob@b.com")

    async def go(url):
        from fastmcp import Client
        from fastmcp.client.auth import BearerAuth

        async with Client(url, auth=BearerAuth(bob)) as client:
            with pytest.raises(Exception) as ei:  # noqa: PT011
                await client.call_tool("create_story", {
                    "name": "story-invasora",
                    "feature": "f-x",
                    "description": "x",
                    "ac": ["Given / When / Then"],
                    "dod": ["nunca"],
                    "scope": "projeto-do-vendor-development",
                })
            assert "denied" in str(ei.value).lower()

    with http_server(server) as url:
        asyncio.run(go(url))
