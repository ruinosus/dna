"""C0 Task 4 — declarative config from `EmitContext`: model/mcp/persistence
never read raw `os.environ`, except the ONE legit read `resolve_persistence`
makes for a Postgres DSN (a SECRET named declaratively by a `ctx.persistence`
`ref`, via the same `ref -> DNA_<REF>_URL` slug rule `dna.emit.scaffold`
already uses)."""
import asyncio
import shutil
from pathlib import Path

from dna.emit import build_copilot_context
from dna.kernel import Kernel
from dna.runtime.adapters.langchain_rt import LangChainRuntime
from dna.runtime.persistence import resolve_persistence
from dna.runtime.port import RuntimeHooks

# Committed fixture (this repo), NOT the sibling dna-cloud repo — must pass on
# a fresh clone with no dna-cloud checkout present. Its memory-copilot.yaml
# declares `model: gpt-5-mini` and `persistence.{checkpoint,memory}` on
# Postgres (ref `primary-pg`) — both exercised below.
FIXTURE_SRC = Path(__file__).parent / "fixtures" / "dna" / "dna-cloud-dev"


def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / ".dna" / "dna-cloud-dev"
    dest.mkdir(parents=True)
    for subdir in ("copilots", "agents", "federations", "tools"):
        shutil.copytree(FIXTURE_SRC / subdir, dest / subdir)
    return tmp_path / ".dna"


def _build_ctx(tmp_path):
    base_dir = _copy_fixture(tmp_path)
    mi = Kernel.quick("dna-cloud-dev", base_dir=str(base_dir))
    return build_copilot_context(mi, "memory-copilot")


async def _compose(_headers):
    return "PROMPT"


def _stub_no_mcp_discovery(monkeypatch):
    async def fake_load_mcp_tools(mcp_url, auth):
        return []

    monkeypatch.setattr(
        "dna.runtime.middleware.mcp_tools_mw.load_mcp_tools", fake_load_mcp_tools
    )


def _stub_no_persistence_resolution(monkeypatch):
    async def fake_resolve_persistence(_persistence):
        return None, None

    monkeypatch.setattr(
        "dna.runtime.persistence.resolve_persistence", fake_resolve_persistence
    )


# ── (1) model: ctx.model wins over OPENAI_MODEL env ────────────────────────


def test_model_binds_from_ctx_even_with_a_different_openai_model_env(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    # A DIFFERENT model than the fixture's `gpt-5-mini` — if the adapter ever
    # regresses to reading this, the captured model below would show it.
    monkeypatch.setenv("OPENAI_MODEL", "gpt-9-env-should-not-be-used")
    _stub_no_mcp_discovery(monkeypatch)
    _stub_no_persistence_resolution(monkeypatch)

    captured = {}
    import langchain.chat_models as chat_models

    real_init_chat_model = chat_models.init_chat_model

    def spy_init_chat_model(model_str, **kwargs):
        captured["model"] = model_str
        return real_init_chat_model(model_str, **kwargs)

    monkeypatch.setattr("langchain.chat_models.init_chat_model", spy_init_chat_model)

    ctx = _build_ctx(tmp_path)
    assert ctx.model == "gpt-5-mini"  # sanity: the fixture's declared model

    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose)
    asyncio.run(LangChainRuntime().build(ctx, hooks))

    assert captured["model"] == "openai:gpt-5-mini"
    assert "gpt-9-env-should-not-be-used" not in captured["model"]


# ── (2) persistence: DSN via the ref -> DNA_<REF>_URL slug rule ────────────


class _FakeConn:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    async def setup(self) -> None:  # pragma: no cover - trivial
        pass


class _FakeCM:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn(self._dsn)

    async def __aexit__(self, *exc: object) -> bool:
        return False


def test_resolve_persistence_reads_dsn_via_ref_slug_rule(monkeypatch):
    monkeypatch.setenv("DNA_PRIMARY_PG_URL", "postgresql://test-user@test-host/dna")

    captured = {"saver_dsn": None, "store_dsn": None}

    class _FakeAsyncPostgresSaver:
        @staticmethod
        def from_conn_string(dsn: str) -> _FakeCM:
            captured["saver_dsn"] = dsn
            return _FakeCM(dsn)

    class _FakeAsyncPostgresStore:
        @staticmethod
        def from_conn_string(dsn: str) -> _FakeCM:
            captured["store_dsn"] = dsn
            return _FakeCM(dsn)

    monkeypatch.setattr(
        "langgraph.checkpoint.postgres.aio.AsyncPostgresSaver",
        _FakeAsyncPostgresSaver,
    )
    monkeypatch.setattr(
        "langgraph.store.postgres.aio.AsyncPostgresStore", _FakeAsyncPostgresStore
    )

    checkpointer, store = asyncio.run(
        resolve_persistence(
            {
                "checkpoint": {"backend": "postgres", "ref": "primary-pg"},
                "memory": {"backend": "postgres", "ref": "primary-pg"},
                "cache": None,
            }
        )
    )

    # `primary-pg` -> `DNA_PRIMARY_PG_URL` (dna.emit.scaffold.pg_env_var's
    # slug rule) — the DSN read came from THAT env var, not a hardcoded name.
    assert captured["saver_dsn"] == "postgresql://test-user@test-host/dna"
    assert captured["store_dsn"] == "postgresql://test-user@test-host/dna"
    assert isinstance(checkpointer, _FakeConn)
    assert isinstance(store, _FakeConn)


def test_resolve_persistence_none_for_undeclared_or_inmemory_slots():
    checkpointer, store = asyncio.run(resolve_persistence(None))
    assert (checkpointer, store) == (None, None)

    checkpointer, store = asyncio.run(
        resolve_persistence({"checkpoint": {"backend": "inmemory", "ref": None}})
    )
    assert (checkpointer, store) == (None, None)


# ── (3) mcp: url comes from ctx.mcp_servers[0].url, not a DNA_MCP_URL env ───


def test_mcp_url_comes_from_ctx_not_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    # A DIFFERENT url than the fixture's federation declares — pins that the
    # adapter cannot regress to reading this env var for the MCP url.
    monkeypatch.setenv("DNA_MCP_URL", "http://env-should-not-be-used.invalid/mcp")
    _stub_no_persistence_resolution(monkeypatch)

    captured = {}

    from dna.runtime.middleware.mcp_tools_mw import (
        DnaMcpToolsMiddleware as _RealDnaMcpToolsMiddleware,
    )

    class _SpyMcpMiddleware(_RealDnaMcpToolsMiddleware):
        # Subclass the REAL middleware (rather than a bare stand-in) so
        # `create_agent`'s own `AgentMiddleware` expectations (state_schema,
        # `.tools`, the wrap_* hooks) stay satisfied — only `__init__` is
        # intercepted, purely to capture the `mcp_url` the adapter passed.
        def __init__(self, mcp_url, mcp_auth):
            captured["mcp_url"] = mcp_url
            super().__init__(mcp_url, mcp_auth)

    monkeypatch.setattr(
        "dna.runtime.adapters.langchain_rt.DnaMcpToolsMiddleware", _SpyMcpMiddleware
    )

    ctx = _build_ctx(tmp_path)
    expected_url = ctx.mcp_servers[0].url
    assert expected_url != "http://env-should-not-be-used.invalid/mcp"

    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose)
    asyncio.run(LangChainRuntime().build(ctx, hooks))

    assert captured["mcp_url"] == expected_url
