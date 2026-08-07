"""``s-porta-de-busca`` on the MCP face — the tool that was missing.

The 11 tools a copilot actually holds (``author_kind`` · ``review_kind`` ·
``list_kinds`` · ``list_my_kinds`` · ``get_document`` · ``get_instance`` ·
``list`` · ``recall`` · ``remember`` · ``consolidate`` · ``forget``) contained no
way to ask *"is there already something like this?"* over an arbitrary Kind —
only ``list_kinds``, which is enumeration. The engine behind the answer has been
in the tree since two-planes F2; what was missing was reachable from a
conversation.

The DOOR's own obligations are what this file pins — the ones the core in
``dna.application.instances`` cannot hold because it does not own the plan:

* the tool exists and is registered (a use-case with no ``@server.tool`` is the
  same defect the story is about, one layer up);
* it is metered against the TARGET KIND's family, derived, never a literal — so
  a search cannot be the cheap door into a family the caller's plan gates;
* it is a READ (``family_op="read"``), so a plan granting read-only reaches it;
* the tenant the guard yields is what travels into the core — the guard resolves
  the workspace, and a door that resolved it and then searched without it would
  pass every behavioural test while returning another workspace's instances.

The degradation contract and the tenant boundary themselves live with the core:
``packages/sdk-py/tests/test_search_instances_port.py``.
"""
from __future__ import annotations

import asyncio
from typing import Any

from dna.application import instances as D

from dna_cli import _mcp_instances as I


class _Port:
    """Project's registered port, reduced to the two fields the family mapping
    reads — carrying its REAL apiVersion, so the derivation under test is the
    live one."""

    kind = "Project"
    api_version = "github.com/ruinosus/dna/portfolio/v1"


def _register(monkeypatch, *, guard, impl):
    monkeypatch.setattr(D, "resolve_kind_port", lambda *a, **k: _Port())

    async def _resolve_live(*_a, **_k):
        return _Port()

    monkeypatch.setattr(D, "resolve_kind_port_live", _resolve_live)
    monkeypatch.setattr(D, "search_instances_impl", impl)

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

            def default_scope(self, _tenant=None):
                return "demo"

        return _L()

    async def plan_families():
        return None

    names = I.register_instance_tools(
        _Server(), live=live, guard=guard, plan_families=plan_families,
    )
    return registered, names


def test_the_tool_is_registered_and_named(monkeypatch):
    """A use-case nobody can call is the story's own defect repeated. The
    returned name list is what the boot log prints, so it must carry it too."""
    async def _impl(*_a, **_k):
        return {}

    async def _guard(family, tenant=None, *, scope=None, family_op="read"):
        return tenant

    registered, names = _register(monkeypatch, guard=_guard, impl=_impl)
    assert "search_instances" in registered
    assert "search_instances" in names


def test_it_meters_the_targets_family_as_a_read(monkeypatch):
    """Derived, not typed. Hardcode ``"definitions"`` in the tool and this still
    passes; change the Kind → family mapping and it fails loudly, which is the
    direction that matters — the generic door must never disagree with the
    hand-written one about the same Kind."""
    seen: list[tuple[str, str, str | None]] = []

    async def _guard(family, tenant=None, *, scope=None, family_op="read"):
        seen.append((family, family_op, scope))
        return "acme"

    async def _impl(*_a, **_k):
        return {}

    registered, _ = _register(monkeypatch, guard=_guard, impl=_impl)
    asyncio.run(registered["search_instances"](
        kind="Project", query="a project like this one", scope="demo"))

    expected = D.family_for_kind(_Port())
    assert expected == "definitions", (
        f"the Kind → family mapping now says {expected!r}; the premise moved"
    )
    assert seen == [(expected, "read", "demo")]


def test_the_guards_tenant_is_what_reaches_the_core(monkeypatch):
    """The guard is the ONLY thing that knows whose workspace this is. A door
    that resolved a tenant and then searched without it would return a plausible
    list drawn from every overlay, and no assertion about hits would notice."""
    captured: dict[str, Any] = {}

    async def _guard(family, tenant=None, *, scope=None, family_op="read"):
        return "acme"

    async def _impl(_live, **kw):
        captured.update(kw)
        return {"hits": [], "degraded": False}

    registered, _ = _register(monkeypatch, guard=_guard, impl=_impl)
    asyncio.run(registered["search_instances"](
        kind="Project", query="cache invalidation", scope="demo", k=25))

    assert captured["tenant"] == "acme"
    assert captured["query"] == "cache invalidation"
    assert captured["k"] == 25
    # The apiVersion travels from the RESOLVED port, never from the caller —
    # same rule the rest of the generic door follows.
    assert captured["api_version"] == _Port.api_version
    assert captured["kind"] == _Port.kind


def test_the_docstring_tells_the_caller_to_read_mode_first(monkeypatch):
    """The tool description is the only thing a model reads before deciding what
    an empty ``hits`` means. It has to carry the caveat — the honest envelope is
    worth nothing if the field that carries it is never looked at."""
    async def _guard(family, tenant=None, *, scope=None, family_op="read"):
        return tenant

    async def _impl(*_a, **_k):
        return {}

    registered, _ = _register(monkeypatch, guard=_guard, impl=_impl)
    doc = registered["search_instances"].__doc__ or ""
    assert "degraded" in doc and "mode" in doc
    assert D.SEARCH_NO_PROVIDER in doc
    assert "BLIND SPOT" in doc
    assert "similarity" in doc.lower() and "enumeration" in doc.lower()
