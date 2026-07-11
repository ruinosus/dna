"""kernel_bootstrap — the ``Kernel.auto()`` / ``Kernel.quick()`` boot recipe,
extracted from the Kernel god-object (kernel decomposition, Fase 4 —
``s-kernel-decomp-f4-bootstrap``).

This is the BOOTSTRAP logic: entry-point discovery
(``importlib.metadata.entry_points(group='dna.extensions')``),
the H8 deterministic boot ordering (instantiate-without-registering →
topo-sort via Kahn's algorithm with alphabetical tie-break, respecting
``depends_on`` → register in order), source/cache/resolver wiring
(FilesystemCache + LocalResolver for filesystem sources, ``_NoopCache``
for self-contained non-filesystem sources), the ``KernelAttachable``
auto-wire, and the closing ``validate_dep_filters()`` gate.

The Kernel RETAINS ``auto`` / ``quick`` as THIN classmethods that delegate
their body here — same signature, same return type, same fail-soft posture.

Subclass-preserving contract: ``auto`` / ``quick`` are classmethods that
build ``cls()`` (not a hardcoded ``Kernel()``), so ``Runtime.auto()`` returns
a ``Runtime`` — its ``storage()`` / ``manifest()`` aliases stay reachable
(``test_manifest_loads``). The build helpers therefore take the concrete
class via ``cls`` and default to ``Kernel`` only when called bare.

Import-circularity: this module needs ``Kernel``, and ``Kernel.auto``/``quick``
need these helpers. Both sides import LAZILY inside the function body — by the
time either runs, ``dna.kernel`` is fully imported, so there is no
circular import at module load.
"""
from __future__ import annotations

import importlib.metadata
import logging
from typing import TYPE_CHECKING

from dna.kernel.protocols import EXTENSIONS_ENTRY_POINT_GROUP

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel import Kernel
    from dna.kernel.instance import ManifestInstance
    from dna.kernel.protocols import Extension

# Preserve the historical logger name so ``[kernel] …`` / ``Auto-loaded
# extension`` lines route identically to when this lived in ``kernel/__init__``.
logger = logging.getLogger("dna.kernel")


def build_quick_manifest(
    scope: str, base_dir: str = ".dna", *, cls: type["Kernel"] | None = None,
) -> "ManifestInstance":
    """Quick-start: filesystem Kernel with every discoverable extension loaded,
    returning the ManifestInstance for ``scope``. Body of ``Kernel.quick``."""
    if cls is None:
        from dna.kernel import Kernel
        cls = Kernel

    from dna.adapters.filesystem import FilesystemCache, FilesystemSource
    from dna.adapters.resolvers import (
        HelixResolver, GitHubResolver, HttpResolver, LocalResolver,
        RegistryResolver,
    )

    k = cls()
    k.source(FilesystemSource(base_dir))
    k.cache(FilesystemCache(base_dir))
    k.resolver("local", LocalResolver(base_dir=base_dir))
    k.resolver("github", GitHubResolver())
    k.resolver("http", HttpResolver())
    k.resolver("https", HttpResolver())
    k.resolver("registry", RegistryResolver())
    k.resolver("helix", HelixResolver())

    # Load all extensions via entry-point discovery
    for ep in importlib.metadata.entry_points(group=EXTENSIONS_ENTRY_POINT_GROUP):
        try:
            ext_cls = ep.load()
            k.load(ext_cls())
        except Exception as e:  # noqa: BLE001
            # fail-soft: one broken extension must not take discovery down
            # — but the boot is now missing Kinds, so this is an ERROR.
            logger.error("Failed to load extension %s: %s", ep.name, e)

    return k.instance(scope)


