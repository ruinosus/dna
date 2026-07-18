"""P3 Task 10 — the Google (Lane B data) port registers into the act-on-behalf
registry when the ``calendar`` group is active AND the Google OAuth client creds
are present. The per-user consent flow / refresh-token store stays deferred (the
port's ``refresh_lookup`` default → an honest capability gap), so a Google
identity gets "no consented credential yet", never a crash.
"""
from __future__ import annotations

import pytest

from dna_cli.graph._config import GraphConfig, GraphGroup
from dna_cli.act_on_behalf._server import build_provider_registry


def _cfg_calendar_active() -> GraphConfig:
    return GraphConfig(
        enabled=True,
        client_id_env="MS_CLIENT_ID",
        credential_env="MS_SECRET",
        groups={"calendar": GraphGroup(
            name="calendar", enabled=True,
            scopes=("https://graph.microsoft.com/Calendars.Read",),
        )},
    )


def test_google_registered_when_creds_present(monkeypatch):
    monkeypatch.setenv("DNA_MCP_GOOGLE_CLIENT_ID", "gid.apps.googleusercontent.com")
    monkeypatch.setenv("DNA_MCP_GOOGLE_CLIENT_SECRET", "GOCSPX-secret")
    registry = build_provider_registry(_cfg_calendar_active())
    assert "microsoft" in registry
    assert "google" in registry
    assert registry["google"].provider == "google"
    assert registry["google"].supports("calendar")


def test_google_absent_without_creds(monkeypatch):
    monkeypatch.delenv("DNA_MCP_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("DNA_MCP_GOOGLE_CLIENT_SECRET", raising=False)
    registry = build_provider_registry(_cfg_calendar_active())
    assert "microsoft" in registry
    assert "google" not in registry  # fail-closed: no creds ⇒ not registered


def test_google_without_consent_store_is_honest_gap(monkeypatch):
    """With no refresh-token store wired (the deferred piece), the Google port
    reports an honest capability gap — never a crash, never a leak. Uses
    ``asyncio.run`` (not the pytest-asyncio marker, which CI's cli env lacks)."""
    import asyncio

    from dna_cli.act_on_behalf._port import ActContext, ActOnBehalfUnavailable

    monkeypatch.setenv("DNA_MCP_GOOGLE_CLIENT_ID", "gid")
    monkeypatch.setenv("DNA_MCP_GOOGLE_CLIENT_SECRET", "sec")
    port = build_provider_registry(_cfg_calendar_active())["google"]
    ctx = ActContext(provider_hint="google", tenant="", subject="google-sub-1")

    async def _call():
        await port.credential_for(
            ctx, "calendar", ["https://www.googleapis.com/auth/calendar.readonly"],
        )

    with pytest.raises(ActOnBehalfUnavailable):
        asyncio.run(_call())
