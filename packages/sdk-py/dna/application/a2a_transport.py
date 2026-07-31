"""A chamada A2A de saída — e as duas regras que a tornam segura.

Um `RemoteAgent` é, por construção, um canal de exfiltração: o DNA manda dado do
workspace para uma URL que o tenant escolheu. Isso não é defeito do A2A (que é
protocolo de transporte e não tem opinião sobre o assunto) — é a natureza da
coisa. As duas regras abaixo são o que separa isso de um vazamento.

**1. O escopo é checado ANTES do envio.** `data_scope.kinds` diz o que aquele
endpoint pode receber. A ordem é load-bearing: checar depois de postar é
auditoria, não controle.

**2. A credencial é do WORKSPACE, nunca do usuário.** O `security_schemes` do
Card diz COMO autenticar; de quem é a credencial é decisão nossa. Repassar o
bearer de quem está conversando faria de cada agente remoto uma impersonação
completa dele contra o nosso próprio MCP. Por isso `call_remote` não tem
parâmetro algum por onde uma identidade de caller entre — a ausência é asserida
por teste, contra a assinatura.

Ausência de credencial RECUSA, em vez de chamar anonimamente: um remoto pode
aceitar anônimo, e essa não é decisão que alguém tomou.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Mapping

from dna.application.delegation import DelegationTarget
from dna.application.delegation_exec import DelegationRefused

_LOGGER = logging.getLogger("dna.a2a")

#: Timeout de uma chamada A2A. Generoso (um especialista pode pensar) mas finito:
#: uma delegação pendurada vira um supervisor mudo, que é indistinguível de um
#: supervisor que esqueceu.
DEFAULT_TIMEOUT_S = 120


def scope_allows(target: DelegationTarget, payload_kinds: Iterable[str]) -> bool:
    """O payload cabe no `data_scope` declarado do alvo?

    Fecha em três casos, e todos de propósito: escopo ausente (`None` — num
    remoto isso é falta de declaração), escopo vazio (registrado, sem permissão)
    e qualquer Kind fora da lista.
    """
    allowed = target.data_scope_kinds
    if not allowed:
        return False
    return set(payload_kinds or ()) <= set(allowed)


def _endpoint(target: DelegationTarget) -> str:
    for iface in target.interfaces or ():
        url = str((iface or {}).get("url") or "")
        if url.startswith("https://"):
            return url
        if url:
            raise DelegationRefused(
                f"o remoto {target.name!r} anuncia {url!r}: delegar dado de "
                f"workspace por texto claro não é permitido"
            )
    raise DelegationRefused(
        f"o remoto {target.name!r} não anuncia interface alcançável (https)"
    )


async def call_remote(
    target: DelegationTarget,
    request: str,
    *,
    credential_for: Callable[[str], str | None],
    http: Any,
    payload_kinds: Iterable[str] = (),
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Chamar `target` por A2A e devolver o texto cru (o parse é do executor).

    Nenhum parâmetro aceita identidade de caller — ver a regra 2 no cabeçalho.
    """
    if not scope_allows(target, payload_kinds):
        raise DelegationRefused(
            f"payload fora do data_scope de {target.name!r}: permitido "
            f"{sorted(target.data_scope_kinds or ())}, pedido "
            f"{sorted(set(payload_kinds or ()))}"
        )
    url = _endpoint(target)
    credential = credential_for(target.name)
    if not credential:
        raise DelegationRefused(
            f"nenhuma credencial de workspace configurada para o remoto "
            f"{target.name!r} — chamar anonimamente não é decisão que este "
            f"código pode tomar"
        )

    body = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": request}]}},
    }
    res = await http.post(
        url,
        json=body,
        headers={"authorization": f"Bearer {credential}", "content-type": "application/json"},
        timeout=timeout_s,
    )
    if getattr(res, "status_code", 500) >= 400:
        raise DelegationRefused(
            f"o remoto {target.name!r} respondeu {res.status_code}"
        )
    _LOGGER.info("a2a call ok", extra={"target": target.name})
    return res.text


def parse_sse_events(corpo: str) -> list[dict]:
    """Os objetos JSON-RPC de um corpo `text/event-stream`.

    Cada evento SSE carrega uma Response JSON-RPC COMPLETA no seu `data:` — é o
    que a 1.0 exige, e é o que o servidor deste mesmo SDK produz
    (`extensions.a2a.server`). Um quadro ilegível é PULADO, não levantado: um
    stream longo não pode morrer inteiro por causa de um evento malformado no
    meio, e o cliente ainda tem os que vieram antes e os que virão depois.
    """
    import json as _json

    eventos: list[dict] = []
    for bloco in corpo.split("\n\n"):
        for linha in bloco.splitlines():
            if not linha.startswith("data:"):
                continue
            bruto = linha[len("data:"):].strip()
            if not bruto:
                continue
            try:
                obj = _json.loads(bruto)
            except Exception:
                continue
            if isinstance(obj, dict):
                eventos.append(obj)
    return eventos


