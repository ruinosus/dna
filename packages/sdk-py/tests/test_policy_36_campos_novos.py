"""#36 — os campos novos da CognitivePolicy, e o fim dos literais no host.

Três famílias de asserção, na ordem que importa:

1. **Paridade sem doc** — workspace sem política se comporta byte-igual a antes
   (o contrato de todo estágio do épico das nove seções).
2. **Clamps** — política é dado de tenant; um número absurdo declara-se, mas
   não executa.
3. **O defeito do teto** — antes do #36, `retrieval.k` valia na BUSCA e o
   `briefing` refatiava em `MAX_MEMORIES` (3): um k=5 buscava 5 e injetava 3.
"""

from __future__ import annotations

import asyncio

from dna.memory.ingestion import (
    IngestionPolicy,
    extraction_prompt,
    parse_facts,
    resolve_ingestion,
)
from dna.memory.policy import RecallInjection, resolve_recall_injection
from dna.runtime.middleware.recall import briefing


# ── 1. paridade sem doc ─────────────────────────────────────────────────────


def test_sem_doc_a_politica_e_o_default_de_codigo():
    p = resolve_ingestion(None)
    assert p == IngestionPolicy()
    assert p.max_facts_per_turn == 5
    assert p.max_transcript_chars == 4000
    assert p.transcript_messages == 6
    assert p.max_arbitrations == 3
    assert p.arbiter_neighbors_multiplier == 3
    assert p.arbiter_neighbors_cap == 24
    assert p.proposal_markers == ()
    assert p.sdlc_interval_seconds == 21600
    assert p.sdlc_max_items == 12
    assert resolve_recall_injection(None) == RecallInjection()


def test_prompt_de_extracao_sem_doc_e_igual_ao_de_antes():
    # O prompt default menciona o teto — sem doc, o número é o de sempre.
    assert "no máximo 5" in extraction_prompt("decidimos usar Stripe")


# ── 2. o doc vence, o lixo cai no default ───────────────────────────────────


def test_o_doc_vence_e_o_lixo_cai_no_default():
    p = resolve_ingestion(
        {
            "ingestion": {
                "max_facts_per_turn": 2,
                "max_transcript_chars": 99,  # < mínimo 200 → default
                "transcript_messages": 10,
                "max_arbitrations": 0,  # zero é válido: árbitro desligado
                "arbiter_neighbors_multiplier": 2,
                "arbiter_neighbors_cap": 999,  # > 50 → default
                "proposal_markers": [r"\bdecided\b", "", 42],
                "sdlc": {"interval_seconds": 3600, "max_items": "doze"},
            }
        }
    )
    assert p.max_facts_per_turn == 2
    assert p.max_transcript_chars == 4000
    assert p.transcript_messages == 10
    assert p.max_arbitrations == 0
    assert p.arbiter_neighbors_multiplier == 2
    assert p.arbiter_neighbors_cap == 24
    assert p.proposal_markers == (r"\bdecided\b",)
    assert p.sdlc_interval_seconds == 3600
    assert p.sdlc_max_items == 12


def test_parse_facts_respeita_o_teto_do_doc():
    p = resolve_ingestion({"ingestion": {"max_facts_per_turn": 2}})
    fatos = parse_facts('{"facts": ["a", "b", "c", "d"]}', p)
    assert fatos == ["a", "b"]


def test_injection_com_doc_e_com_lixo():
    inj = resolve_recall_injection(
        {
            "recall": {
                "injection": {
                    "max_block_chars": 800,
                    "cue_window": 5,
                    "sticky_overlap": 1.5,  # fora de [0,1] → default
                    "min_signal_chars": "doze",  # lixo → default
                }
            }
        }
    )
    assert inj.max_block_chars == 800
    assert inj.cue_window == 5
    assert inj.sticky_overlap == 0.5
    assert inj.min_signal_chars == 12


# ── 3. o defeito do teto (k buscava 5, injetava 3) ──────────────────────────


def test_briefing_injeta_o_k_do_workspace_nao_o_teto_de_codigo():
    memorias = [f"memória número {i} com texto suficiente" for i in range(5)]
    bloco = briefing(memorias, max_memories=5, max_chars=10_000)
    assert bloco.count("memória número") == 5
    # e o default continua sendo o conservador de sempre
    assert briefing(memorias).count("memória número") == 3


def test_middleware_le_k_e_injecao_da_mesma_leitura():
    from dna.runtime.middleware.recall import DnaRecallMiddleware

    async def spec():
        return {
            "recall": {
                "retrieval": {"k": 7},
                "injection": {"cue_window": 5, "max_block_chars": 300},
            }
        }

    mw = DnaRecallMiddleware(policy_source=spec)
    k, inj = asyncio.run(mw._politica_viva())
    assert k == 7
    assert inj.cue_window == 5 and inj.max_block_chars == 300


def test_middleware_sem_policy_source_usa_os_defaults():
    from dna.runtime.middleware.recall import DnaRecallMiddleware

    mw = DnaRecallMiddleware()
    k, inj = asyncio.run(mw._politica_viva())
    assert k == 3
    assert inj == RecallInjection()
