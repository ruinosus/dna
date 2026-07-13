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


# ── intel: the ?source filter isolates a project's own insights ──────────────


def test_intel_insights_source_filter(dna_dir):
    """A project shows only its OWN insights: ``?source=<name>`` filters the
    stream to one IntelSource (the console's per-project view)."""
    _seed_intel_and_run(dna_dir, source="copiloto-medico", tenant="acme")
    _seed_intel_and_run(dna_dir, source="dna", tenant="acme")
    with _client(dna_dir) as c:
        all_ins = c.get("/v1/insights", params={"scope": _SCOPE, "tenant": "acme"}).json()["insights"]
        dna_ins = c.get("/v1/insights",
                        params={"scope": _SCOPE, "tenant": "acme", "source": "dna"}
                        ).json()["insights"]
    # the union carries both sources; the filtered view is dna-only.
    assert {i["source_ref"] for i in all_ins} == {"copiloto-medico", "dna"}
    assert dna_ins, "source=dna returned nothing"
    assert all(i["source_ref"] == "dna" for i in dna_ins)
    assert len(dna_ins) < len(all_ins)


# ── portfolio: orgs / projects / project detail / repos / board ──────────────

_PORTFOLIO_API = "github.com/ruinosus/dna/portfolio/v1"
_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"


def _seed_portfolio(dna_dir, *, tenant="acme"):
    """Seed a small portfolio (1 org, 2 repos, 1 multi-repo project) + a tiny
    board (2 stories, 1 feature) via the SAME kernel write path a face uses.
    Runs on its own loop; the filesystem source persists so the TestClient-booted
    app reads it back."""
    from dna_cli import _mcp_server as M

    def _doc(kind, name, spec, api=_PORTFOLIO_API):
        return {"apiVersion": api, "kind": kind, "metadata": {"name": name},
                "spec": {"name": name, **spec}}

    # TENANTED portfolio docs (written into the tenant overlay).
    tenant_docs = [
        _doc("Organization", "acme-labs", {"slug": "acme-labs", "display_name": "ACME Labs"}),
        _doc("Repo", "acme-web", {"url": "https://github.com/acme/web", "provider": "github"}),
        _doc("Repo", "acme-api", {"url": "https://github.com/acme/api", "provider": "gitlab"}),
        _doc("Project", "acme", {
            "slug": "acme", "org_ref": "acme-labs", "board_scope": _SCOPE,
            "repo_refs": ["acme-web", "acme-api", "ghost-repo"],  # ghost = missing ref
            "intel_source_refs": ["acme-src"], "visibility": "private",
        }),
    ]
    # Story/Feature are GLOBAL SDLC Kinds — written unbound (no tenant); a
    # tenant-scoped board query still sees them (global docs cross tenants).
    global_docs = [
        _doc("Story", "s-one", {"title": "Story one", "description": "one",
                                "status": "in-progress",
                                "created_at": "2026-07-10T10:00:00+00:00"}, api=_SDLC_API),
        _doc("Story", "s-two", {"title": "Story two", "description": "two",
                                "status": "done",
                                "created_at": "2026-07-11T10:00:00+00:00"}, api=_SDLC_API),
        _doc("Feature", "f-one", {"title": "Feature one", "description": "feat one",
                                  "status": "in-development",
                                  "created_at": "2026-07-12T10:00:00+00:00"}, api=_SDLC_API),
    ]

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        for d in tenant_docs:
            await live.kernel.write_document(
                _SCOPE, d["kind"], d["metadata"]["name"], d, tenant=tenant)
        for d in global_docs:
            await live.kernel.write_document(
                _SCOPE, d["kind"], d["metadata"]["name"], d, tenant=None)

    asyncio.run(go())


def test_portfolio_orgs(dna_dir):
    _seed_portfolio(dna_dir)
    with _client(dna_dir) as c:
        body = c.get("/v1/orgs", params={"scope": _SCOPE, "tenant": "acme"}).json()
    assert body["tenant"] == "acme"
    org = next(o for o in body["orgs"] if o["name"] == "acme-labs")
    assert org["slug"] == "acme-labs"
    assert org["display_name"] == "ACME Labs"


def test_portfolio_projects(dna_dir):
    _seed_portfolio(dna_dir)
    with _client(dna_dir) as c:
        projects = c.get("/v1/projects", params={"scope": _SCOPE, "tenant": "acme"}).json()["projects"]
    proj = next(p for p in projects if p["name"] == "acme")
    assert proj["board_scope"] == _SCOPE
    assert proj["repo_refs"] == ["acme-web", "acme-api", "ghost-repo"]
    assert proj["org_ref"] == "acme-labs"
    assert proj["visibility"] == "private"
    assert proj["intel_source_refs"] == ["acme-src"]


def test_portfolio_project_detail_resolves_repos(dna_dir):
    """Project detail resolves ``repo_refs`` → the Repo docs; a missing ref
    (``ghost-repo``) is skipped honestly, never fabricated."""
    _seed_portfolio(dna_dir)
    with _client(dna_dir) as c:
        body = c.get("/v1/projects/acme", params={"scope": _SCOPE, "tenant": "acme"}).json()
        # slug lookup resolves; 404 for an unknown slug.
        assert c.get("/v1/projects/nope",
                     params={"scope": _SCOPE, "tenant": "acme"}).status_code == 404
    assert body["project"]["name"] == "acme"
    resolved = {r["name"]: r for r in body["repos"]}
    assert set(resolved) == {"acme-web", "acme-api"}  # ghost-repo dropped
    assert resolved["acme-web"]["provider"] == "github"
    assert resolved["acme-api"]["provider"] == "gitlab"


def test_portfolio_repos(dna_dir):
    _seed_portfolio(dna_dir)
    with _client(dna_dir) as c:
        repos = c.get("/v1/repos", params={"scope": _SCOPE, "tenant": "acme"}).json()["repos"]
    names = {r["name"] for r in repos}
    assert {"acme-web", "acme-api"} <= names


def test_portfolio_board_summary(dna_dir):
    """The board summary reuses the SDLC read impl: counts by status, totals, and
    the newest items (created_at desc)."""
    _seed_portfolio(dna_dir)
    with _client(dna_dir) as c:
        body = c.get("/v1/board", params={"scope": _SCOPE, "tenant": "acme", "recent": 3}).json()
    assert body["counts"]["stories"] == {"in-progress": 1, "done": 1}
    assert body["counts"]["features"] == {"in-development": 1}
    assert body["totals"] == {"stories": 2, "features": 1, "total": 3}
    # newest-first: the feature (2026-07-12) leads, then s-two (07-11), s-one (07-10).
    assert [r["name"] for r in body["recent"]] == ["f-one", "s-two", "s-one"]
    # scope is required (the board is always for an explicit board_scope).
    with _client(dna_dir) as c:
        assert c.get("/v1/board", params={"tenant": "acme"}).status_code == 422


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
