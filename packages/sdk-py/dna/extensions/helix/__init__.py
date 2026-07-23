"""HelixExtension — Genome, Agent, Actor kinds."""
from __future__ import annotations

import dataclasses
import posixpath
import re
from pathlib import Path
from typing import Any

import yaml

from dna.kernel.descriptor_loader import load_descriptors
from dna.kernel.kinds.base import KindBase
from dna.kernel.models import (
    TypedAgent, TypedActor, TypedUseCase,
    TypedGenome, TypedLayerPolicy,
    AgentSpec,
)
from dna.kernel.preview import PreviewBlock
from dna.kernel.protocols import ExtensionHost, StorageDescriptor, ReaderPort, WriterPort
from dna.kernel.bundle_handle import BundleHandle


def _literal_enum_schema(resolved: Any) -> dict[str, Any] | None:
    """If ``resolved`` is a ``Literal[...]`` (bare or wrapped in an
    ``Optional[...]``/``X | None``), return a JSON-Schema ``enum`` property;
    else ``None``.

    Emits ``{"type": <json-type>, "enum": [...]}`` where the JSON type is
    inferred from the literal members (all-str → ``string``, all-int →
    ``integer``, all-bool → ``boolean``; mixed → type omitted). This is what
    makes a constrained field (e.g. a Guardrail ``severity`` = ``warn | error |
    hard``) actually enforced by the schema rather than accepting any string
    (i-validation-shallow). Parity with the TS ``zodSpecToJsonSchema`` ZodEnum
    branch, which emits the same ``{type, enum}`` shape.
    """
    import typing as _t

    origin = _t.get_origin(resolved)
    if origin is _t.Literal:
        args = list(_t.get_args(resolved))
    elif origin is _t.Union:
        # Optional[Literal[...]] / Literal[...] | None — unwrap NoneType and
        # recover the Literal member if that's the only non-None arm.
        inner = [a for a in _t.get_args(resolved) if a is not type(None)]
        if len(inner) == 1 and _t.get_origin(inner[0]) is _t.Literal:
            args = list(_t.get_args(inner[0]))
        else:
            return None
    else:
        return None

    prop: dict[str, Any] = {"enum": args}
    if args and all(isinstance(a, bool) for a in args):
        prop = {"type": "boolean", "enum": args}
    elif args and all(isinstance(a, str) for a in args):
        prop = {"type": "string", "enum": args}
    elif args and all(isinstance(a, int) and not isinstance(a, bool) for a in args):
        prop = {"type": "integer", "enum": args}
    return prop


def _schema_from_model(model: type) -> dict[str, Any] | None:
    """Build a JSON Schema dict from a typed model's spec dataclass fields.

    The model is e.g. TypedGenome — a dataclass with .metadata and .spec fields.
    We resolve the spec field's type (which may be a string due to
    ``from __future__ import annotations``) and inspect its dataclass fields.
    """
    if not dataclasses.is_dataclass(model):
        return None

    # Find the spec field's type — may be a string or an actual type
    import typing
    spec_type = None
    type_hints = typing.get_type_hints(model)
    spec_type = type_hints.get("spec")

    if spec_type is None or not dataclasses.is_dataclass(spec_type):
        return None

    properties: dict[str, Any] = {}
    spec_hints = typing.get_type_hints(spec_type)
    for f in dataclasses.fields(spec_type):
        resolved = spec_hints.get(f.name)
        # Constrained/enum field — ``Literal["a", "b", ...]`` (also inside an
        # ``Optional[...]``/``X | None``). Emit ``enum`` so the documented
        # contract is actually enforced by the schema (i-validation-shallow),
        # instead of degrading to a bare ``{"type": "string"}`` that accepts any
        # value. Parity: the TS twin's ``zodSpecToJsonSchema`` maps ``z.enum``
        # to the same ``{"type": <t>, "enum": [...]}`` shape.
        enum_prop = _literal_enum_schema(resolved)
        if enum_prop is not None:
            properties[f.name] = enum_prop
            continue
        t = str(resolved) if resolved else str(f.type)
        if resolved is str or t == "<class 'str'>" or t == "str":
            properties[f.name] = {"type": "string"}
        elif resolved is int or t == "<class 'int'>":
            properties[f.name] = {"type": "integer"}
        elif resolved is bool or t == "<class 'bool'>":
            properties[f.name] = {"type": "boolean"}
        elif "list" in t.lower():
            # Inspect the ELEMENT type — list[dict[...]] fields (e.g.
            # Genome.dependencies, UseCase.alternate_flows) are arrays of
            # OBJECTS. The old blanket items:string contradicted the typed
            # model and (since s-write-path-validation made schemas
            # enforceable at write) vetoed legitimate docs; the TS twin
            # (zod z.array(z.record(...))) always said object here.
            inner = t.lower()
            if "dict" in inner:
                items: dict[str, Any] = {"type": "object"}
            elif "int" in inner:
                items = {"type": "integer"}
            else:
                items = {"type": "string"}
            properties[f.name] = {"type": "array", "items": items}
        elif "dict" in t.lower():
            properties[f.name] = {"type": "object"}
        elif "None" in t:
            # Optional field — use the base type
            if "str" in t:
                properties[f.name] = {"type": "string"}
            elif "int" in t:
                properties[f.name] = {"type": "integer"}
            elif "bool" in t:
                properties[f.name] = {"type": "boolean"}
            else:
                properties[f.name] = {}
        else:
            properties[f.name] = {}
    return {"type": "object", "properties": properties}



from dna.kernel.studio_ui import docs_ui


