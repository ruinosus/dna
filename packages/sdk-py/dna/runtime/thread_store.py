"""``dna.runtime.thread_store`` — a conversa como CONTRATO, não como formato novo.

::

        quem PERGUNTA            a PORTA                 quem GUARDA
    ─────────────────────   ─────────────────   ───────────────────────────
     console / REST / MCP →  ThreadStorePort  →  índice (sidecar do host)
                                               →  transcript (checkpoint do
                                                  framework, só LEITURA)

## O que este módulo existe para nomear

Hoje o transcript de um copiloto vive nos **checkpoints do framework** — no
LangGraph, ``checkpoints``/``checkpoint_blobs``/``checkpoint_writes``, chaveados
por ``(thread_id, checkpoint_ns, checkpoint_id)``. Esse mecanismo é o motor de
replay/interrupt do framework: ele carrega o state inteiro do grafo, não um
transcript. E ele não sabe **de quem** é a conversa: não tem dono, não tem
título, não responde "liste as MINHAS conversas".

Cada host que precisou dessas três coisas construiu o mesmo sidecar ao lado, e
cada face nova (REST, MCP, A2A) reinventou a leitura do transcript. O que
faltava não era armazenamento — era o **contrato com nome**.

## As três decisões que este contrato trava

1. **O transcript na fronteira é AG-UI.** Não se inventa formato de mensagem: o
   AG-UI já é a moeda da casa (o conversor oficial do bridge LangGraph é o mesmo
   que a rota de reidratação usa, e os eventos de run assíncrono já são gravados
   nesse formato). A porta devolve mensagens AG-UI em forma JSON — dicts, não
   objetos de framework.

2. **Zero dupla escrita.** A implementação de transcript é uma **projeção de
   LEITURA** sobre o que o framework já grava (:mod:`dna.runtime.adapters.
   langgraph_threads`). Gravar o transcript uma segunda vez — em documento, em
   tabela própria — pagaria custo por turno e criaria dois donos da verdade.
   O que o host grava é só o **índice**: dono, título, contagem, de qual
   copiloto/surface a conversa nasceu.

3. **A posse é fail-closed, e é UMA regra.** :func:`can_read_thread` é a decisão
   pura; toda face a chama em vez de escrever a sua. Duas regras de posse podem
   divergir, e a divergência só aparece quando alguém abre o thread de outro.

## Por que TRÊS Protocols em camada, e não um só

Porque um adapter de leitura sobre o checkpoint **não pode honestamente**
implementar índice e posse — o checkpoint não sabe de quem é a conversa. Um
Protocol único obrigaria esse adapter a stubar metade dos métodos, e um
``NotImplementedError`` atrás de um tipo que promete é pior do que um tipo menor
que cumpre:

* :class:`ThreadTranscriptPort` — LER a conversa (o adapter do framework);
* :class:`ThreadIndexPort` — de QUEM ela é, e listar as de alguém (o host);
* :class:`ThreadStorePort` — a união + :meth:`~ThreadStorePort.import_transcript`,
  o contrato inteiro (:class:`InMemoryThreadStore` é a implementação de
  referência).

## O que o export NÃO promete

``export_transcript``/``import_transcript`` são o caminho real de trocar de
framework: exporta AG-UI do backend velho, importa no novo. O que atravessa é o
**histórico visível**. O que NÃO atravessa é o run pendente — um interrupt
esperando aprovação humana vive no mecanismo do framework, e nenhum formato de
transcript o reconstrói. :attr:`TranscriptExport.pending_state_dropped` diz isso
em voz alta, por thread, em vez de deixar a promessa implícita e falsa.

:func:`migrate_thread` é esse caminho em UMA chamada, e o par
:func:`export_to_json` / :func:`export_from_json` é o que faz o envelope
atravessar um processo (um arquivo, um corpo HTTP). Sem o codec, cada host
inventaria a sua serialização do mesmo envelope — que é exatamente a divergência
silenciosa que este módulo existe para acabar.

## Retenção: a política é do documento, a conexão é do host

O Kind Copilot declara ``persistence.conversation.retention.max_age_days``;
:func:`retention_cutoff` transforma isso no instante de corte. O que faltava era
**quem varre**. :func:`sweep_retention` é o algoritmo — no SDK, uma vez — sobre
duas primitivas que só quem tem a conexão consegue cumprir
(:class:`ThreadPurgePort`) mais, opcionalmente, o apagador do transcript do
framework (:class:`TranscriptPurgePort`). Três decisões ficam travadas ali:

* **sem retenção declarada, a porta não é sequer consultada.** Guardar para
  sempre é o default, e um default que apaga seria o pior defeito possível
  deste módulo;
* **transcript primeiro, índice depois.** Uma queda no meio deixa a linha de
  índice viva — e a varredura seguinte reencontra o thread e termina o serviço.
  A ordem inversa deixaria checkpoint órfão que nenhum índice mais enxerga;
* **o que não se consegue datar nunca vence** (:func:`thread_expired`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

#: O formato do transcript na fronteira da porta. AG-UI (o protocolo de UI de
#: agente que a casa já fala) em forma JSON, versionado pelo nosso envelope — um
#: importador lê este campo antes de confiar no corpo.
TRANSCRIPT_FORMAT = "ag-ui/messages@1"

#: Teto do título derivado. Um título é como a conversa ABRIU, não um resumo.
TITLE_MAX = 80


# ── o dado neutro ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ThreadRef:
    """Uma conversa no ÍNDICE — o que uma lista "minhas conversas" precisa.

    Não carrega mensagem nenhuma: listar é barato justamente porque não toca o
    transcript. ``owner`` é o eixo de posse (o identificador estável do humano
    dono da conversa) e é obrigatório — uma linha sem dono não é listável por
    ninguém e não deve existir.

    ``copilot``/``surface`` respondem "de onde esta conversa nasceu": uma thread
    pertence ao copiloto/fluxo que a abriu, e é isso que deixa a lista ser
    filtrada por copiloto sem inventar um segundo eixo.
    """

    thread_id: str
    owner: str
    workspace: str | None = None
    tenant: str | None = None
    title: str | None = None
    message_count: int = 0
    copilot: str | None = None
    surface: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class Transcript:
    """A conversa LIDA — mensagens AG-UI (dicts JSON) + o state que a UI reidrata.

    ``state`` é o recorte EXPLICITAMENTE permitido pelo chamador
    (``state_keys``), nunca o state inteiro do grafo: o state de um framework
    carrega internals que não são contrato de ninguém. Sem allowlist, ``state``
    é ``{}`` — o default seguro.

    ``pending`` é verdadeiro quando o backend tem um run no meio do caminho (um
    interrupt esperando resposta humana). O transcript é legítimo mesmo assim;
    o flag existe para quem vai EXPORTAR saber o que fica para trás.
    """

    thread_id: str
    messages: tuple[Mapping[str, Any], ...] = ()
    state: Mapping[str, Any] = field(default_factory=dict)
    pending: bool = False

    @property
    def message_count(self) -> int:
        return len(self.messages)


@dataclass(frozen=True)
class TranscriptExport:
    """O envelope portátil de uma conversa — o que atravessa de um framework
    para outro.

    ``format`` é lido ANTES do corpo: um importador que não reconhece o formato
    recusa em vez de adivinhar. ``source`` registra de qual backend saiu
    (``"langchain"``, ``"maf"``, …) — proveniência, não instrução.

    ``pending_state_dropped`` é a honestidade do contrato: quando ``True``, o
    thread tinha um run pendente na origem e ele **não está aqui**. Importar
    este envelope restaura a conversa visível, nunca a aprovação em curso.
    """

    thread_id: str
    messages: tuple[Mapping[str, Any], ...] = ()
    state: Mapping[str, Any] = field(default_factory=dict)
    format: str = TRANSCRIPT_FORMAT
    source: str = ""
    exported_at: str = ""
    pending_state_dropped: bool = False


@dataclass(frozen=True)
class ThreadRetention:
    """Por quanto tempo uma conversa é GUARDADA — política declarada no Kind
    Copilot (``persistence.conversation.retention``).

    Declarar é o que a porta faz; **apagar é de quem tem a conexão**. O DNA não
    roda o expurgo por você — ele carrega o número até quem roda, para que a
    política viva no documento e não no crontab de alguém.

    ``max_age_days`` ausente = guardar indefinidamente (o comportamento de hoje,
    que continua sendo o default de quem não declara nada).
    """

    max_age_days: int | None = None


@dataclass(frozen=True)
class ConversationBinding:
    """O slot ``persistence.conversation`` resolvido — ``{backend, ref}`` mais a
    retenção declarada. Mesmo shape declarativo dos irmãos
    (``checkpoint``/``memory``/``cache``): o ``ref`` aponta um recurso de infra,
    e vários slots podem dividir um mesmo físico."""

    backend: str | None = None
    ref: str | None = None
    retention: ThreadRetention | None = None


@dataclass(frozen=True)
class RetentionSweep:
    """O relatório de UMA passada de :func:`sweep_retention`.

    ``cutoff`` ``None`` é o caso mais importante e o mais fácil de confundir com
    "nada venceu": significa que **não há política declarada** e que nenhuma
    porta foi consultada. Um chamador que loga a varredura tem de conseguir
    distinguir "não apaguei porque não devo" de "não apaguei porque não achei".

    ``expired`` são os ids selecionados; ``deleted`` é quanto o backend
    confirmou ter apagado. Os dois existem separados porque divergir é
    informação: um id que expirou e não foi apagado voltará na próxima passada,
    e um contador só de sucesso esconderia isso.
    """

    cutoff: datetime | None = None
    expired: tuple[str, ...] = ()
    deleted: int = 0
    dry_run: bool = False

    @property
    def has_policy(self) -> bool:
        """Houve política a aplicar. Falso = o copiloto guarda para sempre."""
        return self.cutoff is not None


@dataclass(frozen=True)
class ThreadMigration:
    """O resultado de :func:`migrate_thread` — a troca de framework, contada.

    ``pending_state_dropped`` repete o que o envelope já dizia, no nível em que
    a decisão é tomada: quem migra precisa saber que havia uma aprovação em
    curso do lado de lá, e ela não veio.
    """

    thread: ThreadRef
    source: str = ""
    message_count: int = 0
    pending_state_dropped: bool = False


class ThreadOwnershipError(Exception):
    """Um pedido tocou um ``thread_id`` que pertence a OUTRO dono.

    O caso real é um id forjado/adivinhado: o checkpoint é chaveado só por
    ``thread_id``, então sem esta guarda um id chutado leria (ou continuaria) a
    conversa de outra pessoa. Quem chama decide a forma da recusa — a face de UI
    da casa devolve vazio em vez de 403, porque uma lista vazia é exatamente o
    que um thread novo legitimamente parece e não confirma a existência do
    alheio.
    """

    def __init__(self, thread_id: str) -> None:
        self.thread_id = thread_id
        super().__init__(f"thread {thread_id!r} belongs to another owner")


# ── as decisões puras (uma regra, testável sem banco) ───────────────────


def can_read_thread(owner: str | None, requester: str | None) -> bool:
    """A decisão de posse, fail-closed em todo eixo:

    * pedido sem identidade (``requester`` vazio) → nunca;
    * thread sem dono conhecido (``owner`` ``None`` — não indexado) → nunca. Uma
      conversa legítima é indexada no seu PRIMEIRO turno, então um id sem índice
      não tem histórico listável — e um checkpoint não indexado jamais vaza;
    * dono diferente → nunca.

    Só o dono indexado lê a própria conversa.
    """
    return bool(requester) and owner is not None and owner == requester


def message_role(message: Any) -> str | None:
    """O papel de uma mensagem AG-UI (``{"role": ...}``) ou de um objeto de
    mensagem de framework (``.type``/``.role``). Tolerante de propósito: o
    índice é alimentado no gate de entrada, onde a mensagem ainda pode estar em
    qualquer uma das duas formas."""
    if isinstance(message, Mapping):
        role = message.get("role")
        return str(role) if role is not None else None
    for attr in ("role", "type"):
        value = getattr(message, attr, None)
        if value is not None:
            return str(value)
    return None


def message_text(message: Any) -> str:
    """O texto de uma mensagem, achatado. ``content`` pode ser string ou lista
    de partes (``{"type": "text", "text": ...}``) — multimodal é a forma normal,
    não a exceção."""
    content: Any = (
        message.get("content")
        if isinstance(message, Mapping)
        else getattr(message, "content", "")
    )
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        parts: list[str] = []
        for part in content:
            if isinstance(part, Mapping):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(part, str):
                parts.append(part)
        return " ".join(parts)
    return str(content or "")


def derive_title(messages: Sequence[Any]) -> str | None:
    """O título de uma conversa = o PRIMEIRO turno humano, numa linha, truncado.

    Derivado uma vez e mantido (quem indexa só o escreve quando ainda é nulo):
    uma conversa é nomeada por como ela ABRIU, e um título que muda sozinho a
    cada turno é um item de lista que ninguém reencontra. Sem texto humano
    ainda → ``None``, e a UI mostra o seu próprio rótulo de conversa sem título.
    """
    for message in messages:
        if message_role(message) not in ("user", "human"):
            continue
        text = " ".join(message_text(message).split())
        if not text:
            continue
        return text if len(text) <= TITLE_MAX else text[: TITLE_MAX - 1].rstrip() + "…"
    return None


def resolve_conversation(persistence: Mapping[str, Any] | None) -> ConversationBinding | None:
    """Lê o slot ``conversation`` de ``EmitContext.persistence`` (o bloco neutro
    ``{checkpoint, memory, cache, conversation}``) e devolve o binding, ou
    ``None`` quando o copiloto não declara conversa nenhuma.

    Um copiloto sem o slot é o comportamento de HOJE, intacto: o checkpoint do
    framework segue sendo o motor, e não há contrato de posse/retenção sobre
    ele. Declarar o slot é o que liga a porta — presença é a decisão.
    """
    slot = (persistence or {}).get("conversation")
    if not slot:
        return None
    retention_node = slot.get("retention") or None
    retention = (
        ThreadRetention(max_age_days=retention_node.get("max_age_days"))
        if isinstance(retention_node, Mapping)
        else None
    )
    return ConversationBinding(
        backend=slot.get("backend"), ref=slot.get("ref"), retention=retention
    )


def retention_cutoff(
    retention: ThreadRetention | None, now: datetime | None = None
) -> datetime | None:
    """O instante ANTES do qual uma conversa já venceu, ou ``None`` quando não
    há retenção declarada (guardar para sempre).

    É a conta que o expurgo precisa, aqui e não em cada host, para que dois
    hosts não interpretem "30 dias" de dois jeitos. Quem apaga continua sendo
    quem tem a conexão — este módulo não faz I/O.
    """
    if retention is None or not retention.max_age_days:
        return None
    now = now or datetime.now(timezone.utc)
    return now - timedelta(days=int(retention.max_age_days))


def parse_timestamp(value: Any) -> datetime | None:
    """Um dos carimbos ISO-8601 do índice (``created_at``/``updated_at``) como
    ``datetime`` ciente de fuso, ou ``None`` quando não dá para ler.

    Duas tolerâncias deliberadas, porque o carimbo vem de hosts diferentes:
    ``Z`` no fim (que nem toda versão de Python aceita em ``fromisoformat``) e
    carimbo ingênuo, lido como UTC — o índice é escrito em UTC por construção.
    Qualquer outra coisa é ``None``, e ``None`` NUNCA vence (ver
    :func:`thread_expired`).
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    texto = value.strip()
    if texto.endswith(("Z", "z")):
        texto = texto[:-1] + "+00:00"
    try:
        lido = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return lido if lido.tzinfo else lido.replace(tzinfo=timezone.utc)


