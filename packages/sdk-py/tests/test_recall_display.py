"""i-068 — recall hits carry DISPLAY fields + the per-item ``personal`` flag.

The hits were pointers (``{scope,kind,name,score,title?,snippet?}``) — a UI
rendering them had nothing to show (the DNA Cloud console's blank canvas).
``recall`` already loads every hit's spec for the bi-temporal filter + decay
re-score, so the enrichment lives THERE (``dna.memory.verbs``), above the
providers: pgvector, sqlite-vec and the honest lexical fallback all enrich at
one point, and the providers' port contract is untouched.

Proven here on both planes the SDK can exercise offline:

* provider-backed (sqlite-vec + fake embedder) — hybrid/semantic recall;
* lexical fallback (no provider, ``degraded=True``).

Anti-vacuity: every assertion compares the projected value against the exact
spec that was remembered — never mere key presence.
"""
from __future__ import annotations

import pytest

sqlite_vec = pytest.importorskip("sqlite_vec", reason="search-sqlite extra not installed")

from dna.adapters.filesystem.writable import FilesystemWritableSource  # noqa: E402
from dna.adapters.search.sqlite_vec import SqliteVecRecordSearchProvider  # noqa: E402
from dna.kernel import Kernel  # noqa: E402
from dna.memory import recall, remember  # noqa: E402

_REASON = "a concrete reason long enough for the affect validator to accept it in full"

_OID = "oid-display"
_PERSONAL = f"personal:{_OID}"


def _spec(summary: str, *, area: str = "Feature/display", tags: list[str] | None = None) -> dict:
    return {
        "area": area,
        "surface_when": ["feature_touched"],
        "source_refs": ["s-1"],
        "affect": "triumph",
        "affect_reason": _REASON,
        "summary": summary,
        "tags": tags if tags is not None else ["display", "i068"],
        "created_at": "2026-07-20T10:00:00+00:00",
    }


@pytest.fixture
def kernel_with_provider(tmp_path):
    base = tmp_path / "src"
    base.mkdir()
    kernel = Kernel.auto()
    src = FilesystemWritableSource(base_dir=str(base))
    kernel.source(src)
    prov = SqliteVecRecordSearchProvider(kernel, db_path=str(tmp_path / "mem.db"))
    kernel.record_search_provider(prov)
    yield kernel
    prov.close()


@pytest.fixture
def kernel_lexical(tmp_path):
    base = tmp_path / "src"
    base.mkdir()
    kernel = Kernel.auto()
    kernel.source(FilesystemWritableSource(base_dir=str(base)))
    return kernel


def _hit(res: dict, name: str) -> dict:
    by_name = {h["name"]: h for h in res["hits"]}
    assert name in by_name, res["hits"]
    return by_name[name]


# ── display fields — both planes project the SAME spec values ───────────────


@pytest.mark.asyncio
async def test_provider_hits_carry_display_fields(kernel_with_provider):
    kernel = kernel_with_provider
    spec = _spec("the deploy needs 127.0.0.1 never localhost")
    await remember(kernel, "demo", kind="Engram", name="disp-a", spec=spec)

    res = await recall(kernel, "demo", "deploy localhost", reconsolidate=False)
    assert res["degraded"] is False
    hit = _hit(res, "disp-a")
    # the values ARE the remembered spec's — not just present.
    assert hit["summary"] == spec["summary"]
    assert hit["area"] == spec["area"]
    assert hit["affect"] == spec["affect"]
    assert hit["tags"] == spec["tags"]
    assert hit["created_at"] == spec["created_at"]
    # a hit outside a personal partition is never personal.
    assert hit["personal"] is False


@pytest.mark.asyncio
async def test_lexical_hits_carry_display_fields(kernel_lexical):
    kernel = kernel_lexical
    spec = _spec("the plan bridge is PUT workspace-plan", tags=["billing"])
    await remember(kernel, "demo", kind="Engram", name="disp-lex", spec=spec)

    res = await recall(kernel, "demo", "workspace-plan bridge", reconsolidate=False)
    assert res["degraded"] is True  # honest lexical — no provider registered
    hit = _hit(res, "disp-lex")
    assert hit["summary"] == spec["summary"]
    assert hit["area"] == spec["area"]
    assert hit["affect"] == spec["affect"]
    assert hit["tags"] == ["billing"]
    assert hit["created_at"] == spec["created_at"]
    # the lexical hit had no provider title — recall fills it from the spec.
    assert hit["title"] == spec["summary"]
    assert hit["personal"] is False


