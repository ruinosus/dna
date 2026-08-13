"""s-kernel-fail-soft-audit — the sync-emit async-listener skip is LOUD.

Registering an async listener on a hook that is only fired via sync
``emit()`` used to be an invisible no-op (debug-only log). Now:

- ``emit`` counts every skip in ``skipped_async_emits[hook]`` and warns
  ONCE per (hook, listener) at WARNING level;
- ``emit(strict=True)`` raises instead — for call sites where skipping
  a listener would be a bug;
- ``PromptBuilder.build_async`` (async context) awaits ``emit_async``
  for ``post_build_prompt`` so async listeners actually fire on the
  kernel build path.

⚠️ That third bullet used to name ``prompt_kernel.build_prompt_async``
— a module with ZERO production callers, deleted in s-dna-shrink-faixa-1.
The fix had landed on the dead twin and NEVER on ``PromptBuilder``, the
builder every real caller reaches, so this suite was green about a path
nobody ran while the live path silently skipped async listeners. The
test below now drives the LIVE builder through ``mi.build_prompt_async``.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from dna.kernel import Kernel
from dna.kernel.hooks import HookContext, HookRegistry

BASE_DIR = Path(__file__).parent.parent.parent.parent / "scopes" / "open-swe" / ".dna"


def _ctx() -> HookContext:
    return HookContext(scope="s")


def test_emit_runs_sync_listeners_and_counts_async_skips(caplog):
    reg = HookRegistry()
    hits: list[str] = []
    reg.on("post_build_prompt", lambda ctx: hits.append("sync"))

    async def async_listener(ctx):  # pragma: no cover — must NOT run
        hits.append("async")

    reg.on("post_build_prompt", async_listener)

    with caplog.at_level(logging.WARNING, logger="dna.kernel.hooks"):
        reg.emit("post_build_prompt", _ctx())
        reg.emit("post_build_prompt", _ctx())

    assert hits == ["sync", "sync"]
    # Counter: every skip counted (1 async listener × 2 emits).
    assert reg.skipped_async_emits["post_build_prompt"] == 2
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

    reg.on("post_build_prompt", l1)
    reg.on("post_build_prompt", l2)
    with caplog.at_level(logging.WARNING, logger="dna.kernel.hooks"):
        reg.emit("post_build_prompt", _ctx())
        reg.emit("post_build_prompt", _ctx())
    warnings = [r for r in caplog.records if "SKIPPED" in r.getMessage()]
    assert len(warnings) == 2  # one per listener, deduped across emits
    assert reg.skipped_async_emits["post_build_prompt"] == 4


def test_emit_strict_raises_on_async_listeners():
    reg = HookRegistry()

    async def async_listener(ctx):  # pragma: no cover
        pass

    reg.on("post_build_prompt", async_listener)
    with pytest.raises(RuntimeError, match="emit_async"):
        reg.emit("post_build_prompt", _ctx(), strict=True)


def test_emit_strict_is_noop_without_async_listeners():
    reg = HookRegistry()
    hits: list[str] = []
    reg.on("post_build_prompt", lambda ctx: hits.append("sync"))
    reg.emit("post_build_prompt", _ctx(), strict=True)
    assert hits == ["sync"]


@pytest.fixture
def mi():
    """A REAL ManifestInstance over the open-swe fixture scope.

    Sync fixture on purpose: ``Kernel.quick`` composes through
    ``_run_sync_helper``, which refuses to run inside a live event loop —
    so the MI must be built in the setup phase, before pytest-asyncio
    enters the loop for the test body.
    """
    return Kernel.quick("open-swe", base_dir=str(BASE_DIR))


@pytest.mark.asyncio
async def test_build_prompt_async_reaches_async_post_build_prompt_listener(mi):
    """The LIVE async build path fires emit_async — an async
    post_build_prompt listener is awaited, not silently skipped.

    Drives ``ManifestInstance.build_prompt_async`` → ``PromptBuilder
    .build_async``, the path every real async caller reaches (harness
    lifespan, async middleware). The predecessor of this test drove
    ``prompt/engine.py`` — a module with zero production callers — and so
    proved nothing about this one, which was still on sync ``emit()``.
    """
    fired: list[str] = []

    async def on_post(ctx: HookContext) -> None:
        fired.append(ctx.prompt or "")

    mi._kernel.hooks.on("post_build_prompt", on_post)

    prompt = await mi.build_prompt_async(agent="swe-agent")
    assert isinstance(prompt, str) and prompt
    assert fired, (
        "async post_build_prompt listener must fire on the LIVE async build "
        "path (PromptBuilder.build_async → emit_async) — sync emit() skips it"
    )
    assert fired[0], "the listener receives the composed prompt, not an empty ctx"
    # And nothing was counted as skipped.
    assert mi._kernel.hooks.skipped_async_emits.get("post_build_prompt", 0) == 0


def test_sync_build_prompt_still_uses_sync_emit_and_counts_the_skip(mi):
    """The SYNC path cannot await — it must keep sync ``emit()``, which
    skips async listeners and COUNTS the skip. Locking this stops the
    async fix from being copy-pasted onto ``build()``, where it would
    raise 'coroutine was never awaited' instead of degrading loudly."""

    async def on_post(ctx: HookContext) -> None:  # pragma: no cover — must NOT run
        raise AssertionError("async listener must not run on the sync path")

    mi._kernel.hooks.on("post_build_prompt", on_post)
    mi.build_prompt(agent="swe-agent")

    assert mi._kernel.hooks.skipped_async_emits.get("post_build_prompt", 0) == 1
