"""Copilot → Terraform infra inputs (f-copilot-infra-binding).

The IaC closure: ``build_copilot_context`` → :func:`dna.emit.infra.emit_infra`
renders ONE ``role="infra"`` artifact — a ``<agent>.tfvars.json`` declaring the
resources the declared ``persistence`` / ``knowledge.store`` / ``hosting`` need,
deduped by ``ref``, plus the ``env_injection`` map (each store's TF output → the
env var the emitted copilot reads). The emitted JSON is byte-identical to the TS
twin (``infra.ts``); this file governs the Python side.

The live fixture is ``examples/emitting-to-a-runtime/.dna`` (concierge scope):
``memory-copilot`` declares Postgres persistence (checkpoint + memory on
``primary-pg``) + a pgvector knowledge store on the SAME ``primary-pg`` + Foundry
hosting — the exact Postgres-share + Foundry shape design §3 calls out.
"""
from __future__ import annotations

import json
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = str(_ROOT / "examples" / "emitting-to-a-runtime" / ".dna")
_SCOPE = "concierge"


@pytest.fixture()
def mi():
    from dna.kernel import Kernel

    return Kernel.quick(_SCOPE, base_dir=_BASE)


@pytest.fixture()
def infra_ctx(mi):
    from dna.emit import build_copilot_context

    return build_copilot_context(mi, "memory-copilot", model="azure/gpt-4o", provider="azure")


# ── has_infra gating ─────────────────────────────────────────────────────────


def test_has_infra_true_when_persistence_or_hosting(infra_ctx):
    from dna.emit.infra import has_infra

    assert has_infra(infra_ctx) is True


def test_has_infra_false_for_bare_copilot(mi):
    from dna.emit import build_copilot_context
    from dna.emit.infra import emit_infra, has_infra

    ctx = build_copilot_context(mi, "pure-action-copilot", model="azure/gpt-4o")
    assert has_infra(ctx) is False
    with pytest.raises(Exception):
        emit_infra(ctx)


# ── the emitted artifact shape ───────────────────────────────────────────────


def test_emit_infra_is_one_tfvars_artifact(infra_ctx):
    from dna.emit.infra import emit_infra

    res = emit_infra(infra_ctx)
    assert res.target == "terraform"
    assert [a.role for a in res.artifacts] == ["infra"]
    art = res.artifacts[0]
    assert art.path == "memory_agent.tfvars.json"
    # valid, parseable Terraform JSON var file
    json.loads(art.content)
    assert art.content.endswith("\n")


def _tfvars(ctx) -> dict:
    from dna.emit.infra import emit_infra

    return json.loads(emit_infra(ctx).artifacts[0].content)


# ── Postgres: dedup-by-ref + pgvector coalescing (design §3 row 1) ───────────


def test_postgres_dedups_by_ref_with_pgvector(infra_ctx):
    """checkpoint + memory (postgres) + knowledge.store (pgvector) ALL on
    ``primary-pg`` collapse to ONE Postgres resource with ``pgvector: true`` and
    every slot recorded in ``used_by``."""
    tf = _tfvars(infra_ctx)
    assert len(tf["postgres"]) == 1
    pg = tf["postgres"][0]
    assert pg["ref"] == "primary-pg"
    assert pg["pgvector"] is True
    assert pg["database"] == "dna"
    assert pg["used_by"] == [
        "knowledge.store",
        "persistence.checkpoint",
        "persistence.memory",
    ]
    assert pg["output_env"] == "DNA_PG_URI_PRIMARY_PG"
    assert pg["secret"] is True
    # no mongo/redis declared for this copilot
    assert tf["mongo"] == []


# ── env-injection: ref → TF output → copilot env (design §3 key rule) ────────


def test_env_injection_maps_ref_output_to_copilot_env(infra_ctx):
    tf = _tfvars(infra_ctx)
    inj = tf["env_injection"]
    assert inj["DNA_PG_URI_PRIMARY_PG"] == {
        "from": "postgres['primary-pg'].connection_string",
        "secret": True,
    }


# ── Foundry hosting (design §3 row 4) ────────────────────────────────────────