# ── Named composition layouts (s-dx-named-layouts) ─────────────────────
#
# An author orders persona-vs-instruction by NAME (`layout:` in the Agent
# spec) instead of hand-writing raw Mustache with internal section names
# (`{{{soul_content}}}`, `{{#guardrails-guardrail}}`). Each preset resolves
# to one of these embedded templates via `AgentKind.layout_template()`.
#
# The guardrails block is shared verbatim across layouts — guardrails are
# hard policy and always land LAST, after both the instruction and the
# soul, regardless of their relative order.
_GUARDRAILS_BLOCK = (
    "{{#guardrails-guardrail}}"
    "## Guardrail: {{name}} ({{severity}})\n"
    "{{#description}}_{{description}}_\n\n{{/description}}"
    "{{#rules}}- {{{.}}}\n{{/rules}}\n"
    "{{/guardrails-guardrail}}"
)

# Skills block (i-031) — a referenced Skill now COMPOSES into the system
# prompt, exactly the way Guardrails do: a Mustache section over the
# dep-filtered ``agentskills-skill`` list. Before this fix a Skill wired to
# an Agent was inert — it landed in the Mustache context but no layout ever
# rendered it, so it never reached ``build_prompt`` nor any emitted artifact
# (the composition thesis bought nothing at runtime). The section iterates
# the SAME filtered list the ``skills`` dep_filter produces and inlines each
# skill's SKILL.md body ({{{instruction}}}). Skills land AFTER the soul and
# BEFORE guardrails (procedural know-how, then hard policy). An agent with no
# skills renders the empty section to nothing, so skill-less agents compose
# byte-identically to before. A DeepAgents harness may still layer
# progressive-disclosure on top at runtime; the declarative composition now
# carries the skill so every OTHER runtime (bedrock/vertex/agno/…) gets it.
_SKILLS_BLOCK = (
    "{{#agentskills-skill}}"
    "## Skill: {{name}}\n"
    "{{#description}}_{{description}}_\n\n{{/description}}"
    "{{{instruction}}}\n\n"
    "{{/agentskills-skill}}"
)

# instruction-first (a.k.a. "default") — the historic order; kept byte-
# identical for skill-less agents (the skills section renders to nothing).
_LAYOUT_INSTRUCTION_FIRST = (
    "{{{agent.instruction}}}\n\n"
    "{{{soul_content}}}\n\n"
    + _SKILLS_BLOCK
    + _GUARDRAILS_BLOCK
)

# persona-first — the Soul (personality/voice) leads, then the task
# instruction, then skills, then guardrails. The common reason an author
# reached for a raw promptTemplate before this story existed.
_LAYOUT_PERSONA_FIRST = (
    "{{{soul_content}}}\n\n"
    "{{{agent.instruction}}}\n\n"
    + _SKILLS_BLOCK
    + _GUARDRAILS_BLOCK
)

# Map preset name → template. ``default`` aliases ``instruction-first``.
AGENT_LAYOUTS: dict[str, str] = {
    "default": _LAYOUT_INSTRUCTION_FIRST,
    "instruction-first": _LAYOUT_INSTRUCTION_FIRST,
    "persona-first": _LAYOUT_PERSONA_FIRST,
}

# Public, ordered names for discovery / error messages / CLI validation.
AGENT_LAYOUT_NAMES: list[str] = ["default", "instruction-first", "persona-first"]


