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


# ── memory: POST remembers into the tenant's OWN overlay (the add affordance) ─


def test_remember_memory_roundtrips(dna_dir):
    """The portal's add affordance: POST /v1/memories persists ONE memory into
    the tenant's OWN overlay, and it round-trips on the very next list — the SAME
    CORE remember_impl the MCP `remember` tool uses (one core, three faces)."""
    with _client(dna_dir) as c:
        r = c.post(
            "/v1/memories",
            params={"scope": _SCOPE, "tenant": "acme"},
            json={
                "summary": "Ship the memory panel end-to-end before polishing",
                "area": "dna-cloud",
                "tags": ["decision", "claude"],
            },
        )
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["kind"] == "Engram"
        name = created["name"]
        assert name  # deterministic slug the DELETE path targets

        # round-trips on the next list, tenant-scoped ...
        mems = c.get(
            "/v1/memories", params={"scope": _SCOPE, "tenant": "acme"}
        ).json()["memories"]
        mine = next((m for m in mems if m["name"] == name), None)
        assert mine is not None, [m["name"] for m in mems]
        assert mine["summary"] == "Ship the memory panel end-to-end before polishing"
        assert mine["area"] == "dna-cloud"
        assert "decision" in mine["tags"]

        # ... and is INVISIBLE to another tenant (the #83 isolation holds on write).
        other = {m["name"] for m in c.get(
            "/v1/memories", params={"scope": _SCOPE, "tenant": "globex"}
        ).json()["memories"]}
        assert name not in other


def test_remember_memory_rejects_empty_summary(dna_dir):
    """An empty summary is a 400 — nothing durable is written."""
    with _client(dna_dir) as c:
        r = c.post(
            "/v1/memories",
            params={"scope": _SCOPE, "tenant": "acme"},
            json={"summary": "   "},
        )
        assert r.status_code == 400, r.text


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
    # `items` carries the FULL set (all stories + features), same newest-first
    # order — the console renders every column in full, not just the `recent` head.
    assert [r["name"] for r in body["items"]] == ["f-one", "s-two", "s-one"]
    assert len(body["items"]) == body["totals"]["total"] == 3
    assert {r["kind"] for r in body["items"]} == {"Story", "Feature"}


def test_portfolio_board_items_is_full_not_recent(dna_dir):
    """`recent` is a bounded head; `items` is the WHOLE board. With more items
    than the `recent` window, `items` still returns all of them (the fix for a
    board that showed only ~6 of N)."""
    _seed_portfolio(dna_dir)
    # Seed extra stories so the board exceeds the default recent window.
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        for i in range(8):
            name = f"s-extra-{i}"
            doc = {"apiVersion": _SDLC_API, "kind": "Story",
                   "metadata": {"name": name},
                   "spec": {"name": name, "title": f"Extra {i}",
                            "description": f"extra story {i}", "status": "todo",
                            "created_at": f"2026-07-0{i+1}T09:00:00+00:00"}}
            await live.kernel.write_document(_SCOPE, "Story", name, doc, tenant=None)

    asyncio.run(go())
    with _client(dna_dir) as c:
        body = c.get("/v1/board",
                     params={"scope": _SCOPE, "tenant": "acme", "recent": 3}).json()
    # 2 seeded stories + 8 extra + 1 feature = 11 total; recent is capped at 3.
    assert body["totals"]["total"] == 11
    assert len(body["recent"]) == 3
    assert len(body["items"]) == 11  # the FULL board, past the recent window
    # scope is required (the board is always for an explicit board_scope).
    with _client(dna_dir) as c:
        assert c.get("/v1/board", params={"tenant": "acme"}).status_code == 422


# ── portfolio: board ITEM detail (the console's drawer) ──────────────────────


