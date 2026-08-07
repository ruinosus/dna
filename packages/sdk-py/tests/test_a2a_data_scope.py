"""A extensão de escopo — o que o terceiro PEDE, e o que nunca vira permissão.

O assunto deste arquivo é uma assimetria, e ela é a regra inteira do
consentimento:

    o ESCOPO pode vir do chamador — ele diz o que quer, o usuário decide
    o NOME precisa de âncora — nomear-se é afirmação sobre identidade

Por isso quase tudo aqui é sobre o pedido chegar INTACTO à tela (inclusive um
pedido absurdo, que o humano precisa ver para negar), e sobre ele nunca
atravessar para o campo do que foi concedido.
"""
from __future__ import annotations

import pytest

from dna.extensions.a2a.data_scope import (
    EXTENSION_URI,
    extension_declaration,
    requested_kinds,
)


def _msg(valor) -> dict:
    return {"metadata": {EXTENSION_URI: valor}}


# ── o que o Card anuncia ────────────────────────────────────────────────────


def test_a_declaracao_publica_o_VOCABULARIO():
    """É o que torna a extensão utilizável sem documentação fora de banda: o
    terceiro lê o Card e sabe o que existe para pedir."""
    d = extension_declaration(available_kinds=["Story", "Memory", "Memory"])
    assert d["uri"] == EXTENSION_URI
    assert d["params"]["availableKinds"] == ["Memory", "Story"]


def test_a_extensao_NUNCA_e_obrigatoria_por_default():
    """Um cliente que não conhece esta extensão tem de continuar falando conosco.

    Ele será recusado por falta de CONCESSÃO — com a mensagem que ensina o
    caminho —, e não por falta de uma extensão nossa. Recusar por isso
    transformaria uma conveniência nossa em requisito do protocolo, e um cliente
    A2A conforme deixaria de conseguir nos chamar.
    """
    assert extension_declaration()["required"] is False


def test_vocabulario_vazio_ainda_ANUNCIA_a_extensao():
    """"A extensão existe, o vocabulário não está publicado aqui" é uma
    mensagem — e é o caso de um deployment cujos Kinds são do tenant."""
    d = extension_declaration(available_kinds=[])
    assert d["uri"] == EXTENSION_URI
    assert d["params"]["availableKinds"] == []


# ── o que o chamador pede ───────────────────────────────────────────────────


def test_o_pedido_e_lido_da_metadata_sob_a_URI():
    assert requested_kinds(_msg(["Story", "Memory"])) == ["Memory", "Story"]


def test_a_forma_com_kinds_aninhado_tambem_vale():
    """É o que um cliente escreve por instinto, visto que a declaração do Card
    tem `params`. Recusá-la seria pedantismo com custo de suporte."""
    assert requested_kinds(_msg({"kinds": ["Memory"]})) == ["Memory"]


def test_o_pedido_e_ORDENADO_e_sem_repeticao():
    """Determinístico: o mesmo pedido produz o mesma instância, e uma instância
    que varia sem o fato variar polui o histórico."""
    assert requested_kinds(_msg(["Story", "Memory", "Story"])) == ["Memory", "Story"]


@pytest.mark.parametrize(
    "valor",
    [None, 42, "Memory", {"outra": "coisa"}, [1, 2, 3], [None], [{"k": "v"}]],
)
def test_pedido_MALFORMADO_vira_lista_vazia_e_nao_excecao(valor):
    """Um pedido malformado não pode derrubar a porta, e não pode virar
    permissão. Silêncio vira lista vazia — nos dois sentidos."""
    assert requested_kinds(_msg(valor)) == []


def test_mensagem_SEM_a_extensao_pede_nada():
    assert requested_kinds({"metadata": {}}) == []
    assert requested_kinds({}) == []
    assert requested_kinds(None) == []


def test_a_chave_e_a_URI_INTEIRA_e_nao_um_apelido():
    """`metadata` é espaço compartilhado por todas as extensões de todos os
    fornecedores. Um apelido curto colidiria com a primeira outra extensão que
    tivesse a mesma boa ideia — e a colisão seria silenciosa."""
    assert requested_kinds({"metadata": {"kinds": ["Memory"]}}) == []
    assert requested_kinds({"metadata": {"dataScope": ["Memory"]}}) == []


def test_um_Kind_INEXISTENTE_e_repassado_e_nao_filtrado():
    """De propósito. Pedir um Kind que não existe não é ataque — é um pedido que
    o usuário vai olhar e negar. Filtrar em silêncio esconderia do humano o que
    o agente realmente quis, e é o humano que decide."""
    assert requested_kinds(_msg(["KindQueNaoExiste"])) == ["KindQueNaoExiste"]


