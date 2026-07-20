"""SdlcExtension — software-development lifecycle Kinds.

Seven Kinds for declarative product/engineering management as YAML/markdown:

- ``Roadmap`` — top-level container, lists epics across horizons.
- ``Epic`` — aggregation umbrella (Jira/ADO-aligned); optional target date.
- ``Feature`` — shippable unit; implements UseCases; collects stories.
- ``Story`` — granular task; has owner + estimate + acceptance criteria.
- ``Issue`` — bug/enhancement/question/task; can link to a Finding.
- ``Spec`` — top-level design artifact (ADR-style).
- ``Plan`` — implementation plan, child of a Spec.

Designed to compose with existing DNA Kinds:

- ``Epic.spec.target_package`` references a ``Genome`` (Phase 9 catalog).
- ``Epic.spec.target_version`` matches ``Genome.spec.version`` (Phase 10).
- ``Feature.spec.use_cases`` references existing ``UseCase`` docs (UML modeling).
- ``Feature.spec.owner`` / ``Story.spec.owner`` reference ``Actor`` docs.
- ``Issue.spec.related_finding`` references ``Finding`` docs (eval-derived).

Hierarchy: ``Roadmap → Epic → Feature → Story``. Linkage to design
axis is via ``Story.spec_refs[]`` (M:N to Spec).

v1.3 BREAKING: Milestone Kind renamed to Epic. ``kind: Milestone``
no longer parses; legacy YAMLs must be migrated.
"""
from __future__ import annotations
from typing import Any
from dna.kernel.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost, ReaderPort, StorageDescriptor, TenantScope, WriterPort
from dna.kernel.kind_base import KindBase


# ---------------------------------------------------------------------------
# Status enums (string literals — kept simple so YAML editing stays trivial)
# ---------------------------------------------------------------------------

# v1.3: MILESTONE_STATUSES → EPIC_STATUSES (Jira/ADO alignment).
EPIC_STATUSES = ("planning", "in-progress", "done", "cancelled", "deprecated")
FEATURE_STATUSES = ("discovery", "in-development", "done", "cancelled", "blocked")
# 2026-05-26 — rec-triage-as-status (spike answered):
# `needs-triage` prepended (pré-groom — sem AC/DoD/owner ainda).
# `deferred` antes de cancelled (PM olhou, não é agora, talvez depois).
# Stories existentes em `todo` permanecem como assumed-triaged.
STORY_STATUSES = (
    "needs-triage",
    "todo",
    "in-progress",
    "review",
    "done",
    "blocked",
    "deferred",
    "cancelled",
)
ISSUE_STATUSES = ("open", "triaged", "in-progress", "resolved", "wont-fix", "duplicate")
ISSUE_TYPES = ("bug", "enhancement", "question", "task")
ISSUE_SEVERITIES = ("low", "medium", "high", "critical")

# v1.13: the Kaizen observation arc (observed → routed → resolved) lives
# ONLY in the descriptor kinds/kaizen.kind.yaml since F3 P2 — the enum is
# the schema's `status.enum`; CLI call sites use literals.

# v1.5: shared priority enum across Story/Feature/Epic/Issue.
# Jira-aligned (lexically descending = ascending priority works in pickers).
PRIORITIES = ("highest", "high", "medium", "low", "lowest")

# Universal journey phases — additive layer over Story/Feature/Epic
# status, Spec phase, etc. Maps to Superpowers / BMAD / Spec Kit / Kiro:
#   discover → brainstorming, BMAD Analyst, Spec Kit /specify-prep
#   specify  → BMAD PM/Architect, Spec Kit /specify+/clarify
#   plan     → Superpowers writing-plans, Spec Kit /plan+/tasks
#   build    → executing-plans, BMAD Dev, TDD
#   verify   → running test guides → TestRun (a linked passing run lights it)
#   reflect  → verification-before-completion, BMAD QA, retros
JOURNEY_PHASES = ("discover", "specify", "plan", "build", "verify", "reflect")

# v1.6: Activity Timeline event types. Open enum — additionalProperties
# True on each entry lets new types add fields without schema migration.
# Phase 1 (s-timeline-schema): the names below are the RECOGNIZED types,
# but the schema deliberately does NOT close the vocabulary (no enum) —
# it's documentation-style so future types (e.g. "deploy", "review",
# "block_resolved") just work. This became load-bearing with
# s-write-path-validation (i-008): writes now really validate against the
# schema, and the CLI already stamps types beyond the original five
# ("pr_opened" from `dna sdlc story pr`) — a closed enum here vetoed the
# PR-URL stamp the first time the write path had teeth.
TIMELINE_TYPES = (
    "status_change",     # status flip via CLI/Studio
    "groom",             # board grooming (priority/labels/sprint update)
    "comment",           # manual comment (Studio future)
    "decision",          # extracted from AgentSession transcript
    "artifact_produced", # files/commits/eval-results from a session
)

TIMELINE_SOURCES = (
    "cli",                       # dna sdlc story {start,done,...}
    "studio",                    # Studio drawer save
    "mcp",                       # a write TOOL on the DNA MCP server (f-mcp-sdlc-write)
    "agent-session-extracted",    # extractor pass over a captured session
    "system",                    # auto-stamping that isn't user-attributable
)


def _produces_field_schema() -> dict[str, Any]:
    """JSON Schema for the spec.produces[] field (s-produces-schema-resolver).

    A work item is a HUB: produces[] lists the artifacts it produced, of ANY
    Kind (mirrors AgentSession.produced_artifacts). The derived journey + the
    FOCUS panel + ``dna sdlc produces list`` all read it via
    resolve_work_item_outputs (produces[] ∪ legacy back-refs).
    """
    return {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["kind", "name"],
            "additionalProperties": True,
            "properties": {
                "kind": {"type": "string", "description": "Artifact Kind (any)."},
                "name": {"type": "string", "description": "Artifact doc name."},
                "role": {"type": "string", "description": "Optional role hint (e.g. visual-spec, plan, investigation)."},
                "at": {"type": "string", "format": "date-time"},
            },
        },
        "description": "Artifacts this work item produced — any Kind (hub).",
    }


def _timeline_field_schema() -> dict[str, Any]:
    """JSON Schema for the spec.timeline[] field. Shared by Story,
    Feature, and Issue Kinds — same shape, same docs.

    Each entry has 3 required fields (at, actor, type) plus a
    type-specific set of optional fields. ``additionalProperties: True``
    on the entry lets a agent-session-extractor stamp custom fields
    (e.g. ``confidence`` on a decision event) without breaking the
    schema contract.
    """
    return {
        "type": "array",
        "description": (
            "Append-only activity log. Auto-stamped by the CLI on every "
            "status flip / groom / artifact write; populated by "
            "AgentSession capture for decision + artifact_produced "
            "events. Render in Studio as activity stream."
        ),
        "items": {
            "type": "object",
            "required": ["at", "actor", "type"],
            "properties": {
                "at": {"type": "string", "format": "date-time"},
                "actor": {
                    "type": "string",
                    "description": "Who triggered the event (Actor name or 'claude-code').",
                },
                "type": {
                    "type": "string",
                    "description": (
                        "Event type. Recognized: "
                        + ", ".join(TIMELINE_TYPES)
                        + " (open vocabulary — new types are additive, "
                        "e.g. pr_opened)."
                    ),
                },
                "source": {"type": "string", "enum": list(TIMELINE_SOURCES)},
                # Type-specific (all opt; entry shape varies per type).
                "from": {"type": "string", "description": "status_change: previous status."},
                "to": {"type": "string", "description": "status_change: new status."},
                "fields": {
                    "type": "object",
                    "description": "groom: which fields changed and to what.",
                },
                "summary": {
                    "type": "string",
                    "description": "comment/decision: short human-readable text.",
                },
                "excerpt": {
                    "type": "string",
                    "description": "decision: snippet from the source transcript.",
                },
                "paths": {
                    "type": "array", "items": {"type": "string"},
                    "description": "artifact_produced: file paths touched.",
                },
                "commit_ref": {
                    "type": "string",
                    "description": "Git SHA associated with this event (when relevant).",
                },
                "session_ref": {
                    "type": "string",
                    "description": "Back-link to a AgentSession that produced this event.",
                },
            },
            "additionalProperties": True,
        },
    }


# ---------------------------------------------------------------------------
# Roadmap — top-level container
# ---------------------------------------------------------------------------

class RoadmapKind(KindBase):
    """Roadmap — annual/quarterly plan grouping epics by horizon."""

    api_version = "github.com/ruinosus/dna/sdlc/v1"
    scope = TenantScope.GLOBAL  # SDLC primitives are project-level, not per-tenant
    kind = "Roadmap"
    alias = "sdlc-roadmap"
    scope_inheritable = False
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    storage = StorageDescriptor.yaml("roadmaps")
    graph_style = {"fill": "#0EA5E9", "stroke": "#0284C7", "text_color": "#fff"}
    ascii_icon = "🗺️"
    display_label = "Roadmaps"
    is_prompt_target = False
    flatten_in_context = False
    plane = "record"
    prompt_target_priority = 0
    docs = (
        "A Roadmap groups Epics across time horizons (e.g. Q1 2026, "
        "Q2 2026). Pure organizational doc — no status of its own; the "
        "rolled-up status comes from the Epics it lists."
    )

    def dep_filters(self) -> dict[str, str]:
        return {"epics": "sdlc-epic"}

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["description", "horizons"],
            "properties": {
                "description": {"type": "string"},
                "owner_team": {"type": "string"},
                "horizons": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["label", "epics"],
                        "properties": {
                            "label": {"type": "string", "description": "e.g. 'Q1 2026'"},
                            "start_date": {"type": "string", "format": "date"},
                            "end_date": {"type": "string", "format": "date"},
                            "epics": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Names of Epic docs in this horizon",
                            },
                        },
                    },
                },
                "links": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "External URLs (Confluence, Notion, etc.)",
                },
                "journey_phase": {
                    "type": "string", "enum": list(JOURNEY_PHASES),
                    "description": (
                        "Universal journey phase. Roadmaps typically "
                        "live in `discover` or `specify` — they're the "
                        "north star, not the build."
                    ),
                },
            },
            "additionalProperties": True,
        }

    def summary(self, doc: Any) -> dict[str, Any]:
        spec = doc.spec if hasattr(doc, "spec") else doc
        s = spec if isinstance(spec, dict) else {}
        horizons = s.get("horizons", []) or []
        total = sum(len(h.get("epics", []) or []) for h in horizons)
        return {
            "description": (s.get("description") or "")[:80],
            "horizons": len(horizons),
            "epics": total,
        }


