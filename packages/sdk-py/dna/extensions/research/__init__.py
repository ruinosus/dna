"""ResearchExtension — curated research syntheses with evidence ratings.

A `Research` is a structured artifact representing a piece of curated
inquiry — literature review, web research, field study, etc. Unlike
`Reference` (which is a pointer to 1 external source), a Research
synthesizes N References with:

- **objective** — why the research was conducted
- **methodology** — how it was done (web-search-curated, lit-review,
  interview, field-study, ...)
- **sources** — list of `Reference` doc names this synthesizes from
- **findings** — discrete claims, each with `evidence_rating`
  (evidence-based | opinion-practice | anecdotal) + `source_refs`
  pointing back to the Reference docs that support them
- **recommendations** — priority-ranked actions backed by findings,
  optionally flagged `clinical_decision: true` for human-only approval

Why a Kind, not just markdown:

- **Auditability** — querying "show me all evidence-based findings"
  becomes trivial. Clinical contexts demand a visible evidence trail.
- **Citation graph** — each finding references specific Reference
  docs; each Reference's `cited_by` includes the Research that
  synthesized it. Bidirectional, automatable.
- **Versioning** — `status: superseded` + `superseded_by` lets new
  research replace old without losing history. Critical when the
  evidence base evolves over months.
- **Agent consumption** — a Research is agent-facing knowledge with
  provenance: curated + cited + deterministic, the declarative answer
  to LLM-generated repo-wiki prose (OpenWiki / DeepWiki).

Storage: bundle (`research/<slug>/RESEARCH.md`, frontmatter = spec).

Tenancy: PERMISSIVE (no ``scope`` attribute declared) — a Research is
authored knowledge of THIS repo, not per-client data. It is writable
and readable WITHOUT a mandatory tenant (base doc), with an optional
per-tenant override. Contrast with the upstream port, which marked
Research TENANTED; that would force a tenant on every ``dna research
create`` for a Kind that is repo-authored, not tenant-private. See the
maxim "herdável ⇒ nunca TENANTED": permissive satisfies it (never
TENANTED); the base doc always writes.

Reference companion: the ``Reference`` Kind already ships via the
``sdlc`` extension (alias ``sdlc-reference``). A Research's ``sources``
field names Reference doc slugs — we reuse the existing Kind, we do NOT
register a second Reference here. (Shape note: the sdlc Reference
requires ``{title, kind_of, summary}``; the upstream research Reference
required only ``{title}``. Since ``sources`` holds bare names, the two
interoperate by-name; a Research citing richer references just points at
sdlc Reference docs.)

Recall: the upstream ``recall_research`` semantic tool needs an
embeddings server that did not travel to this repo. Lexical/structured
recall degrades to ``kernel.query`` over the Research catalog; pgvector
semantic recall is documented future work (no crash, no service).

Ported from the upstream SDK (s-dna-research-kind, 2026-07-09).
"""
from __future__ import annotations

from typing import Any

import yaml

from dna.kernel.kind_base import KindBase
from dna.kernel.protocols import ExtensionHost, StorageDescriptor, WriterPort
from dna.kernel.bundle_handle import BundleHandle
from dna.kernel.generic_rw import MarkdownBundleReader


_API_VERSION = "github.com/ruinosus/dna/research/v1"
_ORIGIN = "github.com/ruinosus/dna/research"

# Vocab for methodology enum.
METHODOLOGIES = (
    "web-search-curated",   # human + LLM web search synthesis
    "literature-review",    # systematic review of papers
    "interview",            # human interviews / field testimony
    "field-study",          # observation in real settings
    "experiment",           # controlled study (RCT or quasi)
    "synthesis",            # meta-review of multiple prior researches
    "other",
)

EVIDENCE_RATINGS = ("evidence-based", "opinion-practice", "anecdotal")

