"""A leitura que cruza custo e rendimento — e as três regras que a decidem.

`Story/s-leitura-do-rendimento` · `Spec/spec-rendimento-do-copiloto`.

Sem banco: a regra é pura de propósito (a mesma fronteira de
`dna.runtime.telemetry`), e é justamente a parte que um teste contra o Postgres
nunca exercita nos casos difíceis — que aqui são todos os casos de AUSÊNCIA.

⭐ **O teste que mais importa é o do vazio.** Medido no Postgres de
desenvolvimento em 08/08/2026: 85 turnos, ZERO com desfecho. A leitura roda
sobre dado vazio no dia um, e o defeito que ela não pode ter é devolver
"contenção 0%" — que afirmaria que o copiloto não resolveu nada, quando o que
houve foi ninguém declarar.
"""
from __future__ import annotations

import pytest

from dna.runtime.roi import (
    CAN_SLEEP_UNDECLARED,
    CONSTANT,
    CURRENCY_MISMATCH,
    DECISIONS,
    DECLARED,
    MEASURED,
    NO_APP,
    NO_APPROVALS,
    NO_MODEL_PRICE,
    NO_OUTCOME_DECLARED,
    NO_TURNS,
    NO_VALUE_PER_OUTCOME,
    PROXY,
    ROWS,
    STANDING_REPLICA_USD_MONTH,
    TECHNIQUE_ANSWERED,
    TECHNIQUES_NOT_ANSWERED,
    ModelPrice,
    NotCalculable,
    Number,
    Sample,
    read_yield,
    render,
    sample_from_turns,
    value_per_outcome,
)

# ── os dublês: linhas como o banco as devolve ────────────────────────────────

PRECOS = {"gpt-5-mini": ModelPrice(0.25, 2.0, "USD")}

COPILOT = {
    "value_per_outcome": {
        "human_minutes": 30,
        "hourly_cost": 60,
        "currency": "USD",
    }
}


def _turno(**kw) -> dict:
    linha = {
        "model": "gpt-5-mini",
        "input_tokens": 1000,
        "output_tokens": 500,
        "tokens_partial": False,
        "outcome": "",
        "status": "ok",
    }
    linha.update(kw)
    return linha


def _aprovacao(decision: str) -> dict:
    return {"decision": decision}


def _respostas(reading) -> list:
    """Todas as respostas da leitura, DERIVADAS de `ROWS` e não enumeradas."""
    return [getattr(reading, campo) for campo, _ in ROWS]


# ── AC 1: com valor declarado e desfechos, sai a conta inteira ───────────────


def test_com_valor_declarado_e_desfechos_a_leitura_da_custo_rendimento_e_razao():
    """AC 1. Três desfechos resolvidos, um escalado, preço declarado."""
    amostra = sample_from_turns(
        [_turno(outcome="resolved") for _ in range(3)]
        + [_turno(outcome="escalated")],
    )
    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)

    assert isinstance(r.cost, Number) and r.cost.unit == "USD"
    # 4 turnos × (1000 × 0,25 + 500 × 2,0) / 1e6
    assert r.cost.value == pytest.approx(4 * (1000 * 0.25 + 500 * 2.0) / 1e6)
    assert isinstance(r.value, Number)
    # 3 resolvidos × 30 min ÷ 60 × 60 USD/h = 90 USD
    assert r.value.value == pytest.approx(90.0)
    assert isinstance(r.ratio, Number) and r.ratio.unit == "×"
    assert r.ratio.value == pytest.approx(r.value.value / r.cost.value)
    assert not r.nothing_to_look_at and not r.no_outcome_declared


def test_o_rendimento_diz_que_o_valor_por_desfecho_foi_DECLARADO():
    """A origem do número tem de dizer de onde ele veio, não só quanto é."""
    amostra = sample_from_turns([_turno(outcome="resolved")])
    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)
    assert r.value.basis == DECLARED
    assert "DECLARADO" in r.value.source