# ---------------------------------------------------------------------------
# Epic — Jira/ADO-aligned aggregation umbrella (was Milestone in v1.2)
# ---------------------------------------------------------------------------

class EpicKind(KindBase):
    """Epic — aggregation umbrella (Jira/ADO terminology).

    Replaces the v1.2 Milestone Kind. Same fields, market-aligned name,
    plus ``target_date`` is now OPTIONAL — Epics are aggregations
    first, dated releases second. When ``target_date`` is set, an
    Epic doubles as a Release marker.
    """

    api_version = "github.com/ruinosus/dna/sdlc/v1"
    scope = TenantScope.GLOBAL  # SDLC primitives are project-level, not per-tenant
    kind = "Epic"
    alias = "sdlc-epic"
    # Per-scope ledger, exactly like its Roadmap/Feature/Story/Issue siblings —
    # an Epic in `_lib` must NOT leak into every child scope. This was MISSED by
    # the v1.3 Milestone→Epic rename: the classification stayed pinned to the
    # dead name (kernel `_LEGACY_NON_INHERITABLE` + resolver
    # DEFAULT_NON_INHERITABLE_KINDS_V1 both still say "Milestone"), so Epic
    # silently inherited while its siblings did not.
    scope_inheritable = False
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    storage = StorageDescriptor.yaml("epics")
    graph_style = {"fill": "#8B5CF6", "stroke": "#7C3AED", "text_color": "#fff"}
    ascii_icon = "🎯"
    display_label = "Epics"
    is_prompt_target = False
    flatten_in_context = False
    plane = "record"
    prompt_target_priority = 0
    docs = (
        "An Epic groups Features under a single business goal "
        "(Jira/ADO terminology). May optionally carry a target_date + "
        "target_package + target_version when the Epic is also a "
        "dated release; otherwise it's a pure aggregation umbrella. "
        "status moves through planning → in-progress → done."
    )

    def dep_filters(self) -> dict[str, str]:
        return {"features": "sdlc-feature"}

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["status"],  # v1.3: target_date no longer required
            "properties": {
                "title": {
                    "type": "string",
                    "description": (
                        "Human-readable display name (Jira 'summary'). "
                        "Falls back to description, then to metadata.name slug."
                    ),
                },
                "description": {"type": "string"},
                "target_date": {"type": "string", "format": "date"},
                "status": {"type": "string", "enum": list(EPIC_STATUSES)},
                "target_package": {
                    "type": "string",
                    "description": "owner/name reference to a Genome",
                },
                "target_version": {
                    "type": "string",
                    "description": "Semver to match Genome.spec.version when done",
                },
                "features": {"type": "array", "items": {"type": "string"}},
                "closed_at": {"type": "string", "format": "date-time"},
                "cancelled_reason": {"type": "string"},
                # v1.5 — board-grade fields. Epics drop sprint_ref +
                # time_tracking + mockups + release_target (the Epic
                # IS a release target; sprints don't span Epics).
                "priority": {"type": "string", "enum": list(PRIORITIES)},
                "labels": {"type": "array", "items": {"type": "string"}},
                "reporter": {"type": "string"},
                "watchers": {"type": "array", "items": {"type": "string"}},
                "journey_phase": {
                    "type": "string", "enum": list(JOURNEY_PHASES),
                    "description": (
                        "Universal journey phase (discover → specify → "
                        "plan → build → reflect). Additive layer over "
                        "Story/Feature/Epic status, Spec phase, etc. "
                        "Lets the journey ledger pin this doc to one of "
                        "five universal phases compatible with "
                        "Superpowers / BMAD / Spec Kit / Kiro."
                    ),
                },
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
                "definition_of_done": {"type": "array", "items": {"type": "string"}},
                "business_value": {
                    "type": "number", "minimum": 0, "maximum": 1000,
                },
                "produces": _produces_field_schema(),
                "timeline": _timeline_field_schema(),
            },
            "additionalProperties": True,
        }

    def summary(self, doc: Any) -> dict[str, Any]:
        spec = doc.spec if hasattr(doc, "spec") else doc
        s = spec if isinstance(spec, dict) else {}
        return {
            "status": s.get("status", "planning"),
            "target_date": s.get("target_date", ""),
            "target_package": s.get("target_package", ""),
            "target_version": s.get("target_version", ""),
            "features": len(s.get("features", []) or []),
            "priority": s.get("priority", "medium"),
            "labels": s.get("labels", []) or [],
            "business_value": s.get("business_value"),
        }


# ---------------------------------------------------------------------------
# Feature — shippable unit
# ---------------------------------------------------------------------------

class FeatureKind(KindBase):
    """Feature — a shippable unit of work composed of Stories."""

    api_version = "github.com/ruinosus/dna/sdlc/v1"
    scope = TenantScope.GLOBAL  # SDLC primitives are project-level, not per-tenant
    kind = "Feature"
    alias = "sdlc-feature"
    scope_inheritable = False
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    storage = StorageDescriptor.yaml("features")
    graph_style = {"fill": "#10B981", "stroke": "#059669", "text_color": "#fff"}
    ascii_icon = "🚀"
    display_label = "Features"
    is_prompt_target = False
    flatten_in_context = False
    plane = "record"
    prompt_target_priority = 0
    docs = (
        "A Feature is a shippable unit. It implements one or more "
        "UseCases, decomposes into Stories, and is owned by an Actor. "
        "Its status reflects the development pipeline: discovery → "
        "in-development → done."
    )

    def dep_filters(self) -> dict[str, str]:
        return {
            "stories": "sdlc-story",
            "use_cases": "helix-usecase",
            "owner": "helix-actor",
            "epic": "sdlc-epic",
        }

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["description", "status"],
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Human-readable display name (Jira 'summary').",
                },
                "description": {"type": "string"},
                # User-story slots (2026-05-11 UX audit) — same shape as
                # StorySpec. Features ARE user-stories at a coarser grain;
                # rendering parity in Studio.
                "as_a": {
                    "type": "string",
                    "description": "Role: 'As a <role>'. INVEST/user-story format slot.",
                },
                "i_want": {
                    "type": "string",
                    "description": "Goal: 'I want <goal>'. INVEST/user-story format slot.",
                },
                "so_that": {
                    "type": "string",
                    "description": "Benefit: 'so that <benefit>'. INVEST/user-story format slot.",
                },
                "acceptance_criteria": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Feature-level AC (parent of Story-level AC).",
                },
                "definition_of_done": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Feature-level DoD checks.",
                },
                "narrative_line": {
                    "type": "string",
                    "description": (
                        "One-sentence agent-curated prose summary of what "
                        "this Feature has been DOING (past-tense, semantic) — "
                        "shown next to the Feature in Studio's narrative "
                        "swimlane. Updated by the working agent as scope "
                        "evolves. Distinct from `description` (intent / "
                        "problem statement, written once at file-time)."
                    ),
                },
                "status": {"type": "string", "enum": list(FEATURE_STATUSES)},
                "epic": {"type": "string", "description": "Parent Epic name"},
                "stories": {"type": "array", "items": {"type": "string"}},
                "use_cases": {"type": "array", "items": {"type": "string"}},
                "owner": {"type": "string", "description": "Actor name"},
                "estimate": {
                    "type": "string",
                    "description": "T-shirt size or story points (free-form)",
                },
                "closed_at": {"type": "string", "format": "date-time"},
                "blocked_reason": {"type": "string"},
                # v1.5 — board-grade fields.
                "priority": {"type": "string", "enum": list(PRIORITIES)},
                "labels": {"type": "array", "items": {"type": "string"}},
                "reporter": {"type": "string"},
                "watchers": {"type": "array", "items": {"type": "string"}},
                "journey_phase": {
                    "type": "string", "enum": list(JOURNEY_PHASES),
                    "description": (
                        "Universal journey phase (discover → specify → "
                        "plan → build → reflect). Additive layer over "
                        "Story/Feature/Epic status, Spec phase, etc. "
                        "Lets the journey ledger pin this doc to one of "
                        "five universal phases compatible with "
                        "Superpowers / BMAD / Spec Kit / Kiro."
                    ),
                },
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
                "sprint_ref": {"type": "string"},
                "time_tracking": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "logged_h": {"type": "number", "minimum": 0},
                        "remaining_h": {"type": "number", "minimum": 0},
                        "original_estimate_h": {"type": "number", "minimum": 0},
                    },
                },
                "definition_of_done": {"type": "array", "items": {"type": "string"}},
                "business_value": {
                    "type": "number", "minimum": 0, "maximum": 1000,
                },
                "mockups": {"type": "array", "items": {"type": "string"}},
                "release_target": {"type": "string"},
                "produces": _produces_field_schema(),
                "timeline": _timeline_field_schema(),
            },
            "additionalProperties": True,
        }

    def summary(self, doc: Any) -> dict[str, Any]:
        spec = doc.spec if hasattr(doc, "spec") else doc
        s = spec if isinstance(spec, dict) else {}
        return {
            "status": s.get("status", "discovery"),
            "epic": s.get("epic", ""),
            "owner": s.get("owner", ""),
            "stories": len(s.get("stories", []) or []),
            "use_cases": len(s.get("use_cases", []) or []),
            "priority": s.get("priority", "medium"),
            "labels": s.get("labels", []) or [],
            "sprint_ref": s.get("sprint_ref", ""),
            "business_value": s.get("business_value"),
        }


# ---------------------------------------------------------------------------
# Story — granular task
# ---------------------------------------------------------------------------

