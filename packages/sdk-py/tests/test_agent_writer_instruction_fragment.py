"""s-sync-s3 — the helix AgentWriter must EMIT the instruction_file fragment
(and carried source_files) so save_document persists doc+bundle atomically.

Root cause of i-061/i-062: the writer left AGENT.md body="" for instruction_file
agents and never wrote instruction.md, assuming the fragment pre-existed —
zeroing the instruction when writing to a fresh bundle. This is the structural
fix (every write path benefits; the CLI band-aids become redundant).
"""
from __future__ import annotations

from dna.extensions.helix import AgentWriter
from dna.kernel.bundle.handle import DictBundleHandle


def _raw(spec):
    return {"apiVersion": "github.com/ruinosus/dna/helix/v1", "kind": "Agent",
            "metadata": {"name": "code-reviewer"}, "spec": spec}


W = AgentWriter()


def _entries(handle):
    return {e: handle for e in handle.iter_entries(recursive=True)}


def test_emits_fragment_from_carried_source_files():
    h = DictBundleHandle("code-reviewer", {})
    W.write(h, _raw({
        "model": "m",
        "instruction_file": "instruction.md",
        "source_files": {"instruction.md": "Review code. Cite file:line."},
    }))
    paths = set(h.iter_entries(recursive=True))
    assert "AGENT.md" in paths
    assert "instruction.md" in paths
    assert h.read_text("instruction.md") == "Review code. Cite file:line."
    # AGENT.md body stays empty (fragment owns the instruction).
    assert "Review code" not in h.read_text("AGENT.md")


def test_emits_fragment_from_resolved_inline_when_no_source_files():
    """write_document called WITHOUT the CLI (kinds-api PUT / direct) only has
    the resolved instruction — the fragment must still be emitted."""
    h = DictBundleHandle("code-reviewer", {})
    W.write(h, _raw({
        "model": "m",
        "instruction_file": "instruction.md",
        "instruction": "Resolved body.",
    }))
    assert "instruction.md" in set(h.iter_entries(recursive=True))
    assert h.read_text("instruction.md") == "Resolved body."


def test_emits_binary_source_files():
    h = DictBundleHandle("code-reviewer", {})
    png = b"\x89PNG\r\n\x00\xff"
    W.write(h, _raw({
        "model": "m",
        "instruction_file": "instruction.md",
        "source_files": {"instruction.md": "x", "logo.png": png},
    }))
    paths = set(h.iter_entries(recursive=True))
    assert "logo.png" in paths
    assert h._entries["logo.png"] == png  # stored as raw bytes


def test_inline_agent_unaffected():
    """A non-instruction_file agent still bakes the body into AGENT.md."""
    h = DictBundleHandle("inline", {})
    W.write(h, _raw({"model": "m", "instruction": "inline body here"}))
    assert "inline body here" in h.read_text("AGENT.md")
    assert "instruction.md" not in set(h.iter_entries(recursive=True))
