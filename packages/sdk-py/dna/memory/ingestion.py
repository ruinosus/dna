"""A memória se alimenta da conversa — e se corrige.

## As DUAS etapas, e a segunda é a que torna a primeira segura

::

    1. EXTRAIR      o transcript → fatos discretos
    2. RECONCILIAR  cada fato × as memórias existentes → ADD | UPDATE | INVALIDATE | NONE

Extrair sozinho empilha duplicata e contradição. É a reconciliação que faz a
memória se **corrigir**: um fato posterior atualiza ou invalida um anterior, e o
custo de errar cai de *"para sempre"* para *"até o próximo turno que contradiga"*.

⚠️ **Isso reverte uma decisão anterior deste produto, e a reversão é o ponto.**
Em 02/08 recusamos escrita automática com o argumento de que *"a primeira
memória errada envenena todos os recalls seguintes"*. O argumento assumia
memória **append-only**. Com a etapa 2 ele deixa de valer — e sem a etapa 2 ele
volta a valer inteiro.

## ⚠️ INVALIDATE nunca é DELETE

É ``valid_to`` + ``superseded_by_memory`` — o esquecimento **reversível** que o
`Engram` já provê. Apagar de verdade tiraria a capacidade de responder *"por que
o agente achava X em março?"*, que é metade do valor de uma memória auditável.

## A maioria dos turnos não produz memória nenhuma

O few-shot de referência começa com ``"Hi." → []``, e isso é calibragem, não
economia: um extrator que não sabe disso enche o banco de ruído — e o ruído
depois **sobe sozinho no prompt** pelo recall automático. Piorar o produto para
melhorar a memória seria uma troca ruim.

Daí `worth_extracting`, que é conservador de propósito e mede **antes** de
gastar uma chamada.

## Puro

Nada aqui chama modelo nem banco. O que mora aqui é: **quando** vale extrair, o
**prompt** das duas etapas, e como **ler** o que o modelo respondeu. Quem tem o
cliente executa — a mesma fronteira de `capabilities`, `agent_grant` e
`attachments`.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

_LOGGER = logging.getLogger("dna.memory.ingestion")

__all__ = [
    "ADD",
    "INVALIDATE",
    "NONE",
    "UPDATE",
    "Decision",
    "IngestionPolicy",
    "extraction_prompt",
    "parse_facts",
    "parse_decisions",
    "reconciliation_prompt",
    "EXTRACTION_TEMPLATE",
    "RECONCILIATION_TEMPLATE",
    "resolve_ingestion",
    "sdlc_digest",
    "worth_extracting",
]

ADD = "add"
UPDATE = "update"
INVALIDATE = "invalidate"
NONE = "none"

#: As quatro operações. Fechado porque cada uma é um caminho de escrita REAL —
#: uma quinta que ninguém implementou viraria um fato descartado em silêncio.
OPERATIONS = frozenset({ADD, UPDATE, INVALIDATE, NONE})

#: Teto de fatos por turno. Uma conversa não produz dez fatos duráveis; um
#: modelo que devolve dez está inventando, e o teto transforma isso em ruído
#: limitado em vez de enchente.
MAX_FACTS = 5

#: Quanto do transcript entra na extração. Mais que isto não melhora o fato e
#: piora a conta.
MAX_TRANSCRIPT = 4000

#: Palavras que sozinhas não afirmam nada.
_VAZIAS = {
    "ok", "okay", "sim", "nao", "não", "certo", "beleza", "obrigado", "obrigada",
    "valeu", "pode", "seguir", "isso", "legal", "otimo", "ótimo", "perfeito",
    "yes", "no", "thanks", "thank", "you", "sure", "great", "hi", "hello", "oi",
}


@dataclass(frozen=True)
class IngestionPolicy:
    """A resposta do workspace para *quando* e *de onde* alimentar a memória.

    Os defaults são as decisões do fundador em 03/08: ligado, só do chat, por
    turno, sem aprovação. Um workspace que discorde **declara** — e a declaração
    é dado (`CognitivePolicy.ingestion`), não constante de código.
    """

    enabled: bool = True
    #: ALLOWLIST. Uma fonte ausente nunca é lida — é o campo que decide o que o
    #: agente pode aprender sobre as pessoas dele.
    sources: tuple[str, ...] = ("chat",)
    trigger: str = "per_turn"
    min_signal_chars: int = 25
    require_approval: bool = False
    #: Quantas memórias existentes entram na reconciliação (o k do recall).
    #: Era constante do host — e "está fixo em 8" é exatamente o tipo de
    #: escolha que pertence à política do workspace, não ao código.
    neighbors: int = 8
    #: Assuntos que NUNCA viram memória, mesmo se o modelo os extrair.
    never: tuple[str, ...] = ()
    always: tuple[str, ...] = ()


def resolve_ingestion(policy: Mapping[str, Any] | None) -> IngestionPolicy:
    """Lê `CognitivePolicy.spec` e devolve a política efetiva.

    Ausente ou malformada → os defaults. Uma política que não carrega **não pode
    ligar nada**: o modo de falha seguro de uma configuração de ingestão é o
    comportamento declarado no código, não "faça o que quiser".
    """
    if not isinstance(policy, Mapping):
        return IngestionPolicy()

    bruto = policy.get("ingestion")
    if not isinstance(bruto, Mapping):
        bruto = {}

    memoria = policy.get("memory") if isinstance(policy.get("memory"), Mapping) else {}
    lembrar: dict[str, Any] = {}
    for entrada in (memoria or {}).get("policies") or []:
        if isinstance(entrada, Mapping) and isinstance(entrada.get("remember"), Mapping):
            lembrar = dict(entrada["remember"])

    padrao = IngestionPolicy()
    fontes = bruto.get("sources")
    return IngestionPolicy(
        enabled=bool(bruto.get("enabled", padrao.enabled)),
        sources=tuple(f for f in fontes if isinstance(f, str))
        if isinstance(fontes, list)
        else padrao.sources,
        trigger=str(bruto.get("trigger") or padrao.trigger),
        min_signal_chars=int(bruto.get("min_signal_chars", padrao.min_signal_chars)),
        require_approval=bool(bruto.get("require_approval", padrao.require_approval)),
        neighbors=max(1, int(bruto.get("neighbors", padrao.neighbors))),
        never=tuple(t for t in (lembrar.get("never") or []) if isinstance(t, str)),
        always=tuple(t for t in (lembrar.get("always") or []) if isinstance(t, str)),
    )


def worth_extracting(text: str | None, policy: IngestionPolicy | None = None) -> bool:
    """Vale gastar uma chamada de modelo com este turno?

    ⚠️ Mede ANTES de gastar. É a única defesa barata contra o custo por turno —
    e o custo por turno é o que transforma uma boa feature numa linha de fatura
    que ninguém vê subir.
    """
    p = policy or IngestionPolicy()
    if not p.enabled or p.trigger in ("off", "batch"):
        return False
    if "chat" not in p.sources:
        return False

    limpo = (text or "").strip()
    if len(limpo) < p.min_signal_chars:
        return False
    palavras = [w.strip(".,!?;:").lower() for w in limpo.split()]
    return any(w and w not in _VAZIAS for w in palavras)


#: Os NOMES BEM CONHECIDOS dos templates que um workspace pode sobrescrever —
#: documentos `PromptTemplate` (o Kind que já existia; ver a spec
#: prompts-como-dados). Ausentes, valem os defaults abaixo, testados.
EXTRACTION_TEMPLATE = "memory-extraction"
RECONCILIATION_TEMPLATE = "memory-reconciliation"


def _template_valido(template: Any, obrigatorias: Sequence[str], nome: str) -> str | None:
    """O texto do workspace, SE ele carrega toda variável obrigatória.

    Um template sem `{transcript}` extrairia de nada — para sempre e em
    silêncio. A recusa nomeia a variável faltante no log e cai no default:
    o modo de falha de um template quebrado é o comportamento testado, nunca
    o vazio.
    """
    if not isinstance(template, str) or not template.strip():
        return None
    faltam = [v for v in obrigatorias if ("{" + v + "}") not in template]
    if faltam:
        _LOGGER.warning(
            "PromptTemplate %r ignorado: faltam as variáveis %s", nome, faltam
        )
        return None
    return template


def _preencher(template: str, valores: Mapping[str, str]) -> str:
    """Substituição literal de `{var}` — NUNCA `str.format`.

    Um template de prompt carrega exemplos JSON cheios de chaves; `format`
    quebraria em qualquer um deles, e a quebra apareceria como "template do
    workspace nunca é usado", longe da causa.
    """
    for chave, valor in valores.items():
        template = template.replace("{" + chave + "}", valor)
    return template


def extraction_prompt(
    transcript: str,
    policy: IngestionPolicy | None = None,
    *,
    template: str | None = None,
) -> str:
    """A etapa 1 — o transcript vira fatos discretos.

    O few-shot ensina o caso mais comum, que é **não extrair nada**. Sem ele o
    modelo produz um fato por turno porque foi o que se pediu, e a memória vira
    um diário.

    `template` (o `PromptTemplate` de nome ``memory-extraction``, se o
    workspace declarou um) VENCE o default — desde que carregue `{transcript}`.
    """
    p = policy or IngestionPolicy()
    escolhido = _template_valido(template, ("transcript",), EXTRACTION_TEMPLATE)
    if escolhido is not None:
        return _preencher(escolhido, {"transcript": transcript[:MAX_TRANSCRIPT]})
    nunca = (
        f"\nNUNCA extraia nada sobre: {', '.join(p.never)}.\n" if p.never else ""
    )
    sempre = (
        f"\nPreste atenção especial a: {', '.join(p.always)}.\n" if p.always else ""
    )
    return f"""Extraia FATOS DURÁVEIS sobre o usuário e o trabalho dele desta conversa.

