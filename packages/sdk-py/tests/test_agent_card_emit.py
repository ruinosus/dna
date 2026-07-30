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


def test_streaming_is_advertised_because_AG_UI_already_streams():
    card = agent_card_for(_AGENT, base_url="https://dna.example")
    assert card["capabilities"]["streaming"] is True


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
