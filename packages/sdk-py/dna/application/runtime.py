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

import logging

from datetime import datetime, timezone
from typing import Any

from dna.application.live import LiveDna

logger = logging.getLogger(__name__)


# ── definitions (compose / list agents / tools) ────────────────────────────


def _sections_attribution(agent_spec: Any) -> str:
    """How trustworthy the explain section map is for THIS agent.

    ``PromptBuilder.explain`` reconstructs the section list by matching the
    layout template's Mustache blocks (``{{#alias}}`` / flatten vars) against
    the agent's declared deps — fail-soft string matching, never a re-run of
    composition. Two honesty regimes follow:

    * ``"declared"`` — the agent renders through a KERNEL-OWNED template (a
      named ``layout`` preset or the Kind's default template, including the
      plain-instruction fallback). The kernel authored both the aliases and
      the template, so the block match is correct by construction.
    * ``"heuristic"`` — the agent carries its OWN ``promptTemplate`` (the
      poweruser escape hatch). The match runs against a user-authored
      template, so a section can be silently MISSING from (or over-reported
      in) ``sections`` — the prompt itself is still byte-exact.
    """
    has = agent_spec.get if hasattr(agent_spec, "get") else (lambda _k: None)
    custom = has("promptTemplate") or has("prompt_template")
    return "heuristic" if custom else "declared"


async def compose_prompt_impl(
    live: LiveDna, agent: str, scope: str | None = None, tenant: str | None = None,
    *, explain: bool = False,
) -> dict[str, Any]:
    """Compose ``agent``'s system prompt LIVE (Soul + Guardrails + instruction),
    tenant-aware. This is the killer surface: with ``tenant`` set it returns the
    per-tenant overlay — the composition emit cannot express in a flat file.

    ``explain=True`` (opt-in, i-045) ADDS per-section provenance — ``sections``
    (one row per composed input: source artifact, content hash, version, layer
    origin, tenant-overlay marker) and ``attribution`` (see
    :func:`_sections_attribution`). The ``prompt`` is produced by the SAME
    composition path (``PromptBuilder.explain_async`` delegates to
    ``build_async``), so it is byte-identical to the plain compose by
    construction. Without the flag the return is EXACTLY the historical
    five-key envelope — no new keys, so existing consumers (and the REST/MCP
    wire shapes) are untouched.
    """
    mi = await live.mi(scope, tenant)
    doc = mi.find_agent(agent)
    if doc is None:
        raise ValueError(f"agent {agent!r} not found in scope {mi.scope!r}")
    explanation = None
    if explain:
        explanation = await mi.prompt.explain_async(agent, tenant=tenant)
        prompt = explanation.prompt
    else:
        prompt = await mi.build_prompt_async(agent)
    spec = getattr(doc, "spec", None) or {}
    out: dict[str, Any] = {
        "scope": mi.scope,
        "agent": agent,
        "tenant": tenant,
        "model": spec.get("model") if hasattr(spec, "get") else None,
        "prompt": prompt,
    }
    if explanation is not None:
        out["sections"] = [s.serialize() for s in explanation.sections]
        out["attribution"] = _sections_attribution(spec)
    return out


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


# ── toolkit: PromptTemplates + Skills (the Spec Kit Layer 3 surface) ─────────
#
# The ingested Spec Kit toolkit (``dna specify install-templates``) lands as
# PromptTemplate + Skill Kinds. These use-cases SERVE them live over any face
# (MCP/REST), tenant-aware — so a workspace/tenant overlay of a template or a
# slash-command wins with zero redeploy (the payoff of Layer 3: the toolkit
# becomes versioned, governed, portable policy, not per-repo files). Both Kinds
# are in ``DEFAULT_INHERITABLE_KINDS_V1`` — the overlay is the kernel's, not new
# machinery here.