class GenomeKind(KindBase):
    """Phase 16 — replaces Module as the scope-root identity Kind.

    Carries catalog identity (owner, owner_tenant, repository, visibility),
    versioning (version, changelog_url, deprecated*), runtime defaults
    (default_agent, default_llm, budget, tags), and external dependencies.

    Tenant overlay is field-level: only fields in ``OVERLAYABLE_FIELDS``
    accept layer overrides. Identity and versioning are structurally
    non-overlayable. The kernel enforces this allowlist when resolving
    layers.

    Phase 16 — sole root Kind. Module Kind class is fully deleted.
    """

    api_version = "github.com/ruinosus/dna/v1"
    kind = "Genome"
    alias = "helix-genome"
    is_schema_affecting = True
    is_overlayable = False
    scope_inheritable = False
    # Genome IS the catalog identity — a write must drop the kernel's
    # catalog-tier cache (Phase 3b ch1, i-112; s-write-path-despecialize).
    is_catalog_identity = True
    model = TypedGenome
    origin = "github.com/ruinosus/dna"
    storage = StorageDescriptor.root("Genome.yaml")
    graph_style = {"fill": "#3B82F6", "stroke": "#1D4ED8", "text_color": "#fff"}
    ascii_icon = "📦"
    display_label = "Genome"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False

    # Tenant-overlayable fields. Identity and versioning are NOT here on
    # purpose: a tenant overlay must not change owner, version, etc.
    # Kernel enforces this allowlist in ``_apply_package_field_overlay``
    # (commit 2). For now, the constant exists and tests can read it.
    OVERLAYABLE_FIELDS = frozenset({
        "default_agent",
        "default_llm",
        "budget",
        "tags",
    })

    ui_schema = {
        "owner_tenant": {"widget": "readonly", "label": "Owner tenant", "help": "null = platform-owned (catalog item).", "order": 5},
        "visibility": {"widget": "select", "label": "Visibility", "options": ["public", "internal", "private"], "help": "Who can discover and install this Genome.", "order": 6},
        "version": {"widget": "text", "label": "Version", "help": "Semver. Opt-in. null = unversioned.", "order": 7},
        "changelog_url": {"widget": "text", "label": "Changelog URL", "order": 8},
        "deprecated": {"widget": "checkbox", "label": "Deprecated", "order": 9},
        "deprecated_message": {"widget": "textarea", "label": "Deprecated message", "order": 10},
        "default_agent": {"widget": "text", "label": "Default agent", "help": "Tenant-overlayable.", "order": 20},
        "default_llm": {"widget": "text", "label": "Default LLM", "help": "Tenant-overlayable.", "order": 21},
        "budget": {"widget": "readonly", "label": "Budget", "help": "Tenant-overlayable.", "order": 22},
        "tags": {"widget": "tags", "label": "Tags", "help": "Tenant-overlayable.", "order": 23},
        "owner": {"widget": "text", "label": "Owner", "order": 30},
        "repository": {"widget": "text", "label": "Repository", "order": 31},
        "dependencies": {"widget": "readonly", "label": "External dependencies", "order": 90},
    }
    docs = (
        "A Genome is the scope-root identity document (Phase 16). It "
        "declares catalog identity (owner, owner_tenant, repository, "
        "visibility), versioning (version, changelog_url, deprecated), "
        "runtime defaults (default_agent, default_llm, budget, tags), and "
        "external dependencies. Replaces the legacy Module Kind. Layer "
        "policy moved out to LayerPolicy docs at <scope>/policies/. "
        "Custom Kinds moved out to KindDefinition docs at <scope>/kinds/."
    )

    def schema(self) -> dict[str, Any] | None:
        return _schema_from_model(self.model)

    def get_default_agent_name(self, doc: Any) -> str | None:
        return doc.spec.get("default_agent")

    def parse(self, raw: dict[str, Any]) -> Any:
        return TypedGenome.from_raw(raw)

    def describe(self, doc: Any) -> str | None:
        spec = doc.spec
        lines = [f"Name:       {doc.name}", f"Kind:       Genome"]
        owner = spec.get("owner_tenant") or "platform"
        lines.append(f"Owner:      {owner}")
        if spec.get("version"):
            lines.append(f"Version:    {spec['version']}")
        if spec.get("visibility"):
            lines.append(f"Visibility: {spec['visibility']}")
        if spec.get("default_agent"):
            lines.append(f"Default:    {spec['default_agent']}")
        if spec.get("deprecated"):
            msg = spec.get("deprecated_message") or ""
            lines.append(f"Deprecated: {msg}")
        return "\n".join(lines)

    def summary(self, doc: Any) -> dict[str, Any] | None:
        spec = doc.spec
        return {
            "owner_tenant": spec.get("owner_tenant"),
            "visibility": spec.get("visibility"),
            "version": spec.get("version"),
            "default_agent": spec.get("default_agent"),
            "deprecated": bool(spec.get("deprecated", False)),
        }

    def preview(self, doc: Any) -> list[PreviewBlock]:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        fields: list[dict[str, str]] = []
        for label in ("owner_tenant", "visibility", "version", "default_agent", "default_llm"):
            value = spec_dict.get(label)
            if value is not None and value != "":
                fields.append({"label": label, "value": str(value)})
        if spec_dict.get("deprecated"):
            fields.append({"label": "deprecated", "value": str(spec_dict.get("deprecated_message") or "true")})
        deps = spec_dict.get("dependencies") or []
        if isinstance(deps, list) and deps:
            fields.append({"label": "dependencies", "value": f"{len(deps)} entries"})
        if not fields:
            return [PreviewBlock(kind="empty", title=f"Genome {doc.name}")]
        return [PreviewBlock(kind="fields", title=f"Genome {doc.name}", fields=fields)]


class LayerPolicyKind(KindBase):
    """Phase 16 — overlay policy per (layer, kind) tuple.

    Replaces the legacy ``Module.spec.layers`` field. One LayerPolicy
    doc per layer dimension (e.g. one for "tenant", one for "branch").
    Lives at ``<scope>/policies/<id>.yaml``. The kernel reads these docs
    in ``_check_layer_policy_with_mi`` (commit 2) when validating writes
    against a layer.

    Spec shape:
        layer_id: tenant
        policies:
            helix-agent: locked
            agentskills-skill: open
            helix-genome: locked

    Policy values: ``open`` (default — never raises),
    ``restricted`` (only override existing top-level spec keys),
    ``locked`` (any write raises).
    """

    api_version = "github.com/ruinosus/dna/policy/v1"
    kind = "LayerPolicy"
    alias = "policy-layer-policy"  # s-kind-alias-convention-fix: <owner>-<kebab(kind)>; was "policy-layer" (reversed/truncated)
    is_schema_affecting = True
    is_overlayable = False
    scope_inheritable = False
    model = TypedLayerPolicy
    origin = "github.com/ruinosus/dna/policy"
    storage = StorageDescriptor.yaml("policies")
    graph_style = {"fill": "#A855F7", "stroke": "#7E22CE", "text_color": "#fff"}
    ascii_icon = "🔒"
    display_label = "Layer Policies"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False

    ui_schema = {
        "layer_id": {"widget": "select", "label": "Layer dimension", "options": ["tenant", "branch", "region", "user"], "help": "Which layer dimension this policy applies to.", "order": 10},
        "policies": {"widget": "readonly", "label": "Per-Kind policies", "help": "Map of kind alias → policy (open/restricted/locked).", "order": 20},
    }
    docs = (
        "A LayerPolicy declares overlay rules for one layer dimension "
        "(tenant, branch, region, etc.). Kernel reads these docs to "
        "enforce write policy when a tenant or other layer overlay is "
        "applied. Replaces the legacy Module.spec.layers field. "
        "Some Kinds are structurally non-overlayable (Genome, "
        "KindDefinition, LayerPolicy itself) — their policy is always "
        "locked regardless of doc contents."
    )

    def schema(self) -> dict[str, Any] | None:
        return _schema_from_model(self.model)

    def parse(self, raw: dict[str, Any]) -> Any:
        return TypedLayerPolicy.from_raw(raw)

    def describe(self, doc: Any) -> str | None:
        spec = doc.spec
        layer_id = spec.get("layer_id") or doc.name
        n = len(spec.get("policies") or {})
        return f"Name:    {doc.name}\nKind:    LayerPolicy\nLayer:   {layer_id}\nRules:   {n}"

    def summary(self, doc: Any) -> dict[str, Any] | None:
        spec = doc.spec
        return {
            "layer_id": spec.get("layer_id"),
            "rule_count": len(spec.get("policies") or {}),
        }

    def preview(self, doc: Any) -> list[PreviewBlock]:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        fields: list[dict[str, str]] = []
        if spec_dict.get("layer_id"):
            fields.append({"label": "layer_id", "value": str(spec_dict["layer_id"])})
        policies = spec_dict.get("policies") or {}
        if isinstance(policies, dict):
            for alias, policy in sorted(policies.items()):
                fields.append({"label": str(alias), "value": str(policy)})
        if not fields:
            return [PreviewBlock(kind="empty", title=f"LayerPolicy {doc.name}")]
        return [PreviewBlock(kind="fields", title=f"LayerPolicy {doc.name}", fields=fields)]


