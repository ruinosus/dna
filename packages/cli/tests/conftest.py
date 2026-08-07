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
    """Mirror of packages/sdk-py/tests/conftest.py::_network_available, including
    its retry — see the full rationale there (perf/testes-em-paralelo).

    Short version: one 2 s connect whose negative result was cached for the life
    of the process is not safe under xdist. Every worker probes, a dozen
    handshakes race, and one that misses the deadline turns that worker's real
    ``requires_network`` tests into SKIPS — which are green. A false negative is
    the expensive direction, so cache True on the first success and only cache
    False once the retries are exhausted."""
    if os.environ.get("DNA_OFFLINE"):
        return False
    global _NETWORK_CACHE
    if _NETWORK_CACHE is None:
        for timeout in (5, 5, 10):
            try:
                conn = socket.create_connection(("github.com", 443), timeout=timeout)
                conn.close()
                _NETWORK_CACHE = True
                break
            except OSError:
                continue
        else:
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


@pytest.fixture(autouse=True)
def _isolated_sdlc_scope(monkeypatch):
    """Short-circuit ``--scope`` resolution to a fixed dummy value (autouse).

    Every ``dna sdlc`` verb resolves an absent ``--scope`` via
    ``_resolve_scope_default()``: env ``DNA_SDLC_SCOPE`` > auto-detect
    (probes the REAL filesystem via ``DNA_SOURCE_URL``/CWD, even when a
    test fakes the kernel session via ``SESSION_PROVIDER_KEY`` and never
    opens a real source for reads/writes) > a raised error (no branded
    fallback, s-rename-sdk-board-scope). Without this isolation, running
    the suite from this repo's root auto-detects the repo's OWN board
    scope (``.dna/dna``) and ``click.secho``'s the "auto-detected sole
    SDLC scope" notice, which ``CliRunner`` mixes into ``result.output``
    and breaks any assertion that doesn't expect it (exact-match /
    JSON-parse) — and a repo checked out with 0 or 2+ scopes would raise
    outright. Pre-rename this was masked by coincidence: the notice was
    only suppressed when the detected scope equalled the branded compat
    fallback ('dna-development'), which happened to be exactly this
    repo's real board name; removing that branded fallback exposed the
    missing isolation. Setting ``DNA_SDLC_SCOPE`` short-circuits before
    any filesystem probe, restoring deterministic, silent resolution for
    tests that don't care which scope string comes back (they fake the
    session and never validate it).

    Tests that need real control over scope resolution already
    ``monkeypatch.setenv``/``delenv("DNA_SDLC_SCOPE", ...)`` themselves —
    those calls run in the test body, after this fixture, and simply win.

    The dummy value is ``'dna-development'`` — not a branding choice
    (that literal is banned from PRODUCTION code, guarded by
    ``test_no_branded_scope_default_cli.py``), just matching the scope
    literal a large slice of the pre-existing CLI test suite already
    hardcodes into its fake-session store keys (e.g.
    ``store[("dna-development", "Issue", name)]``), so this fixture
    doesn't force an unrelated rewrite of every one of those fixtures.
    """
    monkeypatch.setenv("DNA_SDLC_SCOPE", "dna-development")


@pytest.fixture(autouse=True)
def _no_worktree_scan_by_default(monkeypatch):
    """Switch the sibling-worktree id scan OFF for the suite (autouse).

    ``dna sdlc issue file`` / ``kaizen flag`` read the OTHER git worktrees of
    this clone before taking ``max(NNN)+1`` — the fix for the ids that collided
    between parallel agents. It shells out to ``git worktree list`` and reads
    real directories, so leaving it on would make every id assertion in this
    suite depend on which worktrees the developer happens to have open.

    The tests that exist to prove the scan turn it back on explicitly, against a
    real git repo they build themselves under ``tmp_path``.
    """
    monkeypatch.setenv("DNA_SDLC_WORKTREE_SCAN", "0")


