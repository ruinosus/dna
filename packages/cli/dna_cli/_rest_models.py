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

from typing import Any, Literal

from pydantic import BaseModel, Field

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


class PromptSectionProvenance(BaseModel):
    """Provenance for ONE composed prompt section (``?explain=true``).

    Mirrors the kernel's ``SectionProvenance.serialize()`` exactly — the same
    map ``dna explain`` prints. No field here is invented by the REST face.
    """

    section: str = Field(description=(
        "Human label of the composed section, e.g. 'instruction', 'soul', "
        "'skill:tdd', 'guardrail:polite'."
    ))
    kind: str = Field(description="The contributing Kind (Agent/Soul/Skill/Guardrail/…).")
    name: str = Field(description="The contributing document name.")
    source: str = Field(description=(
        "Canonical source artifact path, e.g. 'skills/tdd/SKILL.md' ('?' when "
        "the Kind declares no storage pattern)."
    ))
    hash: str | None = Field(default=None, description=(
        "SHA-256 (full hex) of the resolved raw document composed into this "
        "section, or null when it could not be resolved."
    ))
    version: str | None = Field(default=None, description=(
        "metadata.version of the resolved document, when the author set one."
    ))
    origin: str = Field(description=(
        "Effective layer/scope the section resolved from — the scope that won "
        "('(not found)' when resolution failed)."
    ))
    is_inherited: bool = Field(description=(
        "True when 'origin' is a DIFFERENT scope than the requested one (the "
        "section is inherited from a parent/library scope)."
    ))
    overridden_by_tenant: bool = Field(description=(
        "True when the tenant-resolved content of this section DIFFERS from "
        "the base resolution — a per-tenant overlay won. Always false when no "
        "tenant was requested."
    ))


class AgentPromptResponse(BaseModel):
    scope: str
    agent: str
    tenant: str | None = None
    model: str | None = None
    prompt: str
    # ── explain mode (?explain=true, i-045) — ABSENT without the flag ───────
    # The route serializes with response_model_exclude_unset, so a plain
    # compose keeps the exact historical five-key JSON shape; these two fields
    # appear ONLY when the caller opted in.
    sections: list[PromptSectionProvenance] | None = Field(default=None, description=(
        "Per-section provenance of the composed prompt (only with "
        "?explain=true). One row per composed input the layout renders. The "
        "'prompt' field is byte-identical to the non-explain compose — explain "
        "never re-renders. NOTE: when 'attribution' is 'heuristic' this list "
        "may silently omit (or over-report) sections; see 'attribution'."
    ))
    attribution: Literal["declared", "heuristic"] | None = Field(default=None, description=(
        "How the section list was attributed (only with ?explain=true). "
        "'declared': the agent renders through a kernel-owned template (named "
        "layout preset, Kind default, or the plain-instruction fallback) — the "
        "kernel authored both the template and the section aliases, so the "
        "section map is correct by construction. 'heuristic': the agent "
        "carries its OWN promptTemplate, and sections are detected by "
        "fail-soft string-matching Mustache blocks in that user-authored "
        "template — a section can be silently missing from, or over-reported "
        "in, 'sections' (the composed 'prompt' itself is still exact)."
    ))


class ToolSummary(BaseModel):
    name: str | None = None
    description: str = ""


class ToolsResponse(BaseModel):
    scope: str
    tools: list[ToolSummary]


# ── genome view (identity + ships + tenant LayerPolicy) ──────────────────────


class GenomeIdentity(BaseModel):
    version: str | None = None
    visibility: str | None = None
    default_agent: str | None = None
    tags: list[str] = Field(default_factory=list)


class GenomeShips(BaseModel):
    """The module's contents, enumerated live from the scope (not a stored list)."""

    copilots: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    federations: list[str] = Field(default_factory=list)


class GenomeViewResponse(BaseModel):
    scope: str
    identity: GenomeIdentity
    ships: GenomeShips
    # layer_id → {kind-alias → open|restricted|locked}. Genuinely dynamic map,
    # so the values stay loose per the fidelity contract.
    policies: dict[str, dict[str, str]] = Field(default_factory=dict)


