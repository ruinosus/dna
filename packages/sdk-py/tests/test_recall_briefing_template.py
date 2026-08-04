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


# ── E1 do épico: recall.retrieval.k liga o fio ─────────────────────────────


import pytest

from dna.runtime.middleware.recall import DnaRecallMiddleware


@pytest.mark.asyncio
async def test_k_do_doc_vence_o_limit_do_construtor():
    """`recall.retrieval.k` sempre existiu no schema (default 5) enquanto o
    middleware fixava 3 — dois números para a mesma pergunta (varredura
    03/08). Com doc, vale o doc; sem doc/lixo, vale o construtor."""

    async def policy():
        return {"recall": {"retrieval": {"k": 7}}}

    mw = DnaRecallMiddleware(recall=lambda q, k: None, policy_source=policy)
    assert await mw._k_vivo() == 7

    async def lixo():
        return {"recall": {"retrieval": {"k": "sete"}}}

    mw2 = DnaRecallMiddleware(recall=lambda q, k: None, policy_source=lixo)
    assert await mw2._k_vivo() == mw2._limit

    async def explode():
        raise RuntimeError("fora do ar")

    mw3 = DnaRecallMiddleware(recall=lambda q, k: None, policy_source=explode)
    assert await mw3._k_vivo() == mw3._limit

    mw4 = DnaRecallMiddleware(recall=lambda q, k: None)  # sem hook
    assert await mw4._k_vivo() == mw4._limit


@pytest.mark.asyncio
async def test_k_fora_da_sanidade_cai_no_default():
    for ruim in (0, -3, 51, 10**6):
        async def policy(v=ruim):
            return {"recall": {"retrieval": {"k": v}}}

        mw = DnaRecallMiddleware(recall=lambda q, k: None, policy_source=policy)
        assert await mw._k_vivo() == mw._limit, ruim