def thread_expired(thread: ThreadRef, cutoff: datetime | None) -> bool:
    """A conversa venceu — ``updated_at`` é ANTERIOR ao corte.

    Fail-safe nos dois eixos que erram para o lado errado quando invertidos:

    * ``cutoff`` ``None`` (sem política) → nunca vence;
    * carimbo ausente ou ilegível → nunca vence. Uma linha que não se consegue
      datar é uma linha sobre a qual não se tem opinião, e a opinião default de
      um apagador tem de ser "não". O custo do falso-negativo é guardar demais;
      o do falso-positivo é a conversa de alguém.

    A comparação é ESTRITA (``<``): uma conversa exatamente na idade limite
    ainda está dentro dela.
    """
    if cutoff is None:
        return False
    quando = parse_timestamp(thread.updated_at)
    return quando is not None and quando < cutoff


# ── os Protocols ────────────────────────────────────────────────────────


@runtime_checkable
class ThreadTranscriptPort(Protocol):
    """LER a conversa. É o que um adapter de framework consegue prometer: o
    transcript vive no mecanismo do framework, e esta metade da porta é uma
    PROJEÇÃO DE LEITURA sobre ele — nenhuma escrita, nenhum turno mais caro."""

    #: Id estável do backend de origem (``"langchain"``, ``"maf"``, …). Viaja no
    #: envelope de export como proveniência.
    source: str

    async def fetch_transcript(
        self, thread_id: str, *, state_keys: Sequence[str] | None = None
    ) -> Transcript:
        """O transcript de ``thread_id`` em mensagens AG-UI. ``state_keys`` é a
        allowlist do state que a UI reidrata (``None`` = o default declarado
        pela implementação, normalmente nenhum; vazia = só as mensagens). Um
        thread inexistente devolve um :class:`Transcript` VAZIO, nunca um erro —
        é o que uma conversa recém-criada legitimamente parece."""
        ...

    async def export_transcript(
        self, thread_id: str, *, state_keys: Sequence[str] | None = None
    ) -> TranscriptExport:
        """O envelope portátil do thread. Carrega o histórico visível e
        SINALIZA (``pending_state_dropped``) quando deixa um run pendente para
        trás."""
        ...


