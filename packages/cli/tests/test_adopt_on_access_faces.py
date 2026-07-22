"""Adopt-on-access at the FACES — the i-058 hardening's mutation tripwires.

The core properties (cache, single-flight, intent preservation, OSS baseline)
live in ``packages/sdk-py/tests/test_workspace_adopt_on_access.py``. This file
proves the hook is actually WIRED at every place a request resolves a
workspace — each test dies if its face's ``adopt_workspace_scope_on_access``
call is removed:

* **MCP ``_guard``** (the production symptom): the FIRST ``compose_prompt`` /
  ``list_agents`` over a Genome-less workspace already composes the base's
  definitions — in that SAME call — and the workspace scope's Genome exists
  afterwards, declaring the configured base as ``parent_scope``.
* **REST ``--auth token``** (the portal's shared-bearer lane): a
  ``tenant=<workspace>`` read adopts before the route impl lists.
* **REST ``--auth config``** (the verified-identity lane): the middleware's
  membership bind adopts the workspace it just resolved.
* the face-level OSS baseline: WITHOUT the env the same MCP call still finds
  nothing and writes nothing — adoption never turns on by magic.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the 'fastmcp' extra")
pytest.importorskip("fastapi", reason="the REST face needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _mcp_server as M  # noqa: E402
from dna_cli import _rest_api as R  # noqa: E402
from test_mcp_auth import _AGENT, _SCOPE, dna_dir  # noqa: E402,F401

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_WS_VENDOR = "ws-vendor"
_WS_OUTSIDE = "ws-outside"
_OUTSIDE_SCOPE = f"tenant-{_WS_OUTSIDE}"
_ISSUER = "https://dna.test/"
_AUDIENCE = "dna-mcp"
_TOKEN = "portal-shared-token-mvp"  # a fake shared token, NOT a real secret.


def _seed_membership(dna_dir, ws: str, email: str, oid: str) -> None:
    """One ACTIVE WorkspaceMembership (GLOBAL, `_lib`) — the identity→workspace
    boundary the guard resolves."""
    async def go():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        name = f"{ws}--{email.replace('@', '-at-').replace('.', '-')}"
        await live.kernel.write_document(
            "_lib", "WorkspaceMembership", name,
            {"apiVersion": "github.com/ruinosus/dna/tenant/v1",
             "kind": "WorkspaceMembership", "metadata": {"name": name},
             "spec": {"workspace_id": ws, "identity_email": email,
                      "identity_oid": oid, "identity_tid": "some-azure-org",
                      "role": "owner", "status": "active"}},
        )
    asyncio.run(go())


def _genome_parent(dna_dir, scope: str) -> str | None:
    """The scope's declared ``parent_scope`` (None when no Genome exists)."""
    async def go():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        try:
            doc = await live.kernel.get_document(scope, "Genome", scope)
        except (FileNotFoundError, ValueError):
            return None
        return ((doc or {}).get("spec") or {}).get("parent_scope")
    return asyncio.run(go())


def _verifier_and_mint():
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer=_ISSUER,
                           audience=_AUDIENCE)

    def mint(oid: str, email: str):
        return kp.create_token(
            issuer=_ISSUER, audience=_AUDIENCE, subject=oid,
            scopes=["dna.read"],
            additional_claims={"tid": "some-azure-org", "oid": oid, "email": email},
        )

    return verifier, mint


async def _call(url, token, tool, args):
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    async with Client(url, auth=BearerAuth(token)) as client:
        res = await client.call_tool(tool, args)
        return res.structured_content


# ── MCP `_guard`: the production symptom, closed in the SAME call ───────────