def build_auto_kernel(
    source=None, *, cls: type["Kernel"] | None = None,
) -> "Kernel":
    """Create a Kernel with all discoverable extensions loaded.

    Uses importlib.metadata.entry_points (group='dna.extensions')
    to find all installed extensions — both built-in (helix, agentskills,
    soulspec, agentsmd, guardrails, github) and contrib packages (dna-claudemd,
    dna-mcptools, etc.) that declare the same entry-point group.

    If source is provided, also wires source + cache + resolvers.
    Filesystem sources get FilesystemCache + LocalResolver.
    Non-filesystem sources get a noop cache (all docs self-contained).

    Body of ``Kernel.auto``. ``cls`` is the concrete Kernel subclass to
    instantiate (defaults to ``Kernel``) so ``Runtime.auto()`` returns a Runtime.
    """
    if cls is None:
        from dna.kernel import Kernel
        cls = Kernel

    k = cls()

    eps = list(importlib.metadata.entry_points(group=EXTENSIONS_ENTRY_POINT_GROUP))

    # H8 — explicit boot ordering. Two stages:
    #   1. Load every entry-point's class WITHOUT registering it
    #      (just instantiate, read `depends_on` if declared).
    #   2. Topologically sort by declared deps; fallback to
    #      alphabetical (entry-point name, stable across runs).
    #   3. Register in sorted order.
    #
    # Pre-H8: entry-point iteration order was alphabetical-by-name
    # (Python's importlib.metadata default), which silently
    # determined who "won" marker collisions before H1 closed that
    # specific bug. With H1 + H3 the explicit boot order matters
    # less for correctness, but stability across Python versions /
    # pip cache states is still valuable for reproducible behavior
    # (cache invalidation observers, hook subscription order, etc.).
    loaded: list[tuple[str, "Extension"]] = []
    for ep in eps:
        try:
            ext_cls = ep.load()
            ext = ext_cls()
            loaded.append((ep.name, ext))
        except Exception as e:  # noqa: BLE001
            # fail-soft: same posture as ep.load above — boot continues,
            # missing Kinds is an ERROR, not a warning.
            logger.error("Failed to instantiate extension %s: %s", ep.name, e)

    # Build name → ext map and dep graph
    name_to_ext: dict[str, "Extension"] = {n: e for n, e in loaded}
    deps_map: dict[str, set[str]] = {}
    for name, ext in loaded:
        declared = getattr(ext, "depends_on", ())
        if isinstance(declared, str):
            declared = (declared,)
        deps_map[name] = {d for d in declared if d in name_to_ext}

    # Kahn's algorithm with alphabetical tie-breaking
    sorted_order: list[str] = []
    remaining = set(name_to_ext.keys())
    # Build reverse-dependency count
    in_degree: dict[str, int] = {n: len(deps_map[n]) for n in remaining}
    while remaining:
        # Ready: in_degree==0 AND in remaining; alphabetical tie-break
        ready = sorted(n for n in remaining if in_degree[n] == 0)
        if not ready:
            # Cycle: log and break by alphabetical order on the rest
            logger.error(
                "[kernel] dependency cycle in extensions: %s — "
                "falling back to alphabetical for unresolved nodes.",
                sorted(remaining),
            )
            ready = sorted(remaining)
        for n in ready:
            sorted_order.append(n)
            remaining.discard(n)
            # Decrement in-degree of nodes that depend on n
            for other, deps in deps_map.items():
                if n in deps and other in remaining:
                    in_degree[other] -= 1

    for name in sorted_order:
        try:
            k.load(name_to_ext[name])
            logger.info("Auto-loaded extension: %s", name)
        except Exception as e:  # noqa: BLE001
            # fail-soft: discovery survives one broken extension — but the
            # kernel now runs WITHOUT its Kinds/hooks, so this is an ERROR.
            logger.error("Failed to load extension %s: %s", name, e)

    if source is not None:
        k.source(source)
        if source.supports_readers:
            from dna.adapters.filesystem import FilesystemCache
            from dna.adapters.resolvers import LocalResolver
            base_dir = str(source.base_dir)
            k.cache(FilesystemCache(base_dir))
            k.resolver("local", LocalResolver(base_dir=base_dir))
        else:
            k.cache(_NoopCache())
        # H2 — uniform auto-wiring via KernelAttachable capability.
        # Every WritableSource (FS / SQLite / Postgres / custom)
        # that implements ``attach_kernel`` gets wired identically.
        # Eliminates the historical FilesystemWritableSource-only
        # special case at this site, and the silent
        # bundle-write-drop bug when callers did
        # ``Kernel.auto(source=SqlAlchemySource(...))`` directly.
        from dna.kernel.capabilities import KernelAttachable
        if isinstance(source, KernelAttachable):
            source.attach_kernel(k)
        else:
            logger.debug(
                "[kernel] source %s does not implement KernelAttachable. "
                "If it's a writable source, bundle entries may not be "
                "persisted via the kernel's writers. Implement "
                "attach_kernel on the adapter or wire writers via "
                "the constructor.",
                type(source).__name__,
            )

    # s-alias-generated-not-typed — com TODAS as extensions carregadas,
    # todo dep_filter builtin deve resolver pra um alias registrado.
    # Antes: alias com typo degradava o prompt silenciosamente (warning
    # enterrado); agora o boot falha apontando o Kind + campo + alias.
    k.validate_dep_filters()

    return k


