"""``dna_cli._mcp_egress`` — the DNA Cloud **egress policy**: which EXTERNAL MCP
servers a tenant is allowed to dial, given its plan.

The rule this module encodes is one line long: **a destination outside the
operator's curated allowlist is only dialled by a tier that was granted
unrestricted egress; every other tier is allowlist-only.** The allowlist itself
is CONFIG (:data:`ALLOWLIST_ENV`, a CSV of HTTPS prefixes), never a literal —
same contract as the quota caps next door.

Why it lives here, next to :mod:`dna_cli._mcp_quota` and not inside it:

* the tier a call is metered under is resolved by
  :func:`dna_cli._mcp_quota.resolve_metered_tier`, and this policy CONSULTS it —
  so the dependency direction can only ever be egress → tier resolution. A
  sibling module makes that direction structural; folding the policy into
  ``_mcp_quota`` would mix the METER (counters, stores, caps) with a
  DESTINATION policy that counts nothing.
* it is the same package, so anything that already depends on ``dna-cli`` for
  ``resolve_metered_tier`` can import this with no new dependency.

**It could not live in ``dna-sdk``.** The whole plan/tier policy — the resolver
this module calls — lives in the CLI package, and ``dna-sdk`` sits BELOW it in
the dependency graph; putting egress in the SDK would split one policy across
two packages and invert the import.

## The runtime half of a two-sided refusal

This is defence in depth, not the only gate. A portal that lets a user declare
an external MCP server refuses out-of-policy URLs at WRITE time, where it can
put a sentence in front of a human. This module is the RUNTIME half: even a
document written around the portal cannot make a container dial an unauthorised
destination — the server is dropped from the graph with a log naming the URL and
the tier, never dialled in silence.

## Fail-closed, structurally

If the tier resolver raises, the caller is treated as restricted. Not "assume
free and re-derive" — *restricted*, unconditionally — so no configuration of
:paramref:`unrestricted_tiers` can turn a kernel outage into open egress. The
tier reported in the log line falls back to :data:`FAILSAFE_TIER` for
readability only; it never re-enters the decision.

## Two shapes, because there are two kinds of caller

* :func:`filter_egress` — a flat list of ``{"url": ...}`` declarations, filtered
  entry by entry. This is the shape a copilot graph builder holds.
* :func:`partition_egress` — arbitrary objects carrying **one or more** URLs,
  split all-or-nothing into (allowed, refused). This is the shape a server
  mounter holds, and the all-or-nothing part is POLICY, not convenience:
  approving a spec document fetched from an allowlisted host while the calls it
  describes leave for another host is exactly the hole the allowlist exists to
  close. An object is dialled whole or not at all.

Both resolve the tier **at most once**, and not at all when every destination
already passes the allowlist — the common case costs zero kernel reads.

## The OSS invariant

Same as the metering module's: this is reached only by a HOSTED, multi-tenant
face that mounts destinations declared by a tenant. A local ``dna mcp serve``
with ``--auth none`` never calls it, so a self-host is not gated by an allowlist
it never set.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

#: The operator-facing name of the allowlist variable — a CSV of HTTPS prefixes.
#:
#: Exported as a CONSTANT on purpose, and it is the reason this module exists as
#: much as the functions are. While the policy was copied into two deployables,
#: the env name was copied with it; renaming it on one side left both sides
#: green and one of them reading a variable nobody sets — i.e. with an EMPTY
#: allowlist, refusing everything for a restricted tier, with no error anywhere.
#: One definition, imported, is the only version of that which cannot happen.
ALLOWLIST_ENV = "DNA_MCP_EGRESS_ALLOWLIST"

#: Tiers granted unrestricted egress by DEFAULT.
#:
#: This reproduces the decision in force at the time the policy was unified, so
#: adopting the shared module is a behaviour-preserving import swap. It is a
#: DEFAULT ARGUMENT and not a rule: a deployment whose plans are named
#: differently passes its own set.
#:
#: ⚠️ The durable home for this is a cap on the ``PricingPlan`` Kind (read from
#: the registry like ``calls_per_day`` is, "never a cap literal in code"), not a
#: default argument in Python. That is a schema addition plus a coordinated edit
#: of the deployed plan documents — a plan doc missing the new field would go
#: from unrestricted to allowlist-only in silence — so it is tracked as its own
#: work item rather than smuggled in behind a fallback.
DEFAULT_UNRESTRICTED_TIERS: tuple[str, ...] = ("pro",)

#: The tier NAME used in the refusal log when the resolver could not be reached.
#: Cosmetic only — see "Fail-closed, structurally" above; the decision is
#: already made at that point.
FAILSAFE_TIER = "free"

T = TypeVar("T")

__all__ = [
    "ALLOWLIST_ENV",
    "DEFAULT_UNRESTRICTED_TIERS",
    "FAILSAFE_TIER",
    "egress_allowlist",
    "egress_allows",
    "filter_egress",
    "partition_egress",
]


def egress_allowlist(env: Mapping[str, str] | None = None) -> list[str]:
    """The authorised HTTPS prefixes, parsed from :data:`ALLOWLIST_ENV`.

    Read fresh on every call (the process may be reconfigured between requests)
    and forgiving about spacing, because the value is typed by a human into a
    deployment template. An unset or blank variable yields ``[]`` — an empty
    allowlist, which is the strict reading: a restricted tier then reaches
    nothing external. Pass ``env`` to read a mapping other than ``os.environ``.
    """
    raw = (os.environ if env is None else env).get(ALLOWLIST_ENV, "") or ""
    return [p.strip() for p in raw.split(",") if p.strip()]


def egress_allows(url: str, *, allowlist: Sequence[str] | None = None) -> bool:
    """True when ``url`` starts with one of the authorised prefixes.

    Matching is by PREFIX, not by host, and that is deliberate in both
    directions: a prefix can pin a path (``https://host/mcp``) as well as a
    host, which host matching could not express. The cost is the mirror image —
    the prefix ``https://good.example`` also admits
    ``https://good.example.attacker.test``. Write prefixes that end at a path
    separator when the host is what you mean.

    ``allowlist`` defaults to :func:`egress_allowlist`; pass it explicitly to
    parse the environment once across a batch.
    """
    prefixes = egress_allowlist() if allowlist is None else allowlist
    candidate = (url or "").strip()
    return any(candidate.startswith(prefix) for prefix in prefixes)


def _declared_url(server: Any) -> str | None:
    """The URL of one ``{"url": ...}`` declaration, or ``None`` when the entry
    does not declare one in the expected shape.

    ``None`` means "this policy has nothing to say about this entry" — NOT
    "refuse it". A malformed entry is somebody else's validation error, and
    silently eating it here would hide it.
    """
    if isinstance(server, dict):
        url = server.get("url")
        if isinstance(url, str):
            return url
    return None


async def _egress_tier(
    kernel: Any,
    *,
    workspace: str,
    tier_resolver: Callable[..., Any] | None,
    unrestricted_tiers: Collection[str],
) -> tuple[Any, bool]:
    """Resolve the tier and whether it may dial anywhere: ``(tier, unrestricted)``.

    ``tier_resolver`` defaults to :func:`dna_cli._mcp_quota.resolve_metered_tier`,
    imported lazily so this module stays importable (and testable) without the
    metering machinery. A resolver that raises yields ``(FAILSAFE_TIER, False)``
    — restricted, whatever ``unrestricted_tiers`` says.
    """
    if tier_resolver is None:
        from dna_cli._mcp_quota import resolve_metered_tier as tier_resolver
    try:
        tier = await tier_resolver(kernel, tenant=workspace)
    except Exception:  # noqa: BLE001 — resolver down: fail CLOSED for egress.
        return FAILSAFE_TIER, False
    return tier, tier in unrestricted_tiers


async def filter_egress(
    servers: Sequence[Any] | None,
    *,
    workspace: str,
    kernel: Any,
    tier_resolver: Callable[..., Any] | None = None,
    unrestricted_tiers: Collection[str] = DEFAULT_UNRESTRICTED_TIERS,
    log: logging.Logger | None = None,
) -> list[Any]:
    """The ``{"url": ...}`` declarations THIS workspace is allowed to dial.

    Entries whose URL is outside the allowlist are dropped for a restricted tier
    and LOGGED with URL and tier — the other half of the refusal (the sentence a
    human reads) belongs to whatever surface accepted the declaration. Entries
    that declare no string URL are passed through untouched
    (see :func:`_declared_url`).

    ``log`` lets a caller keep its own logger name for these refusals, which is
    what an operator greps for; it defaults to this module's.
    """
    if not servers:
        return []
    prefixes = egress_allowlist()

    def _outside(entry: Any) -> bool:
        url = _declared_url(entry)
        return url is not None and not egress_allows(url, allowlist=prefixes)

    if not any(_outside(s) for s in servers):
        return list(servers)

    tier, unrestricted = await _egress_tier(
        kernel,
        workspace=workspace,
        tier_resolver=tier_resolver,
        unrestricted_tiers=unrestricted_tiers,
    )
    if unrestricted:
        return list(servers)

    out = log or logger
    allowed: list[Any] = []
    for server in servers:
        if _outside(server):
            out.warning(
                "egress refused (tier %s, workspace %s): %s is outside the "
                "%s allowlist — the server was dropped",
                tier, workspace, _declared_url(server), ALLOWLIST_ENV,
            )
            continue
        allowed.append(server)
    return allowed


async def partition_egress(
    items: Sequence[T],
    *,
    urls: Callable[[T], Iterable[Any]],
    workspace: str,
    kernel: Any,
    tier_resolver: Callable[..., Any] | None = None,
    unrestricted_tiers: Collection[str] = DEFAULT_UNRESTRICTED_TIERS,
    log: logging.Logger | None = None,
) -> tuple[list[T], list[T]]:
    """Split ``items`` into ``(allowed, refused)`` — **all-or-nothing per item**.

    ``urls`` extracts every destination one item would reach; an item passes
    only when ALL of them pass. That is the policy, not an implementation
    detail: an item with two destinations (a document to fetch and a base URL
    the calls actually go to) that is half-allowed is not partially safe, it is
    a bypass with extra steps.

    Non-string values from ``urls`` are ignored, matching
    :func:`filter_egress`'s treatment of malformed declarations. An item that
    yields no destinations is allowed — there is nothing to refuse.

    The tier is resolved ONCE for the whole batch, and only if some destination
    fails the allowlist. Refusals are logged per destination, as in
    :func:`filter_egress`.
    """
    if not items:
        return [], []
    prefixes = egress_allowlist()

    refused_urls: dict[int, list[str]] = {}
    for index, item in enumerate(items):
        outside = [
            u for u in urls(item)
            if isinstance(u, str) and not egress_allows(u, allowlist=prefixes)
        ]
        if outside:
            refused_urls[index] = outside
    if not refused_urls:
        return list(items), []

    tier, unrestricted = await _egress_tier(
        kernel,
        workspace=workspace,
        tier_resolver=tier_resolver,
        unrestricted_tiers=unrestricted_tiers,
    )
    if unrestricted:
        return list(items), []

    out = log or logger
    allowed: list[T] = []
    refused: list[T] = []
    for index, item in enumerate(items):
        outside = refused_urls.get(index)
        if not outside:
            allowed.append(item)
            continue
        for url in outside:
            out.warning(
                "egress refused (tier %s, workspace %s): %s is outside the "
                "%s allowlist — the whole declaration was dropped",
                tier, workspace, url, ALLOWLIST_ENV,
            )
        refused.append(item)
    return allowed, refused
