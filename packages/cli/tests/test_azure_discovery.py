"""P1 zero-config discovery surface under ``AzureProvider`` (CI mirror of the
gate-0 curl). Boots the real DNA MCP with the Lane-A facade and asserts the
OAuth 2.1 metadata Claude's connector auto-discovery relies on:

* RFC 8414 authorization-server metadata — ``/register`` (DCR), ``S256``, CIMD, ``none``;
* the ``401 + WWW-Authenticate: … resource_metadata="…"`` challenge (a 401, never a 200);
* RFC 9728 protected-resource-metadata — the MCP scope the client must request.
"""
from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("fastmcp", reason="the MCP HTTP face needs the 'fastmcp' extra")
pytest.importorskip("httpx", reason="the discovery test needs Starlette's TestClient (httpx)")

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_CID = "ff09090f-79e3-4dfe-975c-1a8e007112b7"


@pytest.fixture
def azure_app(monkeypatch):
    monkeypatch.setenv("DNA_MCP_AZURE_CLIENT_ID", _CID)
    monkeypatch.setenv("DNA_MCP_AZURE_CLIENT_SECRET", "s3cr3t")
    monkeypatch.setenv("DNA_MCP_AZURE_TENANT", "organizations")
    monkeypatch.setenv("DNA_MCP_AZURE_BASE_URL", "http://localhost:8765")
    monkeypatch.setenv("DNA_MCP_AZURE_IDENTIFIER_URI", "api://dna-mcp-dnacloud")
    from dna_cli._mcp_auth import azure_provider_from_env
    from dna_cli._mcp_server import build_http_app, build_server

    provider = azure_provider_from_env()
    server = build_server(scope="concierge", base_dir=str(_BASE), auth=provider)
    return build_http_app(server, path="/mcp", transport="http")


def test_as_metadata_advertises_zero_config(azure_app):
    from starlette.testclient import TestClient

    with TestClient(azure_app) as client:
        r = client.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    m = r.json()
    assert m.get("registration_endpoint"), "DCR /register not advertised"
    assert m.get("code_challenge_methods_supported") == ["S256"]
    assert m.get("client_id_metadata_document_supported") is True, "CIMD not advertised"
    assert "none" in m.get("token_endpoint_auth_methods_supported", [])


def test_unauthenticated_request_challenges_with_resource_metadata(azure_app):
    from starlette.testclient import TestClient

    with TestClient(azure_app) as client:
        r = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            headers={"Accept": "application/json, text/event-stream"},
        )
    assert r.status_code == 401, "an MCP client keys off a 401, never a 200"
    assert "resource_metadata" in r.headers.get("www-authenticate", "").lower()


def test_protected_resource_metadata_names_the_mcp_scope(azure_app):
    from starlette.testclient import TestClient

    with TestClient(azure_app) as client:
        r = client.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    scopes = r.json().get("scopes_supported", [])
    assert any("user_impersonation" in s for s in scopes), scopes
