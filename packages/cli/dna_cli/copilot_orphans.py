"""Os ÓRFÃOS da cadeia ``Copilot → App`` — contados, nunca enumerados.

``Story/s-orfaos-viram-visiveis``, a última de ``f-conta-do-copiloto``.

Por que esta guarda existe, e o dia que ela torna visível
---------------------------------------------------------
``Spec/spec-app-e-o-servico`` fez o ``Copilot`` ganhar a relação ``runs_in →
App`` — a primeira relação de SAÍDA dele, a ponta que faltava para a cadeia
``Solution → App → Copilot`` deixar de terminar no vazio. Ela nasceu
**opcional**, e a decisão do founder está registrada com o número na tela:
obrigatória invalidaria de uma vez os copilotos vivos que nasceram antes do
campo existir.

A decisão vem com uma data que ninguém marcou no calendário:

    vira obrigatório no dia em que a contagem de órfãos chegar a zero — e a
    guarda é o que torna esse dia visível em vez de esquecido.

Este módulo é essa guarda. Ele não conserta nada e não impede nada; ele **conta
em voz alta**, toda vez que roda, e grita no dia em que a contagem zerar. É o
mesmo mecanismo de ``guard-app-wiring`` (dna-cloud) e de
``solution_kind.unanswered_cost_question``: o que impede que "faltando" pareça
"pronto".

⭐ AS CONTAGENS, e as duas que a story errou
--------------------------------------------
Medido em 08/08/2026 contra o store REAL (Postgres de dev, ``dna_instances``),
rodando este comando por scope+tenant:

| scope / tenant                 | sem App | arestas App→Copilot penduradas      |
| ------------------------------ | ------- | ----------------------------------- |
| ``dna-cloud``                  | 6 / 6   | 0 ref. declaradas (9 App, nenhum compõe) |
| ``tenant-demo`` / ``demo``     | 7 / 7   | **2 / 3**                           |
| ``tenant-ws-tazfol…`` / ``ws-…``| 8 / 8  | 0 / 2                               |
| união dos scopes               | **9/9** | **2 / 5**                           |

A story disse "5 de 7 sem ``runs_in``" e "2 de 4 arestas penduram". As duas
mereciam ser conferidas, e só uma sobreviveu:

⚠️ **"5 de 7" não é a contagem de ``runs_in``.** NENHUM copiloto do store
preenche o campo — nem um: 9 de 9. O cinco vem da frase da spec "cinco
copilotos não estão em App NENHUM", que é ``App.copilots`` (COMPOSIÇÃO), e não
``runs_in`` (EXECUÇÃO). São fatos diferentes, e não por sutileza: o cabeçalho de
``copilot.kind.yaml`` gasta trinta linhas medindo exatamente esse 1:N para
RECUSAR ``inverse_of`` entre os dois — no dna-cloud um deployment serve os sete
copilotos enquanto o console os agrupa em duas identidades. A story reuniu na
descrição dela os dois lados que o Kind separou de propósito. Esta guarda conta
os dois, em linhas diferentes, e nunca soma.

✅ **"2 de 4" bate** — e vale dizer contra o quê. O 07/08 leu ``dna_edges``
(``App|copilots||2``); esta guarda lê as DECLARAÇÕES. Os dois acham as mesmas 2
penduradas (``i116-app-quebrado`` → ``i116-copiloto-fantasma`` e
``i116-outro-fantasma``), com denominadores diferentes, e a diferença é o
motivo de não construir isto sobre o grafo derivado: medido na mesma passada,
``dna_edges`` carrega **1 aresta de um ``App`` que não existe mais**
(``estudio-pro-teste``, sem linha em ``dna_instances`` — apagado, arestas
deixadas para trás) e **não tem nenhuma das 2 de um ``App`` que existe**
(``estudio-editorial``, que declara dois copilotos). Uma guarda sobre
``dna_edges`` contaria a de um morto e perderia as de um vivo. A declaração é a
fonte; a aresta é uma projeção dela, e estava atrasada nos dois sentidos.

⛔ REGRA 1 — DERIVADA, jamais enumerada
--------------------------------------
Não há a string ``"runs_in"`` neste arquivo, nem ``"copilots"``. Os dois campos
são LIDOS do registro de Kinds, em ``relations_pair()``:

* o(s) campo(s) de ``Copilot`` cujo ``to`` inclui ``App``  → onde o copiloto roda
* o(s) campo(s) de ``App`` cujo ``to`` inclui ``Copilot``  → o que o App compõe

Renomeie ``runs_in``, acrescente uma segunda relação para ``App``, e a guarda
segue junto sem uma linha editada aqui. O custo de não fazer assim está medido
na irmã ``scripts/guard-app-wiring.mjs`` do dna-cloud: o regex dela **não casava
dígito**, e por isso perdeu o serviço ``a2a`` — justamente o que motivou a
guarda inteira. Uma lista à mão erra do mesmo jeito, só que sem regex para
culpar. O auto-teste abaixo planta um descritor com o campo RENOMEADO
exatamente para que essa classe de erro não volte.

⛔ REGRA 2 — universo vazio NÃO é "tudo certo", é RECUSA
-------------------------------------------------------
Zero ``Copilot`` na varredura significa **não há o que olhar**, e jamais "zero
órfãos". A distinção parece pedante até se medir o preço: esta armadilha mordeu
QUATRO vezes nesta casa em dois dias — o ``if not names: return []``, o catálogo
contando toda camada, a projeção opt-in do REST, e um
``test_every_relation_agrees_with_its_own_schema`` que passaria verde contra um
registro sem nenhuma relação array-de-objeto. Verde por vacuidade é
indistinguível de verde honesto, e é por isso que ``refusals`` existe e que a
porta sai com código 1 quando ela não está vazia.

São TRÊS os universos vazios, e cada um tem a sua linha:

1. nenhum ``Copilot`` lido            → recusa (nada a olhar)
2. ``Copilot`` não declara relação para ``App`` → recusa (a guarda perdeu o assunto)
3. ``App`` não declara relação para ``Copilot`` → recusa (idem, do outro lado)

⚠️ E um que **NÃO** é recusa, de propósito: zero ``App`` no scope. Medido em
08/08/2026, o scope de FS ``dna-cloud`` tem 6 ``Copilot`` e 0 ``App`` — recusar
ali seria uma guarda quebrada para um estado real. A pergunta dos órfãos TEM
universo (os 6, todos órfãos); a das arestas não tem. Então a segunda diz "não
há aresta a olhar" com todas as letras, e **nunca imprime um zero** que se leia
como "nenhuma pendurada".

⛔ REGRA 3 — ela REPORTA, não falha
----------------------------------
Órfão hoje é estado LEGÍTIMO: o campo é opcional por decisão registrada.
Reprovar por isso quebraria os copilotos vivos que funcionam. O único caminho de
saída != 0 é a REGRA 2 — quando a guarda é que está quebrada.

⭐ Onde ela mora, e por que não é uma seção de ``dna copilot provenance``
------------------------------------------------------------------------
A pergunta foi feita antes de escrever, com ``copilot_provenance.py`` e o teste
dele abertos, porque ``provenance`` é sobre o MESMO Kind e já reporta quatro
estados que não colapsam. Três medições a responderam, e a primeira sozinha
bastaria:

1. **Os contratos de saída se contradizem.** ``test_scope_sem_copiloto_nao_afirma_nada``
   fixa ``provenance`` em ``exit_code == 0`` + "nada afirmado" para um scope sem
   copiloto. O AC desta story exige o contrário: universo vazio **FALHA**. E as
   duas estão certas nos seus lugares — ``created_by`` pergunta pelo PASSADO, e
   um scope sem copiloto legitimamente não tem passado; a contagem de órfãos é
   um PORTÃO, e um portão que se abre sozinho num scope vazio anunciaria o dia
   errado. Um comando tem um código de saída só.
2. **O universo é outro.** ``provenance`` lê UM Kind por uma relação reflexiva.
   Isto lê DOIS Kinds por duas relações em direções opostas — e ``chain_depth``,
   o coração daquele módulo, não tem sentido aqui (``runs_in`` é ``cardinality:
   one`` e não é reflexiva: a cadeia tem no máximo um elo).
3. **A derivação é outra.** ``provenance`` fixa ``PROVENANCE_FIELD =
   "created_by"`` numa constante, e ali isso é defensável. Aqui a REGRA 1
   proíbe.

Ficam **irmãos no mesmo grupo** (``dna copilot orphans`` ao lado de ``dna
copilot provenance``), com uma linha de cada um apontando para o outro: são duas
perguntas sobre a mesma coisa, e quem faz uma costuma querer a outra.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "APP_KIND",
    "COPILOT_KIND",
    "OrphanReport",
    "classify",
    "orphan_report",
    "relations_pair",
    "self_test",
]

#: Os dois Kinds da cadeia. São nomes de KIND — não de campo. A REGRA 1 é sobre
#: os CAMPOS, que mudam quando alguém renomeia uma relação; o Kind é o assunto
#: da guarda e nomeá-lo é o que a define. Deriva-los também tornaria a guarda
#: incapaz de dizer QUE relação perdeu, que é metade do valor da recusa.
COPILOT_KIND = "Copilot"
APP_KIND = "App"


def relations_pair(ports: Any) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    """``(Copilot→App, App→Copilot)``, lidas do registro — a REGRA 1 em código.

    ``ports`` é o iterável de ``kind_ports()``. Devolve TUPLAS, não relações
    únicas: um Kind pode declarar mais de uma relação para o mesmo alvo, e a
    guarda que assumisse "uma" voltaria a ser uma lista à mão de tamanho 1. Um
    copiloto é órfão quando não preenche NENHUMA das relações que apontam para
    ``App``.

    Tuplas vazias são o sinal da recusa 2/3 da REGRA 2 e sobem intactas até
    ``classify`` — resolver silenciosamente para "nenhuma relação, logo nenhum
    órfão" é literalmente o verde por vacuidade que este módulo existe para
    recusar.
    """
    from dna.kernel.kinds.relations import relations_of  # noqa: PLC0415

    para_app: list[Any] = []
    para_copilot: list[Any] = []
    for port in ports or ():
        kind = getattr(port, "kind", None)
        if kind == COPILOT_KIND:
            para_app += [
                r for r in relations_of(port).values() if APP_KIND in r.to
            ]
        elif kind == APP_KIND:
            para_copilot += [
                r for r in relations_of(port).values() if COPILOT_KIND in r.to
            ]
    return tuple(para_app), tuple(para_copilot)


class OrphanReport(dict):
    """A saída, ``dict`` para o ``--json`` não precisar de conversão.

    Chaves:

    ``orphans``
        Copilotos que não declaram App nenhum. É A contagem — a que precisa
        chegar a zero para ``runs_in`` poder virar obrigatório.
    ``placed``
        Copilotos que declaram onde rodam.
    ``dangling_runs_in``
        ``[copiloto, app]`` em que o App declarado NÃO EXISTE. Dono diferente do
        órfão, e por isso lista própria: o órfão não respondeu; este respondeu
        errado. Colapsar os dois é o defeito que ``dna graph refs`` já corrigiu
        para as suas arestas, e que ``provenance`` separa em
        ``unanswered``/``dangling``.
    ``dangling_composition``
        ``[app, copiloto]`` em que o App compõe um copiloto inexistente — as
        "arestas penduradas" da story, medidas em 2 de 4.
    ``composition_refs``
        Total de referências ``App → Copilot`` declaradas. O denominador do
        anterior, e o que permite dizer "não há aresta a olhar" em vez de zero.
    ``copilots_seen`` / ``apps_seen``
        Os tamanhos dos dois universos. Existem para que a REGRA 2 seja
        VERIFICÁVEL na saída, não só honrada no código.
    ``to_app_fields`` / ``to_copilot_fields``
        Os campos que a guarda DERIVOU. Ficam na saída de propósito: é assim que
        alguém confere que ela ainda está olhando a relação certa depois de um
        rename, sem ler este arquivo.
    ``refusals``
        Não-vazio = a guarda não tem nada confiável a dizer, e a porta sai 1.
    ``ready``
        A contagem chegou a zero **e houve universo**. O dia.
    """

    @property
    def total(self) -> int:
        return self["copilots_seen"]


def classify(
    *,
    copilots: Mapping[str, Any],
    apps: Mapping[str, Any],
    para_app: tuple[Any, ...],
    para_copilot: tuple[Any, ...],
    store_readable: bool = True,
) -> OrphanReport:
    """O núcleo PURO: dois universos e duas relações entram, o relatório sai.

    Puro de propósito — é o que deixa o auto-teste plantar um órfão e um
    universo vazio sem store, sem sessão e sem I/O, e por isso rodar ANTES da
    varredura de verdade em toda invocação.

    ``copilots``/``apps`` mapeiam nome → ``spec`` da instância.
    """
    from dna.kernel.kinds.relations import relation_values  # noqa: PLC0415

    if not store_readable:
        # Sai AQUI, com uma recusa só. As recusas de descritor abaixo são
        # inalcançáveis quando a sessão nem abriu — empilhá-las diria "o Kind
        # Copilot não declara relação para App" sobre um registro que ninguém
        # conseguiu ler, que é uma segunda afirmação falsa em cima da primeira.
        return OrphanReport(
            orphans=[], placed=[], dangling_runs_in=[], dangling_composition=[],
            composition_refs=0, copilots_seen=0, apps_seen=0,
            to_app_fields=[], to_copilot_fields=[],
            refusals=[
                "o store não pôde ser lido — nada aqui é uma resposta sobre "
                "órfãos, e nenhum copiloto foi contado como colocado"
            ],
            ready=False,
        )

    refusals: list[str] = []
    if not para_app:
        refusals.append(
            f"o Kind {COPILOT_KIND} não declara relação nenhuma para "
            f"{APP_KIND} — a guarda perdeu o assunto dela. Foi um rename, ou o "
            f"registro não carregou?"
        )
    if not para_copilot:
        refusals.append(
            f"o Kind {APP_KIND} não declara relação nenhuma para "
            f"{COPILOT_KIND} — sem ela não há aresta que possa pendurar"
        )

    orphans: list[str] = []
    placed: list[str] = []
    dangling_runs_in: list[list[str]] = []
    # ⚠️ A contagem só acontece se a guarda SOUBER o que contar. Sem relação
    # para `App`, todo copiloto cairia em `orphans` — a resposta mais
    # convincente e mais falsa possível, porque a lacuna é da guarda e não dos
    # copilotos. As duas perguntas se calam INDEPENDENTEMENTE: perder a relação
    # de um lado não tem por que apagar a contagem do outro.
    if para_app:
        for nome in sorted(copilots):
            spec = copilots[nome]
            alvos = [a for rel in para_app for a in relation_values(rel, spec)]
            if not alvos:
                orphans.append(nome)
                continue
            placed.append(nome)
            for alvo in alvos:
                if alvo not in apps:
                    dangling_runs_in.append([nome, alvo])

    dangling_composition: list[list[str]] = []
    composition_refs = 0
    if para_copilot:
        for nome in sorted(apps):
            spec = apps[nome]
            for rel in para_copilot:
                for alvo in relation_values(rel, spec):
                    composition_refs += 1
                    if alvo not in copilots:
                        dangling_composition.append([nome, alvo])

    # ⛔ REGRA 2, e a ordem importa: esta recusa é avaliada DEPOIS da contagem,
    # sobre o universo REAL, e não sobre `orphans` — que num scope vazio seria
    # a lista vazia mais convincente do mundo.
    if not copilots:
        refusals.append(
            f"nenhum {COPILOT_KIND} na varredura — isso é NÃO HÁ O QUE OLHAR, "
            f"jamais zero órfãos. Scope errado, tenant errado, ou o store "
            f"mudou de forma?"
        )

    return OrphanReport(
        orphans=orphans,
        placed=placed,
        dangling_runs_in=dangling_runs_in,
        dangling_composition=dangling_composition,
        composition_refs=composition_refs,
        copilots_seen=len(copilots),
        apps_seen=len(apps),
        to_app_fields=sorted(r.name for r in para_app),
        to_copilot_fields=sorted(r.name for r in para_copilot),
        refusals=refusals,
        # ⚠️ `ready` exige universo E ausência de recusa. Sem as duas condições
        # o dia em que `runs_in` pode virar obrigatório seria anunciado por um
        # scope vazio, ou por um registro que perdeu a relação — a REGRA 2
        # escapando pela porta dos fundos, com a recusa registrada logo acima e
        # ignorada na linha seguinte. Amarrar em `refusals` e não em cada
        # condição é o que faz uma recusa NOVA calar o anúncio de graça.
        ready=not refusals and bool(copilots) and not orphans,
    )


def orphan_report(
    *, scope: str | None = None, tenant: str | None = None
) -> OrphanReport:
    """Vai e OLHA: lê os dois Kinds pela porta pública e classifica.

    Uma leitura por Kind, e a resolução feita CONTRA essas listas — não com um
    ``get_doc`` por referência. É o que torna "o alvo não existe" distinguível
    de "o alvo existe" numa passada só, e é o mesmo desenho de
    ``provenance_report``.

    Uma leitura que estoura devolve ``store_readable: False`` e uma recusa, e
    NUNCA zero órfãos.
    """
    from dna_cli._ctx import open_session  # noqa: PLC0415 — o kernel é preguiçoso

    try:
        with open_session(scope) as session:
            para_app, para_copilot = relations_pair(session.kernel.kind_ports())
            copilots = {
                str(i.name): getattr(i, "spec", None)
                for i in (session.query_list(COPILOT_KIND, tenant=tenant) or [])
            }
            apps = {
                str(i.name): getattr(i, "spec", None)
                for i in (session.query_list(APP_KIND, tenant=tenant) or [])
            }
    except Exception as exc:  # noqa: BLE001 — store ilegível reporta o lado ruidoso
        rel = classify(
            copilots={}, apps={}, para_app=(), para_copilot=(),
            store_readable=False,
        )
        rel["refusals"] = [f"{rel['refusals'][0]} — {exc}"]
        return rel

    return classify(
        copilots=copilots, apps=apps,
        para_app=para_app, para_copilot=para_copilot,
    )


# ── auto-teste ───────────────────────────────────────────────────────────────
#
# ⭐ Ele roda ANTES da varredura, em TODA invocação — não só sob uma flag.
# `guard-app-wiring.mjs` faz o mesmo e diz por quê: uma guarda cujo auto-teste
# não roda antes dela mesma não é confiável, porque o relatório verde dela é
# indistinguível de um relatório que não sabe mais olhar. Custa microssegundos:
# `classify` é puro.


def _rel(nome: str, alvo: str, cardinality: str):
    """Uma ``Relation`` de verdade, pelo normalizador do kernel.

    Construída pelo mesmo caminho que o registro usa, e não um dublê com
    ``.name``/``.to``: um auto-teste que inventa a sua própria forma de relação
    prova que a guarda funciona contra a invenção, não contra o kernel.
    """
    from dna.kernel.kinds.relations import normalize_relations  # noqa: PLC0415

    return normalize_relations({nome: {"to": alvo, "cardinality": cardinality}})[nome]


def self_test() -> list[tuple[str, bool]]:
    """``[(caso, passou)]`` — a guarda tem de ACUSAR o que existe para acusar."""
    # ⭐ O campo se chama `roda_em`, e não `runs_in`, DE PROPÓSITO: se alguma
    # linha desta guarda tivesse o nome literal do campo, este caso quebraria.
    # É o análogo do serviço com dígito no nome da guarda irmã — o caso plantado
    # contra a classe de erro que a enumeração causa.
    roda_em = (_rel("roda_em", APP_KIND, "one"),)
    compoe = (_rel("compoe", COPILOT_KIND, "many"),)

    universo = {
        "sem-campo": {"mounts": []},
        "campo-nulo": {"roda_em": None},
        "campo-vazio": {"roda_em": "   "},
        "colocado": {"roda_em": "porta"},
        "aponta-fantasma": {"roda_em": "porta-que-nao-existe"},
    }
    apps = {
        "porta": {"compoe": ["colocado", "copiloto-fantasma"]},
        "porta-vazia": {"title": "sem copiloto, e é legítimo"},
    }
    r = classify(copilots=universo, apps=apps, para_app=roda_em, para_copilot=compoe)

    casos: list[tuple[str, bool]] = [
        (
            "as TRÊS formas do silêncio (ausente, null, vazio) são órfãos",
            r["orphans"] == ["campo-nulo", "campo-vazio", "sem-campo"],
        ),
        ("quem declara onde roda NÃO é órfão", r["placed"] == ["aponta-fantasma", "colocado"]),
        (
            "quem aponta um App inexistente é PENDURADO, e não órfão — ele "
            "respondeu, e a resposta é que está errada",
            r["dangling_runs_in"] == [["aponta-fantasma", "porta-que-nao-existe"]]
            and "aponta-fantasma" not in r["orphans"],
        ),
        (
            "uma referência App→Copilot que não resolve é ACUSADA",
            r["dangling_composition"] == [["porta", "copiloto-fantasma"]],
        ),
        (
            "um App sem copiloto nenhum não inventa aresta",
            r["composition_refs"] == 2,
        ),
        # ⭐ REGRA 1: o campo derivado tem nome ARBITRÁRIO e a guarda o segue.
        (
            "o campo é DERIVADO do descritor — `roda_em`, não um literal",
            r["to_app_fields"] == ["roda_em"] and r["to_copilot_fields"] == ["compoe"],
        ),
        ("com órfãos, a guarda não anuncia o dia", r["ready"] is False),
        ("com universo e sem recusa, ela REPORTA (regra 3)", r["refusals"] == []),
    ]

    # ⛔ REGRA 2, os três universos vazios.
    vazio = classify(copilots={}, apps=apps, para_app=roda_em, para_copilot=compoe)
    casos += [
        (
            "universo vazio RECUSA — não é zero órfãos",
            bool(vazio["refusals"]) and vazio["orphans"] == [],
        ),
        (
            "e um universo vazio JAMAIS anuncia o dia",
            vazio["ready"] is False,
        ),
        # ⚠️ E ela não pode reportar TODO MUNDO como órfão nesse caso: a lacuna
        # é da guarda, não dos copilotos — e `ready` também tem de calar, senão
        # "zero órfãos" viraria "o dia chegou".
        (
            "sem relação Copilot→App declarada, RECUSA e não acusa ninguém",
            (
                lambda x: bool(x["refusals"])
                and x["orphans"] == []
                and x["placed"] == []
                and x["ready"] is False
            )(
                classify(
                    copilots=universo, apps=apps, para_app=(), para_copilot=compoe
                )
            ),
        ),
        (
            "sem relação App→Copilot declarada, RECUSA — e a contagem de "
            "órfãos, que não depende dela, continua sendo feita",
            (
                lambda x: bool(x["refusals"])
                and x["orphans"] == ["campo-nulo", "campo-vazio", "sem-campo"]
                and x["composition_refs"] == 0
            )(
                classify(
                    copilots=universo, apps=apps, para_app=roda_em, para_copilot=()
                )
            ),
        ),
        (
            "store ilegível RECUSA e não conta ninguém como colocado",
            (
                lambda x: bool(x["refusals"]) and x["placed"] == [] and not x["ready"]
            )(
                classify(
                    copilots={}, apps={}, para_app=roda_em,
                    para_copilot=compoe, store_readable=False,
                )
            ),
        ),
    ]

    # ⭐ O dia: zero órfãos, com universo, ANUNCIA.
    zerado = classify(
        copilots={"colocado": {"roda_em": "porta"}},
        apps={"porta": {"compoe": ["colocado"]}},
        para_app=roda_em, para_copilot=compoe,
    )
    casos.append(
        (
            "zero órfãos COM universo anuncia o dia de `runs_in` obrigatório",
            zerado["ready"] is True and zerado["refusals"] == [],
        )
    )

    # ⚠️ E o que NÃO é recusa: zero App é estado real (o scope de FS `dna-cloud`
    # tem 6 Copilot e 0 App, medido em 08/08/2026). A pergunta dos órfãos tem
    # universo; a das arestas não — e a segunda diz isso em vez de imprimir 0.
    sem_app = classify(
        copilots=universo, apps={}, para_app=roda_em, para_copilot=compoe
    )
    casos.append(
        (
            "zero App NÃO é recusa — é a segunda pergunta sem universo",
            sem_app["refusals"] == []
            and sem_app["apps_seen"] == 0
            and sem_app["composition_refs"] == 0,
        )
    )
    return casos
