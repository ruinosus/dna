"""KindRegistry — the kernel's registered-Kind identity map + the full
registration funnel, extracted from the Kernel god-object (kernel decomposition,
Fase 3 — ``s-kernel-decomp-f3-kindregistry``).

Two surfaces live here:

- **Lookup** (Fase pre-3): the ``_kinds`` dict + the read surface (port lookup,
  alias, storage/container resolution, container→kind, describe).
- **Registration** (this slice): ``register_kind`` (the H1 validation funnel —
  Protocol/dup-key/dup-alias/BUNDLE-marker/plane/i-195-name-collision +
  alias generation), the ``_lint_plane`` helper, ``register_from_descriptor``
  (builtin ``*.kind.yaml`` descriptors), and ``register_kind_definitions`` (the
  per-scope KindDefinition funnel — warn+skip instead of raise). The kernel
  keeps ``kind()`` / ``kind_from_descriptor()`` / ``_register_kind_definitions()``
  / ``_register_custom_kinds()`` as THIN facades delegating here.

Registration mutates ``self._kinds`` directly (the registry OWNS the dict; the
kernel's ``_kinds`` property proxies to it, so the ~20 inline ``self._kinds``
read sites across the kernel keep working unchanged). Side effects that touch
the wider kernel — hooks (``kinddef_conflict`` / ``parse_error`` events), the
``_readers`` list (the rescan return gate), the generic reader/writer wiring,
the ``_generics_resolved`` flag, and the ``_loading_ext_owner`` alias-owner
context — route through a NARROW ``RegistryHost`` back-ref (the anti-cosmetic
rule, spec §3.1): the kernel satisfies it structurally. View-only registries
(CompositionEngine / nav_kernel wrapping a kinds map for lookups) pass no host.

One registry per kernel, shared across ``with_tenant`` shallow copies (Kinds are
global — registered once at boot on the base kernel).
"""
from __future__ import annotations

import logging
import re
import warnings
from typing import TYPE_CHECKING, Any

from dna.kernel.errors import KindRegistrationError
from dna.kernel.protocols import KindPort, StoragePattern

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import RegistryHost
    from dna.kernel.protocols import StorageDescriptor

logger = logging.getLogger(__name__)

# s-kinddef-conflict-once (2026-05-27): process-wide set of (apiVersion, kind)
# pairs already warned about in the per-scope KindDefinition funnel. Limits noise
# to one log line per conflict per process — full restart needed to re-warn.
# Module-level (not an instance attr) because some call sites create fresh
# kernel-like wrappers — the instance-attr version was bypassed and warnings
# fired on every MI rebuild, flooding logs.
_GLOBAL_KINDDEF_CONFLICT_WARNED: set[tuple[str, str]] = set()


def _load_kind_docs(kind_port: Any) -> str | None:
    """Resolve kind documentation prose.

    Resolution order:
      1. ``DOCS-<KindName>.md`` inside the kind's extension package
      2. ``DOCS.md`` inside the kind's extension package
      3. The ``docs`` class attribute on the KindPort
      4. ``None``
    """
    import importlib
    import importlib.resources
    from pathlib import Path as _Path

    kind_name = getattr(kind_port, "kind", None) or type(kind_port).__name__
    module_name = type(kind_port).__module__
    package = module_name.rsplit(".", 1)[0] if "." in module_name else module_name

    candidates = [f"DOCS-{kind_name}.md", "DOCS.md"]

    # Try importlib.resources first (works for installed packages)
    for candidate in candidates:
        try:
            ref = importlib.resources.files(package).joinpath(candidate)
            if ref.is_file():
                text = ref.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except (ModuleNotFoundError, FileNotFoundError, AttributeError, TypeError):
            pass

    # Fallback: __file__-relative path (single-file modules, dev layouts)
    try:
        mod = importlib.import_module(module_name)
        mod_file = getattr(mod, "__file__", None)
        if mod_file:
            base = _Path(mod_file).parent
            for candidate in candidates:
                p = base / candidate
                if p.exists():
                    text = p.read_text(encoding="utf-8").strip()
                    if text:
                        return text
    except (ImportError, OSError, AttributeError, ValueError):
        # s-narrow-except-pass — narrowed from bare `except Exception`: the only
        # expected failures here are a missing module (ImportError), unreadable
        # path (OSError), or a module with no usable __file__ (AttributeError/
        # ValueError). Genuine bugs now propagate instead of being swallowed.
        pass

    return getattr(kind_port, "docs", None)