# ── definitions (read/apply/revert a tenant-layer override) ──────────────────


class DefinitionView(BaseModel):
    """``GET /v1/definitions/{kind}/{name}`` — the tenant's view of one
    definition: the effective (composed) spec, the inherited base spec,
    whether the tenant has an override, and the Kind's edit schema. The
    ``pattern``/``body_field``/``bundle_entries`` fields carry the Kind's
    storage taxonomy so the editor is honest about a BUNDLE Kind's files
    being read-only for now (fork is a later plane)."""

    kind: str
    name: str
    overridden: bool
    overlayable: bool
    effective: dict[str, Any]
    base: dict[str, Any] | None = None
    ui_schema: dict[str, Any] = Field(default_factory=dict)
    overlayable_fields: list[str] = Field(default_factory=list)
    pattern: str = ""
    body_field: str | None = None
    bundle_entries: list[str] = Field(default_factory=list)


class DefinitionWriteResponse(BaseModel):
    """``PUT``/``DELETE /v1/definitions/{kind}/{name}`` — the write result.
    ``version`` is set on apply (the write's document version), absent on
    revert."""

    kind: str
    name: str
    version: str | None = None
    overridden: bool


class RegisteredKindView(BaseModel):
    """``GET /v1/kinds/registry/{kind}`` — the registered Kind's descriptor:
    the JSON ``schema`` a form derives validation from and the ``ui_schema``
    widget hints it renders with. Product data model, not tenant data — the
    same answer for every caller (contrast: the authored-Kind door filters)."""

    kind: str
    plane: str = "composition"
    #: The WIRE name (see ``AuthoredKindDetail.schema``): a JSON Schema field
    #: is called ``schema``. The pydantic shadow warning is silenced narrowly
    #: in the cli ``pyproject.toml``, beside the two entries already there.
    schema: dict[str, Any] = Field(default_factory=dict)
    ui_schema: dict[str, Any] = Field(default_factory=dict)
    docs: str | None = None


# ── Kind authoring (the dedicated door — writes an INERT KindDefinition) ────


class AuthorKindResponse(BaseModel):
    """``POST /v1/kinds`` — the authored Kind. ``approved`` is ALWAYS false
    here: this door cannot approve, so the field states the document's actual
    state rather than echoing anything the caller sent."""

    namespace: str
    kind: str
    name: str
    approved: bool
    #: The caller's VERIFIED identity as the document recorded it. ECHOED, never
    #: accepted — there is no request field it could have come from.
    proposed_by: str | None = None
    version: str | None = None
    #: The authored JSON Schema, ECHOED (wire name, like the two other doors —
    #: shadow warning silenced narrowly in pyproject). The MCP Apps kind-draft
    #: card renders its editable rows from this echo; dropping it here would
    #: violate the fidelity contract (FastAPI silently strips unmodeled keys).
    schema: dict[str, Any] | None = None


class ApproveKindResponse(BaseModel):
    """``POST /v1/kinds/{kind}/approve`` — the act that CONFERS effect.

    Carries BOTH actors: a reviewer who must make a second call to learn who
    proposed is a reviewer who will not make it. ``proposed_by`` may equal
    ``approved_by`` (a solo author approving their own proposal) — a fact this
    response reports, not an error it withholds."""

    approved: bool
    kind: str
    name: str
    namespace: str
    approved_by: str
    approved_at: str
    proposed_by: str | None = None
    proposed_at: str | None = None
    version: str | None = None


class RevokeKindResponse(BaseModel):
    """``POST /v1/kinds/{kind}/revoke`` — the act that WITHDRAWS effect (i-085).

    Carries the whole chain of acts, not only the last one: who proposed the
    shape, who conferred effect on it, and who has just withdrawn it.
    ``approved_by`` is present on purpose — revoking is a third act, not an
    erasure of the second, and a record saying only "revoked by X" has lost the
    fact that this Kind governed real documents for a while."""

    revoked: bool
    kind: str
    name: str
    namespace: str
    revoked_by: str
    revoked_at: str
    proposed_by: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    version: str | None = None