def _seed_work_item(dna_dir):
    """Seed one RICH Story (AC/DoD/timeline/produces) so the item-detail endpoint
    has a full doc to project — global SDLC Kind, written unbound."""
    from dna_cli import _mcp_server as M

    doc = {
        "apiVersion": _SDLC_API, "kind": "Story", "metadata": {"name": "s-rich"},
        "spec": {
            "name": "s-rich", "title": "Rich story", "description": "a full body",
            "status": "in-progress", "feature": "f-one", "priority": "high",
            "labels": ["cli", "ts"], "reporter": "claude-code",
            "business_value": 400,
            "acceptance_criteria": [
                {"text": "AC one", "done": False},
                {"text": "AC two", "done": True, "done_at": "2026-07-11T10:00:00+00:00"},
            ],
            "definition_of_done": [{"text": "DoD one", "done": False}],
            "created_at": "2026-07-10T10:00:00+00:00",
            "timeline": [
                {"at": "2026-07-10T10:00:00+00:00", "actor": "claude-code",
                 "type": "status_change", "to": "todo"},
                {"at": "2026-07-10T10:05:00+00:00", "actor": "claude-code",
                 "type": "comment", "summary": "started the work"},
            ],
            "produces": [
                {"kind": "Plan", "name": "plan-s-rich", "role": "implementation"},
            ],
        },
    }

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        await live.kernel.write_document(_SCOPE, "Story", "s-rich", doc, tenant=None)

    asyncio.run(go())


def test_board_item_full_doc(dna_dir):
    """The item-detail endpoint returns the WHOLE work-item: description, AC/DoD
    (verbatim, with their done flags), status, timeline, feature ref, produces."""
    _seed_work_item(dna_dir)
    with _client(dna_dir) as c:
        body = c.get("/v1/board/item",
                     params={"scope": _SCOPE, "name": "s-rich"}).json()
    assert body["kind"] == "Story"
    assert body["name"] == "s-rich"
    assert body["title"] == "Rich story"
    assert body["description"] == "a full body"
    assert body["status"] == "in-progress"
    assert body["feature"] == "f-one"
    assert body["priority"] == "high"
    assert body["labels"] == ["cli", "ts"]
    assert body["business_value"] == 400
    assert [ac["text"] for ac in body["acceptance_criteria"]] == ["AC one", "AC two"]
    assert body["acceptance_criteria"][1]["done"] is True
    assert body["definition_of_done"][0]["text"] == "DoD one"
    assert [ev["type"] for ev in body["timeline"]] == ["status_change", "comment"]
    assert body["produces"][0]["name"] == "plan-s-rich"
    assert body["created_at"] == "2026-07-10T10:00:00+00:00"


def test_board_item_kind_hint_and_not_found(dna_dir):
    """An explicit ``kind`` hint constrains the probe (wrong Kind → 404); an
    unknown name → 404; scope + name are required (422)."""
    _seed_work_item(dna_dir)
    with _client(dna_dir) as c:
        # right kind hint resolves the same doc.
        ok = c.get("/v1/board/item",
                   params={"scope": _SCOPE, "name": "s-rich", "kind": "Story"})
        assert ok.status_code == 200 and ok.json()["kind"] == "Story"
        # a WRONG kind hint → 404 (the probe never falls back off the hint).
        assert c.get("/v1/board/item",
                     params={"scope": _SCOPE, "name": "s-rich", "kind": "Feature"}
                     ).status_code == 404
        # unknown name → 404.
        assert c.get("/v1/board/item",
                     params={"scope": _SCOPE, "name": "s-nope"}).status_code == 404
        # scope + name are both required.
        assert c.get("/v1/board/item",
                     params={"scope": _SCOPE}).status_code == 422
        assert c.get("/v1/board/item",
                     params={"name": "s-rich"}).status_code == 422


# ── portfolio: Membership / Role (the Membros panel — RBAC read + write) ──────