@runtime_checkable
class ThreadIndexPort(Protocol):
    """De QUEM é a conversa, e quais são as de alguém. É a metade que o
    framework não sabe responder e que o host guarda num índice ao lado — o
    único lugar onde há escrita, e ela é por turno, barata e sem transcript."""

    async def index_thread(
        self,
        *,
        owner: str | None,
        thread_id: str | None,
        workspace: str | None = None,
        tenant: str | None = None,
        messages: Sequence[Any] = (),
        copilot: str | None = None,
        surface: str | None = None,
    ) -> ThreadRef | None:
        """Registra/atualiza a conversa e ENFORCE a posse.

        Fail-closed: sem ``owner`` ou sem ``thread_id`` → ``None`` e nada é
        escrito (nunca se indexa uma conversa sem dono). Thread já pertencente a
        outro dono → :class:`ThreadOwnershipError`, ANTES de qualquer escrita —
        é este ponto que fecha o buraco do checkpoint chaveado só por
        ``thread_id``.

        Título é derivado uma vez (:func:`derive_title`) e mantido;
        ``copilot``/``surface`` idem — a conversa pertence a onde nasceu.
        """
        ...

    async def fetch_threads(
        self,
        *,
        owner: str,
        workspace: str | None = None,
        copilot: str | None = None,
        limit: int = 50,
    ) -> Sequence[ThreadRef]:
        """As conversas de ``owner``, mais recentes primeiro por atividade real.
        Os filtros COMPÕEM com o dono, nunca o substituem — sem ``owner`` a
        resposta é vazia, jamais "todas"."""
        ...

    async def thread_owner(self, thread_id: str) -> str | None:
        """O dono indexado de ``thread_id``, ou ``None`` se desconhecido. A
        metade de leitura da guarda de posse — combine com
        :func:`can_read_thread`, não com uma segunda regra."""
        ...