# --- Fake kernel session for `dna sdlc` write verbs ------------------------
#
# REAL creates against an in-memory store: the fake session is INJECTED through
# the click context (``obj={SESSION_PROVIDER_KEY: fake}``, f-cli-session-injection)
# — no reaching inside command modules. The write path (spec assembly, timeline
# stamping, ``_build_raw``) runs for real; only the kernel boundary is faked.
#
# Lived in ``test_sdlc_workitem_cli.py`` until the dated-spec-field guard
# (i-078) needed the same harness; hoisted here rather than copy-pasted.


class FakeDocView:
    def __init__(self, raw: dict):
        self._raw = raw
        self.name = raw.get("metadata", {}).get("name")
        self.kind = raw.get("kind")
        self.spec = raw.get("spec") or {}


class FakeKernel:
    """Records write_instance calls into the shared store."""

    def __init__(self, store: dict):
        self._store = store
        # instance_cmd._stamp_created_at_if_in_schema walks kernel._kinds; empty
        # dict makes it a no-op (returns early), which is fine for the test.
        self._kinds: dict = {}

    def with_tenant(self, tenant):
        return self

    async def get_instance(self, scope, kind, name):
        return self._store.get((scope, kind, name))

    async def query(self, scope, kind, *, projection=None, **_):
        """The enumeration the ``dna.application.sdlc`` cores read before writing.

        Honors ``projection=["name"]`` because the real kernel does, and a
        projected row comes back FLAT (``{"name": …}``) with no ``metadata``
        envelope. A double that always returned the full raw would let a caller
        read ``row["metadata"]["name"]`` and pass against a shape production
        never sends."""
        for (sc, kd, nm), raw in list(self._store.items()):
            if sc == scope and kd == kind:
                yield {"name": nm} if projection == ["name"] else raw

    async def write_instance(self, scope, kind, name, raw, *, if_absent=False, **_):
        # ``if_absent`` is the ATOMIC CREATE the create cores rely on; a double
        # that accepted the kwarg and ignored it would report a guarantee the
        # command does not have.
        if if_absent and (scope, kind, name) in self._store:
            from dna.kernel.errors import InstanceNameTaken

            raise InstanceNameTaken(
                f"{kind} {name!r} already exists in scope {scope!r}")
        self._store[(scope, kind, name)] = raw
        return "v1"


class FakeSession:
    """Drop-in for ClientSession backed by an in-memory dict store."""

    def __init__(self, store: dict, scope: str):
        self._store = store
        self.scope = scope
        self.kernel = FakeKernel(store)
        self.holder = type("_H", (), {"reload": lambda self: None})()

    def get_doc(self, kind, name, *, tenant=None):
        raw = self._store.get((self.scope, kind, name))
        return FakeDocView(raw) if raw is not None else None

    def query_list(self, kind, *, tenant=None):
        return [
            FakeDocView(raw)
            for (sc, kd, _nm), raw in self._store.items()
            if sc == self.scope and kd == kind
        ]

    def run(self, coro):
        import asyncio

        # Use a throwaway loop and tear it down cleanly so we don't pollute
        # the process-global current-loop (other test files' fakes call
        # asyncio.get_event_loop() and break on a leaked/half-open loop).
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


@pytest.fixture
def store():
    """The in-memory backing dict the fake session reads/writes."""
    return {}


@pytest.fixture
def session_obj(store):
    """The ctx.obj to inject: a session factory over the backing store."""
    from dna_cli._ctx import SESSION_PROVIDER_KEY

    @contextlib.contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield FakeSession(store, scope or "dna-development")

    return {SESSION_PROVIDER_KEY: _fake}


@pytest.fixture
def sdlc_runner(session_obj):
    """CliRunner whose invokes carry the injected session by default.

    An explicit ``obj=`` at a call site wins (setdefault) — used by tests
    that build their own fake.
    """
    r = CliRunner()
    _orig = r.invoke

    def _invoke(*args, **kwargs):
        kwargs.setdefault("obj", session_obj)
        return _orig(*args, **kwargs)

    r.invoke = _invoke  # type: ignore[method-assign]
    return r


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
