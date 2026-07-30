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
    token: str | None = None,
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
