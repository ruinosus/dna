"""The PORTFOLIO door at the MCP face — and the bridge from a project to its board.

The Kinds (``Project`` / ``Organization`` / ``Repo``) were always registered and
always reachable through the generic instance door; the application seams were
already written and already served REST. What was missing was a NAME, and a
catalog of 78 Kinds with no named tool is discoverable only by luck.

So these tests do NOT re-prove the seams. They prove the three things the door
itself is responsible for:

1. **the tools are offered** — the six names reach a client's ``tools/list``;
2. **THE BRIDGE** — a project's ``board_scope`` really is the scope that
   ``board_summary`` reads. This is the whole reason ``list_projects`` exists:
   without it a caller holds a roster and a board tool and nothing joins them,
   which is exactly how someone reports "I cannot find the boards" about a
   system that has served them all along. Proven end-to-end through the REAL
   protocol: read the roster, take the field, call the board tool with it, and
   see THAT project's item;
3. **identity and scope are not caller inputs on the write** — ``create_project``
   exposes neither ``claims`` nor ``scope``. A ``claims`` argument would be a
   caller-supplied identity, which is not an identity; a caller-chosen scope
   would be a way to write into another workspace. Both are asserted against
   the tool's PUBLISHED schema, which is what a caller can actually reach.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import shutil

import pytest

pytest.importorskip("fastmcp", reason="the MCP runtime face needs the optional 'fastmcp' extra")

from dna_cli import _mcp_server as M  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"

#: The board scope this project declares. Deliberately NOT the conventional
#: ``<slug>-development``: if the bridge silently rebuilt the scope from the
#: slug instead of READING ``board_scope``, a conventional value would let the
#: bug pass. An unconventional one makes the two paths disagree.
_BOARD_SCOPE = "atlas-board-not-the-convention"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope carrying one Project and, in that
    project's declared board scope, one Story to find."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)

    projects = dst / _SCOPE / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    (projects / "atlas.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/portfolio/v1\n"
        "kind: Project\n"
        "metadata:\n"
        "  name: atlas\n"
        "spec:\n"
        "  slug: atlas\n"
        "  workspace_id: ws-test\n"
        f"  board_scope: {_BOARD_SCOPE}\n"
        "  repo_refs: []\n"
        "  visibility: private\n",
        encoding="utf-8",
    )

    stories = dst / _BOARD_SCOPE / "stories"
    stories.mkdir(parents=True, exist_ok=True)
    (stories / "s-only-on-the-project-board.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/sdlc/v1\n"
        "kind: Story\n"
        "metadata:\n"
        "  name: s-only-on-the-project-board\n"
        "spec:\n"
        "  title: only reachable through the project's board_scope\n"
        "  status: todo\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _payload(result):
    """The tool's data, whichever channel carried it."""
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


def _run(dna_dir, body):
    from fastmcp import Client

    async def go():
        server = M.build_server(base_dir=str(dna_dir))
        async with Client(server) as client:
            return await body(client)

    return asyncio.run(go())


# ── 1. the door is open ────────────────────────────────────────────────────


def test_the_portfolio_tools_are_offered(dna_dir):
    """The six names reach a real client's ``tools/list``. Drop the
    ``register_portfolio_tools`` call and this dies."""
    names = _run(dna_dir, lambda c: c.list_tools())
    offered = {t.name for t in names}
    assert {
        "list_workspaces", "list_projects", "get_project",
        "create_project", "list_repos", "list_orgs",
    } <= offered


# ── 2. THE BRIDGE: board_scope is the board ────────────────────────────────


def test_list_projects_carries_the_board_scope(dna_dir):
    """The roster reports the field that unlocks the board. Remove
    ``board_scope`` from the projected surface and this dies."""
    async def body(client):
        return _payload(await client.call_tool("list_projects", {"scope": _SCOPE}))

    data = _run(dna_dir, body)
    atlas = next(p for p in data["projects"] if p["slug"] == "atlas")
    assert atlas["board_scope"] == _BOARD_SCOPE


def test_the_board_scope_from_the_roster_really_reads_that_board(dna_dir):
    """THE claim this module exists for, proven end-to-end over the real
    protocol: take ``board_scope`` from ``list_projects`` — never a literal —
    hand it to ``board_summary``, and the project's own story is there.

    The board scope is deliberately NOT the conventional ``<slug>-development``,
    so a bridge that rebuilt the scope from the slug instead of reading the
    field would look at an empty scope and this would die."""
    async def body(client):
        roster = _payload(await client.call_tool("list_projects", {"scope": _SCOPE}))
        atlas = next(p for p in roster["projects"] if p["slug"] == "atlas")
        board = _payload(
            await client.call_tool("board_summary", {"scope": atlas["board_scope"]})
        )
        return atlas, board

    atlas, board = _run(dna_dir, body)
    assert atlas["board_scope"] == _BOARD_SCOPE
    assert json.dumps(board).find("s-only-on-the-project-board") != -1, (
        "the project's board_scope did not read the project's board: "
        f"{json.dumps(board)[:400]}"
    )


