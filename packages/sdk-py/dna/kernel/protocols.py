"""v3 Kernel Protocols — the 5 ports + shared types."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Protocol, runtime_checkable

from dna.kernel.bundle_handle import BundleHandle  # noqa: F401  re-exported for typing

if TYPE_CHECKING:
    from dna.kernel.capabilities import SourceCapabilities


# ---------------------------------------------------------------------------
# Query types (Marco A — f-source-as-query, 2026-05-14)
#
# Shared aliases consumed by ``SourcePort.query``. Kept simple on purpose:
# the contract here is just JSON-shaped. Adapters translate to their
# native query language (Postgres SQL with jsonb operators, SQLite
# json_extract, Python filter on a list).
# ---------------------------------------------------------------------------

# A filter is a flat dict of (field-path → value).
#
#   {"status": "in-progress"}                  # equality on spec.status
#   {"feature": "f-foo", "owner": "alice"}     # AND of equalities
#   {"status": {"in": ["todo", "in-progress"]}}  # IN list
#   {"updated_at": {"gt": "2026-05-01"}}       # gt / gte / lt / lte
#   {"title": {"like": "%kernel%"}}            # SQL LIKE pattern
#
# Field paths address the doc envelope rooted at the raw dict
# (``kind``, ``metadata``, ``spec``, ``apiVersion``). Unprefixed keys
# resolve under ``spec.`` by convention so common filters stay short
# (``{"status": "in-progress"}`` ≡ ``{"spec.status": "in-progress"}``).
# Use the explicit ``metadata.name`` or ``kind`` path when needed.
#
# Operators are restricted to the set above. Adapters reject unknown
# operators with ``QueryError``. No nested OR/AND in v1 — keep the
# surface minimal; if you need OR, issue two queries.
QueryFilter = dict[str, Any]

# Projection is a list of dotted field paths to include in each row.
#
#   ["name"]                              # just the slug (always under metadata.name)
#   ["name", "spec.title", "spec.status"] # typical list view
#   None                                  # return the FULL raw dict
#
# Like filters, unprefixed paths resolve under ``spec.``. ``name`` is a
# reserved short for ``metadata.name``.
QueryProjection = list[str]

# Ordering is a list of field paths optionally prefixed with ``-`` for
# descending. Adapters apply ORDER BY in declaration order.
#
#   ["-spec.updated_at"]                  # most recent first
#   ["spec.feature", "-spec.priority"]
QueryOrder = list[str]


class QueryError(ValueError):
    """Raised when a query filter / projection / order_by is malformed
    in a way the adapter can detect statically (unknown operator,
    invalid field path, …). Adapters convert their backend errors
    (Postgres syntax, SQLite parse) into this so callers can handle a
    single exception type."""


# Operators recognized by both adapter push-down and the default
# Python fallback. Adapters MUST raise ``QueryError`` for unknown ops.
_QUERY_OPS = frozenset({"eq", "in", "like", "gt", "gte", "lt", "lte", "neq"})


def _resolve_field_path(doc: dict[str, Any], path: str) -> Any:
    """Walk a dotted ``field_path`` through ``doc``. Unprefixed paths
    resolve under ``spec.``; ``name`` is a reserved short for
    ``metadata.name``. Returns ``None`` when any segment is missing.

    Shared by the Python fallback in ``SourcePort.query`` and by the
    Filesystem adapter (push-down via SQL is handled per-adapter).
    """
    if path == "name":
        meta = doc.get("metadata") or {}
        return meta.get("name") if isinstance(meta, dict) else None
    if path == "kind":
        return doc.get("kind")
    if path == "apiVersion":
        return doc.get("apiVersion")
    if path.startswith("metadata.") or path.startswith("spec.") or path.startswith("apiVersion."):
        segments = path.split(".")
    else:
        # Unprefixed → assume spec.
        segments = ["spec"] + path.split(".")
    cur: Any = doc
    for seg in segments:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(seg)
        if cur is None:
            return None
    return cur


def _match_filter(doc: dict[str, Any], filter: QueryFilter) -> bool:
    """Evaluate a ``QueryFilter`` against a single doc. Used by the
    default Python fallback in ``SourcePort.query`` and by adapters
    that filter in memory (Filesystem). Unknown operators raise
    ``QueryError`` so the caller can debug instead of silently match.
    """
    for path, expected in filter.items():
        actual = _resolve_field_path(doc, path)
        if isinstance(expected, dict) and len(expected) == 1:
            op, val = next(iter(expected.items()))
            if op not in _QUERY_OPS:
                raise QueryError(
                    f"unknown query operator {op!r} on field {path!r}; "
                    f"valid: {sorted(_QUERY_OPS)}"
                )
            if op == "eq" and actual != val:
                return False
            if op == "neq" and actual == val:
                return False
            if op == "in" and actual not in (val or ()):
                return False
            if op == "like":
                if actual is None or not isinstance(val, str):
                    return False
                # SQL LIKE: % = any, _ = single char. Build the regex by
                # tokenizing the pattern so we escape ONLY the literals.
                import re as _re
                regex_parts: list[str] = []
                for ch in str(val):
                    if ch == "%":
                        regex_parts.append(".*")
                    elif ch == "_":
                        regex_parts.append(".")
                    else:
                        regex_parts.append(_re.escape(ch))
                if not _re.match(f"^{''.join(regex_parts)}$", str(actual)):
                    return False
            if op == "gt" and not (actual is not None and actual > val):
                return False
            if op == "gte" and not (actual is not None and actual >= val):
                return False
            if op == "lt" and not (actual is not None and actual < val):
                return False
            if op == "lte" and not (actual is not None and actual <= val):
                return False
        else:
            # Shorthand: {"status": "in-progress"} == {"status": {"eq": ...}}
            if actual != expected:
                return False
    return True


def _project_doc(doc: dict[str, Any], projection: QueryProjection) -> dict[str, Any]:
    """Build a sparse dict from ``doc`` containing only the fields in
    ``projection`` (dotted paths). ``name`` is always added (callers
    rely on it for routing). Nested paths reconstruct the partial
    tree shape.
    """
    out: dict[str, Any] = {}
    paths = list(projection)
    if "name" not in paths:
        paths = ["name", *paths]
    for path in paths:
        val = _resolve_field_path(doc, path)
        if val is None:
            continue
        # Reconstruct nested shape.
        if path == "name":
            out["name"] = val
            continue
        if path in ("kind", "apiVersion"):
            out[path] = val
            continue
        segments = (
            path.split(".") if (
                path.startswith("metadata.") or path.startswith("spec.")
            ) else ["spec", *path.split(".")]
        )
        cur = out
        for seg in segments[:-1]:
            cur = cur.setdefault(seg, {})
        cur[segments[-1]] = val
    return out


def _apply_order_by(rows: list[dict[str, Any]], order_by: QueryOrder) -> list[dict[str, Any]]:
    """Stable sort ``rows`` by each ``order_by`` field, last-first to
    achieve the desired primary/secondary precedence. Prefixed ``-``
    means descending. ``None`` values sort last regardless of order.

    Mixed-type values (int + str across rows on the same field) sort
    by string repr to avoid TypeError. Adapters with native push-down
    use the backend's type semantics; this fallback is best-effort.
    """
    for spec in reversed(order_by):
        descending = spec.startswith("-")
        path = spec[1:] if descending else spec

        def _key(r, _p=path):
            v = _resolve_field_path(r, _p)
            # (None-flag, sortable-value): None always sorts last. The flag
            # must be immune to ``reverse`` — XOR with ``descending`` so the
            # reverse pass puts None at the END too (i-121: parity with PG
            # ``DESC NULLS LAST``; a plain ``v is None`` flips under reverse
            # and shoves Nones to the FRONT in DESC).
            return ((v is None) != descending, "" if v is None else str(v) if not isinstance(v, (int, float)) else v)

        # Two passes so int/str mixed doesn't crash on the second-element compare.
        try:
            rows = sorted(rows, key=_key, reverse=descending)
        except TypeError:
            # Fallback: stringify everything. Same i-121 XOR on the None flag.
            rows = sorted(
                rows,
                key=lambda r, _p=path: (
                    (_resolve_field_path(r, _p) is None) != descending,
                    str(_resolve_field_path(r, _p) or ""),
                ),
                reverse=descending,
            )
    return rows


# ---------------------------------------------------------------------------
# Extension discovery
# ---------------------------------------------------------------------------

EXTENSIONS_ENTRY_POINT_GROUP = "dna.extensions"


# ---------------------------------------------------------------------------
# Phase 16 — bootstrap kinds
#
# Kinds the kernel needs registered/parsed BEFORE ``load_all`` fires.
# ``SourcePort.load_bootstrap_docs`` returns documents of these kinds
# in priority order; adapters that can filter cheaply (SQL ``WHERE
# kind IN (...)``) SHOULD do so. Adapters that scan everything anyway
# (filesystem) MAY return a superset; the kernel filters defensively.
#
# Order is meaningful: KindDefinition first (custom Kinds need to be
# registered before parsing other docs), LayerPolicy next (kernel
# reads at write-time), Genome last (root identity).
# ---------------------------------------------------------------------------

BOOTSTRAP_KIND_NAMES = ("KindDefinition", "LayerPolicy", "Genome")
"""Kind names returned by ``load_bootstrap_docs``, in registration order."""


async def package_doc_for_scope(
    source: "SourcePort", scope: str, *, tenant: str | None = None,
) -> dict | None:
    """Return the Genome doc for ``scope`` (or ``None`` if missing).

    Phase 16 helper — pulls bootstrap docs and filters for the Genome
    Kind. Tenant-aware: when ``tenant`` is set, the underlying adapter
    applies tenant-overlay routing (tenant-published Genome shadows
    platform).
    """
    bootstrap = await source.load_bootstrap_docs(scope, tenant=tenant)
    for d in bootstrap:
        if d.get("kind") == "Genome":
            return d
    return None
"""Entry-point group for extension auto-discovery.

