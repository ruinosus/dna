"""O agente lembra sem precisar DECIDIR lembrar.

## O defeito que este middleware fecha

A memória existe: `Engram`, `recall` como tool de MCP, busca vetorial de
verdade. O que falha é que o modelo precisa **decidir** chamar `recall` — e ele
esquece.

Não há erro quando isso acontece. A conversa segue, a resposta sai plausível, e a
memória que estava no banco não participou. É o modo de falha mais caro do
produto, porque nada o denuncia: não dá exceção, não some da tela, não aparece em
log. Só a resposta é pior do que poderia ser.

## ⚠️ Injetar SEMPRE seria trocar um defeito por outro

Um recall a cada turno custa tokens em **todo** turno e empurra contexto
irrelevante para dentro da janela. Duas defesas, e as duas são numéricas de
propósito — um limite que se possa medir é um limite que se possa corrigir:

* **teto duro** (`MAX_MEMORIES`, `MAX_CHARS`): o piso nunca vira enchente;
* **só quando há sinal** (`worth_recalling`): a maioria dos turnos de uma
  conversa é `"ok"`, `"obrigado"`, `"pode seguir"` — buscar memória para eles é
  gastar sem chance de acertar.

## A tool CONTINUA existindo

Este middleware é o **piso**, não o teto. Uma pergunta explícita sobre memória
deve poder buscar mais fundo do que o piso oferece, e é para isso que `recall`
segue montada.

## ⚠️ O que é injetado precisa APARECER

Memória que entra no prompt sem deixar rastro é mágica não auditável: o usuário
vê o agente "saber" algo e não tem como perguntar de onde veio. Por isso o
middleware carimba o que injetou (`dna.recall.*`) — a aba Atividade já mostra
tool I/O, e isto entra pelo mesmo caminho.

## Puro o suficiente para ser testado sem rede

`recall` é injetado pelo host, como `mcp_auth` e `compose`. A REGRA — quando
buscar, quanto cabe, como renderizar — mora aqui e se exercita com uma lista.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Iterable, Sequence

_LOGGER = logging.getLogger("dna.runtime.recall")

__all__ = [
    "MAX_CHARS",
    "MAX_MEMORIES",
    "KNOWN_TYPE_LABELS",
    "type_label",
    "MIN_SIGNAL_CHARS",
    "DnaRecallMiddleware",
    "briefing",
    "worth_recalling",
    "cues",
    "CUE_WINDOW",
    "STICKY_OVERLAP",
]

#: Quantas memórias entram. Três é um teto escolhido para ser BAIXO: o objetivo é
#: lembrar o agente de que existe memória, não substituir a busca dele.
MAX_MEMORIES = 3

#: Teto de caracteres do bloco inteiro. Um `Engram` longo sozinho não pode comer
#: a janela — o corte é anunciado, como em toda parte deste SDK.
MAX_CHARS = 2000

#: Abaixo disto a mensagem não discrimina nada. `"ok"`, `"pode seguir"`,
#: `"obrigado"` — a maioria dos turnos de uma conversa real.
MIN_SIGNAL_CHARS = 12

#: Quantas mensagens do usuário entram no cue. Três é o suficiente para dar
#: assunto a um `"e o prazo?"` sem arrastar a conversa inteira.
CUE_WINDOW = 3

#: Teto do cue. Ele vira consulta de busca — uma consulta gigante não discrimina
#: melhor, só custa mais.
CUE_MAX_CHARS = 600

#: ⚠️ HISTERESE (Schmitt). Quanto do conjunto anterior precisa sobreviver para
#: que o bloco ANTIGO seja mantido.
#:
#: O ponto NÃO é economizar busca — é manter o prompt ESTÁVEL. Um bloco que muda
#: a cada turno muda o prefixo do prompt a cada turno, e isso invalida o cache do
#: provider: custo real, medível, e invisível até chegar na fatura.
#:
#: Vem do JARVIS (`aap-sdk-v3`): "re-injeta só quando o set muda + histerese".
#: Lá a banda é sobre SCORE (θ_in/θ_out); aqui é sobre SOBREPOSIÇÃO, porque o
#: `recall` não expõe o score ao chamador. Menos fino, mesma intenção — e a
#: diferença está escrita para quem for refinar.
STICKY_OVERLAP = 0.5

#: Palavras que sozinhas não são pergunta. Uma mensagem feita só delas não vira
#: busca, mesmo passando do tamanho mínimo.
_VAZIAS = {
    "ok", "okay", "sim", "nao", "não", "certo", "beleza", "obrigado",
    "obrigada", "valeu", "pode", "seguir", "isso", "legal", "otimo", "ótimo",
    "perfeito", "yes", "no", "thanks", "thank", "you", "sure", "great",
}


def worth_recalling(text: str | None) -> bool:
    """Vale gastar uma busca com esta mensagem?

    ⚠️ O default aqui é **não**, ao contrário de quase todo portão deste SDK. A
    razão é que o custo é assimétrico: buscar à toa gasta tokens em todo turno
    trivial de toda conversa, e não buscar num turno trivial não perde nada —
    a tool `recall` continua lá para o caso raro.
    """
    limpo = (text or "").strip()
    if len(limpo) < MIN_SIGNAL_CHARS:
        return False
    palavras = [p.strip(".,!?;:").lower() for p in limpo.split()]
    return any(p and p not in _VAZIAS for p in palavras)


#: Tipos que o SDK sabe APRESENTAR de forma especial. Tudo que não estiver
#: aqui é apresentado com o próprio nome — nada é descartado.
#:
#: ⚠️ Isto NÃO é a lista de tipos válidos. Essa lista é do `Engram`, e é DADO:
#: um workspace que declare um tipo próprio (`preferencia`, `restricao`) deve
#: vê-lo aparecer no prompt no dia em que o declarar, não no dia em que alguém
#: se lembrar de acrescentá-lo a um dicionário aqui.
#:
#: Uma tabela fechada num middleware é exatamente o que o DNA existe para
#: evitar: ela transforma vocabulário do domínio em constante de código, e o
#: sintoma é um tipo novo sumir do prompt sem erro nenhum.
KNOWN_TYPE_LABELS = {
    # `procedural` é o único com tratamento IMPERATIVO, e por um motivo: uma
    # regra que o modelo leia como anedota é uma regra que ele ignora — e
    # ignorar anedota é o comportamento razoável.
    "procedural": "REGRA (siga)",
    "episodic": "fato ocorrido",
    "semantic": "fato",
}

#: O que um tipo desconhecido vira. Nunca "descartado".
UNTYPED_LABEL = "fato"


def type_label(memory_type: Any) -> str:
    """Como este tipo aparece no prompt. Aceita QUALQUER string não vazia.

    Um tipo que o SDK não conhece é mostrado com o próprio nome, porque o nome é
    a informação: `[preferencia]` diz mais ao modelo do que `[fato]`, e muito
    mais do que sumir.
    """
    t = (memory_type or "").strip() if isinstance(memory_type, str) else ""
    if not t:
        return UNTYPED_LABEL
    return KNOWN_TYPE_LABELS.get(t, t)


def _tipo_de(memoria: Any) -> Any:
    if isinstance(memoria, dict):
        return memoria.get("memory_type") or (memoria.get("spec") or {}).get("memory_type")
    return getattr(memoria, "memory_type", None)


def briefing(memories: Sequence[Any]) -> str:
    """O bloco que entra na mensagem de SISTEMA — ou vazio.

    Vai para o sistema, e não para a conversa, pelo mesmo motivo que a instrução
    da planilha foi: uma parte `text` numa mensagem CHEGA À TELA, e o usuário
    leria a memória injetada como se ele mesmo a tivesse escrito.

    ⚠️ NÃO reordena nem repontua. O `recall` do SDK (`dna.memory.verbs`) já
    aplica curva de Ebbinghaus, validade bitemporal e peso de afeto
    (`dna.memory.decay`). Repontuar aqui seria uma segunda opinião sobre a mesma
    coisa — e a que perde é sempre a que tem menos informação, que é esta.
    """
    linhas: list[str] = []
    gasto = 0
    for m in list(memories)[:MAX_MEMORIES]:
        texto = _texto_de_memoria(m)
        if not texto:
            continue
        linha = f"- [{type_label(_tipo_de(m))}] {texto}"
        if gasto + len(linha) > MAX_CHARS:
            break
        linhas.append(linha)
        gasto += len(linha)
    if not linhas:
        return ""
    return (
        "Memórias já registradas deste workspace, recuperadas para este turno:\n"
        + "\n".join(linhas)
        + "\nO que estiver marcado REGRA você DEVE seguir; o resto é contexto. "
        "Diga quando usar algo que veio da memória. "
        "Se precisar de mais, chame `recall` — isto é um resumo, não tudo."
    )


def _texto_de_memoria(memoria: Any) -> str:
    """O texto de uma memória, seja ela dict, objeto ou string.

    Tolerante de propósito: a forma vem do host (MCP, banco, dublê) e uma
    diferença de formato não pode custar o turno — no pior caso não injeta nada.
    """
    if isinstance(memoria, str):
        return memoria.strip()
    if isinstance(memoria, dict):
        for chave in ("summary", "text", "content", "body", "title", "name"):
            valor = memoria.get(chave)
            if isinstance(valor, str) and valor.strip():
                return valor.strip()
        spec = memoria.get("spec")
        if isinstance(spec, dict):
            return _texto_de_memoria(spec)
        return ""
    for chave in ("summary", "text", "content"):
        valor = getattr(memoria, chave, None)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return ""


def _texto_da_mensagem(m: Any) -> str:
    conteudo = getattr(m, "content", None)
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        return " ".join(
            p.get("text", "")
            for p in conteudo
            if isinstance(p, dict) and p.get("type") == "text" and p.get("text")
        )
    return ""


def cues(messages: Iterable[Any], *, window: int = CUE_WINDOW) -> str:
    """Os CUES vivos — a janela recente do usuário, não só a última fala.

    ⚠️ Buscar só com a última mensagem perde o assunto. Numa conversa real ela é
    curta e dependente (`"e o prazo?"`), e o que dá sentido a ela está duas ou
    três mensagens atrás. Uma busca por `"e o prazo?"` não recupera nada.

    Vem do desenho do JARVIS (`aap-sdk-v3`, peça 1): os cues são "escopo ativo +
    `recent_topics` extraídos do transcript + affect da sessão". Aqui está a
    metade barata e determinística — a janela do transcript. Escopo e affect
    dependem de estado que o host tem e o SDK não.

    A mais RECENTE vem primeiro: se o corte por tamanho tiver de acontecer, ele
    tira o contexto antigo, não a pergunta.
    """
    recentes: list[str] = []
    for m in reversed(list(messages or [])):
        tipo = getattr(m, "type", None) or getattr(m, "role", None)
        if tipo not in ("human", "user"):
            continue
        texto = _texto_da_mensagem(m).strip()
        if texto:
            recentes.append(texto)
        if len(recentes) >= window:
            break
    return " ".join(recentes)[:CUE_MAX_CHARS]


def _chave_de(memoria: Any) -> str:
    """A identidade de uma memória para efeito de histerese.

    Nome do documento quando há; o texto como último recurso — duas memórias com
    o mesmo texto são a mesma para quem lê o prompt.
    """
    if isinstance(memoria, dict):
        for chave in ("name", "id", "memory_id"):
            valor = memoria.get(chave)
            if isinstance(valor, str) and valor:
                return valor
        meta = memoria.get("metadata")
        if isinstance(meta, dict) and isinstance(meta.get("name"), str):
            return meta["name"]
    else:
        for chave in ("name", "id"):
            valor = getattr(memoria, chave, None)
            if isinstance(valor, str) and valor:
                return valor
    return _texto_de_memoria(memoria)[:120]


def _thread_de(request: Any) -> str:
    config = getattr(getattr(request, "runtime", None), "config", None) or {}
    conf = config.get("configurable") if isinstance(config, dict) else None
    if isinstance(conf, dict) and conf.get("thread_id"):
        return str(conf["thread_id"])
    return ""


def _middleware_base():
    from langchain.agents.middleware import AgentMiddleware

    return AgentMiddleware


class DnaRecallMiddleware(_middleware_base()):  # type: ignore[misc]
    """Injeta memória relevante no sistema, quando vale a pena.

    ``recall`` é ``async (consulta: str, limite: int) -> Sequence`` e é do HOST:
    ele tem o cliente MCP, a credencial e o tenant. Ausente, o middleware é um
    no-op — um deployment sem memória continua servindo.
    """

    def __init__(
        self,
        recall: Callable[..., Awaitable[Sequence[Any]]] | None = None,
        *,
        limit: int = MAX_MEMORIES,
    ) -> None:
        super().__init__()
        self._recall = recall
        self._limit = limit
        #: `thread_id -> (chaves, bloco)`. Em processo e limitado: a histerese é
        #: uma otimização de estabilidade, e perdê-la num restart custa um
        #: prompt diferente, nunca uma resposta errada.
        self._ultimo: dict[str, tuple[frozenset[str], str]] = {}

    async def awrap_model_call(self, request, handler):  # noqa: D102
        instrucao = await self._buscar(request)
        if not instrucao:
            return await handler(request)

        base = getattr(request, "system_message", None)
        texto = getattr(base, "content", None) or (base if isinstance(base, str) else "")
        return await handler(
            request.override(system_prompt=f"{texto}\n\n{instrucao}".strip())
        )

    async def _buscar(self, request) -> str:
        if self._recall is None:
            return ""
        consulta = cues(getattr(request, "messages", None) or [])
        if not worth_recalling(consulta):
            return ""
        try:
            memorias = await self._recall(consulta, self._limit)
        except Exception:  # noqa: BLE001 — memória indisponível NÃO derruba o turno
            _LOGGER.warning("recall automático falhou", exc_info=True)
            return ""

        texto = self._estavel(request, memorias or [])
        if texto:
            # ⚠️ Deixa rastro. Memória que entra no prompt sem aparecer é mágica
            # não auditável: o usuário vê o agente "saber" algo e não tem como
            # perguntar de onde veio.
            self._carimbar(len(list(memorias or [])[:MAX_MEMORIES]), consulta)
        return texto

    def _estavel(self, request, memorias: Sequence[Any]) -> str:
        """O bloco, preferindo o ANTERIOR quando o conjunto mal mudou.

        ⚠️ Devolve o bloco velho, não "nada". Pular a injeção quando o set não
        muda tiraria a memória do prompt exatamente nos turnos em que ela
        continua valendo — o oposto do que a histerese quer.
        """
        thread = _thread_de(request)
        novas = frozenset(_chave_de(m) for m in memorias if _chave_de(m))
        anterior = self._ultimo.get(thread)

        if anterior is not None and novas:
            antigas, bloco_antigo = anterior
            if antigas and len(novas & antigas) / len(antigas) >= STICKY_OVERLAP:
                return bloco_antigo

        bloco = briefing(memorias)
        if bloco and thread:
            # Teto bobo, e de propósito: um processo longo com muitas conversas
            # não pode virar um vazamento de memória por causa de uma otimização
            # de prompt.
            if len(self._ultimo) > 500:
                self._ultimo.clear()
            self._ultimo[thread] = (novas, bloco)
        return bloco

    @staticmethod
    def _carimbar(quantas: int, consulta: str) -> None:
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span is not None and span.is_recording():
                span.set_attribute("dna.recall.count", quantas)
                span.set_attribute("dna.recall.query", consulta[:200])
        except Exception:  # noqa: BLE001 — telemetria nunca derruba o observado
            pass
