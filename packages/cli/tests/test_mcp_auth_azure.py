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
