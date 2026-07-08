"""RecognizerExtension — Recognizer kind (Presidio ad-hoc recognizer).

Declares PII detection patterns as manifest documents. Recognizers are
referenced by SafetyPolicy documents via dep_filters and exported to
LiteLLM/Presidio at runtime.

Storage layout::

    .dna/<module>/recognizers/<recognizer-name>/RECOGNIZER.md

RECOGNIZER.md uses frontmatter for metadata (name, description, entity_type,
language, deny_list, context) and body as a YAML list of pattern objects.
"""
from __future__ import annotations

import yaml
from typing import Any

from dna.kernel.models import TypedRecognizer
from dna.kernel.kind_base import KindBase
from dna.kernel.preview import PreviewBlock
from dna.kernel.protocols import BodyMode, StorageDescriptor

from dna.extensions.helix import _schema_from_model


from dna.kernel.studio_ui import docs_ui


class RecognizerKind(KindBase):
    api_version = "presidio/v1"
    kind = "Recognizer"
    alias = "presidio-recognizer"
    is_schema_affecting = True
    ui = docs_ui("Recognizer", mode="govern", label_en="Recognizers", label_pt="Reconhecedores", display_order=51, description_en="Custom PII recognizer (Presidio).", description_pt="Reconhecedor de PII (Presidio) customizado.")
    model = TypedRecognizer
    origin = "microsoft.github.io/presidio"
    storage = StorageDescriptor.bundle(
        "recognizers", "RECOGNIZER.md", body_as=BodyMode.TEXT, body_field="patterns"
    )
    graph_style = {"fill": "#6366F1", "stroke": "#4F46E5", "text_color": "#fff"}
    ascii_icon = "\U0001f50d"  # magnifying glass
    display_label = "Recognizers"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    description_fallback_field = "entity_type"
    ui_schema = {
        "entity_type": {
            "widget": "input",
            "label": "Entity Type",
            "help": "Presidio entity name, e.g. BR_CPF, BR_CNPJ",
            "order": 1,
        },
        "language": {
            "widget": "select",
            "options": ["en", "pt", "es", "de", "fr"],
            "label": "Language",
            "order": 2,
        },
        "patterns": {
            "widget": "code",
            "language": "yaml",
            "label": "Patterns",
            "help": "List of {name, regex, score} objects",
            "height": 200,
            "order": 3,
        },
        "deny_list": {
            "widget": "tags",
            "label": "Deny List",
            "help": "Words that always match this entity",
            "order": 4,
        },
        "context": {
            "widget": "tags",
            "label": "Context Words",
            "help": "Words near the entity that boost confidence",
            "order": 5,
        },
    }
    docs = (
        "A Recognizer is a Presidio ad-hoc recognizer that detects PII "
        "entities using regex patterns or deny lists. Recognizers are "
        "referenced by SafetyPolicy documents and exported to "
        "LiteLLM/Presidio at runtime."
    )

    def schema(self) -> dict[str, Any] | None:
        return _schema_from_model(self.model)

    def parse(self, raw: dict[str, Any]) -> Any:
        spec = raw.get("spec", {})
        spec.setdefault("entity_type", "")
        spec.setdefault("language", "en")

        # The body is stored as LIST by the generic reader.
        # Parse it as YAML to get a list of pattern dicts.
        body = spec.get("patterns", "")
        if isinstance(body, str) and body.strip():
            try:
                parsed = yaml.safe_load(body)
                if isinstance(parsed, list):
                    spec["patterns"] = parsed
                else:
                    spec["patterns"] = []
            except yaml.YAMLError:
                spec["patterns"] = []
        elif not isinstance(body, list):
            spec["patterns"] = []

        if not isinstance(spec.get("deny_list"), list):
            spec["deny_list"] = []
        if not isinstance(spec.get("context"), list):
            spec["context"] = []

        return TypedRecognizer.from_raw(raw)

    def summary(self, doc: Any) -> dict[str, Any] | None:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        patterns = spec_dict.get("patterns", [])
        return {
            "entity_type": spec_dict.get("entity_type", ""),
            "language": spec_dict.get("language", "en"),
            "patterns": len(patterns) if isinstance(patterns, list) else 0,
            "deny_list": len(spec_dict.get("deny_list", [])) if isinstance(spec_dict.get("deny_list"), list) else 0,
        }

    def preview(self, doc: Any) -> list[PreviewBlock]:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        blocks: list[PreviewBlock] = []

        meta: list[dict[str, str]] = []
        for field_name in ("entity_type", "language"):
            val = spec_dict.get(field_name)
            if isinstance(val, str):
                meta.append({"label": field_name, "value": val})
        if meta:
            blocks.append(PreviewBlock(kind="fields", title="Recognizer", fields=meta))

        patterns = spec_dict.get("patterns")
        if isinstance(patterns, list) and patterns:
            body = yaml.dump(patterns, default_flow_style=False, allow_unicode=True)
            blocks.append(
                PreviewBlock(kind="code", title="Patterns", body=body, language="yaml")
            )

        deny_list = spec_dict.get("deny_list")
        if isinstance(deny_list, list) and deny_list:
            blocks.append(
                PreviewBlock(kind="code", title="Deny List", body=", ".join(deny_list), language="text")
            )

        context = spec_dict.get("context")
        if isinstance(context, list) and context:
            blocks.append(
                PreviewBlock(kind="code", title="Context Words", body=", ".join(context), language="text")
            )

        if not blocks:
            return [PreviewBlock(kind="empty", title="Recognizer (empty)")]
        return blocks


class RecognizerExtension:
    name = "recognizer"
    version = "1.0.0"

    def register(self, kernel: Any) -> None:
        kernel.kind(RecognizerKind())
