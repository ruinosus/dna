"""Regression tests for i-061 — `dna doc apply` must persist sibling bundle
entries (the `instruction_file` fragment, scripts/, references/) into the
target source.

The bug: applying an `instruction_file` Agent only wrote the doc index;
the `instruction.md` fragment was never written as a bundle entry, so
`resolve_document` re-resolved `instruction_file` from an empty bundle and
zeroed the agent's instruction — silently turning a specialist into a generic
assistant in EVERY use (chat/eval/voice).

Two halves of the fix are covered:
  1. `_load_apply_input` on a single marker file collects sibling bundle
     files from the parent dir into `spec.source_files` (so `apply AGENT.md`
     == `apply <dir>`).
  2. `_apply_one` pops `spec.source_files` and persists each as a bundle entry
     via `kernel.write_bundle_entry_async` AFTER the doc write.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

from dna_cli import doc_cmd
from dna_cli.doc_cmd import _apply_one, _load_apply_input


def _bundle(tmp_path):
    """An instruction_file Agent bundle: AGENT.md + instruction.md."""
    d = tmp_path / "code-reviewer"
    d.mkdir()
    (d / "AGENT.md").write_text(
        "---\nname: code-reviewer\nmodel: openai:gpt-5-mini\n"
        "instruction_file: instruction.md\n---\n",
        encoding="utf-8",
    )
    (d / "instruction.md").write_text(
        "You review code. Cite file:line and severity.", encoding="utf-8",
    )
    return d


def test_single_marker_apply_collects_sibling_instruction_file(tmp_path):
    """Applying the AGENT.md FILE (not the dir) still picks up instruction.md."""
    from dna.kernel import Kernel

    kernel = Kernel.auto()
    d = _bundle(tmp_path)
    raw = _load_apply_input(str(d / "AGENT.md"), kernel)

    src = (raw.get("spec") or {}).get("source_files") or {}
    assert "instruction.md" in src, f"sibling not collected: {list(src)}"
    assert "review code" in src["instruction.md"].lower()


def _mock_session():
    kernel = MagicMock()
    kernel.write_document = AsyncMock(return_value={"ok": True})
    kernel.write_bundle_entry_async = AsyncMock(return_value=None)
    kernel.with_tenant.return_value = kernel

    s = MagicMock()
    s.kernel = kernel
    s.holder = MagicMock()
    s.scope = "hr-screening"
    s.get_doc.return_value = None  # new doc → CREATED

    def _run(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    s.run = _run
    return s, kernel


def test_apply_one_persists_bundle_entries(monkeypatch):
    """_apply_one must write each source_files entry as a bundle entry AFTER
    the doc write, and NOT leave source_files bloating the stored spec."""
    monkeypatch.setattr(doc_cmd, "_tenant_write_note", lambda t: (None, None))
    s, kernel = _mock_session()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "code-reviewer"},
        "spec": {
            "model": "openai:gpt-5-mini",
            "instruction_file": "instruction.md",
            "source_files": {"instruction.md": "You review code."},
        },
    }

    _apply_one(s, raw, path="code-reviewer/AGENT.md", doc_index=None,
               tenant=None, dry_run=False)

    # The doc was written WITHOUT source_files (no spec bloat).
    assert kernel.write_document.await_count == 1
    written_raw = kernel.write_document.await_args.args[3]
    assert "source_files" not in (written_raw.get("spec") or {})

    # The instruction.md fragment was persisted as a bundle entry.
    assert kernel.write_bundle_entry_async.await_count == 1
    call = kernel.write_bundle_entry_async.await_args
    # (scope, kind, name, entry_path, data, *, tenant)
    assert call.args[1] == "Agent"
    assert call.args[2] == "code-reviewer"
    assert call.args[3] == "instruction.md"
    # i-083: text entries pass through as str (routed to the text column), not
    # force-encoded to bytes.
    assert call.args[4] == "You review code."


def test_single_marker_apply_collects_binary_sibling(tmp_path):
    """i-062 — binary bundle entries (fonts, images) are collected as bytes,
    not dropped like the text-only collection did."""
    from dna.kernel import Kernel

    kernel = Kernel.auto()
    d = tmp_path / "code-reviewer"
    d.mkdir()
    (d / "AGENT.md").write_text(
        "---\nname: code-reviewer\nmodel: openai:gpt-5-mini\n"
        "instruction_file: instruction.md\n---\n",
        encoding="utf-8",
    )
    (d / "instruction.md").write_text("Review code.", encoding="utf-8")
    # A fake binary asset (PNG magic bytes — not valid UTF-8).
    png = b"\x89PNG\r\n\x1a\n\x00\x01\x02\x80\xff\xfe"
    (d / "logo.png").write_bytes(png)

    raw = _load_apply_input(str(d / "AGENT.md"), kernel)
    src = (raw.get("spec") or {}).get("source_files") or {}
    assert src.get("instruction.md") == "Review code."  # text → str
    assert src.get("logo.png") == png                     # binary → bytes


def test_apply_one_persists_binary_bundle_entry(monkeypatch):
    """i-062 — _apply_one writes a binary source_file through as raw bytes."""
    monkeypatch.setattr(doc_cmd, "_tenant_write_note", lambda t: (None, None))
    s, kernel = _mock_session()
    png = b"\x89PNG\r\n\xff\x00"
    raw = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "code-reviewer"},
        "spec": {
            "model": "openai:gpt-5-mini",
            "instruction_file": "instruction.md",
            "source_files": {"instruction.md": "Review code.", "logo.png": png},
        },
    }
    _apply_one(s, raw, path="x/AGENT.md", doc_index=None, tenant=None, dry_run=False)

    assert kernel.write_bundle_entry_async.await_count == 2
    by_path = {
        c.args[3]: c.args[4]
        for c in kernel.write_bundle_entry_async.await_args_list
    }
    assert by_path["instruction.md"] == "Review code."   # i-083: text → str (text column)
    assert by_path["logo.png"] == png                     # bytes → as-is


def test_apply_one_without_source_files_writes_no_entries(monkeypatch):
    """A plain doc (no bundle) writes the doc only — no spurious entry writes."""
    monkeypatch.setattr(doc_cmd, "_tenant_write_note", lambda t: (None, None))
    s, kernel = _mock_session()
    raw = {
        "apiVersion": "github.com/ruinosus/dna/helix/v1",
        "kind": "Agent",
        "metadata": {"name": "inline-agent"},
        "spec": {"model": "openai:gpt-5-mini", "instruction": "inline body"},
    }

    _apply_one(s, raw, path="x.yaml", doc_index=None, tenant=None, dry_run=False)

    assert kernel.write_document.await_count == 1
    assert kernel.write_bundle_entry_async.await_count == 0
