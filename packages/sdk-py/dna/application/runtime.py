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
    sc = scope or live.base_scope
    orgs = [_org_surface(d) for d in await _collect(live, sc, "Organization", tenant)]
    orgs.sort(key=lambda o: o["name"] or "")
    return {"scope": sc, "tenant": tenant, "orgs": orgs}


async def list_projects_impl(
    live: LiveDna, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """List the tenant's ``Project`` docs (the multi-repo containers), projected
    to the console surface (name/slug/org_ref/repo_refs/board_scope/
    intel_source_refs/visibility), sorted by name."""
    sc = scope or live.base_scope
    projects = [_project_surface(d) for d in await _collect(live, sc, "Project", tenant)]
    projects.sort(key=lambda p: p["name"] or "")
    return {"scope": sc, "tenant": tenant, "projects": projects}


async def list_repos_impl(
    live: LiveDna, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """List the tenant's ``Repo`` docs, projected to the console surface
    (name/url/provider/default_branch), sorted by name."""
    sc = scope or live.base_scope
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
    sc = scope or live.base_scope
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
    sc = scope or live.base_scope
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
    sc = scope or live.base_scope
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
    sc = scope or live.base_scope
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
