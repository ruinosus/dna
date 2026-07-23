"""PromptBuilder — mi.prompt.build() namespace.

Extracts prompt-related logic from ManifestInstance. Both
``mi.build_prompt()`` and ``mi.prompt.build()`` return identical results.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from dna.kernel._text import strip_prompt_block
from dna.kernel.errors import AgentNotFound, UnknownLayout

if TYPE_CHECKING:
    from dna.kernel.document import Document
    from dna.kernel.instance import ManifestInstance

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Explain mode — per-section prompt provenance (s-dna-explain-provenance)
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class SectionProvenance:
    """Provenance for ONE composed prompt section.

    A "section" is a declared composition input the layout renders: the
    agent's own instruction, its Soul, each referenced Skill, each
    Guardrail. Attribution is reconstructed from the kernel's OWN declared
    blocks (layout template + dep_filters + flatten_in_context) and the
    layer provenance the kernel already returns from ``resolve_document`` —
    NOT by re-running composition.
    """

    #: Human label, e.g. ``instruction`` / ``soul:expert`` / ``skill:tdd``.
    section: str
    #: The contributing Kind (``Agent`` / ``Soul`` / ``Skill`` / ``Guardrail``).
    kind: str
    #: The contributing document name.
    name: str
    #: Canonical source artifact path, e.g. ``skills/tdd/SKILL.md`` (or ``?``).
    source: str
    #: SHA-256 of the resolved raw doc (full hex; the CLI shows a short form).
    hash: str | None
    #: ``metadata.version`` of the resolved doc, when the author set one.
    version: str | None
    #: Effective layer the section resolved from — the scope that won.
    origin: str
    #: True when ``origin`` is a DIFFERENT scope than the requested one
    #: (the section is inherited from a parent/library scope).
    is_inherited: bool
    #: True when a TENANT overlay layer contributed to the resolved doc —
    #: the CLI stamps ``OVERRIDDEN by tenant overlay`` on these rows.
    overridden_by_tenant: bool

    def serialize(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "kind": self.kind,
            "name": self.name,
            "source": self.source,
            "hash": self.hash,
            "version": self.version,
            "origin": self.origin,
            "is_inherited": self.is_inherited,
            "overridden_by_tenant": self.overridden_by_tenant,
        }


@dataclass
class PromptExplanation:
    """The composed prompt PLUS a section→provenance map.

    ``prompt`` is BYTE-IDENTICAL to ``build_prompt`` — explain mode delegates
    the string rendering to the exact same composition path, so the flat
    prompt can never drift from the explained one.
    """

    prompt: str
    sections: list[SectionProvenance] = field(default_factory=list)

    def serialize(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "sections": [s.serialize() for s in self.sections],
        }


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
            # Fail loud (s-dx-build-prompt-fail-loud): raising a typed error
            # instead of returning a placeholder string means a missing/renamed
            # agent can never silently become the literal instruction.
            raise AgentNotFound(agent_name)

        # Build context — merge backwards-compat params into enabled_slots.
        # An explicit empty list means "disable all", ONLY None means "no
        # filter" — guarding on truthiness would treat ``[]`` as unset and leak
        # every skill/guardrail into the prompt. Latent while skills didn't
        # compose; load-bearing after i-031 (skills now inline).
        slots = dict(enabled_slots or {})
        if enabled_skills is not None and "skills" not in slots:
            slots["skills"] = enabled_skills
        if enabled_guardrails is not None and "guardrails" not in slots:
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

        # Clean output (s-dx-clean-composition-output): template sections can
        # pad the composed prompt with trailing newlines; consumers used to
        # ``.rstrip("\n")`` themselves. Return it already clean so nobody has to.
        return prompt.rstrip("\n")

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
            # Fail loud (s-dx-build-prompt-fail-loud) — see build().
            raise AgentNotFound(agent_name)

        # See build(): [] means "disable all", only None means "no filter".
        slots = dict(enabled_slots or {})
        if enabled_skills is not None and "skills" not in slots:
            slots["skills"] = enabled_skills
        if enabled_guardrails is not None and "guardrails" not in slots:
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

        # Clean output (s-dx-clean-composition-output) — see build().
        return prompt.rstrip("\n")

    # -------------------------------------------------------------------------
    # Explain mode — per-section provenance (s-dna-explain-provenance)
    # -------------------------------------------------------------------------

    def explain(
        self,
        agent: str | None = None,
        *,
        context: dict[str, Any] | None = None,
        enabled_skills: list[str] | None = None,
        enabled_guardrails: list[str] | None = None,
        enabled_slots: dict[str, list[str]] | None = None,
        tenant: str | None = None,
    ) -> PromptExplanation:
        """Compose ``agent`` AND return per-section provenance.

        Returns a :class:`PromptExplanation` — the composed prompt plus a
        section→provenance map (source artifact, content hash, version, and
        the layer/overlay origin of each declared composition input).

        The ``prompt`` is produced by the SAME :meth:`build` path, so it is
        byte-identical to ``build_prompt`` by construction — explain mode
        never re-renders. Provenance is reconstructed from the kernel's own
        declared blocks (layout template + dep_filters + flatten_in_context)
        + the layer provenance ``kernel.resolve_document`` already returns.
        """
        # Prompt = the ONE canonical composition (byte-equal gate: same path).
        prompt = self.build(
            agent,
            context=context,
            enabled_skills=enabled_skills,
            enabled_guardrails=enabled_guardrails,
            enabled_slots=enabled_slots,
        )

        agent_name = agent or self._default_agent_name()
        agent_doc = self._find_agent(agent_name) if agent_name else None
        if not agent_doc:
            raise AgentNotFound(agent_name)

        slots = self._merge_slots(enabled_skills, enabled_guardrails, enabled_slots)
        template = self._effective_template(agent_doc)
        specs = self._section_specs(agent_doc, template, slots)

        sections: list[SectionProvenance] = []
        for section_label, kp, doc_name in specs:
            base = self._resolve_sync(kp.kind, doc_name, None)
            effective = (
                self._resolve_sync(kp.kind, doc_name, tenant)
                if tenant else base
            )
            sections.append(self._section_provenance(
                section_label, kp, doc_name, effective, base, tenant,
            ))
        return PromptExplanation(prompt=prompt, sections=sections)

    async def explain_async(
        self,
        agent: str | None = None,
        *,
        context: dict[str, Any] | None = None,
        enabled_skills: list[str] | None = None,
        enabled_guardrails: list[str] | None = None,
        enabled_slots: dict[str, list[str]] | None = None,
        tenant: str | None = None,
    ) -> PromptExplanation:
        """Async variant of :meth:`explain` (byte-equal to ``build_async``)."""
        prompt = await self.build_async(
            agent,
            context=context,
            enabled_skills=enabled_skills,
            enabled_guardrails=enabled_guardrails,
            enabled_slots=enabled_slots,
        )
        agent_name = agent or self._default_agent_name()
        agent_doc = await self._find_agent_async(agent_name) if agent_name else None
        if not agent_doc:
            raise AgentNotFound(agent_name)

        slots = self._merge_slots(enabled_skills, enabled_guardrails, enabled_slots)
        template = await self._effective_template_async(agent_doc)
        specs = self._section_specs(agent_doc, template, slots)

        sections: list[SectionProvenance] = []
        for section_label, kp, doc_name in specs:
            base = await self._resolve_async(kp.kind, doc_name, None)
            effective = (
                await self._resolve_async(kp.kind, doc_name, tenant)
                if tenant else base
            )
            sections.append(self._section_provenance(
                section_label, kp, doc_name, effective, base, tenant,
            ))
        return PromptExplanation(prompt=prompt, sections=sections)

    async def _resolve_async(self, kind: str, name: str, tenant: str | None) -> Any | None:
        kernel = self._host._kernel
        if kernel is None:
            return None
        try:
            return await kernel.resolve_document(
                self._host.scope, kind, name, tenant=tenant,
            )
        except Exception as e:  # noqa: BLE001 — read path, fail-soft
            logger.debug("explain: resolve_document(%s/%s) failed: %s", kind, name, e)
            return None

    # ── explain helpers ──────────────────────────────────────────────────

    def _default_agent_name(self) -> str | None:
        root = self._host.root
        if root:
            kp = self._host._kinds.get((root.api_version, root.kind))
            if kp:
                return kp.get_default_agent_name(root)
        return None

    @staticmethod
    def _merge_slots(
        enabled_skills: list[str] | None,
        enabled_guardrails: list[str] | None,
        enabled_slots: dict[str, list[str]] | None,
    ) -> dict[str, list[str]]:
        slots = dict(enabled_slots or {})
        if enabled_skills is not None and "skills" not in slots:
            slots["skills"] = enabled_skills
        if enabled_guardrails is not None and "guardrails" not in slots:
            slots["guardrails"] = enabled_guardrails
        return slots

    def _effective_template(self, agent_doc: Document) -> str:
        """The template string the cascade will render (see _render_prompt).

        Resolves a file-ref template so section detection sees the final
        Mustache body. Empty string if no template resolves (plain-text
        fallback — only the instruction section then).
        """
        spec = agent_doc.spec
        tmpl = spec.get("promptTemplate") or spec.get("prompt_template")
        agent_kp = self._host._kinds.get((agent_doc.api_version, agent_doc.kind))
        if not tmpl:
            layout = spec.get("layout")
            if layout and agent_kp is not None:
                tmpl = agent_kp.layout_template(layout)
            elif agent_kp is not None:
                tmpl = agent_kp.prompt_template()
        if not tmpl:
            return ""
        if "/" in tmpl or tmpl.endswith((".mustache", ".md")):
            tmpl = self._host.ref(tmpl)
        return tmpl or ""

    async def _effective_template_async(self, agent_doc: Document) -> str:
        spec = agent_doc.spec
        tmpl = spec.get("promptTemplate") or spec.get("prompt_template")
        agent_kp = self._host._kinds.get((agent_doc.api_version, agent_doc.kind))
        if not tmpl:
            layout = spec.get("layout")
            if layout and agent_kp is not None:
                tmpl = agent_kp.layout_template(layout)
            elif agent_kp is not None:
                tmpl = agent_kp.prompt_template()
        if not tmpl:
            return ""
        if "/" in tmpl or tmpl.endswith((".mustache", ".md")):
            tmpl = await self._host.ref_async(tmpl)
        return tmpl or ""

    def _kp_by_alias(self, alias: str) -> Any | None:
        for kp in self._host._kinds.values():
            if getattr(kp, "alias", None) == alias:
                return kp
        return None

    def _section_specs(
        self, agent_doc: Document, template: str, enabled_slots: dict[str, list[str]],
    ) -> list[tuple[str, Any, str]]:
        """Reconstruct the ordered composition inputs → ``(label, kp, name)``.

        PURE (no I/O beyond reading already-loaded docs). A dep_filter field
        contributes a section iff the layout actually renders it — a flatten
        Kind whose flatten var appears in the template (Soul → soul_content)
        or a Kind whose alias appears as a Mustache section (Skill/Guardrail).
        Non-prompt deps (tools, actors) fall out because the template never
        references them.
        """
        specs: list[tuple[str, Any, str]] = []
        agent_kp = self._host._kinds.get((agent_doc.api_version, agent_doc.kind))

        # The agent's own instruction always leads ({{{agent.instruction}}}).
        specs.append(("instruction", agent_kp, agent_doc.name))

        if agent_kp is None:
            return specs
        filters = agent_kp.dep_filters() or {}
        agent_spec = agent_doc.spec
        for spec_field, alias in filters.items():
            declared = agent_spec.get(spec_field)
            if not declared:
                continue
            names = [declared] if isinstance(declared, str) else list(declared)
            # Honor caller slot filtering so provenance matches the rendered prompt.
            if spec_field in enabled_slots:
                allowed = set(enabled_slots[spec_field])
                names = [n for n in names if n in allowed]
            if not names:
                continue
            kp = self._kp_by_alias(alias)
            if kp is None:
                continue
            if not self._contributes_to_prompt(kp, alias, names, template):
                continue
            singular = spec_field[:-1] if spec_field.endswith("s") else spec_field
            for n in names:
                label = singular if isinstance(declared, str) else f"{singular}:{n}"
                specs.append((label, kp, n))
        return specs

    def _contributes_to_prompt(
        self, kp: Any, alias: str, names: list[str], template: str,
    ) -> bool:
        """True when the layout actually renders this Kind's content."""
        if getattr(kp, "flatten_in_context", False):
            # Flatten Kind (Soul): its spec string keys become top-level vars
            # (soul_content). Contributes iff one of those vars is in template.
            for doc in self._host.documents:
                if doc.kind != kp.kind or doc.name not in names:
                    continue
                for k, v in doc.spec.items():
                    if isinstance(v, str) and (
                        "{{{" + k + "}}}" in template or "{{" + k + "}}" in template
                    ):
                        return True
            return False
        # Section Kind (Skill/Guardrail): rendered as {{#alias}} ... {{/alias}}.
        return ("{{#" + alias + "}}") in template

    def _resolve_sync(self, kind: str, name: str, tenant: str | None) -> Any | None:
        kernel = self._host._kernel
        if kernel is None:
            return None
        from dna.kernel import _run_sync_helper
        kernel_loop = getattr(kernel, "_main_loop", None)
        try:
            return _run_sync_helper(
                kernel.resolve_document(self._host.scope, kind, name, tenant=tenant),
                loop=kernel_loop,
            )
        except Exception as e:  # noqa: BLE001 — read path, fail-soft
            logger.debug("explain: resolve_document(%s/%s) failed: %s", kind, name, e)
            return None

    @staticmethod
    def _doc_hash(raw: Any) -> str | None:
        if not isinstance(raw, dict):
            return None
        from dna.sync.hash import document_hash
        try:
            return document_hash(raw)
        except Exception:  # noqa: BLE001
            return None

    def _section_provenance(
        self,
        section_label: str,
        kp: Any,
        name: str,
        effective: Any | None,
        base: Any | None,
        tenant: str | None,
    ) -> SectionProvenance:
        """Build one provenance row.

        ``effective`` is the tenant-resolved doc (or ``base`` when no tenant);
        ``base`` is always the tenant-free resolution. The overlay marker is
        derived by COMPARING the two — robust to the FS source's tenant→base
        fallback (which makes per-layer ``found`` flags unreliable). Hash +
        version reflect the EFFECTIVE (composed) section; the layer origin is
        read from the base resolution (the clean scope/parent attribution).
        """
        source = self._source_path(kp, name)
        eff_raw = getattr(effective, "doc", None) if effective is not None else None
        base_raw = getattr(base, "doc", None) if base is not None else None

        eff_hash = self._doc_hash(eff_raw)
        version: str | None = None
        if isinstance(eff_raw, dict):
            meta = eff_raw.get("metadata") or {}
            if isinstance(meta, dict):
                v = meta.get("version")
                version = str(v) if v is not None else None

        # Layer origin from the base resolution (parent-scope inheritance is a
        # tenant-independent property; the FS tenant fallback would otherwise
        # stamp every section with the tenant even without an overlay).
        origin = "?"
        is_inherited = False
        origin_src = base if base is not None else effective
        if origin_src is not None:
            prov = getattr(origin_src, "provenance", None)
            eff_layer = getattr(prov, "effective_layer", None) if prov else None
            if eff_layer is not None:
                origin = eff_layer.scope
            elif getattr(origin_src, "doc", None) is None:
                origin = "(not found)"
            is_inherited = bool(getattr(origin_src, "is_inherited", False))

        # Overridden iff a tenant was requested AND the tenant-resolved content
        # actually differs from the base content.
        overridden = bool(
            tenant
            and eff_hash is not None
            and eff_hash != self._doc_hash(base_raw)
        )
        return SectionProvenance(
            section=section_label,
            kind=getattr(kp, "kind", "?"),
            name=name,
            source=source,
            hash=eff_hash,
            version=version,
            origin=origin,
            is_inherited=is_inherited,
            overridden_by_tenant=overridden,
        )

    @staticmethod
    def _source_path(kp: Any, name: str) -> str:
        """Canonical on-disk artifact path for a Kind's doc (best-effort)."""
        storage = getattr(kp, "storage", None)
        if storage is None:
            return "?"
        pattern = getattr(getattr(storage, "pattern", None), "value", None)
        container = getattr(storage, "container", "") or ""
        marker = getattr(storage, "marker", None)
        if pattern == "bundle":
            return f"{container}/{name}/{marker}" if container else f"{name}/{marker}"
        if pattern == "yaml":
            return f"{container}/{name}.yaml" if container else f"{name}.yaml"
        if pattern in ("root", "standalone"):
            return marker or f"{name}"
        return f"{container}/{name}" if container else name

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
        # 1. Agent-level raw template override (poweruser escape hatch).
        agent_spec = agent_doc.spec
        agent_template = agent_spec.get("promptTemplate") or agent_spec.get("prompt_template")
        if agent_template:
            return self._mustache_render(agent_template, ctx)

        agent_kp = self._host._kinds.get((agent_doc.api_version, agent_doc.kind))

        # 2. Named layout preset (s-dx-named-layouts) — author picks the
        # composition order by NAME; the kernel resolves it to an embedded
        # template so the common case never hand-writes Mustache.
        layout = agent_spec.get("layout")
        if layout and agent_kp is not None:
            layout_tmpl = agent_kp.layout_template(layout)
            if layout_tmpl is None:
                raise UnknownLayout(layout, agent_kp.layout_names(), agent_doc.name)
            return self._mustache_render(layout_tmpl, ctx)

        # 3. Kind default template
        if agent_kp:
            kind_template = agent_kp.prompt_template()
            if kind_template:
                return self._mustache_render(kind_template, ctx)

        # 4. Fallback: agent instruction as plain text
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

        # Named layout preset (s-dx-named-layouts) — twin of _render_prompt.
        layout = agent_spec.get("layout")
        if layout and agent_kp is not None:
            layout_tmpl = agent_kp.layout_template(layout)
            if layout_tmpl is None:
                raise UnknownLayout(layout, agent_kp.layout_names(), agent_doc.name)
            return await self._mustache_render_async(layout_tmpl, ctx)

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
            import chevron  # noqa: F401
            return _two_pass_mustache(template, ctx)
        except ImportError:
            result = template
            for key, value in ctx.items():
                if isinstance(value, str):
                    result = result.replace("{{" + key + "}}", value)
                elif isinstance(value, dict) and "instruction" in value:
                    result = result.replace("{{" + key + ".instruction}}", value["instruction"])
            return result

    def _mustache_render(self, template: str, ctx: dict[str, Any]) -> str:
        """Render a Mustache template — see :func:`_two_pass_mustache` for
        the two-pass semantics and the i-046 trust boundary."""
        if "/" in template or template.endswith((".mustache", ".md")):
            template = self._host.ref(template)

        try:
            import chevron  # noqa: F401
            return _two_pass_mustache(template, ctx)
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


