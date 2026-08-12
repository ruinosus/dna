# Kinds & extensions — what behaviour DNA knows about

The kernel imports no extension. Every unit of identity and composition arrives through these ports, which is why adding a Kind never touches the core. (The kernel does NAME a small set of built-in Kinds in its own code — see Microkernel & ports for the measured extent and the guard that caps it.)

!!! info "Generated from the source"

    Names, signatures and docstrings are parsed out of `packages/sdk-py/dna`
    by `scripts/gen_ports_docs.py`. The prose around each contract is
    hand-written in `scripts/ports_prose.py`, and the generator **fails**
    if a port has none — so a new port cannot ship undocumented.

## Extension

`dna.kernel.protocols.Extension` · `@runtime_checkable` · :material-power-plug: **extension point**

The unit of packaging. One `register()` call contributes everything your extension adds; 21 ship in-tree, declared as entry points.

!!! quote "From the source"

    Registers kinds, readers, and writers on the Kernel.

    ``kernel.load(ext)`` fail-loud validates the whole contract before
    calling ``register()``: ``name`` must be a non-empty ``str``,
    ``version`` a ``str``, ``register`` callable (``ExtensionLoadError``
    otherwise). ``register()`` receives the registration-time host slice
    — see :class:`ExtensionHost` for the exact vocabulary.

    Optional capability (feature-tested, NOT a required Protocol member so
    legacy extensions predating Phase 0 keep working) — see
    :class:`TemplateProvider`:

        def templates(self) -> list[Template]: ...

    When present, ``Kernel.list_templates()`` aggregates entries from
    every loaded extension so UIs (Tauri Studio, CLI) can offer
    ``scaffold()`` for any extension-shipped file tree. See
    ``dna.kernel.compose.templates.Template`` for the payload shape.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `register` | <code>def register(self, kernel: 'ExtensionHost') -> None</code> |  |

**Swap it when** — You are shipping more than one Kind, or any Kind plus its reader/writer, or you want your Kinds discovered by installation rather than by import.

**The minimum that works** — `register(host)`. Declare it under the `dna.extensions` entry-point group and installing your package is all the wiring there is.

**What it lights up** — Auto-discovery at `Kernel.auto()`. The kernel validates every registration at boot and fails loud on conflicts — duplicate `(apiVersion, kind)`, duplicate aliases, a Reader missing a required method — so a broken extension stops boot rather than half-registering.

**How you prove it** — Boot `Kernel.auto()` and assert your Kinds are in `kernel.kind_ports()`. The 21 shipped extensions are the worked examples.

**Shipped implementations** — 21 in-tree extensions — helix, agentskills, soulspec, agentsmd, guardrails, kinddef, hooks, safety, recognizer, evidence, audit, collab, sdlc, federation, testkit, tenant, lesson, research, doc, modelreg — each declared under the `dna.extensions` entry-point group rather than subclassing anything

## ExtensionHost

`dna.kernel.protocols.ExtensionHost` · `@runtime_checkable` · :material-hand-extended: handed to you

The nine things you may do inside `Extension.register()`: register a Kind (from a class or a descriptor), a reader, a writer, a hook, a veto, a tool, a composition profile.