def test_the_tool_description_tells_the_model_about_the_bridge(dna_dir):
    """The bridge is only useful if the model LEARNS it without being told
    separately — the sentence lives in the published description, which is what
    a client actually reads. Strip it from the docstring and this dies.

    Not decoration: a roster and a board tool that never mention each other are
    two halves nothing joins, and the model is left to guess the join."""
    tools = {t.name: t for t in _run(dna_dir, lambda c: c.list_tools())}
    description = tools["list_projects"].description or ""
    assert "board_scope" in description
    assert "board_summary" in description


# ── 3. the write takes neither identity nor scope ──────────────────────────


@pytest.mark.parametrize("forbidden", ["claims", "scope"])
def test_create_project_does_not_expose_identity_or_scope(dna_dir, forbidden):
    """Asserted against the PUBLISHED schema — what a caller can actually
    reach — not against the Python signature.

    ``claims``: a caller-supplied identity is not an identity. It is read
    server-side from the verified token.
    ``scope``: the write scope and ``board_scope`` are DERIVED from
    (workspace, slug). A caller-chosen scope is a cross-workspace write vector.

    Add either parameter to the tool and this dies."""
    tools = {t.name: t for t in _run(dna_dir, lambda c: c.list_tools())}
    properties = (tools["create_project"].inputSchema or {}).get("properties") or {}
    assert forbidden not in properties, (
        f"create_project publishes {forbidden!r}: {sorted(properties)}"
    )
    # …and the parameters it DOES take are the intended three.
    assert set(properties) == {"workspace_id", "name", "slug"}


# ── 4. a refusal reaches the agent NAMED (the regression that shipped) ─────


class _MembershipRefusal(Exception):
    """Shaped like the real ``WorkspaceForbidden``: a bare ``Exception``.

    That is the whole point. The first version of this door enumerated
    ``(ValueError, LookupError, PermissionError)`` on a comment asserting
    ``WorkspaceForbidden`` was a ``PermissionError``. It is not — and the most
    likely refusal the door can produce escaped unmapped."""


def test_a_refusal_that_is_not_in_any_enumeration_still_arrives_named(
    dna_dir, monkeypatch,
):
    """Measured against production: ``create_project`` refused a caller with no
    membership and the agent read ``Error calling tool 'create_project'`` — no
    type, no reason, nothing to act on. Same defect as ``i-088``…``i-092``.

    Restore the enumeration and this dies, because ``_MembershipRefusal``
    subclasses neither ``ValueError``, ``LookupError`` nor ``PermissionError``
    — exactly like the real one."""
    from dna.application import runtime

    async def refuse(*a, **k):
        raise _MembershipRefusal(
            "identity '<anonymous>' holds no active WorkspaceMembership"
        )

    monkeypatch.setattr(runtime, "create_project_impl", refuse)

    async def body(client):
        try:
            await client.call_tool(
                "create_project", {"workspace_id": "ws-x", "name": "Atlas"},
            )
        except Exception as exc:  # noqa: BLE001 — the message IS the assertion
            return str(exc)
        return ""

    message = _run(dna_dir, body)
    assert "_MembershipRefusal" in message, (
        f"the refusal reached the agent unnamed: {message!r}"
    )
    assert "no active WorkspaceMembership" in message, (
        f"the reason did not survive: {message!r}"
    )


# ── 5. the diagnostic is audible ──────────────────────────────────────────


def test_our_own_loggers_are_configured_so_info_is_readable(monkeypatch):
    """``uvicorn.run(log_level="info")`` configures uvicorn's loggers and
    nothing else, so ``dna_cli``'s reach the root logger — which has no handler,
    so Python's handler of last resort emits WARNING and above ONLY.

    Every ``logger.info`` in the package was therefore dropped in production
    with no sign: no error, just a line that never appears. It was measured on
    the MCP Apps negotiation log, which recorded the answer to "did the host
    declare the extension?" and never once reached a reader.

    Drop the ``_configure_our_own_logging()`` call and this dies."""
    import logging

    from dna_cli import mcp_cmd

    ours = logging.getLogger("dna_cli")
    saved_handlers, saved_level, saved_propagate = (
        list(ours.handlers), ours.level, ours.propagate,
    )
    ours.handlers.clear()
    try:
        mcp_cmd._configure_our_own_logging()
        assert ours.handlers, "no handler — INFO would fall to the last resort"
        assert logging.getLogger("dna_cli._mcp_server").isEnabledFor(logging.INFO)
    finally:
        ours.handlers[:] = saved_handlers
        ours.setLevel(saved_level)
        ours.propagate = saved_propagate