class StoryKind(KindBase):
    """Story — a developer-sized unit of work; child of a Feature."""

    api_version = "github.com/ruinosus/dna/sdlc/v1"
    scope = TenantScope.GLOBAL  # SDLC primitives are project-level, not per-tenant
    kind = "Story"
    alias = "sdlc-story"
    scope_inheritable = False
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    storage = StorageDescriptor.yaml("stories")
    graph_style = {"fill": "#F59E0B", "stroke": "#D97706", "text_color": "#fff"}
    ascii_icon = "📖"
    display_label = "Stories"
    is_prompt_target = False
    flatten_in_context = False
    plane = "record"
    prompt_target_priority = 0
    docs = (
        "A Story is a granular task: one developer, one PR, one estimate. "
        "Lists acceptance criteria, dependencies (other Stories that must "
        "land first), and rolls up to a Feature."
    )

    # P2L2 — Story is the bread-and-butter Plan-mode item. The SDLC
    # board (mode-landing) is the primary surface; detail/edit live
    # under /docs/Story/:name via the generic ExplorerPage.
    from dna.kernel.studio_ui import StudioUIMetadata as _UI
    ui = _UI(
        mode="plan",
        label={"en": "Stories", "pt-BR": "Histórias"},
        icon="📖",
        description={
            "en": "Developer-sized work units. Child of Feature.",
            "pt-BR": "Unidades de trabalho do dev. Filhos de Feature.",
        },
        breadcrumb=["Plan", "Stories"],
        routes={
            "list":   "docs/Story",
            "detail": "docs/Story/:name",
            "create": "kinds/Story/__new__",
        },
        permissions={
            "list":   "any",
            "detail": "any",
            "create": ["po", "pm", "architect", "tech-lead", "maker"],
            "edit":   ["po", "pm", "architect", "tech-lead", "maker"],
        },
        in_sidebar=False,  # SDLC board is the primary surface; Stories
                            # detail-page is drilled into, not surfaced
                            # at top of the sidebar.
        display_order=12,
    )

    def dep_filters(self) -> dict[str, str]:
        return {
            "feature": "sdlc-feature",
            "owner": "helix-actor",
            "dependencies": "sdlc-story",
            "spec_refs": "sdlc-spec",
        }

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["description", "status"],
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Human-readable display name (Jira 'summary').",
                },
                "description": {"type": "string"},
                # User-story slots (2026-05-11 UX audit): when populated, the
                # Studio Board renders "As a <as_a>, I want <i_want>, so that
                # <so_that>" as the primary content above `description`. The
                # `description` field then becomes optional supporting detail
                # rather than the whole narrative. Old Stories without these
                # fields keep working — Board falls back to `description`.
                "as_a": {
                    "type": "string",
                    "description": "Role: 'As a <role>'. INVEST/user-story format slot.",
                },
                "i_want": {
                    "type": "string",
                    "description": "Goal: 'I want <goal>'. INVEST/user-story format slot.",
                },
                "so_that": {
                    "type": "string",
                    "description": "Benefit: 'so that <benefit>'. INVEST/user-story format slot.",
                },
                "status": {"type": "string", "enum": list(STORY_STATUSES)},
                "feature": {"type": "string", "description": "Parent Feature name"},
                "owner": {"type": "string", "description": "Actor name"},
                "estimate": {
                    "type": "number",
                    "description": "Fibonacci story points (1, 2, 3, 5, 8, 13, 21)",
                },
                "acceptance_criteria": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "required": ["text"],
                                "properties": {
                                    "text": {"type": "string"},
                                    "done": {"type": "boolean"},
                                    "done_at": {"type": "string", "format": "date-time"},
                                    "done_by": {"type": "string"},
                                },
                            },
                        ],
                    },
                    "description": (
                        "Acceptance criteria. Legacy: list[str]. New "
                        "(s-ac-dod-checklist-state): list[{text, done?, "
                        "done_at?, done_by?}] for per-item state tracking."
                    ),
                },
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Other Story names that must land first",
                },
                "spec_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Spec docs (kind=Spec) this Story implements. M:N "
                        "linkage between the planning axis (Story) and the "
                        "design axis (Spec) — Jira/Confluence-shaped."
                    ),
                },
                "closed_at": {"type": "string", "format": "date-time"},
                "blocked_reason": {"type": "string"},
                # v1.5 — board-grade fields (all opt; back-compat preserved).
                "priority": {
                    "type": "string", "enum": list(PRIORITIES),
                    "description": "Board priority. Jira-aligned.",
                },
                "labels": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Free-form tags for swim lanes / filters.",
                },
                "reporter": {
                    "type": "string",
                    "description": "Actor who filed it (vs `owner` who works on it).",
                },
                "watchers": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Actor names subscribed to changes.",
                },
                "journey_phase": {
                    "type": "string", "enum": list(JOURNEY_PHASES),
                    "description": (
                        "Universal journey phase (discover → specify → "
                        "plan → build → reflect). Additive layer over "
                        "Story/Feature/Epic status, Spec phase, etc. "
                        "Lets the journey ledger pin this doc to one of "
                        "five universal phases compatible with "
                        "Superpowers / BMAD / Spec Kit / Kiro."
                    ),
                },
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
                "sprint_ref": {
                    "type": "string",
                    "description": "Sprint identifier (free-form, e.g. '2026-Q2-S2').",
                },
                "time_tracking": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "logged_h": {"type": "number", "minimum": 0},
                        "remaining_h": {"type": "number", "minimum": 0},
                        "original_estimate_h": {"type": "number", "minimum": 0},
                    },
                },
                "definition_of_done": {
                    "type": "array",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "required": ["text"],
                                "properties": {
                                    "text": {"type": "string"},
                                    "done": {"type": "boolean"},
                                    "done_at": {"type": "string", "format": "date-time"},
                                    "done_by": {"type": "string"},
                                },
                            },
                        ],
                    },
                    "description": (
                        "Per-Story DoD. Same union shape as acceptance_criteria — "
                        "legacy list[str] OR list[{text, done?, done_at?, done_by?}]."
                    ),
                },
                "business_value": {
                    "type": "number", "minimum": 0, "maximum": 1000,
                    "description": "WSJF-style scalar for relative prioritization.",
                },
                "mockups": {
                    "type": "array", "items": {"type": "string"},
                    "description": "URLs/paths to design artifacts.",
                },
                "release_target": {
                    "type": "string",
                    "description": (
                        "Epic name OR 'owner/pkg@semver' identifying the release "
                        "this Story unblocks."
                    ),
                },
                # v1.6 — Activity Timeline.
                "produces": _produces_field_schema(),
                "timeline": _timeline_field_schema(),
            },
            "additionalProperties": True,
        }

    def summary(self, doc: Any) -> dict[str, Any]:
        spec = doc.spec if hasattr(doc, "spec") else doc
        s = spec if isinstance(spec, dict) else {}
        return {
            "status": s.get("status", "todo"),
            "feature": s.get("feature", ""),
            "owner": s.get("owner", ""),
            "estimate": s.get("estimate"),
            "spec_refs": len(s.get("spec_refs", []) or []),
            "priority": s.get("priority", "medium"),
            "labels": s.get("labels", []) or [],
            "sprint_ref": s.get("sprint_ref", ""),
            "business_value": s.get("business_value"),
        }


# ---------------------------------------------------------------------------
# Issue — bug / enhancement / question / task
# ---------------------------------------------------------------------------

class IssueKind(KindBase):
    """Issue — manual ticket for bug/enhancement/question/task.

    Distinct from ``Finding`` (which is auto-emitted from EvalRun).
    Issues are human-authored; they CAN link to a Finding via
    ``spec.related_finding`` to track the human follow-up of an
    eval-detected problem.
    """

    api_version = "github.com/ruinosus/dna/sdlc/v1"
    scope = TenantScope.GLOBAL  # SDLC primitives are project-level, not per-tenant
    kind = "Issue"
    alias = "sdlc-issue"
    scope_inheritable = False
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    storage = StorageDescriptor.yaml("issues")
    graph_style = {"fill": "#EF4444", "stroke": "#DC2626", "text_color": "#fff"}
    ascii_icon = "🐞"
    display_label = "Issues"
    is_prompt_target = False
    flatten_in_context = False
    plane = "record"
    prompt_target_priority = 0
    docs = (
        "An Issue is a human-authored ticket — bug, enhancement, question, "
        "or task. Tracked across open → triaged → in-progress → resolved. "
        "Optional links to a parent Feature (work it belongs to) and a "
        "related Finding (eval-detected origin)."
    )

    def dep_filters(self) -> dict[str, str]:
        return {
            "related_feature": "sdlc-feature",
            "owner": "helix-actor",
        }

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["description", "type", "severity", "status"],
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Human-readable display name (Jira 'summary').",
                },
                "description": {"type": "string"},
                "type": {"type": "string", "enum": list(ISSUE_TYPES)},
                "severity": {"type": "string", "enum": list(ISSUE_SEVERITIES)},
                "status": {"type": "string", "enum": list(ISSUE_STATUSES)},
                "owner": {"type": "string", "description": "Actor name"},
                "related_feature": {"type": "string", "description": "Feature name"},
                "related_finding": {"type": "string", "description": "Finding name"},
                "reproduction_steps": {"type": "array", "items": {"type": "string"}},
                "expected_behavior": {"type": "string"},
                "actual_behavior": {"type": "string"},
                "closed_at": {"type": "string", "format": "date-time"},
                "resolution": {"type": "string"},
                # GitHub-bridge provenance (s-github-issues-bridge): an
                # Issue can be PUBLISHED to / IMPORTED from a GitHub issue
                # (`dna sdlc issue publish|import|sync`). These fields are
                # the provenance link — the bridge mirrors WITH provenance,
                # it never replaces the github.com artifact.
                "github_number": {
                    "type": "integer", "minimum": 1,
                    "description": "GitHub issue number this doc is bridged to.",
                },
                "github_url": {
                    "type": "string",
                    "description": "Canonical https URL of the GitHub issue.",
                },
                "github_state": {
                    "type": "string", "enum": ["open", "closed"],
                    "description": "Last observed GitHub-side state.",
                },
                "github_synced_at": {
                    "type": "string", "format": "date-time",
                    "description": "When the GitHub side was last observed/synced.",
                },
                # v1.5 — board-grade common fields. Issues use `severity`
                # natively; `priority` is orthogonal (severity = how bad,
                # priority = how soon).
                "priority": {"type": "string", "enum": list(PRIORITIES)},
                "labels": {"type": "array", "items": {"type": "string"}},
                "reporter": {"type": "string"},
                "watchers": {"type": "array", "items": {"type": "string"}},
                "journey_phase": {
                    "type": "string", "enum": list(JOURNEY_PHASES),
                    "description": (
                        "Universal journey phase (discover → specify → "
                        "plan → build → reflect). Additive layer over "
                        "Story/Feature/Epic status, Spec phase, etc. "
                        "Lets the journey ledger pin this doc to one of "
                        "five universal phases compatible with "
                        "Superpowers / BMAD / Spec Kit / Kiro."
                    ),
                },
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
                "produces": _produces_field_schema(),
                "timeline": _timeline_field_schema(),
            },
            "additionalProperties": True,
        }

    def summary(self, doc: Any) -> dict[str, Any]:
        spec = doc.spec if hasattr(doc, "spec") else doc
        s = spec if isinstance(spec, dict) else {}
        return {
            "type": s.get("type", "bug"),
            "severity": s.get("severity", "medium"),
            "status": s.get("status", "open"),
            "owner": s.get("owner", ""),
            "related_feature": s.get("related_feature", ""),
            "priority": s.get("priority", "medium"),
            "labels": s.get("labels", []) or [],
        }