def _seed_members(dna_dir, *, tenant="acme"):
    """Seed the portfolio + a small RBAC graph on the ``acme`` project: an org
    Owner (superuser), an org Member who is also a project Admin (highest-role-
    wins), and a project Guest. Plus the 4 standard Role rungs (the ladder as
    data). Written into the tenant overlay via the SAME kernel write path a face
    uses."""
    _seed_portfolio(dna_dir, tenant=tenant)
    from dna_cli import _mcp_server as M
    from dna.application.runtime import _member_doc_name

    def _role(rid, display, rank):
        return {"apiVersion": _PORTFOLIO_API, "kind": "Role",
                "metadata": {"name": rid},
                "spec": {"role_id": rid, "display_name": display, "rank": rank}}

    def _member(user, scope_type, scope_ref, role):
        # Name via the SAME deterministic convention the write path uses, so a
        # seeded grant is addressable by set/remove (a role change/remove hits the
        # same doc). Role/Membership specs carry no `name` (additionalProperties:false).
        name = _member_doc_name(user, scope_type, scope_ref)
        return {"apiVersion": _PORTFOLIO_API, "kind": "Membership",
                "metadata": {"name": name},
                "spec": {"user": user, "scope_type": scope_type,
                         "scope_ref": scope_ref, "role": role, "status": "active"}}

    roles = [
        _role("owner", "Owner", 40), _role("admin", "Admin", 30),
        _role("member", "Member", 20), _role("guest", "Guest", 10),
    ]
    members = [
        # org owner → superuser (Owner on every project in the org)
        _member("owner@acme.com", "org", "acme-labs", "owner"),
        # org member + project admin → effective Admin (highest-role-wins)
        _member("admin@acme.com", "org", "acme-labs", "member"),
        _member("admin@acme.com", "project", "acme", "admin"),
        # project guest, no org grant
        _member("guest@acme.com", "project", "acme", "guest"),
    ]

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        for d in [*roles, *members]:
            await live.kernel.write_document(
                _SCOPE, d["kind"], d["metadata"]["name"], d, tenant=tenant)

    asyncio.run(go())


def test_members_list_resolves_effective_roles(dna_dir):
    """The Membros list resolves highest-role-wins: the org owner is superuser
    (Owner here), the org-member-who-is-project-admin resolves Admin, the project
    guest stays Guest. Ordered highest-rank first."""
    _seed_members(dna_dir)
    with _client(dna_dir) as c:
        body = c.get("/v1/projects/acme/members",
                     params={"scope": _SCOPE, "tenant": "acme"}).json()
    by_user = {m["user"]: m for m in body["members"]}
    assert by_user["owner@acme.com"]["role"] == "owner"
    assert by_user["owner@acme.com"]["is_org_owner"] is True
    assert by_user["admin@acme.com"]["role"] == "admin"
    assert by_user["admin@acme.com"]["org_role"] == "member"
    assert by_user["admin@acme.com"]["project_role"] == "admin"
    assert by_user["guest@acme.com"]["role"] == "guest"
    # highest rank first.
    assert [m["role"] for m in body["members"]][:1] == ["owner"]


def test_members_viewer_can_manage(dna_dir):
    """``viewer`` reports whether the caller may manage membership: Owner/Admin →
    can_manage; a Guest → not."""
    _seed_members(dna_dir)
    with _client(dna_dir) as c:
        as_admin = c.get("/v1/projects/acme/members",
                         params={"scope": _SCOPE, "tenant": "acme",
                                 "viewer": "admin@acme.com"}).json()
        as_guest = c.get("/v1/projects/acme/members",
                         params={"scope": _SCOPE, "tenant": "acme",
                                 "viewer": "guest@acme.com"}).json()
    assert as_admin["viewer"]["can_manage"] is True
    assert next(m for m in as_admin["members"] if m["user"] == "admin@acme.com")["you"]
    assert as_guest["viewer"]["can_manage"] is False


def test_members_unknown_project_404(dna_dir):
    _seed_members(dna_dir)
    with _client(dna_dir) as c:
        assert c.get("/v1/projects/nope/members",
                     params={"scope": _SCOPE, "tenant": "acme"}).status_code == 404


