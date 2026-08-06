"""Contradiction detection THROUGH THE DOORS (s-grafo-2-contradicao, degrau 2).

The verdict itself is proven in the SDK (``test_memory_contradiction.py`` +
``test_memory_contradiction_pass.py``). What can only be proven here is that a
client actually reaches it:

* the ``claims`` argument EXISTS on the advertised ``remember`` tool schema — a
  parameter the protocol never announces is a parameter no client will ever
  send, and this codebase has shipped a working seam with no reachable path
  before (``capacidade-existe-porta-nao``);
* a MALFORMED claim is REFUSED at the door, by name and with the offending
  index, and writes nothing — the guard is validated ACROSS the door with bad
  input, not in a unit test no door calls (``guard-existe-porta-nao-chama``);
* ``consolidate(dry_run=true)`` hands the contradiction back over the wire.

Driven through the real ``FastMCP`` protocol (the in-memory ``Client``), and
through the real REST app for the HTTP door.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

from dna_cli import _mcp_server as M

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"

_LIVRO = "KindDefinition/livro"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


# ── the tool surface advertises the parameter ───────────────────────────────


def test_the_remember_tool_advertises_claims(dna_dir):
    """A parameter absent from the advertised schema is a parameter no client
    sends. The seam being implemented is not the same as the seam being
    reachable."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            tool = next(t for t in await client.list_tools() if t.name == "remember")
            return tool

    tool = asyncio.run(scenario())
    assert "claims" in (tool.inputSchema.get("properties") or {}), (
        "remember advertises no `claims` — the detector would never receive one"
    )
    assert "contradict" in (tool.description or "").lower(), (
        "the tool must TELL the model what claims are for, or nothing will "
        "declare one"
    )


def test_the_consolidate_tool_tells_the_model_to_relay_contradictions(dna_dir):
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            return next(
                t for t in await client.list_tools() if t.name == "consolidate"
            )

    description = (asyncio.run(scenario()).description or "").lower()
    assert "contradiction" in description
    assert "await_confirmation" in description


# ── the door refuses bad input, by name, and writes nothing ─────────────────