# ---------------------------------------------------------------------------
# Spec + Plan — pattern-agnostic pointers to design docs / impl plans
# ---------------------------------------------------------------------------

# Common status enum for Spec + Plan — ADR-style (Nygard).
# `proposed` = sent for review; `accepted` = decision ratified;
# `deprecated` = no longer applicable; `superseded` = replaced (use
# `supersedes` field to point at the replacement).
ARTIFACT_STATUSES = ("draft", "proposed", "accepted", "deprecated", "superseded")

# Spec.phase — Superpowers/Spec-Kit phase progression. Orthogonal to
# `status`: status is the document's lifecycle (draft → accepted →
# superseded), phase is the SDLC's perspective on the spec (where the
# work driven by this spec lives in the SDLC).
SPEC_PHASES = ("brainstorm", "spec", "plan_ready", "implementing", "done")


class SpecKind(KindBase):
    """Spec — a design decision record / spec doc.

    Pattern-agnostic: DNA doesn't impose a structure (superpowers, BMAD,
    droid, RFC, ADR, etc. all work). Spec carries the markdown body in
    a SPEC.md bundle + minimal metadata + refs to Epic.
    """

    api_version = "github.com/ruinosus/dna/sdlc/v1"
    scope = TenantScope.GLOBAL  # SDLC primitives are project-level, not per-tenant
    kind = "Spec"
    alias = "sdlc-spec"
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    storage = StorageDescriptor.bundle("specs", "SPEC.md", body_field="body")
    graph_style = {"fill": "#6366F1", "stroke": "#4F46E5", "text_color": "#fff"}
    ascii_icon = "📐"
    display_label = "Specs"
    is_prompt_target = False
    flatten_in_context = False
    plane = "record"
    prompt_target_priority = 0
    # Embeddable (s-spec-embeddable): the markdown body is the design's
    # substance — without this, `dna cognitive search` couldn't find design
    # docs/RFCs/specs by topic (Plan/Issue/Epic/Doc/Research already embed;
    # Spec was the lone SDLC-artifact gap). title+summary+body joined.
    embed_fields = ["title", "summary", "body"]
    docs = (
        "A Spec is a top-level design artifact. Cross-cutting by default "
        "(may drive multiple Features). Pattern-agnostic — superpowers, "
        "BMAD, droid, RFC, ADR, Spec Kit all work. status is ADR-style "
        "(draft → proposed → accepted → deprecated/superseded); phase is "
        "the orthogonal SDLC view (brainstorm → spec → plan_ready → "
        "implementing → done). Linkage to work is via Story.spec_refs[] "
        "(M:N), NOT via Spec.feature — the axis flip preserves "
        "Jira/Confluence semantics."
    )

    def dep_filters(self) -> dict[str, str]:
        return {
            "epic": "sdlc-epic",
            "supersedes": "sdlc-spec",
        }

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["title", "date", "status"],
            "properties": {
                "title": {"type": "string"},
                "date": {"type": "string", "format": "date"},
                "status": {"type": "string", "enum": list(ARTIFACT_STATUSES)},
                "phase": {
                    "type": "string",
                    "enum": list(SPEC_PHASES),
                    "description": (
                        "Where in the SDLC this spec's work sits. "
                        "Orthogonal to status."
                    ),
                },
                "journey_phase": {
                    "type": "string", "enum": list(JOURNEY_PHASES),
                    "description": (
                        "Universal journey phase. A Spec typically lives "
                        "in `specify`, but draft Specs may be `discover` "
                        "and finalized ones referenced by Plans drift to "
                        "`plan`. Coexists with `phase` (SDLC-view) — "
                        "`journey_phase` is the methodology-agnostic layer."
                    ),
                },
                "pattern": {
                    "type": "string",
                    "description": (
                        "Spec-driven pattern this artifact follows "
                        "(superpowers | bmad | droid | rfc | adr | spec-kit | custom)."
                    ),
                },
                "body": {
                    "type": "string",
                    "description": "Markdown body of the spec (stored in SPEC.md).",
                },
                "origin": {
                    "type": "string",
                    "description": (
                        "Optional audit trail — repo-relative path the body was "
                        "harvested from (e.g. docs/superpowers/specs/X.md). Not used "
                        "at runtime."
                    ),
                },
                "epic": {"type": "string"},
                "authors": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
                "supersedes": {
                    "type": "string",
                    "description": "Name of the prior Spec this one replaces.",
                },
                "summary": {
                    "type": "string",
                    "description": "Short one-paragraph summary (auto-extracted).",
                },
            },
            "additionalProperties": True,
        }

    def summary(self, doc: Any) -> dict[str, Any]:
        spec = doc.spec if hasattr(doc, "spec") else doc
        s = spec if isinstance(spec, dict) else {}
        return {
            "title": (s.get("title") or "")[:80],
            "date": s.get("date", ""),
            "status": s.get("status", "draft"),
            "phase": s.get("phase", ""),
            "pattern": s.get("pattern", ""),
            "epic": s.get("epic", ""),
        }


class PlanKind(KindBase):
    """Plan — a concrete implementation plan tied (usually) to a Spec.

    Same pattern-agnostic shape as Spec. The relationship Spec → Plan is
    one-to-many in practice (a Spec may have a brainstorm, then multiple
    iterative plans). Pattern-specific structure stays in markdown.
    """

    api_version = "github.com/ruinosus/dna/sdlc/v1"
    scope = TenantScope.GLOBAL  # SDLC primitives are project-level, not per-tenant
    kind = "Plan"
    alias = "sdlc-plan"
    scope_inheritable = False
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    storage = StorageDescriptor.bundle("plans", "PLAN.md", body_field="body")
    graph_style = {"fill": "#06B6D4", "stroke": "#0891B2", "text_color": "#fff"}
    ascii_icon = "📋"
    display_label = "Plans"
    is_prompt_target = False
    flatten_in_context = False
    plane = "record"
    prompt_target_priority = 0
    docs = (
        "A Plan is a pointer to an implementation plan document on disk. "
        "Usually descends from a Spec (`spec_ref`). Pattern-agnostic — "
        "DNA tracks pointer + metadata + refs, not the structure of "
        "the plan itself."
    )

    def dep_filters(self) -> dict[str, str]:
        return {
            "spec_ref": "sdlc-spec",
            "epic": "sdlc-epic",
        }

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["title", "date", "status"],
            "properties": {
                "title": {"type": "string"},
                "date": {"type": "string", "format": "date"},
                "status": {"type": "string", "enum": list(ARTIFACT_STATUSES)},
                "pattern": {"type": "string"},
                "body": {"type": "string", "description": "Markdown body (stored in PLAN.md)."},
                "origin": {"type": "string", "description": "Optional audit-only origin path."},
                "spec_ref": {
                    "type": "string",
                    "description": "Name of the Spec this plan implements.",
                },
                "epic": {"type": "string"},
                "authors": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
                "journey_phase": {
                    "type": "string", "enum": list(JOURNEY_PHASES),
                    "description": (
                        "Universal journey phase. A Plan typically lives "
                        "in `plan` (decomposition) and may transition to "
                        "`build` once Stories start landing."
                    ),
                },
                "methodology": {
                    "type": "string", "enum": list(JOURNEY_METHODOLOGIES),
                    "description": (
                        "Which planning methodology produced this plan "
                        "(superpowers | bmad | spec-kit | ...). Opt-in; lets "
                        "the journey show the plan's origin honestly. The SDLC "
                        "stays methodology-agnostic — this only records it."
                    ),
                },
            },
            "additionalProperties": True,
        }

    def summary(self, doc: Any) -> dict[str, Any]:
        spec = doc.spec if hasattr(doc, "spec") else doc
        s = spec if isinstance(spec, dict) else {}
        return {
            "title": (s.get("title") or "")[:80],
            "date": s.get("date", ""),
            "status": s.get("status", "draft"),
            "pattern": s.get("pattern", ""),
            "spec_ref": s.get("spec_ref", ""),
        }


# ---------------------------------------------------------------------------
# AgentSession — chat dev↔AI as versioned project artifact (Karpathy 2025)
# ---------------------------------------------------------------------------

