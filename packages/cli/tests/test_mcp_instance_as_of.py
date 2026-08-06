"""``get_instance(as_of=…)`` over MCP — the read in TIME, through the door.

The sibling of ``test_rest_instance_as_of`` and, deliberately, its mirror. i-106
was: the REST route ACCEPTED ``?as_of=`` and IGNORED it, because FastAPI drops
an undeclared query param in silence — so a caller asking what an Issue said
yesterday got today's Issue under a 200, with nothing in the body to contradict
them. The route was fixed. The MCP tool had no ``as_of`` at all, which is the
honest half of the same gap: an agent (the console copilot dials this door)
simply could not read the past.

⚠️ **THE RULE THIS SUITE ENFORCES, and it is the lesson of i-106 rather than a
feature:** a parameter that is accepted must CHANGE the answer or REFUSE. Never
both silently. So the first test is not "as_of works" — it is that the same call
one parameter apart does not agree, which is the exact complaint i-106 made.

The four outcomes are asserted APART, because collapsing any two re-creates the
defect one house over. Over MCP there are no status codes, so the distinction
must live in the type NAME the client receives — which is why the refusals are
relayed as ``AsOfUnsupported`` / ``AsOfTruncated`` and the "did not exist yet"
answer deliberately is not:

    the belief state    the instance, plus as_of / as_of_version / as_of_recorded_at
    did not exist yet   a plain lookup message naming the instant — an ANSWER
    history pruned      ``AsOfTruncated`` — a REFUSAL, and never the line above
    no history at all   ``AsOfUnsupported`` — never today's state under the stamp
    a bad instant       ``ValueError`` — the caller's typo, not the deployment's
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil
from datetime import datetime, timezone

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"

_SQL_SKIP = (
    "the SQL adapter's async driver stack is an SDK extra the CLI does not "
    "pull; the 'no history at all' lane still runs, and it is the one only "
    "this suite can prove."
)


def _mcp(args, **build):
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, **build)

    async def go():
        async with Client(server) as client:
            return await client.call_tool("get_instance", args)

    return asyncio.run(go()).structured_content


def _mcp_refused(args, **build) -> str:
    with pytest.raises(Exception) as ei:  # noqa: PT011 — FastMCP ToolError
        _mcp(args, **build)
    return str(ei.value)


def _story(name: str, status: str, description: str) -> dict:
    return {
        "apiVersion": _SDLC_API, "kind": "Story",
        "metadata": {"name": name},
        "spec": {"description": description, "status": status},
    }


def _engram(name: str, summary: str) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Engram",
        "metadata": {"name": name},
        "spec": {
            "summary": summary, "area": "infra", "affect": "triumph",
            "surface_when": ["feature_touched"], "source_refs": ["i-106"],
        },
    }


async def _tick() -> str:
    """An instant strictly BETWEEN two writes — the sleeps are not superstition:
    two writes in one event-loop turn can land on stamps no test can cut
    between, and the failure would read as a bug in as-of rather than the
    fixture."""
    await asyncio.sleep(0.02)
    t = datetime.now(timezone.utc).isoformat()
    await asyncio.sleep(0.02)
    return t


@pytest.fixture
def fs_dir(tmp_path, monkeypatch):
    """The filesystem store — declares ``versions=True`` and retains nothing."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    return dst


@pytest.fixture
def history(tmp_path, monkeypatch):
    """A SQLite store with REAL history, written through the REAL write path.

    Never by forging version rows: history exists in this product because
    somebody wrote an instance twice, and a fixture that inserted the rows would
    let the tool pass with no producer behind it.
    """
    for _module in ("aiosqlite", "greenlet", "alembic"):
        pytest.importorskip(_module, reason=_SQL_SKIP)
    url = f"sqlite+aiosqlite:///{tmp_path / 'as-of.db'}"
    monkeypatch.setenv("DNA_SOURCE_URL", url)
    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)

    marks: dict[str, str] = {}

    async def seed():
        from dna.adapters.sqlalchemy_ import SqlAlchemySource
        from dna.kernel import Kernel

        src = SqlAlchemySource(url)
        await src.connect()
        k = Kernel.auto()
        k.source(src)

        marks["t_before"] = await _tick()
        await k.write_instance(
            _SCOPE, "Story", "s-x", _story("s-x", "todo", "the first belief"))
        marks["t_mid"] = await _tick()
        await k.write_instance(
            _SCOPE, "Story", "s-x", _story("s-x", "done", "the second belief"))

        # Rewritten past VERSION_CHURN_RETENTION (3) — the pruning is the
        # product's, not the test's.
        for i in range(5):
            await k.write_instance(
                _SCOPE, "Engram", "e-churn", _engram("e-churn", f"belief {i}"))
            await asyncio.sleep(0.01)
        await src.close()

    asyncio.run(seed())
    return marks


# ── 200-equivalent: the belief state, and it DIFFERS from the present ───────