class AgentKind(KindBase):
    api_version = "github.com/ruinosus/dna/v1"
    kind = "Agent"
    alias = "helix-agent"
    is_schema_affecting = True
    model = TypedAgent
    origin = "github.com/ruinosus/dna"
    storage = StorageDescriptor.bundle("agents", "AGENT.md")
    graph_style = {"fill": "#F97316", "stroke": "#EA580C", "text_color": "#fff"}
    ascii_icon = "🤖"
    display_label = "Agents"
    is_prompt_target = True
    prompt_target_priority = 10
    flatten_in_context = False
    ui_schema = {
        "instruction": {
            "widget": "markdown-toc",
            "label": "Instruction (AGENT.md)",
            "help": "The agent's main prompt body. Supports Mustache tags like {{soul_content}}.",
            "height": 520,
            "order": 10,
        },
        "model": {"widget": "text", "label": "Model", "order": 20},
        "layout": {
            "widget": "select",
            "label": "Layout",
            "options": ["default", "instruction-first", "persona-first"],
            "help": "Named composition order — 'persona-first' puts the Soul before the instruction. Leave empty for the default. A raw promptTemplate, if set, overrides this.",
            "order": 25,
        },
        "soul": {"widget": "text", "label": "Soul", "help": "Name of the Soul doc to flatten into the prompt.", "order": 30},
        "skills": {"widget": "tags", "label": "Skills", "order": 40},
        "actors": {"widget": "tags", "label": "Actors this agent serves", "order": 50},
        "guardrails": {"widget": "tags", "label": "Guardrails", "order": 60},
        "tools": {"widget": "tags", "label": "Tools", "order": 70},
        "team_members": {"widget": "tags", "label": "Team members", "order": 80},
        "tags": {"widget": "tags", "label": "Tags", "order": 90},
        "tool_groups": {"widget": "tags", "label": "Tool groups", "help": "Filter the manifest tools this agent receives. Values: 'all' (default), 'code', 'manifest', 'write', 'read'. Combine for unions, e.g. ['code', 'read'].", "order": 86},
        "mcp_servers": {"widget": "tags", "label": "MCP servers", "help": "MCPFederation doc names this agent consumes (e.g. 'drawio'). Remote tools load as first-class agent tools tagged mcp:<ref>. Entries may also be objects {ref, allowed_tools, timeout_s} for per-agent overrides.", "order": 87},
        "objective": {"widget": "textarea", "label": "Objective", "order": 15},
    }
    docs = (
        "A Agent is the primary prompt target: it's what actually runs "
        "when the user talks to the system. It declares an instruction "
        "(usually in a bundle AGENT.md or an agents/<name>.md file), a model "
        "to call, and dep_filters listing which Soul, Skills, and Guardrails "
        "to compose into its system prompt. The Soul, Skills, and Guardrails "
        "are all composed into the prompt every turn (a DeepAgents harness may "
        "additionally expose Skills via progressive disclosure). Priority 10 "
        "means Agent wins over other prompt targets when the harness has to "
        "pick one."
    )

    def dep_filters(self) -> dict[str, str] | None:
        return {
            "soul": "soulspec-soul",
            "skills": "agentskills-skill",
            "guardrails": "guardrails-guardrail",
            "actors": "helix-actor",
            "tools": "helix-tool",
        }

    def schema(self) -> dict[str, Any] | None:
        return _schema_from_model(self.model)

    def parse(self, raw: dict[str, Any]) -> Any:
        return TypedAgent.from_raw(raw)

    def describe(self, doc: Any) -> str | None:
        spec = doc.spec
        lines = [f"Name:    {doc.name}", f"Kind:    Agent"]
        desc = doc.metadata.get("description")
        if desc: lines.append(f"Desc:    {desc}")
        if spec.get("soul"): lines.append(f"Soul:    {spec['soul']}")
        skills = spec.get("skills") or []
        if skills: lines.append(f"Skills:  {', '.join(skills)} ({len(skills)})")
        if spec.get("model"): lines.append(f"Model:   {spec['model']}")
        return "\n".join(lines)

    def summary(self, doc: Any) -> dict[str, Any] | None:
        spec = doc.spec
        return {"skills": len(spec.get("skills") or []), "soul": spec.get("soul")}

    def prompt_template(self) -> str | None:
        # Triple braces disable HTML escaping — instructions are markdown.
        #
        # Composition (i-031): Soul, Skills, and Guardrails all cascade into
        # the system prompt. A referenced Skill's SKILL.md body is inlined via
        # the ``agentskills-skill`` section (see _SKILLS_BLOCK) — the same
        # Mustache-section mechanism Guardrails use — so the "compose a Skill"
        # promise actually buys something at runtime and survives every emit
        # target. (Before i-031 skills were inert: present in context, rendered
        # by no layout.) A DeepAgents harness may ADD progressive disclosure on
        # top (SkillsMiddleware reads SKILL.md on demand); that is a runtime
        # optimization layered over — not a replacement for — the declarative
        # composition, which every other runtime relies on.
        #
        # This IS the ``instruction-first`` / ``default`` named layout — the
        # kind default template and the ``default`` layout are one string, so
        # an agent with no ``layout:`` composes exactly as before.
        return _LAYOUT_INSTRUCTION_FIRST

    def layout_template(self, name: str) -> str | None:
        """Resolve a named layout preset (s-dx-named-layouts)."""
        return AGENT_LAYOUTS.get(name)

    def layout_names(self) -> list[str]:
        return list(AGENT_LAYOUT_NAMES)

    def preview(self, doc: Any) -> list[PreviewBlock]:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        blocks: list[PreviewBlock] = []
        instruction = spec_dict.get("instruction")
        if isinstance(instruction, str) and instruction:
            blocks.append(
                PreviewBlock(kind="markdown", title="AGENT.md (template)", body=instruction)
            )
        meta: list[dict[str, str]] = []
        if isinstance(spec_dict.get("model"), str):
            meta.append({"label": "model", "value": spec_dict["model"]})
        if isinstance(spec_dict.get("soul"), str):
            meta.append({"label": "soul", "value": spec_dict["soul"]})
        for f in ("skills", "guardrails", "tools"):
            arr = spec_dict.get(f)
            if isinstance(arr, list) and arr:
                meta.append({"label": f, "value": ", ".join(str(x) for x in arr)})
        if meta:
            blocks.append(PreviewBlock(kind="fields", title="Metadata", fields=meta))
        if not blocks:
            return [PreviewBlock(kind="empty", title=f"Agent {doc.name}")]
        return blocks