class AgentSessionKind(KindBase):
    """AgentSession — captures a developer↔AI coding session as a doc.

    Tool-agnostic: Claude Code, Cursor, Cline, Codex, Aider all express
    sessions through the same canonical schema. Per-tool adapters
    (entry point ``dna.vibe_adapters``) materialize their
    native storage (JSONL, SQLite, etc.) into this shape.

    Storage: bundle pattern. ``SESSION.md`` carries the rendered
    transcript markdown (human-readable, git-diff-friendly).
    Frontmatter holds structured metadata (model, timestamps, refs).

    Treat as evidence-grade — the chat is the rationale trail for
    the produced Specs/Stories, not the spec itself (per the
    spec-driven-vibe-coding hybrid pattern).
    """

    api_version = "github.com/ruinosus/dna/sdlc/v1"
    scope = TenantScope.GLOBAL  # SDLC primitives are project-level, not per-tenant
    kind = "AgentSession"
    alias = "sdlc-agent-session"
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    storage = StorageDescriptor.bundle("agent-sessions", "SESSION.md", body_field="body")
    graph_style = {"fill": "#EC4899", "stroke": "#DB2777", "text_color": "#fff"}
    ascii_icon = "📜"
    display_label = "Vibe Sessions"
    is_prompt_target = False
    flatten_in_context = False
    plane = "record"
    prompt_target_priority = 0
    docs = (
        "A AgentSession captures a developer↔AI coding conversation as "
        "a versioned project artifact. Tool-agnostic: works for "
        "Claude Code, Cursor, Cline, Codex, Aider via per-tool "
        "adapters. Schema is the LCD (lowest-common-denominator) of "
        "the major tools' export formats."
    )

    def dep_filters(self) -> dict[str, str]:
        return {
            "participants": "helix-actor",
            # produced_artifacts is array of {kind, name} — composite ref
            # not modelable as a flat dep_filter; resolved at render time.
        }

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["title", "tool", "session_id", "started_at"],
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Human-readable session title (Jira-style summary).",
                },
                "tool": {
                    "type": "string",
                    "description": (
                        "Provenance — which AI coding tool produced this session. "
                        "claude-code | cursor | cline | codex | aider | specstory | other."
                    ),
                },
                "tool_version": {"type": "string"},
                "session_id": {
                    "type": "string",
                    "description": "Tool-native session identifier (UUID/sqlite-rowid/etc).",
                },
                "model": {
                    "type": "string",
                    "description": "AI model identifier (e.g. claude-opus-4-7, gpt-5-codex).",
                },
                "workspace_path": {"type": "string"},
                "started_at": {"type": "string", "format": "date-time"},
                "ended_at": {"type": "string", "format": "date-time"},
                "participants": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Actor names (humans + agent identities).",
                },
                "produced_artifacts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["kind", "name"],
                        "properties": {
                            "kind": {"type": "string"},
                            "name": {"type": "string"},
                        },
                    },
                    "description": "Refs to docs created/modified during session.",
                },
                "applied_commits": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Git SHA refs touched in-session.",
                },
                "file_changes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Repo-relative paths edited during session.",
                },
                "token_usage": {
                    "type": "object",
                    "description": "{input, output, cache_*} — adapter-specific shape.",
                },
                "cost_usd": {"type": "number"},
                "summary": {"type": "string"},
                "body": {
                    "type": "string",
                    "description": "Rendered transcript markdown (stored in SESSION.md).",
                },
                "raw_source": {
                    "type": "string",
                    "description": (
                        "Provenance pointer — tool-native source path or URL "
                        "(JSONL file path, sqlite URI, etc). Required for re-derivation."
                    ),
                },
                "tool_specific": {
                    "type": "object",
                    "description": "Escape hatch for per-tool extras (Cline checkpoints, CC git snapshots, etc).",
                },
                "journey_phase": {
                    "type": "string", "enum": list(JOURNEY_PHASES),
                    "description": (
                        "Universal journey phase. AgentSessions usually live "
                        "in `discover` (brainstorming chats) or `build` "
                        "(execution chats). The agent stamps this on capture."
                    ),
                },
            },
            "additionalProperties": True,
        }

    def summary(self, doc: Any) -> dict[str, Any]:
        spec = doc.spec if hasattr(doc, "spec") else doc
        s = spec if isinstance(spec, dict) else {}
        return {
            "title": (s.get("title") or "")[:80],
            "tool": s.get("tool", ""),
            "model": s.get("model", ""),
            "started_at": s.get("started_at", ""),
            "produced_artifacts": len(s.get("produced_artifacts", []) or []),
            "messages_in_body": "—",  # body is markdown, not parsed
        }


# ---------------------------------------------------------------------------
# Narrative — agent-curated project storytelling, indexed by date
# ---------------------------------------------------------------------------

# Narrative — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin NarrativeKind classes (Py+TS) were
# DELETED — synthesized from kinds/narrative.kind.yaml (parity-critical
# package data) via the load_descriptors loop in
# register(). Equivalence with the extinct class frozen in
# tests/test_lote2_descriptor_equivalence.py (golden:
# tests/goldens/lote2/Narrative.golden.json).


# ---------------------------------------------------------------------------
# Bug / Task / Spike — granular work items (split from Issue umbrella)
# ---------------------------------------------------------------------------

BUG_SEVERITY = ("low", "medium", "high", "critical")
BUG_STATUSES = ("open", "triaged", "in-progress", "resolved", "wont-fix", "duplicate", "regression")
TASK_STATUSES = ("todo", "in-progress", "done", "blocked", "cancelled")
SPIKE_STATUSES = ("proposed", "in-progress", "answered", "abandoned")


class BugKind(KindBase):
    """Bug — defeito factual com repro + severity.

    Studio precisa de Kinds dedicados pra navegação. Bug isola
    tracking de defeitos com schema dedicado (repro_steps,
    severity, etc). Issue umbrella continua disponível pra
    enhancement/question/other.

    Storage: bundle ``bugs/<slug>/BUG.md``.
    """

    api_version = "github.com/ruinosus/dna/sdlc/v1"
    scope = TenantScope.GLOBAL
    kind = "Bug"
    alias = "sdlc-bug"
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    storage = StorageDescriptor.bundle("bugs", "BUG.md", body_field="body")
    graph_style = {"fill": "#DC2626", "stroke": "#991B1B", "text_color": "#fff"}
    ascii_icon = "🐛"
    display_label = "Bugs"
    is_prompt_target = False
    flatten_in_context = False
    plane = "record"
    prompt_target_priority = 0
    docs = (
        "A Bug captures a factual defect: repro_steps, severity, "
        "environment, status. Distinct from Postmortem (incident — "
        "sev1-sev5 outage analysis) e Issue umbrella (enhancement/"
        "question/other)."
    )

    def dep_filters(self) -> dict[str, str]:
        return {
            "related_story": "sdlc-story",
            "related_feature": "sdlc-feature",
            "fix_adr": "sdlc-adr",
        }

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["title", "severity", "status"],
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "severity": {"type": "string", "enum": list(BUG_SEVERITY)},
                "status": {"type": "string", "enum": list(BUG_STATUSES)},
                "repro_steps": {"type": "array", "items": {"type": "string"}},
                "expected": {"type": "string"},
                "actual": {"type": "string"},
                "environment": {"type": "string"},
                "root_cause": {"type": "string"},
                "fix_summary": {"type": "string"},
                "fix_adr": {"type": "string"},
                "related_story": {"type": "string"},
                "related_feature": {"type": "string"},
                "related_finding": {"type": "string"},
                "reporter": {"type": "string"},
                "owner": {"type": "string"},
                "found_at": {"type": "string", "format": "date-time"},
                "resolved_at": {"type": "string", "format": "date-time"},
                "labels": {"type": "array", "items": {"type": "string"}},
                "priority": {
                    "type": "string", "enum": ["highest", "high", "medium", "low", "lowest"],
                },
                "body": {"type": "string"},
                "produces": _produces_field_schema(),
                "timeline": _timeline_field_schema(),
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
            },
        }


class TaskKind(KindBase):
    """Task — work item granular (sub-Story).

    Tactical: horas-dias de trabalho. Atlassian Jira Align
    hierarchy: Story → Task → Sub-task.

    Storage: bundle ``tasks/<slug>/TASK.md``.
    """

    api_version = "github.com/ruinosus/dna/sdlc/v1"
    scope = TenantScope.GLOBAL
    kind = "Task"
    alias = "sdlc-task"
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    storage = StorageDescriptor.bundle("tasks", "TASK.md", body_field="body")
    graph_style = {"fill": "#3B82F6", "stroke": "#1D4ED8", "text_color": "#fff"}
    ascii_icon = "✅"
    display_label = "Tasks"
    is_prompt_target = False
    flatten_in_context = False
    plane = "record"
    prompt_target_priority = 0
    docs = (
        "A Task is a granular work item (horas-dias) typically as "
        "sub-item of a Story. For multi-day deliverables use Story."
    )

    def dep_filters(self) -> dict[str, str]:
        return {
            "story_ref": "sdlc-story",
            "owner": "helix-actor",
        }

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["title", "status"],
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "status": {"type": "string", "enum": list(TASK_STATUSES)},
                "story_ref": {"type": "string"},
                "owner": {"type": "string"},
                "estimate_hours": {"type": "number", "minimum": 0},
                "logged_hours": {"type": "number", "minimum": 0},
                "due": {"type": "string", "format": "date"},
                "priority": {
                    "type": "string", "enum": ["highest", "high", "medium", "low", "lowest"],
                },
                "labels": {"type": "array", "items": {"type": "string"}},
                "blocked_reason": {"type": "string"},
                "closed_at": {"type": "string", "format": "date-time"},
                "body": {"type": "string"},
                "produces": _produces_field_schema(),
                "timeline": _timeline_field_schema(),
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
            },
        }


