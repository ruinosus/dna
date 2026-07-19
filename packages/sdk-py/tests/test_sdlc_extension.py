"""Tests for SdlcExtension — 5 Kinds (Roadmap, Epic, Feature, Story, Issue)."""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.extensions.sdlc import (
    FEATURE_STATUSES,
    FeatureKind,
    ISSUE_SEVERITIES,
    ISSUE_STATUSES,
    ISSUE_TYPES,
    IssueKind,
    EPIC_STATUSES,
    EpicKind,
    RoadmapKind,
    SdlcExtension,
    STORY_STATUSES,
    StoryKind,
)


# --- Registration ----------------------------------------------------------

def test_extension_registers_expected_kinds():
    """SDLC extension registers a fixed set of Kinds under
    ``github.com/ruinosus/dna/sdlc/v1``. Adding a Kind to the extension MUST update this
    list — that's the whole point of the test (prevents silent
    expansion of the public contract).

    Current set (31 Kinds): SDLC core + ADO-grade doc Kinds (ADR,
    Changelog, Initiative, Postmortem, Retrospective, RiskRegister,
    SavedView, Spike, Bug, Task) + two of the cognitive triad
    (SynthesisRun, ArchiveProposal — the third, Engram, moved to
    HelixExtension on s-engram-rename 2026-07-19) + SynthesizerState +
    dream/forecast + the UNIFIED CognitivePolicy (was 9 Kinds —
    RecallPolicy, DecayPolicy, MemoryPolicy, AllocationPolicy,
    PaginationPolicy, EngramStrengthPolicy, EmbeddingProfile, AffectPalette
    + the old CognitivePolicy — consolidated by
    s-consolidate-cognitive-policies, 39→31) + Reference + Kaizen
    (improvement observations, v1.13.0)."""
    k = Kernel()
    k.load(SdlcExtension())
    api_kinds = sorted(kn for (av, kn) in k._kinds if av == "github.com/ruinosus/dna/sdlc/v1")
    assert api_kinds == [
        "ADR", "AgentSession",
        "ArchiveProposal", "Bug", "Changelog", "CognitivePolicy",
        "Epic",
        "Feature", "Forecast", "HtmlArtifact", "Initiative", "Insight", "Issue", "Kaizen",
        "Narrative",
        "Plan", "Postmortem", "PromptTemplate", "Reference",
        "Retrospective", "RiskRegister", "Roadmap", "SavedView", "Spec",
        "Spike", "StatusReport", "Story", "SynthesisRun",
        "SynthesizerState", "Task", "WorkflowEvent",
    ]
    assert len(api_kinds) == 31


def test_agent_session_kind_storage_bundle():
    """AgentSession uses bundle storage; SESSION.md carries the transcript markdown."""
    from dna.extensions.sdlc import AgentSessionKind
    sd = AgentSessionKind().storage
    assert sd.pattern.value == "bundle"
    assert sd.container == "agent-sessions"
    assert sd.marker == "SESSION.md"
    assert sd.body_field == "body"


def test_agent_session_required_fields_tool_agnostic():
    """AgentSession schema requires tool + session_id + started_at + title (LCD across CC/Cursor/etc)."""
    from dna.extensions.sdlc import AgentSessionKind
    schema = AgentSessionKind().schema()
    assert set(schema["required"]) == {"title", "tool", "session_id", "started_at"}
    # produced_artifacts is M:N to any kind
    pa = schema["properties"]["produced_artifacts"]
    assert pa["type"] == "array"
    assert pa["items"]["required"] == ["kind", "name"]
    # tool_specific escape hatch exists
    assert "tool_specific" in schema["properties"]


def test_aliases_unique_and_namespaced():
    from dna.extensions.sdlc import SpecKind, PlanKind
    aliases = [
        RoadmapKind().alias,
        EpicKind().alias,
        FeatureKind().alias,
        StoryKind().alias,
        IssueKind().alias,
        SpecKind().alias,
        PlanKind().alias,
    ]
    assert len(set(aliases)) == 7
    assert all(a.startswith("sdlc-") for a in aliases)


