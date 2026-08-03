"""`CognitivePolicy.intel` — o tuning do motor de intel como dado (#36/#33).

As mesmas três famílias do épico: paridade sem doc, clamps, e o fio medido
pelo comportamento (não pela existência do campo).
"""

from __future__ import annotations

from dna.extensions.intel.ranker import score
from dna.extensions.intel.scoring import IntelScoring, resolve_intel_scoring


def test_sem_doc_a_politica_e_o_default():
    pol = resolve_intel_scoring(None)
    assert pol == IntelScoring()
    assert pol.action_bar == 0.85
    assert pol.evidence_weights["evidence-based"] == 0.25
    assert pol.dedup_cosine_threshold == 0.97


def test_o_doc_vence_e_o_lixo_cai_no_default():
    pol = resolve_intel_scoring(
        {
            "intel": {
                "action_bar": 0.7,
                "ranker": {
                    "base": 0.5,
                    "pir_match": 7,  # fora de [0,1] → default
                    "evidence_weights": {"evidence-based": 0.4, "anecdotal": "x"},
                },
                "dedup": {"cosine_threshold": 0.3},  # < 0.5 → default
                "feedback": {"dismiss_penalty": 0.9},
            }
        }
    )
    assert pol.action_bar == 0.7
    assert pol.ranker_base == 0.5
    assert pol.ranker_pir_match == 0.15
    assert pol.evidence_weights["evidence-based"] == 0.4
    assert pol.evidence_weights["anecdotal"] == 0.0
    assert pol.dedup_cosine_threshold == 0.97
    assert pol.feedback_dismiss_penalty == 0.9


def test_ranker_sem_scoring_e_byte_igual_ao_de_antes():
    cand = {"action": "faça X", "evidence_rating": "evidence-based", "pirs": ["a"]}
    fonte = {"pirs": ["a"]}
    antes = score(cand, fonte)
    depois = score(cand, fonte, scoring=None)
    assert float(antes) == float(depois) == 1.0
    assert antes.rationale == depois.rationale


def test_ranker_com_scoring_do_workspace():
    cand = {"action": "faça X", "evidence_rating": "evidence-based", "pirs": []}
    pol = resolve_intel_scoring(
        {"intel": {"ranker": {"base": 0.1, "has_action": 0.1,
                              "evidence_weights": {"evidence-based": 0.1}}}}
    )
    s = score(cand, {}, scoring=pol)
    assert abs(float(s) - 0.3) < 1e-9


def test_analyzer_honra_prompt_overrides_e_valida_material():
    from dna.extensions.intel.analyzer import LLMAnalyzer

    capturado = {}

    class _Client:
        class chat:  # noqa: N801 — espelha o shape do openai
            class completions:  # noqa: N801
                @staticmethod
                def create(**kw):
                    capturado.update(kw)

                    class _R:
                        choices = [
                            type(
                                "C", (), {"message": type("M", (), {"content": '{"insights": []}'})()}
                            )()
                        ]

                    return _R()

    az = LLMAnalyzer(client=_Client())
    fonte = {"name": "f", "type": "repo", "pirs": []}

    # override VÁLIDO ({material} presente) vence o default
    az.analyze(fonte, {"prompt_overrides": {
        "system": "Você é o analista DESTA casa.",
        "template": "Analise só isto: {material} (até {k})",
    }, "notes": "material aqui"})
    assert capturado["messages"][0]["content"] == "Você é o analista DESTA casa."
    assert "Analise só isto:" in capturado["messages"][1]["content"]

    # override SEM {material} é ignorado — analisaria o nada
    az.analyze(fonte, {"prompt_overrides": {"template": "sem a variavel"}})
    assert "Research material" in capturado["messages"][1]["content"]
