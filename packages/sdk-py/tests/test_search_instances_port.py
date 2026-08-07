"""``s-porta-de-busca`` — the door onto a search plane that was already built.

The defect was *capacidade existe, porta não*: ``adapters/search/{pgvector,
sqlite_vec,rrf}.py`` and ``adapters/embedding/onnx.py`` have been in the tree and
in the air, ``kernel.search()`` has routed to them since two-planes F2 — and the
only callers were the memory verbs (``recall``) and two CLI commands. An agent
asking *"does something like this already exist?"* over an arbitrary Kind had
``list_instances``: ENUMERATION, which answers at six instances and does not at
six hundred.

So the thing under test here is a DOOR, and the two ways a door onto an existing
engine goes wrong:

1. **it re-implements the engine.** Pinned by
   :func:`test_the_door_imports_nothing_from_the_search_adapters` and
   :func:`test_the_hits_come_back_in_the_engines_own_ranking` — no fusion, no
   re-ranking, no second RRF.
2. **it lies when the engine is not there.** An embedding-less deployment cannot
   run the dense plane, and ``[]`` from a search that did not fully run is
   indistinguishable from ``[]`` from a search that did — the `indisponível ≠
   zero fabricado` failure. The whole first section below exists to prove the two
   empties are DIFFERENT VALUES, not merely differently documented.

Plus the boundary that any door over stored content must hold: one tenant's
search never reaches another tenant's instances (§3, against the real sqlite-vec
provider, both tenants written and indexed for real).
"""
from __future__ import annotations

import ast
import inspect

import pytest

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application import instances as D
from dna.application.live import LiveDna
from dna.kernel import Kernel

_SCOPE = "demo"

#: Tenanted, record-plane, and a two-field spec — so the tenant boundary in §3
#: is exercised by the SAME Kind the rest of the file uses, instead of by a
#: second fixture that could drift from it. Being TENANTED is why every write
#: below names a tenant: the kernel refuses a tenant-less write on such a Kind,
#: which is the boundary being tested arriving one layer earlier.
_KIND = "Project"

#: The tenant everything in §1–§2 runs as. §3 introduces a second one.
_T = "acme"


def _live(tmp_path) -> LiveDna:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    src = FilesystemWritableSource(base_dir=str(tmp_path / "src"))
    kernel = Kernel.auto(source=src)
    return LiveDna(base_scope=_SCOPE, kernel=kernel, provider=None)


async def _write(live: LiveDna, name: str, text: str, *, tenant: str = _T):
    """One instance whose searchable text is ``text``. The words matter: the
    degraded plane is a TOKEN-set match over the spec's string values, so a
    fixture written as one hyphenated slug would be unfindable by the lexical
    scan and the degraded tests would pass for the wrong reason."""
    return await D.write_instance_impl(
        live, kind=_KIND, name=name, scope=_SCOPE, tenant=tenant,
        spec={"name": text, "slug": name},
    )


class _StubProvider:
    """A ``RecordSearchProvider`` that answers exactly what it is told to.

    Deliberately a stub for §1: what is being pinned there is the DOOR's
    reporting, and a stub is the only way to hold "the semantic plane ran and
    found nothing" fixed while everything else varies. The real engine's own
    behaviour is pinned by ``record_search_conformance_suite`` and, end-to-end
    through this door, by §2 and §3 below — which use the real sqlite-vec
    provider precisely because a stub cannot fail the way a store can.
    """

    def __init__(self, hits=None, boom: bool = False, index_boom: bool = False):
        self._hits = list(hits or [])
        self._boom = boom
        self._index_boom = index_boom
        self.seen_tenants: list[str] = []
        self.indexed: list[dict] = []

    async def index(self, records):
        if self._index_boom:
            raise RuntimeError("index store unreachable")
        self.indexed.extend(records)
        return len(records)

    async def search(self, *, scope, query_text, kind=None, k=10, tenant=""):
        self.seen_tenants.append(tenant)
        if self._boom:
            raise RuntimeError("gateway 403")
        return [dict(h) for h in self._hits]


# ── 1. the two empties are different answers ────────────────────────────────


