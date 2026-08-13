"""What the kernel itself must be able to parse — and nothing else.

This file used to hold 17 ``Typed*`` classes: the parsed shape of Agent, Skill,
Soul, Guardrail, SafetyPolicy, Recognizer, Hook, Genome, LayerPolicy and the
rest. Eleven extension files imported them back OUT of the kernel to register
the very Kinds those classes describe, so the dependency ran the wrong way:
``README.md`` and ``AGENTS.md`` promise "a microkernel that itself knows no
Kinds (extensions register them)", and a kernel carrying fourteen Kind schemas
did not keep that promise.

i-109 inverted the eleven edges. Each ``Typed*`` now lives in the extension that
REGISTERS its Kind — ``extensions/helix/models.py``,
``extensions/agentskills/models.py``, ``extensions/soulspec/models.py``, and so
on — and the extension imports :class:`Metadata` from here rather than its own
schema.

**Two things stay, and each has a reason:**

* :class:`Metadata` — generic envelope structure, not Kind knowledge. Every
  instance of every Kind has a ``metadata:`` block with these six fields; the
  kernel reads ``metadata.name`` to address an instance at all. :class:`FileEntry`
  is the same category (a named file inside a bundle).

* :class:`KindDefinitionSpec` / :class:`TypedKindDefinition` — **bootstrap**.
  A Kind is BORN from a ``KindDefinition``: ``kernel/kinds/registry.py`` parses
  one to synthesize a ``DeclarativeKindPort``, ``kernel/meta.py`` builds the port
  from it, and ``kernel/write/namespace_gate.py`` gates writes of one. Moving it
  to ``extensions/kinddef`` would make the kernel import from an extension to
  learn what a Kind is — the same inverted edge, only worse, because this one
  really is circular. It is the same nature as the three names already held by
  ``protocols.py::BOOTSTRAP_KIND_NAMES``; ``extensions/kinddef`` continuing to
  import from here is therefore correct, and the odd one out on purpose.

  ⚠️ ``Genome`` and ``LayerPolicy`` are in ``BOOTSTRAP_KIND_NAMES`` too and
  still moved to ``extensions/helix``. That list is a LOAD ORDER of Kind
  *names*; the kernel never imported ``TypedGenome`` or ``TypedLayerPolicy``, so
  nothing about bootstrap needed their schemas. Being bootstrap is not, by
  itself, an argument for living here — being parsed BY the kernel is.

Each Typed class has ``.metadata`` (Metadata) and ``.spec`` (a ``*Spec``).
``Instance`` delegates ``doc.metadata`` / ``doc.spec`` to these when available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

@dataclass
class Metadata:
    """Typed metadata common to all kinds."""
    name: str = ""
    description: str = ""
    version: str = ""
    icon: str = ""
    group: str = ""
    labels: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> Metadata:
        return cls(
            name=raw.get("name", ""),
            description=raw.get("description", ""),
            version=raw.get("version", ""),
            icon=raw.get("icon", ""),
            group=raw.get("group", ""),
            labels=raw.get("labels") or {},
        )


@dataclass
class FileEntry:
    """A file within a bundle (scripts/, references/, assets/)."""
    name: str
    content: str



# ---------------------------------------------------------------------------
# KindDefinition (github.com/ruinosus/dna/core/v1)
#
# Meta-kind: instances of this kind declaratively define *new* kinds. At
# kernel load time the kernel performs a 2-phase parse — KindDefinitions
# are parsed first, then each is wrapped in a DeclarativeKindPort and
# registered on the kernel. Regular instances are parsed in the second
# phase and can therefore reference these newly registered kinds.
# ---------------------------------------------------------------------------


def _coerce_post_save_event(raw: Any) -> str | tuple[str, str] | None:
    """Normalize ``spec.post_save_event`` from a descriptor (i-107).

    YAML has no tuples, so a declared ``[create, update]`` pair arrives as a
    ``list``; it becomes a tuple here so the class path and the descriptor path
    hand the same shape to ``event_type_for_port``. Anything else normalizes to
    ``None`` — the generic event pair — rather than raising: the JSON-schema
    gate on the descriptor already refuses malformed declarations at the write
    boundary, and this loader also runs over rows already on disk, where
    raising would make one bad row unloadable instead of merely unremarkable.
    """
    if raw is None or isinstance(raw, str) and not raw:
        return None
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        create, update = raw
        if isinstance(create, str) and isinstance(update, str):
            return (create, update)
    return None


@dataclass
class KindDefinitionSpec:
    target_api_version: str = ""
    target_kind: str = ""
    alias: str = ""
    origin: str = ""
    is_root: bool = False
    prompt_target: bool = False
    flatten_in_context: bool = False
    schema: dict[str, Any] = field(default_factory=dict)
    docs: str | None = None
    storage: dict[str, Any] = field(default_factory=dict)
    dep_filters: dict[str, str] | None = None
    default_agent: str | None = None
    # Schema fragment composition (Story s-workitem-common-schema-fragment
    # re-scoped 2026-05-12). Open-extension primitive: list of namespaced
    # fragment IDs (e.g. ["sdlc/workitem-common", "medical/care-pathway"]).
    # Any extension can register fragments via kernel.register_schema_fragment(id, dict).
    # DeclarativeKindPort merges them in order; later fragments + Kind-specific
    # properties win over earlier ones.
    schema_fragments: list[str] | None = None
    # Back-compat shorthand: workitem_common: true is treated as
    # schema_fragments: ["sdlc/workitem-common"]. Deprecated; new code should
    # use schema_fragments explicitly.
    workitem_common: bool = False
    # UI hints — read by DeclarativeKindPort.__init__ from raw spec.
    graph_style: dict[str, str] | None = None
    ascii_icon: str | None = None
    display_label: str | None = None
    # ---- F3 descriptor fields (spec 2026-06-10-kinds-descriptor-f3, D2) ----
    # These close the gap between hand-written Kind classes and the
    # declarative descriptor so builtin record Kinds can be expressed as
    # `.kind.yaml` package data. Defaults preserve today's behavior.
    #
    # ``plane``: "composition" | "record".
    #
    # ⚠️ NÃO espelha mais ``KindBase.plane`` — i-123 separou os dois. O default
    # do DESCRITOR é ``record`` (a decisão do fundador, com o 48-em-49 escrito
    # em :func:`~dna.kernel.kinds.base.default_plane`); o da CLASSE segue
    # ``composition``, porque ~26 Kinds internos dependem dele e a decisão foi
    # sobre o Kind de tenant, que sempre chega por descritor.
    #
    # Este literal é o default de um ``KindDefinitionSpec`` construído à mão, o
    # que nenhum caminho de produção faz — ``from_raw`` é o único construtor, e
    # lá o default é ``default_plane(raw)``, que olha os sinais de composição
    # antes de responder. Fica igual a ele no caso comum (descritor sem sinal)
    # para que os dois não digam coisas diferentes sobre a mesma pergunta.
    plane: str = "record"
    # ``tenant_scope``: "tenanted" | "global" — mirrors TenantScope.
    # Default "tenanted" matches the documented TenantScope default, BUT the
    # port only sets ``scope`` when explicitly declared (see
    # ``tenant_scope_declared``) — undeclared kinds stay permissive
    # (Phase 1 back-compat, see Kernel._kind_scope).
    tenant_scope: str = "tenanted"
    # Internal: True iff ``tenant_scope`` was explicitly present in the raw
    # spec. NOT a user-facing field.
    tenant_scope_declared: bool = False
    # ``summary``: declarative list-endpoint projection — {field: default}.
    # List form ["a", "b"] is normalized in from_raw to a dict with
    # per-schema-type defaults (array→[], boolean→False,
    # number/integer→None, else ""). None = no projection (today's None).
    summary: dict[str, Any] | None = None
    # ``embed``: source fields for embedding text (feeds D4 derivation).
    embed: list[str] | None = None
    # ``is_runtime_artifact``: docs generated by runtime workflows. The port
    # already read this via getattr but from_raw never populated it.
    is_runtime_artifact: bool = False
    # ``prompt_target_priority``: was hardcoded 5 in DeclarativeKindPort —
    # default 5 preserves that.
    prompt_target_priority: int = 5
    # Kernel classification flags — mirror KindBase defaults.
    scope_inheritable: bool = True
    is_overlayable: bool = True
    # ``post_save_event`` (i-107): the event_type this Kind emits on write.
    # str = one name for create AND update; (create, update) = one each;
    # None = the generic document_created/document_modified pair.
    post_save_event: str | tuple[str, str] | None = None
    # Extra volatile spec fields, unioned with KindBase.VOLATILE_SPEC_FIELDS.
    volatile_spec_fields: list[str] | None = None
    # ---- Descriptor expressiveness fields (spec 2026-06-11, D1/D3-D7) -------
    # All optional; absent → None preserves today's behavior. Consumed by
    # DeclarativeKindPort (kernel/meta.py).
    #
    # D1 ``ui``: raw StudioUIMetadata mapping. ``from_raw`` validates keys ⊆
    # StudioUIMetadata fields (strict — unknown key → ValueError); the port
    # reconstructs the real dataclass so the /kinds/manifest output is
    # byte-identical to the deleted class version.
    ui: dict[str, Any] | None = None
    # D3 ``describe``: template string ("{name} ({status})") OR projection
    # mapping ({"path": "description"}). The port renders the display string.
    describe: str | dict[str, Any] | None = None
    # D4 ``ui_schema``: pass-through widget-hint bag (field → {widget,...}).
    # Permissive — unknown keys allowed (this is an explicitly UI-owned bag,
    # unlike ``ui``). Exposed as ``port.ui_schema``.
    ui_schema: dict[str, Any] | None = None
    # D5 ``spec_defaults``: shallow-merge map applied as {**spec_defaults,
    # **spec} BEFORE schema validation in the port's parse().
    spec_defaults: dict[str, Any] | None = None
    # D6 ``default_agent_field``: spec field whose value is returned VERBATIM
    # by get_default_agent_name (no ``or None`` coercion).
    default_agent_field: str | None = None
    # D7 ``description_fallback_field``: pass-through string attr telling Studio
    # which spec field acts as the card description fallback.
    description_fallback_field: str | None = None
    # ``presentation``: how this Kind's DATA reads — the ordered field list,
    # each entry's human label and semantic role, plus the fields to hide. NOT
    # a layout; see ``dna.kernel.kinds.presentation`` for the line and why it
    # is held there. Stored NORMALIZED (a ``Presentation``): ``from_raw`` runs
    # the same validator a builtin descriptor goes through, so a
    # TENANT-authored Kind declaring it is neither second-class nor a second
    # code path — and a malformed declaration fails at LOAD rather than in
    # front of a user, on whichever surface happens to render it first.
    presentation: Any = None
    # ``overlayable_fields``: the per-FIELD refinement of ``is_overlayable`` —
    # which top-level spec keys a layer (a tenant overlay, a branch) may
    # CHANGE. Enforced by BOTH policy ports (the write port raises, the merge
    # port drops the key with a warning) and intersected with the operator's
    # LayerPolicy docs; see ``KindBase.OVERLAYABLE_FIELDS`` for the full
    # contract. Absent (None) = no per-field restriction, the default for
    # every Kind; an explicit ``[]`` forbids every field change. The port
    # exposes it as ``OVERLAYABLE_FIELDS``.
    overlayable_fields: list[str] | None = None
    # ---- Traits (the open participation vocabulary) ------------------------
    # What this Kind participates in — ``["sdlc.work-item"]``,
    # ``["memory.recallable"]``. Consumers ask ``kernel.kinds_with_trait(name)``
    # rather than carrying a literal Kind-name list. Open vocabulary: an
    # unregistered trait is legal (see dna.kernel.kinds.traits).
    traits: list[str] | None = None
    # ---- Relations (what this Kind POINTS AT) ------------------------------
    # First-class, so a relation is listable without walking properties, its
    # cardinality is declared rather than inferred from ``type: array``, and a
    # reciprocal pair can say that it IS one. Stored NORMALIZED (a
    # ``{name: Relation}`` mapping): ``from_raw`` runs the same validator a
    # builtin descriptor goes through, so a TENANT-authored Kind declaring
    # relations is neither second-class nor a second code path — the precedent
    # ``presentation`` set. Replaces ``x-dna-ref`` / ``x-dna-ref-composite``.
    relations: Any = None
    # ---- Identifiers (what this Kind points NOWHERE with) -----------------
    # The other half of ``relations``, and the half that makes the gap list
    # finite: a field whose NAME looks like a reference and which points at no
    # instance can finally SAY so — ``role: self`` (this instance's own key) or
    # ``role: external`` + ``system`` (minted outside DNA). Stored NORMALIZED,
    # through the same validator a builtin descriptor goes through, so a
    # tenant-authored Kind is neither second-class nor a second code path.
    identifiers: Any = None
    # ---- Parity fields (i-081): what a CLASS could say and a descriptor could
    # not. Seven attributes existed only on ``KindBase``, so a YAML-declared
    # Kind was structurally second-class: it could not invalidate the schema
    # cache, validate on parse, share a bundle marker, hide from the backend,
    # bound its version churn or name a prompt layout. Every one is optional
    # and defaults to today's behavior.
    #
    # ``is_schema_affecting``: a write of this Kind invalidates the schema
    # cache (Kernel._SCHEMA_INVALIDATING_KINDS). Refused on the record plane
    # by the same lint that refuses it for classes.
    is_schema_affecting: bool = False
    # ``is_catalog_identity``: a write of this Kind changes the Catalog tier's
    # scope/mandatory set, so the kernel drops its catalog cache after it.
    is_catalog_identity: bool = False
    # ``validate_on_parse``: parse() validates spec against schema() and raises
    # on a malformed doc (which the loader turns into a parse_error event).
    # NOTE the descriptor port ALREADY validates on parse whenever a schema is
    # declared; declaring this is therefore a statement of intent that the
    # ratchet + ``dna kind show`` can read, and it keeps class→descriptor
    # migrations lossless.
    validate_on_parse: bool = False
    # ``marker_shared_allowed``: this bundle Kind consents to sharing its
    # ``(container, marker)`` pair with another Kind that also consents.
    marker_shared_allowed: bool = False
    # ``visible_in_backend``: explicit override of the storage-pattern default
    # (protocols.resolve_visible_in_backend). Tri-state — None = derive.
    visible_in_backend: bool | None = None
    # ``version_retention``: how many version snapshots to keep for a
    # machine-churn Kind. None = the kernel's curated default.
    version_retention: int | None = None
    # ``layout_names``: the prompt layouts this Kind's instances may name
    # (``UnknownLayout`` lists them). Empty = no layouts, today's default.
    layout_names: list[str] | None = None
    # ---- Approval (the registration gate) + the audit's other half ----------
    # Who PROPOSED this Kind, who APPROVED it, who REVOKED it, and when each
    # happened. A KindDefinition that arrives from a STORE reaches the registry
    # according to its STATE (:func:`dna.kernel.kinds.approval.approval_state`)
    # — authoring a Kind, putting it into effect and withdrawing it are three
    # acts, and the audit is worth something only if each field carries the
    # verified identity of ITS OWN act.
    #
    # ``proposed_by`` is stamped where the proposal happens (the authoring
    # door), because it cannot be back-filled later onto an instance that never
    # recorded one. It is NOT a gate: the registry reads the state, and two
    # fields naming the same identity is legal (see the schema's note —
    # coincidence is a fact the audit reports, not an error).
    #
    # ``revoked_by`` is i-085's third state, and it is a stored field for a
    # measured reason: clearing ``approved_by`` is indistinguishable from never
    # having approved, and never-approved means UNREGISTERED, which means
    # instances are accepted with NO validation. Revoking must tighten, so the
    # fact has to persist. It is deliberately NOT read directly anywhere —
    # ``approval_state`` is the one reader, so no future caller can check
    # ``approved_by`` alone and treat a revoked Kind as approved.
    #
    # All six are pure data here: the registry writes none of them, so the
    # privileged path that may set them is a decision made where the writer is
    # authenticated, not in the kernel.
    proposed_by: str | None = None
    proposed_at: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    revoked_by: str | None = None
    revoked_at: str | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> KindDefinitionSpec:
        missing = [
            f for f in ("target_api_version", "target_kind", "alias", "origin", "storage")
            if not raw.get(f)
        ]
        if missing:
            raise ValueError(
                f"KindDefinition spec missing required fields: {', '.join(missing)}"
            )
        storage = raw.get("storage")
        if not isinstance(storage, dict):
            raise ValueError("KindDefinition spec.storage must be a dict")
        schema = raw.get("schema") or {}
        if not isinstance(schema, dict):
            raise ValueError("KindDefinition spec.schema must be a dict (JSON Schema)")
        # i-080 item 4 — the authored schema is validated HERE, at author time.
        # "Is it a dict" was the only check, so a schema that is not a schema
        # failed once PER INSTANCE at parse time through the fail-soft
        # parse_error channel — a log line far from the author. The guard also
        # refuses a non-local ``$ref`` (nothing resolves it at validation time,
        # and the error it raises is NOT a ValidationError, so it escapes the
        # write path's handler) and a ``pattern`` with measured catastrophic
        # backtracking. ``SchemaGuardError`` subclasses ``ValueError``, so both
        # funnels keep their contract: builtin descriptors raise at boot,
        # per-scope KindDefinitions warn + skip.
        from dna.kernel.kinds.schema_guard import validate_authored_schema

        try:
            validate_authored_schema(schema)
        except ValueError as e:
            raise ValueError(f"KindDefinition spec.schema {e}") from e
        # ---- F3 fields (spec D2) ----------------------------------------
        # i-123 — o default do descritor é ``record``, e ele é COMPUTADO em
        # ``default_plane`` em vez de ser um literal aqui: a razão (48 de 49) e
        # a ressalva (os quatro sinais de composição) moram juntas com a lista
        # de sinais que o lint do registry usa, e não em dois arquivos.
        #
        # ``raw.get("plane")`` e não ``raw.get("plane", ...)``: um ``plane:
        # null`` explícito conta como NÃO DECLARADO, que é o que ele é — e o
        # `author_kind` grava a chave só quando declarada, justamente para que
        # "escolheu" e "nunca foi perguntado" continuem distinguíveis no dado.
        from dna.kernel.kinds.base import default_plane

        declared_plane = raw.get("plane")
        plane = default_plane(raw) if declared_plane is None else declared_plane
        if plane not in ("composition", "record"):
            raise ValueError(
                f"KindDefinition spec.plane must be 'composition' or 'record', got {plane!r}"
            )
        tenant_scope = raw.get("tenant_scope", "tenanted")
        if tenant_scope not in ("tenanted", "global"):
            raise ValueError(
                f"KindDefinition spec.tenant_scope must be 'tenanted' or 'global', "
                f"got {tenant_scope!r}"
            )
        summary = cls._normalize_summary(raw.get("summary"), schema)
        # ---- Descriptor expressiveness validation (spec D1/D3/D4) -----------
        ui = raw.get("ui")
        if ui is not None:
            if not isinstance(ui, dict):
                raise ValueError(
                    "KindDefinition spec.ui must be a mapping of "
                    f"StudioUIMetadata fields, got {type(ui).__name__}"
                )
            # Single source of truth: the allowed key set IS StudioUIMetadata's
            # dataclass fields — never hardcode a second list (D1).
            from dna.kernel.studio_ui import StudioUIMetadata

            allowed = set(StudioUIMetadata.__dataclass_fields__)
            unknown = set(ui) - allowed
            if unknown:
                raise ValueError(
                    "KindDefinition spec.ui has unknown key(s): "
                    f"{', '.join(sorted(unknown))} "
                    f"(allowed: {', '.join(sorted(allowed))})"
                )
        describe = raw.get("describe")
        if describe is not None and not isinstance(describe, (str, dict)):
            raise ValueError(
                "KindDefinition spec.describe must be a template string or a "
                f"{{path}} mapping, got {type(describe).__name__}"
            )
        ui_schema = raw.get("ui_schema")
        if ui_schema is not None and not isinstance(ui_schema, dict):
            raise ValueError(
                "KindDefinition spec.ui_schema must be a mapping, "
                f"got {type(ui_schema).__name__}"
            )
        spec_defaults = raw.get("spec_defaults")
        if spec_defaults is not None and not isinstance(spec_defaults, dict):
            raise ValueError(
                "KindDefinition spec.spec_defaults must be a mapping, "
                f"got {type(spec_defaults).__name__}"
            )
        overlayable_fields = raw.get("overlayable_fields")
        if overlayable_fields is not None and (
            not isinstance(overlayable_fields, list)
            or not all(isinstance(f, str) for f in overlayable_fields)
        ):
            raise ValueError(
                "KindDefinition spec.overlayable_fields must be a list of "
                f"spec field names, got {type(overlayable_fields).__name__}"
            )
        # ``presentation`` — normalized THROUGH the shared validator, never
        # copied through. One reading of the declaration for a builtin
        # descriptor and a tenant instance alike; a second, laxer parse here
        # would be exactly the drift this whole field exists to end. The error
        # is re-raised naming the field so a tenant reads which key of their
        # own instance is wrong.
        from dna.kernel.kinds.presentation import normalize_presentation

        try:
            presentation = normalize_presentation(raw.get("presentation"))
        except ValueError as e:
            raise ValueError(f"KindDefinition spec.presentation — {e}") from e
        from dna.kernel.kinds.traits import normalize_traits

        try:
            traits = sorted(normalize_traits(raw.get("traits")))
        except ValueError as e:
            raise ValueError(f"KindDefinition spec.traits {e}") from e
        # ``relations`` — normalized THROUGH the shared validator, then checked
        # against the schema the SAME from_raw just accepted. This is the one
        # place both halves are in hand, so it is the one place the
        # contradiction "relation `stories` is many, property `stories` is a
        # string" can be caught at all; a registry-wide lint catches the class
        # Kinds, which have no from_raw.
        from dna.kernel.kinds.relations import (
            normalize_relations,
            schema_contradictions,
        )

        try:
            relations = normalize_relations(raw.get("relations"))
        except ValueError as e:
            raise ValueError(f"KindDefinition spec.{e}") from e
        contradictions = schema_contradictions(
            relations, schema,
            # A descriptor pulling in schema_fragments is looking at an
            # INCOMPLETE schema here — the port merges them later — so a
            # relation naming a fragment-supplied property is not a
            # contradiction, it is a property this function cannot see.
            partial=bool(raw.get("schema_fragments") or raw.get("workitem_common")),
        )
        if contradictions:
            raise ValueError(
                "KindDefinition spec.relations contradicts spec.schema: "
                + "; ".join(contradictions)
            )
        # ``identifiers`` — the other half: fields that point NOWHERE and say
        # so. Normalized through ITS shared validator, and checked here for the
        # contradiction only this function can see, because it holds the schema
        # AND the relations at once: a field declared as both a relation and an
        # identifier is two mechanisms answering one question, which is the
        # disease ``relations`` was written to cure.
        from dna.kernel.kinds.identifiers import (
            normalize_identifiers,
            schema_contradictions as identifier_contradictions,
        )

        try:
            identifiers = normalize_identifiers(raw.get("identifiers"))
        except ValueError as e:
            raise ValueError(f"KindDefinition spec.{e}") from e
        id_problems = identifier_contradictions(
            identifiers, relations, schema,
            partial=bool(raw.get("schema_fragments") or raw.get("workitem_common")),
        )
        if id_problems:
            raise ValueError(
                "KindDefinition spec.identifiers contradicts the declaration: "
                + "; ".join(id_problems)
            )
        layout_names = raw.get("layout_names")
        if layout_names is not None and (
            not isinstance(layout_names, list)
            or not all(isinstance(f, str) for f in layout_names)
        ):
            raise ValueError(
                "KindDefinition spec.layout_names must be a list of layout "
                f"names, got {type(layout_names).__name__}"
            )
        version_retention = raw.get("version_retention")
        if version_retention is not None:
            if isinstance(version_retention, bool) or not isinstance(
                version_retention, int
            ):
                raise ValueError(
                    "KindDefinition spec.version_retention must be an integer "
                    f"count of snapshots, got {type(version_retention).__name__}"
                )
            if version_retention < 1:
                raise ValueError(
                    "KindDefinition spec.version_retention must be >= 1 "
                    f"(got {version_retention}); omit it to keep every version"
                )
        visible_in_backend = raw.get("visible_in_backend")
        if visible_in_backend is not None and not isinstance(visible_in_backend, bool):
            raise ValueError(
                "KindDefinition spec.visible_in_backend must be a boolean "
                f"(omit it to derive from storage), got "
                f"{type(visible_in_backend).__name__}"
            )
        return cls(
            target_api_version=raw["target_api_version"],
            target_kind=raw["target_kind"],
            alias=raw["alias"],
            origin=raw["origin"],
            is_root=bool(raw.get("is_root", False)),
            prompt_target=bool(raw.get("prompt_target", False)),
            flatten_in_context=bool(raw.get("flatten_in_context", False)),
            schema=schema,
            docs=raw.get("docs"),
            storage=storage,
            dep_filters=raw.get("dep_filters"),
            default_agent=raw.get("default_agent"),
            workitem_common=bool(raw.get("workitem_common", False)),
            schema_fragments=raw.get("schema_fragments"),
            graph_style=raw.get("graph_style"),
            ascii_icon=raw.get("ascii_icon"),
            display_label=raw.get("display_label"),
            # F3 (spec D2)
            plane=plane,
            tenant_scope=tenant_scope,
            tenant_scope_declared="tenant_scope" in raw,
            summary=summary,
            embed=raw.get("embed"),
            is_runtime_artifact=bool(raw.get("is_runtime_artifact", False)),
            prompt_target_priority=int(raw.get("prompt_target_priority", 5)),
            scope_inheritable=bool(raw.get("scope_inheritable", True)),
            is_overlayable=bool(raw.get("is_overlayable", True)),
            post_save_event=_coerce_post_save_event(raw.get("post_save_event")),
            volatile_spec_fields=raw.get("volatile_spec_fields"),
            # Descriptor expressiveness (spec D1/D3-D7)
            ui=ui,
            describe=describe,
            ui_schema=ui_schema,
            spec_defaults=spec_defaults,
            default_agent_field=raw.get("default_agent_field"),
            description_fallback_field=raw.get("description_fallback_field"),
            presentation=presentation,
            overlayable_fields=overlayable_fields,
            relations=relations,
            identifiers=identifiers,
            # Traits + class-parity fields (i-081)
            traits=traits or None,
            is_schema_affecting=bool(raw.get("is_schema_affecting", False)),
            is_catalog_identity=bool(raw.get("is_catalog_identity", False)),
            validate_on_parse=bool(raw.get("validate_on_parse", False)),
            marker_shared_allowed=bool(raw.get("marker_shared_allowed", False)),
            visible_in_backend=visible_in_backend,
            version_retention=version_retention,
            layout_names=layout_names,
            proposed_by=raw.get("proposed_by"),
            proposed_at=raw.get("proposed_at"),
            approved_by=raw.get("approved_by"),
            approved_at=raw.get("approved_at"),
            revoked_by=raw.get("revoked_by"),
            revoked_at=raw.get("revoked_at"),
        )

    @staticmethod
    def _normalize_summary(
        summary: Any, schema: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Normalize spec.summary to its dict form (F3 spec D2).

        Dict form ``{field: default}`` passes through. List form
        ``["a", "b"]`` gets a default per the field's declared type in
        ``schema.properties``: array→[], boolean→False,
        number/integer→None, anything else (incl. fields absent from the
        schema)→"".
        """
        if summary is None:
            return None
        if isinstance(summary, dict):
            return summary
        if isinstance(summary, list):
            props = schema.get("properties") or {}
            out: dict[str, Any] = {}
            for field_name in summary:
                prop = props.get(field_name)
                ptype = prop.get("type") if isinstance(prop, dict) else None
                if ptype == "array":
                    out[field_name] = []
                elif ptype == "boolean":
                    out[field_name] = False
                elif ptype in ("number", "integer"):
                    out[field_name] = None
                else:
                    out[field_name] = ""
            return out
        raise ValueError(
            "KindDefinition spec.summary must be a dict {field: default} or a "
            f"list of field names, got {type(summary).__name__}"
        )


