"""``dna_cli._mcp_quota`` — the DNA Cloud **quota meter + rate-limiter + feature gate**.

The runtime half of DNA Cloud metering. The auth↔tenancy bridge
(``dna_cli._mcp_auth``) already maps a verified token → a *tenant* (which data)
and → a *tier* (how much). This module is the "how much": given a tier's caps
(read straight from the ``Tier`` Kind ``spec`` via ``kernel.tier`` — **never a
literal in code**) it meters every MCP tool call against three limits:

    * **feature families** — a tool's family (definitions / sdlc / memory / emit)
      must be unlocked by the tier, else :class:`FeatureNotInPlanError` (403).
    * **rate** — calls-per-second window, else :class:`OverQuotaError` (429).
    * **daily quota** — calls-per-day counter, else :class:`OverQuotaError` (429/402).

The counting is behind a small **port** (:class:`QuotaStore`) with two impls:

    * :class:`InProcQuotaStore` — dicts in the server process. The right
      default for a local ``dna mcp serve`` or a single-process self-host, and
      **wrong for metered billing**: it resets on restart and each replica
      keeps its own, so N replicas grant ~N x ``calls_per_day``.
    * :class:`PostgresQuotaStore` — one row per ``(day, tenant, tier)``,
      advanced by an atomic ``INSERT ... ON CONFLICT DO UPDATE``. Durable
      across restarts, shared across replicas, and READABLE by the billing job
      (:meth:`PostgresQuotaStore.calls_on`). This is what makes overage
      billing possible at all.

:func:`store_from_env` picks between them (a Postgres DSN present → durable),
``build_server`` threads the choice down, and both are selected per-server
rather than reached through the module singleton. Only the DAILY counter is
durable; the calls-per-second window stays per-replica by design — see
:class:`PostgresQuotaStore`. See ``adr-dna-cloud-saas``.

The invariant that keeps OSS/self-host untouched lives in the CALLER
(``_mcp_server._guard``): quota is enforced ONLY when a token is present. With no
token (stdio / local / ``auth=None``) the guard is an identity — this module is
never reached, so nothing is metered and everything is unlimited.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import threading as _threading
import time
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class OverQuotaError(PermissionError):
    """The tier's rate or daily-call budget is exhausted (429 / 402 semantics).

    Raised by :func:`enforce_quota` and surfaced to the MCP client as a tool error
    — the "how much" denial. The message names the tier and the cap it hit."""


class FeatureNotInPlanError(PermissionError):
    """A tool family is not unlocked by the caller's tier (403 semantics).

    Raised by :func:`enforce_quota` when the tier's ``feature_families`` does not
    include the called tool's family. The message names the tier and the family."""


class MemoryModeError(PermissionError):
    """The tier's ``memory_mode`` does not grant the attempted memory op (403).

    Raised by :func:`enforce_memory_mode`: the ``memory`` feature family is a
    coarse in/out gate (a tier either exposes memory tools or not); ``memory_mode``
    is the FINER read-vs-write split WITHIN it. Free grants ``read`` (recall only);
    ``write`` ops (remember/consolidate) need a tier whose ``memory_mode`` is
    ``write``. The value is read straight from the ``Tier`` spec — never hardcoded."""


class SdlcModeError(PermissionError):
    """The tier's ``sdlc_mode`` does not grant the attempted SDLC write op (403).

    The SDLC twin of :class:`MemoryModeError`: the ``sdlc`` feature family is the
    coarse gate (a tier either exposes the board tools or not); ``sdlc_mode`` is the
    FINER read-vs-write split WITHIN it. Free grants ``read`` (sdlc_digest /
    list_stories / get_adr); the board WRITE tools (create_story / create_issue /
    set_status / comment / create_feature) need a tier whose ``sdlc_mode`` is
    ``write`` (Pro). Read straight from the ``Tier`` spec — never hardcoded."""


# An access level is a total order: none < read < write. A tool declares the level
# it NEEDS; the tier GRANTS a level. Shared by the memory + sdlc mode gates.
_ACCESS_MODE_RANK: dict[str, int] = {"none": 0, "read": 1, "write": 2}
_MEMORY_MODE_RANK = _ACCESS_MODE_RANK  # back-compat alias.


