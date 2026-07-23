"""Lazy, kernel-driven prompt builder — replaces the MI-walking variant.

Story s-build-prompt-lazy (Feature f-mi-class-extinction, Big-Bang C).

The legacy ``PromptBuilder._build_context_async`` walks every doc in
``self._host.documents`` (which materialized the entire scope) to
populate the Mustache context. That worked but scaled O(scope_size)
on every prompt build — and was the principal RSS leak driver.

This module parses the template's Mustache sections + the agent's
declared deps UP FRONT, then issues bounded queries:

  - **Single doc fetches** for: the agent itself, the root Genome,
    flatten_in_context kinds referenced by name in agent.spec (soul,
    prompt, ...).
  - **Kind-scoped queries** for: each Mustache section ``{{#alias}}``
    in the template. Filtered by name when agent's ``dep_filters``
    declares specific values for that alias.
  - **Skipped** for: kinds neither referenced by the template nor by
    dep_filters. Big win — a typical agent uses 3-5 kinds; legacy
    walked all 30+.

Parity contract: produces an identical context dict shape to
``PromptBuilder._build_context_async``. Tests in
``test_prompt_kernel.py`` lock the parity per agent.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from dna.kernel._text import strip_prompt_block
from dna.kernel.document import Document


# {{#section}} or {{^section}} — captures alias being iterated.
_SECTION_RE = re.compile(r"\{\{[#^]([\w\-]+)\}\}")
# {{flat_field}} or {{{flat_field}}} — captures top-level scalar refs
# (these come from flatten_in_context kinds whose specs are merged
# into the root context).
_SCALAR_RE = re.compile(r"\{\{\{?([\w\-]+(?:\.[\w\-]+)*)\}\}\}?")


def _referenced_aliases(template: str) -> set[str]:
    """Aliases iterated as Mustache sections (``{{#alias}}...{{/alias}}``)."""
    return set(_SECTION_RE.findall(template))


def _referenced_scalars(template: str) -> set[str]:
    """Top-level scalar Mustache references (e.g. ``{{{soul_content}}}``).

    Excludes nested dotted paths (those resolve against context Sections,
    not flat fields).
    """
    out: set[str] = set()
    for ref in _SCALAR_RE.findall(template):
        # Filter out section names (handled separately) and dotted nested refs.
        if "." in ref:
            continue
        out.add(ref)
    return out


def _get_description(doc: Document) -> str:
    """Match PromptBuilder._get_description shape (top-line of body or spec)."""
    desc = doc.metadata.get("description") if doc.metadata else None
    if isinstance(desc, str) and desc:
        return desc
    spec = doc.spec
    desc = spec.get("description") if hasattr(spec, "get") else None
    return desc or ""


async def _entry_from_doc(
    doc: Document, *, ref_resolver,
) -> dict[str, Any]:
    """Build the Mustache section entry for one doc.

    ``ref_resolver`` is an async callable ``(value: str) -> str``
    that resolves file/spec refs via ``source.resolve_ref`` semantics.
    """
    entry: dict[str, Any] = {
        "name": doc.name,
        "description": _get_description(doc),
    }
    spec = doc.spec
    for k, v in (spec.items() if hasattr(spec, "items") else []):
        if isinstance(v, str):
            entry[k] = await ref_resolver(v)
        else:
            entry[k] = v
    return entry


def _ref_resolver_factory(kernel: Any, scope: str):
    """Build an async ref-resolver closured over (kernel, scope).

    Mirrors ``ManifestInstance.ref_async`` semantics — delegates to
    ``kernel._source.resolve_ref`` when the value looks like a ref
    (e.g. ``instruction.md`` → file contents).
    """
    async def _resolve(value: str) -> str:
        if not isinstance(value, str) or not value:
            return value
        # Heuristic: strings ending in known doc-body extensions are refs.
        # Mirrors instance.py:ref/ref_async behavior — anything else
        # passes through unchanged.
        if not (
            value.endswith(".md") or value.endswith(".txt")
            or value.endswith(".yaml") or value.endswith(".yml")
        ):
            return value
        source = getattr(kernel, "_source", None)
        if source is None:
            return value
        try:
            return await source.resolve_ref(scope, value)
        except Exception as e:  # noqa: BLE001
            # fail-soft: an unresolvable file ref degrades to the literal
            # value in the prompt (visible in output) — logged so a broken
            # resolver isn't chased as a "weird prompt" bug.
            logging.getLogger(__name__).debug(
                "build_prompt: resolve_ref(%r) failed in %s: %s",
                value, scope, e,
            )
            return value
    return _resolve


async def build_prompt_async(
    kernel: Any,
    scope: str,
    agent_name: str,
    *,
    tenant: str | None = None,
    context: dict[str, Any] | None = None,
    enabled_skills: list[str] | None = None,
    enabled_guardrails: list[str] | None = None,
    enabled_slots: dict[str, list[str]] | None = None,
) -> str:
    """Lazy prompt build — bounded fetches per Mustache section.

    Algorithm:
      1. Fetch agent doc + root Genome via kernel.get_document.
      2. Resolve the template (agent override → Kind default → fallback).
      3. Parse template for ``{{#alias}}`` sections and ``{{{scalar}}}``
         refs; combine with agent's dep_filters to know which Kinds to
         fetch.
      4. For each referenced alias, ``kernel.query(scope, kind)``
         (filtered by name if dep_filters declares). For flatten_in_context
         kinds referenced by agent.spec by name, targeted get_document.
      5. Apply hooks (pre_build_prompt middleware, post_build_prompt event).
      6. Render Mustache.

    Returns a string. Tenant kwarg flows through every query.
    """
    # --- 1. Fetch agent doc -----------------------------------------------
    agent_raw = await kernel.get_document(scope, "Agent", agent_name, tenant=tenant)
    if agent_raw is None:
        # Fail loud (s-dx-build-prompt-fail-loud): parity with the MI-level
        # PromptBuilder — a missing agent raises rather than returning a
        # placeholder string that would become the literal instruction.
        from dna.kernel.errors import AgentNotFound
        raise AgentNotFound(agent_name)
    agent_doc = kernel._parse_doc(agent_raw, origin="local")
    if agent_doc is None:
        return f"Agent '{agent_name}' parse failed"
    agent_kp = kernel._kinds.get((agent_doc.api_version, agent_doc.kind))

    # --- 2. Fetch root Genome --------------------------------------------
    root_doc: Document | None = None
    # Genome is the canonical root kind (post-Phase-16). Iterate scopes:
    # there's typically exactly one Genome doc per scope.
    pkg_refs = await kernel.list_documents(scope, kind="Genome", tenant=tenant)
    if pkg_refs:
        _kind, pkg_name = pkg_refs[0]
        pkg_raw = await kernel.get_document(scope, "Genome", pkg_name, tenant=tenant)
        if pkg_raw is not None:
            root_doc = kernel._parse_doc(pkg_raw, origin="local")

    # --- 3. Resolve template ----------------------------------------------
    agent_spec = agent_doc.spec
    template = (
        agent_spec.get("promptTemplate")
        or agent_spec.get("prompt_template")
        or (agent_kp.prompt_template() if agent_kp else None)
    )

    # --- 4. Determine referenced kinds -----------------------------------
    referenced_aliases = _referenced_aliases(template) if template else set()
    referenced_scalars = _referenced_scalars(template) if template else set()

    # Build alias → KindPort map for lookup.
    alias_to_kp: dict[str, Any] = {kp.alias: kp for kp in kernel._kinds.values()}

    # Slot filter merge: backwards-compat params into enabled_slots.
    slots = dict(enabled_slots or {})
    if enabled_skills and "skills" not in slots:
        slots["skills"] = enabled_skills
    if enabled_guardrails and "guardrails" not in slots:
        slots["guardrails"] = enabled_guardrails

    # Agent's dep_filters: maps spec_field → target_alias. These tell us
    # which docs the agent has declared per slot (skills, guardrails, etc.)
    dep_filters: dict[str, str] = {}
    if agent_kp:
        dep_filters = agent_kp.dep_filters() or {}

    # --- 5. Build ref resolver --------------------------------------------
    ref_resolve = _ref_resolver_factory(kernel, scope)

    # --- 6. Build context -------------------------------------------------
    ctx: dict[str, Any] = {}

    # Root metadata + spec
    if root_doc:
        ctx["metadata"] = dict(root_doc.metadata)
        ctx["spec"] = dict(root_doc.spec)

    # Agent entry
    instruction_ref = agent_spec.get("instruction", "")
    ctx["agent"] = {
        "name": agent_doc.name,
        "description": _get_description(agent_doc),
        # strip_prompt_block: composition-only normalization (i-013).
        "instruction": (
            strip_prompt_block(await ref_resolve(instruction_ref))
            if instruction_ref
            else ""
        ),
    }
    ctx["agentId"] = agent_doc.name

    # --- 7. Populate referenced aliases (sections) ------------------------
    for alias in referenced_aliases:
        kp = alias_to_kp.get(alias)
        if not kp:
            ctx[alias] = []
            continue
        # Apply dep_filter: do we have a declared name list for this alias?
        declared_names: list[str] | None = None
        for spec_field, target_alias in dep_filters.items():
            if target_alias != alias:
                continue
            declared = agent_spec.get(spec_field)
            if declared is None:
                declared_names = []
                break
            if isinstance(declared, str):
                declared_names = [declared]
                break
            if isinstance(declared, list):
                declared_names = list(declared)
                break
        # Slot override: enabled_slots restricts further.
        for spec_field, override_names in slots.items():
            target_alias = dep_filters.get(spec_field)
            if target_alias == alias:
                if declared_names is not None:
                    declared_names = [
                        n for n in declared_names if n in override_names
                    ]
                else:
                    declared_names = list(override_names)

        # Fetch the docs.
        entries: list[dict[str, Any]] = []
        if declared_names == []:
            ctx[alias] = []
            continue
        if declared_names:
            # Targeted fetches.
            for name in declared_names:
                raw = await kernel.get_document(scope, kp.kind, name, tenant=tenant)
                if raw is None:
                    continue
                doc = kernel._parse_doc(raw, origin="local")
                if doc is not None:
                    entries.append(await _entry_from_doc(doc, ref_resolver=ref_resolve))
        else:
            # Query all of this kind (no declared filter).
            async for raw in kernel.query(scope, kp.kind, tenant=tenant):
                doc = kernel._parse_doc(raw, origin="local")
                if doc is not None:
                    entries.append(await _entry_from_doc(doc, ref_resolver=ref_resolve))
        ctx[alias] = entries

    # --- 8. Flatten kinds — global merge of flatten_in_context kinds ----
    # Legacy semantic (preserved for parity): every flatten_in_context
    # doc in scope has its spec merged into the top-level context. Multiple
    # docs of the same kind result in last-wins per field. This is a known
    # quirk (soul-A overrides soul-B) but agents in production rely on it
    # — e.g., hr-screening's code-reviewer + manifest-inspector receive
    # fair-recruiter's flattened `soul_content` without declaring it.
    #
    # Story s-flatten-explicit-opt-in (proposed follow-up): tighten to
    # only flatten kinds the agent explicitly references. Out-of-scope here.
    _reserved = {"agent", "metadata", "spec", "agentId"}
    flatten_kps = [kp for kp in kernel._kinds.values() if kp.flatten_in_context]
    for kp in flatten_kps:
        async for raw in kernel.query(scope, kp.kind, tenant=tenant):
            doc = kernel._parse_doc(raw, origin="local")
            if doc is None:
                continue
            spec = doc.spec
            for k, v in (spec.items() if hasattr(spec, "items") else []):
                if v is not None and k not in _reserved:
                    # Trailing-whitespace normalization on flattened string
                    # values — the template supplies the joiners (i-013).
                    ctx[k] = (
                        strip_prompt_block(await ref_resolve(v))
                        if isinstance(v, str)
                        else v
                    )

    # --- 9. Extra context from caller -----------------------------------
    if context:
        ctx.update(context)

    # --- 10. pre_build_prompt hook -----------------------------------
    hooks = kernel.hooks if hasattr(kernel, "hooks") else None
    if hooks is not None and hooks.has("pre_build_prompt"):
        from dna.kernel.hooks import HookContext
        hook_ctx = HookContext(scope=scope, agent=agent_name, data={"context": ctx})
        hook_ctx = hooks.run_middleware("pre_build_prompt", hook_ctx)
        ctx = hook_ctx.data.get("context", ctx)

    # --- 11. Render Mustache --------------------------------------------
    prompt = _render(template, ctx, agent_doc)

    # --- 12. post_build_prompt hook ----------------------------------
    if hooks is not None and hooks.has("post_build_prompt"):
        from dna.kernel.hooks import HookContext
        # Async context — reach BOTH channels. A sync emit() here would
        # silently skip async listeners (s-kernel-fail-soft-audit).
        await hooks.emit_async(
            "post_build_prompt",
            HookContext(scope=scope, agent=agent_name, prompt=prompt),
        )

    # Clean output (s-dx-clean-composition-output) — parity with PromptBuilder.
    return prompt.rstrip("\n")


def _render(template: str | None, ctx: dict[str, Any], agent_doc: Document) -> str:
    """Mustache render. Falls back to agent.instruction when no template."""
    if not template:
        return ctx.get("agent", {}).get("instruction", "")
    try:
        import chevron
        return chevron.render(template, ctx)
    except ImportError:
        import pystache  # type: ignore
        return pystache.render(template, ctx)


__all__ = ["build_prompt_async"]
