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

from dna.kernel.invalidation_cost import (
    emit_rebuild,
    invalidation_logging_enabled,
    now,
)
from dna.kernel.protocols import CacheItem, ResolveError

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import InstanceBuilderHost
    from dna.kernel.instance import Instance
    from dna.kernel.manifest import ManifestInstance

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
        caller (instance_async) will run it itself.

        i-123 — ⭐ **é AQUI que o custo da invalidação de escopo aparece.** Uma
        escrita com ``invalidate_mode="scope"`` derruba o cache base e não gasta
        quase nada fazendo isso; o que ela realmente faz é obrigar este método a
        rodar de novo na próxima leitura daquele escopo. O evento ``rebuild``
        emitido no fim carrega ``docs`` e ``ms`` na MESMA linha porque é a
        regressão de um contra o outro que responde à pergunta do fundador — se
        o custo é O(tamanho do escopo).
        """
        from dna.kernel import _run_sync_helper
        from dna.kernel.manifest import ManifestInstance
        k = self._k
        # Desligado: uma comparação de nível, e o relógio fica intocado.
        observing = invalidation_logging_enabled()
        started = now() if observing else 0.0
        skipped_by_plane = 0
        k._ensure_generic_readers_writers()

        # Register custom kinds from the manifest root doc (is_root).
        manifest_raw = next(
            (r for r in raw_docs
             if any(
                 getattr(kp, "is_root", False)
                 for (_, kn), kp in k.kinds_for_scope(scope).items()
                 if kn == r.get("kind")
             )),
            None,
        )
        if manifest_raw:
            k._register_custom_kinds(manifest_raw, scope=scope)

        # Merge source docs + dep docs
        all_raws: list[dict[str, Any]] = list(raw_docs)
        if dep_docs:
            for raw in dep_docs:
                raw["_origin"] = raw.get("_origin", "dep")
            all_raws.extend(dep_docs)

        # Apply layers if provided
        if layers and layer_docs:
            from dna.kernel.compose.layer_resolver import DefaultLayerResolver
            from dna.kernel.protocols import LayerPolicy

            # Declared Kind-name → alias map from the live registry, so the
            # resolver matches policies by DECLARATION instead of inferring
            # the doc→policy relation from name shape (i-044).
            kind_aliases: dict[str, str] = {}
            for (_av, _kname), _kp in k.kinds_for_scope(scope).items():
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
                for (_av, _kname), _kp in k.kinds_for_scope(scope).items():
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
        # i-081: these instances came from THIS scope's store, and the Kinds
        # they declare govern this scope and no other.
        added_readers = k._register_kind_definitions(all_raws, scope=scope)

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
        # i-081: from here on the MI is built against the Kinds that GOVERN this
        # scope — the globals plus the ones this scope's own store declared.
        # Another scope's store-loaded Kind is not in this map, so it cannot
        # route this scope's storage, validate its instances or compose into
        # its prompts.
        _scoped_kinds = k.kinds_for_scope(scope)
        instances: list[Instance] = []
        _resolve_errors: list[str] = resolve_errors or []
        for raw in all_raws:
            # two-planes F2.5 (spec §F2.5): plane="record" Kinds never enter
            # the MI materialization — the MI is O(composição). Filter BEFORE
            # _parse_doc (the parse is the dominant cost, not the load_all
            # I/O). Record reads go through the kernel record plane
            # (mi.all/one delegation, kernel.query/get_instance).
            # Exact (apiVersion, kind) lookup first; on miss fall back to
            # kind_plane (by NAME) — real datasets hold legacy apiVersion
            # variants (e.g. github.com/ruinosus/dna/cognitive/v1 Engram) that would
            # otherwise materialize yet be unreachable via the delegated
            # mi.all/one (which resolves by name). Unregistered kind names
            # stay composition (kind_plane fail-safe) — behavior unchanged.
            # Follow-up (fora deste plano): push-down do filtro de plane pro
            # load_all pra poupar também o I/O.
            # Perf note: fallback by-name é ~20ms/14.7k docs — memoize name→plane se o registry crescer.
            kp = _scoped_kinds.get(
                (raw.get("apiVersion", ""), raw.get("kind", "")),
            )
            plane = (
                getattr(kp, "plane", "composition")
                if kp is not None
                else k.kind_plane(raw.get("kind", ""), scope=scope)
            )
            if plane == "record":
                # i-123 — o que o plano ``record`` POUPA, contado. Um ``+= 1``
                # de inteiro é o custo desta linha ligada ou desligada; medir
                # isto atrás do gate exigiria repetir a condição do filtro.
                skipped_by_plane += 1
                continue
            origin = raw.pop("_origin", "local") if "_origin" in raw else "local"
            doc = k._parse_doc(raw, origin=origin)
            if doc:
                instances.append(doc)

        # F2.5 review C2 — stamp the request tenant on the EAGER MI too,
        # mirroring the lazy path in ``instance_async`` (kernel binding
        # first, then layers["tenant"]); the ``__base__`` sentinel means
        # no-overlay → no stamp. Without this the record-delegation
        # branches (mi.all/one → kernel.query/get_instance with
        # ``getattr(mi, "_tenant", None)``) read tenant=None and
        # tenant-overlay records go invisible for tenanted requests.
        effective_tenant = k.tenant
        if effective_tenant is None and layers:
            effective_tenant = layers.get("tenant")
        if effective_tenant == "__base__":
            effective_tenant = None

        mi = ManifestInstance(
            scope=scope,
            instances=instances,
            kinds=_scoped_kinds,
            source=k._source,
            resolve_errors=_resolve_errors,
            kernel=k,
            profiles=k._profiles,
        )
        if effective_tenant:
            mi._tenant = effective_tenant
        if observing:
            emit_rebuild(
                # ``all_raws``, e não ``raw_docs``: é o conjunto que este build
                # de fato percorreu (fontes + deps + camadas + rescan), que é o
                # denominador honesto do "é O(tamanho do escopo)?".
                docs=len(all_raws), materialized=len(instances),
                skipped=skipped_by_plane, ms=(now() - started) * 1000.0,
            )
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

    async def _parent_scopes(self, scope: str) -> list[str]:
        """The DECLARED ancestors of ``scope``, nearest first — the same walk
        the instances take (``compute_resolution_chain``), fail-soft to the V1
        single ``_lib`` hop when the chain cannot be read.

        Factored out because i-096 needs the identical answer the instance
        merge below already computes: one chain, one meaning of "parent", or
        instances and Kinds inherit along two different graphs."""
        k = self._k
        if scope == k._INHERIT_PARENT_SCOPE:
            return []
        try:
            chain = await k._compute_resolution_chain(scope, None)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "instance build: resolution chain failed for %r — "
                "falling back to single parent %r: %s",
                scope, k._INHERIT_PARENT_SCOPE, e,
            )
            return [k._INHERIT_PARENT_SCOPE]
        seen: list[str] = []
        for s, _t in chain:
            if s != scope and s not in seen:
                seen.append(s)
        return seen

    async def _register_inherited_kind_definitions(
        self, scope: str, parents: list[str] | None = None,
    ) -> bool:
        """i-096 — register the Kinds ``scope``'s DECLARED ANCESTORS declare, so
        the child scope can read *and write* them. Returns the rescan gate.

        The asymmetry this closes. Instances already flow down the declared
        chain (``compute_resolution_chain``, the merge in ``instance_async``
        below), but the KINDS did not: ``KindDefinition`` is a BOOTSTRAP Kind,
        so a base-scope descriptor was loaded and registered **bound to the base
        scope only** (i-081's ``__scopes__``). In a child scope the Kind then
        did not exist — ``kinds_for(scope)`` filtered it out — so
        ``GET /v1/kinds/<K>/instances?tenant=<ws>`` 404'd and a write was refused
        with *"Kind 'K' is not registered on this source"*, while instances of
        that very Kind listed fine through the child. Every PRODUCT Kind
        therefore had to become an extension (code + release) instead of a
        instance, which is the declarative-Kind promise inverted.

        **What this is NOT (the i-081 guard-rail).** Inheritance descends the
        DECLARED chain and nothing else. A sibling scope — one that merely
        exists in the same store, or that shares the same parent — is on no
        chain of this scope, so its instances are never even read here. The
        widening is per (child scope, ancestor descriptor); it is not a
        relaxation of ``applies_to``, which still answers from ``__scopes__``
        alone, so every other filter i-081 installed keeps its exact shape.

        **Precedence is local-wins**, the same as the instances': this pass runs
        AFTER the scope's own Phase 1, and ``inherited_from=`` makes the funnel
        never replace an already-registered descriptor. A nearer ancestor also
        beats a farther one for the same reason — ``parents`` is nearest-first,
        and the first pass to register a key owns it.

        **Cost**: one ``load_bootstrap_docs`` per ancestor per MI build (the
        bootstrap SLICE — Genome + KindDefinition + LayerPolicy, not the scope).
        On the eager path that sits beside a full ``load_all`` per ancestor, so
        it is noise; on the lazy path it is what ``LiveDna.ensure_kinds``
        already pays per scope per TTL window.

        Fail-soft, per ancestor: an unreadable ancestor contributes no Kinds and
        logs — a scope that cannot be read must not turn a request that would
        have worked into an error.
        """
        k = self._k
        if k._source is None:
            return False
        if parents is None:
            parents = await self._parent_scopes(scope)
        added_readers = False
        for parent in parents:
            try:
                parent_bootstrap = await k._source.load_bootstrap_docs(parent)
            except Exception as e:  # noqa: BLE001
                # DEBUG, unlike the instance merge's WARNING for the same
                # ancestor: this pass runs on the TTL'd ``ensure_kinds`` refresh
                # for EVERY scope, and its commonest miss is the V1 ``_lib``
                # tail every chain ends at, which most deployments never
                # materialize as a real scope. A line per scope per window for
                # an expected absence is noise that buries the real ones. The
                # instance merge below still logs loud for a parent that holds
                # content and cannot be read.
                logger.debug(
                    "instance build: ancestor scope %r bootstrap load failed — "
                    "its declared Kinds are unavailable in %r: %s",
                    parent, scope, e,
                )
                continue
            if not parent_bootstrap:
                continue
            added_readers |= k._register_kind_definitions(
                parent_bootstrap, scope=scope, inherited_from=parent,
            )
        return added_readers

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
        to kernel.query). Default honors DNA_LAZY_MI.

        ``lazy`` trades away the INSTANCE materialization, never the Kind
        registry: both branches run Phase 1 (register the Kinds this scope's
        store declares) so a lazily-booted kernel enforces the same schemas and
        routes to the same containers an eagerly-booted one does."""
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
            from dna.kernel.manifest import ManifestInstance
            # Phase 1, on the lazy path too — the bootstrap load exists FOR
            # this. ``BOOTSTRAP_KIND_NAMES`` puts ``KindDefinition`` first
            # precisely so a scope's own declared Kinds are registered before
            # anything parses against them; this branch was loading those
            # instances and parsing them while never running the registration
            # pass, so no store-declared Kind ever reached the registry. Since
            # registration is what confers schema validation and storage
            # routing, on a lazy boot an APPROVED Kind governed nothing and
            # every registry consumer — the write pipeline, the generic
            # instance use-cases, the MI's own kinds map two lines below —
            # answered "that Kind is not registered on this source".
            #
            # ``lazy`` is a trade about INSTANCES (the MI holds bootstrap only
            # and delegates ``all``/``one`` to ``kernel.query``), not about
            # KINDS. The instances this pass reads are already in hand, so the
            # cost is a parse over the bootstrap slice and nothing else.
            #
            # ``scope=`` binds the resulting Kinds to the scope whose store
            # declared them, exactly as the eager path does (i-081); the
            # approval gate lives inside the funnel, so an unapproved
            # KindDefinition is parsed and warn-skipped here as everywhere.
            #
            # What is deliberately NOT done: the declarative-kind RESCAN the
            # eager path runs when registration added a bundle reader
            # (``_rescan_after_kinddef_register_async``). That rescan re-reads
            # every instance in the scope to enrich an instance list a lazy MI
            # does not hold — it is exactly the cost ``lazy`` exists to avoid,
            # and the reader it would use was installed on the kernel by the
            # registration call itself, so the on-demand reads a lazy MI
            # delegates to ``kernel.query`` pick those instances up anyway.
            k._register_kind_definitions(bootstrap_docs, scope=scope)
            # i-096 — and the Kinds the DECLARED ANCESTORS declare, AFTER the
            # local pass so a local declaration wins. This branch is the one
            # ``LiveDna.ensure_kinds`` drives, so it is the branch the REST/MCP
            # instance routes resolve their Kind against: without it, the
            # inheritance would exist only on the eager path and a workspace
            # would see the base's Kinds or not depending on which surface it
            # arrived through.
            await self._register_inherited_kind_definitions(scope)
            # The second door onto the same registry (``custom_kinds`` on the
            # scope's root instance, same approval gate) — wired here too, or
            # "lazy and eager agree on the registry" would hold for one door
            # and not the other.
            lazy_root_raw = next(
                (r for r in bootstrap_docs
                 if any(
                     getattr(kp, "is_root", False)
                     for (_, kn), kp in k.kinds_for_scope(scope).items()
                     if kn == r.get("kind")
                 )),
                None,
            )
            if lazy_root_raw:
                k._register_custom_kinds(lazy_root_raw, scope=scope)
            parsed_bootstrap: list[Instance] = []
            for raw in bootstrap_docs:
                doc = k._parse_doc(raw, origin="local")
                if doc:
                    parsed_bootstrap.append(doc)
            mi = ManifestInstance(
                scope=scope,
                instances=parsed_bootstrap,
                kinds=k.kinds_for_scope(scope),
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

        # Scope-level inheritance — walk the DECLARED parent chain
        # (``Genome.spec.parent_scope``, transitively) via the SAME
        # ``compute_resolution_chain`` the query/resolve paths use (i-058:
        # one mechanism, every consumer — this eager materialization serves
        # ``list_agents`` and ``compose_prompt``, which were blind to a
        # declared parent and only saw the fixed ``_lib`` hop). The chain
        # ends at ``_INHERIT_PARENT_SCOPE`` through the V1 fallback, so a
        # scope with no Genome / no ``parent_scope`` loads EXACTLY the
        # single ``_lib`` hop it always did (golden-pinned in
        # ``tests/test_workspace_definitions_inheritance.py``).
        #
        # Precedence: local wins by (kind, name); then a NEARER parent
        # shadows a farther one, in chain order.
        #
        # Cache-staleness boundary (documented, pinned by test): this build
        # is NOT wired to the resolver's ``_layer_observers`` reverse-dep
        # graph. A doc write in a PARENT scope does not drop a child's
        # cached base MI (``_base_instance_cached*`` consumers — policy
        # checks, MIHolder/Studio — may serve the parent's OLD docs until
        # their own scope invalidates or the process reloads; identical to
        # the pre-chain behavior for ``_lib`` writes). The request paths
        # (``LiveDna.mi`` → ``instance_async(lazy=False)``) rebuild per
        # call and see parent writes immediately; only the declared
        # ``parent_scope`` VALUE itself rides the granular Genome cache
        # (TTL ``_GRANULAR_DOC_TTL``).
        #
        # ``_parent_scopes`` holds the walk (and its fail-soft degradation to
        # the V1 single hop) so the i-096 Kind pass below asks the SAME
        # question: one chain, one meaning of "parent".
        parent_scopes = await self._parent_scopes(scope)
        if parent_scopes:
            seen_keys = {
                (r.get("kind"), (r.get("metadata") or {}).get("name") or r.get("name"))
                for r in raw_docs
            }
            for parent in parent_scopes:
                try:
                    parent_raws = await k._source.load_all(
                        parent, readers=k._readers,
                    )
                except Exception as e:  # noqa: BLE001
                    # fail-soft: a missing/broken parent scope contributes no
                    # inherited docs — but scope-level inheritance silently
                    # turning OFF is a visible degradation, so it logs loud.
                    logger.warning(
                        "instance build: parent scope %r load failed — "
                        "inherited docs unavailable for %r: %s",
                        parent, scope, e,
                    )
                    continue
                added_keys: set[tuple[Any, Any]] = set()
                for praw in parent_raws:
                    pkind = praw.get("kind")
                    if pkind not in k._INHERITABLE_KINDS:
                        continue
                    pname = (praw.get("metadata") or {}).get("name") or praw.get("name")
                    if (pkind, pname) in seen_keys:
                        continue
                    praw.setdefault("_inherited_from", parent)
                    raw_docs.append(praw)
                    added_keys.add((pkind, pname))
                # Keys join the dedup set only after the whole parent is
                # processed: a nearer parent shadows a farther one, while
                # duplicates WITHIN one parent keep the pre-chain behavior
                # (both append — byte-compat with the single-hop merge).
                seen_keys |= added_keys

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
        added_readers = k._register_kind_definitions(
            all_raws_for_rescan, scope=scope,
        )
        # i-096 — the ancestors' declared Kinds, AFTER the local pass (local
        # wins) and BEFORE the rescan (an inherited BUNDLE Kind installs a
        # reader the rescan must then use).
        added_readers |= await self._register_inherited_kind_definitions(
            scope, parent_scopes,
        )
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
