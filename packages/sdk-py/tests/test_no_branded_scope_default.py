"""i-071 — open-core branding leak: the neutral intel engine + CLI must never
hardcode DNA's own dogfood board scope (``"dna-development"``) as a default.

Before this fix, ``dna.extensions.intel.engine.DEFAULT_SCOPE`` and every
``--scope`` option across ``kind_cmd``/``intel_cmd``/``doc_cmd``/
``research_cmd`` defaulted to the literal ``"dna-development"`` — a third
party who ``pip install dna-sdk`` and calls the intel engine (or runs
``dna kind list`` / ``dna doc ...`` / ``dna research ...`` with no
``--scope``) silently got DNA's internal board scope as their default, not
their own.

The fix mirrors the pattern the repo ALREADY uses elsewhere for this exact
problem: ``dna_cli.sdlc._common._autodetect_sdlc_scope`` (sole scope in the
source, else None) and the CLI siblings ``mcp_cmd``/``api_cmd``/``emit_cmd``/
``explain_cmd`` (``--scope default=None``, help "(default: env / sole
scope)"). The intel ENGINE gets its own neutral resolver
(``dna.extensions.intel.engine._resolve_scope``) since it must work for
non-CLI callers too (REST, a bare SDK import) — it resolves the kernel's
SOLE scope via ``kernel.list_scopes_async()``, and raises a clear
``ValueError`` (never a silent guess) when that's ambiguous (0 or 2+ scopes).
``dna_client()``-based commands (``kind_cmd``, ``doc_cmd``) resolve via the
new ``_LocalClient.default_scope`` accessor — the same holder-resolved scope
``_build_holder_async`` already computes, reused rather than reimplemented.

Round 2 (the full sweep) fixed the remaining 12 branded ``--scope`` sites:
``doc_cmd.py`` (list/show/make/transition/fields/create/delete — 7),
``research_cmd.py`` (list/show/create/recall — 4), and ``kind_cmd.py``'s
``describe`` (1, the sibling of ``list`` fixed in round 1). Round 2 also adds
the STRUCTURAL guard below (``test_no_dna_cli_scope_option_defaults_to_a_
branded_scope``) so this bug class can't silently reappear at a 13th site —
it scans every ``--scope`` click option reachable from ``dna_cli``, not a
fixed list of filenames.

OUT of scope (untouched, by design): ``dna_cli.sdlc_cmd`` / ``dna_cli.sdlc.*``
(``DEFAULT_SCOPE = "dna-development"`` is the documented SDLC compat
fallback, entangled with a separate story about renaming THIS repo's own
board) and its test ``packages/cli/tests/test_sdlc_scope_default.py``. The
structural guard excludes commands by where their CALLBACK is actually
DEFINED (``dna_cli.sdlc*``), not by which module re-exports them — e.g.
``hooks_cmd``/``pr_cmd``/``testkit_cmd`` all re-expose the SAME
``sdlc extract-decisions`` command object (still ``dna-development``-
defaulted), so a naive "which module has this attribute" scan would
wrongly flag it 3 extra times outside its true home.
"""
from __future__ import annotations

import importlib
import json
import pathlib
import pkgutil

import click
import pytest
from click.testing import CliRunner

import dna_cli
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


def test_kind_cmd_describe_scope_option_default_is_none_not_dna_development():
    from dna_cli.kind_cmd import describe

    opt = next(p for p in describe.params if p.name == "scope")
    assert opt.default is None


def test_doc_cmd_scope_options_all_default_to_none():
    from dna_cli.doc_cmd import create, delete, fields_help, list_docs, make_doc, show, transition

    for cmd in (list_docs, show, make_doc, transition, fields_help, create, delete):
        opt = next(p for p in cmd.params if p.name == "scope")
        assert opt.default is None, f"{cmd.name}: --scope default={opt.default!r}"


def test_research_cmd_scope_options_all_default_to_none():
    from dna_cli.research_cmd import cmd_create, cmd_list, cmd_recall, cmd_show

    for cmd in (cmd_list, cmd_show, cmd_create, cmd_recall):
        opt = next(p for p in cmd.params if p.name == "scope")
        assert opt.default is None, f"{cmd.name}: --scope default={opt.default!r}"


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


# ── 4. structural guard — catches this bug class WHOLESALE, not by filename ─


def _iter_dna_cli_command_objects():
    """Every click.Command reachable as a module-level attribute of any
    ``dna_cli`` submodule (walking Groups recursively) — dedup'd by object
    identity, since several modules re-export the same command (e.g.
    ``hooks_cmd``/``pr_cmd``/``testkit_cmd`` all expose the SAME ``sdlc``
    subgroup)."""
    seen_ids: set[int] = set()
    for modinfo in pkgutil.walk_packages(dna_cli.__path__, prefix="dna_cli."):
        try:
            mod = importlib.import_module(modinfo.name)
        except Exception:  # noqa: BLE001 — an unimportable module (missing
            # optional extra) has no commands to check; not this guard's job.
            continue
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name, None)
            if not isinstance(obj, click.Command):
                continue
            stack = [obj]
            while stack:
                cmd = stack.pop()
                if id(cmd) in seen_ids:
                    continue
                seen_ids.add(id(cmd))
                if isinstance(cmd, click.Group):
                    stack.extend(cmd.commands.values())
                else:
                    yield cmd


