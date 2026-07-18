"""Lane A (Entra) provider factory — ``azure_provider_from_env``.

The P1 facade: a FastMCP ``AzureProvider`` (OAuthProxy) built from env. The
load-bearing behavior is the **multi-tenant issuer relax** (gate G0.2): real
Entra v2 tokens carry the caller's OWN tenant GUID as ``iss``, so a pinned
issuer rejects every partner-org token. For a multi-tenant authority
(``organizations``/``common``/``consumers``) the factory nulls the verifier's
issuer → validate by audience + signature only (the same policy the ``--auth
config`` path already uses). A single concrete tenant keeps the pinned issuer.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastmcp", reason="the MCP auth face needs the 'fastmcp' extra")

_CID = "ff09090f-79e3-4dfe-975c-1a8e007112b7"


def _base_env(monkeypatch, tenant: str) -> None:
    monkeypatch.setenv("DNA_MCP_AZURE_CLIENT_ID", _CID)
    monkeypatch.setenv("DNA_MCP_AZURE_CLIENT_SECRET", "s3cr3t")
    monkeypatch.setenv("DNA_MCP_AZURE_TENANT", tenant)
    monkeypatch.setenv("DNA_MCP_AZURE_BASE_URL", "http://localhost:8765")
    monkeypatch.setenv("DNA_MCP_AZURE_IDENTIFIER_URI", "api://dna-mcp-dnacloud")


def test_azure_provider_multitenant_relaxes_issuer(monkeypatch):
    _base_env(monkeypatch, "organizations")
    from dna_cli._mcp_auth import azure_provider_from_env

    p = azure_provider_from_env()
    # G0.2 fix: multi-tenant → issuer relaxed to audience+signature only.
    assert p._token_validator.issuer is None
    # audience = [client-id GUID, identifier_uri] (matches the live prod verifier).
    assert _CID in p._token_validator.audience
    assert "api://dna-mcp-dnacloud" in p._token_validator.audience


def test_azure_provider_single_tenant_keeps_issuer(monkeypatch):
    _base_env(monkeypatch, "c5b891f7-65c2-4417-a5af-22cab24dc1d5")
    from dna_cli._mcp_auth import azure_provider_from_env

    p = azure_provider_from_env()
    # A concrete single tenant → issuer stays pinned (only multi-tenant relaxes).
    assert p._token_validator.issuer is not None


def test_azure_provider_requires_core_env(monkeypatch):
    monkeypatch.delenv("DNA_MCP_AZURE_CLIENT_ID", raising=False)
    from dna_cli._mcp_auth import azure_provider_from_env

    with pytest.raises((RuntimeError, KeyError)):
        azure_provider_from_env()


def test_composite_falls_back_to_raw_entra_token(monkeypatch):
    """P1.5 — the facade also accepts a RAW Entra token (portal/copilot), not only
    its own DCR wire tokens: a token the facade path rejects (garbage wire JWT →
    super() returns None) is verified by the MCP-audienced ``_token_validator``."""
    import asyncio

    _base_env(monkeypatch, "organizations")
    from dna_cli._mcp_auth import azure_provider_from_env

    p = azure_provider_from_env()
    sentinel = object()

    async def _fake_raw(token):
        return sentinel

    monkeypatch.setattr(p._token_validator, "load_access_token", _fake_raw)
    # "not-a-wire-jwt" is not a valid facade-issued wire token → super() returns
    # None → the composite falls back to the raw Entra verifier.
    assert asyncio.run(p.load_access_token("not-a-wire-jwt")) is sentinel


def test_composite_returns_none_when_neither_path_accepts(monkeypatch):
    import asyncio

    _base_env(monkeypatch, "organizations")
    from dna_cli._mcp_auth import azure_provider_from_env

    p = azure_provider_from_env()

    async def _reject(token):
        return None

    monkeypatch.setattr(p._token_validator, "load_access_token", _reject)
    assert asyncio.run(p.load_access_token("garbage")) is None


def test_serve_auth_azure_selects_azure_provider(monkeypatch):
    """`dna mcp serve --auth azure` builds the server with an AzureProvider."""
    _base_env(monkeypatch, "organizations")
    from click.testing import CliRunner
    from fastmcp.server.auth.providers.azure import AzureProvider
    import dna_cli.mcp_cmd as mcp_cmd

    captured: dict = {}

    class _Stop(Exception):
        pass

    def _fake_build_server(*, scope, base_dir, auth, graph_config=None):
        captured["auth"] = auth
        raise _Stop()  # stop before build_http_app/uvicorn

    import dna_cli._mcp_server as mcp_server
    monkeypatch.setattr(mcp_server, "build_server", _fake_build_server)  # imported inside serve()
    result = CliRunner().invoke(mcp_cmd.serve, ["--auth", "azure", "--transport", "http"])
    # the branch ran and passed an AzureProvider to build_server
    assert isinstance(captured.get("auth"), AzureProvider), result.output
