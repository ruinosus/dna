"""Tests for the DNA **REST read-API face** (``dna_cli._rest_api`` + ``dna api``).

The thesis: a thin request/response HTTP API — the correct boundary for a WEB app
(the DNA Cloud portal) — over the SAME live kernel + the SAME ``*_impl`` cores the
MCP server uses (zero logic duplication). These tests drive the real FastAPI app
in-process via ``TestClient`` against the committed ``examples/emitting-to-a-runtime``
concierge scope (copied to a tmp dir so tenant overlays + memory can be written).

Proven here:
* ``/v1/agents`` returns the catalog agents; ``/v1/agents/{name}/prompt`` composes
  the live prompt (Soul persona included) and 404s an unknown agent.
* ``/v1/tools`` surfaces the Tool Kind.
* ``/v1/memories`` is TENANT-ISOLATED (tenant A never sees B; base is shared).
* ``/v1/memories/search`` recalls the tenant's memory.
* ``DELETE /v1/memories/{name}`` removes from the tenant's OWN overlay only — a
  base memory (and another tenant's) is untouched (404), the isolation guard.
* ``--auth token`` rejects a missing/wrong bearer (401) and accepts the right one;
  ``/health`` is always OK.
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
_AGENT = "concierge"
_TOKEN = "portal-shared-token-mvp"  # a fake shared token, NOT a real secret.


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope, wired as the source via DNA_BASE_DIR."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _seed_memory(dna_dir, summary: str, *, tenant: str | None = None, tags=None) -> dict:
    """Seed one memory via the SAME impl the MCP `remember` tool uses. Runs on its
    own loop; the filesystem source persists to disk, so the app (booted on the
    TestClient loop) reads it back."""
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await M.remember_impl(
            live, summary, scope=_SCOPE, tenant=tenant, tags=tags or [])

    return asyncio.run(go())


def _client(dna_dir, **kwargs) -> TestClient:
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE, **kwargs))


# ── health ──────────────────────────────────────────────────────────────────


def test_health_ok(dna_dir):
    with _client(dna_dir) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json() == {"ok": True}


# ── definitions: agents / prompt / tools (reuse the MCP impls) ───────────────


def test_agents_returns_catalog(dna_dir):
    with _client(dna_dir) as c:
        r = c.get("/v1/agents", params={"scope": _SCOPE})
        assert r.status_code == 200
        body = r.json()
        assert body["scope"] == _SCOPE
        assert _AGENT in [a["name"] for a in body["agents"]]


def test_agent_prompt_composes_live(dna_dir):
    with _client(dna_dir) as c:
        r = c.get(f"/v1/agents/{_AGENT}/prompt", params={"scope": _SCOPE})
        assert r.status_code == 200
        body = r.json()
        assert body["agent"] == _AGENT
        # The Soul persona is COMPOSED into the prompt (the axis a flat emit drops).
        assert "Helpdesk Concierge" in body["prompt"]


def test_agent_prompt_unknown_404(dna_dir):
    with _client(dna_dir) as c:
        r = c.get("/v1/agents/nope/prompt", params={"scope": _SCOPE})
        assert r.status_code == 404


def test_tools_returns_surface(dna_dir):
    with _client(dna_dir) as c:
        r = c.get("/v1/tools", params={"scope": _SCOPE})
        assert r.status_code == 200
        assert "kb-search" in [t["name"] for t in r.json()["tools"]]


# ── memory: list is tenant-isolated (A never sees B; base shared) ────────────


def test_memories_tenant_isolated(dna_dir):
    _seed_memory(dna_dir, "ACME secret roadmap pivot alpha", tenant="acme")
    _seed_memory(dna_dir, "GLOBEX secret roadmap pivot beta", tenant="globex")
    _seed_memory(dna_dir, "BASE shared knowledge gamma", tenant=None)

    with _client(dna_dir) as c:
        acme = c.get("/v1/memories", params={"scope": _SCOPE, "tenant": "acme"}).json()
        globex = c.get("/v1/memories", params={"scope": _SCOPE, "tenant": "globex"}).json()

    acme_names = {m["name"] for m in acme["memories"]}
    globex_names = {m["name"] for m in globex["memories"]}
    # each tenant sees its OWN memory ...
    assert any("acme" in n for n in acme_names), acme_names
    assert any("globex" in n for n in globex_names), globex_names
    # ... and NEITHER sees the other's (zero cross-tenant leak) ...
    assert not any("globex" in n for n in acme_names)
    assert not any("acme" in n for n in globex_names)
    # ... but the shared BASE memory is visible to BOTH.
    assert any("gamma" in n for n in acme_names)
    assert any("gamma" in n for n in globex_names)


def test_memory_card_surface(dna_dir):
    _seed_memory(dna_dir, "ACME onboarding runbook note delta",
                 tenant="acme", tags=["onboarding", "runbook"])
    with _client(dna_dir) as c:
        mems = c.get("/v1/memories", params={"scope": _SCOPE, "tenant": "acme"}).json()["memories"]
    card = next(m for m in mems if "delta" in m["name"])
    assert card["summary"] == "ACME onboarding runbook note delta"
    assert set(card["tags"]) == {"onboarding", "runbook"}
    assert card["created_at"]


# ── memory: search recalls the tenant's memory ──────────────────────────────


def test_memories_search_recalls(dna_dir):
    _seed_memory(
        dna_dir,
        "the DNA pivot chose portability over prompt-management because runtimes "
        "proliferate in 2026",
        tenant="acme", tags=["pivot", "portability"])
    with _client(dna_dir) as c:
        r = c.get("/v1/memories/search",
                  params={"q": "why the pivot", "scope": _SCOPE, "tenant": "acme", "k": 5})
        assert r.status_code == 200
        body = r.json()
        assert body["query"] == "why the pivot"
        assert body["hits"], "search returned no memory"
        assert any("pivot" in (h.get("name") or "") for h in body["hits"])


# ── memory: DELETE removes from the tenant's OWN overlay only ────────────────


def test_delete_memory_overlay_only(dna_dir):
    """The one write on the read-API, guarded: a tenant deletes its OWN memory,
    but can NEVER delete base or another tenant's (a 404 — the doc is not in its
    overlay). The load-bearing #83 isolation."""
    acme_own = _seed_memory(dna_dir, "ACME deletable memory one", tenant="acme")
    acme_two = _seed_memory(dna_dir, "ACME survivor memory three", tenant="acme")
    base_mem = _seed_memory(dna_dir, "BASE undeletable memory two", tenant=None)

    with _client(dna_dir) as c:
        # 1. tenant deletes its OWN memory → 200, and it's gone from its list.
        r = c.delete(f"/v1/memories/{acme_own['name']}",
                     params={"scope": _SCOPE, "tenant": "acme"})
        assert r.status_code == 200, r.text
        assert r.json()["deleted"] == acme_own["name"]
        after = {m["name"] for m in c.get(
            "/v1/memories", params={"scope": _SCOPE, "tenant": "acme"}).json()["memories"]}
        assert acme_own["name"] not in after

        # 2. tenant CANNOT delete a BASE memory → 404, base survives (visible still).
        r = c.delete(f"/v1/memories/{base_mem['name']}",
                     params={"scope": _SCOPE, "tenant": "acme"})
        assert r.status_code == 404
        still = {m["name"] for m in c.get(
            "/v1/memories", params={"scope": _SCOPE, "tenant": "acme"}).json()["memories"]}
        assert base_mem["name"] in still

        # 3. a DIFFERENT tenant CANNOT delete acme's surviving memory → 404.
        r = c.delete(f"/v1/memories/{acme_two['name']}",
                     params={"scope": _SCOPE, "tenant": "globex"})
        assert r.status_code == 404
        acme_after = {m["name"] for m in c.get(
            "/v1/memories", params={"scope": _SCOPE, "tenant": "acme"}).json()["memories"]}
        assert acme_two["name"] in acme_after  # untouched.


