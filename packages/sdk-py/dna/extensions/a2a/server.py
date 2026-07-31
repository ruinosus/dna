"""A face A2A que SERVE — o mount HTTP sobre o núcleo puro de `rpc.py`.

Fecha a metade que faltava: o SDK já projetava o Agent Card (saída) e já ingeria
o de terceiros (`a2a_ingest`), e já tinha o cliente (`a2a_transport.call_remote`).
Faltava a porta. Sem ela, `capabilities.streaming: true` no Card era uma promessa
sem nada atrás.

## O que ele monta

- ``GET`` no caminho do Card — por padrão ``/.well-known/agent-card.json``, que é
  a convenção da 1.0. O caminho é PARÂMETRO porque a raiz do domínio não é do
  SDK: `dna.emit.agent_card` já dizia isso ("who serves it and at which path is a
  deployment decision"), e um host que monta sob prefixo precisa poder dizer onde.
- ``POST`` no caminho do agente — JSON-RPC 2.0. `message/stream` responde
  ``text/event-stream``; os outros dois, JSON.

## O que ele NÃO faz, e é deliberado

**Não autentica.** A verificação acontece na BORDA, antes de chegar aqui, como as
portas MCP fazem — uma autoridade por porta, o mesmo `_workos_providers`. Meter
verificação aqui dentro criaria uma segunda implementação da regra de identidade,
que é exatamente o débito que o ADR `adr-identity-doors-verify-different-sets`
registrou. Este módulo nunca vê um bearer.

**Não decide o alcance do agente.** Quem executa é o `run` injetado — o mesmo
padrão de `delegation_exec` (a política aqui, os transportes de fora). O que o
agente pode fazer é do host que o construiu.
"""
from __future__ import annotations

import uuid
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Mapping

# Importado no TOPO, e não dentro de `attach_a2a`, por um motivo que custa uma
# tarde para achar: com `from __future__ import annotations` as anotações viram
# STRINGS, e o FastAPI as resolve contra os *globals* do módulo. Um `Request`
# importado dentro da função não está lá — o FastAPI então trata o parâmetro
# como query e devolve 422 `{"loc":["query","request"]}` em toda chamada.
#
# O custo de subir o import é este módulo passar a exigir o extra `api`. É
# honesto: ele SERVE HTTP; sem FastAPI não há o que montar.
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from dna.extensions.a2a.rpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_GET,
    METHOD_SEND,
    METHOD_STREAM,
    PARSE_ERROR,
    STATE_COMPLETED,
    STATE_FAILED,
    STATE_WORKING,
    RpcError,
    parse_request,
    result,
    sse_frame,
    task,
    text_from_message,
)

#: Quantas Tasks concluídas ficam recuperáveis por `tasks/get`.
#:
#: Um teto, e não "todas": um dicionário sem limite num processo de vida longa é
#: um vazamento de memória com passos extras. E não é cache de resultado — é a
#: rede de segurança de um cliente que perdeu a conexão, que volta em segundos,
#: não em dias.
TASK_HISTORY = 256


class TaskStore:
    """As Tasks recentes, por id. Limitado por construção."""

    def __init__(self, limit: int = TASK_HISTORY) -> None:
        self._limit = limit
        self._tasks: OrderedDict[str, dict] = OrderedDict()

    def put(self, item: Mapping[str, Any]) -> None:
        tid = str(item.get("id") or "")
        if not tid:
            return
        self._tasks.pop(tid, None)
        self._tasks[tid] = dict(item)
        while len(self._tasks) > self._limit:
            self._tasks.popitem(last=False)

    def get(self, tid: str) -> dict | None:
        found = self._tasks.get(tid)
        return dict(found) if found else None


