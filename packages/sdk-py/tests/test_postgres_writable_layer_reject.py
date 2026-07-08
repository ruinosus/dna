"""Phase 8a: PostgresSource is now tenant-aware.

Pre-Phase-8a this file asserted ``NotImplementedError`` on layer writes.
After Phase 8a, the adapter accepts ``tenant=`` kwarg natively and
back-compat-translates ``layer=("tenant", X)`` into ``tenant=X``. Layer
keys other than ``"tenant"`` still raise — the schema does not yet
support arbitrary multi-axis layer overlays in Postgres.

These signature tests stay as a safety net so the kernel's
``inspect.signature`` dispatch keeps doing the right thing.
"""
from __future__ import annotations

import inspect

import pytest


def test_postgres_save_document_accepts_tenant_kwarg():
    from dna.adapters.postgres.source import PostgresSource
    sig = inspect.signature(PostgresSource.save_document)
    assert "tenant" in sig.parameters
    assert sig.parameters["tenant"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["tenant"].default is None


def test_postgres_save_document_keeps_layer_kwarg_for_backcompat():
    """Kernel may still pass layer=… for legacy adapters; we accept it."""
    from dna.adapters.postgres.source import PostgresSource
    sig = inspect.signature(PostgresSource.save_document)
    assert "layer" in sig.parameters
    assert sig.parameters["layer"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["layer"].default is None


def test_postgres_delete_document_accepts_tenant_kwarg():
    from dna.adapters.postgres.source import PostgresSource
    sig = inspect.signature(PostgresSource.delete_document)
    assert "tenant" in sig.parameters
    assert sig.parameters["tenant"].default is None


def test_postgres_save_document_raises_on_non_tenant_layer():
    """Only layer_id='tenant' is folded; other axes still raise."""
    import asyncio
    from dna.adapters.postgres.source import PostgresSource
    src = PostgresSource.__new__(PostgresSource)
    raw = {"apiVersion": "x", "kind": "K", "metadata": {"name": "n"}, "spec": {}}
    with pytest.raises(NotImplementedError, match="layer.*not supported"):
        asyncio.run(src.save_document("s", "K", "n", raw, layer=("region", "us-east")))
