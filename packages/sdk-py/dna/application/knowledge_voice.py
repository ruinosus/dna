"""A VOZ que proíbe afirmar em cima de trecho fraco — e ela é METADE da entrega.

## Por que isto é um módulo, e não uma f-string no prompt do agente

Voz de agente é DADO. Um texto que decide como o produto SOA para o cliente não
pode morar como constante no meio do código: ninguém o encontra, ninguém o
revisa, e um tenant que precisa de outra voz não tem onde mudá-la. O catálogo de
``PromptTemplate`` é onde ele mora, e :mod:`dna.prompt_defaults` é o degrau que
deixa o default do SDK ser servido pela MESMA porta que serve as instâncias, com
a ORIGEM dita (``origin="runtime-default"``) — sem virar instância, para que uma
melhoria do SDK alcance todo mundo no próximo release em vez de exigir migração.

## Por que ela existe

A decisão do fundador (08/08/2026, i-154) é **(b) + (c)**: devolver os N
melhores E dizer que podem não servir, cada trecho citado com a fonte. A opção
**(a)** — o copiloto dizer *"não achei nada"* — foi RECUSADA porque exigiria um
piso de relevância que a medição provou não existir: **8 de 12 consultas
irrelevantes pontuam acima da pior relevante** (i-103).

⚠️ **Sem esta voz, (b) vira (a) na prática.** A busca entrega os N melhores com
``relevance_notice`` dizendo que rank não é relevância — e o modelo, que lê os N
melhores como se fossem a resposta, afirma assim mesmo. O envelope honesto
chegaria ao cliente como uma afirmação confiante, que é exatamente o resultado
que (a) foi recusada para evitar. A porta entrega a incerteza; esta voz é o que
faz o agente NÃO a descartar.

⭐ O mesmo desenho do ``degraded``/``relevance_notice`` que ``search_instances``
já entrega, um degrau acima: a porta não esconde a incerteza, e o agente não tem
licença para escondê-la depois.
"""
from __future__ import annotations

from dna.prompt_defaults import register_prompt_default

__all__ = ["KNOWLEDGE_GROUNDING_TEMPLATE", "KNOWLEDGE_GROUNDING_DEFAULT"]

#: O nome pelo qual esta voz é resolvida no catálogo.
KNOWLEDGE_GROUNDING_TEMPLATE = "knowledge-grounding-briefing"

KNOWLEDGE_GROUNDING_DEFAULT = """\
Os trechos abaixo vieram da base de conhecimento deste workspace por busca por \
semelhança. Leia esta advertência antes de usá-los.

⚠️ ELES ESTÃO ORDENADOS, NÃO FILTRADOS. A busca devolve sempre os melhores que \
encontrou — mesmo quando nenhum serve. Um trecho aparecer no topo significa que \
ele foi o MENOS diferente da pergunta, e não que ele a responda. Nesta base, \
consultas sobre assuntos ausentes pontuam rotineiramente acima de trechos \
genuinamente relevantes, então a posição e o score NÃO são evidência.

Como responder:

1. Decida por LEITURA, nunca por posição. Um trecho só sustenta uma afirmação \
se ele efetivamente DIZ aquilo. Se você precisa completar o que ele diz para \
que ele responda, ele não responde.
2. CITE o que usar — o nome do arquivo, e onde dentro dele. Toda frase que \
afirme um fato tirado daqui vem com a fonte colada nela. Uma afirmação sem \
fonte, num turno que consultou a base, é indistinguível de uma inventada.
3. Se os trechos não sustentam a resposta, DIGA ISSO — e diga o que encontrou \
em vez de encontrar o que foi pedido. "A base tem material sobre X, mas nada \
sobre o que você perguntou" é uma resposta útil, correta e verificável.
4. NUNCA preencha lacuna com conhecimento geral fingindo que veio da base. Se \
você complementar com o que já sabe, diga que é seu, não do documento.

⛔ O erro que esta instrução existe para impedir: transformar "estes foram os \
mais próximos" em "isto é o que a base diz". Eles não são a mesma frase, e só \
uma delas é verdadeira.

Trechos:

{chunks}
"""

register_prompt_default(
    KNOWLEDGE_GROUNDING_TEMPLATE,
    description=(
        "A voz que acompanha os trechos da base de conhecimento no prompt: ela "
        "PROÍBE afirmar com base em trecho fraco e EXIGE citação da fonte. É a "
        "metade da decisão (b)+(c) do fundador que não mora na porta de busca — "
        "sem ela o envelope honesto da busca chega ao cliente como afirmação "
        "confiante. A variável {chunks} é OBRIGATÓRIA: sem ela o agente receberia "
        "a advertência sem o material a que ela se refere."
    ),
    body=lambda: KNOWLEDGE_GROUNDING_DEFAULT,
    variables=("chunks",),
    module=__name__,
)
