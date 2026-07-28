"""The agent authors; the agent does NOT approve — the MODEL does not, at least.

The conversational face of tenant Kind authoring. A tenant talks to an agent
over MCP (Claude Desktop, Cursor, the console copilot) and the agent writes the
``KindDefinition`` — the same document the portal and the REST face write,
through the same core (``dna.application.kind_authoring``). A Kind born in one
face and absent from the others is worth nothing, so this is not a convenience
surface: it is one of the three doors the feature is defined by.

**The load-bearing property changed shape, and it did not weaken.** There used
to be no approval tool here at all, asserted twice. There is one now — a
workspace has more than one person, and the approver wants to answer "what is
there to approve?" where she already is. What the two guards below pin is what
they were always FOR: *the model cannot approve*. Absence was one way to buy
that; declaration is the way it is bought now, and both guards were re-aimed at
the property rather than at the old mechanism:

* over the tool list AS A MODEL SEES IT — ``approve_kind`` is registered
  ``visibility: ["app"]`` (MCP Apps, SEP-1865), and a conforming host must not
  put a tool omitting ``"model"`` in the list it hands the model. The re-aimed
  test reads the advertised list and applies that same rule, so the tool may
  exist and must be absent from the model's half. It still discriminates on the
  substring ``"approve"`` — ``grant_approval`` / ``ratify_kind`` / ``bless_kind``
  would sail past a rule written as a spelling — which is why the second guard
  is not a copy of it.
* over the CAPABILITY, and now MEASURED rather than scanned. Every tool the
  model can see is driven with the argument that could name a Kind, against a
  live spy on ``approve_kind_impl`` — the only function that writes
  ``spec.approved_by``. None may reach it, whatever it is called; and the spy is
  proven live by the app-only tool reaching it in the same test, so the guard
  cannot pass because nothing was wired.

**Whose fence the first one is.** Not ours. The MCP Apps spec says a server
cannot distinguish a UI-initiated ``tools/call`` from a model-initiated one, so
``visibility`` is a declaration a HOST enforces and no test here can prove a
third party honours it. What made that residual acceptable is that revocation
exists (i-085): the act is undoable in one step. What is ours we do, and it is
pinned below — the declaration is exact, and a client that tells us it cannot
render MCP Apps is not offered the tool at all rather than being handed it with
the marker stripped off.

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
import contextlib
import pathlib
import shutil

import pytest

pytest.importorskip("fastmcp")

#: The face's own refusal type. Asserting on it rather than on ``Exception``
#: matters: a bare ``pytest.raises(Exception)`` also passes on a ``TypeError``
#: from a typo'd call, so the test would go on "passing" while never reaching
#: the refusal it claims to pin.
from fastmcp.exceptions import ToolError  # noqa: E402 — after the importorskip

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_DNA_CLI = pathlib.Path(__file__).resolve().parents[1] / "dna_cli"
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
#: The workspace the fixture's client speaks for. Same shape as the REST
#: authoring test's, because it is the same door with a different transport.
_WID = "ws-mcpauthoring0000000000001"

_SCHEMA = {"type": "object", "properties": {"titulo": {"type": "string"}}}


@contextlib.contextmanager
def _ui_capable_client(declared: bool):
    """Make the in-memory client announce (or not) the MCP Apps extension, the
    way a UI-capable host does on the wire.

    The client SDK hard-codes its ``ClientCapabilities`` with no seam for an
    extension, so the model class is swapped for the duration. It matters here
    and not only in the card suite: the server strips the whole ``ui`` meta
    block for a client that declared it cannot render, and ``visibility`` lives
    inside that block — so "what does the tool list look like" has two different
    honest answers and the tests have to ask for the one they mean."""
    import mcp.types as mt

    original = mt.ClientCapabilities
    if not declared:
        yield
        return

    def with_ui(**kwargs):
        from dna_cli._mcp_server import MCP_APP_MIME, UI_EXTENSION_ID

        return original(
            **kwargs, extensions={UI_EXTENSION_ID: {"mimeTypes": [MCP_APP_MIME]}},
        )

    mt.ClientCapabilities = with_ui
    try:
        yield
    finally:
        mt.ClientCapabilities = original


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

        # Assigned HERE, not bolted on by the fixture from outside. `stored_spec`
        # reads it, so a `_Face(dna_dir)` built anywhere else used to raise
        # AttributeError on an attribute `__init__` never set — the class was
        # only whole by accident of one fixture.
        self._dna_dir = dna_dir
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

    def list_tools(self, *, ui: bool = True) -> list:
        """The tools this server ADVERTISES.

        ``ui=True`` by default because that is the host the feature is for: one
        that renders MCP Apps, and therefore the one that receives the
        ``visibility`` declaration at all. ``ui=False`` asks the other question
        — what a host that told us it cannot render is offered."""
        from fastmcp import Client

        async def go():
            async with Client(self._server) as client:
                return await client.list_tools()

        with _ui_capable_client(ui):
            return asyncio.run(go())

    def model_tools(self) -> list:
        """The tool list AS A MODEL WOULD SEE IT — the advertised list with the
        MCP Apps visibility rule applied, which is the host's job and therefore
        not something the server's own registry can answer.

        Read through ``_mcp_server.app_only``, the predicate the server itself
        filters with, rather than a second reading of ``_meta.ui.visibility``
        written here: two spellings of this rule would be two answers to the one
        question that keeps approval away from the model."""
        from dna_cli._mcp_server import app_only

        return [t for t in self.list_tools() if not app_only(t)]

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
    return _Face(dna_dir)


# ── the two properties the brief names ──────────────────────────────────────


def test_the_agent_can_author(mcp_client):
    r = mcp_client.call_tool("author_kind", {
        "kind": "Contrato",
        "schema": {"type": "object", "properties": {"titulo": {"type": "string"}}},
    })
    assert r["approved"] is False


def test_the_model_is_not_offered_the_approval_tool(mcp_client):
    """RE-AIMED (was ``test_there_is_no_approval_tool``). The property was never
    "no such tool exists" — it was **the model cannot approve**. The tool exists
    now, and it must be absent from the list a model is given.

    Read the way a model would see it: the advertised list with the MCP Apps
    visibility rule applied. ``visibility: ["app"]`` omits ``"model"``, and the
    spec says a host MUST NOT include such a tool in the model's tool list. That
    is the host's enforcement, not ours (a server cannot tell a UI-initiated
    call from a model-initiated one), so what is testable HERE is that the
    declaration is exact — and it is exactly what an incomplete host would need
    in order to do the right thing.

    Both halves are asserted, because either alone passes for the wrong reason:
    the tool must be REGISTERED and app-only (a missing tool would make the
    first assertion vacuously true), and no ``approve``-ish name may survive
    into the model's half. Drop ``visibility`` — or widen it to
    ``["model","app"]`` — and this dies."""
    from dna_cli._mcp_cards import APPROVE_TOOL
    from dna_cli._mcp_server import app_only

    advertised = {t.name: t for t in mcp_client.list_tools()}
    assert APPROVE_TOOL in advertised, (
        "the approval tool is not registered at all — this guard would then be "
        "passing on an absence rather than on a declaration"
    )
    assert app_only(advertised[APPROVE_TOOL]), (
        f"{APPROVE_TOOL} does not declare visibility omitting 'model' — a host "
        f"would put it straight in the model's tool list: "
        f"{(advertised[APPROVE_TOOL].meta or {}).get('ui')}"
    )

    model_names = {t.name for t in mcp_client.model_tools()}
    assert not any("approve" in n for n in model_names), (
        "approval reached the model's tool list — the agent can approve its own "
        f"proposal, which is the whole point of the gate: {sorted(model_names)}"
    )


def test_a_host_that_cannot_render_is_not_handed_the_approval_tool(mcp_client):
    """The hole the ``ui`` stripping used to open, closed.

    A client that declares it cannot render MCP Apps has the whole ``ui`` meta
    block removed from its listing — that is deliberate, it is how the card
    pointer is withheld. But ``visibility`` lives INSIDE that block, so an
    app-only tool handed to such a client would arrive wearing no marker at all:
    an approval tool, indistinguishable from ``author_kind``, in the model's
    list. The tool is therefore withheld ENTIRELY from that client, which costs
    nothing — a host that cannot render has no button to press it with."""
    from dna_cli._mcp_cards import APPROVE_TOOL

    blind = {t.name: t for t in mcp_client.list_tools(ui=False)}
    assert APPROVE_TOOL not in blind, (
        f"{APPROVE_TOOL} was offered to a client that cannot render it — and "
        f"with its ui meta stripped, so nothing marks it as app-only: "
        f"{(blind[APPROVE_TOOL].meta or {})}"
    )
    # The rest of the surface is untouched: this withholds the app-only tool,
    # not the face.
    assert {"author_kind", "list_my_kinds", "review_kind"} <= set(blind), sorted(blind)


#: The modules the MCP face is BUILT from — ``build_server`` and everything it
#: registers tools from. Deliberately NOT all of ``dna_cli``: ``_rest_api.py``
#: imports ``approve_kind_impl`` **on purpose**, because
#: ``POST /v1/kinds/{kind}/approve``, reached with a reviewer's own credential,
#: IS the human act this whole design routes approval through. A guard that
#: forbade the import package-wide would be red on an untouched tree, and the
#: obvious way to "fix" it would be to delete the approval route itself.
_MCP_FACE = sorted(
    [
        *_DNA_CLI.glob("_mcp_*.py"),
        *(_DNA_CLI / "graph").rglob("*.py"),
        *(_DNA_CLI / "act_on_behalf").rglob("*.py"),
    ]
)

#: The ONE module of the MCP face allowed to reach ``approve_kind_impl`` — the
#: one that registers the app-only tool. Everything else reaching it would be a
#: second, unreviewed path to the act.
_APPROVAL_MODULE = "_mcp_kinds.py"


def test_no_tool_the_model_can_see_reaches_the_approval_capability(mcp_client, monkeypatch):
    """RE-AIMED (was ``test_the_mcp_face_cannot_reach_the_approval_capability``),
    and this is the guard a careless edit reopens the hole through: the old form
    said the MCP face must not IMPORT ``approve_kind_impl``, that import now
    exists on purpose, and deleting the test is easy and looks harmless.

    Why it cannot just be the sibling above: that one discriminates on the
    substring ``"approve"``, and ``grant_approval`` / ``ratify_kind`` /
    ``confer_effect`` / ``bless_kind`` all sail through it (``"approval"`` does
    not even contain ``"approve"``). Renaming is not an exotic risk; it is the
    ordinary way a rule expressed as a string decays.

    So the rule is pinned on the CAPABILITY, and MEASURED rather than scanned.
    ``approve_kind_impl`` is the only function that writes ``spec.approved_by``,
    and the registry withholds registration until that key names someone — so
    nothing can confer effect without going through it, under any name. Every
    tool the MODEL can see is driven with the one argument that could name a
    Kind, against a live spy on that function. None may reach it.

    Two things stop this passing for the wrong reason:

    * the spy is proven LIVE in the same test — the app-only tool reaches it, so
      a guard that passed because nothing was wired fails here instead;
    * the source half is kept, narrowed to an ALLOW-list of one module, so a
      second path to the act (a module that imports it and registers something
      the loop below cannot call with a bare ``kind``) is still caught.

    Widen the approval tool's visibility to ``["model", "app"]``, or drop the
    declaration (which defaults to both), and the loop calls it and this dies.
    """
    import dna_cli._mcp_kinds as K
    from dna_cli._mcp_cards import APPROVE_TOOL

    reached: list[str] = []
    real = K.approve_kind_impl

    async def spy(*args, **kwargs):
        reached.append(str(kwargs.get("kind")))
        return await real(*args, **kwargs)

    monkeypatch.setattr(K, "approve_kind_impl", spy)

    mcp_client.call_tool("author_kind", {"kind": "Contrato", "schema": _SCHEMA})

    driven = []
    for tool in mcp_client.model_tools():
        properties = set((tool.inputSchema or {}).get("properties") or {})
        if "kind" not in properties:
            continue  # nothing this tool could be pointed at a Kind with.
        args = {"kind": "Contrato"}
        if "schema" in properties:
            args["schema"] = _SCHEMA
        driven.append(tool.name)
        with contextlib.suppress(ToolError):
            mcp_client.call_tool(tool.name, args)

    assert driven, (
        "no model-visible tool takes a `kind` at all — the loop proved nothing"
    )
    assert not reached, (
        f"a tool the model can see conferred effect: {driven} reached "
        f"approve_kind_impl for {reached}. Whatever it is named, it can now "
        f"approve its own proposal."
    )

    # …and the spy is LIVE. Without this the test would pass just as happily on
    # a monkeypatch that never took.
    mcp_client.call_tool(APPROVE_TOOL, {"kind": "Contrato"})
    assert reached == ["Contrato"], (
        "the app-only tool did not reach the capability — the spy above was "
        "watching nothing, so its silence meant nothing"
    )

    # The source half, narrowed rather than deleted: exactly one module of the
    # face may reach the act, and it is the one that declares the tool app-only.
    assert _MCP_FACE, "found no MCP face modules — did the package layout change?"
    reachers = sorted(
        p.name for p in _MCP_FACE
        if "approve_kind_impl" in p.read_text(encoding="utf-8")
    )
    assert reachers == [_APPROVAL_MODULE], (
        "a second module of the MCP face reaches approve_kind_impl — there is "
        f"now more than one path to the act: {reachers}"
    )


# ── what the button actually does ───────────────────────────────────────────


def test_the_two_acts_name_two_people(mcp_client, monkeypatch):
    """The scenario the whole feature is for, end to end on one face.

    A workspace has more than one person. Ana's agent authors the Kind; Bea is
    the approver, and she presses the button in her own client, on her own
    connection. So ``proposed_by`` is Ana and ``approved_by`` is Bea — two
    distinct VERIFIED actors, which is exactly what the audit wanted and what
    the old objection ("the agent would approve its own proposal") was really
    about. Neither name came from an argument.

    Both identities are resolved by ``actor_from_context``; on this local lane
    it reads ``DNA_PERSONAL_ID``, which is the same seam a token's ``email``
    claim occupies over an authenticated door. Swapping it between the two calls
    is what makes them two people rather than one caller twice."""
    monkeypatch.setenv("DNA_PERSONAL_ID", "ana@example.com")
    mcp_client.call_tool("author_kind", {"kind": "Contrato", "schema": _SCHEMA})

    monkeypatch.setenv("DNA_PERSONAL_ID", "bea@example.com")
    out = mcp_client.call_tool("approve_kind", {"kind": "Contrato"})
    assert out["approved"] is True, out

    spec = mcp_client.stored_spec(out["name"])
    assert spec["proposed_by"] == "ana@example.com", spec
    assert spec["approved_by"] == "bea@example.com", spec
    assert spec["proposed_at"] and spec["approved_at"], spec


def test_the_approver_cannot_be_named_by_the_caller(mcp_client):
    """The same rule the proposer has, on the act that actually confers effect —
    where it matters most. An ``approved_by`` in the call is refused by the
    transport before the tool runs, exactly as a forged ``proposed_by`` is."""
    mcp_client.call_tool("author_kind", {"kind": "Contrato", "schema": _SCHEMA})

    tool = next(t for t in mcp_client.list_tools() if t.name == "approve_kind")
    properties = set((tool.inputSchema or {}).get("properties") or {})
    assert not properties & {
        "approved_by", "approved_at", "actor", "proposed_by",
    }, properties

    with pytest.raises(ToolError) as ei:
        mcp_client.call_tool_raw("approve_kind", {
            "tenant": _WID, "kind": "Contrato", "approved_by": "attacker@example.com",
        })
    assert "Unexpected keyword argument" in str(ei.value), ei.value


def test_approving_a_revoked_kind_restores_it(mcp_client):
    """Revocation is what made shipping the button acceptable, so the undo is
    pinned on this face and not only on the REST one: approving clears the
    revocation markers, and ``review_kind`` reports the Kind in effect again."""
    from dna.application.kind_authoring import revoke_kind_impl
    from dna.application.sdlc import now_iso
    from dna_cli import _mcp_server as M

    out = mcp_client.call_tool("author_kind", {"kind": "Contrato", "schema": _SCHEMA})
    mcp_client.call_tool("approve_kind", {"kind": "Contrato"})

    async def revoke():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(mcp_client._dna_dir))
        return await revoke_kind_impl(
            live, kind="Contrato", tenant=_WID, actor="ana@example.com",
            now=now_iso(),
        )

    asyncio.run(revoke())
    assert mcp_client.stored_spec(out["name"])["revoked_by"] == "ana@example.com"

    reviewed = mcp_client.call_tool("review_kind", {"kind": "Contrato"})
    assert reviewed["declaration"]["state"] == "revoked", reviewed

    mcp_client.call_tool("approve_kind", {"kind": "Contrato"})
    spec = mcp_client.stored_spec(out["name"])
    assert "revoked_by" not in spec and "revoked_at" not in spec, spec
    reviewed = mcp_client.call_tool("review_kind", {"kind": "Contrato"})
    assert reviewed["declaration"]["state"] == "approved", reviewed


def test_review_kind_shows_the_schema_the_approval_would_confer_effect_on(mcp_client):
    """Approving what you cannot see is not approving — the hole the portal
    closed (i-076) and the reason the button does not live on the roster.

    ``list_my_kinds`` projects thirteen summary fields and deliberately not the
    schema; ``review_kind`` is the route that answers "what would this Kind
    actually validate", which is the question the decision is about."""
    mcp_client.call_tool("author_kind", {"kind": "Contrato", "schema": _SCHEMA})

    listed = mcp_client.call_tool("list_my_kinds", {"scope": _SCOPE})
    row = next(k for k in listed["kinds"] if k["kind"] == "Contrato")
    assert "schema" not in row, "the roster grew a schema column — it is a roster"

    reviewed = mcp_client.call_tool("review_kind", {"kind": "Contrato"})
    declaration = reviewed["declaration"]
    assert declaration["schema"] == _SCHEMA, declaration
    # The SAME projection the roster publishes, plus the schema — not a second
    # shape for one document.
    assert set(row) <= set(declaration), (sorted(row), sorted(declaration))
    for field in row:
        assert declaration[field] == row[field], field


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
        with pytest.raises(ToolError) as ei:
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
    with pytest.raises(ToolError) as ei:
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
    # `state` says WHICH not-approved this is (i-085). The boolean cannot carry
    # three values, and the two it collapses behave in OPPOSITE ways: a Kind
    # that was never approved accepts documents unvalidated, a REVOKED one
    # refuses them and marks every existing document invalid.
    assert row["state"] == "unapproved"
    # The audit fields `list_authored_kinds_impl` projects — reused, not
    # re-invented. A tool that shaped its own rows would drift from the portal's.
    assert set(row) == {
        "name", "kind", "api_version", "namespace", "approved", "state",
        "proposed_by", "proposed_at", "approved_by", "approved_at",
        "revoked_by", "revoked_at", "created_at",
    }, sorted(row)


