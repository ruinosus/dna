"""Um agente do DNA, visto pela interface `AgentExecutor` do `a2a-sdk`.

É a ÚNICA peça nova desta face, e é cola — não protocolo. Quem decide a ordem
dos eventos, o que vira Task, como o SSE é enquadrado e o que a `tasks/get`
devolve é o SDK oficial. O que é nosso é `run(text) -> str`, o mesmo formato
que `delegation_exec` já injeta nos outros transportes.

## Por que não escrevemos isto à mão (de novo)

A face A2A anterior era artesanal, tinha 49 testes verdes e mutação verde.
Mesmo assim errava três coisas do protocolo — o nome do campo do binding, o
valor dele, e a forma de uma ``Part`` — porque os testes foram escritos pela
mesma leitura da especificação que o código. Conformidade não se testa contra a
própria leitura; se mede contra a implementação de referência
(``tests/test_a2a_conformance.py``).

## O que este módulo DECIDE, e é nosso

1. **Uma exceção do agente vira Task ``failed`` com a razão dentro do status.**
   Deixá-la escapar produziria um erro de TRANSPORTE, e o cliente perderia
   tanto o resultado quanto o motivo. A chamada funcionou; foi a tarefa que
   falhou, e a 1.0 distingue as duas coisas de propósito.
2. **Um pedido sem texto algum FALHA em vez de completar vazio.** Uma Task que
   completa sem ter feito nada é o pior desfecho possível, porque parece
   sucesso.
3. **``streaming`` é declarado aqui**, e o Card o deriva — em vez de uma
   constante ``True`` que prometia o que ninguém tinha implementado.

## O que ele NÃO faz

**Não autentica.** A verificação é da PORTA, antes de chegar aqui, como as
portas MCP fazem — uma autoridade por porta (ADR
``adr-identity-doors-verify-different-sets``). Este módulo nunca vê um bearer.

**Não decide o alcance do agente.** Quem executa é o ``run`` injetado; o que o
agente pode fazer é do host que o construiu.
"""
from __future__ import annotations

from typing import Awaitable, Callable

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, Task, TaskState, TaskStatus

__all__ = ["DnaAgentExecutor"]


def _texto_do_pedido(context: RequestContext) -> str:
    """O texto da mensagem, concatenado das partes de texto.

    Partes que não são texto são IGNORADAS, não recusadas: um cliente que anexa
    uma imagem a um pedido cujo texto basta deve ser atendido, e recusar o
    pedido inteiro por causa de uma parte que não sabemos ler trocaria uma
    degradação por uma falha.

    ``Part`` na 1.0 é um ``oneof`` (``text`` | ``raw`` | ``url`` | ``data``) —
    não há campo ``kind`` discriminador, e supor que havia foi um dos três erros
    da versão à mão.
    """
    mensagem = getattr(context, "message", None)
    if mensagem is None:
        return ""
    pedacos = [
        parte.text
        for parte in mensagem.parts
        if parte.WhichOneof("content") == "text" and parte.text.strip()
    ]
    return "\n".join(pedacos)


class DnaAgentExecutor(AgentExecutor):
    """Adapta ``run(text) -> str`` à interface do ``a2a-sdk``."""

    #: O que esta implementação REALMENTE faz — lido por
    #: ``dna.extensions.a2a.serve.attach_a2a`` para derivar
    #: ``capabilities.streaming`` do Card. ``True`` porque os eventos saem pela
    #: ``EventQueue`` conforme acontecem, e o SDK os transmite.
    streaming: bool = True

    def __init__(self, *, run: Callable[[str], Awaitable[str]]) -> None:
        self._run = run

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        # A Task PRIMEIRO. O SDK recusa com `InvalidAgentResponseError: Agent
        # should enqueue Task before TaskStatusUpdateEvent` se um status vier
        # antes — regra da 1.0 que só a implementação de referência conhece, e
        # que uma leitura da especificação não entrega.
        if context.current_task is None:
            await event_queue.enqueue_event(
                Task(
                    id=context.task_id,
                    context_id=context.context_id,
                    status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
                )
            )

        texto = _texto_do_pedido(context)
        if not texto:
            await updater.failed(
                updater.new_agent_message(
                    [Part(text="a mensagem não carrega texto algum; não há o que fazer")]
                )
            )
            return

        await updater.start_work()
        try:
            resultado = await self._run(texto)
        except Exception as exc:  # noqa: BLE001 — a mensagem É o resultado
            await updater.failed(
                updater.new_agent_message([Part(text=f"{type(exc).__name__}: {exc}")])
            )
            return

        await updater.add_artifact([Part(text=resultado)], name="resultado")
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Não suportado — e dizê-lo alto é a resposta honesta.

        Cancelar de verdade exige que ``run`` seja interrompível, e o ``run``
        que recebemos é uma corrotina opaca do host. Um ``cancel`` que devolve
        "cancelado" sem cancelar nada é PIOR que um que recusa: o cliente para
        de esperar enquanto o trabalho continua rodando.
        """
        raise NotImplementedError(
            "este executor não suporta cancelamento: `run` é opaco e não é interrompível"
        )
