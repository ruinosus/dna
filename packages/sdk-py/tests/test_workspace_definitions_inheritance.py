"""Workspace-scope DEFINITIONS inheritance — the i-058 properties, pinned.

The product thesis ("a tenant declares only its difference and inherits the
rest") had a bootstrap hole: a Model-B workspace scope (``tenant-ws-<id>``) is
born EMPTY, and the transitive ``Genome.spec.parent_scope`` chain — the ONE
inheritance mechanism (``compute_resolution_chain``) — was honored by
``kernel.query`` and ``resolve_document`` but NOT by the two readers the
product surfaces actually use:

* the EAGER ManifestInstance materialization (``instance_builder``), which
  serves ``list_agents_impl`` (the AgentBrowser) and ``compose_prompt_impl``
  (the copilot) — it merged only the FIXED single ``_lib`` hop;
* ``kernel.get_document`` (``get_skill`` / ``get_template``) — same fixed hop.

i-058 routes BOTH through the existing chain. These tests state the resulting
SYSTEM properties, not the mechanism:

1. a workspace scope that declares a parent reads the parent's definitions on
   every definition surface (listing, compose, get, query) — transitively;
2. NO declared parent → NO inheritance beyond the V1 ``_lib`` hop (the
   anti-vacuity baseline: inheritance is a declaration, not global magic);
3. a local doc of the same (kind, name) OVERRIDES the inherited one, and a
   nearer parent shadows a farther one;
4. MEMORY and BOARD Kinds (``scope_inheritable=False``) never flow through
   the chain — the base is curated content, not shared state;
5. the documented cache-staleness boundary: a parent write is visible
   immediately to per-request builds (the ``LiveDna.mi`` path) but does NOT
   drop an already-cached child base MI (``_base_instance_cached*``) — the
   same boundary ``_lib`` writes always had, now pinned so a change to it is
   a conscious act.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application.live import LiveDna
from dna.application.runtime import (
    compose_prompt_impl,
    list_agents_impl,
    list_tools_impl,
)
from dna.kernel import Kernel

_API = "github.com/ruinosus/dna/v1"

#: The host-curated base scope (dna-cloud will point
#: DNA_WORKSPACE_DEFINITIONS_BASE at its equivalent, ``dna-development``).
_BASE = "base-defs"
#: A newborn workspace scope that DECLARES the base as parent.
_WS = "tenant-ws-new"
#: A workspace scope that declares NO parent (anti-vacuity control).
_WS_PLAIN = "tenant-ws-plain"
#: A workspace scope that declares the parent AND overrides one agent.
_WS_OVERRIDE = "tenant-ws-override"


def _doc(kind: str, name: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {"apiVersion": _API, "kind": kind,
            "metadata": {"name": name}, "spec": spec}


def _write(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(doc, default_flow_style=False))


@pytest.fixture()
def kernel(tmp_path: Path) -> Kernel:
    base = tmp_path / ".dna"

    # ── the curated base: definitions + (deliberately) memory & board ──
    _write(base / _BASE / "Genome.yaml", _doc("Genome", _BASE, {}))
    _write(base / _BASE / "agents" / "assistant.yaml",
           _doc("Agent", "assistant",
                {"instruction": "Base instruction: help honestly."}))
    _write(base / _BASE / "agents" / "shadow-me.yaml",
           _doc("Agent", "shadow-me", {"instruction": "base-defs copy"}))
    _write(base / _BASE / "skills" / "shared-skill.yaml",
           _doc("Skill", "shared-skill", {"instruction": "shared how-to"}))
    _write(base / _BASE / "tools" / "grep-tool.yaml",
           _doc("Tool", "grep-tool",
                {"input_schema": {"type": "object"}, "runtime": "python"}))
    _write(base / _BASE / "engrams" / "base-memory.yaml",
           _doc("Engram", "base-memory",
                {"summary": "the host's private memory", "area": "general"}))
    _write(base / _BASE / "stories" / "base-story.yaml",
           _doc("Story", "base-story",
                {"title": "the host's board item", "status": "todo"}))

    # ── workspace scopes ──
    _write(base / _WS / "Genome.yaml",
           _doc("Genome", _WS, {"parent_scope": _BASE}))
    _write(base / _WS_PLAIN / "Genome.yaml", _doc("Genome", _WS_PLAIN, {}))
    _write(base / _WS_OVERRIDE / "Genome.yaml",
           _doc("Genome", _WS_OVERRIDE, {"parent_scope": _BASE}))
    _write(base / _WS_OVERRIDE / "agents" / "assistant.yaml",
           _doc("Agent", "assistant",
                {"instruction": "Workspace override: speak Portuguese."}))

    # ── _lib (the V1 fallback tail of every chain) ──
    _write(base / "_lib" / "Genome.yaml", _doc("Genome", "_lib", {}))
    _write(base / "_lib" / "agents" / "lib-agent.yaml",
           _doc("Agent", "lib-agent", {"instruction": "I live in _lib."}))
    _write(base / "_lib" / "agents" / "shadow-me.yaml",
           _doc("Agent", "shadow-me", {"instruction": "_lib copy"}))

    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    return k


def _live(kernel: Kernel) -> LiveDna:
    return LiveDna(base_scope=_BASE, kernel=kernel, provider=None,
                   vendor_workspace="ws-vendor")


def _agent_docs(mi: Any) -> dict[str, str]:
    return {d.name: (d.spec.get("instruction") or "")
            for d in mi.documents if d.kind == "Agent"}


# ── 1. inheritance flows to every definition surface ────────────────────────


@pytest.mark.asyncio
async def test_listing_surfaces_the_base_agents(kernel: Kernel) -> None:
    """The AgentBrowser property: a newborn workspace that declares the base
    as parent LISTS the base's agents — no seed script, no redeploy."""
    out = await list_agents_impl(_live(kernel), scope=_WS)
    names = {a["name"] for a in out["agents"]}
    assert "assistant" in names
    assert out["scope"] == _WS