class ActorKind(KindBase):
    api_version = "github.com/ruinosus/dna/v1"
    kind = "Actor"
    alias = "helix-actor"
    model = TypedActor
    origin = "github.com/ruinosus/dna/actor"
    storage = StorageDescriptor.yaml("actors")
    graph_style = {"fill": "#EC4899", "stroke": "#DB2777", "text_color": "#fff"}
    ascii_icon = "👤"
    display_label = "Actors"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    ui_schema = {
        "role": {"widget": "text", "label": "Role", "help": "Short job title or functional role.", "order": 10},
        "actor_type": {
            "widget": "select",
            "label": "Actor type",
            "help": "human = person/role; system = external service or upstream; time = scheduled trigger.",
            "order": 20,
        },
        "goals": {"widget": "list-markdown", "label": "Goals", "help": "What this actor is trying to achieve.", "order": 30},
        "pain_points": {"widget": "list-markdown", "label": "Pain points", "order": 40},
        "preferences": {"widget": "readonly", "label": "Preferences", "help": "Nested object; edit in YAML for now.", "order": 90},
    }
    docs = (
        "An Actor is a UML-canonical participant in the system: a human user, "
        "an external system, or a time/schedule trigger. Actors describe who "
        "(or what) initiates or collaborates with agents. The actor_type "
        "field disambiguates: 'human' for people/roles, 'system' for "
        "external services or upstream systems, 'time' for scheduled "
        "triggers. Stored as a flat yaml file under actors/<name>.yaml."
    )

    def schema(self) -> dict[str, Any] | None:
        return _schema_from_model(self.model)

    def parse(self, raw: dict[str, Any]) -> Any:
        return TypedActor.from_raw(raw)

    def summary(self, doc: Any) -> dict[str, Any] | None:
        return None

    def preview(self, doc: Any) -> list[PreviewBlock]:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        fields: list[dict[str, str]] = []
        if isinstance(spec_dict.get("role"), str):
            fields.append({"label": "role", "value": spec_dict["role"]})
        if isinstance(spec_dict.get("actor_type"), str):
            fields.append({"label": "actor_type", "value": spec_dict["actor_type"]})
        goals = spec_dict.get("goals")
        if isinstance(goals, list) and goals:
            fields.append(
                {"label": "goals", "value": "\n".join(f"• {g}" for g in goals)}
            )
        pain_points = spec_dict.get("pain_points")
        if isinstance(pain_points, list) and pain_points:
            fields.append(
                {"label": "pain_points", "value": "\n".join(f"• {p}" for p in pain_points)}
            )
        if not fields:
            return [PreviewBlock(kind="empty", title=f"Actor {doc.name}")]
        return [PreviewBlock(kind="fields", title=f"Actor {doc.name}", fields=fields)]


