"""Unit tests for the definition read/apply/revert use-cases (s-strain-customization-ui).

Backed by the filesystem writable source so no Postgres is needed — the pg-backed
compose behaviour is proven separately in test_definition_overlay_pg.py.
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
    apply_definition_impl,
    read_definition_impl,
    revert_definition_impl,
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
    (base / "_lib").mkdir(parents=True, exist_ok=True)
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    return LiveDna(base_scope=_BASE, kernel=k, provider=None,
                   vendor_workspace=None, workspace_definitions_base=_BASE)


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
