"""The agent authors; the agent does NOT approve.

The conversational face of tenant Kind authoring. A tenant talks to an agent
over MCP (Claude Desktop, Cursor, the console copilot) and the agent writes the
``KindDefinition`` — the same document the portal and the REST face write,
through the same core (``dna.application.kind_authoring``). A Kind born in one
face and absent from the others is worth nothing, so this is not a convenience
surface: it is one of the three doors the feature is defined by.

What is deliberately ABSENT is the load-bearing part. There is **no approval
tool**, and there must never be one: approval is what confers effect (the
registry withholds registration until ``spec.approved_by`` names someone), so a
tool that approved would let the agent approve its own proposal and the gate
this whole branch exists to make mechanical would be decorative. The second
test below is a *negative* assertion over the whole advertised tool surface, not
over a name we happen to remember — an ``approve_kind`` added anywhere on this
server fails it (verified by adding one; see the task report).

The other three properties each pin something that would silently rot:

* the PROPOSER is server-resolved. ``proposed_by`` is stamped from the verified
  identity of the request (``actor_from_context``), and there is no tool
  argument that can reach it — asserted twice, once on the tool's advertised
  input schema and once on the STORED document after a call that tries.
* a bad Kind name refuses LEGIBLY. ``kind`` is the one caller-controlled value
  that becomes a path component, so it is validated as a CamelCase identifier;
  over a conversational face an illegible refusal is a refusal the agent retries
  forever, so the message has to reach the client intact.
* ``list_my_kinds`` reads through ``list_authored_kinds_impl`` — the same audit
  projection the portal renders, not a second shape for the same data.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastmcp")

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
#: The workspace the fixture's client speaks for. Same shape as the REST
#: authoring test's, because it is the same door with a different transport.
_WID = "ws-mcpauthoring0000000000001"

_SCHEMA = {"type": "object", "properties": {"titulo": {"type": "string"}}}


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope, with the ``_lib`` registry scope
    that :func:`~dna.application.namespace_assignment.assign_namespace` reads
    before it mints. Mirrors ``test_kind_authoring_route.py``'s fixture — the
    example scope ships no ``_lib`` and a filesystem source raises for a scope
    directory that is not there."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    lib = dst / "_lib"
    lib.mkdir(parents=True, exist_ok=True)
    (lib / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        "metadata:\n  name: _lib\n"
        "spec: {}\n"
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    # The proposer test asserts the server-resolved actor for an unauthenticated
    # caller. `actor_from_context` honours DNA_PERSONAL_ID on that path, so an
    # operator's own env var would otherwise decide whether the test passes.
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    return dst


class _Face:
    """A client on the DNA MCP face, bound to one workspace + scope.

    The binding lives here rather than in every call because over a real
    transport it is not an argument at all: an authenticated door resolves the
    workspace from the token and the tool never sees a ``tenant``. Binding it in
    the fixture keeps the test bodies about the thing under test.

    Sync methods over ``asyncio.run``, matching the rest of this suite — the
    ``packages/cli`` venv carries no ``pytest-asyncio``.
    """

    def __init__(self, dna_dir: pathlib.Path) -> None:
        from dna_cli import _mcp_server as M

        self._server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
        # Only the workspace. NOT the scope: ``author_kind`` deliberately takes
        # none (the Kind lands at the base of the scope the workspace owns, which
        # the core derives), and binding one here would hide that.
        self._bound = {"tenant": _WID}

    def call_tool(self, name: str, args: dict) -> dict:
        """Call ``name`` and return its structured result."""
        from fastmcp import Client

        async def go():
            async with Client(self._server) as client:
                return await client.call_tool(name, {**self._bound, **args})

        return asyncio.run(go()).structured_content

    def call_tool_raw(self, name: str, args: dict) -> dict:
        """Call ``name`` with EXACTLY ``args`` — nothing bound, nothing added.

        The proposer test needs this: it sends a forged ``proposed_by`` and the
        point is that nothing between the client and the tool tidied the payload.
        """
        from fastmcp import Client

        async def go():
            async with Client(self._server) as client:
                return await client.call_tool(name, args)

        return asyncio.run(go()).structured_content

    def list_tools(self) -> list:
        from fastmcp import Client

        async def go():
            async with Client(self._server) as client:
                return await client.list_tools()

        return asyncio.run(go())

    def stored_spec(self, name: str) -> dict:
        """The spec of an authored document, read back from the STORE.

        Through a kernel booted FRESH over the same directory: what the tool
        returned in its response is not evidence about what was persisted."""
        from dna_cli import _mcp_server as M

        async def go():
            live = await M.boot_live(base_dir=str(self._dna_dir))
            raw = await live.kernel.get_document(_SCOPE, "KindDefinition", name)
            return dict((raw or {}).get("spec") or {})

        return asyncio.run(go())


@pytest.fixture
def mcp_client(dna_dir):
    face = _Face(dna_dir)
    face._dna_dir = dna_dir
    return face


# ── the two properties the brief names ──────────────────────────────────────


def test_the_agent_can_author(mcp_client):
    r = mcp_client.call_tool("author_kind", {
        "kind": "Contrato",
        "schema": {"type": "object", "properties": {"titulo": {"type": "string"}}},
    })
    assert r["approved"] is False


def test_there_is_no_approval_tool(mcp_client):
    names = {t.name for t in mcp_client.list_tools()}
    assert not any("approve" in n for n in names), (
        "approval is the human act — exposing it as a tool would let "
        "the agent approve its own proposal, which is the whole point of the gate"
    )


# ── the proposer is the SERVER's, never the caller's ────────────────────────


def test_the_tool_advertises_no_way_to_name_the_proposer(mcp_client):
    """The first half of the proof, on the DECLARATION.

    An agent reads the input schema to decide what to send. If ``proposed_by`` /
    ``approved_by`` / a timestamp appeared there, a caller naming itself would be
    the documented interface — and the core's field-by-field build (which drops
    them) would be a silent contradiction of the tool's own contract rather than
    a guard. So the absence is asserted where an agent would look."""
    tool = next(t for t in mcp_client.list_tools() if t.name == "author_kind")
    properties = set((tool.inputSchema or {}).get("properties") or {})
    assert not properties & {
        "proposed_by", "proposed_at", "approved_by", "approved_at", "actor",
    }, properties


def test_a_forged_proposer_reaches_nothing(mcp_client):
    """The second half, on the WIRE and then on the STORED document.

    MEASURED, and it is stronger than "the value is dropped": a call carrying
    ``proposed_by`` never reaches the tool at all — FastMCP validates arguments
    against the declared signature and refuses the unexpected keyword. So the
    forgery fails at the transport, one layer above the core's field-by-field
    build, and the two guards are independent.

    Then the honest call, checked on what was PERSISTED — a response body can be
    right about a document that is wrong. The stored proposer is the face's
    server-resolved actor (``actor_from_context``); with no token and no
    ``DNA_PERSONAL_ID`` that is the unidentified-local marker, which is still an
    identity the server chose and not one the caller supplied."""
    from dna_cli._mcp_auth import UNIDENTIFIED_LOCAL_ACTOR

    for forged in ("proposed_by", "approved_by", "proposed_at", "approved_at"):
        with pytest.raises(Exception) as ei:  # noqa: PT011 — FastMCP ToolError
            mcp_client.call_tool_raw("author_kind", {
                "tenant": _WID, "kind": "Forjado", "schema": _SCHEMA,
                forged: "attacker@example.com",
            })
        assert "Unexpected keyword argument" in str(ei.value), (forged, ei.value)

    out = mcp_client.call_tool("author_kind", {
        "kind": "Forjado", "schema": _SCHEMA})
    spec = mcp_client.stored_spec(out["name"])
    assert spec["proposed_by"] == UNIDENTIFIED_LOCAL_ACTOR, spec
    # …and the approval half is not merely different — it is ABSENT. The
    # registry's gate reads this key; a value here would confer effect.
    assert not spec.get("approved_by"), spec


# ── a bad Kind name refuses LEGIBLY ─────────────────────────────────────────


def test_a_traversing_kind_name_is_refused_in_words_the_agent_can_read(mcp_client):
    """``kind`` becomes a path component, so it is validated as a CamelCase
    identifier. Over a conversational face the refusal has to arrive as a
    sentence: an agent that gets an opaque failure retries the same call."""
    with pytest.raises(Exception) as ei:  # noqa: PT011 — FastMCP ToolError
        mcp_client.call_tool("author_kind", {
            "kind": "../../../etc/pwned", "schema": _SCHEMA,
        })
    message = str(ei.value)
    assert "CamelCase" in message, message
    assert "../../../etc/pwned" in message, message


# ── list_my_kinds is the audit projection, not a second shape ───────────────


def test_list_my_kinds_shows_the_proposal_and_its_approval_state(mcp_client):
    mcp_client.call_tool("author_kind", {"kind": "Contrato", "schema": _SCHEMA})
    listed = mcp_client.call_tool("list_my_kinds", {"scope": _SCOPE})
    rows = [k for k in listed["kinds"] if k["kind"] == "Contrato"]
    assert rows, listed
    row = rows[0]
    assert row["approved"] is False
    # The audit fields `list_authored_kinds_impl` projects — reused, not
    # re-invented. A tool that shaped its own rows would drift from the portal's.
    assert set(row) == {
        "name", "kind", "api_version", "namespace", "approved",
        "proposed_by", "proposed_at", "approved_by", "approved_at", "created_at",
    }, sorted(row)
