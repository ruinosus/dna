"""Capacidade de deployment — a regra, exercitada sem rede.

O módulo sob teste não mede nada: ele carrega o vocabulário e a REGRA. Medir é
I/O e mora em quem tem o cliente — o mesmo desenho de `agent_grant`, e pelo mesmo
motivo: uma regra que precisa de rede para ser exercitada é uma regra cujos casos
difíceis ninguém roda.
"""
from __future__ import annotations

import pytest

from dna.runtime.capabilities import (
    CAPABILITIES,
    CAPABILITY_CODE_INTERPRETER,
    CAPABILITY_IMAGE_GENERATION,
    CAPABILITY_INPUT_FILE,
    CapabilityReport,
    MissingCapability,
    report_from_probe,
    require_capabilities,
)

AGORA = "2026-08-02T12:00:00Z"


def _relatorio(**suportado) -> CapabilityReport:
    return CapabilityReport(
        endpoint="https://exemplo/openai/v1/",
        deployment="gpt-5-mini",
        supported=suportado,
        measured_at=AGORA,
    )


# ── a regra ─────────────────────────────────────────────────────────────────


def test_o_que_o_deployment_tem_passa():
    require_capabilities(_relatorio(input_file=True), [CAPABILITY_INPUT_FILE])


def test_o_que_falta_LEVANTA_antes_de_executar():
    """Antes, e não no meio: a alternativa é o provider recusar durante a
    chamada, e aí a recusa chega como falha de stream sem nomear o que faltava."""
    with pytest.raises(MissingCapability) as exc:
        require_capabilities(
            _relatorio(input_file=True, image_generation=False),
            [CAPABILITY_IMAGE_GENERATION],
        )
    assert exc.value.missing == [CAPABILITY_IMAGE_GENERATION]
    assert exc.value.deployment == "gpt-5-mini"


def test_DESCONHECIDO_dentro_de_um_relatorio_conta_como_ausente():
    """Ausência FECHA, como em todo portão deste SDK.

    Otimismo aqui trocaria uma recusa clara no início por uma falha no meio do
    stream — que é onde este produto já aprendeu que dói mais.
    """
    with pytest.raises(MissingCapability):
        require_capabilities(_relatorio(input_file=True), [CAPABILITY_CODE_INTERPRETER])


def test_SEM_relatorio_nenhum_NAO_bloqueia():
    """⚠️ A assimetria com o teste acima é deliberada, e é a parte que se erra.

    Dentro de um relatório, desconhecido fecha — mediu-se o resto e aquilo não
    apareceu. SEM relatório, não há medição a interpretar: transformar "ninguém
    mediu" em "não pode" quebraria todo deployment que ainda não rodou a sonda,
    inclusive os que suportam tudo.
    """
    require_capabilities(None, [CAPABILITY_IMAGE_GENERATION])


def test_exigir_NADA_nunca_bloqueia():
    require_capabilities(None, [])
    require_capabilities(_relatorio(), [])


def test_uma_capacidade_DESCONHECIDA_e_erro_de_programacao():
    """O vocabulário é fechado de propósito: um nome livre viraria uma exigência
    que nenhuma sonda consegue satisfazer nem refutar — e o agente ficaria
    permanentemente recusado por um typo."""
    with pytest.raises(ValueError, match="desconhecida"):
        require_capabilities(_relatorio(input_file=True), ["desenha_bem"])


def test_a_recusa_carrega_o_MOTIVO_do_provider():
    """É o que torna a recusa acionável. "Não suportado" manda adivinhar; o
    texto do provider nomeia o deployment que falta."""
    r = CapabilityReport(
        endpoint="https://exemplo/openai/v1/",
        deployment="gpt-5-mini",
        supported={CAPABILITY_IMAGE_GENERATION: False},
        measured_at=AGORA,
        reasons={CAPABILITY_IMAGE_GENERATION: "The API deployment does not exist"},
    )
    with pytest.raises(MissingCapability) as exc:
        require_capabilities(r, [CAPABILITY_IMAGE_GENERATION])
    assert "does not exist" in str(exc.value)
    assert exc.value.reasons[CAPABILITY_IMAGE_GENERATION]


def test_a_recusa_carrega_os_DADOS_para_quem_a_trata():
    """A mensagem é para humano; os campos são para código. Parse de texto de
    erro quebra na primeira melhoria de redação — a mesma forma do GrantRefused."""
    with pytest.raises(MissingCapability) as exc:
        require_capabilities(_relatorio(), list(CAPABILITIES))
    assert set(exc.value.missing) == CAPABILITIES


# ── a leitura da sonda ──────────────────────────────────────────────────────


def test_a_saida_da_sonda_vira_relatorio():
    r = report_from_probe(
        {
            "endpoint": "https://hub/openai/v1/",
            "modelo": "gpt-5.4",
            "capacidades": {
                "input_file": {"ok": True, "motivo": ""},
                "code_interpreter": {"ok": True, "motivo": ""},
                "image_generation": {"ok": False, "motivo": "deployment não existe"},
            },
        },
        measured_at=AGORA,
    )
    assert r.deployment == "gpt-5.4"
    assert r.has(CAPABILITY_INPUT_FILE)
    assert not r.has(CAPABILITY_IMAGE_GENERATION)
    assert r.missing == [CAPABILITY_IMAGE_GENERATION]
    assert r.reasons[CAPABILITY_IMAGE_GENERATION] == "deployment não existe"


def test_uma_capacidade_que_o_SDK_nao_conhece_e_IGNORADA():
    """A sonda pode ser mais nova que o runtime que lê o resultado. Estourar aí
    faria uma sonda atualizada derrubar um runtime que estava funcionando."""
    r = report_from_probe(
        {
            "endpoint": "e",
            "modelo": "m",
            "capacidades": {
                "input_file": {"ok": True},
                "capacidade_do_futuro": {"ok": True},
            },
        },
        measured_at=AGORA,
    )
    assert r.has(CAPABILITY_INPUT_FILE)
    assert "capacidade_do_futuro" not in r.supported


def test_o_relatorio_carrega_QUANDO_foi_medido():
    """Capacidade sem data é afirmação sem validade: o provider ganha formatos e
    perde deployments, e quem lê precisa poder decidir se confia."""
    r = report_from_probe({"endpoint": "e", "modelo": "m", "capacidades": {}}, measured_at=AGORA)
    assert r.measured_at == AGORA


def test_a_chave_e_o_PAR_endpoint_deployment():
    """MEDIDO em 02/08: o mesmo `gpt-5-mini` tem `image_generation` num recurso e
    não noutro. Uma chave só com o nome do modelo daria a mesma resposta para os
    dois — que é exatamente por que uma tabela por modelo não serve."""
    a = report_from_probe(
        {"endpoint": "https://a/", "modelo": "gpt-5-mini",
         "capacidades": {"image_generation": {"ok": False}}}, measured_at=AGORA)
    b = report_from_probe(
        {"endpoint": "https://b/", "modelo": "gpt-5-mini",
         "capacidades": {"image_generation": {"ok": True}}}, measured_at=AGORA)
    assert a.deployment == b.deployment
    assert a.endpoint != b.endpoint
    assert a.has(CAPABILITY_IMAGE_GENERATION) != b.has(CAPABILITY_IMAGE_GENERATION)
