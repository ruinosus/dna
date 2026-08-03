"""O card MCP Apps do Kind autorado (Kind Studio F3) — o template e o eco.

O que se prende:

* o template é ESTÁTICO e sem dado embutido (cacheável por URI), carrega a
  lib vendorada entre os MESMOS sentinelas do memory card, e é INTERATIVO —
  reautora via ``callServerTool`` apontando o nome real da tool;
* a honestidade do funil está NO template: toda renderização diz que a
  aprovação é humana e acontece no portal;
* ``author_kind_impl`` ECOA o schema no resultado — sem o eco o card não tem
  o que editar, e a regressão seria um card permanentemente vazio em outra
  máquina (host de terceiro), o pior lugar para descobrir.
"""
from __future__ import annotations

from datetime import timezone  # noqa: F401 — paridade com o teste vizinho
from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.emit.mcp_ui import (
    MCP_APP_MIME,
    UI_KIND_DRAFT_URI,
    kind_draft_card_html,
)

_SENTINEL_BEGIN = "/*! begin vendored @modelcontextprotocol/ext-apps */"
_SENTINEL_END = "/*! end vendored @modelcontextprotocol/ext-apps */"


def test_template_estatico_interativo_e_sem_dado():
    h = kind_draft_card_html()
    assert h == kind_draft_card_html(), "o template deve ser byte-estável"
    assert _SENTINEL_BEGIN in h and _SENTINEL_END in h
    # Interatividade: reautorar chama a tool pelo NOME REAL — o mesmo que o
    # servidor registra; um rename de tool quebra AQUI, não no host alheio.
    assert "callServerTool" in h
    assert '"author_kind"' in h or "author_kind" in h
    # A honestidade do funil, no template: aprovação humana, no portal.
    assert "human approves it in the portal" in h
    # Sem dado embutido: nenhum Kind real, nenhum schema de exemplo.
    assert "Contrato" not in h and '"properties": {"' not in h


def test_uri_e_mime_sao_o_contrato_do_host():
    assert UI_KIND_DRAFT_URI == "ui://dna/kind-draft"
    assert MCP_APP_MIME == "text/html;profile=mcp-app"


# ── o eco do schema na porta ───────────────────────────────────────────────


def _write_yaml(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(doc, default_flow_style=False))


@pytest.mark.asyncio
async def test_author_kind_ecoa_o_schema_para_o_card(tmp_path: Path):
    from dna.adapters.filesystem import FilesystemCache
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.application.kind_authoring import author_kind_impl
    from dna.application.live import LiveDna
    from dna.kernel import Kernel

    base = tmp_path / ".dna"
    for scope in ("acme", "_lib"):
        _write_yaml(base / scope / ("Genome.yaml" if scope == "acme" else "manifest.yaml"), {
            "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
            "metadata": {"name": scope}, "spec": {},
        })
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    live = LiveDna(base_scope="acme", kernel=k, provider=None, vendor_workspace=None)

    schema = {"type": "object", "properties": {"titulo": {"type": "string"}}}
    res = await author_kind_impl(
        live, kind="Deal", schema=schema, tenant="ws-acme",
        actor="a@acme.example", now="2026-08-03T12:00:00Z",
    )
    assert res["schema"] == schema, "o card renderiza a partir DESTE eco"
    assert res["approved"] is False