def attach_a2a(
    app: Any,
    path: str,
    *,
    run: Callable[[str], Awaitable[str]],
    card: Mapping[str, Any],
    card_path: str = "/.well-known/agent-card.json",
    store: TaskStore | None = None,
) -> TaskStore:
    """Montar a face A2A de `run` em `app`, e devolver o armazém de Tasks.

    `run(text) -> str` é o agente. `card` é o dict de
    `dna.emit.agent_card.agent_card_for` — servido verbatim, porque o Card é a
    projeção e duplicá-la aqui criaria uma segunda verdade sobre o mesmo agente.
    """
    tasks = store or TaskStore()

    @app.get(card_path)
    async def _card() -> Any:  # pragma: no cover - trivial
        return JSONResponse(dict(card))

    @app.post(path)
    async def _rpc(request: Request) -> Any:
        try:
            payload = await request.json()
        except Exception:
            # Corpo ilegível: `id` desconhecido, e a especificação manda `null`.
            return JSONResponse(
                RpcError(PARSE_ERROR, "request body is not valid JSON").envelope(),
                status_code=200,
            )

        try:
            pedido = parse_request(payload)
        except RpcError as exc:
            return JSONResponse(exc.envelope(), status_code=200)

        if pedido.method == METHOD_GET:
            tid = pedido.params.get("id")
            found = tasks.get(str(tid)) if tid else None
            if found is None:
                return JSONResponse(
                    RpcError(INVALID_PARAMS, f"unknown task {tid!r}", pedido.id).envelope(),
                    status_code=200,
                )
            return JSONResponse(result(pedido.id, found))

        try:
            texto = text_from_message(pedido.params)
        except RpcError as exc:
            return JSONResponse(
                RpcError(exc.code, exc.message, pedido.id).envelope(), status_code=200
            )

        task_id = str(uuid.uuid4())
        context_id = str(pedido.params.get("contextId") or uuid.uuid4())

        if pedido.method == METHOD_SEND:
            return JSONResponse(
                result(pedido.id, await _execute(run, tasks, task_id, context_id, texto))
            )

        if pedido.method == METHOD_STREAM:
            async def stream():
                # O primeiro evento sai ANTES de o agente começar. É o que
                # transforma a espera em progresso — sem ele, o cliente fica com
                # uma conexão aberta e silenciosa, indistinguível de travada.
                yield sse_frame(
                    result(pedido.id, task(task_id, context_id, STATE_WORKING))
                )
                final = await _execute(run, tasks, task_id, context_id, texto)
                yield sse_frame(result(pedido.id, final))

            return StreamingResponse(
                stream(),
                media_type="text/event-stream",
                # Sem isto um proxy pode BUFERIZAR o stream inteiro e entregá-lo
                # no fim — o streaming continuaria "funcionando" nos testes e
                # deixaria de funcionar em produção, atrás do primeiro proxy.
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        # `parse_request` já recusou todo método fora de METHODS; chegar aqui
        # significaria que a lista e o dispatch divergiram.
        return JSONResponse(  # pragma: no cover - inalcançável por construção
            RpcError(INTERNAL_ERROR, f"unrouted method {pedido.method!r}", pedido.id).envelope(),
            status_code=200,
        )

    return tasks


async def _execute(
    run: Callable[[str], Awaitable[str]],
    tasks: TaskStore,
    task_id: str,
    context_id: str,
    texto: str,
) -> dict[str, Any]:
    """Rodar o agente e dar forma ao desfecho — completado ou falho.

    Uma exceção do agente NÃO escapa: ela viraria um 500 sem `id`, e o cliente
    perderia tanto o resultado quanto a razão. Vira uma Task `failed` com o
    motivo dentro do status, que é o que a 1.0 define para falha de tarefa.
    """
    try:
        texto_final = await run(texto)
    except Exception as exc:  # noqa: BLE001 — a mensagem É o resultado
        falha = task(task_id, context_id, STATE_FAILED, error=f"{type(exc).__name__}: {exc}")
        tasks.put(falha)
        return falha
    pronto = task(task_id, context_id, STATE_COMPLETED, text=texto_final)
    tasks.put(pronto)
    return pronto
