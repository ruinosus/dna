"""Shared pytest fixtures for CLI tests.

CLI tests use Click's CliRunner — they invoke commands in-process
(no subprocess overhead), capture stdout/stderr, and exit codes.

Tests scope:
- dna auth login / whoami / logout / print-token / internal-token
  (the Phase E auth surface)
- Anything else gets added when it bites in regression.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    """Click CliRunner — captures output + exit code for in-process invokes."""
    return CliRunner()


@pytest.fixture
def isolated_keyring(monkeypatch, tmp_path):
    """Point DeviceCodeCredentials cache at a tmp dir + isolate keyring.

    Prevents tests from touching the real OS keyring (Keychain on macOS,
    Credential Manager on Windows, Secret Service on Linux).

    Sets DNA_TOKEN_CACHE_DIR → tmp_path; also disables the keyring backend
    so the file-fallback path is exercised deterministically.
    """
    monkeypatch.setenv("DNA_TOKEN_CACHE_DIR", str(tmp_path))
    # Disable keyring discovery — forces file fallback.
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Null")
    yield tmp_path