# --- Spec + Plan specific --------------------------------------------------

def test_spec_schema_pattern_agnostic():
    """Spec doesn't lock structure to one pattern (superpowers/BMAD/etc.)."""
    from dna.extensions.sdlc import SpecKind
    schema = SpecKind().schema()
    assert set(schema["required"]) == {"title", "date", "status"}
    # pattern is optional + free-form (no enum)
    pattern_prop = schema["properties"]["pattern"]
    assert "enum" not in pattern_prop
    # body field exists (bundle storage; SPEC.md body)
    assert "body" in schema["properties"]


def test_spec_dep_filters_post_axis_flip():
    """v1.3 axis flip: Spec.dep_filters has epic + supersedes (no feature)."""
    from dna.extensions.sdlc import SpecKind
    deps = SpecKind().dep_filters()
    assert deps["epic"] == "sdlc-epic"
    assert deps["supersedes"] == "sdlc-spec"
    assert "feature" not in deps


def test_plan_links_spec_via_spec_ref():
    from dna.extensions.sdlc import PlanKind
    deps = PlanKind().dep_filters()
    assert deps["spec_ref"] == "sdlc-spec"


def test_spec_summary_extracts_metadata():
    from dna.extensions.sdlc import SpecKind
    kp = SpecKind()

    class _D:
        spec = {
            "title": "Phase 16 — Scope segregation: Module → Genome + LayerPolicy + KindDefinition",
            "date": "2026-05-08",
            "status": "accepted",
            "phase": "done",
            "pattern": "superpowers",
            "epic": "e-scope-segregation",
        }

    s = kp.summary(_D())
    assert s["pattern"] == "superpowers"
    assert s["epic"] == "e-scope-segregation"
    assert s["status"] == "accepted"
    assert s["phase"] == "done"


def test_spec_status_enum_is_adr_style():
    """Spec lifecycle is Nygard ADR-style: draft|proposed|accepted|deprecated|superseded."""
    from dna.extensions.sdlc import SpecKind
    statuses = SpecKind().schema()["properties"]["status"]["enum"]
    assert set(statuses) == {"draft", "proposed", "accepted", "deprecated", "superseded"}


def test_spec_phase_enum_is_superpowers_style():
    """Spec.phase is the Superpowers/Spec-Kit lifecycle, orthogonal to status."""
    from dna.extensions.sdlc import SpecKind
    phases = SpecKind().schema()["properties"]["phase"]["enum"]
    assert set(phases) == {"brainstorm", "spec", "plan_ready", "implementing", "done"}


def test_spec_no_longer_carries_feature_axis():
    """Axis flip: Spec.feature was removed; linkage is via Story.spec_refs[]."""
    from dna.extensions.sdlc import SpecKind
    schema = SpecKind().schema()
    assert "feature" not in schema["properties"]
    assert "feature" not in SpecKind().dep_filters()


def test_plan_no_longer_carries_feature_axis():
    """Axis flip: Plan.feature removed. Plan still references its parent Spec via spec_ref."""
    from dna.extensions.sdlc import PlanKind
    schema = PlanKind().schema()
    assert "feature" not in schema["properties"]
    assert "feature" not in PlanKind().dep_filters()
    # spec_ref → Spec relationship is preserved
    assert PlanKind().dep_filters()["spec_ref"] == "sdlc-spec"


def test_story_has_spec_refs_linkage():
    """Story.spec_refs[] is the M:N link from planning axis to design axis."""
    from dna.extensions.sdlc import StoryKind
    schema = StoryKind().schema()
    spec_refs = schema["properties"]["spec_refs"]
    assert spec_refs["type"] == "array"
    assert spec_refs["items"]["type"] == "string"
    assert StoryKind().dep_filters()["spec_refs"] == "sdlc-spec"


# --- Storage descriptors ---------------------------------------------------

@pytest.mark.parametrize(
    "kp_cls,container",
    [
        (RoadmapKind, "roadmaps"),
        (EpicKind, "epics"),
        (FeatureKind, "features"),
        (StoryKind, "stories"),
        (IssueKind, "issues"),
    ],
)
def test_storage_yaml_pattern(kp_cls, container):
    sd = kp_cls().storage
    assert sd.pattern.value == "yaml"
    assert sd.container == container


