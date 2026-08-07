"""Approving a Kind has to TAKE EFFECT — the rebuild trigger (i-090).

The mechanism was already right and the product was still broken. Registration
is what confers schema enforcement and storage routing, and registration happens
**inside a Manifest Instance build**; the approval write correctly invalidates
the scope's base MI so the *next* build is fresh. Nothing scheduled that next
build. It arrived only when somebody happened to call a ``definitions``-family
route (``list_agents`` / ``compose_prompt`` / ``list_tools`` / ``genome_view``)
for that scope, in that process — and the instance routes (``write_instance``,
``list_instances``, ``get_instance``, ``list_kinds``) never do: they read the
Kind registry directly.

So the measured sequence a human performs — approve, then immediately use the
Kind — answered ``UnknownKindError: Kind 'Deal' is not registered on this
source``, and the moment approval started to hold was indeterminate and
different on every replica. Revocation had exactly the same window, which is the
dangerous half: it made a withdrawal SLOW TO CLOSE the door, the loosening that
``i-085``/#261 exists to prevent.

Two layers are under test here, and they are deliberately proved apart:

* **Layer 1 — re-register in the act.** ``approve_kind_impl`` /
  ``revoke_kind_impl`` rebuild their scope's registry before returning, so the
  replica that served the act honours it on the very next call. It closes the
  case a human hits first and closes NOTHING on the sibling replicas.
* **Layer 2 — ``LiveDna.ensure_kinds`` behind a short TTL at the Kind-resolution
  seam of the instance routes.** This is what closes every replica, and it turns
  "indeterminate" into a number: at most ``kind_refresh_ttl`` seconds.

**The trap this file is written against.** A fixture that builds a fresh kernel
between the approval and the write passes with NEITHER layer implemented — a new
kernel registers the approved Kind on its first build no matter what. Every test
below therefore holds ONE ``LiveDna`` (hence one ``Kernel``) across the whole
sequence, and ``test_the_fixture_would_fail_without_a_trigger`` pins that
property directly so the guarantee cannot rot into a fresh-kernel test later.

**Which test proves which layer** — measured by disabling each layer in turn,
because "there are tests for both" is not the same claim as "each layer is
independently load-bearing":

* with **Layer 2 disabled**, five tests fail — every one of the sibling-replica
  and window tests, and no other;
* with **Layer 1 disabled**, five tests fail — the revocation-immediacy pair,
  ``test_layer_one_does_not_depend_on_the_ttl_seam``, the fail-soft test and the
  refresh-count test.

The three that pass under either (approve-then-write, schema enforced, catalog)
are product acceptance rather than layer isolation: they assert the sequence a
human performs, and either mechanism satisfying it is the correct outcome.
"""
from __future__ import annotations

import asyncio
import time

from pathlib import Path
from typing import Any

import pytest
import yaml

from dna._yaml import safe_load
from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application import live as live_mod
from dna.application.instances import (
    UnknownKindError,
    get_instance_impl,
    list_kinds_impl,
    write_instance_impl,
)
from dna.application.kind_authoring import (
    approve_kind_impl,
    author_kind_impl,
    revoke_kind_impl,
)
from dna.application.live import LiveDna
from dna.kernel import Kernel
from dna.kernel.errors import RevokedKindWrite

_SCOPE = "board"
_TENANT = "ws-acme"
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"titulo": {"type": "string"}},
    "required": ["titulo"],
}


def _write_yaml(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(doc, default_flow_style=False))


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    base = tmp_path / ".dna"
    _write_yaml(base / _SCOPE / "Genome.yaml", {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": _SCOPE}, "spec": {},
    })
    _write_yaml(base / "_lib" / "manifest.yaml", {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": "_lib"}, "spec": {},
    })
    return base


def _replica(base: Path, *, ttl: float | None = None) -> LiveDna:
    """ONE replica — one process, one kernel, held for the whole sequence.

    Two calls over the same ``base`` are two SIBLING replicas sharing a store,
    which is what a multi-replica deployment is."""
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    live = LiveDna(base_scope=_SCOPE, kernel=k, provider=None,
                   vendor_workspace=None)
    if ttl is not None:
        live.kind_refresh_ttl = ttl
    return live


async def _serving(live: LiveDna) -> None:
    """Put the replica in the state a running pod is in: the registry for this
    scope has already been built once, WITHOUT the Kind.

    Skipping this would let a first-ever build inside the write path mask the
    defect — the reproduction has to start from a warm process."""
    await live.mi(_SCOPE)


async def _authored(live: LiveDna, *, now: str = "2026-07-28T10:00:00Z") -> str:
    res = await author_kind_impl(
        live, kind="Deal", schema=_SCHEMA, tenant=_TENANT, now=now,
        actor="author@acme.example",
    )
    return str(res["name"])


