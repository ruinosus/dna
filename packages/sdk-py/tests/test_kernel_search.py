"""F2 D2: kernel.search — provider plugável + fallback léxico degraded.

Two-planes F2 (spec D2): o kernel core NÃO ganha dependência de LLM —
`search()` roteia pro RecordSearchProvider registrado (PG: pgvector/RRF
em harness-shared, wired no boot dos apps) e, sem provider OU com
provider quebrado, degrada pra um scan léxico in-memory honesto
(``degraded: True`` explícito — nunca finge similaridade).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dna.kernel import Kernel


def _doc(kind: str, name: str, spec: dict) -> dict:
    return {"kind": kind, "metadata": {"name": name}, "spec": spec}


def _wire(docs: list[dict] | None = None, tenant_binding: str | None = None):
    """Kernel com fake source cujo query() rende ``docs`` do kind pedido.

    Mesmo padrão de test_kernel_query.py (SdlcExtension carregada pra
    Story ser non-inheritable e a query ficar no scope pedido).
    """
    docs = docs or []

    async def _fake_query(scope, kind, **kwargs):
        _fake_query.last_args = (scope, kind)
        _fake_query.last_kwargs = kwargs
        for d in docs:
            if d.get("kind") == kind:
                yield d
    _fake_query.last_args = None
    _fake_query.last_kwargs = {}

    src = MagicMock()
    src.query = _fake_query

    k = Kernel()
    from dna.extensions.sdlc import SdlcExtension
    k.load(SdlcExtension())
    if tenant_binding:
        k.tenant = tenant_binding
    k._source = src  # type: ignore[assignment]
    return k, src


@pytest.mark.asyncio
async def test_search_routes_to_registered_provider():
    k, _src = _wire()
    calls = []

    class _Prov:
        async def search(self, *, scope, query_text, kind=None, k=10, tenant=""):
            calls.append((scope, query_text, kind, k, tenant))
            return [{"scope": scope, "kind": "Story", "name": "s-hit", "score": 0.9}]

    k.record_search_provider(_Prov())
    res = await k.search("sc", "tema x", kind="Story", k=5)
    assert res["degraded"] is False
    assert [h["name"] for h in res["hits"]] == ["s-hit"]
    assert calls == [("sc", "tema x", "Story", 5, "")]


@pytest.mark.asyncio
async def test_search_without_provider_falls_back_lexical_degraded():
    k, _src = _wire(docs=[
        _doc("Story", "s-match", {"title": "cache invalidation storm"}),
        _doc("Story", "s-miss", {"title": "totally unrelated"}),
    ])
    res = await k.search("sc", "invalidation cache", kind="Story", k=5)
    assert res["degraded"] is True
    assert [h["name"] for h in res["hits"]] == ["s-match"]
    assert res["hits"][0]["score"] > 0


@pytest.mark.asyncio
async def test_search_fallback_without_kind_returns_empty_degraded():
    k, _src = _wire()
    res = await k.search("sc", "qualquer coisa")
    assert res == {"hits": [], "degraded": True}


@pytest.mark.asyncio
async def test_search_provider_error_falls_back_lexical():
    k, _src = _wire(docs=[_doc("Story", "s-1", {"title": "abc"})])

    class _Boom:
        async def search(self, **kw):
            raise RuntimeError("gateway 403")

    k.record_search_provider(_Boom())
    res = await k.search("sc", "abc", kind="Story")
    assert res["degraded"] is True  # provider falhou → léxico, nunca crash
    assert [h["name"] for h in res["hits"]] == ["s-1"]


@pytest.mark.asyncio
async def test_search_provider_failure_warns_once_then_debug(caplog):
    """F2 T5 review carry-over: o warning de provider quebrado é DAMPED —
    traceback completo UMA vez por episódio de falha, repetições em debug;
    sucesso do provider OU re-registro resetam o damper."""
    import logging

    k, _src = _wire(docs=[_doc("Story", "s-1", {"title": "abc"})])

    class _Flaky:
        fail = True

        async def search(self, **kw):
            if self.fail:
                raise RuntimeError("gateway 403")
            return []

    prov = _Flaky()
    k.record_search_provider(prov)
    logger_name = "dna.kernel"

    def _recs(level):
        return [
            r for r in caplog.records
            if r.levelno == level and "search provider" in r.getMessage()
        ]

    with caplog.at_level(logging.DEBUG, logger=logger_name):
        await k.search("sc", "abc", kind="Story")
        await k.search("sc", "abc", kind="Story")
        await k.search("sc", "abc", kind="Story")
    assert len(_recs(logging.WARNING)) == 1  # só a primeira falha
    assert len(_recs(logging.DEBUG)) == 2    # repetições rebaixadas
    assert _recs(logging.WARNING)[0].exc_info  # traceback preservado

    # Sucesso fecha o episódio → próxima falha volta a WARNING.
    caplog.clear()
    prov.fail = False
    with caplog.at_level(logging.DEBUG, logger=logger_name):
        res = await k.search("sc", "abc", kind="Story")
        assert res["degraded"] is False
        prov.fail = True
        await k.search("sc", "abc", kind="Story")
    assert len(_recs(logging.WARNING)) == 1

    # Re-registro também reseta o damper.
    assert k._search_provider_warned is True
    k.record_search_provider(prov)
    assert k._search_provider_warned is False


@pytest.mark.asyncio
async def test_lexical_fallback_queries_source_with_limit_500_and_bound_tenant():
    """F2 T5 review carry-over: o scan léxico é bounded (limit=500) e
    propaga o tenant binding do kernel até o source.query."""
    k, src = _wire(
        docs=[_doc("Story", "s-1", {"title": "abc"})],
        tenant_binding="globex",
    )
    res = await k.search("sc", "abc", kind="Story")
    assert res["degraded"] is True
    assert src.query.last_kwargs["limit"] == 500
    assert src.query.last_kwargs["tenant"] == "globex"


@pytest.mark.asyncio
async def test_search_tenant_binding_kernel_tenant_wins_when_kwarg_absent():
    """Tenant binding igual ao query(): kwarg > Kernel.tenant."""
    k, _src = _wire(tenant_binding="globex")
    seen = []

    class _Prov:
        async def search(self, *, scope, query_text, kind=None, k=10, tenant=""):
            seen.append(tenant)
            return []

    k.record_search_provider(_Prov())
    await k.search("sc", "x", kind="Story")
    await k.search("sc", "x", kind="Story", tenant="acme")
    assert seen == ["globex", "acme"]


@pytest.mark.asyncio
async def test_search_lexical_shape_score_order_and_limit():
    """Fallback léxico: token-set dos VALORES string do spec (recursivo),
    score = tokens da query presentes ÷ nº tokens, ordena DESC, corta em k,
    shape {scope, kind, name, score} (name via metadata)."""
    k, _src = _wire(docs=[
        _doc("Story", "s-full", {"title": "alpha beta", "nested": {"x": ["gamma"]}}),
        _doc("Story", "s-half", {"title": "alpha only here"}),
        _doc("Story", "s-zero", {"title": "nothing relevant"}),
    ])
    res = await k.search("sc", "alpha beta", kind="Story", k=1)
    assert res["degraded"] is True
    assert res["hits"] == [
        {"scope": "sc", "kind": "Story", "name": "s-full", "score": 1.0},
    ]
    # sem limit: ambos com score>0, ordenados por score DESC
    res2 = await k.search("sc", "alpha beta", kind="Story", k=10)
    assert [h["name"] for h in res2["hits"]] == ["s-full", "s-half"]
    assert res2["hits"][1]["score"] == 0.5
