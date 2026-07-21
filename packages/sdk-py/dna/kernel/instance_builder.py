"""InstanceBuilder — the kernel's ManifestInstance construction, extracted from
the Kernel god-object (kernel-decompose-continue).

Behavior-preserving: ``build`` (pure compute), ``instance`` / ``instance_async``
(load + dep-resolve + layer + scope-inherit + lazy/eager), ``resolve_layers`` /
``resolve_layers_async``, and the two rescan helpers move verbatim; the kernel
keeps the public five + the helpers as thin delegators (build/instance/
instance_async/resolve_layers are heavily used — operations, admin, runtime,
deps, agent routes — all unchanged). Holds a back-ref to the kernel for the
accessors it needs; ``ManifestInstance`` is constructed with ``kernel=self._k``.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from dna.kernel.protocols import CacheItem, ResolveError

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import InstanceBuilderHost
    from dna.kernel.document import Document
    from dna.kernel.instance import ManifestInstance

logger = logging.getLogger(__name__)


class InstanceBuilder:
    """Builds ManifestInstances. One per kernel; back-ref to it."""

    def __init__(self, kernel: "InstanceBuilderHost") -> None:
        self._k = kernel

    def build(
        self,
        raw_docs: list[dict],
        scope: str,
        layers: dict[str, str] | None = None,
        layer_docs: list[dict] | None = None,
        dep_docs: list[dict] | None = None,
        resolve_errors: list[str] | None = None,
        *,
        skip_async_rescan: bool = False,
    ) -> "ManifestInstance":
        """Build a ManifestInstance from pre-loaded data. Pure computation, no
        I/O. ``skip_async_rescan`` suppresses the sync rescan when an async
        caller (instance_async) will run it itself."""
        from dna.kernel import _run_sync_helper
        from dna.kernel.instance import ManifestInstance
        k = self._k
        k._ensure_generic_readers_writers()

        # Register custom kinds from the manifest root doc (is_root).
        manifest_raw = next(
            (r for r in raw_docs
             if any(
                 getattr(kp, "is_root", False)
                 for (_, kn), kp in k._kinds.items()
                 if kn == r.get("kind")
             )),
            None,
        )
        if manifest_raw:
            k._register_custom_kinds(manifest_raw)

        # Merge source docs + dep docs
        all_raws: list[dict[str, Any]] = list(raw_docs)
        if dep_docs:
            for raw in dep_docs:
                raw["_origin"] = raw.get("_origin", "dep")
            all_raws.extend(dep_docs)

        # Apply layers if provided
        if layers and layer_docs:
            from dna.kernel.layer_resolver import DefaultLayerResolver
            from dna.kernel.protocols import LayerPolicy

            # Declared Kind-name → alias map from the live registry, so the
            # resolver matches policies by DECLARATION instead of inferring
            # the doc→policy relation from name shape (i-044).
            kind_aliases: dict[str, str] = {}
            for (_av, _kname), _kp in k._kinds.items():
                _alias = getattr(_kp, "alias", None)
                if _alias:
                    kind_aliases.setdefault(_kname, _alias)

            resolver = DefaultLayerResolver(kind_aliases=kind_aliases)
            policies: dict[str, LayerPolicy] = {}

            # LayerPolicy docs (filter by current layer ids); merge across all
            # matching docs, last write wins per alias.
            wanted_layer_ids = set(layers.keys()) if layers else set()
            for raw in all_raws:
                if raw.get("kind") != "LayerPolicy":
                    continue
                lp_spec = (raw.get("spec") or {})
                if not isinstance(lp_spec, dict):
                    continue
                if lp_spec.get("layer_id") not in wanted_layer_ids:
                    continue
                lp_policies = lp_spec.get("policies") or {}
                if not isinstance(lp_policies, dict):
                    continue
                for alias, ps in lp_policies.items():
                    try:
                        policies[alias] = LayerPolicy(str(ps).lower())
                    except ValueError:
                        policies[alias] = LayerPolicy.OPEN

            # Typo detection (i-044): a policy key that names NO registered
            # Kind (by name or alias) — and no declarative Kind shipped as a
            # KindDefinition doc in this build — can never match anything.
            # That is exactly how `helix-agnet: locked` silently degrades the
            # strongest protection in the system to OPEN, so it warns.
            if policies:
                import re as _re
                import warnings as _warnings
                known_keys: set[str] = set()
                kind_tails: set[str] = set()
                for (_av, _kname), _kp in k._kinds.items():
                    known_keys.add(_kname)
                    known_keys.add(_kname.lower())
                    kind_tails.add(_kname.lower())
                    kind_tails.add(
                        _re.sub(r"(?<!^)(?=[A-Z])", "-", _kname).lower()
                    )
                    _alias = getattr(_kp, "alias", None)
                    if _alias:
                        known_keys.add(_alias)
                # KindDefinition docs register AFTER layer resolution (Phase
                # 1 below) — accept their declared aliases/targets up front
                # so legitimate declarative-kind policies don't warn.
                for raw in all_raws:
                    if raw.get("kind") != "KindDefinition":
                        continue
                    kd_spec = raw.get("spec") or {}
                    if not isinstance(kd_spec, dict):
                        continue
                    for key in ("alias", "target_kind"):
                        v = kd_spec.get(key)
                        if isinstance(v, str) and v:
                            known_keys.add(v)
                            known_keys.add(v.lower())
                            kind_tails.add(v.lower())

                def _matchable(key: str) -> bool:
                    if key in known_keys:
                        return True
                    # The resolver's legacy suffix heuristics would still
                    # connect this key to a registered Kind — legal, if
                    # inferred; not a typo.
                    return any(
                        key == tail or key.endswith(f"-{tail}")
                        for tail in kind_tails
                    )

                for policy_key in sorted(k2 for k2 in policies if not _matchable(k2)):
                    _warnings.warn(
                        f"LayerPolicy declares a policy for {policy_key!r}, "
                        f"but no registered Kind has that name or alias — "
                        f"this entry will never match, and the Kind it was "
                        f"meant to govern falls back to OPEN. Check for a "
                        f"typo.",
                        stacklevel=2,
                    )

            class _DirectSource:
                def load_layer(self, _scope, _lid, _lv):
                    return layer_docs

            all_raws = resolver.resolve(all_raws, layers, _DirectSource(), scope, policies)

        # ── Phase 1: parse + register KindDefinitions ──
        added_readers = k._register_kind_definitions(all_raws)

        # If new declarative kinds introduced readers/markers, re-scan the source
        # so instance docs of those kinds are picked up. Async callers pass
        # skip_async_rescan=True and run the rescan themselves.
        if added_readers and k._source is not None and not skip_async_rescan:
            try:
                extra = _run_sync_helper(
                    k._source.load_all(scope, readers=k._readers),
                    loop=k._main_loop,
                )
                self._merge_rescan_extras(all_raws, extra)
            except Exception as e:  # pragma: no cover — defensive
                logger.debug("Declarative-kind rescan failed: %s", e)

        # ── Phase 2: parse all docs via KindPorts ──
        documents: list[Document] = []
        _resolve_errors: list[str] = resolve_errors or []
        for raw in all_raws:
            # two-planes F2.5 (spec §F2.5): plane="record" Kinds never enter
            # the MI materialization — the MI is O(composição). Filter BEFORE
            # _parse_doc (the parse is the dominant cost, not the load_all
            # I/O). Record reads go through the kernel record plane
            # (mi.all/one delegation, kernel.query/get_document).
            # Exact (apiVersion, kind) lookup first; on miss fall back to
            # kind_plane (by NAME) — real datasets hold legacy apiVersion
            # variants (e.g. github.com/ruinosus/dna/cognitive/v1 Engram) that would
            # otherwise materialize yet be unreachable via the delegated
            # mi.all/one (which resolves by name). Unregistered kind names
            # stay composition (kind_plane fail-safe) — behavior unchanged.
            # Follow-up (fora deste plano): push-down do filtro de plane pro
            # load_all pra poupar também o I/O.
            # Perf note: fallback by-name é ~20ms/14.7k docs — memoize name→plane se o registry crescer.
            kp = k._kinds.get((raw.get("apiVersion", ""), raw.get("kind", "")))
            plane = (
                getattr(kp, "plane", "composition")
                if kp is not None
                else k.kind_plane(raw.get("kind", ""))
            )
            if plane == "record":
                continue
            origin = raw.pop("_origin", "local") if "_origin" in raw else "local"
            doc = k._parse_doc(raw, origin=origin)
            if doc:
                documents.append(doc)

        # F2.5 review C2 — stamp the request tenant on the EAGER MI too,
        # mirroring the lazy path in ``instance_async`` (kernel binding
        # first, then layers["tenant"]); the ``__base__`` sentinel means
        # no-overlay → no stamp. Without this the record-delegation
        # branches (mi.all/one → kernel.query/get_document with
        # ``getattr(mi, "_tenant", None)``) read tenant=None and
        # tenant-overlay records go invisible for tenanted requests.
        effective_tenant = k.tenant
        if effective_tenant is None and layers:
            effective_tenant = layers.get("tenant")
        if effective_tenant == "__base__":
            effective_tenant = None

        mi = ManifestInstance(
            scope=scope,
            documents=documents,
            kinds=k._kinds,
            source=k._source,
            resolve_errors=_resolve_errors,
            kernel=k,
            profiles=k._profiles,
        )
        if effective_tenant:
            mi._tenant = effective_tenant
        return mi

    def _merge_rescan_extras(self, all_raws: list[dict], extra: list[dict]) -> None:
        """Merge re-scan results into ``all_raws`` deduped by
        (apiVersion, kind, name). Shared between sync and async rescan paths."""
        seen_keys = {
            (r.get("apiVersion", ""), r.get("kind", ""),
             (r.get("metadata") or {}).get("name", ""))
            for r in all_raws
        }
        for r in extra:
            key = (r.get("apiVersion", ""), r.get("kind", ""),
                   (r.get("metadata") or {}).get("name", ""))
            if key not in seen_keys:
                all_raws.append(r)
                seen_keys.add(key)

    async def _rescan_after_kinddef_register_async(
        self, scope: str, all_raws: list[dict], added_readers: bool,
    ) -> None:
        """Async sibling of the rescan block in ``build`` — awaits load_all
        directly (no sync-in-loop guard). Called from ``instance_async``."""
        k = self._k
        if not added_readers or k._source is None:
            return
        try:
            extra = await k._source.load_all(scope, readers=k._readers)
            self._merge_rescan_extras(all_raws, extra)
        except Exception as e:
            logger.debug("Declarative-kind rescan (async) failed: %s", e)

    def instance(self, scope: str, layers: dict[str, str] | None = None) -> "ManifestInstance":
        """Sync wrapper around ``instance_async``. From inside an event loop,
        prefer ``await instance_async`` to avoid the run-in-thread fallback."""
        from dna.kernel import _run_sync_helper
        return _run_sync_helper(
            self.instance_async(scope, layers), loop=self._k._main_loop,
        )

    async def instance_async(
        self, scope: str, layers: dict[str, str] | None = None,
        *, lazy: bool | None = None,
    ) -> "ManifestInstance":
        """Async-native MI construction. Phase 9 tenant binding auto-promotes
        into layers; ``lazy`` opts into bootstrap-only MI (mi.all/one delegate
        to kernel.query). Default honors DNA_LAZY_MI."""
        k = self._k
        k._ensure_generic_readers_writers()
        assert k._source, "No source registered. Call kernel.source() first."
        assert k._cache, "No cache registered. Call kernel.cache() first."

        if layers is None and k.tenant:
            layers = {"tenant": k.tenant}

        # Short-circuit to the per-scope base MI cache when no real overlay is
        # requested (the __base__ sentinel, or layers=None + tenant=None) — avoids
        # a full MI rebuild on every no-tenant activity / cognitive-hook fire.
        if (
            lazy is None
            and (
                (
                    layers is not None
                    and len(layers) == 1
                    and layers.get("tenant") == "__base__"
                )
                or (layers is None and k.tenant is None)
            )
        ):
            return await k._base_instance_cached_async(scope)

        # 1. Load bootstrap docs (Genome + KindDefinition + LayerPolicy).
        effective_tenant = k.tenant
        if effective_tenant is None and layers:
            effective_tenant = layers.get("tenant")
        bootstrap_docs = await k._source.load_bootstrap_docs(
            scope, tenant=effective_tenant,
        )

        # 1a. Find the Genome doc (dependency resolution).
        manifest: dict[str, Any] = {}
        for d in bootstrap_docs:
            if d.get("kind") == "Genome":
                manifest = d
                break

        # 2. Resolve deps (auto on cache miss)
        dep_docs: list[dict[str, Any]] = []
        resolve_errors: list[str] = []
        dep_uri_by_key: dict[str, str] = {}
        deps = manifest.get("spec", {}).get("dependencies", [])
        for dep in deps:
            uri = dep.get("source", "")
            scheme = uri.split(":")[0] if ":" in uri else ""
            resolver = k._resolvers.get(scheme)
            if not resolver:
                resolve_errors.append(f"No resolver for scheme '{scheme}' in {uri}")
                continue
            key = resolver.cache_key(uri)
            dep_uri_by_key[key] = uri
            if not await k._cache.has(scope, key):
                try:
                    resolved = await resolver.resolve(uri, dep)
                    cache_items = [
                        CacheItem(name=r.name, kind=r.kind, content_path=r.source_path)
                        for r in resolved
                    ]
                    await k._cache.store(scope, key, cache_items)
                except ResolveError as e:
                    resolve_errors.append(f"Resolve error for {uri}: {e}")
                    logger.warning("Resolve error for %s: %s", uri, e)

        # 3. Load source docs + cache docs (lazy resolution order: explicit
        # kwarg > DNA_LAZY_MI env > off; non-tenant layers force eager).
        layer_keys = set((layers or {}).keys())
        non_tenant_layers = layer_keys - {"tenant"}
        if lazy is True and not non_tenant_layers:
            _lazy_enabled = True
        elif lazy is False:
            _lazy_enabled = False
        else:
            _lazy_enabled = (
                os.environ.get("DNA_LAZY_MI", "0") == "1"
                and not non_tenant_layers
            )
        if _lazy_enabled:
            from dna.kernel.instance import ManifestInstance
            parsed_bootstrap: list[Document] = []
            for raw in bootstrap_docs:
                doc = k._parse_doc(raw, origin="local")
                if doc:
                    parsed_bootstrap.append(doc)
            mi = ManifestInstance(
                scope=scope,
                documents=parsed_bootstrap,
                kinds=k._kinds,
                source=k._source,
                resolve_errors=resolve_errors,
                kernel=k,
                profiles=k._profiles,
                lazy=True,
            )
            if effective_tenant:
                mi._tenant = effective_tenant
            return mi

        raw_docs = await k._source.load_all(scope, readers=k._readers)

        # Scope-level inheritance — load _INHERIT_PARENT_SCOPE docs filtered to
        # _INHERITABLE_KINDS, merge with local (local wins by (kind, name)).
        if scope != k._INHERIT_PARENT_SCOPE:
            try:
                parent_raws = await k._source.load_all(
                    k._INHERIT_PARENT_SCOPE, readers=k._readers,
                )
            except Exception as e:  # noqa: BLE001
                # fail-soft: a missing/broken parent scope contributes no
                # inherited docs — but scope-level inheritance silently
                # turning OFF is a visible degradation, so it logs loud.
                logger.warning(
                    "instance build: parent scope %r load failed — "
                    "inherited docs unavailable for %r: %s",
                    k._INHERIT_PARENT_SCOPE, scope, e,
                )
                parent_raws = []
            local_keys = {
                (r.get("kind"), (r.get("metadata") or {}).get("name") or r.get("name"))
                for r in raw_docs
            }
            for praw in parent_raws:
                pkind = praw.get("kind")
                if pkind not in k._INHERITABLE_KINDS:
                    continue
                pname = (praw.get("metadata") or {}).get("name") or praw.get("name")
                if (pkind, pname) in local_keys:
                    continue
                praw.setdefault("_inherited_from", k._INHERIT_PARENT_SCOPE)
                raw_docs.append(praw)

        for key, uri in dep_uri_by_key.items():
            key_raws = await k._cache.load_key(scope, key, readers=k._readers)
            for raw in key_raws:
                raw["_origin"] = uri
            dep_docs.extend(key_raws)

        # 4. Load layer docs if needed
        layer_docs: list[dict] | None = None
        if layers:
            layer_docs = []
            for layer_id, value in layers.items():
                ld = await k._source.load_layer(
                    scope, layer_id, value, readers=k._readers,
                )
                layer_docs.extend(ld)

        # build does kinddef-register + sync rescan; here we already hold a loop,
        # so we ask build to skip the sync rescan and run the async rescan
        # ourselves on the same all_raws build will assemble.
        all_raws_for_rescan = list(raw_docs)
        if dep_docs:
            all_raws_for_rescan.extend(dep_docs)
        added_readers = k._register_kind_definitions(all_raws_for_rescan)
        await self._rescan_after_kinddef_register_async(
            scope, all_raws_for_rescan, added_readers,
        )
        if len(all_raws_for_rescan) > len(raw_docs) + (len(dep_docs) if dep_docs else 0):
            return self.build(
                all_raws_for_rescan, scope, layers, layer_docs, None,
                resolve_errors, skip_async_rescan=True,
            )
        return self.build(
            raw_docs, scope, layers, layer_docs, dep_docs, resolve_errors,
            skip_async_rescan=True,
        )

    def resolve_layers(self, mi: "ManifestInstance", layers: dict[str, str]) -> "ManifestInstance":
        """Resolve layers on an existing MI (sync wrapper)."""
        return self.instance(mi.scope, layers=layers)

    async def resolve_layers_async(
        self, mi: "ManifestInstance", layers: dict[str, str],
    ) -> "ManifestInstance":
        """Async-native layer resolver — MI.resolve_async() delegates here."""
        return await self.instance_async(mi.scope, layers=layers)