def _enforce_mode(
    *, caps: dict[str, Any], tier: str, op: str, field: str,
    label: str, error: type[PermissionError],
) -> None:
    """Gate one tool call against a tier's ``<field>`` access mode — the shared
    read-vs-write refinement behind :func:`enforce_memory_mode` +
    :func:`enforce_sdlc_mode`. Granted mode is READ from ``caps[field]`` (never
    hardcoded); empty ``caps`` (OSS) enforces nothing; a missing mode on a
    configured tier defaults to ``none`` (fail closed)."""
    if not caps:
        return  # unconfigured / OSS source → enforce nothing (mirror enforce_quota).
    granted = str(caps.get(field) or "none")
    have = _ACCESS_MODE_RANK.get(granted, 0)
    need = _ACCESS_MODE_RANK.get(op, _ACCESS_MODE_RANK["write"])  # unknown op → strictest.
    if have < need:
        raise error(
            f"tier {tier!r} grants {field}={granted!r}, which does not permit a "
            f"{op!r} {label} operation — a write needs a tier whose {field} is "
            f"'write' (upgrade the plan)."
        )


def enforce_memory_mode(*, caps: dict[str, Any], tier: str, op: str) -> None:
    """Gate one memory tool call against the tier's ``memory_mode`` — raises on a
    breach. The read-vs-write refinement of the ``memory`` feature-family gate.

    ``caps`` is the ``Tier`` Kind's ``spec`` dict (from ``kernel.tier(...)``); the
    granted mode is READ from ``caps['memory_mode']`` (``none``/``read``/``write``),
    never hardcoded. ``op`` is the level the tool needs — ``read`` (recall) or
    ``write`` (remember/consolidate). Denies when the granted rank is below the
    needed rank: a ``read`` tier calling a ``write`` op → :class:`MemoryModeError`.

    Empty ``caps`` (an unconfigured / OSS source) enforces nothing — mirrors
    :func:`enforce_quota` exactly, so the OSS/self-host path is never blocked. A
    missing ``memory_mode`` on a configured tier defaults to ``none`` (fail closed —
    the schema's own default), denying any memory op until the tier declares one."""
    _enforce_mode(
        caps=caps, tier=tier, op=op, field="memory_mode", label="memory",
        error=MemoryModeError,
    )


def enforce_sdlc_mode(*, caps: dict[str, Any], tier: str, op: str) -> None:
    """Gate one SDLC board **write** tool against the tier's ``sdlc_mode`` — the
    SDLC twin of :func:`enforce_memory_mode`. Free grants ``read`` (the board is
    listable/diffable); the write tools need ``sdlc_mode='write'`` (Pro). Read from
    the ``Tier`` spec (zero hardcode); empty caps (OSS) enforce nothing; a missing
    mode on a configured tier defaults to ``none`` (fail closed)."""
    _enforce_mode(
        caps=caps, tier=tier, op=op, field="sdlc_mode", label="sdlc",
        error=SdlcModeError,
    )


# ── the metering key ───────────────────────────────────────────────────────
#
# The port's ``key`` is opaque to the STORE contract but not to this module:
# ``enforce_quota`` composes it and a durable store has to decompose it to put
# tenant and tier in their own columns (a billing job cannot be asked to LIKE
# against a composite string). Composition and decomposition therefore live
# side by side, as one fact, instead of the format being an f-string in one
# function and a split in another.


def quota_key(tenant: str | None, tier: str) -> str:
    """Compose the metering key for a ``(tenant, tier)`` pair."""
    return f"{tenant or '-'}::{tier}"


def split_quota_key(key: str) -> tuple[str, str]:
    """Decompose a metering key back into ``(tenant, tier)``.

    Splits on the LAST ``::`` because the tenant half is itself structured —
    personal-memory partitions are ``personal:<oid>`` /
    ``personal:google:<sub>`` (single colons, see
    ``dna.memory.personal.personal_tenant``) — while the tier half is a bare
    Tier id. A key with no separator is treated as all-tenant, tier ``'-'``."""
    tenant, sep, tier = key.rpartition("::")
    if not sep:
        return key, "-"
    return tenant, tier


