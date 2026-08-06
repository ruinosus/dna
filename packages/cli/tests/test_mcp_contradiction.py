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


# ── …and TELLS the model WHEN to declare one, and when NOT to ───────────────
#
# Degrau 2 shipped the field and the algebra, and the acceptance still did not
# close: the real memories carry no claims, so the detector answers `undecided`
# about every one of them. Knowing WHAT a claim is never made anything declare
# one — the tool has to say WHEN. These are the door-side proof that it does,
# because a rule that lives only in a Python docstring is a rule the model
# never reads.


def _remember_description(dna_dir) -> str:
    from fastmcp import Client

    async def scenario():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            tool = next(t for t in await client.list_tools() if t.name == "remember")
            return tool.description or ""

    return asyncio.run(scenario())


def test_the_announced_description_carries_the_one_instruction(dna_dir):
    """VERBATIM, and from the SDK — not a paraphrase kept in the face.

    The text is owned by ``dna.memory.contradiction``, beside the rule it
    paraphrases, and interpolated into the tool's ``description=`` (a docstring
    literal cannot interpolate). This is what makes deleting the instruction —
    or letting this face drift to its own stale copy — a red test.
    """
    from dna.memory.contradiction import WHEN_TO_CLAIM

    # A gutted constant is `in` every string. Say the instruction still EXISTS
    # before asserting it travels, or emptying it passes this test.
    assert len(WHEN_TO_CLAIM.strip()) > 200, "the instruction was emptied"
    assert WHEN_TO_CLAIM in _remember_description(dna_dir), (
        "the wire does not carry `WHEN_TO_CLAIM` — whatever the Python "
        "docstrings say, the model reads only this"
    )


def test_the_instruction_is_a_discriminant_and_not_a_category_list(dna_dir):
    """The trap this instruction exists to avoid is OVER-triggering.

    An instruction with only the YES half — "declare a claim whenever you record
    a state that can later change", which is what this tool said until now —
    asks for a claim on "Barna likes tea" too, because a preference IS a state
    that can change. The pass then reports a normal preference as a conflict,
    and a detector that flags the normal trains its reader to ignore the next
    one, including the true one.

    So the announced text must carry BOTH halves. These are the load-bearing
    phrases; if a rewrite drops one, this is where a reviewer is told.
    """
    announced = _remember_description(dna_dir).lower()

    # the discriminant itself — substitution, not importance, not "is it a fact?"
    assert "substitution" in announced
    assert "would make this one false" in announced

    # the counter-cases: the half that keeps the pass quiet about the normal
    assert "accumulate" in announced, (
        "no ACCUMULATE case — nothing stops a claim on 'likes tea' beside "
        "'likes coffee', a false contradiction by construction"
    )
    assert "un-happen" in announced, (
        "no EVENT case — nothing stops a claim on 'met the client on 03/08', "
        "which substitutes nothing and can only produce noise"
    )
    assert "no claims is the normal case" in announced, (
        "the tool must say that declaring NOTHING is fine, or a model reading "
        "an instruction infers it is expected to comply on every write"
    )

    # the format the trigger implies — polarity, and when the object may go
    assert "existence claim" in announced
    assert "denies" in announced


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


def test_the_rest_door_publishes_when_to_declare_a_claim(dna_dir):
    """On the FIELD, where the caller choosing what to send is looking.

    The REST reader is a human (or a generated client's types), and the whole
    instruction is useless one paragraph away from the decision it governs. The
    same ``WHEN_TO_CLAIM`` the MCP tool announces — one text, three faces.
    """
    from dna.memory.contradiction import WHEN_TO_CLAIM

    client = _rest_client(dna_dir)
    schema = client.get("/openapi.json").json()
    body = (
        schema["paths"]["/v1/memories"]["post"]["requestBody"]
        ["content"]["application/json"]["schema"]
    )
    ref = body.get("$ref", "")
    if ref:
        body = schema["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    described = body["properties"]["claims"].get("description") or ""
    assert WHEN_TO_CLAIM in described, (
        "`claims` is declared but not explained — a caller told only that the "
        "field exists sends one for everything, and the pass starts crying wolf"
    )
    # …and the two NO cases survived into the published contract, since an
    # emptied constant would satisfy the containment above on its own.
    low = described.lower()
    assert "would make this one false" in low
    assert "accumulate" in low and "un-happen" in low


def test_the_rest_door_accepts_a_valid_claim(dna_dir):
    client = _rest_client(dna_dir)
    res = client.post(f"/v1/memories?scope={_SCOPE}", json={
        "summary": "O Kind Livro ainda precisa de aprovação.",
        "area": _LIVRO,
        "claims": [{"predicate": "approval", "object": "pending"}],
    })
    assert res.status_code == 201, res.text
    assert res.json()["kind"] == "Engram"
