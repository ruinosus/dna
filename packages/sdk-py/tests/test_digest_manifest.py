"""s-sync-s2 — kernel.digest_manifest(scope): {(kind,name): digest} for a
scope, source-independent (same content → same manifest across FS/Postgres),
covering bundle entries (incl. binaries) via a Merkle fold over s-sync-s1's
canonical_digest.
"""
from __future__ import annotations

import asyncio

import pytest

from dna.kernel import Kernel


class _FakeSource:
    """Minimal SourcePort surface for digest_manifest: a layer of resolved
    raw docs + per-doc bundle entries."""

    def __init__(self, docs, entries):
        self._docs = docs
        self._entries = entries

    async def load_layer(self, scope, layer_id, layer_value, readers=None):
        return list(self._docs)

    async def _load_bundle_entries(self, scope, kind, name, tenant):
        return dict(self._entries.get((kind, name), {}))


def _agent_raw(name, instruction, extra=None):
    spec = {"model": "openai:gpt-5-mini", "instruction": instruction,
            "instruction_file": "instruction.md"}
    if extra:
        spec.update(extra)
    return {"apiVersion": "github.com/ruinosus/dna/helix/v1", "kind": "Agent",
            "metadata": {"name": name}, "spec": spec}


def _manifest(source):
    k = Kernel.auto()
    k.source(source)
    return asyncio.run(k.digest_manifest("test-scope"))


def test_manifest_covers_all_docs_keyed_by_kind_name():
    src = _FakeSource(
        [_agent_raw("code-reviewer", "Review code."),
         _agent_raw("talent-screener", "Screen candidates.")],
        {("Agent", "code-reviewer"): {"AGENT.md": "...", "instruction.md": "Review code."},
         ("Agent", "talent-screener"): {"AGENT.md": "...", "instruction.md": "Screen candidates."}},
    )
    m = _manifest(src)
    assert set(m) == {("Agent", "code-reviewer"), ("Agent", "talent-screener")}
    assert all(isinstance(v, str) and len(v) == 64 for v in m.values())  # sha256 hex
    assert m[("Agent", "code-reviewer")] != m[("Agent", "talent-screener")]


def test_manifest_is_deterministic():
    src = _FakeSource(
        [_agent_raw("a", "hi")],
        {("Agent", "a"): {"AGENT.md": "x", "instruction.md": "hi"}},
    )
    assert _manifest(src) == _manifest(src)


def test_binary_entry_divergence_changes_digest():
    """A bundle whose binary asset differs hashes differently — the gap the
    audit found (market-demo fonts) is now detectable."""
    base_entries = {"AGENT.md": "x", "instruction.md": "hi", "logo.png": b"\x89PNG-A"}
    src_a = _FakeSource([_agent_raw("a", "hi")],
                        {("Agent", "a"): dict(base_entries)})
    src_b = _FakeSource([_agent_raw("a", "hi")],
                        {("Agent", "a"): {**base_entries, "logo.png": b"\x89PNG-B"}})
    assert _manifest(src_a)[("Agent", "a")] != _manifest(src_b)[("Agent", "a")]


def test_marker_only_bundle_matches_specdigest_path():
    """A bundle with only the marker (no extra entries) still produces a
    stable digest (spec-only path)."""
    src = _FakeSource([_agent_raw("a", "hi")],
                      {("Agent", "a"): {"AGENT.md": "x"}})
    m = _manifest(src)
    assert ("Agent", "a") in m and len(m[("Agent", "a")]) == 64


def test_volatile_stamps_dont_change_manifest():
    src1 = _FakeSource([_agent_raw("a", "hi", {"updated_at": "T1", "version": 1})],
                       {("Agent", "a"): {"AGENT.md": "x", "instruction.md": "hi"}})
    src2 = _FakeSource([_agent_raw("a", "hi", {"updated_at": "T2", "version": 9})],
                       {("Agent", "a"): {"AGENT.md": "x", "instruction.md": "hi"}})
    assert _manifest(src1) == _manifest(src2)
