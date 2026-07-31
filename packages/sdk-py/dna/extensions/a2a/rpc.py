"""O núcleo PURO da face A2A — o envelope JSON-RPC 2.0 e a forma de Task.

A2A 1.0 é JSON-RPC 2.0 sobre HTTP POST. Este módulo faz o que não precisa de
rede: interpretar o pedido, recusar o malformado com o código certo, extrair o
texto da mensagem e dar forma à Task. Quem executa o agente e quem escreve os
bytes na resposta são de fora — a mesma separação que `delegation_exec` já usa
(a política aqui, os transportes injetados).

## Por que puro

A face de saída (o Agent Card) já é pura (`dna.emit.agent_card`) e é testada
sem servidor. A face de ENTRADA merece o mesmo: os erros de protocolo — id
ausente, método desconhecido, params errados — são exatamente o que um cliente
externo vai exercitar primeiro, e são triviais de testar aqui e caros de testar
por HTTP.

## O que este módulo NÃO decide

Autenticação. Um servidor A2A verifica a credencial ANTES de chegar aqui, na
borda, como as portas MCP fazem — uma autoridade por porta. Este módulo recebe um
pedido já autenticado e nunca vê um bearer; a mesma regra que o Agent Card segue
("no field here can carry a credential").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

#: Os métodos que a 1.0 define e que esta face serve.
#:
#: `message/send` responde a Task completa; `message/stream` transmite os eventos
#: por SSE; `tasks/get` devolve o estado de uma Task já criada — é o que permite
#: a um cliente que perdeu a conexão recuperar o resultado, e sem ele o
#: streaming seria uma promessa sem rede de segurança.
METHOD_SEND = "message/send"
METHOD_STREAM = "message/stream"
METHOD_GET = "tasks/get"
METHODS = (METHOD_SEND, METHOD_STREAM, METHOD_GET)

#: Códigos de erro do JSON-RPC 2.0. Enumerados porque são do PROTOCOLO, não
#: nossos: um cliente A2A de terceiro os interpreta por número, e inventar um
#: código aqui seria falar outra língua com quem segue a especificação.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

#: Os estados de Task que esta face produz. A 1.0 define mais (`input-required`,
#: `canceled`); declarar só o que se produz evita anunciar um ciclo de vida que
#: não existe do lado de cá.
STATE_WORKING = "working"
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"


@dataclass(frozen=True)
class RpcRequest:
    """Um pedido JSON-RPC já validado."""

    id: Any
    method: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RpcError(Exception):
    """Uma recusa de protocolo, com o código que a especificação manda."""

    code: int
    message: str
    id: Any = None

    def envelope(self) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": self.id,
            "error": {"code": self.code, "message": self.message},
        }


def parse_request(payload: Any) -> RpcRequest:
    """Validar um pedido JSON-RPC 2.0, ou levantar `RpcError` com o código certo.

    O `id` é extraído ANTES de qualquer outra checagem e viaja em toda recusa:
    um erro sem `id` é um erro que o cliente não consegue casar com o pedido que
    o causou, e a especificação o exige de volta justamente por isso.
    """
    if not isinstance(payload, Mapping):
        raise RpcError(INVALID_REQUEST, "the request body must be a JSON object")

    rpc_id = payload.get("id")

    if payload.get("jsonrpc") != "2.0":
        raise RpcError(INVALID_REQUEST, "jsonrpc must be exactly '2.0'", rpc_id)

    method = payload.get("method")
    if not isinstance(method, str) or not method:
        raise RpcError(INVALID_REQUEST, "method is required", rpc_id)
    if method not in METHODS:
        # A mensagem NOMEIA o que existe. Um cliente que errou o método está
        # tentando descobrir a superfície, e mandá-lo de volta sem a lista o
        # obriga a adivinhar — quando o Agent Card e esta linha são as duas
        # únicas fontes que ele tem.
        raise RpcError(
            METHOD_NOT_FOUND,
            f"unknown method {method!r}; this agent serves {', '.join(METHODS)}",
            rpc_id,
        )

    params = payload.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, Mapping):
        raise RpcError(INVALID_PARAMS, "params must be an object", rpc_id)

    return RpcRequest(id=rpc_id, method=method, params=params)


def text_from_message(params: Mapping[str, Any]) -> str:
    """O texto de um `message/send`/`message/stream`, concatenado das partes.

    A 1.0 modela a mensagem como `{role, parts:[{kind:"text", text}, …]}`. Partes
    que não são texto são IGNORADAS, não recusadas: um cliente que anexa uma
    imagem a um pedido cujo texto basta deve ser atendido, e recusar o pedido
    inteiro por causa de uma parte que não sabemos ler seria trocar uma
    degradação por uma falha.

    Um pedido SEM nenhum texto, porém, é recusado: não há tarefa a executar, e
    inventar uma vazia produziria uma Task que completa sem ter feito nada — o
    pior resultado possível, porque parece sucesso.
    """
    mensagem = params.get("message")
    if not isinstance(mensagem, Mapping):
        raise RpcError(INVALID_PARAMS, "params.message is required")

    partes = mensagem.get("parts")
    if not isinstance(partes, (list, tuple)):
        raise RpcError(INVALID_PARAMS, "params.message.parts must be an array")

    pedacos: list[str] = []
    for parte in partes:
        if not isinstance(parte, Mapping):
            continue
        if parte.get("kind") not in (None, "text"):
            continue
        texto = parte.get("text")
        if isinstance(texto, str) and texto.strip():
            pedacos.append(texto)

    if not pedacos:
        raise RpcError(
            INVALID_PARAMS,
            "params.message.parts carries no text; there is nothing to do",
        )
    return "\n".join(pedacos)


def task(
    task_id: str,
    context_id: str,
    state: str,
    *,
    text: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Um objeto Task da 1.0, pronto para virar `result`.

    O texto do agente vira um `artifact` — e não uma `message` — porque artifact
    é o que a especificação define como SAÍDA de uma task, e um cliente que
    coleta resultados lê artifacts. Devolver como mensagem faria o resultado
    parecer conversa.
    """
    corpo: dict[str, Any] = {
        "id": task_id,
        "contextId": context_id,
        "kind": "task",
        "status": {"state": state},
    }
    if error:
        # A razão viaja DENTRO do status, não como erro de JSON-RPC: a chamada
        # funcionou, foi a tarefa que falhou. Confundir os dois faria um cliente
        # tratar uma falha de negócio como protocolo quebrado e reenviar.
        corpo["status"]["message"] = {
            "role": "agent",
            "parts": [{"kind": "text", "text": error}],
        }
    if text:
        corpo["artifacts"] = [
            {"artifactId": f"{task_id}-result", "parts": [{"kind": "text", "text": text}]}
        ]
    return corpo


def result(rpc_id: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    """A resposta de sucesso do JSON-RPC."""
    return {"jsonrpc": "2.0", "id": rpc_id, "result": dict(payload)}


def sse_frame(payload: Mapping[str, Any]) -> str:
    """Um evento SSE — cada `data:` é uma Response JSON-RPC 2.0 COMPLETA.

    É o que a 1.0 exige, e é a parte que mais se erra: mandar só o objeto Task,
    sem o envelope, faz o stream falar um protocolo diferente do da chamada
    síncrona, e um cliente conforme não o interpreta.
    """
    import json as _json

    return f"data: {_json.dumps(payload, ensure_ascii=False)}\n\n"
