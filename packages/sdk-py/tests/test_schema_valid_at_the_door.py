"""O metaschema na PORTA — os dois buracos medidos em 03/08/2026.

O guard (``validate_authored_schema``) sempre existiu, testado em unit — mas
NENHUM teste atravessava uma porta com schema inválido, e foi exatamente por
isso que os dois gaps sobreviveram:

1. ``author_kind_impl`` não o chamava: schema inválido gravava OK, o humano
   APROVAVA, o Kind nunca registrava (warn+skip no registry) e todo doc
   futuro respondia o 404 genérico de Kind desconhecido — apontando o autor
   para o lugar errado.
2. ``input_schema``/``output_schema`` de um doc Tool nunca eram validados: o
   Kind só exige ``type: object``, e o lixo era servido ao modelo como
   ``parameters`` — o erro nascia no provedor de LLM, longe do autor.

⚠️ O que "inválido" significa aqui: JSON Schema tem vocabulário ABERTO —
``{"tipo": "banana"}`` é um schema VÁLIDO (keyword desconhecida é ignorada).
O metaschema pega o lixo ESTRUTURAL: ``type`` fora do enum, ``required`` que
não é lista, ``properties`` que não é objeto. Os testes usam esses.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application.kind_authoring import author_kind_impl
from dna.application.live import LiveDna
from dna.kernel import Kernel

_SCOPE = "acme"
_TENANT = "ws-acme"
_NOW = "2026-08-03T12:00:00Z"

INVALIDOS: list[dict[str, Any]] = [
    {"type": "banana"},                       # type fora do enum do metaschema
    {"type": "object", "required": "titulo"}, # required deve ser array
    {"type": "object", "properties": []},     # properties deve ser objeto
]
VALIDO = {"type": "object", "properties": {"titulo": {"type": "string"}}}


def _write_yaml(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(doc, default_flow_style=False))


@pytest.fixture()
def live(tmp_path: Path) -> LiveDna:
    base = tmp_path / ".dna"
    _write_yaml(base / _SCOPE / "Genome.yaml", {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": _SCOPE}, "spec": {},
    })
    _write_yaml(base / "_lib" / "manifest.yaml", {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": "_lib"}, "spec": {},
    })
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    return LiveDna(base_scope=_SCOPE, kernel=k, provider=None,
                   vendor_workspace=None)


# ── 1. a porta de autoria ──────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("schema", INVALIDOS)
async def test_author_kind_recusa_schema_invalido_na_porta(live, schema):
    """A recusa acontece ONDE o autor pode agir — nunca warn+skip depois."""
    with pytest.raises(ValueError):
        await author_kind_impl(
            live, kind="Deal", schema=schema, tenant=_TENANT,
            actor="author@acme.example", now=_NOW,
        )


@pytest.mark.asyncio
async def test_author_kind_aceita_schema_valido(live):
    res = await author_kind_impl(
        live, kind="Deal", schema=VALIDO, tenant=_TENANT,
        actor="author@acme.example", now=_NOW,
    )
    assert res["kind"] == "Deal"


@pytest.mark.asyncio
async def test_keyword_desconhecida_continua_valida(live):
    """Vocabulário aberto é do PADRÃO: `tipo: banana` não é recusável — o
    metaschema pega lixo estrutural, não typo semântico. Se este teste
    quebrar, o guard ficou mais estrito que o JSON Schema e vai recusar
    schemas legítimos com anotações próprias."""
    res = await author_kind_impl(
        live, kind="Livre", schema={"tipo": "banana"}, tenant=_TENANT,
        actor="author@acme.example", now=_NOW,
    )
    assert res["kind"] == "Livre"


# ── 2. o guard do Tool ─────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("schema", INVALIDOS)
async def test_tool_com_input_schema_invalido_e_vetado(live, schema):
    from dna.kernel.kinds.schema_guard import SchemaGuardError

    with pytest.raises(SchemaGuardError) as exc:
        await live.kernel.write_instance(
            _SCOPE, "Tool", "minha-tool",
            {
                "apiVersion": "github.com/ruinosus/dna/helix/v1",
                "kind": "Tool",
                "metadata": {"name": "minha-tool"},
                "spec": {"type": "http", "input_schema": schema},
            },
        )
    # A recusa NOMEIA o campo — é o que a torna acionável na tela.
    assert "spec.input_schema" in str(exc.value)


@pytest.mark.asyncio
async def test_tool_com_schemas_validos_grava(live):
    await live.kernel.write_instance(
        _SCOPE, "Tool", "tool-ok",
        {
            "apiVersion": "github.com/ruinosus/dna/helix/v1",
            "kind": "Tool",
            "metadata": {"name": "tool-ok"},
            "spec": {
                "type": "http",
                "input_schema": VALIDO,
                "output_schema": {},  # vazio = permissivo, como o write path
            },
        },
    )
