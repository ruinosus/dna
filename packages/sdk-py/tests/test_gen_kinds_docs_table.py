"""A tabela de campos da referência de Kinds — e o que ela escondia.

`scripts/gen_kinds_docs.py` gera `docs/reference/kinds/*.md` a partir do
`schema()` de cada Kind registrado, e é guardado contra drift no CI. Mas ele só
percorria as `properties` do TOPO.

O efeito é o pior tipo de documentação errada: a que parece completa. Um leitor
que abrisse a referência do `RemoteAgent` para saber como escrever um
`supported_interfaces` via a linha "array — cada entrada nomeia um binding de
protocolo" e **nenhum nome de campo** — nem `protocol_binding`, nem `url`, nem
`protocol_version`. A informação existia no schema, era obrigatória para
escrever a instância, e não chegava a lugar nenhum.

O gerador não tinha teste (só a guarda de drift, que prova que a saída é
estável — não que ela é completa). Este arquivo testa a função pura que monta a
tabela.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GERADOR = _REPO_ROOT / "scripts" / "gen_kinds_docs.py"


@pytest.fixture(scope="module")
def gerador():
    if not _GERADOR.exists():  # pragma: no cover - fora do checkout do repo
        pytest.skip("gen_kinds_docs.py só existe no checkout do repo")
    spec = importlib.util.spec_from_file_location("_gen_kinds_docs", _GERADOR)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _tabela(gerador, schema: dict) -> str:
    import io

    out = io.StringIO()
    gerador._schema_table(schema, out)
    return out.getvalue()


#: A forma exata do `supported_interfaces` do Kind `RemoteAgent` — o caso que
#: revelou o buraco.
_SCHEMA = {
    "type": "object",
    "required": ["supported_interfaces", "data_scope"],
    "properties": {
        "supported_interfaces": {
            "type": "array",
            "description": "Onde alcançar o agente.",
            "items": {
                "type": "object",
                "required": ["protocol_binding", "url"],
                "properties": {
                    "protocol_binding": {
                        "type": "string",
                        "enum": ["JSONRPC", "GRPC", "HTTP+JSON"],
                        "description": "O binding.",
                    },
                    "url": {"type": "string", "description": "HTTPS obrigatório."},
                },
            },
        },
        "data_scope": {
            "type": "object",
            "required": ["kinds"],
            "properties": {
                "kinds": {"type": "array", "description": "O que pode ser enviado."}
            },
        },
    },
}


def test_os_campos_DENTRO_de_um_array_de_objetos_aparecem(gerador):
    tabela = _tabela(gerador, _SCHEMA)
    assert "supported_interfaces[].protocol_binding" in tabela, tabela
    assert "supported_interfaces[].url" in tabela, tabela


def test_os_campos_de_um_objeto_aninhado_aparecem(gerador):
    tabela = _tabela(gerador, _SCHEMA)
    assert "data_scope.kinds" in tabela, tabela


def test_o_required_do_nivel_ANINHADO_e_respeitado(gerador):
    """`url` é obrigatório DENTRO da interface, não no topo. Herdar o required
    do pai marcaria campos opcionais como exigidos — pior que não marcar."""
    linhas = {
        linha.split("|")[1].strip(): linha
        for linha in _tabela(gerador, _SCHEMA).splitlines()
        if linha.startswith("|") and "`" in linha
    }
    assert "yes" in linhas["`supported_interfaces[].url`"]
    assert "yes" in linhas["`supported_interfaces[].protocol_binding`"]


def test_os_valores_de_um_enum_sao_mostrados(gerador):
    """Saber que o campo se chama `protocol_binding` e não saber que o valor é
    `JSONRPC` (maiúsculo) deixa o leitor a um passo do mesmo erro que originou
    esta correção."""
    tabela = _tabela(gerador, _SCHEMA)
    assert "JSONRPC" in tabela, tabela
    assert "HTTP+JSON" in tabela, tabela


def test_um_pipe_dentro_de_um_valor_nao_quebra_a_tabela(gerador):
    """`HTTP+JSON` é inofensivo, mas um enum com `|` partiria a linha em duas
    colunas e a tabela inteira sairia torta."""
    tabela = _tabela(
        gerador,
        {
            "type": "object",
            "properties": {"m": {"type": "string", "enum": ["a|b", "c"]}},
        },
    )
    linha = [x for x in tabela.splitlines() if x.startswith("| `m`")][0]
    assert "a\\|b" in linha, linha


def test_a_recursao_nao_explode_num_schema_ciclico(gerador):
    """Um schema que se referencia (por `$ref` resolvido, ou por engano de
    construção) não pode pendurar o gerador — a guarda de profundidade é o que
    garante que a documentação sempre termina de ser gerada."""
    ciclico: dict = {"type": "object", "properties": {}}
    ciclico["properties"]["eu"] = ciclico
    assert _tabela(gerador, ciclico)


def test_um_kind_sem_campos_continua_dizendo_isso(gerador):
    assert "No structured spec fields" in _tabela(gerador, {})