# ── the store port (swap in Postgres/Redis for real billing) ───────────────


class QuotaStore(Protocol):
    """The metering port — the seam a durable (Postgres/Redis) store slots into.

    Two axes, keyed by an opaque ``key`` (the caller composes it from
    tenant+tier — see :func:`quota_key`): a **daily** counter (calendar-day
    bucket, UTC) and a **rate** window (recent-call timestamps), plus the
    billing read :meth:`calls_on`. :class:`InProcQuotaStore` is the
    single-process default; :class:`PostgresQuotaStore` is the durable impl
    behind this identical interface."""

    def incr_day(self, key: str) -> int:
        """Increment today's counter for ``key`` and return the new count."""
        ...

    def note_call(self, key: str) -> None:
        """Record a call for ``key`` at the current instant (rate window)."""
        ...

    def rate_count(self, key: str, window_s: float) -> int:
        """How many calls ``key`` made in the last ``window_s`` seconds."""
        ...

    def calls_on(self, tenant: str, day: _dt.date | None = None) -> int:
        """Total calls ``tenant`` made on ``day`` (UTC; default today).

        The BILLING read — the one the DNA Cloud overage job needs and the
        reason a durable store exists at all. Summed across tiers, because the
        metering key is ``tenant::tier`` and a tenant that changed plan
        mid-day owns a bucket per tier; the bill is for the tenant."""
        ...


class InProcQuotaStore:
    """Default in-process :class:`QuotaStore` — a dict counter + a per-key window.

    Daily counts live in ``(day, key) -> int`` where ``day`` is the UTC calendar
    day (``time.gmtime`` → ``YYYY-DDD``); rate timestamps live in
    ``key -> [monotonic-ish wall times]``, pruned to the window on each read.

    Uses the wall clock (``time.time`` / ``time.gmtime``) — this is runtime server
    code, not composition, so real time is correct here. NOT durable and NOT
    shared across processes: fine to prototype, **replace for real billing**."""

    def __init__(self) -> None:
        self._day_counts: dict[tuple[str, str], int] = {}
        self._calls: dict[str, list[float]] = {}

    @staticmethod
    def _today() -> str:
        t = time.gmtime()
        return f"{t.tm_year:04d}-{t.tm_yday:03d}"

    @staticmethod
    def _day_label(day: _dt.date) -> str:
        """A ``date`` in the same ``YYYY-DDD`` shape ``_today`` produces."""
        return f"{day.year:04d}-{day.timetuple().tm_yday:03d}"

    def reset(self) -> None:
        """Drop every counter — the supported way to isolate tests.

        Exists so callers stop reaching into ``_day_counts`` / ``_calls``: a
        test poking a private is what made the module-level singleton look
        load-bearing in the first place."""
        self._day_counts.clear()
        self._calls.clear()

    def calls_on(self, tenant: str, day: _dt.date | None = None) -> int:
        """In-process twin of the billing read (see :class:`QuotaStore`).

        Answers from the same dicts ``incr_day`` writes, summing the tiers
        whose key carries ``tenant``. Correct for THIS process only — the
        reason :class:`PostgresQuotaStore` exists."""
        label = self._day_label(day or _dt.datetime.now(_dt.UTC).date())
        return sum(
            count
            for (bucket_day, key), count in self._day_counts.items()
            if bucket_day == label and split_quota_key(key)[0] == tenant
        )

    def incr_day(self, key: str) -> int:
        bucket = (self._today(), key)
        count = self._day_counts.get(bucket, 0) + 1
        self._day_counts[bucket] = count
        return count

    def note_call(self, key: str) -> None:
        self._calls.setdefault(key, []).append(time.time())

    def rate_count(self, key: str, window_s: float) -> int:
        now = time.time()
        cutoff = now - window_s
        recent = [t for t in self._calls.get(key, []) if t >= cutoff]
        # prune so the list does not grow unbounded.
        self._calls[key] = recent
        return len(recent)


