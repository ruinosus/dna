"""`AgentGrant` — a concessão que deixa um TERCEIRO agir em nome de um usuário.

É o GÊMEO DE ENTRADA do `RemoteAgent`, e os dois juntos dizem a coisa toda:

    RemoteAgent  →  "podemos mandar dado para lá"
    AgentGrant   →  "eles podem agir por nós"

Mora aqui, e não no deployment, porque a simetria é do PROTOCOLO. Um host que
serve A2A precisa das duas metades — e ter só a de saída modelada foi exatamente
o que deixou a porta de ENTRADA inalcançável: ela aceitava qualquer token válido
do usuário, então "autorizar a Acme" e "ter um usuário logado" eram
indistinguíveis.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml
from jsonschema import Draft202012Validator

import dna.extensions.a2a as pacote

_KIND = pathlib.Path(pacote.__file__).parent / "kinds" / "agent-grant.kind.yaml"


def _schema() -> dict:
    return yaml.safe_load(_KIND.read_text())["spec"]["schema"]


def _spec(**overrides) -> dict:
    base = {
        "client_id": "https://claude.ai/oauth/mcp-oauth-client-metadata",
        "subject": "user_01KXV762MWW3J7X90A36PQ5DV0",
        "state": "pending",
        "requested_at": "2026-07-31T12:00:00Z",
    }
    base.update(overrides)
    return base


def _erros(spec: dict) -> list[str]:
    validador = Draft202012Validator(_schema())
    return [f"{list(e.path)}: {e.message}" for e in validador.iter_errors(spec)]


def test_um_pedido_recem_chegado_e_valido():
    assert not _erros(_spec())


def test_o_estado_e_TRI_estado():
    """Um booleano `granted` faria "pediu e ninguém decidiu" parecer "negado", e
    são coisas diferentes: a primeira precisa aparecer na tela para alguém
    decidir, a segunda já foi decidida. É o mesmo motivo do `signature_state`."""
    for estado in ("pending", "active", "revoked"):
        assert not _erros(_spec(state=estado)), estado
    assert _erros(_spec(state="granted")), "aceitou um estado fora do tri-estado"


def test_um_grant_SEM_escopo_e_valido_e_significa_NADA():
    """Escopo ausente é "não pode receber dado nenhum", nunca "pode tudo" — a
    mesma leitura do `data_scope` do RemoteAgent, onde ausência FECHA."""
    assert not _erros(_spec(scope_kinds=[]))


def test_o_escopo_PEDIDO_e_um_campo_SEPARADO_do_concedido():
    """A separação é a regra inteira do consentimento: o agente pede, o usuário
    decide. Um campo só faria pedir ser igual a receber."""
    spec = _spec(scope_kinds=[], requested_scope_kinds=["Memory", "Story"])
    assert not _erros(spec)
    propriedades = _schema()["properties"]
    assert "requested_scope_kinds" in propriedades
    assert "scope_kinds" in propriedades


def test_o_schema_e_FECHADO():
    """`additionalProperties: false` — um campo a mais num documento de
    AUTORIZAÇÃO é a forma mais silenciosa de alguém anexar permissão."""
    assert _erros(_spec(admin=True)), "o schema aceitou um campo desconhecido"


def test_nao_ha_campo_para_credencial():
    """Como no RemoteAgent e no Agent Card: identidade e permissão moram aqui;
    segredo não. O schema fechado é o que garante isso estruturalmente, e este
    teste é o que impede alguém de abrir uma exceção "só desta vez"."""
    plano = _KIND.read_text().lower()
    for proibido in ("token:", "secret", "password", "bearer", "api_key"):
        assert proibido not in plano, f"o Kind menciona {proibido!r}"


def test_o_Kind_e_TENANTED_e_do_plano_de_REGISTRO():
    """Uma concessão é um fato consultável de um workspace — não algo que se
    dobra num prompt."""
    spec = yaml.safe_load(_KIND.read_text())["spec"]
    assert spec["tenant_scope"] == "tenanted"
    assert spec["plane"] == "record"
    assert spec["prompt_target"] is False
