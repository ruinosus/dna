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
      A HARD cap, and an HONEST one (i-050): the denied call is NOT counted, so
      the counter the overage job bills from (``SUM(calls) - included``) can
      never carry calls the customer was refused.

And one thing that is deliberately NOT a limit in that sense:

    * **the margin breaker** — a COST-PROTECTION CUTOUT the operator arms on a
      plan (:func:`enforce_margin_breaker`, i-134). The three limits above are
      what a plan SELLS; this is a fuse that stops one account costing the
      operator more than it can absorb while the right sold axis does not exist
      yet. It never goes on a price page, it counts nothing of its own, and it
      is OFF unless a plan declares it. Read the block comment above
      :func:`enforce_margin_breaker` before touching it — the distinction is
      the point, and it is the thing most easily lost.

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


class MarginBreakerTripped(OverQuotaError):
    """The operator's COST-PROTECTION CUTOUT is open for this tenant (429).

    ⚠️ **This is not a plan allowance and it is not a pricing axis.** Read the
    long-form reasoning on :func:`enforce_margin_breaker`; the short version is
    that a sold limit is a PROMISE to the customer and this is a FUSE for the
    operator, and confusing the two would put a number on a price list that
    nobody agreed to sell.

    Subclasses :class:`OverQuotaError` deliberately, and the choice is the
    defence rather than a convenience. Every face that relays plan denials
    already enumerates ``OverQuotaError`` by name (the MCP ``_guard``, the REST
    ``_plan_gate``, DNA Cloud's A2A door), and this house has measured twice
    what a hand-written enumeration costs when a new refusal type is declared
    beside it: the refusal escapes as an unexplained 500 on whichever face
    nobody remembered. Inheriting means this refusal is relayed correctly by
    every face written BEFORE it existed — 429 on REST, a ToolError naming the
    reason on MCP — with no enumeration to widen.

    (Not a ``dna.kernel.errors.KernelRefusal`` and not a ``CapabilityRefusal``:
    both are the KERNEL's vocabulary — a verdict the kernel reached about a
    write, or a statement about what the wired STORE can do — and the kernel
    adjudicates no plan. The derived guard that pins the kernel bases
    (``test_face_refusal_parity``'s
    ``test_every_rest_capability_refusal_carries_the_marker_base``) keys on the
    REST statuses 501/410, which is exactly where a margin cutout does not
    land. The quota module's own family is the right one, and
    ``tests/test_quota_refusals_reach_both_faces.py`` is its derived guard.)"""


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


class InstanceModeError(PermissionError):
    """The tier's ``<family>_mode`` does not grant the attempted GENERIC instance
    op (403) — the family-agnostic sibling of :class:`MemoryModeError` /
    :class:`SdlcModeError`.

    Raised by :func:`enforce_family_mode` for a family that has no first-class
    gate of its own (``definitions``, ``emit``). The generic instance tools span
    every family at once, so they cannot ride a per-family exception type the
    way the hand-written tools do; the message still NAMES the cap the tier
    would have to declare (e.g. ``definitions_mode: write``)."""


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


#: Families that own a first-class mode gate + exception type. A generic
#: instance call on one of these raises the SAME error the hand-written tool for
#: that family raises, so a denial reads identically whichever door produced it.
_FAMILY_MODE_ERRORS: dict[str, type[PermissionError]] = {
    "memory": MemoryModeError,
    "sdlc": SdlcModeError,
}