@runtime_checkable
class ThreadPurgePort(Protocol):
    """As duas primitivas que **só quem tem a conexão** consegue cumprir, e que
    são tudo o que :func:`sweep_retention` precisa do host.

    São duas, e não uma varredura inteira, de propósito: o ALGORITMO (qual é o
    corte, quem venceu, em que ordem apagar, o que reportar) é do SDK, para que
    dois hosts não interpretem a mesma política de dois jeitos; o que sobra para
    o host é uma consulta e um delete — o que ele já sabe escrever no seu
    dialeto. Um host que implementasse a varredura inteira reescreveria a
    política, e é aí que "30 dias" vira dois números diferentes.
    """

    async def expired_threads(
        self,
        *,
        cutoff: datetime,
        copilot: str | None = None,
        limit: int = 100,
    ) -> Sequence[ThreadRef]:
        """As conversas com ``updated_at`` anterior a ``cutoff``, mais antigas
        primeiro, no máximo ``limit``.

        O filtro ``copilot`` não é enfeite: a retenção é declarada no documento
        do **Copilot**, então uma varredura sem esse recorte aplicaria a
        política de um copiloto às conversas de outro. ``None`` = todos, e só é
        legítimo quando o host sabe que a política é única.

        O lote existe para que a varredura seja repetível: quem chama roda até
        vir vazio, e uma queda no meio não deixa trabalho perdido.
        """
        ...

    async def delete_thread(self, thread_id: str) -> bool:
        """Apaga a linha de ÍNDICE da conversa. ``True`` = havia algo e sumiu.

        Não apaga o transcript — ele vive no mecanismo do framework, fora do
        alcance do índice. Quem tem as duas metades passa também um
        :class:`TranscriptPurgePort` para :func:`sweep_retention`.

        Idempotente por contrato: apagar o que já não existe é ``False``, nunca
        erro — uma varredura interrompida é retomada, não reparada.
        """
        ...


