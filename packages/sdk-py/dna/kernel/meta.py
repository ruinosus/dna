"""Meta-kind machinery: DeclarativeKindPort synthesized from TypedKindDefinition.

A KindDefinition document declaratively describes a new kind (schema, storage,
prompt flags, dep_filters). The kernel's 2-phase loader parses these first
and synthesizes a DeclarativeKindPort per definition via
``DeclarativeKindPort.from_typed(typed_def)``. These synthetic ports are
registered on the kernel and then the second phase parses every other
document against the now-expanded kind registry.
"""
from __future__ import annotations

from typing import Any

import colorsys

from dna.kernel.kind_base import KindBase
from dna.kernel.models import TypedKindDefinition
from dna.kernel.preview import PreviewBlock
from dna.kernel.protocols import (
    BodyMode,
    StorageDescriptor,
    StoragePattern,
    TenantScope,
)


# ---------------------------------------------------------------------------
# Schema Fragment Registry
#
# Open-extension primitive: any extension can register named schema fragments
# (namespaced via "owner/fragment-name"). KindDefinition.spec.schema_fragments
# lists IDs; DeclarativeKindPort looks them up and merges into schema.properties.
#
# Kernel never imports from any specific extension — fragments are pushed in
# by extension.register() calls. 3rd-party extensions can add their own
# fragments without modifying the SDK.
# ---------------------------------------------------------------------------

_SCHEMA_FRAGMENTS: dict[str, dict[str, Any]] = {}


def register_schema_fragment(fragment_id: str, schema: dict[str, Any]) -> None:
    """Register a named JSON-Schema fragment. Extensions call this from their
    ``register(kernel)`` method.

    Convention: ``fragment_id`` is namespaced ``<owner>/<name>`` (e.g.
    ``sdlc/workitem-common``). Later registrations override earlier ones for
    the same ID; tests can reset the registry via :func:`_reset_schema_fragments`.

    Parameters
    ----------
    fragment_id : str
        Stable name. Recommend ``<owner>/<name>`` or ``<owner>/<name>/v<N>``.
    schema : dict
        JSON Schema fragment. Typically ``{"type": "object", "properties": {...}}``
        — only the ``properties`` block is merged into target Kinds.
    """
    _SCHEMA_FRAGMENTS[fragment_id] = schema


def _lookup_schema_fragment(fragment_id: str) -> dict[str, Any] | None:
    return _SCHEMA_FRAGMENTS.get(fragment_id)


def list_schema_fragments() -> list[str]:
    """List registered fragment IDs (for debug / `dna kind fragments list`)."""
    return sorted(_SCHEMA_FRAGMENTS.keys())


def _reset_schema_fragments() -> None:
    """Test-only: clear the registry."""
    _SCHEMA_FRAGMENTS.clear()


def storage_dict_to_descriptor(storage: dict[str, Any]) -> StorageDescriptor:
    """Convert a literal YAML storage dict into a StorageDescriptor.

    Supported shapes:
      - {type: bundle, container, marker, body_as?, body_field?}
      - {type: yaml, container}
      - {type: standalone, path, body_as?, body_field?}
      - {type: root, marker?}

    Raises ``ValueError`` on unknown/missing ``type``.
    """
    if not isinstance(storage, dict):
        raise ValueError(f"storage must be a dict, got {type(storage).__name__}")

    stype = storage.get("type")
    if not stype:
        raise ValueError("storage dict must have a 'type' field")

    def _body_as(val: Any) -> BodyMode:
        if val is None:
            return BodyMode.TEXT
        try:
            return BodyMode(val)
        except ValueError as e:
            raise ValueError(
                f"unknown body_as={val!r} (expected one of {[m.value for m in BodyMode]})"
            ) from e

    if stype == "bundle":
        container = storage.get("container") or storage.get("dir")
        marker = storage.get("marker")
        if not container or not marker:
            raise ValueError("storage type=bundle requires 'container' (or 'dir') and 'marker'")
        return StorageDescriptor.bundle(
            container=container,
            marker=marker,
            body_as=_body_as(storage.get("body_as")),
            body_field=storage.get("body_field", "instruction"),
        )

    if stype == "yaml":
        container = storage.get("container") or storage.get("dir")
        if not container:
            raise ValueError("storage type=yaml requires 'container'")
        return StorageDescriptor.yaml(container=container)

    if stype == "standalone":
        filename = storage.get("path") or storage.get("filename") or storage.get("marker")
        if not filename:
            raise ValueError("storage type=standalone requires 'path' (or 'filename')")
        return StorageDescriptor.standalone(
            filename=filename,
            body_as=_body_as(storage.get("body_as")),
            body_field=storage.get("body_field", "content"),
        )

    if stype == "root":
        return StorageDescriptor.root(filename=storage.get("marker", "manifest.yaml"))

    raise ValueError(
        f"unknown storage type={stype!r} "
        f"(expected: bundle, yaml, standalone, root)"
    )