# ── intel: sources + insights + the feedback state transition ────────────────


def _seed_intel_and_run(dna_dir, source="copiloto-medico", tenant="acme"):
    """Seed an IntelSource + run one engine pass (SeedAnalyzer) so the REST face
    has real data to list. Runs on its own loop; the filesystem source persists,
    so the TestClient-booted app reads it back."""
    from dna_cli import _mcp_server as M
    from dna.extensions.intel import engine

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        await live.kernel.write_document(
            _SCOPE, "IntelSource", source,
            {
                "apiVersion": "github.com/ruinosus/dna/intel/v1",
                "kind": "IntelSource",
                "metadata": {"name": source},
                "spec": {
                    "name": source, "type": "repo", "cadence": "weekly",
                    "threshold": 0.6,
                    "pirs": ["regulação", "concorrentes", "tech PT-BR"],
                },
            },
            tenant=tenant,
        )
        return await engine.run_pass(live.kernel, source, scope=_SCOPE, tenant=tenant)

    return asyncio.run(go())


def test_intel_sources_endpoint(dna_dir):
    _seed_intel_and_run(dna_dir)
    with _client(dna_dir) as c:
        r = c.get("/v1/sources", params={"scope": _SCOPE, "tenant": "acme"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "copiloto-medico" in [s["name"] for s in body["sources"]]
        src = next(s for s in body["sources"] if s["name"] == "copiloto-medico")
        assert src["threshold"] == 0.6
        assert "regulação" in src["pirs"]


def test_intel_insights_endpoint_and_state_filter(dna_dir):
    result = _seed_intel_and_run(dna_dir)
    with _client(dna_dir) as c:
        r = c.get("/v1/insights", params={"scope": _SCOPE, "tenant": "acme"})
        assert r.status_code == 200, r.text
        items = r.json()["insights"]
        assert len(items) == result.kept_count == 7
        # ranked (score desc) and all state=new after a fresh pass
        assert items[0]["score"] >= items[-1]["score"]
        assert all(i["state"] == "new" for i in items)
        # the suppressed weak candidate never became an insight
        assert not any("LLM clínico em PT" in (i["title"] or "") for i in items)
        # state filter
        assert c.get("/v1/insights",
                     params={"scope": _SCOPE, "tenant": "acme", "state": "actioned"}
                     ).json()["insights"] == []


def test_intel_patch_state(dna_dir):
    result = _seed_intel_and_run(dna_dir)
    name = result.kept[0]["name"]
    with _client(dna_dir) as c:
        # new → actioned
        r = c.patch(f"/v1/insights/{name}/state",
                    params={"scope": _SCOPE, "tenant": "acme"}, json={"state": "actioned"})
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "actioned"
        # it now shows under the actioned filter
        actioned = c.get("/v1/insights",
                         params={"scope": _SCOPE, "tenant": "acme", "state": "actioned"}
                         ).json()["insights"]
        assert name in [i["name"] for i in actioned]
        # invalid state → 400
        assert c.patch(f"/v1/insights/{name}/state",
                       params={"scope": _SCOPE, "tenant": "acme"},
                       json={"state": "bogus"}).status_code == 400
        # missing doc → 404
        assert c.patch("/v1/insights/ins-nope/state",
                       params={"scope": _SCOPE, "tenant": "acme"},
                       json={"state": "actioned"}).status_code == 404


def test_intel_metrics_endpoint(dna_dir):
    result = _seed_intel_and_run(dna_dir)
    names = [k["name"] for k in result.kept]
    with _client(dna_dir) as c:
        # no feedback yet → precision undefined
        m0 = c.get("/v1/insights/metrics", params={"scope": _SCOPE, "tenant": "acme"})
        assert m0.status_code == 200, m0.text
        assert m0.json()["precision"] is None
        # action 2, dismiss 1 → precision 2/3, noise 1/3
        for n in names[:2]:
            c.patch(f"/v1/insights/{n}/state",
                    params={"scope": _SCOPE, "tenant": "acme"}, json={"state": "actioned"})
        c.patch(f"/v1/insights/{names[2]}/state",
                params={"scope": _SCOPE, "tenant": "acme"}, json={"state": "dismissed"})
        m = c.get("/v1/insights/metrics",
                  params={"scope": _SCOPE, "tenant": "acme"}).json()
        assert m["actioned"] == 2 and m["dismissed"] == 1
        assert round(m["precision"], 4) == round(2 / 3, 4)
        assert round(m["noise_rate"], 4) == round(1 / 3, 4)


# ── auth: --auth token gates every route but /health ─────────────────────────


def test_auth_token_gate(dna_dir):
    with _client(dna_dir, auth="token", token=_TOKEN) as c:
        # health stays open (a liveness probe needs no token).
        assert c.get("/health").status_code == 200
        # missing bearer → 401.
        assert c.get("/v1/agents", params={"scope": _SCOPE}).status_code == 401
        # wrong bearer → 401.
        assert c.get("/v1/agents", params={"scope": _SCOPE},
                     headers={"Authorization": "Bearer nope"}).status_code == 401
        # right bearer → 200.
        r = c.get("/v1/agents", params={"scope": _SCOPE},
                  headers={"Authorization": f"Bearer {_TOKEN}"})
        assert r.status_code == 200
        assert _AGENT in [a["name"] for a in r.json()["agents"]]


def test_auth_none_is_open(dna_dir):
    with _client(dna_dir) as c:  # auth defaults to none.
        assert c.get("/v1/agents", params={"scope": _SCOPE}).status_code == 200


# ── the [api] extra stays optional (lazy import) ─────────────────────────────


def test_base_import_never_pulls_fastapi():
    """Importing the CLI + the REST module must NOT import `fastapi` at module
    load — only build_app() does. Guards the promise that the base install carries
    no FastAPI requirement (mirrors the MCP lazy-import guard)."""
    import importlib

    importlib.import_module("dna_cli")
    importlib.import_module("dna_cli.api_cmd")
    mod = importlib.import_module("dna_cli._rest_api")

    src = pathlib.Path(mod.__file__).read_text()
    assert "from fastapi import" in src  # it IS imported, lazily (inside build_app)
    top_level = [
        ln for ln in src.splitlines()
        if ln.startswith(("import fastapi", "from fastapi"))
    ]
    assert top_level == [], f"FastAPI must be imported lazily, found top-level: {top_level}"