def build_from_config(
    path: str | None = None, *, cls: type["Kernel"] | None = None,
) -> "Kernel":
    """Body of ``Kernel.from_config`` — read ``dna.config.yaml``, resolve every
    port to its adapter, return the wired Kernel.

    No config present (and no ``path``) → default filesystem ``.dna`` source,
    unchanged. Otherwise the config's ``source`` URL is resolved through the
    public ``source_from_url`` factory (file/sqlite/postgres), then ``search`` /
    ``embedding`` providers are wired when requested. SQL migrations run on a
    short-lived loop here so this stays a synchronous boot-time factory.
    """
    import asyncio

    if cls is None:
        from dna.kernel import Kernel
        cls = Kernel

    from dna.adapters.source_url import resolve_default_fs_url, source_from_url
    from dna.config import load_config

    cfg = load_config(path)
    source_url = cfg.source if cfg is not None else resolve_default_fs_url()

    # Build (+ connect, for SQL) the source on a throwaway loop. Filesystem
    # sources fill their writers via attach_kernel below, so no kernel is
    # needed at construction time.
    source = asyncio.run(source_from_url(source_url))

    # build_auto_kernel wires source + cache + resolvers + attach_kernel
    # (writers/readers) + the dep-filter validation gate — one recipe, reused.
    k = build_auto_kernel(source, cls=cls)

    if cfg is not None:
        _wire_search(k, cfg)
        _wire_embedding(k, cfg)

    return k


def _wire_embedding(kernel: "Kernel", cfg) -> None:
    """Register the embedding provider named in the config. ``off`` / ``fake``
    leave the deterministic fake floor in place (zero heavy deps); ``onnx``
    imports + registers the real all-MiniLM provider (opt-in extra)."""
    if cfg.embedding in ("off", "fake"):
        return
    if cfg.embedding == "onnx":
        from dna.adapters.embedding.onnx import OnnxEmbeddingProvider
        kernel.embedding_provider(OnnxEmbeddingProvider())


def _wire_search(kernel: "Kernel", cfg) -> None:
    """Register the record-search provider named in the config. ``off`` leaves
    the lexical fallback; ``sqlite-vec`` / ``pgvector`` import + register the
    matching opt-in provider (the latter reuses the config's Postgres DSN)."""
    if cfg.search == "off":
        return
    if cfg.search == "sqlite-vec":
        from dna.adapters.search.sqlite_vec import SqliteVecRecordSearchProvider
        kernel.record_search_provider(SqliteVecRecordSearchProvider(kernel))
    elif cfg.search == "pgvector":
        from dna.adapters.search.pgvector import PgVecRecordSearchProvider
        kernel.record_search_provider(
            PgVecRecordSearchProvider(kernel, dsn=cfg.source)
        )


class _NoopCache:
    """Minimal CachePort for non-filesystem sources (all docs self-contained)."""

    async def load_all(self, scope, readers=None):
        return []

    async def load_key(self, scope, key, readers=None):
        return []

    async def store(self, scope, key, items):
        pass

    async def has(self, scope, key):
        return True  # Pretend cache is always hit → skip resolver calls