@dataclass
class TypedKindDefinition:
    metadata: Metadata
    spec: KindDefinitionSpec

    API_VERSION = "github.com/ruinosus/dna/core/v1"
    KIND = "KindDefinition"

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> TypedKindDefinition:
        av = raw.get("apiVersion", cls.API_VERSION)
        if av != cls.API_VERSION:
            raise ValueError(
                f"TypedKindDefinition expects apiVersion={cls.API_VERSION!r}, got {av!r}"
            )
        kn = raw.get("kind", cls.KIND)
        if kn != cls.KIND:
            raise ValueError(
                f"TypedKindDefinition expects kind={cls.KIND!r}, got {kn!r}"
            )
        typed = cls(
            metadata=Metadata.from_raw(raw.get("metadata", {})),
            spec=KindDefinitionSpec.from_raw(raw.get("spec", {})),
        )
        # s-dna-kindport-descriptor-schema: AFTER the hand-rolled checks
        # (which own the didactic error messages), validate the effective
        # envelope against the published JSON Schema
        # (docs/schemas/kind-definition.schema.json) — the backstop that
        # catches typo'd/unknown spec fields and wrong types the
        # hand-rolled checks silently ignored. apiVersion/kind are folded
        # in with their defaults so partial raws keep working.
        from dna.kernel.kinds.schema import (
            validate_kind_definition,
        )
        validate_kind_definition({**raw, "apiVersion": av, "kind": kn})
        return typed
# ── DNA namespace ──────────────────────────────────────────────────────────
# Single authoritative namespace constant (spec §8: swapping the namespace
# is one commit + a golden regen). NOTE: literal-type positions
# (typing.Literal / schema literals / *.kind.yaml descriptors) must stay in
# sync with this value — the descriptor + parity suites enforce it.
DNA_NAMESPACE = "github.com/ruinosus/dna"
