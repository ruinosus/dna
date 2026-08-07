"""i-134 — the MARGIN BREAKER: a cost cutout for the operator, not a sold limit.

## The defect, measured

``calls_per_day`` limits FREQUENCY, not cost. Pro admits 10.000 calls/day —
~300.000/month — and at the token prices read from the Azure Retail Prices API
that ceiling accommodates **US$ 6.000 to 19.500/month** of model spend against
**US$ 27,86** of net revenue: 215x to 700x. No fraud is required; heavy but
entirely legitimate use with long prompts is enough. The environment's floor is
~US$ 88/month, so four Pro accounts pay for the server and one heavy account
undoes all four.

## The distinction every assertion here is protecting

A **sold limit** is a promise to the customer: it goes on a price page, into a
contract, into what the buyer expects. A **breaker** is what stops the house
burning down while the right sold limit does not exist yet — and the pricing
decision (i-112) belongs to the founder and has not been made. If the code, the
message or the Kind ever reads as *"we sell N calls per month"*, the breaker has
become the thing it was built to avoid; ``test_the_cutout_never_surfaces_as_a
_plan_feature`` and ``test_the_refusal_reads_as_a_fuse_not_as_an_allowance``
are the two that fail when it does.

## Why it counts CALLS and not TOKENS

Measured 07/08/2026, and the measurement is the design. The money is spent by
model inference; the only token count that exists anywhere in this codebase is
``dna.runtime.telemetry.TurnRecorder``, reading OpenInference LLM spans at the
END of a turn, inside the copilot PROCESS, handing the total to a host-supplied
sink. ``enforce_plan`` — the one gate both faces and the A2A door run — is a
different process metering a different event (one tool call, not one turn) and
receives no token count at all. The only feed that could be built is the
``dna_turn`` one the pricing research already disqualified: it drops under
pressure, swallows its own exceptions by design, records nothing without a
pool, and vanishes by CASCADE with the thread.

For an invoice, undercounting loses money. For a breaker, undercounting means
it never trips — **and a breaker that does not trip is indistinguishable from
no breaker.** So the fuse is built on ``dna_quota_counters``, the one meter this
house built to decide with, and it bounds worst-case cost by bounding served
calls, which is the only quantity the gate can count exactly.

## The two mutants these tests exist to kill

1. **delete the breaker** — remove the ``enforce_margin_breaker`` call from
   ``enforce_quota`` and ``test_the_breaker_is_wired_into_the_metered_path``
   plus the whole "trips" group go red. It is checked through ``enforce_quota``
   and through the MCP + REST faces, not only against the function, because a
   gate nobody calls is the defect this repo has catalogued three times as
   *"capacidade existe, porta não"*.
2. **let an unreadable counter through** — return ``0`` (or skip the check)
   when the store raises or cannot answer, and the ``fail-safe`` group goes
   red. Zero reads as "well under the ceiling", which is the confident lie the
   fail-safe refuses; ``DNA_QUOTA_REQUIRE_TIERS`` set the precedent by
   propagating a registry failure "so the metered call fails instead of the
   billing", and this follows it.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import pathlib
import shutil

import pytest

from dna_cli import _mcp_quota as Q


# ── the caps are DATA: every number below is read from a plan spec ──────────


def _caps(*, cutout: int | None, window: int | None = None,
          calls_per_day: int | None = None, rate: int | None = None) -> dict:
    """A ``PricingPlan`` spec fragment. The breaker's number lives HERE, never
    in the code under test — the same contract ``calls_per_day`` has had since
    the enforcer was written."""
    caps: dict = {"feature_families": ["definitions"]}
    if cutout is not None:
        caps[Q.MARGIN_BREAKER_CAP_FIELD] = cutout
    if window is not None:
        caps[Q.MARGIN_BREAKER_WINDOW_FIELD] = window
    if calls_per_day is not None:
        caps["calls_per_day"] = calls_per_day
    if rate is not None:
        caps["rate_per_sec"] = rate
    return caps


class _Store(Q.InProcQuotaStore):
    """The in-process store with a settable window answer.

    Subclasses the real one rather than faking the port: everything the tests
    do NOT override (the daily counter, ``calls_on``, the i-050 conditional
    increment) is then the production code, so an assertion about "the denied
    call was not counted" is measuring the real counter and not a double's
    opinion of it."""

    def __init__(self, window_calls: int = 0):
        super().__init__()
        self.window_calls = window_calls
        self.window_reads: list[tuple[str, int]] = []

    def calls_in_window(self, tenant: str, days: int) -> int:
        self.window_reads.append((tenant, days))
        return self.window_calls


class _BlindStore(Q.InProcQuotaStore):
    """A store whose window read FAILS — the outage case."""

    def calls_in_window(self, tenant: str, days: int) -> int:
        raise RuntimeError("counters table unreachable")


class _OldStore:
    """A ``QuotaStore`` from before the window read existed — or a host's own.

    Satisfies every method the daily cap needs and NONE of the breaker's. It is
    the shape that makes the second mutant survive if the enforcer treats a
    missing method as "no fuse declared" instead of "cannot decide"."""

    def __init__(self):
        self._inner = Q.InProcQuotaStore()

    def incr_day(self, key):  # pragma: no cover - not reached in these tests
        return self._inner.incr_day(key)

    def try_incr_day(self, key, cap):
        return self._inner.try_incr_day(key, cap)

    def note_call(self, key):
        return self._inner.note_call(key)

    def rate_count(self, key, window_s):
        return self._inner.rate_count(key, window_s)

    def calls_on(self, tenant, day=None):
        return self._inner.calls_on(tenant, day)


# ── it TRIPS, and the number comes from the plan ───────────────────────────


def test_under_the_cutout_the_call_is_served():
    store = _Store(window_calls=9)
    Q.enforce_quota(caps=_caps(cutout=10), tenant="acme", tier="pro",
                    family="definitions", store=store)


def test_at_the_cutout_the_call_is_refused():
    """At, not past: the ceiling is the first value that is too many, exactly
    like ``calls_per_day``'s ``calls >= cap``. An off-by-one here is a breaker
    that serves one call more than the operator authorised, every window."""
    store = _Store(window_calls=10)
    with pytest.raises(Q.MarginBreakerTripped):
        Q.enforce_quota(caps=_caps(cutout=10), tenant="acme", tier="pro",
                        family="definitions", store=store)


def test_the_cutout_number_is_READ_from_the_plan_not_hardcoded():
    """What this assertion would see change: the same usage, two plans, two
    verdicts. A literal anywhere on the path makes both plans agree — which is
    the failure a test that only checks "it refuses at 10" cannot see."""
    store = _Store(window_calls=40)
    Q.enforce_quota(caps=_caps(cutout=50), tenant="acme", tier="pro",
                    family="definitions", store=store)
    with pytest.raises(Q.MarginBreakerTripped):
        Q.enforce_quota(caps=_caps(cutout=5), tenant="acme", tier="pro",
                        family="definitions", store=store)


def test_the_window_is_READ_from_the_plan_and_reaches_the_store():
    """The horizon is data too, and it must arrive at the counter — a window
    the enforcer reads and never passes on is a knob that does nothing."""
    store = _Store(window_calls=0)
    Q.enforce_quota(caps=_caps(cutout=10, window=7), tenant="acme", tier="pro",
                    family="definitions", store=store)
    assert store.window_reads == [("acme", 7)]


def test_a_plan_without_a_window_gets_the_documented_default():
    store = _Store(window_calls=0)
    Q.enforce_quota(caps=_caps(cutout=10), tenant="acme", tier="pro",
                    family="definitions", store=store)
    assert store.window_reads == [("acme", Q.DEFAULT_MARGIN_BREAKER_WINDOW_DAYS)]


@pytest.mark.parametrize("bad", [0, -1, "many", None])
def test_a_nonsense_window_falls_back_instead_of_disabling_the_fuse(bad):
    """``days <= 0`` makes the window read count nothing, i.e. a breaker that
    never trips. A typo in a YAML must not silently be that."""
    assert Q.margin_breaker_window_days(
        {Q.MARGIN_BREAKER_WINDOW_FIELD: bad}
    ) == Q.DEFAULT_MARGIN_BREAKER_WINDOW_DAYS


@pytest.mark.parametrize("bad", ["lots", "", [10]])
def test_a_nonsense_CEILING_refuses_rather_than_serving_uncapped(bad):
    """The other half of the same typo. An unreadable ceiling is not "no
    ceiling": somebody typed a number into a plan and meant a fuse, and
    falling through would serve uncapped on a mistake — which is the fail-open
    this gate exists to refuse. It is the outage answer, not a denial."""
    store = _Store(window_calls=0)
    with pytest.raises(Q.MarginBreakerUnreadable):
        Q.enforce_quota(caps=_caps(cutout=bad), tenant="acme", tier="pro",
                        family="definitions", store=store)


# ── it is OFF unless a plan declares it (the OSS invariant, and the default) ─


def test_no_cutout_declared_means_no_breaker_and_no_counter_read():
    """The default. Every plan written before i-134 behaves exactly as before,
    and the store is not even asked — so declaring the field is the whole
    opt-in and there is no env flag to remember."""
    store = _Store(window_calls=10**9)
    Q.enforce_quota(caps=_caps(cutout=None), tenant="acme", tier="pro",
                    family="definitions", store=store)
    assert store.window_reads == []


def test_empty_caps_are_untouched_the_oss_self_host_path():
    """An unconfigured / OSS source enforces nothing — mirrors every other gate
    in this module, and puts the self-host structurally out of reach."""
    store = _Store(window_calls=10**9)
    Q.enforce_quota(caps={}, tenant=None, tier="free",
                    family="definitions", store=store)
    assert store.window_reads == []


# ── it costs NOTHING to be refused (i-050 / i-055 inherited) ────────────────


def test_a_call_the_breaker_refuses_never_reaches_the_billed_counter():
    """The invariant the ORDERING exists for. ``try_incr_day`` is the counter
    the overage job bills from; a fuse checked after it would bill a call the
    fuse then refused. Move ``enforce_margin_breaker`` below the daily cap in
    ``enforce_quota`` and this goes red."""
    store = _Store(window_calls=10)
    with pytest.raises(Q.MarginBreakerTripped):
        Q.enforce_quota(caps=_caps(cutout=10, calls_per_day=1000),
                        tenant="acme", tier="pro", family="definitions",
                        store=store)
    assert store.calls_on("acme") == 0


def test_a_call_the_breaker_refuses_never_extends_the_rate_window():
    """The i-055 twin: the rate window records what the tenant SPENT, and a
    refused call spent nothing. Move the breaker below the rate gate and the
    refusal starts throttling a tenant for a call it never got."""
    store = _Store(window_calls=10)
    with pytest.raises(Q.MarginBreakerTripped):
        Q.enforce_quota(caps=_caps(cutout=10, rate=5), tenant="acme",
                        tier="pro", family="definitions", store=store)
    assert store.rate_count(Q.quota_key("acme", "pro"), 1.0) == 0


def test_a_locked_family_is_still_refused_before_the_breaker_reads_anything():
    """Order is family → breaker: a family the plan does not unlock costs no
    counter read, exactly as it costs no quota."""
    store = _Store(window_calls=10**9)
    caps = _caps(cutout=1)
    caps["feature_families"] = ["sdlc"]
    with pytest.raises(Q.FeatureNotInPlanError):
        Q.enforce_quota(caps=caps, tenant="acme", tier="pro",
                        family="definitions", store=store)
    assert store.window_reads == []


# ── FAIL-SAFE, not fail-open (mutant #2) ───────────────────────────────────


def test_an_unreadable_counter_REFUSES_the_call():
    """The mutant: swallow the read error, serve the call. A breaker that
    cannot tell whether it is tripped and lets the call through is
    indistinguishable from no breaker — which is the entire defect of i-134."""
    with pytest.raises(Q.MarginBreakerUnreadable):
        Q.enforce_quota(caps=_caps(cutout=10), tenant="acme", tier="pro",
                        family="definitions", store=_BlindStore())


def test_a_store_that_cannot_answer_the_question_REFUSES_the_call():
    """A missing method is treated exactly like a failing one, and that is the
    point: a host injects its own ``QuotaStore``, and a store silently lacking
    the window read would disable the fuse with nothing red anywhere — the same
    outcome as deleting it, arrived at by omission."""
    with pytest.raises(Q.MarginBreakerUnreadable):
        Q.enforce_quota(caps=_caps(cutout=10), tenant="acme", tier="pro",
                        family="definitions", store=_OldStore())


def test_the_failsafe_refusal_counts_nothing_either():
    store = _BlindStore()
    with pytest.raises(Q.MarginBreakerUnreadable):
        Q.enforce_quota(caps=_caps(cutout=10, calls_per_day=1000),
                        tenant="acme", tier="pro", family="definitions",
                        store=store)
    assert store.calls_on("acme") == 0


def test_the_failsafe_is_not_a_plan_denial():
    """503, never 403/429. The caller did nothing wrong and has nothing to fix
    — the deployment cannot decide. Told it was denied, an operator goes
    looking for an entitlement instead of for a database."""
    assert not issubclass(Q.MarginBreakerUnreadable, PermissionError)
    assert issubclass(Q.MarginBreakerUnreadable, Q.TierRegistryUnavailableError)


def test_an_unreadable_counter_is_NOT_an_outage_when_no_cutout_is_declared():
    """The fail-safe cannot leak into deployments that never armed the fuse —
    a broken window read on a plan with no ceiling must change nothing."""
    Q.enforce_quota(caps=_caps(cutout=None), tenant="acme", tier="pro",
                    family="definitions", store=_BlindStore())


# ── the refusal SAYS what happened, and does not sell anything ─────────────


def test_the_refusal_reads_as_a_fuse_not_as_an_allowance():
    """⚠️ The assertion that protects the distinction in the only place the
    CUSTOMER ever sees it. A message like "your plan includes N calls" turns a
    protection ceiling into a commercial promise nobody agreed to — which is
    exactly what i-134 said must not happen, and it would happen in a sentence,
    not in a schema."""
    store = _Store(window_calls=10)
    with pytest.raises(Q.MarginBreakerTripped) as exc:
        Q.enforce_quota(caps=_caps(cutout=10), tenant="acme", tier="pro",
                        family="definitions", store=store)
    message = str(exc.value).lower()
    # What happened, in the tenant's own numbers.
    assert "10" in message and "acme" in message
    # What to do about it — and it is NOT "buy more", because there is nothing
    # to buy: the ceiling is the operator's, not a shelf item.
    assert "operator" in message
    # It DISCLAIMS the commercial reading out loud rather than merely avoiding
    # it. A message that is silent about what it is gets read as a plan limit
    # by default, because every other refusal on this path is one.
    assert "not part of what the plan sells" in message
    assert "fuse" in message
    # And it never makes the affirmative promise. These are the phrasings a
    # sold-allowance denial uses; none of them may appear in a fuse.
    for sold in ("your plan includes", "included in your plan",
                 "upgrade the plan", "upgrade your plan", "quota exhausted"):
        assert sold not in message, sold


def test_the_refusal_says_the_denial_cost_nothing():
    store = _Store(window_calls=10)
    with pytest.raises(Q.MarginBreakerTripped) as exc:
        Q.enforce_quota(caps=_caps(cutout=10), tenant="acme", tier="pro",
                        family="definitions", store=store)
    assert "nothing was counted" in str(exc.value).lower()


def test_the_failsafe_message_names_the_unknown_rather_than_implying_a_denial():
    with pytest.raises(Q.MarginBreakerUnreadable) as exc:
        Q.enforce_quota(caps=_caps(cutout=10), tenant="acme", tier="pro",
                        family="definitions", store=_BlindStore())
    assert "unknown" in str(exc.value).lower()


# ── the window read itself, on the store that hosting actually uses ────────


def test_inproc_window_sums_only_days_inside_the_horizon():
    """Direct on the real store: yesterday counts, 40 days ago does not."""
    store = Q.InProcQuotaStore()
    today = _dt.datetime.now(_dt.UTC).date()
    key = Q.quota_key("acme", "pro")
    store._day_counts[(store._day_label(today), key)] = 3
    store._day_counts[(store._day_label(today - _dt.timedelta(days=1)), key)] = 4
    store._day_counts[(store._day_label(today - _dt.timedelta(days=40)), key)] = 99
    assert store.calls_in_window("acme", 30) == 7


def test_inproc_window_is_correct_across_a_year_boundary():
    """The bucket label is ``YYYY-DDD`` and comparing two of those as STRINGS
    is right until 31 December: ``'2026-365' < '2027-001'`` holds by accident of
    the prefix, and a 30-day horizon straddling New Year silently becomes a
    365-day one. Pinned by construction rather than by waiting for December."""
    store = Q.InProcQuotaStore()
    assert store._label_day("2026-365") == _dt.date(2026, 12, 31)
    assert store._label_day("2027-001") == _dt.date(2027, 1, 1)
    assert store._label_day("not-a-day") is None


def test_inproc_window_sums_across_tiers_like_the_billing_read_does():
    """A tenant that changed plan mid-window owns a bucket per tier, and the
    exposure belongs to the TENANT — the same reason ``calls_on`` sums tiers."""
    store = Q.InProcQuotaStore()
    today = store._day_label(_dt.datetime.now(_dt.UTC).date())
    store._day_counts[(today, Q.quota_key("acme", "free"))] = 2
    store._day_counts[(today, Q.quota_key("acme", "pro"))] = 5
    store._day_counts[(today, Q.quota_key("other", "pro"))] = 900
    assert store.calls_in_window("acme", 30) == 7


def test_inproc_window_counts_what_the_daily_counter_actually_wrote():
    """End to end on one store: the fuse reads the SAME rows the cap advances,
    which is why there is no second counter to drift."""
    store = Q.InProcQuotaStore()
    for _ in range(4):
        store.try_incr_day(Q.quota_key("acme", "pro"), 100)
    assert store.calls_in_window("acme", 30) == 4
    assert store.calls_on("acme") == 4


def test_an_empty_horizon_counts_nothing():
    assert Q.InProcQuotaStore().calls_in_window("acme", 0) == 0


# ── the cutout is not a product (the distinction, in the Kind) ─────────────


def _pricing_plan_spec() -> dict:
    import yaml

    root = pathlib.Path(Q.__file__).resolve().parents[3]
    path = (root / "packages" / "sdk-py" / "dna" / "extensions" / "cloud"
            / "kinds" / "pricing-plan.kind.yaml")
    return yaml.safe_load(path.read_text())["spec"]


def test_the_cutout_is_declared_on_the_plan_Kind():
    """The enforcer reads it from the plan, so the plan has to be able to carry
    it — and the two halves must agree on the SPELLING. A field named one way
    in the schema and read another way is a fuse nobody can arm."""
    properties = _pricing_plan_spec()["schema"]["properties"]
    assert Q.MARGIN_BREAKER_CAP_FIELD in properties
    assert Q.MARGIN_BREAKER_WINDOW_FIELD in properties


def test_the_cutout_never_surfaces_as_a_plan_feature():
    """⚠️ The distinction, pinned in the Kind. ``summary`` is what a portal
    renders for a plan — the price-page projection — and a fuse must not be in
    it. Add it there and this goes red, which is the moment somebody would
    otherwise have turned a protection ceiling into a number the product
    appears to sell, while the pricing decision (i-112) is still open."""
    summary = _pricing_plan_spec()["summary"]
    assert Q.MARGIN_BREAKER_CAP_FIELD not in summary
    assert Q.MARGIN_BREAKER_WINDOW_FIELD not in summary


def test_the_schema_says_out_loud_that_it_is_not_a_sold_limit():
    """Cheap, and it is the sentence a future reader meets FIRST. The whole
    risk this issue named is that the next person reads the field and concludes
    "so we sell calls per month"."""
    prop = _pricing_plan_spec()["schema"]["properties"][Q.MARGIN_BREAKER_CAP_FIELD]
    text = prop["description"].lower()
    assert "not a sold limit" in text
    assert "not a pricing axis" in text


def test_the_cutout_is_off_by_default_in_the_schema():
    """No number ships. The values are the founder's decision (i-112) and this
    change deliberately does not make one — a default other than null would be
    a pricing decision smuggled in as a schema default."""
    properties = _pricing_plan_spec()["schema"]["properties"]
    for field in (Q.MARGIN_BREAKER_CAP_FIELD, Q.MARGIN_BREAKER_WINDOW_FIELD):
        assert properties[field].get("default") is None
        assert "null" in properties[field]["type"]
    assert Q.MARGIN_BREAKER_CAP_FIELD not in _pricing_plan_spec()["schema"]["required"]


# ── the breaker is WIRED: it runs on the path a real call takes (mutant #1) ─


_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"


def _tier_doc(tier_id: str, **spec) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/cloud/v1",
        "kind": "PricingPlan",
        "metadata": {"name": tier_id},
        "spec": {
            "tier_id": tier_id, "display_name": tier_id.title(),
            "price_usd_month": 0, "calls_per_day": 1000, "rate_per_sec": 1000,
            "feature_families": ["definitions", "sdlc", "memory"],
            "memory_mode": "write", "sdlc_mode": "write",
            "definitions_mode": "write", "aliases": [], **spec,
        },
    }


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_QUOTA_DSN", raising=False)
    monkeypatch.delenv(Q.REQUIRE_TIERS_ENV, raising=False)
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    return dst


def _seed(dna_dir, *docs):
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        for kind, name, doc in docs:
            await live.kernel.write_instance("_lib", kind, name, doc)

    asyncio.run(go())


def test_the_breaker_is_wired_into_the_metered_path(dna_dir):
    """MUTANT #1, killed through the SHARED CORE rather than the function.

    Delete the ``enforce_margin_breaker`` call from ``enforce_quota`` and this
    goes red — which the unit tests above would NOT, because they would keep
    proving that a function nobody calls behaves correctly. This repo has
    catalogued that exact defect three times as *"capacidade existe, porta
    não"*: a gate built, tested, green, and reachable by no request.
    """
    _seed(dna_dir, ("PricingPlan", "free",
                    _tier_doc("free", **{Q.MARGIN_BREAKER_CAP_FIELD: 2})))
    store = Q.InProcQuotaStore()

    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        served = 0
        for _ in range(5):
            try:
                await Q.enforce_plan(live.kernel, tenant="acme",
                                     family="definitions", store=store,
                                     claimed_tier="free")
            except Q.MarginBreakerTripped:
                return served
            served += 1
        return served

    # Exactly the plan's ceiling is served; the next call opens the fuse.
    assert asyncio.run(go()) == 2
    # And the tenant's billed counter carries the two SERVED calls only.
    assert store.calls_on("acme") == 2


def test_the_breaker_reaches_the_REST_face_as_a_429(dna_dir):
    """The other door, because the policy is shared and the mapping is not.
    429 with the refusal's own sentence, via ``OverQuotaError`` — the base the
    face has always named, which is why relaying works with no tuple widened."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from dna_cli import _rest_api as R

    _seed(dna_dir, ("PricingPlan", "free",
                    _tier_doc("free", **{Q.MARGIN_BREAKER_CAP_FIELD: 0})))
    app = R.build_app(base_dir=str(dna_dir), scope=_SCOPE, auth="token",
                      token="portal-shared-token-mvp",
                      quota_store=Q.InProcQuotaStore())
    with TestClient(app) as client:
        r = client.post(
            "/v1/memories", params={"scope": _SCOPE, "tenant": "acme"},
            json={"summary": "a write the fuse should stop"},
            headers={"Authorization": "Bearer portal-shared-token-mvp"},
        )
    assert r.status_code == 429, r.text
    assert "cutout" in r.json()["detail"].lower()


def test_the_failsafe_reaches_the_REST_face_as_a_503(dna_dir):
    """And the outage half maps to *service unavailable*, never to a denial —
    inherited from ``TierRegistryUnavailableError``'s mapping, which predates
    the breaker."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from dna_cli import _rest_api as R

    _seed(dna_dir, ("PricingPlan", "free",
                    _tier_doc("free", **{Q.MARGIN_BREAKER_CAP_FIELD: 10})))
    app = R.build_app(base_dir=str(dna_dir), scope=_SCOPE, auth="token",
                      token="portal-shared-token-mvp",
                      quota_store=_BlindStore())
    with TestClient(app) as client:
        r = client.post(
            "/v1/memories", params={"scope": _SCOPE, "tenant": "acme"},
            json={"summary": "a write during a counter outage"},
            headers={"Authorization": "Bearer portal-shared-token-mvp"},
        )
    assert r.status_code == 503, r.text
