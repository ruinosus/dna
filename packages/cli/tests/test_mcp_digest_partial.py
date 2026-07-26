"""``sdlc_digest`` never reports a clean board it could not read.

The hole was three lines::

    try:
        docs.extend(await _collect(live, sc, kind, tenant))
    except Exception:   # kind absent in this source
        continue

The comment names one cause. The code catches every cause — a dropped
connection, a statement timeout, a permission error on one Kind — and then the
digest reports ``rag_status: green`` and the verdict "nada precisa da sua
atenção". The delegator's ONE retrospective surface says everything is fine
precisely when it could not look.

Two distinctions the result now carries:

* **absent vs unreadable.** A Kind that is not registered on this source is a
  fact about the source, known from the registry BEFORE any query — it does not
  need an exception to discover, and it is not a failure. Anything a query
  raises is.
* **partial vs empty.** A digest missing a Kind is visibly partial: ``partial:
  true``, the failed Kinds with their errors, a verdict that says so, and a
  ``rag_status`` that is never ``green`` — an unread board is not a clean one.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil
from datetime import datetime, timedelta, timezone

import pytest

from dna_cli._digest import build_digest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


# ── the pure aggregator owns the consequences ───────────────────────────────


def _window():
    now = datetime.now(timezone.utc)
    return now - timedelta(days=1), now


def test_a_complete_digest_is_unchanged():
    since, until = _window()
    dg = build_digest(docs=[], since=since, until=until, scope="s")
    assert dg["partial"] is False
    assert dg["rag_status"] == "green"
    assert dg["sources"] == {"absent": [], "unreadable": []}
    assert "nada precisa da sua atenção" in dg["verdict"]


def test_an_unreadable_kind_makes_the_digest_visibly_partial():
    since, until = _window()
    dg = build_digest(
        docs=[], since=since, until=until, scope="s",
        unreadable=[{"kind": "Issue", "error": "ConnectionResetError: reset"}],
    )
    assert dg["partial"] is True
    assert dg["sources"]["unreadable"] == [
        {"kind": "Issue", "error": "ConnectionResetError: reset"}]
    # never green: an unread board is not a clean board.
    assert dg["rag_status"] == "amber"
    assert "Issue" in dg["verdict"]
    assert "incompleto" in dg["verdict"].lower()


def test_a_red_board_stays_red_when_partial():
    """Partial DEGRADES the signal, it does not overwrite it — a blocked item is
    still the loudest fact on the board."""
    since, until = _window()
    dg = build_digest(
        docs=[{"kind": "Story", "name": "s-x",
               "spec": {"status": "blocked", "title": "t"}}],
        since=since, until=until, scope="s",
        unreadable=[{"kind": "Issue", "error": "boom"}],
    )
    assert dg["partial"] is True
    assert dg["rag_status"] == "red"


def test_an_absent_kind_is_reported_but_is_not_a_failure():
    """A source that does not register ``Bug`` is not a broken source."""
    since, until = _window()
    dg = build_digest(
        docs=[], since=since, until=until, scope="s", absent=["Bug"])
    assert dg["partial"] is False
    assert dg["sources"]["absent"] == ["Bug"]
    assert dg["rag_status"] == "green"


# ── the MCP use-case classifies its own reads ──────────────────────────────


def test_a_read_failure_is_reported_instead_of_swallowed(dna_dir, monkeypatch):
    from dna_cli import _mcp_server as M

    real = M._collect

    async def flaky(live, scope, kind, tenant=None):
        if kind == "Issue":
            raise ConnectionResetError("connection reset by peer")
        return await real(live, scope, kind, tenant)

    monkeypatch.setattr(M, "_collect", flaky)

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await M.sdlc_digest_impl(live, since="99d", scope=_SCOPE)

    dg = asyncio.run(go())
    assert dg["partial"] is True
    failed = {f["kind"]: f["error"] for f in dg["sources"]["unreadable"]}
    assert "Issue" in failed
    assert "ConnectionResetError" in failed["Issue"]   # names the cause
    assert "connection reset by peer" in failed["Issue"]
    assert dg["rag_status"] != "green"
    # the Kinds that DID read still contributed — a partial digest is still useful.
    assert dg["sources"]["absent"] == []


def test_a_kind_the_source_does_not_register_is_absent_not_failed(
    dna_dir, monkeypatch,
):
    """Classified from the Kind REGISTRY, before any query — so it needs no
    exception to discover and cannot be confused with one."""
    import dna_cli.sdlc_cmd as SC
    from dna_cli import _mcp_server as M

    monkeypatch.setattr(SC, "_digest_kinds", lambda kernel=None: ("Story", "Nonesuch"))

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await M.sdlc_digest_impl(live, since="99d", scope=_SCOPE)

    dg = asyncio.run(go())
    assert dg["sources"]["absent"] == ["Nonesuch"]
    assert dg["sources"]["unreadable"] == []
    assert dg["partial"] is False


def test_a_healthy_digest_over_the_face_reports_complete(dna_dir):
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))

    async def go():
        async with Client(server) as client:
            return await client.call_tool("sdlc_digest", {"scope": _SCOPE})

    dg = asyncio.run(go()).structured_content
    assert dg["partial"] is False
    assert dg["sources"]["unreadable"] == []
