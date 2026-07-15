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
    same pattern as ``PUT /v1/tenant-plan``) so the signed-in user becomes Owner of
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


async def recall_impl(
    live: LiveDna, query: str, scope: str | None = None, k: int = 5,
    tenant: str | None = None,
) -> dict[str, Any]:
    """Recall DNA memory for ``query`` — hybrid + bi-temporal + retention
    re-scored when the search extra is present, honest lexical otherwise.
    Tenant-scoped when ``tenant`` is set (the auth bridge injects it)."""
    from dna.memory import recall
    from dna.memory.verbs import MEMORY_KINDS

    sc = scope or live.default_scope(tenant)
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

    sc = scope or live.default_scope(tenant)
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

    sc = scope or live.default_scope(tenant)
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

    sc = scope or live.default_scope(tenant)
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

    sc = scope or live.default_scope(tenant)
    try:
        out = await forget(live.kernel, sc, name, kind=kind, tenant=tenant)
    except KeyError:
        return {"kind": kind, "name": name, "forgotten": False}
    return {"kind": kind, "name": name, "forgotten": not out["already_forgotten"]}


# ── cloud: the billing→enforcement bridge write (WorkspacePlan) ─────────────

# WorkspacePlan is GLOBAL and _lib-resident (base only, no per-tenant overlay) —
# the same scope kernel.workspace_plan() reads _lib-direct. The doc NAME equals
# the workspace_id so the read matches on spec.workspace_id, and the write is a
# natural upsert (write_document keys on name) → idempotent under Stripe's
# at-least-once retries. ADR "Model B": billing keys on the workspace, not the
# Azure tid; the founding workspace's id == the founder's tid, so a plan written
# for it keys on the SAME string as before (zero migration).
_WORKSPACE_PLAN_SCOPE = "_lib"
_CLOUD_API = "github.com/ruinosus/dna/cloud/v1"


async def set_workspace_plan_impl(
    live: LiveDna,
    workspace_id: str,
    tier_id: str,
    *,
    source: str = "stripe",
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Upsert the WorkspacePlan Kind assigning ``workspace_id`` to ``tier_id`` —
    the billing→enforcement BRIDGE write that dna-cloud's Stripe webhook drives so
    runtime quota (``kernel.workspace_plan(workspace_id)`` in the MCP guard)
    follows billing state without a redeploy (ADR "Model B" — billing attaches to
    the workspace, not an identity/Azure org).

    GLOBAL / ``_lib``-direct: WorkspacePlan is not tenant-overlaid — the doc lives
    in ``_lib`` with its NAME == the workspace_id (the opaque value the kernel
    ``tenant`` dimension carries; the founding workspace's id == the founder's old
    ``tid``), so the guard's ``spec.workspace_id`` lookup resolves it regardless of
    the caller's scope. The write is an UPSERT keyed on that name, so a redelivered
    Stripe event (at-least-once) converges on the same doc — idempotent by
    construction.

    Only the schema-allowed keys are written (the descriptor is
    ``additionalProperties: false``): ``workspace_id``/``tier_id`` (required),
    ``source``, ``status``, the two Stripe ids, and an ISO ``updated_at`` stamp.
    Optional refs are omitted when absent so a status-only transition never nulls a
    previously-recorded customer/subscription id — mirroring the portal store's
    COALESCE-on-update semantics."""
    workspace_id = (workspace_id or "").strip()
    tier_id = (tier_id or "").strip()
    if not workspace_id:
        raise ValueError("workspace_id is required")
    if not tier_id:
        raise ValueError("tier_id is required")

    spec: dict[str, Any] = {
        "workspace_id": workspace_id,
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
        "kind": "WorkspacePlan",
        "metadata": {"name": workspace_id},
        "spec": spec,
    }
    # GLOBAL kind → no tenant kwarg (a tenant on a GLOBAL write is rejected).
    await live.kernel.write_document(
        _WORKSPACE_PLAN_SCOPE, "WorkspacePlan", workspace_id, raw, invalidate_mode="doc"
    )
    return {
        "scope": _WORKSPACE_PLAN_SCOPE,
        "workspace_id": workspace_id,
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


def _slug(text: str) -> str:
    import hashlib
    import re

    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
    h = hashlib.sha1(text.encode()).hexdigest()[:10]
    return f"rem-{h}-{base}" if base else f"rem-{h}"
