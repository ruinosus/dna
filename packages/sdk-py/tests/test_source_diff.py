"""s-sync-s4 — Kernel.diff_manifests (pure set-diff) + cross-source diff via the
parametrized digest_manifest. This is the engine behind `dna source diff`: two
sources in sync → empty diff; drift → detected, in seconds, no content transfer.
"""
from __future__ import annotations

import asyncio

from dna.kernel import Kernel


# ───────────────────────── pure diff_manifests ─────────────────────────

def test_diff_identical_is_empty():
    m = {("Agent", "a"): "h1", ("Skill", "s"): "h2"}
    assert Kernel.diff_manifests(m, dict(m)) == {"added": [], "changed": [], "removed": []}


def test_diff_added_removed_changed():
    a = {("Agent", "a"): "h1", ("Agent", "b"): "h2", ("Skill", "s"): "hs"}
    b = {("Agent", "a"): "h1", ("Agent", "b"): "DIFFERENT", ("Doc", "d"): "hd"}
    out = Kernel.diff_manifests(a, b)
    assert out["added"] == [("Skill", "s")]            # in a (source) not b
    assert out["removed"] == [("Doc", "d")]            # in b (target) not a
    assert out["changed"] == [("Agent", "b")]   # digest drifted


def test_diff_is_sorted_and_stable():
    a = {("K", "z"): "1", ("K", "a"): "1"}
    b = {}
    assert Kernel.diff_manifests(a, b)["added"] == [("K", "a"), ("K", "z")]


# ───────────────────── cross-source via digest_manifest ─────────────────

class _FakeSource:
    def __init__(self, docs, entries=None):
        self._docs = docs
        self._entries = entries or {}

    async def load_layer(self, scope, lid, lv, readers=None):
        return list(self._docs)

    async def _load_bundle_entries(self, scope, kind, name, tenant):
        return dict(self._entries.get((kind, name), {}))


def _agent(name, instruction):
    return {"apiVersion": "github.com/ruinosus/dna/helix/v1", "kind": "Agent",
            "metadata": {"name": name},
            "spec": {"model": "m", "instruction": instruction}}


def test_in_sync_sources_have_empty_diff():
    k = Kernel.auto()
    fs = _FakeSource([_agent("code-reviewer", "Review code.")])
    pg = _FakeSource([_agent("code-reviewer", "Review code.")])
    k.source(fs)
    man_fs = asyncio.run(k.digest_manifest("scope-x"))
    man_pg = asyncio.run(k.digest_manifest("scope-x", source=pg))
    assert Kernel.diff_manifests(man_fs, man_pg) == {"added": [], "changed": [], "removed": []}


def test_drift_between_sources_is_detected():
    k = Kernel.auto()
    fs = _FakeSource([_agent("code-reviewer", "Review code v2."), _agent("new-one", "hi")])
    pg = _FakeSource([_agent("code-reviewer", "Review code v1.")])  # stale + missing new-one
    k.source(fs)
    man_fs = asyncio.run(k.digest_manifest("scope-x"))
    man_pg = asyncio.run(k.digest_manifest("scope-x", source=pg))
    diff = Kernel.diff_manifests(man_fs, man_pg)
    assert ("Agent", "new-one") in diff["added"]
    assert ("Agent", "code-reviewer") in diff["changed"]
    assert diff["removed"] == []
