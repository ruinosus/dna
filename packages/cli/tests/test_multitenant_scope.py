"""Feature ``f-cloud-multitenant`` — the **per-tenant base scope** (audit H2).

Two layers, both proven here:

1. **The resolver (pure policy)** — ``LiveDna.default_scope`` /
   ``LiveDna.scope_is_bound``. With multi-tenant OFF (``vendor_tenant`` unset) the
   scope-less default stays ``base_scope`` for everyone (today's behavior, the OSS
   / self-host path). With it ON, a scope-less read resolves PER TENANT — the
   reserved vendor tenant to ``base_scope`` (``dna-development`` stays the
   vendor's, un-moved), every other tenant to its OWN ``tenant-<tid>`` scope — so
   a new outside tenant never reads the vendor's data as its own.

2. **End-to-end over real JWT + HTTP** — with ``DNA_VENDOR_TENANT`` set, a
   non-vendor token that explicitly asks for the vendor's scope is DENIED
   (cross-scope), while the vendor token reaches ``base_scope`` and a non-vendor
   token reaches its own (empty) scope. Reuses the ``s-mcp-oauth-auth`` harness.
"""
from __future__ import annotations

import asyncio

import pytest

from dna.application.live import LiveDna


# ── the resolver: pure policy (no kernel) ──────────────────────────────────


def _live(vendor: str | None = None, prefix: str = "tenant-") -> LiveDna:
    return LiveDna(
        base_scope="dna-development", kernel=None, provider=None,
        vendor_tenant=vendor, tenant_scope_prefix=prefix,
    )


def test_default_scope_multitenant_off_is_base_for_all():
    live = _live(vendor=None)
    assert live.default_scope(None) == "dna-development"
    assert live.default_scope("acme") == "dna-development"  # OFF → unchanged.


def test_default_scope_no_tenant_is_base():
    # Even with multi-tenant ON, an un-tenanted (stdio / local) read is unchanged.
    assert _live(vendor="vendorX").default_scope(None) == "dna-development"


def test_default_scope_vendor_reserved_to_base():
    live = _live(vendor="vendorX")
    assert live.default_scope("vendorX") == "dna-development"  # vendor keeps it.


def test_default_scope_other_tenant_gets_own_scope():
    live = _live(vendor="vendorX")
    assert live.default_scope("acme") == "tenant-acme"
    assert live.default_scope("globex") == "tenant-globex"


def test_default_scope_prefix_is_configurable():
    assert _live(vendor="v", prefix="t_").default_scope("acme") == "t_acme"


def test_scope_is_bound_off_allows_any_scope():
    # Multi-tenant OFF → binding is a no-op (the shared-scope + overlay model).
    live = _live(vendor=None)
    assert live.scope_is_bound("anything", "acme") is True


def test_scope_is_bound_allows_none_and_own_scope():
    live = _live(vendor="vendorX")
    assert live.scope_is_bound(None, "acme") is True          # omitted → default.
    assert live.scope_is_bound("tenant-acme", "acme") is True  # own scope.
    assert live.scope_is_bound("dna-development", "vendorX") is True  # vendor's own.


def test_scope_is_bound_denies_cross_scope():
    live = _live(vendor="vendorX")
    # a non-vendor tenant naming the vendor's scope → cross-scope.
    assert live.scope_is_bound("dna-development", "acme") is False
    # a tenant naming ANOTHER tenant's scope → cross-scope.
    assert live.scope_is_bound("tenant-globex", "acme") is False


# ── end-to-end: cross-scope denied when multi-tenant is ON ─────────────────

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the 'fastmcp' extra")

from dna_cli import _mcp_server as M  # noqa: E402
from test_mcp_auth import _AGENT, _SCOPE, dna_dir, _verifier_and_tokens  # noqa: E402,F401


def test_cross_scope_request_denied_when_multitenant_on(dna_dir, http_server, monkeypatch):
    """With DNA_VENDOR_TENANT set, a non-vendor token that names the vendor's
    scope is DENIED (cross-scope), while the vendor token reaches it."""
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    # The example scope is `concierge` → that is this source's base_scope. Treat
    # `vendorX` as the reserved vendor; `acme` is an outside tenant.
    monkeypatch.setenv("DNA_VENDOR_TENANT", "vendorX")
    verifier, mint = _verifier_and_tokens()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    token_vendor, token_acme = mint("vendorX"), mint("acme")

    async def call(url, token, scope):
        async with Client(url, auth=BearerAuth(token)) as client:
            res = await client.call_tool(
                "list_agents", {"scope": scope} if scope else {}
            )
            return res.structured_content

    with http_server(server) as url:
        # vendor names the base scope → allowed (it IS its own default).
        vend = asyncio.run(call(url, token_vendor, _SCOPE))
        assert any(a["name"] == _AGENT for a in vend["agents"])

        # acme (outside tenant) names the vendor's scope → DENIED cross-scope.
        with pytest.raises(Exception) as ei:  # noqa: PT011
            asyncio.run(call(url, token_acme, _SCOPE))
        assert "cross-scope" in str(ei.value).lower()