# ── AC 2: sem valor declarado, NÃO CALCULÁVEL — nunca zero ──────────────────


def test_sem_value_per_outcome_o_rendimento_e_NAO_CALCULAVEL_com_o_motivo():
    """AC 2 — a regra 1 da spec, e o mutante mais óbvio desta story."""
    amostra = sample_from_turns([_turno(outcome="resolved")])
    r = read_yield(amostra, copilot={}, prices=PRECOS)

    assert isinstance(r.value, NotCalculable)
    assert r.value.reason == NO_VALUE_PER_OUTCOME
    assert "value_per_outcome" in r.value.missing
    assert r.value.detail.strip()


def test_sem_value_per_outcome_NADA_na_leitura_vira_um_rendimento_zero():
    """⭐ O mutante: `value_per_outcome` ausente virando 0.

    Derivado de `ROWS`, não enumerado: se alguém acrescentar um campo novo que
    fabrique um zero, este teste o pega sem ser editado.
    """
    amostra = sample_from_turns([_turno(outcome="resolved")])
    r = read_yield(amostra, copilot=None, prices=PRECOS)

    for resposta in _respostas(r):
        if isinstance(resposta, Number) and resposta.unit in ("USD", "×"):
            # O único dinheiro que pode existir sem valor declarado é o CUSTO,
            # e ele nunca é zero num turno que gastou token.
            assert resposta.value != 0.0, (
                f"um zero fabricado saiu da leitura: {resposta}"
            )


def test_o_valor_declarado_PELA_METADE_nao_e_meio_valor():
    """Sem `currency`, presumir USD erra por um fator de cinco na primeira
    frota que mistura duas."""
    parcial = value_per_outcome(
        {"value_per_outcome": {"human_minutes": 30, "hourly_cost": 60}}
    )
    assert isinstance(parcial, NotCalculable)
    assert parcial.missing == ("currency",)


def test_um_valor_declarado_ZERO_e_uma_declaracao_e_passa():
    """Ausente não é zero; zero DECLARADO é zero — e a diferença é o ponto."""
    vpo = value_per_outcome(
        {"value_per_outcome": {"human_minutes": 0, "hourly_cost": 60, "currency": "USD"}}
    )
    assert not isinstance(vpo, NotCalculable)
    assert vpo.per_outcome == 0.0


def test_um_valor_declarado_NEGATIVO_e_recusado():
    vpo = value_per_outcome(
        {"value_per_outcome": {"human_minutes": -5, "hourly_cost": 60, "currency": "USD"}}
    )
    assert isinstance(vpo, NotCalculable)


# ── AC 3: a aceitação do HITL é PROXY, com as contagens que a originam ──────


def test_a_taxa_de_aceitacao_vem_rotulada_como_PROXY_com_as_contagens():
    """AC 3 — e a regra 2: o rótulo viaja com o número."""
    amostra = sample_from_turns(
        [_turno()],
        [_aprovacao("approve")] * 20 + [_aprovacao("edit")] * 3,
    )
    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)

    assert isinstance(r.acceptance, Number)
    assert r.acceptance.basis == PROXY
    assert r.acceptance.value == pytest.approx(100 * 20 / 23)
    for pedaco in ("approve 20", "edit 3", "reject 0"):
        assert pedaco in r.acceptance.source
    assert "PROXY" in r.acceptance.source


def test_sem_nenhuma_decisao_a_aceitacao_e_INDEFINIDA_e_nao_zero_por_cento():
    """0% diria que o humano rejeitou tudo. Ninguém decidiu nada."""
    r = read_yield(sample_from_turns([_turno()]), copilot=COPILOT, prices=PRECOS)
    assert isinstance(r.acceptance, NotCalculable)
    assert r.acceptance.reason == NO_APPROVALS


def test_uma_aprovacao_PENDENTE_nao_entra_no_denominador():
    """Pendência não é concordância — e o texto tem de dizer que ela existe."""
    amostra = sample_from_turns([_turno()], [_aprovacao(""), _aprovacao("")])
    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)
    assert isinstance(r.acceptance, NotCalculable)
    assert amostra.undecided == 2
    assert "não" in r.acceptance.detail and "decidida" in r.acceptance.detail


