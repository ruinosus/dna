"""write_document blocks per-tenant overlays of _lib Agents.

The `_lib` scope is the shared agent baseline (jarvis + the 12 transversais).
A per-tenant overlay silently FORKS the persona and shadows the base for that
tenant's reads — the root cause of the JARVIS 16384 outage (2026-05-29) and the
stale-persona bug (2026-06-14, DNA_TENANT=acme pollution). The guard turns that
silent corruption into a loud error. _lib agents are base-only (edit in git
+ `dna doc apply --scope _lib`).
"""
from __future__ import annotations

import pytest

from dna.extensions.helix import HelixExtension
from dna.kernel import Kernel
from dna.kernel.protocols import TenantNotAllowed
from tests.test_kernel_invalidate_modes import _FakeWritableSource


def _kernel() -> Kernel:
    k = Kernel()
    # s-write-path-despecialize — the fork guard is a pre_save veto hook
    # registered by the Helix extension (the Agent owner), no
    # longer a kernel special-case; a bare Kernel() has no guard.
    k.load(HelixExtension())
    k.source(_FakeWritableSource())
    return k


def _ua_raw() -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "jarvis"},
        "spec": {"instruction": "you are jarvis"},
    }


@pytest.mark.asyncio
async def test_platform_agent_tenant_fork_is_blocked():
    k = _kernel()
    with pytest.raises(TenantNotAllowed, match="_lib agent"):
        await k.write_document(
            "_lib", "Agent", "jarvis", _ua_raw(), tenant="acme",
        )


@pytest.mark.asyncio
async def test_platform_agent_base_write_is_allowed():
    k = _kernel()
    # No tenant → base write of a _lib agent is the canonical path.
    await k.write_document("_lib", "Agent", "jarvis", _ua_raw())


@pytest.mark.asyncio
async def test_non_platform_scope_agent_tenant_overlay_is_allowed():
    k = _kernel()
    # A normal scope's agent CAN have a tenant overlay — the guard is
    # _lib-specific, not a blanket ban on tenanted agents.
    await k.write_document(
        "acme-app", "Agent", "helper", _ua_raw(), tenant="acme",
    )
