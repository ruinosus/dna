"""A RAIA do turno: teste e uso real param de somar na mesma conta (`i-158`).

*"Uma coisa é conversa de teste, outra é conversa real."*

Sem banco, como o resto de `dna.runtime.roi`: a regra é pura de propósito, e os
casos que decidem esta issue são todos de AUSÊNCIA — que é justamente o que um
teste contra o Postgres exercita mal.

⭐ **O teste que mais importa não é o do filtro, é o do que ficou DE FORA.**
Filtrar é fácil e um `WHERE` resolve. O defeito que este item existe para
impedir é a exclusão SILENCIOSA: um painel que passa a somar só a raia real e
não diz que descartou doze turnos transformou uma decisão de leitura num número,
e ninguém consegue conferir um denominador que não aparece.
"""
from __future__ import annotations

import pytest

from dna.runtime.roi import (
    ModelPrice,
    Sample,
    read_yield,
    render,
    sample_from_turns,
)
from dna.runtime.telemetry import LANE_REAL, LANE_TEST, LANES

PRECOS = {"gpt-5-mini": ModelPrice(0.25, 2.0, "USD")}


def _turno(**kw) -> dict:
    linha = {
        "model": "gpt-5-mini",
        "input_tokens": 1000,
        "output_tokens": 500,
        "tokens_partial": False,
        "outcome": "",
        "lane": "",
        "status": "ok",
    }
    linha.update(kw)
    return linha


# ── o vocabulário, e a recusa ────────────────────────────────────────────────


def test_o_vocabulario_de_raia_NAO_e_uma_segunda_copia():
    """`roi` importa `LANES` de `telemetry`, e não redigita as duas palavras.

    A mesma disciplina de `OUTCOMES` e `DECISIONS`, e pela mesma razão: duas
    listas do mesmo vocabulário divergem, e a divergência só aparece quando
    alguém acrescenta uma raia nova de um lado só.
    """
    import dna.runtime.roi as roi
    import dna.runtime.telemetry as telemetry

    assert roi.LANES is telemetry.LANES


def test_o_VAZIO_nao_e_uma_raia_do_vocabulario():
    """⭐ Vazio é a AUSÊNCIA de declaração, e pô-lo na lista o tornaria uma.

    Se `""` fosse membro de `LANES`, `_raia` o deixaria passar como valor
    válido e a distinção inteira desta issue morreria na porta de entrada.
    """
    assert "" not in LANES
    assert LANES == {LANE_REAL, LANE_TEST}


def test_uma_raia_INVENTADA_nao_entra_na_conta():
    """`prod`, `staging`, `testing` — nenhum é raia, e nenhum vira uma.

    Contá-los os faria aparecer numa estatística que não sabe o que eles
    significam, e aqui essa estatística é a que decide o que entra na conta de
    alguém.
    """
    amostra = sample_from_turns(
        [_turno(lane="prod"), _turno(lane="testing"), _turno(lane=True)]
    )
    assert amostra.lanes == {"": 3}
    assert amostra.undeclared_lane == 3


def test_a_raia_e_lida_sem_diferenciar_caixa_nem_espaco():
    """` TEST ` é a mesma declaração que `test` — como o desfecho já fazia."""
    assert sample_from_turns([_turno(lane=" TEST ")]).lanes == {LANE_TEST: 1}


# ── contar, e contar o que ficou de fora ─────────────────────────────────────


def test_sem_filtro_a_amostra_conta_TUDO_e_nada_e_excluido():
    amostra = sample_from_turns(
        [_turno(lane=LANE_REAL), _turno(lane=LANE_TEST), _turno()]
    )
    assert amostra.turns == 3
    assert amostra.lanes == {LANE_REAL: 1, LANE_TEST: 1, "": 1}
    assert amostra.lane_filter is None
    assert amostra.excluded_turns == 0
    assert amostra.excluded_by_lane == {}


def test_filtrando_a_raia_real_os_numeros_sao_SO_dela():
    amostra = sample_from_turns(
        [
            _turno(lane=LANE_REAL, input_tokens=100, output_tokens=10),
            _turno(lane=LANE_TEST, input_tokens=9999, output_tokens=9999),
        ],
        lane=LANE_REAL,
    )
    assert amostra.turns == 1
    assert amostra.input_tokens == 100
    assert amostra.output_tokens == 10


