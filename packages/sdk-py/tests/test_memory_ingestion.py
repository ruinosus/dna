"""A memória se alimenta da conversa — e se CORRIGE."""
from __future__ import annotations

import json

from dna.memory.ingestion import (
    ADD,
    INVALIDATE,
    MAX_FACTS,
    NONE,
    UPDATE,
    IngestionPolicy,
    extraction_prompt,
    parse_decisions,
    parse_facts,
    reconciliation_prompt,
    resolve_ingestion,
    worth_extracting,
)


# ── a maioria dos turnos NÃO produz memória ─────────────────────────────────


def test_um_turno_TRIVIAL_nao_gasta_chamada():
    """⚠️ Mede ANTES de gastar. O custo por turno é o que transforma uma boa
    feature numa linha de fatura que ninguém vê subir."""
    for trivial in ("ok", "obrigado!", "oi", "pode seguir", "   ", None):
        assert worth_extracting(trivial) is False


def test_uma_AFIRMACAO_duravel_vale_a_chamada():
    assert worth_extracting("decidimos que o prazo de renovacao passa a ser 60 dias")


def test_o_few_shot_ENSINA_a_nao_extrair():
    """Sem isso o modelo produz um fato por turno porque foi o que se pediu — e
    a memória vira um diário."""
    p = extraction_prompt("qualquer conversa")
    assert '"facts": []' in p
    assert "A resposta mais comum é uma lista VAZIA" in p


# ── a política manda ────────────────────────────────────────────────────────


def test_a_politica_pode_DESLIGAR_a_ingestao():
    desligada = IngestionPolicy(enabled=False)
    assert worth_extracting("decidimos que o prazo passa a ser 60 dias", desligada) is False


def test_uma_fonte_AUSENTE_nunca_e_lida():
    """⚠️ `sources` é ALLOWLIST, não preferência. É o campo que decide o que o
    agente pode aprender sobre as pessoas do workspace."""
    so_sdlc = IngestionPolicy(sources=("sdlc",))
    assert worth_extracting("decidimos que o prazo passa a ser 60 dias", so_sdlc) is False


def test_trigger_batch_nao_extrai_no_turno():
    lote = IngestionPolicy(trigger="batch")
    assert worth_extracting("decidimos que o prazo passa a ser 60 dias", lote) is False


def test_politica_AUSENTE_cai_nos_defaults_declarados():
    """Uma configuração que não carrega não pode LIGAR nada: o modo de falha
    seguro é o comportamento declarado no código, não "faça o que quiser"."""
    p = resolve_ingestion(None)
    assert (p.enabled, p.sources, p.trigger, p.require_approval) == (
        True, ("chat",), "per_turn", False,
    )
    assert resolve_ingestion({"ingestion": "nao e objeto"}).trigger == "per_turn"


def test_a_politica_do_workspace_e_lida():
    p = resolve_ingestion({
        "ingestion": {"enabled": True, "sources": ["chat", "sdlc"],
                      "trigger": "batch", "min_signal_chars": 40,
                      "require_approval": True},
        "memory": {"policies": [{"remember": {"never": ["salário"], "always": ["prazo"]}}]},
    })
    assert p.sources == ("chat", "sdlc") and p.trigger == "batch"
    assert p.require_approval is True and p.min_signal_chars == 40
    assert p.never == ("salário",) and p.always == ("prazo",)


def test_o_NEVER_e_filtro_e_nao_so_instrucao():
    """⚠️ Instrução é pedido; filtro é garantia. Um modelo que ignore o prompt
    não pode conseguir gravar o que o workspace proibiu."""
    p = IngestionPolicy(never=("salário",))
    assert extraction_prompt("x", p).count("salário") == 1
    assert parse_facts('{"facts": ["O salário do João é 10k", "O prazo é 60 dias"]}', p) == [
        "O prazo é 60 dias"
    ]


# ── a reconciliação, que é o que torna a etapa 1 segura ─────────────────────


def test_o_prompt_de_reconciliacao_oferece_as_QUATRO_operacoes():
    p = reconciliation_prompt(["novo fato"], [{"id": "m1", "summary": "antigo"}])
    for op in (ADD, UPDATE, INVALIDATE, NONE):
        assert op in p
    assert "m1" in p and "antigo" in p


def test_ele_PREFERE_update_a_add():
    """Duas memórias sobre a mesma coisa fazem o agente servir as duas versões e
    parecer confuso — e o recall automático serve as duas."""
    assert "Prefira" in reconciliation_prompt(["x"], [])


def test_INVALIDATE_e_descrito_como_REVERSIVEL():
    """Apagar de verdade tiraria a capacidade de responder "por que o agente
    achava X em março?" — metade do valor de uma memória auditável."""
    p = reconciliation_prompt(["x"], [])
    assert "não é apagada" in p


def test_uma_operacao_DESCONHECIDA_vira_none_e_nunca_add():
    """⚠️ O default FECHA. Um modelo que invente `"merge"` não pode virar uma
    escrita que ninguém revisou."""
    [d] = parse_decisions('{"decisions": [{"op": "merge", "text": "x"}]}')
    assert d.op == NONE


def test_uma_operacao_SEM_o_que_precisa_e_inerte():
    """Melhor perder um fato que executar um `update` sem alvo."""
    assert parse_decisions('{"decisions": [{"op": "add"}]}') == []
    assert parse_decisions('{"decisions": [{"op": "update", "text": "x"}]}') == []
    assert parse_decisions('{"decisions": [{"op": "invalidate"}]}') == []