Any Python package can register extensions by declaring this group in
pyproject.toml:

    [project.entry-points."dna.extensions"]
    myext = "my_package:MyExtension"

Kernel.auto() and Kernel.quick() use this group to discover and load
all installed extensions automatically.
"""


# ---------------------------------------------------------------------------
# Layer policy
# ---------------------------------------------------------------------------

class LayerPolicy(str, Enum):
    """Controls what a layer overlay can do to a kind's documents."""
    OPEN = "open"            # Deep merge spec, can add new documents
    RESTRICTED = "restricted" # Only override existing keys in spec, can't add new docs
    LOCKED = "locked"        # Block all changes (warn only)


# ---------------------------------------------------------------------------
# Tenant scope (Kubernetes-style: each KindPort declares its scope)
# ---------------------------------------------------------------------------

class TenantScope(str, Enum):
    """Whether a Kind's documents belong to a tenant or are globally shared.

    Mirrors the Kubernetes CRD ``scope: Namespaced | Cluster`` model. Each
    KindPort declares its scope; the kernel enforces it on every write.

    - ``TENANTED`` (default): documents belong to one tenant. Writing
      requires a tenant arg; reading is filtered by tenant. Agent,
      EvalCase, EvalRun, AssessmentRun, Finding, etc.
    - ``GLOBAL``: documents are shared across all tenants. Writes must
      not pass a tenant; reads ignore the bound tenant. Doc,
      KindDefinition, Module-level configs, etc.
    """
    TENANTED = "tenanted"
    GLOBAL = "global"


