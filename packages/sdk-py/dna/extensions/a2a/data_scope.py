"""O que o agente de terceiro PEDE — a extensão A2A de escopo de dado.

## O problema, na tela

A porta registrava ``requested_scope_kinds: []`` sempre, porque nada no
protocolo dizia o que o chamador queria. O usuário via *"este agente pediu
acesso"* e dois botões — uma decisão de segurança **sem objeto**. Não é falta de
polimento: consentimento sem escopo é consentimento sobre nada, e "conceder"
vira um sim em branco.

## Por que uma EXTENSÃO, e não um campo nosso

A2A tem ponto de extensão de primeira classe, e é onde isto pertence:

* ``AgentCapabilities.extensions`` — o Card **anuncia** (``uri``,
  ``description``, ``params``). É aqui que o terceiro DESCOBRE o vocabulário,
  sem coordenação prévia e sem documentação fora de banda.
* ``Message.extensions`` — o chamador **declara** que está usando a extensão.
* ``Message.metadata`` — carrega os valores, sob a chave da URI.

Inventar um campo no corpo seria reimplementar um mecanismo que o padrão já tem
— e um cliente A2A conforme, de outra empresa, não teria como adivinhá-lo.

## Por que NÃO escopo OAuth

Escopo OAuth é vocabulário ESTÁTICO, registrado no provedor de identidade. Os
nossos Kinds são dinâmicos e **por tenant** — um workspace autora o próprio Kind
e ele passa a valer sem deploy. Empurrar esse vocabulário para o IdP mataria
exatamente essa propriedade, e ainda faria a lista de Kinds de um cliente
aparecer no cadastro de outro.

O token continua carregando o portão GROSSO (quem é o agente, qual audiência,
qual tenant). O que se pede sobre DADO é fino, nosso, e vive aqui.

## ⚠️ Pedir NUNCA é receber

Tudo que este módulo devolve é **pedido**, e vai para ``requested_scope_kinds``
— jamais para ``scope_kinds``. A assimetria é deliberada e é a regra inteira do
consentimento:

    o ESCOPO pedido pode vir do chamador — ele diz o que quer, o usuário decide
    o NOME do agente precisa de âncora — nomear-se é afirmação sobre identidade

Só a segunda engana. Um agente que mente sobre o que quer está pedindo demais na
frente de um humano, que é onde se deve pedir; um agente que mente sobre QUEM É
usa a nossa tela como instrumento.

Por isso não há checagem de "este Kind existe" aqui: pedir um Kind inexistente
não é ataque, é um pedido que o usuário vai olhar e negar. Filtrar em silêncio
esconderia do humano o que o agente realmente quis.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

__all__ = ["EXTENSION_URI", "extension_declaration", "requested_kinds"]

#: A URI da extensão. É identificador, não endereço a buscar — nada nesta
#: biblioteca a dereferencia. Aponta para o repositório do padrão de fato (o
#: nosso), que é a convenção do A2A para extensões de fornecedor.
EXTENSION_URI = "https://github.com/ruinosus/dna/a2a/data-scope/v1"

#: A chave dentro de ``metadata``. A URI inteira, e não um apelido curto:
#: ``metadata`` é espaço compartilhado por todas as extensões de todos os
#: fornecedores, e uma chave como ``"kinds"`` colidiria com a primeira outra
#: extensão que tivesse a mesma boa ideia.
_CHAVE = EXTENSION_URI

#: Teto de itens lidos de um pedido. Um chamador que manda dez mil Kinds não
#: está pedindo acesso — está fazendo a nossa tela ficar inutilizável, que é uma
#: negação de serviço contra o HUMANO, não contra o servidor.
_MAX_ITENS = 64

#: Teto do tamanho de um nome de Kind. Nome de Kind é identificador, não texto.
_MAX_TAMANHO = 128


def extension_declaration(
    *, available_kinds: Iterable[str] = (), required: bool = False
) -> dict[str, Any]:
    """A declaração que o Agent Card publica — o vocabulário, descoberto.

    ``available_kinds`` é o que ESTE deployment pode conceder. Publicá-lo é o
    que torna a extensão utilizável sem documentação fora de banda: o terceiro
    lê o Card e sabe o que existe para pedir. Vazio é legítimo — significa "a
    extensão existe, pergunte ao operador o vocabulário".

    ``required=False`` sempre, por default e por desenho: um cliente que não
    conhece esta extensão tem de continuar conseguindo falar conosco. Ele será
    recusado por falta de CONCESSÃO (com a mensagem que ensina o caminho), e não
    por falta de uma extensão nossa — recusar por isso transformaria uma
    conveniência nossa em requisito do protocolo.
    """
    # ⚠️ SEM o teto de `requested_kinds`. Os dois números parecem o mesmo e não
    # são: `_MAX_ITENS` defende o HUMANO de um pedido absurdo de terceiro;
    # aqui a lista é NOSSA, e cortá-la tornaria Kinds reais indescobríveis sem
    # nada na tela dizendo que faltou. Medido: o registro local tem 81 Kinds e
    # esta função publicava 64, em silêncio.
    kinds = _limpar(available_kinds, limite=None)
    return {
        "uri": EXTENSION_URI,
        "description": (
            "Declare which DNA Kinds the caller wants to act on. The values are "
            "a REQUEST shown to the user for approval — never a grant."
        ),
        "required": bool(required),
        "params": {"availableKinds": kinds},
    }


def requested_kinds(message: Any) -> list[str]:
    """Os Kinds que ESTA mensagem pede, ordenados e sem repetição.

    Aceita a mensagem do SDK (protobuf) ou um mapa — o chamador não deveria ter
    de converter, e o portão que consome isto roda nos dois mundos (produção com
    protobuf, teste com dict).

    Devolve ``[]`` para tudo que não é uma lista de textos: ausente, malformado,
    número, mapa aninhado. **Silêncio vira lista vazia, nunca exceção** — um
    pedido malformado não pode derrubar a porta, e não pode virar permissão.
    """
    metadata = _metadata(message)
    if not metadata:
        return []
    bruto = metadata.get(_CHAVE)
    # Duas formas aceitas: a lista direta, ou um mapa com `kinds`. A segunda é o
    # que um cliente escreve por instinto (o mesmo instinto que fez a declaração
    # do Card ter `params`), e recusá-la seria pedantismo com custo de suporte.
    if isinstance(bruto, Mapping):
        bruto = bruto.get("kinds")
    if not isinstance(bruto, (list, tuple)):
        return []
    return _limpar(bruto)


def _limpar(valores: Iterable[Any], *, limite: int | None = _MAX_ITENS) -> list[str]:
    """Nomes de Kind limpos, ordenados e sem repetição.

    ``limite=None`` para a lista que NÓS publicamos; o teto existe contra o que
    um terceiro manda, e aplicá-lo aos dois lados corta o nosso próprio
    vocabulário sem avisar ninguém.
    """
    vistos: set[str] = set()
    for v in valores:
        if not isinstance(v, str):
            continue
        nome = v.strip()
        if nome and len(nome) <= _MAX_TAMANHO:
            vistos.add(nome)
        if limite is not None and len(vistos) >= limite:
            break
    return sorted(vistos)


def _metadata(message: Any) -> Mapping[str, Any] | None:
    """O ``metadata`` da mensagem, como mapa Python.

    O SDK entrega um ``google.protobuf.Struct``; ele não é um ``Mapping`` do
    Python, mas responde a ``keys``/``__getitem__`` e converte com
    ``MessageToDict``. Tentar a conversão e cair para o acesso direto cobre os
    dois sem importar protobuf aqui — o que manteria o extra ``a2a`` opcional
    (a mesma disciplina de ``emit.agent_card``).
    """
    if message is None:
        return None
    if isinstance(message, Mapping):
        bruto = message.get("metadata")
    else:
        bruto = getattr(message, "metadata", None)
    if bruto is None:
        return None
    if isinstance(bruto, Mapping):
        return bruto
    try:
        from google.protobuf.json_format import MessageToDict

        return MessageToDict(bruto)
    except Exception:  # noqa: BLE001 — não é protobuf, ou não converte
        try:
            return dict(bruto.items())
        except Exception:  # noqa: BLE001
            return None
