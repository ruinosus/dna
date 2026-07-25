"""The filesystem writer emits READABLE, round-trip-safe YAML (i-070).

`yaml.dump` without ``allow_unicode`` escapes every non-ASCII char
(``é`` → ``\\xE9``, ``→`` → ``\\u2192``), which forces double-quoted style;
double-quoted strings wrapped at the default width=80 then use ``\\`` line
continuation plus a leading ``\\ `` on the next line. The result is
unreadable YAML — and, per the ResearchWriter's own note, markdown-ish
content can even fail to round-trip ("unexpected end of stream").

Every other writer in this repo (research, tenant, kinddef, safety,
recognizer, lesson, helix, emit) already passes ``allow_unicode=True``;
the generic filesystem doc writer — the one that persists the whole SDLC
board and every plain-YAML Kind — was the one that did not.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.kernel import Kernel

_SCOPE = "test-yaml"
# Accented text + an arrow + enough length to cross the default width=80.
_BODY = (
    "Inventariar as superfícies de query (mi.documents vs kernel.query) nos 2 "
    "SDKs; decidir o conjunto blessed pré-1.0 → deprecations com guidance clara."
)
_MULTILINE = "Primeira linha com acentuação é í ã.\nSegunda linha → com seta.\nTerceira."


@pytest.fixture()
def source(tmp_path: Path) -> FilesystemWritableSource:
    base = tmp_path / ".dna"
    (base / _SCOPE).mkdir(parents=True)
    (base / "_lib").mkdir(parents=True, exist_ok=True)
    k = Kernel.auto()
    src = FilesystemWritableSource(str(base), kernel=k)
    k.source(src)
    return src


def _written_text(source: FilesystemWritableSource, name: str) -> str:
    for path in Path(source.base_dir).rglob(f"{name}.yaml"):
        return path.read_text(encoding="utf-8")
    raise AssertionError(f"no {name}.yaml written under {source.base_dir}")


@pytest.mark.asyncio
async def test_unicode_is_written_verbatim_not_escaped(source) -> None:
    """Accents and arrows survive as themselves — no \\xE9 / \\u2192 escapes."""
    raw = {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Story",
           "metadata": {"name": "s-acentos"}, "spec": {"body": _BODY}}
    await source.save_document(_SCOPE, "Story", "s-acentos", raw)
    text = _written_text(source, "s-acentos")

    assert "superfícies" in text and "→" in text
    assert "\\xE9" not in text and "\\u2192" not in text


@pytest.mark.asyncio
async def test_long_lines_are_not_split_with_backslash_continuations(source) -> None:
    """No ``\\`` line-continuation artifacts — the thing that makes the board
    unreadable (a trailing backslash plus a leading ``\\ `` on the next line)."""
    raw = {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Story",
           "metadata": {"name": "s-longa"}, "spec": {"body": _BODY}}
    await source.save_document(_SCOPE, "Story", "s-longa", raw)
    text = _written_text(source, "s-longa")

    assert not any(line.rstrip().endswith("\\") for line in text.splitlines())


@pytest.mark.asyncio
async def test_multiline_uses_block_literal_and_round_trips(source) -> None:
    """Multi-line content is emitted as a block literal (``|``) and parses
    back to exactly what was written."""
    raw = {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Story",
           "metadata": {"name": "s-multi"}, "spec": {"body": _MULTILINE}}
    await source.save_document(_SCOPE, "Story", "s-multi", raw)
    text = _written_text(source, "s-multi")

    assert "|" in text.split("body:")[1].splitlines()[0]
    assert yaml.safe_load(text)["spec"]["body"] == _MULTILINE