@pytest.mark.parametrize("bad, needle", [
    ([{"object": "pending"}], "claims[0].predicate is required"),
    ([{"predicate": "approval", "polarity": "maybe"}], "claims[0].polarity"),
    ([{"predicate": "approval", "objekt": "pending"}], "unknown field(s)"),
    ([{"predicate": "ok"}, {"predicate": ""}], "claims[1].predicate"),
])
def test_the_mcp_door_refuses_a_malformed_claim(dna_dir, bad, needle):
    """ACROSS the door with invalid input — the message names the index and the
    field, and it arrives as a refusal (``ValueError`` relayed by ``_refusing``),
    never as an unexplained failure."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            with pytest.raises(Exception) as ei:  # noqa: PT011 — ToolError/McpError
                await client.call_tool("remember", {
                    "summary": "o Kind Livro ainda precisa de aprovação",
                    "scope": _SCOPE, "area": _LIVRO, "claims": bad,
                })
            return str(ei.value)

    message = asyncio.run(scenario())
    assert needle in message, message
    assert "ValueError" in message, (
        "the refusal must carry its type name, so a caller can tell a malformed "
        "document from an operator veto"
    )


def test_a_refused_claim_writes_nothing(dna_dir):
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            with pytest.raises(Exception):  # noqa: B017,PT011
                await client.call_tool("remember", {
                    "summary": "memória com claim inválido",
                    "scope": _SCOPE, "area": _LIVRO,
                    "claims": [{"predicate": "approval", "polarity": "maybe"}],
                })
            return await client.call_tool(
                "recall", {"query": "claim inválido", "scope": _SCOPE},
            )

    hits = asyncio.run(scenario()).structured_content["hits"]
    assert not [h for h in hits if "claim inválido" in (h.get("summary") or "")]


# ── the whole loop, over the wire ───────────────────────────────────────────


def test_the_livro_contradiction_travels_the_whole_loop(dna_dir):
    """Write both beliefs through ``remember``, then read the conflict back
    through ``consolidate(dry_run=true)`` — the founder's case, end to end,
    entirely over the MCP protocol."""
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            await client.call_tool("remember", {
                "summary": "O Kind Livro ainda precisa de aprovação.",
                "scope": _SCOPE, "area": _LIVRO, "affect": "ominous",
                "claims": [{"predicate": "approval", "object": "pending"}],
            })
            await client.call_tool("remember", {
                "summary": "O Kind Livro foi aprovado pelo founder no portal.",
                "scope": _SCOPE, "area": _LIVRO, "affect": "triumph",
                "claims": [{"predicate": "approval", "object": "approved"}],
            })
            return await client.call_tool(
                "consolidate", {"scope": _SCOPE, "dry_run": True},
            )

    report = asyncio.run(scenario()).structured_content
    (conflict,) = report["contradictions"]
    assert conflict["subject"] == _LIVRO
    assert conflict["predicate"] == "approval"
    assert len(conflict["names"]) == 2
    assert conflict["proposal"]["strategy"] == "await_confirmation"
    # PRESENTED, not resolved — this call had `apply` off and must stay off.
    assert report["applied"] is False
    assert report["archived"] == 0


def test_a_valid_claim_round_trips_through_the_door(dna_dir):
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        live = await M.boot_live(base_dir=str(dna_dir))
        async with Client(server) as client:
            out = await client.call_tool("remember", {
                "summary": "O Kind Livro ainda precisa de aprovação.",
                "scope": _SCOPE, "area": _LIVRO,
                "claims": [{"predicate": "approval", "object": "pending"}],
            })
            name = out.structured_content["name"]
        return await live.kernel.get_document(_SCOPE, "Engram", name)

    doc = asyncio.run(scenario())
    assert doc["spec"]["claims"] == [
        {"predicate": "approval", "object": "pending", "polarity": "asserts"}
    ]


# ── the REST door ───────────────────────────────────────────────────────────


def _rest_client(dna_dir):
    pytest.importorskip(
        "fastapi", reason="the REST read-API needs the optional 'fastapi' extra"
    )
    from fastapi.testclient import TestClient

    from dna_cli import _rest_api as R

    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE))


def test_the_rest_door_refuses_a_malformed_claim_with_400(dna_dir):
    """A caller mistake must read as one. A 500 tells the caller nothing to
    fix, and the field name is the only part of the message that helps."""
    client = _rest_client(dna_dir)
    res = client.post(f"/v1/memories?scope={_SCOPE}", json={
        "summary": "memória com claim inválido",
        "area": _LIVRO,
        "claims": [{"predicate": "approval", "polarity": "maybe"}],
    })
    assert res.status_code == 400, res.text
    assert "claims[0].polarity" in res.json()["detail"]


def test_the_rest_door_declares_claims_in_its_openapi_contract(dna_dir):
    """The generated clients are built from this schema; a body field missing
    from it is a field no generated client can send."""
    client = _rest_client(dna_dir)
    schema = client.get("/openapi.json").json()
    body = (
        schema["paths"]["/v1/memories"]["post"]["requestBody"]
        ["content"]["application/json"]["schema"]
    )
    ref = body.get("$ref", "")
    if ref:
        body = schema["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    assert "claims" in (body.get("properties") or {}), body


def test_the_rest_door_accepts_a_valid_claim(dna_dir):
    client = _rest_client(dna_dir)
    res = client.post(f"/v1/memories?scope={_SCOPE}", json={
        "summary": "O Kind Livro ainda precisa de aprovação.",
        "area": _LIVRO,
        "claims": [{"predicate": "approval", "object": "pending"}],
    })
    assert res.status_code == 201, res.text
    assert res.json()["kind"] == "Engram"