async def _approve(live: LiveDna, *, now: str = "2026-07-28T11:00:00Z") -> Any:
    return await approve_kind_impl(
        live, kind="Deal", tenant=_TENANT, actor="reviewer@acme.example",
        now=now,
    )


async def _revoke(live: LiveDna, *, now: str = "2026-07-28T12:00:00Z") -> Any:
    return await revoke_kind_impl(
        live, kind="Deal", tenant=_TENANT, actor="reviewer@acme.example",
        now=now,
    )


async def _write(live: LiveDna, name: str, titulo: str = "primeiro") -> Any:
    return await write_instance_impl(
        live, kind="Deal", name=name, spec={"titulo": titulo},
        tenant=_TENANT,
    )


def _stored_spec(base: Path, doc_name: str) -> dict[str, Any]:
    raw = safe_load((base / _SCOPE / "kinds" / doc_name / "KIND.yaml").read_text())
    return (raw or {}).get("spec") or {}


def _count_refreshes(
    live: LiveDna, monkeypatch: pytest.MonkeyPatch, *, delay: bool = False,
) -> dict[str, int]:
    """Count the SEAM's own store reads — ``instance_async(..., lazy=True)``.

    Deliberately narrower than "every MI build". A write already triggers other
    builds that have nothing to do with this change (the layer-policy check goes
    through the kernel's base-MI cache, and that cache is neither TTL'd nor
    single-flighted — pre-existing behaviour, measured, untouched here).
    Counting those too would make this assertion a statement about the kernel's
    caching rather than about the seam, and it would have been satisfied by
    accident. The bootstrap-slice rebuild is the thing this change introduces
    and the thing whose cost the SLA is quoted against, so it is the thing
    counted.

    ``delay=True`` inserts a yield inside the refresh so a racing caller can
    enter it — without one, a single-flight assertion can pass on a refresh that
    simply never suspended."""
    calls = {"n": 0}
    original = live.kernel.instance_async

    async def counting(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("lazy") is True:
            calls["n"] += 1
            if delay:
                await asyncio.sleep(0)
        return await original(*args, **kwargs)

    monkeypatch.setattr(live.kernel, "instance_async", counting)
    return calls


# ── the fixture's own honesty ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_fixture_would_fail_without_a_trigger(store: Path):
    """Guard the guard: the sequence must run on ONE kernel.

    This project has shipped tests that passed for the wrong reason. The whole
    weight of this file rests on the approval and the write happening in the
    same process over the same registry, so that fact is asserted rather than
    assumed — and the contrast case is asserted too: a replica BOOTED AFTER the
    approval, whose first Manifest Instance build therefore happens after the
    fact, registers the Kind with no trigger anywhere. That is precisely the
    false green this file exists to avoid; if someone ever "simplifies" the
    fixture into that shape, this test is what says the file stopped measuring
    anything."""
    live = _replica(store)
    await _serving(live)
    kernel_before = live.kernel
    await _authored(live)
    await _approve(live)
    assert live.kernel is kernel_before, (
        "the approval must not have replaced the kernel — if it did, every "
        "assertion in this file is about a fresh registry and proves nothing"
    )

    # The contrast: a replica whose FIRST build happens after the approval
    # needs no trigger at all. This is what a fresh-kernel fixture would be
    # measuring, and it is nothing.
    newborn = _replica(store, ttl=0.0)   # Layer 2 OFF — the boot build is enough.
    await _serving(newborn)
    await _write(newborn, "deal-newborn")


# ── Layer 1: the act re-registers ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_approval_holds_on_the_very_next_write_with_no_rebuild_between(
    store: Path,
):
    """The reproduction, and the fix: author → approve → WRITE, one process.

    Nothing rebuilds the Manifest Instance between the approval and the write.
    Before the fix this raised
    ``UnknownKindError: Kind 'Deal' is not registered on this source``."""
    live = _replica(store)
    await _serving(live)
    await _authored(live)
    await _approve(live)

    out = await _write(live, "deal-1")

    assert out["kind"] == "Deal"
    assert out["created"] is True


@pytest.mark.asyncio
async def test_the_approved_schema_is_enforced_on_that_very_next_write(
    store: Path,
):
    """Registered is not enough — the SCHEMA has to be in force.

    A trigger that made the Kind resolvable without putting its schema behind
    the write would be the worst outcome of the three: the Kind looks approved
    and validates nothing."""
    live = _replica(store)
    await _serving(live)
    await _authored(live)
    await _approve(live)

    with pytest.raises(Exception) as excinfo:
        await write_instance_impl(
            live, kind="Deal", name="deal-bad", spec={"titulo": 123},
            tenant=_TENANT,
        )
    assert "titulo" in str(excinfo.value)