class AuthoredKindSummary(BaseModel):
    """One ``KindDefinition`` document as the audit surface sees it — ALL THREE
    actors, so the reviewer deciding whether to confer effect can see who asked
    for it, and whether anyone has since taken it away, without leaving the
    list."""

    name: str | None = None
    kind: str | None = None
    api_version: str | None = None
    namespace: str | None = None
    #: "Is this Kind currently conferring effect." False for a REVOKED Kind as
    #: well as for one nobody ever approved — which is why ``state`` exists.
    approved: bool = False
    #: WHICH not-approved this is: ``unapproved`` | ``approved`` | ``revoked``
    #: (i-085). The boolean above cannot carry three values, and the two it
    #: collapses behave in OPPOSITE ways — a Kind that was never approved
    #: accepts documents with no validation at all, a revoked one refuses them
    #: and marks every existing document invalid. Reporting the loosest and the
    #: tightest states in the system with the same word is how a reviewer ends
    #: up believing a revocation did nothing.
    state: str = "unapproved"
    proposed_by: str | None = None
    proposed_at: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    #: Null on every Kind that was never revoked — the honest answer, and not
    #: the same fact as "revoked by nobody".
    revoked_by: str | None = None
    revoked_at: str | None = None
    created_at: str | None = None


class AuthoredKindDetail(AuthoredKindSummary):
    """``GET /v1/kinds/{kind}`` — one authored Kind, in full.

    SUBCLASSES the summary rather than restating it: the roster and the single
    read describe the SAME document, and two independent field lists are two
    vocabularies for one thing — the kind of drift that reads, to the human
    doing the review, as two different documents.

    What it adds is what the roster deliberately withholds. ``schema`` is the
    reason the route exists: registration is what confers schema validation and
    storage routing, so "should this take effect?" is a question ABOUT the
    schema, and a reviewer who cannot see it is not reviewing anything.
    ``traits`` travels with it because it is the other half of what the
    authoring door stored and the other half of what would take effect.

    ``schema`` is ``null``, never ``{}``, for a document that stored none —
    "there is no schema here" and "the schema is the empty object" are
    different facts about what would be conferred."""

    #: The WIRE name, and not ours to rename: a JSON Schema field is called
    #: ``schema``, and ``POST /v1/kinds`` already takes it under that name.
    #: Pydantic warns because ``BaseModel.schema`` is a deprecated attribute
    #: (it names the nearest parent, ``AuthoredKindSummary``, in the message);
    #: the warning is silenced narrowly — this exact model, this exact field —
    #: in the cli ``pyproject.toml``, beside the twin entry the request body
    #: needed.
    schema: dict[str, Any] | None = None
    traits: list[str] = Field(default_factory=list)
    #: How documents of this Kind will READ — the ordered fields, their human
    #: labels, their semantic roles, and what is hidden — composed with the
    #: Kind's own ``display_label``/``ascii_icon``.
    #:
    #: It travels here for the same reason ``schema`` does: this approval
    #: confers it. ``schema`` says what a document may CONTAIN; this says what
    #: a person will SEE of it, in what order and under what names, on every
    #: surface the workspace has. That is the half a reviewer could not see,
    #: and the half a portal needs the moment the Kind exists — one
    #: declaration, read by a React screen and by a sandboxed prefab card that
    #: share no runtime and never will.
    #:
    #: ``null``, never ``{}``, for a Kind that declares none — and also for one
    #: whose stored declaration no longer normalizes: "this Kind declares no
    #: reading I can read" is the honest answer, and a 500 on the screen a
    #: reviewer uses to decide whether the Kind takes effect is not.
    presentation: dict[str, Any] | None = None


