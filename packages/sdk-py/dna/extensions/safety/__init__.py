"""SafetyPolicyExtension — SafetyPolicy kind (declarative input/output safety enforcement).

SafetyPolicy documents declare enforcement rules in YAML. The runtime applies
them as a tiered pipeline on both input (prompt context) and output (LLM
response). Tier 1 (regex) is built-in; heavier tiers are opt-in via extras.

Storage layout::

    .dna/<module>/safety/<policy-name>/SAFETYPOLICY.md

SAFETYPOLICY.md uses frontmatter for config (scope, action, severity) and
body as a YAML list of rule dicts.
"""
from __future__ import annotations

import yaml
from importlib.resources import files as _pkg_files
from pathlib import Path as _Path
from typing import Any

from dna.kernel.models import TypedSafetyPolicy
from dna.kernel.kinds.base import KindBase
from dna.kernel.preview import PreviewBlock
from dna.kernel.protocols import ExtensionHost, BodyMode, StorageDescriptor
from dna.kernel.compose.templates import Template

from dna.extensions.helix import _schema_from_model


from dna.kernel.studio_ui import docs_ui


class SafetyPolicyKind(KindBase):
    api_version = "github.com/ruinosus/dna/v1"
    kind = "SafetyPolicy"
    alias = "helix-safety-policy"
    is_schema_affecting = True
    ui = docs_ui("SafetyPolicy", mode="govern", label_en="Safety Policies", label_pt="Políticas de Segurança", display_order=50, description_en="Scope safety/PII/content policy.", description_pt="Política de segurança/PII/conteúdo do scope.")
    model = TypedSafetyPolicy
    origin = "github.com/ruinosus/dna/safety"
    storage = StorageDescriptor.bundle(
        "safety", "SAFETYPOLICY.md", body_as=BodyMode.TEXT, body_field="rules"
    )
    graph_style = {"fill": "#DC2626", "stroke": "#B91C1C", "text_color": "#fff"}
    ascii_icon = "\U0001f6e1"  # shield
    display_label = "Safety Policies"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    description_fallback_field = "rules"
    ui_schema = {
        "engine": {
            "widget": "select",
            "label": "Engine",
            "help": "presidio uses Tier-1 regex (built-in); ml-privacy-filter uses the openai/privacy-filter ONNX model — install with `uv sync --extra ml-privacy`.",
            "options": ["presidio", "ml-privacy-filter"],
            "order": 1,
        },
        "scope": {
            "widget": "select",
            "label": "Scope",
            "help": "input guards user prompt context; output guards LLM response; both runs on each side.",
            "options": ["input", "output", "both"],
            "order": 2,
        },
        "action": {
            "widget": "select",
            "label": "Action",
            "help": "mask redacts PII inline; block rejects the message; log passes through with violation metadata.",
            "options": ["mask", "block", "log"],
            "order": 3,
        },
        "severity": {
            "widget": "select",
            "label": "Severity",
            "help": "error fails the turn; warn lets it continue.",
            "options": ["error", "warn"],
            "order": 4,
        },
        "rules": {
            "widget": "code",
            "label": "Rules (YAML)",
            "language": "yaml",
            "help": "YAML list of safety rule objects.",
            "height": 300,
            "order": 5,
        },
        # ML-only fields — meaningful only when engine == "ml-privacy-filter"
        "model": {
            "widget": "input",
            "label": "Model ID",
            "help": "HuggingFace repo id (only used when engine=ml-privacy-filter).",
            "order": 6,
        },
        "backend": {
            "widget": "select",
            "label": "Backend",
            "help": "auto picks ONNX if available; explicit modes fail loud.",
            "options": ["auto", "transformers", "onnxruntime"],
            "order": 7,
        },
        "threshold": {
            "widget": "input",
            "label": "Threshold",
            "help": "Minimum confidence score (0..1) to flag an entity.",
            "order": 8,
        },
        "categories": {
            "widget": "code",
            "label": "Categories (YAML list, null = all 8)",
            "language": "yaml",
            "help": "Subset of T1-locked categories: account_number, private_address, private_email, private_person, private_phone, private_url, private_date, secret.",
            "height": 120,
            "order": 9,
        },
        "mask_char": {
            "widget": "input",
            "label": "Mask string",
            "help": "Replacement string when action=mask.",
            "order": 10,
        },
        "budget_ms": {
            "widget": "input",
            "label": "Budget (ms)",
            "help": "Per-call wall-clock budget; over-budget scans log-and-continue without blocking the turn.",
            "order": 11,
        },
    }
    docs = (
        "A SafetyPolicy declares runtime enforcement rules for input and/or "
        "output. Rules are organized by type (pii, content_safety, "
        "topic_restriction, prompt_injection, banned_words, custom_regex) and "
        "enforced via a tiered scanner pipeline. Tier 1 (regex) is built-in "
        "and handles CPF, CNPJ, email, phone, credit card masking plus prompt "
        "injection heuristics. Higher tiers (ML, API, LLM judge) are opt-in "
        "via pip extras. Actions: mask replaces detected text inline, block "
        "rejects the message entirely, log passes through with violation "
        "metadata attached."
    )

    def dep_filters(self) -> dict[str, str] | None:
        return {"recognizers": "presidio-recognizer"}

    def schema(self) -> dict[str, Any] | None:
        return _schema_from_model(self.model)

    def parse(self, raw: dict[str, Any]) -> Any:
        spec = raw.get("spec", {})
        spec.setdefault("scope", "both")
        spec.setdefault("action", "mask")
        spec.setdefault("severity", "error")

        # The body is stored as TEXT (a string) by the generic reader.
        # Parse it as YAML to get a list of rule dicts.
        body = spec.get("rules", "")
        if isinstance(body, str) and body.strip():
            try:
                parsed = yaml.safe_load(body)
                if isinstance(parsed, list):
                    spec["rules"] = parsed
                else:
                    spec["rules"] = []
            except yaml.YAMLError:
                spec["rules"] = []
        elif not isinstance(body, list):
            spec["rules"] = []

        return TypedSafetyPolicy.from_raw(raw)

    def summary(self, doc: Any) -> dict[str, Any] | None:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        rules = spec_dict.get("rules", [])
        return {
            "scope": spec_dict.get("scope", "both"),
            "action": spec_dict.get("action", "mask"),
            "severity": spec_dict.get("severity", "error"),
            "rules": len(rules) if isinstance(rules, list) else 0,
        }

    def preview(self, doc: Any) -> list[PreviewBlock]:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        blocks: list[PreviewBlock] = []

        meta: list[dict[str, str]] = []
        for field_name in ("scope", "action", "severity"):
            val = spec_dict.get(field_name)
            if isinstance(val, str):
                meta.append({"label": field_name, "value": val})
        if meta:
            blocks.append(PreviewBlock(kind="fields", title="Policy", fields=meta))

        rules = spec_dict.get("rules")
        if isinstance(rules, list) and rules:
            body = yaml.dump(rules, default_flow_style=False, allow_unicode=True)
            blocks.append(
                PreviewBlock(kind="code", title="Rules", body=body, language="yaml")
            )

        if not blocks:
            return [PreviewBlock(kind="empty", title="SafetyPolicy (empty)")]
        return blocks


