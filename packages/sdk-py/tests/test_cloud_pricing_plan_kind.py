"""s-dna-cloud-plans — Tier Kind (DNA Cloud pricing plans) + kernel.tier().

Covers the declarative-caps contract shipped as the `cloud` extension:

1. The ``cloud`` extension registers Tier from its descriptor
   (``kinds/pricing-plan.kind.yaml`` — record plane, GLOBAL, generated-convention
   alias ``cloud-pricing-plan``). NOT named ``Plan`` — that alias belongs to the
   SDLC implementation-plan Kind.
2. ``kernel.tier`` resolves a Tier from ``_lib`` by ``tier_id`` then
   ``aliases[]``, returning the RAW DICT row whose ``spec`` carries the
   caps — proving the caps come from the DOC, never a literal in code.
3. Mutating a Tier doc's ``calls_per_day`` and re-reading returns the new
   value (no redeploy — a limit change is a file edit).

TS twin: tests/cloud-extension.test.ts.
"""
from __future__ import annotations

import pytest

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.cloud import CloudExtension
from dna.kernel import Kernel
from dna.kernel.protocols import TenantScope


def _tier(tier_id: str, *, display_name: str, price: float,
          calls_per_day: int | None, memory_mode: str,
          aliases: list[str] | None = None) -> dict:
    """Build a Tier doc. Caps live HERE (the doc), never in the code."""
    return {
        "apiVersion": "github.com/ruinosus/dna/cloud/v1",
        "kind": "PricingPlan",
        "metadata": {"name": tier_id},
        "spec": {
            "tier_id": tier_id,
            "display_name": display_name,
            "price_usd_month": price,
            "calls_per_day": calls_per_day,
            "rate_per_sec": 1,
            "max_tenants": 1,
            "feature_families": ["definitions", "sdlc", "memory"],
            "memory_mode": memory_mode,
            "aliases": aliases or [],
        },
    }


async def _kernel(tmp_path) -> Kernel:
    k = Kernel()
    k.load(CloudExtension())
    src = FilesystemWritableSource(str(tmp_path / ".dna"))
    k.source(src)
    src.attach_kernel(k)
    # Tiers live in the _lib scope (tiers/<tier_id>.yaml) — kernel.tier
    # queries _lib directly regardless of caller scope.
    await k.write_document(
        "_lib", "PricingPlan", "free",
        _tier("free", display_name="Free", price=0, calls_per_day=100,
              memory_mode="read", aliases=["starter"]),
    )
    await k.write_document(
        "_lib", "PricingPlan", "pro",
        _tier("pro", display_name="Pro", price=29, calls_per_day=10000,
              memory_mode="write"),
    )
    return k


# ---------------------------------------------------------------------------
# 1. Kind registration (descriptor)
# ---------------------------------------------------------------------------

def test_tier_kind_registered_from_descriptor():
    k = Kernel()
    k.load(CloudExtension())
    kp = k.kind_port_for("PricingPlan")
    assert kp is not None
    # Explicit alias `cloud-pricing-plan` — NOT `Plan` (that alias belongs to SDLC).
    assert kp.alias == "cloud-pricing-plan"
    assert kp.plane == "record"
    # GLOBAL — a shared base registry, no per-tenant override.
    assert kp.scope == TenantScope.GLOBAL
    assert kp.storage.container == "tiers"
    assert getattr(kp, "__declarative__", False) is True


def test_cloud_registers_tier_not_plan():
    """The cloud extension must register `Tier`, never `Plan` — `Plan` is the
    SDLC implementation-plan Kind and must remain its own thing. Loading only
    the cloud extension, Tier exists and Plan is absent."""
    k = Kernel()
    k.load(CloudExtension())
    assert k.kind_port_for("PricingPlan") is not None
    assert k.kind_port_for("Plan") is None


# ---------------------------------------------------------------------------
# 2. Resolution — caps come from the DOC
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tier_resolves_caps_from_doc(tmp_path):
    k = await _kernel(tmp_path)

    free = await k.tier("free")
    assert free is not None
    fspec = free.get("spec") or {}
    assert fspec["calls_per_day"] == 100
    assert fspec["memory_mode"] == "read"
    assert fspec["price_usd_month"] == 0

    pro = await k.tier("pro")
    assert pro is not None
    pspec = pro.get("spec") or {}
    assert pspec["calls_per_day"] == 10000
    assert pspec["memory_mode"] == "write"
    assert pspec["price_usd_month"] == 29


@pytest.mark.asyncio
async def test_tier_resolves_by_alias(tmp_path):
    k = await _kernel(tmp_path)
    by_alias = await k.tier("starter")  # alias of `free`
    assert by_alias is not None
    assert (by_alias.get("spec") or {})["tier_id"] == "free"


@pytest.mark.asyncio
async def test_tier_unknown_returns_none(tmp_path):
    k = await _kernel(tmp_path)
    assert await k.tier("nonexistent") is None


# ---------------------------------------------------------------------------
# 3. No-redeploy — edit the cap, re-read, new value (data, not code)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tier_cap_is_data_not_code(tmp_path):
    k = await _kernel(tmp_path)
    assert (await k.tier("free"))["spec"]["calls_per_day"] == 100
    # Edit the Free plan's daily quota — a file edit, no redeploy.
    await k.write_document(
        "_lib", "PricingPlan", "free",
        _tier("free", display_name="Free", price=0, calls_per_day=250,
              memory_mode="read", aliases=["starter"]),
    )
    assert (await k.tier("free"))["spec"]["calls_per_day"] == 250
