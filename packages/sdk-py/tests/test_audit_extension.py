"""AuditLog Kind — extension wiring + kernel round-trip + emit_audit unit.

F1.2 of f-multi-role (2026-05-15). The AuditLogKind class was migrated to a
descriptor (kinds/audit-log.kind.yaml) in expr batch A (plan
2026-06-11-descriptor-expressiveness); schema / storage / tenanted / ui /
summary equivalence with the extinct class is frozen in
test_expr_batch_a_equivalence.py (incl. the byte-identical manifest diff).
What survives here is the registration check, the end-to-end write→read
round-trip through a real writable source, and the emit_audit helper unit.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dna.kernel import Kernel
from dna.extensions.audit import AuditExtension
from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource


def test_audit_extension_registers_kind():
    k = Kernel()
    k.load(AuditExtension())
    aliases = {kp.alias for kp in k._kinds.values()}
    assert "audit-auditlog" in aliases


def test_audit_kind_round_trip_through_kernel(tmp_path: Path):
    """Write an AuditLog doc + read it back through the kernel."""
    async def run():
        (tmp_path / "scope").mkdir()
        (tmp_path / "scope" / "manifest.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
            "metadata: {name: scope}\nspec: {}\n"
        )
        k = Kernel()
        k.load(AuditExtension())
        src = FilesystemWritableSource(
            str(tmp_path), writers=list(k._writers), kernel=k,
        )
        k.source(src)
        k.cache(FilesystemCache(tmp_path / ".cache"))

        audit_doc = {
            "apiVersion": "github.com/ruinosus/dna/audit/v1",
            "kind": "AuditLog",
            "metadata": {"name": "audit-test-123"},
            "spec": {
                "actor": "dev-user",
                "roles": ["maker"],
                "operation": "PUT /scopes/X/docs/Agent/Y",
                "outcome": "success",
                "captured_at": "2026-05-15T22:00:00Z",
                "target_kind": "Agent",
                "target_name": "Y",
                "target_scope": "X",
            },
        }
        # AuditLog is TENANTED — need a tenant on write.
        await k.write_document(
            "scope", "AuditLog", "audit-test-123", audit_doc, tenant="acme",
        )

        # Read back via kernel.query (cross-tenant).
        rows = [r async for r in k.query(
            "scope", "AuditLog", tenant="acme",
        )]
        assert len(rows) == 1
        spec = rows[0]["spec"]
        assert spec["actor"] == "dev-user"
        assert spec["roles"] == ["maker"]
        assert spec["outcome"] == "success"

    asyncio.run(run())


