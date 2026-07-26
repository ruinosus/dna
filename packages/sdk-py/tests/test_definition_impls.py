"""Unit tests for the definition read/apply/revert use-cases (s-strain-customization-ui).

Backed by the filesystem writable source so no Postgres is needed — the pg-backed
compose behaviour is proven separately in test_definition_overlay_pg.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application.live import LiveDna
from dna.application.runtime import (
    apply_definition_impl,
    read_definition_impl,
    revert_definition_impl,
    write_bundle_entry_impl,
)
from dna.kernel import Kernel

_BASE = "dna-cloud"
_WID = "ws-cust00000000000000000001"


def _doc(kind: str, name: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {"apiVersion": "github.com/ruinosus/dna/v1", "kind": kind,
            "metadata": {"name": name}, "spec": spec}


def _write(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(doc, default_flow_style=False))


@pytest.fixture()
def live(tmp_path: Path) -> LiveDna:
    base = tmp_path / ".dna"
    _write(base / _BASE / "Genome.yaml", _doc("Genome", _BASE, {}))
    _write(base / _BASE / "agents" / "assistant.yaml",
           _doc("Agent", "assistant", {"instruction": "Base agent."}))
    # Record-plane Kinds (plane: record in their descriptors) — deliberately
    # absent from ``mi.documents``; the definitions read must still find them.
    _write(base / _BASE / "tools" / "ping.yaml",
           _doc("Tool", "ping", {"type": "http", "endpoint": "https://example.test/ping"}))
    _write(base / _BASE / "copilots" / "concierge.yaml",
           _doc("Copilot", "concierge", {
               "mounts": [{"id": "main", "agent": "assistant", "path": "/agui"}],
               "serving": {"transport": "ag-ui"},
           }))
    (base / "_lib").mkdir(parents=True, exist_ok=True)
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    return LiveDna(base_scope=_BASE, kernel=k, provider=None,
                   vendor_workspace=None, workspace_definitions_base=_BASE)


class _NoOpCache:
    """The composition cache is irrelevant here; the Kernel just requires one."""

    async def has(self, scope: str, key: str) -> bool:
        return True

    async def load_all(self, scope: str, readers: Any = None) -> list[Any]:
        return []

    async def store(self, scope: str, key: str, items: Any) -> None:
        pass


@pytest_asyncio.fixture()
async def live_sqlite(tmp_path: Path):
    """Same seed over the SQLAlchemy adapter — the production-shaped source.
    Its async engine is loop-bound, so the kernel's SYNC helpers raise here
    while the filesystem source tolerates them."""
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    src = SqlAlchemySource(f"sqlite+aiosqlite:///{tmp_path / 'dna.db'}")
    await src.connect()
    k = Kernel.auto()
    k.source(src)
    k.cache(_NoOpCache())
    for kind, name, spec in [
        ("Genome", _BASE, {}),
        ("Agent", "assistant", {"instruction": "Base agent."}),
    ]:
        await k.write_document(_BASE, kind, name, _doc(kind, name, spec))
    try:
        yield LiveDna(base_scope=_BASE, kernel=k, provider=None,
                      vendor_workspace=None, workspace_definitions_base=_BASE)
    finally:
        await src.close()


@pytest.mark.asyncio
async def test_read_returns_base_and_schema_when_not_overridden(live: LiveDna) -> None:
    out = await read_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant")
    assert out["overridden"] is False
    assert out["effective"]["instruction"] == "Base agent."
    assert out["base"]["instruction"] == "Base agent."
    assert isinstance(out["ui_schema"], dict)
    assert "pattern" in out and isinstance(out["bundle_entries"], list)
    assert "body_field" in out


@pytest.mark.asyncio
async def test_apply_then_read_shows_override(live: LiveDna) -> None:
    await apply_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant",
        spec={"instruction": "Speak Portuguese."})
    out = await read_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant")
    assert out["overridden"] is True
    assert out["effective"]["instruction"] == "Speak Portuguese."
    assert out["base"]["instruction"] == "Base agent."


@pytest.mark.asyncio
async def test_apply_with_spec_equal_to_base_still_shows_overridden(live: LiveDna) -> None:
    """The ``overridden`` contract is doc PRESENCE, not a spec-value diff: an
    override whose composed spec happens to MATCH base (identical-value / a
    merge-to-base edit) must still report overridden=True — the tenant-layer doc
    exists, so a spec-diff would (incorrectly) say False and orphan the editor's
    Revert affordance. Reverting then correctly clears the flag."""
    await apply_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant",
        spec={"instruction": "Base agent."})
    out = await read_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant")
    assert out["overridden"] is True
    assert out["effective"]["instruction"] == "Base agent."
    assert out["base"]["instruction"] == "Base agent."

    await revert_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant")
    out = await read_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant")
    assert out["overridden"] is False


# ── record-plane Kinds (Tool, Copilot, …) — i-076 ────────────────────────────
#
# 35 of the registered Kinds declare ``plane: record`` in their descriptor, and
# the instance builder deliberately keeps those out of ``mi.documents`` (the MI
# is O(composition)). The definitions API must not inherit that exclusion: it
# knows exactly which (kind, name) it wants, so it resolves record Kinds through
# the kernel record plane instead. Before the fix these read paths raised
# ``ValueError: no Tool named 'ping' …`` while apply/revert worked — a
# WRITE-ONLY API for every record Kind.


@pytest.mark.parametrize(
    ("kind", "name", "probe"),
    [("Tool", "ping", "type"), ("Copilot", "concierge", "mounts")],
)
@pytest.mark.asyncio
async def test_read_resolves_record_plane_kind(
    live: LiveDna, kind: str, name: str, probe: str
) -> None:
    out = await read_definition_impl(
        live, scope=_BASE, tenant=_WID, kind=kind, name=name)
    assert out["overridden"] is False
    assert out["effective"][probe], f"{kind} spec is empty — read fell back to {{}}"
    assert out["base"] == out["effective"]
    # The whole point of the surface: a schema-driven editor needs the ui_schema.
    assert out["ui_schema"], f"{kind} carries no ui_schema"
    assert probe in out["ui_schema"]


@pytest.mark.asyncio
async def test_record_plane_write_then_read_round_trip(live: LiveDna) -> None:
    """The asymmetry users actually hit: PUT succeeded where GET 404'd, so an
    override could be saved and never read back."""
    await apply_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Tool", name="ping",
        spec={"type": "http", "endpoint": "https://tenant.test/ping"})
    out = await read_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Tool", name="ping")
    assert out["overridden"] is True
    assert out["effective"]["endpoint"] == "https://tenant.test/ping"
    assert out["base"]["endpoint"] == "https://example.test/ping"

    await revert_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Tool", name="ping")
    out = await read_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Tool", name="ping")
    assert out["overridden"] is False
    assert out["effective"]["endpoint"] == "https://example.test/ping"


@pytest.mark.asyncio
@pytest.mark.filterwarnings("error::RuntimeWarning")
async def test_bundle_pattern_kind_reports_its_entries(live_sqlite: LiveDna) -> None:
    """``bundle_entries`` must actually list the bundle's files.

    The listing went through the SYNC ``kernel.list_bundle_entries``, whose
    ``_run_sync_helper`` raises against a loop-bound SQL source — and
    ``read_definition_impl`` is always awaited, so the broad ``except``
    swallowed it and every bundle Kind reported ``[]`` (plus a stray "coroutine
    was never awaited" RuntimeWarning). It stayed hidden because the only Kinds
    that reached the block were composition Kinds; resolving record Kinds
    (ADR/Memory/Plan/Spec/… are all bundle-pattern) drags the dead code into
    the light. Runs on the SQL adapter because that is where the sync bundle
    helpers break — the filesystem source tolerates them (B1's lesson, see
    ``reconcile_forks_impl``).
    """
    await write_bundle_entry_impl(
        live_sqlite, scope=_BASE, tenant=_WID, kind="Agent", name="assistant",
        entry="scripts/hello.sh", content="echo hi\n")
    out = await read_definition_impl(
        live_sqlite, scope=_BASE, tenant=_WID, kind="Agent", name="assistant")
    assert out["pattern"] == "bundle"
    assert "scripts/hello.sh" in out["bundle_entries"]


@pytest.mark.asyncio
async def test_read_unknown_record_plane_name_still_raises(live: LiveDna) -> None:
    """The 404 path stays a 404 — resolving record Kinds must not invent docs."""
    with pytest.raises(ValueError, match="no Tool named 'nope'"):
        await read_definition_impl(
            live, scope=_BASE, tenant=_WID, kind="Tool", name="nope")


@pytest.mark.asyncio
async def test_revert_falls_back_to_base(live: LiveDna) -> None:
    await apply_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant",
        spec={"instruction": "Speak Portuguese."})
    await revert_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant")
    out = await read_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant")
    assert out["overridden"] is False
    assert out["effective"]["instruction"] == "Base agent."
