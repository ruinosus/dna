"""O extra `mcp` declara `prefab-ui` DIRETO — não só pela cadeia de extras.

`fastmcp[apps]` -> `fastmcp-slim[apps]` -> `prefab-ui` é declarada em todos os
níveis, e mesmo assim o pacote NÃO foi instalado num ambiente real (dna-cloud,
31/07): o resolvedor trouxe `fastmcp-slim` como dependência simples e o extra
dele se perdeu no caminho.

O efeito foi o pior tipo de falha: `review_kind` e toda tool que renderiza card
morriam com `ModuleNotFoundError` NO SERVIDOR, devolvendo "erro interno" ao
agente. Quem consumia gastou três rodadas procurando o defeito no cliente, atrás
de um dado que nunca foi produzido.
"""
from __future__ import annotations

import pathlib
import tomllib


def _extras():
    p = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
    return tomllib.loads(p.read_text(encoding="utf-8"))["project"]["optional-dependencies"]


def test_o_extra_mcp_declara_prefab_ui_diretamente():
    mcp = " ".join(_extras()["mcp"])
    assert "prefab-ui" in mcp, (
        "o extra `mcp` voltou a depender só da cadeia `fastmcp[apps]` para trazer "
        "`prefab-ui` — e essa cadeia ja falhou em ambiente real"
    )


def test_o_codigo_que_importa_prefab_ui_e_servido_pelo_extra_mcp():
    """A ligação que justifica a declaração: o import é DIRETO no código que o
    extra `mcp` serve. Se ele sumir, a declaração vira carga morta e este teste
    avisa; se aparecer noutro módulo, a declaração continua correta."""
    fonte = (
        pathlib.Path(__file__).resolve().parents[1] / "dna_cli" / "_mcp_cards.py"
    ).read_text(encoding="utf-8")
    assert "from prefab_ui" in fonte
