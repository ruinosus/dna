"""``dna invalidation stats`` — a PORTA por onde os gatilhos do i-123 viram número.

A instrumentação (em ``dna.kernel.invalidation_cost``) só está pronta se o
número chegar em alguém: uma métrica que ninguém lê é a mesma família de
"capacidade existe, porta não". Então ela tem estes testes do lado do comando,
atravessando o Click de verdade.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from dna_cli.invalidation_cmd import invalidation


@pytest.fixture
def runner():
    return CliRunner()


def _linha(**campos) -> str:
    """Uma linha como o coletor a entrega: prefixada e tudo."""
    from dna.kernel.invalidation_cost import INVALIDATION_MARK

    return (
        "2026-08-07T20:11:02.51Z ca-dna-api-4j2 stdout F "
        + INVALIDATION_MARK + json.dumps(campos)
    )


def _escritas(scope_mode: int, total: int = 20) -> list[str]:
    return (
        [_linha(ev="write", mode="scope", plane="composition", kind="Genome",
                op="write", tenant="-")] * scope_mode
        + [_linha(ev="write", mode="doc", plane="record", kind="Story",
                  op="write", tenant="-")] * (total - scope_mode)
    )


def test_o_comando_le_de_stdin(runner):
    """O caso de uso real é um pipe: nada aqui precisa de arquivo nem de banco."""
    feed = "\n".join(_escritas(1) + [_linha(ev="rebuild", docs=10, ms=5.0,
                                            materialized=8, skipped=2)])
    r = runner.invoke(invalidation, ["stats"], input=feed)
    assert r.exit_code == 0, r.output
    assert "21 linha(s) de invalidação lidas" in r.output
    assert "[ok] p95 do rebuild de escopo" in r.output
    assert "[ok] escritas que derrubam o escopo: 1/20 = 5.0%" in r.output


def test_zero_linha_NAO_se_le_como_nao_disparou(runner):
    """⚠️ A mentira mais fácil que este relatório poderia contar.

    Funil desligado e "tudo bem" são estados diferentes, e renderizá-los igual
    faria um operador concluir que mediu quando não mediu.
    """
    r = runner.invoke(invalidation, ["stats"], input="uma linha de outra coisa\n")
    assert r.exit_code == 0, r.output
    assert "NADA foi medido" in r.output
    assert "não disparou" in r.output
    assert "DNA_INVALIDATION_TELEMETRY=on" in r.output


def test_o_veredicto_de_CADA_gatilho_e_impresso(runner):
    caro = "\n".join(
        [_linha(ev="rebuild", docs=50_000, ms=1500.0, materialized=900,
                skipped=49_100)] * 20
        + _escritas(15)
    )
    r = runner.invoke(invalidation, ["stats"], input=caro)
    assert r.exit_code == 0, r.output
    assert "[DISPAROU] p95 do rebuild de escopo: 1500.0 ms (limiar 1000 ms" in r.output
    assert "[DISPAROU] escritas que derrubam o escopo: 15/20 = 75.0%" in r.output
    # ⚠️ E a porta que cada um destrava, nomeada — senão o gatilho disparado
    # manda alguém redescobrir a decisão que já está escrita.
    assert "push-down do filtro de plane" in r.output
    assert "batch_writes()" in r.output
    # …e explicitamente NÃO "troque o default", que o i-123 já fez.
    assert "i-123 já fez isso" in r.output


def test_o_relatorio_NOMEIA_os_kinds_que_derrubam_escopo(runner):
    r = runner.invoke(invalidation, ["stats"], input="\n".join(_escritas(5)))
    assert "Genome: 5 escrita(s) de escopo" in r.output


def test_a_ressalva_do_fan_out_e_IMPRESSA(runner):
    """`invalidate` sair barato não significa que `composition` é barato — a
    ressalva tem de chegar na TELA, não ficar num docstring."""
    r = runner.invoke(
        invalidation, ["stats"],
        input="\n".join([_linha(ev="invalidate", ms=0.2, kind="Genome",
                                op="write", holders=1, batch=False,
                                tenant="-")]),
    )
    assert "O custo está em `rebuild`" in r.output


def test_a_evidencia_de_linearidade_sai_por_balde(runner):
    feed = "\n".join([
        _linha(ev="rebuild", docs=50, ms=2.0, materialized=50, skipped=0),
        _linha(ev="rebuild", docs=5_000, ms=180.0, materialized=400, skipped=4_600),
        _linha(ev="rebuild", docs=50_000, ms=1_700.0, materialized=900,
               skipped=49_100),
    ])
    r = runner.invoke(invalidation, ["stats"], input=feed)
    assert "<100 docs: 2.0 ms" in r.output
    assert "<10k docs: 180.0 ms" in r.output
    assert "10k+ docs: 1700.0 ms" in r.output


def test_o_gate_sai_1_quando_algum_disparou(runner):
    lento = "\n".join(
        [_linha(ev="rebuild", docs=10, ms=5_000.0, materialized=10, skipped=0)] * 5
    )
    assert runner.invoke(invalidation, ["stats", "--gate"], input=lento).exit_code == 1
    calmo = "\n".join(
        [_linha(ev="rebuild", docs=10, ms=5.0, materialized=10, skipped=0)] * 5
    )
    assert runner.invoke(invalidation, ["stats", "--gate"], input=calmo).exit_code == 0


def test_o_gate_vale_TAMBEM_no_modo_json(runner):
    """O ramo `--json` retorna cedo; um `--gate` que só valesse no ramo humano
    seria um portão que o script — o único que usa `--json` — não tem."""
    lento = "\n".join(
        [_linha(ev="rebuild", docs=10, ms=5_000.0, materialized=10, skipped=0)] * 5
    )
    r = runner.invoke(invalidation, ["stats", "--json", "--gate"], input=lento)
    assert r.exit_code == 1
    assert json.loads(r.output)["fired"] is True


def test_o_comando_esta_registrado_no_dna(runner):
    """Uma porta que o `dna` não expõe é uma porta que ninguém acha."""
    from dna_cli import main

    r = runner.invoke(main, ["invalidation", "stats", "--help"])
    assert r.exit_code == 0, r.output
    assert "DNA_INVALIDATION_TELEMETRY=on" in r.output