def enforce_family_mode(
    *, caps: dict[str, Any], tier: str, family: str, op: str,
) -> None:
    """Gate one GENERIC instance call against the tier's ``<family>_mode``.

    The uniform rule the generic instance tools are metered by
    (``s-mcp-generic-instance-tools``). One tool spans every feature family, so
    the family is derived from the TARGET KIND
    (``dna.application.instances.family_for_kind``) and this gate then applies
    that family's access mode — ``sdlc_mode`` for a board Kind, ``memory_mode``
    for an Engram, ``definitions_mode`` for everything else. There is no
    per-tool special case to get wrong, and a caller cannot pick its family by
    picking a tool.

    Read (``op='read'``) and write (``op='write'``) are deliberately asymmetric:

    * a **write** ALWAYS requires an explicitly granted ``write`` — a plan that
      never declared the family's mode grants ``none`` (the Kind's schema
      default) and the write is refused. Fail closed: the generic write is new
      capability, and a plan written before it existed cannot have consented to
      it. The message names the missing cap, so granting it is a one-line plan
      edit rather than a code change.
    * a **read** is enforced only when the tier actually DECLARES that family's
      mode. Reads were already governed by the coarse ``feature_families`` gate
      on every existing tool; retro-denying them on plans that never spoke about
      modes would break configured deployments to no security end.

    Empty ``caps`` (an unconfigured / OSS source) enforces nothing, exactly like
    :func:`enforce_quota` — the self-host path is never capped."""
    field = f"{family}_mode"
    if op == "read" and field not in caps:
        return  # the plan never spoke about this family's modes — see above.
    _enforce_mode(
        caps=caps, tier=tier, op=op, field=field, label=family,
        error=_FAMILY_MODE_ERRORS.get(family, InstanceModeError),
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
        """Increment today's counter for ``key`` and return the new count.

        UNCONDITIONAL — this is the soft-cap primitive (count everything,
        bill the excess). The hard-cap enforcement path does NOT use it;
        see :meth:`try_incr_day`."""
        ...

    def try_incr_day(self, key: str, cap: int) -> int | None:
        """Increment today's counter for ``key`` ONLY if the post-increment
        count stays within ``cap``; return the new count, or ``None`` when the
        cap is already spent (in which case NOTHING was counted).

        The hard-cap primitive, and the billing-honesty guarantee lives here:
        a denied call must never reach the counter the overage job bills from
        (``SUM(calls) - included``), or a capped tenant gets charged for calls
        it was refused. The check-and-increment must be ATOMIC — a separate
        check-then-``incr_day`` reintroduces the read-modify-write race the
        durable store's ``INSERT .. ON CONFLICT`` exists to kill."""
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

    def calls_in_window(self, tenant: str, days: int) -> int:
        """Total calls ``tenant`` made over the last ``days`` UTC days,
        today INCLUDED — the read the margin breaker decides on.

        Deliberately the SAME rows :meth:`calls_on` reads, aggregated over a
        wider horizon rather than counted into a second place. A separate
        counter for the breaker would be a second version of the truth that
        can drift from the billed one, and drift in the direction that matters
        (undercount) is a breaker that does not trip. There is one counter;
        this is a different question asked of it.

        Summed across tiers for the same reason :meth:`calls_on` is: the
        exposure belongs to the tenant, and a tenant that changed plan
        mid-window owns a bucket per tier.

        ``days <= 0`` yields ``0`` (an empty horizon counts nothing). A store
        that cannot answer must RAISE, never return ``0`` — zero reads as
        "well under the ceiling", which is the confident lie the breaker's
        fail-safe (:class:`MarginBreakerUnreadable`) exists to refuse."""
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

    @staticmethod
    def _label_day(label: str) -> _dt.date | None:
        """A ``YYYY-DDD`` bucket label back to the ``date`` it names.

        The window read needs ORDER over buckets, and the label's lexical
        order is not it: ``'2026-365' < '2027-001'`` holds, but only by
        accident of the year prefix — compare two labels as strings inside a
        window that straddles New Year's Eve and a 30-day horizon silently
        becomes a 365-day one. Parsing to a real date is the only comparison
        that is right in December."""
        try:
            return _dt.datetime.strptime(label, "%Y-%j").date()
        except ValueError:
            return None

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

    def calls_in_window(self, tenant: str, days: int) -> int:
        """In-process twin of the breaker read (see :class:`QuotaStore`).

        ⚠️ Carries this store's standing caveat, and it BITES HARDER here than
        on the daily axis. The dicts are per-process and reset on restart, so
        the window this answers is "what THIS replica has seen since it
        started" — never the tenant's real 30 days. On the daily cap that
        means N replicas grant ~N x the cap; on a breaker it means the fuse
        may never blow at all, because no single process ever accumulates the
        history. The in-process store stays the right default for a local
        ``dna mcp serve`` (which has no plan, so no breaker), and a hosted
        deployment that declares a ceiling must run the durable store — the
        warning in :func:`store_from_env` already says so for billing, and the
        breaker raises the stakes rather than changing the rule."""
        if days <= 0:
            return 0
        cutoff = _dt.datetime.now(_dt.UTC).date() - _dt.timedelta(days=days - 1)
        total = 0
        for (bucket_day, key), count in self._day_counts.items():
            bucket = self._label_day(bucket_day)
            if bucket is None or bucket < cutoff:
                continue
            if split_quota_key(key)[0] == tenant:
                total += count
        return total

    def incr_day(self, key: str) -> int:
        bucket = (self._today(), key)
        count = self._day_counts.get(bucket, 0) + 1
        self._day_counts[bucket] = count
        return count

    def try_incr_day(self, key: str, cap: int) -> int | None:
        """Count only if the post-increment count stays ≤ ``cap`` (see the port).

        Check-and-increment under one dict read/write pair — the same (single-
        process) consistency the unconditional ``incr_day`` above already
        relies on; the ATOMIC version of this conditional lives in
        :meth:`PostgresQuotaStore.try_incr_day`, where replicas contend."""
        bucket = (self._today(), key)
        count = self._day_counts.get(bucket, 0)
        if count >= cap:
            return None  # cap spent — the denial costs NOTHING (i-050).
        self._day_counts[bucket] = count + 1
        return count + 1

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
#: instance tables — the host provisions nothing extra.
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


#: asyncpg's ``ssl=`` values → libpq's ``sslmode=``. libpq's own mode names
#: pass through unchanged; asyncpg's boolean spellings map to the nearest
#: libpq mode (secure on truthy, plain on falsy).
_SSL_TO_SSLMODE = {
    "disable": "disable", "allow": "allow", "prefer": "prefer",
    "require": "require", "verify-ca": "verify-ca",
    "verify-full": "verify-full",
    "true": "require", "on": "require", "1": "require", "yes": "require",
    "false": "disable", "off": "disable", "0": "disable", "no": "disable",
}

#: Query params only asyncpg (or SQLAlchemy's asyncpg dialect) understands.
#: libpq rejects the WHOLE connection on any option it does not know
#: ('invalid connection option "..."'), so these are dropped, not passed.
_ASYNCPG_ONLY_QUERY_PARAMS = frozenset({
    "prepared_statement_cache_size",
    "statement_cache_size",
    "prepared_statement_name_func",
    "max_cached_statement_lifetime",
    "max_cacheable_statement_size",
    "command_timeout",
    "server_settings",
})


def _libpq_query(query: str) -> str:
    """Normalize a DSN query string to the dialect this store SPEAKS — libpq.

    The store's DBAPI is psycopg2/psycopg (see :func:`_sync_driver`), and
    libpq only accepts ``sslmode=``; the fallback DSN (``DNA_SOURCE_URL``)
    is asyncpg-shaped in a hosted deployment and carries ``ssl=require`` —
    which libpq rejects with ``invalid connection option "ssl"`` (i-057, seen
    live in dna-cloud). So: ``ssl=`` is translated to ``sslmode=`` (values
    mapped via ``_SSL_TO_SSLMODE``; an already-present ``sslmode=`` wins and
    the ``ssl=`` twin is dropped), asyncpg-only params are removed, and
    everything else (libpq-valid options like ``application_name``) passes
    through untouched."""
    from urllib.parse import parse_qsl, urlencode

    pairs = parse_qsl(query, keep_blank_values=True)
    has_sslmode = any(k == "sslmode" for k, _ in pairs)
    out: list[tuple[str, str]] = []
    for k, v in pairs:
        if k == "ssl":
            if has_sslmode:
                continue  # the explicit libpq spelling wins; drop the twin.
            out.append(("sslmode", _SSL_TO_SSLMODE.get(v.lower(), v)))
        elif k in _ASYNCPG_ONLY_QUERY_PARAMS:
            continue
        else:
            out.append((k, v))
    return urlencode(out)


def sync_pg_url(dsn: str) -> str:
    """Rewrite a DNA source DSN into a SQLAlchemy **sync** Postgres URL.

    Accepts what ``DNA_SOURCE_URL`` may carry — ``postgres://``,
    ``postgresql://``, ``postgresql+asyncpg://`` — and swaps the driver for
    the installed sync one, leaving host/database alone. The QUERY STRING is
    normalized to the libpq dialect the sync driver actually speaks
    (``ssl=`` → ``sslmode=``, asyncpg-only params dropped — see
    :func:`_libpq_query`): the fallback DSN is asyncpg-shaped by design, and
    handing its ``ssl=require`` to psycopg2 kills every metered call with
    ``invalid connection option "ssl"`` (i-057)."""
    scheme, sep, rest = dsn.partition("://")
    if not sep:
        raise ValueError(f"not a Postgres URL: {dsn!r}")
    base = scheme.split("+", 1)[0].lower()
    if base not in ("postgresql", "postgres"):
        raise ValueError(f"not a Postgres URL: {dsn!r}")
    netpath, qmark, query = rest.partition("?")
    if qmark:
        normalized = _libpq_query(query)
        rest = f"{netpath}?{normalized}" if normalized else netpath
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
    itself already makes to the same database.

    **Dialect:** the store connects through a SYNC DBAPI (psycopg2/psycopg —
    see :func:`_sync_driver`), i.e. it speaks **libpq** connection options.
    The ``dsn`` may be asyncpg-shaped (``DNA_SOURCE_URL`` is, in the hosted
    deployment); :func:`sync_pg_url` normalizes it — driver swapped and the
    query string translated to libpq (``ssl=`` → ``sslmode=``, asyncpg-only
    params dropped) — so a DSN the SOURCE dials with asyncpg cannot kill the
    quota connection with ``invalid connection option "ssl"`` (i-057)."""

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

    def try_incr_day(self, key: str, cap: int) -> int | None:
        """Advance today's counter ONLY while it stays within ``cap`` — atomically.

        The i-050 fix hinges on this statement. The cap rides INSIDE the same
        ``INSERT ... ON CONFLICT DO UPDATE`` that made the unconditional
        increment race-free, as the UPDATE's ``WHERE``::

            ON CONFLICT (day, tenant, tier)
            DO UPDATE SET calls = dna_quota_counters.calls + 1
            WHERE dna_quota_counters.calls < :cap
            RETURNING calls

        Postgres evaluates that ``WHERE`` against the row AFTER taking its
        lock and seeing the last COMMITTED value — the exact property the
        64x8-thread test pins for ``incr_day`` — so under concurrency exactly
        ``cap`` increments succeed and every loser gets ``None`` having
        written NOTHING. A check-then-``incr_day`` split across two
        statements would reintroduce the read-modify-write race; a
        compensating decrement after the denial would leave a window in which
        the billing read sees phantom calls. Neither is needed: the condition
        and the increment are one statement.

        When the ``WHERE`` rejects (or ``cap < 1`` — the fresh-INSERT arm
        would otherwise mint a count of 1 past a zero cap), no row comes back
        and the counter is untouched: a denied call is invisible to
        :meth:`calls_on`, the read the overage job bills from."""
        import sqlalchemy as sa

        if cap < 1:
            return None  # a cap of 0 admits nothing; never reach the INSERT arm.
        tenant, tier = split_quota_key(key)
        stmt = sa.text(
            f"INSERT INTO {self._qualified} (day, tenant, tier, calls) "
            "VALUES (:day, :tenant, :tier, 1) "
            "ON CONFLICT (day, tenant, tier) "
            f"DO UPDATE SET calls = {self._table}.calls + 1 "
            f"WHERE {self._table}.calls < :cap "
            "RETURNING calls"
        )
        with self._get_engine().begin() as conn:
            row = conn.execute(
                stmt,
                {"day": self._today(), "tenant": tenant, "tier": tier, "cap": cap},
            ).first()
        return int(row[0]) if row else None

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

    def calls_in_window(self, tenant: str, days: int) -> int:
        """Durable calls ``tenant`` made over the last ``days`` UTC days.

        The margin breaker's read (see :class:`QuotaStore`). One aggregate
        over the SAME rows :meth:`calls_on` bills from — no second counter, so
        the fuse and the invoice can never disagree about what was served.

        The horizon is a ROLLING window anchored on today, not the calendar
        month, and that is the safer of the two: a calendar period resets at
        midnight on the 1st, so a runaway spanning the 31st and the 1st gets
        two full ceilings inside 48 hours. A rolling window has no such seam.

        A failure PROPAGATES. Returning ``0`` on an unreachable table would
        read as "well under the ceiling" and serve the call — the fail-open
        :class:`MarginBreakerUnreadable` exists to refuse.

        NOTE the shape of the read: the counter's primary key is
        ``(day, tenant, tier)``, so a tenant-equality + day-range predicate
        scans the range rather than seeking one row. That is one aggregate per
        metered call over at most ``days`` x tenants rows, against the same
        pooled connection the counter already uses. It is deliberately NOT
        cached in-process: a cache is stale in the direction that undercounts,
        and a breaker that undercounts does not trip."""
        import sqlalchemy as sa

        if days <= 0:
            return 0
        stmt = sa.text(
            f"SELECT COALESCE(SUM(calls), 0) FROM {self._qualified} "
            "WHERE tenant = :tenant AND day >= :since"
        )
        since = self._today() - _dt.timedelta(days=days - 1)
        with self._get_engine().connect() as conn:
            row = conn.execute(stmt, {"tenant": tenant, "since": since}).first()
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


# ── the hosted-shape switch: fail-CLOSED on a missing Tier registry ─────────
#
# Empty caps are AMBIGUOUS: for an OSS/self-host they mean "never opted into
# DNA Cloud pricing — enforce nothing" (the open-core hard rule, default,
# untouched); for a HOSTED deployment whose Tier seed failed at boot they mean
# "every cap just silently evaporated" — fail-open exactly where money needs
# fail-closed. The SDK cannot tell the two apart, so the HOST declares which
# shape it is (i-051): dna-cloud sets the flag in its mcp container; a
# self-host never does.

#: Set to ``1`` (or ``true``/``yes``/``on``) to REFUSE metered calls when the
#: Tier registry is empty or unreadable, instead of serving them uncapped.
REQUIRE_TIERS_ENV = "DNA_QUOTA_REQUIRE_TIERS"


def require_tiers(env: Any = None) -> bool:
    """Whether this process opted into fail-CLOSED quota (the hosted shape).

    Read per-call (not cached at server build) so the flag is testable and a
    supervisor restart is not needed to observe a corrected environment. The
    guard consults it ONLY on the metered (token-present) branch — the
    stdio/local path returns before any of this, so the OSS invariant is
    structurally out of the flag's reach."""
    env = os.environ if env is None else env
    return str(env.get(REQUIRE_TIERS_ENV) or "").strip().lower() in (
        "1", "true", "yes", "on",
    )


class TierRegistryUnavailableError(RuntimeError):
    """The host demanded fail-CLOSED quota (``DNA_QUOTA_REQUIRE_TIERS=1``) and the
    Tier registry is empty or unreadable — the metered call must be REFUSED, not
    served uncapped (503 semantics on HTTP, a ToolError on MCP).

    Deliberately NOT a :class:`PermissionError`: the caller did nothing wrong —
    the deployment is broken, and the two faces map it to their transport's
    "service unavailable", never to a plan denial."""


class MarginBreakerUnreadable(TierRegistryUnavailableError):
    """The plan declared a cost-protection cutout and the counter it reads
    cannot be reached — so the call is REFUSED, never served on the assumption
    that the cutout is closed (503 semantics).

    The fail-SAFE half of :func:`enforce_margin_breaker`, and it follows the
    precedent set immediately above: under ``DNA_QUOTA_REQUIRE_TIERS`` a Tier
    registry the enforcer cannot read PROPAGATES, so the metered call fails
    instead of the billing. A breaker degrades the same way or not at all —
    **a breaker that cannot tell whether it is tripped and lets the call
    through is indistinguishable from no breaker**, which is exactly the defect
    i-134 measured.

    It needs no environment flag to opt in, because THE OPT-IN IS THE FIELD: a
    plan that never declared ``margin_breaker_calls_per_window`` never reaches
    this code, so an OSS / self-host source (empty caps) and every plan written
    before the cutout existed are structurally out of its reach. A deployment
    that DID declare a ceiling has said it wants the fuse; serving uncapped
    because a SELECT failed would be the fail-open this class exists to refuse.

    Subclasses :class:`TierRegistryUnavailableError` for the same reason
    :class:`MarginBreakerTripped` subclasses :class:`OverQuotaError`: both
    faces already map that type to 503, and the parent's own docstring states
    the semantics this needs verbatim — *the caller did nothing wrong, the
    deployment is broken*. Inheriting relays it correctly on faces written
    before it existed, with no enumeration to widen."""


# ── the MARGIN BREAKER (i-134) — a fuse for the operator, never a product ──
#
# ⭐ READ THIS BEFORE TOUCHING ANYTHING BELOW. The distinction it draws is the
# whole reason this code exists, and it is the thing most likely to be lost:
#
#     a SOLD LIMIT is a PROMISE to the customer — it belongs on the price
#     page, in the contract, in what the buyer expects to receive;
#     a BREAKER is what stops the house burning down while the right sold
#     limit does not exist yet.
#
# So: this cap is NOT a pricing axis, it must NOT appear on a plan table, and
# nobody reading this file tomorrow should be able to conclude "ah, we sell
# calls per month". The pricing decision (i-112) belongs to the founder and has
# not been made. This is the fuse that keeps the question open.
#
# WHY IT IS DENOMINATED IN CALLS AND NOT IN TOKENS — measured 07/08/2026, and
# the measurement is the design:
#
#   * the money is spent by MODEL INFERENCE, and the only place a token count
#     exists in this codebase is `dna.runtime.telemetry.TurnRecorder`, which
#     reads OpenInference LLM spans at the END of a turn, inside the copilot
#     PROCESS, and hands the total to a host-supplied sink;
#   * `enforce_plan` — this module, the one gate both faces and the A2A door
#     run — is a DIFFERENT process metering a DIFFERENT event (one tool call,
#     not one turn) and receives no token count of any kind. There is no
#     wiring, and the only feed that could be built is the `dna_turn` one that
#     the pricing research already disqualified: it drops under pressure
#     (`QUEUE_MAX`), swallows its own exceptions by design, records nothing
#     without a pool, and vanishes by CASCADE with the thread.
#
# For an INVOICE, undercounting loses money. For a BREAKER, undercounting means
# it never trips — and a breaker that does not trip is indistinguishable from
# no breaker. So the fuse is NOT built on a source with holes; it is built on
# the one meter this house constructed to decide with (`dna_quota_counters`),
# and it bounds the WORST-CASE cost by bounding the number of served calls,
# which is the only quantity the gate can count exactly.
#
# The operator therefore derives the NUMBER from dollars — worst-case cost per
# call x ceiling <= what the account can be allowed to cost — and writes it on
# the plan. The unit is calls because that is what can be counted honestly; the
# intent is dollars, and the name says so.
#
# ⚠️ WHAT THIS FUSE DOES NOT COVER, named rather than left to be rediscovered.
# It is keyed on the METERING TENANT, which is the workspace — the same key the
# daily cap and the bill already use. A billing ACCOUNT that owns N workspaces
# therefore gets N fuses, so account-level exposure is still multiplied by
# however many workspaces it can create. Closing that is the OTHER half of
# i-134 and it lives in dna-cloud, not here: `POST /api/workspaces` has no plan
# gate at all, and `max_tenants` — declared on the `PricingPlan` Kind since the
# Kind was written — still has NO READER anywhere. Two named, unbuilt things;
# neither is this change, and neither is a reason to key the fuse on an
# identity this gate would have to go looking for.

#: The cutout, in calls over the window. ``None`` / absent = NO BREAKER, which
#: is the default and keeps every existing plan (and every OSS self-host, whose
#: caps are empty) behaving exactly as before. Declaring it is the opt-in.
MARGIN_BREAKER_CAP_FIELD = "margin_breaker_calls_per_window"

#: The rolling horizon in days. Rolling, not calendar: a calendar period resets
#: at midnight on the 1st, so a runaway straddling the 31st and the 1st would
#: get two full ceilings inside 48 hours.
MARGIN_BREAKER_WINDOW_FIELD = "margin_breaker_window_days"

#: Used when a plan declares a ceiling but no horizon. 30 days is the period the
#: bill accrues in, which is the horizon the exposure is measured over.
DEFAULT_MARGIN_BREAKER_WINDOW_DAYS = 30


def margin_breaker_window_days(caps: dict[str, Any]) -> int:
    """The breaker's horizon for these caps, in days.

    READ from the plan (never a literal at the call site — the same contract
    ``calls_per_day`` has); a plan that declares a ceiling and no horizon gets
    :data:`DEFAULT_MARGIN_BREAKER_WINDOW_DAYS`. A non-positive or unparseable
    value also falls back rather than silently disabling the fuse: ``days <= 0``
    makes the window read count nothing, which is a breaker that never trips —
    exactly the failure mode this whole module is about."""
    raw = caps.get(MARGIN_BREAKER_WINDOW_FIELD)
    try:
        days = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_MARGIN_BREAKER_WINDOW_DAYS
    return days if days > 0 else DEFAULT_MARGIN_BREAKER_WINDOW_DAYS


def enforce_margin_breaker(
    *,
    caps: dict[str, Any],
    tenant: str | None,
    tier: str,
    store: QuotaStore,
) -> None:
    """Refuse this call when the operator's COST-PROTECTION CUTOUT is open.

    Not a plan allowance — read the block comment above this function before
    changing anything here, including the message.

    **What it decides on.** ``store.calls_in_window(tenant, days)``: the sum of
    the SAME durable counters the daily cap advances and the overage job bills
    from, over a rolling window. No second counter, no telemetry, no estimate.
    An estimated breaker refuses honest customers by arithmetic nobody agreed
    to, which is worse than none.

    **Where it sits, and why.** After the feature-family gate and BEFORE the
    rate window and the daily counter. That ordering is load-bearing in both
    directions:

    * before the daily counter, because :meth:`QuotaStore.try_incr_day` is the
      billed one and i-050 says a refused call must never reach it. Checking
      the fuse after the increment would bill a call the fuse then refused;
    * before the rate window, because ``note_call`` records what the tenant
      SPENT (i-055) and a refused call must not extend a window it never used.

    It counts NOTHING itself — it is a read — so a refusal here leaves both
    counters exactly as they were, and the honesty guarantees of i-050 and
    i-055 are inherited rather than re-argued.

    **The residual, stated rather than hidden.** The check is a READ, and the
    increment it will be measured by happens after it (the daily counter,
    further down :func:`enforce_quota`), so N calls in flight can each observe
    the same sub-ceiling total and all be admitted: the fuse can overshoot by
    roughly the in-flight concurrency. The error is in the direction of serving
    a handful of extra
    calls out of a ceiling in the tens of thousands, never of refusing a tenant
    who is under it — which is the right way round for a cutout whose purpose
    is to stop a runaway, and the wrong way round would be a false refusal.

    **Fail-SAFE, not fail-open.** If the store cannot answer — it raises, or it
    is an older/foreign :class:`QuotaStore` with no window read at all — the
    call is REFUSED with :class:`MarginBreakerUnreadable`. Precedent:
    ``DNA_QUOTA_REQUIRE_TIERS``, which propagates a registry failure "so the
    metered call fails instead of the billing". A missing method is treated
    exactly like a failing one on purpose: a host that injects its own store
    would otherwise disable the fuse in silence, which is the same outcome as
    deleting it.

    Empty ``caps`` (OSS / self-host) and any plan that does not declare the
    ceiling never reach any of this."""
    declared = caps.get(MARGIN_BREAKER_CAP_FIELD)
    if declared is None:
        return  # no cutout declared — the default, and the OSS path.
    try:
        cap = int(declared)
    except (TypeError, ValueError):
        # An unreadable ceiling is not "no ceiling". Somebody typed a number
        # into a plan and meant a fuse; falling through would serve uncapped
        # on a typo, which is the fail-open this whole gate refuses. The
        # message names the value so the fix is a one-line plan edit.
        raise MarginBreakerUnreadable(
            f"tier {tier!r} declares a cost-protection cutout "
            f"({MARGIN_BREAKER_CAP_FIELD}={declared!r}) that is not a number, "
            f"so the ceiling is UNKNOWN — refusing this call instead of "
            f"serving it uncapped. Fix the value on the plan."
        ) from None
    days = margin_breaker_window_days(caps)
    key_tenant = tenant or "-"

    read = getattr(store, "calls_in_window", None)
    if read is None:
        raise MarginBreakerUnreadable(
            f"tier {tier!r} declares a cost-protection cutout "
            f"({MARGIN_BREAKER_CAP_FIELD}={cap}), but the quota store wired "
            f"into this process ({type(store).__name__}) cannot report usage "
            f"over a window — so whether the cutout is open is UNKNOWN, and "
            f"this call is refused rather than served on the assumption that "
            f"it is closed."
        )
    try:
        used = int(read(key_tenant, days))
    except Exception as exc:  # noqa: BLE001 — a fuse that cannot read must open.
        raise MarginBreakerUnreadable(
            f"tier {tier!r} declares a cost-protection cutout "
            f"({MARGIN_BREAKER_CAP_FIELD}={cap} per {days}d) and the usage "
            f"counter could not be read, so whether the cutout is open is "
            f"UNKNOWN — refusing this call instead of serving it uncapped "
            f"(counter read failed: {exc})"
        ) from None

    if used >= cap:
        raise MarginBreakerTripped(
            f"cost-protection cutout OPEN for {key_tenant!r}: "
            f"{used} metered calls in the last {days} days, at or past the "
            f"operator's protection ceiling of {cap}. This ceiling is NOT part "
            f"of what the plan sells and is not a usage allowance — it is a "
            f"fuse the operator sets to bound what a single account can cost, "
            f"and it opened. Nothing was counted for this refused call. Ask "
            f"the operator to raise the ceiling for this account, or wait for "
            f"the window to roll."
        )


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
    1b. **margin breaker** — if ``caps['margin_breaker_calls_per_window']`` is
       set, refuse once the tenant's rolling-window usage reaches it
       (:func:`enforce_margin_breaker`). A COST CUTOUT for the operator, not a
       sold limit; it counts nothing itself and runs before anything is
       counted, so a refusal here leaves both counters untouched.
    2. **rate** — if ``caps['rate_per_sec']`` is set, admit the call only while
       the 1-second window is under the cap, and record it ONLY if admitted; at
       the cap → :class:`OverQuotaError` and the denied call does not extend the
       window (i-055: the refusal says "retry shortly", so the retry must not be
       what keeps the window shut).
    3. **daily quota** — if ``caps['calls_per_day']`` is set, count this call
       ONLY if the day's counter stays within the cap (one atomic conditional
       increment — :meth:`QuotaStore.try_incr_day`); at the cap →
       :class:`OverQuotaError` and the denied call is NOT counted (i-050:
       what was refused must never reach the billed counter).

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

    # 1b. the MARGIN BREAKER (i-134). A cost-protection cutout for the
    # OPERATOR — not a sold limit, not a pricing axis, never a price-page
    # number. It runs here, before the rate window and before the daily
    # counter, because both of those RECORD something (i-055 / i-050) and a
    # call this fuse refuses must leave no trace in either. It records nothing
    # itself: it reads the counters the daily cap already writes.
    enforce_margin_breaker(caps=caps, tenant=tenant, tier=tier, store=store)

    key = quota_key(tenant, tier)

    # 2. rate limit (calls-per-second window). Policy: the window records what
    # the tenant SPENT, so a denied call never enters it (i-055 — the rate
    # twin of i-050's billing honesty on the daily axis below). It used to
    # `note_call` BEFORE checking, which made the refusal self-defeating: the
    # message says "retry shortly", retry-on-429 is the default behaviour of
    # every MCP client, and each retry re-filled the window it was waiting on —
    # so a client under load drove its own throughput toward zero by obeying the
    # instruction. Checking first means the window clears one second after the
    # last ADMITTED call, which is the only reading under which "retry shortly"
    # is true. Admission is unchanged: `rate` calls per window still pass, the
    # (rate + 1)-th still does not.
    rate = caps.get("rate_per_sec")
    if rate is not None:
        if store.rate_count(key, 1.0) >= rate:
            raise OverQuotaError(
                f"tier {tier!r} rate limit exceeded ({rate}/s) — slow down "
                f"(retry shortly; this denied call did NOT extend the window)."
            )
        store.note_call(key)

    # 3. daily quota (calls-per-day counter). Policy: HARD cap — a denied call
    # is NOT counted (i-050). The overage job bills SUM(calls) - included off
    # this counter, so counting a denial would charge the customer for a call
    # it was refused; deny-without-counting is the only reading under which
    # `calls_per_day` (sold as a hard cap) and per-call overage cannot
    # contradict each other. The increment is CONDITIONAL AND ATOMIC
    # (`try_incr_day` — the cap rides inside the store's own statement), never
    # check-then-increment. A future SOFT cap (overage billing: allow AND
    # count above the cap) is the other branch of this `if` — it would switch
    # to the unconditional `store.incr_day(key)` and not raise, gated on a
    # Tier-spec knob (e.g. `spec.overage`), which is a product decision, not a
    # rewrite here.
    cpd = caps.get("calls_per_day")
    if cpd is not None:
        if store.try_incr_day(key, int(cpd)) is None:
            raise OverQuotaError(
                f"tier {tier!r} daily call quota exhausted (the {cpd}/day cap "
                f"is spent; this denied call was NOT counted) — upgrade the "
                f"plan or wait for the daily reset."
            )


