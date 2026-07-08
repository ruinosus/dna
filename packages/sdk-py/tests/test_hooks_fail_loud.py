"""s-kernel-fail-soft-audit — the sync-emit async-listener skip is LOUD.

Registering an async listener on a hook that is only fired via sync
``emit()`` used to be an invisible no-op (debug-only log). Now:

- ``emit`` counts every skip in ``skipped_async_emits[hook]`` and warns
  ONCE per (hook, listener) at WARNING level;
- ``emit(strict=True)`` raises instead — for call sites where skipping
  a listener would be a bug;
- ``prompt_kernel.build_prompt_async`` (async context) awaits
  ``emit_async`` for ``post_build_prompt`` so async listeners actually
  fire on the kernel build path.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from dna.kernel.hooks import HookContext, HookRegistry


def _ctx() -> HookContext:
    return HookContext(scope="s")


def test_emit_runs_sync_listeners_and_counts_async_skips(caplog):
    reg = HookRegistry()
    hits: list[str] = []
    reg.on("h", lambda ctx: hits.append("sync"))

    async def async_listener(ctx):  # pragma: no cover — must NOT run
        hits.append("async")

    reg.on("h", async_listener)

    with caplog.at_level(logging.WARNING, logger="dna.kernel.hooks"):
        reg.emit("h", _ctx())
        reg.emit("h", _ctx())

    assert hits == ["sync", "sync"]
    # Counter: every skip counted (1 async listener × 2 emits).
    assert reg.skipped_async_emits["h"] == 2
    # Warning: once per (hook, listener), not per emit.
    warnings = [r for r in caplog.records if "SKIPPED" in r.getMessage()]
    assert len(warnings) == 1
    assert "async_listener" in warnings[0].getMessage()


def test_emit_warns_once_per_listener_not_per_hook(caplog):
    reg = HookRegistry()

    async def l1(ctx):  # pragma: no cover
        pass

    async def l2(ctx):  # pragma: no cover
        pass

    reg.on("h", l1)
    reg.on("h", l2)
    with caplog.at_level(logging.WARNING, logger="dna.kernel.hooks"):
        reg.emit("h", _ctx())
        reg.emit("h", _ctx())
    warnings = [r for r in caplog.records if "SKIPPED" in r.getMessage()]
    assert len(warnings) == 2  # one per listener, deduped across emits
    assert reg.skipped_async_emits["h"] == 4


def test_emit_strict_raises_on_async_listeners():
    reg = HookRegistry()

    async def async_listener(ctx):  # pragma: no cover
        pass

    reg.on("h", async_listener)
    with pytest.raises(RuntimeError, match="emit_async"):
        reg.emit("h", _ctx(), strict=True)


def test_emit_strict_is_noop_without_async_listeners():
    reg = HookRegistry()
    hits: list[str] = []
    reg.on("h", lambda ctx: hits.append("sync"))
    reg.emit("h", _ctx(), strict=True)
    assert hits == ["sync"]


@pytest.mark.asyncio
async def test_build_prompt_async_reaches_async_post_build_prompt_listener():
    """The kernel's async build path fires emit_async — an async
    post_build_prompt listener is awaited, not silently skipped."""
    from dna.kernel.document import Document
    from dna.kernel.prompt_kernel import build_prompt_async

    agent_raw = {
        "apiVersion": "v1", "kind": "Agent",
        "metadata": {"name": "a-1"},
        "spec": {"instruction": "Do the thing."},
    }

    async def _get(scope, kind, name, **kw):
        if kind == "Agent" and name == "a-1":
            return dict(agent_raw)
        return None

    async def _list(scope, *, kind=None, tenant=None):
        return []

    async def _query(scope, kind, **kw):
        if kind == "Agent":
            yield dict(agent_raw)
        return

    def _parse(raw, origin="local"):
        meta = raw.get("metadata", {}) or {}
        return Document(
            api_version=raw.get("apiVersion", "v1"), kind=raw["kind"],
            name=meta.get("name", ""), metadata=meta,
            spec=raw.get("spec", {}) or {},
        )

    kp = SimpleNamespace(
        kind="Agent", alias="v1-utilityagent", api_version="v1",
        is_prompt_target=True, prompt_target_priority=1,
        flatten_in_context=False,
        dep_filters=lambda: {},
        prompt_template=lambda doc=None: None,
        summary=lambda doc: None,
    )

    async def _resolve_ref(scope, value):
        return value

    kernel = SimpleNamespace(
        query=_query,
        get_document=_get,
        list_documents=_list,
        _parse_doc=_parse,
        _kinds={("v1", "Agent"): kp},
        _source=SimpleNamespace(resolve_ref=_resolve_ref),
        hooks=HookRegistry(),
    )

    fired: list[str] = []

    async def on_post(ctx):
        fired.append(ctx.prompt or "")

    kernel.hooks.on("post_build_prompt", on_post)

    prompt = await build_prompt_async(kernel, "scope-x", "a-1")
    assert isinstance(prompt, str)
    assert fired, (
        "async post_build_prompt listener must fire on the async build "
        "path (emit_async) — it used to be silently skipped by sync emit()"
    )
    # And nothing was counted as skipped.
    assert kernel.hooks.skipped_async_emits.get("post_build_prompt", 0) == 0