@pytest.mark.asyncio
async def test_the_catalog_lists_the_kind_on_the_very_next_call(store: Path):
    """``list_kinds`` is an instance route too — it reads the registry directly.

    An approval that holds for ``write_instance`` but leaves the catalog saying
    the Kind does not exist is a product that contradicts itself in two
    adjacent calls."""
    live = _replica(store)
    await _serving(live)
    await _authored(live)
    await _approve(live)

    catalog = await list_kinds_impl(live, tenant=_TENANT)
    assert "Deal" in {e["kind"] for e in catalog["kinds"]}


@pytest.mark.asyncio
async def test_revocation_closes_the_door_on_the_very_next_write(store: Path):
    """The dangerous half. A revocation that is slow to take effect keeps
    accepting instances of a Kind the workspace has just withdrawn.

    Same sequence, one process, no rebuild: approve → write (accepted) →
    revoke → write (must be REFUSED)."""
    live = _replica(store)
    await _serving(live)
    await _authored(live)
    await _approve(live)
    await _write(live, "deal-before")

    await _revoke(live)

    with pytest.raises(RevokedKindWrite):
        await _write(live, "deal-after")


@pytest.mark.asyncio
async def test_re_approving_re_opens_the_door_on_the_very_next_write(
    store: Path,
):
    """Reversible in one act, and the trigger must carry that direction too —
    otherwise the fix is a ratchet that only ever tightens."""
    live = _replica(store)
    await _serving(live)
    await _authored(live)
    await _approve(live)
    await _revoke(live)
    with pytest.raises(RevokedKindWrite):
        await _write(live, "deal-during-revocation")

    await _approve(live, now="2026-07-28T13:00:00Z")

    out = await _write(live, "deal-after-reapproval")
    assert out["kind"] == "Deal"


@pytest.mark.asyncio
async def test_layer_one_does_not_depend_on_the_ttl_seam(store: Path):
    """Layer 1 stands ALONE — with the TTL seam disabled the act still holds.

    Proving the two layers apart is the point: if this only passed with
    ``ensure_kinds`` armed, the "~60 ms once per approval" claim would be
    describing work that never happens."""
    live = _replica(store, ttl=0.0)   # Layer 2 OFF for this replica.
    await _serving(live)
    await _authored(live)
    await _approve(live)

    out = await _write(live, "deal-layer1-only")
    assert out["kind"] == "Deal"


# ── Layer 2: the TTL seam, proved WITHOUT the approving call ────────────────


@pytest.mark.asyncio
async def test_a_sibling_replica_that_never_approved_picks_the_kind_up(
    store: Path,
):
    """The gap Layer 1 leaves, closed by Layer 2.

    Replica B is warm (it has served this scope) and it did NOT serve the
    approval — replica A did. Nothing invalidated B, nothing rebuilt B. The
    instance route's own ``ensure_kinds`` is the only thing that can make this
    pass."""
    a = _replica(store)
    b = _replica(store)
    await _serving(a)
    await _serving(b)
    # B is warm AND its refresh clock has already ticked for this scope, so the
    # pass below cannot be a first-ever refresh.
    with pytest.raises(UnknownKindError):
        await _write(b, "deal-too-early")

    await _authored(a)
    await _approve(a)

    b.kind_refresh_ttl = 0.05
    await asyncio.sleep(0.06)
    out = await _write(b, "deal-from-sibling")
    assert out["kind"] == "Deal"


@pytest.mark.asyncio
async def test_the_ttl_is_a_real_window_and_it_is_the_published_sla(
    store: Path, monkeypatch: pytest.MonkeyPatch,
):
    """The number an operator can publish: at most ``kind_refresh_ttl``.

    Inside the window a sibling replica is legitimately still stale — that is
    the SLA, stated honestly rather than implied — and when the window closes
    the refresh fires with no other trigger. The clock is driven rather than
    slept on so the window's two sides are asserted deterministically."""
    now = [1_000.0]
    monkeypatch.setattr(live_mod, "_monotonic", lambda: now[0])

    a = _replica(store, ttl=30.0)
    b = _replica(store, ttl=30.0)
    await _serving(a)
    await _serving(b)
    with pytest.raises(UnknownKindError):
        await _write(b, "deal-t0")     # warms B's refresh clock at t=1000.

    await _authored(a)
    await _approve(a)

    now[0] += 29.0                     # still inside the 30 s window.
    with pytest.raises(UnknownKindError):
        await _write(b, "deal-t29")

    now[0] += 2.0                      # 31 s — the window has closed.
    out = await _write(b, "deal-t31")
    assert out["kind"] == "Deal"