# ── the ONE metered-call policy (shared by the MCP guard and the REST gates) ─
#
# Before i-042 this pipeline lived INSIDE `_mcp_server._guard` (tier resolution
# → caps → mode gates → enforce_quota), which made it structurally impossible
# for the REST face to enforce the same plan without duplicating policy. It is
# now the module's own composition, and BOTH faces call it:
#
#     _mcp_server._guard / _personal_guard   →  enforce_plan(...)
#     _rest_api build_app's _plan_gate       →  enforce_plan(...)
#
# so a policy change (tier order, fail-closed switch, i-050 honesty) lands on
# both channels at once — there is no second copy to drift. The transport error
# mapping (ToolError vs HTTPException) is the ONLY thing each face keeps.


async def resolve_metered_tier(
    kernel: Any,
    *,
    tenant: str | None,
    claimed_tier: str | None = None,
    default_tier: str = "free",
) -> str:
    """Resolve the effective Tier id for a metered call.

    The resolution order the MCP guard always applied, now shared verbatim:
    **explicit claim → AccountPlan store → Free floor**. A ``claimed_tier``
    (the token's explicit ``plan`` claim) WINS and the store is not consulted;
    otherwise the billing→enforcement bridge resolves **workspace → account →
    plan** in TWO HOPS, because the subscription belongs to the BILLING
    ACCOUNT, not to a workspace: the resolved workspace's ``account_id``
    (``kernel.account_for_workspace``) then that ACCOUNT's assigned Tier from
    the ``AccountPlan`` Kind (``kernel.account_plan`` — written by dna-cloud's
    Stripe webhook). One plan covers every workspace the account owns, so a
    second workspace is never a second charge.

    Both hops are fail-closed by omission — a workspace with no ``account_id``,
    or an account with no plan, simply yields no tier and the ``default_tier``
    floor stands. Neither hop can ever return ANOTHER account's plan: the
    second lookup is keyed strictly on the id the first returned, and a blank
    account_id is refused before the query rather than matched against blank
    docs.

    NOTE the cost: one extra _lib registry read per metered call (Workspace) on
    top of the AccountPlan read — the same order as the WorkspaceMembership
    read the guard's ``_workspace()`` already performs, against the same
    ``_lib`` scope and the same cache, so the hot path gains a read of a kind
    it was already doing, not a new class of work."""
    if claimed_tier is not None:
        return claimed_tier
    if tenant:
        account_id = await kernel.account_for_workspace(tenant)
        if account_id:
            plan = await kernel.account_plan(account_id)
            store_tier = ((plan or {}).get("spec") or {}).get("tier_id")
            if store_tier:
                return str(store_tier)
    return default_tier