class DeclarativeKindPort:
    """A synthetic KindPort generated from a TypedKindDefinition.

    Behaves like any hand-written KindPort: it declares identity, storage,
    and prompt flags, and its ``parse(raw)`` validates the raw ``spec``
    against the JSON Schema declared in the KindDefinition. On validation
    failure a clear ValueError is raised.
    """

    # Allow discovery as a declarative (not extension-backed) port.
    __declarative__ = True

    def __init__(self, typed_def: TypedKindDefinition) -> None:
        self._typed_def = typed_def
        spec = typed_def.spec
        self.api_version: str = spec.target_api_version
        self.kind: str = spec.target_kind
        self.alias: str = spec.alias
        self.origin: str = spec.origin
        self.model: type = dict
        self.is_root: bool = spec.is_root
        self.is_prompt_target: bool = spec.prompt_target
        # F3 fields read via getattr — like schema_fragments below, specs are
        # duck-typed in tests (SimpleNamespace), so stay defensive with the
        # same defaults KindDefinitionSpec declares.
        # F3 (spec D2): was hardcoded 5 — now declarable, default 5 preserved.
        self.prompt_target_priority: int = int(
            getattr(spec, "prompt_target_priority", 5)
        )
        self.flatten_in_context: bool = spec.flatten_in_context
        # F3 (spec D2): from_raw now populates is_runtime_artifact.
        self.is_runtime_artifact: bool = bool(
            getattr(spec, "is_runtime_artifact", False)
        )
        # ---- F3 descriptor fields (spec 2026-06-10-kinds-descriptor-f3, D2) --
        # ``plane``: mirrors KindBase.plane ("composition" default).
        self.plane: str = getattr(spec, "plane", "composition")
        # ``scope``: mirrors the class attribute (e.g. KaizenKind declares
        # `scope = TenantScope.GLOBAL`). Only set when tenant_scope was
        # EXPLICITLY declared — undeclared kinds stay permissive (Phase 1
        # back-compat: Kernel._kind_scope reads getattr(kp, "scope", None)).
        if getattr(spec, "tenant_scope_declared", False):
            self.scope: TenantScope = TenantScope(spec.tenant_scope)
        # Kernel classification flags — mirror KindBase defaults.
        self.scope_inheritable: bool = bool(getattr(spec, "scope_inheritable", True))
        self.is_overlayable: bool = bool(getattr(spec, "is_overlayable", True))
        # ``embed_fields``: source fields for embedding text (D4 derivation).
        self.embed_fields: list[str] | None = getattr(spec, "embed", None)
        # ``summary``: declarative list-endpoint projection {field: default}.
        # Values MAY be projection objects (spec D2); lint them at load so a
        # bad descriptor fails fast (unknown key / exclusivity violation).
        self._summary: dict[str, Any] | None = getattr(spec, "summary", None)
        self._lint_summary(self._summary)
        # Declared volatile fields union the KindBase defaults so the
        # canonical digest contract matches hand-written record Kinds.
        # (C1 review carry-over: read the defaults FROM KindBase — never
        # re-hardcode the set; a KindBase change must propagate here.)
        self.VOLATILE_SPEC_FIELDS: frozenset[str] = (
            KindBase.VOLATILE_SPEC_FIELDS
            | frozenset(getattr(spec, "volatile_spec_fields", None) or ())
        )
        self.docs: str | None = spec.docs
        self._dep_filters: dict[str, str] | None = spec.dep_filters
        self._default_agent: str | None = spec.default_agent
        self._json_schema: dict[str, Any] = spec.schema or {}
        # ---- Descriptor expressiveness fields (spec 2026-06-11, D1/D3-D7) ----
        # D1 ``ui``: reconstruct the real StudioUIMetadata from the validated
        # mapping so /kinds/manifest output is byte-identical to the deleted
        # class version (the route calls ui.to_dict() AND ui.resolve_label()).
        ui_raw = getattr(spec, "ui", None)
        if ui_raw is not None:
            from dna.kernel.studio_ui import StudioUIMetadata

            self.ui: StudioUIMetadata | None = StudioUIMetadata(**ui_raw)
        else:
            self.ui = None
        # D3 ``describe``: template string OR {"path": field} mapping.
        self._describe: str | dict[str, Any] | None = getattr(spec, "describe", None)
        # D4 ``ui_schema``: pass-through widget-hint bag (no kernel interp).
        self.ui_schema: dict[str, Any] | None = getattr(spec, "ui_schema", None)
        # D5 ``spec_defaults``: shallow-merge map applied in parse() BEFORE
        # validation. Lint NOW (load time) — fail fast on a bad descriptor.
        self._spec_defaults: dict[str, Any] | None = getattr(spec, "spec_defaults", None)
        if self._spec_defaults:
            self._lint_spec_defaults(self._spec_defaults, self._json_schema)
        # D6 ``default_agent_field``: spec field returned VERBATIM by
        # get_default_agent_name.
        self._default_agent_field: str | None = getattr(spec, "default_agent_field", None)
        # D7 ``description_fallback_field``: pass-through string attr.
        self.description_fallback_field: str | None = getattr(
            spec, "description_fallback_field", None
        )
        # Schema-fragment composition (Story s-workitem-common-schema-fragment
        # re-scoped after architecture review): KindDefinition.spec.schema_fragments
        # is a list of namespaced fragment IDs (e.g. "sdlc/workitem-common").
        # Any extension can register fragments via kernel.schema_fragment(id, dict).
        # Kernel walks the list and merges each fragment's properties into
        # schema.properties, with later fragments + Kind-specific properties
        # winning over earlier ones. Open-for-extension contract preserved —
        # kernel never imports from a specific extension.
        #
        # Registry is queried lazily via a module-level helper so this class
        # doesn't depend on holding a kernel ref.
        fragment_ids = getattr(spec, "schema_fragments", None) or []
        # Back-compat: honour legacy spec.workitem_common: true as shorthand
        # for schema_fragments: ["sdlc/workitem-common"].
        if getattr(spec, "workitem_common", False):
            fragment_ids = list(fragment_ids) + ["sdlc/workitem-common"]
        if fragment_ids:
            merged_props: dict[str, Any] = {}
            for fid in fragment_ids:
                frag = _lookup_schema_fragment(fid)
                if not frag:
                    continue
                frag_props = frag.get("properties") if isinstance(frag, dict) else None
                if isinstance(frag_props, dict):
                    merged_props.update(frag_props)
            # Kind-specific properties override fragment-provided ones.
            if not self._json_schema:
                self._json_schema = {"type": "object", "properties": {}}
            if not isinstance(self._json_schema.get("properties"), dict):
                self._json_schema["properties"] = {}
            kind_props = self._json_schema["properties"]
            merged_props.update(kind_props)
            self._json_schema["properties"] = merged_props

        self.storage: StorageDescriptor = storage_dict_to_descriptor(spec.storage)

        # Rendering hints — read from KindDefinition spec if user-provided,
        # otherwise auto-derive. Custom kinds get a deterministic color from
        # their origin hash.
        raw_spec = spec.__dict__ if hasattr(spec, "__dict__") else {}
        user_style = raw_spec.get("graph_style") if isinstance(raw_spec, dict) else None
        if isinstance(user_style, dict) and user_style.get("fill") and user_style.get("stroke"):
            # Canonical key is snake_case `text_color`; camelCase `textColor`
            # stays accepted for back-compat (C4 review carry-over — mirrors
            # the TS twin meta.ts: `text_color ?? textColor ?? "#fff"`).
            user_text_color = user_style.get("text_color")
            if user_text_color is None:
                user_text_color = user_style.get("textColor")
            self.graph_style: dict[str, str] = {
                "fill": user_style["fill"],
                "stroke": user_style["stroke"],
                "text_color": user_text_color if user_text_color is not None else "#fff",
            }
        else:
            h = 0
            for c in self.origin:
                h = (h * 31 + ord(c)) & 0xFFFFFFFF
            hue = h % 360

            def _hsl_to_hex(h_: int, s_: int, l_: int) -> str:
                r, g, b = colorsys.hls_to_rgb(h_ / 360, l_ / 100, s_ / 100)
                return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

            self.graph_style = {
                "fill": _hsl_to_hex(hue, 55, 55),
                "stroke": _hsl_to_hex(hue, 55, 40),
                "text_color": "#fff",
            }
        self.ascii_icon: str = (
            raw_spec.get("ascii_icon")
            if isinstance(raw_spec, dict) and isinstance(raw_spec.get("ascii_icon"), str)
            else "📄"
        )
        self.display_label: str = (
            raw_spec.get("display_label")
            if isinstance(raw_spec, dict) and isinstance(raw_spec.get("display_label"), str)
            else (self.kind + "s")
        )

    # -- Descriptor expressiveness helpers (spec D5) --------------------------

    @staticmethod
    def _lint_spec_defaults(
        spec_defaults: dict[str, Any], json_schema: dict[str, Any]
    ) -> None:
        """Load-time lint for ``spec_defaults`` (spec D5).

        Each default KEY must exist in ``schema.properties`` and its VALUE
        must validate against THAT property's subschema. ``required`` is
        intentionally IGNORED — defaults are a *partial* spec (autolab's real
        ``_DEFAULTS`` does not satisfy ``required:[program, max_iterations]``).
        Raises ValueError on a bad descriptor (fail fast at load).
        """
        props = json_schema.get("properties") if isinstance(json_schema, dict) else None
        if not isinstance(props, dict):
            props = {}
        try:
            import jsonschema
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "jsonschema is required to lint declarative kinds; "
                "install with `pip install jsonschema>=4.0`"
            ) from e
        for key, value in spec_defaults.items():
            if key not in props:
                raise ValueError(
                    f"KindDefinition spec_defaults key {key!r} is not a "
                    f"property in schema.properties"
                )
            subschema = props[key]
            if isinstance(subschema, dict):
                try:
                    jsonschema.validate(instance=value, schema=subschema)
                except jsonschema.ValidationError as e:
                    raise ValueError(
                        f"KindDefinition spec_defaults[{key!r}]={value!r} fails "
                        f"its property subschema: {e.message}"
                    ) from e

    # -- KindPort API ---------------------------------------------------------

    def dep_filters(self) -> dict[str, str] | None:
        return self._dep_filters

    def dependencies(self) -> dict[str, str] | None:
        return self.dep_filters()

    def schema(self) -> dict[str, Any] | None:
        return self._json_schema if self._json_schema else None

    def get_default_agent_name(self, doc: Any) -> str | None:
        # D6: when default_agent_field is declared, return the spec field
        # VERBATIM (no ``or None`` coercion — "" stays "", mirroring the
        # eval-evalexperiment class). Otherwise fall back to the static
        # default_agent (legacy descriptor behavior).
        if self._default_agent_field is not None:
            spec = getattr(doc, "spec", None) or {}
            if not isinstance(spec, dict):
                spec = {}
            return spec.get(self._default_agent_field)
        return self._default_agent

    def get_layer_policies(self, doc: Any) -> dict | None:
        return None

    def parse(self, raw: dict[str, Any]) -> Any:
        spec = raw.get("spec", {}) if isinstance(raw, dict) else {}
        # D5: shallow-merge {**spec_defaults, **spec} BEFORE validation —
        # exactly autolab-run's class behavior (defaults fill, spec overrides).
        if self._spec_defaults and isinstance(spec, dict):
            spec = {**self._spec_defaults, **spec}
            if isinstance(raw, dict):
                raw = {**raw, "spec": spec}
        if self._json_schema:
            try:
                import jsonschema
            except ImportError as e:  # pragma: no cover
                raise RuntimeError(
                    "jsonschema is required to validate declarative kinds; "
                    "install with `pip install jsonschema>=4.0`"
                ) from e
            try:
                jsonschema.validate(instance=spec, schema=self._json_schema)
            except jsonschema.ValidationError as e:
                raise ValueError(
                    f"DeclarativeKind {self.kind!r} spec validation failed: {e.message} "
                    f"(path: {'/'.join(str(p) for p in e.absolute_path) or '<root>'})"
                ) from e
        return raw

    def describe(self, doc: Any) -> str | None:
        """Display string for a doc (spec D3).

        - Template form (``str``): substitute ``{field}`` placeholders from
          the spec top level; a missing/None field renders as "".
        - Projection form (``{"path": field}``): return the spec field
          verbatim (or None if absent).
        - No ``describe`` declared → None (today's behavior).
        """
        if self._describe is None:
            return None
        spec = getattr(doc, "spec", None) or {}
        if not isinstance(spec, dict):
            spec = {}
        if isinstance(self._describe, dict):
            field_name = self._describe.get("path")
            if field_name is None:
                return None
            val = spec.get(field_name)
            return val if val is not None else None

        class _BlankMissing(dict):
            def __missing__(self, key: str) -> str:
                return ""

        # str.format_map with a defaulting dict: missing field → "". A
        # present-but-None value also renders "" (None → "" for display).
        safe = _BlankMissing({k: ("" if v is None else v) for k, v in spec.items()})
        return self._describe.format_map(safe)

    # -- Summary projection vocabulary (spec D2) ------------------------------
    # A value in ``summary:`` MAY be a projection object. Plain values keep
    # today's meaning (the projected default). The closed vocabulary + FIXED
    # combinator order: resolve (``path``|``count_of``) → ``default`` →
    # ``round`` → ``truncate``. ``format`` is exclusive of all the others.
    _PROJECTION_KEYS: frozenset[str] = frozenset(
        {
            "count_of",
            "path",
            "paths",
            "format",
            "truncate",
            "round",
            "default",
            "filter_falsy",
            "all_or_empty",
            "placeholder_defaults",
        }
    )
    # Keys that mark a dict VALUE as a projection object (vs a plain default
    # that just happens to be a dict). If a dict carries ANY of these, it is
    # treated as a projection and linted against the closed vocabulary.
    _PROJECTION_MARKERS: frozenset[str] = frozenset(
        {"count_of", "path", "paths", "format"}
    )

    @classmethod
    def _is_projection(cls, value: Any) -> bool:
        return isinstance(value, dict) and bool(
            cls._PROJECTION_MARKERS & set(value.keys())
        )

    @classmethod
    def _lint_summary(cls, summary: dict[str, Any] | None) -> None:
        """Load-time lint for projection objects in ``summary:`` (spec D2).

        Any key in a projection object outside the closed vocabulary →
        ValueError. Mutually-exclusive resolvers (``count_of`` xor ``path``
        xor ``paths`` xor ``format``) are enforced, and ``format`` is
        exclusive of the combinators. Fail fast at descriptor load.
        """
        if not isinstance(summary, dict):
            return
        for field, value in summary.items():
            if not cls._is_projection(value):
                continue
            keys = set(value.keys())
            unknown = keys - cls._PROJECTION_KEYS
            if unknown:
                raise ValueError(
                    f"KindDefinition summary[{field!r}] projection has "
                    f"unknown key(s) {sorted(unknown)!r}; allowed: "
                    f"{sorted(cls._PROJECTION_KEYS)!r}"
                )
            resolvers = keys & {"count_of", "path", "paths", "format"}
            if len(resolvers) != 1:
                raise ValueError(
                    f"KindDefinition summary[{field!r}] projection must have "
                    f"exactly one of count_of/path/paths/format, got "
                    f"{sorted(resolvers)!r}"
                )
            if "format" in keys and (keys - {"format", "all_or_empty", "placeholder_defaults"}):
                raise ValueError(
                    f"KindDefinition summary[{field!r}] format projection is "
                    f"exclusive of path/count_of/round/truncate/default"
                )
            if "paths" in keys and (keys - {"paths", "filter_falsy"}):
                raise ValueError(
                    f"KindDefinition summary[{field!r}] paths projection only "
                    f"supports filter_falsy"
                )

    @staticmethod
    def _walk_path(spec: dict[str, Any], path: str) -> Any:
        """Dict-only walk over a dotted ``a.b.c`` path. Missing → None."""
        cur: Any = spec
        for seg in path.split("."):
            if not isinstance(cur, dict) or seg not in cur:
                return None
            cur = cur[seg]
        return cur

    @staticmethod
    def _bankers_round(value: float, ndigits: int) -> Any:
        """Banker's rounding (round-half-to-even) — matches Python ``round``."""
        return round(value, ndigits)

    @classmethod
    def _resolve_projection(cls, spec: dict[str, Any], proj: dict[str, Any]) -> Any:
        # -- format (exclusive) -----------------------------------------------
        if "format" in proj:
            template: str = proj["format"]
            all_or_empty = bool(proj.get("all_or_empty"))
            ph_defaults = proj.get("placeholder_defaults") or {}
            import re

            names = re.findall(r"\{([^}]+)\}", template)
            resolved: dict[str, Any] = {}
            for name in names:
                present = name in spec and spec.get(name) is not None
                if present:
                    resolved[name] = spec[name]
                elif all_or_empty:
                    return ""
                elif name in ph_defaults:
                    resolved[name] = ph_defaults[name]
                else:
                    resolved[name] = ""

            class _BlankMissing(dict):
                def __missing__(self, key: str) -> str:
                    return ""

            return template.format_map(_BlankMissing(resolved))

        # -- paths + filter_falsy (leaf-keyed) --------------------------------
        if "paths" in proj:
            out: dict[str, Any] = {}
            filter_falsy = bool(proj.get("filter_falsy"))
            for path in proj["paths"]:
                leaf = path.split(".")[-1]
                val = cls._walk_path(spec, path)
                if filter_falsy and not val:
                    continue
                out[leaf] = val
            return out

        # -- resolve: count_of | path -----------------------------------------
        if "count_of" in proj:
            target = spec.get(proj["count_of"])
            # Mirror the TS guard: only str/list (and tuple) are measured via
            # len; everything else (dict, int, float, None, bool, ...) → 0.
            # Python's bare ``len(target)`` would element-count a dict and HARD
            # CRASH (uncaught TypeError) on an int/float — diverging from TS,
            # which yields 0. count_of's contract is "length of a sequence".
            value: Any = (
                len(target) if isinstance(target, (str, list, tuple)) else 0
            )
        else:  # path
            value = cls._walk_path(spec, proj["path"])

        # -- default (fires on missing OR None, post-resolve) -----------------
        if "default" in proj and value is None:
            value = proj["default"]

        # -- round (numeric; None passes through) -----------------------------
        if "round" in proj and isinstance(value, (int, float)) and not isinstance(value, bool):
            value = cls._bankers_round(value, proj["round"])

        # -- truncate (string[:N]) --------------------------------------------
        if "truncate" in proj and isinstance(value, str):
            value = value[: proj["truncate"]]

        return value

    def summary(self, doc: Any) -> dict[str, Any] | None:
        """Declarative projection (F3 spec D2): when the KindDefinition
        declares ``summary: {field: <plain default | projection object>}``,
        project the doc's spec. A PLAIN value keeps today's meaning (present
        field from spec, else the declared default). A PROJECTION object runs
        the closed vocabulary (count_of/path/paths/format + combinators).
        No declaration → None (today's behavior)."""
        if self._summary is None:
            return None
        spec = getattr(doc, "spec", None) or {}
        if not isinstance(spec, dict):
            spec = {}
        out: dict[str, Any] = {}
        for field, value in self._summary.items():
            if self._is_projection(value):
                out[field] = self._resolve_projection(spec, value)
            else:
                out[field] = spec.get(field, value)
        return out

    def prompt_template(self) -> str | None:
        return None

    def preview(self, doc: Any) -> list[PreviewBlock]:
        """Preview blocks derived from the kind's JSON schema.

        Walks the top-level ``properties`` of ``self._json_schema`` and
        renders each property based on its declared type. Mirrors the TS
        DeclarativeKindPort.preview() impl line for line.
        """
        import json as _json

        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}

        props = self._json_schema.get("properties") if isinstance(self._json_schema, dict) else None
        if not isinstance(props, dict) or not props:
            if not spec_dict:
                return [PreviewBlock(kind="empty", title=f"{self.kind} (empty)")]
            return [
                PreviewBlock(
                    kind="code",
                    title=f"{self.kind} spec",
                    body=_json.dumps(spec_dict, indent=2, default=str),
                    language="json",
                )
            ]

        required = set(self._json_schema.get("required") or [])
        ordered = sorted(
            props.items(),
            key=lambda kv: (0 if kv[0] in required else 1, kv[0]),
        )

        blocks: list[PreviewBlock] = []
        fields: list[dict[str, str]] = []

        for field_name, prop_schema in ordered:
            value = spec_dict.get(field_name)
            if value is None or value == "":
                continue
            ptype = prop_schema.get("type") if isinstance(prop_schema, dict) else None
            pformat = prop_schema.get("format") if isinstance(prop_schema, dict) else None
            max_length = prop_schema.get("maxLength", 0) if isinstance(prop_schema, dict) else 0
            title = (prop_schema.get("title") if isinstance(prop_schema, dict) else None) or field_name

            if (
                ptype == "string"
                and isinstance(value, str)
                and (pformat == "markdown" or max_length >= 400 or len(value) > 200)
            ):
                blocks.append(PreviewBlock(kind="markdown", title=title, body=value))
                continue

            if ptype == "string" and isinstance(value, str):
                fields.append({"label": title, "value": value})
                continue

            if ptype in ("integer", "number"):
                fields.append({"label": field_name, "value": str(value)})
                continue

            if ptype == "boolean":
                fields.append(
                    {"label": field_name, "value": "true" if value else "false"}
                )
                continue

            if ptype == "array" and isinstance(value, list):
                items = prop_schema.get("items") if isinstance(prop_schema, dict) else None
                if isinstance(items, dict) and items.get("type") == "string" and not items.get("enum"):
                    fields.append(
                        {
                            "label": title,
                            "value": "\n".join(f"• {v}" for v in value),
                        }
                    )
                else:
                    blocks.append(
                        PreviewBlock(
                            kind="code",
                            title=title,
                            body=_json.dumps(value, indent=2, default=str),
                            language="json",
                        )
                    )
                continue

            if ptype == "object" or isinstance(value, (dict, list)):
                blocks.append(
                    PreviewBlock(
                        kind="code",
                        title=title,
                        body=_json.dumps(value, indent=2, default=str),
                        language="json",
                    )
                )
                continue

            fields.append({"label": field_name, "value": str(value)})

        if fields:
            blocks.insert(0, PreviewBlock(kind="fields", title=self.kind, fields=fields))

        if not blocks:
            return [PreviewBlock(kind="empty", title=f"{self.kind} (empty)")]
        return blocks

    @classmethod
    def from_typed(cls, typed_def: TypedKindDefinition) -> "DeclarativeKindPort":
        return cls(typed_def)
