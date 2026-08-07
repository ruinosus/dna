"""s-strain-customization-ui / Task 3 — the ``/v1/definitions/{kind}/{name}``
REST surface has ZERO business logic of its own (it delegates verbatim to the
same ``*_definition_impl`` core Task 1 added), but the FACE mapping — the
three exceptions the core raises into the three HTTP statuses the portal's
editor depends on — has no committed coverage before this test:

    read_definition_impl  ValueError                 → 404 (unknown kind/name)
    apply_definition_impl LayerPolicyViolationError   → 403 (LOCKED Kind)
    apply_definition_impl ValueError (no tenant)      → 400
    revert_definition_impl ValueError (no tenant)     → 400

A refactor of ``_rest_api.py`` (e.g. collapsing the except clauses, or
swapping the exception order) could silently regress any of these mappings
with nothing red in CI. This module stands up the real FastAPI app via
``TestClient`` (mirroring ``test_rest_write_quota.py``'s app-construction +
seeding pattern) and asserts the routes' actual HTTP behavior end to end,
including the PUT→GET→DELETE→GET override round-trip.

Seed mirrors ``packages/sdk-py/tests/test_definition_overlay_pg.py``: the
``concierge`` example scope already ships an ``Agent`` (``concierge``) and an
``MCPFederation`` (``dna-mcp``); we add ONE ``LayerPolicy`` doc (Kind
ALIASES, i-049: ``AgentKind.alias = "helix-agent"``,
``MCPFederationKind.alias = "federation-mcp"``) marking the agent layer OPEN
and the federation layer LOCKED, keyed the same way the pg test keys it
(``layer_id: "tenant"``, one LayerPolicy doc per (layer_id, scope)).

The ``/v1/definitions`` routes are auth-guarded (``dependencies=guarded`` —
bearer verification only) but NOT plan-gated (no ``_plan_gate`` call in any
of the three handlers — unlike the memory write routes), so ``--auth none``
exercises the exact same code path as ``--auth token``/``config`` would;
no Tier/PricingPlan/quota seeding is needed here.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_WID = "ws-rest0000000000000000001"

# The scope already ships these (examples/emitting-to-a-runtime/.dna/concierge):
_AGENT = "concierge"          # Kind Agent, alias "helix-agent"
_FEDERATION = "dna-mcp"       # Kind MCPFederation, alias "federation-mcp"

LAYER_POLICY_RAW = {
    "apiVersion": "github.com/ruinosus/dna/policy/v1",
    "kind": "LayerPolicy",
    "metadata": {"name": "tenant-default"},
    "spec": {
        "layer_id": "tenant",
        "policies": {"helix-agent": "open", "federation-mcp": "locked"},
    },
}


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope, wired via DNA_BASE_DIR (same
    fixture shape as test_rest_write_quota.py's ``dna_dir``)."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _seed_layer_policy(dna_dir) -> None:
    """Write the LayerPolicy doc into the ``concierge`` scope itself (a
    bootstrap Kind — one per (layer_id, scope), never per-tenant) — mirrors
    ``test_definition_overlay_pg.py``'s ``live_pg`` seed, on the filesystem
    source via ``boot_live`` on a fresh loop."""
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        await live.kernel.write_instance(
            _SCOPE, "LayerPolicy", "tenant-default", LAYER_POLICY_RAW)

    asyncio.run(go())


def _client(dna_dir) -> TestClient:
    """auth=none — the definitions routes are auth-guarded but not
    plan-gated, so the default (unauthenticated) client exercises the same
    handler code the token/config lanes would."""
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE))


# ── GET ───────────────────────────────────────────────────────────────────


def test_get_definition_returns_effective_spec_for_seeded_agent(dna_dir):
    _seed_layer_policy(dna_dir)
    with _client(dna_dir) as c:
        r = c.get(f"/v1/definitions/Agent/{_AGENT}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kind"] == "Agent"
        assert body["name"] == _AGENT
        assert body["overridden"] is False
        assert "Answer using the runbook" in body["effective"]["instruction"]


def test_get_definition_404_for_unknown_name(dna_dir):
    _seed_layer_policy(dna_dir)
    with _client(dna_dir) as c:
        r = c.get("/v1/definitions/Agent/nonexistent-agent-xyz")
        assert r.status_code == 404, r.text


# ── PUT ───────────────────────────────────────────────────────────────────


def test_put_valid_overlayable_override_returns_200(dna_dir):
    _seed_layer_policy(dna_dir)
    with _client(dna_dir) as c:
        r = c.put(
            f"/v1/definitions/Agent/{_AGENT}",
            params={"tenant": _WID},
            json={"spec": {"instruction": "Focus on compliance runbooks only."}},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kind"] == "Agent"
        assert body["name"] == _AGENT
        assert body["overridden"] is True


def test_put_locked_kind_is_403(dna_dir):
    """The central constraint this task exists to protect: a write to a
    LOCKED Kind (MCPFederation, alias "federation-mcp") is vetoed by the
    kernel's LayerPolicy check and surfaced as 403, never silently dropped
    and never a 500."""
    _seed_layer_policy(dna_dir)
    with _client(dna_dir) as c:
        r = c.put(
            f"/v1/definitions/MCPFederation/{_FEDERATION}",
            params={"tenant": _WID},
            json={"spec": {"transport": "streamable_http", "url": "https://evil.example",
                            "allowed_tools": []}},
        )
        assert r.status_code == 403, r.text


def test_put_without_tenant_is_400(dna_dir):
    _seed_layer_policy(dna_dir)
    with _client(dna_dir) as c:
        r = c.put(
            f"/v1/definitions/Agent/{_AGENT}",
            json={"spec": {"instruction": "no tenant given"}},
        )
        assert r.status_code == 400, r.text


# ── DELETE + round-trip ──────────────────────────────────────────────────


def test_delete_existing_override_returns_200(dna_dir):
    _seed_layer_policy(dna_dir)
    with _client(dna_dir) as c:
        put = c.put(
            f"/v1/definitions/Agent/{_AGENT}",
            params={"tenant": _WID},
            json={"spec": {"instruction": "Temporary override for delete test."}},
        )
        assert put.status_code == 200, put.text
        r = c.delete(f"/v1/definitions/Agent/{_AGENT}", params={"tenant": _WID})
        assert r.status_code == 200, r.text
        assert r.json()["overridden"] is False


def test_put_then_get_then_delete_round_trips_overridden_flag(dna_dir):
    """PUT flips ``overridden`` true for that tenant's GET; DELETE flips it
    back — the exact state the editor's Save / Reset-to-default renders."""
    _seed_layer_policy(dna_dir)
    with _client(dna_dir) as c:
        before = c.get(f"/v1/definitions/Agent/{_AGENT}", params={"tenant": _WID})
        assert before.status_code == 200, before.text
        assert before.json()["overridden"] is False

        put = c.put(
            f"/v1/definitions/Agent/{_AGENT}",
            params={"tenant": _WID},
            json={"spec": {"instruction": "Overridden instruction for round-trip."}},
        )
        assert put.status_code == 200, put.text

        after_put = c.get(f"/v1/definitions/Agent/{_AGENT}", params={"tenant": _WID})
        assert after_put.status_code == 200, after_put.text
        after_body = after_put.json()
        assert after_body["overridden"] is True
        assert "round-trip" in after_body["effective"]["instruction"]

        # A DIFFERENT tenant (no override) still reads the unmodified base.
        other = c.get(f"/v1/definitions/Agent/{_AGENT}",
                      params={"tenant": "ws-other0000000000000000002"})
        assert other.status_code == 200, other.text
        assert other.json()["overridden"] is False
        assert "Answer using the runbook" in other.json()["effective"]["instruction"]

        delete = c.delete(f"/v1/definitions/Agent/{_AGENT}", params={"tenant": _WID})
        assert delete.status_code == 200, delete.text
        assert delete.json()["overridden"] is False

        after_delete = c.get(f"/v1/definitions/Agent/{_AGENT}", params={"tenant": _WID})
        assert after_delete.status_code == 200, after_delete.text
        after_delete_body = after_delete.json()
        assert after_delete_body["overridden"] is False
        assert "Answer using the runbook" in after_delete_body["effective"]["instruction"]