# The process-wide in-process store. Still a singleton ON PURPOSE for the
# in-process case: two servers in one process (the Lane A + Lane B facades)
# must meter into the SAME dicts or a caller would get two budgets. It is no
# longer the *only* reachable store — ``build_server`` selects via
# :func:`store_from_env` and threads the choice down to ``enforce_quota``.
DEFAULT_STORE = InProcQuotaStore()


# ── the durable store (Postgres) ───────────────────────────────────────────

#: The counter table. Owned by the SDK's Alembic ladder
#: (``dna.adapters.sqlalchemy_.schema`` + revision ``0002_quota_counters``), so
#: it is created by the SAME ``SqlAlchemySource.connect()`` that builds the
#: document tables — the host provisions nothing extra.
DEFAULT_QUOTA_TABLE = "dna_quota_counters"


def _sync_driver() -> str:
    """The installed sync Postgres DBAPI, as a SQLAlchemy driver name.

    The port is SYNCHRONOUS (``incr_day`` returns an ``int``, not an
    awaitable) because ``enforce_quota`` is synchronous, so the durable store
    needs a sync DBAPI. The SDK's ``[postgres]`` extra ships **asyncpg**,
    which is async-only and unusable here — hence ``dna-cli[quota]``."""
    import importlib.util

    for name in ("psycopg2", "psycopg"):
        if importlib.util.find_spec(name) is not None:
            return name
    raise RuntimeError(
        "the durable quota store needs a synchronous Postgres driver — install "
        "it with:  pip install 'dna-cli[quota]'  (asyncpg, shipped by "
        "dna-sdk[postgres], is async-only and cannot back this store)."
    )


def sync_pg_url(dsn: str) -> str:
    """Rewrite a DNA source DSN into a SQLAlchemy **sync** Postgres URL.

    Accepts what ``DNA_SOURCE_URL`` may carry — ``postgres://``,
    ``postgresql://``, ``postgresql+asyncpg://`` — and swaps the driver for
    the installed sync one, leaving host/database/query string alone."""
    scheme, sep, rest = dsn.partition("://")
    if not sep:
        raise ValueError(f"not a Postgres URL: {dsn!r}")
    base = scheme.split("+", 1)[0].lower()
    if base not in ("postgresql", "postgres"):
        raise ValueError(f"not a Postgres URL: {dsn!r}")
    return f"postgresql+{_sync_driver()}://{rest}"


def is_postgres_url(url: str) -> bool:
    """Whether ``url`` names a Postgres database (any driver spelling)."""
    scheme = url.partition("://")[0].split("+", 1)[0].lower()
    return scheme in ("postgresql", "postgres")


