"""Adopt-on-access — the i-058 hardening's core properties.

Production taught the lesson this file encodes: adoption wired ONLY to
provision-owner never ran (the portal's call site was gated on a stale pre-D5
condition), so the founder's workspace lived for hours with no Genome and
``compose_prompt`` found nothing to inherit. The robust trigger is the moment
no navigation path can skip: **when a request resolves a workspace** the faces
call :func:`dna.application.runtime.adopt_workspace_scope_on_access`.

Properties proven here (each one kills a specific mutant):

* a first access over a Genome-less workspace ADOPTS, and the very same call
  sequence already reads the base's definitions (same-call semantics);
* the probe is CACHED: the second access performs ZERO kernel reads and ZERO
  kernel writes (kills the broken-cache mutant — ensure-per-request would
  still be write-idempotent, so the read count is the tripwire);
* a CONCURRENT first burst single-flights to exactly ONE kernel write;
* an operator-authored ``parent_scope`` is never overwritten — not even by a
  fresh process (a cold cache);
* no configured base → NOTHING written (the OSS / self-host baseline);
* the vendor's own scope and a ``personal:`` partition are never touched;
* a FAILED probe is not cached — the next access retries and heals.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application.live import LiveDna
from dna.application.runtime import (
    adopt_workspace_scope_on_access,
    list_agents_impl,
)
from dna.kernel import Kernel

_BASE_SCOPE = "dna-development"
_VENDOR_WS = "ws-vendor00000000000000000"
_WS = "ws-adoptme00000000000000000"


def _doc(kind: str, name: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {"apiVersion": "github.com/ruinosus/dna/v1", "kind": kind,
            "metadata": {"name": name}, "spec": spec}


def _write(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(doc, default_flow_style=False))


@pytest.fixture()
def kernel(tmp_path: Path) -> Kernel:
    base = tmp_path / ".dna"
    # The host's curated base scope, already seeded with one definition.
    _write(base / _BASE_SCOPE / "Genome.yaml", _doc("Genome", _BASE_SCOPE, {}))
    _write(base / _BASE_SCOPE / "agents" / "assistant.yaml",
           _doc("Agent", "assistant", {"instruction": "Curated base agent."}))
    (base / "_lib").mkdir(parents=True)
    return _kernel_over(base)


def _kernel_over(base: Path) -> Kernel:
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    return k


def _live(kernel: Kernel, definitions_base: str | None) -> LiveDna:
    return LiveDna(
        base_scope=_BASE_SCOPE,
        kernel=kernel,
        provider=None,
        vendor_workspace=_VENDOR_WS,
        workspace_definitions_base=definitions_base,
    )


async def _genome_or_none(kernel: Kernel, scope: str) -> dict[str, Any] | None:
    try:
        return await kernel.get_document(scope, "Genome", scope)
    except (FileNotFoundError, ValueError):
        return None


class _Counter:
    """Count the kernel's Genome reads + all writes without changing behavior."""

    def __init__(self, kernel: Kernel) -> None:
        self.reads: list[tuple] = []
        self.writes: list[tuple] = []
        self._orig_get = kernel.get_document
        self._orig_write = kernel.write_document

        async def counting_get(scope, kind, name, *a, **kw):
            if kind == "Genome":
                self.reads.append((scope, kind, name))
            # Force a real suspension point: the filesystem adapter is
            # sync-under-async (it never yields), which would let a LOCKLESS
            # implementation pass the concurrency test by accident — each
            # coroutine would run probe+write to completion before the next
            # started. A Postgres source DOES yield here; simulate that, so
            # the single-flight property is tested against the interleaving
            # that production actually has.
            await asyncio.sleep(0)
            return await self._orig_get(scope, kind, name, *a, **kw)

        async def counting_write(scope, kind, name, *a, **kw):
            self.writes.append((scope, kind, name))
            # The same forced suspension INSIDE the probe's read→write window:
            # this is the interleaving that makes a lockless implementation
            # visibly double-write (every racer reads "no Genome" before any
            # of them lands the write) instead of being saved by the sync
            # filesystem adapter completing each probe atomically.
            await asyncio.sleep(0)
            return await self._orig_write(scope, kind, name, *a, **kw)

        kernel.get_document = counting_get  # type: ignore[method-assign]
        kernel.write_document = counting_write  # type: ignore[method-assign]


# ── the adoption property: access adopts, and the SAME call sees the base ───


@pytest.mark.asyncio
async def test_first_access_adopts_and_the_same_call_sees_the_base(
    kernel: Kernel,
) -> None:
    """A request over a Genome-less workspace adopts on access, and the SAME
    request already lists the base's definitions — the exact production hole
    (compose over ``tenant-ws-…`` finding nothing) closed at the source."""
    live = _live(kernel, _BASE_SCOPE)
    ws_scope = live.default_scope(_WS)
    assert await _genome_or_none(kernel, ws_scope) is None

    # The faces run adopt BEFORE the tool impl — same order here, same call.
    result = await adopt_workspace_scope_on_access(live, _WS)
    listed = await list_agents_impl(live, scope=ws_scope)

    assert result is not None and result["written"] is True
    assert result["parent_scope"] == _BASE_SCOPE
    assert "assistant" in {a["name"] for a in listed["agents"]}
    genome = await kernel.get_document(ws_scope, "Genome", ws_scope)
    assert genome["spec"]["parent_scope"] == _BASE_SCOPE


