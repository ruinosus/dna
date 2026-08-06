"""A capability refusal reaches the MCP client NAMED, exactly as it does over REST.

The ports catalogue states four refusals as CONTRACT, each because the only
alternative is a confident answer that is not true:

* ``edge_graph=False`` → ``GraphUnsupported`` (REST **501**), never ``[]`` — an
  empty list reads as *nothing points at this instance*.
* ``as_of_reads`` absent → ``AsOfUnsupported`` (REST **501**), never today's
  state under a past timestamp.
* history pruned → ``AsOfTruncated`` (REST **410**), never a bare
  ``LookupError`` — *"it did not exist yet"* is a different answer from *"I no
  longer hold the record"*.
* no ``find_instances_by_id_prefix`` → ``InstanceIdLookupUnsupported`` (REST
  **501**), never an empty result set.

The REST face mapped all four. The MCP face mapped one. The gap was structural,
not an oversight per tool: ``_refusing()`` relays ``KernelRefusal`` — the marker
base for a VERDICT ABOUT THE REQUEST — and a capability refusal is not that. It
is the deployment saying it cannot answer at all, and the four inherit from
``RuntimeError`` / ``NotImplementedError`` / ``LookupError``, so only
``AsOfTruncated`` fell inside a tuple this face already caught.

**Everything here goes THROUGH THE TOOL.** That is not ceremony. The bug WAS the
boundary: ``dna.memory.verbs.recall`` raised the right exception, from the right
place, with the right sentence, and every unit test of it was green — the loss
happened between the use-case and the wire. A test that calls ``recall_impl``
directly cannot see it, and this house has shipped a validator that no door
called before (``guard-existe-porta-nao-chama``).

``test_a_capability_refusal_survives_mask_error_details`` is the one that pins
the fix rather than an accident. FastMCP's default (``mask_error_details=False``)
already lets an unmapped exception's message through, so with the default alone
the "before" and "after" strings differ only by the type-name prefix. Flip the
setting an operator is invited to flip and the difference is total: an unmapped
exception becomes ``Error calling tool 'recall'`` with NO reason, while a
``ToolError`` is delivered verbatim — because ``ToolError`` is FastMCP's own
declaration that a message is meant for the client. That is the whole property
being bought, and it is invisible at the default.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A REAL filesystem-backed store — the adapter that makes this reachable.

    It declares ``versions=True`` and ``list_versions`` returns ``[]``: it keeps
    no history at all. That is not a contrived fixture, it is the default
    self-host deployment, and it is exactly the store the catalogue's
    ``as_of_reads`` flag exists to describe.
    """
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _call(server, tool, args):
    from fastmcp import Client

    async def go():
        async with Client(server) as client:
            return await client.call_tool(tool, args)

    return asyncio.run(go())


def _refused(server, tool, args) -> str:
    with pytest.raises(Exception) as ei:  # noqa: PT011 — FastMCP ToolError
        _call(server, tool, args)
    return str(ei.value)


# ── end to end: no injection anywhere ───────────────────────────────────────


def test_recall_as_of_on_a_store_with_no_history_is_refused_by_name(dna_dir):
    """The defect, reproduced through the door and then fixed there.

    Nothing is faked: a real filesystem store, a real ``recall`` call with a
    real past timestamp. Before the fix the client got FastMCP's generic
    ``Error calling tool 'recall'`` wrapper and the server logged a full
    traceback — a documented refusal, delivered in the shape of a crash.
    """
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    msg = _refused(server, "recall", {
        "query": "anything", "scope": _SCOPE,
        "as_of": "2020-01-01T00:00:00Z"})

    # The NAME, because an agent acts on it: ``AsOfUnsupported`` means "stop
    # asking this deployment about the past", which is a different remedy from
    # every other way a recall can fail.
    assert "AsOfUnsupported" in msg, msg
    # …and the reason, verbatim, including WHY it refused rather than degraded.
    assert "version history" in msg, msg
    assert "CURRENT belief state" in msg, msg