class AuthoredKindsResponse(BaseModel):
    """``GET /v1/kinds`` — every authored Kind in the scope, approved or not.
    Documents, not registry entries: an UNAPPROVED Kind is exactly the one the
    registry does not have, and it is the one a reviewer came here for."""

    scope: str
    kinds: list[AuthoredKindSummary] = Field(default_factory=list)


# ── bundle entries (list/read/write/revert a bundle-file fork — plane B) ────
#
# A bundle-pattern Kind (Skill, and any future bundle Kind) stores MULTIPLE
# files per document (SKILL.md + scripts/…), not a single spec — these are the
# file-grained twin of DefinitionView/DefinitionWriteResponse above, generic
# over any bundle Kind, with the SAME LayerPolicy governance (a fork on a
# LOCKED Kind is vetoed, 403).


class BundleEntrySummary(BaseModel):
    entry: str
    overridden: bool


class BundleEntriesView(BaseModel):
    """``GET /v1/definitions/{kind}/{name}/entries`` — a bundle document's
    entry files (base ∪ tenant overlay), each flagged ``overridden`` —
    whether THIS tenant forked that specific file."""

    kind: str
    name: str
    entries: list[BundleEntrySummary]


class BundleEntryView(BaseModel):
    """``GET /v1/definitions/{kind}/{name}/entries/{entry}`` — one bundle
    entry's effective content (tenant overlay wins over base), whether this
    tenant forked it, and whether it's binary (a decode failure — reported
    honestly rather than mangling bytes into ``content``)."""

    kind: str
    name: str
    entry: str
    content: str
    overridden: bool
    binary: bool


class WriteBundleEntryRequest(BaseModel):
    """``PUT /v1/definitions/{kind}/{name}/entries/{entry}`` — the fork's new
    content. The request body is exactly ``{"content": "..."}``."""

    content: str


class BundleEntryWriteResponse(BaseModel):
    """``PUT``/``DELETE /v1/definitions/{kind}/{name}/entries/{entry}`` — the
    write result."""

    kind: str
    name: str
    entry: str
    overridden: bool


# ── reconcile (2-way diff of a tenant's forks vs base-NOW — plane B2) ───────
#
# A tenant's fork can drift not because the tenant changed anything, but
# because the BASE moved on (an upstream release). This is the file-grained
# twin of "what did I change vs what changed under me" — READ-only: the three
# resolutions an editor offers over this view are all EXISTING B1 primitives
# (keep = no-op, take-base = the DELETE, edit = the PUT). No new write route.


class ReconcileFileEntry(BaseModel):
    entry: str
    status: str  # "identical" | "diverged"
    base: str | None = None
    mine: str | None = None
    binary: bool = False


class ReconcileView(BaseModel):
    """``GET /v1/definitions/{kind}/{name}/reconcile`` — per forked entry, the
    tenant's fork content vs the base's CURRENT content."""

    kind: str
    name: str
    files: list[ReconcileFileEntry]


# ── memory ──────────────────────────────────────────────────────────────────


class MemorySummary(BaseModel):
    """One memory as the WORKSPACE list surface projects it.

    ``affect`` and ``personal`` were added by i-079, when this route stopped
    carrying its own copy of ``list_memories_impl`` and delegated to the core.
    They are not decoration: ``affect`` is stored on every Engram and is what a
    memory card renders, and ``personal`` (i-068) is the per-item flag that
    tells the caller's own memory from a shared one. The core had always
    projected both — only this face's copy did not, so the two list surfaces of
    one app were two different SHAPES as well as two different answers.

    Both are additive and defaulted, so a client written against the older
    response keeps parsing. ``personal`` is always ``False`` here: a workspace
    read never resolves the caller's private partition. It is carried anyway so
    the item shape matches :class:`PersonalMemorySummary` field for field — a
    UI that renders one list must not need two renderers."""

    name: str | None = None
    summary: str | None = None
    area: str | None = None
    tags: list[str] = []
    affect: str | None = None
    created_at: str | None = None
    personal: bool = False


class MemoriesResponse(BaseModel):
    scope: str
    tenant: str | None = None
    memories: list[MemorySummary]


