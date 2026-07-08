"""s-kernel-capability-protocols — capability detection on the kernel write path
is typed: BundleEntryReadable via isinstance, and write-kwarg support via a
memoized typed probe (no inspect.signature on every write).
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from dna.adapters.sqlite import SqliteSource
from dna.kernel.capabilities import (
    BundleEntryReadable,
    TenantAware,
    WriteKwargSupport,
    write_kwarg_support,
)


@pytest_asyncio.fixture
async def source(tmp_path):
    src = SqliteSource(str(tmp_path / "caps.db"))
    await src.connect()
    yield src
    await src.close()


class TestBundleEntryReadableIsInstance:
    def test_sqlite_is_bundle_entry_readable(self, source):
        # method-presence capability → expressed via isinstance, not hasattr
        assert isinstance(source, BundleEntryReadable)

    def test_plain_object_is_not(self):
        assert not isinstance(object(), BundleEntryReadable)


class TestWriteKwargSupport:
    def test_modern_adapter_reports_all_kwargs(self, source):
        ws = write_kwarg_support(source)
        assert isinstance(ws, WriteKwargSupport)
        assert ws.author is True
        assert ws.tenant is True
        assert ws.layer_save is True
        assert ws.tenant_delete is True
        assert ws.layer_delete is True

    def test_is_memoized_on_the_instance(self, source):
        first = write_kwarg_support(source)
        second = write_kwarg_support(source)
        # same frozen object returned — inspect.signature ran once
        assert first is second
        assert getattr(source, "_dna_write_kwarg_support") is first

    def test_legacy_adapter_without_tenant_kwarg(self):
        class LegacySource:
            async def save_document(self, scope, kind, name, raw, *, layer=None):
                return "1"

            async def delete_document(self, scope, kind, name, *, layer=None):
                return None

        ws = write_kwarg_support(LegacySource())
        assert ws.tenant is False
        assert ws.author is False
        assert ws.layer_save is True
        assert ws.tenant_delete is False

    def test_tenant_aware_protocol_matches_modern_adapter(self, source):
        # TenantAware is documentation + static typing; isinstance only confirms
        # the methods exist (it can't see the tenant kwarg — that's why the kernel
        # uses write_kwarg_support for the actual decision).
        assert isinstance(source, TenantAware)
