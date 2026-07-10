"""Shared pytest fixtures for CLI tests.

CLI tests use Click's CliRunner — they invoke commands in-process
(no subprocess overhead), capture stdout/stderr, and exit codes.

Tests scope:
- dna auth login / whoami / logout / print-token / internal-token
  (the Phase E auth surface)
- Anything else gets added when it bites in regression.
"""
from __future__ import annotations

import os
import socket

import pytest
from click.testing import CliRunner


# --- requires_network gate (mirror of packages/sdk-py/tests/conftest.py) ----
#
# ``DNA_OFFLINE=1`` forces the skip regardless of real connectivity — CI
# runners DO have network, but CI must never clone external repos
# (s-public-ci); the python workflow exports DNA_OFFLINE=1.

_NETWORK_CACHE: bool | None = None


def _network_available() -> bool:
    if os.environ.get("DNA_OFFLINE"):
        return False
    global _NETWORK_CACHE
    if _NETWORK_CACHE is None:
        try:
            conn = socket.create_connection(("github.com", 443), timeout=2)
            conn.close()
            _NETWORK_CACHE = True
        except OSError:
            _NETWORK_CACHE = False
    return _NETWORK_CACHE


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_network: skip unless outbound network is available "
        "(and DNA_OFFLINE is unset — see tests/conftest.py)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if item.get_closest_marker("requires_network") and not _network_available():
            item.add_marker(pytest.mark.skip(
                reason="no network / GitHub access (or DNA_OFFLINE=1 set)",
            ))


@pytest.fixture
def runner():
    """Click CliRunner — captures output + exit code for in-process invokes."""
    return CliRunner()


@pytest.fixture(autouse=True)
def _isolated_active_story(monkeypatch, tmp_path):
    """Point the active-story pointer at a per-test tmp file (autouse).

    ``dna sdlc story start`` writes ``.dna/active-story.txt`` at the
    enclosing REPO root even when the kernel session is faked — without
    this isolation, running the CLI suite repoints the developer's real
    active story, and with the git↔SDLC prepare-commit-msg hook installed
    that mis-stamps their next commits' ``Work-Item:`` trailer. Bit us
    live during s-sdlc-git-symbiosis: a ``story start s-noted`` test leaked
    into (and at one point got committed to) the repo pointer.

    Tests that need full control (the hook/hooks-CLI suites drive real
    tmp git repos) simply ``monkeypatch.delenv(DNA_ACTIVE_STORY_PATH)``.
    """
    monkeypatch.setenv(
        "DNA_ACTIVE_STORY_PATH", str(tmp_path / "test-active-story.txt"),
    )


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
