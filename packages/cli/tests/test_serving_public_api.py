"""Tests for dna_cli.serving — the PUBLIC serving surface (Spec 2 of the
dna-cloud apps/ monolith: the SDK stops being a production endpoint and instead
exposes the primitives a host composes its own server from).

  • the public names resolve to the real factories/helpers (mutation: an export
    dropped or rewired → dies);
  • the convenience `serve` commands warn they are deprecated for production
    (mutation: the warning removed → dies).
"""

from __future__ import annotations

import dna_cli.serving as serving
from dna_cli import _mcp_server, _rest_api, _mcp_auth, _mcp_quota


def test_public_names_resolve_to_the_real_primitives():
    # The factories a host runs.
    assert serving.build_mcp_server is _mcp_server.build_server
    assert serving.build_rest_app is _rest_api.build_app
    # The auth providers a host wires in.
    assert serving.jwt_provider_from_env is _mcp_auth.jwt_provider_from_env
    assert serving.azure_provider_from_env is _mcp_auth.azure_provider_from_env
    assert serving.build_auth_from_config is _mcp_auth.build_auth_from_config
    # The metering counter a host spends against.
    assert serving.quota_store_from_env is _mcp_quota.store_from_env


def test_all_is_the_complete_public_surface():
    expected = {
        "build_mcp_server",
        "build_rest_app",
        "build_auth_from_config",
        "azure_provider_from_env",
        "jwt_provider_from_env",
        "quota_store_from_env",
    }
    assert set(serving.__all__) == expected
    for name in expected:
        assert hasattr(serving, name), name


# The deprecation is asserted at the SOURCE (a behavioral CliRunner invocation
# would actually run/block the server). The mutation intent holds: remove the
# echo from the serve body and these die.
import inspect


def test_mcp_serve_http_warns_it_is_deprecated_for_production():
    from dna_cli.mcp_cmd import serve as mcp_serve

    src = inspect.getsource(mcp_serve.callback)
    assert 'DEPRECATED for production' in src
    # Gated on non-stdio: the local stdio (library) use must NOT warn.
    assert 'if transport != "stdio":' in src


def test_api_serve_warns_it_is_deprecated_for_production():
    from dna_cli.api_cmd import serve as api_serve

    src = inspect.getsource(api_serve.callback)
    assert 'DEPRECATED for production' in src
    assert 'build_rest_app' in src  # the warning points hosts at the public factory


# ── build_rest_app(auth="config") is FILE-FREE: providers come from the CALLER ──
# The core builder does NO config-file I/O — reading a dna.config.yaml is the CLI's
# job. An in-process host (dna-cloud) passes providers built from its OWN env via
# `auth_providers=`. These lock that seam (mutation: the core falls back to a file,
# or drops the auth_providers path → dies).
import pytest


def test_build_rest_app_config_builds_from_auth_providers_without_a_file(tmp_path, monkeypatch):
    from fastapi import FastAPI

    monkeypatch.chdir(tmp_path)  # a dna.config.yaml here would prove file-reading
    app = serving.build_rest_app(
        auth="config",
        auth_providers=[
            {
                "type": "entra",
                "name": "entra-multitenant",
                "issuer": "https://login.microsoftonline.com/organizations/v2.0",
                "audience": "aud-x",
                "tenant_claim": "tid",
            }
        ],
    )
    assert isinstance(app, FastAPI)  # verifier built from the mappings, no exception
    assert not (tmp_path / "dna.config.yaml").exists()  # the core touched no file


def test_build_rest_app_config_without_providers_or_verifier_fails_loud(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no dna.config.yaml to silently fall back to
    with pytest.raises(RuntimeError, match="auth_providers"):
        serving.build_rest_app(auth="config")


def test_build_rest_app_config_parses_provider_mappings(tmp_path, monkeypatch):
    # A malformed mapping flows through parse_auth_providers → ValueError, proving
    # the auth_providers really drive provider parsing (not silently ignored).
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        serving.build_rest_app(auth="config", auth_providers=[{"issuer": "https://i"}])  # no type