# ── ⭐ regra 3: vazio NÃO pode ser lido como zero ────────────────────────────


def test_ZERO_turnos_e_NAO_HA_O_QUE_OLHAR_e_nao_um_resultado():
    """⭐ A armadilha desta story, e a mesma do PR #354.

    Derivado de `ROWS`: TODA resposta da leitura tem de ser não-calculável.
    """
    r = read_yield(Sample(), copilot=COPILOT, prices=PRECOS)

    assert r.nothing_to_look_at
    for campo, rotulo in ROWS:
        resposta = getattr(r, campo)
        assert isinstance(resposta, NotCalculable), (
            f"{rotulo} devolveu um número sobre ZERO turnos: {resposta}"
        )
    assert r.tokens.reason == NO_TURNS
    assert "NÃO HÁ O QUE OLHAR" in render(r)[0]


def test_85_turnos_e_NENHUM_desfecho_e_o_estado_medido_e_nao_e_contencao_zero():
    """⭐ O estado real do banco de dev em 08/08/2026, e a leitura tem de
    dizer "nenhum turno declarou desfecho" em vez de 0%."""
    amostra = sample_from_turns([_turno() for _ in range(85)])
    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)

    assert r.no_outcome_declared
    assert isinstance(r.containment, NotCalculable)
    assert r.containment.reason == NO_OUTCOME_DECLARED
    assert isinstance(r.value, NotCalculable)
    assert r.value.reason == NO_OUTCOME_DECLARED
    # E o custo CONTINUA saindo: os turnos aconteceram e custaram.
    assert isinstance(r.cost, Number) and r.cost.value > 0
    # ⭐ E a TELA não pode mostrar 0% na linha da contenção. Asserção sobre a
    # LINHA e não sobre o texto inteiro: a explicação ("devolver 0% afirmaria
    # que nada foi resolvido") contém o "0%" de propósito, e é o número
    # renderizado que este teste existe para proibir.
    linhas = render(r)
    linha_contencao = next(l for l in linhas if l.startswith("Contenção:"))
    assert linha_contencao.startswith("Contenção: NÃO CALCULÁVEL")
    assert "[PROXY]" not in linha_contencao, "não há número para rotular"
    linha_rendimento = next(l for l in linhas if l.startswith("Rendimento:"))
    assert linha_rendimento.startswith("Rendimento: NÃO CALCULÁVEL")
    assert any("NENHUM dos 85 turnos declarou desfecho" in l for l in linhas)


def test_um_desfecho_vazio_NUNCA_e_contado_como_resolved():
    """⭐ O mutante: `outcome` vazio contado como `resolved`."""
    amostra = sample_from_turns(
        [_turno(outcome=""), _turno(outcome=None), _turno(outcome="resolved")]
    )
    assert amostra.resolved == 1
    assert amostra.declared_outcomes == 1
    assert amostra.undeclared_outcomes == 2

    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)
    assert r.containment.value == pytest.approx(100.0)  # 1 de 1 DECLARADO
    assert r.value.is_floor, "com 2 turnos sem desfecho o rendimento é um piso"


def test_um_desfecho_INVENTADO_nao_entra_na_conta():
    """`status='ok'` nunca foi um desfecho. `ok`/`sucesso` também não são."""
    amostra = sample_from_turns(
        [_turno(outcome="ok"), _turno(outcome="sucesso"), _turno(outcome="RESOLVED")]
    )
    # Só o terceiro, normalizado, é um desfecho de verdade.
    assert amostra.outcomes == {"resolved": 1}


def test_o_vocabulario_de_desfecho_NAO_e_uma_segunda_copia():
    """A porta de escrita e a de leitura falam a MESMA lista, ou uma delas
    contaria o que a outra recusa."""
    from dna.runtime import roi, telemetry

    assert roi.OUTCOMES is telemetry.OUTCOMES