def test_recall_without_as_of_still_answers(dna_dir):
    """The refusal is scoped to the question that cannot be answered.

    Without this, a fix that turned every ``recall`` into a refusal would pass
    the test above.
    """
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    result = _call(server, "recall", {"query": "anything", "scope": _SCOPE})
    assert result.structured_content["hits"] == []
    assert result.structured_content["query"] == "anything"


def test_a_capability_refusal_survives_mask_error_details(dna_dir, monkeypatch):
    """With masking ON, a mapped refusal still carries name + reason.

    This is the assertion the default setting hides. ``mask_error_details``
    replaces the message of any exception that is NOT a ``ToolError`` with a
    generic string — so before the fix this call returned literally ``Error
    calling tool 'recall'`` and the agent had nothing at all to act on.
    """
    pytest.importorskip("fastmcp")
    import fastmcp

    from dna_cli import _mcp_server as M

    monkeypatch.setattr(fastmcp.settings, "mask_error_details", True)
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    msg = _refused(server, "recall", {
        "query": "anything", "scope": _SCOPE,
        "as_of": "2020-01-01T00:00:00Z"})

    assert "AsOfUnsupported" in msg, msg
    assert "version history" in msg, msg


def test_masking_really_does_erase_an_unmapped_exception(dna_dir, monkeypatch):
    """The control for the test above — the mechanism, not the claim.

    An exception the face does NOT translate is erased under masking. Without
    this case, ``test_a_capability_refusal_survives_mask_error_details`` could
    pass on a build where masking silently did nothing, and would then be
    asserting FastMCP's default rather than our mapping.
    """
    pytest.importorskip("fastmcp")
    import fastmcp

    from dna_cli import _mcp_server as M

    async def boom(*a, **kw):
        raise ArithmeticError("a genuine bug, not a refusal")

    monkeypatch.setattr(fastmcp.settings, "mask_error_details", True)
    monkeypatch.setattr(M, "recall_impl", boom)
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    msg = _refused(server, "recall", {"query": "q", "scope": _SCOPE})

    assert "a genuine bug" not in msg, msg  # masked, as a bug should be


# ── every capability refusal, through the relay ─────────────────────────────


def _capability_refusals():
    from dna_cli._mcp_refusals import CAPABILITY_REFUSALS

    return [cls("this deployment cannot answer that") for cls in CAPABILITY_REFUSALS]


@pytest.mark.parametrize("exc", _capability_refusals(), ids=lambda e: type(e).__name__)
def test_every_capability_refusal_is_relayed_by_name(dna_dir, monkeypatch, exc):
    """Not one of the four may reach the client unnamed.

    Injected at the use-case seam because three of the four need a store this
    deployment does not have (no edge graph / no id search / pruned history) —
    provoking them for real would prove the ADAPTER's honesty, and what is under
    test here is the FACE's. ``AsOfUnsupported`` is covered without any injection
    by the end-to-end case above, which is what keeps this parametrization from
    being a test of its own fixture.

    The list is imported, not written here: a name added to
    ``CAPABILITY_REFUSALS`` gains a case, and one deleted loses one, without
    anyone editing this file.
    """
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    async def boom(*a, **kw):
        raise exc

    monkeypatch.setattr(M, "recall_impl", boom)
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    msg = _refused(server, "recall", {"query": "q", "scope": _SCOPE})

    assert type(exc).__name__ in msg, msg
    assert str(exc) in msg, msg


def test_a_real_bug_is_still_reported_as_a_bug(dna_dir, monkeypatch):
    """The tuple is deliberately not ``Exception``.

    A caller told "refused" stops investigating, so a crash dressed as a policy
    decision costs more than a crash. Widening ``CAPABILITY_REFUSALS`` to
    something that swallows ``AttributeError`` would make the four cases above
    pass and this one fail, which is the point.
    """
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    async def boom(*a, **kw):
        raise AttributeError("'NoneType' object has no attribute 'kernel'")

    monkeypatch.setattr(M, "recall_impl", boom)
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    msg = _refused(server, "recall", {"query": "q", "scope": _SCOPE})
    assert "AttributeError" not in msg or "refused" not in msg.lower(), msg
