"""Shared pytest fixtures for CLI tests.

CLI tests use Click's CliRunner — they invoke commands in-process
(no subprocess overhead), capture stdout/stderr, and exit codes.

Tests scope:
- dna auth login / whoami / logout / print-token / internal-token
  (the Phase E auth surface)
- Anything else gets added when it bites in regression.
"""
from __future__ import annotations

import contextlib
import os
import socket
import threading
import time
from collections.abc import Iterator

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


# --- requires_postgres gate (mirror of packages/sdk-py/tests/conftest.py) ---
#
# The durable quota store is only meaningfully testable against a real
# Postgres: what it exists to guarantee (a count that survives a restart and
# is shared by concurrent replicas) is a property of the DATABASE, not of the
# Python. Same DSN env vars the SDK's Postgres tests read.


def pg_dsn() -> str:
    for var in ("DATABASE_URL", "DNA_PG_TEST_URL", "DNA_PG_TEST_DSN"):
        dsn = os.environ.get(var)
        if dsn:
            return dsn
    return ""


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_network: skip unless outbound network is available "
        "(and DNA_OFFLINE is unset — see tests/conftest.py)",
    )
    config.addinivalue_line(
        "markers",
        "requires_postgres: skip unless a Postgres DSN is set "
        "(DATABASE_URL / DNA_PG_TEST_URL / DNA_PG_TEST_DSN — see tests/conftest.py)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if item.get_closest_marker("requires_network") and not _network_available():
            item.add_marker(pytest.mark.skip(
                reason="no network / GitHub access (or DNA_OFFLINE=1 set)",
            ))
        if item.get_closest_marker("requires_postgres") and not pg_dsn():
            item.add_marker(pytest.mark.skip(
                reason="no Postgres DSN (DATABASE_URL / DNA_PG_TEST_URL / "
                       "DNA_PG_TEST_DSN) set",
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


# --- MCP HTTP harness (transport + auth stories) ---------------------------
#
# Run a built FastMCP server over a REAL Streamable-HTTP socket (uvicorn on a
# free port, background thread, clean shutdown), so the remote-transport + auth
# stories are proven end-to-end through the wire — exactly what a remote/web MCP
# client does — not just via the in-memory client.


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_port(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with contextlib.suppress(OSError):
            with socket.create_connection((host, port), timeout=0.5):
                return
        time.sleep(0.05)
    raise RuntimeError(f"HTTP server never came up on {host}:{port}")


@contextlib.contextmanager
def serve_http(
    server, host: str = "127.0.0.1", path: str = "/mcp", port: int | None = None
) -> Iterator[str]:
    """Serve ``server`` over Streamable HTTP on a free port; yield the endpoint URL.

    Uses ``uvicorn.Server`` over ``server.http_app()`` so shutdown is clean
    (``should_exit`` + join), leaving no orphan listener between tests. Pass an
    explicit ``port`` when the auth provider needs the public URL up front (PRM).
    """
    import uvicorn

    port = port or _free_port()
    app = server.http_app(path=path)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    uv = uvicorn.Server(config)
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    try:
        _wait_port(host, port)
        yield f"http://{host}:{port}{path}"
    finally:
        uv.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def http_server():
    """Expose ``serve_http`` as a fixture for tests that want the HTTP harness."""
    return serve_http


@pytest.fixture
def free_port():
    """A free localhost TCP port (for tests that need the URL before serving)."""
    return _free_port


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
