"""s-dna-typed-hook-names — the hook-name vocabulary is typed + fail-loud.

Hook names used to be magic strings: ``on("pre_saev", fn)`` compiled, ran,
and the listener never fired — silently. Now:

1. ``HookName`` (Literal) + ``KNOWN_HOOK_NAMES`` are the single vocabulary,
   locked to the golden ``tests/golden-fixtures/port-surface.json``
   (section ``hook_names``) — hook names are wire vocabulary, so drift
   turns this suite red.
2. Registering or emitting an UNKNOWN name warns (``UnknownHookNameWarning``,
   once per registry+name) — fail-loud, never fail-closed (custom names
   stay legal, back-compat).
3. The veto channel is typed: ``emit_veto`` carries a ``PreSaveContext``
   and the real guards (helix fork guard, sdlc bitemporal) consume its
   fields (scope/kind/name/raw/tenant/kernel).

"""
from __future__ import annotations

import json
import pathlib
import warnings
from typing import get_args

import pytest

from dna.kernel.hooks import (
    HookContext,
    HookName,
    HookRegistry,
    KNOWN_HOOK_NAMES,
    PreSaveContext,
    UnknownHookNameWarning,
)

_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[3]
    / "tests" / "golden-fixtures" / "port-surface.json"
)


# ---------------------------------------------------------------------------
# 1. Vocabulary — single source, golden-locked
# ---------------------------------------------------------------------------

def test_known_hook_names_mirror_the_literal():
    assert KNOWN_HOOK_NAMES == get_args(HookName)
    assert len(set(KNOWN_HOOK_NAMES)) == len(KNOWN_HOOK_NAMES), "duplicates"


def test_vocabulary_matches_golden_fixture():
    fixture = json.loads(_FIXTURE.read_text())
    fixture_names = fixture["hook_names"]["names"]
    assert list(KNOWN_HOOK_NAMES) == fixture_names, (
        "hook-name vocabulary drifted from tests/golden-fixtures/"
        "port-surface.json (section hook_names) — the vocabulary is wire "
        "vocabulary; update the fixture deliberately."
    )


def test_every_builtin_emit_site_name_is_in_the_vocabulary():
    # The names the kernel itself emits/registers (grep-audited at story
    # time). If a new builtin hook point appears, it must enter HookName.
    for name in (
        "pre_build_prompt", "post_build_prompt", "pre_save", "post_save",
        "post_delete", "kinddef_conflict", "parse_error", "extension_error",
    ):
        assert name in KNOWN_HOOK_NAMES


# ---------------------------------------------------------------------------
# 2. Unknown-name warning — fail-loud, not fail-closed
# ---------------------------------------------------------------------------

def test_typo_in_on_warns_and_names_the_vocabulary():
    reg = HookRegistry()
    with pytest.warns(UnknownHookNameWarning, match=r"pre_saev.*known:"):
        reg.on("pre_saev", lambda ctx: None)
    # Back-compat: the (mis)named listener is still registered.
    assert reg.has("pre_saev")


@pytest.mark.parametrize("method", ["use", "on", "on_async", "on_veto"])
def test_every_registration_surface_warns_on_unknown_name(method):
    reg = HookRegistry()
    async def afn(ctx):  # on_async requires a coroutine-shaped listener
        return None
    fn = afn if method == "on_async" else (lambda ctx: None)
    with pytest.warns(UnknownHookNameWarning):
        getattr(reg, method)("not_a_hook", fn)


def test_emit_surfaces_warn_on_unknown_name():
    reg = HookRegistry()
    with pytest.warns(UnknownHookNameWarning):
        reg.emit("not_a_hook", HookContext(scope="s"))


@pytest.mark.asyncio
async def test_async_emit_surfaces_warn_on_unknown_name():
    reg = HookRegistry()
    with pytest.warns(UnknownHookNameWarning):
        await reg.emit_async("not_a_hook", HookContext(scope="s"))
    with pytest.warns(UnknownHookNameWarning):
        await reg.emit_veto("not_a_hook_either", PreSaveContext(
            scope="s", kind="K", name="n", raw={},
        ))


