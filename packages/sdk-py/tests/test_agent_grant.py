"""A decisão de conceder — pura, sem I/O, e por isso testável de verdade.

Quem lê e escreve o documento é o HOST (a porta, no deployment). O que mora aqui
é a REGRA, e ela é pequena de propósito: uma regra de autorização que precisa de
banco para ser exercitada é uma regra que ninguém testa nos casos difíceis — e
num portão os casos difíceis são exatamente os que importam.
"""
from __future__ import annotations

import pytest

from dna.application.agent_grant import (
    GrantRefused,
    grant_allows,
    pending_grant,
)


def test_um_grant_ATIVO_permite():
    assert grant_allows({"state": "active"}) is True


@pytest.mark.parametrize("estado", ["pending", "revoked"])
def test_pendente_e_revogado_NAO_permitem(estado):
    """Pendente não é "ainda não negado" — é "ninguém decidiu". Agir sem decisão
    é a decisão errada, e é a que ninguém consegue apontar depois."""
    assert grant_allows({"state": estado}) is False


def test_a_AUSENCIA_de_grant_nao_permite():
    """Fail closed. Um agente sobre o qual não sabemos nada é um agente que não
    foi autorizado — nunca um que "ainda não foi negado"."""
    assert grant_allows(None) is False


def test_um_estado_DESCONHECIDO_nao_permite():
    """Um documento de versão futura, ou corrompido, FECHA.

    É a propriedade que carrega o módulo: a lista é de UM permitido, e o resto é
    o resto. Um portão escrito ao contrário — negar o que conhece — abriria para
    tudo que ele não conhece, incluindo um estado que alguém acrescentar ao Kind
    depois sem lembrar deste arquivo.
    """
    assert grant_allows({"state": "aprovadissimo"}) is False


def test_um_grant_que_nem_e_mapa_nao_permite():
    """Entrada malformada fecha, em vez de levantar. Levantar num portão
    transforma dado ruim em erro 500 — e um 500 num caminho de autorização é
    indistinguível de indisponibilidade."""
    assert grant_allows("active") is False
    assert grant_allows(["active"]) is False


def test_o_pedido_nasce_PENDENTE_e_sem_escopo():
    """Inerte por construção — a mesma propriedade do `a2a_ingest`
    (`approved=False`, sempre) e do `author_kind`. Não há caminho neste módulo
    que produza um grant já ativo: conceder é ato humano, e ato humano não tem
    atalho de código."""
    p = pending_grant(client_id="c", subject="u")
    assert p["state"] == "pending"
    assert p["scope_kinds"] == []
    assert "granted_at" not in p


def test_o_escopo_PEDIDO_e_registrado_mas_NAO_concedido():
    """O agente pede; o usuário decide. Registrar o pedido é o que deixa a tela
    pré-marcar o que ele quer — mas entra em `requested_scope_kinds`, jamais em
    `scope_kinds`. Se pedir escrevesse no campo concedido, pedir seria receber.
    """
    p = pending_grant(client_id="c", subject="u", requested_scope=["Story", "Memory"])
    assert p["scope_kinds"] == []
    assert p["requested_scope_kinds"] == ["Memory", "Story"]


def test_o_escopo_pedido_e_ORDENADO_e_sem_repeticao():
    """Determinístico: o mesmo pedido produz o mesmo documento. Um documento que
    varia sem o fato variar polui o histórico — e histórico é metade do que a
    auditoria vende."""
    p = pending_grant(
        client_id="c", subject="u", requested_scope=["Story", "Memory", "Story"]
    )
    assert p["requested_scope_kinds"] == ["Memory", "Story"]


def test_um_pedido_SEM_escopo_declarado_nao_marca_nada():
    """Agente que não declara nada deixa a tela sem nada marcado. **Silêncio
    nunca vira permissão** — nem sequer uma sugestão de permissão."""
    p = pending_grant(client_id="c", subject="u")
    assert p["requested_scope_kinds"] == []


def test_a_recusa_ENSINA_o_caminho():
    """Uma recusa que não diz onde resolver é meia recusa: o terceiro recebe
    "negado" e um humano tem de adivinhar que existe uma tela em algum lugar."""
    exc = GrantRefused(
        client_id="Acme Faturas", portal_url="https://p/console/conexoes"
    )
    texto = str(exc)
    assert "Acme Faturas" in texto
    assert "https://p/console/conexoes" in texto


def test_a_recusa_carrega_os_dados_para_quem_a_TRATA():
    """A mensagem é para humano; os campos são para código. Quem captura precisa
    saber QUAL client foi recusado sem fazer parse de texto — parse de mensagem
    de erro é acoplamento que quebra na primeira melhoria de redação."""
    exc = GrantRefused(client_id="c-1", portal_url="https://p")
    assert exc.client_id == "c-1"
    assert exc.portal_url == "https://p"
