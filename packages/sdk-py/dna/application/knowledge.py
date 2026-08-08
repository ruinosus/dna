"""A base de conhecimento: a COLA entre um arquivo subido e uma resposta citada.

## O que este módulo é, e sobretudo o que ele NÃO é

Não é um motor de RAG. As peças todas já existiam e já eram nossas — o
``SourceArtifact`` guarda o original, o ``EmbeddingPort``/ONNX embute de graça,
``dna_search_docs_*`` indexa, ``search_instances_impl`` entrega um envelope
honesto. Faltava a cola, e é só ela que mora aqui:

    arquivo → (markitdown) → Markdown → (chonkie) → trechos
            → instâncias de ``KnowledgeChunk`` → backfill_index
            → dna_search_docs_384 → busca → hits COM SCORE E FONTE

O corte em trechos e a extração vivem na camada de hospedagem (é lá que os
bytes e o blob estão). O que está aqui é o Kind, a busca e a CITAÇÃO.

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
from typing import Any

from dna.application.instances import search_instances_impl

logger = logging.getLogger(__name__)

__all__ = [
    "KNOWLEDGE_CHUNK_KIND",
    "chunk_name",
    "collection_prefix",
    "search_knowledge_impl",
]

#: O Kind cujas instâncias são trechos. Uma coleção é um PREFIXO do nome deles.
KNOWLEDGE_CHUNK_KIND = "KnowledgeChunk"


def collection_prefix(collection: str) -> str:
    """O prefixo de nome que ISOLA uma coleção dentro do índice.

    Uma coleção não é um ``scope`` (o scope é função 1:1 do workspace e a porta
    NEGA qualquer outro — ``LiveDna.scope_is_bound``), não é uma coluna (seria
    migration nova sobre a 0013, que é de hoje): é um prefixo do NOME da
    instância, filtrado no SQL pelo índice único que já existe. A barra final é
    obrigatória — sem ela ``handbook`` alcançaria ``handbook-2024``."""
    return f"{collection}/"


def chunk_name(collection: str, sha256: str, ordinal: int) -> str:
    """O nome determinístico de um trecho: ``<collection>/<sha12>/<ordinal>``.

    Determinístico de propósito: re-ingerir o MESMO arquivo na MESMA coleção
    reescreve as mesmas instâncias em vez de duplicar o corpus, e o índice pula
    o que não mudou (idempotência por ``text_hash``). O ordinal é zero-padded
    para que a ordem lexicográfica do nome seja a ordem de leitura."""
    return f"{collection}/{sha256[:12]}/{ordinal:05d}"


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
