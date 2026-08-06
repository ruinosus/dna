"""``dna graph stats`` — a PORTA por onde o gatilho 2 vira número.

A fatia 0 de ``spec-topologia-do-grafo`` só está pronta se o número chegar em
alguém: uma métrica que ninguém lê é a mesma família de "capacidade existe,
porta não" — o defeito que esta casa já caçou três vezes no mesmo dia. Então a
instrumentação (em ``dna.kernel.query.graph``) tem estes testes do lado do
comando, atravessando o Click de verdade:

* o comando lê de STDIN, que é o que torna
  ``az containerapp logs show … | dna graph stats`` possível sem arquivo nem
  banco no meio;
* ele imprime o veredicto de CADA gatilho, não só os números crus;
* ``--gate`` sai 1 quando algum disparou, para um cron ou um passo de CI;
* **zero linha não se lê como "não disparou"** — o caso em que o funil está
  desligado ou a fonte está errada é dito com todas as letras, porque é a
  mentira mais fácil que este relatório poderia contar.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from dna_cli.graph_cmd import graph


@pytest.fixture
def runner():
    return CliRunner()


def _line(*, ms: float, depth: int = 3, stop: str = "complete",
          tenant: str = "-") -> str:
    """Uma linha como o coletor a entrega: prefixada e tudo."""
    from dna.kernel.query.graph import TRAVERSAL_MARK

    body = json.dumps({
        "kind": "Feature", "dir": "in", "depth": depth, "stop": stop,
        "edges": 3, "ms": ms, "producer": "warn", "tenant": tenant,
    })
    return f"2026-08-06T20:11:02.51Z ca-dna-api-4j2 stdout F {TRAVERSAL_MARK}{body}"


def test_o_comando_le_de_stdin(runner):
    """O caso de uso real é um pipe: nada aqui precisa de arquivo nem de banco."""
    feed = "\n".join(_line(ms=12.0) for _ in range(20))
    r = runner.invoke(graph, ["stats"], input=feed)
    assert r.exit_code == 0, r.output
    assert "20 travessia(s) lidas" in r.output
    assert "[ok] p95 depth>=3" in r.output
    assert "[ok] truncadas" in r.output


def test_o_veredicto_de_cada_gatilho_e_impresso(runner):
    lentas = "\n".join(_line(ms=900.0) for _ in range(20))
    r = runner.invoke(graph, ["stats"], input=lentas)
    assert r.exit_code == 0, r.output
    assert "[DISPAROU] p95 depth>=3: 900.0 ms (limiar 500 ms" in r.output
    # A porta já nomeada, para não ter de ser procurada de novo.
    assert "Apache AGE" in r.output


def test_gate_sai_1_quando_disparou(runner):
    lentas = "\n".join(_line(ms=900.0) for _ in range(20))
    assert runner.invoke(graph, ["stats", "--gate"], input=lentas).exit_code == 1
    rapidas = "\n".join(_line(ms=9.0) for _ in range(20))
    assert runner.invoke(graph, ["stats", "--gate"], input=rapidas).exit_code == 0


def test_sem_gate_o_comando_INFORMA_e_nao_barra(runner):
    """Mesmo padrão do ``cost`` / ``cost:gate`` do dna-cloud: informar por
    default, barrar quando alguém pediu."""
    lentas = "\n".join(_line(ms=900.0) for _ in range(20))
    r = runner.invoke(graph, ["stats"], input=lentas)
    assert r.exit_code == 0 and "DISPAROU" in r.output


def test_truncamento_dispara_pelo_stop_que_a_resposta_ja_devolvia(runner):
    feed = [_line(ms=5.0, stop="truncated") for _ in range(5)]
    feed += [_line(ms=5.0) for _ in range(95)]
    r = runner.invoke(graph, ["stats", "--gate"], input="\n".join(feed))
    assert r.exit_code == 1
    assert "[DISPAROU] truncadas: 5/100 = 5.00% (limiar 1%)" in r.output


def test_zero_linha_NAO_se_le_como_nao_disparou(runner):
    """⚠️ O relatório de zeros sobre a fonte errada seria indistinguível de um
    ambiente saudável. Ele se denuncia, e ``--gate`` não passa a impressão de
    aprovação por ter saído 0 sem medir nada."""
    r = runner.invoke(graph, ["stats"], input="linha de outro serviço\noutra\n")
    assert r.exit_code == 0
    assert "0 travessia(s) lidas (2 linha(s) ignoradas)" in r.output
    assert "NADA foi medido" in r.output
    assert "isto não é 'não disparou'" in r.output


def test_json_carrega_o_relatorio_inteiro(runner):
    feed = [_line(ms=900.0, tenant="deadbeef") for _ in range(10)]
    feed += [_line(ms=5.0, depth=1) for _ in range(10)]
    r = runner.invoke(graph, ["stats", "--json"], input="\n".join(feed))
    assert r.exit_code == 0, r.output
    report = json.loads(r.output)
    assert report["calls"] == 20
    assert report["deep"]["calls"] == 10
    assert report["worst_tenant"]["tenant"] == "deadbeef"
    assert report["triggers"]["scale_p95"]["fired"] is True
    assert report["triggers"]["scale_truncated"]["fired"] is False
    assert report["fired"] is True


def test_o_arquivo_tambem_serve(runner, tmp_path):
    p = tmp_path / "api.log"
    p.write_text("\n".join(_line(ms=7.0) for _ in range(3)), encoding="utf-8")
    r = runner.invoke(graph, ["stats", str(p)])
    assert r.exit_code == 0, r.output
    assert "3 travessia(s) lidas" in r.output


def test_a_ajuda_diz_como_LIGAR_o_funil(runner):
    """Um comando de leitura que não diz como ligar a produção do dado deixa o
    leitor com um relatório vazio e nenhuma pista."""
    r = runner.invoke(graph, ["stats", "--help"])
    assert r.exit_code == 0
    assert "DNA_GRAPH_TELEMETRY=on" in r.output
    assert "gatilho 1" in r.output.lower()