@pytest.mark.asyncio
async def test_the_two_empties_are_different_answers(tmp_path):
    """⭐ The story's reason to exist.

    Same Kind, same scope, same query, same empty ``hits`` — and the caller must
    be able to tell "I searched and there is nothing like this" from "I could not
    search". The first licenses a creator to go ahead and author; the second does
    not, and reporting it as the first is how a workspace ends up with the same
    Kind declared twice.

    The assertion is on VALUES that differ, not on a docstring that explains: a
    caller reading only ``hits`` gets the same thing from both, so everything
    that separates them has to be in the payload."""
    live = _live(tmp_path)
    await _write(live, "alpha", "alpha project")

    live.kernel.record_search_provider(_StubProvider(hits=[]))
    searched = await D.search_instances_impl(
        live, kind=_KIND, query="zzz nothing like this", scope=_SCOPE, tenant=_T)

    live.kernel.record_search_provider(None)
    could_not = await D.search_instances_impl(
        live, kind=_KIND, query="zzz nothing like this", scope=_SCOPE, tenant=_T)

    # Both are empty. That is the premise, not the finding.
    assert searched["hits"] == [] and could_not["hits"] == []
    assert searched["count"] == could_not["count"] == 0

    # …and they are not the same answer.
    assert searched != could_not

    # The one that MAY be read as "nothing similar exists".
    assert searched["mode"] == "hybrid"
    assert searched["degraded"] is False
    assert searched["degraded_reason"] is None
    assert searched["notice"] is None

    # The one that may NOT — and that says so in words, in the payload, because
    # `degraded: true` beside `hits: []` is read as an answer by every caller
    # that does not already know better.
    assert could_not["mode"] == "lexical"
    assert could_not["degraded"] is True
    assert could_not["degraded_reason"] == D.SEARCH_NO_PROVIDER
    assert could_not["notice"]
    assert "NOT evidence that nothing similar exists" in could_not["notice"]
    assert "no embedding/search provider" in could_not["notice"].lower()


@pytest.mark.asyncio
async def test_a_broken_provider_is_named_apart_from_an_absent_one(tmp_path):
    """``kernel.search`` collapses both into one ``degraded`` flag — on purpose,
    it is a read and it never raises. But the two have different remedies
    (configure a provider vs. read the logs), and a door that reports one word
    for both sends its caller to the wrong place. The provider is still in hand
    at this layer, so the split costs one comparison."""
    live = _live(tmp_path)
    await _write(live, "alpha", "alpha project")

    live.kernel.record_search_provider(_StubProvider(boom=True))
    out = await D.search_instances_impl(
        live, kind=_KIND, query="alpha", scope=_SCOPE, tenant=_T)

    assert out["degraded"] is True
    assert out["degraded_reason"] == D.SEARCH_PROVIDER_ERROR
    assert out["degraded_reason"] != D.SEARCH_NO_PROVIDER
    assert "FAILED on this call" in out["notice"]
    # It still ANSWERS — the lexical fallback ran and found the instance whose
    # text repeats the query's token. Degrading is not refusing.
    assert [h["name"] for h in out["hits"]] == ["alpha"]
    assert out["mode"] == "lexical"


@pytest.mark.asyncio
async def test_a_stale_index_degrades_even_though_the_provider_answered(tmp_path):
    """The third blind spot, and the quietest: the provider is healthy and the
    dense plane runs, but over an index that could not be refreshed — so the
    instance the caller wrote a moment ago is invisible to it. ``recall`` learned
    this one the hard way (a confident, non-degraded answer that could not
    contain the thing just stored); this door is born with it."""
    live = _live(tmp_path)
    await _write(live, "alpha", "alpha project")

    live.kernel.record_search_provider(_StubProvider(hits=[], index_boom=True))
    out = await D.search_instances_impl(
        live, kind=_KIND, query="alpha", scope=_SCOPE, tenant=_T)

    # The search itself was NOT degraded — the semantic plane ran.
    assert out["mode"] == "hybrid"
    # …and the answer is degraded anyway, because it is.
    assert out["degraded"] is True
    assert out["degraded_reason"] == D.SEARCH_INDEX_STALE
    assert out["index_refreshed"] is False
    assert "index store unreachable" in out["index_error"]
    assert "NOT read-your-writes" in out["notice"]


@pytest.mark.asyncio
async def test_every_degradation_carries_a_notice_that_says_what_was_lost(tmp_path):
    """A reason code nobody has the table for is a reason code nobody reads.
    Every value the door can put in ``degraded_reason`` must come with prose —
    derived from the mapping, so a reason added later without one fails here."""
    assert set(D._SEARCH_NOTICE) == {
        D.SEARCH_NO_PROVIDER, D.SEARCH_PROVIDER_ERROR, D.SEARCH_INDEX_STALE,
    }
    for reason, notice in D._SEARCH_NOTICE.items():
        assert len(notice) > 80, reason
        assert "NOT" in notice, f"{reason} does not say what may not be concluded"


