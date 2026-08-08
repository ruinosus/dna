"""A base de conhecimento: a COLA entre um arquivo subido e uma resposta citada.

## O que este módulo é, e sobretudo o que ele NÃO é

Não é um motor de RAG. As peças todas já existiam e já eram nossas — o
``SourceArtifact`` guarda o original, o ``EmbeddingPort``/ONNX embute de graça,
``dna_search_docs_*`` indexa, ``search_instances_impl`` entrega um envelope
honesto. Faltava a cola, e é só ela que mora aqui:

    arquivo → (markitdown) → Markdown → (chonkie) → trechos
            → instâncias de ``KnowledgeChunk`` → backfill_index
            → dna_search_docs_384 → busca → hits COM SCORE E FONTE

## ⭐ A FRONTEIRA: onde os bytes param, e por quê

A **extração** (bytes → Markdown) vive na camada de HOSPEDAGEM, e a **ingestão**
(Markdown → trechos → instâncias → índice) vive AQUI. A linha não é arbitrária:

* o ``uri`` de um ``SourceArtifact`` é **opaco por contrato** — identidade,
  nunca credencial (o descritor diz isso com todas as letras). Um SDK
  vendor-neutro que soubesse resolver ``blob://`` teria de saber de credencial,
  e é exatamente esse o furo que a regra open-core existe para não abrir;
* o conversor (``markitdown``) é dependência do HOST, que já a declara e já a
  usa no anexo de conversa. Trazê-la para cá seria uma SEGUNDA extração, e duas
  extrações do mesmo arquivo divergem no dia em que uma for corrigida.

Por isso :func:`ingest_knowledge_impl` recebe **Markdown já extraído**, e não
bytes nem leitor injetado. Um ``extract`` injetado foi considerado e recusado
por não fazer NADA: o host continuaria fornecendo o callable, os bytes e o
sha256, e o SDK só os repassaria — uma indireção sem comportamento.

⚠️ **O sha256 é dos BYTES ORIGINAIS, jamais do Markdown.** Hashear o texto
extraído daria um valor que parece o mesmo campo e nunca casa com o
``SourceArtifact`` — uma citação que não confere. Por isso a porta EXIGE o
``source_sha256`` e vai LER a procedência (``uri``, ``filename``) da instância
do artefato, em vez de aceitá-la do chamador.

## ⭐ A decisão que rege esta porta (fundador, 08/08/2026 — i-154)

**(b) + (c)**, e a (a) foi RECUSADA com número na tela:

* **(a)** *"o copiloto diz 'não achei nada'"* — ⛔ exige um piso de relevância
  que a medição desta release provou não existir: **8 de 12 consultas
  IRRELEVANTES pontuam acima da PIOR relevante** (dna#364, i-103, 24 consultas
  contra o índice real). Prometer "não achei" sem poder cumprir seria a pior
  das três — o silêncio viraria afirmação.
* **(b)** devolver os N melhores **e DIZER que podem não servir**.
* **(c)** todo trecho **CITADO COM A FONTE**: qual arquivo, e ONDE dentro dele.

E a instrução do agente que PROÍBE afirmar com base em trecho fraco é METADE da
entrega, não enfeite — sem ela (b) vira (a) na prática, porque o modelo lê os N
melhores e responde como se fossem certos. Ela é DADO, não string de código:
mora no catálogo de ``PromptTemplate`` (:mod:`dna.application.knowledge_voice`).

⚠️ Nada disto torna a busca PRECISA. O reranker cross-encoder continua sendo o
remédio real da relevância e continua NOMEADO e não construído (i-103). Esta
porta torna o produto HONESTO sem ele. O dia em que o reranker entrar, (a) passa
a ser possível — e aí é decisão nova.

## Por que esta porta não inventa envelope

``search_instances_impl`` já entrega ``mode``/``degraded``/``degraded_reason``/
``notice``/``relevance_notice``/``min_similarity``/``floored_out``/
``index_refreshed``. Este módulo CHAMA aquela porta e acrescenta uma coisa só —
a citação. Um segundo envelope seria um segundo lugar para a honestidade
divergir, e o primeiro já está certo.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from dna.application.instances import search_instances_impl

logger = logging.getLogger(__name__)

__all__ = [
    "COLLECTION_RE",
    "DEFAULT_CHUNK_CHARS",
    "DEFAULT_MIN_CHUNK_CHARS",
    "KNOWLEDGE_CHUNK_KIND",
    "NAME_SEPARATOR",
    "CHARACTER_TOKENIZER",
    "chunk_markdown",
    "chunk_name",
    "collection_prefix",
    "ingest_knowledge_impl",
    "search_knowledge_impl",
    "source_prefix",
]

#: O Kind cujas instâncias são trechos. Uma coleção é um PREFIXO do nome deles.
KNOWLEDGE_CHUNK_KIND = "KnowledgeChunk"

#: O alfabeto de uma coleção, o MESMO que o descritor do Kind impõe em
#: ``spec.collection``. Repetido aqui para que a recusa aconteça ANTES de
#: escrever o primeiro trecho, com o nome do campo na mensagem, em vez de sair
#: como erro de schema no trecho 0 de duzentos.
COLLECTION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

#: ⭐ O separador do nome de um trecho, e ele NÃO é uma escolha estética.
#:
#: Este módulo nasceu com ``/``, e um nome com ``/`` NÃO PODE SER ESCRITO: o
#: kernel valida todo nome de instância como um ÚNICO componente de caminho
#: (``dna.kernel.errors.validate_instance_name`` → ``_path_component_fault``,
#: chamado por ``Kernel.write_instance`` e ``Kernel.delete_instance`` antes de
#: qualquer adapter), e um ``/`` é recusado porque o adapter de arquivo grava
#: em ``<scope>/<container>/<name>``. A metade de LEITURA passou verde com o
#: formato antigo porque ler não valida nome; foi a metade de ESCRITA que
#: cobrou. Guarda: ``test_knowledge_ingest.py::test_chunk_name_e_um_componente_
#: de_caminho_valido``.
#:
#: E o substituto não pode ser qualquer caractere legal. Ele tem de estar FORA
#: do alfabeto de :data:`COLLECTION_RE` (``[a-z0-9-]``), senão o prefixo de uma
#: coleção alcança outra: com ``-`` como separador, a coleção ``handbook``
#: teria prefixo ``handbook-`` e varreria os trechos de ``handbook-2024``, que
#: é exatamente o vazamento que a barra final existia para impedir. O ponto
#: está fora do alfabeto, é explicitamente permitido pela regra de componente
#: (*"Dots, hyphens and double hyphens are fine"*) e não tem significado para
#: nenhum dos dois stores.
NAME_SEPARATOR = "."


def collection_prefix(collection: str) -> str:
    """O prefixo de nome que ISOLA uma coleção dentro do índice.

    Uma coleção não é um ``scope`` (o scope é função 1:1 do workspace e a porta
    NEGA qualquer outro — ``LiveDna.scope_is_bound``), não é uma coluna (seria
    migration nova sobre a 0013, que é de hoje): é um prefixo do NOME da
    instância, filtrado no SQL pelo índice único que já existe. O separador
    final é obrigatório — sem ele ``handbook`` alcançaria ``handbook-2024``.
    Por que ``.`` e não ``/``, ver :data:`NAME_SEPARATOR`."""
    return f"{collection}{NAME_SEPARATOR}"


def source_prefix(collection: str, sha256: str) -> str:
    """O prefixo que isola os trechos de UM arquivo DENTRO de uma coleção.

    É o universo da re-ingestão: exatamente as instâncias que uma nova passagem
    do mesmo artefato pode substituir ou tornar órfãs. Um prefixo mais largo
    (a coleção) apagaria os trechos de outros arquivos; um mais estreito não
    existe, porque abaixo dele só há o ordinal."""
    return f"{collection}{NAME_SEPARATOR}{sha256[:12]}{NAME_SEPARATOR}"


def chunk_name(collection: str, sha256: str, ordinal: int) -> str:
    """O nome determinístico de um trecho: ``<collection>.<sha12>.<ordinal>``.

    Determinístico de propósito: re-ingerir o MESMO arquivo na MESMA coleção
    reescreve as mesmas instâncias em vez de duplicar o corpus, e o índice pula
    o que não mudou (idempotência por ``text_hash``). O ordinal é zero-padded
    para que a ordem lexicográfica do nome seja a ordem de leitura."""
    return f"{source_prefix(collection, sha256)}{ordinal:05d}"


def _citation(spec: dict[str, Any]) -> dict[str, Any]:
    """A FONTE de um trecho, projetada do spec — o (c) da decisão.

    ⚠️ Só reporta o que o spec REALMENTE carrega. Um campo ausente fica ausente:
    nunca `0`, nunca "desconhecido", e sobretudo nunca uma PÁGINA estimada. O
    markitdown devolve Markdown plano e não sabe a página; um número inventado
    seria uma citação falsa, e uma citação falsa é pior que nenhuma porque
    parece conferível."""
    cite: dict[str, Any] = {}
    for src, dst in (
        ("source_filename", "filename"),
        ("source_sha256", "sha256"),
        ("source_uri", "uri"),
        ("collection", "collection"),
        ("ordinal", "ordinal"),
        ("start_char", "start_char"),
        ("end_char", "end_char"),
    ):
        value = spec.get(src)
        if value is not None:
            cite[dst] = value
    return cite


async def search_knowledge_impl(
    live: Any, *, query: str, collection: str | None = None,
    scope: str | None = None, tenant: str | None = None, k: int = 10,
    min_similarity: float | None = None,
) -> dict[str, Any]:
    """Buscar TRECHOS do corpus e devolvê-los citados. A porta do (b)+(c).

    Delega inteiramente a ``search_instances_impl`` (mesmo refresh idempotente
    do índice, mesmo isolamento por tenant, MESMO envelope de honestidade) com
    ``kind=KnowledgeChunk``, e acrescenta duas coisas:

    * ``collection`` vira ``name_prefix`` — o filtro roda no SQL, onde os
      candidatos são ESCOLHIDOS. Pós-filtrar aqui seria devolver menos hits do
      que o k pedido sem nada dizer, que é o defeito que esta feature existe
      para não cometer.
    * cada hit ganha ``text`` + ``citation`` — o trecho que o modelo vai ler e
      a fonte que a resposta tem de mostrar.

    O envelope de ``search_instances_impl`` volta INTACTO. Um chamador que já
    sabe ler ``degraded``/``relevance_notice`` não aprende nada novo.
    """
    out = await search_instances_impl(
        live, kind=KNOWLEDGE_CHUNK_KIND, query=query, scope=scope,
        tenant=tenant, k=k, min_similarity=min_similarity,
        name_prefix=collection_prefix(collection) if collection else None,
    )
    out["collection"] = collection

    # Cada hit é um ponteiro ``{scope, kind, name, score, ...}``; o texto e a
    # procedência estão no spec. Carrega-se um a um (no máximo ``k``, e ``k`` é
    # limitado a 100 pela porta abaixo) porque um trecho SEM fonte não pode ser
    # citado — e um trecho que não pode ser citado esta porta não devolve.
    enriched: list[dict[str, Any]] = []
    for hit in out.get("hits") or []:
        try:
            doc = await live.kernel.get_instance(
                hit.get("scope") or out["scope"], KNOWLEDGE_CHUNK_KIND,
                hit["name"], tenant=tenant,
            )
        except Exception as exc:  # noqa: BLE001 — um hit ilegível não derruba a busca
            logger.warning(
                "search_knowledge: trecho %s ilegível: %s", hit.get("name"), exc,
            )
            continue
        spec = (doc or {}).get("spec") or {}
        text = spec.get("text")
        if not text:
            continue
        enriched.append({**hit, "text": text, "citation": _citation(spec)})

    out["hits"] = enriched
    out["count"] = len(enriched)
    return out


# ══════════════════════════ a metade de ESCRITA ══════════════════════════
#
# ⭐ NÃO SE ESCREVE CORTADOR À MÃO. O cortador é o `chonkie` (MIT, 4.6k★, "the
# lightweight ingestion library for fast, efficient and robust RAG pipelines"),
# pela regra não-negociável da casa: quando existe biblioteca mantida para o
# problema, ela é obrigatória. A busca foi feita e está registrada na ficha
# i-154 — recusadas com motivo: `docling` (cortador MELHOR, mas opera sobre
# formato próprio: adotá-lo é trocar a EXTRAÇÃO inteira, e virou ficha própria),
# `unstructured` (árvore pesada e sobrepõe o markitdown que o host já tem),
# `llama_index` (framework com modelo de documento que competiria com Kind), e
# RAGFlow / R2R / Cognee (motores completos — alternativas à NOSSA camada, não
# peças dentro dela).
#
# ⚠️ E o `chonkie` só é leve se FICAR leve: 6 dependências obrigatórias
# (`tqdm`, `numpy`, `chonkie-core`, `tenacity`, `httpx`, `tokie`), das quais
# `numpy` e `httpx` já estavam na árvore. Nenhum extra (`[semantic]`, `[st]`,
# `[neural]`, `[tokenizers]`) é ligado: cada um deles arrasta modelo, torch ou
# download, e peso é a ÚNICA razão legítima de recusar uma biblioteca oficial.
# Por isso ele é o extra `dna-sdk[knowledge]` e o import é preguiçoso.

#: O tamanho de um trecho, em CARACTERES. Escolhido pelo embedder que vai
#: consumi-lo: o piso da casa é o all-MiniLM-L6-v2 (fastembed/ONNX), cuja
#: janela é de 512 tokens — a ~4 caracteres por token, um trecho de 1200
#: caracteres cabe com folga, e o que não cabe o modelo TRUNCA calado. Menor é
#: melhor para recuperação (um trecho grande dilui o vetor no assunto médio do
#: parágrafo) e pior para leitura (um trecho pequeno perde o contexto).
DEFAULT_CHUNK_CHARS = 1200

#: ⚠️ O ``min_characters_per_chunk`` do ``chonkie``, e ele NÃO É O QUE O NOME
#: SUGERE. Medido em 08/08/2026, contra o chonkie 1.7.0:
#:
#:     texto = "frase de teste. " * 80     (1280 caracteres, chunk_size=200)
#:     min=1..16  → 7 trechos de ~192   ✅
#:     min=17..64 → 1 trecho de 1280    ⛔ SEIS VEZES o chunk_size pedido
#:
#: Ele não é um PISO sobre o trecho de saída — é um piso sobre cada SEGMENTO
#: que um nível pode produzir, e quando os segmentos naturais daquele nível são
#: menores que ele, o nível inteiro DESISTE de cortar e devolve o texto inteiro.
#: Como o último nível corta por PALAVRA (~5 caracteres), um valor "razoável"
#: como 64 desliga a recursão até o fim e entrega um trecho gigante.
#:
#: E o modo de falha é silencioso do pior jeito: o all-MiniLM-L6-v2 aceita 512
#: tokens e TRUNCA o resto sem dizer nada, então o trecho fica no corpus, com
#: texto e citação corretos, e um vetor que só representa o começo dele. Nada na
#: tela diferencia isso de um trecho bem cortado.
#:
#: Daí o valor 4 — abaixo do tamanho de uma palavra, para que o nível de
#: palavra sempre possa cortar. O piso sobre a SAÍDA quem dá é o
#: ``_merge_splits`` do próprio chonkie, que junta os segmentos pequenos até
#: perto do ``chunk_size``; não era este parâmetro que fazia isso.
DEFAULT_MIN_CHUNK_CHARS = 4

#: O tokenizador padrão do cortador. ``"character"`` conta CARACTERES e é o
#: único que não baixa nada nem exige extra — o que importa numa ingestão que
#: roda dentro de um container sem rede de saída. A consequência é dita em
#: :func:`chunk_markdown` e ela é sobre HONESTIDADE, não sobre desempenho.
CHARACTER_TOKENIZER = "character"

#: A mensagem quando o extra não está instalado. Uma linha, com o comando.
_CHONKIE_MISSING = (
    "a ingestão da base de conhecimento precisa do `chonkie`, que é um EXTRA: "
    "pip install 'dna-sdk[knowledge]'. O corte NÃO tem substituto à mão neste "
    "módulo de propósito — um cortador caseiro é a roda que a regra "
    "'usar a implementação oficial' existe para não reinventar."
)


def _markdown_rules() -> Any:
    """As regras recursivas para Markdown, DECLARADAS aqui em vez de baixadas.

    O ``chonkie`` publica exatamente estas regras como a receita ``markdown``,
    e ``RecursiveChunker.from_recipe("markdown")`` as busca no **Chonkie Hub**
    (um dataset no HuggingFace) — o que exige o extra ``[hub]`` E uma chamada de
    rede no momento da ingestão. Nenhum dos dois é aceitável aqui: um container
    que ingere um arquivo do cliente não sai para a internet buscar
    configuração, e o resultado do corte não pode depender de um repositório de
    terceiros estar no ar. Então a receita vira DADO no código, onde é revisável
    num diff, e ``rules=`` é o ponto de extensão que a própria biblioteca
    documenta para isto.

    Os cinco níveis, do mais estrutural ao mais bruto — e a ordem é a tese: um
    trecho deveria quebrar num limite que o AUTOR desenhou (o título), e só
    descer para o parágrafo, a linha, a frase e a palavra quando o de cima não
    couber.
    """
    from chonkie.types.recursive import RecursiveLevel, RecursiveRules

    return RecursiveRules(levels=[
        # 1. cabeçalhos — `include_delim="next"` porque o `#` abre a seção que
        #    vem DEPOIS dele; grudá-lo no trecho anterior daria a cada trecho o
        #    título do SEGUINTE, que é a pior legenda possível numa citação.
        RecursiveLevel(
            delimiters=["######", "#####", "####", "###", "##", "#"],
            include_delim="next",
        ),
        RecursiveLevel(delimiters=["\n\n", "\r\n\r\n"], include_delim="prev"),
        RecursiveLevel(delimiters=["\n", "\r"], include_delim="prev"),
        RecursiveLevel(delimiters=[". ", "! ", "? "], include_delim="prev"),
        RecursiveLevel(delimiters=None, whitespace=True, include_delim="prev"),
    ])


def chunk_markdown(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_CHARS,
    min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS,
    tokenizer: str = CHARACTER_TOKENIZER,
) -> list[dict[str, Any]]:
    """Cortar Markdown em trechos com OFFSET, via ``chonkie``. Puro.

    Devolve ``[{text, start_char, end_char, token_count}]`` na ordem de leitura.
    Separado da porta de propósito: o corte não toca kernel nem I/O, então ele
    se testa com uma string e sem banco, e a porta abaixo se testa sem inventar
    corte.

    ⚠️ ``token_count`` só vem preenchido quando o tokenizador REALMENTE conta
    tokens. Com ``"character"`` (o padrão, e o único offline) o ``chonkie``
    devolve o número de CARACTERES no mesmo atributo — reportá-lo como
    ``token_count`` seria um número que parece conferível e não é, que é a
    forma de mentira que este módulo inteiro existe para não cometer. O campo
    aceita ``null`` no schema justamente para isto.

    ⭐ **O ``chunk_size`` é um TETO, não uma sugestão** — e garanti-lo custou um
    segundo cortador. O ``RecursiveChunker`` desiste de cortar quando nenhum
    nível produz segmentos acima do ``min_characters_per_chunk`` (ver
    :data:`DEFAULT_MIN_CHUNK_CHARS`), e mesmo com o valor certo um "token" único
    maior que o teto — uma linha base64 dentro de uma cerca de código, um
    caminho gigante — não tem onde ser cortado. O que sobra é passado ao
    ``TokenChunker`` do próprio ``chonkie``, que é a primitiva de janela fixa da
    biblioteca e portanto respeita o teto por construção. Continua sendo a
    implementação oficial: o que este módulo faz é ESCOLHER entre as duas, não
    reimplementar nenhuma.

    Por que o teto importa mais do que parece: o embedder do piso
    (all-MiniLM-L6-v2) aceita 512 tokens e TRUNCA o excedente sem avisar. Um
    trecho grande demais fica no corpus com texto e citação corretos e um vetor
    que só representa o começo dele — e nada na tela distingue isso de um trecho
    bem cortado.
    """
    if not isinstance(text, str):
        raise TypeError(f"chunk_markdown: text deve ser str, veio {type(text).__name__}")
    if chunk_size < 1:
        raise ValueError(f"chunk_markdown: chunk_size deve ser >= 1, veio {chunk_size}")
    if min_chunk_chars < 1:
        raise ValueError(
            f"chunk_markdown: min_chunk_chars deve ser >= 1, veio {min_chunk_chars}")
    if not text.strip():
        return []
    try:
        from chonkie import RecursiveChunker, TokenChunker
    except ImportError as exc:  # pragma: no cover — depende do ambiente
        raise ImportError(_CHONKIE_MISSING) from exc

    chunker = RecursiveChunker(
        tokenizer=tokenizer,
        chunk_size=chunk_size,
        rules=_markdown_rules(),
        min_characters_per_chunk=min_chunk_chars,
    )
    counts_tokens = tokenizer != CHARACTER_TOKENIZER
    fallback: Any = None
    out: list[dict[str, Any]] = []
    for chunk in chunker.chunk(text):
        body = getattr(chunk, "text", "") or ""
        start = getattr(chunk, "start_index", 0) or 0
        count = getattr(chunk, "token_count", None)
        if count is not None and count > chunk_size:
            if fallback is None:
                fallback = TokenChunker(
                    tokenizer=tokenizer, chunk_size=chunk_size, chunk_overlap=0)
            logger.debug(
                "chunk_markdown: um trecho de %s excedeu o teto de %s e foi "
                "recortado por janela fixa — o texto não tinha limite natural "
                "abaixo do teto.", count, chunk_size,
            )
            pieces = [
                (getattr(p, "text", "") or "",
                 start + (getattr(p, "start_index", 0) or 0),
                 getattr(p, "token_count", None))
                for p in fallback.chunk(body)
            ]
        else:
            pieces = [(body, start, count)]
        for piece_text, piece_start, piece_count in pieces:
            if not piece_text.strip():
                # Um trecho só de espaço em branco não é conhecimento, e no
                # índice ele é uma vaga do top-k gasta com nada.
                continue
            out.append({
                "text": piece_text,
                "start_char": piece_start,
                "end_char": piece_start + len(piece_text),
                "token_count": piece_count if counts_tokens else None,
            })
    return out


async def ingest_knowledge_impl(
    live: Any,
    *,
    collection: str,
    source_sha256: str,
    text: str,
    scope: str | None = None,
    tenant: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_CHARS,
    min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS,
    tokenizer: str = CHARACTER_TOKENIZER,
    max_chunks: int | None = None,
    prune: bool = True,
    index: bool = True,
    now: str | None = None,
) -> dict[str, Any]:
    """Ingerir um artefato JÁ EXTRAÍDO numa coleção consultável. A porta da cola.

    ``Markdown → trechos → instâncias de KnowledgeChunk → backfill_index``, que
    é o pedaço do meio que faltava: o ``SourceArtifact`` guardava o anexo, o
    índice indexava instâncias, e nada ligava um ao outro.

    Bytes e extração NÃO passam por aqui — ver a fronteira no topo do módulo.
    O chamador (o host) resolve o ``uri``, converte para Markdown e passa o
    texto com o ``source_sha256`` do artefato que já registrou.

    ## ⚠️ O truncamento de 200k NÃO é herdado, e isto é uma decisão

    O host trunca o anexo de CONVERSA em ``MAX_EXTRACTED_CHARS = 200_000`` e
    marca o corte. Aquele limite responde a *"quanto cabe no contexto de um
    turno"*, e é a pergunta certa lá. Uma base de conhecimento faz a pergunta
    OPOSTA: ela existe justamente para que o tamanho do documento pare de ser
    problema de contexto — o modelo lê os trechos recuperados, nunca o arquivo
    inteiro. Herdar o teto perderia o FIM de todo documento longo em silêncio,
    e um índice que não sabe que está incompleto responde com a mesma
    confiança sobre o que tem e sobre o que perdeu.

    Então **não há teto por padrão** (``max_chunks=None``). Um chamador que
    precise de um pode declará-lo, e aí o corte é REPORTADO — ``truncated``,
    ``chunks_dropped`` e ``chars_dropped`` no resultado — nunca calado.

    ## Re-ingestão: o que se sobrescreve, o que se poda, e o que fica

    ``chunk_name`` é determinístico, então re-ingerir o MESMO arquivo com o
    MESMO corte reescreve as mesmas instâncias (e o índice pula o que não mudou,
    por ``text_hash``). O buraco está no corte DIFERENTE — outro ``chunk_size``,
    outra versão do ``chonkie`` — que produz menos trechos: os ordinais que
    sobravam ficariam no store e no índice, e voltariam numa busca como texto
    antigo do mesmo arquivo, sem nada dizendo que são de uma versão morta.

    Por isso ``prune=True`` (padrão): ao final, tudo que existe sob
    :func:`source_prefix` e NÃO está na leva nova é removido do store e do
    índice. Duas notas sobre isso:

    * ``KnowledgeChunk`` declara ``record.append-only``, que é uma regra sobre
      a FERRAMENTA GENÉRICA (*"never deletable through a generic tool, with the
      purpose-built path left open"* — ``delete_refusal``). Esta porta é o
      caminho purpose-built, no mesmo desenho de ``forget`` para o Engram: ela
      chama ``kernel.delete_instance`` diretamente, e a ferramenta genérica
      continua recusando.
    * ⚠️ O que a poda NÃO alcança, dito: trocar o NOME DA COLEÇÃO deixa os
      trechos antigos onde estavam. É indistinguível, daqui, de uma segunda
      coleção legítima do mesmo arquivo — e apagar por adivinhação seria pior
      que deixar. Renomear coleção é operação de quem sabe o que quis.

    ## Custo

    ZERO em chamada paga: o embedder do piso é ONNX local (``dna-sdk[embed-onnx]``),
    e nenhum caminho desta porta chama serviço remoto. Se um dia um embedder
    remoto for o registrado, o custo passa a ser POR UPLOAD, e isso é decisão de
    quem opera — não desta porta, que só usa o provider já registrado no kernel.

    Devolve ``{scope, collection, source_sha256, source_uri, source_filename,
    chunks_written, chunk_names, pruned, indexed, truncated, chunks_dropped,
    chars_dropped}``.
    """
    from dna.application.instances import write_instance_impl
    from dna.application.runtime import artifact_name
    from dna.application.sdlc import now_iso
    from dna.memory.verbs import backfill_index

    collection = (collection or "").strip()
    if not COLLECTION_RE.match(collection):
        raise ValueError(
            f"collection {collection!r} não é um nome de coleção: minúsculas, "
            f"dígitos e hífen, começando por letra ou dígito, até 63 caracteres "
            f"({COLLECTION_RE.pattern}). O nome da coleção ABRE o nome de cada "
            f"trecho, então ele é identidade — e um caractere fora deste "
            f"alfabeto faria o prefixo de uma coleção alcançar outra."
        )
    digest = (source_sha256 or "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError(
            f"source_sha256 {source_sha256!r} não é um sha256 hex de 64 "
            f"caracteres. Ele é o endereço de conteúdo dos BYTES ORIGINAIS (o "
            f"mesmo do SourceArtifact), nunca um hash do Markdown extraído — "
            f"esse último parece o mesmo campo e nunca confere."
        )
    if not isinstance(text, str):
        raise TypeError(
            f"text deve ser o Markdown já extraído (str), veio "
            f"{type(text).__name__}. Bytes não entram nesta porta — ver a "
            f"fronteira no topo de dna.application.knowledge."
        )

    sc = scope or live.default_scope(tenant)
    stamp = now or now_iso()

    # A PROCEDÊNCIA vem do artefato, não do chamador. `uri` e `filename` são o
    # que a citação MOSTRA para uma pessoa; aceitá-los como argumento deixaria
    # a citação dizer o que quem chamou quisesse, sobre bytes que ele nem
    # precisa ter. Aqui eles são LIDOS da instância que registrou o upload — e
    # a leitura é, de quebra, a prova de que o artefato citado existe.
    art = await live.kernel.get_instance(
        sc, "SourceArtifact", artifact_name(digest), tenant=tenant)
    if not isinstance(art, dict):
        raise ValueError(
            f"nenhum SourceArtifact {digest!r} registrado no scope {sc!r}"
            + (f" sob o workspace {tenant!r}" if tenant else "")
            + " — registre o artefato primeiro (POST /v1/artifacts / "
            "register_artifact_impl) e só então ingira a partir dele. A "
            "citação de um trecho tem de apontar para um original que existe."
        )
    art_spec = art.get("spec") or {}
    source_uri = art_spec.get("uri")
    source_filename = art_spec.get("filename")

    pieces = chunk_markdown(
        text, chunk_size=chunk_size, min_chunk_chars=min_chunk_chars,
        tokenizer=tokenizer,
    )
    truncated = False
    chunks_dropped = 0
    chars_dropped = 0
    if max_chunks is not None and len(pieces) > max_chunks:
        dropped = pieces[max_chunks:]
        pieces = pieces[:max_chunks]
        truncated = True
        chunks_dropped = len(dropped)
        chars_dropped = sum(len(p["text"]) for p in dropped)
        logger.warning(
            "ingest_knowledge: %s trecho(s) (%s caracteres) do arquivo %s NÃO "
            "foram ingeridos — max_chunks=%s. A base ficou incompleta para "
            "este documento, e a busca não tem como saber disso.",
            chunks_dropped, chars_dropped, digest[:12], max_chunks,
        )

    written: list[str] = []
    for ordinal, piece in enumerate(pieces):
        name = chunk_name(collection, digest, ordinal)
        await write_instance_impl(
            live,
            kind=KNOWLEDGE_CHUNK_KIND,
            name=name,
            # merge=False: um trecho é INTEIRAMENTE derivado. Mesclar deixaria
            # campos de uma ingestão anterior (outro offset, outro token_count)
            # sobreviverem sob um texto novo, e a citação apontaria para um
            # recorte que não existe mais.
            merge=False,
            spec={
                "text": piece["text"],
                "collection": collection,
                "source_sha256": digest,
                "ordinal": ordinal,
                "source_uri": source_uri,
                "source_filename": source_filename,
                "start_char": piece["start_char"],
                "end_char": piece["end_char"],
                "token_count": piece["token_count"],
                "extracted_at": stamp,
            },
            scope=sc,
            tenant=tenant,
            # ⛔ `source_sha256=` do write genérico NÃO é passado de propósito.
            # Ele apenda a instância ao `derived_refs` do artefato — uma
            # leitura-modificação-escrita do MESMO artefato por trecho, ou seja
            # O(n²) sobre uma lista que cresce, para instalar uma aresta que
            # este Kind JÁ TEM: `source_sha256` é relação declarada com
            # `by: sha256`, e ela resolve (foi o ponto da metade de leitura).
        )
        written.append(name)

    pruned: list[str] = []
    if prune:
        pruned = await _prune_stale_chunks(
            live, scope=sc, tenant=tenant, prefix=source_prefix(collection, digest),
            keep=set(written),
        )

    indexed = 0
    if index:
        indexed = int(await backfill_index(
            live.kernel, sc, kinds=[KNOWLEDGE_CHUNK_KIND], tenant=tenant))

    return {
        "scope": sc,
        "collection": collection,
        "source_sha256": digest,
        "source_uri": source_uri,
        "source_filename": source_filename,
        "chunks_written": len(written),
        "chunk_names": written,
        "pruned": pruned,
        "indexed": indexed,
        "truncated": truncated,
        "chunks_dropped": chunks_dropped,
        "chars_dropped": chars_dropped,
    }


async def _prune_stale_chunks(
    live: Any, *, scope: str, tenant: str | None, prefix: str, keep: set[str],
) -> list[str]:
    """Remover do store E DO ÍNDICE os trechos de ``prefix`` que a leva nova não
    escreveu. Devolve os nomes removidos, em ordem.

    Os dois lados importam e o segundo é o que morde: ``backfill_index`` só
    INDEXA — ele nunca remove. Uma instância apagada cujo registro ficou no
    índice continua sendo devolvida pela busca (a porta de leitura carrega o
    spec de cada hit e descarta o que não lê, então o sintoma não é texto
    velho: é um top-k que encolhe sem dizer por quê). Por isso a poda fala com
    o provider diretamente, pelo mesmo ``delete`` que a suíte de conformidade
    do ``RecordSearchProvider`` já exercita.
    """
    from dna.memory.verbs import _provider

    stale: list[str] = []
    async for raw in live.kernel.query(scope, KNOWLEDGE_CHUNK_KIND, tenant=tenant):
        name = (raw.get("metadata") or {}).get("name") or raw.get("name")
        if name and name.startswith(prefix) and name not in keep:
            stale.append(name)
    if not stale:
        return []
    stale.sort()
    for name in stale:
        await live.kernel.delete_instance(
            scope, KNOWLEDGE_CHUNK_KIND, name, tenant=tenant, invalidate_mode="doc")
    prov = _provider(live.kernel)
    if prov is not None:
        try:
            await prov.delete([
                {"scope": scope, "kind": KNOWLEDGE_CHUNK_KIND, "name": name,
                 "tenant": tenant or ""}
                for name in stale
            ])
        except Exception as exc:  # noqa: BLE001
            # Fail-soft no ÍNDICE, nunca no store: a instância já foi removida,
            # que é o fato. Um registro órfão no índice é recuperável (a próxima
            # poda ou um reindex o alcança) e é RUIDOSO aqui de propósito.
            logger.warning(
                "ingest_knowledge: %s trecho(s) removidos do store mas NÃO do "
                "índice (%s) — a busca pode devolver menos hits que o k pedido "
                "até o índice ser varrido de novo.", len(stale), exc,
            )
    return stale
