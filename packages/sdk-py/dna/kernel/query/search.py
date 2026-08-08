"""SearchEngine — the record ``search`` facade + lexical fallback extracted from
the Kernel god-object (``s-kernel-decomp-f5-satellites``).

Two-planes F2 (D2): a registered ``RecordSearchProvider`` gives real semantic
search (pgvector/RRF, ``degraded=False``); with no provider — or on any provider
error — the engine degrades to an HONEST lexical token-match scan over
``query()`` (``degraded=True``), never similarity. Search is a READ: it degrades,
it never raises.

Behavior-preserving extraction: ``search`` + ``_lexical_search`` move here
verbatim; the kernel keeps both as thin delegators (the public ``search`` is
called from CLI/Studio/agent routes). The provider + its failure-warning damper
(``_search_provider`` / ``_search_provider_warned``) stay KERNEL state — the
kernel keeps ``record_search_provider`` as the registration entry point, and the
engine reads/writes the damper through the host — so the exact ``with_tenant``
sharing semantics are preserved (``_search_provider`` shared by reference,
``_search_provider_warned`` copied by value per shallow copy). A STATELESS
back-ref collaborator that reads ``k.tenant`` (effective-tenant auto-stamp), so
``with_tenant`` rebinds it to the copy.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from dna.kernel.collaborator_ports import SearchEngineHost

logger = logging.getLogger(__name__)


class SearchEngine:
    """The kernel's record-search surface. One per kernel; back-ref to it."""

    def __init__(self, kernel: "SearchEngineHost") -> None:
        self._k = kernel

    async def search(
        self, scope: str, query_text: str, *,
        kind: str | None = None, k: int = 10, tenant: str | None = None,
        min_similarity: float | None = None, name_prefix: str | None = None,
    ) -> dict[str, Any]:
        """Public record search (F2 D2). Provider registered → semantic
        (pgvector/RRF, degraded=False). No provider OR provider error →
        lexical token-match fallback over query() (degraded=True; requires
        ``kind`` — without it returns empty degraded). Tenant binding igual
        ao query(): kwarg > ``Kernel.tenant``.

        ``min_similarity`` (i-103) is the CALLER's relevance floor over the
        dense plane's raw cosine: hits scoring below it are dropped and counted
        in ``floored_out``. ``None`` — the default, and the only value the SDK
        itself ever passes — applies no floor.

        ⚠️ There is deliberately NO shipped default, and that is a measurement
        rather than a decision left open: on this deployment's own corpus,
        unrelated queries reach 0.53 while genuine matches start at 0.35, so no
        cutoff separates them (and neither corpus z-score nor top-1 margin does
        either — both overlap 12/12). See :mod:`dna.kernel.query.relevance`. The
        parameter exists because a caller with context may still want one; a
        constant here would be the engine pretending to a judgment it cannot
        make.

        The floor is applied HERE rather than inside each provider on purpose:
        it is policy over the score, not part of producing it, so a third-party
        ``RecordSearchProvider`` needs no new kwarg and cannot get it wrong. It
        also never applies to the lexical fallback — a degraded answer is
        already the honest "we could not tell", and filtering it further would
        shrink a blind spot into a claim.
        """
        from dna.kernel.query.relevance import apply_similarity_floor

        host = self._k
        effective_tenant = tenant if tenant is not None else (host.tenant or "")
        prov = host._search_provider
        if prov is not None:
            try:
                # ⚠️ `name_prefix` só é PASSADO quando existe, e isso não é
                # microtuning. O kwarg é novo: um `RecordSearchProvider` de
                # terceiro escrito contra o protocolo anterior levanta
                # `TypeError` ao recebê-lo — e o `except` logo abaixo o captura,
                # degradando TODA busca para o plano lexical, com
                # `degraded=True` e nenhuma pista de que a causa foi assinatura.
                # Passar só quando há prefixo mantém o provider antigo intacto
                # no caso comum e deixa a incompatibilidade aparecer só onde ela
                # é real. (Medido: foi exatamente assim que
                # `test_search_routes_to_registered_provider` caiu.)
                narrowing = {"name_prefix": name_prefix} if name_prefix else {}
                hits = await prov.search(
                    scope=scope, query_text=query_text, kind=kind,
                    k=k, tenant=effective_tenant or "",
                    **narrowing,
                )
                host._search_provider_warned = False  # episode over
                kept, dropped, unscored = apply_similarity_floor(
                    hits, min_similarity,
                )
                return {
                    "hits": kept, "degraded": False,
                    "floored_out": dropped,
                    "floor_unscored": unscored,
                }
            except Exception:  # noqa: BLE001 — search é leitura; degrada, nunca quebra
                # Damped: full traceback ONCE per failure episode (a broken
                # provider would otherwise spam a warning per request);
                # repeats at debug until a successful call resets.
                if not host._search_provider_warned:
                    host._search_provider_warned = True
                    logger.warning(
                        "[kernel] search provider failed; lexical fallback "
                        "(further failures logged at debug until recovery)",
                        exc_info=True,
                    )
                else:
                    logger.debug(
                        "[kernel] search provider still failing; lexical fallback",
                        exc_info=True,
                    )
        return {
            # ⭐ O prefixo ATRAVESSA para o plano degradado, e essa é a linha
            # que impede um vazamento entre coleções. O piso de relevância
            # deliberadamente NÃO atravessa (ver a docstring: filtrar um plano
            # cego encolheria um ponto cego em afirmação) — mas `name_prefix`
            # não é política sobre o score, é RECORTE do universo. Um fallback
            # que ignorasse o recorte devolveria trechos de OUTRAS coleções
            # marcados apenas como `degraded`, e "degradado" leria como "menos
            # preciso" quando na verdade seria "de outro corpus".
            "hits": await self._lexical_search(
                scope, query_text, kind=kind, k=k,
                tenant=effective_tenant or None, name_prefix=name_prefix,
            ),
            "degraded": True,
            # Present with the same keys on BOTH branches so a caller never has
            # to test for their existence — the floor simply did not run here
            # (see the docstring: a degraded answer is already "we cannot tell",
            # and filtering it would turn a blind spot into a claim).
            "floored_out": 0,
            "floor_unscored": 0,
        }

    async def _lexical_search(
        self, scope: str, query_text: str, *,
        kind: str | None = None, k: int = 10, tenant: str | None = None,
        name_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        """Degraded fallback for ``search()`` — honest DEV lexical scan,
        NOT similarity (two-planes F2).

        Matches by token-set over the STRING VALUES of each doc's spec
        (recursive walk; never substring over serialized JSON —
        ``json.dumps`` Py and ``JSON.stringify`` TS diverge in separators
        and would break parity). Requires ``kind`` (records are scanned
        per-kind); without it there is nothing safe to scan → empty.
        Score = query tokens present ÷ total query tokens.
        """
        if not kind:
            return []
        q_tokens = query_text.lower().split()
        if not q_tokens:
            return []

        def _spec_tokens(node: Any, out: set[str]) -> None:
            if isinstance(node, str):
                out.update(node.lower().split())
            elif isinstance(node, dict):
                for v in node.values():
                    _spec_tokens(v, out)
            elif isinstance(node, (list, tuple)):
                for v in node:
                    _spec_tokens(v, out)

        hits: list[dict[str, Any]] = []
        async for row in self._k.query(scope, kind, tenant=tenant, limit=500):
            tokens: set[str] = set()
            _spec_tokens(row.get("spec") or {}, tokens)
            name = (row.get("metadata") or {}).get("name") or row.get("name") or ""
            # ⚠️ O recorte vem ANTES do escore, não depois: `limit=500` é um
            # orçamento de varredura, e filtrar o que já foi escolhido deixa uma
            # coleção volumosa consumir o orçamento inteiro e expulsar as
            # outras — a mesma armadilha que o plano denso mede em
            # `RecordSearchProvider`. Aqui a varredura é por Kind e o corte é em
            # memória, então o orçamento continua sendo gasto com o que foi
            # descartado; isso é uma LIMITAÇÃO do plano degradado, e está dita
            # em vez de escondida.
            if name_prefix and not name.startswith(name_prefix):
                continue
            score = sum(1 for t in q_tokens if t in tokens) / len(q_tokens)
            if score > 0:
                hits.append(
                    {"scope": scope, "kind": kind, "name": name, "score": score},
                )
        hits.sort(key=lambda h: -h["score"])
        return hits[:k]
