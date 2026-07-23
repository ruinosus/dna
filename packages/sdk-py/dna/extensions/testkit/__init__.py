"""TestkitExtension — first-class TEST artifacts for the SDLC.

Registers TWO artifact KindPorts (not work-items — a test script is a document,
like a Spec/HtmlArtifact, produced BY a work item and verifying it):

  - TestGuide (testkit-test-guide) — a declarative test SCRIPT: an ordered list
    of ``steps`` (action → expected) that validates one or more work items. The
    roteiro that used to live in chat / a generic HtmlArtifact becomes a
    versioned, schema-validated, re-runnable doc linked to its Story via
    ``verifies`` (and the Story's ``produces[]``).

  - TestRun (testkit-test-run) — an EXECUTION record of a TestGuide: the
    ``outcome`` (pass/fail/partial/blocked), who ran it, per-step results and
    evidence. Producing one stamps an ``artifact_produced`` event on the work
    item's timeline (so it surfaces in FOCUS for free), and a passing run with
    ``verifies`` pointing at a Story drives the derived journey's ``verify``
    phase.

Both are GLOBAL-scoped per-project ledger docs (like the SDLC kinds), stored
under ``<scope>/.dna/<scope>/test-guides|test-runs/``. Auto-exposed in Studio
via ``ui = docs_ui(...)`` (generic docs surface; forms from ``schema()``).

Story: s-decompose-jarvis-session-context follow-up — the "TESTS as dedicated
kinds/extensions" gap in the dogfooded SDLC.
"""
from __future__ import annotations

from typing import Any

from dna.kernel.protocols import ExtensionHost, StorageDescriptor, TenantScope
from dna.kernel.kinds.base import KindBase
from dna.kernel.studio_ui import docs_ui

_API_VERSION = "github.com/ruinosus/dna/testkit/v1"
_ORIGIN = "github.com/ruinosus/dna/testkit"

# Kinds of test a TestGuide can describe. Deliberately excludes "unit" — unit
# tests live in the CI suites (vitest/pytest), not in human/orchestrated guides.
_TEST_KINDS = ["manual", "smoke", "e2e", "regression", "integration"]
_GUIDE_STATUS = ["draft", "active", "deprecated"]
_RUN_OUTCOME = ["pass", "fail", "partial", "blocked"]
_STEP_RESULT = ["pass", "fail", "skip"]

#: Product-lane test kinds — a human validating the feature in the UI. The
#: ``story done`` gate (s-testkit-done-requires-product-smoke) counts these;
#: the automated lane (e2e/regression/integration) is proven by CI on the PR.
PRODUCT_TEST_KINDS = frozenset({"manual", "smoke"})


def derive_overall_outcome(step_results: list[dict] | None) -> str:
    """Derive a TestRun's overall outcome from its per-step results.

    Precedence: any ``fail`` → ``fail``; all ``pass`` → ``pass``; a mix of
    ``pass``/``skip`` (no fail) → ``partial``; nothing run → ``blocked``. Used by
    the Studio runner endpoint so the overall outcome is never out of sync with
    what the tester actually marked per step.
    """
    results = [str((r or {}).get("result")) for r in (step_results or [])]
    results = [r for r in results if r in _STEP_RESULT]
    if not results:
        return "blocked"
    if "fail" in results:
        return "fail"
    if all(r == "pass" for r in results):
        return "pass"
    return "partial"


class TestGuideKind(KindBase):
    api_version = _API_VERSION
    kind = "TestGuide"
    alias = "testkit-test-guide"
    ui = docs_ui(
        "TestGuide", mode="quality", label_en="Test Guides", label_pt="Roteiros de Teste",
        icon="🧪", display_order=70,
        description_en="Declarative test scripts (steps → expected) that verify work items.",
        description_pt="Roteiros de teste declarativos (passos → esperado) que verificam work items.",
    )
    model = dict
    origin = _ORIGIN
    scope = TenantScope.GLOBAL
    storage = StorageDescriptor.yaml("test-guides")
    graph_style = {"fill": "#2DD4BF", "stroke": "#0D9488", "text_color": "#fff"}
    ascii_icon = "🧪"
    display_label = "Test Guides"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    is_schema_affecting = False
    # Inheritable by default (like HtmlArtifact/Research — an artifact, not a
    # work-item): a guide authored in _lib can be inherited by every scope.
    docs = (
        "A TestGuide is a declarative test SCRIPT: an ordered list of steps "
        "(action → expected) that validates one or more work items. A versioned, "
        "schema-validated, re-runnable doc — the roteiro that used to live in "
        "chat or a generic HtmlArtifact. Links to its Story via ``verifies`` (and "
        "the Story's ``produces[]``)."
    )

    def schema(self) -> dict[str, Any] | None:
        return {
            "type": "object",
            "required": ["description", "kind_of_test", "steps"],
            "additionalProperties": False,
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What this guide validates (one line or short paragraph).",
                },
                "kind_of_test": {"type": "string", "enum": _TEST_KINDS},
                "status": {"type": "string", "enum": _GUIDE_STATUS, "default": "active"},
                "steps": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["action", "expected"],
                        "additionalProperties": False,
                        "properties": {
                            "action": {"type": "string", "description": "What the tester does."},
                            "expected": {"type": "string", "description": "Observable expected result."},
                            "where": {
                                "type": "string",
                                "description": "Where in the product to do it (route/screen) so a non-dev can follow, e.g. '/scopes/:scope/sdlc/v2?t=focus'.",
                            },
                        },
                    },
                },
                "verifies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Work items this guide verifies, as 'Kind/name' refs (e.g. 'Story/s-x').",
                },
                "prerequisites": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Setup needed before running, e.g. ['make up', 'tenant acme selected'].",
                },
                "scope_hint": {"type": "string", "description": "Target area/scope for the run."},
                "owner": {"type": "string", "description": "Actor who owns this guide."},
                "labels": {"type": "array", "items": {"type": "string"}, "default": []},
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
            },
        }

    def describe(self, doc: Any) -> str | None:
        spec = getattr(doc, "spec", None) or {}
        if not isinstance(spec, dict):
            spec = dict(spec) if spec else {}
        steps = spec.get("steps") or []
        return f"{spec.get('kind_of_test', '?')} · {len(steps)} steps [{spec.get('status', 'active')}]"

    def summary(self, doc: Any) -> dict[str, Any] | None:
        spec = getattr(doc, "spec", None) or {}
        if not isinstance(spec, dict):
            spec = dict(spec) if spec else {}
        steps = spec.get("steps") or []
        return {
            "kind_of_test": spec.get("kind_of_test", ""),
            "status": spec.get("status", "active"),
            "steps_count": len(steps),
            "verifies": spec.get("verifies") or [],
            "owner": spec.get("owner", ""),
        }