def task_text(evento: Mapping[str, Any]) -> str | None:
    """O texto de um artifact de Task, ou `None`.

    Lê `result.artifacts[].parts[].text` — o lugar que a 1.0 define para a SAÍDA
    de uma task. Um evento de progresso (`working`) não tem artifact e devolve
    `None`, e é isso que deixa quem consome distinguir "andou" de "terminou" sem
    olhar o estado por fora.
    """
    resultado = (evento or {}).get("result")
    if not isinstance(resultado, Mapping):
        return None
    pedacos: list[str] = []
    for art in resultado.get("artifacts") or []:
        if not isinstance(art, Mapping):
            continue
        for parte in art.get("parts") or []:
            if isinstance(parte, Mapping) and isinstance(parte.get("text"), str):
                pedacos.append(parte["text"])
    return "\n".join(pedacos) if pedacos else None


async def stream_remote(
    target: DelegationTarget,
    request: str,
    *,
    credential_for: Callable[[str], str | None],
    http: Any,
    on_event: Callable[[Mapping[str, Any]], None] | None = None,
    payload_kinds: Iterable[str] = (),
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Chamar `target` por `message/stream` e devolver o texto FINAL.

    ## O que ela ganha sobre `call_remote`

    O progresso. `call_remote` abre a conexão e fica muda até o fim — para um
    alvo de 20 segundos isso é indistinguível de travado, que foi a queixa que
    originou este épico. Aqui cada evento passa por `on_event` assim que chega.

    ## As mesmas recusas

    `data_scope` e credencial são verificados ANTES de qualquer byte, com as
    mensagens idênticas às de `call_remote`. Um caminho novo com portões mais
    frouxos que o antigo seria a forma mais silenciosa de perder uma garantia.

    ## O retorno continua sendo TEXTO

    O executor (`delegation_exec`) faz o parse conforme o `format` que o alvo
    declara. Devolver aqui uma estrutura obrigaria o chamador a conhecer A2A —
    e o ponto de `delegation_exec` é que ele não conhece transporte nenhum.
    """
    if not scope_allows(target, payload_kinds):
        raise DelegationRefused(
            f"payload fora do data_scope de {target.name!r}: permitido "
            f"{sorted(target.data_scope_kinds or ())}, pedido "
            f"{sorted(set(payload_kinds or ()))}"
        )
    url = _endpoint(target)
    credential = credential_for(target.name)
    if not credential:
        raise DelegationRefused(
            f"nenhuma credencial de workspace configurada para o remoto "
            f"{target.name!r} — chamar anonimamente não é decisão que este "
            f"código pode tomar"
        )

    body = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/stream",
        "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": request}]}},
    }
    res = await http.post(
        url,
        json=body,
        headers={
            "authorization": f"Bearer {credential}",
            "content-type": "application/json",
            # Declarado no pedido: um servidor que não faz streaming pode
            # responder JSON, e aí `parse_sse_events` não acha evento nenhum —
            # o fallback abaixo cobre esse caso em vez de devolver vazio.
            "accept": "text/event-stream",
        },
        timeout=timeout_s,
    )
    if getattr(res, "status_code", 500) >= 400:
        raise DelegationRefused(f"o remoto {target.name!r} respondeu {res.status_code}")

    eventos = parse_sse_events(res.text)
    if not eventos:
        # Não foi um stream — um servidor sem streaming responde JSON puro. O
        # retorno cru acontece na última linha desta função (nenhum artifact ⇒
        # `res.text`), então aqui só fica o registro: teste de mutação mostrou
        # que um `return` antecipado seria redundante, e guarda redundante é
        # código que passa a existir sem ninguém poder prová-lo errado.
        _LOGGER.info("a2a stream sem eventos; corpo cru", extra={"target": target.name})

    ultimo_texto: str | None = None
    for evento in eventos:
        if on_event is not None:
            on_event(evento)
        texto = task_text(evento)
        if texto is not None:
            ultimo_texto = texto

    _LOGGER.info(
        "a2a stream ok", extra={"target": target.name, "events": len(eventos)}
    )
    # O ÚLTIMO artifact vence: um stream pode reemitir a task com o resultado
    # crescendo, e o primeiro seria parcial.
    return ultimo_texto if ultimo_texto is not None else res.text