def test_serve_actually_configures_logging_before_it_serves(dna_dir, monkeypatch):
    """The function being CORRECT is not the property that failed — the property
    that failed is that nobody called it.

    A first version of this test called ``_configure_our_own_logging()`` itself
    and then asserted the loggers were configured. It passed with the call
    REMOVED from ``serve``, which is the exact shape of the production bug it
    was meant to prevent: a diagnostic that is perfect and unreachable.

    So this drives the real command with ``uvicorn.run`` stubbed, and asserts
    the configuration happened by the time serving would have begun."""
    import logging

    from click.testing import CliRunner

    from dna_cli import mcp_cmd

    seen: dict[str, object] = {}

    def fake_run(app, **kwargs):
        ours = logging.getLogger("dna_cli")
        seen["handlers"] = list(ours.handlers)
        seen["info_enabled"] = logging.getLogger(
            "dna_cli._mcp_server"
        ).isEnabledFor(logging.INFO)

    # `uvicorn` is imported INSIDE serve(), so patch the module itself.
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", fake_run)

    ours = logging.getLogger("dna_cli")
    saved = (list(ours.handlers), ours.level, ours.propagate)
    ours.handlers.clear()
    try:
        result = CliRunner().invoke(
            mcp_cmd.mcp,
            ["serve", "--transport", "http", "--base-dir", str(dna_dir)],
        )
        assert result.exit_code == 0, result.output
        assert seen.get("handlers"), (
            "serve reached uvicorn.run with our loggers unconfigured — every "
            "logger.info in the package would be dropped, exactly as in prod"
        )
        assert seen.get("info_enabled") is True
    finally:
        ours.handlers[:] = saved[0]
        ours.setLevel(saved[1])
        ours.propagate = saved[2]


def test_the_log_level_is_overridable(monkeypatch):
    """An operator who wants less can say so. Hard-code the level and this
    dies."""
    import logging

    from dna_cli import mcp_cmd

    ours = logging.getLogger("dna_cli")
    saved_handlers, saved_level, saved_propagate = (
        list(ours.handlers), ours.level, ours.propagate,
    )
    try:
        monkeypatch.setenv("DNA_LOG_LEVEL", "WARNING")
        mcp_cmd._configure_our_own_logging()
        assert not logging.getLogger("dna_cli._mcp_server").isEnabledFor(logging.INFO)
    finally:
        ours.handlers[:] = saved_handlers
        ours.setLevel(saved_level)
        ours.propagate = saved_propagate


# ── 6. the two doors meter the same entity the same way ───────────────────


def test_the_portfolio_door_meters_the_family_the_kind_derives(dna_dir, monkeypatch):
    """The defect this pins, measured in production on the first battery.

    ``create_project`` refused with *"tier 'free' does not include the 'write'
    tool family"* while ``write_instance(kind="Project")`` — the SAME entity,
    the other door — succeeded. The generic door DERIVES the family from the
    Kind; this one NAMED ``"read"`` / ``"write"``, two strings no tier unlocks.
    Two doors disagreeing about one entity is not a policy.

    Driven through the module's real registration with the guard spied on, so
    what is asserted is the family the guard ACTUALLY receives. Hardcode a
    family string again and this dies."""
    from dna.application import instances as D

    from dna_cli import _mcp_portfolio as P

    class _Port:
        """Stands in for Project's registered port: the two fields
        ``family_for_kind`` reads, carrying Project's real apiVersion."""

        kind = "Project"
        api_version = "github.com/ruinosus/dna/portfolio/v1"

    monkeypatch.setattr(D, "resolve_kind_port", lambda *a, **k: _Port())

    seen: list[tuple[str, str]] = []

    async def spy_guard(family, tenant=None, *, scope=None, family_op="read"):
        seen.append((family, family_op))
        return tenant

    registered: dict[str, Any] = {}

    class _Server:
        def tool(self, **_kw):
            def deco(fn):
                registered[fn.__name__] = fn
                return fn

            return deco

    async def live():
        class _L:
            kernel = object()

        return _L()

    P.register_portfolio_tools(_Server(), live=live, guard=spy_guard)

    expected = D.family_for_kind(_Port())
    assert expected == "definitions", (
        f"the Kind → family mapping now says {expected!r}; the premise of this "
        "test moved and the door must move with it — which is the whole point"
    )

    # The guard runs BEFORE the impl, and the impl is not what this test
    # claims — a stubbed store failing afterwards is expected and irrelevant.
    for call in (
        lambda: registered["list_projects"](),
        lambda: registered["create_project"](workspace_id="ws-a", name="Atlas"),
    ):
        try:
            asyncio.run(call())
        except Exception:  # noqa: BLE001 — see above
            pass

    assert seen, "the guard was never called"
    for family, _op in seen:
        assert family == expected, (
            f"the door metered {family!r} where the Kind derives {expected!r} — "
            "the generic door and this one would disagree about Project"
        )
    assert ("definitions", "write") in seen, (
        "creating a project must still meter as a WRITE operation; only the "
        "FAMILY is derived, never the read/write distinction"
    )
