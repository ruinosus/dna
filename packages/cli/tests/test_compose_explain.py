"""Provenance ON THE WIRE (i-045) — ``compose_prompt`` explain mode across faces.

``PromptBuilder.explain()`` (the per-section provenance map ``dna explain``
prints) was reachable from exactly ONE consumer: the CLI. These tests prove it
is now reachable from the paid surface — the CORE ``compose_prompt_impl``
(shared by MCP + REST), the REST route ``GET /v1/agents/{name}/prompt`` via
``?explain=true``, and the MCP ``compose_prompt`` tool via ``explain=true`` —
under two NON-NEGOTIABLE contracts:

1. **Opt-in only, shape frozen.** Without the flag, the compose envelope is
   EXACTLY the historical five keys (``scope/agent/tenant/model/prompt``) —
   on the impl dict AND on the REST wire (the route serializes with
   ``response_model_exclude_unset``). A sixth key appearing without the flag
   is a contract break, and these tests die on it.
2. **Byte-equal prompt.** With the flag, ``prompt`` is byte-identical to the
   plain compose (explain delegates to the SAME build path — never re-renders),
   for the base composition and under a tenant overlay.

Plus the HONESTY contract: ``attribution`` says how trustworthy the section
map is — ``declared`` for kernel-owned templates (layout preset / Kind
default), ``heuristic`` when the agent carries its own ``promptTemplate``
(section detection is fail-soft string matching and can err silently).
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastmcp", reason="needs the optional 'fastmcp' extra")

from dna_cli import _mcp_server as M  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_AGENT = "concierge"

#: The historical compose envelope — frozen. Order matters (JSON key order is
#: part of the wire shape the portal/dna-cloud consumes today).
_PLAIN_KEYS = ["scope", "agent", "tenant", "model", "prompt"]
_EXPLAIN_KEYS = _PLAIN_KEYS + ["sections", "attribution"]

#: Every provenance row carries exactly what SectionProvenance.serialize()
#: knows — no invented fields, no dropped fields.
_SECTION_KEYS = {
    "section", "kind", "name", "source", "hash", "version",
    "origin", "is_inherited", "overridden_by_tenant",
}

_OVERLAY_SENTINEL = "ACME-ONLY escalation: page the on-call SRE before answering."


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope, wired via DNA_BASE_DIR."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


async def _overlay_agent(live) -> None:
    """Write the acme per-tenant override of the concierge Agent instruction."""
    await live.kernel.with_tenant("acme").write_document(
        _SCOPE, "Agent", _AGENT,
        {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": _AGENT},
            "spec": {
                "instruction": _OVERLAY_SENTINEL,
                "layout": "persona-first",
                "soul": "helpdesk-host",
                "guardrails": ["grounded-citation"],
                "tools": ["kb-search"],
                "model": "azure/gpt-4o",
            },
        },
    )


# ── core impl: the shape contract (mutation guard b) ─────────────────────────


def test_compose_without_flag_shape_frozen(dna_dir):
    """The plain compose envelope is EXACTLY the historical five keys, in
    order. If explain mode ever leaks a key into the default path (or a key is
    renamed/dropped), this dies."""
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await M.compose_prompt_impl(live, _AGENT, scope=_SCOPE)

    res = asyncio.run(scenario())
    assert list(res.keys()) == _PLAIN_KEYS


def test_compose_explain_false_is_default(dna_dir):
    """``explain=False`` explicitly === omitting it — same frozen envelope."""
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await M.compose_prompt_impl(live, _AGENT, scope=_SCOPE, explain=False)

    assert list(asyncio.run(scenario()).keys()) == _PLAIN_KEYS


# ── core impl: explain mode (mutation guard a) ───────────────────────────────


def test_compose_explain_returns_sections(dna_dir):
    """With the flag: the envelope gains ``sections`` + ``attribution``; every
    declared composition input of the concierge agent is attributed; every row
    carries the full provenance surface; the non-prompt dep (tools) is NOT a
    section. If the sections are dropped from the flagged response, this dies."""
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await M.compose_prompt_impl(live, _AGENT, scope=_SCOPE, explain=True)

    res = asyncio.run(scenario())
    assert list(res.keys()) == _EXPLAIN_KEYS
    labels = [s["section"] for s in res["sections"]]
    assert "instruction" in labels
    assert "soul" in labels
    assert "guardrail:grounded-citation" in labels
    assert not any(lbl.startswith("tool") for lbl in labels)
    for s in res["sections"]:
        assert set(s.keys()) == _SECTION_KEYS, s
        assert s["hash"] and len(s["hash"]) == 64  # sha256 hex — real content hash
        assert s["origin"] == _SCOPE
        assert s["overridden_by_tenant"] is False  # no tenant requested


def test_compose_explain_prompt_byte_identical(dna_dir):
    """The byte-equal gate ON THE PAID SURFACE: the flagged compose returns the
    exact same prompt as the plain one — base AND under a tenant overlay."""
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await _overlay_agent(live)
        out = []
        for tenant in (None, "acme"):
            plain = await M.compose_prompt_impl(live, _AGENT, scope=_SCOPE, tenant=tenant)
            flagged = await M.compose_prompt_impl(
                live, _AGENT, scope=_SCOPE, tenant=tenant, explain=True)
            out.append((tenant, plain["prompt"], flagged["prompt"]))
        return out

    for tenant, plain, flagged in asyncio.run(scenario()):
        assert plain == flagged, f"explain re-rendered the prompt (tenant={tenant})"


def test_compose_explain_tenant_overlay_flagged(dna_dir):
    """A per-tenant overlay is visible IN the provenance: the overlaid section
    is marked ``overridden_by_tenant`` for the tenant compose, and only it."""
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await _overlay_agent(live)
        base = await M.compose_prompt_impl(live, _AGENT, scope=_SCOPE, explain=True)
        tenant = await M.compose_prompt_impl(
            live, _AGENT, scope=_SCOPE, tenant="acme", explain=True)
        return base, tenant

    base, tenant = asyncio.run(scenario())
    assert _OVERLAY_SENTINEL in tenant["prompt"]
    t_rows = {s["section"]: s["overridden_by_tenant"] for s in tenant["sections"]}
    assert t_rows["instruction"] is True
    assert t_rows["soul"] is False
    assert t_rows["guardrail:grounded-citation"] is False
    # The base compose never reports an overlay.
    assert all(s["overridden_by_tenant"] is False for s in base["sections"])


def test_compose_explain_unknown_agent_raises(dna_dir):
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await M.compose_prompt_impl(live, "nope", scope=_SCOPE, explain=True)

    with pytest.raises(ValueError, match="not found"):
        asyncio.run(scenario())


# ── the honesty contract: attribution ───────────────────────────────────────


def test_attribution_declared_for_kernel_owned_template(dna_dir):
    """concierge renders through the named ``persona-first`` layout — a
    kernel-owned template, so the section map is ``declared``."""
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await M.compose_prompt_impl(live, _AGENT, scope=_SCOPE, explain=True)

    assert asyncio.run(scenario())["attribution"] == "declared"


def test_attribution_heuristic_for_custom_template(dna_dir):
    """An agent carrying its OWN promptTemplate gets ``heuristic`` — section
    detection string-matches a user-authored template and can err silently, and
    the contract says so instead of pretending precision."""
    async def scenario():
        live = await M.boot_live(base_dir=str(dna_dir))
        await live.kernel.write_document(
            _SCOPE, "Agent", "custom-tpl",
            {
                "apiVersion": "github.com/ruinosus/dna/v1",
                "kind": "Agent",
                "metadata": {"name": "custom-tpl"},
                "spec": {
                    "instruction": "Do the custom thing.",
                    "soul": "helpdesk-host",
                    # A user-authored template that renders the soul WITHOUT
                    # the kernel's block conventions — exactly the case where
                    # section attribution can miss.
                    "promptTemplate": "CUSTOM: {{{agent.instruction}}}",
                    "model": "azure/gpt-4o",
                },
            },
        )
        return await M.compose_prompt_impl(live, "custom-tpl", scope=_SCOPE, explain=True)

    res = asyncio.run(scenario())
    assert res["attribution"] == "heuristic"
    assert res["prompt"].startswith("CUSTOM: ")


# ── REST face: GET /v1/agents/{name}/prompt?explain=true ────────────────────


@pytest.fixture
def rest_client(dna_dir):
    pytest.importorskip("fastapi", reason="needs the optional 'api' extra")
    from fastapi.testclient import TestClient

    from dna_cli import _rest_api as R

    with TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE)) as c:
        yield c


def test_rest_compose_without_flag_wire_shape_frozen(rest_client):
    """The wire contract: WITHOUT the flag the JSON body is EXACTLY the
    historical five keys — the explain fields are ABSENT (not null). This is
    the cache-poisoning guard too: the flagless response carries no trace of
    explain mode."""
    r = rest_client.get(f"/v1/agents/{_AGENT}/prompt", params={"scope": _SCOPE})
    assert r.status_code == 200
    assert list(r.json().keys()) == _PLAIN_KEYS
    assert "sections" not in r.text and "attribution" not in r.text


def test_rest_compose_explain_false_same_as_absent(rest_client):
    r = rest_client.get(
        f"/v1/agents/{_AGENT}/prompt", params={"scope": _SCOPE, "explain": "false"})
    assert r.status_code == 200
    assert list(r.json().keys()) == _PLAIN_KEYS


def test_rest_compose_explain_true_carries_sections(rest_client):
    plain = rest_client.get(
        f"/v1/agents/{_AGENT}/prompt", params={"scope": _SCOPE}).json()
    r = rest_client.get(
        f"/v1/agents/{_AGENT}/prompt", params={"scope": _SCOPE, "explain": "true"})
    assert r.status_code == 200
    body = r.json()
    assert list(body.keys()) == _EXPLAIN_KEYS
    assert body["attribution"] == "declared"
    # Byte-equal ACROSS requests: the explained prompt IS the plain prompt.
    assert body["prompt"] == plain["prompt"]
    labels = [s["section"] for s in body["sections"]]
    assert {"instruction", "soul", "guardrail:grounded-citation"} <= set(labels)
    for s in body["sections"]:
        assert set(s.keys()) == _SECTION_KEYS


def test_rest_compose_explain_unknown_agent_404(rest_client):
    r = rest_client.get(
        "/v1/agents/nope/prompt", params={"scope": _SCOPE, "explain": "true"})
    assert r.status_code == 404


def test_rest_openapi_documents_explain(rest_client):
    """The OpenAPI contract DOCUMENTS the semantics: the query param exists and
    the response schema explains the attribution honesty rule."""
    spec = rest_client.app.openapi()
    op = spec["paths"]["/v1/agents/{name}/prompt"]["get"]
    params = {p["name"]: p for p in op["parameters"]}
    assert "explain" in params
    assert params["explain"]["required"] is False
    schemas = spec["components"]["schemas"]
    assert "PromptSectionProvenance" in schemas
    attribution = schemas["AgentPromptResponse"]["properties"]["attribution"]
    desc = attribution.get("description", "")
    assert "heuristic" in desc and "declared" in desc
    # The honesty semantics are written down, not implied.
    assert "missing" in desc or "omit" in desc


# ── MCP face: the compose_prompt tool grows the same opt-in ─────────────────


def test_mcp_compose_prompt_tool_explain(dna_dir):
    """Through the REAL FastMCP protocol: the tool takes ``explain`` and the
    flagged call carries sections while the plain call keeps today's shape."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            plain = (await client.call_tool(
                "compose_prompt", {"agent": _AGENT, "scope": _SCOPE}
            )).structured_content
            flagged = (await client.call_tool(
                "compose_prompt",
                {"agent": _AGENT, "scope": _SCOPE, "explain": True},
            )).structured_content
        return plain, flagged

    plain, flagged = asyncio.run(scenario())
    assert list(plain.keys()) == _PLAIN_KEYS
    assert list(flagged.keys()) == _EXPLAIN_KEYS
    assert flagged["prompt"] == plain["prompt"]
    assert [s["section"] for s in flagged["sections"]].count("instruction") == 1
    assert flagged["attribution"] == "declared"
