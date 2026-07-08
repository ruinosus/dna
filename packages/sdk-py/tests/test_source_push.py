"""s-sync-s5 — kernel.push_scope: reconcile a target source to match the
current (source-of-truth) for a scope. Minimal diff (s4) → write added/changed
via save_document (the s3 atomic net) → optional prune. Idempotent.
"""
from __future__ import annotations

import asyncio

from dna.kernel import Kernel
from dna.testing import CoreSourceStub


def _agent(name, instruction):
    return {"apiVersion": "github.com/ruinosus/dna/helix/v1", "kind": "Agent",
            "metadata": {"name": name},
            "spec": {"model": "m", "instruction": instruction}}


class _FromSource(CoreSourceStub):
    """Read source-of-truth: a fixed set of docs."""
    def __init__(self, docs):
        self._by_name = {d["metadata"]["name"]: d for d in docs}

    async def load_layer(self, scope, lid, lv, readers=None):
        return list(self._by_name.values())

    async def load_one(self, scope, kind, name, readers=None, tenant=None):
        return self._by_name.get(name)

    async def _load_bundle_entries(self, scope, kind, name, tenant):
        return {}  # inline agents — no fragments here


class _ToSource(CoreSourceStub):
    """Writable target that records writes and reflects them in its manifest."""
    def __init__(self, docs=None):
        self._by_name = {d["metadata"]["name"]: d for d in (docs or [])}
        self.writes = []
        self.deletes = []

    async def load_layer(self, scope, lid, lv, readers=None):
        return list(self._by_name.values())

    async def _load_bundle_entries(self, scope, kind, name, tenant):
        return {}

    async def save_document(self, scope, kind, name, raw, author=None, *, tenant=None, layer=None):
        # strip transport like the real net would
        spec = dict(raw.get("spec") or {})
        spec.pop("source_files", None)
        self._by_name[name] = {**raw, "spec": spec}
        self.writes.append((kind, name))
        return "v1"

    async def delete_document(self, scope, kind, name, *, tenant=None, layer=None):
        self._by_name.pop(name, None)
        self.deletes.append((kind, name))


def _kernel(from_src):
    k = Kernel.auto()
    k.source(from_src)
    return k


def test_dry_run_returns_diff_without_writing():
    frm = _FromSource([_agent("a", "v2"), _agent("b", "hi")])
    to = _ToSource([_agent("a", "v1")])  # a drifted, b missing
    k = _kernel(frm)
    out = asyncio.run(k.push_scope("s", to, dry_run=True))
    assert ("Agent", "a") in out["changed"]
    assert ("Agent", "b") in out["added"]
    assert to.writes == [] and out["applied"] == []


def test_push_converges_and_is_idempotent():
    frm = _FromSource([_agent("a", "v2"), _agent("b", "hi")])
    to = _ToSource([_agent("a", "v1")])
    k = _kernel(frm)
    out = asyncio.run(k.push_scope("s", to))
    assert ("write", "Agent", "a") in out["applied"]
    assert ("write", "Agent", "b") in out["applied"]
    # Target now matches source — a re-push is a no-op.
    out2 = asyncio.run(k.push_scope("s", to))
    assert out2["added"] == [] and out2["changed"] == [] and out2["applied"] == []


def test_prune_deletes_target_only_docs():
    frm = _FromSource([_agent("a", "hi")])
    to = _ToSource([_agent("a", "hi"), _agent("stale", "old")])  # stale only in target
    k = _kernel(frm)
    # Without prune: stale is reported removed but NOT deleted.
    out = asyncio.run(k.push_scope("s", to))
    assert ("Agent", "stale") in out["removed"]
    assert to.deletes == []
    # With prune: stale is deleted.
    out2 = asyncio.run(k.push_scope("s", to, prune=True))
    assert ("delete", "Agent", "stale") in out2["applied"]
    assert ("Agent", "stale") in to.deletes


def test_authored_only_filters_runtime_kinds():
    # An Evidence (runtime artifact) in the source must NOT be pushed under
    # authored-only; a Agent must.
    frm = _FromSource([
        _agent("a", "hi"),
        {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Evidence",
         "metadata": {"name": "run-1"}, "spec": {"suite": "x"}},
    ])
    to = _ToSource([])
    k = _kernel(frm)
    artifact = {kp.kind for kp in k._kinds.values() if getattr(kp, "is_runtime_artifact", False)}
    include = lambda raw: raw.get("kind") not in artifact  # noqa: E731
    out = asyncio.run(k.push_scope("s", to, include=include))
    assert ("write", "Agent", "a") in out["applied"]
    assert not any(kind == "Evidence" for _, kind, _ in out["applied"])