async def resolve_tier_caps(kernel: Any, tier: str) -> dict[str, Any]:
    """Resolve a Tier id to its caps ``spec`` — with the i-051 fail-closed switch.

    ``kernel.tier(tier)`` → unknown tier falls to the ``free`` doc (the Free
    floor) → still nothing = empty caps. Empty caps are AMBIGUOUS: an OSS /
    self-host source that never seeded Tier docs must enforce NOTHING (the
    open-core rule), while a hosted deployment whose Tier seed failed must
    REFUSE the call rather than serve it uncapped. The host declares which
    shape it is via ``DNA_QUOTA_REQUIRE_TIERS`` (:func:`require_tiers`):

    * flag OFF — empty caps pass through (enforce nothing); a registry READ
      error propagates as the real bug it is (not a quota refusal).
    * flag ON — empty caps AND a registry read error both raise
      :class:`TierRegistryUnavailableError` (fail closed, nothing served)."""
    try:
        row = await kernel.tier(tier)
        if row is None:
            row = await kernel.tier("free")  # unknown tier → Free floor.
    except Exception as exc:  # noqa: BLE001 — flag-on only; see docstring.
        if not require_tiers():
            raise  # flag OFF: not a quota refusal — surface the real bug.
        raise TierRegistryUnavailableError(
            "tier registry empty/unreadable — quota enforcement "
            "unavailable, refusing this call (DNA_QUOTA_REQUIRE_TIERS=1; "
            f"registry read failed: {exc})"
        ) from None
    caps = (row or {}).get("spec") or {}
    if not caps and require_tiers():
        raise TierRegistryUnavailableError(
            "tier registry empty/unreadable — quota enforcement "
            "unavailable, refusing this call (DNA_QUOTA_REQUIRE_TIERS=1). "
            "Seed the Tier docs in _lib, or unset the flag on an uncapped "
            "self-host."
        )
    return caps


