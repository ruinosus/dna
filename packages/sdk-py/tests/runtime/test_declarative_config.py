"""C0 Task 4 — declarative config from `EmitContext`: model/mcp/persistence
never read raw `os.environ`, except the TWO legit reads:

1. `resolve_persistence` reads a Postgres DSN — a SECRET named declaratively
   by a `ctx.persistence` `ref`, via the same `ref -> DNA_<REF>_URL` slug
   rule `dna.emit.scaffold` already uses;
2. `mcp_tool_stack` honors `DNA_MCP_URL` as the HOST's deploy-time override
   over the federation's declarative placeholder URL (the fixture's
   `https://mcp.dna-cloud.example/mcp` is exactly such a placeholder — a real
   deployment points the SAME def at ITS endpoint via env, not by editing the
   def). Unset, the `ctx.mcp_servers[0].url` from the def wins.
"""
import asyncio
import shutil
import sys
import types
from pathlib import Path

import pytest

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


def _install_fake_module(monkeypatch, name: str, **attrs: object) -> None:
    """Register a synthetic module (and expose it on its parent) so the
    function-local `from <name> import X` inside `resolve_persistence` binds
    the fake — parents (`langgraph`, `langgraph.checkpoint`,
    `langgraph.store`) are real; only the postgres leaves are synthesized."""
    mod = types.ModuleType(name)
    for attr, value in attrs.items():
        setattr(mod, attr, value)
    monkeypatch.setitem(sys.modules, name, mod)
    parent_name, _, child = name.rpartition(".")
    if parent_name and parent_name in sys.modules:
        monkeypatch.setattr(sys.modules[parent_name], child, mod, raising=False)


def test_resolve_persistence_reads_dsn_via_ref_slug_rule(monkeypatch):
    # i-064: was quarantined because the monkeypatch targeted the REAL
    # `langgraph.checkpoint.postgres` module by dotted path, which the
    # `[runtime]` extra deliberately does NOT install
    # (`langgraph-checkpoint-postgres` is the HOST's dependency — dna-cloud's
    # copilot pyproject declares it; `resolve_persistence` imports it inside
    # the function for exactly that reason). What THIS test pins is the
    # declarative DSN read (`ref -> DNA_<REF>_URL`), not the driver — so the
    # postgres modules are synthesized instead of imported.
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

    import langgraph.checkpoint  # noqa: F401 — real parents, fake leaves
    import langgraph.store  # noqa: F401

    _install_fake_module(monkeypatch, "langgraph.checkpoint.postgres")
    _install_fake_module(
        monkeypatch,
        "langgraph.checkpoint.postgres.aio",
        AsyncPostgresSaver=_FakeAsyncPostgresSaver,
    )
    _install_fake_module(monkeypatch, "langgraph.store.postgres")
    _install_fake_module(
        monkeypatch,
        "langgraph.store.postgres.aio",
        AsyncPostgresStore=_FakeAsyncPostgresStore,
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


# ── (3) mcp url: ctx.mcp_servers[0].url by default; DNA_MCP_URL is the
#      HOST's deploy-time override over the declarative placeholder ─────────
#
# i-064: the original test here (`test_mcp_url_comes_from_ctx_not_env`)
# asserted a contract `mcp_tool_stack` deliberately retired — the adapter
# instances `DNA_MCP_URL` as the host's env override over the federation's
# placeholder URL (see langchain_rt.py's `mcp_tool_stack` docstring). The
# test was quarantined instead of updated; these two pin the CURRENT
# contract, from both sides.


def _build_and_capture_mcp_url(tmp_path, monkeypatch) -> tuple:
    """Build the runtime for the committed fixture and capture the `mcp_url`
    the adapter handed `DnaMcpToolsMiddleware`; returns `(ctx, captured)`."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
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
        def __init__(self, mcp_url, mcp_auth, **kwargs):
            captured["mcp_url"] = mcp_url
            super().__init__(mcp_url, mcp_auth, **kwargs)

    monkeypatch.setattr(
        "dna.runtime.adapters.langchain_rt.DnaMcpToolsMiddleware", _SpyMcpMiddleware
    )

    ctx = _build_ctx(tmp_path)
    hooks = RuntimeHooks(mcp_auth=lambda: {}, compose=_compose)
    asyncio.run(LangChainRuntime().build(ctx, hooks))
    return ctx, captured


def test_mcp_url_comes_from_ctx_when_no_host_override(tmp_path, monkeypatch):
    monkeypatch.delenv("DNA_MCP_URL", raising=False)
    ctx, captured = _build_and_capture_mcp_url(tmp_path, monkeypatch)
    assert captured["mcp_url"] == ctx.mcp_servers[0].url


def test_dna_mcp_url_env_overrides_the_declarative_placeholder(
    tmp_path, monkeypatch
):
    override = "https://mcp.host-deployment.example/mcp"
    monkeypatch.setenv("DNA_MCP_URL", override)
    ctx, captured = _build_and_capture_mcp_url(tmp_path, monkeypatch)
    # Sanity: the override really differs from the def's placeholder, so the
    # assertion below can only pass via the env path.
    assert ctx.mcp_servers[0].url != override
    assert captured["mcp_url"] == override