Um fato durável vale além desta conversa: uma decisão, uma preferência, uma
restrição, um prazo, um dado do negócio. NÃO é fato durável: uma pergunta, uma
saudação, um pedido pontual, ou algo que só vale neste turno.

A resposta mais comum é uma lista VAZIA. Extraia no máximo {MAX_FACTS}.{nunca}{sempre}
Exemplos:
  "Oi, tudo bem?"                            -> {{"facts": []}}
  "me explica como funciona o portal"        -> {{"facts": []}}
  "decidimos que o prazo passa a ser 60 dias" -> {{"facts": ["O prazo de renovação é 60 dias"]}}
  "prefiro resumos em tópicos curtos"        -> {{"facts": ["Prefere resumos em tópicos curtos"]}}
  "o contrato da ACME vence em março de 2027" -> {{"facts": ["O contrato da ACME vence em março de 2027"]}}

Responda SOMENTE com JSON no formato {{"facts": ["...", "..."]}}.

Conversa:
{transcript[:MAX_TRANSCRIPT]}"""


def reconciliation_prompt(
    facts: Sequence[str],
    existing: Sequence[Mapping[str, Any]],
    *,
    template: str | None = None,
) -> str:
    """A etapa 2 — cada fato contra o que já existe.

    ⚠️ É esta etapa que torna a escrita automática defensável. Sem ela, cada
    conversa acrescenta e nada corrige: contradições convivem, duplicatas se
    somam, e o recall automático passa a servir as duas versões do mesmo assunto.

    `template` (``memory-reconciliation``) VENCE o default se carregar
    `{facts}` E `{memories}` — sem as duas, a decisão sairia sem um dos lados.
    """
    memorias = json.dumps(
        [
            {"id": str(m.get("id") or m.get("name") or i), "text": _texto(m)}
            for i, m in enumerate(existing)
        ],
        ensure_ascii=False,
    )
    fatos_json = json.dumps(list(facts), ensure_ascii=False)
    escolhido = _template_valido(
        template, ("facts", "memories"), RECONCILIATION_TEMPLATE
    )
    if escolhido is not None:
        return _preencher(escolhido, {"facts": fatos_json, "memories": memorias})
    return f"""Você gerencia a memória de um sistema. Compare os FATOS NOVOS com a MEMÓRIA ATUAL e decida, para cada fato, uma operação:

