"""Quem autorizou o quê, e quando — a trilha de aprovação.

## ⚠️ Isto NÃO é a telemetria de turno, e as garantias são OPOSTAS

`dna.runtime.telemetry` responde *"o que aconteceu?"*. Este módulo responde
*"quem autorizou o quê?"*. Confundi-los estraga os dois:

======================  ==========================  =========================
                        telemetria                  trilha de aprovação
======================  ==========================  =========================
sob pressão             **descarta** (fila c/ teto)  não perde nada
texto                   truncado em 8 KB             **íntegro**
banco fora              segue sem registrar          a ação **não acontece**
======================  ==========================  =========================

A regra da telemetria é *"observar nunca derruba o observado"*. Aqui ela **se
inverte**: se não dá para registrar a autorização, não se deve executar a ação.

Uma trilha com buracos silenciosos é **pior que nenhuma**, porque parece
cobertura — quem confia nela não procura em outro lugar.

## A gravação fica ANTES do efeito

::

    modelo chama tool gated
       → o LangGraph INTERROMPE e checkpointa o pedido   (durável por si)
       → humano decide na tela
       → grava pedido + decisão, numa linha             ← falhou aqui? NÃO executa
       → a tool roda

É isso que faz *"não está na trilha"* significar *"não aconteceu"* — a única
propriedade que torna uma auditoria útil.

**Um ponto de gravação, não dois.** A primeira versão desta spec pedia gravar a
solicitação *antes de perguntar*, e implementá-la exigia subclassear o
`HumanInTheLoopMiddleware` e reconstruir o envelope dele por fora — acoplamento
a método privado, que quebra a cada atualização do LangChain.

E era redundante: **o LangGraph já checkpointa a interrupção pendente.** Um
pedido sem resposta já é durável, e recuperável do próprio estado do grafo. O
que não era durável — e é o que esta trilha grava — é a DECISÃO.

**O custo, dito com todas as letras:** uma indisponibilidade do banco bloqueia
ações aprovadas. Foi decisão do fundador, tomada com o custo na tela. O modo de
falha é VISÍVEL (o usuário vê o erro), que é o oposto do modo de falha da
alternativa.

## `arguments` não é truncado

É o que foi autorizado. Um corte tornaria a trilha incapaz de responder à única
pergunta que ela existe para responder — e diferente da telemetria, onde cortar
é a decisão certa, aqui o tamanho é o preço da integridade.

## Puro

Nada aqui grava. O host tem a conexão; o que mora aqui é a FORMA do registro e a
regra de que ele precede o efeito.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

__all__ = [
    "DECISIONS",
    "ApprovalRecord",
    "AuditUnavailable",
    "records_from_request",
    "settle",
]

#: As decisões que o `HumanInTheLoopMiddleware` do LangChain conhece. Fechado de
#: propósito: uma decisão que a trilha não sabe nomear não pode ser auditada, e
#: aceitar um nome livre transformaria a coluna num campo de texto qualquer.
DECISIONS = frozenset({"approve", "reject", "edit", "respond"})


class AuditUnavailable(RuntimeError):
    """A trilha não pôde ser gravada — e por isso a ação não acontece.

    Existe como tipo próprio porque quem captura precisa distinguir "a escrita
    falhou" de "o usuário recusou": os dois impedem a ação, e só um é um
    problema de operação.
    """


@dataclass(frozen=True)
class ApprovalRecord:
    """Uma linha da trilha. Append-only: uma decisão não se edita, se sucede."""

    approval_id: str
    tool: str
    #: Os argumentos ÍNTEGROS, como JSON. Nunca truncados — ver o cabeçalho.
    arguments: str
    turn_id: str = ""
    thread_id: str = ""
    workspace: str = ""
    #: A conta. Não muda.
    oid: str = ""
    #: O humano. Muda — por isso vive AO LADO do `oid`, nunca no lugar dele.
    actor_email: str = ""
    requested_at: str = ""
    #: Vazio enquanto ninguém decidiu. Uma linha sem decisão é uma solicitação
    #: pendente, e ela precisa existir: sem ela, um processo que morre entre o
    #: pedido e a resposta não deixaria rastro de que houve pergunta.
    decision: str = ""
    decided_at: str = ""
    edited_args: str = ""
    reason: str = ""


def _json(value: Any) -> str:
    import json

    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def records_from_request(
    payload: Any,
    *,
    ids: Iterable[str],
    requested_at: str,
    turn_id: str = "",
    thread_id: str = "",
    workspace: str = "",
    oid: str = "",
    actor_email: str = "",
) -> list[ApprovalRecord]:
    """As solicitações desta interrupção — uma por tool a aprovar.

    `payload` é o envelope canônico do `HumanInTheLoopMiddleware`
    (``{"action_requests": [{name, args, description}, ...]}``). Formato
    inesperado devolve lista vazia; quem chama trata isso como "nada a
    registrar", nunca como sucesso.

    ⚠️ Uma solicitação por ação, e não uma por interrupção. O middleware pode
    gatear várias tools numa tacada, e a decisão é **posicional** — registrar
    uma linha só perderia qual argumento pertence a qual aprovação.
    """
    pedidos = (payload or {}).get("action_requests") if isinstance(payload, dict) else None
    if not isinstance(pedidos, list):
        return []

    saida: list[ApprovalRecord] = []
    fila = list(ids)
    for i, pedido in enumerate(pedidos):
        if not isinstance(pedido, dict):
            continue
        saida.append(
            ApprovalRecord(
                approval_id=fila[i] if i < len(fila) else f"{turn_id}:{i}",
                tool=str(pedido.get("name") or "?"),
                arguments=_json(pedido.get("args")),
                turn_id=turn_id,
                thread_id=thread_id,
                workspace=workspace,
                oid=oid,
                actor_email=actor_email,
                requested_at=requested_at,
            )
        )
    return saida


def settle(
    records: list[ApprovalRecord], decisions: Any, *, decided_at: str
) -> list[ApprovalRecord]:
    """Casa cada solicitação com a decisão que a respondeu — POSICIONALMENTE.

    É posicional porque o contrato do `HumanInTheLoopMiddleware` é: uma decisão
    por `action_request`, na mesma ordem. Casar por nome de tool pareceria mais
    seguro e seria **pior**: duas chamadas da mesma tool numa interrupção
    ficariam ambíguas, e a ambiguidade cairia justamente no caso em que a
    trilha mais importa.

    Uma decisão com tipo desconhecido vira ``reject`` com o motivo registrado —
    nunca é silenciosamente tratada como aprovação. O default fecha, como todo
    portão deste SDK.
    """
    lista = decisions if isinstance(decisions, list) else []
    saida = []
    for i, registro in enumerate(records):
        crua = lista[i] if i < len(lista) else None
        tipo = (crua or {}).get("type") if isinstance(crua, dict) else None
        conhecida = tipo in DECISIONS
        saida.append(
            ApprovalRecord(
                **{
                    **registro.__dict__,
                    "decision": tipo if conhecida else "reject",
                    "decided_at": decided_at,
                    "edited_args": _json((crua or {}).get("edited_action"))
                    if isinstance(crua, dict) and crua.get("edited_action")
                    else "",
                    "reason": (
                        ""
                        if conhecida
                        else f"decisão desconhecida: {tipo!r} — tratada como recusa"
                    )
                    or (str((crua or {}).get("message") or "") if isinstance(crua, dict) else ""),
                }
            )
        )
    return saida
