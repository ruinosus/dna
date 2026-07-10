"""WritableSourcePort — the UNIFIED write/read contract conformance.

Historia: F2 D2 (s-f2-recordstore-port) declarou um ``RecordStorePort``
que era uma cópia quase literal do contrato writable ("FORMALIZA o
contrato que os sources writáveis já satisfazem"). O
s-sourceport-contract-cleanup unificou os dois: ``WritableSourcePort`` É
o contrato único (put=save_document, delete=delete_document, query,
count; ``search`` vive no RecordSearchProvider registrado no kernel).
``RecordStorePort`` virou alias deprecado.

Este arquivo era o conformance test que mantinha as duas portas em
sincronia — agora é o conformance test do contrato único, nas mesmas
camadas de antes:

- ``isinstance`` com ``@runtime_checkable`` — valida NOMES de membros;
- asserts de assinatura via ``inspect.signature`` — paridade REAL de
  parâmetros (precedente: ``test_query_signature_is_correct`` em
  ``test_sourceport_query_protocol.py``);
- coroutine-ness (async def vs async generator).

``CompositeFilesystemSource`` é OBRIGATÓRIA aqui: é o caminho da
distribuição community. ``SqlAlchemySource`` é o único adapter SQL
(ambos os dialetos, mesma classe) desde s-retire-raw-sql-adapters.
"""
from __future__ import annotations

import inspect

import pytest

from dna.adapters.filesystem.composite import CompositeFilesystemSource
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.adapters.sqlalchemy_ import SqlAlchemySource
from dna.kernel.protocols import (
    SourcePort,
    WritableSourcePort,
)

_ADAPTERS = [
    SqlAlchemySource,
    FilesystemWritableSource,
    CompositeFilesystemSource,
]
_PORT_METHODS = ["save_document", "delete_document", "query", "count"]


def _make(cls, tmp_path):
    """Cheap instances — no I/O at construction for any of the three."""
    if cls is SqlAlchemySource:
        # engine creation is lazy — no file/server touched here
        return cls(f"sqlite+aiosqlite:///{tmp_path / 'port.sqlite3'}")
    return cls(tmp_path)  # FS roots; empty dir is a valid (scopeless) tree


def _params(fn) -> list[tuple[str, inspect._ParameterKind, object]]:
    """(name, kind, default) per parameter — annotations are NOT compared
    (the Protocol is typed, adapters are deliberately untyped)."""
    return [
        (n, p.kind, p.default)
        for n, p in inspect.signature(fn).parameters.items()
        if n != "self"
    ]


# ---------------------------------------------------------------------------
# isinstance conformance (runtime_checkable → member NAMES)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", _ADAPTERS, ids=lambda c: c.__name__)
def test_adapter_satisfies_writable_source_port(cls, tmp_path):
    assert isinstance(_make(cls, tmp_path), WritableSourcePort)


def test_runtime_checkable_rejects_non_conforming():
    """Sanity: the isinstance check is not a tautology — an object missing
    ``count`` fails it."""

    class _NoCount:
        supports_readers = False

        async def load_bootstrap_docs(self, *a, **kw): ...
        async def load_all(self, *a, **kw): ...
        async def resolve_ref(self, *a, **kw): ...
        async def load_layer(self, *a, **kw): ...
        async def close(self): ...
        async def list_doc_refs(self, *a, **kw): ...
        async def load_one(self, *a, **kw): ...
        async def save_document(self, *a, **kw): ...
        async def delete_document(self, *a, **kw): ...
        async def save_manifest(self, *a, **kw): ...
        async def list_versions(self, *a, **kw): ...
        async def get_version(self, *a, **kw): ...
        async def publish(self, *a, **kw): ...
        async def load_drafts(self, *a, **kw): ...
        async def list_scopes(self): ...
        def capabilities(self): ...
        def query(self, *a, **kw): ...

    assert not isinstance(_NoCount(), WritableSourcePort)


# ---------------------------------------------------------------------------
# Signature conformance (inspect.signature → parameter parity)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", _ADAPTERS, ids=lambda c: c.__name__)
@pytest.mark.parametrize("method", _PORT_METHODS)
def test_adapter_signature_matches_port(cls, method):
    expected = _params(getattr(WritableSourcePort, method))
    actual = _params(getattr(cls, method))
    assert actual == expected, (
        f"{cls.__name__}.{method} diverge do WritableSourcePort:\n"
        f"  port:    {expected}\n  adapter: {actual}"
    )


def test_read_half_signatures_come_from_source_port():
    """``query``/``count`` são herdados de ``SourcePort`` — o contrato
    unificado não pode divergir da metade de leitura."""
    assert _params(WritableSourcePort.query) == _params(SourcePort.query)
    assert _params(WritableSourcePort.count) == _params(SourcePort.count)


# ---------------------------------------------------------------------------
# Coroutine-ness conformance (async vs async-generator)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", _ADAPTERS, ids=lambda c: c.__name__)
@pytest.mark.parametrize("method", ["save_document", "delete_document", "count"])
def test_adapter_method_is_coroutine(cls, method):
    """`save_document`, `delete_document` and `count` must be plain coroutine
    functions (``async def``, not async generators)."""
    fn = getattr(cls, method)
    assert inspect.iscoroutinefunction(fn), (
        f"{cls.__name__}.{method} deve ser coroutine function (async def), "
        f"mas é: {type(fn)}"
    )


@pytest.mark.parametrize("cls", _ADAPTERS, ids=lambda c: c.__name__)
def test_adapter_query_is_async_gen(cls):
    """`query` must be an async generator function (``async def … yield``)."""
    fn = getattr(cls, "query")
    assert inspect.isasyncgenfunction(fn), (
        f"{cls.__name__}.query deve ser async generator function (async def … yield), "
        f"mas é: {type(fn)}"
    )


def test_port_query_options_are_keyword_only():
    """Precedente test_query_signature_is_correct: as opções de query/count
    são keyword-only com default None (put: tenant/layer/write_class)."""
    qp = inspect.signature(WritableSourcePort.query).parameters
    for opt in ("filter", "projection", "limit", "offset", "order_by", "tenant"):
        assert qp[opt].kind == inspect.Parameter.KEYWORD_ONLY
        assert qp[opt].default is None
    cp = inspect.signature(WritableSourcePort.count).parameters
    for opt in ("filter", "group_by", "tenant"):
        assert cp[opt].kind == inspect.Parameter.KEYWORD_ONLY
        assert cp[opt].default is None
    sp = inspect.signature(WritableSourcePort.save_document).parameters
    assert sp["write_class"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sp["write_class"].default == "substantive"


# ---------------------------------------------------------------------------
# Deprecated alias
# ---------------------------------------------------------------------------

def test_record_store_port_is_deprecated_alias():
    """``RecordStorePort`` importa com DeprecationWarning e É o
    ``WritableSourcePort`` (reexport, não uma porta paralela)."""
    import dna.kernel.protocols as protocols

    with pytest.warns(DeprecationWarning, match="RecordStorePort is deprecated"):
        alias = protocols.RecordStorePort
    assert alias is WritableSourcePort

    with pytest.warns(DeprecationWarning):
        from dna.kernel.protocols import RecordStorePort  # noqa: PLC0415
    assert RecordStorePort is WritableSourcePort


def test_unknown_module_attr_still_raises():
    import dna.kernel.protocols as protocols

    with pytest.raises(AttributeError):
        protocols.DoesNotExist  # noqa: B018