class PersonalMemorySummary(BaseModel):
    """One memory as the PERSONAL list surface projects it — the core
    ``list_memories_impl`` item shape (i-068 enriched): the dashboard fields
    plus the per-ITEM ``personal`` flag. A personal read unions the caller's
    ``personal:<oid>`` partition with the shared base, so the flag varies per
    item (``True`` = the caller's own private memory; ``False`` = a shared
    base memory riding along)."""

    name: str | None = None
    summary: str | None = None
    area: str | None = None
    tags: list[str] = []
    affect: str | None = None
    created_at: str | None = None
    personal: bool = False


class PersonalMemoriesResponse(BaseModel):
    """The caller's OWN personal memories (+ the shared base they union with).

    Like :class:`ImportMemoriesResponse`, ``partition`` echoes only the SCHEME
    the read resolved (``personal``) — never the concrete ``personal:<oid>``
    value, which would leak the server-derived identity onto the wire. There is
    deliberately NO ``tenant`` field for the same reason."""

    scope: str
    partition: str = "personal"
    memories: list[PersonalMemorySummary]


class RememberResponse(BaseModel):
    kind: str
    name: str
    indexed: bool


class ImportFailure(BaseModel):
    """One MIF doc that could not be written — reported, never swallowed."""

    id: str
    error: str


class ImportMemoriesResponse(BaseModel):
    """The outcome of a MIF bundle import into the caller's PERSONAL partition.

    The counts always reconcile with the bundle size
    (``imported + skipped + failed == received``), so a partial import is always
    VISIBLE — ``failed`` is a reported outcome, never a silent one.
    ``partition`` echoes only the SCHEME the write landed in (``personal``),
    never the concrete ``personal:<oid>`` value — echoing that back would leak
    the server-derived identity onto the wire."""

    imported: int
    skipped: int
    failed: int
    received: int
    partition: str = "personal"
    as_mode: str = "both"
    dedupe: str = "id"
    ids: list[str] = []
    errors: list[ImportFailure] = []


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
    # A1 — the explicit owning workspace. None on a legacy pre-A1 doc.
    workspace_id: str | None = None
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


# ── cloud (account-plan billing bridge) ─────────────────────────────────────


class AccountPlanResponse(BaseModel):
    """``PUT /v1/account-plan`` — the account→Tier assignment that was written.

    Keyed on the BILLING ACCOUNT, not a workspace: this one assignment covers
    every workspace whose ``account_id`` matches."""

    scope: str
    account_id: str
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


class CreateWorkspaceResponse(BaseModel):
    """``POST /v1/workspaces`` — the created workspace. ``workspace_id`` is
    SERVER-MINTED; there is no request field for it."""

    workspace_id: str
    name: str
    slug: str
    created_by: str | None = None
    created_at: str | None = None
    #: The BILLING ACCOUNT that owns it, taken from the creator's verified
    #: account claim. ``None`` = no resolvable account ⇒ the Free floor.
    #: Reported, never accepted — there is no request field for it.
    account_id: str | None = None
    role: str = "owner"
    membership: WorkspaceMemberSurface | None = None


class WorkspaceSummary(BaseModel):
    workspace_id: str
    name: str | None = None
    slug: str | None = None
    role: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    #: The billing account that owns the workspace (``None`` ⇒ Free floor). Read
    #: from the Workspace doc — NOT from the caller, who may be an invited guest
    #: from another account entirely. This list is keyed by MEMBERSHIP, which is
    #: precisely why a per-workspace plan could not be fanned out safely.
    account_id: str | None = None


class WorkspacesResponse(BaseModel):
    """``GET /v1/workspaces`` — the caller's ACTIVE memberships, projected."""

    identity_oid: str | None = None
    identity_email: str | None = None
    workspaces: list[WorkspaceSummary] = []


class CreateProjectResponse(BaseModel):
    """``POST /v1/projects`` — the created project. ``scope`` is DERIVED from the
    workspace (never caller-supplied)."""

    scope: str
    workspace_id: str
    project: ProjectSummary


