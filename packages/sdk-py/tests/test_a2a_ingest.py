"""Entrada: um Agent Card de terceiro vira um `RemoteAgent` INERTE.

Registrar um agente passa a ser escrever um documento — sem deploy, sem edição
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
    "supportedInterfaces": [{"transport": "jsonrpc", "url": "https://vendor.example/a2a"}],
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
