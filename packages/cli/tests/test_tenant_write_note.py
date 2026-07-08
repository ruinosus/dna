"""Tests for _tenant_write_note (i-020).

A write of a TENANTED Kind resolves its tenant from --tenant > DNA_TENANT >
unbound. The bug: the success line only surfaced the `--tenant` flag, so a
write driven by DNA_TENANT showed NO tenant — and a tenant not in
DNA_DEV_ALLOWED_TENANTS silently landed docs the Studio never browses.
This helper resolves the EFFECTIVE tenant and warns on the allow-list mismatch.
"""
from __future__ import annotations

from dna_cli.doc_cmd import _tenant_write_note


def test_flag_wins(monkeypatch) -> None:
    monkeypatch.delenv("DNA_TENANT", raising=False)
    monkeypatch.delenv("DNA_DEV_ALLOWED_TENANTS", raising=False)
    eff, warn = _tenant_write_note("acme")
    assert eff == "acme"
    assert warn is None


def test_env_used_when_no_flag(monkeypatch) -> None:
    monkeypatch.setenv("DNA_TENANT", "acme")
    monkeypatch.delenv("DNA_DEV_ALLOWED_TENANTS", raising=False)
    eff, warn = _tenant_write_note(None)
    assert eff == "acme"
    assert warn is None


def test_unbound_when_neither(monkeypatch) -> None:
    monkeypatch.delenv("DNA_TENANT", raising=False)
    monkeypatch.delenv("DNA_DEV_ALLOWED_TENANTS", raising=False)
    eff, warn = _tenant_write_note(None)
    assert eff is None
    assert warn is None


def test_warns_when_effective_not_in_allowed(monkeypatch) -> None:
    monkeypatch.delenv("DNA_TENANT", raising=False)
    monkeypatch.setenv("DNA_DEV_ALLOWED_TENANTS", "acme,innovec")
    eff, warn = _tenant_write_note("dev-tenant")
    assert eff == "dev-tenant"
    assert warn is not None
    assert "dev-tenant" in warn
    assert "DNA_DEV_ALLOWED_TENANTS" in warn


def test_no_warn_when_effective_in_allowed(monkeypatch) -> None:
    monkeypatch.setenv("DNA_DEV_ALLOWED_TENANTS", "acme,innovec")
    eff, warn = _tenant_write_note("acme")
    assert eff == "acme"
    assert warn is None


def test_no_warn_when_no_allowlist(monkeypatch) -> None:
    monkeypatch.delenv("DNA_DEV_ALLOWED_TENANTS", raising=False)
    eff, warn = _tenant_write_note("whatever")
    assert eff == "whatever"
    assert warn is None