def test_members_admin_can_set_role(dna_dir):
    """An Admin may invite/set a Member role — the write succeeds and the new
    member appears in the list."""
    _seed_members(dna_dir)
    with _client(dna_dir) as c:
        r = c.post("/v1/projects/acme/members",
                   params={"scope": _SCOPE, "tenant": "acme"},
                   json={"user": "newbie@acme.com", "role": "member",
                         "actor": "admin@acme.com"})
        assert r.status_code == 201, r.text
        assert r.json()["member"]["role"] == "member"
        body = c.get("/v1/projects/acme/members",
                     params={"scope": _SCOPE, "tenant": "acme"}).json()
    assert "newbie@acme.com" in {m["user"] for m in body["members"]}


def test_members_guest_cannot_mutate(dna_dir):
    """RBAC: a Guest actor is rejected (403) on a write — the isolation the panel
    relies on to gate its controls."""
    _seed_members(dna_dir)
    with _client(dna_dir) as c:
        r = c.post("/v1/projects/acme/members",
                   params={"scope": _SCOPE, "tenant": "acme"},
                   json={"user": "x@acme.com", "role": "member",
                         "actor": "guest@acme.com"})
        assert r.status_code == 403, r.text
        # an anonymous actor (no identity) is likewise rejected.
        assert c.post("/v1/projects/acme/members",
                      params={"scope": _SCOPE, "tenant": "acme"},
                      json={"user": "x@acme.com", "role": "member"}
                      ).status_code == 403


def test_members_only_owner_grants_owner(dna_dir):
    """An Admin cannot escalate someone to Owner (403); an Owner can."""
    _seed_members(dna_dir)
    with _client(dna_dir) as c:
        assert c.post("/v1/projects/acme/members",
                      params={"scope": _SCOPE, "tenant": "acme"},
                      json={"user": "x@acme.com", "role": "owner",
                            "actor": "admin@acme.com"}).status_code == 403
        assert c.post("/v1/projects/acme/members",
                      params={"scope": _SCOPE, "tenant": "acme"},
                      json={"user": "x@acme.com", "role": "owner",
                            "actor": "owner@acme.com"}).status_code == 201


def test_members_unknown_role_422(dna_dir):
    _seed_members(dna_dir)
    with _client(dna_dir) as c:
        assert c.post("/v1/projects/acme/members",
                      params={"scope": _SCOPE, "tenant": "acme"},
                      json={"user": "x@acme.com", "role": "wizard",
                            "actor": "owner@acme.com"}).status_code == 422


def test_members_remove_and_rbac(dna_dir):
    """Admin removes a project Guest's grant (200), then a repeat 404s (gone).
    A Guest actor cannot remove (403)."""
    _seed_members(dna_dir)
    with _client(dna_dir) as c:
        # guest cannot remove.
        assert c.delete("/v1/projects/acme/members/guest@acme.com",
                        params={"scope": _SCOPE, "tenant": "acme",
                                "actor": "guest@acme.com"}).status_code == 403
        # admin removes the guest's project grant.
        r = c.delete("/v1/projects/acme/members/guest@acme.com",
                     params={"scope": _SCOPE, "tenant": "acme",
                             "actor": "admin@acme.com"})
        assert r.status_code == 200, r.text
        # gone → the user no longer in the list.
        body = c.get("/v1/projects/acme/members",
                     params={"scope": _SCOPE, "tenant": "acme"}).json()
        assert "guest@acme.com" not in {m["user"] for m in body["members"]}
        # removing again → 404.
        assert c.delete("/v1/projects/acme/members/guest@acme.com",
                        params={"scope": _SCOPE, "tenant": "acme",
                                "actor": "admin@acme.com"}).status_code == 404


def test_members_tenant_isolation(dna_dir):
    """A membership seeded for tenant ``acme`` is invisible to tenant ``other``
    (which sees an empty roster on the shared base project)."""
    _seed_members(dna_dir, tenant="acme")
    # Seed the project (only) for a second tenant so the slug resolves there.
    _seed_portfolio(dna_dir, tenant="other")
    with _client(dna_dir) as c:
        acme = c.get("/v1/projects/acme/members",
                     params={"scope": _SCOPE, "tenant": "acme"}).json()
        other = c.get("/v1/projects/acme/members",
                      params={"scope": _SCOPE, "tenant": "other"}).json()
    assert {m["user"] for m in acme["members"]} >= {"owner@acme.com", "admin@acme.com"}
    assert other["members"] == []