def test_hosting_foundry_module_inputs(infra_ctx):
    tf = _tfvars(infra_ctx)
    h = tf["hosting"]
    assert h["target"] == "foundry"
    assert h["mode"] == "self-hosted"
    assert h["image"]["container_port"] == 8088  # foundry default
    f = h["foundry"]
    assert f["account"] and f["project"] and f["acr"]
    assert f["model_deployment"] == "azure/gpt-4o"
    assert f["rbac"] == [
        {"principal": "project_identity", "role": "AcrPull"},
        {"principal": "agent_identity", "role": "Azure AI User"},
    ]
    # the agent version is NOT an ARM resource (design §3)
    assert "post-provision" in h["note"]


def test_foundry_ignores_stores(infra_ctx):
    """Foundry is a managed runtime — the declared ``hosting.stores`` is ignored,
    and recorded as an honest loss."""
    from dna.emit.infra import emit_infra

    res = emit_infra(infra_ctx)
    assert any("hosting.stores is ignored for target 'foundry'" in l for l in res.losses)
    # foundry's own state → no synthesized postgres beyond the declared primary-pg
    tf = json.loads(res.artifacts[0].content)
    assert [p["ref"] for p in tf["postgres"]] == ["primary-pg"]


# ── synthetic ctx cases: mongo / redis / langgraph stores ────────────────────


def test_mongo_atlas_vector_search():
    from dna.emit import EmitContext
    from dna.emit.infra import emit_infra

    ctx = EmitContext(
        name="atlas-copilot",
        description="",
        instructions="x",
        model="azure/gpt-4o",
        persistence={
            "checkpoint": {"backend": "mongo", "ref": "atlas-1"},
            "memory": None,
            "cache": None,
        },
        knowledge_store={"backend": "mongo-atlas", "ref": "atlas-1", "embed": None},
    )
    tf = json.loads(emit_infra(ctx).artifacts[0].content)
    assert len(tf["mongo"]) == 1
    m = tf["mongo"][0]
    assert m["ref"] == "atlas-1"
    assert m["atlas"] is True
    assert m["vector_search"] is True
    assert m["output_env"] == "DNA_MONGO_URI_ATLAS_1"


def test_langgraph_stores_synthesize_postgres_and_redis():
    from dna.emit import EmitContext
    from dna.emit.infra import emit_infra

    ctx = EmitContext(
        name="lg-copilot",
        description="",
        instructions="x",
        model="azure/gpt-4o",
        hosting={
            "mode": "hosted",
            "target": "langgraph-platform",
            "resources": {"cpu": "1", "memory": "2Gi"},
            "image": {"registry_hint": "ghcr", "remote_build": False,
                      "base_image": None, "port": None},
            "env": None,
            "stores": {"postgres": "required", "redis": "required"},
        },
    )
    tf = json.loads(emit_infra(ctx).artifacts[0].content)
    assert tf["hosting"]["target"] == "langgraph-platform"
    assert tf["hosting"]["image"]["container_port"] == 8123  # langgraph default
    assert tf["hosting"]["langgraph_platform"]["secret_env"] == ["LANGGRAPH_CLOUD_LICENSE_KEY"]
    # stores rolled into synthesized resources (no persistence ref declared)
    assert [p["ref"] for p in tf["postgres"]] == ["lg_copilot-pg"]
    assert [r["ref"] for r in tf["redis"]] == ["lg_copilot-redis"]
    # the control-plane secret rides in env_injection
    assert "LANGGRAPH_CLOUD_LICENSE_KEY" in tf["env_injection"]


def test_unknown_backend_is_an_honest_loss():
    from dna.emit import EmitContext
    from dna.emit.infra import emit_infra

    ctx = EmitContext(
        name="weird-copilot",
        description="",
        instructions="x",
        model="azure/gpt-4o",
        persistence={
            "checkpoint": {"backend": "cassandra", "ref": "c1"},
            "memory": None,
            "cache": None,
        },
    )
    res = emit_infra(ctx)
    tf = json.loads(res.artifacts[0].content)
    assert tf["postgres"] == [] and tf["mongo"] == [] and tf["redis"] == []
    assert any("cassandra" in l and "no Terraform infra mapping" in l for l in res.losses)


# ── determinism ──────────────────────────────────────────────────────────────


def test_emit_is_deterministic(infra_ctx):
    from dna.emit.infra import emit_infra

    a = emit_infra(infra_ctx).artifacts[0].content
    b = emit_infra(infra_ctx).artifacts[0].content
    assert a == b
