"""A face A2A que SERVE — as rotas do SDK OFICIAL montadas num app do host.

Este módulo tem uma responsabilidade e ela cabe numa frase: pegar o Card que
``dna.emit.agent_card`` projeta, entregá-lo ao ``a2a-sdk`` junto com um
executor, e montar as rotas que o SDK produz. Não há protocolo escrito aqui —
nem envelope JSON-RPC, nem enquadramento SSE, nem armazém de Tasks. Tudo isso é
do SDK, e essa é a decisão inteira desta face.

## O que continua NOSSO

- **A projeção do Card.** O Card é a nossa verdade sobre o agente
  (``dna.emit.agent_card.agent_card_for``); o SDK só o serve. Duplicar a
  projeção aqui criaria uma segunda verdade sobre o mesmo agente.
- **A derivação de ``capabilities.streaming``.** O Card diz o que o EXECUTOR
  montado faz, e não uma constante. Fixo em ``True``, era promessa sem nada
  atrás.

## O que ele NÃO faz, e é deliberado

**Não autentica.** A verificação acontece na BORDA, antes de chegar aqui, como
as portas MCP fazem — uma autoridade por porta (ADR
``adr-identity-doors-verify-different-sets``). Meter verificação aqui criaria
uma segunda implementação da regra de identidade, que é exatamente o débito que
aquele ADR registrou. Este módulo nunca vê um bearer.

## O caminho do Card

Default ``AGENT_CARD_WELL_KNOWN_PATH`` (``/.well-known/agent-card.json``), lido
do SDK e não escrito à mão. Continua PARÂMETRO porque a raiz do domínio não é do
SDK: um host que monta sob prefixo precisa poder dizer onde.
"""
from __future__ import annotations

from typing import Any, Mapping

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH

__all__ = ["attach_a2a", "card_to_proto"]


def card_to_proto(card: Mapping[str, Any]) -> AgentCard:
    """O Card (dict camelCase da nossa projeção) como ``AgentCard`` do SDK.

    ``ParseDict`` é ESTRITO — um campo desconhecido levanta em vez de ser
    ignorado. É de propósito que a conversão passe por ele: é o ponto onde uma
    divergência entre a nossa projeção e a 1.0 vira erro AQUI, na montagem, em
    vez de virar um Card que ninguém lá fora consegue ler.
    """
    from google.protobuf import json_format

    return json_format.ParseDict(dict(card), AgentCard())


def attach_a2a(
    app: Any,
    path: str,
    *,
    executor: Any,
    card: Mapping[str, Any],
    card_path: str = AGENT_CARD_WELL_KNOWN_PATH,
    task_store: Any = None,
) -> DefaultRequestHandler:
    """Montar a face A2A de ``executor`` em ``app``, e devolver o handler do SDK.

    ``card`` é o dict de ``dna.emit.agent_card.agent_card_for``.
    ``capabilities.streaming`` é SOBRESCRITO a partir de ``executor.streaming``:
    quem monta é quem sabe o que o executor faz, e o Card não deve prometer o
    que ninguém implementou.

    ``task_store`` default é o ``InMemoryTaskStore`` do SDK. O antecessor à mão
    tinha um armazém próprio com um teto de 256 inventado; o SDK traz este e um
    ``DatabaseTaskStore`` nos extras, para quem precisar de durabilidade.
    """
    corpo = dict(card)
    capacidades = dict(corpo.get("capabilities") or {})
    capacidades["streaming"] = bool(getattr(executor, "streaming", False))
    corpo["capabilities"] = capacidades

    proto = card_to_proto(corpo)
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store or InMemoryTaskStore(),
        agent_card=proto,
    )
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(proto, card_url=card_path),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=path),
    )
    return handler