def test_o_vocabulario_de_decisao_nao_DIVERGE_do_middleware():
    """`DECISIONS` é enumerado; esta é a guarda que impede o drift."""
    import inspect

    from dna.runtime.middleware.hitl import dna_hitl_middleware

    padrao = inspect.signature(dna_hitl_middleware).parameters[
        "allowed_decisions"
    ].default
    assert tuple(padrao) == DECISIONS


# ── o viés: os DOIS zeros de token ──────────────────────────────────────────


def test_um_turno_com_uso_ILEGIVEL_torna_a_conta_um_PISO():
    """⚠️ `tokens_partial = true`: houve chamada e ela não reportou uso. O
    provedor cobrou; somar zero e calar é o que fazia o turno caro parecer
    barato."""
    amostra = sample_from_turns(
        [_turno(tokens_partial=True, input_tokens=0, output_tokens=0)]
    )
    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)

    assert amostra.unreadable_turns == 1
    assert r.tokens.is_floor and r.cost.is_floor
    # E o PISO tem de aparecer na LINHA, não só no objeto: um `is_floor`
    # guardado e omitido na tela é a mesma cegueira do rótulo de proxy.
    linha = next(l for l in render(r) if l.startswith("Tokens:"))
    assert "≥ PISO" in linha
    assert any("ILEG" in n or "não reportou uso" in n for n in r.notes)


def test_um_turno_SEM_chamada_ao_modelo_tem_a_conta_FECHADA_em_zero():
    """Os 7 turnos que morreram em 7–32 ms: zero é a MEDIÇÃO CERTA, e nada
    aqui pode transformá-los em piso."""
    amostra = sample_from_turns(
        [_turno(model="", input_tokens=0, output_tokens=0, tokens_partial=False)]
    )
    assert not amostra.usage_is_floor
    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)
    assert isinstance(r.tokens, Number) and r.tokens.value == 0.0
    assert not r.tokens.is_floor


def test_um_turno_ANTERIOR_a_0012_nao_e_declarado_fechado():
    """`tokens_partial IS NULL` = ninguém estava olhando. Nem `false` nem
    `true` seriam verdade sobre ele."""
    amostra = sample_from_turns([_turno(tokens_partial=None)])
    assert amostra.unknown_usage_turns == 1
    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)
    assert r.tokens.is_floor
    assert any("0012" in n for n in r.notes)


def test_um_modelo_ILEGIVEL_sem_preco_deixa_o_custo_NAO_CALCULAVEL():
    """Um balde com zero token mas turno ilegível PRECISA de preço — sem ele
    nem o piso dá para dizer."""
    amostra = sample_from_turns(
        [_turno(model="claude-x", input_tokens=0, output_tokens=0, tokens_partial=True)]
    )
    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)
    assert isinstance(r.cost, NotCalculable)
    assert r.cost.reason == NO_MODEL_PRICE
    assert "claude-x" in r.cost.missing


# ── o preço: exato em tokens, declarado em dinheiro ─────────────────────────


def test_sem_preco_declarado_o_dinheiro_e_NAO_CALCULAVEL_mas_os_tokens_saem():
    """⭐ A afirmação da spec que o código desmentiu: *"o custo já é exato"*.
    Exata é a contagem de TOKENS; o dinheiro depende de um preço que este
    repositório não guarda em lugar nenhum."""
    amostra = sample_from_turns([_turno()])
    r = read_yield(amostra, copilot=COPILOT, prices=None)

    assert isinstance(r.cost, NotCalculable)
    assert r.cost.reason == NO_MODEL_PRICE
    assert isinstance(r.tokens, Number)
    assert r.tokens.value == 1500 and r.tokens.basis == MEASURED


def test_um_modelo_SEM_preco_nao_produz_um_custo_parcial_menor_que_o_real():
    amostra = sample_from_turns([_turno(), _turno(model="claude-opus-5")])
    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)
    assert isinstance(r.cost, NotCalculable)
    assert r.cost.missing == ("claude-opus-5",)


