"""i-051, sdk-py half — ``RegistryAccessor.tier()`` under ``DNA_QUOTA_REQUIRE_TIERS``.

``tier()`` is fail-SOFT by design: a registry glitch degrades to ``None``
(logged loud) so an OSS kernel never crashes over a pricing Kind it does not
use. But downstream, ``None`` becomes empty caps becomes NO quota enforcement
— so in the HOSTED shape that same softness silently converts a database
hiccup into unlimited unbilled calls. Under the opt-in flag the ``except``
must PROPAGATE: the caller (the MCP guard) then fails the request instead of
serving it unmetered.

Fake-slice pattern from ``test_kernel_satellites_f5.py`` — the accessor is
exercised against a narrow host whose ``query`` raises, no kernel involved.
"""
from __future__ import annotations

import types

import pytest

from dna.kernel.registry_accessor import _REQUIRE_TIERS_ENV, RegistryAccessor


def _boom_slice() -> types.SimpleNamespace:
    async def _boom(*_a, **_k):
        raise RuntimeError("registry down")
        yield  # pragma: no cover — make it a generator

    return types.SimpleNamespace(query=_boom)


@pytest.mark.asyncio
async def test_tier_stays_fail_soft_by_default(monkeypatch):
    """BASELINE (anti-vacuity). Flag unset → the glitch degrades to ``None``,
    exactly today's behavior — the OSS kernel never crashes over Tier."""
    monkeypatch.delenv(_REQUIRE_TIERS_ENV, raising=False)
    ra = RegistryAccessor(_boom_slice())  # type: ignore[arg-type]
    assert await ra.tier("free") is None


@pytest.mark.asyncio
async def test_tier_propagates_the_failure_under_the_flag(monkeypatch):
    """THE property. Flag ON → the registry failure PROPAGATES instead of
    degrading to ``None``: a hosted deployment must fail the call, not the
    billing. Remove the re-raise and this test dies."""
    monkeypatch.setenv(_REQUIRE_TIERS_ENV, "1")
    ra = RegistryAccessor(_boom_slice())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="registry down"):
        await ra.tier("free")


@pytest.mark.asyncio
async def test_the_flag_only_hardens_tier_not_the_other_reads(monkeypatch):
    """Scope control: the flag is a QUOTA contract, not a general fail-hard
    switch — ``model_profile`` (and the rest of the accessor) keeps its
    fail-soft behavior even with the flag ON."""
    monkeypatch.setenv(_REQUIRE_TIERS_ENV, "1")
    ra = RegistryAccessor(_boom_slice())  # type: ignore[arg-type]
    assert await ra.model_profile("gpt-x") is None