@runtime_checkable
class TranscriptPurgePort(Protocol):
    """A metade do apagamento que só o FRAMEWORK consegue: sumir com o
    transcript de fato (no LangGraph, as linhas de checkpoint do thread).

    Protocol separado pela mesma razão que separa leitura de índice: um adapter
    de framework não sabe de quem é a conversa nem quando ela venceu, e um
    índice não alcança o checkpoint. Juntar os dois num tipo só obrigaria
    alguém a stubar metade.
    """

    async def delete_transcript(self, thread_id: str) -> None:
        """Apaga o que o framework guarda do thread. Idempotente: um thread sem
        checkpoint não é erro."""
        ...


@runtime_checkable
class ThreadStorePort(ThreadTranscriptPort, ThreadIndexPort, Protocol):
    """O contrato INTEIRO: índice + transcript + a escrita de portabilidade.

    Uma implementação disto é o que um host injeta quando quer que conversa seja
    dado do DNA de ponta a ponta. Um adapter de framework normalmente cumpre só
    :class:`ThreadTranscriptPort`; o host compõe as duas metades.
    """

    async def import_transcript(
        self,
        export: TranscriptExport,
        *,
        owner: str,
        thread_id: str | None = None,
        workspace: str | None = None,
        tenant: str | None = None,
        copilot: str | None = None,
        surface: str | None = None,
    ) -> ThreadRef:
        """Importa um envelope como conversa de ``owner``.

        Recusa formato desconhecido (``ValueError``) em vez de adivinhar o
        corpo, e recusa thread de outro dono (:class:`ThreadOwnershipError`) —
        a MESMA regra de posse de :meth:`~ThreadIndexPort.index_thread`.

        O que entra é o histórico visível. Um run pendente na origem não
        atravessa, e o envelope já dizia isso.
        """
        ...