# Lifecycle: brief (recipe being written) → ready (recipe complete) →
# draft (Research generated, pre-review) → published (finalized) →
# superseded/retracted (terminal states).
STATUSES = ("brief", "ready", "draft", "published", "superseded", "retracted")
RECIPE_STATUSES = ("brief", "ready")
OUTPUT_STATUSES = ("draft", "published", "superseded", "retracted")

VISIBILITY = ("scope-private", "shared")


# Block-literal representer for multi-line strings. yaml.safe_dump with
# width=N wraps long double-quoted strings using ``\`` line continuation.
# For markdown-ish content (tables with ``|``, emojis next to escapes,
# fenced blocks) that output can fail to round-trip ("unexpected end of
# stream"). Block literals (``|``) don't escape: they round-trip cleanly.
# Used by ResearchWriter when serializing bundle frontmatter.
class _BlockLiteralDumper(yaml.SafeDumper):
    pass


def _str_block_literal_representer(dumper, value):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_BlockLiteralDumper.add_representer(str, _str_block_literal_representer)


def _safe_dump_with_block_literals(envelope: dict[str, Any]) -> str:
    """yaml dump that uses block-literal style for multi-line strings —
    round-trip safe regardless of escape complexity."""
    return yaml.dump(
        envelope, Dumper=_BlockLiteralDumper,
        default_flow_style=False, sort_keys=False,
        allow_unicode=True, width=100,
    ).rstrip("\n")