!!! quote "From the source"

    The registration-time surface the Kernel offers to ``Extension.register()``.

    This is the *explicit contract* of what an extension may call while it
    is being loaded (``s-dna-extension-host-contract``). It is a narrow
    slice of the Kernel — the registration vocabulary — NOT the whole
    Kernel API. Deriving it from actual usage across every builtin
    extension keeps it honest:

    ========================  =================================================
    Member                    What it registers
    ========================  =================================================
    ``kind(kp)``              a KindPort (identity + composition of a Kind)
    ``kind_from_descriptor``  a record Kind from a ``kinds/*.kind.yaml``
                              descriptor dict (F3 — Kinds as data). Pair it
                              with ``dna.kernel.source.descriptor_loader.
                              load_descriptors(package)`` to read the package
                              data files.
    ``reader(r)``             a ReaderPort (detect/scan a bundle format)
    ``writer(w)``             a WriterPort (write a bundle format)
    ``on(hook, fn)``          an event subscriber (e.g. ``post_save``)
    ``on_veto(hook, fn)``     a veto listener (e.g. ``pre_save`` write guards
                              — raising vetoes the operation)
    ``tool(td)``              a ToolDefinition (tool metadata)
    ``composition_profile``   a CompositionProfile (orchestrator kind wiring)
    ``hooks``                 the HookRegistry itself, for advanced listener
                              management (``kernel.hooks.on_veto(..., key=)``)
    ========================  =================================================

    The real ``Kernel`` satisfies this Protocol structurally (guarded by
    ``tests/test_extension_host_contract.py``). TS twin:
    ``ExtensionHost`` in ``src/kernel/protocols.ts``.

**You do not implement this — the kernel does.** The kernel implements it and passes it into your `register()`. You call these methods; you never satisfy this Protocol. It is on this page because it is the **menu** — everything an extension is allowed to contribute is in the table below, and nothing else is.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `hooks` | <code>def hooks(self) -> Any</code> |  |
| `kind` | <code>def kind(self, k: KindPort) -> None</code> |  |
| `kind_from_descriptor` | <code>def kind_from_descriptor(self, raw: dict[str, Any]) -> KindPort</code> |  |
| `reader` | <code>def reader(self, r: ReaderPort) -> None</code> |  |
| `writer` | <code>def writer(self, w: WriterPort) -> None</code> |  |
| `on` | <code>def on(self, hook: str, fn: Any) -> None</code> |  |
| `on_veto` | <code>def on_veto(self, hook: str, fn: Any, *, priority: int=..., key: str \| None=...) -> None</code> |  |
| `tool` | <code>def tool(self, td: ToolDefinition) -> None</code> |  |
| `composition_profile` | <code>def composition_profile(self, profile: Any) -> None</code> |  |

## KindPort

`dna.kernel.protocols.KindPort` · `@runtime_checkable` · :material-power-plug: **extension point**

Identity, schema and composition role for one Kind. The port that keeps Kind-specific behaviour OUT of the kernel — no extension is imported by the core, whatever it may name in a literal.

!!! quote "From the source"

    WHO — identity + composition role.

    This runtime_checkable Protocol lists ONLY the core contract every
    Kind must provide — it is exactly what the H1 registration gate
    (``kernel.kind`` → ``isinstance(k, KindPort)``) enforces.

    The optional presentation/UX surface (``docs``, ``ui_schema``,
    ``graph_style``, ``ascii_icon``, ``display_label``, ``presentation``,
    ``description_fallback_field``, ``visible_in_backend``,
    ``preview()``, ``graph_meta()``) lives on the separate
    ``KindPresentation`` capability Protocol below — declared there so
    it is typed + documented, but NEVER required by the isinstance
    check (s-dna-kindport-descriptor-schema).

    .. warning:: do NOT add optional members to THIS Protocol body.
       ``runtime_checkable`` isinstance checks member PRESENCE — a new
       member here silently breaks registration of every third-party
       Kind that doesn't declare it (the ``is_runtime_artifact``
       precedent — see test_port_contract.py). Optional surface goes
       on ``KindPresentation`` (or a new capability Protocol) instead.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `dep_filters` | <code>def dep_filters(self) -> dict[str, str] \| None</code> |  |
| `dependencies` | <code>def dependencies(self) -> dict[str, str] \| None</code> | Which spec fields reference other kinds by alias. |
| `schema` | <code>def schema(self) -> dict[str, Any] \| None</code> | JSON Schema for this kind's spec. |
| `get_default_agent_name` | <code>def get_default_agent_name(self, doc: Any) -> str \| None</code> |  |
| `get_layer_policies` | <code>def get_layer_policies(self, doc: Any) -> dict[str, dict[str, LayerPolicy]] \| None</code> |  |
| `parse` | <code>def parse(self, raw: dict[str, Any]) -> Any</code> |  |
| `describe` | <code>def describe(self, doc: Any) -> str \| None</code> |  |
| `summary` | <code>def summary(self, doc: Any) -> dict[str, Any] \| None</code> |  |
| `prompt_template` | <code>def prompt_template(self) -> str \| None</code> |  |

**Swap it when** — Only when your Kind needs custom behaviour — a bespoke bundle format, a typed parse step, a composition rule. A record-shaped Kind with none of that needs **no class at all**: write a `*.kind.yaml` descriptor and register it with `kind_from_descriptor()`. Reach for a class second, not first.

**The minimum that works** — `kind`, `alias`, `api_version`, `plane` and `schema()`. Everything else has a default.

**What it lights up** — Your Kind across every face at once — CLI, REST, MCP, the generic instance tools — because those faces are generic over the registry. It also enrols your Kind in [the generated Kinds reference](../kinds/index.md), so registering is what makes it documented.

**How you prove it** — Register it and let `scripts/gen_kinds_docs.py` and `scripts/docs_coverage_guard.py` run — the first proves the kernel sees it, the second fails the build until prose exists for it.

**Shipped implementations** — `KindBase` (`dna.kernel.kinds.base`) — the base every built-in Kind subclasses; third-party Kinds may satisfy the Protocol structurally instead

## KindPresentation

`dna.kernel.protocols.KindPresentation` · typing-only (not `@runtime_checkable`) · :material-power-plug: **extension point**

An optional slice of a Kind: the short preview a list renders, and the metadata a graph view needs.

!!! quote "From the source"

    Optional presentation/UX capability of a Kind (typing-only).

    Every member here is OPTIONAL at runtime: a Kind that provides none
    of them is still a perfectly valid ``KindPort`` (the H1 gate never
    requires them). This Protocol exists so the ~9 attrs/methods that
    used to live only in docstrings + ``hasattr`` duck-typing have an
    explicit, typed home (s-dna-kindport-descriptor-schema).

    Deliberately NOT ``@runtime_checkable`` and NOT part of
    ``KindPort``: ``runtime_checkable`` Protocols check member PRESENCE,
    so folding these into ``KindPort`` would make ``isinstance`` (the H1
    registration gate) reject every minimal third-party Kind — exactly
    the breakage the ``is_runtime_artifact`` addition caused once
    (see test_port_contract.py).

    Conventions:

    - ``KindBase`` provides defaults for all ATTRIBUTE members (None),
      so subclasses opt in field-by-field.
    - ``preview``/``graph_meta`` have no KindBase default — ABSENCE is
      meaningful (consumers fall back to the generic renderer).
    - Consumers read via typed access with a default —
      ``getattr(kp, "ascii_icon", None)`` /
      ``fn = getattr(kp, "preview", None)`` — never ``hasattr``.
    - Tracked in ``tests/golden-fixtures/port-surface.json`` (the
      ``KindPresentation`` port).

    Members:

    - ``docs`` — prose explanation of what this kind IS at the concept
      level. Surfaced by the harness ``describe_kind`` tool. When an
      extension ships a ``DOCS.md`` next to its package, the kernel's
      ``_load_kind_docs`` loader overrides this attribute at load time.
    - ``description_fallback_field`` — spec field to derive
      metadata.description from when none was declared. See
      ``Kernel._fill_derived_description``.
    - ``ui_schema`` — per-field UI hints for Studio form rendering,
      keyed by spec field name. Each entry may declare ``widget``
      (``text | textarea | markdown | markdown-toc | code | select |
      checkbox | list-markdown | tags | readonly``), ``label``,
      ``help``, ``language`` (for ``code``), ``height`` (px), ``order``.
      When absent, consumers infer the widget from the value type.
      See ``docs/KIND-UI-HINTS.md`` for the full contract.
    - ``graph_style`` — ``{"fill": "#F97316", "stroke": "#EA580C",
      "text_color": "#fff"}`` colors for mermaid/graph visualizations.
    - ``ascii_icon`` — single emoji/char for ASCII tree views.
    - ``display_label`` — human-friendly plural label (e.g. "Agents").
    - ``presentation`` — how this Kind's DATA reads, declared ONCE for every
      surface: an ordered field list, each entry carrying a human ``label``
      and an optional semantic ``role`` (``identifier``/``title``/``status``/
      ``owner``/``parent``/… — a closed vocabulary), plus the fields to keep
      ``hidden``. Deliberately NOT a layout — it says what a field MEANS, and
      each surface decides what that becomes on it (a table column, a state
      line, a badge). ``ui_schema`` is its sibling and NOT its twin: that one
      hints how a human EDITS a field (widget, help, height); this one says
      what the value means when a human READS it. Normalized + validated by
      ``dna.kernel.kinds.presentation`` (``presentation_of`` and the
      ``presentation_wire`` envelope, which composes it with ``display_label``
      and ``ascii_icon``). A TENANT Kind declares it in the very same words,
      as ``KindDefinition.spec.presentation``.
    - ``visible_in_backend`` — explicit backend-visibility override;
      ``None`` falls back to ``default_visible_in_backend(storage)``
      (see ``resolve_visible_in_backend``).
    - ``preview(doc)`` — renderable blocks for the Studio's preview
      pane; absent (or ``None`` result) → ``generic_spec_dump``.
    - ``graph_meta(doc)`` — per-doc annotations for graph rendering and
      health checks (e.g. Guardrail returns severity/scope/rules).

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `preview` | <code>def preview(self, doc: Any) -> 'list[PreviewBlock] \| None'</code> |  |
| `graph_meta` | <code>def graph_meta(self, doc: Any) -> dict[str, Any] \| None</code> |  |

**Swap it when** — Your Kind shows up in a UI and the default rendering is unhelpful.

**The minimum that works** — Either `preview` or `graph_meta`; both are optional.

**What it lights up** — Richer rendering in the console and graph views. Omitted, callers get the generic presentation — a real degradation, not a failure.

**How you prove it** — Covered by your Kind's own tests; there is no separate battery.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

## KindRelations

`dna.kernel.protocols.KindRelations` · typing-only (not `@runtime_checkable`) · :material-power-plug: **extension point**

The declared relations of a Kind — attribute-shaped, which is why it has no methods.

!!! quote "From the source"

    Optional relations capability of a Kind (typing-only).

    A sibling of :class:`KindPresentation` and deliberately not a member of it:
    presentation says how a Kind's data READS on a surface, relations say what
    the Kind POINTS AT — a statement about the model, true whether or not
    anything is being rendered. Folding one into the other would make a Kind
    that declares relations also claim a rendering opinion it never had.

    Same two constraints as ``KindPresentation``, for the same reasons: NOT
    ``@runtime_checkable`` and NOT part of ``KindPort``, because
    ``runtime_checkable`` checks member PRESENCE and the H1 registration gate
    would then reject every minimal third-party Kind — the breakage the
    ``is_runtime_artifact`` addition caused once.

    - ``relations`` — ``{relation name: Relation}``, where a relation's NAME is
      the spec field holding its value. Four keys and no more: ``to`` (the
      target Kind, a list for a polymorphic one, or ``*`` when the target
      travels in the value), ``cardinality`` (``one``/``many``, declared and
      never inferred from ``type: array``), ``inverse_of`` (the relation name
      on the target that is this one's other half) and ``by`` (how the value
      addresses the target — ``name`` by default, and the ONLY addressing the
      kernel resolves and therefore validates). Normalized + validated by
      ``dna.kernel.kinds.relations`` (``relations_of``). A TENANT Kind declares
      it in the very same words, as ``KindDefinition.spec.relations``.

_No methods: this Protocol is satisfied by **attributes**, not calls (see the source docstring above)._

**Swap it when** — Your Kind references other instances and you want those references in the derived reference graph.

**The minimum that works** — The declared relation attributes; see the source docstring above.

**What it lights up** — Edges in the reference graph — **if the active source records edges**. This is the sharpest instance of the catalogue's central rule: on a store that declares `edge_graph=False`, the graph face answers `unsupported` (REST **501**) and not an empty list, because `[]` reads as *nothing points at this instance*, and that is a claim only a store which actually keeps edges may make. Declaring relations on a filesystem-backed deployment is therefore not wrong — it is simply unanswerable, and the face says so.

**How you prove it** — `dna graph` against a Postgres-backed source; `tests/test_graph_traversal.py` is the in-tree reference.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

## TemplateProvider

`dna.kernel.protocols.TemplateProvider` · `@runtime_checkable` · :material-power-plug: **extension point**

An optional extra capability of an `Extension`: ship starter files.

!!! quote "From the source"

    Optional Extension capability — ships scaffold file trees.

    Kept OFF the ``Extension`` Protocol body so legacy extensions that
    predate Phase 0 keep satisfying ``Extension`` without modification.
    ``Kernel.list_templates()`` feature-tests each loaded extension
    (``isinstance(ext, TemplateProvider)`` — or the historical
    ``hasattr(ext, "templates")``) and aggregates the entries so UIs
    (Studio, CLI) can offer ``scaffold()`` for any extension-shipped
    file tree. See ``dna.kernel.compose.templates.Template``.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `templates` | <code>def templates(self) -> list['Template']</code> |  |

**Swap it when** — Your extension has a `dna new`-style starting point worth shipping.

**The minimum that works** — `templates()`.

**What it lights up** — Your templates in the scaffolding commands. Detected by feature test, so omitting it is invisible and harmless.

**How you prove it** — `SafetyPolicyExtension.templates()` (`dna.extensions.safety`) is the only shipped implementation and the reference.

**Shipped implementations** — `SafetyPolicyExtension` (`dna.extensions.safety`) — satisfies it structurally, via an optional `templates()` method

## ToolPort

`dna.kernel.protocols.ToolPort` · `@runtime_checkable` · :material-power-plug: **extension point**

A callable exposed to agents, wrapping a LangChain `StructuredTool` so framework compatibility is preserved while DNA adds discovery and policy on top.

!!! quote "From the source"

    An invocable tool exposed to agents. The underlying callable is
    a langchain StructuredTool (preserves framework compatibility);
    this port adds DNA discovery metadata (group, hitl, scope).

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `get_callable` | <code>def get_callable(self) -> Any</code> | Return the underlying langchain StructuredTool (or function). |

**Swap it when** — Rarely as a *class*. `ToolDefinition` is the concrete implementation and almost everyone should instantiate it rather than write a second one — the pluralism here is in the tool instances, not in implementations of the port.

**The minimum that works** — `get_callable()`.

**What it lights up** — The tool over the MCP face and in emitted agents. Note that the tool *definition* is data — see [Tools as data](../../guides/tools-as-data.md) — so the usual answer is a declared tool, not a new class.

**How you prove it** — Exercise it through `dna mcp serve` and the `list_tools` face.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

