"""A chamada A2A de saída — e as duas regras que a tornam segura.

Um `RemoteAgent` é, por construção, um canal de exfiltração: o DNA manda dado do
workspace para uma URL que o tenant escolheu. Isso não é defeito do A2A (que é
protocolo de transporte e não tem opinião sobre o assunto) — é a natureza da
coisa. As duas regras abaixo são o que separa isso de um vazamento.

**O transporte é o `Client` do `a2a-sdk`**, nunca um POST à mão. A versão
anterior montava o envelope JSON-RPC aqui e chamava o método `message/send` —
que é o nome da A2A **0.3**. Contra um servidor 1.0 conforme, aquilo respondia
`-32601 Method not found`, e nenhum teste pegava: eles foram escritos pela mesma
leitura da especificação que o código. O que continua NOSSO são as duas regras
abaixo, e elas correm ANTES de o cliente sequer ser construído.

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
import uuid
from typing import Any, Callable, Iterable

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


def _client_para(target: DelegationTarget, url: str, http: Any):
    """O `Client` oficial, apontado a `url`.

    Um Card MÍNIMO — só a interface que vamos usar — em vez de buscar o Card
    remoto na hora: o documento `RemoteAgent` JÁ é o Card ingerido e aprovado
    por um humano (`a2a_ingest`), e ir buscá-lo de novo trocaria a verdade
    APROVADA pela verdade corrente do terceiro, sem que ninguém aprovasse a
    troca.
    """
    from a2a.client import ClientConfig, ClientFactory
    from a2a.types import AgentCard, AgentInterface
    from a2a.utils.constants import PROTOCOL_VERSION_1_0, TransportProtocol

    card = AgentCard(
        name=target.name,
        supported_interfaces=[
            AgentInterface(
                url=url,
                protocol_binding=TransportProtocol.JSONRPC.value,
                protocol_version=PROTOCOL_VERSION_1_0,
            )
        ],
    )
    fabrica = ClientFactory(ClientConfig(httpx_client=http, streaming=True))
    return fabrica.create(card)


def _texto_do_evento(evento: Any) -> str | None:
    """O texto de um `StreamResponse`, ou `None` se ele não carrega resultado.

    Lê os `artifacts` — o lugar que a 1.0 define para a SAÍDA de uma task. Um
    evento de progresso não tem artifact e devolve `None`, e é isso que deixa
    quem consome distinguir "andou" de "terminou" sem olhar o estado por fora.
    """
    qual = evento.WhichOneof("payload") if hasattr(evento, "WhichOneof") else None
    if qual == "artifact_update":
        partes = list(evento.artifact_update.artifact.parts)
    elif qual == "task" and evento.task.artifacts:
        partes = [p for art in evento.task.artifacts for p in art.parts]
    else:
        return None
    pedacos = [p.text for p in partes if p.WhichOneof("content") == "text"]
    return "\n".join(pedacos) if pedacos else None


async def call_remote(
    target: DelegationTarget,
    request: str,
    *,
    credential_for: Callable[[str], str | None],
    http: Any = None,
    payload_kinds: Iterable[str] = (),
    timeout_s: int = DEFAULT_TIMEOUT_S,
    on_event: Callable[[Any], None] | None = None,
) -> str:
    """Chamar `target` por A2A e devolver o texto cru (o parse é do executor).

    Nenhum parâmetro aceita identidade de caller — ver a regra 2 no cabeçalho.

    `on_event`, quando dado, recebe cada evento assim que chega: é o que
    transforma a espera em progresso. Sem ele a chamada é silenciosa até o fim,
    e para um alvo de vinte segundos isso é indistinguível de travado.

    O retorno continua sendo TEXTO: `delegation_exec` faz o parse conforme o
    `format` que o alvo declara, e devolver aqui uma estrutura obrigaria o
    chamador a conhecer A2A — o ponto de `delegation_exec` é justamente que ele
    não conhece transporte nenhum.
    """
    # As duas recusas, ANTES de qualquer byte E antes de o cliente existir.
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

    import httpx
    from a2a.client import ClientCallContext
    from a2a.types import Message, Part, Role, SendMessageRequest

    proprio = http is None
    cliente_http = http if http is not None else httpx.AsyncClient()
    cliente = _client_para(target, url, cliente_http)

    # A credencial viaja pelo contexto DA CHAMADA, não gravada num cliente HTTP
    # que pode ser compartilhado: `service_parameters` é a costura que o próprio
    # SDK usa para isso (`a2a.client.auth.AuthInterceptor` escreve no mesmo
    # lugar). Mutar os headers de um cliente do chamador vazaria a credencial
    # deste remoto para toda chamada seguinte feita com ele.
    contexto = ClientCallContext(
        service_parameters={"Authorization": f"Bearer {credential}"},
        timeout=float(timeout_s),
    )
    pedido = SendMessageRequest(
        message=Message(
            message_id=str(uuid.uuid4()),
            role=Role.ROLE_USER,
            parts=[Part(text=request)],
        )
    )

    ultimo_texto: str | None = None
    eventos = 0
    try:
        async for evento in cliente.send_message(pedido, context=contexto):
            eventos += 1
            if on_event is not None:
                on_event(evento)
            texto = _texto_do_evento(evento)
            if texto is not None:
                # O ÚLTIMO artifact vence: um stream pode reemitir o resultado
                # crescendo, e o primeiro seria parcial.
                ultimo_texto = texto
    finally:
        # Fechar só o que NÓS abrimos: `Client.close()` fecha o httpx por baixo,
        # e fechar o do chamador o quebraria para a próxima chamada.
        if proprio:
            await cliente.close()

    _LOGGER.info("a2a call ok", extra={"target": target.name, "events": eventos})
    return ultimo_texto or ""