@pytest.mark.asyncio
async def test_compose_composes_the_inherited_agent(kernel: Kernel) -> None:
    """The copilot property: compose over the workspace scope composes the
    inherited definition instead of falling back to 'agent not found'."""
    out = await compose_prompt_impl(_live(kernel), "assistant", scope=_WS)
    assert "Base instruction: help honestly." in out["prompt"]
    assert out["scope"] == _WS


@pytest.mark.asyncio
async def test_get_document_walks_the_declared_chain(kernel: Kernel) -> None:
    """The get_skill/get_template read path resolves a base doc through the
    declared chain (it used to probe only the fixed ``_lib`` hop)."""
    raw = await kernel.get_document(_WS, "Skill", "shared-skill")
    assert raw is not None
    assert raw["spec"]["instruction"] == "shared how-to"


@pytest.mark.asyncio
async def test_query_walks_the_declared_chain(kernel: Kernel) -> None:
    """kernel.query (list_tools/list_skills/lazy MI) sees base definitions —
    including record-plane Kinds like Tool."""
    agents = [r async for r in kernel.query(_WS, "Agent")]
    tools = [r async for r in kernel.query(_WS, "Tool")]
    agent_names = {(r.get("metadata") or {}).get("name") for r in agents}
    tool_names = {(r.get("metadata") or {}).get("name") for r in tools}
    assert "assistant" in agent_names
    assert "grep-tool" in tool_names


@pytest.mark.asyncio
async def test_list_tools_surfaces_the_base_tools(kernel: Kernel) -> None:
    """The Tool surface (record plane, served by kernel.query) inherits
    through the same chain — the P6b probe of the live investigation."""
    out = await list_tools_impl(_live(kernel), scope=_WS)
    assert "grep-tool" in {t["name"] for t in out["tools"]}


@pytest.mark.asyncio
async def test_inheritance_is_transitive_and_nearer_parent_shadows(
    kernel: Kernel,
) -> None:
    """The chain is transitive (ws → base → V1 ``_lib`` tail) and positional:
    ``shadow-me`` exists in BOTH base-defs and ``_lib`` — the nearer parent's
    copy wins; ``lib-agent`` exists only in ``_lib`` and still arrives."""
    mi = await kernel.instance_async(_WS, lazy=False)
    agents = _agent_docs(mi)
    assert agents["shadow-me"] == "base-defs copy"
    assert "lib-agent" in agents


# ── 2. anti-vacuity: no declaration, no inheritance ─────────────────────────


@pytest.mark.asyncio
async def test_no_declared_parent_means_no_base_definitions(
    kernel: Kernel,
) -> None:
    """Inheritance is a DECLARATION, not global magic: a workspace scope
    without ``parent_scope`` stays blind to the base on every surface (it
    keeps only the historical V1 ``_lib`` hop)."""
    out = await list_agents_impl(_live(kernel), scope=_WS_PLAIN)
    names = {a["name"] for a in out["agents"]}
    assert "assistant" not in names
    assert "lib-agent" in names  # the V1 hop, unchanged

    assert await kernel.get_document(_WS_PLAIN, "Skill", "shared-skill") is None

    rows = [r async for r in kernel.query(_WS_PLAIN, "Agent")]
    assert "assistant" not in {(r.get("metadata") or {}).get("name") for r in rows}