class SpikeKind(KindBase):
    """Spike — technical investigation time-boxed.

    Scrum convention: exploração técnica pra responder UMA
    pergunta antes de comprometer story-level work. Time-boxed
    (default 8h). Outcome: findings + recommendation pra próximo
    Story/ADR.

    Storage: bundle ``spikes/<slug>/SPIKE.md``.
    """

    api_version = "github.com/ruinosus/dna/sdlc/v1"
    scope = TenantScope.GLOBAL
    kind = "Spike"
    alias = "sdlc-spike"
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    storage = StorageDescriptor.bundle("spikes", "SPIKE.md", body_field="body")
    graph_style = {"fill": "#A855F7", "stroke": "#7E22CE", "text_color": "#fff"}
    ascii_icon = "🔬"
    display_label = "Spikes"
    is_prompt_target = False
    flatten_in_context = False
    plane = "record"
    prompt_target_priority = 0
    docs = (
        "A Spike is a time-boxed technical investigation. ONE "
        "question + finite time budget + outcome handoff (findings "
        "→ Story or ADR). Distinct from Story (work to ship) e "
        "ADR (decision já tomada)."
    )

    def dep_filters(self) -> dict[str, str]:
        return {
            "follow_up_story": "sdlc-story",
            "follow_up_adr": "sdlc-adr",
            "follow_up_spec": "sdlc-spec",
            "feature": "sdlc-feature",
            # Multi-ref attachments (2026-05-26 — design-spike workflow).
            "references": "sdlc-reference",
            "related_spikes": "sdlc-spike",
        }

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["title", "question_to_answer", "status"],
            "properties": {
                "title": {"type": "string"},
                "question_to_answer": {"type": "string"},
                "status": {"type": "string", "enum": list(SPIKE_STATUSES)},
                "time_box_hours": {
                    "type": "number", "minimum": 0, "default": 8,
                },
                "logged_hours": {"type": "number", "minimum": 0},
                "findings": {"type": "string"},
                "recommendation": {"type": "string"},
                "follow_up_story": {"type": "string"},
                "follow_up_adr": {"type": "string"},
                "follow_up_spec": {"type": "string"},
                "feature": {"type": "string"},
                "owner": {"type": "string"},
                # Multi-ref attachments — design spikes anexam HTML mockups,
                # Research syntheses + free-form References. Kind referencia
                # outros Kinds via spec field array + dep_filters declares
                # the target kind.
                "html_artifacts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "HtmlArtifact names attached to this Spike (rendered "
                        "mockups, diagrams, design comparisons)."
                    ),
                },
                "research_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Research names this Spike consulted (curated "
                        "syntheses with N References)."
                    ),
                },
                "references": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Free-form Reference names (papers, blog posts, "
                        "library docs cited mid-spike)."
                    ),
                },
                "related_spikes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Sibling Spikes investigating overlapping questions."
                    ),
                },
                "started_at": {"type": "string", "format": "date-time"},
                "completed_at": {"type": "string", "format": "date-time"},
                "labels": {"type": "array", "items": {"type": "string"}},
                "body": {"type": "string"},
                "produces": _produces_field_schema(),
                "timeline": _timeline_field_schema(),
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
            },
        }


# ---------------------------------------------------------------------------
# Initiative — investment unit between Epic and Theme (Atlassian Jira Align)
# ---------------------------------------------------------------------------

INITIATIVE_STATUSES = ("proposed", "in-flight", "done", "cancelled", "deferred")


class InitiativeKind(KindBase):
    """Initiative — investment-level umbrella between Theme/OKR and Epic.

    Atlassian Jira Align hierarchy:
    Theme/OKR → **Initiative** → Epic → Feature → Story → Task

    Horizon: 1-2 trimestres. Owner típico: PM ou Product Lead.
    Para roadmaps grandes (enterprise) onde Epic é granular demais
    pra strategy review com C-level.

    Storage: bundle ``initiatives/<slug>/INITIATIVE.md``.

    Spec: docs/superpowers/specs/2026-05-26-vocabulary-sanitization.md §5
    + Jira Align glossary.
    """

    api_version = "github.com/ruinosus/dna/sdlc/v1"
    scope = TenantScope.GLOBAL
    kind = "Initiative"
    alias = "sdlc-initiative"
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    storage = StorageDescriptor.bundle("initiatives", "INITIATIVE.md", body_field="body")
    graph_style = {"fill": "#0EA5E9", "stroke": "#0284C7", "text_color": "#fff"}
    ascii_icon = "🎲"
    display_label = "Initiatives"
    is_prompt_target = False
    flatten_in_context = False
    plane = "record"
    prompt_target_priority = 0
    docs = (
        "An Initiative is a strategic investment unit (1-2 quarters) "
        "that groups Epics under a measurable outcome. Sits between "
        "Theme/OKR (annual) and Epic (multi-sprint). For enterprise "
        "roadmaps where Theme→Epic skip loses too much resolution."
    )

    def dep_filters(self) -> dict[str, str]:
        return {
            "epics": "sdlc-epic",
            "owner": "helix-actor",
        }

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["title", "status"],
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "status": {
                    "type": "string", "enum": list(INITIATIVE_STATUSES),
                },
                "owner": {"type": "string", "description": "Actor name (PM / Product Lead)."},
                "horizon_start": {"type": "string", "format": "date"},
                "horizon_end": {"type": "string", "format": "date"},
                "outcome_metric": {
                    "type": "string",
                    "description": "What KR/metric this initiative is targeted at.",
                },
                "target_value": {"type": "string", "description": "e.g. '+30% MAU' or '<200ms p95'."},
                "epics": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Epic names this initiative groups.",
                },
                "theme_ref": {
                    "type": "string",
                    "description": "Optional Theme/OKR Objective slug.",
                },
                "business_value": {"type": "number"},
                "priority": {
                    "type": "string", "enum": ["highest", "high", "medium", "low", "lowest"],
                },
                "labels": {"type": "array", "items": {"type": "string"}},
                "body": {"type": "string"},
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
            },
        }


# ---------------------------------------------------------------------------
# Changelog — Keep a Changelog 1.1.0 + SemVer 2.0
# ---------------------------------------------------------------------------

CHANGELOG_SECTIONS = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")


# Changelog — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin ChangelogKind classes (Py+TS) were
# DELETED — synthesized from kinds/changelog.kind.yaml (parity-critical
# package data) via the load_descriptors loop in
# register(). Equivalence with the extinct class frozen in
# tests/test_lote2_descriptor_equivalence.py (golden:
# tests/goldens/lote2/Changelog.golden.json).


# ---------------------------------------------------------------------------
# Postmortem — Google SRE blameless incident analysis
# ---------------------------------------------------------------------------

# Postmortem — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin PostmortemKind classes (Py+TS) were
# DELETED — synthesized from kinds/postmortem.kind.yaml (parity-critical
# package data) via the load_descriptors loop in
# register(). Equivalence with the extinct class frozen in
# tests/test_lote2_descriptor_equivalence.py (golden:
# tests/goldens/lote2/Postmortem.golden.json).


# ---------------------------------------------------------------------------
# RiskRegister — PMBOK 7 + ISO 31000:2018
# ---------------------------------------------------------------------------

# RiskRegister — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin RiskRegisterKind classes (Py+TS) were
# DELETED — synthesized from kinds/risk-register.kind.yaml (parity-critical
# package data) via the load_descriptors loop in
# register(). Equivalence with the extinct class frozen in
# tests/test_lote2_descriptor_equivalence.py (golden:
# tests/goldens/lote2/RiskRegister.golden.json).


# ---------------------------------------------------------------------------
# ADR — Architecture Decision Record (Nygard 2011, MADR template)
# ---------------------------------------------------------------------------

# ADR — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin ADRKind classes (Py+TS) were
# DELETED — synthesized from kinds/adr.kind.yaml (parity-critical
# package data) via the load_descriptors loop in
# register(). Equivalence with the extinct class frozen in
# tests/test_lote2_descriptor_equivalence.py (golden:
# tests/goldens/lote2/ADR.golden.json).


# ---------------------------------------------------------------------------
# Retrospective — sprint/PI/incident retro (Atlassian 4 Ls)
# ---------------------------------------------------------------------------

# Retrospective — F3 lote-1 (spec 2026-06-10-kinds-descriptor-f3): the twin RetrospectiveKind classes (Py+TS) were
# DELETED — synthesized from kinds/retrospective.kind.yaml (parity-critical
# package data) via the load_descriptors loop in
# register(). Equivalence with the extinct class frozen in
# tests/test_lote1_descriptor_equivalence.py (golden:
# tests/goldens/lote1/Retrospective.golden.json).


# ---------------------------------------------------------------------------
# WorkflowEvent — append-only ledger of phase transitions
# ---------------------------------------------------------------------------

# Methodologies the journey ledger knows about. The canonical short
# tags are a closed enum so Studio can render badges; the
# `methodology_artifact` field carries the open-world details.
JOURNEY_METHODOLOGIES = (
    "superpowers", "bmad", "spec-kit", "kiro",
    "rfc", "adr", "ad-hoc", "custom",
)


# ---------------------------------------------------------------------------
# SavedView — filter+groupBy+sort persistence as first-class entity
# ---------------------------------------------------------------------------

# SavedView — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin SavedViewKind classes (Py+TS) were
# DELETED — synthesized from kinds/saved-view.kind.yaml (parity-critical
# package data) via the load_descriptors loop in
# register(). Equivalence with the extinct class frozen in
# tests/test_lote2_descriptor_equivalence.py (golden:
# tests/goldens/lote2/SavedView.golden.json).


# ---------------------------------------------------------------------------
# StatusReport (was: "Insights" — Insight + StatusReport)
# ---------------------------------------------------------------------------
# censo-12-kinds (2026-07-20): the `Insight` Kind (alias sdlc-insight) was
# DELETED. It was the oracle DEFINITION — a perpetual question bound to a
# target UA — and the runner that was to iterate active Insights and
# dispatch them never shipped in this distribution, so nothing ever
# produced the StatusReports it pointed at. StatusReport itself STAYS and is
# genuinely LIVE: `dna sdlc digest --save` writes one (sdlc_cmd.py) and reads
# them back. Note that live path already wrote spec.insight='sdlc-digest', a
# synthetic marker — never an Insight slug — so the dep_filter on sdlc-insight
# was dead for the only real producer even before the deletion.
# NOTE: this is unrelated to `IntelInsight` (alias intel-insight, the
# intel extension), which is live and stays.