# ---------------------------------------------------------------------------
# s-alias-generated-not-typed — alias generation + canonical dep_filter
# resolution. Aliases used to be hand-typed strings on every Kind class
# (~46 divergences from the <owner>-<kebab(kind)> convention + one
# recorded bug: "policy-layer" reversed/truncated). New Kinds OMIT the
# alias and get it generated; legacy aliases stay untouched (live wire
# format in dep_filters / Mustache / LayerPolicy docs).
# ---------------------------------------------------------------------------

def kebab_kind_name(kind: str) -> str:
    """CamelCase kind name → kebab-case: EvalCase → eval-case, ADR → adr,
    HTMLThing → html-thing."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", kind)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "-", s)
    return s.lower()


def generate_alias(owner: str, kind: str) -> str:
    """The canonical alias for a Kind: ``<owner>-<kebab(kind)>``."""
    return f"{owner}-{kebab_kind_name(kind)}"


# Ratchet (shrink-only): every builtin CLASS Kind that still hand-types
# its alias — the live wire format that CANNOT be renamed without a doc
# migration. New Kinds must OMIT the alias (generation). Entries leave
# as classes migrate to generation/descriptors — NEVER add one
# (test_alias_generation.py::test_explicit_alias_ratchet_is_shrink_only).
EXPLICIT_ALIAS_ALLOWLIST: frozenset[str] = frozenset({
    # helix
    "helix-genome", "helix-agent", "helix-actor",
    "helix-usecase", "helix-tool", "policy-layer-policy",
    "helix-canvas",
    "helix-setting", "helix-theme", "helix-user-profile",
    # sdlc (classes; os descriptors ficam fora do ratchet)
    
    
    
    
    # eval
    
    
    # gaia / blocks
    
    
    # single-kind extensions
    "agentskills-skill", "soulspec-soul", "agentsmd-agent",
    "guardrails-guardrail", "helix-hook",
    "helix-safety-policy", "presidio-recognizer", "collab-comment",
    "kinddef-kinddefinition",
    
    
    "evidence-policy", "federation-mcp",
    # s-automation-trio-extinction: jobs-jobtype / hooktype-hooktype /
    # scheduletype-scheduletype extintos (unificados no Kind Automation).
    
    
    
    
    
    "tenant-tenant", "tenant-membership",
    "audit-userroleassignment", 
    
    
})

# i-195 — kind names allowed to exist under MULTIPLE api_versions in the
# extension/builtin funnel. SHRINK-ONLY ratchet: the Reference pair
# (github.com/ruinosus/dna/research/v1 + github.com/ruinosus/dna/sdlc/v1) predates the guard and is scheduled to
# be merged by the Reference-family unification follow-up; when that
# lands, empty this set. NEVER add a name here — rename the new Kind
# instead (the whole point of i-195 is that bare-name lookups become
# ambiguous the moment two api_versions share a kind name).
KIND_NAME_COLLISION_ALLOWLIST: frozenset[str] = frozenset({"Reference"})

# warn-once cache for ambiguous bare-name lookups (module-level on the
# instance would be fine too, but keep parity with
# _GLOBAL_KINDDEF_CONFLICT_WARNED's process-wide semantics).
_AMBIGUOUS_LOOKUP_WARNED: set[str] = set()


class KindRegistry:
    """Holds the registered KindPorts and the lookups over them."""

    def __init__(
        self,
        kinds: dict[tuple[str, str], "KindPort"] | None = None,
        *,
        host: "RegistryHost | None" = None,
    ) -> None:
        # ``kinds`` lets a registry VIEW wrap an existing dict without
        # copying (e.g. CompositionEngine / nav_kernel resolving over a
        # kinds map) so alias + legacy ``kind=`` dep_filter resolution
        # share the ONE canonical implementation below.
        self._kinds: dict[tuple[str, str], "KindPort"] = (
            kinds if kinds is not None else {}
        )
        # ``host`` is the NARROW ``RegistryHost`` back-ref used ONLY by the
        # registration funnel (hooks fan-out, the ``_readers`` rescan gate,
        # generic reader/writer wiring, ``_generics_resolved``, alias-owner
        # context). It is only read at registration time (boot), long after
        # kernel ``__init__`` completes — so the kernel may pass ``self``
        # before its ``hooks``/``_readers`` exist. View-only registries pass
        # ``None`` and never call the register_* methods.
        self._host: "RegistryHost | None" = host

    def port_for(
        self, kind: str, *, api_version: str | None = None,
    ) -> "KindPort | None":
        """Lookup a registered KindPort by kind name (case-sensitive).

        With ``api_version`` the lookup is EXACT on ``(api_version, kind)``.
        Bare lookups on an ambiguous name (two api_versions sharing a kind
        name — the allowlisted ``Reference`` pair, or per-scope
        KindDefinitions shadowing builtins like the demo scopes' local
        Doc/EvalCase) resolve deterministically: extension/builtin ports
        beat per-scope declarative ones, then registration order — and a
        warning fires once per process per name (i-195).
        """
        if api_version is not None:
            return self._kinds.get((api_version, kind))
        matches = [kp for kp in self._kinds.values() if kp.kind == kind]
        if not matches:
            return None
        if len(matches) > 1:
            if kind not in _AMBIGUOUS_LOOKUP_WARNED:
                _AMBIGUOUS_LOOKUP_WARNED.add(kind)
                logger.warning(
                    "Ambiguous bare kind-name lookup %r: %d ports share the "
                    "name (%s). Resolving extension-first then registration "
                    "order; pass api_version= for exact resolution. "
                    "(warned once per process — i-195)",
                    kind, len(matches),
                    ", ".join(kp.api_version for kp in matches),
                )
            # per-scope DeclarativeKindPorts carry __declarative__ WITHOUT
            # __builtin_descriptor__; extension classes + builtin
            # descriptors must win the bare name.
            extension_first = [
                kp for kp in matches
                if not getattr(kp, "__declarative__", False)
                or getattr(kp, "__builtin_descriptor__", False)
            ]
            if extension_first:
                return extension_first[0]
        return matches[0]

    def all_ports(self) -> list["KindPort"]:
        """All registered KindPorts. Order matches registration."""
        return list(self._kinds.values())

    def alias_for(self, kind: str, *, api_version: str | None = None) -> str:
        """Resolve a kind name to its globally-unique alias (``<owner>-<kind>``).
        Falls back to ``kind.lower()`` when no registered port provides one.
        Routes through ``port_for`` so ambiguous names resolve with the same
        deterministic preference (i-195)."""
        port = self.port_for(kind, api_version=api_version)
        alias = getattr(port, "alias", None) if port is not None else None
        return alias if alias else kind.lower()

    def container_for(
        self, kind_name: str, *, api_version: str | None = None,
    ) -> "str | None":
        """Return the storage container directory for a kind, or None."""
        kp = self.port_for(kind_name, api_version=api_version)
        if kp is None:
            return None
        sd = getattr(kp, "storage", None)
        return sd.container if sd else None

    def storage_for(
        self, kind_name: str, *, api_version: str | None = None,
    ) -> "StorageDescriptor | None":
        """Return the StorageDescriptor for a kind, or None if unknown."""
        kp = self.port_for(kind_name, api_version=api_version)
        return getattr(kp, "storage", None) if kp is not None else None

    def by_container(self, container: str) -> "str | None":
        """Return the kind name whose StorageDescriptor.container matches.
        None for empty container (ROOT kinds) or unregistered containers."""
        if not container:
            return None
        for kp in self._kinds.values():
            sd = getattr(kp, "storage", None)
            if sd is not None and sd.container == container:
                return kp.kind
        return None

    def resolve_dep_filter_target(self, value: str) -> "KindPort | None":
        """Canonical dep_filter target resolution (s-alias-generated-not-typed).

        The CONTRACT is alias-valued dep_filters (``"soulspec-soul"``).
        The legacy ``"kind=<Name>"`` format resolves through a DEPRECATED
        shim so per-scope KindDefinition docs keep working. Builtin
        extensions must be alias-pure (validate_dep_filters rejects
        ``kind=`` there). Since s-unify-composition-subsystems this is
        THE resolver for every dep_filter reader — ``validate_refs`` /
        ``mi.composition``, nav_kernel, and kinds-api docs all route
        through it.
        """
        if value.startswith("kind="):
            warnings.warn(
                f"dep_filter value {value!r} uses the legacy 'kind=' format"
                " — use the target Kind's alias instead"
                " (s-alias-generated-not-typed).",
                DeprecationWarning,
                stacklevel=3,
            )
            return self.port_for(value[len("kind="):])
        for kp in self._kinds.values():
            if getattr(kp, "alias", None) == value:
                return kp
        return None

    def validate_dep_filters(self) -> None:
        """s-alias-generated-not-typed — every dep_filter target of an
        EXTENSION-registered Kind must resolve to a registered alias.

        Aliases are the wire key of dep_filters / Mustache sections /
        LayerPolicy — a typo used to degrade the prompt SILENTLY (the
        dep just vanished from the context, warning buried in logs).
        Called at the end of ``Kernel.auto()``; harness boots hit it too.

        - Extension/builtin port with an unknown alias OR the legacy
          ``kind=`` format → ``KindRegistrationError`` (boot fails loud).
        - Per-scope declarative ports (user KindDefinition docs) only
          WARN — user docs never take the boot down (same posture as
          the parse_error / plane-lint funnels).
        """
        problems: list[str] = []
        for kp in self.all_ports():
            filters = None
            try:
                filters = kp.dep_filters()
            except Exception as e:  # noqa: BLE001
                # fail-soft: um port quebrado não derruba a validação dos
                # demais — mas o skip é logado (o Kind fica SEM validação de
                # dep_filters; um typo dele passaria batido em silêncio).
                logger.warning(
                    "validate_dep_filters: %s.dep_filters() raised (%s) — "
                    "skipping this Kind's dep_filter validation.", kp.kind, e,
                )
                continue
            if not filters:
                continue
            is_declarative = (
                getattr(kp, "__declarative__", False)
                and not getattr(kp, "__builtin_descriptor__", False)
            )
            for field, value in filters.items():
                if not isinstance(value, str):
                    continue
                if value.startswith("kind="):
                    msg = (
                        f"{kp.kind}.dep_filters[{field!r}] uses the legacy "
                        f"'kind=' format ({value!r}) — use the target Kind's "
                        f"alias (builtin extensions are alias-pure)."
                    )
                else:
                    # Polymorphic refs (WorkflowEvent.ref) declare a
                    # PIPE-UNION of aliases — validate each term.
                    unknown = [
                        part for part in value.split("|")
                        if self.resolve_dep_filter_target(part) is None
                    ]
                    if not unknown:
                        continue
                    msg = (
                        f"{kp.kind}.dep_filters[{field!r}] points at unknown "
                        f"alias(es) {unknown!r} — the dep would silently "
                        f"vanish from prompts/composition."
                    )
                if is_declarative:
                    logger.warning("[kernel] dep_filter (per-scope): %s", msg)
                else:
                    problems.append(msg)
        if problems:
            raise KindRegistrationError(
                "dep_filter validation failed (s-alias-generated-not-typed):\n  "
                + "\n  ".join(problems)
            )

    def describe(
        self, kind_name: str, *, api_version: str | None = None,
    ) -> dict[str, Any] | None:
        """Summary dict for a registered kind, including resolved docs."""
        kp = self.port_for(kind_name, api_version=api_version)
        if kp is None:
            return None
        return {
            "kind": kp.kind,
            "alias": getattr(kp, "alias", None),
            "api_version": kp.api_version,
            "is_root": getattr(kp, "is_root", False),
            "is_prompt_target": getattr(kp, "is_prompt_target", False),
            "docs": getattr(kp, "_resolved_docs", None) or getattr(kp, "docs", None),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Registration funnel (Fase 3 — s-kernel-decomp-f3-kindregistry). Moved
    # verbatim from Kernel.kind()/_lint_kind_plane/kind_from_descriptor/
    # _register_kind_definitions/_register_custom_kinds/_make_dynamic_kind.
    # The kernel keeps thin facades delegating here.
    # ─────────────────────────────────────────────────────────────────────

    def register_kind(self, k: "KindPort") -> None:
        # H1 — Boot-time validation (Protocol + uniqueness + marker collision).
        # Catches the failure modes that previously surfaced at runtime as
        # silent overwrites or first-match-wins scanner bugs:
        #   1. Object doesn't satisfy KindPort Protocol  → registration error
        #   2. Duplicate (api_version, kind) tuple        → registration error
        #   3. Duplicate alias across registered Kinds    → registration error
        #   4. BUNDLE-pattern (container, marker) clash   → registration error
        #   5. plane="record" with composition signals     → registration error
        if not isinstance(k, KindPort):
            raise KindRegistrationError(
                f"Kind {type(k).__name__} does not satisfy KindPort "
                f"Protocol. See dna.kernel.protocols.KindPort for "
                f"the required attributes/methods (api_version, kind, alias, "
                f"model, origin, storage, is_root, is_prompt_target, "
                f"prompt_target_priority, flatten_in_context, dep_filters, "
                f"dependencies, schema, get_default_agent_name, "
                f"get_layer_policies, parse, describe, summary, prompt_template)."
            )
        # s-alias-generated-not-typed — Kind sem alias declarado ganha o
        # gerado <owner>-<kebab(kind)>. Owner: attr explícito no port →
        # contexto da Extension sendo carregada (kernel.load) → 1º token
        # do api_version. Aliases legados digitados ficam intocados (wire
        # format vivo); o ratchet EXPLICIT_ALIAS_ALLOWLIST impede Kind
        # NOVO de digitar um.
        if not getattr(k, "alias", None):
            owner = (
                getattr(k, "alias_owner", None)
                or getattr(self._host, "_loading_ext_owner", None)
                or k.api_version.split(".")[0].split("/")[0]
            )
            k.alias = generate_alias(owner, k.kind)
            k.__alias_generated__ = True
        key = (k.api_version, k.kind)
        if key in self._kinds:
            existing = self._kinds[key]
            # F3 (spec D3) — declarative ports are ALL the same class
            # (DeclarativeKindPort), so the type(existing) is type(k)
            # check below would silently no-op two DIFFERENT descriptors
            # claiming the same key. Real identity on the declarative
            # path is the descriptor digest: same digest → idempotent
            # no-op; different digest → registration error.
            if (
                getattr(existing, "__declarative__", False)
                and getattr(k, "__declarative__", False)
            ):
                existing_digest = getattr(existing, "__descriptor_digest__", None)
                new_digest = getattr(k, "__descriptor_digest__", None)
                if existing_digest == new_digest:
                    logger.debug(
                        "[kernel] Declarative kind (%r, %r) re-registered "
                        "with identical descriptor digest — idempotent "
                        "no-op.",
                        k.api_version, k.kind,
                    )
                    return
                raise KindRegistrationError(
                    f"Kind ({k.api_version!r}, {k.kind!r}) already "
                    f"registered from a DIFFERENT descriptor (existing "
                    f"alias {existing.alias!r}, new alias {k.alias!r}). "
                    f"Two descriptors cannot claim the same "
                    f"(api_version, kind) key — pick a distinct "
                    f"api_version namespace."
                )
            # H1 — idempotent re-registration: same class re-registering
            # with the same key is a silent no-op + debug log. This
            # mirrors Python's `import` semantics — calling
            # ``kernel.load(MyExtension())`` twice (e.g. in a test that
            # both uses ``build_kernel`` AND explicitly loads the
            # extension) shouldn't crash. A *different* class trying to
            # claim the same key IS still a registration error.
            if type(existing) is type(k):
                logger.debug(
                    "[kernel] Kind (%r, %r) re-registered by same class "
                    "%s — idempotent no-op.",
                    k.api_version, k.kind, type(k).__name__,
                )
                return
            raise KindRegistrationError(
                f"Kind ({k.api_version!r}, {k.kind!r}) already registered "
                f"by {type(existing).__name__}; refusing to overwrite with "
                f"{type(k).__name__}. Two extensions cannot share the same "
                f"(api_version, kind) pair — pick distinct api_version "
                f"namespaces (e.g. {k.api_version}-v2)."
            )
        if k.alias:
            for existing_key, existing_kind in self._kinds.items():
                if getattr(existing_kind, "alias", None) == k.alias:
                    raise KindRegistrationError(
                        f"Kind alias {k.alias!r} already registered by "
                        f"{type(existing_kind).__name__} "
                        f"({existing_key[0]}, {existing_key[1]}); refusing "
                        f"to register {type(k).__name__}. Aliases are the "
                        f"globally-unique key used in dep_filters and "
                        f"templates — pick a distinct value."
                    )
        # 6. Kind-NAME collision across api_versions (i-195). Bare-name
        # lookups (port_for/alias_for/kind_plane/write-path demotion)
        # become ambiguous the moment two api_versions share a kind name
        # — the Reference pair shipped exactly that and silently resolved
        # first-match. New extension Kinds must pick a unique name; the
        # legacy pair is allowlisted (shrink-only ratchet, emptied by the
        # Reference-family merge). Collisions where the EXISTING port is
        # a per-scope declarative shadow (demo scopes' local Doc/EvalCase)
        # don't block the extension from claiming its canonical name.
        if k.kind not in KIND_NAME_COLLISION_ALLOWLIST:
            for (existing_api, existing_name), existing_kind in self._kinds.items():
                if (
                    existing_name == k.kind
                    and existing_api != k.api_version
                    and (
                        not getattr(existing_kind, "__declarative__", False)
                        or getattr(existing_kind, "__builtin_descriptor__", False)
                    )
                ):
                    raise KindRegistrationError(
                        f"Kind NAME {k.kind!r} already registered under "
                        f"api_version {existing_api!r} (alias "
                        f"{getattr(existing_kind, 'alias', None)!r}); refusing "
                        f"{k.api_version!r}. Two api_versions sharing a kind "
                        f"name makes every bare-name lookup ambiguous — pick "
                        f"a distinct kind name (i-195)."
                    )
        # Two-planes lint (spec 2026-06-09, D1) — extracted to a helper
        # (F3 spec D3) so the per-scope KindDefinition funnel
        # (register_kind_definitions) runs the SAME validation.
        self._lint_plane(k)
        sd = getattr(k, "storage", None)
        if sd is not None and getattr(sd, "pattern", None) == StoragePattern.BUNDLE:
            new_pair = (sd.container, sd.marker)
            new_shared_ok = bool(getattr(k, "marker_shared_allowed", False))
            for existing_key, existing_kind in self._kinds.items():
                existing_sd = getattr(existing_kind, "storage", None)
                if existing_sd is None:
                    continue
                if getattr(existing_sd, "pattern", None) != StoragePattern.BUNDLE:
                    continue
                existing_pair = (existing_sd.container, existing_sd.marker)
                if existing_pair != new_pair:
                    continue
                # H1 — explicit opt-in: only allow shared marker if BOTH
                # colliding Kinds set ``marker_shared_allowed = True``.
                # Historical example: autoagent's AgentProgramKind once shared
                # the ``programs/<name>/program.md`` marker with autoresearch's
                # ResearchProgramKind (podado — s-unify-experiment-run-families/
                # OpçãoA), disambiguating via the frontmatter ``dialect:`` field
                # at read time. The opt-in makes any such sharing intentional +
                # greppable; the H3 scanner routes at read time via the dialect
                # field.
                existing_shared_ok = bool(
                    getattr(existing_kind, "marker_shared_allowed", False)
                )
                if new_shared_ok and existing_shared_ok:
                    logger.info(
                        "[kernel] BUNDLE marker shared by design: "
                        "(container=%r, marker=%r) — owners: %s + %s. "
                        "Both Kinds opted in via marker_shared_allowed=True; "
                        "Reader.detect() must disambiguate at read time.",
                        sd.container, sd.marker,
                        type(existing_kind).__name__, type(k).__name__,
                    )
                    continue
                raise KindRegistrationError(
                    f"BUNDLE storage (container={sd.container!r}, "
                    f"marker={sd.marker!r}) already registered by "
                    f"{type(existing_kind).__name__} "
                    f"({existing_key[0]}, {existing_key[1]}); refusing "
                    f"to register {type(k).__name__}. Two bundle Kinds "
                    f"using the same (container, marker) pair would "
                    f"collide in the filesystem scanner. Pick a unique "
                    f"container OR marker — OR set "
                    f"``marker_shared_allowed = True`` on BOTH Kinds AND "
                    f"ensure their Reader.detect() implementations "
                    f"disambiguate at read time (e.g. by frontmatter "
                    f"``dialect`` field)."
                )
        self._kinds[key] = k
        if self._host is not None:
            self._host._generics_resolved = False
        # Resolve docs (DOCS-<Kind>.md > DOCS.md > docs class attr)
        try:
            k._resolved_docs = _load_kind_docs(k)
        except Exception as e:  # pragma: no cover — defensive
            logger.debug("Failed to resolve docs for %s: %s", k.kind, e)
            k._resolved_docs = getattr(k, "docs", None)

    @staticmethod
    def _lint_plane(k: "KindPort") -> None:
        """Two-planes lint (spec 2026-06-09, D1) — plane is explicit and
        validated, never derived. A "record" Kind cannot carry any
        composition signal; contradictions fail registration loudly
        instead of silently mis-routing the write path.

        F3 (spec D3): extracted from ``register_kind()`` so BOTH funnels run
        it — ``register_kind()`` (extension classes + builtin descriptors)
        raises; ``register_kind_definitions`` (per-scope) catches → warn + skip
        (per-scope docs never take the boot down).
        """
        plane = getattr(k, "plane", "composition")
        if plane not in ("composition", "record"):
            raise KindRegistrationError(
                f"Kind {type(k).__name__} has invalid plane={plane!r}; "
                f"expected 'composition' or 'record'."
            )
        if plane == "record":
            contradictions = []
            if getattr(k, "is_prompt_target", False):
                contradictions.append("is_prompt_target=True")
            if getattr(k, "flatten_in_context", False):
                contradictions.append("flatten_in_context=True")
            if getattr(k, "is_schema_affecting", False):
                contradictions.append("is_schema_affecting=True")
            if getattr(k, "is_root", False):
                contradictions.append("storage.pattern==ROOT")
            if contradictions:
                raise KindRegistrationError(
                    f"Kind {type(k).__name__} declares plane='record' but "
                    f"carries composition signals: {', '.join(contradictions)}. "
                    f"Records never compose into agent prompts — either drop "
                    f"the signal or remove plane='record'."
                )

    def register_from_descriptor(self, raw: dict[str, Any]) -> "KindPort":
        """F3 (spec D3): register a BUILTIN Kind from a KindDefinition
        descriptor (``kinds/*.kind.yaml`` package data).

        Same format + same funnel as everything else: parses
        ``TypedKindDefinition``, synthesizes a ``DeclarativeKindPort`` and
        registers it via ``register_kind()`` — so the F1 plane lint and the H1
        validations all apply. The port is stamped with:

        - ``__builtin_descriptor__ = True`` — conflict marker: per-scope
          KindDefinitions on the same key lose to it (warn +
          ``kinddef_conflict`` event + skip), exactly like extension
          classes.
        - ``__descriptor_digest__`` — sha256 of the canonical JSON of the
          raw spec (same recipe as ``sync/hash.py:document_hash`` and the
          TS ``documentHash``). ``register_kind()`` uses it for strong
          idempotency: same digest re-registering → no-op; a DIFFERENT
          descriptor on the same key → ``KindRegistrationError``.

        Returns the registered port (the existing one on an idempotent
        re-register).
        """
        from dna.kernel.meta import DeclarativeKindPort
        from dna.kernel.models import TypedKindDefinition
        from dna.sync.hash import document_hash

        typed = TypedKindDefinition.from_raw(raw)
        port = DeclarativeKindPort.from_typed(typed)
        port.__builtin_descriptor__ = True
        port.__descriptor_digest__ = document_hash(raw.get("spec") or {})
        self.register_kind(port)
        # register_kind() no-ops on an idempotent re-register — hand back
        # whatever is actually registered for the key.
        return self._kinds[(port.api_version, port.kind)]

    def register_kind_definitions(self, all_raws: list[dict[str, Any]]) -> bool:
        """Phase 1 of 2-phase loading: parse KindDefinition docs + register
        synthetic DeclarativeKindPorts on the kernel.

        Extension-registered kinds win on conflict: if a port with the same
        (target_api_version, target_kind) is already registered, the
        declarative one is skipped and a warning is emitted via the
        HookRegistry event ``kinddef_conflict``.
        """
        from dna.kernel.meta import DeclarativeKindPort
        from dna.kernel.models import TypedKindDefinition

        host = self._host
        reader_count_before = len(host._readers)
        registered_any = False

        for raw in all_raws:
            if raw.get("apiVersion") != TypedKindDefinition.API_VERSION:
                continue
            if raw.get("kind") != TypedKindDefinition.KIND:
                continue
            try:
                typed = TypedKindDefinition.from_raw(raw)
            except Exception as e:
                logger.warning("Failed to parse KindDefinition: %s", e)
                if host.hooks.has("parse_error"):
                    from dna.kernel.hooks import HookContext
                    host.hooks.emit("parse_error", HookContext(
                        kind=TypedKindDefinition.KIND,
                        name=(raw.get("metadata") or {}).get("name", ""),
                        data={"error": str(e)},
                    ))
                continue

            key = (typed.spec.target_api_version, typed.spec.target_kind)
            if key in self._kinds:
                existing = self._kinds[key]
                is_builtin_descriptor = getattr(
                    existing, "__builtin_descriptor__", False
                )
                if not getattr(existing, "__declarative__", False) \
                        or is_builtin_descriptor:
                    # Extension-registered kind wins on conflict — and so
                    # does a BUILTIN descriptor (F3 spec D3: builtin
                    # descriptors are extension-registered Kinds that
                    # happen to be declarative; before the marker this
                    # branch skipped them SILENTLY — now they get the
                    # same warn + kinddef_conflict event treatment).
                    # s-kinddef-conflict-once (2026-05-27): warn ONLY the
                    # first time we see each conflict PER PROCESS. Using
                    # module-level cache (not instance attr) because some
                    # call sites create fresh kernel-like wrappers — the
                    # instance-attr version was bypassed and warnings
                    # fired on every MI rebuild, flooding logs.
                    if key not in _GLOBAL_KINDDEF_CONFLICT_WARNED:
                        _GLOBAL_KINDDEF_CONFLICT_WARNED.add(key)
                        logger.warning(
                            "KindDefinition %s/%s conflicts with %s kind; "
                            "keeping it and skipping the per-scope "
                            "declarative port. (further occurrences of "
                            "this same conflict are suppressed "
                            "process-wide)",
                            key[0], key[1],
                            "builtin-descriptor" if is_builtin_descriptor
                            else "extension-registered",
                        )
                    from dna.kernel.hooks import HookContext
                    host.hooks.emit("kinddef_conflict", HookContext(
                        kind=key[1],
                        name=typed.metadata.name,
                        data={
                            "apiVersion": key[0],
                            "reason": (
                                "builtin_descriptor_wins"
                                if is_builtin_descriptor
                                else "extension_wins"
                            ),
                        },
                    ))
                    continue
                # Same declarative port already registered — silent
                # no-op. The 2-phase load path used to re-register here
                # but that produced log spam (3 lines × N scopes per
                # Temporal activity call) AND added 3-5s per case
                # rebuilding the resolved-docs cache. Idempotent
                # re-registration is unnecessary because the kernel's
                # `_kinds` dict already holds the synthesized port from
                # the prior pass. To pick up a NEW version of a
                # KindDefinition, callers should clear `self._kinds[key]`
                # via the explicit unregister path before re-running.
                continue

            try:
                port = DeclarativeKindPort.from_typed(typed)
            except Exception as e:
                logger.error(
                    "Failed to synthesize DeclarativeKindPort for %s/%s: %s",
                    key[0], key[1], e,
                )
                continue
            # F3 (spec D3): the per-scope funnel writes straight into
            # self._kinds (bypassing register_kind()), so the F1 plane lint
            # never ran here. Run the SAME helper — but warn + skip instead of
            # raising: per-scope docs never take the boot down (same
            # contract as the parse_error path above).
            try:
                self._lint_plane(port)
            except KindRegistrationError as e:
                logger.warning(
                    "KindDefinition %s/%s failed the plane lint: %s — "
                    "skipping registration.",
                    key[0], key[1], e,
                )
                if host.hooks.has("parse_error"):
                    from dna.kernel.hooks import HookContext
                    host.hooks.emit("parse_error", HookContext(
                        kind=TypedKindDefinition.KIND,
                        name=typed.metadata.name,
                        data={"error": str(e)},
                    ))
                continue
            self._kinds[key] = port
            host._generics_resolved = False
            registered_any = True
            try:
                port._resolved_docs = _load_kind_docs(port)
            except Exception as e:  # pragma: no cover — defensive
                # fail-soft: docs are cosmetic metadata — mirror the
                # register_kind() path (logs at debug, falls back to class attr).
                logger.debug(
                    "Failed to resolve docs for declarative kind %s: %s",
                    port.kind, e,
                )
                port._resolved_docs = getattr(port, "docs", None)
            logger.info(
                "Registered declarative kind: %s/%s (alias: %s)",
                key[0], key[1], typed.spec.alias,
            )

        # Re-resolve generic readers/writers now that we may have new BUNDLE kinds
        host._ensure_generic_readers_writers()
        return registered_any and len(host._readers) > reader_count_before

    def register_custom_kinds(self, manifest: dict[str, Any]) -> None:
        """Register dynamic kinds from Module.spec.custom_kinds.

        Each entry: {apiVersion, kind, alias, fields: {name: {type, required?, default?}}}
        Creates a minimal KindPort so mi.all("Pipeline") works.
        """
        custom_kinds = manifest.get("spec", {}).get("custom_kinds", [])
        for ck in custom_kinds:
            av = ck.get("apiVersion", "custom/v1")
            kn = ck.get("kind", "")
            alias = ck.get("alias", kn.lower())
            if not kn:
                continue
            key = (av, kn)
            if key in self._kinds:
                continue  # Already registered (by extension or previous call)

            # Create a dynamic KindPort (use _make_dynamic_kind to avoid closure issues)
            dk = self._make_dynamic_kind(av, kn, alias)
            self._kinds[key] = dk
            logger.info("Registered custom kind: %s/%s (alias: %s)", av, kn, alias)

    @staticmethod
    def _make_dynamic_kind(av: str, kn: str, al: str) -> Any:
        """Create a minimal KindPort for a custom kind."""
        class DK:
            api_version = av
            kind = kn
            alias = al
            model = dict
            origin = "custom"
            is_root = False
            is_prompt_target = False
            flatten_in_context = False
            def dep_filters(self): return None
            def dependencies(self): return self.dep_filters()
            def schema(self): return None
            def get_default_agent_name(self, doc): return None
            def get_layer_policies(self, doc): return None
            def parse(self, raw): return raw
            def describe(self, doc): return None
            def summary(self, doc): return None
            def prompt_template(self): return None
        return DK()