async def _query_rows(
    live: LiveDna, scope: str, kind: str, tenant: str | None = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    async for row in live.kernel.query(scope, kind, tenant=tenant):
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _row_name(row: dict[str, Any]) -> str | None:
    meta = row.get("metadata") if isinstance(row, dict) else None
    if isinstance(meta, dict) and meta.get("name"):
        return meta["name"]
    return row.get("name") if isinstance(row, dict) else None


async def list_templates_impl(
    live: LiveDna, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """List the PromptTemplates in ``scope`` (name + description + variable
    count), tenant-aware. The Spec Kit templates ingested by
    ``dna specify install-templates`` surface here — servable to any client."""
    sc = scope or live.base_scope
    templates: list[dict[str, Any]] = []
    for row in await _query_rows(live, sc, "PromptTemplate", tenant):
        spec = row.get("spec") or {}
        spec = spec if isinstance(spec, dict) else {}
        variables = spec.get("variables") or []
        templates.append({
            "name": _row_name(row),
            "description": spec.get("description") or "",
            "variables_count": len(variables) if isinstance(variables, list) else 0,
            "tags": spec.get("tags") or [],
        })
    templates.sort(key=lambda t: t["name"] or "")
    return {"scope": sc, "templates": templates}


async def get_template_impl(
    live: LiveDna, name: str, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """Fetch one PromptTemplate's full body + variables, tenant-aware. With
    ``tenant`` set the per-workspace/tenant OVERLAY wins (no redeploy) — the
    Layer 3 governance payoff."""
    sc = scope or live.base_scope
    raw = await live.kernel.get_document(sc, "PromptTemplate", name, tenant=tenant)
    if raw is None:
        raise ValueError(f"PromptTemplate {name!r} not found in scope {sc!r}")
    spec = raw.get("spec") or {}
    spec = spec if isinstance(spec, dict) else {}
    return {
        "scope": sc,
        "name": name,
        "tenant": tenant,
        "body": spec.get("body") or "",
        "variables": spec.get("variables") or [],
        "description": spec.get("description") or "",
        "tags": spec.get("tags") or [],
    }


async def list_skills_impl(
    live: LiveDna, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """List the Skills in ``scope`` (name + description), tenant-aware. The Spec
    Kit slash-command definitions ingested as Skills surface here."""
    sc = scope or live.base_scope
    skills: list[dict[str, Any]] = []
    for row in await _query_rows(live, sc, "Skill", tenant):
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        skills.append({
            "name": _row_name(row),
            "description": (meta.get("description") if isinstance(meta, dict) else "") or "",
            "tags": (meta.get("tags") if isinstance(meta, dict) else []) or [],
        })
    skills.sort(key=lambda s: s["name"] or "")
    return {"scope": sc, "skills": skills}


async def get_skill_impl(
    live: LiveDna, name: str, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """Fetch one Skill's full instruction body + metadata, tenant-aware. With
    ``tenant`` set the per-workspace/tenant OVERLAY wins (no redeploy)."""
    sc = scope or live.base_scope
    raw = await live.kernel.get_document(sc, "Skill", name, tenant=tenant)
    if raw is None:
        raise ValueError(f"Skill {name!r} not found in scope {sc!r}")
    spec = raw.get("spec") or {}
    spec = spec if isinstance(spec, dict) else {}
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    return {
        "scope": sc,
        "name": name,
        "tenant": tenant,
        "instruction": spec.get("instruction") or "",
        "description": (meta.get("description") if isinstance(meta, dict) else "") or "",
        "scripts": sorted((spec.get("scripts") or {}).keys()) if isinstance(spec.get("scripts"), dict) else [],
    }


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
    sc = scope or live.default_scope(tenant)
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
    sc = scope or live.default_scope(tenant)
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


# ── portfolio (the DNA Cloud console read model) ───────────────────────────
#
# Thin read projections over the 5 TENANTED portfolio Kinds (Organization /
# Project / Repo, plus Membership / Role) the PortfolioExtension registers. They
# reuse the SAME ``_collect`` query primitive every list surface here is built on
# (and ``list_stories_impl`` for the board) — no new query logic, just the shape
# the console renders. Tenant-aware: with ``tenant`` set ``kernel.query`` returns
# the shared base plus the tenant's OWN overlay only (#83 isolation).


def _org_surface(d: dict[str, Any]) -> dict[str, Any]:
    spec = d["spec"]
    return {
        "name": d["name"],
        "slug": spec.get("slug"),
        "display_name": spec.get("display_name") or spec.get("name") or d["name"],
    }


def _project_surface(d: dict[str, Any]) -> dict[str, Any]:
    spec = d["spec"]
    return {
        "name": d["name"],
        "slug": spec.get("slug"),
        # A1: the owning workspace is an explicit field. Absent on a legacy
        # pre-A1 doc — reported as None rather than guessed from the tenant key.
        "workspace_id": spec.get("workspace_id"),
        "org_ref": spec.get("org_ref"),
        "repo_refs": list(spec.get("repo_refs") or []),
        "board_scope": spec.get("board_scope"),
        "intel_source_refs": list(spec.get("intel_source_refs") or []),
        "visibility": spec.get("visibility", "private"),
    }


def _repo_surface(d: dict[str, Any]) -> dict[str, Any]:
    spec = d["spec"]
    return {
        "name": d["name"],
        "url": spec.get("url"),
        "provider": spec.get("provider", "github"),
        "default_branch": spec.get("default_branch"),
    }


async def list_orgs_impl(
    live: LiveDna, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """List the tenant's ``Organization`` docs, projected to the console card
    surface (``name`` / ``slug`` / ``display_name``), sorted by name."""
    sc = scope or live.default_scope(tenant)
    orgs = [_org_surface(d) for d in await _collect(live, sc, "Organization", tenant)]
    orgs.sort(key=lambda o: o["name"] or "")
    return {"scope": sc, "tenant": tenant, "orgs": orgs}


async def list_projects_impl(
    live: LiveDna, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """List the tenant's ``Project`` docs (the multi-repo containers), projected
    to the console surface (name/slug/org_ref/repo_refs/board_scope/
    intel_source_refs/visibility), sorted by name."""
    sc = scope or live.default_scope(tenant)
    projects = [_project_surface(d) for d in await _collect(live, sc, "Project", tenant)]
    projects.sort(key=lambda p: p["name"] or "")
    return {"scope": sc, "tenant": tenant, "projects": projects}


async def list_repos_impl(
    live: LiveDna, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """List the tenant's ``Repo`` docs, projected to the console surface
    (name/url/provider/default_branch), sorted by name."""
    sc = scope or live.default_scope(tenant)
    repos = [_repo_surface(d) for d in await _collect(live, sc, "Repo", tenant)]
    repos.sort(key=lambda r: r["name"] or "")
    return {"scope": sc, "tenant": tenant, "repos": repos}


class ProjectNotFound(LookupError):
    """The requested Project is absent for this (scope, tenant)."""


async def get_project_impl(
    live: LiveDna, slug: str, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """One project's detail + its RESOLVED repos. Matches ``slug`` against the
    project's ``spec.slug`` (falling back to the doc name), then resolves each
    ``repo_refs`` entry to its ``Repo`` doc — the N—N edge lives on the Project
    side, so this is a lookup over the tenant's Repo docs (missing refs are
    skipped honestly, never fabricated). Raises :class:`ProjectNotFound`."""
    sc = scope or live.default_scope(tenant)
    rows = await _collect(live, sc, "Project", tenant)
    match = next(
        (d for d in rows if d["spec"].get("slug") == slug or d["name"] == slug),
        None,
    )
    if match is None:
        raise ProjectNotFound(
            f"project {slug!r} not found in scope {sc!r}"
            + (f" (tenant={tenant})" if tenant else "")
        )
    project = _project_surface(match)
    repo_rows = {d["name"]: d for d in await _collect(live, sc, "Repo", tenant)}
    repos = [
        _repo_surface(repo_rows[ref]) for ref in project["repo_refs"] if ref in repo_rows
    ]
    return {"scope": sc, "tenant": tenant, "project": project, "repos": repos}


# ── portfolio: Membership / Role (the console's RBAC read + write model) ─────
#
# The Membros panel resolves a user's EFFECTIVE role at a project — the standard
# ladder (owner > admin > member > guest), highest-role-wins across a user's
# org- and project-scope grants, with the org owner a superuser. All read + write
# logic lives HERE (the core); the REST face is a thin translator (adr-faces-reorg).

_PORTFOLIO_API = "github.com/ruinosus/dna/portfolio/v1"

# The standard ladder as a rank fallback — a tenant that has NOT seeded Role docs
# still resolves highest-role-wins. When Role docs ARE present their ``rank`` wins
# (the ladder is data — a custom rung slots in without a code change).
_ROLE_RANKS: dict[str, int] = {"owner": 40, "admin": 30, "member": 20, "guest": 10}
_ROLE_DISPLAY: dict[str, str] = {
    "owner": "Owner", "admin": "Admin", "member": "Member", "guest": "Guest",
}


class MemberForbidden(PermissionError):
    """The acting user (``actor``) lacks the role to mutate this project's
    membership (needs Owner/Admin; only an Owner may grant Owner). → HTTP 403."""


class MemberNotFound(LookupError):
    """The targeted project-scope Membership is absent for this (project, tenant)
    — nothing to remove. → HTTP 404."""


def _member_doc_name(user: str, scope_type: str, scope_ref: str) -> str:
    """Deterministic Membership doc name per (user, scope_type, scope_ref), so a
    role change overwrites the SAME doc rather than creating a duplicate grant."""
    import re

    def s(x: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", str(x).lower()).strip("-")

    return f"{s(user)}--{scope_type}--{s(scope_ref)}"


async def _role_ranks(
    live: LiveDna, scope: str, tenant: str | None
) -> dict[str, int]:
    """The role→rank map — the standard ladder, overlaid by any tenant Role docs
    (the ladder AS DATA: a seeded/custom rung's ``rank`` wins)."""
    ranks = dict(_ROLE_RANKS)
    for d in await _collect(live, scope, "Role", tenant):
        spec = d["spec"]
        rid = spec.get("role_id") or d["name"]
        rank = spec.get("rank")
        if rid and isinstance(rank, int):
            ranks[str(rid).lower()] = rank
    return ranks


def _effective_role(grant: dict[str, Any], ranks: dict[str, int]) -> str | None:
    """Highest-role-wins across a user's org- and project-scope grants (the org
    grant inherits DOWN to the project; the higher rank of the two wins)."""
    roles = [r for r in (grant.get("org"), grant.get("project")) if r]
    if not roles:
        return None
    return max(roles, key=lambda r: ranks.get(str(r).lower(), 0))


def _scope_note(org_role: str | None, project_role: str | None) -> str | None:
    """A human explanation of WHERE the effective role comes from (mirrors the
    prototype's scope notes: 'Org Owner → herda Owner aqui', 'Org Member ·
    Project Admin (highest-role-wins)', 'Guest · sem acesso a outros projetos')."""
    if org_role == "owner":
        return "Org Owner → herda Owner aqui"
    if project_role == "guest" and not org_role:
        return "Guest · sem acesso a outros projetos da org"
    parts: list[str] = []
    if org_role:
        parts.append(f"Org {_ROLE_DISPLAY.get(org_role, org_role.capitalize())}")
    if project_role:
        parts.append(
            f"Project {_ROLE_DISPLAY.get(project_role, project_role.capitalize())}"
        )
    note = " · ".join(parts)
    if org_role and project_role and org_role != project_role:
        note += " (highest-role-wins)"
    return note or None


async def _members_context(
    live: LiveDna, scope: str, slug: str, tenant: str | None
) -> dict[str, Any]:
    """Resolve the project (by ``slug`` or name) + everyone's org/project grants
    on it, tenant-scoped. Shared by the list + both writes. Raises
    :class:`ProjectNotFound`."""
    rows = await _collect(live, scope, "Project", tenant)
    match = next(
        (d for d in rows if d["spec"].get("slug") == slug or d["name"] == slug),
        None,
    )
    if match is None:
        raise ProjectNotFound(
            f"project {slug!r} not found in scope {scope!r}"
            + (f" (tenant={tenant})" if tenant else "")
        )
    project = _project_surface(match)
    org_ref = project.get("org_ref")
    project_key = {project["name"]}
    if project.get("slug"):
        project_key.add(project["slug"])

    grants: dict[str, dict[str, Any]] = {}
    for d in await _collect(live, scope, "Membership", tenant):
        spec = d["spec"]
        user = spec.get("user")
        st = spec.get("scope_type")
        ref = spec.get("scope_ref")
        role = (spec.get("role") or "").lower() or None
        if not user or not role:
            continue
        applies = (st == "project" and ref in project_key) or (
            st == "org" and org_ref and ref == org_ref
        )
        if not applies:
            continue
        g = grants.setdefault(user, {})
        if st == "project":
            g["project"] = role
            g["status"] = spec.get("status")
            g["invited_at"] = spec.get("invited_at")
        elif st == "org":
            g["org"] = role
    ranks = await _role_ranks(live, scope, tenant)
    return {
        "project": project,
        "org_ref": org_ref,
        "project_key": project_key,
        "grants": grants,
        "ranks": ranks,
    }


def _require_manage(
    ctx: dict[str, Any], actor: str | None, *, target_role: str | None = None
) -> None:
    """RBAC gate on a membership WRITE: the ``actor`` must be Owner/Admin of the
    project (or its org). Additionally, only an Owner may grant the Owner role (no
    privilege escalation by an Admin). Raises :class:`MemberForbidden`."""
    actor_role = (
        _effective_role(ctx["grants"].get(actor, {}), ctx["ranks"]) if actor else None
    )
    if actor_role not in ("owner", "admin"):
        raise MemberForbidden(
            f"actor {actor or '<anonymous>'!r} lacks manage permission on project "
            f"{ctx['project']['name']!r} — needs Owner/Admin (has "
            f"{actor_role or 'no role'})"
        )
    if target_role == "owner" and actor_role != "owner":
        raise MemberForbidden("only an Owner may grant the Owner role")


def _member_surface(
    user: str, grant: dict[str, Any], ranks: dict[str, int], viewer: str | None
) -> dict[str, Any]:
    org_role = grant.get("org")
    project_role = grant.get("project")
    effective = _effective_role(grant, ranks) or "guest"
    return {
        "user": user,
        "role": effective,
        "role_display": _ROLE_DISPLAY.get(effective, effective.capitalize()),
        "org_role": org_role,
        "project_role": project_role,
        "is_org_owner": org_role == "owner",
        "status": grant.get("status") or "active",
        "scope_note": _scope_note(org_role, project_role),
        "you": bool(viewer) and user == viewer,
    }


async def list_members_impl(
    live: LiveDna,
    slug: str,
    scope: str | None = None,
    tenant: str | None = None,
    viewer: str | None = None,
) -> dict[str, Any]:
    """List a project's members with their RESOLVED role (highest-role-wins across
    org + project grants, org-owner a superuser), tenant-scoped. When ``viewer``
    is given, flags the viewer's own row (``you``) and reports whether they may
    manage membership (``viewer.can_manage`` — Owner/Admin). Raises
    :class:`ProjectNotFound`."""
    sc = scope or live.default_scope(tenant)
    ctx = await _members_context(live, sc, slug, tenant)
    ranks = ctx["ranks"]
    members = [
        _member_surface(user, grant, ranks, viewer)
        for user, grant in ctx["grants"].items()
    ]
    # Highest rank first, then user for a stable order.
    members.sort(key=lambda m: (-ranks.get(m["role"], 0), m["user"]))
    viewer_role = (
        _effective_role(ctx["grants"].get(viewer, {}), ranks) if viewer else None
    )
    return {
        "scope": sc,
        "tenant": tenant,
        "project": {
            "name": ctx["project"]["name"],
            "slug": ctx["project"].get("slug"),
            "org_ref": ctx["org_ref"],
        },
        "members": members,
        "viewer": {
            "user": viewer,
            "role": viewer_role,
            "can_manage": viewer_role in ("owner", "admin"),
        },
    }


async def set_member_impl(
    live: LiveDna,
    slug: str,
    user: str,
    role: str,
    scope: str | None = None,
    tenant: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    """Invite / set a user's PROJECT-scope role — the Membros panel's write. RBAC:
    ``actor`` must be Owner/Admin (only an Owner may grant Owner). Upserts the SAME
    deterministic Membership doc (a role change overwrites, never duplicates),
    preserving an existing invite's ``status``/``invited_at``. Tenant-scoped: the
    write routes to the caller's tenant overlay only."""
    sc = scope or live.default_scope(tenant)
    user = (user or "").strip()
    role = (role or "").lower().strip()
    if not user:
        raise ValueError("user is required")
    if role not in _ROLE_RANKS:
        raise ValueError(
            f"unknown role {role!r} — expected one of {sorted(_ROLE_RANKS)}"
        )
    ctx = await _members_context(live, sc, slug, tenant)
    _require_manage(ctx, actor, target_role=role)

    project_name = ctx["project"]["name"]
    name = _member_doc_name(user, "project", project_name)
    write_kernel = live.kernel.with_tenant(tenant) if tenant else live.kernel

    # Preserve an existing grant's invite lifecycle (role change ≠ re-invite).
    existing = await write_kernel.get_document(sc, "Membership", name, tenant=tenant)
    ex_spec = (existing or {}).get("spec") or {}
    now = datetime.now(timezone.utc).isoformat()
    spec = {
        "user": user,
        "scope_type": "project",
        "scope_ref": project_name,
        "role": role,
        "status": ex_spec.get("status") or "invited",
        "invited_at": ex_spec.get("invited_at") or now,
    }
    raw = {
        "apiVersion": _PORTFOLIO_API,
        "kind": "Membership",
        "metadata": {"name": name},
        "spec": spec,
    }
    await write_kernel.write_document(
        sc, "Membership", name, raw, invalidate_mode="doc"
    )
    return {
        "scope": sc,
        "tenant": tenant,
        "member": {
            "user": user,
            "role": role,
            "scope_type": "project",
            "scope_ref": project_name,
            "status": spec["status"],
        },
    }


async def remove_member_impl(
    live: LiveDna,
    slug: str,
    user: str,
    scope: str | None = None,
    tenant: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    """Remove a user's PROJECT-scope grant — the Membros panel's remove. RBAC:
    ``actor`` must be Owner/Admin. Removing an Owner's grant requires Owner.
    Deletes ONLY the project-scope Membership (an inherited org grant is
    untouched). 404 (:class:`MemberNotFound`) when the user has no project grant
    here. Tenant-scoped."""
    sc = scope or live.default_scope(tenant)
    user = (user or "").strip()
    if not user:
        raise ValueError("user is required")
    ctx = await _members_context(live, sc, slug, tenant)
    # Removing an Owner needs Owner (same escalation guard as granting Owner).
    target_project_role = (ctx["grants"].get(user) or {}).get("project")
    _require_manage(
        ctx, actor, target_role="owner" if target_project_role == "owner" else None
    )

    project_name = ctx["project"]["name"]
    name = _member_doc_name(user, "project", project_name)
    write_kernel = live.kernel.with_tenant(tenant) if tenant else live.kernel
    try:
        await write_kernel.delete_document(
            sc, "Membership", name, invalidate_mode="doc"
        )
    except ValueError as exc:  # filesystem/pg source raises ValueError("not_found")
        if "not_found" in str(exc).lower():
            raise MemberNotFound(
                f"user {user!r} has no project-scope membership on "
                f"{project_name!r} (tenant={tenant}) — nothing to remove"
            ) from None
        raise
    return {"removed": user, "scope": sc, "tenant": tenant}


async def provision_tenant_owner_impl(
    live: LiveDna,
    tenant: str,
    user: str,
    scope: str | None = None,
) -> dict[str, Any]:
    """Bootstrap the FIRST Owner of a tenant — the fix for a brand-new tenant
    having ZERO Membership docs (audit finding C3).

    Without this, a freshly provisioned tenant's very first user could not manage
    members: ``_require_manage`` found no Owner/Admin grant for them and 403'd every
    membership write, and nothing ever made the sole user the Owner of their own
    tenant. On first authenticated access the DNA Cloud portal calls this (server
    side, with the shared bearer — the portal never opens the DNA source directly,
    same pattern as ``PUT /v1/account-plan``) so the signed-in user becomes Owner of
    their OWN tenant and member management works.

    **Idempotent + first-owner-only.** If the tenant ALREADY has any Owner
    Membership (org- or project-scope), this is a NO-OP — a *later* user signing
    into the same tenant does NOT auto-escalate to Owner (they need an invite from
    an existing Owner/Admin). That first-owner-only rule is what makes it safe to
    call on every sign-in / dashboard load.

    **What it grants.** An ORG-scope Owner Membership for every organization the
    tenant references (the org owner is a superuser — Owner across every project in
    that org), plus a PROJECT-scope Owner Membership for any orgless Project (one an
    org grant would not cover). The org set is taken from BOTH the Organization docs
    AND every non-empty ``project.org_ref`` — so the guard's ``applies`` check
    (org-grant matches ``project.org_ref``; project-grant matches the project name)
    matches one of these grants for any project in the tenant, even a dangling
    org_ref with no Organization doc. Memberships are written ``active`` (the tenant
    owner is a real member, not a pending invite). TENANTED: the write routes to the
    caller's OWN tenant overlay only.
    """
    sc = scope or live.default_scope(tenant)
    tenant = (tenant or "").strip()
    user = (user or "").strip()
    if not tenant:
        raise ValueError("tenant is required")
    if not user:
        raise ValueError("user is required")

    # First-owner-only: if ANY Owner membership already exists in this tenant, it is
    # already provisioned — never auto-escalate a subsequent user.
    existing = await _collect(live, sc, "Membership", tenant)
    for d in existing:
        if (d["spec"].get("role") or "").lower() == "owner":
            return {
                "scope": sc,
                "tenant": tenant,
                "user": user,
                "provisioned": False,
                "reason": "owner_exists",
                "grants": [],
            }

    orgs = await _collect(live, sc, "Organization", tenant)
    projects = await _collect(live, sc, "Project", tenant)

    # The set of grants that guarantee the user is Owner of every project in the
    # tenant: one org-scope grant per referenced org, one project-scope grant per
    # orgless project.
    org_refs: set[str] = {o["name"] for o in orgs if o.get("name")}
    orgless_projects: list[str] = []
    for proj in projects:
        oref = (proj["spec"].get("org_ref") or "").strip()
        if oref:
            org_refs.add(oref)
        elif proj.get("name"):
            orgless_projects.append(proj["name"])

    write_kernel = live.kernel.with_tenant(tenant) if tenant else live.kernel
    now = datetime.now(timezone.utc).isoformat()
    grants: list[dict[str, Any]] = []

    async def _grant(scope_type: str, scope_ref: str) -> None:
        name = _member_doc_name(user, scope_type, scope_ref)
        raw = {
            "apiVersion": _PORTFOLIO_API,
            "kind": "Membership",
            "metadata": {"name": name},
            "spec": {
                "user": user,
                "scope_type": scope_type,
                "scope_ref": scope_ref,
                "role": "owner",
                "status": "active",
                "invited_at": now,
            },
        }
        await write_kernel.write_document(
            sc, "Membership", name, raw, invalidate_mode="doc"
        )
        grants.append(
            {"scope_type": scope_type, "scope_ref": scope_ref, "role": "owner"}
        )

    for ref in sorted(org_refs):
        await _grant("org", ref)
    for ref in orgless_projects:
        await _grant("project", ref)

    return {
        "scope": sc,
        "tenant": tenant,
        "user": user,
        "provisioned": bool(grants),
        "grants": grants,
    }


async def board_summary_impl(
    live: LiveDna, scope: str, tenant: str | None = None, recent: int = 6
) -> dict[str, Any]:
    """A compact SDLC summary for a project's ``board_scope``: Story + Feature
    counts by status, totals, the FULL ``items`` list, and the ``recent`` newest.

    REUSES the shared SDLC read impl (``list_stories_impl``) for the Story
    projection + counts; Features come through the SAME ``_collect`` primitive
    (no reimplemented query). ``items`` is EVERY Story + Feature (newest-first) so
    the console renders a real board (all columns full), not a 6-item teaser;
    ``recent`` stays the ``recent``-sized head of that same list for back-compat.
    Ordering is by ``created_at`` (fail-soft — a missing/unparseable timestamp
    sorts last)."""

    def _counts(statuses: Any) -> dict[str, int]:
        c: dict[str, int] = {}
        for st in statuses:
            key = st or "unknown"
            c[key] = c.get(key, 0) + 1
        return c

    stories = (await list_stories_impl(live, scope=scope, tenant=tenant))["stories"]
    story_docs = await _collect(live, scope, "Story", tenant)
    feature_docs = await _collect(live, scope, "Feature", tenant)

    features = [
        {
            "name": d["name"],
            "title": d["spec"].get("title"),
            "status": d["spec"].get("status"),
        }
        for d in feature_docs
    ]

    dated: list[tuple[str, dict[str, Any]]] = []
    for kind, docs in (("Story", story_docs), ("Feature", feature_docs)):
        for d in docs:
            spec = d["spec"]
            dated.append(
                (
                    spec.get("created_at") or "",
                    {
                        "kind": kind,
                        "name": d["name"],
                        "title": spec.get("title"),
                        "status": spec.get("status"),
                        "created_at": spec.get("created_at"),
                    },
                )
            )
    dated.sort(key=lambda t: t[0], reverse=True)
    ordered = [item for _, item in dated]

    return {
        "scope": scope,
        "tenant": tenant,
        "counts": {
            "stories": _counts(s.get("status") for s in stories),
            "features": _counts(f["status"] for f in features),
        },
        "totals": {
            "stories": len(stories),
            "features": len(features),
            "total": len(stories) + len(features),
        },
        "items": ordered,
        "recent": ordered[: max(0, recent)],
    }


# The SDLC work-item Kinds a board card can point at, probed in this order when
# the caller does not pin a ``kind`` (Story/Feature dominate the board; the rest
# are reachable so a drawer over any work item resolves).
_BOARD_ITEM_KINDS: tuple[str, ...] = ("Story", "Feature", "Epic", "Issue", "Spike")


class BoardItemNotFound(LookupError):
    """The requested board work-item is absent for this (scope, tenant)."""


def _work_item_surface(
    kind: str, name: str, scope: str, tenant: str | None, raw: dict[str, Any]
) -> dict[str, Any]:
    """Project a full SDLC work-item doc onto the console's item-detail surface —
    the whole thing the drawer renders (description, AC/DoD, status, timeline,
    feature/epic refs, produces). No reshaping of the nested lists: AC/DoD entries
    and timeline events pass through verbatim so the UI can render checkboxes +
    an activity feed."""
    spec = raw.get("spec") or {}
    return {
        "scope": scope,
        "tenant": tenant,
        "kind": kind,
        "name": name,
        "title": spec.get("title"),
        "status": spec.get("status"),
        "description": spec.get("description"),
        "priority": spec.get("priority"),
        "labels": list(spec.get("labels") or []),
        "feature": spec.get("feature"),
        "epic": spec.get("epic"),
        "reporter": spec.get("reporter"),
        "business_value": spec.get("business_value"),
        "acceptance_criteria": list(spec.get("acceptance_criteria") or []),
        "definition_of_done": list(spec.get("definition_of_done") or []),
        "timeline": list(spec.get("timeline") or []),
        "produces": list(spec.get("produces") or []),
        "created_at": spec.get("created_at"),
        "updated_at": spec.get("updated_at"),
        "closed_at": spec.get("closed_at"),
    }


async def board_item_impl(
    live: LiveDna, scope: str, name: str, tenant: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """One board work-item's FULL doc by ``name`` — the console's item-detail
    drawer. Reuses the SAME ``kernel.get_document`` doc-read primitive
    ``get_adr_impl`` uses (no new query logic): with an explicit ``kind`` it reads
    that one Kind; otherwise it probes the SDLC work-item Kinds
    (:data:`_BOARD_ITEM_KINDS`) and returns the first match. Tenant-aware — a
    tenant sees the shared base plus its OWN overlay only. Raises
    :class:`BoardItemNotFound` when ``name`` is unknown for this (scope, tenant).
    """
    candidates = [kind] if kind else list(_BOARD_ITEM_KINDS)
    for k in candidates:
        raw = await live.kernel.get_document(scope, k, name, tenant=tenant)
        if raw is not None:
            return _work_item_surface(k, name, scope, tenant, raw)
    raise BoardItemNotFound(
        f"work-item {name!r} not found in scope {scope!r}"
        + (f" (kind={kind})" if kind else "")
        + (f" (tenant={tenant})" if tenant else "")
    )


# ── memory (declarative recall) ────────────────────────────────────────────


def _resolve_memory_target(
    live: LiveDna, scope: str | None, tenant: str | None,
    memory_scope: str, oid: str | None, family: str | None = None,
) -> tuple[str, str | None]:
    """Resolve the ``(scope, tenant)`` a memory op runs against for the given
    :data:`~dna.memory.personal.MemoryScope` (ADR-personal-memory §3.3 / §5).

    * ``personal`` → ``tenant = personal:<oid>`` (oid resolved SERVER-SIDE by the
      surface, fail-closed on missing identity), and the scope is PINNED to the
      shared **base** scope (``live.base_scope``) so recall UNIONs the base ``''``
      ``_lib`` defaults (ratified #4) rather than a workspace's data — the personal
      partition is workspace-independent (the same partition in every workspace +
      client). A caller-passed ``scope`` is deliberately IGNORED here (i-069):
      every personal WRITE lands at ``base_scope`` (this same resolver), so a
      personal READ that honored a forwarded workspace scope (e.g. the console's
      ``tenant-<ws>`` — the 0.25.0 ``GET /v1/memories/personal`` face forwards its
      ``scope`` query param) would target a (scope, partition) pair nothing ever
      writes to and return an honest-looking EMPTY result while the user's
      memories sit in ``base_scope`` — reads and writes must resolve the SAME
      home, structurally. (Local single-user flexibility is untouched: the CLI's
      ``--personal --scope X`` composes its tenant directly and never routes
      through this resolver.)
    * ``workspace`` (default) → the current behavior unchanged: scope defaults to
      ``default_scope(tenant)``, tenant is the resolved workspace id. A raw
      ``tenant`` naming the reserved ``personal:`` scheme is REJECTED here
      (INV-PERSONAL layer 4) — a workspace request may never name a personal
      partition directly.
    """
    from dna.memory.personal import (
        PERSONAL_SCOPE,
        assert_no_personal_override,
        resolve_memory_tenant,
    )

    if memory_scope == PERSONAL_SCOPE:
        tn = resolve_memory_tenant(
            memory_scope=PERSONAL_SCOPE, oid=oid, workspace_tenant=tenant,
            family=family,
        )
        return live.base_scope, tn
    assert_no_personal_override(tenant)
    return scope or live.default_scope(tenant), tenant


async def recall_impl(
    live: LiveDna, query: str, scope: str | None = None, k: int = 5,
    tenant: str | None = None, *, memory_scope: str = "workspace",
    oid: str | None = None,
    family: str | None = None,
) -> dict[str, Any]:
    """Recall DNA memory for ``query`` — hybrid + bi-temporal + retention
    re-scored when the search extra is present, honest lexical otherwise.
    Tenant-scoped when ``tenant`` is set (the auth bridge injects it).

    ``memory_scope="personal"`` recalls the caller's OWN private partition
    (``personal:<oid>``, oid server-derived) unioned with the base ``_lib``
    defaults — never any workspace's memory (ADR-personal-memory)."""
    from dna.memory import recall
    from dna.memory.verbs import MEMORY_KINDS

    sc, tenant = _resolve_memory_target(live, scope, tenant, memory_scope, oid, family)
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
    kind: str = "Engram",
    area: str = "general",
    affect: str = "triumph",
    tags: list[str] | None = None,
    owner: str = "mcp",
    tenant: str | None = None,
    *,
    memory_scope: str = "workspace",
    oid: str | None = None,
    family: str | None = None,
) -> dict[str, Any]:
    """Persist a memory Kind (deterministically enriched + indexed) — mirrors
    ``dna memory remember``. Written into the tenant overlay when ``tenant`` is
    set (the auth bridge injects it).

    ``memory_scope="personal"`` writes to the caller's OWN private partition
    (``personal:<oid>``, oid server-derived) — "remember privately", never shared
    with the workspace (ADR-personal-memory)."""
    from dna.memory import remember

    sc, tenant = _resolve_memory_target(live, scope, tenant, memory_scope, oid, family)
    name = _slug(summary)
    spec: dict[str, Any] = {"summary": summary}
    if kind == "Engram":
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
    tenant: str | None = None, *, memory_scope: str = "workspace",
    oid: str | None = None,
    family: str | None = None,
) -> dict[str, Any]:
    """Deterministic memory consolidation pass (Ebbinghaus retention). With
    ``apply=True`` stale memories are soft-forgotten (bi-temporal, never
    deleted). Mirrors ``dna memory consolidate``.

    ``memory_scope="personal"`` consolidates ONLY the caller's personal partition
    (``personal:<oid>``) — never touches workspace memory (ADR-personal-memory §4)."""
    from dna.memory import consolidate

    sc, tenant = _resolve_memory_target(live, scope, tenant, memory_scope, oid, family)
    return await consolidate(live.kernel, sc, apply=apply, tenant=tenant)


async def import_memories_impl(
    live: LiveDna,
    docs: list[dict[str, Any]],
    *,
    as_mode: str = "both",
    dedupe: str = "id",
    scope: str | None = None,
    tenant: str | None = None,
    memory_scope: str = "workspace",
    oid: str | None = None,
    family: str | None = None,
) -> dict[str, Any]:
    """Ingest already-parsed MIF Memory Units — mirrors ``dna memory import``.

    Thin: it resolves the ``(scope, tenant)`` target for the requested
    :data:`~dna.memory.personal.MemoryScope` and hands off to the ONE write
    pipeline, :func:`dna.memory.verbs.import_mif_docs`, which the CLI calls too.

    ``memory_scope="personal"`` imports into the caller's OWN private partition
    (``personal:<oid>``, oid derived SERVER-SIDE by the face — never a caller
    argument, INV-PERSONAL layer 1) — "your memory, yours", never a shared
    partition. ``_resolve_memory_target`` fails closed on a missing identity and
    rejects a raw ``personal:`` tenant override (layer 4).
    """
    from dna.memory.verbs import import_mif_docs

    sc, tenant = _resolve_memory_target(live, scope, tenant, memory_scope, oid, family)
    return await import_mif_docs(
        live.kernel, sc, docs, as_mode=as_mode, dedupe=dedupe, tenant=tenant
    )


async def list_memories_impl(
    live: LiveDna, scope: str | None = None, kind: str = "Engram",
    tenant: str | None = None, *, memory_scope: str = "workspace",
    oid: str | None = None,
    family: str | None = None,
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
    disappears from BOTH surfaces, never a ghost.

    Each item carries ``personal: bool`` (i-068) — the per-ITEM flag telling
    whether it resolves from the caller's ``personal:<oid>`` partition rather
    than the shared base a personal read unions with (same predicate recall's
    hits use, ``dna.memory.verbs.is_personal_doc``); always ``False`` on a
    workspace read."""
    from dna.memory.decay import currently_valid
    from dna.memory.verbs import is_personal_doc, memory_created_at

    sc, tenant = _resolve_memory_target(live, scope, tenant, memory_scope, oid, family)
    memories: list[dict[str, Any]] = []
    for d in await _collect(live, sc, kind, tenant):
        spec = d["spec"]
        if not currently_valid(spec.get("valid_to")):
            continue  # forgotten / superseded — never surfaced (mirrors recall).
        memories.append(
            {
                "name": d["name"],
                "summary": spec.get("summary"),
                "area": spec.get("area"),
                "tags": list(spec.get("tags") or []),
                "affect": spec.get("affect"),
                # Engram stamps ``created_at`` (== ``valid_from`` seed); the
                # shared helper falls back to the reconsolidation timeline.
                "created_at": memory_created_at(spec),
                "personal": await is_personal_doc(
                    live.kernel, sc, kind, d["name"], spec, tenant,
                ),
            }
        )
    memories.sort(key=lambda m: (m.get("created_at") or ""), reverse=True)
    return {"scope": sc, "memories": memories}


async def forget_impl(
    live: LiveDna, name: str, scope: str | None = None,
    kind: str = "Engram", tenant: str | None = None,
    *, memory_scope: str = "workspace", oid: str | None = None,
    family: str | None = None,
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

    sc, tenant = _resolve_memory_target(live, scope, tenant, memory_scope, oid, family)
    try:
        out = await forget(live.kernel, sc, name, kind=kind, tenant=tenant)
    except KeyError:
        return {"kind": kind, "name": name, "forgotten": False}
    return {"kind": kind, "name": name, "forgotten": not out["already_forgotten"]}


# ── cloud: the billing→enforcement bridge write (AccountPlan) ───────────────

# **The subscription belongs to the BILLING ACCOUNT, not to a workspace.** One
# AccountPlan doc covers EVERY workspace whose ``Workspace.account_id`` matches —
# so the second workspace is not a second charge, and billing writes ONE doc
# instead of fanning out one per workspace.
#
# Why that fan-out had to die rather than be implemented: workspace enumeration
# is by MEMBERSHIP, not ownership (``GET /v1/workspaces`` lists what you belong
# to). A biller fanning a paid tier across "the account's workspaces" would have
# swept in every workspace somebody ELSE founded and invited the payer into, and
# handed each one a tier its own account never bought. Fixing that needed a
# private ownership ledger — a fourth source of truth propping up a wrong model.
# Keying the plan on the account removes the question instead of answering it.
#
# AccountPlan is GLOBAL and _lib-resident (base only, no per-tenant overlay) — the
# same scope kernel.account_plan() reads _lib-direct, and it HAS to be: an account
# sits above every workspace it owns. The doc NAME equals the account_id so the
# read matches on spec.account_id, and the write is a natural upsert
# (write_document keys on name) → idempotent under Stripe's at-least-once
# retries. The account_id is opaque here — nothing parses or validates its shape.
_ACCOUNT_PLAN_SCOPE = "_lib"
_CLOUD_API = "github.com/ruinosus/dna/cloud/v1"


async def set_account_plan_impl(
    live: LiveDna,
    account_id: str,
    tier_id: str,
    *,
    source: str = "stripe",
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Upsert the AccountPlan Kind assigning ``account_id`` to ``tier_id`` — the
    billing→enforcement BRIDGE write that dna-cloud's Stripe webhook drives, so
    runtime quota follows billing state without a redeploy.

    **ONE write covers the whole account.** Every workspace carrying this
    ``account_id`` resolves to this plan (``kernel.account_for_workspace`` then
    ``kernel.account_plan`` in the MCP guard). There is nothing to keep in sync
    and no way for a workspace to end up on a stale tier, because no workspace
    holds a tier.

    GLOBAL / ``_lib``-direct: AccountPlan is not tenant-overlaid — the doc lives in
    ``_lib`` with its NAME == the account_id, so the guard's ``spec.account_id``
    lookup resolves it regardless of the caller's scope. The write is an UPSERT
    keyed on that name, so a redelivered Stripe event (at-least-once) converges on
    the same doc — idempotent by construction.

    Only the schema-allowed keys are written (the descriptor is
    ``additionalProperties: false``): ``account_id``/``tier_id`` (required),
    ``source``, ``status``, the two Stripe ids, and an ISO ``updated_at`` stamp.
    Optional refs are omitted when absent so a status-only transition never nulls a
    previously-recorded customer/subscription id — mirroring the portal store's
    COALESCE-on-update semantics."""
    account_id = (account_id or "").strip()
    tier_id = (tier_id or "").strip()
    if not account_id:
        raise ValueError("account_id is required")
    if not tier_id:
        raise ValueError("tier_id is required")

    spec: dict[str, Any] = {
        "account_id": account_id,
        "tier_id": tier_id,
        "source": source,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if status:
        spec["status"] = status
    if stripe_customer_id:
        spec["stripe_customer_id"] = stripe_customer_id
    if stripe_subscription_id:
        spec["stripe_subscription_id"] = stripe_subscription_id

    raw = {
        "apiVersion": _CLOUD_API,
        "kind": "PlanBinding",
        "metadata": {"name": account_id},
        "spec": spec,
    }
    # GLOBAL kind → no tenant kwarg (a tenant on a GLOBAL write is rejected).
    await live.kernel.write_document(
        _ACCOUNT_PLAN_SCOPE, "PlanBinding", account_id, raw, invalidate_mode="doc"
    )
    return {
        "scope": _ACCOUNT_PLAN_SCOPE,
        "account_id": account_id,
        "tier_id": tier_id,
        "status": status,
    }


# ── workspace invites (ADR "Model B", F3 — the cross-org join) ──────────────
#
# The identity→workspace boundary writes: a workspace Owner/Admin invites a
# collaborator from ANY org by EMAIL (a pending WorkspaceMembership, oid unbound);
# the invitee's first VERIFIED sign-in BINDS their durable oid and flips it active.
# All three impls are GLOBAL / _lib-direct (WorkspaceMembership is the tenancy
# boundary — it lives ABOVE any single workspace, exactly like TenantPlan, so
# there is no `tenant` kwarg). The SECURITY decision (who may invite, which invite
# a sign-in may bind) is the pure `dna.tenancy` policy — these impls only
# authorize + persist through the SAME `kernel.write_document` funnel the seed uses.

_TENANT_API = "github.com/ruinosus/dna/tenant/v1"
_WORKSPACE_SCOPE = "_lib"
# The workspace-level role ladder (the WorkspaceMembership descriptor enum).
_WS_ROLES = ("owner", "admin", "member", "guest")


class WorkspaceForbidden(Exception):
    """The actor lacks Owner/Admin on the workspace (RBAC deny → HTTP 403)."""


class WorkspaceLastOwner(Exception):
    """The revoke target is the workspace's SOLE active owner — revoking it would
    orphan the workspace, so it is refused (fail-closed → HTTP 409)."""


class WorkspaceMemberNotFound(LookupError):
    """The revoke target holds no WorkspaceMembership in this workspace — a clear
    no-op (→ HTTP 404)."""


def _ws_member_surface(spec: dict[str, Any]) -> dict[str, Any]:
    """Project a WorkspaceMembership ``spec`` to the wire shape the portal reads
    (the SAME field set ``list_workspace_members_impl`` returns, plus the
    ``workspace_id``)."""
    return {
        "workspace_id": spec.get("workspace_id"),
        "identity_email": spec.get("identity_email"),
        "identity_oid": spec.get("identity_oid"),
        "role": spec.get("role"),
        "status": spec.get("status"),
        "bound": bool(spec.get("identity_oid")),
        "invited_by": spec.get("invited_by"),
        "invited_at": spec.get("invited_at"),
        "accepted_at": spec.get("accepted_at"),
    }


async def _workspace_grants(live: LiveDna) -> tuple[list[dict], list[Any]]:
    """The RAW WorkspaceMembership rows AND their pure-policy views, in the same
    order (so an index/object correlates one to the other)."""
    from dna.tenancy import Membership

    raw = await live.kernel.workspace_memberships()
    memberships = [Membership.from_spec(g.get("spec") or {}) for g in raw]
    return raw, memberships


def _require_workspace_manage(
    actor: Any, workspace_id: str, memberships: list[Any], *, target_role: str | None = None
) -> str:
    """RBAC gate on a workspace membership WRITE: ``actor`` (a verified
    :class:`dna.tenancy.Identity`) must hold an ACTIVE Owner/Admin grant in
    ``workspace_id``; only an Owner may grant/seed the Owner role. Returns the
    actor's role. Raises :class:`WorkspaceForbidden` (fail-closed)."""
    from dna.tenancy import can_invite, role_in_workspace

    actor_role = role_in_workspace(actor, workspace_id, memberships)
    if not can_invite(actor_role):
        raise WorkspaceForbidden(
            f"actor {(getattr(actor, 'email', None) or '<anonymous>')!r} is not an "
            f"Owner/Admin of workspace {workspace_id!r} (has "
            f"{actor_role or 'no membership'}) — cannot manage members"
        )
    if target_role == "owner" and actor_role != "owner":
        raise WorkspaceForbidden("only an Owner may grant the Owner role")
    return actor_role


def _require_workspace_membership(
    actor: Any, workspace_id: str, memberships: list[Any], action: str
) -> str:
    """The BASELINE Model B authorization: ``actor`` must hold an ACTIVE grant in
    ``workspace_id`` — any role. Returns that role; raises
    :class:`WorkspaceForbidden` (fail-closed → 403) otherwise.

    Distinct from :func:`_require_workspace_manage`, which additionally demands
    Owner/Admin. Membership writes need the stronger gate; creating content
    INSIDE a workspace you belong to needs only this one."""
    from dna.tenancy import role_in_workspace

    role = role_in_workspace(actor, workspace_id, memberships)
    if not role:
        raise WorkspaceForbidden(
            f"identity {(getattr(actor, 'email', None) or '<anonymous>')!r} holds no "
            f"active WorkspaceMembership in workspace {workspace_id!r} — "
            f"cannot {action}"
        )
    return role


async def invite_member_impl(
    live: LiveDna,
    workspace_id: str,
    email: str,
    role: str,
    *,
    actor_claims: dict[str, Any] | None,
) -> dict[str, Any]:
    """Create (or re-issue) an invite — a ``pending`` :class:`WorkspaceMembership`
    keyed by the invited EMAIL, ``identity_oid`` null (bound later on accept).

    RBAC: the ``actor`` (derived from the caller's VERIFIED token claims) must be
    Owner/Admin of ``workspace_id``; only an Owner may invite an Owner. Idempotent
    upsert on the deterministic ``{workspace_id}--{email}`` doc name: re-inviting an
    existing member preserves their bound ``oid``/``status`` (a role change, not a
    downgrade to pending), while inviting a fresh email creates the pending grant.
    GLOBAL write into ``_lib`` (no tenant binding)."""
    from dna.tenancy import identity_from_token, normalize_email, workspace_membership_name

    workspace_id = (workspace_id or "").strip()
    email = normalize_email(email)
    role = (role or "").lower().strip()
    if not workspace_id:
        raise ValueError("workspace_id is required")
    if not email:
        raise ValueError("email is required")
    if role not in _WS_ROLES:
        raise ValueError(f"unknown role {role!r} — expected one of {list(_WS_ROLES)}")

    actor = identity_from_token(actor_claims or {})
    _, memberships = await _workspace_grants(live)
    _require_workspace_manage(actor, workspace_id, memberships, target_role=role)

    name = workspace_membership_name(workspace_id, email)
    existing = await live.kernel.get_document(_WORKSPACE_SCOPE, "WorkspaceMembership", name)
    ex_spec = (existing or {}).get("spec") or {}
    now = datetime.now(timezone.utc).isoformat()
    # Preserve an already-bound member's identity + lifecycle (re-invite = role
    # change, never a re-open of an accepted grant); a fresh invite is pending.
    spec = {
        "workspace_id": workspace_id,
        "identity_email": email,
        "identity_oid": ex_spec.get("identity_oid"),
        "identity_tid": ex_spec.get("identity_tid"),
        "role": role,
        "status": ex_spec.get("status") or "pending",
        "invited_by": getattr(actor, "email", None) or ex_spec.get("invited_by"),
        "invited_at": ex_spec.get("invited_at") or now,
        "accepted_at": ex_spec.get("accepted_at"),
    }
    raw = {
        "apiVersion": _TENANT_API,
        "kind": "WorkspaceMembership",
        "metadata": {"name": name},
        "spec": spec,
    }
    # GLOBAL kind → no tenant kwarg (a tenant on a GLOBAL write is rejected).
    await live.kernel.write_document(
        _WORKSPACE_SCOPE, "WorkspaceMembership", name, raw, invalidate_mode="doc"
    )
    return {
        "workspace_id": workspace_id,
        "invite": {
            "identity_email": email,
            "role": role,
            "status": spec["status"],
            "invited_by": spec["invited_by"],
            "bound": bool(spec["identity_oid"]),
        },
    }


async def list_workspace_members_impl(
    live: LiveDna,
    workspace_id: str,
    *,
    actor_claims: dict[str, Any] | None = None,
    actor: Any = None,
) -> dict[str, Any]:
    """List a workspace's members (grants) — the Membros panel read. RBAC: the
    actor (verified token claims, or a pre-built :class:`dna.tenancy.Identity` for
    a GET) must be Owner/Admin of ``workspace_id``. Projects each grant to
    email/role/status/bound + invite audit. GLOBAL / ``_lib``-direct."""
    from dna.tenancy import identity_from_token

    workspace_id = (workspace_id or "").strip()
    if not workspace_id:
        raise ValueError("workspace_id is required")
    if actor is None:
        actor = identity_from_token(actor_claims or {})
    raw_grants, memberships = await _workspace_grants(live)
    _require_workspace_manage(actor, workspace_id, memberships)

    members = []
    for g in raw_grants:
        spec = g.get("spec") or {}
        if (spec.get("workspace_id") or "") != workspace_id:
            continue
        members.append({
            "identity_email": spec.get("identity_email"),
            "role": spec.get("role"),
            "status": spec.get("status"),
            "bound": bool(spec.get("identity_oid")),
            "invited_by": spec.get("invited_by"),
            "invited_at": spec.get("invited_at"),
            "accepted_at": spec.get("accepted_at"),
        })
    members.sort(key=lambda m: (m.get("identity_email") or ""))
    return {"workspace_id": workspace_id, "members": members}


async def accept_invites_impl(
    live: LiveDna, claims: dict[str, Any] | None
) -> dict[str, Any]:
    """Accept every pending invite a VERIFIED sign-in claims — the cross-org join's
    second phase. Matches the token's VERIFIED email against unbound grants,
    BINDS the durable ``oid`` (+ ``tid`` provenance), and flips ``pending→active``
    (stamping ``accepted_at``). An already-active-but-unbound grant (the F1 seed)
    just captures its ``oid``.

    The security decision is the pure ``dna.tenancy.bindable_invites_for``
    (verified-email-only matching; an oid-bound grant is never returned, so it can
    NOT be hijacked by a different oid; no oid / unverified email → nothing bound).
    This impl only persists that decision, GLOBAL into ``_lib``. Idempotent: a
    re-sign-in after acceptance finds nothing unbound left to bind."""
    from dna.tenancy import (
        bindable_invites_for,
        identity_from_token,
        verified_email_from_claims,
        workspace_membership_name,
    )

    identity = identity_from_token(claims or {})
    verified_email = verified_email_from_claims(claims or {})
    raw_grants, memberships = await _workspace_grants(live)
    to_bind = bindable_invites_for(identity, verified_email, memberships)
    bind_ids = {id(m) for m in to_bind}

    accepted: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for g, m in zip(raw_grants, memberships):
        if id(m) not in bind_ids:
            continue
        spec = dict(g.get("spec") or {})
        was_pending = (spec.get("status") or "pending") == "pending"
        spec["identity_oid"] = identity.oid
        spec["identity_tid"] = identity.tid or spec.get("identity_tid")
        spec["status"] = "active"
        spec["accepted_at"] = now if was_pending else (spec.get("accepted_at") or now)
        name = workspace_membership_name(spec["workspace_id"], spec["identity_email"])
        raw = {
            "apiVersion": _TENANT_API,
            "kind": "WorkspaceMembership",
            "metadata": {"name": name},
            "spec": spec,
        }
        await live.kernel.write_document(
            _WORKSPACE_SCOPE, "WorkspaceMembership", name, raw, invalidate_mode="doc"
        )
        accepted.append({
            "workspace_id": spec["workspace_id"],
            "role": spec.get("role"),
            "activated": was_pending,
        })
    return {
        "identity_oid": identity.oid,
        "identity_email": verified_email,
        "accepted": accepted,
    }


def assert_may_bootstrap_workspace(
    identity: Any, workspace_id: str, memberships: Any = ()
) -> None:
    """Entitlement gate for owner-bootstrap — **ONE rule now, and it is the
    security one.**

    History (read it, it is the point of this function). This gate used to be a
    single equality ``identity.tid == workspace_id`` doing TWO jobs at once:

    * **Rule 1 — zero-migration.** Workspace #1's id *was* the founder's Azure
      ``tid``, so rows keyed ``tenant == tid`` were already that workspace's
      data. **This rule is now DEAD.** Product decision **D5** gives every
      workspace a server-minted id and demotes the ``tid`` to a mere fact of
      authentication. The founder's workspace keeps working not through any
      special case but because its id is simply one more opaque string.
    * **Rule 2 — anti-takeover.** A verified identity must never seize a
      workspace by racing its legitimate owner to the bootstrap. **This rule
      survives, and it now has an implementation of its OWN** rather than being
      a side-effect of Rule 1.

    **The new entitlement rule, stated without the word ``tid``:**

        You may bootstrap a workspace **iff you already hold an ACTIVE
        WorkspaceMembership in it.**

    That reads circular until you notice what changed around it: bootstrap NO
    LONGER CREATES ANYTHING out of nothing. Creation became an explicit,
    separate act — :func:`create_workspace_impl` (``POST /v1/workspaces``) mints
    the id AND its first owner grant together, and the id is minted **by the
    server**, so a caller cannot name a workspace into existence. Takeover is
    therefore impossible *by construction* rather than by comparison: there is
    no unclaimed-but-nameable id left to race for. What remains for
    provision-owner is the idempotent re-login no-op (bind/repair an existing
    grant), and that legitimately requires the grant to already exist.

    Fail-closed by default: ``memberships`` defaults to empty, so a caller that
    forgets to pass the grants denies rather than allows.

    Args:
        identity: the VERIFIED caller (:class:`dna.tenancy.Identity`).
        workspace_id: the workspace being bootstrapped.
        memberships: every :class:`dna.tenancy.Membership` in the source
            (unfiltered — the match is done here, on the verified identity).

    Raises:
        WorkspaceForbidden: the caller holds no active membership here.
    """
    from dna.tenancy import active_workspaces_for

    if workspace_id in active_workspaces_for(identity, list(memberships or ())):
        return
    # Deny. Name the CALLER, not only the defended target, so the 403 is
    # diagnosable in a log: email + the durable oid, plus the tid as PROVENANCE
    # (it is reported, never consulted — it decides nothing here any more).
    raise WorkspaceForbidden(
        f"identity {(getattr(identity, 'email', None) or '<anonymous>')!r} "
        f"(oid={getattr(identity, 'oid', None)!r}, "
        f"tid={getattr(identity, 'tid', None)!r} — provenance only, not consulted) "
        f"holds no active WorkspaceMembership in workspace {workspace_id!r}; "
        f"provision-owner cannot create a workspace (use POST /v1/workspaces, "
        f"which mints its own id) — owner bootstrap denied"
    )


async def provision_workspace_owner_impl(
    live: LiveDna,
    workspace_id: str,
    claims: dict[str, Any] | None,
) -> dict[str, Any]:
    """Re-login reconciliation for a workspace the caller ALREADY belongs to.

    **This use-case no longer creates anything from nothing** — decision D5 took
    creation away from it and gave it to :func:`create_workspace_impl`
    (``POST /v1/workspaces``), which mints the id server-side. What survives here
    is the idempotent, safe-to-call-on-every-dashboard-load half:

    * the caller holds an ACTIVE grant here → NO-OP returning that grant
      (``already_member``), plus a back-fill of the ``Workspace`` identity doc if
      (and only if) an owner grant exists while the doc does not — the repair path
      for a grant seeded before its Workspace doc was written;
    * the caller holds NO active grant here → :class:`WorkspaceForbidden` (403).
      There is nothing legitimate left for a non-member to bootstrap: an id it
      does not belong to either does not exist (ids are generated and
      unguessable) or belongs to somebody else.

    **Entitlement guard** — :func:`assert_may_bootstrap_workspace`, which carries
    the full contract and the history of why it used to compare ``tid``. It no
    longer mentions ``tid`` at all: entitlement is "I hold an active membership
    here". The anti-takeover property it used to provide as a side-effect is now
    structural — nobody can name a workspace into existence.

    Naming note: the route keeps the ``provision-owner`` name for wire
    compatibility with the deployed portal, which calls it on every sign-in.

    GLOBAL / ``_lib``-direct (Workspace + WorkspaceMembership are the tenancy
    boundary — no ``tenant`` kwarg)."""
    from dna.tenancy import (
        account_id_from_claims,
        identity_from_token,
        membership_matches_identity,
        normalize_email,
    )

    workspace_id = (workspace_id or "").strip()
    if not workspace_id:
        raise ValueError("workspace_id is required")

    identity = identity_from_token(claims or {})
    email = normalize_email(identity.email)
    if not email:
        raise ValueError("the verified identity must carry an email claim")
    if not identity.oid:
        raise ValueError("the verified identity must carry an oid claim")

    raw_grants, memberships = await _workspace_grants(live)

    # Entitlement gate — the ONE rule: an active membership here. Fail-closed;
    # raises WorkspaceForbidden (403) for everyone else. Read its docstring
    # before touching it: it is the anti-takeover surface.
    assert_may_bootstrap_workspace(identity, workspace_id, memberships)

    spec: dict[str, Any] = {}
    role = None
    for g, m in zip(raw_grants, memberships):
        if m.workspace_id == workspace_id and membership_matches_identity(m, identity):
            spec = g.get("spec") or {}
            role = m.role
            break

    # i-058 ADOPTION: a workspace born BEFORE the definitions base existed
    # declares its scope's ``parent_scope`` on the next sign-in — the idempotent
    # path that retrofits inheritance onto existing workspaces with zero
    # operational steps (deploy with DNA_WORKSPACE_DEFINITIONS_BASE set; the
    # next dashboard load adopts). Intent-preserving: an operator-authored
    # parent_scope is never overwritten, the vendor's base scope is never
    # touched (see ensure_workspace_scope_genome). Fail-soft — a hiccup here
    # must not fail a sign-in — but LOUD, because a silently missing Genome is
    # the bootstrap hole coming back.
    if live.workspace_definitions_base:
        try:
            await ensure_workspace_scope_genome(live, workspace_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "provision-owner: definitions-base adoption failed for "
                "workspace %r (scope %r, base %r) — the workspace scope still "
                "has no declared parent: %s",
                workspace_id, live.default_scope(workspace_id),
                live.workspace_definitions_base, e,
            )

    # Repair, never create: an OWNER whose Workspace identity doc is missing gets
    # it written. Gated on the owner grant, so this can never mint a workspace for
    # a caller who does not already own one.
    workspace_created = False
    if role == "owner" and not await _get_workspace_doc(live, workspace_id):
        now = datetime.now(timezone.utc).isoformat()
        await live.kernel.write_document(
            _WORKSPACE_SCOPE, "Workspace", workspace_id,
            {
                "apiVersion": _TENANT_API,
                "kind": "Workspace",
                "metadata": {"name": workspace_id},
                "spec": {
                    "workspace_id": workspace_id,
                    "name": email,  # a sensible default display name; editable.
                    "slug": _email_slug(email),
                    "created_by": email,
                    "created_at": now,
                    # This repair path only ever runs for an OWNER whose identity
                    # doc is missing, so the caller IS the account that owns the
                    # workspace — stamping it here is the same act creation would
                    # have performed. None when the sign-in has no account claim
                    # ⇒ the Free floor, never a guess.
                    "account_id": account_id_from_claims(claims or {}),
                },
            },
            invalidate_mode="doc",
        )
        workspace_created = True

    return {
        "workspace_id": workspace_id,
        "provisioned": False,
        "reason": "already_member",
        "workspace_created": workspace_created,
        "membership": _ws_member_surface(spec),
    }


# ── workspace CREATION — the act that was missing (decision D5) ──────────────
#
# Before this, a Workspace could only be born from a seed script: the portal's
# "workspace" was a by-product of signing in and its id WAS the Azure `tid`. That
# is the whole reason `assert_may_bootstrap_workspace` had to compare tids. With
# an explicit creation act the id is minted here, server-side, and the takeover
# question stops being a comparison and becomes a structural impossibility.

# The generated id's shape. `ws-` + 24 chars of lowercase RFC-4648 base32 over 15
# random bytes = 120 bits of entropy, alphabet [a-z2-7]. Chosen because the id is
# used verbatim in FOUR places that each constrain it:
#   * the kernel `tenant` COLUMN value (must be a plain, stable string);
#   * a FILENAME — `_lib/workspaces/<id>.yaml` (no `/`, no case-collisions on a
#     case-insensitive filesystem → lowercase-only, hence base32 over base64);
#   * a SCOPE name — `tenant-<id>` (see LiveDna.default_scope);
#   * a URL path segment — `/w/<id>/mcp` (must need no percent-encoding).
# Opaque: it encodes nothing (no email, no tid, no timestamp, no counter), so it
# leaks no tenancy information and cannot be enumerated. Unguessable at 120 bits,
# which is what lets the entitlement rule be "membership" instead of "id equality".
_WORKSPACE_ID_PREFIX = "ws-"
_WORKSPACE_ID_BYTES = 15


def new_workspace_id() -> str:
    """Mint a fresh, opaque, unguessable ``workspace_id`` (see the note above).

    The server ALWAYS calls this; a client-supplied id is never honoured. That is
    not input validation, it is the anti-takeover mechanism: an id nobody can
    name is an id nobody can race you to."""
    import base64
    import secrets

    raw = base64.b32encode(secrets.token_bytes(_WORKSPACE_ID_BYTES))
    return _WORKSPACE_ID_PREFIX + raw.decode("ascii").rstrip("=").lower()


def slugify(value: str) -> str:
    """Fold a display name into a URL-safe handle (``[a-z0-9-]``, no run of
    hyphens, trimmed). Returns ``""`` when nothing usable survives — the caller
    decides the fallback, so this never invents a name."""
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return re.sub(r"-{2,}", "-", text)


async def _get_workspace_doc(live: LiveDna, workspace_id: str) -> dict[str, Any] | None:
    """Read one ``Workspace`` doc, tolerating a source that has never had a
    ``_lib`` scope (a brand-new install) — absent scope means 'no workspace'."""
    try:
        return await live.kernel.get_document(
            _WORKSPACE_SCOPE, "Workspace", workspace_id
        )
    except (FileNotFoundError, ValueError):
        return None


async def _all_workspaces(live: LiveDna) -> list[dict[str, Any]]:
    """Every ``Workspace`` doc in the source (raw rows). Fail-soft to ``[]`` — a
    source with no ``_lib`` yet simply has no workspaces."""
    try:
        return await live.kernel.workspaces()
    except Exception:  # noqa: BLE001 — an absent registry is 'no workspaces'.
        return []


async def _unique_workspace_slug(live: LiveDna, wanted: str) -> str:
    """``wanted``, suffixed ``-2``, ``-3``… until no existing Workspace claims it.

    Slug is PRESENTATION over a stable id (the GitHub model), so a collision is
    resolved by decorating the slug — never by touching the id, and never by
    refusing the creation."""
    taken = {
        ((row.get("spec") or {}).get("slug") or "").lower()
        for row in await _all_workspaces(live)
    }
    if wanted not in taken:
        return wanted
    n = 2
    while f"{wanted}-{n}" in taken:
        n += 1
    return f"{wanted}-{n}"


#: The core DNA apiVersion — the Genome a workspace scope is born with.
_DNA_API = "github.com/ruinosus/dna/v1"


async def ensure_workspace_scope_genome(
    live: LiveDna, workspace_id: str,
) -> dict[str, Any]:
    """Declare the workspace scope's ``parent_scope`` = the configured
    definitions base — **the birth certificate of the overlay thesis** (i-058).

    A Model-B workspace routes to the scope ``tenant-<id>``, which is born
    EMPTY and unreachable by any boot seed (workspaces are born after boot).
    With no parent declared, every definition surface over it (list_agents /
    compose_prompt / get_* / query) had "no rest to inherit". This writes the
    scope's Genome declaring ``parent_scope = live.workspace_definitions_base``
    so the EXISTING resolution chain (``compute_resolution_chain`` — the one
    mechanism behind query, resolve_document, get_document and the eager MI)
    delivers the host's curated definitions from the first request.

    Idempotent + intent-preserving, so it is safe on every create AND on every
    sign-in (the adoption path for workspaces born before the base existed):

    * no base configured (OSS / self-host) → NO-OP;
    * the workspace resolves to the VENDOR's base scope (multi-workspace off,
      or the vendor workspace itself) → NO-OP — never write a Genome into the
      host's own scope, and never declare a scope its own parent;
    * the scope's Genome already declares ANY ``parent_scope`` → NO-OP — an
      operator-authored parent wins over configuration;
    * Genome present without a parent → merged write (spec preserved);
    * Genome absent → a minimal Genome is written.

    Returns ``{"scope", "parent_scope", "written"}`` — ``written`` is True only
    when a doc was actually persisted this call.
    """
    base = (live.workspace_definitions_base or "").strip()
    scope = live.default_scope(workspace_id)
    if not base or scope == live.base_scope or scope == base:
        return {"scope": scope, "parent_scope": None, "written": False}

    try:
        existing = await live.kernel.get_document(scope, "Genome", scope)
    except (FileNotFoundError, ValueError):
        existing = None
    spec = dict((existing or {}).get("spec") or {})
    declared = spec.get("parent_scope")
    if existing is not None and isinstance(declared, str) and declared:
        return {"scope": scope, "parent_scope": declared, "written": False}

    spec["parent_scope"] = base
    meta = dict((existing or {}).get("metadata") or {})
    meta["name"] = scope
    await live.kernel.write_document(
        scope, "Genome", scope,
        {
            "apiVersion": (existing or {}).get("apiVersion") or _DNA_API,
            "kind": "Genome",
            "metadata": meta,
            "spec": spec,
        },
        invalidate_mode="doc",
    )
    return {"scope": scope, "parent_scope": base, "written": True}


async def adopt_workspace_scope_on_access(
    live: LiveDna, workspace_id: str | None,
) -> dict[str, Any] | None:
    """Adopt-on-access — the ROBUST trigger for i-058's definitions inheritance.

    Production taught the lesson: adoption wired ONLY to provision-owner is
    fragile by design — it depends on a portal navigation path nobody
    guaranteed (the dna-cloud call site was gated on a stale pre-D5 condition,
    so the founder used the portal for hours and no Genome was ever born).
    The robust place is the moment that CANNOT be skipped: **when a request
    resolves a workspace** (the MCP ``_guard`` bind / the REST workspace
    middleware). If that workspace's scope has no declared parent and a
    definitions base is configured, adopt it right there — the same request
    (compose/list) then already reads the inherited definitions, because the
    faces call this BEFORE the tool/route impl runs and
    :func:`ensure_workspace_scope_genome` writes with ``invalidate_mode="doc"``.

    Cheap by construction (this runs on EVERY guarded request):

    * no ``workspace_id`` / no configured base / a ``personal:`` partition /
      the vendor's own scope → an in-memory early return, no kernel touch;
    * ``live.adoption_probed`` memoizes every scope that already reached a
      stable state (parent declared — by us or by an operator — or exempt), so
      the steady-state cost is one set lookup;
    * a per-``live`` ``asyncio.Lock`` single-flights the first probe, so a
      burst of concurrent requests over a fresh scope yields ONE kernel write,
      never N (``ensure_workspace_scope_genome`` is idempotent anyway — the
      lock is about cost, the ensure is about correctness);
    * intent-preserving exactly like the ensure it wraps: an authored
      ``parent_scope`` is never overwritten, the vendor/base scope is never
      touched, and with no base configured NOTHING is written (OSS untouched).

    Fail-soft + loud: an adoption error must not fail the request that
    triggered it (the request proceeds against the unparented scope, exactly
    as before this feature), but it is logged as a warning AND the scope is
    NOT cached, so the next request retries instead of sealing the hole.

    Returns the :func:`ensure_workspace_scope_genome` result when the probe
    ran, ``None`` on every early return (cache hit / exempt / failure).
    """
    from dna.memory.personal import PERSONAL_TENANT_PREFIX

    if not workspace_id or not live.workspace_definitions_base:
        return None
    if workspace_id.startswith(PERSONAL_TENANT_PREFIX):
        return None  # personal partitions are people, not workspaces (ADR B1).
    scope = live.default_scope(workspace_id)
    if scope == live.base_scope or scope == live.workspace_definitions_base:
        return None  # the vendor's own scope is never touched (i-058 rule).
    if scope in live.adoption_probed:
        return None  # steady state: one set lookup, zero kernel reads.

    import asyncio

    if live.adoption_lock is None:
        live.adoption_lock = asyncio.Lock()
    async with live.adoption_lock:
        if scope in live.adoption_probed:  # lost the race to the first flight.
            return None
        try:
            result = await ensure_workspace_scope_genome(live, workspace_id)
        except Exception as e:  # noqa: BLE001 — fail-soft, retry next request.
            logger.warning(
                "adopt-on-access: definitions-base adoption failed for "
                "workspace %r (scope %r, base %r) — the request proceeds "
                "against the unparented scope and the NEXT request retries: %s",
                workspace_id, scope, live.workspace_definitions_base, e,
            )
            return None
        live.adoption_probed.add(scope)
        if result.get("written"):
            logger.info(
                "adopt-on-access: workspace %r scope %r adopted parent_scope=%r "
                "(i-058) — definitions inheritance is live from this request on",
                workspace_id, scope, result.get("parent_scope"),
            )
        return result


async def create_workspace_impl(
    live: LiveDna,
    name: str,
    claims: dict[str, Any] | None,
    *,
    slug: str | None = None,
) -> dict[str, Any]:
    """**Create a workspace and its first owner** — the act of creation that DNA
    Cloud was missing (decision D5). ``POST /v1/workspaces``.

    * the ``workspace_id`` is MINTED HERE (:func:`new_workspace_id`). There is no
      parameter for it and a client-supplied one is ignored by construction — the
      signature simply cannot receive it. This is what makes takeover impossible:
      you cannot claim an id you cannot name.
    * the caller's VERIFIED identity (oid + email, ``tid`` recorded as provenance
      only) becomes the workspace's ``owner``, ``status: active``, bound.
    * the workspace's ``account_id`` — WHICH BILLING ACCOUNT PAYS FOR IT — is
      stamped here from the verified account claim
      (:func:`dna.tenancy.account_id_from_claims`). This is the only moment it is
      ever written. Because the plan is keyed on the ACCOUNT, this workspace is
      instantly covered by whatever plan the account already has: a second
      workspace is not a second charge and needs no billing write at all. A
      sign-in with no resolvable account gets ``account_id: null`` → no
      AccountPlan → the Free floor (fail-closed).
    * ``slug`` defaults to a slugified ``name`` (falling back to the id when the
      name slugifies to nothing) and is made unique by suffixing.

    **Atomicity — what you actually get.** The kernel exposes no multi-document
    transaction, so this is NOT atomic; it is *ordered + compensated*:

    1. the ``Workspace`` doc is written first;
    2. then (when ``live.workspace_definitions_base`` is set) the workspace
       SCOPE's Genome declaring its ``parent_scope`` — the definitions-
       inheritance birth certificate (:func:`ensure_workspace_scope_genome`,
       i-058); if it fails, (1) is best-effort deleted and the error re-raised;
    3. then the owner ``WorkspaceMembership``;
    4. if (3) fails, (2) and (1) are best-effort DELETED and the error
       re-raised.

    The ordering is chosen so the surviving failure state is the harmless one. A
    Workspace with no owner grant is INERT: no identity resolves to it, it never
    appears in :func:`list_workspaces_impl` (which enumerates by membership), and
    nobody can adopt it — :func:`assert_may_bootstrap_workspace` requires a
    membership that does not exist, and its id is unguessable. Worst case it is
    unreferenced garbage under a name no one can type; the client just retries and
    gets a fresh id. The reverse order would leave a grant pointing at a workspace
    that does not exist — a ghost the caller can enumerate and read through, which
    is the strictly worse failure. If the compensating delete ALSO fails, the
    orphan simply persists; it is still inert.

    GLOBAL / ``_lib``-direct (no ``tenant`` kwarg — Workspace and
    WorkspaceMembership are the tenancy boundary, they cannot live inside it)."""
    from dna.tenancy import (
        account_id_from_claims,
        identity_from_token,
        normalize_email,
        workspace_membership_name,
    )

    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")

    identity = identity_from_token(claims or {})
    email = normalize_email(identity.email)
    if not email:
        raise ValueError("the verified identity must carry an email claim")
    if not identity.oid:
        raise ValueError("the verified identity must carry an oid claim")

    # The BILLING ACCOUNT, stamped ONCE, HERE, from the VERIFIED claims — the
    # only moment a workspace learns who pays for it. None is a legitimate answer
    # (the sign-in belongs to no billing account) and is written as null: that
    # workspace resolves to no AccountPlan and therefore to the Free floor. It is
    # deliberately NOT an error — refusing to create the workspace would lock out
    # every identity lane that has no account claim, and it is deliberately NOT
    # defaulted to anything, because every non-null default here is somebody
    # else's subscription.
    account_id = account_id_from_claims(claims or {})

    workspace_id = new_workspace_id()
    wanted = slugify(slug or name) or workspace_id
    slug_value = await _unique_workspace_slug(live, wanted)

    now = datetime.now(timezone.utc).isoformat()
    ws_raw = {
        "apiVersion": _TENANT_API,
        "kind": "Workspace",
        "metadata": {"name": workspace_id},
        "spec": {
            "workspace_id": workspace_id,
            "name": name,
            "slug": slug_value,
            "created_by": email,
            "created_at": now,
            "account_id": account_id,
        },
    }
    await live.kernel.write_document(
        _WORKSPACE_SCOPE, "Workspace", workspace_id, ws_raw, invalidate_mode="doc"
    )

    # i-058 — the scope is born declaring its parent (the definitions base),
    # so the first list_agents/compose over this workspace already inherits
    # the host's curated definitions. NO-OP when no base is configured.
    definitions: dict[str, Any] = {"scope": None, "parent_scope": None, "written": False}
    try:
        definitions = await ensure_workspace_scope_genome(live, workspace_id)
    except Exception:
        # Compensate: without its birth Genome the workspace would silently
        # re-open the bootstrap hole this feature closes — fail the creation
        # (the client retries and gets a fresh id), removing the litter.
        try:
            await live.kernel.delete_document(
                _WORKSPACE_SCOPE, "Workspace", workspace_id
            )
        except Exception:  # noqa: BLE001
            pass
        raise

    grant_name = workspace_membership_name(workspace_id, email)
    spec = {
        "workspace_id": workspace_id,
        "identity_email": email,
        "identity_oid": identity.oid,
        # PROVENANCE ONLY — recorded so an operator can see which Azure org the
        # creating sign-in came from. It authorizes nothing (decision D5).
        "identity_tid": identity.tid,
        "role": "owner",
        "status": "active",
        "invited_by": None,
        "invited_at": now,
        "accepted_at": now,
    }
    try:
        await live.kernel.write_document(
            _WORKSPACE_SCOPE, "WorkspaceMembership", grant_name,
            {
                "apiVersion": _TENANT_API,
                "kind": "WorkspaceMembership",
                "metadata": {"name": grant_name},
                "spec": spec,
            },
            invalidate_mode="doc",
        )
    except Exception:
        # Compensate: an ownerless Workspace is inert, but leaving it is still
        # litter. Best-effort — a failed rollback must not mask the real error.
        if definitions.get("written"):
            try:
                await live.kernel.delete_document(
                    definitions["scope"], "Genome", definitions["scope"]
                )
            except Exception:  # noqa: BLE001
                pass
        try:
            await live.kernel.delete_document(
                _WORKSPACE_SCOPE, "Workspace", workspace_id
            )
        except Exception:  # noqa: BLE001
            pass
        raise

    return {
        "workspace_id": workspace_id,
        "name": name,
        "slug": slug_value,
        "created_by": email,
        "created_at": now,
        # Surfaced (never accepted) so a caller can SEE which billing account it
        # landed in — null means "no account ⇒ Free floor", which is a fact the
        # portal must be able to show rather than discover from a quota denial.
        "account_id": account_id,
        "role": "owner",
        "membership": _ws_member_surface(spec),
    }


async def list_workspaces_impl(
    live: LiveDna, claims: dict[str, Any] | None
) -> dict[str, Any]:
    """**Enumerate the workspaces the caller belongs to** — ``GET /v1/workspaces``,
    the workspace switcher's data source (its absence was recorded in
    ``dna-cloud/lib/copilot.ts``).

    Membership is the enumeration key, never the ``tid``: a workspace is listed
    iff the VERIFIED identity holds an ACTIVE grant in it (pending invites are not
    listed — they authorize nothing). A grant whose ``Workspace`` doc is missing is
    still listed, with ``name``/``slug`` ``None`` — the id is a fact, the display
    name is not, and inventing one would be fabricating data.

    Sorted by display name (ids last, so an unnamed workspace does not sit on
    top). Read-only, GLOBAL / ``_lib``-direct."""
    from dna.tenancy import identity_from_token, membership_matches_identity

    identity = identity_from_token(claims or {})
    _, memberships = await _workspace_grants(live)
    docs = {
        ((row.get("spec") or {}).get("workspace_id") or ""): (row.get("spec") or {})
        for row in await _all_workspaces(live)
    }

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for m in memberships:
        if not m.workspace_id or m.workspace_id in seen:
            continue
        if not membership_matches_identity(m, identity):
            continue
        seen.add(m.workspace_id)
        spec = docs.get(m.workspace_id) or {}
        out.append({
            "workspace_id": m.workspace_id,
            "name": spec.get("name"),
            "slug": spec.get("slug"),
            "role": m.role,
            "created_by": spec.get("created_by"),
            "created_at": spec.get("created_at"),
            # The billing account that owns it (null = none ⇒ Free floor). Read
            # ONLY from the Workspace doc — never inferred from the caller, who
            # may well be an invited guest from a different account entirely.
            # That distinction is exactly why the abandoned portal-side fan-out
            # could not be made safe: this list is keyed by MEMBERSHIP.
            "account_id": spec.get("account_id"),
        })
    out.sort(key=lambda w: ((w["name"] or "").lower(), w["workspace_id"]))
    return {
        "identity_oid": identity.oid,
        "identity_email": identity.email,
        "workspaces": out,
    }


async def create_project_impl(
    live: LiveDna,
    workspace_id: str,
    name: str,
    claims: dict[str, Any] | None,
    *,
    slug: str | None = None,
) -> dict[str, Any]:
    """**Create a Project inside a workspace** — ``POST /v1/projects`` (decision
    A1: ``Project`` becomes a real entity with an EXPLICIT ``workspace_id``).

    Authorization is the same one rule as everywhere else in Model B: the VERIFIED
    identity must hold an ACTIVE :class:`WorkspaceMembership` in ``workspace_id``,
    else :class:`WorkspaceForbidden` (403). No ``tid`` is consulted.

    **The scope is DERIVED, not supplied.** The write lands in
    ``live.default_scope(workspace_id)`` and the project's ``board_scope`` is the
    conventional ``<slug>-development``. Neither is a parameter: a caller-chosen
    scope would be a cross-workspace write vector, and the whole point of A1 is
    that the project's identity is (workspace, slug) — the scope is a rendering of
    that, downstream of it.

    Slug defaults to a slugified ``name``, made unique WITHIN the workspace.
    TENANTED write — the doc is keyed to ``workspace_id`` in the ``tenant``
    column, matching the declared ``spec.workspace_id``."""
    from dna.tenancy import identity_from_token

    workspace_id = (workspace_id or "").strip()
    if not workspace_id:
        raise ValueError("workspace_id is required")
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")

    identity = identity_from_token(claims or {})
    _, memberships = await _workspace_grants(live)
    _require_workspace_membership(identity, workspace_id, memberships, "create a project")

    sc = live.default_scope(workspace_id)
    existing = await _collect(live, sc, "Project", workspace_id)
    taken = {
        ((d["spec"].get("slug") or d["name"] or "")).lower() for d in existing
    }
    wanted = slugify(slug or name) or slugify(name) or "project"
    slug_value = wanted
    n = 2
    while slug_value in taken:
        slug_value = f"{wanted}-{n}"
        n += 1

    now = datetime.now(timezone.utc).isoformat()
    spec = {
        "name": name,
        "slug": slug_value,
        "workspace_id": workspace_id,
        "org_ref": None,
        "repo_refs": [],
        # DERIVED, by convention — not an identity, and not caller-supplied.
        "board_scope": f"{slug_value}-development",
        "intel_source_refs": [],
        "visibility": "private",
        "created_at": now,
    }
    write_kernel = live.kernel.with_tenant(workspace_id)
    await write_kernel.write_document(
        sc, "Project", name,
        {
            "apiVersion": _PORTFOLIO_API,
            "kind": "Project",
            "metadata": {"name": name},
            "spec": spec,
        },
        invalidate_mode="doc",
    )
    return {
        "scope": sc,
        "workspace_id": workspace_id,
        "project": {
            "name": name,
            "slug": slug_value,
            "workspace_id": workspace_id,
            "org_ref": None,
            "repo_refs": [],
            "board_scope": spec["board_scope"],
            "intel_source_refs": [],
            "visibility": "private",
        },
    }


async def revoke_workspace_member_impl(
    live: LiveDna,
    workspace_id: str,
    *,
    actor_claims: dict[str, Any] | None,
    target_email: str | None = None,
    target_oid: str | None = None,
) -> dict[str, Any]:
    """Revoke (remove) a member's ``WorkspaceMembership`` — the Members panel's
    remove (issue ``i-033``). The target is named by ``target_email`` or
    ``target_oid`` (oid wins when both are given — the durable key).

    RBAC + policy is the pure ``dna.tenancy.plan_revoke`` decision:

    * the ``actor`` (from the caller's VERIFIED claims) must be Owner/Admin, else
      :class:`WorkspaceForbidden` (403) — checked BEFORE the target is revealed, so
      an unauthorized caller gets no membership-existence oracle;
    * the LAST active owner can NEVER be revoked — the workspace must never be
      orphaned, else :class:`WorkspaceLastOwner` (409, fail-closed);
    * a target holding no grant here is :class:`WorkspaceMemberNotFound` (404, a
      clear no-op — revoking a non-member is not an error to hide).

    Revoking removes the grant outright (``kernel.delete_document`` — the
    WorkspaceMembership status enum has no ``revoked`` state; a removed grant no
    longer authorizes, exactly like the portfolio ``remove_member_impl``). Works on
    a ``pending`` invite (rescind) or an ``active`` member. GLOBAL / ``_lib``-direct
    (no tenant kwarg). Idempotent-ish: a second revoke of the same target 404s."""
    from dna.tenancy import (
        identity_from_token,
        normalize_email,
        plan_revoke,
        role_in_workspace,
        workspace_membership_name,
    )

    workspace_id = (workspace_id or "").strip()
    if not workspace_id:
        raise ValueError("workspace_id is required")
    target_email = normalize_email(target_email)
    target_oid = (target_oid or "").strip()
    if not target_email and not target_oid:
        raise ValueError("target_email or target_oid is required")

    actor = identity_from_token(actor_claims or {})
    raw_grants, memberships = await _workspace_grants(live)
    actor_role = role_in_workspace(actor, workspace_id, memberships)

    # Locate the target grant in THIS workspace (oid wins when provided).
    target_spec: dict[str, Any] | None = None
    target_m: Any = None
    for g, m in zip(raw_grants, memberships):
        spec = g.get("spec") or {}
        if (spec.get("workspace_id") or "") != workspace_id:
            continue
        if target_oid:
            if (spec.get("identity_oid") or "") == target_oid:
                target_spec, target_m = spec, m
                break
        elif normalize_email(spec.get("identity_email")) == target_email:
            target_spec, target_m = spec, m
            break

    decision = plan_revoke(actor_role, target_m, workspace_id, memberships)
    if decision.reason == "not_authorized":
        raise WorkspaceForbidden(
            f"actor {(actor.email or '<anonymous>')!r} is not an Owner/Admin of "
            f"workspace {workspace_id!r} (has {actor_role or 'no membership'}) — "
            f"cannot revoke members"
        )
    if decision.reason == "not_found":
        raise WorkspaceMemberNotFound(
            f"no membership for the target ("
            f"{target_oid or target_email!r}) in workspace {workspace_id!r} — "
            f"nothing to revoke"
        )
    if decision.reason == "last_owner":
        raise WorkspaceLastOwner(
            f"cannot revoke the last remaining owner of workspace "
            f"{workspace_id!r} — the workspace would be orphaned"
        )

    assert target_spec is not None  # reason=='ok' ⇒ a target was located.
    name = workspace_membership_name(workspace_id, target_spec.get("identity_email") or "")
    await live.kernel.delete_document(
        _WORKSPACE_SCOPE, "WorkspaceMembership", name, invalidate_mode="doc"
    )
    return {
        "workspace_id": workspace_id,
        "revoked": True,
        "target": _ws_member_surface(target_spec),
    }


def _slug(text: str) -> str:
    import hashlib
    import re

    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
    h = hashlib.sha1(text.encode()).hexdigest()[:10]
    return f"rem-{h}-{base}" if base else f"rem-{h}"


def _email_slug(email: str) -> str:
    """A clean URL-safe workspace slug from an email local part (no ``rem-``
    prefix — that ``_slug`` above is for memory doc names)."""
    import re

    local = (email or "").split("@", 1)[0]
    return re.sub(r"[^a-z0-9]+", "-", local.lower()).strip("-") or "workspace"
