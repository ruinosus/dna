"""``Copilot.created_by`` lido como RELATÓRIO — quem veio de onde, e quem não diz.

O par deste módulo é :mod:`dna_cli.solution_kind`'s ``unanswered_cost_question``:
uma pergunta cuja resposta é um FATO DECLARADO, cuja ausência é **não-respondida**
e cujo relatório fala em toda execução em vez de uma vez só.

Por que um relatório e não uma recusa
-------------------------------------
``created_by`` é opcional, e tem de ser: os 7 ``Copilot`` vivos medidos em
07/08/2026 (``Spec/spec-a-fabrica``) nasceram antes do campo existir, e pelo
menos um deles FOI gerado — o par ``Livro``/``escrita-de-livro``, Kind autorado
por tenant mais o copiloto que o compõe. Tornar o campo obrigatório invalidaria
os sete no dia da migração; presumir "escrito à mão" no silêncio deles
fabricaria um passado, que é a recusa que a i-137 do dna-cloud já tinha feito ao
NÃO dar blueprint retroativo aos mesmos sete.

Os quatro estados, e por que nenhum colapsa no outro
----------------------------------------------------
``answered``
    ``created_by`` nomeia um ``Copilot`` que existe. A procedência é legível.

``unanswered``
    O campo está ausente, nulo ou vazio. **Não é "escrito à mão"** — é ninguém
    ter respondido. A distinção é a razão deste módulo existir.

``dangling``
    O campo nomeia um criador que não existe no scope. Um DONO diferente do
    anterior: ``unanswered`` acusa quem nunca preencheu, ``dangling`` acusa um
    nome que nunca existiu (ou um alvo apagado). Imprimir a mesma palavra para
    os dois é o defeito que ``dna graph refs`` já corrigiu para as suas arestas.

``cycle``
    A cadeia volta a um copiloto já visitado — inclusive o caso de um copiloto
    que se declara criador de si mesmo. É uma AFIRMAÇÃO impossível, não uma
    lacuna, e reportá-la junto com ``dangling`` esconderia que a topologia está
    quebrada e não a referência.

A PROFUNDIDADE da cadeia
------------------------
``depth`` é o comprimento da cadeia ``created_by`` a partir de cada copiloto:
``0`` para quem não tem procedência declarada, ``1`` para quem foi criado por um
copiloto que não declara a sua, e assim por diante. Um copiloto que criou outro
que criou outro fica visível aqui como ``depth: 2``.

⚠️ Isto NÃO é um segundo mecanismo de travessia. A declaração é uma só —
``Copilot.spec.created_by``, com ``spec.relations`` a impondo na escrita — e
``dna graph refs Copilot <nome> --direction out --depth N`` a caminha pelo
``dna_edges``. O motivo de a profundidade também ser respondida AQUI é que o
grafo derivado exige um store que o produza: num scope de FS
(``GraphUnsupported``) a pergunta ficaria sem resposta, e a cadeia é justamente
o que a story pediu para conseguir responder. Dois leitores da mesma declaração,
nunca duas declarações.

A leitura que falha reporta o lado RUIDOSO
------------------------------------------
Um store ilegível não é "tudo respondido": a leitura é tentada uma vez e uma
falha devolve TODOS os copilotos como não-respondidos, com ``store_readable:
False`` dizendo o porquê. Verde por vacuidade é a classe de defeito que já cegou
três guardas nesta casa.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "COPILOT_KIND",
    "PROVENANCE_FIELD",
    "ProvenanceReport",
    "chain_depth",
    "provenance_report",
]

#: O Kind que este relatório lê — e o mesmo que ``created_by`` aponta, porque a
#: relação é reflexiva por desenho (a fábrica é feita do próprio material).
COPILOT_KIND = "Copilot"

#: O campo declarado em ``spec.relations.created_by`` do descritor. Uma
#: constante, e não a string solta em três lugares, pela mesma razão que
#: ``COST_FIELD`` é uma: o nome mudou de casa uma vez e vai mudar de novo.
PROVENANCE_FIELD = "created_by"


def _declared(spec: Any) -> str | None:
    """O criador declarado, ou ``None`` para as três formas de silêncio.

    Ausente, ``null`` e string vazia são o MESMO fato — ninguém respondeu — e
    ``relation_values`` no kernel faz exatamente esta leitura para não reportar
    uma relação opcional não preenchida como referência pendurada.
    """
    if not isinstance(spec, dict):
        return None
    value = spec.get(PROVENANCE_FIELD)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def chain_depth(name: str, creators: dict[str, str | None]) -> tuple[int, bool]:
    """``(profundidade, houve_ciclo)`` da cadeia ``created_by`` a partir de ``name``.

    ``creators`` mapeia cada copiloto EXISTENTE ao criador que ele declara (ou
    ``None``). Um passo até um nome fora do mapa — um ``dangling`` — conta como
    profundidade e PARA: a cadeia realmente tem aquele elo, e o que falta é o
    próximo, não este.

    O ciclo é detectado e devolvido em vez de levantar: uma topologia impossível
    é um achado do relatório, e um relatório que estoura no dado que existe para
    denunciar não denuncia nada.
    """
    visto = {name}
    profundidade = 0
    atual = creators.get(name)
    while atual:
        profundidade += 1
        if atual in visto:
            return profundidade, True
        visto.add(atual)
        if atual not in creators:  # dangling — o elo existe, o próximo não
            return profundidade, False
        atual = creators[atual]
    return profundidade, False


class ProvenanceReport(dict):
    """A saída, como ``dict`` para o ``--json`` não precisar de conversão.

    Chaves: ``answered``/``unanswered``/``dangling``/``cycles`` (listas de nomes,
    ordenadas), ``depths`` (nome → profundidade) e ``store_readable``.
    """

    @property
    def total(self) -> int:
        return (
            len(self["answered"]) + len(self["unanswered"]) + len(self["dangling"])
        )


def provenance_report(
    *, scope: str | None = None, tenant: str | None = None
) -> ProvenanceReport:
    """Quem declarou de onde veio, quem não declarou, e quem apontou para o nada.

    Vai e OLHA — lista os ``Copilot`` do scope pela porta pública
    (``session.query_list``) e resolve cada ``created_by`` contra essa mesma
    lista. Resolver contra a lista, e não com uma leitura por copiloto, é o que
    torna "o criador não existe" distinguível de "o criador existe e está mudo"
    numa passada só.
    """
    from dna_cli._ctx import open_session  # noqa: PLC0415 — o kernel é preguiçoso

    try:
        with open_session(scope) as session:
            instancias = session.query_list(COPILOT_KIND, tenant=tenant) or []
            creators = {
                str(inst.name): _declared(getattr(inst, "spec", None))
                for inst in instancias
            }
    except Exception:  # noqa: BLE001 — store ilegível reporta o lado ruidoso
        return ProvenanceReport(
            answered=[], unanswered=[], dangling=[], cycles=[],
            depths={}, store_readable=False,
        )

    answered: list[str] = []
    unanswered: list[str] = []
    dangling: list[str] = []
    cycles: list[str] = []
    depths: dict[str, int] = {}

    for name in sorted(creators):
        declarado = creators[name]
        profundidade, ciclo = chain_depth(name, creators)
        depths[name] = profundidade
        if ciclo:
            cycles.append(name)
        if declarado is None:
            unanswered.append(name)
        elif declarado in creators:
            answered.append(name)
        else:
            dangling.append(name)

    return ProvenanceReport(
        answered=answered, unanswered=unanswered, dangling=dangling,
        cycles=sorted(cycles), depths=depths, store_readable=True,
    )
