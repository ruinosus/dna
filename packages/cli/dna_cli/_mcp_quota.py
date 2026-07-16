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

The counting is behind a small **port** (:class:`QuotaStore`) so the default
in-process impl (fine to prototype, **WRONG for real billing** — it is per-process
and resets on restart) can be swapped for a Postgres/Redis-backed store without
touching the enforcement policy. The durable store is the DNA Cloud SaaS control
plane's job — see ``adr-dna-cloud-saas``.

The invariant that keeps OSS/self-host untouched lives in the CALLER
(``_mcp_server._guard``): quota is enforced ONLY when a token is present. With no
token (stdio / local / ``auth=None``) the guard is an identity — this module is
never reached, so nothing is metered and everything is unlimited.
"""
from __future__ import annotations

import time
from typing import Any, Protocol


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


# ── the store port (swap in Postgres/Redis for real billing) ───────────────


class QuotaStore(Protocol):
    """The metering port — the seam a durable (Postgres/Redis) store slots into.

    Two axes, keyed by an opaque ``key`` (the caller composes it from
    tenant+tier): a **daily** counter (calendar-day bucket, UTC) and a **rate**
    window (recent-call timestamps). The default :class:`InProcQuotaStore` is
    in-process — correct for a single prototype process, **wrong for billing**
    (per-process, resets on restart). ``adr-dna-cloud-saas`` covers the durable
    impl behind this identical interface."""

    def incr_day(self, key: str) -> int:
        """Increment today's counter for ``key`` and return the new count."""
        ...

    def note_call(self, key: str) -> None:
        """Record a call for ``key`` at the current instant (rate window)."""
        ...

    def rate_count(self, key: str, window_s: float) -> int:
        """How many calls ``key`` made in the last ``window_s`` seconds."""
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


# The module-level singleton the server wires by default. A host that wants a
# durable store passes its own ``QuotaStore`` into ``enforce_quota``.
DEFAULT_STORE = InProcQuotaStore()


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

    key = f"{tenant or '-'}::{tier}"

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