# ──────────────────────────────────────────────────────────────────────
# Two-pass Mustache with a trust boundary (i-046)
# ──────────────────────────────────────────────────────────────────────

# Sentinels standing in for content-borne mustache delimiters between the
# two passes. Unicode Private Use Area codepoints — they carry no meaning
# to chevron and are not expected in legitimate document content.
_LIT_OPEN = "\ue000"
_LIT_CLOSE = "\ue001"

# Context entries whose strings MAY carry live mustache refs. The agent
# document is the composition root — its author writes ``instruction`` (and
# picks/authors the template), so refs inside it are a feature (e.g. the
# open-swe scope's instruction interpolating ``{{repository}}``). Every
# OTHER document's content (Skill, Soul, guardrails, memory, tenant
# overlays of those docs, caller extras) is DATA: a third party's ``{{``
# must reach the final prompt as ``{{``, not execute as template.
_TEMPLATE_BEARING_CTX_KEYS = frozenset({"agent"})


def _protect_literals(value: Any) -> Any:
    """Deep-copy ``value`` with mustache delimiters in strings replaced by
    inert sentinels (restored verbatim after the final pass)."""
    if isinstance(value, str):
        return value.replace("{{", _LIT_OPEN).replace("}}", _LIT_CLOSE)
    if isinstance(value, dict):
        return {k: _protect_literals(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_protect_literals(v) for v in value]
    return value


def _restore_literals(text: str) -> str:
    return text.replace(_LIT_OPEN, "{{").replace(_LIT_CLOSE, "}}")


def _two_pass_mustache(template: str, ctx: dict[str, Any]) -> str:
    """Render ``template`` twice against ``ctx`` — with a trust boundary.

    Why two passes at all: pass 1 expands the layout/kind/agent template
    (inserting ``{{{agent.instruction}}}``, section content, …); pass 2
    exists so refs INSIDE the agent's own instruction (``{{repository}}``,
    ``{{soul_content}}``) still resolve — the ref-inside-content feature.

    Why the boundary (i-046): before it, pass 2 re-rendered EVERYTHING the
    first pass inserted, so a Skill/Soul/tenant-overlay containing ``{{``
    executed as template inside the final prompt — template injection when
    that content is third-party input (and silent data loss for literal
    ``{{`` in honest content, which chevron erases as an unknown tag).

    The rule: only the agent document's own entry
    (``_TEMPLATE_BEARING_CTX_KEYS``) keeps live delimiters. All other
    context values have ``{{``/``}}`` swapped for sentinels before pass 1
    and restored after pass 2 — they flow through both passes untouched
    and land in the prompt byte-identical.
    """
    import chevron

    safe_ctx = {
        k: (v if k in _TEMPLATE_BEARING_CTX_KEYS else _protect_literals(v))
        for k, v in ctx.items()
    }
    first_pass = chevron.render(template, safe_ctx)
    return _restore_literals(chevron.render(first_pass, safe_ctx))
