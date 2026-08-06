"""Every write tool on the MCP face RELAYS the refusal it was given.

The hole: the face enumerated the exception types it would translate, and the
enumeration was wrong.

* ``write_instance`` caught ``(ValueError, LookupError, PermissionError)``. But
  ``LayerPolicyViolationError`` / ``TenantNotAllowed`` / ``TenantRequired`` /
  ``InvalidTenantSlug`` are plain ``Exception`` and ``NotWritableError`` is a
  ``RuntimeError`` — so not one of them matched. The LayerPolicy veto is the
  likeliest refusal there is on a tenant write, and it escaped.
* ``create_story`` / ``create_issue`` / ``create_feature`` had no ``try`` at all.
* not one of the five memory tools mapped anything.

The fix is a kernel-level marker base (``dna.kernel.errors.KernelRefusal``) plus
ONE mapping per tool, so a refusal declared tomorrow is relayed by a face written
today. These tests inject each refusal at the use-case seam — the point of the
test is what the FACE does with it, and provoking a live LayerPolicy veto through
an authenticated tenant write would prove the kernel's gate, not the mapping.
One end-to-end case (a create over an existing name) carries no fake at all.
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
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _refusals():
    """One instance of each kernel refusal a write can legitimately hit."""
    from dna.kernel import KindRetiredError, NotWritableError
    from dna.kernel.protocols import (
        InvalidTenantSlug,
        LayerPolicyViolationError,
        SpecValidationError,
        TenantNotAllowed,
        TenantRequired,
    )

    return [
        LayerPolicyViolationError("layer 'tenant' LOCKED for alias helix-agent"),
        TenantNotAllowed("global kind Story written with tenant='acme'"),
        TenantRequired("tenanted kind Agent written with no tenant"),
        InvalidTenantSlug("tenant slug 'personal:x' uses a reserved scheme"),
        NotWritableError("no WritableSourcePort is registered"),
        KindRetiredError("Kind 'Actor' was retired"),
        SpecValidationError("schema validation failed at spec.status"),
    ]


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


# ── the generic write ───────────────────────────────────────────────────────


@pytest.mark.parametrize("exc", _refusals(), ids=lambda e: type(e).__name__)
def test_write_document_relays_every_kernel_refusal(dna_dir, monkeypatch, exc):
    pytest.importorskip("fastmcp")
    from dna.application import instances as D
    from dna_cli import _mcp_server as M

    async def boom(*a, **kw):
        raise exc

    monkeypatch.setattr(D, "write_instance_impl", boom)
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    msg = _refused(server, "write_instance", {
        "kind": "ModelProfile", "name": "x",
        "spec": {"model_id": "x", "provider": "y"}, "scope": _SCOPE})
    assert type(exc).__name__ in msg, msg   # the client learns WHICH refusal
    assert str(exc) in msg                  # …and its reason, verbatim


def test_a_stale_if_match_is_an_honest_refusal_not_a_500(dna_dir):
    """The concurrency guard's own refusal travels the same road."""
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    _call(server, "write_instance", {
        "kind": "ModelProfile", "name": "m", "scope": _SCOPE,
        "spec": {"model_id": "m", "provider": "p"}})
    msg = _refused(server, "write_instance", {
        "kind": "ModelProfile", "name": "m", "scope": _SCOPE,
        "spec": {"provider": "q"}, "if_match": "not-the-current-etag"})
    assert "ConcurrentWriteError" in msg
    assert "get_instance" in msg  # names the remedy


# ── the board write tools (which had no ``try`` at all) ─────────────────────


_BOARD_TOOLS = [
    ("create_story", "create_story_impl",
     {"name": "s-x", "feature": "f-x", "description": "d",
      "ac": ["Given X, when Y, then Z"], "dod": ["code+tests"]}),
    ("create_issue", "create_issue_impl", {"slug": "x", "description": "d"}),
    ("create_feature", "create_feature_impl",
     {"name": "f-x", "title": "t", "description": "d"}),
    ("set_status", "set_status_impl",
     {"kind": "Story", "name": "s-x", "status": "done"}),
    ("comment", "comment_impl",
     {"kind": "Story", "name": "s-x", "body": "hi"}),
]


@pytest.mark.parametrize(("tool", "impl", "args"), _BOARD_TOOLS,
                         ids=[t[0] for t in _BOARD_TOOLS])
def test_every_board_write_tool_relays_a_kernel_refusal(
    dna_dir, monkeypatch, tool, impl, args,
):
    pytest.importorskip("fastmcp")
    from dna.kernel.protocols import LayerPolicyViolationError
    from dna_cli import _mcp_server as M

    async def boom(*a, **kw):
        raise LayerPolicyViolationError("the board scope is LOCKED for this layer")

    monkeypatch.setattr(M, impl, boom)
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    msg = _refused(server, tool, {**args, "scope": _SCOPE})
    assert "LayerPolicyViolationError" in msg, msg
    assert "LOCKED" in msg