def _dna_cli_scope_options():
    """``(command_name, click.Option)`` for every ``--scope`` option reachable
    from ``dna_cli``, EXCLUDING any command whose callback is actually
    DEFINED in ``dna_cli.sdlc`` / ``dna_cli.sdlc_cmd`` (checked via
    ``callback.__module__`` — the command's origin, not whichever module
    happens to import/re-expose it) — the documented SDLC compat fallback,
    out of scope for this ticket."""
    for cmd in _iter_dna_cli_command_objects():
        callback = getattr(cmd, "callback", None)
        callback_module = getattr(callback, "__module__", "") or ""
        if callback_module.startswith("dna_cli.sdlc"):
            continue
        for p in cmd.params:
            if isinstance(p, click.Option) and p.name == "scope":
                yield cmd.name, p


def test_no_dna_cli_scope_option_defaults_to_a_branded_scope():
    """The wholesale guard: no ``--scope`` click option anywhere in
    ``dna_cli`` (outside the documented SDLC exclusion) may default to the
    branded literal ``"dna-development"``. Catches a 13th site the next time
    someone copy-pastes an old ``--scope`` option, without anyone having to
    remember or maintain a list of filenames."""
    offenders = [
        (cmd_name, opt.default)
        for cmd_name, opt in _dna_cli_scope_options()
        if opt.default == "dna-development"
    ]
    assert offenders == [], f"branded --scope defaults found: {offenders}"


# ── 5. functional regressions — the resolution actually WORKS end to end ───


def test_doc_list_with_no_scope_resolves_via_dna_client_default_scope():
    """``dna doc list`` (a ``dna_client()``/``_LocalClient`` command, not
    ``dna_session``) with ``--scope`` omitted must resolve through the new
    ``_LocalClient.default_scope`` accessor and actually find real data —
    not just carry a ``None`` default that later 404s. Uses the same fixture
    ``test_definition_cmd.py`` already proves has a real ``Agent`` doc named
    ``concierge`` in the (alphabetically-first) ``concierge`` scope."""
    from dna_cli.doc_cmd import doc

    base = pathlib.Path(__file__).resolve().parents[3] / "examples" / "emitting-to-a-runtime" / ".dna"
    runner = CliRunner()
    result = runner.invoke(
        doc, ["list", "Agent", "--json"],
        env={"DNA_BASE_DIR": str(base), "DNA_SOURCE_URL": ""},
    )
    assert result.exit_code == 0, result.output
    names = {row["name"] for row in json.loads(result.output)}
    assert "concierge" in names


def test_research_create_and_list_with_no_scope_round_trips_via_dna_session(tmp_path):
    """Regression for the ``s.scope`` fix in ``research_cmd.cmd_create``:
    with ``--scope`` omitted, ``dna_session(None)`` resolves the sole scope
    — the WRITE must land there too. Before the fix, ``write_document`` was
    called with the raw (still-``None``, once the option default changed)
    ``scope`` local instead of the session's resolved ``s.scope`` — a latent
    crash the click-level "default is None" check alone would never catch."""
    from dna_cli.research_cmd import research

    scope_dir = tmp_path / "acme-board"
    scope_dir.mkdir()
    (scope_dir / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        "metadata: {name: acme-board}\nspec: {}\n"
    )
    spec_file = tmp_path / "rsh.yaml"
    spec_file.write_text(json.dumps({
        "apiVersion": "github.com/ruinosus/dna/research/v1",
        "kind": "Research",
        "metadata": {"name": "rsh-test"},
        "spec": {
            "title": "T", "objective": "O", "methodology": "synthesis",
            "status": "published",
            "findings": [
                {"id": "f-a", "title": "A", "evidence_rating": "evidence-based"},
            ],
            "recommendations": [
                {"id": "rec-a", "priority": "high", "summary": "do it"},
            ],
        },
    }))

    runner = CliRunner()
    env = {"DNA_BASE_DIR": str(tmp_path), "DNA_SOURCE_URL": ""}
    created = runner.invoke(research, ["create", str(spec_file)], env=env)
    assert created.exit_code == 0, created.output

    listed = runner.invoke(research, ["list", "--json"], env=env)
    assert listed.exit_code == 0, listed.output
    rows = json.loads(listed.output)
    assert any(r["name"] == "rsh-test" for r in rows), rows
