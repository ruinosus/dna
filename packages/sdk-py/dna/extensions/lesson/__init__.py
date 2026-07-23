"""LessonExtension — declarative educational activities for AAC use.

A `Lesson` is a short, structured activity Lumi can run with Mateus
(or any child with similar profile). Each lesson targets a single
concept group (cores básicas, animais conhecidos, comida, rotinas),
declares a skill (reconhecer, parear, repetir, identificar), and
provides Lumi-spoken prompts + a list of target Pictogram concepts.

Why a Kind, not Python code:
    * Lesson content is curated by caregivers (parents, therapists),
      not engineers. YAML is editable in Studio without code review.
    * A/B test variants of the same lesson without redeploy.
    * Per-child overlay possible in future (Lesson tenant overlay).

The agent runs a lesson by calling `start_lesson(subject)`. The
tool fetches the catalog, picks the best match, and returns a
script the model can speak through with PTT pauses.

Storage: bundle (LESSON.md frontmatter = spec). GLOBAL scope —
the catalog is per-scope (Mateus's project alpha), not per-tenant.

Phase 16-pre (2026-05-20). Story `s-mateus-lesson-extension`.
"""
from __future__ import annotations

import re
from typing import Any

import yaml

from dna.kernel.kinds.base import KindBase
from dna.kernel.protocols import ExtensionHost, StorageDescriptor, TenantScope, WriterPort
from dna.kernel.bundle.handle import BundleHandle


_API_VERSION = "github.com/ruinosus/dna/lesson/v1"
_ORIGIN = "github.com/ruinosus/dna/lesson"


from dna.kernel.generic_rw import MarkdownBundleReader


