"""A regra de concessão — pura, e pequena de propósito.

Quem lê e escreve o documento ``AgentGrant`` é o HOST (a porta A2A, no
deployment). O que mora aqui é a DECISÃO, e ela é minúscula: uma regra de
autorização que precisa de banco para ser exercitada é uma regra que ninguém
testa nos casos difíceis — e num portão os casos difíceis são exatamente os que
importam.

## A propriedade que carrega o módulo

**Tudo que não é ``active`` fecha.** Ausente fecha, pendente fecha, revogado
fecha, malformado fecha, desconhecido fecha.

Não há lista de negados a manter — há uma lista de UM permitido, e o resto é o
resto. Um portão escrito ao contrário (que nega o que conhece) abre para tudo
que ele NÃO conhece: um estado novo acrescentado ao Kind depois, um documento de
versão futura, um campo corrompido. E abre em silêncio, que é o pior jeito.

## A separação que é a regra inteira

``scope_kinds`` é o que foi CONCEDIDO. ``requested_scope_kinds`` é o que foi
PEDIDO. Dois campos, porque o agente pede e o usuário decide — um campo só faria
pedir ser igual a receber.

## Inerte por construção

Não existe função aqui que produza um grant já ``active``. Conceder é ato humano,
e ato humano não tem atalho de código — a mesma propriedade do ``a2a_ingest``
(``approved=False``, sempre) e do ``author_kind``.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

__all__ = ["GrantRefused", "STATE_ACTIVE", "STATE_PENDING", "STATE_REVOKED",
           "grant_allows", "pending_grant"]

#: O ÚNICO estado que permite agir. Ver a propriedade no cabeçalho: a lista de
#: permitidos tem um item, e não há lista de negados.
STATE_ACTIVE = "active"

#: Pediu, e ninguém decidiu. Diferente de negado — este precisa APARECER numa
#: tela; negado já foi decidido e não pede nada.
STATE_PENDING = "pending"

STATE_REVOKED = "revoked"


class GrantRefused(Exception):
    """O terceiro não foi autorizado por este usuário — e a mensagem diz o que fazer.

    Uma recusa que não ensina o caminho é meia recusa: o agente recebe "negado" e
    um humano precisa adivinhar que existe uma tela em algum lugar.

    Os campos existem separados da mensagem porque quem CAPTURA precisa saber
    qual client foi recusado sem fazer parse do texto — parse de mensagem de erro
    é acoplamento que quebra na primeira melhoria de redação.
    """

    def __init__(self, *, client_id: str, portal_url: str) -> None:
        self.client_id = client_id
        self.portal_url = portal_url
        super().__init__(
            f"acesso não concedido: {client_id!r} ainda não foi autorizado por "
            f"este usuário. Um pedido foi registrado — a concessão acontece em "
            f"{portal_url}. Reenvie depois da aprovação."
        )


def grant_allows(grant: Mapping[str, Any] | None) -> bool:
    """Este grant permite agir?

    Só ``active`` permite. Entrada que nem é mapa devolve ``False`` em vez de
    levantar: levantar num portão transforma dado ruim em erro 500, e um 500 num
    caminho de autorização é indistinguível de indisponibilidade — o operador
    procura a causa no lugar errado.
    """
    if not isinstance(grant, Mapping):
        return False
    return grant.get("state") == STATE_ACTIVE


def pending_grant(
    *, client_id: str, subject: str, requested_scope: Iterable[str] = ()
) -> dict[str, Any]:
    """O documento de um pedido recém-chegado — INERTE.

    ``requested_scope`` é ordenado e desduplicado para que o mesmo pedido produza
    o mesmo documento: um documento que varia sem o fato variar polui o
    histórico, e histórico é metade do que a auditoria vende.

    Sem escopo declarado, ``requested_scope_kinds`` fica vazio e a tela não
    pré-marca nada. **Silêncio nunca vira permissão** — nem sequer uma sugestão
    dela.
    """
    return {
        "client_id": client_id,
        "subject": subject,
        "state": STATE_PENDING,
        "scope_kinds": [],
        "requested_scope_kinds": sorted(set(requested_scope or ())),
    }