def test_mcp_first_compose_over_a_genomeless_workspace_adopts_and_finds(
    dna_dir, http_server, monkeypatch,
):
    """The exact production failure, inverted: bob's workspace scope has NO
    Genome (born before the base existed); his FIRST compose_prompt — no
    scope, no prior sign-in, no provision-owner ever called — adopts on
    access and composes the vendor base's agent in that same call."""
    _seed_membership(dna_dir, _WS_OUTSIDE, "bob@b.com", "oid-bob")
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", _WS_VENDOR)
    monkeypatch.setenv("DNA_WORKSPACE_DEFINITIONS_BASE", _SCOPE)
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), scope=_SCOPE, auth=verifier)
    bob = mint("oid-bob", "bob@b.com")

    assert _genome_parent(dna_dir, _OUTSIDE_SCOPE) is None  # truly Genome-less.

    with http_server(server) as url:
        out = asyncio.run(_call(url, bob, "compose_prompt", {"agent": _AGENT}))
        assert out["tenant"] == _WS_OUTSIDE  # resolved workspace, bound scope.
        assert "Helpdesk Concierge" in out["prompt"]  # the BASE's definition.

        # And the definition surfaces agree, still inside this process/session.
        listed = asyncio.run(_call(url, bob, "list_agents", {}))
        assert _AGENT in {a["name"] for a in listed["agents"]}

    # The adoption is durable: the scope's Genome now declares the base.
    assert _genome_parent(dna_dir, _OUTSIDE_SCOPE) == _SCOPE


def test_mcp_without_the_env_nothing_is_adopted(dna_dir, http_server, monkeypatch):
    """The face-level OSS baseline (anti-vacuity): no configured base → the
    same first call still finds nothing to inherit and writes NO Genome —
    adoption never turns on by magic."""
    _seed_membership(dna_dir, _WS_OUTSIDE, "bob@b.com", "oid-bob")
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", _WS_VENDOR)
    monkeypatch.delenv("DNA_WORKSPACE_DEFINITIONS_BASE", raising=False)
    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), scope=_SCOPE, auth=verifier)
    bob = mint("oid-bob", "bob@b.com")

    with http_server(server) as url:
        with pytest.raises(Exception, match="(?i)not found|no agent"):
            asyncio.run(_call(url, bob, "compose_prompt", {"agent": _AGENT}))

    assert _genome_parent(dna_dir, _OUTSIDE_SCOPE) is None


# ── REST `--auth token` (the portal's shared-bearer lane) ────────────────────


def test_rest_token_lane_adopts_on_the_tenant_param(dna_dir, monkeypatch):
    """The portal lane: a `tenant=<workspace>` read under the trusted shared
    bearer adopts before the route lists — the console's /v1/agents over a
    fresh workspace already shows the curated base."""
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", _WS_VENDOR)
    monkeypatch.setenv("DNA_WORKSPACE_DEFINITIONS_BASE", _SCOPE)
    app = R.build_app(base_dir=str(dna_dir), scope=_SCOPE,
                      auth="token", token=_TOKEN)
    with TestClient(app) as c:
        r = c.get("/v1/agents", params={"tenant": _WS_OUTSIDE},
                  headers={"Authorization": f"Bearer {_TOKEN}"})
        assert r.status_code == 200, r.text
        assert _AGENT in {a["name"] for a in r.json()["agents"]}

    assert _genome_parent(dna_dir, _OUTSIDE_SCOPE) == _SCOPE


# ── REST `--auth config` (the verified-identity lane) ────────────────────────


class _FakeAccess:
    def __init__(self, claims):
        self.claims = claims


class _FakeVerifier:
    def __init__(self, table):
        self._table = table

    async def verify_token(self, token):
        claims = self._table.get(token)
        return _FakeAccess(claims) if claims is not None else None


def test_rest_config_lane_adopts_the_membership_bound_workspace(
    dna_dir, monkeypatch,
):
    """The verified-identity lane: the middleware resolves bob's workspace
    from his ACTIVE membership and adopts it right there — the same request's
    /v1/agents read already inherits the base."""
    _seed_membership(dna_dir, _WS_OUTSIDE, "bob@b.com", "oid-bob")
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", _WS_VENDOR)
    monkeypatch.setenv("DNA_WORKSPACE_DEFINITIONS_BASE", _SCOPE)
    app = R.build_app(
        base_dir=str(dna_dir), scope=_SCOPE, auth="config",
        verifier=_FakeVerifier(
            {"bob": {"oid": "oid-bob", "email": "bob@b.com", "tid": "org-b"}}),
    )
    with TestClient(app) as c:
        r = c.get("/v1/agents", headers={"Authorization": "Bearer bob"})
        assert r.status_code == 200, r.text
        assert _AGENT in {a["name"] for a in r.json()["agents"]}

    assert _genome_parent(dna_dir, _OUTSIDE_SCOPE) == _SCOPE
