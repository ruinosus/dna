"""HookExtension — Hook kind (declarative hooks in manifest YAML).

Hooks declared as YAML documents are auto-registered on the kernel's
HookRegistry at ``ManifestInstance.apply_hooks()`` time. Supports
middleware (inject_fields, script) and event (log, script) actions.

Storage layout::

    .dna/<module>/hooks/<hook-name>/HOOK.md

HOOK.md uses frontmatter for metadata + action config, and body for
inject_fields YAML payloads or script code.
"""
from __future__ import annotations

import yaml
from typing import Any

from dna.kernel.models import TypedHook
from dna.kernel.kind_base import KindBase
from dna.kernel.preview import PreviewBlock
from dna.kernel.protocols import ExtensionHost, BodyMode, StorageDescriptor

from dna.extensions.helix import _schema_from_model


from dna.kernel.studio_ui import docs_ui


class HookKind(KindBase):
    api_version = "github.com/ruinosus/dna/v1"
    kind = "Hook"
    alias = "helix-hook"
    is_schema_affecting = True
    ui = docs_ui("Hook", mode="build", label_en="Hooks", label_pt="Hooks", display_order=52, description_en="Lifecycle hooks run on kernel events.", description_pt="Hooks de ciclo de vida executados em eventos do kernel.")
    model = TypedHook
    origin = "github.com/ruinosus/dna/hooks"
    storage = StorageDescriptor.bundle("hooks", "HOOK.md", body_as=BodyMode.TEXT, body_field="body")
    graph_style = {"fill": "#8B5CF6", "stroke": "#7C3AED", "text_color": "#fff"}
    ascii_icon = "\u2693"
    display_label = "Hooks"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    description_fallback_field = "body"
    ui_schema = {
        "target": {
            "widget": "select",
            "label": "Target Hook",
            "help": "Lifecycle hook point (e.g. pre_build_prompt, post_build_prompt).",
            "order": 10,
        },
        "type": {
            "widget": "select",
            "label": "Type",
            "help": "middleware intercepts data flow; event is fire-and-forget.",
            "order": 20,
        },
        "action": {
            "widget": "select",
            "label": "Action",
            "help": "inject_fields merges YAML body into context; log emits info; script runs code.",
            "order": 30,
        },
        "body": {
            "widget": "markdown",
            "label": "HOOK.md",
            "help": "Body: YAML fields for inject_fields, or Python code for script action.",
            "height": 280,
            "order": 40,
        },
    }
    docs = (
        "A Hook is a declarative lifecycle interceptor. It attaches to a "
        "kernel hook point (e.g. pre_build_prompt) and runs an action: "
        "inject_fields merges YAML key-value pairs into the prompt context, "
        "log emits a structured info message, and script executes inline "
        "Python code. Hooks are stored in HOOK.md bundles and are "
        "auto-registered when ManifestInstance.apply_hooks() is called."
    )

    def schema(self) -> dict[str, Any] | None:
        return _schema_from_model(self.model)

    def parse(self, raw: dict[str, Any]) -> Any:
        spec = raw.get("spec", {})
        spec.setdefault("target", "pre_build_prompt")
        spec.setdefault("type", "middleware")
        spec.setdefault("action", "inject_fields")

        # For inject_fields, parse the body as YAML into spec.fields
        action = spec.get("action", "inject_fields")
        body = spec.get("body", "").strip()
        if action == "inject_fields" and body and not spec.get("fields"):
            try:
                parsed = yaml.safe_load(body)
                if isinstance(parsed, dict):
                    spec["fields"] = parsed
            except yaml.YAMLError:
                pass  # Leave fields empty if body isn't valid YAML

        return TypedHook.from_raw(raw)

    def summary(self, doc: Any) -> dict[str, Any] | None:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        return {
            "target": spec_dict.get("target", "pre_build_prompt"),
            "type": spec_dict.get("type", "middleware"),
            "action": spec_dict.get("action", "inject_fields"),
        }

    def preview(self, doc: Any) -> list[PreviewBlock]:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        blocks: list[PreviewBlock] = []

        body = spec_dict.get("body")
        if isinstance(body, str) and body.strip():
            blocks.append(
                PreviewBlock(kind="markdown", title="HOOK.md", body=body)
            )

        meta: list[dict[str, str]] = []
        target = spec_dict.get("target")
        if isinstance(target, str):
            meta.append({"label": "target", "value": target})
        hook_type = spec_dict.get("type")
        if isinstance(hook_type, str):
            meta.append({"label": "type", "value": hook_type})
        action = spec_dict.get("action")
        if isinstance(action, str):
            meta.append({"label": "action", "value": action})
        if meta:
            blocks.append(PreviewBlock(kind="fields", title="Config", fields=meta))

        fields = spec_dict.get("fields")
        if isinstance(fields, dict) and fields:
            import json
            blocks.append(
                PreviewBlock(
                    kind="code",
                    title="Injected Fields",
                    body=json.dumps(fields, indent=2, default=str),
                    language="json",
                )
            )

        if not blocks:
            return [PreviewBlock(kind="empty", title="Hook (empty)")]
        return blocks


class HookExtension:
    name = "hooks"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(HookKind())