@pytest.mark.asyncio
async def test_second_access_touches_the_kernel_zero_times(
    kernel: Kernel,
) -> None:
    """The probe is CACHED: after the first access reaches a stable state, the
    steady-state cost is one set lookup — zero Genome reads, zero writes.

    This is the test that kills the broken-cache mutant: an ensure-per-request
    implementation is still WRITE-idempotent (the second ensure writes
    nothing), so counting writes alone would pass it — the Genome READ count
    is what proves the cache short-circuits before the kernel."""
    live = _live(kernel, _BASE_SCOPE)
    counter = _Counter(kernel)

    first = await adopt_workspace_scope_on_access(live, _WS)
    assert first is not None and first["written"] is True
    reads_after_first = len(counter.reads)
    writes_after_first = len(counter.writes)
    assert writes_after_first == 1  # the one Genome write.

    second = await adopt_workspace_scope_on_access(live, _WS)
    assert second is None  # cache hit — the probe never re-ran.
    assert len(counter.reads) == reads_after_first  # ZERO new kernel reads.
    assert len(counter.writes) == writes_after_first  # ZERO new writes.


@pytest.mark.asyncio
async def test_concurrent_first_burst_single_flights_to_one_write(
    kernel: Kernel,
) -> None:
    """Eight simultaneous first requests over a fresh workspace scope produce
    exactly ONE kernel write — the single-flight lock, not luck."""
    live = _live(kernel, _BASE_SCOPE)
    counter = _Counter(kernel)

    results = await asyncio.gather(
        *(adopt_workspace_scope_on_access(live, _WS) for _ in range(8))
    )

    written = [r for r in results if r is not None and r.get("written")]
    assert len(written) == 1
    assert len(counter.writes) == 1
    genome = await kernel.get_document(
        live.default_scope(_WS), "Genome", live.default_scope(_WS))
    assert genome["spec"]["parent_scope"] == _BASE_SCOPE


# ── intent preservation ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_authored_parent_survives_access_even_with_a_cold_cache(
    kernel: Kernel,
) -> None:
    """An operator-authored ``parent_scope`` is never overwritten — including
    by a FRESH live handle (a new process whose probe cache is cold)."""
    ws_scope = f"tenant-{_WS}"
    await kernel.write_document(
        ws_scope, "Genome", ws_scope,
        _doc("Genome", ws_scope, {"parent_scope": "operator-base"}),
        invalidate_mode="doc",
    )

    live = _live(kernel, _BASE_SCOPE)
    result = await adopt_workspace_scope_on_access(live, _WS)
    assert result is not None and result["written"] is False
    assert result["parent_scope"] == "operator-base"

    # A cold cache (new process) probes again — and still never rewrites.
    cold = _live(kernel, _BASE_SCOPE)
    counter = _Counter(kernel)
    again = await adopt_workspace_scope_on_access(cold, _WS)
    assert again is not None and again["written"] is False
    assert len(counter.writes) == 0
    genome = await kernel.get_document(ws_scope, "Genome", ws_scope)
    assert genome["spec"]["parent_scope"] == "operator-base"


@pytest.mark.asyncio
async def test_without_a_configured_base_nothing_is_written(
    kernel: Kernel,
) -> None:
    """The OSS / self-host baseline: no env → no probe, no write, no Genome."""
    live = _live(kernel, None)
    counter = _Counter(kernel)
    assert await adopt_workspace_scope_on_access(live, _WS) is None
    assert counter.reads == [] and counter.writes == []
    assert await _genome_or_none(kernel, f"tenant-{_WS}") is None


@pytest.mark.asyncio
async def test_vendor_workspace_and_personal_partition_are_never_touched(
    kernel: Kernel,
) -> None:
    """The vendor's own scope must never declare a parent, and a ``personal:``
    partition is a person, not a workspace — both are hard early returns."""
    live = _live(kernel, _BASE_SCOPE)
    counter = _Counter(kernel)

    assert await adopt_workspace_scope_on_access(live, _VENDOR_WS) is None
    assert await adopt_workspace_scope_on_access(live, "personal:oid-x") is None
    assert await adopt_workspace_scope_on_access(live, None) is None
    assert await adopt_workspace_scope_on_access(live, "") is None

    assert counter.reads == [] and counter.writes == []
    base_genome = await kernel.get_document(_BASE_SCOPE, "Genome", _BASE_SCOPE)
    assert "parent_scope" not in (base_genome or {}).get("spec", {})


# ── failure semantics: fail-soft, retry, heal ────────────────────────────────


@pytest.mark.asyncio
async def test_a_failed_probe_is_not_cached_and_the_next_access_heals(
    kernel: Kernel,
) -> None:
    """A transient write failure must not seal the hole: the failing access
    survives (fail-soft, returns None) and the NEXT access retries and
    adopts."""
    live = _live(kernel, _BASE_SCOPE)
    orig_write = kernel.write_document
    boom = {"armed": True}

    async def flaky_write(*a: Any, **kw: Any) -> Any:
        if boom["armed"]:
            boom["armed"] = False
            raise RuntimeError("transient source hiccup")
        return await orig_write(*a, **kw)

    kernel.write_document = flaky_write  # type: ignore[method-assign]

    assert await adopt_workspace_scope_on_access(live, _WS) is None  # soft.
    ws_scope = live.default_scope(_WS)
    assert ws_scope not in live.adoption_probed  # NOT cached — retry allowed.

    healed = await adopt_workspace_scope_on_access(live, _WS)
    assert healed is not None and healed["written"] is True
    genome = await kernel.get_document(ws_scope, "Genome", ws_scope)
    assert genome["spec"]["parent_scope"] == _BASE_SCOPE