@pytest.mark.asyncio
async def test_scope_without_parent_keeps_the_v1_single_hop_exactly(
    kernel: Kernel,
) -> None:
    """Byte-compat golden for the pre-i058 behavior: local docs first (in
    load order), then ONLY ``_lib``'s inheritable docs, stamped
    ``_inherited_from='_lib'`` — no other scope contributes."""
    mi = await kernel.instance_async(_WS_PLAIN, lazy=False)
    agents = _agent_docs(mi)
    assert set(agents) == {"lib-agent", "shadow-me"}
    assert agents["shadow-me"] == "_lib copy"  # _lib's copy — base never consulted


# ── 3. override: the workspace declares only its difference ─────────────────


@pytest.mark.asyncio
async def test_local_override_wins_over_the_base(kernel: Kernel) -> None:
    """The overlay thesis: an identically-named local doc REPLACES the
    inherited one — on the listing (no duplicate), on compose, on get."""
    mi = await kernel.instance_async(_WS_OVERRIDE, lazy=False)
    assistants = [d for d in mi.documents
                  if d.kind == "Agent" and d.name == "assistant"]
    assert len(assistants) == 1
    assert assistants[0].spec["instruction"].startswith("Workspace override")

    out = await compose_prompt_impl(_live(kernel), "assistant", scope=_WS_OVERRIDE)
    assert "Workspace override: speak Portuguese." in out["prompt"]
    assert "Base instruction" not in out["prompt"]

    raw = await kernel.get_document(_WS_OVERRIDE, "Agent", "assistant")
    assert raw["spec"]["instruction"].startswith("Workspace override")


# ── 4. isolation: definitions inherit; memory and board never do ────────────


@pytest.mark.asyncio
async def test_memory_and_board_do_not_flow_through_the_chain(
    kernel: Kernel,
) -> None:
    """The base is CURATED CONTENT, not shared state. Through the very same
    chain that delivers the Agent (the in-test anti-vacuity control), the
    base's Engram (memory) and Story (board) must NOT surface in the
    workspace — on the MI, on query, on get_document."""
    mi = await kernel.instance_async(_WS, lazy=False)
    assert "assistant" in _agent_docs(mi)  # the chain IS live for definitions
    kinds_present = {(d.kind, d.name) for d in mi.documents}
    assert ("Engram", "base-memory") not in kinds_present
    assert ("Story", "base-story") not in kinds_present
    # Scope IDENTITY/POLICY never crosses the chain either: the only Genome
    # in the workspace MI is the workspace's own. (Engram/Story are ALSO
    # blocked by the record-plane filter — this is the assertion that keeps
    # the non-inheritable gate itself honest for composition-plane Kinds.)
    genomes = {d.name for d in mi.documents if d.kind == "Genome"}
    assert genomes == {_WS}

    engrams = [r async for r in kernel.query(_WS, "Engram")]
    stories = [r async for r in kernel.query(_WS, "Story")]
    assert engrams == []
    assert stories == []

    assert await kernel.get_document(_WS, "Engram", "base-memory") is None
    assert await kernel.get_document(_WS, "Story", "base-story") is None


# ── 5. the documented cache-staleness boundary, pinned ──────────────────────


@pytest.mark.asyncio
async def test_parent_write_visibility_boundary(kernel: Kernel) -> None:
    """Two halves of the DOCUMENTED boundary (instance_builder docstring):

    * per-request builds (``LiveDna.mi`` → ``instance_async(lazy=False)``)
      see a parent-scope write IMMEDIATELY — the MCP/REST surfaces are never
      stale w.r.t. base definitions;
    * an already-cached child base MI (``_base_instance_cached_async``) is
      NOT dropped by a parent write — the historical ``_lib`` boundary, now
      explicit. If wiring parent writes into invalidation ever changes this,
      this test dying is the intended signal that the boundary moved.
    """
    # Prime the child's cached base MI.
    cached_before = await kernel._base_instance_cached_async(_WS)
    assert "late-agent" not in _agent_docs(cached_before)

    await kernel.write_document(
        _BASE, "Agent", "late-agent",
        _doc("Agent", "late-agent", {"instruction": "arrived after boot"}),
        invalidate_mode="doc",
    )

    # Half 1 — the request path sees it now.
    fresh = await kernel.instance_async(_WS, lazy=False)
    assert "late-agent" in _agent_docs(fresh)

    # Half 2 — the cached MI is stale until ITS scope is invalidated.
    cached_after = await kernel._base_instance_cached_async(_WS)
    assert cached_after is cached_before
    assert "late-agent" not in _agent_docs(cached_after)

    # An explicit child-scope drop converges it.
    kernel._kcache.base_drop(_WS)
    reconverged = await kernel._base_instance_cached_async(_WS)
    assert "late-agent" in _agent_docs(reconverged)