def test_as_quatro_operacoes_bem_formadas_passam():
    ds = parse_decisions(json.dumps({"decisions": [
        {"op": "add", "text": "fato novo"},
        {"op": "update", "id": "m1", "text": "fato corrigido"},
        {"op": "invalidate", "id": "m2", "reason": "contradito"},
        {"op": "none"},
    ]}))
    assert [d.op for d in ds] == [ADD, UPDATE, INVALIDATE, NONE]
    assert ds[1].memory_id == "m1" and ds[2].reason == "contradito"


# ── ler o que o modelo devolveu ─────────────────────────────────────────────


def test_JSON_em_cerca_de_markdown_e_lido():
    """Modelos embrulham JSON em ```json com frequência suficiente para que
    tratar isso como erro signifique perder fatos por formatação."""
    assert parse_facts('```json\n{"facts": ["um fato"]}\n```') == ["um fato"]


def test_resposta_INESPERADA_devolve_vazio_e_nunca_lixo():
    """⚠️ Lixo aqui vira memória, e memória vira prompt: um parse permissivo não
    custa um erro, custa o agente afirmando bobagem com confiança."""
    for ruim in (None, "desculpe, nao entendi", '{"outra": "coisa"}', 42):
        assert parse_facts(ruim) == []
        assert parse_decisions(ruim) == []


def test_ha_TETO_de_fatos_por_turno():
    """Uma conversa não produz dez fatos duráveis; um modelo que devolve dez
    está inventando."""
    muitos = json.dumps({"facts": [f"fato {i}" for i in range(50)]})
    assert len(parse_facts(muitos)) == MAX_FACTS


# ── a fonte sdlc ────────────────────────────────────────────────────────────


def test_o_digest_do_board_e_TITULO_e_resultado_nao_o_yaml():
    """⚠️ O fato durável de uma história entregue é o que ela MUDOU, não o
    registro do processo. O documento inteiro faria o extrator achar fatos
    sobre o board, não sobre o trabalho."""
    from dna.memory.ingestion import sdlc_digest

    d = sdlc_digest(
        [
            {"spec": {"title": "Billing por uso", "outcome": "Stripe metered ligado"}},
            # O shape do digest retrospectivo: title no TOPO, sem spec.
            {"kind": "Story", "name": "s-x", "title": "Sem resultado registrado"},
            {"spec": {"outcome": "sem titulo, nao entra"}},
        ],
        decided=[{"kind": "ADR", "name": "adr-1", "title": "Postgres, nao Cosmos"}],
    )
    assert "entregue: Billing por uso — Stripe metered ligado" in d
    assert "entregue: Sem resultado registrado" in d
    assert "decidido: Postgres, nao Cosmos" in d
    assert "nao entra" not in d


def test_o_digest_tem_TETO():
    from dna.memory.ingestion import SDLC_MAX_ITEMS, sdlc_digest

    d = sdlc_digest([{"title": f"h{i}"} for i in range(50)])
    assert d.count("entregue:") == SDLC_MAX_ITEMS


# ── templates do workspace (PromptTemplate de nome bem conhecido) ───────────


def test_o_template_do_workspace_VENCE_o_default():
    from dna.memory.ingestion import extraction_prompt, reconciliation_prompt

    p = extraction_prompt("a conversa", template="Extraia disto: {transcript}")
    assert p == "Extraia disto: a conversa"
    r = reconciliation_prompt(
        ["fato"], [{"id": "m1", "summary": "velho"}],
        template="NOVOS {facts} vs ATUAL {memories}",
    )
    assert '"fato"' in r and '"m1"' in r and r.startswith("NOVOS ")


def test_template_SEM_variavel_obrigatoria_cai_no_default_nao_no_vazio():
    """⚠️ Um template sem {transcript} extrairia de NADA, para sempre e em
    silêncio. A recusa cai no default testado — nunca no texto quebrado."""
    from dna.memory.ingestion import extraction_prompt, reconciliation_prompt

    p = extraction_prompt("a conversa", template="sem variavel nenhuma")
    assert "a conversa" in p and "FATOS DURÁVEIS" in p
    r = reconciliation_prompt(["f"], [], template="so tem {facts}")
    assert "MEMÓRIA ATUAL" in r


def test_o_preenchimento_NAO_quebra_com_chaves_de_JSON_no_template():
    """`str.format` quebraria em qualquer exemplo JSON do template; a
    substituição é literal de propósito."""
    from dna.memory.ingestion import extraction_prompt

    t = 'Responda {"facts": []} apos ler: {transcript}'
    assert extraction_prompt("x", template=t) == 'Responda {"facts": []} apos ler: x'


def test_template_vazio_ou_nao_string_e_ignorado():
    from dna.memory.ingestion import extraction_prompt

    assert "FATOS DURÁVEIS" in extraction_prompt("x", template="   ")
    assert "FATOS DURÁVEIS" in extraction_prompt("x", template=None)


def test_neighbors_vem_da_POLITICA_nao_do_codigo():
    from dna.memory.ingestion import resolve_ingestion

    assert resolve_ingestion({"ingestion": {"neighbors": 20}}).neighbors == 20
    assert resolve_ingestion(None).neighbors == 8
    # Zero seria reconciliar contra nada — gravaria duplicata sempre.
    assert resolve_ingestion({"ingestion": {"neighbors": 0}}).neighbors == 1
