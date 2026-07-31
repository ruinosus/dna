"""`DnaAgentExecutor` — o agente do DNA visto pela interface do SDK oficial.

É cola, não protocolo: quem decide o que sai na fila de eventos, em que ordem, e
o que vira Task é o `a2a-sdk`. O que é nosso é `run(text) -> str` — e três
decisões que o SDK não toma por nós e não deveria tomar: o que fazer com uma
exceção do agente, o que fazer com um pedido sem texto, e se declaramos
streaming.

A `EventQueue` do SDK é um protocolo com um único método (`enqueue_event`), então
o dublê aqui é um coletor honesto e não uma reimplementação — ele tem exatamente
a superfície que o executor usa.
"""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("a2a", reason="o executor adapta o SDK oficial")

from a2a.server.agent_execution import RequestContext  # noqa: E402
from a2a.server.context import ServerCallContext  # noqa: E402
from a2a.types import (  # noqa: E402
    Message,
    Part,
    Role,
    SendMessageRequest,
    TaskState,
)

from dna.extensions.a2a.executor import DnaAgentExecutor  # noqa: E402


class _FilaColetora:
    """A `EventQueue` do SDK tem UM método; este dublê tem o mesmo."""

    def __init__(self) -> None:
        self.eventos: list = []

    async def enqueue_event(self, evento) -> None:
        self.eventos.append(evento)


def _contexto(texto: str) -> RequestContext:
    return RequestContext(
        call_context=ServerCallContext(),
        request=SendMessageRequest(
            message=Message(
                message_id="m1", role=Role.ROLE_USER, parts=[Part(text=texto)]
            )
        ),
        task_id="t1",
        context_id="c1",
    )


def _rodar(run, texto: str) -> list:
    fila = _FilaColetora()
    asyncio.run(DnaAgentExecutor(run=run).execute(_contexto(texto), fila))
    return fila.eventos


def _estados(eventos) -> list:
    return [
        e.status.state for e in eventos if type(e).__name__ == "TaskStatusUpdateEvent"
    ]


def test_a_Task_e_enfileirada_ANTES_de_qualquer_status():
    """Regra da 1.0 que só a implementação de referência conhece: o SDK recusa
    com `InvalidAgentResponseError: Agent should enqueue Task before
    TaskStatusUpdateEvent` se um status vier primeiro."""

    async def run(texto: str) -> str:
        return f"eco:{texto}"

    eventos = _rodar(run, "ola")
    assert type(eventos[0]).__name__ == "Task", [type(e).__name__ for e in eventos]


def test_o_texto_do_agente_sai_como_ARTIFACT_e_a_task_completa():
    async def run(texto: str) -> str:
        return f"eco:{texto}"

    eventos = _rodar(run, "ola")
    tipos = [type(e).__name__ for e in eventos]
    assert "TaskArtifactUpdateEvent" in tipos, tipos
    textos = [
        p.text
        for e in eventos
        if type(e).__name__ == "TaskArtifactUpdateEvent"
        for p in e.artifact.parts
    ]
    assert textos == ["eco:ola"], textos
    assert TaskState.TASK_STATE_COMPLETED in _estados(eventos), _estados(eventos)


def test_uma_excecao_do_agente_vira_task_FAILED_com_a_razao_dentro():
    """Deixar escapar produziria um erro de TRANSPORTE sem `id` — o cliente
    perderia o resultado E a razão. A chamada funcionou; foi a tarefa que
    falhou, e a 1.0 distingue as duas coisas de propósito."""

    async def run(_texto: str) -> str:
        raise RuntimeError("o alvo caiu")

    eventos = _rodar(run, "ola")
    assert TaskState.TASK_STATE_FAILED in _estados(eventos), _estados(eventos)
    razoes = [
        p.text
        for e in eventos
        if type(e).__name__ == "TaskStatusUpdateEvent" and e.status.HasField("message")
        for p in e.status.message.parts
    ]
    assert any("o alvo caiu" in r for r in razoes), razoes


def test_um_pedido_sem_texto_algum_falha_em_vez_de_completar_vazio():
    """Uma Task que completa sem ter feito nada é o pior desfecho possível,
    porque parece sucesso."""
    chamado = []

    async def run(texto: str) -> str:  # pragma: no cover — não deve ser chamado
        chamado.append(texto)
        return "nunca"

    eventos = _rodar(run, "   ")
    assert TaskState.TASK_STATE_FAILED in _estados(eventos), _estados(eventos)
    assert not chamado, "o agente rodou com pedido vazio"


def test_partes_que_nao_sao_texto_sao_IGNORADAS_e_nao_recusadas():
    """Um cliente que anexa uma imagem a um pedido cujo texto basta deve ser
    atendido; recusar o pedido inteiro por uma parte que não sabemos ler
    trocaria uma degradação por uma falha."""

    async def run(texto: str) -> str:
        return f"li:{texto}"

    fila = _FilaColetora()
    ctx = RequestContext(
        call_context=ServerCallContext(),
        request=SendMessageRequest(
            message=Message(
                message_id="m1",
                role=Role.ROLE_USER,
                parts=[Part(url="https://x/foto.png"), Part(text="ola")],
            )
        ),
        task_id="t1",
        context_id="c1",
    )
    asyncio.run(DnaAgentExecutor(run=run).execute(ctx, fila))
    textos = [
        p.text
        for e in fila.eventos
        if type(e).__name__ == "TaskArtifactUpdateEvent"
        for p in e.artifact.parts
    ]
    assert textos == ["li:ola"], textos


def test_o_executor_declara_que_faz_streaming():
    """`attach_a2a` DERIVA `capabilities.streaming` disto — o Card deixa de
    prometer o que ninguém implementou."""
    assert DnaAgentExecutor.streaming is True


def test_cancelar_RECUSA_alto_em_vez_de_fingir():
    """Um `cancel` que devolve "cancelado" sem cancelar nada é pior que um que
    recusa: o cliente para de esperar enquanto o trabalho continua rodando."""

    async def run(texto: str) -> str:  # pragma: no cover
        return texto

    with pytest.raises(NotImplementedError):
        asyncio.run(
            DnaAgentExecutor(run=run).cancel(_contexto("x"), _FilaColetora())
        )
