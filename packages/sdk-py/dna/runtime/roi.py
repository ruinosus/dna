"""A leitura que cruza CUSTO e RENDIMENTO — e diz, alto, quando não dá para calcular.

`Spec/spec-rendimento-do-copiloto` · `Story/s-leitura-do-rendimento`.

O custo de um turno está gravado (`dna_turn`: tokens, modelo, duração), o
desfecho passou a estar (``outcome``, revisão 0012), a aceitação do humano
também (`dna_approval`), e o valor de um desfecho é DECLARADO no Kind
(`Copilot.value_per_outcome`). Este módulo é o único lugar onde essas quatro
coisas se encontram — e o que ele mais faz é **recusar-se a inventar**.

## As três regras, e elas mandam mais que qualquer número

**1. Sem `value_per_outcome` não há ROI — há contagem.** A leitura devolve
:class:`NotCalculable` com o motivo. Nunca zero, nunca estimativa. Presumir
zero renderizaria todo copiloto da frota como custo puro; presumir qualquer
outra coisa seria inventar o único número da cadeia que **não se mede**.

**2. Todo número derivado de proxy carrega o rótulo.** Contenção e taxa de
aceitação NÃO medem valor entregue — medem trabalho terminado sozinho e
concordância de quem revisou. Por isso :class:`Number` não tem construtor sem
``basis`` e sem ``source``: um número sai daqui com a procedência colada nele
ou não sai.

**3. ⭐ Vazio não é zero, e este módulo nasceu com a prova na mão.** MEDIDO no
Postgres de desenvolvimento em 08/08/2026: **85 turnos, ZERO com desfecho
declarado.** A coluna existe desde a 0012 e nada a preenche ainda. Uma leitura
que devolvesse "contenção 0%" sobre isso estaria afirmando que o copiloto não
resolveu nada, quando o que houve foi **ninguém declarar**. São afirmações
opostas e o mesmo zero as escreveria.

    Esta casa já pagou o erro duas vezes no mesmo dia (07/08): uma guarda com
    ``if not names: return []`` — verde por vacuidade — e um catálogo que
    contava "sem resposta" para toda camada. A correção do PR #354
    (``declaration_gaps.nothing_to_look_at``) é a mesma daqui: **vazio é um
    ACHADO**, e :attr:`YieldReading.nothing_to_look_at` o diz por nome.

## Qual das técnicas de mercado esta leitura responde

ROI de agente tem três técnicas, e elas não valem o mesmo (a tabela é da spec):

======================  ================================  ==========  ==========
técnica                 o que mede                        exige       rigor
======================  ================================  ==========  ==========
contenção / deflection  % concluído sem escalar           desfecho    **proxy**
redução de AHT          o mesmo trabalho, com e sem       linha-base  proxy melhor
holdout / A-B           diferença causal                  metade sem  **prova**
======================  ================================  ==========  ==========

**Esta leitura responde a PRIMEIRA, e só ela** (:data:`TECHNIQUE_ANSWERED`).
Não há linha de base para AHT e não há volume para holdout — as duas estão
declaradas como não-respondidas em :data:`TECHNIQUES_NOT_ANSWERED`, porque
"a maioria das empresas faz a primeira e chama de ROI" é justamente o erro que
este módulo existe para não cometer em silêncio.

## O viés que inclina a conta a favor do agente

Um turno cujo uso é ILEGÍVEL (``tokens_partial = true``: houve chamada ao
modelo e ela não reportou uso) não pode entrar na conta como se tivesse custado
zero — o provedor cobrou o prompt. E um turno anterior à 0012
(``tokens_partial IS NULL``) não pode ser declarado fechado. Nos dois casos o
número que sai daqui é um **PISO** (:attr:`Number.is_floor`), e ele diz que é.

A assimetria é deliberada: o piso vale para o CUSTO (que é subestimado) e
também para o VALOR (subestimado por turnos sem desfecho declarado). Quando as
duas pontas são piso, a **razão** entre elas não é limite de lado nenhum, e a
leitura anota isso em vez de fingir uma direção.

## O que este módulo NÃO faz

Não abre conexão. A regra é daqui, o I/O é de quem tem o cliente — a mesma
fronteira de `dna.runtime.telemetry`, e o que torna esta lógica exercitável
**sem banco e sem rede**. Quem tem a conexão usa :func:`gather_sample`, que
agrega no banco; quem tem as linhas usa :func:`sample_from_turns`. Os dois
produzem o MESMO :class:`Sample`, e é isso que um teste consegue medir.

E não tem tabela de preço de modelo. **Medido em 08/08/2026: não existe nenhuma
neste repositório** — nem Kind, nem constante, nem arquivo. Preço de token muda
de semana em semana e é fato do CONTRATO de quem opera, não do SDK; uma tabela
embutida aqui envelheceria em silêncio e produziria dinheiro errado com cara de
medição. Então o preço é DECLARADO pelo chamador (:class:`ModelPrice`), e sem
ele o custo em dinheiro é :class:`NotCalculable` — o que corrige, de passagem,
a afirmação da spec de que *"o custo já é exato, nada falta"*: exata é a
contagem de TOKENS; o dinheiro depende de um preço que ninguém declarou ainda.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from dna.runtime.telemetry import OUTCOMES

__all__ = [
    "CONSTANT",
    "DECISIONS",
    "DECLARED",
    "MEASURED",
    "ModelPrice",
    "NotCalculable",
    "Number",
    "PROXY",
    "STANDING_REPLICA_USD_MONTH",
    "Sample",
    "TECHNIQUE_ANSWERED",
    "TECHNIQUES_NOT_ANSWERED",
    "TokenUse",
    "ValuePerOutcome",
    "YieldReading",
    "gather_sample",
    "read_yield",
    "render",
    "sample_from_turns",
    "value_per_outcome",
]

# ── a procedência de cada número ─────────────────────────────────────────────
#
# ⭐ Quatro palavras, e elas não são decoração: são a diferença entre um número
# que alguém pode usar para decidir e um número que alguém vai usar para decidir
# achando que é outra coisa.

#: Contado no registro. `dna_turn`, `dna_approval` — aconteceu e está gravado.
MEASURED = "MEASURED"
#: Dito por um humano no descritor. `value_per_outcome`, `can_sleep`. Não se
#: mede, não se infere, e a ausência é um achado — nunca um default.
DECLARED = "DECLARED"
#: ⚠️ Derivado, e NÃO mede o que parece medir. Contenção não é valor entregue;
#: aceitação não é qualidade. São defensáveis e não são prova.
PROXY = "PROXY"
#: Constante MEDIDA uma vez, fora deste sistema, e carregada à mão. Não é
#: leitura de fatura e não se atualiza sozinha — ver
#: :data:`STANDING_REPLICA_USD_MONTH`.
CONSTANT = "CONSTANT"

BASES = frozenset({MEASURED, DECLARED, PROXY, CONSTANT})

#: O vocabulário do HITL. ⚠️ Enumerado aqui e GUARDADO contra o original: o
#: dono é `dna.runtime.middleware.hitl.dna_hitl_middleware(allowed_decisions=…)`,
#: e `test_o_vocabulario_de_decisao_nao_DIVERGE_do_middleware` fica vermelho se
#: os dois andarem para lados diferentes. Copiar sem guarda é como as duas
#: listas desta casa divergiram antes.
DECISIONS = ("approve", "edit", "reject")

#: A técnica que esta leitura responde, pelo nome que o mercado usa.
TECHNIQUE_ANSWERED = "contenção / deflection (proxy)"

#: E as que ela NÃO responde, com o motivo — porque "a maioria das empresas faz
#: a primeira e chama de ROI", e não dizer qual foi feita é como isso acontece.
TECHNIQUES_NOT_ANSWERED = (
    "redução de AHT — exige uma linha de base do mesmo trabalho sem o agente, "
    "e não existe nenhuma",
    "holdout / A-B — exige metade dos usuários sem o agente, e não há volume",
)

#: ⚠️ O custo de um App que NÃO dorme, em US$/mês. CONSTANTE MEDIDA em
#: 31/07/2026 no dna-cloud — o serviço `copilot`, com `minReplicas: 1`, foi
#: US$ 94,43 de uma fatura de US$ 230,29 — e arredondada para baixo no
#: `CLAUDE.md` como "~US$ 90/mês". **Não é leitura de fatura**: ninguém aqui
#: fala com o billing do Azure, e o número não se atualiza sozinho. Sai desta
#: leitura com `basis=CONSTANT` justamente para não ser confundida com a
#: contagem de tokens, que é medição de verdade.
STANDING_REPLICA_USD_MONTH = 90.0

# ── os motivos de não dar para calcular ──────────────────────────────────────

NO_TURNS = "no_turns"
NO_OUTCOME_DECLARED = "no_outcome_declared"
NO_VALUE_PER_OUTCOME = "no_value_per_outcome"
NO_MODEL_PRICE = "no_model_price"
NO_APPROVALS = "no_approvals"
NO_APP = "no_app"
CAN_SLEEP_UNDECLARED = "can_sleep_undeclared"
CURRENCY_MISMATCH = "currency_mismatch"
COST_IS_ZERO = "cost_is_zero"
UPSTREAM_NOT_CALCULABLE = "upstream_not_calculable"


@dataclass(frozen=True)
class NotCalculable:
    """Não dá para calcular, e **por quê** — que é a metade que importa.

    ⭐ Este tipo existe para que a ausência tenha uma FORMA. Um ``None``
    devolvido no lugar de um número atravessa qualquer soma como zero na
    primeira vez que alguém esquecer de testar; um objeto com ``reason`` não
    atravessa nada e obriga quem lê a decidir o que mostrar.
    """

    #: Código estável — dá para ramificar sem casar frase.
    reason: str
    #: A frase para um humano. Diz o que falta, não "erro".
    detail: str
    #: O que exatamente falta (modelos sem preço, campos não declarados…).
    missing: tuple[str, ...] = ()

    def __str__(self) -> str:  # pragma: no cover - conveniência de log
        falta = f" ({', '.join(self.missing)})" if self.missing else ""
        return f"NÃO CALCULÁVEL: {self.detail}{falta}"


@dataclass(frozen=True)
class Number:
    """Um número que NÃO ANDA SOZINHO — unidade, procedência e origem juntas.

    ⚠️ ``basis`` e ``source`` são obrigatórios e validados no construtor, e é
    de propósito: um `Number` sem procedência não chega a existir. A regra 2
    da spec ("todo número derivado de proxy carrega o rótulo") só é uma regra
    se for impossível produzir o número sem ela.
    """

    value: float
    #: "USD", "tokens", "%", "×", "USD/mês" — o que o `value` conta.
    unit: str
    #: Um de :data:`BASES`.
    basis: str
    #: De onde ele veio, em uma frase que um humano lê ao lado do número.
    source: str
    #: ⚠️ O valor é um PISO — o real é >= este. Ver "o viés" no topo.
    is_floor: bool = False

    def __post_init__(self) -> None:
        if self.basis not in BASES:
            raise ValueError(
                f"procedência {self.basis!r} não é uma de {sorted(BASES)} — "
                "um número sem procedência conhecida não sai daqui"
            )
        if not (self.source or "").strip():
            raise ValueError(
                "um número sem origem declarada não sai daqui "
                "(veja a regra 2 no topo do módulo)"
            )

    @property
    def label(self) -> str:
        """O rótulo que ACOMPANHA o número onde quer que ele apareça."""
        piso = " ≥ PISO" if self.is_floor else ""
        return f"[{self.basis}{piso}]"

    def __str__(self) -> str:
        return f"{_num(self.value)} {self.unit} {self.label}"


#: O que uma pergunta devolve: um número com procedência, ou o motivo de não
#: haver número. Nunca ``None``, nunca zero fabricado.
Answer = "Number | NotCalculable"


@dataclass(frozen=True)
class ModelPrice:
    """O preço de um modelo, DECLARADO por quem opera.

    Por milhão de tokens, que é como os provedores publicam. ``currency`` é
    declarada e nunca presumida, pela mesma razão que `value_per_outcome` exige
    a dela: uma taxa cuja moeda foi assumida está errada por um fator de cinco
    na primeira frota que mistura duas.
    """

    input_per_million: float
    output_per_million: float
    currency: str

    def cost_of(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_per_million
            + output_tokens * self.output_per_million
        ) / 1_000_000


@dataclass(frozen=True)
class ValuePerOutcome:
    """Quanto vale UM desfecho resolvido — declarado, nunca medido.

    ⭐ É o único número da cadeia inteira que não existe em telemetria nenhuma:
    quanto um humano teria gasto fazendo aquilo à mão não é observável de dentro
    do sistema que o substituiu.
    """

    human_minutes: float
    hourly_cost: float
    currency: str

    @property
    def per_outcome(self) -> float:
        return self.human_minutes / 60.0 * self.hourly_cost


@dataclass(frozen=True)
class TokenUse:
    """O uso de um modelo dentro da amostra — e os DOIS zeros separados."""

    input_tokens: int = 0
    output_tokens: int = 0
    #: Quantos turnos passaram por este modelo.
    turns: int = 0
    #: ⚠️ Turnos com ``tokens_partial = true``: houve chamada ao modelo e ela
    #: não reportou uso. O provedor cobrou; a contagem é um PISO.
    unreadable_turns: int = 0
    #: Turnos com ``tokens_partial IS NULL`` — anteriores à 0012. Ninguém
    #: estava olhando; não dá para afirmar que a conta está fechada.
    unknown_turns: int = 0

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def needs_price(self) -> bool:
        """Este modelo precisa de preço para virar dinheiro?

        ⚠️ Um balde com zero token mas com turno ILEGÍVEL precisa: o zero dele
        é o zero mentiroso, e sem preço não há como dizer sequer o piso.
        """
        return self.tokens > 0 or self.unreadable_turns > 0


def _somar(a: TokenUse, b: TokenUse) -> TokenUse:
    return TokenUse(
        input_tokens=a.input_tokens + b.input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
        turns=a.turns + b.turns,
        unreadable_turns=a.unreadable_turns + b.unreadable_turns,
        unknown_turns=a.unknown_turns + b.unknown_turns,
    )


@dataclass(frozen=True)
class Sample:
    """O que foi CONTADO. A entrada da leitura, e a única.

    Duas coisas produzem um `Sample` — :func:`sample_from_turns` (as linhas na
    mão) e :func:`gather_sample` (a agregação no banco) — e elas têm de
    concordar. Ter UM tipo de entrada é o que torna essa concordância uma
    asserção possível em vez de uma esperança.
    """

    #: ⭐ Quantos turnos foram OLHADOS. Zero aqui não é "tudo certo": é
    #: :attr:`YieldReading.nothing_to_look_at`, que é um achado.
    turns: int = 0
    #: desfecho → contagem. **Só os DECLARADOS e válidos.** Um turno sem
    #: desfecho não aparece aqui, e é isso que impede vazio de virar zero.
    outcomes: Mapping[str, int] = field(default_factory=dict)
    #: modelo → uso. A chave ``""`` é o turno que morreu antes de qualquer
    #: chamada ao modelo (7 dos 9 erros medidos em 07/08) — zero legítimo.
    usage: Mapping[str, TokenUse] = field(default_factory=dict)
    #: decisão → contagem, restrito a :data:`DECISIONS`.
    decisions: Mapping[str, int] = field(default_factory=dict)
    #: Aprovações pedidas e ainda não decididas — fora do denominador da taxa
    #: de aceitação, porque uma pendência não é uma concordância.
    undecided: int = 0

    @property
    def declared_outcomes(self) -> int:
        return sum(self.outcomes.values())

    @property
    def undeclared_outcomes(self) -> int:
        """Turnos que NÃO declararam desfecho. Hoje, no dev, são todos."""
        return max(0, self.turns - self.declared_outcomes)

    @property
    def resolved(self) -> int:
        return self.outcomes.get("resolved", 0)

    @property
    def input_tokens(self) -> int:
        return sum(u.input_tokens for u in self.usage.values())

    @property
    def output_tokens(self) -> int:
        return sum(u.output_tokens for u in self.usage.values())

    @property
    def unreadable_turns(self) -> int:
        return sum(u.unreadable_turns for u in self.usage.values())

    @property
    def unknown_usage_turns(self) -> int:
        return sum(u.unknown_turns for u in self.usage.values())

    @property
    def usage_is_floor(self) -> bool:
        """A soma de tokens é um PISO — alguém consumiu e não reportou."""
        return self.unreadable_turns > 0 or self.unknown_usage_turns > 0

    @property
    def decided(self) -> int:
        return sum(self.decisions.values())


# ── de linhas para amostra ───────────────────────────────────────────────────


def _campo(linha: Any, nome: str) -> Any:
    """O campo, venha a linha como `Mapping` (banco) ou objeto (`Turn`)."""
    if isinstance(linha, Mapping):
        return linha.get(nome)
    return getattr(linha, nome, None)


def _desfecho(linha: Any) -> str:
    """O desfecho DECLARADO nesta linha, ou ``""``.

    ⭐ O vocabulário é importado de `dna.runtime.telemetry.OUTCOMES` — o mesmo
    da porta de escrita, e nunca uma segunda cópia. Um valor fora dele (``ok``,
    ``sucesso``, um typo) sai como vazio: contá-lo o faria entrar numa
    estatística que não sabe o que ele significa.

    E o que a função NÃO faz continua sendo o ponto: não olha ``status``, não
    tem fallback, não tem "se não disseram, deu certo".
    """
    valor = _campo(linha, "outcome")
    texto = str(valor or "").strip().lower()
    return texto if texto in OUTCOMES else ""


def _int(valor: Any) -> int:
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0


def sample_from_turns(
    turns: Iterable[Any], approvals: Iterable[Any] = ()
) -> Sample:
    """Conta linhas de ``dna_turn`` / ``dna_approval`` numa :class:`Sample`.

    Aceita `Mapping` (o que um cursor devolve) ou objeto com atributos (o
    :class:`~dna.runtime.telemetry.Turn` do recorder) — as duas formas do mesmo
    fato, e nenhuma delas obriga um banco a existir para exercitar a regra.
    """
    total = 0
    desfechos: dict[str, int] = {}
    uso: dict[str, TokenUse] = {}
    for linha in turns:
        total += 1
        desfecho = _desfecho(linha)
        if desfecho:
            desfechos[desfecho] = desfechos.get(desfecho, 0) + 1
        parcial = _campo(linha, "tokens_partial")
        modelo = str(_campo(linha, "model") or "")
        uso[modelo] = _somar(
            uso.get(modelo, TokenUse()),
            TokenUse(
                input_tokens=_int(_campo(linha, "input_tokens")),
                output_tokens=_int(_campo(linha, "output_tokens")),
                turns=1,
                unreadable_turns=1 if parcial is True else 0,
                unknown_turns=1 if parcial is None else 0,
            ),
        )

    decisoes: dict[str, int] = {}
    pendentes = 0
    for linha in approvals:
        decisao = str(_campo(linha, "decision") or "").strip().lower()
        if decisao in DECISIONS:
            decisoes[decisao] = decisoes.get(decisao, 0) + 1
        else:
            # Inclui a pendência (``''``) E o valor estranho. Os dois estão
            # fora do denominador pelo mesmo motivo: não são uma concordância.
            pendentes += 1

    return Sample(
        turns=total,
        outcomes=desfechos,
        usage=uso,
        decisions=decisoes,
        undecided=pendentes,
    )


async def gather_sample(
    connection: Any,
    tables: Any,
    *,
    workspace: str | None = None,
    agent: str | None = None,
    since: Any = None,
    until: Any = None,
) -> Sample:
    """A mesma :class:`Sample`, agregada NO BANCO — a porta desta leitura.

    ``connection`` é uma ``AsyncConnection`` do SQLAlchemy e ``tables`` o
    ``Tables`` de :func:`dna.adapters.sqlalchemy_.schema.build_metadata`. Só
    agregados viajam de volta: a pergunta é "quantos", nunca "quais", e trazer
    85 mil linhas para contá-las em Python seria a mesma coisa com uma fatura
    maior.

    ⚠️ **Postgres.** ``dna_turn`` e ``dna_approval`` são tabelas de plano de
    controle e não existem num self-host SQLite (revisões 0004/0005) — ali
    ``tables.turn`` é ``None``, e chamar isto levanta em vez de devolver uma
    amostra vazia. Vazio significaria "nenhum turno", e o que houve foi "esta
    pergunta não se faz aqui": as duas coisas não podem sair pela mesma porta.
    """
    import sqlalchemy as sa

    turn = getattr(tables, "turn", None)
    approval = getattr(tables, "approval", None)
    if turn is None or approval is None:
        raise RuntimeError(
            "dna_turn/dna_approval não existem neste dialeto (Postgres-only, "
            "revisões 0004/0005) — uma amostra vazia aqui seria lida como "
            "'nenhum turno', que é outra afirmação"
        )

    def _onde(tabela: Any) -> list[Any]:
        filtros: list[Any] = []
        if workspace is not None:
            filtros.append(tabela.c.workspace == workspace)
        if since is not None:
            filtros.append(_quando(tabela) >= since)
        if until is not None:
            filtros.append(_quando(tabela) < until)
        return filtros

    def _quando(tabela: Any) -> Any:
        return tabela.c.started_at if "started_at" in tabela.c else tabela.c.requested_at

    filtros_turno = _onde(turn)
    if agent is not None:
        filtros_turno.append(turn.c.agent == agent)

    # Um agregado por (modelo, desfecho, legibilidade do uso) — as três
    # dimensões que a leitura precisa distinguir, e nenhuma a mais.
    q = sa.select(
        turn.c.model,
        turn.c.outcome,
        turn.c.tokens_partial,
        sa.func.count().label("turns"),
        sa.func.coalesce(sa.func.sum(turn.c.input_tokens), 0).label("input_tokens"),
        sa.func.coalesce(sa.func.sum(turn.c.output_tokens), 0).label("output_tokens"),
    ).group_by(turn.c.model, turn.c.outcome, turn.c.tokens_partial)
    if filtros_turno:
        q = q.where(sa.and_(*filtros_turno))

    total = 0
    desfechos: dict[str, int] = {}
    uso: dict[str, TokenUse] = {}
    for linha in (await connection.execute(q)).mappings():
        n = _int(linha["turns"])
        total += n
        desfecho = _desfecho(linha)
        if desfecho:
            desfechos[desfecho] = desfechos.get(desfecho, 0) + n
        parcial = linha["tokens_partial"]
        modelo = str(linha["model"] or "")
        uso[modelo] = _somar(
            uso.get(modelo, TokenUse()),
            TokenUse(
                input_tokens=_int(linha["input_tokens"]),
                output_tokens=_int(linha["output_tokens"]),
                turns=n,
                unreadable_turns=n if parcial is True else 0,
                unknown_turns=n if parcial is None else 0,
            ),
        )

    qa = sa.select(approval.c.decision, sa.func.count().label("n")).group_by(
        approval.c.decision
    )
    filtros_aprov = _onde(approval)
    if filtros_aprov:
        qa = qa.where(sa.and_(*filtros_aprov))

    decisoes: dict[str, int] = {}
    pendentes = 0
    for linha in (await connection.execute(qa)).mappings():
        n = _int(linha["n"])
        decisao = str(linha["decision"] or "").strip().lower()
        if decisao in DECISIONS:
            decisoes[decisao] = decisoes.get(decisao, 0) + n
        else:
            pendentes += n

    return Sample(
        turns=total,
        outcomes=desfechos,
        usage=uso,
        decisions=decisoes,
        undecided=pendentes,
    )


# ── o valor declarado ────────────────────────────────────────────────────────


def value_per_outcome(copilot_spec: Mapping[str, Any] | None) -> Any:
    """O ``value_per_outcome`` do `Copilot`, ou o motivo de não haver.

    ⚠️ **Os TRÊS campos são exigidos, e a moeda é um deles.** Uma declaração
    pela metade não é um valor pela metade — é um valor desconhecido. Faltando
    ``currency``, presumir USD estaria errado por um fator de cinco na primeira
    frota que mistura duas; faltando ``hourly_cost``, presumir qualquer coisa é
    exatamente a estimativa inventada que a regra 1 proíbe.

    ``human_minutes: 0`` é uma DECLARAÇÃO (alguém disse que não vale nada) e
    passa. Ausente não é zero; zero declarado é zero.
    """
    spec = copilot_spec or {}
    bruto = spec.get("value_per_outcome")
    if not isinstance(bruto, Mapping) or not bruto:
        return NotCalculable(
            NO_VALUE_PER_OUTCOME,
            "este Copilot nunca declarou quanto vale um desfecho — há contagem "
            "de turnos, não ROI",
            missing=("value_per_outcome",),
        )
    faltando: list[str] = []
    valores: dict[str, Any] = {}
    for campo in ("human_minutes", "hourly_cost", "currency"):
        valor = bruto.get(campo)
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            faltando.append(campo)
        else:
            valores[campo] = valor
    if faltando:
        return NotCalculable(
            NO_VALUE_PER_OUTCOME,
            "o valor de referência está declarado pela metade, e meia "
            "declaração não é meio valor — é valor desconhecido",
            missing=tuple(faltando),
        )
    try:
        minutos = float(valores["human_minutes"])
        hora = float(valores["hourly_cost"])
    except (TypeError, ValueError):
        return NotCalculable(
            NO_VALUE_PER_OUTCOME,
            "o valor de referência não é numérico",
            missing=("human_minutes", "hourly_cost"),
        )
    if minutos < 0 or hora < 0:
        return NotCalculable(
            NO_VALUE_PER_OUTCOME,
            "o valor de referência é negativo — não há leitura honesta disso",
            missing=("human_minutes", "hourly_cost"),
        )
    return ValuePerOutcome(minutos, hora, str(valores["currency"]).strip())


# ── a leitura ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class YieldReading:
    """Custo, rendimento, e a razão — cada um com procedência ou com motivo."""

    sample: Sample
    #: A contagem de tokens. Esta é EXATA (com a ressalva do piso) e não depende
    #: de preço nenhum.
    tokens: Any
    #: O dinheiro dos tokens. Depende de :class:`ModelPrice` DECLARADO.
    cost: Any
    #: ⚠️ O custo da réplica fixa do App, em US$/mês. `basis=CONSTANT` e
    #: **fora** da razão — é mensal, o resto é por turno.
    standing_cost: Any
    #: O rendimento: desfechos resolvidos × o valor declarado.
    value: Any
    #: rendimento ÷ custo dos tokens.
    ratio: Any
    #: ⚠️ PROXY — contenção/deflection.
    containment: Any
    #: ⚠️ PROXY — taxa de aceitação do HITL.
    acceptance: Any
    #: O que quem lê precisa saber junto dos números.
    notes: tuple[str, ...] = ()

    @property
    def nothing_to_look_at(self) -> bool:
        """⭐ **NÃO HÁ O QUE OLHAR** — e isto é um ACHADO, não um "tudo certo".

        Zero turnos não responde "o copiloto não rendeu nada"; responde
        "ninguém mediu". A distinção é a mesma de
        ``DeclarationGaps.nothing_to_look_at`` (PR #354), e existe porque o
        verde por vacuidade já cegou três guardas nesta casa.
        """
        return self.sample.turns == 0

    @property
    def no_outcome_declared(self) -> bool:
        """⭐ Houve turnos e NENHUM declarou desfecho — o estado de hoje.

        MEDIDO em 08/08/2026: 85 turnos, zero desfechos. Contenção aqui não é
        0%: é indefinida, e a leitura diz isso por nome.
        """
        return self.sample.turns > 0 and self.sample.declared_outcomes == 0

    @property
    def technique(self) -> str:
        return TECHNIQUE_ANSWERED


def _num(valor: float) -> str:
    inteiro = abs(valor - round(valor)) < 1e-9
    return f"{int(round(valor))}" if inteiro else f"{valor:,.4f}".rstrip("0")


def _sem_turnos() -> NotCalculable:
    return NotCalculable(
        NO_TURNS,
        "NÃO HÁ O QUE OLHAR — nenhum turno na amostra. Isto é um achado, não "
        "um resultado zero",
    )


def _tokens(sample: Sample) -> Any:
    if sample.turns == 0:
        return _sem_turnos()
    piso = sample.usage_is_floor
    origem = (
        f"soma de input+output em {sample.turns} turno(s) de dna_turn"
    )
    if piso:
        origem += (
            f"; {sample.unreadable_turns} com uso ILEGÍVEL e "
            f"{sample.unknown_usage_turns} sem a coluna tokens_partial — "
            "o provedor cobrou o que não foi reportado"
        )
    return Number(
        float(sample.input_tokens + sample.output_tokens),
        "tokens",
        MEASURED,
        origem,
        is_floor=piso,
    )


def _cost(sample: Sample, prices: Mapping[str, ModelPrice] | None) -> Any:
    if sample.turns == 0:
        return _sem_turnos()
    precisam = sorted(m for m, u in sample.usage.items() if u.needs_price)
    if not prices:
        return NotCalculable(
            NO_MODEL_PRICE,
            "nenhum preço de modelo foi declarado — tokens são exatos, "
            "dinheiro exige um preço, e este SDK não guarda tabela de preço "
            "(ela envelhece em silêncio)",
            missing=tuple(m or "<sem modelo>" for m in precisam),
        )
    faltando = tuple(m or "<sem modelo>" for m in precisam if m not in prices)
    if faltando:
        return NotCalculable(
            NO_MODEL_PRICE,
            "há tokens gastos em modelo(s) sem preço declarado — o custo "
            "parcial seria menor que o real, que é o erro que mais engana",
            missing=faltando,
        )
    moedas = {prices[m].currency for m in precisam}
    if len(moedas) > 1:
        return NotCalculable(
            CURRENCY_MISMATCH,
            "os preços declarados estão em moedas diferentes — somá-los "
            "produziria um número que não é dinheiro nenhum",
            missing=tuple(sorted(moedas)),
        )
    moeda = next(iter(moedas)) if moedas else _moeda_unica(prices)
    total = sum(
        prices[m].cost_of(u.input_tokens, u.output_tokens)
        for m, u in sample.usage.items()
        if u.needs_price
    )
    piso = sample.usage_is_floor
    origem = f"tokens medidos × preço DECLARADO de {len(precisam) or 1} modelo(s)"
    if piso:
        origem += " — PISO: há turnos cujo uso não foi reportado"
    return Number(float(total), moeda, MEASURED, origem, is_floor=piso)


def _moeda_unica(prices: Mapping[str, ModelPrice]) -> str:
    moedas = {p.currency for p in prices.values()}
    return next(iter(moedas)) if len(moedas) == 1 else "?"


def _value(sample: Sample, vpo: Any) -> Any:
    if sample.turns == 0:
        return _sem_turnos()
    if isinstance(vpo, NotCalculable):
        return vpo
    if sample.declared_outcomes == 0:
        return NotCalculable(
            NO_OUTCOME_DECLARED,
            "nenhum turno declarou desfecho — o rendimento é DESCONHECIDO, e "
            "zero aqui afirmaria que o copiloto não resolveu nada, que é outra "
            "coisa",
            missing=("dna_turn.outcome",),
        )
    piso = sample.undeclared_outcomes > 0
    origem = (
        f"{sample.resolved} desfecho(s) resolvido(s) × "
        f"{_num(vpo.human_minutes)} min ÷ 60 × {_num(vpo.hourly_cost)} "
        f"{vpo.currency} — o valor por desfecho é DECLARADO no Copilot"
    )
    if piso:
        origem += (
            f"; PISO: {sample.undeclared_outcomes} turno(s) não declararam "
            "desfecho e podem ter resolvido"
        )
    return Number(
        sample.resolved * vpo.per_outcome,
        vpo.currency,
        DECLARED,
        origem,
        is_floor=piso,
    )


def _ratio(value: Any, cost: Any) -> tuple[Any, tuple[str, ...]]:
    for lado, nome in ((value, "rendimento"), (cost, "custo")):
        if isinstance(lado, NotCalculable):
            return (
                NotCalculable(
                    UPSTREAM_NOT_CALCULABLE,
                    f"a razão precisa dos dois lados, e o {nome} não é "
                    f"calculável: {lado.detail}",
                    missing=lado.missing,
                ),
                (),
            )
    if value.unit != cost.unit:
        return (
            NotCalculable(
                CURRENCY_MISMATCH,
                f"o rendimento está em {value.unit} e o custo em {cost.unit} — "
                "a razão entre moedas diferentes não é um número",
                missing=(value.unit, cost.unit),
            ),
            (),
        )
    if cost.value == 0:
        return (
            NotCalculable(
                COST_IS_ZERO,
                "o custo medido é zero — a razão não existe, e um número "
                "grande aqui seria uma divisão disfarçada de resultado",
            ),
            (),
        )
    notas: tuple[str, ...] = ()
    origem = f"rendimento ÷ custo dos tokens, ambos em {value.unit}"
    if value.is_floor and cost.is_floor:
        # ⚠️ Os dois lados subestimados: a razão não é limite de lado nenhum.
        notas = (
            "⚠️ rendimento E custo são PISOS — a razão entre dois pisos não "
            "limita nada, nem por cima nem por baixo. Ela é uma referência, "
            "não um resultado.",
        )
        origem += " — os DOIS lados são pisos"
    elif value.is_floor:
        origem += " — o rendimento é piso, então a razão também é"
    elif cost.is_floor:
        origem += " — o custo é piso, então a razão é um TETO"
    return (
        Number(
            value.value / cost.value,
            "×",
            MEASURED if not value.is_floor else DECLARED,
            origem,
            is_floor=value.is_floor and not cost.is_floor,
        ),
        notas,
    )


def _containment(sample: Sample) -> Any:
    """⚠️ Contenção/deflection — PROXY, e o rótulo não é opcional."""
    if sample.turns == 0:
        return _sem_turnos()
    if sample.declared_outcomes == 0:
        return NotCalculable(
            NO_OUTCOME_DECLARED,
            "nenhum turno declarou desfecho — a contenção é INDEFINIDA. "
            "Devolver 0% afirmaria que nada foi resolvido; o que houve foi "
            "ninguém declarar",
            missing=("dna_turn.outcome",),
        )
    cobertura = sample.declared_outcomes / sample.turns
    escalados = sample.outcomes.get("escalated", 0)
    abandonados = sample.outcomes.get("abandoned", 0)
    origem = (
        f"contenção/deflection: {sample.resolved} resolvido(s) de "
        f"{sample.declared_outcomes} turno(s) COM desfecho declarado "
        f"({escalados} escalado(s), {abandonados} abandonado(s)); "
        f"cobertura {cobertura:.0%} dos {sample.turns} turnos. "
        "⚠️ PROXY — mede trabalho terminado sem escalar, NÃO valor entregue"
    )
    return Number(
        100.0 * sample.resolved / sample.declared_outcomes,
        "%",
        PROXY,
        origem,
        is_floor=False,
    )


def _acceptance(sample: Sample) -> Any:
    """⚠️ Taxa de aceitação do HITL — PROXY, com as contagens que a originam."""
    if sample.decided == 0:
        return NotCalculable(
            NO_APPROVALS,
            "nenhuma decisão de HITL registrada — a taxa de aceitação é "
            "INDEFINIDA. 0% diria que o humano rejeitou tudo"
            + (
                f" (há {sample.undecided} aprovação(ões) pedida(s) e não "
                "decidida(s), e pendência não é concordância)"
                if sample.undecided
                else ""
            ),
            missing=("dna_approval.decision",),
        )
    contagens = ", ".join(
        f"{d} {sample.decisions.get(d, 0)}" for d in DECISIONS
    )
    origem = (
        f"taxa de aceitação: {contagens} — aprovado sem o humano tocar, sobre "
        f"{sample.decided} decisão(ões). ⚠️ PROXY — `edit` é o mais valioso "
        "dos três (a diferença entre `arguments` e `edited_args` é o quanto o "
        "agente errou) e esta taxa não o lê"
    )
    return Number(
        100.0 * sample.decisions.get("approve", 0) / sample.decided,
        "%",
        PROXY,
        origem,
    )


def _standing_cost(app_spec: Mapping[str, Any] | None) -> Any:
    """O custo da réplica fixa — CONSTANTE, e rotulada como tal."""
    if app_spec is None:
        return NotCalculable(
            NO_APP,
            "este Copilot não diz em que App roda (`runs_in`), então o custo "
            "do processo que o serve não entra na conta",
            missing=("Copilot.runs_in",),
        )
    dorme = app_spec.get("can_sleep")
    if dorme is None:
        return NotCalculable(
            CAN_SLEEP_UNDECLARED,
            "o App nunca respondeu se pode dormir — e presumir o lado barato "
            "esconde exatamente a réplica que ninguém decidiu",
            missing=("App.can_sleep",),
        )
    if dorme:
        return Number(
            0.0,
            "USD/mês",
            DECLARED,
            "App.can_sleep: true — escala a zero, sem réplica fixa. Não inclui "
            "o consumo por requisição",
        )
    return Number(
        STANDING_REPLICA_USD_MONTH,
        "USD/mês",
        CONSTANT,
        "App.can_sleep: false — réplica fixa. ⚠️ CONSTANTE medida em "
        "31/07/2026 no dna-cloud (US$ 94,43 de US$ 230,29), NÃO lida de "
        "fatura e não se atualiza sozinha",
    )


def read_yield(
    sample: Sample,
    *,
    copilot: Mapping[str, Any] | None = None,
    app: Mapping[str, Any] | None = None,
    prices: Mapping[str, ModelPrice] | None = None,
) -> YieldReading:
    """A leitura inteira: custo, rendimento, razão, e os dois proxies.

    ``copilot`` e ``app`` são os ``spec`` dos descritores (`Copilot` e o `App`
    de ``runs_in``). ``prices`` é a tabela DECLARADA de preço por modelo.
    Qualquer um deles ausente não vira zero — vira :class:`NotCalculable` com
    o motivo, e é isso que esta função existe para garantir.
    """
    vpo = value_per_outcome(copilot)
    tokens = _tokens(sample)
    cost = _cost(sample, prices)
    value = _value(sample, vpo)
    ratio, notas_razao = _ratio(value, cost)
    containment = _containment(sample)
    acceptance = _acceptance(sample)
    standing = _standing_cost(app)

    notas: list[str] = []
    if sample.turns == 0:
        notas.append(
            "⭐ NÃO HÁ O QUE OLHAR: nenhum turno na amostra. Um relatório "
            "verde aqui seria verde por vacuidade."
        )
    elif sample.declared_outcomes == 0:
        notas.append(
            f"⭐ NENHUM dos {sample.turns} turnos declarou desfecho. A coluna "
            "`outcome` existe (revisão 0012) e nada a preenche — quem fecha o "
            "turno precisa chamar `stamp_outcome`. Enquanto isso, contenção e "
            "rendimento são INDEFINIDOS, jamais zero."
        )
    elif sample.undeclared_outcomes:
        notas.append(
            f"{sample.undeclared_outcomes} de {sample.turns} turnos não "
            "declararam desfecho; eles estão FORA da contenção e o rendimento "
            "é um piso."
        )
    if sample.unreadable_turns:
        notas.append(
            f"⚠️ {sample.unreadable_turns} turno(s) chamaram o modelo e a "
            "chamada não reportou uso (`tokens_partial = true`). O provedor "
            "cobrou o prompt; a conta de tokens é um PISO, nunca zero."
        )
    if sample.unknown_usage_turns:
        notas.append(
            f"{sample.unknown_usage_turns} turno(s) são anteriores à revisão "
            "0012 (`tokens_partial IS NULL`): não dá para afirmar que a conta "
            "deles está fechada."
        )
    if isinstance(standing, Number) and standing.value:
        notas.append(
            "⚠️ O custo da réplica fixa é MENSAL e está FORA da razão, que é "
            "por turno. Somar os dois misturaria unidades."
        )
    notas.extend(notas_razao)
    notas.append(
        f"Técnica respondida: {TECHNIQUE_ANSWERED}. Não respondidas: "
        + "; ".join(TECHNIQUES_NOT_ANSWERED)
        + "."
    )

    return YieldReading(
        sample=sample,
        tokens=tokens,
        cost=cost,
        standing_cost=standing,
        value=value,
        ratio=ratio,
        containment=containment,
        acceptance=acceptance,
        notes=tuple(notas),
    )


# ── a saída para humano ──────────────────────────────────────────────────────

#: A ordem em que a leitura se lê. Nomeada aqui para que a tela e o texto não
#: inventem cada uma a sua.
ROWS = (
    ("tokens", "Tokens"),
    ("cost", "Custo (tokens)"),
    ("standing_cost", "Custo fixo do App"),
    ("value", "Rendimento"),
    ("ratio", "Rendimento ÷ custo"),
    ("containment", "Contenção"),
    ("acceptance", "Aceitação (HITL)"),
)


def render(reading: YieldReading) -> list[str]:
    """As linhas que um humano lê — **com a procedência colada em cada número**.

    ⚠️ O rótulo (`[PROXY]`, `[CONSTANT]`, `≥ PISO`) sai aqui porque é aqui que
    alguém vê o número. Um `basis` guardado no objeto e omitido na tela é a
    regra 2 cumprida onde ninguém olha.
    """
    linhas: list[str] = []
    if reading.nothing_to_look_at:
        linhas.append("⭐ NÃO HÁ O QUE OLHAR — nenhum turno na amostra.")
    else:
        linhas.append(
            f"{reading.sample.turns} turno(s) · "
            f"{reading.sample.declared_outcomes} com desfecho declarado · "
            f"{reading.sample.decided} decisão(ões) de HITL"
        )
    for campo, rotulo in ROWS:
        resposta = getattr(reading, campo)
        if isinstance(resposta, NotCalculable):
            linhas.append(f"{rotulo}: NÃO CALCULÁVEL — {resposta.detail}")
            if resposta.missing:
                linhas.append(f"    falta: {', '.join(resposta.missing)}")
        else:
            linhas.append(f"{rotulo}: {resposta}")
            linhas.append(f"    origem: {resposta.source}")
    for nota in reading.notes:
        linhas.append(f"• {nota}")
    return linhas