class TestTheReadInTime:
    def test_as_of_returns_the_past_not_the_present(self, history):
        """THE assertion i-106 is about, now at the MCP wire.

        Two calls, one parameter apart, must not agree — the whole complaint was
        that they did. A tool that accepted ``as_of`` and threw it away would
        pass every other test in this file.
        """
        now = _mcp({"kind": "Story", "name": "s-x"})
        then = _mcp({"kind": "Story", "name": "s-x",
                     "as_of": history["t_mid"]})

        assert now["instance"]["spec"]["status"] == "done"
        assert then["instance"]["spec"]["status"] == "todo", (
            "the as-of read handed back the CURRENT instance — i-106, restored "
            "on the face that never had the parameter at all"
        )
        assert then["instance"]["spec"]["description"] == "the first belief"

    def test_the_answer_says_it_is_historical(self, history):
        """A body a caller cannot tell apart from a live read is the defect with
        extra steps — so the version and the RECORDING time both travel, and a
        live read carries neither."""
        then = _mcp({"kind": "Story", "name": "s-x",
                     "as_of": history["t_mid"]})
        assert then["as_of"], "the instant did not come back"
        assert then["as_of_version"] == 1
        assert then["as_of_recorded_at"] <= then["as_of"], (
            "the version that answered was recorded AFTER the instant asked for"
        )

        live = _mcp({"kind": "Story", "name": "s-x"})
        assert live.get("as_of") is None
        assert live.get("as_of_version") is None
        assert live.get("as_of_recorded_at") is None

    def test_the_two_faces_agree_about_the_past(self, history):
        """The same store, the same instant, the same belief state.

        i-106's sibling failure would be a second implementation of the read
        drifting from the first; comparing catches it in either direction.
        """
        pytest.importorskip(
            "fastapi", reason="the REST read-API needs the 'fastapi' extra")
        from fastapi.testclient import TestClient

        from dna_cli import _rest_api as R

        with TestClient(R.build_app(scope=_SCOPE)) as c:
            rest = c.get("/v1/kinds/Story/instances/s-x",
                         params={"as_of": history["t_mid"]}).json()
        mcp = _mcp({"kind": "Story", "name": "s-x",
                    "as_of": history["t_mid"]})
        assert mcp == rest

    def test_the_instant_comes_back_normalized(self, history):
        """``Z`` in, ``+00:00`` out — echoing what the caller typed would let a
        misread offset survive the round trip unnoticed."""
        out = _mcp({"kind": "Story", "name": "s-x",
                    "as_of": "2099-01-01T00:00:00Z"})
        assert out["as_of"] == "2099-01-01T00:00:00+00:00"


# ── the refusals, each distinguishable from the others BY NAME ──────────────


class TestTheRefusals:
    def test_before_it_existed_is_an_answer_not_a_capability_refusal(
        self, history,
    ):
        """"Nothing was recorded under that name by then" is an ANSWER, and it
        must NOT arrive wearing a refusal's name — otherwise a caller reads "the
        store cannot tell me" out of "the store told me nothing was there"."""
        msg = _mcp_refused({"kind": "Story", "name": "s-x",
                            "as_of": history["t_before"]})
        assert "s-x" in msg, msg
        assert "AsOf" not in msg, msg

    def test_pruned_history_is_named_and_is_NOT_the_line_above(self, history):
        """⚠️ The collapse an as-of read may never make.

        Over REST these two differ by 410 vs 404. Over MCP there is no status
        code, so the ONLY thing that can carry the distinction is the type name
        — which is exactly why ``AsOfTruncated`` has to be caught BEFORE the
        plain ``LookupError`` arm it inherits from.
        """
        msg = _mcp_refused({"kind": "Engram", "name": "e-churn",
                            "as_of": history["t_before"]})
        assert "AsOfTruncated" in msg, msg
        assert "pruned" in msg, msg

        # ...and the same instance read NOW is perfectly readable, so the
        # refusal is about the instant and not about the instance.
        assert _mcp({"kind": "Engram", "name": "e-churn"})["instance"]

    def test_a_store_without_history_is_refused_not_answered_with_today(
        self, fs_dir,
    ):
        """The refusal only this lane can prove: the filesystem adapter declares
        ``versions=True`` and keeps nothing. Serving the current instance here
        would be a fabricated past wearing a real answer's clothes."""
        msg = _mcp_refused(
            {"kind": "Agent", "name": "concierge",
             "as_of": "2026-08-05T14:00:00Z"},
            base_dir=str(fs_dir))
        assert "AsOfUnsupported" in msg, msg
        assert "version history" in msg, msg

        # Anti-vacuity: without ``as_of`` the very same call is a normal read,
        # so the refusal is the parameter's doing and not a broken fixture.
        assert _mcp({"kind": "Agent", "name": "concierge"},
                    base_dir=str(fs_dir))["instance"]

    def test_the_refusal_survives_mask_error_details(self, fs_dir, monkeypatch):
        """With masking on, anything that is not a ``ToolError`` loses its
        message entirely. This is the assertion the default setting hides."""
        pytest.importorskip("fastmcp")
        import fastmcp

        monkeypatch.setattr(fastmcp.settings, "mask_error_details", True)
        msg = _mcp_refused(
            {"kind": "Agent", "name": "concierge",
             "as_of": "2026-08-05T14:00:00Z"},
            base_dir=str(fs_dir))
        assert "AsOfUnsupported" in msg, msg
        assert "version history" in msg, msg

    def test_a_nonsense_instant_is_the_callers_error(self, fs_dir):
        """Answered BEFORE the store's capability is consulted: an
        ``AsOfUnsupported`` here would blame the deployment for a typo."""
        msg = _mcp_refused(
            {"kind": "Agent", "name": "concierge", "as_of": "ontem à tarde"},
            base_dir=str(fs_dir))
        assert "ISO-8601" in msg, msg
        assert "AsOfUnsupported" not in msg, msg


# ── the parameter is DECLARED, which is what makes it findable ──────────────


def test_the_tool_schema_declares_as_of(fs_dir):
    """i-106 was FOUND by reading ``openapi.json`` and seeing ``as_of`` on two
    memory routes and nowhere else. The MCP equivalent is the tool's input
    schema: it is where an agent learns the parameter exists, and a read in time
    nobody can discover is not a port."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(fs_dir))

    async def go():
        async with Client(server) as client:
            return await client.list_tools()

    tool = {t.name: t for t in asyncio.run(go())}["get_instance"]
    assert "as_of" in tool.inputSchema["properties"], tool.inputSchema
    assert "as_of" in (tool.description or "")