# ── os verbos (o algoritmo mora aqui, a conexão mora no host) ───────────


async def sweep_retention(
    index: ThreadPurgePort,
    retention: ThreadRetention | None,
    *,
    transcript: TranscriptPurgePort | None = None,
    copilot: str | None = None,
    now: datetime | None = None,
    limit: int = 100,
    dry_run: bool = False,
) -> RetentionSweep:
    """Aplica UMA passada da retenção declarada. É o "quem varre" que faltava.

    O DNA carregava o número (``retention.max_age_days``) e a conta
    (:func:`retention_cutoff`) desde a fatia 1, e nada mais: o slot existia sem
    ninguém que agisse sobre ele. Este verbo age — sobre as primitivas do host,
    sem abrir conexão nenhuma e sem depender de scheduler algum. Quem chama é um
    job do host (cron, worker, comando), e chamar em laço até ``expired`` vir
    vazio é o uso previsto.

    A ordem do apagamento é contrato, não detalhe: **transcript primeiro,
    índice depois**. Se o processo morre no meio, a linha de índice sobrevive, a
    passada seguinte reencontra o thread e termina o serviço. A ordem inversa
    deixaria checkpoint órfão — dado que ninguém mais lista, ninguém mais apaga
    e ninguém mais sabe que existe.

    ``dry_run`` seleciona e reporta sem apagar nada: é como se olha uma política
    de retenção nova antes de confiar nela.
    """
    cutoff = retention_cutoff(retention, now=now)
    if cutoff is None:
        # Sem política declarada a porta NÃO é consultada. Guardar para sempre é
        # o default de quem não declara nada, e uma varredura que "não achou
        # nada" seria indistinguível de uma que não devia ter rodado.
        return RetentionSweep(cutoff=None, dry_run=dry_run)

    vencidas = await index.expired_threads(cutoff=cutoff, copilot=copilot, limit=limit)
    ids = tuple(t.thread_id for t in vencidas if t.thread_id)
    if dry_run:
        return RetentionSweep(cutoff=cutoff, expired=ids, deleted=0, dry_run=True)

    apagadas = 0
    for thread_id in ids:
        if transcript is not None:
            await transcript.delete_transcript(thread_id)
        if await index.delete_thread(thread_id):
            apagadas += 1
    return RetentionSweep(cutoff=cutoff, expired=ids, deleted=apagadas, dry_run=False)


# ── o envelope atravessando processo ────────────────────────────────────


def export_to_json(export: TranscriptExport) -> dict[str, Any]:
    """O envelope em JSON puro — dicts, listas e escalares, nada de dataclass.

    Existe porque "exporta do backend velho, importa no novo" atravessa um
    arquivo ou um corpo HTTP, e sem um codec no contrato cada host inventaria a
    sua serialização do MESMO envelope. Duas serializações do mesmo dado é a
    divergência silenciosa de sempre, só que na fronteira mais cara de todas.
    """
    return {
        "format": export.format,
        "thread_id": export.thread_id,
        "source": export.source,
        "exported_at": export.exported_at,
        "pending_state_dropped": export.pending_state_dropped,
        "messages": [dict(m) for m in export.messages],
        "state": dict(export.state),
    }


def export_from_json(payload: Mapping[str, Any]) -> TranscriptExport:
    """Lê um envelope serializado — checando o ``format`` ANTES do corpo.

    Um formato desconhecido é ``ValueError``, jamais uma leitura otimista: o
    corpo de um transcript de outra versão pode até se parecer com este, e
    "quase certo" numa conversa importada é pior do que recusar.
    """
    if not isinstance(payload, Mapping):
        raise TypeError("transcript export payload must be a mapping")
    formato = payload.get("format")
    if formato != TRANSCRIPT_FORMAT:
        raise ValueError(
            f"unknown transcript format {formato!r}; this reader "
            f"reads {TRANSCRIPT_FORMAT!r}"
        )
    mensagens = payload.get("messages") or ()
    if not isinstance(mensagens, (list, tuple)):
        raise ValueError("transcript export 'messages' must be a list")
    estado = payload.get("state") or {}
    if not isinstance(estado, Mapping):
        raise ValueError("transcript export 'state' must be an object")
    return TranscriptExport(
        thread_id=str(payload.get("thread_id") or ""),
        messages=tuple(dict(m) for m in mensagens if isinstance(m, Mapping)),
        state=dict(estado),
        format=TRANSCRIPT_FORMAT,
        source=str(payload.get("source") or ""),
        exported_at=str(payload.get("exported_at") or ""),
        pending_state_dropped=bool(payload.get("pending_state_dropped")),
    )


