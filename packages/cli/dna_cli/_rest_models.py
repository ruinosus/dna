"""``dna_cli._rest_models`` — typed **response models** for the DNA REST read-API.

The REST face (:mod:`dna_cli._rest_api`) delegates to the transport-agnostic
``*_impl`` use-cases in ``dna.application`` / ``dna.extensions.intel.engine``,
which return plain ``dict[str, Any]`` envelopes. Without a declared
``response_model`` FastAPI can only emit an opaque ``{type: object,
additionalProperties: true}`` response schema, so the generated clients
(``packages/client-ts`` + the drift-tested ``docs/openapi.json``) type inputs but
leave response BODIES untyped (``unknown`` / ``dict``).

These Pydantic models describe EXACTLY what each handler returns, so the OpenAPI
response schemas — and the clients generated from them — carry the real shape.

**Fidelity contract (load-bearing).** FastAPI VALIDATES + SERIALIZES the handler's
returned dict through the ``response_model``: a key the model omits is silently
DROPPED from the response, and a required field the dict omits raises a 500. So
every model here is a faithful SUPERSET of the handler's real payload, with
optional/defaulted fields wherever the handler may omit or null a value. Where a
payload is genuinely dynamic (a memory recall ``hit``, a Document ``spec``, a
status→count map, an SDLC work-item's verbatim AC/DoD/timeline lists) the ENVELOPE
is typed but that field stays loose (``dict[str, Any]`` / ``list[...]`` / ``Any``)
— honest about what can and cannot be pinned. Imported LAZILY by ``build_app``
(alongside the lazy ``fastapi`` import), so ``import dna_cli`` stays light.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# ── health ──────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    ok: bool


# ── definitions (agents / tools) ────────────────────────────────────────────


class AgentSummary(BaseModel):
    name: str
    kind: str
    description: str


class AgentsResponse(BaseModel):
    scope: str
    agents: list[AgentSummary]


class AgentPromptResponse(BaseModel):
    scope: str
    agent: str
    tenant: str | None = None
    model: str | None = None
    prompt: str


class ToolSummary(BaseModel):
    name: str | None = None
    description: str = ""


class ToolsResponse(BaseModel):
    scope: str
    tools: list[ToolSummary]


# ── memory ──────────────────────────────────────────────────────────────────


class MemorySummary(BaseModel):
    name: str | None = None
    summary: str | None = None
    area: str | None = None
    tags: list[str] = []
    created_at: str | None = None


class MemoriesResponse(BaseModel):
    scope: str
    tenant: str | None = None
    memories: list[MemorySummary]


class RememberResponse(BaseModel):
    kind: str
    name: str
    indexed: bool


class RecallResponse(BaseModel):
    """The recall envelope is typed; each ``hit`` stays a loose dict — its shape
    varies with the search plane active (lexical vs. hybrid/semantic add
    ``retention``/``semantic``/``rank_*`` keys), so it is honestly dynamic."""

    query: str
    scope: str
    degraded: bool = False
    semantic: bool = False
    hits: list[dict[str, Any]] = []


class DeleteMemoryResponse(BaseModel):
    deleted: str
    scope: str
    tenant: str | None = None


# ── intel (sources / insights / metrics) ────────────────────────────────────


class IntelSourceSummary(BaseModel):
    name: str | None = None
    type: str | None = None
    cadence: str = "weekly"
    threshold: float = 0.6
    pirs: list[str] = []
    muted: bool = False


class SourcesResponse(BaseModel):
    scope: str
    tenant: str | None = None
    sources: list[IntelSourceSummary]


class IntelInsightSummary(BaseModel):
    name: str | None = None
    title: str | None = None
    fact: str | None = None
    why: str | None = None
    action: str | None = None
    score: float = 0.0
    state: str = "new"
    source_ref: str | None = None
    pirs: list[str] = []
    evidence_rating: str | None = None
    created_at: str | None = None


class InsightsResponse(BaseModel):
    scope: str
    tenant: str | None = None
    insights: list[IntelInsightSummary]


class InsightMetricsResponse(BaseModel):
    counts: dict[str, int] = {}
    actioned: int = 0
    dismissed: int = 0
    # ``None`` (not zero) until a disposition exists — precision/noise-rate are
    # undefined with no actioned+dismissed insights (feedback.precision/noise_rate).
    precision: float | None = None
    noise_rate: float | None = None
    scope: str
    tenant: str | None = None
    source_ref: str | None = None


class InsightStateResponse(BaseModel):
    name: str
    state: str
    scope: str
    tenant: str | None = None


# ── portfolio (orgs / projects / repos / members) ───────────────────────────


class OrgSummary(BaseModel):
    name: str | None = None
    slug: str | None = None
    display_name: str | None = None


class OrgsResponse(BaseModel):
    scope: str
    tenant: str | None = None
    orgs: list[OrgSummary]


class ProjectSummary(BaseModel):
    name: str | None = None
    slug: str | None = None
    org_ref: str | None = None
    repo_refs: list[str] = []
    board_scope: str | None = None
    intel_source_refs: list[str] = []
    visibility: str = "private"


class ProjectsResponse(BaseModel):
    scope: str
    tenant: str | None = None
    projects: list[ProjectSummary]


class RepoSummary(BaseModel):
    name: str | None = None
    url: str | None = None
    provider: str = "github"
    default_branch: str | None = None


class ReposResponse(BaseModel):
    scope: str
    tenant: str | None = None
    repos: list[RepoSummary]


class ProjectDetailResponse(BaseModel):
    scope: str
    tenant: str | None = None
    project: ProjectSummary
    repos: list[RepoSummary]


class ProjectRef(BaseModel):
    name: str | None = None
    slug: str | None = None
    org_ref: str | None = None


class ProjectMemberSurface(BaseModel):
    user: str
    role: str
    role_display: str
    org_role: str | None = None
    project_role: str | None = None
    is_org_owner: bool = False
    status: str = "active"
    scope_note: str | None = None
    you: bool = False


class ProjectMemberViewer(BaseModel):
    user: str | None = None
    role: str | None = None
    can_manage: bool = False


class ProjectMembersResponse(BaseModel):
    scope: str
    tenant: str | None = None
    project: ProjectRef
    members: list[ProjectMemberSurface]
    viewer: ProjectMemberViewer


class SetMemberInfo(BaseModel):
    user: str
    role: str
    scope_type: str
    scope_ref: str
    status: str


class SetMemberResponse(BaseModel):
    scope: str
    tenant: str | None = None
    member: SetMemberInfo


class RemoveMemberResponse(BaseModel):
    removed: str
    scope: str
    tenant: str | None = None


class OwnerGrant(BaseModel):
    scope_type: str
    scope_ref: str
    role: str


class ProvisionTenantOwnerResponse(BaseModel):
    scope: str
    tenant: str | None = None
    user: str
    provisioned: bool
    reason: str | None = None
    grants: list[OwnerGrant] = []


# ── board (SDLC read model) ─────────────────────────────────────────────────


class BoardCounts(BaseModel):
    """Status→count maps (dynamic keys — a status label is data)."""

    stories: dict[str, int] = {}
    features: dict[str, int] = {}


class BoardTotals(BaseModel):
    stories: int = 0
    features: int = 0
    total: int = 0


class BoardListItem(BaseModel):
    kind: str
    name: str | None = None
    title: str | None = None
    status: str | None = None
    created_at: str | None = None


class BoardResponse(BaseModel):
    scope: str
    tenant: str | None = None
    counts: BoardCounts
    totals: BoardTotals
    items: list[BoardListItem] = []
    recent: list[BoardListItem] = []


class BoardItemResponse(BaseModel):
    """One SDLC work-item's full doc. The nested AC/DoD/timeline/produces lists
    pass through VERBATIM (the drawer renders them raw), so they stay loosely
    typed; ``business_value`` may be a label or a number → ``Any``."""

    scope: str
    tenant: str | None = None
    kind: str
    name: str
    title: str | None = None
    status: str | None = None
    description: str | None = None
    priority: str | None = None
    labels: list[str] = []
    feature: str | None = None
    epic: str | None = None
    reporter: str | None = None
    business_value: Any | None = None
    acceptance_criteria: list[Any] = []
    definition_of_done: list[Any] = []
    timeline: list[dict[str, Any]] = []
    produces: list[Any] = []
    created_at: str | None = None
    updated_at: str | None = None
    closed_at: str | None = None


# ── cloud (workspace-plan billing bridge) ───────────────────────────────────


class WorkspacePlanResponse(BaseModel):
    scope: str
    workspace_id: str
    tier_id: str
    status: str | None = None


# ── workspace invites / members (Model B tenancy boundary) ──────────────────


class InviteInfo(BaseModel):
    identity_email: str | None = None
    role: str
    status: str
    invited_by: str | None = None
    bound: bool = False


class InviteResponse(BaseModel):
    workspace_id: str
    invite: InviteInfo


class WorkspaceMemberSummary(BaseModel):
    identity_email: str | None = None
    role: str | None = None
    status: str | None = None
    bound: bool = False
    invited_by: str | None = None
    invited_at: str | None = None
    accepted_at: str | None = None


class WorkspaceMembersResponse(BaseModel):
    workspace_id: str
    members: list[WorkspaceMemberSummary]


class AcceptedInvite(BaseModel):
    workspace_id: str
    role: str | None = None
    activated: bool = False


class AcceptInvitesResponse(BaseModel):
    identity_oid: str | None = None
    identity_email: str | None = None
    accepted: list[AcceptedInvite] = []


class WorkspaceMemberSurface(BaseModel):
    """The ``_ws_member_surface`` projection (a superset of
    :class:`WorkspaceMemberSummary` with the ``workspace_id`` + ``identity_oid``)."""

    workspace_id: str | None = None
    identity_email: str | None = None
    identity_oid: str | None = None
    role: str | None = None
    status: str | None = None
    bound: bool = False
    invited_by: str | None = None
    invited_at: str | None = None
    accepted_at: str | None = None


class ProvisionWorkspaceOwnerResponse(BaseModel):
    workspace_id: str
    provisioned: bool
    reason: str | None = None
    workspace_created: bool = False
    membership: WorkspaceMemberSurface | None = None


class RevokeWorkspaceMemberResponse(BaseModel):
    workspace_id: str
    revoked: bool
    target: WorkspaceMemberSurface
