"""``dna graph refs --as-of`` — a TERCEIRA face do mesmo verbo, e as recusas.

A comparação entre REST e MCP mora em ``test_mcp_graph_refs.py``; o que só esta
suíte pode provar é o que a face de terminal FAZ com uma recusa. Uma travessia
histórica que não pode ser respondida e sai como ``no edges recorded`` é
indistinguível, para quem lê o terminal, de "nada aponta para esta instância" —
o mesmo colapso que o ``GraphUnsupported`` já custou uma vez, agora com o eixo
do tempo por cima.

A `dna graph refs` também é a única face que IMPRIME ``as_of_truncated`` em
prosa, e a ordem importa: o aviso vem antes da lista, porque um leitor que veja
a lista primeiro já a leu como completa.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import shutil

import pytest
from click.testing import CliRunner

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"

_SQL_SKIP = (
    "the SQL adapter's async driver stack is an SDK extra the CLI does not "
    "pull; the refusal lane — the one only this suite can prove — still runs."
)


def _run(args, env):
    from dna_cli.graph_cmd import graph

    return CliRunner().invoke(graph, args, env=env, catch_exceptions=False)


@pytest.fixture
def fs_env(tmp_path):
    """O store de filesystem — o que não guarda aresta NEM história."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    return {
        "DNA_BASE_DIR": str(dst),
        "DNA_SOURCE_URL": "",
        "DNA_WRITE_VALIDATION": "off",
    }


@pytest.fixture
def sql_env(tmp_path, monkeypatch):
    for _module in ("aiosqlite", "greenlet", "alembic"):
        pytest.importorskip(_module, reason=_SQL_SKIP)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)
    url = f"sqlite+aiosqlite:///{tmp_path / 'refs.db'}"

    def _doc(kind, name, **spec):
        base = {"description": "d", "status": "todo"}
        base.update(spec)
        return {
            "apiVersion": _SDLC_API, "kind": kind,
            "metadata": {"name": name}, "spec": base,
        }

    async def seed():
        from dna.adapters.sqlalchemy_ import SqlAlchemySource
        from dna.kernel import Kernel

        src = SqlAlchemySource(url)
        await src.connect()
        k = Kernel.auto()
        k.source(src)
        await k.write_instance(_SCOPE, "Feature", "f-y", _doc("Feature", "f-y"))
        await k.write_instance(
            _SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"))
        await src.close()

    asyncio.run(seed())
    return {
        "DNA_SOURCE_URL": url,
        "DNA_BASE_DIR": "",
        "DNA_WRITE_VALIDATION": "off",
    }


def test_o_as_of_atravessa_a_face_de_terminal(sql_env):
    """i-106 generalizado: um parâmetro que a face ACEITA e IGNORA devolve o
    presente sob um carimbo do passado, com saída zero. O eco é a prova de que
    ele chegou."""
    r = _run(
        ["refs", "Story", "s-x", "--scope", _SCOPE, "--direction", "out",
         "--as-of", "2099-01-01", "--json"],
        env=sql_env,
    )
    assert r.exit_code == 0, r.output
    saida = json.loads(r.output)
    assert saida["as_of"] == "2099-01-01T00:00:00+00:00"
    assert [e["to_name"] for e in saida["edges"]] == ["f-y"]
    assert saida["as_of_truncated"] == []


def test_uma_travessia_VIVA_diz_as_of_nulo(sql_env):
    r = _run(
        ["refs", "Story", "s-x", "--scope", _SCOPE, "--direction", "out",
         "--json"],
        env=sql_env,
    )
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["as_of"] is None


def test_a_instancia_que_nao_existia_ainda_FALHA_em_vez_de_imprimir_vazio(
    sql_env,
):
    """⚠️ A asserção central desta suíte.

    Sem o arm de ``LookupError`` a mensagem que sairia é ``no edges recorded
    (producer: warn, stop: complete)`` — que um humano lê como "esta Story não
    aponta para nada em 2020", quando a verdade é "esta Story não existia em
    2020". Sair 0 com essa linha é pior que sair 1 com a verdade."""
    r = _run(
        ["refs", "Story", "s-x", "--scope", _SCOPE, "--direction", "out",
         "--as-of", "2020-01-01"],
        env=sql_env,
    )
    assert r.exit_code != 0, r.output
    assert "no edges recorded" not in r.output
    assert "2020-01-01" in r.output


def test_um_as_of_que_nao_e_instante_FALHA_nomeando_o_valor(sql_env):
    r = _run(
        ["refs", "Story", "s-x", "--scope", _SCOPE, "--as-of", "ontem"],
        env=sql_env,
    )
    assert r.exit_code != 0, r.output
    assert "ontem" in r.output


def test_o_store_sem_arestas_recusa_pelo_NOME_tambem_com_as_of(fs_env):
    """A recusa que já existia continua chegando com o eixo novo por cima — e
    ela vem pelo NOME, porque o remédio ("rode contra um adapter que guarda
    arestas") é diferente de todo outro jeito de esta chamada falhar."""
    r = _run(
        ["refs", "Agent", "concierge", "--scope", _SCOPE,
         "--as-of", "2026-01-01"],
        env=fs_env,
    )
    assert r.exit_code != 0, r.output
    assert "GraphUnsupported" in r.output, r.output