def test_a_amostra_filtrada_CONTINUA_sabendo_o_que_ficou_de_fora():
    """⭐ O coração da issue. Filtrar não pode ser esquecer.

    `lanes` é o único campo que NÃO sofre o filtro, e é por isso que
    `excluded_turns` tem de onde sair.
    """
    amostra = sample_from_turns(
        [_turno(lane=LANE_REAL)] * 5
        + [_turno(lane=LANE_TEST)] * 3
        + [_turno()] * 2,
        lane=LANE_REAL,
    )
    assert amostra.turns == 5
    assert amostra.lanes_seen == 10
    assert amostra.excluded_turns == 5
    assert amostra.excluded_by_lane == {LANE_TEST: 3, "": 2}


def test_filtrar_PELA_raia_nao_declarada_e_uma_pergunta_legitima():
    """`lane=""` ≠ `lane=None`: um filtra pelos não classificados, o outro não
    filtra. Colapsar os dois faria "quantos ninguém classificou?" ficar sem
    resposta — e é a pergunta que o dia um deste mecanismo faz."""
    linhas = [_turno(lane=LANE_REAL), _turno(), _turno()]
    assert sample_from_turns(linhas, lane="").turns == 2
    assert sample_from_turns(linhas, lane="").excluded_turns == 1
    assert sample_from_turns(linhas).turns == 3


# ── as três ausências, e nenhuma delas é zero ────────────────────────────────


def test_uma_amostra_SEM_contagem_de_raia_diz_que_NAO_SABE():
    """⚠️ Banco sem a 0014, ou leitor antigo: a raia não foi CONTADA.

    Diferente de "todos sem raia declarada", que é uma medição. Colapsar as
    duas faria a tela afirmar "86 não declarados" sobre uma pergunta que
    ninguém chegou a fazer.
    """
    amostra = Sample(turns=86)  # nenhuma raia contada
    assert amostra.lane_unknown is True
    assert amostra.undeclared_lane == 0
    assert amostra.lanes_seen == 86


def test_uma_amostra_COM_raia_contada_e_toda_vazia_NAO_e_desconhecida():
    amostra = sample_from_turns([_turno()] * 86)
    assert amostra.lane_unknown is False
    assert amostra.undeclared_lane == 86


def test_a_leitura_de_um_banco_sem_a_0014_AVISA_que_pode_conter_exercicio():
    reading = read_yield(Sample(turns=86), prices=PRECOS)
    aviso = _uma_nota_com(reading, "NÃO FOI CONTADA")
    assert "0014" in aviso
    assert "exercício" in aviso


def test_os_86_turnos_MEDIDOS_saem_como_NAO_DECLARADOS_e_nao_como_reais():
    """⭐ O estado medido em 08/08/2026, e a recusa que ele exige.

    86 turnos, nenhum com raia. A leitura não pode chamá-los de `real` (seria
    afirmar uso de cliente sobre turnos que a medição diz serem de agente) nem
    de `test` (difamaria qualquer um que fosse legítimo).
    """
    reading = read_yield(sample_from_turns([_turno()] * 86), prices=PRECOS)
    assert reading.sample.undeclared_lane == 86
    assert reading.sample.lanes.get(LANE_REAL, 0) == 0
    nota = _uma_nota_com(reading, "não declaram raia")
    assert "não é `real`" in nota


# ── o painel NUNCA exclui em silêncio ────────────────────────────────────────


def _uma_nota_com(reading, trecho: str) -> str:
    achadas = [n for n in reading.notes if trecho in n]
    assert achadas, (
        f"nenhuma nota contém {trecho!r}. Notas: {list(reading.notes)}"
    )
    return achadas[0]


def test_uma_conta_que_EXCLUI_diz_quantos_e_de_que_raia():
    """⭐ A regra 3 da issue, e a razão de este arquivo existir."""
    amostra = sample_from_turns(
        [_turno(lane=LANE_REAL)] * 76
        + [_turno(lane=LANE_TEST)] * 12
        + [_turno()] * 2,
        lane=LANE_REAL,
    )
    nota = _uma_nota_com(read_yield(amostra, prices=PRECOS), "ficaram DE FORA")
    assert "76 de 90" in nota
    assert "12 test" in nota
    assert "2 sem raia declarada" in nota