class UseCaseKind(KindBase):
    api_version = "github.com/ruinosus/dna/v1"
    kind = "UseCase"
    alias = "helix-usecase"
    model = TypedUseCase
    origin = "github.com/ruinosus/dna/usecase"
    storage = StorageDescriptor.yaml("use_cases")
    graph_style = {"fill": "#F59E0B", "stroke": "#D97706", "text_color": "#fff"}
    ascii_icon = "📋"
    display_label = "UseCases"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    ui_schema = {
        "primary_actor": {"widget": "text", "label": "Primary actor", "help": "Name of the Actor doc that initiates this use case.", "order": 10},
        "supporting_actors": {"widget": "tags", "label": "Supporting actors", "order": 20},
        "agents": {"widget": "tags", "label": "Agents", "help": "Agents that fulfill this use case.", "order": 30},
        "soul": {"widget": "text", "label": "Soul", "help": "Name of the Soul that shapes the tone of this flow. Optional — if set, overrides the agent's soul for this use case scope.", "order": 40},
        "skills": {"widget": "tags", "label": "Skills", "help": "Skills required by the agents to fulfill this use case.", "order": 50},
        "tools": {"widget": "tags", "label": "Tools", "help": "Tools the agents invoke during this use case.", "order": 60},
        "guardrails": {"widget": "tags", "label": "Guardrails", "help": "Guardrails that apply specifically to this use case.", "order": 70},
        "preconditions": {"widget": "list-markdown", "label": "Preconditions", "order": 80},
        "main_flow": {"widget": "list-markdown", "label": "Main flow", "help": "Ordered steps describing the happy path.", "order": 90},
        "alternate_flows": {"widget": "readonly", "label": "Alternate flows", "help": "Named deviations. Nested object; edit in YAML.", "order": 100},
        "postconditions": {"widget": "list-markdown", "label": "Postconditions", "order": 110},
        "success_criteria": {"widget": "list-markdown", "label": "Success criteria", "order": 120},
    }
    docs = (
        "A UseCase is a UML-canonical use case: a goal-oriented interaction "
        "between actors and the system. It composes one primary actor, "
        "supporting actors, and the agents that fulfill the goal. Use cases "
        "carry preconditions, a main flow of steps, alternate flows, "
        "postconditions, and success criteria. Not a prompt target — purely "
        "declarative composition/documentation. Stored as a flat yaml file "
        "under use_cases/<name>.yaml."
    )

    def dep_filters(self) -> dict[str, str] | None:
        return {
            "primary_actor":     "helix-actor",
            "supporting_actors": "helix-actor",
            "agents":            "helix-agent",
            "soul":              "soulspec-soul",
            "skills":            "agentskills-skill",
            "tools":             "helix-tool",
            "guardrails":        "guardrails-guardrail",
        }

    def schema(self) -> dict[str, Any] | None:
        return _schema_from_model(self.model)

    def parse(self, raw: dict[str, Any]) -> Any:
        return TypedUseCase.from_raw(raw)

    def summary(self, doc: Any) -> dict[str, Any] | None:
        return None

    def preview(self, doc: Any) -> list[PreviewBlock]:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        fields: list[dict[str, str]] = []
        if isinstance(spec_dict.get("primary_actor"), str):
            fields.append({"label": "primary_actor", "value": spec_dict["primary_actor"]})
        for f in ("supporting_actors", "agents", "skills", "tools", "guardrails"):
            arr = spec_dict.get(f)
            if isinstance(arr, list) and arr:
                fields.append({"label": f, "value": ", ".join(str(x) for x in arr)})
        for label, key, prefix in [
            ("preconditions", "preconditions", "• "),
            ("main_flow", "main_flow", None),
            ("success_criteria", "success_criteria", "• "),
        ]:
            arr = spec_dict.get(key)
            if isinstance(arr, list) and arr:
                if prefix is None:
                    body = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(arr))
                else:
                    body = "\n".join(f"{prefix}{s}" for s in arr)
                fields.append({"label": label, "value": body})
        if not fields:
            return [PreviewBlock(kind="empty", title=f"UseCase {doc.name}")]
        return [PreviewBlock(kind="fields", title=f"UseCase {doc.name}", fields=fields)]


_BINARY_EXTENSIONS = {".tar", ".gz", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".wasm", ".bin", ".exe", ".so", ".dylib"}
_KNOWN_DIRS = {"scripts", "references", "assets"}

# AGENT.md frontmatter passthrough allowlist.
#
# Derived from ``AgentSpec`` so adding a field to the dataclass
# automatically opens it in the reader and writer — no separate
# allowlist to keep in sync. Two recurring bugs (``shell_sandbox`` in
# 2026-05-08, ``codegraph``/``tool_groups``/``tests`` shortly after)
# were caused by exactly that drift.
#
# ``instruction`` is excluded: the reader fills it from the AGENT.md
# body (or via ``instruction_file`` resolution), never from a top-level
# frontmatter key. Allowing it here would let an authoring mistake
# (frontmatter ``instruction:``) silently shadow the body.
_SPEC_FIELDS: frozenset[str] = frozenset(
    f.name for f in dataclasses.fields(AgentSpec) if f.name != "instruction"
)


def _read_text_safe(path: Path) -> str | None:
    if any(path.name.endswith(ext) for ext in _BINARY_EXTENSIONS):
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, ValueError):
        return None