def test_spec_plan_storage_bundle():
    """Spec + Plan use BUNDLE pattern (markdown body in marker file).

    Pattern-agnostic still — but bundle gives us frontmatter + body,
    aligning with Skill / Soul / Doc convention. NO external file_path
    needed because the bundle IS the source of truth.
    """
    from dna.extensions.sdlc import SpecKind, PlanKind
    sp_sd = SpecKind().storage
    assert sp_sd.pattern.value == "bundle"
    assert sp_sd.container == "specs"
    assert sp_sd.marker == "SPEC.md"
    assert sp_sd.body_field == "body"

    pl_sd = PlanKind().storage
    assert pl_sd.pattern.value == "bundle"
    assert pl_sd.container == "plans"
    assert pl_sd.marker == "PLAN.md"
    assert pl_sd.body_field == "body"


# --- Schema validation -----------------------------------------------------

def test_roadmap_schema_required_fields():
    schema = RoadmapKind().schema()
    assert "description" in schema["required"]
    assert "horizons" in schema["required"]
    horizons = schema["properties"]["horizons"]
    assert horizons["type"] == "array"


def test_milestone_status_enum_complete():
    schema = EpicKind().schema()
    statuses = schema["properties"]["status"]["enum"]
    assert set(statuses) == set(EPIC_STATUSES)
    assert "done" in statuses
    assert "deprecated" in statuses
    # `shipped` was renamed to `done` in v1.2 (Jira/Azure DevOps alignment).
    assert "shipped" not in statuses


def test_milestone_links_to_package():
    schema = EpicKind().schema()
    props = schema["properties"]
    assert "target_package" in props
    assert "target_version" in props


def test_feature_dep_filters_link_kinds():
    deps = FeatureKind().dep_filters()
    assert deps["use_cases"] == "helix-usecase"
    assert deps["owner"] == "helix-actor"
    assert deps["stories"] == "sdlc-story"


def test_feature_status_enum():
    statuses = FeatureKind().schema()["properties"]["status"]["enum"]
    assert set(statuses) == set(FEATURE_STATUSES)


def test_story_status_and_estimate():
    schema = StoryKind().schema()
    statuses = schema["properties"]["status"]["enum"]
    assert set(statuses) == set(STORY_STATUSES)
    assert schema["properties"]["estimate"]["type"] == "number"
    assert schema["properties"]["dependencies"]["items"]["type"] == "string"


def test_issue_full_taxonomy():
    schema = IssueKind().schema()
    props = schema["properties"]
    assert set(props["type"]["enum"]) == set(ISSUE_TYPES)
    assert set(props["severity"]["enum"]) == set(ISSUE_SEVERITIES)
    assert set(props["status"]["enum"]) == set(ISSUE_STATUSES)
    # Phase-16 link to Finding (eval-derived issues bridge into manual tracking)
    assert "related_finding" in props


def test_issue_dep_filters_link_finding():
    deps = IssueKind().dep_filters()
    assert deps["related_feature"] == "sdlc-feature"


# --- Parse + Summary -------------------------------------------------------

def test_milestone_summary_extracts_target():
    kp = EpicKind()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "Epic",
        "metadata": {"name": "release-2-0"},
        "spec": {
            "status": "in-progress",
            "target_date": "2026-06-30",
            "target_package": "platform/hr-screening",
            "target_version": "2.0.0",
            "features": ["pii-masking", "tenant-overlay"],
        },
    }

    class _D:
        spec = raw["spec"]

    s = kp.summary(_D())
    assert s["status"] == "in-progress"
    assert s["target_version"] == "2.0.0"
    assert s["features"] == 2


def test_roadmap_summary_counts_epics():
    kp = RoadmapKind()

    class _D:
        spec = {
            "description": "2026 roadmap",
            "horizons": [
                {"label": "Q1", "epics": ["e-foundations"]},
                {
                    "label": "Q2",
                    "epics": ["e-multi-tenant", "e-eval-evolve"],
                },
            ],
        }

    s = kp.summary(_D())
    assert s["horizons"] == 2
    assert s["epics"] == 3