def test_precos_em_MOEDAS_diferentes_nao_se_somam():
    amostra = sample_from_turns([_turno(), _turno(model="modelo-br")])
    precos = dict(PRECOS, **{"modelo-br": ModelPrice(1.0, 2.0, "BRL")})
    r = read_yield(amostra, copilot=COPILOT, prices=precos)
    assert isinstance(r.cost, NotCalculable)
    assert r.cost.reason == CURRENCY_MISMATCH


def test_a_razao_entre_MOEDAS_diferentes_nao_e_um_numero():
    amostra = sample_from_turns([_turno(outcome="resolved")])
    copilot = {"value_per_outcome": {"human_minutes": 30, "hourly_cost": 300, "currency": "BRL"}}
    r = read_yield(amostra, copilot=copilot, prices=PRECOS)
    assert isinstance(r.ratio, NotCalculable)
    assert r.ratio.reason == CURRENCY_MISMATCH


def test_a_razao_avisa_quando_os_DOIS_lados_sao_pisos():
    """Piso ÷ piso não limita nada, nem por cima nem por baixo."""
    amostra = sample_from_turns(
        [_turno(outcome="resolved", tokens_partial=True), _turno()]
    )
    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)
    assert r.value.is_floor and r.cost.is_floor
    assert any("PISOS" in n for n in r.notes)


# ── o custo fixo do App: CONSTANTE, e rotulada como tal ─────────────────────


def test_um_App_que_NAO_dorme_custa_a_constante_medida_e_ela_diz_que_e_constante():
    """⭐ O mutante: a constante rotulada como medição."""
    amostra = sample_from_turns([_turno()])
    r = read_yield(amostra, copilot=COPILOT, app={"can_sleep": False}, prices=PRECOS)

    assert isinstance(r.standing_cost, Number)
    assert r.standing_cost.value == STANDING_REPLICA_USD_MONTH
    assert r.standing_cost.basis == CONSTANT
    assert r.standing_cost.unit == "USD/mês"
    assert "não" in r.standing_cost.source.lower()
    assert "fatura" in r.standing_cost.source
    assert any("MENSAL" in n and "FORA da razão" in n for n in r.notes)


def test_um_App_que_DORME_nao_carrega_replica_fixa():
    r = read_yield(
        sample_from_turns([_turno()]), copilot=COPILOT, app={"can_sleep": True},
        prices=PRECOS,
    )
    assert isinstance(r.standing_cost, Number) and r.standing_cost.value == 0.0
    assert r.standing_cost.basis == DECLARED


def test_um_App_que_NUNCA_respondeu_nao_vira_o_lado_barato():
    """Presumir `can_sleep: true` esconde exatamente a réplica que ninguém
    decidiu — ~US$ 90/mês, recorrente."""
    r = read_yield(sample_from_turns([_turno()]), copilot=COPILOT, app={}, prices=PRECOS)
    assert isinstance(r.standing_cost, NotCalculable)
    assert r.standing_cost.reason == CAN_SLEEP_UNDECLARED


def test_um_Copilot_sem_runs_in_diz_que_nao_sabe_onde_roda():
    r = read_yield(sample_from_turns([_turno()]), copilot=COPILOT, prices=PRECOS)
    assert isinstance(r.standing_cost, NotCalculable)
    assert r.standing_cost.reason == NO_APP
    assert "runs_in" in r.standing_cost.missing[0]


# ── a regra 2: nenhum número anda sem procedência ───────────────────────────


def test_um_numero_sem_procedencia_conhecida_NAO_CHEGA_A_EXISTIR():
    with pytest.raises(ValueError):
        Number(1.0, "USD", "ACHISMO", "de onde eu quiser")


def test_um_numero_sem_ORIGEM_nao_chega_a_existir():
    with pytest.raises(ValueError):
        Number(1.0, "USD", MEASURED, "   ")


