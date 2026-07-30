"""Entrada: um Agent Card de terceiro vira um `RemoteAgent` documento — INERTE.

Registrar um agente remoto passa a ser escrever um documento: sem deploy, sem
edição de código. "Inerte" é a palavra que carrega o desenho inteiro deste
módulo — buscar um Card por HTTP é só leitura de uma URL pública; NUNCA pode,
por si só, conceder acesso a dado do workspace. Um `RemoteAgent` só se torna
delegável depois que um humano aprova, pelo mesmo funil que já existe para os
Kinds autorados por tenant (`author_kind` / aprovação no portal). Por isso
`ingest_card` escreve sempre com `approved=False` — não há um caminho que
escreva `True`.

── As três propriedades que carregam o desenho ──────────────────────────────

1. **Inerte por construção.** `write(spec=..., approved=False)`, sempre. Um
   Card buscado nunca concede acesso; a aprovação é humana e vive fora deste
   módulo.
2. **`data_scope` vem do CALLER, nunca do Card.** Um terceiro não declara — e
   não poderia declarar — o que ele tem permissão de receber do NOSSO
   workspace. `card_to_spec` recebe `data_scope_kinds` como parâmetro
   obrigatório e nunca o lê do JSON do Card.
3. **`signature_state` é derivado, não copiado.** Ausência de `signatures` no
   Card → `"unsigned"`. Presença → `"present_unverified"` — a verificação
   criptográfica está fora desta versão (decidir a cadeia de confiança é
   decisão de produto), e o estado diz isso em voz alta em vez de deixar a
   ausência de verificação implícita.

`card_to_spec` é a tradução PURA (Card JSON em camelCase → spec do Kind
`RemoteAgent` em snake_case, a convenção do kernel). `ingest_card` é a única
parte com efeito: busca o Card por HTTP e delega a escrita a `write`
(injetado — o `parse()`/persistência real é do chamador, não deste módulo).
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping

#: Timeout de uma busca de Card. Generoso mas finito, pelo mesmo motivo do
#: transporte de saída (`dna.application.a2a_transport`): uma busca pendurada
#: não deve travar quem está registrando o remoto.
DEFAULT_TIMEOUT_S = 30

#: A2A (camelCase) → kernel (snake_case), campo a campo, no nível raiz do Card.
#: Nomeada explicitamente em vez de uma heurística de conversão de string —
#: um Kind é um contrato, e o contrato é a lista de campos que ele declara.
_FIELD_MAP = {
    "supportedInterfaces": "supported_interfaces",
    "securitySchemes": "security_schemes",
    "defaultInputModes": "default_input_modes",
    "defaultOutputModes": "default_output_modes",
    "documentationUrl": "documentation_url",
    "iconUrl": "icon_url",
}

#: O mesmo mapeamento, mas para dentro de `capabilities` (flags booleanas).
_CAPABILITY_FIELD_MAP = {
    "pushNotifications": "push_notifications",
    "extendedAgentCard": "extended_agent_card",
}

#: A2A 1.0 exige estes três; um Card sem eles não é um Card.
_REQUIRED = ("name", "description", "supportedInterfaces")

#: Campos copiados como vieram — já são snake_case-compatíveis ou o kernel
#: preserva a forma do A2A (`skills`, `signatures`).
_PASSTHROUGH = ("name", "description", "version", "skills")


def card_to_spec(card: Mapping[str, Any], *, data_scope_kinds: list[str]) -> dict:
    """Traduzir um Agent Card do A2A (camelCase) no spec do Kind `RemoteAgent`
    (snake_case) — pura, sem I/O.

    Levanta ``ValueError`` se `name`, `description` ou `supportedInterfaces`
    estiverem ausentes: o A2A 1.0 os exige, e um Card sem eles não é um Card.

    `data_scope_kinds` vem do CALLER, nunca do Card — ver o cabeçalho do
    módulo, propriedade 2.
    """
    missing = [field for field in _REQUIRED if field not in card]
    if missing:
        raise ValueError(
            f"Card do A2A sem campo(s) obrigatório(s): {', '.join(missing)} — "
            f"um Card sem eles não é um Card (A2A 1.0)"
        )

    spec: dict = {}
    for field in _PASSTHROUGH:
        if field in card:
            spec[field] = card[field]
    spec["supported_interfaces"] = card["supportedInterfaces"]

    for camel, snake in _FIELD_MAP.items():
        if camel == "supportedInterfaces":
            continue
        if camel in card:
            spec[snake] = card[camel]

    if "capabilities" in card:
        spec["capabilities"] = {
            _CAPABILITY_FIELD_MAP.get(key, key): value
            for key, value in card["capabilities"].items()
        }

    signatures = card.get("signatures")
    if signatures:
        spec["signatures"] = signatures
        spec["signature_state"] = "present_unverified"
    else:
        spec["signature_state"] = "unsigned"

    # O campo que é NOSSO, nunca do Card — ver o cabeçalho do módulo,
    # propriedade 2.
    spec["data_scope"] = {"kinds": list(data_scope_kinds)}

    return spec


async def ingest_card(
    url: str,
    *,
    http: Any,
    data_scope_kinds: list[str],
    write: Callable[..., Awaitable[str]],
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Buscar um Agent Card de terceiro e escrevê-lo como `RemoteAgent`
    INERTE (``approved=False``, sempre — ver o cabeçalho do módulo,
    propriedade 1).

    `http` e `write` são injetados: o transporte HTTP real e a persistência
    real vivem no chamador (o roteador/tool que expõe isto), não aqui.
    """
    res = await http.get(url, timeout=timeout_s)
    status = getattr(res, "status_code", 200)
    if status >= 400:
        raise ValueError(f"não foi possível buscar o Card em {url!r}: HTTP {status}")

    card = res.json()
    spec = card_to_spec(card, data_scope_kinds=data_scope_kinds)
    return await write(spec=spec, approved=False)