def test_uma_conta_que_nao_exclui_NADA_tambem_o_diz():
    """Dizer "nada foi excluído" não é ruído: a ausência da frase e a ausência
    de exclusão seriam indistinguíveis, e quem lê ficaria sem saber se o
    painel filtra."""
    amostra = sample_from_turns([_turno(lane=LANE_REAL)] * 3, lane=LANE_REAL)
    nota = _uma_nota_com(read_yield(amostra, prices=PRECOS), "nada foi excluído")
    assert LANE_REAL in nota


def test_uma_conta_SEM_filtro_com_raias_MISTURADAS_avisa_que_soma_tudo():
    """Sem filtro o painel soma teste com uso real. Ele pode — mas não pode
    calar, porque o número parece a conta do cliente e não é."""
    amostra = sample_from_turns(
        [_turno(lane=LANE_REAL)] * 4 + [_turno(lane=LANE_TEST)] * 2
    )
    nota = _uma_nota_com(read_yield(amostra, prices=PRECOS), "soma TODAS as raias")
    assert "4 real" in nota
    assert "2 test" in nota


def test_o_aviso_da_raia_vem_ANTES_de_qualquer_outro():
    """Quem lê precisa saber SOBRE O QUE a conta é antes de ler a conta.

    Uma exclusão anunciada no rodapé é lida depois de a decisão já ter sido
    tomada.
    """
    reading = read_yield(
        sample_from_turns(
            [_turno(lane=LANE_REAL)] * 2 + [_turno(lane=LANE_TEST)],
            lane=LANE_REAL,
        ),
        prices=PRECOS,
    )
    assert "ficaram DE FORA" in reading.notes[0]


def test_o_render_poe_a_raia_e_a_exclusao_na_PRIMEIRA_linha():
    """⚠️ A mesma disciplina do `label` de `Number`: um qualificador que não
    aparece na mesma linha do número é um qualificador que ninguém lê. E
    "76 turnos" sem dizer de que raia é a pior versão disso, porque parece
    completo."""
    linhas = render(
        read_yield(
            sample_from_turns(
                [_turno(lane=LANE_REAL)] * 76 + [_turno(lane=LANE_TEST)] * 12,
                lane=LANE_REAL,
            ),
            prices=PRECOS,
        )
    )
    assert "raia real" in linhas[0]
    assert "76 turno(s)" in linhas[0]
    assert "12 turno(s) FORA desta conta" in linhas[0]


def test_sem_filtro_o_render_NAO_inventa_uma_raia_na_primeira_linha():
    """Uma leitura de todas as raias não pode dizer "raia real" — nem "raia
    nenhuma". Ela simplesmente não fala de raia ali, e a nota explica."""
    linhas = render(read_yield(sample_from_turns([_turno()] * 3), prices=PRECOS))
    assert "raia" not in linhas[0]
    assert "FORA desta conta" not in linhas[0]


# ── a raia não contamina o resto da leitura ──────────────────────────────────


def test_um_turno_de_TESTE_excluido_sai_da_conta_de_TOKENS_tambem():
    """Não basta o painel dizer que excluiu: o número tem de mudar. Um filtro
    que só decora a prosa seria o pior dos dois mundos."""
    linhas = [
        _turno(lane=LANE_REAL, input_tokens=100, output_tokens=100),
        _turno(lane=LANE_TEST, input_tokens=5000, output_tokens=5000),
    ]
    tudo = read_yield(sample_from_turns(linhas), prices=PRECOS)
    so_real = read_yield(sample_from_turns(linhas, lane=LANE_REAL), prices=PRECOS)
    assert tudo.tokens.value == 10200
    assert so_real.tokens.value == 200


def test_ZERO_turnos_continua_sendo_NAO_HA_O_QUE_OLHAR_e_a_raia_nao_fala():
    """Uma amostra vazia não ganha uma nota de raia — não há raia a discutir,
    e `nothing_to_look_at` já diz tudo o que há a dizer."""
    reading = read_yield(Sample(), prices=PRECOS)
    assert reading.nothing_to_look_at is True
    assert not [n for n in reading.notes if "raia" in n.lower()]


@pytest.mark.parametrize("raia", sorted(LANES))
def test_qualquer_raia_do_vocabulario_atravessa_a_leitura_inteira(raia):
    """DERIVADO de `LANES`, não enumerado: uma raia nova acrescentada ao
    vocabulário passa a ser exercitada aqui sem ninguém lembrar."""
    amostra = sample_from_turns([_turno(lane=raia)], lane=raia)
    assert amostra.turns == 1
    assert amostra.excluded_turns == 0
    assert read_yield(amostra, prices=PRECOS).tokens.value == 1500
