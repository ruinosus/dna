"""GuardrailExtension — Guardrail kind (reader/writer handled by generic machinery)."""
from __future__ import annotations

from typing import Any

from dna.kernel.models import TypedGuardrail
from dna.kernel.kinds.base import KindBase
from dna.kernel.preview import PreviewBlock
from dna.kernel.protocols import ExtensionHost, BodyMode, StorageDescriptor

from dna.extensions.helix import _schema_from_model

_DEFAULT_SEVERITY = "warn"
_DEFAULT_SCOPE = "both"


from dna.kernel.studio_ui import docs_ui


class GuardrailKind(KindBase):
    api_version = "github.com/ruinosus/dna/v1"
    kind = "Guardrail"
    alias = "guardrails-guardrail"
    is_schema_affecting = True
    ui = docs_ui("Guardrail", mode="build", label_en="Guardrails", label_pt="Guardrails", display_order=51, description_en="Safety/policy rules enforced on agents.", description_pt="Regras de segurança/política aplicadas a agentes.")
    model = TypedGuardrail
    origin = "github.com/ruinosus/dna/guardrails"
    storage = StorageDescriptor.bundle("guardrails", "GUARDRAIL.md", body_as=BodyMode.LIST, body_field="rules")
    graph_style = {"fill": "#EF4444", "stroke": "#DC2626", "text_color": "#fff"}
    ascii_icon = "🛡️"
    display_label = "Guardrails"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    description_fallback_field = "instruction"
    ui_schema = {
        "instruction": {
            "widget": "markdown",
            "label": "GUARDRAIL.md",
            "help": "Prose body explaining the intent behind the rule set.",
            "height": 280,
            "order": 10,
        },
        "rules": {
            "widget": "list-markdown",
            "label": "Rules",
            "help": "Individual directives the agent must follow every turn.",
            "order": 20,
        },
        "severity": {
            "widget": "select",
            "label": "Severity",
            "help": "warn lets the turn continue; error fails the turn; hard refuses to answer.",
            "order": 30,
        },
        "scope": {
            "widget": "select",
            "label": "Scope",
            "help": "input guards the user prompt; output guards the agent response; both runs on each side.",
            "order": 40,
        },
    }
    docs = (
        "A Guardrail is a safety or compliance rule set that shapes what an "
        "agent may produce. It has a severity (warn | error | hard) indicating "
        "how strictly the rule must be enforced, and a scope (input | output | "
        "both) indicating which side of the model call it applies to. Rules "
        "are declared as a markdown list of directives in GUARDRAIL.md. "
        "Guardrails are referenced by an agent's dep_filters and flattened "
        "into the system prompt so the model sees them on every turn. Use a "
        "Guardrail for hard constraints like 'never leak PII' or 'refuse "
        "destructive commands without confirmation'."
    )

    # Validate the spec against schema() on read/compose (not only on write) —
    # a doc with e.g. ``severity: critical`` surfaces as a fail-soft parse_error
    # instead of silently composing (i-validation-shallow). Parity: the TS twin
    # rejects on parse via GuardrailSchema (z.enum).
    validate_on_parse = True

    def schema(self) -> dict[str, Any] | None:
        return _schema_from_model(self.model)

    def parse(self, raw: dict[str, Any]) -> Any:
        spec = raw.get("spec", {})
        spec.setdefault("severity", _DEFAULT_SEVERITY)
        spec.setdefault("scope", _DEFAULT_SCOPE)
        # Enforce the schema (enum-constrained severity/scope) on parse. Mirrors
        # the TS GuardrailSchema.parse throw; the kernel's _parse_doc catches it
        # → typed=None + parse_error event (the doc still loads, untyped).
        self._validate_spec(raw)
        return TypedGuardrail.from_raw(raw)

    def summary(self, doc: Any) -> dict[str, Any] | None:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        return {
            "severity": spec_dict.get("severity", "warn"),
            "scope": spec_dict.get("scope", "both"),
            "rules": (
                len(spec_dict.get("rules", []))
                if isinstance(spec_dict.get("rules"), list)
                else 0
            ),
        }

    def preview(self, doc: Any) -> list[PreviewBlock]:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        blocks: list[PreviewBlock] = []

        instruction = spec_dict.get("instruction")
        if isinstance(instruction, str) and instruction:
            blocks.append(
                PreviewBlock(kind="markdown", title="GUARDRAIL.md", body=instruction)
            )

        rules = spec_dict.get("rules")
        if isinstance(rules, list) and rules:
            body = "\n".join(
                f"- {r if isinstance(r, str) else str(r)}" for r in rules
            )
            blocks.append(PreviewBlock(kind="markdown", title="Rules", body=body))

        meta: list[dict[str, str]] = []
        severity = spec_dict.get("severity")
        if isinstance(severity, str):
            meta.append({"label": "severity", "value": severity})
        scope = spec_dict.get("scope")
        if isinstance(scope, str):
            meta.append({"label": "scope", "value": scope})
        if meta:
            blocks.append(PreviewBlock(kind="fields", title="Policy", fields=meta))

        if not blocks:
            return [PreviewBlock(kind="empty", title="Guardrail (empty)")]
        return blocks


class GuardrailExtension:
    name = "guardrails"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(GuardrailKind())
        # Layer 3 (spec-kit adoption): the constitution Guardrail becomes a
        # LIVE, no-deploy, overridable write-time gate. Registered as a pre_save
        # veto so flipping the constitution's severity enforces on the next
        # write with zero redeploy.
        from dna.extensions.guardrails.write_guards import register_constitution_guard
        register_constitution_guard(kernel)