- "{ADD}": informação nova, não presente na memória.
- "{UPDATE}": a memória já trata do assunto, mas o fato novo a torna mais precisa
  ou a corrige. Informe o `id` da memória e o texto FINAL completo.
- "{INVALIDATE}": o fato novo CONTRADIZ uma memória existente e ela deixou de
  valer. Informe o `id`. (A memória não é apagada — é marcada como não mais
  válida, e continua auditável.)
- "{NONE}": o fato já está na memória, ou não vale guardar.

Prefira "{UPDATE}" a "{ADD}" quando o assunto for o mesmo: duas memórias sobre a
mesma coisa fazem o agente servir as duas versões e parecer confuso.

MEMÓRIA ATUAL:
{memorias}

FATOS NOVOS:
{fatos_json}

Responda SOMENTE com JSON:
{{"decisions": [{{"op": "{ADD}", "text": "..."}},
                {{"op": "{UPDATE}", "id": "...", "text": "..."}},
                {{"op": "{INVALIDATE}", "id": "...", "reason": "..."}},
                {{"op": "{NONE}"}}]}}"""


@dataclass(frozen=True)
class Decision:
    """Uma operação a aplicar. `memory_id` é vazio para `add`."""

    op: str
    text: str = ""
    memory_id: str = ""
    reason: str = ""
    #: Preenchido pelo host quando ele classifica; o SDK não infere aqui.
    memory_type: str = ""


def _texto(m: Any) -> str:
    if isinstance(m, str):
        return m
    if isinstance(m, Mapping):
        for k in ("summary", "text", "content", "body"):
            v = m.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        spec = m.get("spec")
        if isinstance(spec, Mapping):
            return _texto(spec)
    return ""


def _json_de(bruto: Any) -> Any:
    """O JSON que o modelo devolveu, tolerante a cerca de markdown.

    Modelos embrulham JSON em ```json …``` com frequência suficiente para que
    tratar isso como erro signifique perder fatos por formatação.
    """
    if isinstance(bruto, (dict, list)):
        return bruto
    texto = str(bruto or "").strip()
    cerca = re.search(r"```(?:json)?\s*(.+?)\s*```", texto, re.S)
    if cerca:
        texto = cerca.group(1)
    try:
        return json.loads(texto)
    except (ValueError, TypeError):
        # Última tentativa: o primeiro objeto balanceado do texto.
        inicio = texto.find("{")
        if inicio >= 0:
            try:
                return json.loads(texto[inicio : texto.rfind("}") + 1])
            except (ValueError, TypeError):
                pass
        return None


def parse_facts(raw: Any, policy: IngestionPolicy | None = None) -> list[str]:
    """Os fatos da etapa 1. Formato inesperado devolve `[]`, nunca lixo.

    Lixo aqui vira memória, e memória vira prompt: um parse permissivo não custa
    um erro, custa o agente afirmando bobagem com confiança.
    """
    p = policy or IngestionPolicy()
    dados = _json_de(raw)
    fatos = dados.get("facts") if isinstance(dados, Mapping) else dados
    if not isinstance(fatos, list):
        return []

    limpos: list[str] = []
    for f in fatos:
        if not isinstance(f, str):
            continue
        t = f.strip()
        if not t:
            continue
        # A allowlist de assunto é aplicada AQUI também, e não só no prompt:
        # instrução é pedido, filtro é garantia.
        if any(n.lower() in t.lower() for n in p.never):
            _LOGGER.info("fato descartado por política `never`")
            continue
        limpos.append(t)
        if len(limpos) >= MAX_FACTS:
            break
    return limpos


def parse_decisions(raw: Any) -> list[Decision]:
    """As operações da etapa 2.

    ⚠️ Operação desconhecida vira `none`, nunca `add`. O default FECHA: um
    modelo que invente `"merge"` não pode virar uma escrita que ninguém revisou.
    """
    dados = _json_de(raw)
    itens = dados.get("decisions") if isinstance(dados, Mapping) else dados
    if not isinstance(itens, list):
        return []

    saida: list[Decision] = []
    for d in itens:
        if not isinstance(d, Mapping):
            continue
        op = str(d.get("op") or "").strip().lower()
        if op not in OPERATIONS:
            _LOGGER.info("operação desconhecida %r tratada como `none`", op)
            op = NONE
        texto = str(d.get("text") or "").strip()
        mid = str(d.get("id") or d.get("memory_id") or "").strip()
        # Uma operação sem o que ela precisa é inerte, não um erro: melhor
        # perder um fato que executar um `update` sem alvo.
        if op == ADD and not texto:
            continue
        if op in (UPDATE, INVALIDATE) and not mid:
            continue
        if op == UPDATE and not texto:
            continue
        saida.append(
            Decision(op=op, text=texto, memory_id=mid, reason=str(d.get("reason") or ""))
        )
    return saida


# ── a fonte `sdlc`: o board vira material de extração ───────────────────────

#: Quantas historias entram num digest. O board de um mes nao produz cem fatos
#: duraveis; um digest gigante so encarece a chamada.
SDLC_MAX_ITEMS = 12


def sdlc_digest(
    completed: Sequence[Mapping[str, Any]],
    decided: Sequence[Mapping[str, Any]] = (),
    *,
    max_items: int = SDLC_MAX_ITEMS,
) -> str:
    """O texto que a extração lê quando a fonte é o BOARD.

    Recebe os buckets ``completed``/``decided`` do digest retrospectivo (a tool
    `sdlc_digest` já os calcula — itens ``{"kind", "name", "title"}``) e produz
    o mesmo formato de "transcript" que a extração de chat consome — o pipeline
    das duas etapas é UM, e a fonte é só de onde o texto veio.

    ⚠️ Por que título + resultado, e não o documento inteiro: o fato durável de
    uma história entregue é o que ELA MUDOU ("o billing agora usa Stripe
    metered"), não o registro do processo. Despejar o YAML inteiro faria o
    extrator achar fatos sobre o board, não sobre o trabalho.
    """
    def _linha(rotulo: str, doc: Mapping[str, Any]) -> str | None:
        spec = doc.get("spec") if isinstance(doc.get("spec"), Mapping) else doc
        titulo = str(spec.get("title") or spec.get("summary") or "").strip()
        if not titulo:
            return None
        resultado = str(
            spec.get("outcome") or spec.get("resolution") or ""
        ).strip()
        return f"{rotulo}: {titulo}" + (f" — {resultado[:200]}" if resultado else "")

    linhas: list[str] = []
    for doc in list(completed):
        if (l := _linha("entregue", doc)) is not None:
            linhas.append(l)
    for doc in list(decided):
        if (l := _linha("decidido", doc)) is not None:
            linhas.append(l)
    return "\n".join(linhas[:max_items])