class ResearchKind(KindBase):
    api_version = _API_VERSION
    kind = "Research"
    # alias generated as <owner>-<kebab(kind)> = "research-research" (owner =
    # extension name "research"). New Kinds must not TYPE an explicit alias
    # (guard: test_alias_generation.py, s-alias-generated-not-typed); declaring
    # it None keeps the KindPort Protocol satisfied while triggering generation.
    alias = None
    alias_owner = "research"
    model = dict
    origin = _ORIGIN
    # PERMISSIVE tenancy — NO ``scope`` attribute declared. The write
    # pipeline treats an undeclared scope as permissive (base writes with
    # or without a tenant), matching this Kind being repo-authored
    # knowledge, not tenant-private data. (Upstream set TENANTED; DNA
    # decision ratified: permissive.)
    storage = StorageDescriptor.bundle("research", "RESEARCH.md")
    graph_style = {"fill": "#7C3AED", "stroke": "#5B21B6", "text_color": "#fff"}
    ascii_icon = "🔬"
    display_label = "Research"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False

    docs = (
        "A Research is a curated synthesis of N external sources "
        "(Reference docs) with objective, methodology, evidence-rated "
        "findings, and priority recommendations. Designed for "
        "auditability + agent consumption. Use Reference for a single "
        "external source; use Research to consolidate multiple "
        "References into a position with recommendations."
    )

    def schema(self) -> dict[str, Any] | None:
        return {
            "type": "object",
            "required": ["title", "objective", "methodology", "status"],
            "additionalProperties": True,
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short human title in PT-BR or EN.",
                },
                "objective": {
                    "type": "string",
                    "description": "Why this research was conducted. 1-3 sentences.",
                },
                "executive_summary": {
                    "type": "string",
                    "description": "TL;DR — 200-500 words. What this research concludes + what to do. Goes prominently at top of viewer + listing card preview.",
                },
                "key_takeaways": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-7 bullets — 'if you read nothing else'. Most surfaceable in dashboards.",
                    "default": [],
                },
                "overall_confidence": {
                    "type": "string",
                    "enum": ["high", "moderate", "low", "very-low"],
                    "description": "GRADE-inspired confidence rating. Computable: high if >=80% findings evidence-based, moderate 60-80, low 40-60, very-low <40. Author can override.",
                },
                "last_reviewed_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Most recent human review of this research (for living reviews).",
                },
                "next_review_due": {
                    "type": "string",
                    "format": "date-time",
                    "description": "When this research should be re-validated (literature evolves).",
                },
                "methodology": {
                    "type": "string",
                    "enum": list(METHODOLOGIES),
                    "default": "web-search-curated",
                },
                "conducted_by": {
                    "type": "string",
                    "description": (
                        "Actor who ran the synthesis: claude-code, "
                        "jefferson, auto-synth, ..."
                    ),
                },
                "conducted_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "When the research was synthesized.",
                },
                "scope_ref": {
                    "type": "string",
                    "description": "Scope this research informs (e.g. 'dna-development').",
                },
                "visibility": {
                    "type": "string",
                    "enum": list(VISIBILITY),
                    "default": "scope-private",
                    "description": (
                        "scope-private = only this scope sees it. "
                        "shared = discoverable across scopes."
                    ),
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Reference doc names this research synthesizes "
                        "from. Each entry should resolve to a Reference doc "
                        "(sdlc-reference Kind)."
                    ),
                    "default": [],
                },
                "findings": {
                    "type": "array",
                    "description": (
                        "Discrete claims extracted from sources. Each "
                        "has an evidence rating that gates how the "
                        "recommendation is presented."
                    ),
                    "items": {
                        "type": "object",
                        "required": ["id", "title", "evidence_rating"],
                        "additionalProperties": True,
                        "properties": {
                            "id": {
                                "type": "string",
                                "pattern": "^f-[a-z0-9-]+$",
                                "description": "Stable id within this Research (e.g. 'f-diataxis-adoption').",
                            },
                            "title": {"type": "string"},
                            "summary": {"type": "string"},
                            "evidence_rating": {
                                "type": "string",
                                "enum": list(EVIDENCE_RATINGS),
                            },
                            "source_refs": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Reference names supporting this finding.",
                                "default": [],
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "default": [],
                            },
                        },
                    },
                    "default": [],
                },
                "recommendations": {
                    "type": "array",
                    "description": (
                        "Actionable proposals derived from findings, "
                        "ranked by priority. Items marked "
                        "`clinical_decision: true` require human "
                        "sign-off before implementation."
                    ),
                    "items": {
                        "type": "object",
                        "required": ["id", "priority", "summary"],
                        "additionalProperties": True,
                        "properties": {
                            "id": {
                                "type": "string",
                                "pattern": "^rec-[a-z0-9-]+$",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                            },
                            "summary": {"type": "string"},
                            "effort_hours": {"type": "number"},
                            "clinical_decision": {"type": "boolean", "default": False},
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "default": [],
                            },
                            "backed_by_findings": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Finding ids supporting this recommendation.",
                                "default": [],
                            },
                            "status": {
                                "type": "string",
                                "enum": ["proposed", "accepted", "rejected", "implemented", "blocked"],
                                "default": "proposed",
                            },
                        },
                    },
                    "default": [],
                },
                "status": {
                    "type": "string",
                    "enum": list(STATUSES),
                    "default": "draft",
                    "description": (
                        "Lifecycle: brief|ready (recipe phase) → "
                        "draft|published (output phase) → superseded|retracted (terminal)."
                    ),
                },
                "superseded_by": {
                    "type": "string",
                    "description": "Name of newer Research that replaces this one.",
                },
                "retracted_reason": {
                    "type": "string",
                    "description": "Why this Research was retracted (audit trail).",
                },
                # ─── RECIPE PHASE FIELDS. Optional, populated when
                # status in (brief, ready). ──────────────────────────
                "audience_context": {
                    "type": "string",
                    "description": "Recipe phase: context block fed to the LLM.",
                },
                "research_blocks": {
                    "type": "array",
                    "description": (
                        "Recipe phase: structured question blocks. "
                        "Each block has title + list of questions."
                    ),
                    "items": {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {
                            "title": {"type": "string"},
                            "questions": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                    "default": [],
                },
                "output_constraints": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recipe phase: extra output constraints.",
                    "default": [],
                },
                "reference_baselines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recipe phase: Research names to NOT duplicate.",
                    "default": [],
                },
                "brief_notes": {
                    "type": "string",
                    "description": "Recipe phase: author notes about the recipe.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "owner": {
                    "type": "string",
                    "description": "Who owns/maintains the doc.",
                },
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
            },
        }

    def describe(self, doc: Any) -> str | None:
        spec = getattr(doc, "spec", None) or {}
        if not isinstance(spec, dict):
            spec = dict(spec) if spec else {}
        title = spec.get("title", "?")
        status = spec.get("status", "draft")
        return f"{title} [{status}]"

    def summary(self, doc: Any) -> dict[str, Any] | None:
        spec = getattr(doc, "spec", None) or {}
        if not isinstance(spec, dict):
            spec = dict(spec) if spec else {}
        findings = spec.get("findings", []) or []
        recs = spec.get("recommendations", []) or []
        ev_findings = sum(1 for f in findings if f.get("evidence_rating") == "evidence-based")
        return {
            "title": spec.get("title", ""),
            "methodology": spec.get("methodology", ""),
            "status": spec.get("status", "draft"),
            "sources_count": len(spec.get("sources", []) or []),
            "findings_count": len(findings),
            "evidence_based_count": ev_findings,
            "recommendations_count": len(recs),
        }


