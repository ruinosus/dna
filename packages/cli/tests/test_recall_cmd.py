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
                "spec": {"title": text, "description": text},
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
