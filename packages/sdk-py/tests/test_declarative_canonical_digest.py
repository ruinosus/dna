"""i-declarative-canonical-digest — a descriptor (F3) Kind must expose the SAME
``canonical_digest`` contract as a hand-written record Kind, so ``dna source
push``/``diff`` (source_sync's ``digest_manifest``) work on scopes made of
descriptor Kinds — the FS→Postgres replicate/seed path the hosted console needs.

Regression: ``DeclarativeKindPort`` had ``VOLATILE_SPEC_FIELDS`` but no
``canonical_digest`` method, so ``source_sync.py`` raised
``AttributeError: 'DeclarativeKindPort' object has no attribute
'canonical_digest'`` on every descriptor Kind. The port now shares KindBase's
canonical implementation verbatim (same function objects). Spike: sp-postgres-substrate.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from dna.kernel import Kernel
from dna.kernel.kinds.base import KindBase
from dna.kernel.meta import DeclarativeKindPort


def _doc(kind, name, spec):
    return SimpleNamespace(kind=kind, name=name, spec=spec)


def _descriptor_port(kind_name):
    """A live DeclarativeKindPort for a builtin descriptor Kind."""
    k = Kernel.auto()
    port = k.kind_port_for(kind_name)
    assert isinstance(port, DeclarativeKindPort), (
        f"{kind_name} should be descriptor-backed (F3), got {type(port).__name__}"
    )
    return port


# --- the crash it fixes ------------------------------------------------------

def test_descriptor_kind_has_canonical_digest_no_attributeerror():
    """The exact regression: calling canonical_digest on a descriptor Kind used
    to raise AttributeError (killing source push/diff). It now returns a hash."""
    port = _descriptor_port("IntelSource")
    digest = port.canonical_digest(
        _doc("IntelSource", "watch-x", {"cadence": "daily", "updated_at": "T1"})
    )
    assert isinstance(digest, str) and len(digest) == 64  # sha256 hex


def test_descriptor_digest_stable_across_calls():
    port = _descriptor_port("Project")
    doc = _doc("Project", "acme-dev", {"board_scope": "acme-development",
                                       "repo_refs": ["a", "b"]})
    assert port.canonical_digest(doc) == port.canonical_digest(doc)


# --- byte-identical to the hand-written KindBase contract --------------------

def test_descriptor_digest_identical_to_kindbase():
    """A descriptor Kind must digest byte-identically to the equivalent
    hand-written record Kind (KindBase) — otherwise source-sync would MISS or
    DUPLICATE changes across the FS↔Postgres boundary. Proven by pinning a
    reference KindBase to the SAME kind + VOLATILE_SPEC_FIELDS."""
    port = _descriptor_port("IntelSource")

    class _Ref(KindBase):
        api_version = "ref/v1"
        kind = "IntelSource"
        alias = "intel-source"
        VOLATILE_SPEC_FIELDS = port.VOLATILE_SPEC_FIELDS

    ref = _Ref()
    spec = {"cadence": "daily", "threshold": 0.7, "pirs": ["x", "y"],
            "updated_at": "2026-07-11T00:00:00Z", "version": 5}
    doc = _doc("IntelSource", "watch-x", spec)
    assert port.canonical_digest(doc) == ref.canonical_digest(doc)


def test_descriptor_digest_ignores_volatile_and_transport():
    """Same content, different volatile stamps / transport source_files → same
    digest (the invariant source-sync relies on to detect 'in sync')."""
    port = _descriptor_port("IntelSource")
    base = {"cadence": "daily", "threshold": 0.5}
    d1 = port.canonical_digest(_doc("IntelSource", "a",
                                    {**base, "updated_at": "T1", "version": 1}))
    d2 = port.canonical_digest(_doc("IntelSource", "a",
                                    {**base, "updated_at": "T9", "version": 42,
                                     "source_files": {"x.md": "..."}}))
    assert d1 == d2


def test_descriptor_digest_sensitive_to_content():
    port = _descriptor_port("IntelSource")
    d1 = port.canonical_digest(_doc("IntelSource", "a", {"cadence": "daily"}))
    d2 = port.canonical_digest(_doc("IntelSource", "a", {"cadence": "weekly"}))
    assert d1 != d2


# --- end-to-end: digest_manifest over a descriptor-Kind scope ----------------

class _FakeSource:
    """Minimal CORE SourcePort surface serving one descriptor-Kind doc, so
    kernel.digest_manifest (the source_sync path that CRASHED) runs end-to-end."""

    supports_readers = False

    def __init__(self, docs):
        self._docs = docs

    async def load_bootstrap_docs(self, scope, *, tenant=None):
        return []

    async def load_all(self, scope, readers=None):
        return list(self._docs)

    async def load_layer(self, scope, layer_id, layer_value, readers=None):
        return []

    async def resolve_ref(self, scope, ref):
        return ref

    async def close(self):
        return None


def test_digest_manifest_over_descriptor_kind_scope():
    """The full source_sync path (dna source push/diff calls this) over a scope
    whose docs are backed by a descriptor Kind — used to crash with
    AttributeError, now yields a stable {(kind,name): digest} manifest."""
    raw = {
        "apiVersion": "github.com/ruinosus/dna/intel/v1",
        "kind": "IntelSource",
        "metadata": {"name": "watch-repo"},
        "spec": {"cadence": "daily", "threshold": 0.7,
                 "updated_at": "T1", "version": 3},
    }
    k = Kernel.auto()
    k.source(_FakeSource([raw]))
    manifest = asyncio.run(k.digest_manifest("intel-scope"))
    assert set(manifest) == {("IntelSource", "watch-repo")}
    assert len(manifest[("IntelSource", "watch-repo")]) == 64
    # deterministic: a second run over the same content matches
    k2 = Kernel.auto()
    k2.source(_FakeSource([raw]))
    assert asyncio.run(k2.digest_manifest("intel-scope")) == manifest