# ── 2. the door is a door, not a second search engine ───────────────────────


def test_the_door_imports_nothing_from_the_search_adapters():
    """``dna.application.instances`` must not reach into ``dna.adapters.search``.

    Reimplementing a shipped protocol is banned in this house, and the shape the
    ban takes HERE is precise: the fusion (``rrf.reciprocal_rank_fusion``), the
    dense plane and the lexical plane belong to the adapters, reached only
    through ``kernel.search``. An import from the door into that package is the
    first move of every hand-rolled re-rank, so it is refused at the import, not
    argued about at review.

    Read from the AST rather than from the text: the module NAMES ``rrf`` and
    ``pgvector`` in prose, on purpose (a door should say what is behind it), and
    a grep-shaped guard would have to choose between banning the sentence and
    passing on the import. The AST has no such ambiguity — it sees imports."""
    tree = ast.parse(inspect.getsource(D))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    offenders = {m for m in imported if m.startswith("dna.adapters.search")}
    assert not offenders, (
        f"the search door imports {sorted(offenders)} directly — the fusion / "
        "dense / lexical planes are reached through kernel.search() and nowhere "
        "else, or the next person writes a second RRF here"
    )

    # …and it does not hand-roll fusion under another name. The only arithmetic
    # a door may do on a rank is none.
    body = inspect.getsource(D.search_instances_impl)
    for banned in ("1 / (", "1.0 / (", "sort(", "sorted("):
        assert banned not in body, (
            f"{banned!r} in the search door — ranking belongs to the engine"
        )


@pytest.mark.asyncio
async def test_the_hits_come_back_in_the_engines_own_ranking(tmp_path):
    """No second sort. RRF already ordered these; a door that re-sorts by
    ``score`` would look identical on this fixture and diverge the moment a
    provider ranks by something the score does not fully express."""
    live = _live(tmp_path)
    ranked = [
        {"scope": _SCOPE, "kind": _KIND, "name": "third", "score": 0.9,
         "rank_dense": 3, "rank_lexical": 1},
        {"scope": _SCOPE, "kind": _KIND, "name": "first", "score": 0.1,
         "rank_dense": 1, "rank_lexical": 9},
        {"scope": _SCOPE, "kind": _KIND, "name": "second", "score": 0.5},
    ]
    live.kernel.record_search_provider(_StubProvider(hits=ranked))
    out = await D.search_instances_impl(
        live, kind=_KIND, query="x", scope=_SCOPE, tenant=_T)

    assert [h["name"] for h in out["hits"]] == ["third", "first", "second"]
    # The optional provider extras travel untouched — a caller that wants to see
    # WHICH plane found a hit can.
    assert out["hits"][0]["rank_lexical"] == 1


@pytest.mark.asyncio
async def test_it_searches_through_the_real_engine_and_the_ranks_prove_rrf_ran(tmp_path):
    """End-to-end over the REAL ``SqliteVecRecordSearchProvider`` — dense
    (vec0 KNN over ``kernel.embed``) + lexical (FTS5) fused by the shared
    ``rrf.reciprocal_rank_fusion``.

    ``rank_dense`` / ``rank_lexical`` on a hit are the observable evidence that
    two independently-ranked lists were fused rather than one list returned:
    they are the positions RRF consumed. Embeddings here are the deterministic
    offline fake, so what this pins is that the door reaches the engine and
    relays its shape — the engine's own ranking quality is the conformance
    kit's job."""
    pytest.importorskip("sqlite_vec", reason="search-sqlite extra not installed")
    from dna.adapters.search.sqlite_vec import SqliteVecRecordSearchProvider

    live = _live(tmp_path)
    await _write(live, "cache-invalidation", "cache invalidation storm")
    await _write(live, "billing-portal", "billing portal checkout")

    prov = SqliteVecRecordSearchProvider(live.kernel, db_path=str(tmp_path / "s.db"))
    live.kernel.record_search_provider(prov)
    try:
        out = await D.search_instances_impl(
            live, kind=_KIND, query="cache invalidation", scope=_SCOPE, tenant=_T)
    finally:
        prov.close()

    assert out["mode"] == "hybrid"
    assert out["degraded"] is False
    assert out["degraded_reason"] is None
    # The door refreshed THIS Kind's slice of the index. Without that step the
    # engine would answer confidently out of an index only the memory verbs ever
    # wrote to, and every non-memory Kind would come back empty — a wrong answer
    # wearing `degraded: false`.
    assert out["index_refreshed"] is True
    names = [h["name"] for h in out["hits"]]
    assert "cache-invalidation" in names
    top = next(h for h in out["hits"] if h["name"] == "cache-invalidation")
    assert top["rank_lexical"] == 1, "the lexical plane did not rank the match first"
    assert "rank_dense" in top, "the dense plane did not contribute — nothing was fused"


