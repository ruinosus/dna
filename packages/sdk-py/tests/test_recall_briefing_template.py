"""O briefing do recall como CATÁLOGO (varredura voz-é-dado, 03/08).

A voz de maior tráfego do produto: o template `memory-recall-briefing`
({memories}) vence quando presente; ausente/sem a variável, vale o default —
e o default continua dirigindo o modelo (REGRA/recall)."""
from dna.runtime.middleware.recall import BRIEFING_TEMPLATE, briefing


def _mem(texto):
    return {"summary": texto, "memory_type": "semantic"}


def test_template_vence_e_default_cobre():
    ms = [_mem("O prazo é 60 dias")]
    custom = briefing(ms, template="CONTEXTO:\n{memories}\nFIM")
    assert custom.startswith("CONTEXTO:") and "60 dias" in custom
    # template sem a variável = inválido → default
    fallback = briefing(ms, template="sem variável nenhuma")
    assert "recall" in fallback and "60 dias" in fallback
    assert briefing([], template="CONTEXTO:{memories}") == ""


def test_nome_de_catalogo_e_o_contrato():
    assert BRIEFING_TEMPLATE == "memory-recall-briefing"
