"""Entrada: um Agent Card de terceiro vira um `RemoteAgent` INERTE.

Registrar um agente passa a ser escrever uma instância — sem deploy, sem edição
de código. E inerte é a palavra que carrega o desenho: um remoto só é delegável
depois que um humano aprova, pelo mesmo funil dos Kinds autorados. Sem isso,
"buscar um Card" seria "conceder acesso a dado do workspace" numa chamada HTTP.
"""
from __future__ import annotations

import asyncio

import pytest

from dna.application.a2a_ingest import card_to_spec, ingest_card

_CARD = {
    "name": "invoice-reader",
    "description": "Reads invoices",
    "version": "2.1.0",
    # A forma REAL da 1.0. A fixture dizia `{"transport": "jsonrpc"}` — um campo
    # que não existe na especificação — e por isso o teste passava contra um
    # Card que nenhum servidor A2A publica.
    "supportedInterfaces": [
        {
            "url": "https://vendor.example/a2a",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        }
    ],
    "capabilities": {"streaming": True, "pushNotifications": False},
    "skills": [
        {"id": "read", "name": "Read invoice", "description": "…", "tags": ["ocr"]}
    ],
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["application/json"],
}


def test_the_card_translates_to_the_kind_shape():
    spec = card_to_spec(_CARD, data_scope_kinds=["SourceArtifact"])
    assert spec["name"] == "invoice-reader"
    assert spec["supported_interfaces"][0]["url"] == "https://vendor.example/a2a"
    assert spec["capabilities"]["push_notifications"] is False
    assert spec["default_output_modes"] == ["application/json"]


def test_the_data_scope_comes_from_the_CALLER_not_the_card():
    """O `data_scope` é nosso: um Card de terceiro não declara — e não poderia
    declarar — o que ele tem permissão de receber do nosso workspace."""
    spec = card_to_spec(_CARD, data_scope_kinds=["Invoice"])
    assert spec["data_scope"] == {"kinds": ["Invoice"]}


def test_a_card_without_signatures_is_marked_unsigned():
    spec = card_to_spec(_CARD, data_scope_kinds=[])
    assert spec["signature_state"] == "unsigned"


def test_a_signed_card_is_marked_present_unverified():
    """A verificação criptográfica está fora desta versão. O estado diz isso em
    voz alta, em vez de deixar a ausência de verificação implícita."""
    signed = dict(_CARD, signatures=[{"protected": "…", "signature": "…"}])
    spec = card_to_spec(signed, data_scope_kinds=[])
    assert spec["signature_state"] == "present_unverified"
    assert spec["signatures"] == signed["signatures"]


@pytest.mark.parametrize("missing", ["name", "description", "supportedInterfaces"])
def test_a_card_missing_a_required_field_is_REFUSED(missing):
    bad = {k: v for k, v in _CARD.items() if k != missing}
    with pytest.raises(ValueError):
        card_to_spec(bad, data_scope_kinds=[])


def test_ingest_writes_an_INERT_document():
    """A propriedade central. `write` recebe `approved=False`: buscar um Card
    nunca concede acesso."""
    seen = {}

    class _Http:
        async def get(self, url, *, timeout=None):
            class _R:
                status_code = 200

                def json(self):
                    return _CARD

            return _R()

    async def _write(*, spec, approved):
        seen["spec"] = spec
        seen["approved"] = approved
        return "remote-invoice-reader"

    name = asyncio.run(
        ingest_card(
            "https://vendor.example/.well-known/agent-card.json",
            http=_Http(),
            data_scope_kinds=["SourceArtifact"],
            write=_write,
        )
    )
    assert name == "remote-invoice-reader"
    assert seen["approved"] is False, "um Card buscado NÃO pode nascer aprovado"


# ── o Card REAL, medido do a2a-sdk 1.1.2 ────────────────────────────────────
#
# Não é fixture inventada: é a serialização que um servidor A2A 1.0 conforme
# publica em /.well-known/agent-card.json, capturada do SDK oficial. Contra ela,
# `card_to_spec` + o schema do Kind recusavam DUAS vezes — `protocolBinding` era
# propriedade desconhecida num schema fechado, e `transport` estava faltando.
# Ou seja: nenhum agente A2A real podia ser registrado, e os 49 testes verdes
# não sabiam disso porque as fixtures herdavam o mesmo erro de leitura.
CARD_CONFORME = {
    "name": "eco",
    "description": "devolve o que recebe",
    "version": "0.1.0",
    "supportedInterfaces": [
        {
            "url": "https://exemplo/a2a",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        }
    ],
    "capabilities": {"streaming": True},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [{"id": "eco", "name": "eco", "description": "ecoa"}],
}


def _validador_do_kind():
    from pathlib import Path

    import yaml
    from jsonschema import Draft202012Validator

    import dna.extensions.a2a as pacote

    caminho = Path(pacote.__file__).parent / "kinds" / "remote-agent.kind.yaml"
    schema = yaml.safe_load(caminho.read_text())["spec"]["schema"]
    return Draft202012Validator(schema)


def test_um_card_conforme_vira_RemoteAgent_valido():
    spec = card_to_spec(CARD_CONFORME, data_scope_kinds=["Story"])
    erros = [
        f"{list(e.path)}: {e.message}" for e in _validador_do_kind().iter_errors(spec)
    ]
    assert not erros, "o Kind recusou um Agent Card A2A 1.0 conforme: " + "; ".join(erros)


def test_a_interface_preserva_binding_e_versao_do_protocolo():
    spec = card_to_spec(CARD_CONFORME, data_scope_kinds=[])
    assert spec["supported_interfaces"] == [
        {
            "url": "https://exemplo/a2a",
            "protocol_binding": "JSONRPC",
            "protocol_version": "1.0",
        }
    ]


def test_o_campo_transport_da_versao_a_mao_nao_e_mais_aceito():
    """Sem compatibilidade, por decisão: duas leituras do mesmo campo
    convivendo é exatamente o débito que esta troca existe para não criar."""
    antigo = dict(
        CARD_CONFORME,
        supportedInterfaces=[{"transport": "jsonrpc", "url": "https://exemplo/a2a"}],
    )
    spec = card_to_spec(antigo, data_scope_kinds=[])
    assert list(_validador_do_kind().iter_errors(spec)), (
        "a forma antiga passou — o schema ainda aceita as duas leituras"
    )