# StatusReport — F3 lote-2 (spec 2026-06-10-kinds-descriptor-f3): the twin StatusReportKind classes (Py+TS) were
# DELETED — synthesized from kinds/status-report.kind.yaml (parity-critical
# package data) via the load_descriptors loop in
# register(). Equivalence with the extinct class frozen in
# tests/test_lote2_descriptor_equivalence.py (golden:
# tests/goldens/lote2/StatusReport.golden.json).


# ---------------------------------------------------------------------------
# Engram (was: the "Cognitive Memory Triad", v1.9.0)
#
# Spec (historical): docs/superpowers/specs/2026-05-11-cognitive-memory-triad.md
#
# Engram (renamed from LessonLearned, s-engram-rename 2026-07-19 — see
# below) = unbidden recall with affect (surface label in Studio: "Lições
# Aprendidas"). It is a real platform memory primitive with live consumers.
#
# censo-12-kinds (2026-07-20): the other two members, SynthesisRun and
# ArchiveProposal, were DELETED. Both only ever existed to receive the
# output of a cognition-engine family that never shipped in this
# distribution — there is no dna/cognitive/ package here, no dream-gen
# engine, no deep-sleep orphan scan. Nothing produced them and nothing
# read them.
# ---------------------------------------------------------------------------

# s-engram-rename (2026-07-19): Engram (formerly LessonLearned) MOVED OUT of
# this extension — it is now registered by HelixExtension from
# ``helix/kinds/engram.kind.yaml`` (identity github.com/ruinosus/dna/v1,
# alias helix-engram) — memory is a platform primitive, not sdlc-owned. A
# clean rename (zero users at the time), NOT a compat alias: stored docs are
# rewritten in place by ``scripts/migrate_lesson_learned_to_engram.py``.
# REMEMBRANCE_AFFECTS / REMEMBRANCE_SURFACE_TRIGGERS now live ONLY in that
# descriptor — the single source for the Engram enums. Equivalence with the
# extinct LessonLearnedKind class stays frozen in
# tests/test_lote1_descriptor_equivalence.py (golden:
# tests/goldens/lote1/Engram.golden.json) — the fixture kernel loads
# HelixExtension for it now. The class's dead to_card (zero consumers) was
# not carried over; `embed:` replaces the legacy EMBEDDABLE_KINDS entry
# (F3 D4).


# censo-12-kinds (2026-07-20): PatternInsight, Forecast, SynthesizerState,
# ArchiveProposal and PreMortem were DELETED here, together with
# SynthesisRun and Insight above. They formed the record-plane surface of a
# cognition-engine family (dream-gen, dream-interp lenses, hindsight hooks,
# a verification loop, a deep-sleep orphan scan) that does not exist in this
# distribution — it arrived as residue of an unrelated extraction. Kinds
# whose only purpose was to hold that family's output have no future; the
# documents a PERSON writes (Postmortem, Retrospective, RiskRegister) and
# CognitivePolicy (read in production by registry_accessor.py) stay.


# ---------------------------------------------------------------------------
# Extension
# ---------------------------------------------------------------------------

REFERENCE_KIND_OFS = ("web", "paper", "book", "file", "internal-doc", "other")


def _workitem_common_schema() -> dict[str, Any]:
    """Shared JSON Schema fragment for work-item Kinds (Bug, Spike, Task,
    Improvement, Incident, TechDebt) declared via KindDefinition with
    ``spec.workitem_common: true``.

    Each KindDefinition opting in receives these properties merged into
    its `schema.properties` — without copy-pasting timeline/comments/
    commit_refs/AC/DoD across N KIND.yaml files.

    Story: s-workitem-common-schema-fragment (f-extended-work-item-kinds re-scope).

    Returns
    -------
    dict[str, Any]
        Properties dict to merge into KindDefinition.spec.schema.properties.
    """
    return {
        "title": {"type": "string", "description": "Display name"},
        "description": {"type": "string"},
        "owner": {"type": "string", "description": "Actor name"},
        "parent": {
            "type": "string",
            "description": "Parent ref (Story/<X> | Feature/<X> | Epic/<X>)",
        },
        "labels": {"type": "array", "items": {"type": "string"}, "default": []},
        "estimate": {"type": "integer", "description": "Story points / hours"},
        "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "acceptance_criteria": {
            "type": "array", "items": {"type": "string"}, "default": [],
            "description": "Given/When/Then sentences.",
        },
        "definition_of_done": {
            "type": "array", "items": {"type": "string"}, "default": [],
        },
        "timeline": _timeline_field_schema(),
        "comments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "at": {"type": "string", "format": "date-time"},
                    "actor": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
            "default": [],
        },
        "commit_refs": {
            "type": "array", "items": {"type": "string"}, "default": [],
            "description": "Git SHAs associated with this work item.",
        },
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"},
        "closed_at": {"type": "string", "format": "date-time"},
        "as_a": {"type": "string", "description": "User-story slot"},
        "i_want": {"type": "string", "description": "User-story slot"},
        "so_that": {"type": "string", "description": "User-story slot"},
    }


class ReferenceKind(KindBase):
    """Reference — external citation artifact (web/paper/book/file/internal-doc).

    Wraps external sources with metadata so SDLC docs can cite evidence
    durably. Any other Kind (Story, Feature, Spec, Plan, Engram, etc.)
    gains an optional ``spec.references: list[str]`` field naming
    Reference doc slugs. CLI ``dna sdlc cite`` maintains the
    bidirectional graph (Reference.spec.cited_by += caller_ref).

    Spec: docs/superpowers/specs/2026-05-12-f-reference-citation-kind.md
    """

    api_version = "github.com/ruinosus/dna/sdlc/v1"
    scope = TenantScope.GLOBAL
    kind = "Reference"
    alias = "sdlc-reference"
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    storage = StorageDescriptor.yaml("references")
    graph_style = {"fill": "#6366F1", "stroke": "#4F46E5", "text_color": "#fff"}
    ascii_icon = "📚"
    display_label = "References"
    is_prompt_target = False
    flatten_in_context = False
    plane = "record"
    prompt_target_priority = 0

    def dep_filters(self) -> dict[str, str]:
        return {}

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["title", "kind_of", "summary"],
            "properties": {
                "title": {"type": "string"},
                "kind_of": {"type": "string", "enum": list(REFERENCE_KIND_OFS)},
                "url": {"type": "string"},
                "fetched_at": {"type": "string", "format": "date-time"},
                "summary": {"type": "string", "description": "1-2 sentence what this source says."},
                "key_quotes": {"type": "array", "items": {"type": "string"}, "default": []},
                "relevance": {"type": "string", "description": "Why this matters for THIS project."},
                "tags": {"type": "array", "items": {"type": "string"}, "default": []},
                "cited_by": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Auto-maintained by `dna sdlc cite`. Don't author by hand.",
                },
                "content_path": {
                    "type": "string",
                    "description": "Optional path to rich-content sidecar (e.g. docs/superpowers/research/<slug>.md)",
                },
                "owner": {"type": "string", "default": "claude-code"},
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
            },
            "additionalProperties": True,
        }

    def summary(self, doc: Any) -> dict[str, Any]:
        s = doc.spec if hasattr(doc, "spec") else doc
        s = s if isinstance(s, dict) else {}
        return {
            "title": s.get("title", ""),
            "kind_of": s.get("kind_of", "other"),
            "url": s.get("url", ""),
            "cited_by_count": len(s.get("cited_by") or []),
        }

    def to_card(self, doc: Any) -> dict[str, Any]:
        s = doc.spec or {}
        return {
            "name": doc.name, "scope": doc.scope, "kind": "Reference",
            "title": s.get("title"), "kind_of": s.get("kind_of"),
            "url": s.get("url"), "cited_by_count": len(s.get("cited_by") or []),
        }


# PromptTemplate — expr batch B (plan 2026-06-11-descriptor-expressiveness,
# Chunk 4): the twin classes were DELETED; synthesized from
# kinds/prompt-template.kind.yaml via the load_descriptors loop in register().
#
# s-consolidate-cognitive-policies (f-kind-catalog-governance, 2026-07-07):
# the 9 cognitive policy Kinds (RecallPolicy, DecayPolicy, MemoryPolicy, the
# old CognitivePolicy, AllocationPolicy, PaginationPolicy,
# EngramStrengthPolicy, EmbeddingProfile, AffectPalette) were consolidated
# into ONE expanded CognitivePolicy descriptor
# (kinds/cognitive-policy.kind.yaml) with one top-level spec section per
# former Kind. The 8 retired names are pinned in Kernel._REMOVED_KINDS
# (+ _REMOVED_KIND_NOTES); docs were migrated by
# scripts/migrate_cognitive_policies.py.


# ---------------------------------------------------------------------------
# Kaizen — first-class improvement observation (record plane)
#
# F3 P2 (spec 2026-06-10-kinds-descriptor-f3): the twin KaizenKind classes
# (Py + TS) were DELETED — the Kind is now synthesized from the descriptor
# kinds/kaizen.kind.yaml (parity-critical package data, byte-identical
# Py↔TS) via kernel.kind_from_descriptor in register() below. Equivalence
# with the old class is frozen in tests/test_kaizen_descriptor_equivalence.py.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# HtmlArtifact — an HTML page as a first-class work-item output (record plane)
#
# s-dx-html-artifact-kind. A bundle Kind whose primary marker (ARTIFACT.html)
# holds the raw HTML **verbatim** (byte-faithful round-trip — no frontmatter
# injection that would corrupt the document), plus an optional artifact.json
# companion carrying structured metadata (title, description, source,
# created_at) — mirrors the Soul bundle (SOUL.md + soul.json). Linked to a
# work item via ``spec.produces[]`` / ``spec.html_artifacts[]`` so the
# roteiro/design doc that used to live in chat becomes rastreável on the board.
# Custom reader/writer (not the generic marker-frontmatter path) because the
# marker is arbitrary HTML, not markdown-with-frontmatter.
# ---------------------------------------------------------------------------

_HTML_ARTIFACT_API_VERSION = "github.com/ruinosus/dna/sdlc/v1"


