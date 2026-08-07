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
payload is genuinely dynamic (a memory recall ``hit``, an Instance ``spec``, a
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
    name: str = Field(description="The contributing instance name.")
    source: str = Field(description=(
        "Canonical source artifact path, e.g. 'skills/tdd/SKILL.md' ('?' when "
        "the Kind declares no storage pattern)."
    ))
    hash: str | None = Field(default=None, description=(
        "SHA-256 (full hex) of the resolved raw instance composed into this "
        "section, or null when it could not be resolved."
    ))
    version: str | None = Field(default=None, description=(
        "metadata.version of the resolved instance, when the author set one."
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
    ``version`` is set on apply (the write's instance version), absent on
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


# ── the schema graph (GET /v1/graph/kinds) ──────────────────────────────────
#
# The SET answer the registry could always give and no door served: which
# Kinds may reference which, through which field. Served because deriving it
# cost the portal one ``/v1/kinds/registry/{kind}`` call PER KIND, on every
# render — latency that grew with the workspace, for a graph the registry
# already holds whole.
#
# The models mirror ``dna.kernel.query.kind_graph`` exactly; every count in
# ``coverage`` is DERIVED there from the collections it describes, never
# enumerated. The tiering and the relation reading live in the SDK too, so this
# envelope and ``docs/reference/data-model.md`` are two renderings of ONE
# computation.


class KindGraphNode(BaseModel):
    """One registered Kind as a node. Identity only — the descriptor
    (``schema``/``ui_schema``) stays behind ``GET /v1/kinds/registry/{kind}``,
    because a graph that inlined 84 JSON Schemas would be a download, not a
    graph."""

    kind: str
    #: The Kind's alias (``sdlc-story``). Empty for a Kind that declares none.
    alias: str = ""
    #: Alias prefix (``sdlc``, ``helix``, …) — a grouping that comes from the
    #: data, not from an editorial opinion. ``ungrouped`` without an alias.
    group: str = "ungrouped"
    plane: str = ""


class KindGraphEdge(BaseModel):
    """One SCHEMA edge: Kind ``from_kind`` points at ``to_kind`` through the
    relation ``field``.

    ``tier`` says where the edge comes from — ``declared`` (``spec.relations``,
    the Kind's own statement about what it points at) or ``composition``
    (``dep_filters``: a real declaration that drives prompt composition and is
    never checked against stored data).

    ⚠️ ``followed`` and ``enforced`` are TWO flags, and neither is the same as
    ``tier == "declared"``. They were one field until fatia 5 of
    ``spec-topologia-do-grafo`` taught the kernel to resolve a spec-KEY
    address, which split what used to coincide:

    * ``followed`` — the kernel reads the target and this edge exists as data.
      True for ``by: name`` and for ``by: <key>``.
    * ``enforced`` — an unresolvable value REFUSES the write. True only for
      ``by: name``, because the by-key resolver is deliberately poorer than the
      live alias-tolerant lookups and may not veto what they accept.

    A relation whose value carries its own Kind (``to: "*"`` with a composite
    ``by``) is fully declared and neither followed nor enforced. A renderer
    that draws all edges alike asserts a confidence the model does not have;
    one that reads only ``enforced`` calls thirteen real, edge-producing
    relations unchecked.

    ``to_kind`` is a registered Kind, or ``*`` when the target Kind travels
    inside the VALUE. A declaration naming a Kind nobody registers is a gap,
    not an edge, and comes back under ``unresolved``."""

    from_kind: str
    #: The relation's name, which is also the spec field holding its value.
    field: str
    to_kind: str
    #: Declared on the relation — NOT read off ``type: array``. A model states
    #: its own multiplicity; inferring it from JSON was the old guess.
    cardinality: Literal["one", "many"] = "one"
    tier: Literal["declared", "composition"]
    #: True when the relation names SEVERAL possible target Kinds (the edge is
    #: one of them, and its siblings share ``from_kind``+``field``), or when the
    #: target is chosen per value.
    polymorphic: bool = False
    #: How the VALUE addresses the target: ``name`` (the target instance's
    #: name), a spec FIELD of the target (``workspace_id``, ``role_id``,
    #: ``tier_id``), or a composite form (``Kind:name``, ``Kind/name``,
    #: ``{kind, name}``) when ``to_kind`` is ``*``.
    by: str = "name"
    #: Does the kernel FOLLOW this relation at write time — read the target and
    #: produce a data edge? True for ``by: name`` and, since fatia 5 of
    #: ``spec-topologia-do-grafo``, for a spec-KEY address too. False only when
    #: the value carries its own Kind, which nothing parses yet.
    #:
    #: ⚠️ Declared here BECAUSE the key is new. A ``response_model`` drops what
    #: it does not name, in silence — the renderer would go on reading
    #: ``enforced`` alone and drawing every by-key relation as unchecked while
    #: its edges sat in ``dna_edges``. Guarded in ``test_mcp_graph_refs.py``.
    followed: bool = False
    #: Does an unresolvable value REFUSE the write? Strictly narrower than
    #: ``followed``, and the gap IS the ``by: <key>`` relations: the kernel
    #: resolves them and draws their edges, and deliberately does not veto over
    #: them, because the live alias-tolerant lookups (``kernel.tier()``,
    #: ``kernel.model_profile()``) accept addresses this resolver cannot see.
    #: Derived from the declaration, never from the tier.
    enforced: bool = False
    #: The relation on ``to_kind`` that is this one's other half, when the pair
    #: is declared. ``null`` for the many relations that point one way. The
    #: DECLARATION is checked (a broken pair is an ``unresolved`` row with
    #: ``origin: inverse``); instance reciprocity is reported at write time and
    #: never enforced.
    inverse_of: str | None = None


class KindGraphUnresolved(BaseModel):
    """Something the model cannot honour, or a field nobody has declared.

    Returned, not dropped: this list is the honest measure of what the model
    still cannot express, and it shrinks when relations get declared — never
    when the projection gets cleverer.

    ``origin`` says which it is, and it is what makes the list usable:

    * ``declared`` — a relation's ``to`` names a Kind no registry provides;
    * ``composition`` — a ``dep_filters`` alias no Kind claims;
    * ``inverse`` — a declared ``inverse_of`` does not PAIR: the target
      declares no such relation, or it points elsewhere, or it names a
      different inverse. Two Kinds claiming to be halves of one relation while
      disagreeing about it — which nothing could say before;
    * ``undeclared`` — the field NAME looks like a reference
      (``_id``/``_ref``/``_refs``) and no relation declares it. Often not a
      reference at all: an OAuth ``client_id``, a Stripe customer id, an IdP
      subject. This projection no longer guesses a TARGET, so the row states
      only what it can see: somebody should look.

    The first three are CLAIMS somebody made; the fourth is an invitation.
    ``coverage.declared_origins`` names the ones worth alarm, so a consumer
    DERIVES the ranking instead of hard-coding it, and never has to translate
    ``reason`` — which stays English prose for whoever reads the raw answer."""

    kind: str
    field: str
    origin: Literal["declared", "composition", "inverse", "undeclared"]
    reason: str
    #: A machine-readable sub-code, present on ``inverse`` rows
    #: (``inverse_missing`` / ``inverse_target`` / ``inverse_not_mutual``) and
    #: ``null`` elsewhere — always PRESENT so a consumer types the shape once.
    code: str | None = None


class KindGraphLimit(BaseModel):
    """One thing this graph cannot see, stated by the graph itself.

    ``code`` is the machine-readable handle a UI switches on — its own copy,
    in its own catalogue, in its own language. ``detail`` is documentation for
    whoever reads the raw answer and is NOT display copy: a screen rendering
    English shipped from a backend is the failure this project keeps its UI
    strings in i18n catalogues to avoid."""

    code: str
    detail: str


class KindGraphCoverage(BaseModel):
    """What the graph covers — the numbers a screen must qualify itself with.

    This block exists so that no consumer can honestly render the edge list as
    "all the relations". On the 06/08/2026 measurement, AFTER the relations
    became first-class, the model carried 97 schema edges: 47 declared and 50
    from composition, of which **21** are actually enforced on write. Every
    field here is derived from the collections it counts."""

    kinds: int
    edges: int
    declared: int = 0
    composition: int = 0
    #: Edges the kernel REFUSES a write over. The number that says how much of
    #: the model the runtime VETOES on, as opposed to how much of it is written
    #: down. Derived from ``edges[].enforced``, never from a tier.
    enforced: int = 0
    #: Edges the kernel READS the target of, and therefore records in
    #: ``dna_edges``. Strictly ``>= enforced`` since fatia 5, and the gap is
    #: the ``by: <key>`` relations. A screen reporting only ``enforced`` shows
    #: a model less connected than the data it is drawn from.
    followed: int = 0
    #: How many Kinds declare at least one relation — the epic's own measuring
    #: stick, since most Kinds legitimately point at nothing.
    kinds_with_relations: int = 0
    unresolved: int = 0
    #: ``unresolved`` split by ``origin`` — the shape of the gap list, which
    #: the single total cannot show: 23 rows of one origin read exactly like
    #: 23 broken declarations. Derived from the rows, so it cannot drift.
    unresolved_by_origin: dict[str, int] = Field(default_factory=dict)
    #: The ``unresolved[].origin`` values that mean a DECLARATION the model
    #: cannot honour — the rows that deserve alarm. A list the consumer derives
    #: from, so the ranking is never re-typed in a screen and can grow without
    #: a client release.
    declared_origins: list[str] = Field(default_factory=list)
    limits: list[KindGraphLimit] = Field(default_factory=list)


class KindGraphResponse(BaseModel):
    """``GET /v1/graph/kinds`` — the whole SCHEMA graph in one call.

    SCHEMA, not data: these edges say which Kinds MAY point at which. Which
    INSTANCES actually point at which is a different graph, derived at write
    time, and this route does not answer it — ``coverage.limits`` carries that
    statement on the wire so it travels with the answer instead of living in a
    doc page a caller may never read.

    The ``undeclarable`` list this envelope used to carry is GONE, and its
    absence is the feature: those rows were real references the annotation
    could not express, and the declaration expresses them now. They are edges,
    with ``enforced: false`` saying exactly how far the runtime goes."""

    #: The scope the registry was resolved for; ``null`` when the caller named
    #: none and the deployment's default applied.
    scope: str | None = None
    kinds: list[KindGraphNode] = Field(default_factory=list)
    edges: list[KindGraphEdge] = Field(default_factory=list)
    unresolved: list[KindGraphUnresolved] = Field(default_factory=list)
    coverage: KindGraphCoverage


class RegisteredKindEntry(BaseModel):
    """One row of ``GET /v1/kinds/registry`` — a Kind the registry actually
    serves in this scope, with the facts a caller needs BEFORE acting on it.

    Deliberately the same row the MCP ``list_kinds`` tool has always returned
    (both project ``list_kinds_impl``): ``writable``/``deletable`` plus the
    refusal that explains a ``false``, so an operation the runtime would refuse
    is visible without attempting it."""

    kind: str
    alias: str | None = None
    api_version: str
    #: The quota family a call on this Kind is metered under.
    family: str | None = None
    #: ``composition`` (it composes into prompts) or ``record`` (it does not).
    plane: str = "composition"
    display_label: str | None = None
    tenant_scope: str | None = None
    storage_pattern: str | None = None
    traits: list[str] = Field(default_factory=list)
    writable: bool = True
    write_refusal: str | None = None
    deletable: bool = True
    delete_refusal: str | None = None


class RegisteredKindsResponse(BaseModel):
    """``GET /v1/kinds/registry`` — the Kind CATALOG of one scope.

    The collection sibling of ``GET /v1/kinds/registry/{kind}``, and the REST
    door for a capability the runtime already had: ``list_kinds_impl`` has
    served the MCP face since the catalog existed, so a portal could ask an
    agent what Kinds exist but could not ask the read-API. Every consumer that
    wanted the list had to hardcode one — and a hardcoded list is exactly how a
    newly-registered Kind stays invisible.

    ``filtered_by_plan`` is true only when the caller's unlocked feature
    families actually SHORTENED the catalog, with ``filtered_out`` naming how
    many rows were withheld — so "the plan filtered nothing" and "the plan hid
    forty Kinds" are different answers."""

    scope: str
    kinds: list[RegisteredKindEntry] = Field(default_factory=list)
    count: int = 0
    filtered_by_plan: bool = False
    filtered_out: int = 0


# ── Kind authoring (the dedicated door — writes an INERT KindDefinition) ────


class AuthorKindResponse(BaseModel):
    """``POST /v1/kinds`` — the authored Kind. ``approved`` is ALWAYS false
    here: this door cannot approve, so the field states the instance's actual
    state rather than echoing anything the caller sent."""

    namespace: str
    kind: str
    name: str
    approved: bool
    #: The caller's VERIFIED identity as the instance recorded it. ECHOED, never
    #: accepted — there is no request field it could have come from.
    proposed_by: str | None = None
    version: str | None = None
    #: The authored JSON Schema, ECHOED (wire name, like the two other doors —
    #: shadow warning silenced narrowly in pyproject). The MCP Apps kind-draft
    #: card renders its editable rows from this echo; dropping it here would
    #: violate the fidelity contract (FastAPI silently strips unmodeled keys).
    schema: dict[str, Any] | None = None
    #: What the Kind POINTS AT, echoed in the shape it was STORED in (not the
    #: shape the caller sent — ``Relation.to_declaration()`` drops a restated
    #: default, so the two differ and the instance is the one worth reading
    #: back). ``None`` for a Kind that declared none.
    relations: dict[str, Any] | None = None
    #: The DECLARED plane, or ``None``. ``None`` is not ``"composition"``: the
    #: instance stores no plane at all unless one was declared, and collapsing
    #: the two here would report a decision nobody made.
    plane: str | None = None
    #: DERIVED, never stored, and ``null`` unless there is something to say —
    #: i-117's third state, where "the prose named nothing" and "the prose named
    #: three things" both produce silence rather than a menu. Each entry is
    #: ``{field, to, cardinality}``. MODELED because FastAPI strips unmodeled
    #: keys, which is how a hint computed correctly reaches nobody.
    suggested_relations: list[dict[str, Any]] | None = None
    #: The paste-ready sentence that goes with ``suggested_relations``.
    suggestion: str | None = None


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
    fact that this Kind governed real instances for a while."""

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
    """One ``KindDefinition`` instance as the audit surface sees it — ALL THREE
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
    #: accepts instances with no validation at all, a revoked one refuses them
    #: and marks every existing instance invalid. Reporting the loosest and the
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
    read describe the SAME instance, and two independent field lists are two
    vocabularies for one thing — the kind of drift that reads, to the human
    doing the review, as two different instances.

    What it adds is what the roster deliberately withholds. ``schema`` is the
    reason the route exists: registration is what confers schema validation and
    storage routing, so "should this take effect?" is a question ABOUT the
    schema, and a reviewer who cannot see it is not reviewing anything.
    ``traits`` travels with it because it is the other half of what the
    authoring door stored and the other half of what would take effect.

    ``schema`` is ``null``, never ``{}``, for an instance that stored none —
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
    #: How instances of this Kind will READ — the ordered fields, their human
    #: labels, their semantic roles, and what is hidden — composed with the
    #: Kind's own ``display_label``/``ascii_icon``.
    #:
    #: It travels here for the same reason ``schema`` does: this approval
    #: confers it. ``schema`` says what an instance may CONTAIN; this says what
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
    #: ⭐ What the Kind POINTS AT — and the field that makes this route load
    #: bearing for the human gate rather than merely informative. Approval is
    #: what REGISTERS the Kind, and registration is what makes the write path
    #: resolve these relations and the graph draw them. A reviewer who is not
    #: shown the declared links is approving edges nobody displayed, which is
    #: the shape of a gate that has stopped gating.
    #:
    #: Read off the instance VERBATIM, never re-normalized on the way out: a
    #: stored declaration this runtime can no longer parse must reach the
    #: reviewer as what it is, not as ``null``.
    relations: dict[str, Any] | None = None
    #: The DECLARED plane, or ``null`` for an instance that declares none.
    #: ``null`` is NOT ``"composition"`` — the default is applied by whatever
    #: reads the instance, and keeping the two apart is what makes "how many
    #: tenant Kinds are on the composition plane BY CHOICE?" a question with an
    #: answer.
    plane: str | None = None


class AuthoredKindsResponse(BaseModel):
    """``GET /v1/kinds`` — every authored Kind in the scope, approved or not.
    Instances, not registry entries: an UNAPPROVED Kind is exactly the one the
    registry does not have, and it is the one a reviewer came here for."""

    scope: str
    kinds: list[AuthoredKindSummary] = Field(default_factory=list)


# ── bundle entries (list/read/write/revert a bundle-file fork — plane B) ────
#
# A bundle-pattern Kind (Skill, and any future bundle Kind) stores MULTIPLE
# files per instance (SKILL.md + scripts/…), not a single spec — these are the
# file-grained twin of DefinitionView/DefinitionWriteResponse above, generic
# over any bundle Kind, with the SAME LayerPolicy governance (a fork on a
# LOCKED Kind is vetoed, 403).


class BundleEntrySummary(BaseModel):
    entry: str
    overridden: bool


class BundleEntriesView(BaseModel):
    """``GET /v1/definitions/{kind}/{name}/entries`` — a bundle instance's
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
    #: See :class:`RecallResponse` — the same two transaction-time fields, so
    #: the list and the search surface stay legible as one pair.
    as_of: str | None = None
    as_of_truncated: list[str] | None = None


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
    #: Echoed ONLY on a transaction-time read (``?as_of=``), normalized to UTC.
    #: Absent means "the current belief state" — a caller can tell a historical
    #: answer from a live one without re-reading its own request.
    as_of: str | None = None
    #: Memories the store cannot answer for at ``as_of`` because their version
    #: history was pruned past it. NAMED, not counted: "no record" is a blind
    #: spot the caller must be able to SEE, never silently "no memory".
    as_of_truncated: list[str] | None = None


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


# ── the generic, kubernetes-shaped instance write ───────────────────────────
#
# POST /v1/kinds/{kind}/instances — the path names the Kind (the k8s
# convention this route follows: "kind is inferred from the endpoint the
# client submits to"), the body carries only what k8s calls `metadata`/`spec`.


class WriteKindInstanceRequest(BaseModel):
    """``POST /v1/kinds/{kind}/instances`` — the instance to write.

    Deliberately narrow: no ``scope``, no ``claims`` anywhere on this model —
    neither is reachable through this route's body (identity/scope are never
    caller input here; see the route for the full reasoning).

    ``kind`` is OPTIONAL and, when given, MUST equal the path's ``{kind}`` —
    a caller naming a DIFFERENT Kind in the body is refused (400) rather than
    the path or the body silently winning. Two sources stating one fact is
    exactly the defect this route exists to close.

    ``source_sha256``, when given, cites the ``SourceArtifact`` (by content
    address) this instance was extracted from — the runtime closes the
    provenance edge (``derived_refs``) server-side."""

    metadata: dict[str, Any]
    spec: dict[str, Any]
    kind: str | None = None
    source_sha256: str | None = None


class ListKindInstancesResponse(BaseModel):
    """``GET /v1/kinds/{kind}/instances`` — uma página de instâncias do Kind.

    `instances` é a linha como o kernel a moldou: `{"name": …}` sem projeção, e
    `{"name": …, "spec": {…}}` com `fields`. `projected` ecoa o que foi pedido,
    para um leitor distinguir uma página de nomes de uma projetada — sem isso,
    um `spec` ausente seria ambíguo entre "não pedi" e "não tem".

    `has_more` é respondido buscando UMA linha a mais, não adivinhado a partir
    de a página ter vindo cheia."""

    scope: str
    kind: str
    api_version: str
    instances: list[dict[str, Any]]
    count: int
    offset: int
    has_more: bool
    projected: list[str] | None = None


class GetKindInstanceResponse(BaseModel):
    """``GET /v1/kinds/{kind}/instances/{name}`` — UMA instância, VERBATIM.

    A lista projetada passa pela vista dos readers quando o Kind é produzível
    por bundle (Agent, Skill…) — e a vista NORMALIZA: `spec.description` e
    `spec.tools_requiring_confirmation` de um Agent gravado pelo funil
    genérico simplesmente não viajam por ela (medido 05/08/2026 na aba
    Configuração do dna-cloud). Esta porta lê a instância como a camada do
    chamador o vê, sem projeção e sem vista — o `get_instance_impl` que
    sempre existiu e não tinha rota.

    `etag` é o token de concorrência otimista para um write subsequente
    (``if_match``): um lost update vira recusa, não sobrescrita silenciosa.

    Os TRÊS campos `as_of*` só aparecem quando o chamador pediu leitura no
    tempo, e existem para que uma resposta histórica não seja confundível com
    uma viva por quem só olha `instance` (i-106: a rota ACEITAVA `?as_of=` e
    devolvia o presente, sem nada na resposta que a desmentisse). Presentes ⇒ o
    corpo é o estado de crença daquele instante; ausentes ⇒ é o de agora."""

    scope: str
    kind: str
    api_version: str
    name: str
    instance: dict[str, Any]
    etag: str | None = None
    #: O instante pedido, NORMALIZADO para ISO-8601 UTC — devolver o que o
    #: chamador digitou esconderia um fuso mal lido.
    as_of: str | None = None
    #: Qual versão da instância respondeu (`dna_versions.version`).
    as_of_version: int | None = None
    #: Quando ela foi GRAVADA (tempo de transação). Nunca igual a `as_of`, e é a
    #: distância entre os dois que diz há quanto tempo aquela crença estava
    #: parada quando o chamador perguntou.
    as_of_recorded_at: str | None = None


class ResolveInstanceResponse(BaseModel):
    """``GET /v1/instances/{id}`` — the ONE instance a short id names (i-114).

    The id lane, kept separate from the ``{kind}/{name}`` lane on purpose. A
    short name and a short id are both strings; a single door that accepted
    "a name or maybe an id" would eventually answer a name query with an id
    match, and nothing in the response would say so.

    ``id`` echoes back the FULL id, not the prefix the caller sent — the
    expansion is the answer, exactly as ``git rev-parse`` returns the whole
    hash. A prefix matching more than one instance is a **409**, never a pick.
    """

    #: The full 12-character id the prefix expanded to.
    id: str
    scope: str
    kind: str
    api_version: str
    name: str
    instance: dict[str, Any]
    etag: str | None = None


class GraphRefEdge(BaseModel):
    """ONE edge of the derived reference graph.

    ``resolved: false`` is a DANGLING reference — declared, written, resolving
    to nothing. It travels rather than being filtered out: with
    ``DNA_REF_VALIDATION=warn`` (the default) such an instance persists, so
    dropping the row would render a tidier graph than the data deserves. These
    rows ARE the list of what is broken.

    ``to_scope`` may differ from the request's scope (a reference can resolve
    in a parent scope) and is ``null`` when the resolution went through the
    inheritance chain without the parent being recorded — never a stand-in for
    "the same scope"."""

    depth: int
    direction: str
    #: A aresta grava a apiVersion dos DOIS lados (fatia 1 da
    #: spec-topologia-do-grafo). `to_kind` sozinho identifica um NOME de Kind,
    #: e um nome só é único entre apiVersions porque o registro recusa colisões
    #: — invariante de outro módulo. Um lado da aresta que dependesse disso
    #: estaria certo por sorte emprestada.
    from_api_version: str | None = None
    from_kind: str
    from_name: str
    #: The spec field the reference was declared on.
    field: str
    #: Position inside an array-valued reference; 0 for a scalar one.
    ordinal: int
    to_api_version: str | None = None
    to_kind: str | None = None
    to_name: str
    to_scope: str | None = None
    #: Quando a instância alvo foi APAGADA (i-131). A aresta continua existindo
    #: de propósito — a decisão do founder sobre o `AuditLog` diz que uma linha
    #: de auditoria sobre instância apagada TEM que continuar apontando, e o
    #: `on_target_delete: allow` é o vocabulário disso. O defeito que este campo
    #: fecha não era a aresta sobreviver; era ela seguir dizendo
    #: `resolved: true` enquanto sobrevivia.
    to_deleted_at: str | None = None
    #: The ``metadata.id`` of the instance this edge actually resolved to
    #: (i-114) — the pair Kubernetes' ``ownerReferences`` carries, and for the
    #: same reason: the AUTHOR wrote ``to_name``, but which instance that name
    #: hit is a fact only the write path knew, and it stops being recoverable
    #: the moment the name moves. ``null`` when the edge is dangling, or when
    #: the target predates the id. Never a stand-in for "unchanged".
    to_id: str | None = None
    #: Every declared target — more than one means a polymorphic reference.
    declared_to: list[str] = []
    resolved: bool
    #: This edge points back at a node the walk had already visited. Reported
    #: rather than hidden — ``Story.dependencies → Story`` makes cycles
    #: ordinary data, and the closing edge is the one that shows the cycle.
    closes_cycle: bool = False
    #: The instance version these edges were derived from. Lower than the
    #: instance's current version means the relations are STALE.
    from_version: int


class GraphRefsResponse(BaseModel):
    """``GET /v1/kinds/{kind}/instances/{name}/refs`` — the DATA graph.

    ``stop`` says WHY the walk ended (``complete`` / ``depth_reached`` /
    ``truncated``), because a caller that cannot tell "this is everything" from
    "this is where I stopped" will render the second as the first.

    ``graph_producer`` reports the producer's mode (``warn`` / ``enforce`` /
    ``off``). With it ``off`` the write path performs no reference lookups, so
    no edges are produced — defensible operationally, and NOT the same as "this
    instance has no relations". A store that keeps no edge graph at all answers
    501, never an empty list.

    ⚠️ These are the ENFORCED relations only — the ones ``spec.relations``
    declares with a concrete target addressed by instance name, which is the
    only kind the write path resolves. The schema graph also carries relations
    addressed by a domain key or carrying their Kind in the value, plus
    composition edges from ``dep_filters``, none of which is ever checked
    against data; calling this "the relations" would claim a completeness the
    producer does not have."""

    scope: str
    kind: str
    api_version: str
    name: str
    direction: str
    depth: int
    stop: str
    graph_producer: str
    edges: list[GraphRefEdge] = []


class WriteKindInstanceResponse(BaseModel):
    """``POST /v1/kinds/{kind}/instances`` — the written instance. ``scope``
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
