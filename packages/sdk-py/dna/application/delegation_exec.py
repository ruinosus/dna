"""O executor de `delegate_to` — a porta que faltava.

`delegate_to` vivia no kernel apenas como VOCABULÁRIO: o bloco
`delegation_target_for` e o campo `team_members` estavam modelados, documentados
e sem uma linha de implementação em nenhum pacote. Capacidade existe, porta não —
o padrão que este projeto já viu três vezes. Isto é a porta.

── A forma ──────────────────────────────────────────────────────────────────

A política (`dna.application.delegation`) decide QUEM pode chamar QUEM. Este
módulo decide COMO: resolve o alvo pelo roster, escolhe o transporte pelo Kind do
alvo, e parseia o retorno pelo `format` que o ALVO declarou.

Os transportes são INJETADOS (`run_local`, `call_remote`). Não é adorno de
testabilidade: é o que faz a face A2A ser aditiva. Um alvo que era local passa a
remoto trocando o documento, e nem o supervisor nem este módulo mudam.

── Recusa nomeada, nunca silêncio ───────────────────────────────────────────

Toda recusa levanta `DelegationRefused` com o motivo. O pior modo de falha desta
feature não é um erro: é um delegador narrando "convertido!" sobre trabalho que
ninguém fez. Silêncio produz exatamente isso.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, Iterable, Mapping

from dna.application.delegation import DelegationTarget, targets_for

_LOGGER = logging.getLogger("dna.delegation")

#: Os formatos de retorno que o kernel declara.
FORMATS = ("slug", "json", "text")


class DelegationRefused(Exception):
    """Uma delegação recusada, com o motivo no texto.

    Exceção própria (e não `PermissionError`) porque o chamador precisa
    distinguir "não pode" de qualquer outra falha — e porque uma enumeração de
    exceções alheias já ficou cega neste projeto."""


def parse_result(fmt: str, raw: str) -> Any:
    """Interpretar o retorno do alvo pelo `format` que ele declarou.

    Um `json` malformado é RECUSADO, não devolvido como texto: cair para texto
    esconderia um alvo que quebrou o próprio contrato, e o delegador seguiria
    adiante achando que entendeu.
    """
    if fmt not in FORMATS:
        raise DelegationRefused(
            f"formato de retorno desconhecido {fmt!r} — o kernel declara {FORMATS}"
        )
    if fmt == "text":
        return raw
    if fmt == "json":
        try:
            return json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise DelegationRefused(
                f"o alvo declarou format=json e devolveu algo que não é json: {exc}"
            ) from exc
    lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    if not lines:
        raise DelegationRefused("o alvo declarou format=slug e não devolveu slug algum")
    return lines[-1]


async def delegate(
    *,
    delegator: str,
    target_name: str,
    request: str,
    documents: Iterable[Mapping[str, Any]],
    run_local: Callable[[str, str], Awaitable[str]],
    call_remote: Callable[[DelegationTarget, str], Awaitable[str]],
) -> dict:
    """Delegar `request` a `target_name`, em nome de `delegator`.

    Recusa (nunca devolve silenciosamente) quando o alvo não está no roster —
    o que cobre, pela política, tanto "o delegador não o listou" quanto "o alvo
    não aceita este delegador".
    """
    roster = {t.name: t for t in targets_for(delegator, documents)}
    target = roster.get(target_name)
    if target is None:
        raise DelegationRefused(
            f"{delegator!r} não pode delegar a {target_name!r}: o alvo não está no "
            f"roster (ou o delegador não o declarou em team_members, ou o alvo não "
            f"aceita este delegador em delegation_target_for.agents). "
            f"Alvos disponíveis: {sorted(roster) or 'nenhum'}"
        )

    if target.kind == "RemoteAgent":
        raw = await call_remote(target, request)
        transport = "a2a"
    else:
        raw = await run_local(target.name, request)
        transport = "local"

    _LOGGER.info(
        "delegated", extra={"delegator": delegator, "target": target_name, "transport": transport}
    )
    return {
        "target": target.name,
        "transport": transport,
        "format": target.format,
        "result": parse_result(target.format, raw),
    }