async def migrate_thread(
    source: ThreadTranscriptPort,
    target: ThreadStorePort,
    thread_id: str,
    *,
    owner: str,
    state_keys: Sequence[str] | None = None,
    target_thread_id: str | None = None,
    workspace: str | None = None,
    tenant: str | None = None,
    copilot: str | None = None,
    surface: str | None = None,
) -> ThreadMigration:
    """Troca de framework, para UMA conversa, em uma chamada: exporta de onde
    ela está e importa onde ela vai passar a estar.

    A fatia 1 deixou as duas metades prontas e ninguém as juntando — e um
    caminho que existe só como "chame A e depois B" é um caminho que cada host
    percorre à sua maneira, inclusive errando a ordem dos donos. Aqui a posse é
    afirmada UMA vez, no destino: importar sobre thread alheio levanta
    :class:`ThreadOwnershipError` antes de qualquer escrita.

    O que atravessa é o histórico visível. O run pendente fica — e o resultado
    diz, em vez de deixar o chamador descobrir quando o usuário reabrir a
    conversa e a aprovação não estiver mais lá.
    """
    export = await source.export_transcript(thread_id, state_keys=state_keys)
    ref = await target.import_transcript(
        export,
        owner=owner,
        thread_id=target_thread_id or thread_id,
        workspace=workspace,
        tenant=tenant,
        copilot=copilot,
        surface=surface,
    )
    return ThreadMigration(
        thread=ref,
        source=export.source,
        message_count=len(export.messages),
        pending_state_dropped=export.pending_state_dropped,
    )


# ── implementação de referência ─────────────────────────────────────────


