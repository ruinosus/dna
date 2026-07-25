"""i-071 — open-core branding leak: the neutral intel engine + CLI must never
hardcode DNA's own dogfood board scope (``"dna-development"``) as a default.

Before this fix, ``dna.extensions.intel.engine.DEFAULT_SCOPE`` and the
``kind_cmd``/``intel_cmd`` CLI ``--scope`` options all defaulted to the
literal ``"dna-development"`` — a third party who ``pip install dna-sdk``
and calls the intel engine (or runs ``dna kind list`` / ``dna intel ...``)
with no ``--scope`` silently got DNA's internal board scope as their
default, not their own.

The fix mirrors the pattern the repo ALREADY uses elsewhere for this exact
problem: ``dna_cli.sdlc._common._autodetect_sdlc_scope`` (sole scope in the
source, else None) and the CLI siblings ``mcp_cmd``/``api_cmd``/``emit_cmd``/
``explain_cmd`` (``--scope default=None``, help "(default: env / sole
scope)"). The intel ENGINE gets its own neutral resolver
(``dna.extensions.intel.engine._resolve_scope``) since it must work for
non-CLI callers too (REST, a bare SDK import) — it resolves the kernel's
SOLE scope via ``kernel.list_scopes_async()``, and raises a clear
``ValueError`` (never a silent guess) when that's ambiguous (0 or 2+ scopes).

OUT of scope (untouched, by design): ``dna_cli.sdlc._common.DEFAULT_SCOPE``
(the documented SDLC compat fallback, entangled with a separate story about
renaming THIS repo's own board) and its test
``packages/cli/tests/test_sdlc_scope_default.py``.
"""
from __future__ import annotations

import pytest

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.intel import IntelExtension, engine
from dna.kernel import Kernel


def _bootstrap_scope(tmp_path, scope: str) -> None:
    (tmp_path / scope).mkdir(parents=True, exist_ok=True)
    (tmp_path / scope / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        f"metadata: {{name: {scope}}}\nspec: {{}}\n"
    )


async def _kernel(tmp_path, *scopes: str) -> Kernel:
    k = Kernel()
    k.load(IntelExtension())
    for scope in scopes:
        _bootstrap_scope(tmp_path, scope)
    src = FilesystemWritableSource(str(tmp_path), writers=list(k._writers), kernel=k)
    k.source(src)
    src.attach_kernel(k)
    return k


async def _seed_source(k: Kernel, scope: str, tenant: str, name: str = "src-1") -> None:
    await k.write_document(
        scope, "IntelSource", name,
        {
            "apiVersion": "github.com/ruinosus/dna/intel/v1",
            "kind": "IntelSource",
            "metadata": {"name": name},
            "spec": {
                "name": name, "type": "repo", "cadence": "weekly",
                "threshold": 0.6, "pirs": [], "muted": False,
            },
        },
        tenant=tenant,
    )


# ── 1. no branded constant / default survives ──────────────────────────────


def test_engine_no_longer_exports_a_branded_default_scope_constant():
    assert not hasattr(engine, "DEFAULT_SCOPE")


def test_kind_cmd_list_scope_option_default_is_none_not_dna_development():
    from dna_cli.kind_cmd import list_kinds

    opt = next(p for p in list_kinds.params if p.name == "scope")
    assert opt.default is None


def test_intel_cmd_scope_options_all_default_to_none():
    from dna_cli.intel_cmd import cmd_list, cmd_metrics, cmd_run, cmd_sources

    for cmd in (cmd_sources, cmd_run, cmd_list, cmd_metrics):
        opt = next(p for p in cmd.params if p.name == "scope")
        assert opt.default is None, f"{cmd.name}: --scope default={opt.default!r}"


# ── 2. sole-scope resolution — a real neutral scope, never the branded one ──


@pytest.mark.asyncio
async def test_run_pass_with_no_scope_resolves_the_sole_scope(tmp_path):
    k = await _kernel(tmp_path, "acme-board")
    await _seed_source(k, "acme-board", "acme")

    result = await engine.run_pass(k, "src-1", tenant="acme")  # no scope= given

    assert result.scope == "acme-board"
    assert result.scope != "dna-development"


@pytest.mark.asyncio
async def test_list_sources_with_no_scope_resolves_the_sole_scope(tmp_path):
    k = await _kernel(tmp_path, "acme-board")
    await _seed_source(k, "acme-board", "acme")

    rows = await engine.list_sources(k, tenant="acme")  # no scope= given

    assert [r["name"] for r in rows] == ["src-1"]


@pytest.mark.asyncio
async def test_feedback_metrics_with_no_scope_resolves_the_sole_scope(tmp_path):
    k = await _kernel(tmp_path, "acme-board")

    metrics = await engine.feedback_metrics(k, tenant="acme")  # no scope= given

    assert metrics["scope"] == "acme-board"


# ── 3. ambiguous resolution raises a clear error — never a silent guess ────


@pytest.mark.asyncio
async def test_run_pass_with_no_scope_and_two_scopes_raises(tmp_path):
    k = await _kernel(tmp_path, "acme-board", "other-board")

    with pytest.raises(ValueError, match="scope"):
        await engine.run_pass(k, "src-1", tenant="acme")


@pytest.mark.asyncio
async def test_list_sources_with_no_scope_and_zero_scopes_raises(tmp_path):
    k = await _kernel(tmp_path)  # no scope bootstrapped at all

    with pytest.raises(ValueError, match="scope"):
        await engine.list_sources(k)


@pytest.mark.asyncio
async def test_list_insights_with_no_scope_and_two_scopes_raises(tmp_path):
    k = await _kernel(tmp_path, "acme-board", "other-board")

    with pytest.raises(ValueError, match="scope"):
        await engine.list_insights(k)


@pytest.mark.asyncio
async def test_set_insight_state_with_no_scope_and_two_scopes_raises(tmp_path):
    k = await _kernel(tmp_path, "acme-board", "other-board")

    with pytest.raises(ValueError, match="scope"):
        await engine.set_insight_state(k, "ins-1", "actioned")
