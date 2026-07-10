"""PromptBuilder — mi.prompt.build() namespace.

Extracts prompt-related logic from ManifestInstance. Both
``mi.build_prompt()`` and ``mi.prompt.build()`` return identical results.
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from dna.kernel._text import strip_prompt_block

if TYPE_CHECKING:
    from dna.kernel.document import Document
    from dna.kernel.instance import ManifestInstance

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Namespace for prompt building — accessed via ``mi.prompt``."""

    def __init__(self, host: ManifestInstance) -> None:
        self._host = host

    def build(
        self,
        agent: str | None = None,
        *,
        context: dict[str, Any] | None = None,
        enabled_skills: list[str] | None = None,
        enabled_guardrails: list[str] | None = None,
        enabled_slots: dict[str, list[str]] | None = None,
    ) -> str:
        """Build system prompt via template cascade.

        Equivalent to ``mi.build_prompt()``.

        Template cascade (highest priority wins):
        1. Agent.spec.promptTemplate -- agent-level override
        2. Kind default template -- registered via prompt_template() on KindPort
        3. Fallback -- agent instruction as plain text

        Agent dep_filters control which kinds appear in the Mustache context.
        flatten_in_context kinds have their spec flattened into context.
        """
        # Resolve agent name
        agent_name = agent
        if not agent_name:
            root = self._host.root
            if root:
                kp = self._host._kinds.get((root.api_version, root.kind))
                if kp:
                    agent_name = kp.get_default_agent_name(root)

        agent_doc = self._find_agent(agent_name) if agent_name else None
        if not agent_doc:
            return f"Agent '{agent_name}' not found"

        # Build context — merge backwards-compat params into enabled_slots
        slots = dict(enabled_slots or {})
        if enabled_skills and "skills" not in slots:
            slots["skills"] = enabled_skills
        if enabled_guardrails and "guardrails" not in slots:
            slots["guardrails"] = enabled_guardrails
        ctx = self._build_context(agent_doc, context, slots)

        # Hook: pre_build_prompt — middleware can modify context
        hooks = self._host._kernel.hooks if self._host._kernel else None
        if hooks and hooks.has("pre_build_prompt"):
            from dna.kernel.hooks import HookContext
            hook_ctx = HookContext(scope=self._host.scope, agent=agent_name, data={"context": ctx})
            hook_ctx = hooks.run_middleware("pre_build_prompt", hook_ctx)
            ctx = hook_ctx.data.get("context", ctx)

        # Render via template cascade
        prompt = self._render_prompt(ctx, agent_doc)

        # Hook: post_build_prompt — event notification
        if hooks and hooks.has("post_build_prompt"):
            from dna.kernel.hooks import HookContext
            hooks.emit("post_build_prompt", HookContext(scope=self._host.scope, agent=agent_name, prompt=prompt))

        return prompt

    async def build_async(
        self,
        agent: str | None = None,
        *,
        context: dict[str, Any] | None = None,
        enabled_skills: list[str] | None = None,
        enabled_guardrails: list[str] | None = None,
        enabled_slots: dict[str, list[str]] | None = None,
    ) -> str:
        """Async variant of :py:meth:`build`.

        Use from inside the harness event loop (graph compilation in
        lifespan, async middleware) so ``self._host.ref_async`` is
        awaited on the caller's loop — keeping the asyncpg pool's
        loop binding intact.
        """
        agent_name = agent
        if not agent_name:
            root = self._host.root
            if root:
                kp = self._host._kinds.get((root.api_version, root.kind))
                if kp:
                    agent_name = kp.get_default_agent_name(root)

        agent_doc = await self._find_agent_async(agent_name) if agent_name else None
        if not agent_doc:
            return f"Agent '{agent_name}' not found"

        slots = dict(enabled_slots or {})
        if enabled_skills and "skills" not in slots:
            slots["skills"] = enabled_skills
        if enabled_guardrails and "guardrails" not in slots:
            slots["guardrails"] = enabled_guardrails
        ctx = await self._build_context_async(agent_doc, context, slots)

        hooks = self._host._kernel.hooks if self._host._kernel else None
        if hooks and hooks.has("pre_build_prompt"):
            from dna.kernel.hooks import HookContext
            hook_ctx = HookContext(scope=self._host.scope, agent=agent_name, data={"context": ctx})
            hook_ctx = hooks.run_middleware("pre_build_prompt", hook_ctx)
            ctx = hook_ctx.data.get("context", ctx)

        prompt = await self._render_prompt_async(ctx, agent_doc)

        if hooks and hooks.has("post_build_prompt"):
            from dna.kernel.hooks import HookContext
            hooks.emit("post_build_prompt", HookContext(scope=self._host.scope, agent=agent_name, prompt=prompt))

        return prompt

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _find_agent(self, name: str) -> Document | None:
        """Find prompt target document by name, preferring highest priority."""
        best: Document | None = None
        best_priority = -1
        for d in self._host.documents:
            kp = self._host._kinds.get((d.api_version, d.kind))
            if kp and kp.is_prompt_target and d.name == name:
                priority = getattr(kp, "prompt_target_priority", 0)
                if priority > best_priority:
                    best = d
                    best_priority = priority
        return best

    async def _find_agent_async(self, name: str) -> Document | None:
        """Async variant of ``_find_agent`` that is safe under lazy MI.

        Walking ``self._host.documents`` from inside a running loop on a
        lazy MI triggers ``_materialize_full`` → ``_run_sync_helper`` →
        strict raise. This variant enumerates registered prompt-target
        kinds and queries each via ``all_async`` (which uses
        ``kernel.query`` end-to-end without re-entering the sync helper).
        """
        best: Document | None = None
        best_priority = -1
        seen_kinds: set[str] = set()
        for kp in self._host._kinds.values():
            if not getattr(kp, "is_prompt_target", False):
                continue
            kind = getattr(kp, "kind", None)
            if not kind or kind in seen_kinds:
                continue
            seen_kinds.add(kind)
            try:
                docs = await self._host.all_async(kind)
            except Exception as e:  # noqa: BLE001
                # fail-soft: read path — a broken Kind is skipped in the
                # prompt-target lookup (logged; the miss surfaces downstream
                # as agent-not-found).
                logger.debug(
                    "prompt target lookup: all_async(%r) failed: %s", kind, e,
                )
                continue
            for d in docs:
                if d.name != name:
                    continue
                priority = getattr(kp, "prompt_target_priority", 0)
                if priority > best_priority:
                    best = d
                    best_priority = priority
        return best

    async def _all_docs_async(self) -> list[Document]:
        """Lazy-MI-safe enumeration of every doc across registered kinds.

        Used by ``_build_context_async`` to replace the sync walk over
        ``self._host.documents`` that breaks on lazy MI inside running
        loop. Order is by kind iteration (not original insertion);
        consumers must not rely on a global ordering.
        """
        out: list[Document] = []
        seen_kinds: set[str] = set()
        for kp in self._host._kinds.values():
            kind = getattr(kp, "kind", None)
            if not kind or kind in seen_kinds:
                continue
            seen_kinds.add(kind)
            try:
                docs = await self._host.all_async(kind)
            except Exception as e:  # noqa: BLE001
                # fail-soft: read path — a broken Kind contributes no docs to
                # the context walk (logged).
                logger.debug(
                    "context walk: all_async(%r) failed: %s", kind, e,
                )
                continue
            out.extend(docs)
        return out

    def _build_context(
        self,
        agent_doc: Document,
        extra: dict[str, Any] | None,
        enabled_slots: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """Build Mustache context from all documents."""
        ctx: dict[str, Any] = {}

        # Root metadata + spec
        root = self._host.root
        if root:
            ctx["metadata"] = dict(root.metadata)
            ctx["spec"] = dict(root.spec)

        # Agent entry
        agent_spec = agent_doc.spec
        instruction_ref = agent_spec.get("instruction", "")
        ctx["agent"] = {
            "name": agent_doc.name,
            "description": _get_description(agent_doc),
            # strip_prompt_block: composition-only trailing-whitespace
            # normalization (i-013) — storage stays byte-faithful.
            "instruction": (
                strip_prompt_block(self._host.ref(instruction_ref))
                if instruction_ref
                else ""
            ),
        }
        ctx["agentId"] = agent_doc.name

        # All documents grouped by alias (for Mustache sections)
        for doc in self._host.documents:
            kp = self._host._kinds.get((doc.api_version, doc.kind))
            if not kp:
                continue
            alias = kp.alias
            lst = ctx.setdefault(alias, [])

            entry: dict[str, Any] = {
                "name": doc.name,
                "description": _get_description(doc),
            }
            spec = doc.spec
            for k, v in spec.items():
                entry[k] = self._host.ref(v) if isinstance(v, str) else v
            lst.append(entry)

        # Dep filtering: agent's dep_filters restrict which docs appear per alias
        agent_kp = self._host._kinds.get((agent_doc.api_version, agent_doc.kind))
        if agent_kp:
            filters = agent_kp.dep_filters()
            if filters:
                for spec_field, target_alias in filters.items():
                    if target_alias not in ctx:
                        continue
                    declared = agent_spec.get(spec_field)
                    if declared is None:
                        ctx[target_alias] = []
                        continue
                    if not declared:
                        ctx[target_alias] = []
                        continue
                    if isinstance(declared, str):
                        ctx[target_alias] = [e for e in ctx[target_alias] if e.get("name") == declared]
                    elif isinstance(declared, list):
                        ctx[target_alias] = [e for e in ctx[target_alias] if e.get("name") in declared]

        # Generic slot filtering: caller restricts which docs appear per slot.
        if agent_kp and enabled_slots:
            filters = agent_kp.dep_filters()
            if filters:
                for slot_name, enabled_names in enabled_slots.items():
                    alias = filters.get(slot_name)
                    if alias and alias in ctx:
                        ctx[alias] = [e for e in ctx[alias] if e.get("name") in enabled_names]

        # Flatten: kinds with flatten_in_context have their spec entries merged into ctx.
        # String values (soul_content, agents_content, ...) get trailing
        # whitespace normalized — the template supplies the joiners (i-013).
        _reserved = {"agent", "metadata", "spec", "agentId"}
        for doc in self._host.documents:
            kp = self._host._kinds.get((doc.api_version, doc.kind))
            if not kp or not kp.flatten_in_context:
                continue
            spec = doc.spec
            for k, v in spec.items():
                if v is not None and k not in _reserved:
                    ctx[k] = (
                        strip_prompt_block(self._host.ref(v))
                        if isinstance(v, str)
                        else v
                    )

        # Extra context from caller
        if extra:
            ctx.update(extra)

        return ctx

    def _render_prompt(self, ctx: dict[str, Any], agent_doc: Document) -> str:
        """Render prompt via template cascade."""
        # 1. Agent-level template override
        agent_spec = agent_doc.spec
        agent_template = agent_spec.get("promptTemplate") or agent_spec.get("prompt_template")
        if agent_template:
            return self._mustache_render(agent_template, ctx)

        # 2. Kind default template
        agent_kp = self._host._kinds.get((agent_doc.api_version, agent_doc.kind))
        if agent_kp:
            kind_template = agent_kp.prompt_template()
            if kind_template:
                return self._mustache_render(kind_template, ctx)

        # 3. Fallback: agent instruction as plain text
        return ctx.get("agent", {}).get("instruction", "")

    async def _build_context_async(
        self,
        agent_doc: Document,
        extra: dict[str, Any] | None,
        enabled_slots: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """Async variant of :py:meth:`_build_context`.

        All ``self._host.ref(...)`` calls become awaits. Same Mustache
        context shape; only the I/O dispatch changes — coros are
        awaited on the caller's loop.
        """
        ctx: dict[str, Any] = {}

        root = self._host.root
        if root:
            ctx["metadata"] = dict(root.metadata)
            ctx["spec"] = dict(root.spec)

        agent_spec = agent_doc.spec
        instruction_ref = agent_spec.get("instruction", "")
        ctx["agent"] = {
            "name": agent_doc.name,
            "description": _get_description(agent_doc),
            # strip_prompt_block: composition-only normalization (i-013).
            "instruction": (
                strip_prompt_block(await self._host.ref_async(instruction_ref))
                if instruction_ref
                else ""
            ),
        }
        ctx["agentId"] = agent_doc.name

        all_docs = await self._all_docs_async()
        for doc in all_docs:
            kp = self._host._kinds.get((doc.api_version, doc.kind))
            if not kp:
                continue
            alias = kp.alias
            lst = ctx.setdefault(alias, [])

            entry: dict[str, Any] = {
                "name": doc.name,
                "description": _get_description(doc),
            }
            spec = doc.spec
            for k, v in spec.items():
                entry[k] = (
                    await self._host.ref_async(v) if isinstance(v, str) else v
                )
            lst.append(entry)

        agent_kp = self._host._kinds.get((agent_doc.api_version, agent_doc.kind))
        if agent_kp:
            filters = agent_kp.dep_filters()
            if filters:
                for spec_field, target_alias in filters.items():
                    if target_alias not in ctx:
                        continue
                    declared = agent_spec.get(spec_field)
                    if declared is None:
                        ctx[target_alias] = []
                        continue
                    if not declared:
                        ctx[target_alias] = []
                        continue
                    if isinstance(declared, str):
                        ctx[target_alias] = [e for e in ctx[target_alias] if e.get("name") == declared]
                    elif isinstance(declared, list):
                        ctx[target_alias] = [e for e in ctx[target_alias] if e.get("name") in declared]

        if agent_kp and enabled_slots:
            filters = agent_kp.dep_filters()
            if filters:
                for slot_name, enabled_names in enabled_slots.items():
                    alias = filters.get(slot_name)
                    if alias and alias in ctx:
                        ctx[alias] = [e for e in ctx[alias] if e.get("name") in enabled_names]

        _reserved = {"agent", "metadata", "spec", "agentId"}
        for doc in all_docs:
            kp = self._host._kinds.get((doc.api_version, doc.kind))
            if not kp or not kp.flatten_in_context:
                continue
            spec = doc.spec
            for k, v in spec.items():
                if v is not None and k not in _reserved:
                    ctx[k] = (
                        strip_prompt_block(await self._host.ref_async(v))
                        if isinstance(v, str)
                        else v
                    )

        if extra:
            ctx.update(extra)

        return ctx

    async def _render_prompt_async(
        self, ctx: dict[str, Any], agent_doc: Document,
    ) -> str:
        """Async variant of :py:meth:`_render_prompt`.

        Only the path that loads a template via ``self._host.ref(...)``
        differs — the Mustache rendering itself is pure-CPU.
        """
        agent_spec = agent_doc.spec
        agent_template = agent_spec.get("promptTemplate") or agent_spec.get("prompt_template")
        if agent_template:
            return await self._mustache_render_async(agent_template, ctx)

        agent_kp = self._host._kinds.get((agent_doc.api_version, agent_doc.kind))
        if agent_kp:
            kind_template = agent_kp.prompt_template()
            if kind_template:
                return await self._mustache_render_async(kind_template, ctx)

        return ctx.get("agent", {}).get("instruction", "")

    async def _mustache_render_async(
        self, template: str, ctx: dict[str, Any],
    ) -> str:
        """Async variant of :py:meth:`_mustache_render`."""
        if "/" in template or template.endswith((".mustache", ".md")):
            template = await self._host.ref_async(template)

        try:
            import chevron
            first_pass = chevron.render(template, ctx)
            return chevron.render(first_pass, ctx)
        except ImportError:
            result = template
            for key, value in ctx.items():
                if isinstance(value, str):
                    result = result.replace("{{" + key + "}}", value)
                elif isinstance(value, dict) and "instruction" in value:
                    result = result.replace("{{" + key + ".instruction}}", value["instruction"])
            return result

    def _mustache_render(self, template: str, ctx: dict[str, Any]) -> str:
        """Render a Mustache template. Double render for refs inside content."""
        if "/" in template or template.endswith((".mustache", ".md")):
            template = self._host.ref(template)

        try:
            import chevron
            first_pass = chevron.render(template, ctx)
            return chevron.render(first_pass, ctx)
        except ImportError:
            result = template
            for key, value in ctx.items():
                if isinstance(value, str):
                    result = result.replace("{{" + key + "}}", value)
                elif isinstance(value, dict) and "instruction" in value:
                    result = result.replace("{{" + key + ".instruction}}", value["instruction"])
            return result


def _get_description(doc: Document) -> str:
    return doc.metadata.get("description", "")