def test_um_pedido_ABSURDO_e_limitado_mas_nao_ignorado():
    """Dez mil Kinds não é pedido, é tornar a tela inutilizável — negação de
    serviço contra o HUMANO. Corta-se o volume; o pedido continua existindo."""
    lido = requested_kinds(_msg([f"Kind{i}" for i in range(10_000)]))
    assert 0 < len(lido) <= 64


def test_nome_absurdamente_longo_e_descartado():
    assert requested_kinds(_msg(["K" * 5_000, "Memory"])) == ["Memory"]


# ── a ligação com o Card ────────────────────────────────────────────────────


def test_o_Card_anuncia_a_extensao_quando_o_deployment_a_serve():
    from dna.emit.agent_card import agent_card_for

    card = agent_card_for(
        {"metadata": {"name": "copiloto"}, "spec": {}},
        base_url="https://exemplo.dev/a2a",
        data_scope_kinds=["Memory"],
    )
    exts = card["capabilities"]["extensions"]
    assert [e["uri"] for e in exts] == [EXTENSION_URI]
    assert exts[0]["params"]["availableKinds"] == ["Memory"]


def test_sem_a_extensao_o_Card_nao_ganha_a_chave():
    """`None` é "este deployment não pede escopo" — diferente de lista vazia,
    que anuncia a extensão sem vocabulário. Colapsar as duas faria o terceiro
    nunca pedir nada."""
    from dna.emit.agent_card import agent_card_for

    card = agent_card_for(
        {"metadata": {"name": "copiloto"}, "spec": {}},
        base_url="https://exemplo.dev/a2a",
    )
    assert "extensions" not in card["capabilities"]
    assert card["capabilities"]["streaming"] is False


def test_o_VOCABULARIO_publicado_nao_e_truncado():
    """O teto de `_MAX_ITENS` defende o HUMANO de um pedido absurdo de terceiro.
    A lista que NÓS publicamos é outra coisa: cortá-la tornaria Kinds reais
    indescobríveis, sem nada em lugar nenhum dizendo que faltou.

    Medido em 02/08: o registro local tem 81 Kinds e a declaração publicava 64.
    Achado rodando, não lendo — os dois números parecem o mesmo teto.
    """
    muitos = [f"Kind{i:03d}" for i in range(200)]
    publicado = extension_declaration(available_kinds=muitos)["params"]["availableKinds"]
    assert len(publicado) == 200


def test_mas_o_PEDIDO_continua_com_teto():
    """Os dois lados não compartilham o número, e é isso que este par prova."""
    assert len(requested_kinds(_msg([f"Kind{i:03d}" for i in range(200)]))) == 64


def test_um_Mapping_REGISTRADO_sem_get_nao_estoura():
    """⚠️ `isinstance(x, Mapping)` NÃO garante `x.get`.

    `Mapping.register(C)` faz o `isinstance` responder `True` sem trazer um
    único método do mixin. O `google.protobuf.Struct` é exatamente isso, e é o
    que a porta recebe em `message.metadata`.

    O rascunho deste módulo confiava no `isinstance` e devolvia o objeto cru; o
    chamador estourava com `AttributeError: get`. Achado no uso REAL — os testes
    passavam todos, porque o dublê deles era `dict`.

    E o sintoma era pior que o defeito: o executor da porta transforma exceção
    em Task `failed` com a razão dentro, então o terceiro recebia a string
    "AttributeError: get" e o log do servidor não tinha traceback nenhum.
    """
    from collections.abc import Mapping

    class _StructFalso:
        """Como o protobuf: responde a `items`/`__getitem__`, não a `get`."""

        def __init__(self, dados):
            self._d = dados

        def items(self):
            return self._d.items()

        def __getitem__(self, k):
            return self._d[k]

        def __iter__(self):
            return iter(self._d)

        def __len__(self):
            return len(self._d)

    class _MensagemFalsa:
        """Como a mensagem do SDK: `metadata` é ATRIBUTO, e o valor é o Struct."""

        def __init__(self, metadata):
            self.metadata = metadata

    Mapping.register(_StructFalso)
    assert isinstance(_StructFalso({}), Mapping)
    assert not hasattr(_StructFalso({}), "get"), "o dublê deixou de ser fiel"

    msg = _MensagemFalsa(_StructFalso({EXTENSION_URI: ["Memory"]}))
    assert requested_kinds(msg) == ["Memory"]

    # E a forma aninhada, onde o `.get` seria chamado no valor interno.
    aninhado = _MensagemFalsa(_StructFalso({EXTENSION_URI: {"kinds": ["Story"]}}))
    assert requested_kinds(aninhado) == ["Story"]
