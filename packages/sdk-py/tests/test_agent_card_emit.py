"""Saída: um documento `Agent` projetado num Agent Card do A2A.

É `emit` — a tese que o DNA já tem: projetar um documento num artefato que um
sistema externo consome (`dna.emit.mcp_ui`, `dna.emit.frontend`). Um Agent Card é
mais um alvo, não um mecanismo novo. É o lado que permite OUTRO sistema delegar
PARA nós.

O módulo devolve o Card; QUEM o serve e em qual path é decisão de deployment
(`/.well-known/` é convenção de raiz de domínio, e a raiz não é do SDK).
"""
from __future__ import annotations

from dna.emit.agent_card import agent_card_for

_AGENT = {
    "kind": "Agent",
    "metadata": {"name": "converter-agent", "description": "Converte arquivos"},
    "spec": {
        "instruction": "…",
        "model": "gpt-5-mini",
        "delegation_target_for": {
            "agents": ["supervisor-agent"],
            "use_when": "o usuário anexou um arquivo",
            "purpose": "Registra um arquivo como documento tipado",
        },
    },
}


def test_the_required_a2a_fields_are_present():
    card = agent_card_for(_AGENT, base_url="https://dna.example")
    for field in (
        "name",
        "description",
        "supportedInterfaces",
        "version",
        "capabilities",
        "defaultInputModes",
        "defaultOutputModes",
        "skills",
    ):
        assert field in card, f"Card sem {field} não é um Card válido do A2A 1.0"


def test_streaming_e_DERIVADO_do_que_o_executor_faz():
    """Fixo em `True`, `capabilities.streaming` era promessa sem nada atrás — o
    Card anunciava uma capacidade que ninguém tinha implementado. Quem monta a
    face sabe o que o executor faz, e é quem responde por isso."""
    assert agent_card_for(_AGENT, base_url="https://dna.example")["capabilities"] == {
        "streaming": False
    }
    assert agent_card_for(_AGENT, base_url="https://dna.example", streaming=True)[
        "capabilities"
    ] == {"streaming": True}


def test_the_skills_derive_from_the_agents_tools():
    """Derivar, não enumerar: o Card não mantém uma lista paralela do que o
    agente sabe fazer. Troque para uma lista à mão e ela ficará velha em
    silêncio — o modo de falha que este projeto já viu várias vezes."""
    card = agent_card_for(_AGENT, tools=("author_kind", "list_kinds"), base_url="https://x")
    assert {s["id"] for s in card["skills"]} == {"author_kind", "list_kinds"}


def test_the_purpose_becomes_the_description_when_present():
    """`purpose`/`use_when` do bloco de delegação existem para um delegador
    escolher alvo. É exatamente o que um Card comunica."""
    card = agent_card_for(_AGENT, base_url="https://x")
    assert "Registra um arquivo" in card["description"]


def test_no_credential_is_ever_projected():
    """O Card sai; segredo não sai com ele."""
    card = agent_card_for(_AGENT, base_url="https://x")
    flat = repr(card).lower()
    for leak in ("bearer ", "sk-", "api_key", "password", "secret"):
        assert leak not in flat


# ── conformidade: o Card é lido pelo PARSER OFICIAL ─────────────────────────
#
# O teste que a versão à mão não tinha. Um Card que nós mesmos validamos contra
# a nossa leitura da spec é uma tautologia; um Card que o `a2a-sdk` faz o parse
# é um fato. Foi exatamente aqui que a versão à mão falhou: emitia
# `{"transport": "jsonrpc"}` e a 1.0 pede `protocolBinding: "JSONRPC"` — então o
# `ClientFactory` oficial achava ZERO interfaces e não conseguia nos chamar.

import pytest  # noqa: E402

pytest.importorskip("a2a", reason="a conformidade se mede contra o SDK oficial")


def test_o_card_projetado_e_lido_pelo_parser_oficial_sem_perda():
    from google.protobuf import json_format

    from a2a.types import AgentCard

    card = agent_card_for(_AGENT, tools=["review_kind", "list_stories"],
                          base_url="https://dna.example/a2a")

    # ParseDict é ESTRITO: um campo desconhecido levanta. É essa severidade que
    # transforma o teste numa medição de conformidade em vez de um smoke test.
    proto = json_format.ParseDict(card, AgentCard())

    assert proto.name == "converter-agent"
    assert [s.id for s in proto.skills] == ["list_stories", "review_kind"]


def test_a_interface_declara_o_binding_que_o_cliente_oficial_procura():
    """O `ClientFactory` filtra por `protocol_binding`; um Card com o nome
    errado do campo produz zero candidatos e um cliente que não nos alcança."""
    from google.protobuf import json_format

    from a2a.client.client_factory import ClientFactory
    from a2a.types import AgentCard
    from a2a.utils.constants import PROTOCOL_VERSION_1_0, TransportProtocol

    card = agent_card_for(_AGENT, base_url="https://dna.example/a2a")
    proto = json_format.ParseDict(card, AgentCard())

    escolhida = ClientFactory._find_best_interface(
        list(proto.supported_interfaces),
        protocol_bindings=[TransportProtocol.JSONRPC],
    )
    assert escolhida is not None, "o cliente oficial não achou interface alguma"
    assert escolhida.url == "https://dna.example/a2a"
    assert escolhida.protocol_version == PROTOCOL_VERSION_1_0
