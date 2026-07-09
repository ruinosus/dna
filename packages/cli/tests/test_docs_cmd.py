"""``dna docs`` against the NATIVE ``Doc`` Kind (s-tier-a-doc-kind).

End-to-end, offline: drives the real CLI (CliRunner, in-process) against a
filesystem scope holding two Doc bundles (en + pt-BR) and **no per-scope
KindDefinition** — proving the corpus reader works out-of-the-box now that
the Doc Kind ships as a builtin descriptor
(``dna/extensions/doc/kinds/doc.kind.yaml``). Before this, the CLI group
degraded: users had to hand-author a KindDefinition first (the old
cli-tour workaround).
"""
from __future__ import annotations

import json

from click.testing import CliRunner

from dna_cli import main

_GENOME_LIB = (
    "apiVersion: github.com/ruinosus/dna/v1\n"
    "kind: Genome\n"
    "metadata: { name: _lib }\n"
    "spec: {}\n"
)

_GENOME_DOCS = (
    "apiVersion: github.com/ruinosus/dna/v1\n"
    "kind: Genome\n"
    "metadata:\n"
    "  name: docs\n"
    "  description: In-product documentation corpus\n"
    "spec: {}\n"
)

_DOC_EN = """---
description: Welcome to the corpus
icon: "👋"
order: 1
locale: en
kind_of: tutorial
category: Getting started
---

# Welcome

This corpus is served in-product: agents and the UI read these pages
through the kernel.
"""

_DOC_PT = """---
description: Bem-vindo ao corpus
icon: "👋"
order: 2
locale: pt-BR
kind_of: tutorial
category: Primeiros passos
---

# Bem-vindo

Este corpus é servido dentro do produto.
"""


def _make_corpus(tmp_path):
    """Two native Doc bundles (en + pt-BR); NO kinds/ dir anywhere."""
    base = tmp_path / ".dna"
    (base / "_lib").mkdir(parents=True)
    (base / "_lib" / "Genome.yaml").write_text(_GENOME_LIB, encoding="utf-8")
    scope = base / "docs"
    scope.mkdir()
    (scope / "Genome.yaml").write_text(_GENOME_DOCS, encoding="utf-8")
    for name, content in (("welcome", _DOC_EN), ("boas-vindas", _DOC_PT)):
        bundle = scope / "docs" / name
        bundle.mkdir(parents=True)
        (bundle / "DOC.md").write_text(content, encoding="utf-8")
    return base


def _runner_env(tmp_path, monkeypatch):
    base = _make_corpus(tmp_path)
    monkeypatch.setenv("DNA_BASE_DIR", str(base))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return CliRunner()


def test_docs_list_en_out_of_the_box(tmp_path, monkeypatch):
    runner = _runner_env(tmp_path, monkeypatch)
    res = runner.invoke(main, ["docs", "list", "--locale", "en", "--json"])
    assert res.exit_code == 0, res.output
    rows = json.loads(res.output)
    assert [r["name"] for r in rows] == ["welcome"]
    assert rows[0]["title"] == "Welcome to the corpus"
    assert rows[0]["kind_of"] == "tutorial"
    assert rows[0]["category"] == "Getting started"
    assert rows[0]["order"] == 1


def test_docs_list_default_locale_is_pt_br(tmp_path, monkeypatch):
    runner = _runner_env(tmp_path, monkeypatch)
    res = runner.invoke(main, ["docs", "list", "--json"])
    assert res.exit_code == 0, res.output
    rows = json.loads(res.output)
    assert [r["name"] for r in rows] == ["boas-vindas"]
    assert rows[0]["title"] == "Bem-vindo ao corpus"


def test_docs_show_prints_markdown_body(tmp_path, monkeypatch):
    runner = _runner_env(tmp_path, monkeypatch)
    res = runner.invoke(main, ["docs", "show", "welcome", "--locale", "en"])
    assert res.exit_code == 0, res.output
    assert "# Welcome" in res.output
    assert "through the kernel" in res.output
    # frontmatter stays in the spec, never leaks into the body
    assert "kind_of" not in res.output


def test_docs_show_locale_fallback(tmp_path, monkeypatch):
    """A doc that only exists in one locale is still reachable (the CLI
    falls back to the first candidate when the locale doesn't match)."""
    runner = _runner_env(tmp_path, monkeypatch)
    res = runner.invoke(main, ["docs", "show", "boas-vindas", "--locale", "en"])
    assert res.exit_code == 0, res.output
    assert "# Bem-vindo" in res.output


def test_docs_show_unknown_doc_fails(tmp_path, monkeypatch):
    runner = _runner_env(tmp_path, monkeypatch)
    res = runner.invoke(main, ["docs", "show", "nope"])
    assert res.exit_code != 0