def test_a_create_over_an_existing_story_is_refused_by_name(dna_dir):
    """No injection: two ``create_story`` calls with the same name. The second
    used to REPLACE the first — status, timeline, AC and DoD — and report
    success."""
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    _call(server, "create_story", {
        "name": "s-mine", "feature": "f-demo", "description": "the real one",
        "ac": ["Given A, when B, then C"], "dod": ["merged"], "scope": _SCOPE})
    msg = _refused(server, "create_story", {
        "name": "s-mine", "feature": "f-other", "description": "a guess",
        "ac": ["Given X, when Y, then Z"], "dod": ["code+tests"],
        "scope": _SCOPE})
    assert "InstanceExists" in msg
    assert "s-mine" in msg          # names the existing instance
    assert "set_status" in msg      # …and what to do instead

    kept = _call(server, "get_instance",
                 {"kind": "Story", "name": "s-mine", "scope": _SCOPE})
    spec = kept.structured_content["instance"]["spec"]
    assert spec["description"] == "the real one"
    assert spec["acceptance_criteria"] == ["Given A, when B, then C"]


def test_a_create_over_an_existing_feature_is_refused_by_name(dna_dir):
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    _call(server, "create_feature", {
        "name": "f-mine", "title": "T", "description": "the real one",
        "scope": _SCOPE})
    msg = _refused(server, "create_feature", {
        "name": "f-mine", "title": "T2", "description": "a guess",
        "scope": _SCOPE})
    assert "InstanceExists" in msg and "f-mine" in msg


# ── the memory tools (which mapped nothing) ────────────────────────────────


_MEMORY_TOOLS = [
    ("remember", "remember_impl", {"summary": "s"}),
    ("recall", "recall_impl", {"query": "q"}),
    ("consolidate", "consolidate_impl", {}),
    ("list_memories", "list_memories_impl", {}),
    ("forget", "forget_impl", {"name": "n"}),
]


@pytest.mark.parametrize(("tool", "impl", "args"), _MEMORY_TOOLS,
                         ids=[t[0] for t in _MEMORY_TOOLS])
def test_every_memory_tool_relays_a_kernel_refusal(
    dna_dir, monkeypatch, tool, impl, args,
):
    pytest.importorskip("fastmcp")
    from dna.kernel.protocols import TenantNotAllowed
    from dna_cli import _mcp_server as M

    async def boom(*a, **kw):
        raise TenantNotAllowed("Engram is GLOBAL here — tenant must be None")

    monkeypatch.setattr(M, impl, boom)
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    msg = _refused(server, tool, {**args, "scope": _SCOPE})
    assert "TenantNotAllowed" in msg, msg
    assert "GLOBAL" in msg


# ── a refusal is a refusal, not a bug: real bugs still surface as bugs ──────


def test_an_unexpected_error_is_not_dressed_up_as_a_refusal(dna_dir, monkeypatch):
    """The mapping must not become a blanket ``except Exception`` that reports
    every crash as a policy decision — a caller told "refused" stops
    investigating."""
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    async def boom(*a, **kw):
        raise ZeroDivisionError("a genuine bug")

    monkeypatch.setattr(M, "create_story_impl", boom)
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    msg = _refused(server, "create_story", {
        "name": "s-x", "feature": "f-x", "description": "d", "scope": _SCOPE})
    assert "ZeroDivisionError" not in msg or "refus" not in msg.lower()


# ── the DELETE tool, which until now had no refusal to relay ────────────────


def test_delete_instance_relays_the_on_target_delete_refusal(dna_dir, monkeypatch):
    """``TargetDeleteRestricted`` (slice 2 of ``spec-topologia-do-grafo``) is
    the first refusal the delete path can raise — writes had ``pre_save``,
    deletes had nothing.

    This is the whole point of the marker base, asserted rather than assumed:
    the tool's ``except WRITE_REFUSALS`` was written before this refusal
    existed, and it relays it anyway because the tuple names ``KernelRefusal``
    rather than a list of types. If somebody ever narrows that tuple to an
    enumeration, this goes red — which is the failure the enumeration caused
    the first time."""
    pytest.importorskip("fastmcp")
    from dna.application import instances as D
    from dna.kernel.errors import TargetDeleteRestricted
    from dna_cli import _mcp_server as M

    exc = TargetDeleteRestricted(
        "refusing to delete Feature/f-x: 47 reference(s) declare "
        "on_target_delete: restrict",
        referrers=[{"kind": "Story", "name": "s-1", "relation": "feature"}],
    )

    async def boom(*a, **kw):
        raise exc

    monkeypatch.setattr(D, "delete_instance_impl", boom)
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    msg = _refused(server, "delete_instance", {
        "kind": "ModelProfile",
        "api_version": "github.com/ruinosus/dna/modelreg/v1",
        "name": "x", "scope": _SCOPE})
    assert "TargetDeleteRestricted" in msg, msg
    assert "on_target_delete: restrict" in msg, msg


def test_the_delete_refusal_is_inside_the_tuple_the_TOOL_catches(dna_dir):
    """Derived from the face's own tuple, not retyped here. The test above
    proves the relay end to end; this one names WHY it works, so a narrowing of
    ``WRITE_REFUSALS`` fails with the reason on screen instead of as a mystery
    in a FastMCP error string."""
    from dna.kernel.errors import TargetDeleteRestricted
    from dna_cli._mcp_instances import WRITE_REFUSALS

    assert issubclass(TargetDeleteRestricted, WRITE_REFUSALS)