async def enforce_plan(
    kernel: Any,
    *,
    tenant: str | None,
    family: str,
    store: QuotaStore,
    claimed_tier: str | None = None,
    memory_op: str | None = None,
    sdlc_op: str | None = None,
    family_op: str | None = None,
    quota_tenant: str | None = None,
) -> str:
    """Meter ONE authenticated call against the caller's plan — the shared core.

    Composes the whole pipeline the MCP ``_guard`` always ran, for any face:

    1. resolve the Tier (:func:`resolve_metered_tier` — claim → workspace →
       account → AccountPlan →
       Free floor),
    2. resolve its caps (:func:`resolve_tier_caps` — Free-doc fallback, empty
       caps = OSS no-op, ``DNA_QUOTA_REQUIRE_TIERS`` fail-closed),
    3. the PRE-COUNTER gates — ``memory_op``/``sdlc_op`` against the tier's
       ``memory_mode``/``sdlc_mode`` (a denied write costs no quota), and
       ``family_op`` against ``<family>_mode`` for a GENERIC instance call whose
       family was derived from the target Kind (:func:`enforce_family_mode`),
    4. :func:`enforce_quota` — family gate, the margin breaker (i-134 — the
       operator's cost cutout, not a sold limit), rate window, daily cap (the
       i-050 honesty lives there: a denied call is never counted).

    ``quota_tenant`` overrides the METERING key only (the personal-memory case:
    tenancy resolves no workspace but usage meters per ``personal:<oid>``
    partition). Raises the quota exception family
    (:class:`FeatureNotInPlanError` / :class:`MemoryModeError` /
    :class:`SdlcModeError` / :class:`InstanceModeError` /
    :class:`OverQuotaError`, whose subclass :class:`MarginBreakerTripped` is the
    cost cutout) or :class:`TierRegistryUnavailableError` (whose subclass
    :class:`MarginBreakerUnreadable` is the cutout's fail-safe); each face maps
    them to its transport, and the two new ones ride the parents' mappings on
    purpose so no face has to widen an enumeration to relay them.
    Returns the resolved tier id (observability / tests).

    The OSS invariant is the CALLER's job, exactly as before: a face only calls
    this once it knows the request is authenticated/metered (MCP: token present;
    REST: ``--auth token|config``). ``--auth none`` / stdio never reach here."""
    tier = await resolve_metered_tier(kernel, tenant=tenant, claimed_tier=claimed_tier)
    caps = await resolve_tier_caps(kernel, tier)
    # memory_mode / sdlc_mode are pre-counter gates (like the family gate):
    # a denied write costs no quota. Enforce them BEFORE metering.
    if memory_op is not None:
        enforce_memory_mode(caps=caps, tier=tier, op=memory_op)
    if sdlc_op is not None:
        enforce_sdlc_mode(caps=caps, tier=tier, op=sdlc_op)
    if family_op is not None:
        enforce_family_mode(caps=caps, tier=tier, family=family, op=family_op)
    enforce_quota(
        caps=caps,
        tenant=quota_tenant if quota_tenant is not None else tenant,
        tier=tier, family=family, store=store,
    )
    return tier