class LessonKind(KindBase):
    api_version = _API_VERSION
    kind = "Lesson"
    alias = "lesson-lesson"
    model = dict
    origin = _ORIGIN
    scope = TenantScope.GLOBAL
    storage = StorageDescriptor.bundle("lessons", "LESSON.md")
    graph_style = {"fill": "#F59E0B", "stroke": "#D97706", "text_color": "#fff"}
    ascii_icon = "📚"
    display_label = "Lessons"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False

    docs = (
        "A Lesson is a short, structured educational activity the "
        "agent can run with a pre-reader child. Declarative — content "
        "is in YAML, edited by caregivers in Studio, no code review. "
        "Tools: start_lesson(subject) picks one; record_attempt "
        "(concept, correct) tracks performance into Engram docs."
    )

    def schema(self) -> dict[str, Any] | None:
        return {
            "type": "object",
            "required": ["subject", "target_concepts", "prompts"],
            "additionalProperties": True,
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Short concept group ('cores-basicas', 'animais-conhecidos', 'rotina-comer').",
                },
                "title": {
                    "type": "string",
                    "description": "Display title in PT-BR ('Cores básicas', 'Animais que você conhece').",
                },
                "skill": {
                    "type": "string",
                    "enum": [
                        "reconhecer", "identificar", "parear",
                        "repetir", "associar", "contar", "ordenar",
                    ],
                    "default": "reconhecer",
                },
                "modality": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["visual", "audio", "interativo"]},
                    "default": ["visual", "audio", "interativo"],
                },
                "difficulty": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 1,
                },
                "duration_seconds_max": {
                    "type": "integer",
                    "default": 120,
                    "description": "Cap to respect TDAH attention budget. 60-180 typical for ages 8-12.",
                },
                "target_concepts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Concept slugs that match Pictogram.spec.concept (azul, vermelho, etc).",
                },
                "prompts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "DEPRECATED v2: legacy flat list of Lumi-spoken prompts. Use `steps` instead. Kept for back-compat with v1 seeds — if `steps` is missing, runtime synthesizes a 1-step-per-prompt timeline.",
                },
                # Multi-step format — s-mateus-lessons-multistep-schema 2026-05-20.
                # Each step has a `kind` cue (present/repeat/test/celebrate/review)
                # and a prompt Lumi speaks. Optional `expected_concept` points to
                # a Pictogram concept to show via show_pictogram. on_correct /
                # on_incorrect carry the navigation hint for the agent.
                "steps": {
                    "type": "array",
                    "description": "Ordered list of LessonStep objects. Agent walks them in order, listening to Mateus between each, calling show_pictogram for visual anchor and record_attempt on test steps.",
                    "items": {
                        "type": "object",
                        "required": ["kind", "prompt"],
                        "additionalProperties": True,
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": ["present", "repeat", "test", "celebrate", "review"],
                                "description": (
                                    "present = introduce concept; repeat = ask "
                                    "Mateus to repeat/imitate; test = ask Mateus "
                                    "to identify (calls record_attempt); "
                                    "celebrate = positive reinforcement; "
                                    "review = recap before next step."
                                ),
                            },
                            "prompt": {
                                "type": "string",
                                "description": "Short PT-BR phrase Lumi speaks at this step. ≤6 words ideal.",
                            },
                            "expected_concept": {
                                "type": "string",
                                "description": "Optional Pictogram concept slug to show via show_pictogram(). Required on `test` steps so record_attempt knows the target.",
                            },
                            "on_correct": {
                                "type": "string",
                                "description": "Lumi's reaction on success. Default: 'Isso!' for test, advance otherwise.",
                            },
                            "on_incorrect": {
                                "type": "string",
                                "description": "Lumi's reaction on failure. Default: gentle re-prompt + show pictogram again.",
                            },
                            "hint_ladder": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional 1-3 progressively stronger hints if Mateus errs (silhouette → color → sound).",
                            },
                        },
                    },
                },
                "reinforcement": {
                    "type": "string",
                    "enum": ["celebrate", "gentle", "neutral"],
                    "default": "celebrate",
                    "description": "How Lumi reacts to correct answers. 'celebrate' = set_pose celebrating + warm phrase.",
                },
                "on_no_response": {
                    "type": "string",
                    "default": "Vamos tentar outra coisa?",
                    "description": "Phrase Lumi says after ~30s of no input. Always gentle, never pressuring.",
                },
                "success_criteria": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "How to mark this lesson 'done well'. Example: {matches: 3, duration_min: 30}.",
                },
                "approved_by": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
            },
        }

    def describe(self, doc: Any) -> str | None:
        spec = getattr(doc, "spec", None) or {}
        if not isinstance(spec, dict):
            spec = dict(spec) if spec else {}
        title = spec.get("title") or spec.get("subject", "?")
        diff = spec.get("difficulty", 1)
        return f"{title} (lv {diff})"

    def summary(self, doc: Any) -> dict[str, Any] | None:
        spec = getattr(doc, "spec", None) or {}
        if not isinstance(spec, dict):
            spec = dict(spec) if spec else {}
        concepts = spec.get("target_concepts", []) or []
        steps = spec.get("steps", []) or []
        return {
            "subject": spec.get("subject", ""),
            "skill": spec.get("skill", ""),
            "difficulty": spec.get("difficulty", 1),
            "concept_count": len(concepts),
            "step_count": len(steps),
            "format": "multi-step" if steps else "legacy-prompts",
        }


class LessonWriter(WriterPort):
    def can_write(self, raw: dict) -> bool:
        return raw.get("kind") == "Lesson"

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
            "kind": raw.get("kind", "Lesson"),
            "metadata": clean_meta,
            "spec": clean_spec,
        }
        fm_yaml = yaml.safe_dump(
            envelope, default_flow_style=False, sort_keys=False,
            allow_unicode=True, width=100,
        ).rstrip("\n")
        title = clean_spec.get("title") or clean_spec.get("subject", "?")
        skill = clean_spec.get("skill", "reconhecer")
        diff = clean_spec.get("difficulty", 1)
        body = (
            f"# Lesson — {title} (skill: {skill}, lv {diff})\n\n"
            f"Curated educational activity for child-companion agents. "
            f"Run via `start_lesson({clean_spec.get('subject', '?')})`.\n"
        )
        return [
            {"relativePath": "LESSON.md", "content": f"---\n{fm_yaml}\n---\n\n{body}"},
        ]

    def write(self, bundle: BundleHandle, raw: dict) -> None:
        for f in self.serialize(raw):
            bundle.write_text(f["relativePath"], f["content"])


class LessonExtension:
    name = "lesson"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(LessonKind())
        kernel.reader(MarkdownBundleReader("LESSON.md", "Lesson", "github.com/ruinosus/dna/lesson/v1"))
        kernel.writer(LessonWriter())
