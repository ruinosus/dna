"""TenantKind (Phase A) — Kind registration + reader/writer round-trip.

Story `s-tenant-lifecycle-phase-a-kind-crud` (2026-05-25).
"""
from __future__ import annotations

import pytest

from dna.extensions.tenant import (
    TenantExtension, TenantKind, TenantReader, TenantWriter,
    validate_slug, PLATFORM_SCOPE,
)
from dna.kernel.bundle_handle import DictBundleHandle


# ── slug validation ──────────────────────────────────────────────────


def test_valid_slugs():
    for s in ["acme", "globex", "acme-corp", "a", "x-1-2-3", "lumi-prod"]:
        validate_slug(s)  # no raise


def test_invalid_slug_chars():
    for s in ["ACME", "acme_corp", "acme.corp", "açai", "a b"]:
        with pytest.raises(ValueError, match=r"\[a-z0-9-\]"):
            validate_slug(s)


def test_reserved_slugs():
    for s in ["_global", "_legacy", "_system", "_lib", ""]:
        with pytest.raises(ValueError, match="reserved"):
            validate_slug(s)


def test_slug_max_length():
    long_ok = "a" * 253
    validate_slug(long_ok)
    too_long = "a" * 254
    with pytest.raises(ValueError):
        validate_slug(too_long)


# ── KindPort surface ─────────────────────────────────────────────────


def test_tenant_kind_metadata():
    k = TenantKind()
    assert k.kind == "Tenant"
    assert k.alias == "tenant-tenant"
    assert k.api_version == "github.com/ruinosus/dna/tenant/v1"
    from dna.kernel.protocols import TenantScope
    assert k.scope == TenantScope.GLOBAL


def test_tenant_kind_schema_required_fields():
    schema = TenantKind().schema()
    assert schema is not None
    assert set(schema["required"]) == {"slug", "display_name", "owner_email", "status"}
    props = schema["properties"]
    assert "plan" in props
    assert props["plan"]["enum"] == ["free", "pro", "enterprise"]
    assert props["status"]["enum"] == ["active", "suspended", "deleted"]


def test_tenant_kind_describe_and_summary():
    k = TenantKind()
    class Doc:
        spec = {
            "slug": "acme", "display_name": "ACME Corp",
            "status": "active", "plan": "pro", "member_count_cached": 5,
        }
    doc = Doc()
    assert k.describe(doc) == "ACME Corp [active · pro]"
    summary = k.summary(doc)
    assert summary == {
        "slug": "acme", "display_name": "ACME Corp",
        "status": "active", "plan": "pro", "member_count": 5,
    }


# ── Reader + Writer round-trip ───────────────────────────────────────


def _sample_raw():
    return {
        "apiVersion": "github.com/ruinosus/dna/tenant/v1",
        "kind": "Tenant",
        "metadata": {"name": "acme"},
        "spec": {
            "slug": "acme",
            "display_name": "ACME Corp",
            "owner_email": "ops@acme.com",
            "status": "active",
            "plan": "pro",
            "created_at": "2026-05-25T20:00:00+00:00",
            "metadata": {"region": "br", "lgpd_consent": True},
        },
    }


def test_writer_emits_tenant_md_only_when_no_source_files():
    handle = DictBundleHandle("acme", {})
    TenantWriter().write(handle, _sample_raw())
    files = list(handle.iter_entries(recursive=True))
    assert files == ["TENANT.md"]
    content = handle.read_text("TENANT.md")
    assert "apiVersion: github.com/ruinosus/dna/tenant/v1" in content
    assert "slug: acme" in content
    assert "display_name: ACME Corp" in content


def test_reader_detect_matches_tenant_apiversion():
    handle = DictBundleHandle("acme", {})
    TenantWriter().write(handle, _sample_raw())
    assert TenantReader().detect(handle) is True


def test_reader_detect_rejects_other_apiversion():
    handle = DictBundleHandle("foo", {
        "TENANT.md": "---\napiVersion: github.com/ruinosus/dna/lesson/v1\nkind: Lesson\n---\n",
    })
    assert TenantReader().detect(handle) is False


def test_reader_round_trips_raw_dict():
    handle = DictBundleHandle("acme", {})
    raw = _sample_raw()
    TenantWriter().write(handle, raw)
    read_back = TenantReader().read(handle)
    assert read_back["apiVersion"] == "github.com/ruinosus/dna/tenant/v1"
    assert read_back["kind"] == "Tenant"
    assert read_back["metadata"]["name"] == "acme"
    assert read_back["spec"]["slug"] == "acme"
    assert read_back["spec"]["display_name"] == "ACME Corp"
    assert read_back["spec"]["plan"] == "pro"
    assert read_back["spec"]["metadata"]["region"] == "br"


# ── Extension registers correctly ────────────────────────────────────


def test_extension_registers_both_kinds_reader_writer():
    """Phase B added TenantMembership alongside Tenant — extension
    registers both kinds + their reader/writer pairs."""
    captured: dict[str, list] = {"kinds": [], "readers": [], "writers": []}
    class FakeKernel:
        def kind(self, k): captured["kinds"].append(k)
        def reader(self, r): captured["readers"].append(r)
        def writer(self, w): captured["writers"].append(w)
    TenantExtension().register(FakeKernel())
    kinds = sorted([k.kind for k in captured["kinds"]])
    assert kinds == ["Tenant", "TenantMembership"]
    assert len(captured["readers"]) == 2
    assert len(captured["writers"]) == 2


def test_make_membership_name_is_stable_and_safe():
    from dna.extensions.tenant import make_membership_name
    assert make_membership_name("acme", "john@acme.com") == "acme--john-at-acme-com"
    # Idempotent
    assert (
        make_membership_name("acme", "John@Acme.COM")
        == make_membership_name("acme", "john@acme.com")
    )
    # Funky chars sanitized
    name = make_membership_name("acme", "x+y@a.b.c")
    assert all(c.isalnum() or c == "-" for c in name)


def test_platform_scope_constant():
    assert PLATFORM_SCOPE == "_lib"
