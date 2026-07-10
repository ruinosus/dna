"""s-sourceport-contract-cleanup — SourceCapabilities conformance.

Adapters now DECLARE their capabilities explicitly (a literal
``SourceCapabilities`` returned by ``capabilities()``); the kernel consults
:func:`source_capabilities` — never ``hasattr``/``inspect``. To keep the
declarations honest, this suite asserts, for EVERY in-repo adapter:

    declared == derive_capabilities(adapter)   # reflection oracle

so a declaration can't lie about what the adapter actually implements
(the old dicts drifted precisely because nothing pinned them to reality).

Also covered:
  - the deprecated reflection fallback for external adapters that don't
    declare (DeprecationWarning + correct derivation);
  - memoization semantics of :func:`source_capabilities`;
  - :func:`write_kwarg_support` reading the declaration (not reflecting).
"""
from __future__ import annotations

import warnings

import pytest

from dna.adapters.filesystem.composite import CompositeFilesystemSource
from dna.adapters.filesystem.source import FilesystemSource
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.adapters.sqlalchemy_ import SqlAlchemySource
from dna.kernel.capabilities import (
    DELETE_OPTIONAL_KWARGS,
    SAVE_OPTIONAL_KWARGS,
    SourceCapabilities,
    derive_capabilities,
    source_capabilities,
    write_kwarg_support,
)

# (id, factory) — SqlAlchemySource enters once per dialect: capabilities are
# declared per-instance (the pg row uses an unreachable DSN; the engine is
# lazy, so declaration honesty is checked with no server).
_ADAPTERS = [
    ("FilesystemSource",
     lambda tmp: FilesystemSource(tmp)),
    ("FilesystemWritableSource",
     lambda tmp: FilesystemWritableSource(tmp)),
    ("CompositeFilesystemSource",
     lambda tmp: CompositeFilesystemSource(tmp)),
    ("SqlAlchemySource[sqlite]",
     lambda tmp: SqlAlchemySource(f"sqlite+aiosqlite:///{tmp}/caps.sqlite3")),
    ("SqlAlchemySource[postgres]",
     lambda tmp: SqlAlchemySource("postgresql+asyncpg://u:p@nowhere.invalid/db")),
]
_ADAPTER_IDS = [i for i, _ in _ADAPTERS]
_ADAPTER_FACTORIES = [f for _, f in _ADAPTERS]


def _make(factory, tmp_path):
    """Cheap instances — no I/O at construction for any of them."""
    return factory(tmp_path)


# ---------------------------------------------------------------------------
# Declaration honesty: declared literal == reflection oracle
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("factory", _ADAPTER_FACTORIES, ids=_ADAPTER_IDS)
def test_declared_capabilities_match_reflection_oracle(factory, tmp_path):
    src = _make(factory, tmp_path)
    declared = src.capabilities()
    assert isinstance(declared, SourceCapabilities)
    oracle = derive_capabilities(src, label=declared.source)
    assert declared == oracle, (
        f"{type(src).__name__} declara capabilities que divergem do que o "
        f"adapter realmente implementa:\n  declared: {declared}\n  oracle:   {oracle}"
    )


@pytest.mark.parametrize("factory", _ADAPTER_FACTORIES, ids=_ADAPTER_IDS)
def test_declared_kwargs_within_port_vocabulary(factory, tmp_path):
    caps = _make(factory, tmp_path).capabilities()
    assert caps.write_kwargs <= SAVE_OPTIONAL_KWARGS
    assert caps.delete_kwargs <= DELETE_OPTIONAL_KWARGS


# ---------------------------------------------------------------------------
# source_capabilities — declared-first accessor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("factory", _ADAPTER_FACTORIES, ids=_ADAPTER_IDS)
def test_source_capabilities_uses_declaration_without_warning(factory, tmp_path):
    src = _make(factory, tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        caps = source_capabilities(src)
    assert caps == src.capabilities()


def test_source_capabilities_memoizes_on_instance(tmp_path):
    src = FilesystemWritableSource(tmp_path)
    first = source_capabilities(src)
    second = source_capabilities(src)
    assert first is second
    assert getattr(src, "_dna_source_capabilities") is first


def test_undeclared_adapter_falls_back_to_derivation_with_warning():
    """External adapters that predate the declaration contract keep
    working: reflection-derived capabilities + a DeprecationWarning."""

    class _LegacyExternalSource:
        async def load_all(self, scope, readers=None):
            return []

        async def save_document(self, scope, kind, name, raw, author=None):
            return "1"

        async def delete_document(self, scope, kind, name):
            return None

    with pytest.warns(DeprecationWarning, match="does not declare SourceCapabilities"):
        caps = source_capabilities(_LegacyExternalSource())
    assert caps.source == "_LegacyExternalSource"
    assert caps.granular is False
    assert caps.granular_list is False
    assert caps.granular_one is False
    assert caps.query_pushdown is False
    assert caps.write_kwargs == frozenset({"author"})
    assert caps.delete_kwargs == frozenset()
    assert caps.tenant_layer_writes is False


def test_legacy_dict_capabilities_degrade_to_derivation():
    """A source whose capabilities() still returns the pre-dataclass dict
    is treated as undeclared (derivation fallback), never crashes."""

    class _DictCapsSource:
        def capabilities(self):
            return {"drafts": True}

        async def load_all(self, scope, readers=None):
            return []

    caps = source_capabilities(_DictCapsSource())
    assert isinstance(caps, SourceCapabilities)
    assert caps.drafts is False  # derived (no load_drafts/publish), dict ignored


# ---------------------------------------------------------------------------
# write_kwarg_support — now a declaration read
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "factory", _ADAPTER_FACTORIES[1:], ids=_ADAPTER_IDS[1:],
)  # every writable adapter (all but the read-only FilesystemSource)
def test_write_kwarg_support_reads_declaration(factory, tmp_path):
    src = _make(factory, tmp_path)
    ws = write_kwarg_support(src)
    assert ws.author and ws.tenant and ws.layer_save
    assert ws.tenant_delete and ws.layer_delete
    assert ws.write_class and ws.version_retention