class HtmlArtifactKind(KindBase):
    api_version = _HTML_ARTIFACT_API_VERSION
    kind = "HtmlArtifact"
    # alias GENERATED = "<owner>-<kebab(kind)>" = "sdlc-html-artifact"
    # (s-alias-generated-not-typed — new Kinds must not type the alias).
    alias = None
    alias_owner = "sdlc"
    model = dict
    origin = "github.com/ruinosus/dna/sdlc"
    # Record plane — a produced artifact, never part of agent composition.
    plane = "record"
    # PERMISSIVE tenancy — no ``scope`` declared: repo-authored output,
    # inheritable like Research (an artifact, not tenant-private data).
    storage = StorageDescriptor.bundle("html-artifacts", "ARTIFACT.html")
    graph_style = {"fill": "#EA580C", "stroke": "#C2410C", "text_color": "#fff"}
    ascii_icon = "📄"
    display_label = "HTML Artifacts"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    description_fallback_field = None
    ui_schema = {
        "html": {
            "widget": "code",
            "language": "html",
            "label": "ARTIFACT.html",
            "help": "The raw HTML page (stored byte-faithful).",
            "height": 520,
            "order": 10,
        },
        "artifact_json": {
            "widget": "code",
            "language": "json",
            "label": "artifact.json",
            "help": "Structured metadata (title, description, source, created_at).",
            "height": 220,
            "order": 20,
        },
    }
    docs = (
        "An HtmlArtifact stores an HTML page as a first-class, linkable output "
        "of a work item (Story/Feature/Epic/Spike). It is a bundle: "
        "ARTIFACT.html holds the raw HTML verbatim (byte-faithful round-trip) "
        "plus an optional artifact.json companion with structured metadata "
        "(title, description, source, created_at) — the same shape as a Soul's "
        "SOUL.md + soul.json. Attach one to a work item with "
        "``dna sdlc produces add <WiKind>/<wi> HtmlArtifact/<name>`` so a "
        "design doc, roteiro, or report that used to live in chat becomes "
        "traceable on the board."
    )

    def schema(self) -> dict[str, Any] | None:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "html": {
                    "type": "string",
                    "description": "The raw HTML document (byte-faithful).",
                },
                "artifact_json": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "Structured metadata: title, description, source, created_at.",
                },
            },
        }

    def parse(self, raw: dict[str, Any]) -> Any:
        from dna.kernel.models import TypedHtmlArtifact
        return TypedHtmlArtifact.from_raw(raw)

    def summary(self, doc: Any) -> dict[str, Any] | None:
        # Keep list endpoints light — never ship the full HTML in a summary.
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        aj = spec_dict.get("artifact_json") or {}
        aj = aj if isinstance(aj, dict) else {}
        return {
            "title": aj.get("title"),
            "source": aj.get("source"),
            "created_at": aj.get("created_at"),
            # published_url — the canonical hosted location (e.g. a claude.ai
            # artifact URL) so the gallery can render a clickable link instead
            # of only the byte-blob. Lives in artifact_json (free-form).
            "published_url": aj.get("published_url"),
            "html_bytes": len(spec_dict.get("html") or ""),
        }

    def preview(self, doc: Any) -> list["PreviewBlock"]:
        from dna.kernel.preview import PreviewBlock
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        html = spec_dict.get("html")
        blocks: list[PreviewBlock] = []
        if isinstance(html, str) and html:
            blocks.append(PreviewBlock(kind="code", title="ARTIFACT.html", body=html, language="html"))
        aj = spec_dict.get("artifact_json")
        if aj and isinstance(aj, dict):
            import json as _json
            blocks.append(
                PreviewBlock(
                    kind="code",
                    title="artifact.json",
                    body=_json.dumps(aj, indent=2, ensure_ascii=False),
                    language="json",
                )
            )
        if not blocks:
            return [PreviewBlock(kind="empty", title="HtmlArtifact (empty)")]
        return blocks


class HtmlArtifactReader(ReaderPort):
    """Detects and reads ARTIFACT.html bundles (raw HTML + artifact.json)."""

    def detect(self, bundle: Any) -> bool:
        return bundle.exists("ARTIFACT.html")

    def read(self, bundle: Any) -> dict[str, Any]:
        import json as _json
        spec: dict[str, Any] = {}
        metadata: dict[str, Any] = {}

        # ARTIFACT.html — read verbatim (byte-faithful; no frontmatter parse).
        if bundle.exists("ARTIFACT.html"):
            spec["html"] = bundle.read_text("ARTIFACT.html")

        # artifact.json companion — structured metadata.
        if bundle.exists("artifact.json"):
            aj = _json.loads(bundle.read_text("artifact.json"))
            if isinstance(aj, dict):
                spec["artifact_json"] = aj
                # Promote description into metadata for search/listing.
                desc = aj.get("description")
                if isinstance(desc, str) and desc and not metadata.get("description"):
                    metadata["description"] = desc

        metadata.setdefault("name", bundle.name)
        return {
            "apiVersion": _HTML_ARTIFACT_API_VERSION,
            "kind": "HtmlArtifact",
            "metadata": metadata,
            "spec": spec,
        }


class HtmlArtifactWriter(WriterPort):
    """Writes an HtmlArtifact raw dict back to an ARTIFACT.html bundle."""

    def can_write(self, raw: dict) -> bool:
        return raw.get("kind") == "HtmlArtifact"

    def serialize(self, raw: dict) -> list[dict[str, str]]:
        import json as _json
        files: list[dict[str, str]] = []
        spec = raw.get("spec", {}) or {}

        # ARTIFACT.html — verbatim HTML (byte-faithful).
        files.append({"relativePath": "ARTIFACT.html", "content": spec.get("html", "") or ""})

        # artifact.json — canonical JSON companion. metadata.description is a
        # DERIVED promotion of artifact_json.description on read, so it is NOT
        # re-emitted separately (no phantom frontmatter — F3 market-fidelity).
        aj = spec.get("artifact_json")
        if aj and isinstance(aj, dict):
            files.append(
                {"relativePath": "artifact.json", "content": _json.dumps(aj, indent=2, ensure_ascii=False)}
            )
        return files

    def write(self, bundle: Any, raw: dict) -> None:
        for f in self.serialize(raw):
            bundle.write_text(f["relativePath"], f["content"])


class SdlcExtension:
    """SDLC primitives — Roadmap, Epic, Feature, Story, Issue, Spec, Plan,
    AgentSession, Narrative, WorkflowEvent, StatusReport.

    Engram (formerly LessonLearned) moved to HelixExtension
    (s-engram-rename, 2026-07-19) — memory is a platform primitive.

    v1.10.0 (2026-05-12): Reference Kind (f-reference-citation-kind +
    f-semon-correct-memory).
    v1.14.0 (2026-07-07): the 9 cognitive policy Kinds consolidated into one
    expanded CognitivePolicy (s-consolidate-cognitive-policies).
    v1.15.0 (2026-07-20): 5 Kinds REMOVED — ArchiveProposal, Forecast,
    Insight, SynthesisRun, SynthesizerState (censo-12-kinds). See the block
    comment above their former descriptors for why.
    """

    name = "sdlc"
    version = "1.15.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(RoadmapKind())
        kernel.kind(EpicKind())
        kernel.kind(FeatureKind())
        kernel.kind(StoryKind())
        kernel.kind(IssueKind())
        kernel.kind(SpecKind())
        kernel.kind(PlanKind())
        kernel.kind(AgentSessionKind())
        kernel.kind(BugKind())
        kernel.kind(TaskKind())
        kernel.kind(SpikeKind())
        kernel.kind(InitiativeKind())
        # v1.10.0 — f-reference-citation-kind + f-semon-correct-memory
        kernel.kind(ReferenceKind())
        # s-dx-html-artifact-kind — HTML page as a first-class work-item output.
        # Bundle Kind (custom reader/writer for byte-faithful HTML), mirroring
        # the Soul (SOUL.md + soul.json) mechanic.
        kernel.kind(HtmlArtifactKind())
        kernel.reader(HtmlArtifactReader())
        kernel.writer(HtmlArtifactWriter())
        # expr batch B (plan 2026-06-11-descriptor-expressiveness, Chunk 4):
        # PromptTemplate migrated to a descriptor — registered via the
        # load_descriptors loop below (kinds/*.kind.yaml), not per-Kind here.
        # s-consolidate-cognitive-policies: the cognitive policy family is
        # ONE descriptor now (kinds/cognitive-policy.kind.yaml).
        # F3 P2 (spec 2026-06-10-kinds-descriptor-f3): builtin record
        # Kinds expressed as descriptors — kinds/*.kind.yaml package data
        # registered through the SAME funnel as per-scope KindDefinitions
        # (plane lint + digest idempotency + builtin conflict marker).
        # Structured as a loop so migration batches just drop files into
        # kinds/ — no per-Kind code. Pilot: Kaizen (v1.13.0 s-kaizen-kind,
        # class twins deleted).
        for raw in load_descriptors("dna.extensions.sdlc"):
            kernel.kind_from_descriptor(raw)

        # s-write-path-despecialize — the bi-temporal Engram guard
        # (i-046) is a pre_save veto hook owned by this extension, not a
        # kernel special-case. Stays wired here even though Engram itself
        # now registers via HelixExtension (s-engram-rename) — the hook
        # matches ctx.kind by string, independent of which extension
        # registered the Kind.
        from dna.extensions.sdlc.write_guards import (
            register_write_guards,
        )
        register_write_guards(kernel)

        # v1.11.0 — f-extended-work-item-kinds (KindDefinition-driven).
        # Register the shared work-item common schema fragment so
        # KindDefinitions can reference it via spec.schema_fragments:
        # ["sdlc/workitem-common"]. Open-extension pattern: any other
        # extension can register its own fragments (e.g.
        # "medical/care-pathway-common") without modifying the SDK.
        try:
            from dna.kernel.meta import register_schema_fragment
            register_schema_fragment(
                "sdlc/workitem-common",
                {"type": "object", "properties": _workitem_common_schema()},
            )
        except Exception:  # noqa: BLE001 — kernel may not expose API yet
            pass
