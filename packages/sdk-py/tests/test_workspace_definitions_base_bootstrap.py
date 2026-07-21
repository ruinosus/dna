"""The workspace scope is BORN declaring its parent — i-058's application half.

``test_workspace_definitions_inheritance.py`` proves that a workspace scope
WITH a declared ``parent_scope`` reads the base's definitions on every
surface. This module proves the declaration actually happens at the two
moments the product has:

* **birth** — ``create_workspace_impl`` (``POST /v1/workspaces``) writes the
  scope's Genome with ``parent_scope = live.workspace_definitions_base``
  between the Workspace doc and the owner grant;
* **adoption** — ``provision_workspace_owner_impl`` (called on every portal
  sign-in) retrofits the same Genome onto a workspace born BEFORE the base
  was configured — zero operational steps for the two production workspaces.

And the boundaries that keep it honest:

* no base configured (the OSS / self-host default) → NOTHING is written —
  the anti-vacuity baseline: inheritance never turns on by magic;
* an operator-authored ``parent_scope`` is NEVER overwritten;
* the VENDOR workspace (whose scope IS the host's base scope) is never
  touched — the base scope must not end up declaring a parent, nor itself.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application.live import LiveDna
from dna.application.runtime import (
    create_workspace_impl,
    ensure_workspace_scope_genome,
    list_agents_impl,
    provision_workspace_owner_impl,
)
from dna.kernel import Kernel

_BASE_SCOPE = "dna-development"
_VENDOR_WS = "ws-vendor00000000000000000"
_CLAIMS = {"oid": "oid-founder", "email": "founder@dna.dev", "tid": "tid-azure"}


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
    """Read a scope's Genome, treating a scope the FS source has never seen
    (no directory yet — PG's 'empty scope' equivalent) as 'no Genome'."""
    try:
        return await kernel.get_document(scope, "Genome", scope)
    except FileNotFoundError:
        return None


# ── birth: create declares the parent ───────────────────────────────────────


@pytest.mark.asyncio
async def test_create_births_the_scope_with_the_declared_parent(
    kernel: Kernel,
) -> None:
    """The full product loop: create a workspace, then browse it — the
    newborn scope's Genome declares the base, and list_agents already
    surfaces the curated definitions. No seed script, no redeploy."""
    live = _live(kernel, _BASE_SCOPE)
    out = await create_workspace_impl(live, "Acme", _CLAIMS)
    ws_scope = live.default_scope(out["workspace_id"])

    genome = await kernel.get_document(ws_scope, "Genome", ws_scope)
    assert genome is not None
    assert genome["spec"]["parent_scope"] == _BASE_SCOPE

    listed = await list_agents_impl(live, scope=ws_scope)
    assert "assistant" in {a["name"] for a in listed["agents"]}


@pytest.mark.asyncio
async def test_without_a_configured_base_nothing_is_written(
    kernel: Kernel,
) -> None:
    """The anti-vacuity baseline at the application layer: the OSS/self-host
    default (no base configured) creates the workspace EXACTLY as today —
    no Genome, no inheritance, the scope stays empty."""
    live = _live(kernel, None)
    out = await create_workspace_impl(live, "Plain", _CLAIMS)
    ws_scope = live.default_scope(out["workspace_id"])

    assert await _genome_or_none(kernel, ws_scope) is None
    # Materialize the empty scope dir (what any first write does; PG treats an
    # unknown scope as empty) so the listing surface can answer honestly.
    src_base = Path(kernel.active_source.base_dir)
    (src_base / ws_scope).mkdir()
    listed = await list_agents_impl(live, scope=ws_scope)
    assert "assistant" not in {a["name"] for a in listed["agents"]}


# ── adoption: an existing workspace declares the parent on sign-in ──────────


@pytest.mark.asyncio
async def test_provision_owner_adopts_an_existing_workspace(
    kernel: Kernel,
) -> None:
    """A workspace born BEFORE the base existed (created with no base
    configured) is adopted by the next sign-in once the env lands — and the
    adoption is idempotent (the second sign-in writes nothing)."""
    born_before = _live(kernel, None)
    out = await create_workspace_impl(born_before, "Legacy", _CLAIMS)
    wid = out["workspace_id"]
    ws_scope = born_before.default_scope(wid)
    assert await _genome_or_none(kernel, ws_scope) is None

    # The deploy that sets DNA_WORKSPACE_DEFINITIONS_BASE, then a sign-in.
    live = _live(kernel, _BASE_SCOPE)
    res = await provision_workspace_owner_impl(live, wid, _CLAIMS)
    assert res["reason"] == "already_member"

    genome = await kernel.get_document(ws_scope, "Genome", ws_scope)
    assert genome is not None
    assert genome["spec"]["parent_scope"] == _BASE_SCOPE

    # Idempotent: a second sign-in is a no-op on the Genome.
    again = await ensure_workspace_scope_genome(live, wid)
    assert again["written"] is False
    assert again["parent_scope"] == _BASE_SCOPE


@pytest.mark.asyncio
async def test_an_operator_authored_parent_is_never_overwritten(
    kernel: Kernel,
) -> None:
    """Configuration yields to intent: a Genome that already declares a
    parent (any parent) survives both adoption and re-creation paths."""
    live = _live(kernel, _BASE_SCOPE)
    out = await create_workspace_impl(live, "Custom", _CLAIMS)
    wid = out["workspace_id"]
    ws_scope = live.default_scope(wid)

    # An operator re-points the scope at a custom base…
    custom = await kernel.get_document(ws_scope, "Genome", ws_scope)
    custom["spec"]["parent_scope"] = "operator-base"
    await kernel.write_document(ws_scope, "Genome", ws_scope, custom,
                                invalidate_mode="doc")

    # …and neither adoption nor the ensure helper claws it back.
    await provision_workspace_owner_impl(live, wid, _CLAIMS)
    res = await ensure_workspace_scope_genome(live, wid)
    assert res["written"] is False
    assert res["parent_scope"] == "operator-base"
    genome = await kernel.get_document(ws_scope, "Genome", ws_scope)
    assert genome["spec"]["parent_scope"] == "operator-base"


# ── the vendor boundary ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_vendor_scope_is_never_touched(kernel: Kernel) -> None:
    """The vendor workspace resolves to the host's OWN base scope — writing a
    Genome there would make the base declare a parent (or itself). Both the
    vendor id and the multi-workspace-off regime are no-ops."""
    live = _live(kernel, _BASE_SCOPE)
    res = await ensure_workspace_scope_genome(live, _VENDOR_WS)
    assert res["written"] is False

    single_tenant = LiveDna(
        base_scope=_BASE_SCOPE, kernel=kernel, provider=None,
        vendor_workspace=None,  # multi-workspace OFF
        workspace_definitions_base=_BASE_SCOPE,
    )
    res = await ensure_workspace_scope_genome(single_tenant, "ws-whatever")
    assert res["written"] is False

    genome = await kernel.get_document(_BASE_SCOPE, "Genome", _BASE_SCOPE)
    assert "parent_scope" not in (genome or {}).get("spec", {})