# ── first-owner provisioning: POST /v1/tenants/{tid}/provision-owner ─────────
#
# The C3 fix: a brand-new tenant has ZERO Membership docs, so its first user could
# not manage members (_require_manage 403'd every write). Provisioning makes the
# signed-in user Owner of their OWN tenant. These drive the endpoint in-process
# then prove, end-to-end, that the just-provisioned user can add a member.


def test_provision_owner_unblocks_first_member_add(dna_dir):
    """A fresh tenant (portfolio seeded, NO memberships) → the first user cannot
    manage members; after provisioning they are Owner and CAN add a member."""
    _seed_portfolio(dna_dir, tenant="acme")  # org acme-labs + project acme, no members
    founder = "founder@acme.com"
    with _client(dna_dir) as c:
        # Before: the founder has no grant — cannot manage, and a write 403s.
        before = c.get("/v1/projects/acme/members",
                       params={"scope": _SCOPE, "tenant": "acme",
                               "viewer": founder}).json()
        assert before["members"] == []
        assert before["viewer"]["can_manage"] is False
        assert c.post("/v1/projects/acme/members",
                      params={"scope": _SCOPE, "tenant": "acme"},
                      json={"user": "teammate@acme.com", "role": "member",
                            "actor": founder}).status_code == 403

        # Provision: the founder becomes Owner of their tenant (org-scope grant).
        r = c.post("/v1/tenants/acme/provision-owner",
                   params={"scope": _SCOPE}, json={"user": founder})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["provisioned"] is True
        assert {"scope_type": "org", "scope_ref": "acme-labs",
                "role": "owner"} in body["grants"]

        # After: the founder is Owner (can_manage) AND the add now succeeds.
        after = c.get("/v1/projects/acme/members",
                      params={"scope": _SCOPE, "tenant": "acme",
                              "viewer": founder}).json()
        assert after["viewer"]["can_manage"] is True
        assert next(m for m in after["members"]
                    if m["user"] == founder)["role"] == "owner"
        add = c.post("/v1/projects/acme/members",
                     params={"scope": _SCOPE, "tenant": "acme"},
                     json={"user": "teammate@acme.com", "role": "member",
                           "actor": founder})
        assert add.status_code == 201, add.text
        roster = c.get("/v1/projects/acme/members",
                       params={"scope": _SCOPE, "tenant": "acme"}).json()
    assert "teammate@acme.com" in {m["user"] for m in roster["members"]}