@pytest.mark.asyncio
async def test_provider_title_is_never_overwritten(kernel_with_provider):
    """The provider indexes a title of its own — enrichment must not clobber it
    (strictly additive: existing hit keys win)."""
    kernel = kernel_with_provider
    spec = dict(_spec("summary text for the title test"), title="the explicit title")
    await remember(kernel, "demo", kind="Engram", name="disp-title", spec=spec)

    res = await recall(kernel, "demo", "title test summary", reconsolidate=False)
    assert _hit(res, "disp-title")["title"] == "the explicit title"


@pytest.mark.asyncio
async def test_fields_absent_from_spec_are_not_fabricated(kernel_lexical):
    kernel = kernel_lexical
    spec = _spec("an engram note with no tags")
    spec.pop("tags")
    await remember(kernel, "demo", kind="Engram", name="disp-notags", spec=spec)

    res = await recall(kernel, "demo", "engram note tags", reconsolidate=False)
    hit = _hit(res, "disp-notags")
    assert "tags" not in hit  # never a fabricated []
    assert hit["summary"] == spec["summary"]


# ── the per-item personal flag — a personal recall unions the base ──────────


@pytest.mark.asyncio
async def test_personal_recall_flags_per_item(kernel_with_provider):
    """One recall, two provenances: the shared base memory rides along with
    ``personal: False``; the caller's own partition memory carries ``True``.
    The flag is per-ITEM — never per-call."""
    kernel = kernel_with_provider
    await remember(
        kernel, "demo", kind="Engram", name="mem-shared",
        spec=_spec("shared base note about the genome teal palette"),
    )
    await remember(
        kernel, "demo", kind="Engram", name="mem-private",
        spec=_spec("private note about the genome teal palette"),
        tenant=_PERSONAL,
    )

    res = await recall(
        kernel, "demo", "genome teal palette", tenant=_PERSONAL,
        reconsolidate=False,
    )
    assert _hit(res, "mem-shared")["personal"] is False
    assert _hit(res, "mem-private")["personal"] is True


@pytest.mark.asyncio
async def test_personal_flag_in_lexical_fallback(kernel_lexical):
    kernel = kernel_lexical
    await remember(
        kernel, "demo", kind="Engram", name="lex-shared",
        spec=_spec("shared lexical fallback marker"),
    )
    await remember(
        kernel, "demo", kind="Engram", name="lex-private",
        spec=_spec("private lexical fallback marker"),
        tenant=_PERSONAL,
    )

    res = await recall(
        kernel, "demo", "lexical fallback marker", tenant=_PERSONAL,
        reconsolidate=False,
    )
    assert res["degraded"] is True
    assert _hit(res, "lex-shared")["personal"] is False
    assert _hit(res, "lex-private")["personal"] is True


@pytest.mark.asyncio
async def test_personal_shadow_of_a_base_doc_is_flagged(kernel_lexical):
    """A personal overlay that SHADOWS a base doc of the same name: the
    returned spec IS the personal copy, so the flag must say so."""
    kernel = kernel_lexical
    await remember(
        kernel, "demo", kind="Engram", name="mem-shadow",
        spec=_spec("the shared wording of the shadow note"),
    )
    await remember(
        kernel, "demo", kind="Engram", name="mem-shadow",
        spec=_spec("the PRIVATE wording of the shadow note"),
        tenant=_PERSONAL,
    )

    res = await recall(
        kernel, "demo", "wording shadow note", tenant=_PERSONAL,
        reconsolidate=False,
    )
    hit = _hit(res, "mem-shadow")
    assert hit["personal"] is True
    assert hit["summary"] == "the PRIVATE wording of the shadow note"


@pytest.mark.asyncio
async def test_workspace_recall_is_never_personal(kernel_lexical):
    kernel = kernel_lexical
    await remember(
        kernel, "demo", kind="Engram", name="ws-base",
        spec=_spec("acme workspace base note"),
    )
    await remember(
        kernel, "demo", kind="Engram", name="ws-note",
        spec=_spec("acme workspace overlay note"), tenant="acme",
    )
    res = await recall(
        kernel, "demo", "acme workspace overlay", tenant="acme",
        reconsolidate=False,
    )
    assert all(h["personal"] is False for h in res["hits"])
    assert _hit(res, "ws-note")["summary"] == "acme workspace overlay note"