class InMemoryThreadStore:
    """A :class:`ThreadStorePort` inteira, em memória.

    Existe por dois motivos, os dois de contrato: prova que a porta é
    IMPLEMENTÁVEL como um todo (um Protocol que ninguém consegue cumprir é
    desenho, não contrato), e serve de par de conformidade nos testes — o mesmo
    kit roda contra ela e contra um adapter de framework, e a divergência falha
    em CI em vez de aparecer em produção.

    Também é o backend honesto de uma execução local sem banco: as conversas
    existem, são listáveis e somem no fim do processo — que é exatamente o que
    "sem persistência declarada" significa.
    """

    source = "inmemory"

    def __init__(self) -> None:
        self._threads: dict[str, ThreadRef] = {}
        self._transcripts: dict[str, Transcript] = {}

    # -- índice --------------------------------------------------------

    async def index_thread(
        self,
        *,
        owner: str | None,
        thread_id: str | None,
        workspace: str | None = None,
        tenant: str | None = None,
        messages: Sequence[Any] = (),
        copilot: str | None = None,
        surface: str | None = None,
    ) -> ThreadRef | None:
        if not owner or not thread_id:
            return None
        existing = self._threads.get(thread_id)
        if existing is not None and existing.owner != owner:
            raise ThreadOwnershipError(thread_id)
        now = datetime.now(timezone.utc).isoformat()
        ref = ThreadRef(
            thread_id=thread_id,
            owner=owner,
            workspace=workspace if existing is None else (existing.workspace or workspace),
            tenant=tenant if existing is None else (existing.tenant or tenant),
            # COALESCE do primeiro valor: título/copiloto/surface descrevem como
            # a conversa NASCEU e não se reescrevem a cada turno.
            title=(existing.title if existing and existing.title else derive_title(messages)),
            message_count=len(messages),
            copilot=(existing.copilot if existing and existing.copilot else copilot),
            surface=(existing.surface if existing and existing.surface else surface),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._threads[thread_id] = ref
        return ref

    async def fetch_threads(
        self,
        *,
        owner: str,
        workspace: str | None = None,
        copilot: str | None = None,
        limit: int = 50,
    ) -> Sequence[ThreadRef]:
        if not owner:
            return []
        rows = [
            t
            for t in self._threads.values()
            if t.owner == owner
            and (workspace is None or t.workspace == workspace)
            and (copilot is None or t.copilot == copilot)
        ]
        rows.sort(key=lambda t: t.updated_at or "", reverse=True)
        return rows[: max(0, limit)]

    async def thread_owner(self, thread_id: str) -> str | None:
        ref = self._threads.get(thread_id)
        return ref.owner if ref else None

    # -- retenção ------------------------------------------------------

    async def expired_threads(
        self,
        *,
        cutoff: datetime,
        copilot: str | None = None,
        limit: int = 100,
    ) -> Sequence[ThreadRef]:
        rows = [
            t
            for t in self._threads.values()
            if (copilot is None or t.copilot == copilot) and thread_expired(t, cutoff)
        ]
        # Mais ANTIGAS primeiro: um lote que começa pelas recentes deixa as
        # vencidas há mais tempo para o fim, que é exatamente ao contrário do
        # que uma retenção quer.
        rows.sort(key=lambda t: t.updated_at or "")
        return rows[: max(0, limit)]

    async def delete_thread(self, thread_id: str) -> bool:
        return self._threads.pop(thread_id, None) is not None

    async def delete_transcript(self, thread_id: str) -> None:
        # Idempotente: aqui o transcript é um dict; num framework de verdade é o
        # checkpoint dele. Nos dois casos, apagar o que não existe não é erro.
        self._transcripts.pop(thread_id, None)

    # -- transcript ----------------------------------------------------

    async def fetch_transcript(
        self, thread_id: str, *, state_keys: Sequence[str] | None = None
    ) -> Transcript:
        stored = self._transcripts.get(thread_id)
        if stored is None:
            return Transcript(thread_id=thread_id)
        allowed = set(state_keys or ())
        return Transcript(
            thread_id=thread_id,
            messages=stored.messages,
            state={k: v for k, v in stored.state.items() if k in allowed},
            pending=stored.pending,
        )

    async def export_transcript(
        self, thread_id: str, *, state_keys: Sequence[str] | None = None
    ) -> TranscriptExport:
        transcript = await self.fetch_transcript(thread_id, state_keys=state_keys)
        return TranscriptExport(
            thread_id=thread_id,
            messages=transcript.messages,
            state=transcript.state,
            source=self.source,
            exported_at=datetime.now(timezone.utc).isoformat(),
            pending_state_dropped=transcript.pending,
        )

    async def import_transcript(
        self,
        export: TranscriptExport,
        *,
        owner: str,
        thread_id: str | None = None,
        workspace: str | None = None,
        tenant: str | None = None,
        copilot: str | None = None,
        surface: str | None = None,
    ) -> ThreadRef:
        if export.format != TRANSCRIPT_FORMAT:
            raise ValueError(
                f"unknown transcript format {export.format!r}; "
                f"this store reads {TRANSCRIPT_FORMAT!r}"
            )
        target = thread_id or export.thread_id
        existing = self._threads.get(target)
        if existing is not None and existing.owner != owner:
            raise ThreadOwnershipError(target)
        self._transcripts[target] = Transcript(
            thread_id=target,
            messages=tuple(export.messages),
            state=dict(export.state),
            # O que entra é histórico. Um run pendente ficou na origem — importar
            # jamais ressuscita uma aprovação em curso.
            pending=False,
        )
        ref = await self.index_thread(
            owner=owner,
            thread_id=target,
            workspace=workspace,
            tenant=tenant,
            messages=list(export.messages),
            copilot=copilot,
            surface=surface,
        )
        assert ref is not None  # owner + thread_id validados acima
        return ref

    # -- conveniência de teste/execução local --------------------------

    def seed_transcript(self, transcript: Transcript) -> None:
        """Planta um transcript direto (sem passar por um framework). É o que
        deixa o kit de conformidade exercitar a metade de LEITURA desta
        implementação sem grafo nenhum."""
        self._transcripts[transcript.thread_id] = transcript


__all__ = [
    "TRANSCRIPT_FORMAT",
    "TITLE_MAX",
    "ThreadRef",
    "Transcript",
    "TranscriptExport",
    "ThreadRetention",
    "ThreadMigration",
    "RetentionSweep",
    "ConversationBinding",
    "ThreadOwnershipError",
    "ThreadTranscriptPort",
    "ThreadIndexPort",
    "ThreadPurgePort",
    "TranscriptPurgePort",
    "ThreadStorePort",
    "InMemoryThreadStore",
    "can_read_thread",
    "derive_title",
    "export_from_json",
    "export_to_json",
    "message_role",
    "message_text",
    "migrate_thread",
    "parse_timestamp",
    "resolve_conversation",
    "retention_cutoff",
    "sweep_retention",
    "thread_expired",
]