def test_provision_owner_is_first_owner_only_noop(dna_dir):
    """Idempotent + first-owner-only: with an Owner already present, provisioning a
    DIFFERENT user is a NO-OP — a later user does not auto-escalate to Owner."""
    _seed_members(dna_dir)  # seeds owner@acme.com as org owner
    with _client(dna_dir) as c:
        r = c.post("/v1/tenants/acme/provision-owner",
                   params={"scope": _SCOPE},
                   json={"user": "intruder@acme.com"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["provisioned"] is False
        assert body["reason"] == "owner_exists"
        assert body["grants"] == []
        roster = c.get("/v1/projects/acme/members",
                       params={"scope": _SCOPE, "tenant": "acme"}).json()
    # The intruder was NOT granted anything.
    assert "intruder@acme.com" not in {m["user"] for m in roster["members"]}


def test_provision_owner_requires_user(dna_dir):
    """An empty user is a 400 (tenant comes from the path segment)."""
    _seed_portfolio(dna_dir, tenant="acme")
    with _client(dna_dir) as c:
        assert c.post("/v1/tenants/acme/provision-owner",
                      params={"scope": _SCOPE}, json={"user": ""}
                      ).status_code == 400


# ── cloud billing → enforcement bridge: PUT /v1/workspace-plan ───────────────
#
# The write that closes the billing→runtime gap (finding C4): dna-cloud's Stripe
# webhook PUTs the workspace→tier assignment here, and the MCP runtime reads it
# via kernel.workspace_plan(workspace_id) (ADR "Model B" — billing keys on the
# workspace, not the Azure tid). These drive the REST endpoint in-process, then
# read back through the SAME kernel accessor the MCP quota guard uses — proving
# the two stores are bridged (webhook write → runtime read).


def _read_workspace_plan(dna_dir, workspace_id: str) -> dict | None:
    """Read the WorkspacePlan the way the MCP quota guard does
    (kernel.workspace_plan), on its own loop against the on-disk source the app
    also wrote to."""
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await live.kernel.workspace_plan(workspace_id)

    return asyncio.run(go())


def test_workspace_plan_put_bridges_to_runtime_read(dna_dir):
    """PUT /v1/workspace-plan(acme→pro) → kernel.workspace_plan('acme') resolves
    pro. The C4 bridge: what the webhook writes is what the runtime reads."""
    with _client(dna_dir) as c:
        r = c.put(
            "/v1/workspace-plan",
            json={
                "workspace_id": "acme",
                "tier_id": "pro",
                "stripe_customer_id": "cus_123",
                "stripe_subscription_id": "sub_123",
                "status": "active",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["tier_id"] == "pro"
        assert r.json()["workspace_id"] == "acme"

    plan = _read_workspace_plan(dna_dir, "acme")
    assert plan is not None, "the runtime read must see the webhook's write"
    spec = plan["spec"]
    assert spec["workspace_id"] == "acme"
    assert spec["tier_id"] == "pro"
    assert spec["source"] == "stripe"
    assert spec["stripe_customer_id"] == "cus_123"
    assert spec["status"] == "active"
    assert spec.get("updated_at")


def test_workspace_plan_put_is_idempotent_and_downgrades(dna_dir):
    """Stripe redelivers (at-least-once) → a repeat PUT converges (still one
    assignment, same tier); a later downgrade PUT flips pro→free in place."""
    with _client(dna_dir) as c:
        c.put("/v1/workspace-plan",
              json={"workspace_id": "acme", "tier_id": "pro", "status": "active"})
        # redelivery of the same event → same result, no duplicate doc.
        c.put("/v1/workspace-plan",
              json={"workspace_id": "acme", "tier_id": "pro", "status": "active"})
    assert _read_workspace_plan(dna_dir, "acme")["spec"]["tier_id"] == "pro"

    with _client(dna_dir) as c:
        r = c.put("/v1/workspace-plan",
                  json={"workspace_id": "acme", "tier_id": "free", "status": "canceled"})
        assert r.status_code == 200
    plan = _read_workspace_plan(dna_dir, "acme")["spec"]
    assert plan["tier_id"] == "free"
    assert plan["status"] == "canceled"


def test_workspace_plan_put_requires_workspace_and_tier(dna_dir):
    """A missing workspace_id or tier_id is a 400 (the two required schema
    fields)."""
    with _client(dna_dir) as c:
        assert c.put("/v1/workspace-plan",
                     json={"workspace_id": "", "tier_id": "pro"}).status_code == 400
        assert c.put("/v1/workspace-plan",
                     json={"workspace_id": "acme", "tier_id": ""}).status_code == 400


def test_workspace_plan_put_is_auth_guarded(dna_dir):
    """The bridge write is bearer-guarded (only dna-cloud holds DNA_API_TOKEN):
    a missing/wrong bearer is 401, the right one 200."""
    with _client(dna_dir, auth="token", token=_TOKEN) as c:
        body = {"workspace_id": "acme", "tier_id": "pro"}
        assert c.put("/v1/workspace-plan", json=body).status_code == 401
        assert c.put("/v1/workspace-plan", json=body,
                     headers={"Authorization": "Bearer nope"}).status_code == 401
        assert c.put("/v1/workspace-plan", json=body,
                     headers={"Authorization": f"Bearer {_TOKEN}"}).status_code == 200


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