def test_TODO_numero_da_leitura_carrega_procedencia_e_origem():
    """Derivado de `ROWS`: um campo novo sem procedência cai aqui sozinho."""
    amostra = sample_from_turns(
        [_turno(outcome="resolved")], [_aprovacao("approve")]
    )
    r = read_yield(amostra, copilot=COPILOT, app={"can_sleep": False}, prices=PRECOS)
    numeros = [x for x in _respostas(r) if isinstance(x, Number)]
    assert len(numeros) == len(ROWS), "algum campo ficou não-calculável neste caso"
    for n in numeros:
        assert n.basis and n.source.strip()


def test_o_rotulo_de_PROXY_aparece_ONDE_o_numero_aparece():
    """⭐ O mutante: o rótulo de proxy sumindo.

    Guardar `basis=PROXY` no objeto e omiti-lo na tela é a regra 2 cumprida
    onde ninguém olha.
    """
    amostra = sample_from_turns(
        [_turno(outcome="resolved")], [_aprovacao("approve"), _aprovacao("reject")]
    )
    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)
    texto = render(r)

    linha_contencao = next(l for l in texto if l.startswith("Contenção:"))
    linha_aceitacao = next(l for l in texto if l.startswith("Aceitação"))
    assert "[PROXY]" in linha_contencao
    assert "[PROXY]" in linha_aceitacao
    # E o custo, que NÃO é proxy, não pode ser rotulado como se fosse.
    linha_custo = next(l for l in texto if l.startswith("Custo (tokens):"))
    assert "[PROXY]" not in linha_custo and "[MEASURED]" in linha_custo


def test_o_render_diz_QUAL_tecnica_de_mercado_esta_sendo_respondida():
    """DoD: os nomes de mercado, e qual deles a resposta está dando."""
    r = read_yield(sample_from_turns([_turno()]), copilot=COPILOT, prices=PRECOS)
    texto = "\n".join(render(r))
    assert TECHNIQUE_ANSWERED in texto
    for nao_respondida in TECHNIQUES_NOT_ANSWERED:
        assert nao_respondida in texto
    assert "AHT" in texto and "holdout" in texto


def test_a_contencao_diz_a_COBERTURA_da_amostra():
    """5 turnos, 2 com desfecho: a contenção é sobre 2, e o texto diz isso."""
    amostra = sample_from_turns(
        [_turno(outcome="resolved"), _turno(outcome="escalated")]
        + [_turno() for _ in range(3)]
    )
    r = read_yield(amostra, copilot=COPILOT, prices=PRECOS)
    assert r.containment.value == pytest.approx(50.0)
    assert "cobertura 40%" in r.containment.source
    assert "PROXY" in r.containment.source


# ── as duas formas da mesma linha ───────────────────────────────────────────


def test_a_amostra_e_a_MESMA_venha_a_linha_como_Mapping_ou_como_Turn():
    """O cursor devolve `Mapping`; o recorder devolve `Turn`. Uma leitura que
    só entendesse uma das duas leria vazio contra a outra — e vazio, aqui,
    seria lido como zero."""
    from dna.runtime.telemetry import Turn

    como_dict = sample_from_turns(
        [_turno(outcome="resolved", tokens_partial=True)]
    )
    como_turn = sample_from_turns(
        [
            Turn(
                turn_id="t1",
                model="gpt-5-mini",
                input_tokens=1000,
                output_tokens=500,
                tokens_partial=True,
                outcome="resolved",
            )
        ]
    )
    assert como_dict == como_turn


def test_uma_amostra_montada_A_MAO_com_zero_turnos_nao_engana_a_leitura():
    """Alguém pode construir a `Sample` errada; a leitura ainda tem de recusar."""
    r = read_yield(
        Sample(turns=0, outcomes={"resolved": 3}), copilot=COPILOT, prices=PRECOS
    )
    assert r.nothing_to_look_at
    assert isinstance(r.value, NotCalculable)
    assert isinstance(r.containment, NotCalculable)
