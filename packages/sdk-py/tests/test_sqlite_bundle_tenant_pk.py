"""s-sqlite-bundle-tenant-pk — bundle_entries PK includes tenant (migration v8).

Before v8 the PK was (scope, kind, name, entry_path), created before the
`tenant` column existed (ALTER can't add a column to a PK in SQLite). Two
tenants writing the same (scope, kind, name, entry_path) collided — the second
UPSERT overwrote the first. This brings SQLite to parity with Postgres, which
keys on the full 5-tuple.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from dna.adapters.sqlite import SqliteSource


@pytest_asyncio.fixture
async def source(tmp_path):
    src = SqliteSource(str(tmp_path / "tenant_pk.db"))
    await src.connect()
    yield src
    await src.close()


class TestTenantBundlePk:
    @pytest.mark.asyncio
    async def test_two_tenants_same_entry_do_not_collide(self, source):
        """Two tenants write the same (scope, kind, name, entry_path) with
        different content → both rows persist; each reads back its own."""
        await source.write_bundle_entry(
            "shared-scope", "Skill", "greeter", "SKILL.md",
            "acme version", tenant="acme", kind="Skill",
        )
        await source.write_bundle_entry(
            "shared-scope", "Skill", "greeter", "SKILL.md",
            "globex version", tenant="globex", kind="Skill",
        )

        acme = await source.fetch_bundle_entry(
            "shared-scope", "Skill", "greeter", "SKILL.md",
            tenant="acme", kind="Skill",
        )
        globex = await source.fetch_bundle_entry(
            "shared-scope", "Skill", "greeter", "SKILL.md",
            tenant="globex", kind="Skill",
        )

        assert acme == b"acme version"
        assert globex == b"globex version"  # NOT overwritten by acme

    @pytest.mark.asyncio
    async def test_base_layer_and_tenant_overlay_coexist(self, source):
        """A base-layer entry (no tenant) and a tenant overlay of the same
        entry both persist; tenant read prefers overlay, falls back to base."""
        await source.write_bundle_entry(
            "shared-scope", "Skill", "greeter", "SKILL.md",
            "base version", kind="Skill",  # tenant=None → '' base row
        )
        await source.write_bundle_entry(
            "shared-scope", "Skill", "greeter", "SKILL.md",
            "acme overlay", tenant="acme", kind="Skill",
        )

        # acme sees its overlay
        assert await source.fetch_bundle_entry(
            "shared-scope", "Skill", "greeter", "SKILL.md",
            tenant="acme", kind="Skill",
        ) == b"acme overlay"
        # globex (no overlay) falls back to base
        assert await source.fetch_bundle_entry(
            "shared-scope", "Skill", "greeter", "SKILL.md",
            tenant="globex", kind="Skill",
        ) == b"base version"

    @pytest.mark.asyncio
    async def test_same_tenant_rewrite_is_idempotent_upsert(self, source):
        """Re-writing the same (5-tuple) updates in place — no duplicate rows."""
        await source.write_bundle_entry(
            "shared-scope", "Skill", "greeter", "SKILL.md",
            "v1", tenant="acme", kind="Skill",
        )
        await source.write_bundle_entry(
            "shared-scope", "Skill", "greeter", "SKILL.md",
            "v2", tenant="acme", kind="Skill",
        )
        assert await source.fetch_bundle_entry(
            "shared-scope", "Skill", "greeter", "SKILL.md",
            tenant="acme", kind="Skill",
        ) == b"v2"

    @pytest.mark.asyncio
    async def test_load_bundle_entries_is_tenant_scoped(self, source):
        """_load_bundle_entries filters to one tenant so overlay rows don't
        leak into a base-layer load (which would collide on entry_path)."""
        await source.write_bundle_entry(
            "shared-scope", "Skill", "greeter", "SKILL.md",
            "base", kind="Skill",
        )
        await source.write_bundle_entry(
            "shared-scope", "Skill", "greeter", "SKILL.md",
            "acme", tenant="acme", kind="Skill",
        )
        base_entries = await source._load_bundle_entries("shared-scope", "Skill", "greeter")
        acme_entries = await source._load_bundle_entries(
            "shared-scope", "Skill", "greeter", tenant="acme",
        )
        assert base_entries["SKILL.md"] == "base"
        assert acme_entries["SKILL.md"] == "acme"