class ResearchWriter(WriterPort):
    def can_write(self, raw: dict) -> bool:
        return raw.get("kind") == "Research"

    def serialize(self, raw: dict) -> list[dict[str, str]]:
        spec = raw.get("spec", {}) or {}
        if not isinstance(spec, dict):
            spec = dict(spec) if spec else {}
        meta = dict(raw.get("metadata", {}) or {})
        clean_spec = {
            k: v for k, v in spec.items()
            if v is not None and v != "" and v != [] and v != {}
        }
        clean_meta = {k: v for k, v in meta.items() if v is not None}
        envelope = {
            "apiVersion": raw.get("apiVersion", _API_VERSION),
            "kind": raw.get("kind", "Research"),
            "metadata": clean_meta,
            "spec": clean_spec,
        }
        fm_yaml = _safe_dump_with_block_literals(envelope)
        title = clean_spec.get("title", "?")
        method = clean_spec.get("methodology", "synthesis")
        n_findings = len(clean_spec.get("findings", []) or [])
        n_sources = len(clean_spec.get("sources", []) or [])
        body = (
            f"# Research — {title}\n\n"
            f"Methodology: {method} · {n_sources} sources · {n_findings} findings.\n\n"
            f"This file's spec (frontmatter above) is the authoritative "
            f"data. The prose below is for human reading and is regenerated "
            f"on each write. Edit via `dna research` CLI or the Studio "
            f"viewer; raw frontmatter edits are also supported.\n"
        )
        return [
            {"relativePath": "RESEARCH.md", "content": f"---\n{fm_yaml}\n---\n\n{body}"},
        ]

    def write(self, bundle: BundleHandle, raw: dict) -> None:
        for f in self.serialize(raw):
            bundle.write_text(f["relativePath"], f["content"])


def compute_overall_confidence(findings: list[dict[str, Any]]) -> str:
    """GRADE-inspired confidence rating from findings distribution.

    high       — ≥80% findings evidence-based
    moderate   — 60-80%
    low        — 40-60%
    very-low   — <40%

    Used as default when author hasn't explicitly set
    `overall_confidence`. Author override always wins.
    """
    if not findings:
        return "very-low"
    ev = sum(1 for f in findings if f.get("evidence_rating") == "evidence-based")
    pct = ev / len(findings)
    if pct >= 0.80:
        return "high"
    if pct >= 0.60:
        return "moderate"
    if pct >= 0.40:
        return "low"
    return "very-low"


class ResearchExtension:
    name = "research"
    version = "1.2.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(ResearchKind())
        # Reference companion is provided by the sdlc extension
        # (alias sdlc-reference) — NOT re-registered here.
        kernel.reader(MarkdownBundleReader("RESEARCH.md", "Research", _API_VERSION))
        kernel.writer(ResearchWriter())
