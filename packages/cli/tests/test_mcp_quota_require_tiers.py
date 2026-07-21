"""i-051 — ``DNA_QUOTA_REQUIRE_TIERS``: opt-in fail-CLOSED for an empty Tier registry.

The default (flag OFF) is fail-OPEN **by design**: a source with no ``Tier``
docs is an OSS/self-host that never opted into DNA Cloud pricing, and the
open-core hard rule says it must never be capped. But the SAME silence is a
billing hole in the HOSTED shape: if the Tier seed fails at boot (or the
registry read starts throwing), every cap silently evaporates and a metered
deployment serves unlimited, unbilled calls — fail-open where money depends on
fail-closed. The flag lets the HOST declare which shape it is; the SDK never
guesses.

Properties pinned here (each states what must remain true of the SYSTEM,
mirroring ``test_workspace_takeover_guard.py``):

1. **flag OFF + empty registry → fail-open, untouched** — the baseline that
   keeps the refusal tests non-vacuous AND pins the open-core rule;
2. **flag ON + empty registry + authenticated call → explicit refusal** — a
   ToolError naming the tier registry, never a silent unlimited pass;
3. **flag ON + seeded registry → indistinguishable from flag OFF** — the flag
   bites ONLY when the registry is empty/unreadable, normal metering is
   byte-for-byte the same denial;
4. **flag ON + NO token → still free** — the flag must never leak enforcement
   into the stdio/local/self-host path (the OSS invariant of ``_guard``).

The sdk-py half (the ``registry_accessor.tier()`` fail-soft ``except`` must
PROPAGATE under the flag instead of degrading to ``None``) is pinned in
``packages/sdk-py/tests/test_registry_accessor_require_tiers.py``.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

from dna_cli import _mcp_quota as Q

# Reuse the quota suite's helpers — same Tier-doc shape, same token mint.
from test_mcp_quota import _SCOPE, _seed_tiers, _verifier_and_mint


# ── the flag parser itself (pure) ───────────────────────────────────────────


def test_require_tiers_reads_the_documented_truthy_values():
    for on in ("1", "true", "TRUE", "yes", "on"):
        assert Q.require_tiers({Q.REQUIRE_TIERS_ENV: on}) is True
    for off in ("", "0", "false", "off", "no"):
        assert Q.require_tiers({Q.REQUIRE_TIERS_ENV: off}) is False
    assert Q.require_tiers({}) is False  # absent → OFF: fail-open is the default


# ── integration over a real token context ──────────────────────────────────

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv(Q.REQUIRE_TIERS_ENV, raising=False)
    Q.DEFAULT_STORE.reset()
    return dst


def _authed_server(dna_dir):
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    verifier, mint = _verifier_and_mint()
    server = M.build_server(base_dir=str(dna_dir), auth=verifier)
    return server, mint(tenant="acme", plan="free")


def test_flag_off_an_empty_registry_stays_fail_open(dna_dir, http_server):
    """BASELINE (anti-vacuity + the open-core rule). No Tier docs, flag unset:
    an authenticated call passes unmetered — today's behavior, untouched.
    Without this test, the refusal below could pass on a server that refuses
    EVERYTHING."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    server, token = _authed_server(dna_dir)  # NOTHING seeded — registry is empty

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            for _ in range(3):
                res = await client.call_tool("list_stories", {"scope": _SCOPE})
                assert res.structured_content["scope"] == _SCOPE

    with http_server(server) as url:
        asyncio.run(go(url))


def _assert_refused(server, token, http_server):
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            with pytest.raises(Exception) as ei:  # noqa: PT011 — ToolError/McpError
                await client.call_tool("list_stories", {"scope": _SCOPE})
            msg = str(ei.value).lower()
            assert "tier registry" in msg and "refus" in msg

    with http_server(server) as url:
        asyncio.run(go(url))


def test_flag_on_an_empty_registry_refuses_metered_calls(dna_dir, http_server,
                                                         monkeypatch):
    """THE property, EMPTY half. Hosted shape (flag ON), ``_lib`` exists but
    holds no Tier docs (the seed never ran): an authenticated call is REFUSED
    with an error naming the tier registry — never silently served unmetered.
    If this test needs its assertion (not merely its setup) weakened, the
    billing hole is open again."""
    pytest.importorskip("fastmcp")
    (dna_dir / "_lib").mkdir()  # the registry scope EXISTS — it is just empty
    monkeypatch.setenv(Q.REQUIRE_TIERS_ENV, "1")
    server, token = _authed_server(dna_dir)
    _assert_refused(server, token, http_server)


def test_flag_on_an_unreadable_registry_refuses_metered_calls(dna_dir,
                                                              http_server,
                                                              monkeypatch):
    """THE property, UNREADABLE half. No ``_lib`` scope at all — the registry
    read RAISES (and under the flag the SDK propagates instead of degrading to
    ``None``, see the sdk-py twin suite). The caller must see the SAME
    explicit refusal, not a masked internal error and never an unmetered
    pass."""
    pytest.importorskip("fastmcp")
    monkeypatch.setenv(Q.REQUIRE_TIERS_ENV, "1")
    server, token = _authed_server(dna_dir)  # dna_dir has NO _lib directory
    _assert_refused(server, token, http_server)


def test_flag_on_with_seeded_tiers_meters_exactly_like_flag_off(dna_dir,
                                                                http_server,
                                                                monkeypatch):
    """The flag bites ONLY on an empty/unreadable registry. With Tier docs
    seeded, flag ON behaves exactly like today: under-cap calls pass, the
    cap+1 call is denied by the QUOTA (not by the registry refusal)."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    asyncio.run(_seed_tiers(dna_dir, free_calls_per_day=2,
                            free_families=["definitions", "sdlc", "memory"]))
    monkeypatch.setenv(Q.REQUIRE_TIERS_ENV, "1")
    server, token = _authed_server(dna_dir)

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            for _ in range(2):
                res = await client.call_tool("list_stories", {"scope": _SCOPE})
                assert res.structured_content["scope"] == _SCOPE
            with pytest.raises(Exception) as ei:  # noqa: PT011
                await client.call_tool("list_stories", {"scope": _SCOPE})
            msg = str(ei.value).lower()
            assert "quota" in msg
            assert "tier registry" not in msg  # denied by the CAP, not the flag

    with http_server(server) as url:
        asyncio.run(go(url))


def test_flag_on_never_touches_the_tokenless_path(dna_dir, monkeypatch):
    """The OSS invariant survives the flag: with NO token (auth=None,
    stdio/local) the guard returns before the metered branch, so even flag ON
    + empty registry serves freely. The open-core rule is not negotiable by
    environment variable."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from dna_cli import _mcp_server as M

    monkeypatch.setenv(Q.REQUIRE_TIERS_ENV, "1")
    server = M.build_server(base_dir=str(dna_dir))  # auth=None, NOTHING seeded

    async def go():
        async with Client(server) as client:
            for _ in range(3):
                res = await client.call_tool("list_stories", {"scope": _SCOPE})
                assert res.structured_content["scope"] == _SCOPE

    asyncio.run(go())