class SafetyPolicyExtension:
    name = "safety"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(SafetyPolicyKind())

    def templates(self) -> list[Template]:
        """Declare the bundled ``safety/ml-privacy-filter`` scaffold.

        The file tree lives next to this module
        (``extensions/safety/templates/ml-privacy-filter``) and is
        resolved via ``importlib.resources`` so it works in editable
        installs, wheels, and zipapps alike.
        """
        root = _Path(str(_pkg_files("dna.extensions.safety") / "templates"))
        return [
            Template(
                id="safety/ml-privacy-filter",
                label="ML Privacy Filter (openai/privacy-filter)",
                kind="SafetyPolicy",
                description=(
                    "SafetyPolicy that routes context strings through the "
                    "openai/privacy-filter ONNX model (Apache 2.0, 8 entity "
                    "categories). Masks PII in agent input by default; edit "
                    "spec.action to switch to block or log. Requires the "
                    "ml-privacy extras: `cd python-harness && uv sync --extra "
                    "ml-privacy`. The model downloads on first use (~1.5 GB)."
                ),
                files_root=root / "ml-privacy-filter",
                owner_extension="safety",
                post_init_hint=(
                    "Install the harness extras (`uv sync --extra ml-privacy`), "
                    "restart the harness, and open Studio Explorer to view the "
                    "new `pii-ml-filter` SafetyPolicy. The first agent turn "
                    "after install will trigger a one-time model download."
                ),
            )
        ]
