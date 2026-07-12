"""`dna recall` / `dna search` / `dna research recall` — end-to-end, offline.

Seeds a filesystem scope, then drives the real CLI (CliRunner, in-process) with
DNA_BASE_DIR pointed at it. With the `search-sqlite` extra present the search is
hybrid (degraded=false, provider-backed); the same command degrades honestly to
the kernel's lexical scan when the extra is absent (skipped here, exercised by
the provider's own import-isolation guard).
"""
from __future__ import annotations

import asyncio

import pytest
from click.testing import CliRunner

sqlite_vec = pytest.importorskip(
    "sqlite_vec",
    reason="search-sqlite extra not installed",
)

from dna_cli import main  # noqa: E402


_DOCS = [
    ("s-memory", "memory similarity vector embedding recall cognitive"),
    ("s-banana", "banana tropical yellow fruit smoothie"),
    ("s-fusion", "hybrid search fusion reciprocal rank bm25"),
]


def _seed_scope(base_dir: str, scope: str) -> None:
    from dna.kernel import Kernel
    from dna.adapters.filesystem.writable import FilesystemWritableSource

    async def go() -> None:
        kernel = Kernel.auto()
        src = FilesystemWritableSource(base_dir=base_dir)
        Kernel.auto(source=src)
        kernel.source(src)
        for name, text in _DOCS:
            raw = {
                "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
                "kind": "Story",
                "metadata": {"name": name},
                # status: Story schema requires it — the generic write-path
                # validation (i-008) now vetoes the skeletal fixture.
                "spec": {"title": text, "description": text, "status": "todo"},
            }
            await kernel.write_document(scope, "Story", name, raw)

    asyncio.run(go())


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    base = tmp_path / "src"
    base.mkdir()
    _seed_scope(str(base), "demo")
    monkeypatch.setenv("DNA_BASE_DIR", str(base))
    monkeypatch.setenv("DNA_SEARCH_DIR", str(tmp_path / "search"))
    return base


def test_recall_hybrid_ranks_relevant_doc_first(seeded):
    runner = CliRunner()
    result = runner.invoke(
        main, ["recall", "memory recall cognitive", "--scope", "demo",
                "--kind", "Story", "-k", "3", "--json"],
    )
    assert result.exit_code == 0, result.output
    import json
    payload = json.loads(result.output)
    assert payload["degraded"] is False, "provider present → must not degrade"
    names = [h["name"] for h in payload["hits"]]
    assert names and names[0] == "s-memory", names


def test_search_alias_works(seeded):
    runner = CliRunner()
    result = runner.invoke(
        main, ["search", "banana fruit smoothie", "--scope", "demo",
                "--kind", "Story", "-k", "3", "--json"],
    )
    assert result.exit_code == 0, result.output
    import json
    payload = json.loads(result.output)
    assert payload["hits"][0]["name"] == "s-banana"


def test_research_recall_routes_through_search(seeded, monkeypatch):
    """`dna research recall` is the i-004 wiring: same provider-backed path,
    constrained to kind=Research. With no Research docs it returns cleanly
    (exit 0, no matches) — proving it routes without crashing."""
    runner = CliRunner()
    result = runner.invoke(
        main, ["research", "recall", "memory", "--scope", "demo",
                "-k", "3", "--json"],
    )
    assert result.exit_code == 0, result.output
    import json
    payload = json.loads(result.output)
    assert payload["degraded"] is False
    assert payload["hits"] == []  # no Research kind seeded


def test_document_text_derivation():
    from dna.adapters.search.sqlite_vec import document_text

    raw = {"metadata": {"name": "s-x"},
           "spec": {"title": "Alpha", "nested": {"k": "Beta"}, "list": ["Gamma"]}}
    text = document_text(raw)
    assert "s-x" in text and "Alpha" in text and "Beta" in text and "Gamma" in text


def test_register_provider_wires_onnx_embedder_when_extra_present():
    """With the ``embed-onnx`` extra installed, ``_register_provider`` upgrades
    the dense plane from the fake-hash floor to the real offline ONNX embedder,
    so ``semantic`` recall is genuinely semantic (not lexical-in-disguise).

    Construction is lazy (no model download here) — we only assert the registered
    provider's identity, so this stays fast and offline."""
    pytest.importorskip("fastembed", reason="embed-onnx extra not installed")

    from dna.adapters.embedding.onnx import ONNX_MODEL_ID
    from dna.kernel import Kernel
    from dna_cli.recall_cmd import _register_provider

    class _Holder:
        def __init__(self, kernel):
            self.kernel = kernel

    kernel = Kernel.auto()
    # Floor is not eagerly registered — no explicit embedder yet.
    assert getattr(kernel, "_embedding_provider", None) is None

    provider = _register_provider(_Holder(kernel))
    assert provider is not None, "search-sqlite present → provider registered"
    # The ONNX embedder is now the active space (real semantic embeddings).
    assert kernel.embedding_model_id == ONNX_MODEL_ID


def test_register_embedder_is_noop_when_embedder_already_wired():
    """``_register_embedder`` respects an explicit prior registration — it never
    clobbers a boot-time / config-chosen embedder."""
    from dna.kernel import Kernel
    from dna.kernel.embedding import FAKE_EMBEDDING_MODEL_ID, FakeEmbeddingProvider
    from dna_cli.recall_cmd import _register_embedder

    kernel = Kernel.auto()
    kernel.embedding_provider(FakeEmbeddingProvider())
    _register_embedder(kernel)  # extra may be present, but one is already wired
    assert kernel.embedding_model_id == FAKE_EMBEDDING_MODEL_ID