@pytest.mark.asyncio
async def test_k_is_clamped(tmp_path):
    live = _live(tmp_path)
    prov = _StubProvider(hits=[])
    live.kernel.record_search_provider(prov)
    seen = {}

    async def _spy(scope, query_text, *, kind=None, k=10, tenant=None):
        seen["k"] = k
        return {"hits": [], "degraded": False}

    live.kernel.search = _spy  # type: ignore[method-assign]
    await D.search_instances_impl(
        live, kind=_KIND, query="x", scope=_SCOPE, tenant=_T, k=10_000)
    assert seen["k"] == 100
    await D.search_instances_impl(
        live, kind=_KIND, query="x", scope=_SCOPE, tenant=_T, k=0)
    assert seen["k"] == 1


@pytest.mark.asyncio
async def test_an_unknown_kind_is_refused_not_answered_empty(tmp_path):
    """Same refusal every other generic instance use-case makes. An empty result
    for a Kind that does not exist is the same fabrication in a different coat."""
    live = _live(tmp_path)
    with pytest.raises(D.UnknownKindError):
        await D.search_instances_impl(
            live, kind="Nope", query="x", scope=_SCOPE, tenant=_T)


# ── 3. the tenant boundary ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_tenant_reaches_the_engine_verbatim(tmp_path):
    """The provider's isolation rule is ``row_tenant in ("", tenant)`` — so the
    value this door passes IS the boundary. Dropping it does not fail loudly; it
    widens the search to everybody's overlay and still returns a plausible list."""
    live = _live(tmp_path)
    prov = _StubProvider(hits=[])
    live.kernel.record_search_provider(prov)

    await D.search_instances_impl(
        live, kind=_KIND, query="x", scope=_SCOPE, tenant="acme")
    await D.search_instances_impl(
        live, kind=_KIND, query="x", scope=_SCOPE, tenant="globex")
    assert prov.seen_tenants == ["acme", "globex"]


@pytest.mark.asyncio
async def test_one_tenant_never_finds_another_tenants_instance(tmp_path):
    """Two tenants, both written and both indexed for real, searched with the
    real engine: each finds its own and neither finds the other's.

    Against the REAL provider deliberately — the overlay-shadow filter lives
    inside it, and a stub that answered whatever it was handed would pass this
    test while the door leaked."""
    pytest.importorskip("sqlite_vec", reason="search-sqlite extra not installed")
    from dna.adapters.search.sqlite_vec import SqliteVecRecordSearchProvider

    live = _live(tmp_path)
    await _write(live, "acme-roadmap", "secret roadmap for acme", tenant="acme")
    await _write(live, "globex-roadmap", "secret roadmap for globex", tenant="globex")

    prov = SqliteVecRecordSearchProvider(live.kernel, db_path=str(tmp_path / "t.db"))
    live.kernel.record_search_provider(prov)
    try:
        acme = await D.search_instances_impl(
            live, kind=_KIND, query="secret roadmap", scope=_SCOPE, tenant="acme")
        globex = await D.search_instances_impl(
            live, kind=_KIND, query="secret roadmap", scope=_SCOPE, tenant="globex")
    finally:
        prov.close()

    acme_names = {h["name"] for h in acme["hits"]}
    globex_names = {h["name"] for h in globex["hits"]}
    assert "acme-roadmap" in acme_names
    assert "globex-roadmap" not in acme_names
    assert "globex-roadmap" in globex_names
    assert "acme-roadmap" not in globex_names


@pytest.mark.asyncio
async def test_the_tenant_reaches_the_source_on_the_degraded_path_too(tmp_path):
    """The lexical fallback scans through ``kernel.query`` — a path that has its
    own tenant argument, and therefore its own way to leak. A door tested only
    with a provider registered would never touch it."""
    live = _live(tmp_path)
    await _write(live, "acme-only", "roadmap for acme", tenant="acme")
    await _write(live, "globex-only", "roadmap for globex", tenant="globex")

    acme = await D.search_instances_impl(
        live, kind=_KIND, query="roadmap", scope=_SCOPE, tenant="acme")
    assert acme["degraded"] is True  # no provider — this IS the fallback path
    names = {h["name"] for h in acme["hits"]}
    assert "acme-only" in names
    assert "globex-only" not in names