def _collect_dir(directory: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for f in sorted(directory.rglob("*")):
        if f.is_file():
            text = _read_text_safe(f)
            if text is not None:
                rel = str(f.relative_to(directory))
                files[rel] = text
    return files


def _collect_bundle_subdir(bundle: "BundleHandle", dir_name: str) -> dict[str, str]:
    """Collect all text files under a named subdirectory in a BundleHandle."""
    files: dict[str, str] = {}
    prefix = dir_name + "/"
    for entry in bundle.iter_entries(recursive=True):
        if not entry.startswith(prefix):
            continue
        rel = entry[len(prefix):]
        fname = entry.split("/")[-1]
        if any(fname.endswith(ext) for ext in _BINARY_EXTENSIONS):
            continue
        try:
            text = bundle.read_text(entry)
            files[rel] = text
        except (UnicodeDecodeError, ValueError):
            pass
    return files


def _resolve_instruction_file(bundle: BundleHandle, rel: str) -> str:
    """Resolve an instruction_file reference WITHIN the bundle.

    Phase 8 (Option A): bundles are atomic. ``instruction_file`` must
    point at an entry inside the same bundle — no ``..`` segments, no
    absolute paths. This keeps bundles portable across any Source
    backend (filesystem, Postgres, S3) without the reader needing to
    cross bundle boundaries.

    Migration note: agents that previously referenced shared prompts
    via ``../../programs/.../prompts/x.md`` should copy or symlink the
    prompt into their own bundle and reference the local name.

    Rules:
      - Must be a relative POSIX path with no parent-traversal (``..``).
      - Must not be absolute (no leading ``/`` or Windows drive prefix).
      - Resolved entry must exist and be UTF-8 text.
    """
    if not isinstance(rel, str) or not rel:
        raise ValueError("instruction_file must be a non-empty string")
    if rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        raise ValueError(f"instruction_file must be a relative path, got {rel!r}")
    normalized = posixpath.normpath(rel)
    if normalized.startswith("..") or "/.." in normalized:
        raise ValueError(
            f"instruction_file must stay within the bundle (no '..' allowed): {rel!r}. "
            f"Phase 8 made bundles atomic — copy or symlink the referenced file "
            f"into the bundle and update the reference to a local name."
        )
    if not bundle.exists(normalized):
        raise FileNotFoundError(
            f"bundle '{bundle.name}': instruction_file entry not found: {normalized!r}"
        )
    return bundle.read_text(normalized)


class AgentReader(ReaderPort):
    """Detects and reads AGENT.md bundles."""

    def detect(self, bundle: BundleHandle) -> bool:
        return bundle.exists("AGENT.md")

    def read(self, bundle: BundleHandle) -> dict[str, Any]:
        agent_md = bundle.read_text("AGENT.md")
        fm = self._parse_frontmatter(agent_md)
        name = fm.get("name", bundle.name)
        description = fm.get("description", "")
        labels = fm.get("labels", {})

        body = re.sub(r"^---\n.*?---\n?", "", agent_md, flags=re.DOTALL).strip()

        # instruction_file resolution — must occur BEFORE treating body as instruction.
        instruction_file = fm.get("instruction_file")
        if instruction_file is not None:
            # Mutual-exclusion: reject frontmatter `instruction:` (legacy).
            if fm.get("instruction"):
                raise ValueError(
                    f"bundle '{bundle.name}': cannot set both frontmatter 'instruction' and "
                    f"'instruction_file' (instruction_file={instruction_file!r})"
                )
            if body:
                raise ValueError(
                    f"bundle '{bundle.name}': cannot set both AGENT.md body and instruction_file "
                    f"(instruction_file={instruction_file!r}, body_len={len(body)})"
                )
            # Phase 8 Option A: instruction_file must stay inside the bundle —
            # no escape hatch needed; same code path works for any Source backend.
            instruction_content = _resolve_instruction_file(bundle, instruction_file)
            spec: dict[str, Any] = {"instruction": instruction_content}
        else:
            spec = {"instruction": body}
        for field in _SPEC_FIELDS:
            if field in fm:
                spec[field] = fm[field]

        for dir_name in _KNOWN_DIRS:
            if bundle.exists(dir_name):
                files = _collect_bundle_subdir(bundle, dir_name)
                if files:
                    spec[dir_name] = files

        extras: dict[str, dict[str, str]] = {}
        for entry in sorted(bundle.iter_entries()):
            if bundle.is_file(entry) or entry in _KNOWN_DIRS:
                continue
            files = _collect_bundle_subdir(bundle, entry)
            if files:
                extras[entry] = files
        if extras:
            spec["extras"] = extras

        root_files: dict[str, str] = {}
        for entry in sorted(bundle.iter_entries()):
            if not bundle.is_file(entry) or entry == "AGENT.md":
                continue
            if any(entry.endswith(ext) for ext in _BINARY_EXTENSIONS):
                continue
            try:
                text = bundle.read_text(entry)
                root_files[entry] = text
            except (UnicodeDecodeError, ValueError):
                pass
        if root_files:
            spec["root_files"] = root_files

        metadata: dict[str, Any] = {"name": name, "description": description}
        if labels:
            metadata["labels"] = labels

        return {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": metadata,
            "spec": spec,
        }

    def _parse_frontmatter(self, text: str) -> dict[str, Any]:
        match = re.match(r"^---\n(.*?)---\n?", text, re.DOTALL)
        if not match:
            return {}
        return yaml.safe_load(match.group(1)) or {}


class AgentWriter(WriterPort):
    """Writes a Agent raw dict back to an AGENT.md bundle directory.

    ``write`` delegates to ``serialize`` (via ``_entries``) so both
    surfaces cannot drift — the WriterPort coherence contract enforced by
    the round-trip conformance suite (s-dna-rw-roundtrip-suite).
    """

    def can_write(self, raw: dict) -> bool:
        return raw.get("kind") == "Agent"

    def _entries(self, raw: dict, default_name: str) -> list[dict[str, Any]]:
        spec = raw.get("spec", {})
        meta = raw.get("metadata", {})
        entries: list[dict[str, Any]] = []

        fm: dict[str, Any] = {}
        fm["name"] = meta.get("name", default_name)
        if meta.get("description"):
            fm["description"] = meta["description"]
        if meta.get("labels"):
            fm["labels"] = meta["labels"]
        for field in _SPEC_FIELDS:
            if field in spec and spec[field]:
                fm[field] = spec[field]

        frontmatter = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
        # When instruction_file is set, the body is owned by the fragment file.
        # Do NOT bake spec.instruction into the body — it would duplicate content.
        if spec.get("instruction_file"):
            body = ""
        else:
            body = spec.get("instruction", "")
        entries.append({
            "relativePath": "AGENT.md",
            "content": f"---\n{frontmatter}---\n\n{body}",
        })

        # s-sync-s3 — emit the instruction_file FRAGMENT so the bundle is
        # self-contained in ANY source. Previously the writer left body="" and
        # never wrote instruction.md, assuming the fragment pre-existed — which
        # silently zeroed the instruction when writing to a fresh bundle (the
        # i-061 root). save_document persists whatever the writer emits in ONE
        # transaction, so emitting it here makes the doc+fragment atomic for
        # EVERY write path (CLI, kinds-api PUT, direct). Source: the carried
        # source_files entry, else the resolved inline instruction.
        instruction_file = spec.get("instruction_file")
        source_files = spec.get("source_files") or {}
        if instruction_file:
            frag = source_files.get(instruction_file)
            if frag is None:
                frag = spec.get("instruction")
            if frag is not None:
                if isinstance(frag, (bytes, bytearray)):
                    entries.append({
                        "relativePath": instruction_file,
                        "content_bytes": bytes(frag),
                    })
                else:
                    entries.append({
                        "relativePath": instruction_file, "content": frag,
                    })

        # s-sync-s3 — persist any remaining carried bundle entries (binary
        # assets like fonts/images, scripts/, references/). Text as content,
        # binary as content_bytes; the marker + instruction_file are already done.
        for rel, content in source_files.items():
            if rel in ("AGENT.md", instruction_file):
                continue
            if isinstance(content, (bytes, bytearray)):
                entries.append({
                    "relativePath": rel, "content_bytes": bytes(content),
                })
            else:
                entries.append({"relativePath": rel, "content": content})

        for dir_name in ("scripts", "references", "assets"):
            files = spec.get(dir_name, {})
            if isinstance(files, dict) and files:
                for fname, fcontent in files.items():
                    entries.append({
                        "relativePath": f"{dir_name}/{fname}", "content": fcontent,
                    })

        for dir_name, dir_files in spec.get("extras", {}).items():
            if isinstance(dir_files, dict):
                for fname, fcontent in dir_files.items():
                    entries.append({
                        "relativePath": f"{dir_name}/{fname}", "content": fcontent,
                    })

        for fname, fcontent in spec.get("root_files", {}).items():
            entries.append({"relativePath": fname, "content": fcontent})

        return entries

    def serialize(self, raw: dict) -> list[dict[str, Any]]:
        """Twin of typescript AgentWriter.serialize — name falls back to
        ``""`` (no bundle context here; write() uses the bundle name)."""
        return self._entries(raw, "")

    def write(self, bundle: BundleHandle, raw: dict) -> None:
        from dna.kernel.writer_helpers import write_entries_to_handle
        write_entries_to_handle(bundle, self._entries(raw, bundle.name))


from dna.kernel.composition_resolver import (
    CompositionProfile,
    CompositionSlot,
    HealthCheckHint,
    QuadrantHint,
    TimelineHint,
)

HELIX_PROFILE = CompositionProfile(
    orchestrator_alias="helix-agent",
    label="Helix Agent",
    slots=(
        CompositionSlot(
            name="soul",
            target_alias="soulspec-soul",
            cardinality="one",
            order=1,
            filterable=False,
            timeline=TimelineHint(label="Soul", item_label="personality loaded"),
            health_check=HealthCheckHint(
                rule="at-least-one",
                severity="warn",
                issue_key="agents_without_soul",
                message="Agent has no soul",
            ),
        ),
        CompositionSlot(
            name="skills",
            target_alias="agentskills-skill",
            cardinality="many",
            order=2,
            filterable=True,
            timeline=TimelineHint(label="Skills", item_label="instruction loaded"),
            quadrant=QuadrantHint(axis="x", label="Few Skills --> Many Skills", max_scale=15),
        ),
        CompositionSlot(
            name="guardrails",
            target_alias="guardrails-guardrail",
            cardinality="many",
            order=3,
            filterable=True,
            timeline=TimelineHint(label="Guardrails", item_label="rules applied"),
            health_check=HealthCheckHint(
                rule="at-least-one",
                severity="warn",
                issue_key="agents_without_guardrails",
                message="Agent has no guardrails",
            ),
            quadrant=QuadrantHint(axis="y", label="Few Guardrails --> Many Guardrails", max_scale=10),
        ),
        CompositionSlot(
            name="tools",
            target_alias="helix-tool",
            cardinality="many",
            order=4,
        ),
        CompositionSlot(
            name="actors",
            target_alias="helix-actor",
            cardinality="many",
            order=5,
        ),
    ),
)


class HelixExtension:
    name = "helix"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        # Phase 16 cleanup — ModuleKind class deleted. GenomeKind is
        # the canonical root identity Kind. Externally authored
        # manifests with ``kind: Module`` no longer parse — they need
        # to migrate to ``kind: Genome``.
        kernel.kind(GenomeKind())
        kernel.kind(LayerPolicyKind())
        kernel.kind(AgentKind())
        kernel.kind(ActorKind())
        kernel.kind(UseCaseKind())
        # Tool (helix-tool) ships as a descriptor — kinds/tool.kind.yaml
        # (f-dna-tools-as-data / s-tool-kind-descriptor). It WAS a
        # hand-written ToolKind class; migrated to a record-plane descriptor
        # per the repo's own ratchet (record Kinds are data, not classes).
        for raw in load_descriptors("dna.extensions.helix"):
            kernel.kind_from_descriptor(raw)
        # 2026-05-26 — absorbed from claude-code-templates catalog (MIT).
        # Setting rounds out the Claude-Code-customization primitives that
        # live alongside Skill / UA / Soul / Tool.
        from dna.extensions.helix._extras import (
            SettingKind, ThemeKind,
            UserProfileKind, CanvasKind,
        )
        kernel.kind(SettingKind())
        kernel.kind(ThemeKind())
        kernel.kind(UserProfileKind())
        # s-jarvis-canvas (2026-05-27) — shared whiteboard JARVIS ↔ user.
        kernel.kind(CanvasKind())
        kernel.reader(AgentReader())
        kernel.writer(AgentWriter())
        kernel.composition_profile(HELIX_PROFILE)
        # s-write-path-despecialize — Agent write rules (platform-agent
        # fork guard, prompt-budget, Kind-Writer contract) are pre_save VETO
        # hooks owned by this extension, not kernel special-cases.
        from dna.extensions.helix.write_guards import (
            register_write_guards,
        )
        register_write_guards(kernel)