class TestRunKind(KindBase):
    api_version = _API_VERSION
    kind = "TestRun"
    alias = "testkit-test-run"
    ui = docs_ui(
        "TestRun", mode="quality", label_en="Test Runs", label_pt="Execuções de Teste",
        icon="🧾", display_order=71,
        description_en="Execution records of a TestGuide (outcome, who, per-step results).",
        description_pt="Registros de execução de um TestGuide (resultado, quem, resultados por passo).",
    )
    model = dict
    origin = _ORIGIN
    scope = TenantScope.GLOBAL
    storage = StorageDescriptor.yaml("test-runs")
    graph_style = {"fill": "#34D399", "stroke": "#059669", "text_color": "#fff"}
    ascii_icon = "🧾"
    display_label = "Test Runs"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    is_schema_affecting = False
    # Inheritable by default (artifact, not a work-item).
    docs = (
        "A TestRun is an EXECUTION record of a TestGuide: the outcome "
        "(pass/fail/partial/blocked), who ran it, per-step results and evidence. "
        "Producing one stamps an ``artifact_produced`` event on the work item's "
        "timeline (surfaces in FOCUS); a passing run whose ``verifies`` points at "
        "a Story drives the derived journey's ``verify`` phase."
    )

    def schema(self) -> dict[str, Any] | None:
        return {
            "type": "object",
            "required": ["guide_ref", "outcome"],
            "additionalProperties": False,
            "properties": {
                "guide_ref": {
                    "type": "string",
                    "description": "Name of the TestGuide that was executed.",
                },
                "outcome": {"type": "string", "enum": _RUN_OUTCOME},
                "verifies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Work items this run verifies (inherited from the guide); drives journey 'verify'.",
                },
                "executed_by": {"type": "string", "description": "Actor who ran it."},
                "executed_at": {"type": "string", "format": "date-time"},
                "step_results": {
                    "type": "array",
                    "default": [],
                    "items": {
                        "type": "object",
                        "required": ["step_index", "result"],
                        "additionalProperties": False,
                        "properties": {
                            "step_index": {"type": "integer", "minimum": 0},
                            "result": {"type": "string", "enum": _STEP_RESULT},
                            "notes": {"type": "string"},
                            "screenshot": {
                                "type": "string",
                                "description": "Screenshot evidence for this step (data URL or asset ref).",
                            },
                        },
                    },
                },
                "evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Refs/links backing the outcome, e.g. ['HtmlArtifact/ha-x', urls].",
                },
                "screenshots": {
                    "type": "array",
                    "default": [],
                    "items": {
                        "type": "object",
                        "properties": {
                            "asset": {"type": "string"},
                            "mime": {"type": "string"},
                            "blob": {"type": "string"},
                        },
                        "required": ["asset"],
                    },
                    "description": "Run-level evidence prints, Asset-backed (asset name + blob path), NOT inline base64.",
                },
                "notes": {"type": "string"},
                "labels": {"type": "array", "items": {"type": "string"}, "default": []},
            },
        }

    def describe(self, doc: Any) -> str | None:
        spec = getattr(doc, "spec", None) or {}
        if not isinstance(spec, dict):
            spec = dict(spec) if spec else {}
        return f"{spec.get('guide_ref', '?')} → {spec.get('outcome', '?')}"

    def summary(self, doc: Any) -> dict[str, Any] | None:
        spec = getattr(doc, "spec", None) or {}
        if not isinstance(spec, dict):
            spec = dict(spec) if spec else {}
        return {
            "guide_ref": spec.get("guide_ref", ""),
            "outcome": spec.get("outcome", ""),
            "executed_by": spec.get("executed_by", ""),
            "executed_at": spec.get("executed_at"),
            "verifies": spec.get("verifies") or [],
        }


class TestkitExtension:
    name = "testkit"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(TestGuideKind())
        kernel.kind(TestRunKind())

    def kinds(self) -> list[Any]:
        return [TestGuideKind(), TestRunKind()]


__all__ = ["TestGuideKind", "TestRunKind", "TestkitExtension"]