# Reserved tenant slugs — never accepted as user input
RESERVED_TENANT_SLUGS = frozenset({"_global", "_legacy", "_system", ""})


# ── Special scopes (i-112) ──────────────────────────────────────────────────
# Single source of truth para os nomes de scope-mágico que estavam espalhados
# como literais. Renomeado "_platform"→"_lib" (f-platform-rename-lib, big-bang
# 2026-06-16) — o scope-biblioteca compartilhado agora se chama "_lib". DOIS
# papéis distintos (ver spec
# docs/superpowers/specs/2026-06-09-scope-model-system-catalog-base-design.md):
#   DEFAULT_BASE_SCOPE — fallback de herança quando um Genome omite parent_scope.
#   SYSTEM_SCOPE       — casa dos lookups globais do runtime (model registry,
#                        voice policy), lidos NÃO-herdavelmente.
# Ambos = "_lib" hoje; nomeados separados pra Fases futuras poderem divergir
# (ex: split _lib=conteúdo vs _system=config-de-runtime).
DEFAULT_BASE_SCOPE = "_lib"
SYSTEM_SCOPE = "_lib"


class TenantRequired(Exception):
    """Raised when a TENANTED kind is written without a tenant arg.

    Bind a tenant on construction (``Kernel(tenant=X)``) or per-call
    (``kernel.with_tenant(X).write_document(...)``).
    """


class TenantNotAllowed(Exception):
    """Raised when a GLOBAL kind is written with a tenant arg.

    Global kinds (Doc, KindDefinition, ...) are shared across
    tenants. Writes must explicitly pass ``tenant=None``.
    """


class VersionAlreadyPublished(Exception):
    """Raised when a Module is published at an existing semver version.

    Phase 10 — releases are immutable (npm/Cargo/Helm convention). To
    ship a fix, bump and republish (``dna package bump patch``). The
    24h unpublish window (``DELETE /catalog/.../@<version>``) is the
    only way to take a release back.
    """


class InvalidTenantSlug(Exception):
    """Raised when a tenant slug is empty, reserved (_global, _legacy,
    _system), or contains invalid characters (anything other than
    [a-z0-9-]). Slug rules align with k8s namespace + DNS label.
    """


def validate_tenant_slug(tenant: str | None) -> None:
    """Raise InvalidTenantSlug if tenant is not None and is reserved.

    Phase 1 only checks the reserved set + non-empty/length. Character
    rules (DNS-label, lowercase) are NOT enforced at the kernel boundary
    so existing tests/data using uppercase ("T1", "Acme") keep working.
    Path-traversal safety lives in the adapter (e.g.
    ``_validate_layer_segments`` in FilesystemWritableSource).

    Phase 2 may tighten to k8s namespace rules (``[a-z0-9-]{1,63}``)
    once the migration is complete.
    """
    if tenant is None:
        return
    if tenant in RESERVED_TENANT_SLUGS:
        raise InvalidTenantSlug(
            f"tenant slug {tenant!r} is reserved (one of {sorted(RESERVED_TENANT_SLUGS)})"
        )
    if not (1 <= len(tenant) <= 253):
        raise InvalidTenantSlug(
            f"tenant slug {tenant!r} must be 1-253 chars (got {len(tenant)})"
        )


class LayerPolicyViolationError(Exception):
    """Raised when a write to a layer violates the declared LayerPolicy
    in ``Module.spec.layers``.

    - LOCKED on the alias: any write raises.
    - RESTRICTED: writes that add new top-level spec keys raise; writes
      that only override existing keys are allowed.
    - OPEN: never raises.

    Raised by ``Kernel.write_document`` before the adapter is touched.
    Harness endpoints translate this to HTTP 403.
    """
    pass


# ---------------------------------------------------------------------------
# Composition result
# ---------------------------------------------------------------------------

@dataclass
class CompositionResult:
    """Result of validating cross-kind references.

    resolved: list of successfully resolved refs (e.g., "brad.soul=brad → found")
    missing: list of missing refs (e.g., "brad.soul=nonexistent → NOT FOUND")
    warnings: list of non-fatal issues
    deferred: refs whose target Kind is plane="record" (two-planes F2.5,
        spec D6). Records are excluded from the MI materialization, so the
        engine can't check them against the doc index — they resolve
        lazily via the kernel record plane at read time. Deferred refs
        are NOT missing: ``valid`` ignores them.
    """
    resolved: list[str]
    missing: list[str]
    warnings: list[str]
    deferred: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.missing) == 0


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

@dataclass
class CacheItem:
    """An item stored in cache."""
    name: str
    kind: str
    content_path: Path
    raw: dict | None = None


@dataclass
class ResolvedItem:
    """An item resolved from an external source."""
    name: str
    kind: str
    source_path: Path


class ResolveError(Exception):
    """Raised when dependency resolution fails."""


class ResolveNotFoundError(ResolveError):
    """Source URI target not found (404, missing path, etc.)."""


class ResolveAuthError(ResolveError):
    """Authentication/authorization failure (401, 403)."""


