"""``dna.application.runtime`` — the DNA **application / use-case layer** (core).

Per ``adr-faces-reorg`` (move #1, load-bearing): the transport-agnostic
``*_impl`` use-cases the DNA faces share (CLI, MCP server, REST API) live HERE,
in the core — NOT buried in the CLI package. Each function takes a
:class:`~dna.application.live.LiveDna` handle and drives the kernel directly;
none imports HTTP / Click / FastMCP. The faces are thin adapters: they translate
transport + edge validation (the MCP server's auth/quota bridge, HTTP
request/response shaping, JSON-RPC translation) and then delegate to these
use-cases.

These are THIN wrappers over already-tested pure cores — the kernel composition
(``build_prompt``), the emit tool projection (``ToolLibrary``) and the memory
verbs (``dna.memory``). No new business logic lives here; the logic moved,
byte-for-byte, out of ``dna_cli._mcp_server`` so a third face is a new adapter,
never a re-implementation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dna.application.live import LiveDna


# ── definitions (compose / list agents / tools) ────────────────────────────


async def compose_prompt_impl(
    live: LiveDna, agent: str, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """Compose ``agent``'s system prompt LIVE (Soul + Guardrails + instruction),
    tenant-aware. This is the killer surface: with ``tenant`` set it returns the
    per-tenant overlay — the composition emit cannot express in a flat file."""
    mi = await live.mi(scope, tenant)
    doc = mi.find_agent(agent)
    if doc is None:
        raise ValueError(f"agent {agent!r} not found in scope {mi.scope!r}")
    prompt = await mi.build_prompt_async(agent)
    spec = getattr(doc, "spec", None) or {}
    return {
        "scope": mi.scope,
        "agent": agent,
        "tenant": tenant,
        "model": spec.get("model") if hasattr(spec, "get") else None,
        "prompt": prompt,
    }


def _prompt_target_kinds(mi: Any) -> set[str]:
    kinds: set[str] = set()
    for kp in getattr(mi, "_kinds", {}).values():
        if getattr(kp, "is_prompt_target", False) and getattr(kp, "kind", None):
            kinds.add(kp.kind)
    return kinds


async def list_agents_impl(
    live: LiveDna, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """List the prompt-target agents (Agent/UtilityAgent/…) in ``scope``,
    tenant-aware when ``tenant`` is set (the auth bridge injects it)."""
    mi = await live.mi(scope, tenant)
    targets = _prompt_target_kinds(mi)
    agents: list[dict[str, Any]] = []
    for d in mi.documents:
        if d.kind not in targets:
            continue
        meta = getattr(d, "metadata", None) or {}
        agents.append(
            {
                "name": d.name,
                "kind": d.kind,
                "description": (meta.get("description") if hasattr(meta, "get") else "") or "",
            }
        )
    agents.sort(key=lambda a: a["name"])
    return {"scope": mi.scope, "agents": agents}


def _tool_surface(row: dict[str, Any]) -> dict[str, Any]:
    """Project a raw Tool doc (kernel-query row) to its agent-facing surface —
    the SAME projection ``dna.tools.ToolSurface`` performs (description =
    ``metadata.description``, parameters = ``spec.input_schema``). Read off the
    async-query row so no sync kernel roundtrip fires inside the event loop
    (Tool is a record-plane Kind — it is NOT in ``mi.documents``)."""
    meta = row.get("metadata") or {}
    spec = row.get("spec") or {}
    return {
        "name": meta.get("name") or row.get("name"),
        "description": (meta.get("description") or ""),
        "parameters": dict(spec.get("input_schema") or {}),
    }


async def _tool_rows(
    live: LiveDna, scope: str, tenant: str | None = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    async for row in live.kernel.query(scope, "Tool", tenant=tenant):
        if isinstance(row, dict):
            rows.append(row)
    return rows


async def list_tools_impl(
    live: LiveDna, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """List the Tool Kind surfaces declared in ``scope`` (name + description)."""
    mi = await live.mi(scope, tenant)
    tools = [
        {"name": s["name"], "description": s["description"]}
        for s in (_tool_surface(r) for r in await _tool_rows(live, mi.scope, tenant))
    ]
    tools.sort(key=lambda t: t["name"] or "")
    return {"scope": mi.scope, "tools": tools}


async def get_tool_impl(
    live: LiveDna, name: str, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """The full agent-facing surface of one Tool: description + input schema."""
    mi = await live.mi(scope, tenant)
    rows = await _tool_rows(live, mi.scope, tenant)
    surface = next((s for s in map(_tool_surface, rows) if s["name"] == name), None)
    if surface is None:
        available = sorted(filter(None, (s["name"] for s in map(_tool_surface, rows))))
        raise ValueError(f"tool {name!r} not found in scope {mi.scope!r}; available: {available}")
    return {"scope": mi.scope, **surface}


# ── SDLC (the self-describing board) ───────────────────────────────────────


async def _collect(
    live: LiveDna, scope: str, kind: str, tenant: str | None = None
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    async for row in live.kernel.query(scope, kind, tenant=tenant):
        meta = row.get("metadata") if isinstance(row, dict) else None
        name = (meta or {}).get("name") if isinstance(meta, dict) else None
        spec = row.get("spec") if isinstance(row, dict) else None
        out.append(
            {
                "kind": kind,
                "name": name or (row.get("name") if isinstance(row, dict) else None),
                "spec": spec if isinstance(spec, dict) else dict(spec or {}),
            }
        )
    return out


async def list_stories_impl(
    live: LiveDna, status: str | None = None, scope: str | None = None,
    tenant: str | None = None,
) -> dict[str, Any]:
    """List Stories, optionally filtered by ``status`` (todo/in-progress/…)."""
    sc = scope or live.base_scope
    stories: list[dict[str, Any]] = []
    for d in await _collect(live, sc, "Story", tenant):
        spec = d["spec"]
        st = spec.get("status")
        if status and st != status:
            continue
        stories.append(
            {
                "name": d["name"],
                "title": spec.get("title"),
                "status": st,
                "feature": spec.get("feature"),
                "priority": spec.get("priority"),
            }
        )
    stories.sort(key=lambda s: (s.get("status") or "", s.get("name") or ""))
    return {"scope": sc, "count": len(stories), "stories": stories}


async def get_adr_impl(
    live: LiveDna, name: str, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """Fetch one ADR (Architecture Decision Record) by name — the decision the
    board recorded, verbatim (context / decision / consequences / body)."""
    sc = scope or live.base_scope
    raw = await live.kernel.get_document(sc, "ADR", name, tenant=tenant)
    if raw is None:
        raise ValueError(f"ADR {name!r} not found in scope {sc!r}")
    spec = raw.get("spec") or {}
    return {
        "scope": sc,
        "name": name,
        "title": spec.get("title"),
        "status": spec.get("status"),
        "context": spec.get("context"),
        "decision": spec.get("decision"),
        "consequences": spec.get("consequences"),
        "body": spec.get("body"),
    }


# ── memory (declarative recall) ────────────────────────────────────────────


async def recall_impl(
    live: LiveDna, query: str, scope: str | None = None, k: int = 5,
    tenant: str | None = None,
) -> dict[str, Any]:
    """Recall DNA memory for ``query`` — hybrid + bi-temporal + retention
    re-scored when the search extra is present, honest lexical otherwise.
    Tenant-scoped when ``tenant`` is set (the auth bridge injects it)."""
    from dna.memory import recall
    from dna.memory.verbs import MEMORY_KINDS

    sc = scope or live.base_scope
    if live.provider is not None:
        try:
            from dna.memory import backfill_index

            await backfill_index(live.kernel, sc, kinds=MEMORY_KINDS, tenant=tenant)
        except Exception:  # noqa: BLE001 — indexing failure degrades to lexical
            pass
    res = await recall(live.kernel, sc, query, k=k, actor="mcp", tenant=tenant)
    return res


async def remember_impl(
    live: LiveDna,
    summary: str,
    scope: str | None = None,
    kind: str = "LessonLearned",
    area: str = "general",
    affect: str = "triumph",
    tags: list[str] | None = None,
    owner: str = "mcp",
    tenant: str | None = None,
) -> dict[str, Any]:
    """Persist a memory Kind (deterministically enriched + indexed) — mirrors
    ``dna memory remember``. Written into the tenant overlay when ``tenant`` is
    set (the auth bridge injects it)."""
    from dna.memory import remember

    sc = scope or live.base_scope
    name = _slug(summary)
    spec: dict[str, Any] = {"summary": summary}
    if kind == "LessonLearned":
        spec.update(
            {
                "area": area,
                "surface_when": ["feature_touched"],
                "source_refs": [area],
                "affect": affect,
                "owner": owner,
            }
        )
        if tags:
            spec["tags"] = list(tags)
    out = await remember(live.kernel, sc, kind=kind, name=name, spec=spec, tenant=tenant)
    return {"kind": out["kind"], "name": out["name"], "indexed": out["indexed"]}


async def consolidate_impl(
    live: LiveDna, scope: str | None = None, apply: bool = False,
    tenant: str | None = None,
) -> dict[str, Any]:
    """Deterministic memory consolidation pass (Ebbinghaus retention). With
    ``apply=True`` stale memories are soft-forgotten (bi-temporal, never
    deleted). Mirrors ``dna memory consolidate``."""
    from dna.memory import consolidate

    sc = scope or live.base_scope
    return await consolidate(live.kernel, sc, apply=apply, tenant=tenant)


async def list_memories_impl(
    live: LiveDna, scope: str | None = None, kind: str = "LessonLearned",
    tenant: str | None = None,
) -> dict[str, Any]:
    """List the tenant's stored memories — the LIST surface the DNA Cloud memory
    dashboard renders. Tenant-aware via the same ``kernel.query`` idiom every
    list surface uses (``_collect``): with ``tenant`` set the caller sees the
    shared base PLUS its own overlay only, never another tenant's overlay (#83).
    Projects each memory to ``{name, summary, area, tags, affect, created_at}``
    and sorts newest-first when a timestamp is available. FORGOTTEN memories
    (bi-temporally demoted by ``forget`` — ``spec.valid_to`` set/in the past) are
    EXCLUDED, using the SAME ``currently_valid`` predicate ``recall`` applies
    (verbs.py) so the list and recall agree: a memory dropped by ``forget``
    disappears from BOTH surfaces, never a ghost."""
    from dna.memory.decay import currently_valid

    sc = scope or live.base_scope
    memories: list[dict[str, Any]] = []
    for d in await _collect(live, sc, kind, tenant):
        spec = d["spec"]
        if not currently_valid(spec.get("valid_to")):
            continue  # forgotten / superseded — never surfaced (mirrors recall).
        # LessonLearned stamps ``created_at`` (== ``valid_from`` seed); fall back
        # to the reconsolidation timeline's first ``at`` when a variant omits it.
        created = spec.get("created_at") or spec.get("valid_from")
        if not created:
            history = spec.get("cues_history") or []
            if isinstance(history, list) and history and isinstance(history[0], dict):
                created = history[0].get("at")
        memories.append(
            {
                "name": d["name"],
                "summary": spec.get("summary"),
                "area": spec.get("area"),
                "tags": list(spec.get("tags") or []),
                "affect": spec.get("affect"),
                "created_at": created,
            }
        )
    memories.sort(key=lambda m: (m.get("created_at") or ""), reverse=True)
    return {"scope": sc, "memories": memories}


async def forget_impl(
    live: LiveDna, name: str, scope: str | None = None,
    kind: str = "LessonLearned", tenant: str | None = None,
) -> dict[str, Any]:
    """Forget ONE memory by its doc ``name`` (slug) — the DELETE surface the DNA
    Cloud memory dashboard calls. NOT a hard delete: routes through the memory
    verb ``dna.memory.forget`` — a **bi-temporal DEMOTION** that stamps
    ``valid_to`` (a revivable tombstone, auditable, never destroyed; verbs.py
    "NEVER hard-delete"). ``tenant=tenant`` writes the demotion into the caller's
    OWN overlay only — never base, never another tenant (#83). Because the write
    invalidates the recall index AND ``recall``/``list_memories`` both exclude
    ``valid_to`` memories, a forgotten memory disappears from both surfaces (no
    ghost).

    Result mapping: a real demotion → ``forgotten: True``; an already-forgotten
    memory (idempotent re-forget) → ``forgotten: False``; a name that does not
    exist in the caller's layer (``forget`` raises ``KeyError``) → a clean
    ``forgotten: False`` no-op, never a 500."""
    from dna.memory import forget

    sc = scope or live.base_scope
    try:
        out = await forget(live.kernel, sc, name, kind=kind, tenant=tenant)
    except KeyError:
        return {"kind": kind, "name": name, "forgotten": False}
    return {"kind": kind, "name": name, "forgotten": not out["already_forgotten"]}


def _slug(text: str) -> str:
    import hashlib
    import re

    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
    h = hashlib.sha1(text.encode()).hexdigest()[:10]
    return f"rem-{h}-{base}" if base else f"rem-{h}"