# --- Identity properties ---------------------------------------------------

def test_kinds_not_prompt_targets():
    """SDLC docs are organizational, never injected into prompts."""
    for kp_cls in [RoadmapKind, EpicKind, FeatureKind, StoryKind, IssueKind]:
        kp = kp_cls()
        assert kp.is_prompt_target is False
        assert kp.flatten_in_context is False
        assert kp.is_root is False  # Phase 16 — only Genome is root


# --- Agent memory Phase 0 — visibility axis (s-agent-memory-phase-0-bridge) -

def test_engram_has_visibility_axis():
    """visibility controls recall audience; default shared. owner stays = attribution.
    Enum: shared (all agents) | private (owner only) | pinned (always-in-context) |
    archived (retained, excluded from default recall)."""
    # F3 lote-1: class deleted — port synthesized from the descriptor.
    # Engram itself now registers via HelixExtension (s-engram-rename).
    from dna.extensions.helix import HelixExtension
    from dna.kernel import Kernel
    k = Kernel(); k.load(HelixExtension())
    props = k.kind_port_for("Engram").schema()["properties"]
    vis = props["visibility"]
    assert vis["enum"] == ["shared", "private", "pinned", "archived"]
    assert vis.get("default") == "shared"
    # owner still present (attribution axis), orthogonal to visibility
    assert "owner" in props


def test_memory_section_is_agent_governance_only():
    """CognitivePolicy.memory.policies[] (ex-MemoryPolicy) governs the AGENT
    axis (visibility/include_agents/pinned/remember) — and deliberately does
    NOT own scoring/affect/decay (those live in the sibling engram_strength /
    affect / decay sections; rsh-agent-memory-semon-convergence +
    s-consolidate-cognitive-policies)."""
    from dna.extensions.sdlc import SdlcExtension
    from dna.kernel import Kernel
    k = Kernel(); k.load(SdlcExtension())
    schema = k.kind_port_for("CognitivePolicy").schema()
    assert schema.get("additionalProperties") is False  # left the grandfather set
    top = schema["properties"]
    entry = top["memory"]["properties"]["policies"]["items"]
    props = entry["properties"]
    # Has the agent-governance knobs
    assert "applies_to" in props and "defaults" in props and "remember" in props
    dv = props["defaults"]["properties"]["visibility"]
    assert dv["enum"] == ["shared", "private", "pinned", "archived"]
    assert "include_agents" in props["defaults"]["properties"]
    assert "pinned_budget" in props["defaults"]["properties"]
    # Does NOT duplicate Semon inside the memory entry (siblings own those)
    for forbidden in ("scoring", "affect_weights", "decay", "rrf"):
        assert forbidden not in props, f"memory entry must NOT own {forbidden} (siblings do)"
    # ...and the siblings DO exist as sections of the unified Kind.
    for section in ("recall", "decay", "generation", "allocation",
                    "pagination", "engram_strength", "embedding", "affect"):
        assert section in top, f"missing consolidated section {section}"


def test_engram_coala_and_bitemporal_fields():
    """Phase 4: memory_type (CoALA, orthogonal to EngramState) + bi-temporal
    valid_from/valid_to/superseded_by_memory (invalidate-not-delete)."""
    # F3 lote-1: class deleted — port synthesized from the descriptor.
    # Engram itself now registers via HelixExtension (s-engram-rename).
    from dna.extensions.helix import HelixExtension
    from dna.kernel import Kernel
    k = Kernel(); k.load(HelixExtension())
    props = k.kind_port_for("Engram").schema()["properties"]
    assert props["memory_type"]["enum"] == ["episodic", "semantic", "procedural"]
    for f in ("valid_from", "valid_to", "superseded_by_memory"):
        assert f in props, f"missing bi-temporal field {f}"
    # named superseded_by_memory (NOT superseded_by — that's an ADR dep token)
    assert "superseded_by" not in props
