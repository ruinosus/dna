"""Feature ``f-cloud-multitenant`` — the REST **token→tenant** edge (audit H3).

``dna api serve --auth config`` verifies a USER bearer JWT against the SAME
pluggable N-provider IdP layer the MCP server uses (``dna.config.yaml``'s
``auth.providers[]``, reused via ``dna_cli._mcp_auth``) and BINDS the request's
``tenant`` to the token's claim — so ``?tenant=`` stops being caller-supplied:

* a valid token → its tenant overrides any ``?tenant=`` the caller sends;
* no bearer → 401;
* a token with no tenant claim → 403 (fail-closed, the MCP-bridge policy).

The verifier is a static-key ``oidc`` provider (a test RSA keypair) — no JWKS
fetch, no external IdP.
"""
from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("fastmcp", reason="the token→tenant edge needs the 'fastmcp' extra")
pytest.importorskip("fastapi")

from fastmcp.server.auth.providers.jwt import RSAKeyPair  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_ISSUER = "https://dna.test/"
_AUDIENCE = "dna-mcp"


def test_force_tenant_qs_drops_caller_tenant_and_binds_token():
    # a caller-supplied tenant is dropped; other params survive; token wins.
    out = R._force_tenant_qs(b"scope=x&tenant=globex&k=5", "acme")
    from urllib.parse import parse_qsl

    d = dict(parse_qsl(out.decode()))
    assert d["tenant"] == "acme"
    assert d["scope"] == "x"
    assert d["k"] == "5"


@pytest.fixture
def config_app(tmp_path, monkeypatch):
    """Build the REST app in ``--auth config`` mode against a static-key oidc
    provider, and mint tokens for it. cwd holds the dna.config.yaml the middleware
    reads; DNA_BASE_DIR points the source at the example scope."""
    from fastapi.testclient import TestClient

    kp = RSAKeyPair.generate()
    cfg = tmp_path / "dna.config.yaml"
    cfg.write_text(
        "source: file://.dna\n"
        "auth:\n"
        "  providers:\n"
        "    - type: oidc\n"
        f"      issuer: {_ISSUER}\n"
        f"      audience: {_AUDIENCE}\n"
        "      tenant_claim: tenant\n"
        "      public_key: |\n"
        + "".join(f"        {line}\n" for line in kp.public_key.splitlines()),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DNA_BASE_DIR", str(_BASE))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)

    app = R.build_app(auth="config")

    def mint(tenant: str | None):
        claims = {"tenant": tenant} if tenant else {}
        return kp.create_token(
            issuer=_ISSUER, audience=_AUDIENCE, subject="user-1",
            scopes=["dna.read"], additional_claims=claims,
        )

    return TestClient(app), mint


def test_health_is_open(config_app):
    client, _ = config_app
    assert client.get("/health").status_code == 200


def test_missing_bearer_is_401(config_app):
    client, _ = config_app
    assert client.get("/v1/memories").status_code == 401


def test_invalid_bearer_is_401(config_app):
    client, _ = config_app
    r = client.get("/v1/memories", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_tokenless_tenant_is_403(config_app):
    client, mint = config_app
    r = client.get(
        "/v1/memories", headers={"Authorization": f"Bearer {mint(None)}"}
    )
    assert r.status_code == 403


def test_tenant_bound_from_token_overrides_query(config_app):
    """The token's tenant WINS over a caller-supplied ``?tenant=`` — the response
    echoes the token's tenant (``acme``), not the forged ``globex``."""
    client, mint = config_app
    r = client.get(
        "/v1/memories?tenant=globex",
        headers={"Authorization": f"Bearer {mint('acme')}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["tenant"] == "acme"