class PostgresQuotaStore:
    """Durable :class:`QuotaStore` — the counter DNA Cloud bills from.

    Closes the two defects of :class:`InProcQuotaStore` that made the overage
    job unimplementable: the count SURVIVES a restart (it is a row, not a
    dict) and it is SHARED by every replica (one row per ``(day, tenant,
    tier)``, so N replicas cannot each grant a full ``calls_per_day``).

    The daily counter is advanced with a single atomic statement::

        INSERT ... VALUES (..., 1)
        ON CONFLICT (day, tenant, tier)
        DO UPDATE SET calls = dna_quota_counters.calls + 1
        RETURNING calls

    — never SELECT-then-UPDATE. Under concurrency the losing writer blocks on
    the conflicting row's lock and its ``+ 1`` applies to the COMMITTED value,
    so N concurrent increments produce exactly N. The ``RETURNING`` is what
    lets the caller keep enforcing on the post-increment count without a
    second round trip.

    **The rate window is deliberately NOT persisted.** ``note_call`` /
    ``rate_count`` delegate to an in-process window, so the calls-per-second
    limit stays per-replica. Persisting it would mean a row per call for a
    one-second horizon — write amplification with no billing value, since
    nothing bills on rate — and Postgres is the wrong engine for it (that is
    Redis' job, and the port stays open for exactly that). The consequence is
    explicit: with N replicas the effective burst ceiling is N x
    ``rate_per_sec``. That is a throttle, not a budget; the DAILY cap, which
    is what money depends on, is exact.

    Every call opens its own short transaction on a pooled connection. The
    call is blocking, and ``enforce_quota`` runs on the server's event loop —
    one local round trip per metered tool call, alongside the several the tool
    itself already makes to the same database."""

    def __init__(
        self,
        dsn: str,
        *,
        schema: str | None = None,
        table: str = DEFAULT_QUOTA_TABLE,
        engine: Any = None,
        pool_size: int = 5,
    ) -> None:
        self._url = sync_pg_url(dsn) if engine is None else None
        self._schema = schema
        self._table = table
        self._pool_size = pool_size
        self._engine = engine
        # Guards lazy engine construction: the first metered calls can arrive
        # concurrently, and two threads racing here would each build a pool and
        # one would be dropped on the floor still holding its connections.
        self._engine_lock = _threading.Lock()
        # The rate window has no durable component — see the class docstring.
        self._rate = InProcQuotaStore()

    # -- plumbing ----------------------------------------------------------

    @property
    def _qualified(self) -> str:
        return f"{self._schema}.{self._table}" if self._schema else self._table

    def _get_engine(self) -> Any:
        """The lazily-built sync engine.

        Lazy so constructing the store (which ``build_server`` does at import
        of a facade, before anything is served) never opens a socket, and a
        misconfigured DSN surfaces on the first metered call rather than at
        startup of an otherwise-working server."""
        if self._engine is None:
            with self._engine_lock:
                if self._engine is None:  # re-check: another thread may have won
                    import sqlalchemy as sa

                    self._engine = sa.create_engine(
                        self._url, pool_size=self._pool_size,
                        pool_pre_ping=True, future=True,
                    )
        return self._engine

    @staticmethod
    def _today() -> _dt.date:
        """Today in UTC — the bucket boundary is the STORE's clock.

        Not the database's ``CURRENT_DATE``: that follows the server's
        timezone, so a database in a non-UTC zone would roll the billing day
        at the wrong instant. Every replica reads UTC, so they agree."""
        return _dt.datetime.now(_dt.UTC).date()

    # -- the port ----------------------------------------------------------

    def incr_day(self, key: str) -> int:
        """Atomically advance today's counter for ``key``; return the new count."""
        import sqlalchemy as sa

        tenant, tier = split_quota_key(key)
        stmt = sa.text(
            f"INSERT INTO {self._qualified} (day, tenant, tier, calls) "
            "VALUES (:day, :tenant, :tier, 1) "
            "ON CONFLICT (day, tenant, tier) "
            f"DO UPDATE SET calls = {self._table}.calls + 1 "
            "RETURNING calls"
        )
        with self._get_engine().begin() as conn:
            row = conn.execute(
                stmt, {"day": self._today(), "tenant": tenant, "tier": tier}
            ).first()
        return int(row[0]) if row else 1

    def note_call(self, key: str) -> None:
        """Record a call in the (per-replica) rate window."""
        self._rate.note_call(key)

    def rate_count(self, key: str, window_s: float) -> int:
        """Calls in this REPLICA's rate window (see the class docstring)."""
        return self._rate.rate_count(key, window_s)

    def calls_on(self, tenant: str, day: _dt.date | None = None) -> int:
        """Total durable calls ``tenant`` made on ``day`` (UTC; default today).

        The billing read. Sums across tiers, so a tenant that upgraded mid-day
        is billed for everything it actually called."""
        import sqlalchemy as sa

        stmt = sa.text(
            f"SELECT COALESCE(SUM(calls), 0) FROM {self._qualified} "
            "WHERE tenant = :tenant AND day = :day"
        )
        with self._get_engine().connect() as conn:
            row = conn.execute(
                stmt, {"tenant": tenant, "day": day or self._today()}
            ).first()
        return int(row[0]) if row else 0

    def close(self) -> None:
        """Dispose the connection pool (tests / shutdown)."""
        if self._engine is not None:
            self._engine.dispose()


#: Guards the in-process fallback warning (see :func:`store_from_env`).
_WARNED_IN_PROCESS = False