# ── an unreadable claim registry refuses in words, not as a bare failure ────


def test_an_unreadable_registry_refuses_the_listing_in_words(
    mcp_client, monkeypatch,
):
    """The MCP twin of the REST doors' 503 — the parity this module's docstring
    already claims.

    ``list_my_kinds`` filters to what the caller owns, and ownership comes from
    the ``KindNamespace`` claim registry. When that read fails the core refuses
    with :class:`~dna.application.kind_authoring.NamespaceRegistryUnreadable`
    rather than degrading to the unfiltered roster — right, and pinned on the
    REST side already.

    What was NOT pinned is the last hop. ``NamespaceRegistryUnreadable`` is a
    ``RuntimeError``, so it is outside ``AUTHORING_REFUSALS`` (deliberately: a
    genuine bug must keep looking like a bug) AND outside the
    ``FileNotFoundError`` branch that exists for exactly this condition. It
    therefore escaped BOTH handlers and reached the agent as FastMCP's masked
    "Error calling tool" — an unexplained failure, which over a conversational
    face is the input to a retry loop, not to a fix. REST answers the same
    condition with a sentence naming the missing precondition; this asserts the
    sentence arrives here too.

    Injected at the seam (``kind_namespaces`` raising something that is NOT a
    missing file) because on a filesystem store the honest ``FileNotFoundError``
    hides the gap that only a networked registry shows — the same injection the
    REST tests use, for the same reason.
    """
    from dna.kernel import Kernel

    mcp_client.call_tool("author_kind", {"kind": "Contrato", "schema": _SCHEMA})

    async def boom(self, *a, **kw):
        raise RuntimeError("connection reset by peer")

    monkeypatch.setattr(Kernel, "kind_namespaces", boom, raising=True)

    with pytest.raises(ToolError) as ei:
        mcp_client.call_tool("list_my_kinds", {"scope": _SCOPE})
    message = str(ei.value)
    # Actionable: WHAT is missing, WHO can fix it, and the underlying cause.
    assert "registry" in message.lower(), message
    assert "operator" in message.lower(), message
    assert "connection reset by peer" in message, message