class ResolveNetworkError(ResolveError):
    """Network-level failure (timeout, DNS, connection refused)."""


# ---------------------------------------------------------------------------
# Port protocols
# ---------------------------------------------------------------------------

@runtime_checkable
class SourcePort(Protocol):
    """WHERE — load documents from storage."""

    @property
    def supports_readers(self) -> bool:
        """Whether this source uses ReaderPort plugins to detect bundles.

        Filesystem sources return True (they walk directories).
        Database sources return False (documents are self-contained JSON).
        Used by Kernel.auto() to decide whether to wire cache + resolvers.
        """
        return False

    async def load_bootstrap_docs(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the docs the kernel needs registered/parsed BEFORE
        ``load_all`` fires.

        Phase 16 — replaces the cardinality-1 ``load_manifest`` contract
        with a list of bootstrap-priority docs. Generalizes for
        multiple "system" Kinds:

        - ``KindDefinition`` (``dna.kind/v1``) — custom Kind schemas.
          Registered first so subsequent parsing has the types
          available.
        - ``LayerPolicy`` (``github.com/ruinosus/dna/policy/v1``) — overlay rules read by
          the kernel at write-time enforcement.
        - ``Genome`` (``github.com/ruinosus/dna/v1``) — scope-root identity Kind.
          Used by ``mi.root`` and dependency resolution
          (``Genome.spec.dependencies``).

        Adapters that can filter cheaply (SQL ``WHERE kind IN (...)``)
        SHOULD do so. Adapters that scan everything (filesystem) MAY
        return a superset — the kernel filters defensively.

        Tenant semantics: when ``tenant`` is set, the tenant-published
        Genome SHADOWS the platform Genome (Phase 9 multi-tenant
        publishing). KindDefinition + LayerPolicy stay platform-only
        (non-overlayable per Phase 16).
        """
        ...

    async def load_all(
        self, scope: str, readers: list[ReaderPort] | None = None
    ) -> list[dict[str, Any]]: ...

    async def resolve_ref(self, scope: str, ref: str) -> str: ...

    async def load_layer(
        self, scope: str, layer_id: str, layer_value: str,
        readers: list | None = None,
    ) -> list[dict[str, Any]]: ...

    async def close(self) -> None: ...

    # L1 (s-sourceport-granular-protocol, 2026-05-14) — granular access.
    #
    # ``load_all`` carrega TODOS os docs do scope + bundle entries (N+1
    # query no caso PG → 3-19s para 1510 docs). Para hot paths que
    # querem só metadata (/tree) ou 1 doc (/docs/Kind/Name), isso é
    # custo desproporcional. Os 2 métodos abaixo permitem acesso
    # granular sem reconstruir a ManifestInstance inteira.
    #
    # s-sourceport-contract-cleanup: o suporte é DECLARADO via
    # ``SourceCapabilities.granular_list``/``granular_one`` (nunca
    # hasattr). Adapters sem impl caem no fallback que itera load_all().

    async def list_doc_refs(
        self, scope: str, *, kind: str | None = None,
        tenant: str | None = None,
    ) -> list[tuple[str, str]]:
        """Lista (kind, name) de todos os docs do scope. Filtrável por
        kind. Retorna metadata only — sem bundle entries, sem parse.

        Custo esperado:
        - Postgres: 1 SELECT indexed → 10-20ms para 1510 rows.
        - Filesystem: directory walk sem parse → 30-50ms.
        - SQLite: 1 SELECT indexed → 5-10ms.

        Tenant: quando ``tenant`` é passado, retorna a união do base
        layer com o overlay (tenant-published shadows platform).
        ``None`` (default) = base only.
        """
        ...

    async def load_one(
        self, scope: str, kind: str, name: str, *,
        readers: list[ReaderPort] | None = None,
        tenant: str | None = None,
    ) -> dict[str, Any] | None:
        """Carrega UM doc específico com seu bundle (se aplicável).
        Retorna o raw dict (kind, name, spec, metadata) ou None se
        não encontrado.

        Custo esperado:
        - Postgres: 1-2 SELECTs (content + bundle_entries) → 5-10ms.
        - Filesystem: parse de 1 bundle → 10-30ms.
        - SQLite: 1-2 SELECTs → 3-8ms.

        Tenant: idem ``list_doc_refs``. Overlay shadows base quando
        ambos existem.
        """
        ...

    # Marco A (f-source-as-query, 2026-05-14) — query layer.
    #
    # ``query`` é o método-substrate da arquitetura production-viable
    # (spec: docs/superpowers/specs/2026-05-14-production-viable-kernel.md).
    # Substitui o pattern "load_all + filter em Python" por push-down
    # nativo no source. Postgres traduz para 1 SQL com WHERE +
    # jsonb_build_object para projection; SQLite usa json_extract;
    # Filesystem itera arquivos e filtra em Python (OK porque FS-source
    # é só dev mode com scopes pequenos).
    #
    # Retorna AsyncIterator em vez de list para que o caller decida
    # materializar. List views materializam até ``limit``; agent paths
    # que iteram scope inteiro podem streamar.
    #
    # s-sourceport-contract-cleanup: o suporte é DECLARADO via
    # ``SourceCapabilities.query_pushdown`` (nunca hasattr). Sources sem
    # impl são servidos pelo kernel via ``query_fallback.query_via_load_all``.
    # Adapters concretos (Postgres/FS/SQLite) shippam impl em paridade.

    async def query(
        self, scope: str, kind: str, *,
        filter: QueryFilter | None = None,
        projection: QueryProjection | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: QueryOrder | None = None,
        tenant: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Push-down query sobre o storage do scope.

        Args:
            scope: identificador do scope (ex: ``dna-development``).
            kind: nome do Kind (ex: ``Story``). Multi-kind queries
                não são suportadas em v1 — chame múltiplas vezes em
                ``asyncio.gather`` (ou use o endpoint composto HTTP).
            filter: ``QueryFilter`` — dict de field_path → value. Veja
                a docstring de ``QueryFilter`` para shape + operadores.
                ``None`` = sem filtro.
            projection: ``QueryProjection`` — lista de field_paths para
                incluir em cada row. ``None`` = retorna raw dict
                completo (mesmo shape de ``load_one``). Quando
                projection é dada, rows são objects com apenas os
                campos pedidos (mais ``name`` sempre presente).
            limit: máximo de rows a retornar. ``None`` = sem limite.
                Recomendado SEMPRE passar limit em hot paths para
                proteger contra scopes que crescem.
            offset: paginação. Usado com ``limit``. Default 0.
            order_by: ``QueryOrder``. ``None`` = ordem natural do
                adapter (insertion order para FS; índice padrão para
                SQL). Use ``"-spec.field"`` para descending.
            tenant: overlay aware. ``None`` = base layer only. Slug
                = união base + overlay com overlay shadowing base
                (mesma semântica de ``load_one`` + ``load_layer``).

        Returns:
            ``AsyncIterator[dict]`` — itera rows. Caller pode materializar
            via ``[r async for r in source.query(...)]`` ou consumir
            preguiçosamente.

        Raises:
            QueryError — filter/projection/order_by malformado em forma
                detectável estaticamente (operador inválido, path com
                sintaxe quebrada). Adapters podem levantar erros
                runtime (timeout, conexão) — esses propagam como
                exceções nativas do backend.

        Custo esperado (1500 docs no scope, filter+limit típicos):
        - Postgres: 1 SELECT indexed → 5-30ms.
        - Filesystem: glob + parse + filter em Python → 30-150ms.
        - SQLite: 1 SELECT indexed → 3-15ms.

        Examples:
            # List view: 50 Stories in-progress mais recentes
            async for row in source.query(
                "dna-development", "Story",
                filter={"status": "in-progress"},
                projection=["name", "spec.title", "spec.feature"],
                order_by=["-spec.updated_at"],
                limit=50,
            ):
                ...

            # Cross-tenant: union base + acme overlay
            async for row in source.query(
                "hr-screening", "Agent",
                tenant="acme",
            ):
                ...

            # Single-field count helper (materialized)
            rows = [r async for r in source.query(
                scope, "Issue", filter={"status": "open"},
                projection=["name"],
            )]
            assert len(rows) == open_count

        Implementations:
            Concrete adapters (Postgres / SQLite / Filesystem) ship
            impls in parity and declare ``query_pushdown=True`` in
            their ``SourceCapabilities``. Sources without a native
            impl are served by the kernel via the load_all fallback in
            ``dna.kernel.query_fallback.query_via_load_all``
            (s-sourceport-contract-cleanup: the fallback used to be a
            ~60-line concrete body HERE, reaching back into the
            mediator via ``getattr(self, "_kernel")`` — the Protocol
            now declares the signature only).
        """
        ...

    async def count(
        self, scope: str, kind: str, *,
        filter: QueryFilter | None = None,
        group_by: str | None = None,
        tenant: str | None = None,
    ) -> dict[str, Any]:
        """Aggregation push-down (two-planes F2, spec D2): total de docs
        que casam o ``filter``, opcionalmente agrupados por um field_path
        (``group_by``, mesma convenção do QueryFilter — ex.: ``spec.status``).

        Returns:
            ``{"total": int, "groups": list[{"key", "count"}] | None}`` —
            groups ordenados por count DESC; key None agrupa docs sem o campo.

        Fallbacks vivem em ``dna.kernel.query_fallback``
        (``count_via_query`` ride o ``query`` do adapter;
        ``count_via_load_all`` é o caminho kernel-side p/ sources sem
        query nativo). Adapters SQL fazem override com
        ``SELECT count(*) … GROUP BY`` nativo.
        """
        ...

    # Phase 14w — bundle binary entry fetch.
    #
    # Implementations are OPTIONAL — the Kernel checks via hasattr
    # before delegating, so adapters that don't override get a clean
    # NotImplementedError. Filesystem adapter ships an impl out of the
    # box; SQLite/Postgres impls land alongside the bundle round-trip
    # work from Phase 8 PR2 (`dna_bundle_entries` table).
    #
    # `fetch_bundle_entry(scope, kind, name, entry, *, tenant=None) -> bytes`
    #   Fetch a binary file from inside a bundle (e.g. graph.json
    #   from a GraphifyArtifact bundle, scripts/run.py from a Skill
    #   bundle). Adapters MUST honor the tenant overlay convention:
    #   if `tenant` is set and the bundle exists under
    #   `tenants/<tenant>/scopes/<scope>/<container>/<name>/`, return
    #   that overlay's bytes; otherwise fall through to the base layer.
    #   Raises `FileNotFoundError` when the bundle or entry is missing.


@runtime_checkable
class RecordSearchProvider(Protocol):
    """Two-planes F2 (spec D2): semantic search over record docs. The PG
    adapter (pgvector+RRF) lives in harness-shared and registers itself on
    the kernel at app boot — the kernel core gains NO LLM/embedding deps.
    Without a provider, kernel.search() degrades to an in-memory lexical
    scan (explicit ``degraded: True`` — never fake similarity).

    Hit shape: the guaranteed intersection across providers and the lexical
    fallback is ``{scope, kind, name, score}`` — RRF hits carry extra fields
    (title/snippet/rank components) that callers must treat as optional."""

    async def search(
        self, *, scope: str, query_text: str, kind: str | None = None,
        k: int = 10, tenant: str = "",
    ) -> list[dict[str, Any]]: ...


# Two-planes F2 (spec D2) — ``RecordStorePort`` used to be declared HERE as a
# near-verbatim copy of the writable-source contract (its own docstring
# admitted: "NÃO é uma interface nova... FORMALIZA o contrato que os sources
# writáveis já satisfazem"). s-sourceport-contract-cleanup unified the two:
# ``WritableSourcePort`` IS the single contract (save_document /
# delete_document / query / count — identical signatures). ``RecordStorePort``
# survives as a deprecated module-level alias (see ``__getattr__`` at the
# bottom of this file); the fifth record-plane operation, ``search``, still
# lives on ``RecordSearchProvider`` registered on the kernel.


@runtime_checkable
class CachePort(Protocol):
    """WHERE — store/retrieve installed deps."""

    async def load_all(
        self, scope: str, readers: list[ReaderPort] | None = None
    ) -> list[dict[str, Any]]: ...

    async def load_key(
        self, scope: str, key: str, readers: list[ReaderPort] | None = None
    ) -> list[dict[str, Any]]: ...

    async def store(self, scope: str, key: str, items: list[CacheItem]) -> None: ...

    async def has(self, scope: str, key: str) -> bool: ...


@runtime_checkable
class ResolverPort(Protocol):
    """FROM — fetch external deps."""

    async def resolve(self, uri: str, dep: dict[str, Any]) -> list[ResolvedItem]: ...

    def cache_key(self, uri: str) -> str: ...


@runtime_checkable
class ReaderPort(Protocol):
    """Reads a bundle and produces a raw dict.

    Phase 8 (PR1) — ``detect`` and ``read`` now receive a
    ``BundleHandle`` instead of a ``pathlib.Path``. The handle abstracts
    over filesystem, Postgres, S3, in-memory dict — same reader works
    regardless of where the bundle lives. See ``dna.kernel.bundle_handle``.

    Backward-compat: ``BundleHandle.path`` returns the underlying
    filesystem ``Path`` when FS-backed (``None`` otherwise) — escape
    hatch for code that genuinely needs Path semantics. New readers
    SHOULD use ``handle.read_text(...)`` / ``handle.iter_entries(...)``.
    """

    def detect(self, bundle: "BundleHandle") -> bool: ...

    def read(self, bundle: "BundleHandle") -> dict[str, Any]: ...


@runtime_checkable
class WriterPort(Protocol):
    """Writes a raw dict back to a bundle. Inverse of ReaderPort.

    Phase 8 (PR1) — ``write`` receives a ``BundleHandle`` instead of
    ``Path``; same source-agnostic contract.
    """

    def can_write(self, raw: dict) -> bool: ...

    def write(self, bundle: "BundleHandle", raw: dict) -> None: ...


# ---------------------------------------------------------------------------
# Tool port (s-dna-tool-decorator, 2026-05-24)
#
# DNA layer ON TOP of langchain — never replaces langchain's
# StructuredTool. ``@dna_tool`` decorator wraps langchain's ``@tool``
# (so deepagents/langgraph still get exactly what they expect) and
# ADDS DNA-side metadata for declarative discovery.
#
# Architecture:
#   - Decorator runs at function definition time → emits ToolDefinition
#   - Extension.register(kernel) calls kernel.tool(td) per definition
#     (analogous to kernel.kind(KindPort))
#   - Studio/clients query via kernel.get_tools(group=...) — pure
#     metadata, no execution
#   - Agent dispatch path (make_manifest_tools) returns the unchanged
#     langchain StructuredTool[] — agnostic to DNA wrapping
# ---------------------------------------------------------------------------


@runtime_checkable
class ToolPort(Protocol):
    """An invocable tool exposed to agents. The underlying callable is
    a langchain StructuredTool (preserves framework compatibility);
    this port adds DNA discovery metadata (group, hitl, scope).
    """

    name: str
    group: str | None
    description: str  # full docstring
    summary: str       # first paragraph
    args_schema: dict[str, Any]
    hitl: bool
    scope: str | None
    source: str  # module file name (best-effort)

    def get_callable(self) -> Any:
        """Return the underlying langchain StructuredTool (or function)."""
        ...


@dataclass
class ToolDefinition:
    """Concrete ToolPort implementation. Stored in ``kernel._tools``.

    The ``_callable`` field holds the langchain StructuredTool; never
    serialize or wrap-replace it — downstream langgraph / deepagents
    consume it directly. ``get_callable()`` is the canonical accessor.
    """
    name: str
    group: str | None = None
    description: str = ""
    summary: str = ""
    args_schema: dict[str, Any] = field(default_factory=dict)
    hitl: bool = False
    scope: str | None = None
    source: str = ""
    _callable: Any = None

    def get_callable(self) -> Any:
        return self._callable


# ---------------------------------------------------------------------------
# Storage descriptor
# ---------------------------------------------------------------------------

class StoragePattern(StrEnum):
    """How a kind's documents are laid out on the filesystem."""
    BUNDLE = "bundle"       # Directory with a marker file (e.g. SKILL.md)
    YAML = "yaml"           # Plain YAML files inside a container directory
    ROOT = "root"           # Single root file (e.g. manifest.yaml)
    STANDALONE = "standalone"  # Standalone file at module root (e.g. AGENTS.md)


class BodyMode(StrEnum):
    """How the body/content of a marker file is parsed."""
    TEXT = "text"           # Raw text string
    LIST = "list"           # Markdown list → list[str]
    SECTIONS = "sections"   # Markdown H2 sections → dict[str, str]


@dataclass
class StorageDescriptor:
    """Declares how a kind's documents are stored on the filesystem.

    Used by writers, readers, and the Studio UI to understand the
    canonical layout for each kind without hardcoded maps.
    """
    container: str
    pattern: StoragePattern
    marker: str | None = None
    body_as: BodyMode | None = None
    body_field: str | None = None
    body_parser: Callable[[str], dict[str, Any]] | None = field(
        default=None, repr=False
    )

    @classmethod
    def bundle(
        cls,
        container: str,
        marker: str,
        body_as: BodyMode = BodyMode.TEXT,
        body_field: str = "instruction",
    ) -> "StorageDescriptor":
        """Bundle directory containing a marker file (e.g. SKILL.md)."""
        return cls(
            container=container,
            pattern=StoragePattern.BUNDLE,
            marker=marker,
            body_as=body_as,
            body_field=body_field,
        )

    @classmethod
    def yaml(cls, container: str) -> "StorageDescriptor":
        """Plain YAML files inside a container directory."""
        return cls(
            container=container,
            pattern=StoragePattern.YAML,
        )

    @classmethod
    def root(cls, filename: str = "manifest.yaml") -> "StorageDescriptor":
        """Single root file at the module root."""
        return cls(
            container="",
            pattern=StoragePattern.ROOT,
            marker=filename,
        )

    @classmethod
    def standalone(
        cls,
        filename: str,
        body_as: BodyMode = BodyMode.TEXT,
        body_field: str = "content",
    ) -> "StorageDescriptor":
        """Standalone file at the module root (e.g. AGENTS.md)."""
        return cls(
            container="",
            pattern=StoragePattern.STANDALONE,
            marker=filename,
            body_as=body_as,
            body_field=body_field,
        )


def default_visible_in_backend(storage: "StorageDescriptor | None") -> bool:
    """Default visibility policy. Override explicitly on KindPort when needed."""
    if storage is None:
        return False
    if storage.pattern in (StoragePattern.BUNDLE, StoragePattern.STANDALONE):
        return True
    return False  # yaml and root both default hidden


def resolve_visible_in_backend(kp) -> bool:
    """Read visible_in_backend, falling back to default_visible_in_backend(storage)."""
    explicit = getattr(kp, "visible_in_backend", None)
    if explicit is not None:
        return bool(explicit)
    return default_visible_in_backend(getattr(kp, "storage", None))


@runtime_checkable
class KindPort(Protocol):
    """WHO — identity + composition role.

    Optional attributes (read by the kernel at load time, not required
    by the Protocol check):

    - ``docs: str | None`` — prose explanation of what this kind IS at
      the concept level. Surfaced by the harness `describe_kind` tool
      for "what is a Soul?" style questions. When an extension ships a
      ``DOCS.md`` file alongside its package, the kernel's
      ``_load_kind_docs`` loader overrides this attribute at load time.
    - ``description_fallback_field: str | None`` — name of the spec
      field to derive metadata.description from when none was
      declared. See ``Kernel._fill_derived_description``.
    - ``ui_schema: dict[str, dict] | None`` — per-field UI hints that
      tell consumers (e.g. the Tauri Studio) how to render each spec
      field. Keyed by spec field name. Each entry may declare:

        - ``widget`` (str): one of ``text | textarea | markdown |
          markdown-toc | code | select | checkbox | list-markdown |
          tags | readonly``
        - ``label`` (str): human-friendly label
        - ``help`` (str): help text shown next to the field
        - ``language`` (str): for ``code`` widget, CodeMirror language
        - ``height`` (int): editor height in px
        - ``order`` (int): render order (lower first; default 0)

      When absent, consumers should infer the widget from the value
      type. Missing fields are rendered with the default widget for
      their Python type (str → textarea, bool → checkbox, etc.).
      See ``docs/KIND-UI-HINTS.md`` for the full contract.
    """

    api_version: str
    kind: str
    alias: str
    model: type
    origin: str | None
    storage: StorageDescriptor

    # Phase 16 — ``is_root`` is derived from ``storage.pattern == ROOT``
    # (KindBase.is_root @property). The Protocol still exposes it as a
    # readable attribute via structural typing — third-party Kinds that
    # don't subclass KindBase need to provide their own implementation.
    is_root: bool
    is_prompt_target: bool
    prompt_target_priority: int
    flatten_in_context: bool

    # ``is_runtime_artifact`` — True for Kinds whose documents are
    # produced by runtime workflows (eval engine, GAIA pipeline,
    # autolab loop, evidence-capture hooks, etc.) rather than authored
    # as source-of-truth. Tools that replicate "the inputs to the
    # system" (filesystem→Postgres seed, catalog publish, manifest
    # export) MUST skip Kinds where this is True so they don't
    # re-inject historical execution data as if it were canonical
    # configuration. Default ``False`` keeps existing extensions and
    # third-party Kinds unchanged.
    is_runtime_artifact: bool

    def dep_filters(self) -> dict[str, str] | None: ...

    def dependencies(self) -> dict[str, str] | None:
        """Which spec fields reference other kinds by alias.

        Clearer name for dep_filters(). Default implementation delegates
        to dep_filters() so existing extensions stay compatible.
        """
        ...

    def schema(self) -> dict[str, Any] | None:
        """JSON Schema for this kind's spec."""
        ...

    def get_default_agent_name(self, doc: Any) -> str | None: ...

    def get_layer_policies(self, doc: Any) -> dict[str, dict[str, LayerPolicy]] | None: ...

    def parse(self, raw: dict[str, Any]) -> Any: ...

    def describe(self, doc: Any) -> str | None: ...

    def summary(self, doc: Any) -> dict[str, Any] | None: ...

    def prompt_template(self) -> str | None: ...

    # Optional: returns renderable blocks for the Studio's preview pane.
    # Each extension implements this for its own kinds. When not present,
    # the kernel falls back to generic_spec_dump from preview.py.
    # Not declared on the Protocol body so existing extensions stay
    # Protocol-compatible without changes; consumers feature-test via
    # hasattr(kp, "preview").

    # -- Rendering hints (all optional, duck-typed) ------------------------
    #
    # graph_style: dict | None
    #   {"fill": "#F97316", "stroke": "#EA580C", "text_color": "#fff"}
    #   Colors for mermaid diagrams, graph nodes, and other visualizations.
    #
    # ascii_icon: str | None
    #   Single emoji or character for ASCII tree / compact views.
    #
    # display_label: str | None
    #   Human-friendly plural label (e.g. "Agents" for Agent).
    #
    # graph_meta(doc) -> dict | None
    #   Per-doc annotations for graph rendering and health checks.
    #   e.g. Guardrail returns {"severity": ..., "scope": ..., "rules": ...}.


@runtime_checkable
class Extension(Protocol):
    """Registers kinds, readers, and writers on the Kernel.

    Optional capability (feature-tested via ``hasattr``, NOT a required
    Protocol member so legacy extensions predating Phase 0 keep working):

        def templates(self) -> list[Template]: ...

    When present, ``Kernel.list_templates()`` aggregates entries from
    every loaded extension so UIs (Tauri Studio, CLI) can offer
    ``scaffold()`` for any extension-shipped file tree. See
    ``dna.kernel.templates.Template`` for the payload shape.
    """

    name: str
    version: str

    def register(self, kernel: Any) -> None: ...


# Re-export Template at the protocols surface so downstream code can do
# ``from dna.kernel.protocols import Template`` alongside the other
# port types. The ``templates()`` method on Extension is intentionally kept
# OFF the Protocol body (feature-tested via ``hasattr``) to preserve
# backwards compatibility with third-party extensions that predate Phase 0.
from dna.kernel.templates import Template  # noqa: E402  re-export

__all__ = [
    "EXTENSIONS_ENTRY_POINT_GROUP",
    "LayerPolicy",
    "CompositionResult",
    "CacheItem",
    "ResolvedItem",
    "ResolveError",
    "ResolveNotFoundError",
    "ResolveAuthError",
    "ResolveNetworkError",
    "SourcePort",
    "CachePort",
    "ResolverPort",
    "ReaderPort",
    "WriterPort",
    "StoragePattern",
    "BodyMode",
    "StorageDescriptor",
    "default_visible_in_backend",
    "resolve_visible_in_backend",
    "KindPort",
    "Extension",
    "WritableSourcePort",
    "Template",
]


# ---------------------------------------------------------------------------
# Writable source port
# ---------------------------------------------------------------------------


@runtime_checkable
class WritableSourcePort(SourcePort, Protocol):
    """SourcePort with write + versioning capabilities.

    Phase 2a (tenant first-class): ``tenant`` is now a first-class
    parameter on save/delete. Adapters route tenant-scoped writes to
    physically isolated storage (e.g. ``tenants/<X>/scopes/<S>/``);
    ``layer`` is reserved for non-tenant overlays (branch, region,
    user) — when both are passed the adapter combines them.
    """

    async def save_document(
        self, scope: str, kind: str, name: str, raw: dict,
        author: str | None = None,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
        write_class: str = "substantive",
        version_retention: int | None = None,
    ) -> str: ...

    async def delete_document(
        self, scope: str, kind: str, name: str,
        *,
        tenant: str | None = None,
        layer: tuple[str, str] | None = None,
    ) -> None: ...

    async def save_manifest(self, scope: str, manifest: dict) -> str: ...

    async def list_versions(
        self, scope: str, kind: str, name: str
    ) -> list[dict]: ...

    async def get_version(
        self, scope: str, kind: str, name: str, version_id: str
    ) -> dict: ...

    async def publish(self, scope: str, kind: str, name: str) -> str: ...

    async def load_drafts(self, scope: str) -> list[dict]: ...

    async def list_scopes(self) -> list[str]: ...

    # s-capabilities-dataclass — sync + typed: capabilities() is a cheap
    # isinstance-derived ``SourceCapabilities`` (no I/O), uniformly sync across
    # every adapter. Callers read fixed dataclass fields, not a magic-string dict.
    def capabilities(self) -> "SourceCapabilities": ...


# ---------------------------------------------------------------------------
# Deprecated aliases (module-level __getattr__ keeps imports working)
# ---------------------------------------------------------------------------


def __getattr__(name: str):
    if name == "RecordStorePort":
        import warnings

        warnings.warn(
            "RecordStorePort is deprecated (s-sourceport-contract-cleanup): "
            "the record-plane contract was unified into WritableSourcePort "
            "(identical save_document/delete_document/query/count "
            "signatures). Import WritableSourcePort instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return WritableSourcePort
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