def store_from_env(env: Any = None) -> Any:
    """Select the :class:`QuotaStore` for this process from the environment.

    A Postgres DSN present → the DURABLE store; absent → the in-process one.
    The DSN is taken from ``DNA_QUOTA_DSN`` if set, else from
    ``DNA_SOURCE_URL`` when that already names Postgres — which is the hosted
    shape, so a DNA Cloud deployment gets durable metering with no new
    configuration, in the same database the counter's migration ran against.
    ``DNA_QUOTA_SCHEMA`` overrides the schema (default: the connection's
    search_path, i.e. ``public`` — matching how the CLI builds its source,
    which passes no schema).

    The in-process fallback is a LEGITIMATE default, not a degraded mode: it
    is what a local ``dna mcp serve`` and a SQLite self-host should use. It is
    only wrong for metered multi-replica hosting, so the warning names that
    case rather than crying wolf on every stdio run."""
    env = os.environ if env is None else env
    dsn = (env.get("DNA_QUOTA_DSN") or "").strip()
    if not dsn:
        source_url = (env.get("DNA_SOURCE_URL") or "").strip()
        if source_url and is_postgres_url(source_url):
            dsn = source_url
    if not dsn:
        # Once per process: a host builds one server per identity lane (the
        # Entra facade + the WorkOS facade), and the same warning twice reads
        # like two different problems.
        global _WARNED_IN_PROCESS
        if _WARNED_IN_PROCESS:
            return DEFAULT_STORE
        _WARNED_IN_PROCESS = True
        logger.warning(
            "MCP quota metering is IN-PROCESS: counts reset on restart and are "
            "per-replica, so a calls_per_day cap is not enforceable across a "
            "scaled deployment and usage-based billing cannot read them. This "
            "is fine for local/self-hosted single-process use. For hosted "
            "metering set DNA_QUOTA_DSN (or run against a postgresql:// "
            "DNA_SOURCE_URL) and install dna-cli[quota]."
        )
        return DEFAULT_STORE
    return PostgresQuotaStore(dsn, schema=(env.get("DNA_QUOTA_SCHEMA") or None))


# ── the enforcer (caps come from the Tier spec — zero literals) ─────────────


def enforce_quota(
    *,
    caps: dict[str, Any],
    tenant: str | None,
    tier: str,
    family: str,
    store: QuotaStore = DEFAULT_STORE,
) -> None:
    """Meter one MCP tool call against a tier's caps — raises on any breach.

    ``caps`` is the ``Tier`` Kind's ``spec`` dict (from ``kernel.tier(...)``); every
    limit is READ from it, never hardcoded:

    1. **family gate** — if ``caps['feature_families']`` is a non-empty list and
       ``family`` is not in it → :class:`FeatureNotInPlanError`.
    2. **rate** — if ``caps['rate_per_sec']`` is set, record the call and if the
       1-second window now exceeds it → :class:`OverQuotaError`.
    3. **daily quota** — if ``caps['calls_per_day']`` is set, increment today's
       counter and if it now exceeds the cap → :class:`OverQuotaError`.

    A ``None`` cap means *unlimited* for that axis (skipped). Empty ``caps`` (an
    unconfigured / OSS source) enforces nothing. The metering key is
    ``f"{tenant or '-'}::{tier}"`` so tenants+tiers meter independently. Order is
    family → rate → quota: gate the unlocked-ness before spending any counter."""
    # 1. feature-family gate (before counting — a locked family costs no quota).
    families = caps.get("feature_families")
    if isinstance(families, list) and families and family not in families:
        raise FeatureNotInPlanError(
            f"tier {tier!r} does not include the {family!r} tool family "
            f"(unlocked families: {families}) — upgrade the plan to use it."
        )

    key = quota_key(tenant, tier)

    # 2. rate limit (calls-per-second window).
    rate = caps.get("rate_per_sec")
    if rate is not None:
        store.note_call(key)
        if store.rate_count(key, 1.0) > rate:
            raise OverQuotaError(
                f"tier {tier!r} rate limit exceeded ({rate}/s) — slow down "
                f"(retry shortly)."
            )

    # 3. daily quota (calls-per-day counter).
    cpd = caps.get("calls_per_day")
    if cpd is not None:
        count = store.incr_day(key)
        if count > cpd:
            raise OverQuotaError(
                f"tier {tier!r} daily call quota exhausted "
                f"({count - 1}/{cpd} used today) — upgrade the plan or wait for "
                f"the daily reset."
            )