def test_valid_names_never_warn():
    reg = HookRegistry()
    with warnings.catch_warnings():
        warnings.simplefilter("error", UnknownHookNameWarning)
        for name in KNOWN_HOOK_NAMES:
            reg.use(name, lambda ctx: ctx)
            reg.on(name, lambda ctx: None)
            reg.on_veto(name, lambda ctx: None)
            reg.emit(name, HookContext(scope="s"))
            reg.run_middleware(name, HookContext(scope="s"))


def test_unknown_name_warns_once_per_registry_and_name():
    reg = HookRegistry()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        reg.on("typo_hook", lambda ctx: None)
        reg.on("typo_hook", lambda ctx: None)      # same name → deduped
        reg.emit("typo_hook", HookContext(scope="s"))
        reg.on("other_typo", lambda ctx: None)     # new name → new warning
    ours = [w for w in caught if issubclass(w.category, UnknownHookNameWarning)]
    assert len(ours) == 2
    # A fresh registry warns again (dedup is per instance, not global).
    reg2 = HookRegistry()
    with pytest.warns(UnknownHookNameWarning):
        reg2.on("typo_hook", lambda ctx: None)


def test_kernel_facade_delegates_the_warning():
    from dna.kernel import Kernel
    k = Kernel()
    with pytest.warns(UnknownHookNameWarning, match="post_saev"):
        k.on("post_saev", lambda ctx: None)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UnknownHookNameWarning)
        k.on("post_save", lambda ctx: None)
        k.on_veto("pre_save", lambda ctx: None)
        k.use("pre_build_prompt", lambda ctx: ctx)


# ---------------------------------------------------------------------------
# 3. Typed veto ctx — the REAL guards consume PreSaveContext fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_typed_ctx_drives_the_platform_agent_fork_guard():
    from dna.extensions.helix.write_guards import (
        platform_agent_fork_guard,
    )
    from dna.kernel.protocols import DEFAULT_BASE_SCOPE, TenantNotAllowed

    reg = HookRegistry()
    reg.on_veto("pre_save", platform_agent_fork_guard, priority=10)
    # Base write (no tenant) passes.
    await reg.emit_veto("pre_save", PreSaveContext(
        scope=DEFAULT_BASE_SCOPE, kind="Agent", name="jarvis", raw={},
    ))
    # Per-tenant overlay of a _lib Agent is vetoed.
    with pytest.raises(TenantNotAllowed):
        await reg.emit_veto("pre_save", PreSaveContext(
            scope=DEFAULT_BASE_SCOPE, kind="Agent", name="jarvis",
            raw={}, tenant="acme",
        ))


@pytest.mark.asyncio
async def test_typed_ctx_drives_the_sdlc_bitemporal_guard():
    """The bitemporal guard reads ctx.kernel/scope/kind/name/tenant and
    MUTATES ctx.raw in place — PreSaveContext carries every field it needs."""
    from dna.extensions.sdlc.write_guards import (
        bitemporal_engram_guard,
    )

    class _FakeKernel:
        async def get_document(self, scope, kind, name, tenant=None):
            return {"spec": {"valid_to": "2026-01-01T00:00:00Z",
                             "superseded_by_memory": "rem-x"}}

    reg = HookRegistry()
    reg.on_veto("pre_save", bitemporal_engram_guard, priority=40)
    ctx = PreSaveContext(
        scope="dna-development", kind="Engram", name="rem-1",
        raw={"spec": {"body": "rewrite without valid_to"}},
        kernel=_FakeKernel(),
    )
    await reg.emit_veto("pre_save", ctx)
    # Never resurrect a superseded memory: valid_to preserved on ctx.raw.
    assert ctx.raw["spec"]["valid_to"] == "2026-01-01T00:00:00Z"
    assert ctx.raw["spec"]["superseded_by_memory"] == "rem-x"