@pytest.mark.asyncio
async def test_the_ttl_seam_closes_a_revocation_on_a_sibling_replica(
    store: Path, monkeypatch: pytest.MonkeyPatch,
):
    """Revocation is the half that must not lag, and it lags on the SIBLINGS
    until Layer 2 fires. Same window, opposite direction."""
    now = [2_000.0]
    monkeypatch.setattr(live_mod, "_monotonic", lambda: now[0])

    a = _replica(store, ttl=30.0)
    b = _replica(store, ttl=30.0)
    await _serving(a)
    await _serving(b)
    await _authored(a)
    await _approve(a)
    now[0] += 31.0
    await _write(b, "deal-b-before")    # B has the Kind, via its own refresh.

    await _revoke(a)

    now[0] += 31.0
    with pytest.raises(RevokedKindWrite):
        await _write(b, "deal-b-after")


@pytest.mark.asyncio
async def test_the_seam_does_not_re_read_the_store_inside_the_window(
    store: Path, monkeypatch: pytest.MonkeyPatch,
):
    """The cost half of the SLA: one bootstrap read per scope per window, not
    one per request. A seam that rebuilt on every instance call would trade a
    product bug for a worse one."""
    now = [3_000.0]
    monkeypatch.setattr(live_mod, "_monotonic", lambda: now[0])

    live = _replica(store, ttl=30.0)
    await _serving(live)
    await _authored(live)
    await _approve(live)

    calls = _count_refreshes(live, monkeypatch)

    for i in range(6):
        await _write(live, f"deal-hot-{i}")
        await get_instance_impl(live, kind="Deal", name=f"deal-hot-{i}",
                                tenant=_TENANT)
    assert calls["n"] == 0, (
        "12 instance calls inside one TTL window rebuilt the registry "
        f"{calls['n']} times — the window is what makes the seam affordable"
    )

    now[0] += 31.0
    await _write(live, "deal-after-window")
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_concurrent_document_calls_single_flight_the_refresh(
    store: Path, monkeypatch: pytest.MonkeyPatch,
):
    """A burst over a cold scope must yield ONE rebuild, not N — otherwise the
    seam becomes a thundering herd at every window boundary and at boot."""
    now = [4_000.0]
    monkeypatch.setattr(live_mod, "_monotonic", lambda: now[0])

    a = _replica(store)
    b = _replica(store, ttl=30.0)
    await _serving(a)
    await _serving(b)
    await _authored(a)
    await _approve(a)

    calls = _count_refreshes(b, monkeypatch, delay=True)

    results = await asyncio.gather(*[
        _write(b, f"deal-burst-{i}") for i in range(8)
    ])
    assert all(r["kind"] == "Deal" for r in results)
    assert calls["n"] == 1, f"{calls['n']} concurrent rebuilds for one scope"


@pytest.mark.asyncio
async def test_a_failed_refresh_never_becomes_a_refusal(store: Path):
    """Fail-SOFT, and deliberately. The seam is a freshness optimisation on a
    path that already worked; a store hiccup during the refresh must leave the
    request to proceed against the registry the replica already has, and the
    next request retries — never turn a readable Kind into an error."""
    live = _replica(store)
    await _serving(live)
    await _authored(live)
    await _approve(live)          # Layer 1 registered it on this replica.

    async def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("store unreachable")

    live.kernel.instance_async = boom          # type: ignore[method-assign]
    live._kinds_refreshed.clear()              # force the seam to try.

    out = await _write(live, "deal-degraded")
    assert out["kind"] == "Deal"


# ── configuration ───────────────────────────────────────────────────────────


def test_the_ttl_is_configurable_by_the_operator(
    monkeypatch: pytest.MonkeyPatch,
):
    """The SLA is a number an operator has to be able to move — shorter for a
    deployment that wants approvals to land faster, ``0`` to switch the seam off
    entirely."""
    monkeypatch.setenv(live_mod.KIND_REFRESH_TTL_ENV, "5")
    assert live_mod.default_kind_refresh_ttl() == 5.0
    monkeypatch.setenv(live_mod.KIND_REFRESH_TTL_ENV, "0")
    assert live_mod.default_kind_refresh_ttl() == 0.0
    monkeypatch.setenv(live_mod.KIND_REFRESH_TTL_ENV, "not-a-number")
    assert live_mod.default_kind_refresh_ttl() == live_mod.KIND_REFRESH_TTL_DEFAULT
    monkeypatch.delenv(live_mod.KIND_REFRESH_TTL_ENV)
    assert live_mod.default_kind_refresh_ttl() == live_mod.KIND_REFRESH_TTL_DEFAULT


def test_the_clock_the_window_is_measured_on_is_monotonic():
    """Wall-clock would make an NTP step either stall the refresh for hours or
    fire it on every request."""
    assert live_mod._monotonic is time.monotonic