class ArtifactSummary(BaseModel):
    """One ``SourceArtifact`` — the original a projection derives from."""

    name: str
    sha256: str
    uri: str
    filename: str | None = None
    mime: str | None = None
    size_bytes: int | None = None
    uploaded_by: str | None = None
    uploaded_at: str | None = None
    derived_refs: list[dict[str, Any]] = []


class RegisterArtifactResponse(BaseModel):
    """``POST /v1/artifacts`` — the registered artifact. ``scope`` is DERIVED
    from the workspace (never caller-supplied)."""

    scope: str
    workspace_id: str
    artifact: ArtifactSummary


# ── the generic, kubernetes-shaped document write ───────────────────────────
#
# POST /v1/kinds/{kind}/documents — the path names the Kind (the k8s
# convention this route follows: "kind is inferred from the endpoint the
# client submits to"), the body carries only what k8s calls `metadata`/`spec`.


class WriteKindDocumentRequest(BaseModel):
    """``POST /v1/kinds/{kind}/documents`` — the document to write.

    Deliberately narrow: no ``scope``, no ``claims`` anywhere on this model —
    neither is reachable through this route's body (identity/scope are never
    caller input here; see the route for the full reasoning).

    ``kind`` is OPTIONAL and, when given, MUST equal the path's ``{kind}`` —
    a caller naming a DIFFERENT Kind in the body is refused (400) rather than
    the path or the body silently winning. Two sources stating one fact is
    exactly the defect this route exists to close.

    ``source_sha256``, when given, cites the ``SourceArtifact`` (by content
    address) this document was extracted from — the runtime closes the
    provenance edge (``derived_refs``) server-side."""

    metadata: dict[str, Any]
    spec: dict[str, Any]
    kind: str | None = None
    source_sha256: str | None = None


class ListKindDocumentsResponse(BaseModel):
    """``GET /v1/kinds/{kind}/documents`` — uma página de documentos do Kind.

    `documents` é a linha como o kernel a moldou: `{"name": …}` sem projeção, e
    `{"name": …, "spec": {…}}` com `fields`. `projected` ecoa o que foi pedido,
    para um leitor distinguir uma página de nomes de uma projetada — sem isso,
    um `spec` ausente seria ambíguo entre "não pedi" e "não tem".

    `has_more` é respondido buscando UMA linha a mais, não adivinhado a partir
    de a página ter vindo cheia."""

    scope: str
    kind: str
    api_version: str
    documents: list[dict[str, Any]]
    count: int
    offset: int
    has_more: bool
    projected: list[str] | None = None


class GetKindDocumentResponse(BaseModel):
    """``GET /v1/kinds/{kind}/documents/{name}`` — UM documento, VERBATIM.

    A lista projetada passa pela vista dos readers quando o Kind é produzível
    por bundle (Agent, Skill…) — e a vista NORMALIZA: `spec.description` e
    `spec.tools_requiring_confirmation` de um Agent gravado pelo funil
    genérico simplesmente não viajam por ela (medido 05/08/2026 na aba
    Configuração do dna-cloud). Esta porta lê o documento como a camada do
    chamador o vê, sem projeção e sem vista — o `get_document_impl` que
    sempre existiu e não tinha rota.

    `etag` é o token de concorrência otimista para um write subsequente
    (``if_match``): um lost update vira recusa, não sobrescrita silenciosa."""

    scope: str
    kind: str
    api_version: str
    name: str
    document: dict[str, Any]
    etag: str | None = None


class WriteKindDocumentResponse(BaseModel):
    """``POST /v1/kinds/{kind}/documents`` — the written document. ``scope``
    is DERIVED (there is no ``scope`` field on the request to have supplied
    one from)."""

    scope: str
    kind: str
    api_version: str
    name: str
    tenant: str | None = None
    version: str | None = None
    created: bool
    merged: bool
    etag: str | None = None
    source_sha256: str | None = None


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
