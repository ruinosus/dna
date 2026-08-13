"""HookExtension — Hook kind (declarative hooks in manifest YAML).

Hooks declared as YAML documents are auto-registered on the kernel's
HookRegistry at ``ManifestInstance.apply_hooks()`` time. Supports
middleware (inject_fields, script) and event (log, script) actions.

The registration itself lives HERE, in ``HookExtension.activate_manifest``
(the :class:`~dna.kernel.protocols.ManifestActivator` capability), not in the
kernel: an extension that registers a Kind owns the code that reads that
Kind's schema (i-112, board dna).

Storage layout::

    .dna/<module>/hooks/<hook-name>/HOOK.md

HOOK.md uses frontmatter for metadata + action config, and body for
inject_fields YAML payloads or script code.
"""
from __future__ import annotations

import yaml
from typing import Any

from dna._yaml import safe_load
from dna.extensions.hooks.models import TypedHook
from dna.kernel.kinds.base import KindBase
from dna.kernel.preview import PreviewBlock
from dna.kernel.protocols import ExtensionHost, BodyMode, StorageDescriptor

from dna.extensions.helix import _schema_from_model


from dna.kernel.studio_ui import docs_ui


class HookKind(KindBase):
    # ---- Island, and a LEGITIMATE one (i-119 group C, 06/08/2026) ---------
    # i-119 filed `Hook.target` as "nomeia um Kind" and paired it with
    # `Automation.result_kind` as the two cases that need a vocabulary for
    # "points at the Kind registry". Measured, that reading is wrong, and the
    # code says so in one line: `HookExtension.activate_manifest` below passes
    # this value straight to `kernel.hooks.use(target, ...)` /
    # `kernel.hooks.on(target, ...)`. It is a HOOK POINT — `pre_build_prompt`,
    # `post_save`, `parse_error` — from the kernel's own `HookName` vocabulary
    # (dna/kernel/hooks.py, s-dna-typed-hook-names). The default value is
    # `pre_build_prompt`, which is not the name of any Kind and never was.
    #
    # So this Kind belongs in i-119's group A: it does not point at an
    # instance, and nothing points at it. Declaring `relations` here would be
    # inventing an edge to zero a number, which is the error the taxonomy spec
    # names. Nothing to do, and the reason IS the deliverable.
    #
    # What the field actually is, is a CONTROLLED VOCABULARY token — the same
    # shape as `Lesson.skill` and `Automation.on.hook`, and the same shape
    # i-119's third open item raises for `LayerPolicy.layer_id`. That item asks
    # whether `spec.identifiers` wants a third `role` for "names a dimension of
    # controlled vocabulary". It is worth the founder knowing the item is not
    # one field: it is a family of at least four, and this is one of them.
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
                parsed = safe_load(body)
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


def _field_injector(fields: dict[str, Any]):
    """Middleware that merges a Hook's ``inject_fields`` into the context."""
    def injector(ctx):
        context = ctx.data.get("context", {})
        context.update(fields)
        ctx.data["context"] = context
        return ctx
    return injector


def _event_logger(hook_name: str, target: str):
    """Listener for ``action: log`` — a structured info line per event."""
    def log_event(ctx):
        import logging
        logging.getLogger("dna.hooks").info(
            "[Hook:%s] %s agent=%s scope=%s",
            hook_name, target, ctx.agent, ctx.scope,
        )
    return log_event


def _compile_hook_script(body: Any, hook_name: str):
    """Compile a Hook's ``script`` body into a callable, or ``None``.

    Fail-soft with a warning, unchanged from the kernel version it was moved
    from: one Hook with a typo in its body must not take a whole scope's
    activation down. The ``exec`` is deliberate — a ``script`` Hook IS inline
    Python, and the Kind's own ``docs`` say exactly that.
    """
    if not isinstance(body, str) or not body.strip():
        return None
    try:
        ns: dict[str, Any] = {}
        exec(f"_hook_fn = {body.strip()}", ns)  # noqa: S102
        fn = ns.get("_hook_fn")
        return fn if callable(fn) else None
    except Exception as e:  # noqa: BLE001
        import warnings
        warnings.warn(f"Hook {hook_name}: script compilation failed: {e}")
        return None


class HookExtension:
    name = "hooks"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(HookKind())

    # ── ManifestActivator (i-112, board dna) ────────────────────────────────
    #
    # The body below used to be half of ``ManifestInstance.apply_hooks``, in
    # the KERNEL. The kernel read ``Hook.spec`` field by field — target, type,
    # action, fields, body — ``exec()``d the body and branched on both enums,
    # while THIS class did nothing but ``kernel.kind(...)``: the extension
    # declared the type and the kernel implemented the behaviour.
    #
    # i-112 MOVED it instead of declaring a trait, and that is the point of the
    # issue rather than an implementation detail: a trait would have replaced
    # the string ``"Hook"`` in the kernel and left all five field reads sitting
    # there, making the boundary LOOK fixed. What had to move is the schema
    # knowledge, so the code that reads the schema is what moved.
    #
    # ``HookKind.kind`` rather than the literal ``"Hook"``: the name lives once,
    # on the Kind, and a rename cannot leave this reader behind.

    def activate_manifest(self, mi: Any, kernel: Any) -> None:
        """Register every ``Hook`` instance in *mi* on the kernel's registry."""
        hooks = getattr(kernel, "hooks", None)
        if hooks is None:
            return

        for doc in mi._all(HookKind.kind):
            spec = doc.spec
            target = spec.get("target", "")
            hook_type = spec.get("type", "middleware")
            action = spec.get("action", "inject_fields")
            if not target:
                continue

            if hook_type == "middleware":
                if action == "inject_fields":
                    fields = spec.get("fields", {})
                    if fields:
                        hooks.use(target, _field_injector(dict(fields)))
                elif action == "script":
                    fn = _compile_hook_script(spec.get("body", ""), doc.name)
                    if fn is not None:
                        hooks.use(target, fn)

            elif hook_type == "event":
                if action == "log":
                    hooks.on(target, _event_logger(doc.name, target))
                elif action == "script":
                    fn = _compile_hook_script(spec.get("body", ""), doc.name)
                    if fn is not None:
                        hooks.on(target, fn)
