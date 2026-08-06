"""``dna_cli._mcp_egress`` — the plan-gated egress policy.

What these tests hold down, in the order the policy decides:

1. the ALLOWLIST is config, parsed forgivingly, and its ENV NAME is a contract
   (a deployment writes it; a rename that only lands on one side is the failure
   mode this module was extracted to make impossible);
2. matching is by PREFIX — both what that buys and what it costs;
3. the TIER gate — resolved at most once, never at all when nothing is outside
   the list, and FAIL-CLOSED when the resolver is down;
4. the two caller shapes decide the SAME way, one entry at a time
   (:func:`filter_egress`) and all-or-nothing per object
   (:func:`partition_egress`).

The tier resolver is injected in almost every test: what is under test here is
the POLICY, not the plan lookup (that has its own suite next door). One test
deliberately does NOT inject it, to prove the default wiring reaches
``dna_cli._mcp_quota.resolve_metered_tier`` — otherwise every green test here
could be running against a resolver production never calls.
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from dna_cli._mcp_egress import (
    ALLOWLIST_ENV,
    DEFAULT_UNRESTRICTED_TIERS,
    FAILSAFE_TIER,
    egress_allowlist,
    egress_allows,
    filter_egress,
    partition_egress,
)

_INSIDE = "https://mcp.example.test/mcp"
_OUTSIDE = "https://elsewhere.example/mcp"
_PREFIX = "https://mcp.example.test"


def _resolver(tier, *, calls: list | None = None):
    """A tier resolver double that records how often it was consulted."""

    async def resolve(_kernel, *, tenant):
        if calls is not None:
            calls.append(tenant)
        return tier

    return resolve


async def _boom(_kernel, *, tenant):
    raise RuntimeError("kernel unreachable")


def _run(coro):
    return asyncio.run(coro)


# --- 1. the allowlist is config -------------------------------------------


def test_allowlist_parses_csv_and_trims(monkeypatch):
    monkeypatch.setenv(ALLOWLIST_ENV, " https://a.example , https://b.example ,, ")
    assert egress_allowlist() == ["https://a.example", "https://b.example"]


def test_allowlist_unset_or_blank_is_empty(monkeypatch):
    monkeypatch.delenv(ALLOWLIST_ENV, raising=False)
    assert egress_allowlist() == []
    monkeypatch.setenv(ALLOWLIST_ENV, "   ")
    assert egress_allowlist() == []


def test_allowlist_can_read_an_injected_mapping(monkeypatch):
    """The env is the default source, not the only one — so a caller holding a
    settings mapping does not have to mutate the process environment."""
    monkeypatch.setenv(ALLOWLIST_ENV, "https://from-os.example")
    assert egress_allowlist({ALLOWLIST_ENV: "https://injected.example"}) == [
        "https://injected.example",
    ]


def test_the_env_name_is_the_operator_contract():
    """This literal is written by hand into deployment templates.

    It is asserted here — rather than left implicit — because the failure it
    guards is silent: read a variable nobody sets and you get an EMPTY
    allowlist, which for a restricted tier refuses everything, with no error
    anywhere. If this name has to change, it changes here AND in every template
    that writes it, in the same commit.
    """
    assert ALLOWLIST_ENV == "DNA_MCP_EGRESS_ALLOWLIST"


# --- 2. matching is by prefix ----------------------------------------------


def test_prefix_matching_admits_a_path_scoped_entry(monkeypatch):
    monkeypatch.setenv(ALLOWLIST_ENV, "https://host.example/team-a/")
    assert egress_allows("https://host.example/team-a/mcp")
    assert not egress_allows("https://host.example/team-b/mcp")


def test_prefix_matching_also_admits_a_lookalike_host(monkeypatch):
    """The documented cost of prefix (rather than host) matching.

    Pinned as a TEST so the trade-off is a decision on record: a prefix that
    stops at the host also admits any longer host that starts with it. Anyone
    tightening this to host matching will see this test and have to say so.
    """
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    assert egress_allows("https://mcp.example.test.attacker.invalid/mcp")


def test_allows_is_false_on_an_empty_allowlist(monkeypatch):
    monkeypatch.delenv(ALLOWLIST_ENV, raising=False)
    assert not egress_allows(_INSIDE)


def test_allows_tolerates_surrounding_space_and_empty_input(monkeypatch):
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    assert egress_allows(f"  {_INSIDE}")
    assert not egress_allows("")


# --- 3. the tier gate ------------------------------------------------------


def test_nothing_outside_the_list_never_resolves_the_tier(monkeypatch):
    """The common case must cost ZERO kernel reads — the mount path runs it on
    every cache miss, per workspace."""
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    calls: list = []
    out = _run(filter_egress(
        [{"url": _INSIDE}, {"url": _PREFIX + "/other"}],
        workspace="ws", kernel=None,
        tier_resolver=_resolver("free", calls=calls),
    ))
    assert out == [{"url": _INSIDE}, {"url": _PREFIX + "/other"}]
    assert calls == []


def test_a_restricted_tier_drops_what_is_outside(monkeypatch, caplog):
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    with caplog.at_level(logging.WARNING):
        out = _run(filter_egress(
            [{"url": _INSIDE}, {"url": _OUTSIDE}],
            workspace="ws", kernel=None, tier_resolver=_resolver("free"),
        ))
    assert out == [{"url": _INSIDE}]
    # The refusal is never silent: URL, tier and workspace are all in the line,
    # because that log IS the operator's only view of a dropped destination.
    assert any(
        _OUTSIDE in r.getMessage() and "free" in r.getMessage()
        and "ws" in r.getMessage()
        for r in caplog.records
    )


def test_an_unrestricted_tier_keeps_everything(monkeypatch):
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    servers = [{"url": _INSIDE}, {"url": _OUTSIDE}]
    out = _run(filter_egress(
        servers, workspace="ws", kernel=None,
        tier_resolver=_resolver(DEFAULT_UNRESTRICTED_TIERS[0]),
    ))
    assert out == servers


def test_the_unrestricted_set_is_a_parameter(monkeypatch):
    """A deployment whose plans are named differently passes its own set — the
    default is a default, not a rule."""
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    servers = [{"url": _OUTSIDE}]
    assert _run(filter_egress(
        servers, workspace="ws", kernel=None,
        tier_resolver=_resolver("scale"),
    )) == []
    assert _run(filter_egress(
        servers, workspace="ws", kernel=None,
        tier_resolver=_resolver("scale"), unrestricted_tiers=("scale",),
    )) == servers


def test_a_resolver_that_raises_fails_closed(monkeypatch):
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    assert _run(filter_egress(
        [{"url": _OUTSIDE}], workspace="ws", kernel=None, tier_resolver=_boom,
    )) == []


def test_a_resolver_that_raises_is_restricted_even_if_the_failsafe_tier_is_unrestricted(
    monkeypatch,
):
    """The fail-closed path must not be re-derivable from configuration.

    A kernel outage reports :data:`FAILSAFE_TIER` in the log for readability. If
    that name also re-entered the DECISION, an operator who granted that tier
    unrestricted egress would have turned every kernel outage into open egress —
    the one failure the policy exists to prevent, reachable by a plausible
    config. So the refusal is structural, not name-based.
    """
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    assert _run(filter_egress(
        [{"url": _OUTSIDE}], workspace="ws", kernel=None, tier_resolver=_boom,
        unrestricted_tiers=(FAILSAFE_TIER,),
    )) == []


def test_the_default_resolver_is_the_metering_one(monkeypatch):
    """No injection: the policy must reach the SAME tier resolution the meter
    uses. Without this, every other test here could be green against a resolver
    production never calls."""
    import dna_cli._mcp_quota as quota

    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    seen: list = []

    async def fake(_kernel, *, tenant, **_kw):
        seen.append(tenant)
        return DEFAULT_UNRESTRICTED_TIERS[0]

    monkeypatch.setattr(quota, "resolve_metered_tier", fake)
    servers = [{"url": _OUTSIDE}]
    assert _run(filter_egress(servers, workspace="ws-42", kernel=None)) == servers
    assert seen == ["ws-42"]


def test_a_caller_can_keep_its_own_logger_name(monkeypatch, caplog):
    """Two deployables log these refusals; each keeps the logger name its
    operators already grep for."""
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    with caplog.at_level(logging.WARNING):
        _run(filter_egress(
            [{"url": _OUTSIDE}], workspace="ws", kernel=None,
            tier_resolver=_resolver("free"), log=logging.getLogger("door.egress"),
        ))
    assert [r.name for r in caplog.records] == ["door.egress"]


# --- 4a. filter_egress: the flat-declaration shape -------------------------


@pytest.mark.parametrize("servers", [None, [], ()])
def test_no_declarations_is_no_destinations(servers):
    assert _run(filter_egress(
        servers, workspace="ws", kernel=None, tier_resolver=_boom,
    )) == []


def test_an_entry_without_a_string_url_passes_through(monkeypatch):
    """A malformed declaration is somebody else's validation error.

    This policy has nothing to say about an entry that declares no URL, and
    eating it here would hide the real defect behind a security-shaped silence.
    """
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    weird = [{"no_url": 1}, {"url": 42}, "not-a-dict"]
    assert _run(filter_egress(
        list(weird), workspace="ws", kernel=None, tier_resolver=_resolver("free"),
    )) == weird


def test_a_malformed_entry_alone_does_not_even_resolve_the_tier(monkeypatch):
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    calls: list = []
    _run(filter_egress(
        [{"no_url": 1}], workspace="ws", kernel=None,
        tier_resolver=_resolver("free", calls=calls),
    ))
    assert calls == []


# --- 4b. partition_egress: the all-or-nothing shape ------------------------


class _Declared:
    """Stand-in for a declared server carrying TWO destinations: the instance
    that describes it and the base URL its calls actually leave for."""

    def __init__(self, name, url, base_url=None):
        self.name = name
        self.url = url
        self.base_url = base_url

    def __repr__(self):  # pragma: no cover — assertion readability only
        return f"_Declared({self.name!r})"


def _urls(item):
    return [item.url] + ([item.base_url] if item.base_url else [])


def test_partition_is_all_or_nothing_across_an_items_destinations(monkeypatch):
    """THE hole this shape exists to close: an instance fetched from an
    allowlisted host whose calls leave for another host is not half-safe."""
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    half = _Declared("half", url=_INSIDE, base_url=_OUTSIDE)
    whole = _Declared("whole", url=_INSIDE, base_url=_PREFIX + "/api")
    ok, refused = _run(partition_egress(
        [half, whole], urls=_urls, workspace="ws", kernel=None,
        tier_resolver=_resolver("free"),
    ))
    assert ok == [whole]
    assert refused == [half]


def test_partition_resolves_the_tier_once_for_the_whole_batch(monkeypatch):
    """N declarations must not be N plan lookups — the mounter runs this over
    every server a workspace declared."""
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    calls: list = []
    items = [_Declared(f"s{i}", url=_OUTSIDE) for i in range(5)]
    ok, refused = _run(partition_egress(
        items, urls=_urls, workspace="ws", kernel=None,
        tier_resolver=_resolver("free", calls=calls),
    ))
    assert (ok, refused) == ([], items)
    assert calls == ["ws"]


def test_partition_never_resolves_when_everything_is_inside(monkeypatch):
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    calls: list = []
    items = [_Declared("a", url=_INSIDE, base_url=_PREFIX + "/api")]
    ok, refused = _run(partition_egress(
        items, urls=_urls, workspace="ws", kernel=None,
        tier_resolver=_resolver("free", calls=calls),
    ))
    assert (ok, refused) == (items, [])
    assert calls == []


def test_partition_lets_an_unrestricted_tier_through_whole(monkeypatch):
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    items = [_Declared("a", url=_OUTSIDE, base_url=_OUTSIDE)]
    ok, refused = _run(partition_egress(
        items, urls=_urls, workspace="ws", kernel=None,
        tier_resolver=_resolver(DEFAULT_UNRESTRICTED_TIERS[0]),
    ))
    assert (ok, refused) == (items, [])


def test_partition_fails_closed_when_the_resolver_raises(monkeypatch):
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    items = [_Declared("a", url=_OUTSIDE)]
    ok, refused = _run(partition_egress(
        items, urls=_urls, workspace="ws", kernel=None, tier_resolver=_boom,
    ))
    assert (ok, refused) == ([], items)


def test_partition_of_nothing_is_two_empties():
    assert _run(partition_egress(
        [], urls=_urls, workspace="ws", kernel=None, tier_resolver=_boom,
    )) == ([], [])


def test_partition_allows_an_item_with_no_destinations(monkeypatch):
    """Nothing to refuse. The symmetric case of the malformed declaration in
    :func:`filter_egress` — refusing here would invent a policy about a shape
    the policy does not describe."""
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    item = _Declared("empty", url=None)
    ok, refused = _run(partition_egress(
        [item], urls=lambda i: [u for u in _urls(i) if u], workspace="ws",
        kernel=None, tier_resolver=_resolver("free"),
    ))
    assert (ok, refused) == ([item], [])


def test_partition_ignores_non_string_destinations(monkeypatch):
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    item = _Declared("odd", url=_INSIDE)
    ok, refused = _run(partition_egress(
        [item], urls=lambda i: [i.url, 42, None], workspace="ws", kernel=None,
        tier_resolver=_resolver("free"),
    ))
    assert (ok, refused) == ([item], [])


def test_partition_logs_every_refused_destination(monkeypatch, caplog):
    monkeypatch.setenv(ALLOWLIST_ENV, _PREFIX)
    item = _Declared("two", url=_OUTSIDE, base_url="https://third.example/api")
    with caplog.at_level(logging.WARNING):
        _run(partition_egress(
            [item], urls=_urls, workspace="ws", kernel=None,
            tier_resolver=_resolver("free"),
        ))
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert _OUTSIDE in logged and "https://third.example/api" in logged


# --- the two shapes must not disagree --------------------------------------


@pytest.mark.parametrize("allow,tier,urls", [
    (_PREFIX, "free", [_INSIDE]),
    (_PREFIX, "free", [_OUTSIDE]),
    (_PREFIX, DEFAULT_UNRESTRICTED_TIERS[0], [_OUTSIDE]),
    (_PREFIX, "free", ["https://mcp.example.test.attacker.invalid/mcp"]),
    ("", "free", [_INSIDE]),
    ("", DEFAULT_UNRESTRICTED_TIERS[0], [_OUTSIDE]),
    ("https://a.example,https://b.example", "free",
     ["https://a.example/x", "https://b.example/y", "https://c.example/z"]),
    (_PREFIX, "free", [f"  {_INSIDE}"]),
])
def test_the_two_shapes_decide_the_same_for_single_destination_items(
    monkeypatch, allow, tier, urls,
):
    """One destination per item is where the two shapes overlap completely — so
    there they must agree exactly. This is the assertion that keeps a fix
    applied to one entry point from leaving the other behind, which is the
    original defect that unified this policy in the first place."""
    monkeypatch.setenv(ALLOWLIST_ENV, allow)

    flat = _run(filter_egress(
        [{"url": u} for u in urls], workspace="ws", kernel=None,
        tier_resolver=_resolver(tier),
    ))
    items = [_Declared(u, url=u) for u in urls]
    kept, _ = _run(partition_egress(
        items, urls=_urls, workspace="ws", kernel=None,
        tier_resolver=_resolver(tier),
    ))

    assert [s["url"] for s in flat] == [i.url for i in kept]
