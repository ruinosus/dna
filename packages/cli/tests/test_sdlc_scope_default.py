"""i-012 — `dna sdlc` scope default is configurable, not hardcoded.

Pilot phase-2 friction: every sdlc verb demanded --scope because the
default was the hardcoded 'dna-development' (which only works in this
repo by name coincidence). Adopter repos have arbitrary board-scope
names ('foundry-dev', ...).

s-rename-sdk-board-scope removed that branded fallback entirely (the
same open-core branding leak i-071 removed everywhere else in the CLI,
and the same fix the neutral intel engine already applies via
``dna.extensions.intel.engine._resolve_scope``) — hardcoding THIS
repo's own board name in the neutral CLI is exactly the bug class i-071
exists to catch.

Documented precedence (single helper, applied to every sdlc verb via
_scope_option):

  1. --scope explicit            (always wins)
  2. env DNA_SDLC_SCOPE
  3. auto-detect                 (sole scope in the source with SDLC
                                  structure — stories/features/epics/
                                  issues containers)
  4. a clear, actionable error   (no branded fallback — an explicit
                                  error beats a silently wrong default;
                                  names both escape hatches, --scope
                                  and DNA_SDLC_SCOPE)
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from click.testing import CliRunner

from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli import sdlc_cmd


class _Doc:
    def __init__(self, spec):
        self.spec = spec


def _invoke_and_capture_scope(monkeypatch, *args):
    """Run `story check` against a fake session; return the scope the
    command resolved (what dna_session was opened with)."""
    seen: dict = {}

    class _FakeSession:
        def __init__(self, scope):
            self.scope = scope

            class _K:
                async def write_document(self, scope, kind, name, raw):
                    pass

            self.kernel = _K()

        def get_doc(self, kind, name, *, tenant=None):
            return _Doc({
                "status": "review",
                "acceptance_criteria": ["one"],
                "definition_of_done": ["two"],
            })

        def run(self, coro):
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        seen["scope"] = scope
        yield _FakeSession(scope)

    r = CliRunner().invoke(
        sdlc_cmd.sdlc,
        ["story", "check", "s-x", "--ac", "1", "--evidence", "e", *args],
        obj={SESSION_PROVIDER_KEY: _fake},
    )
    assert r.exit_code == 0, r.output
    return seen["scope"]


def _mk_sdlc_scope(base: Path, name: str, containers=("stories",)) -> None:
    for c in containers:
        (base / name / c).mkdir(parents=True, exist_ok=True)


def _isolate_source(monkeypatch, base: Path) -> None:
    """Point source resolution at a tmp base dir, clear competing knobs."""
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DNA_SOURCE_URL", f"file://{base}")
    monkeypatch.delenv("DNA_SDLC_SCOPE", raising=False)


# ── 1. explicit --scope always wins ─────────────────────────────────────


def test_explicit_scope_beats_env_and_autodetect(monkeypatch, tmp_path):
    _isolate_source(monkeypatch, tmp_path / "src")
    _mk_sdlc_scope(tmp_path / "src", "foundry-dev")
    monkeypatch.setenv("DNA_SDLC_SCOPE", "env-scope")
    scope = _invoke_and_capture_scope(monkeypatch, "--scope", "explicit-scope")
    assert scope == "explicit-scope"


# ── 2. env DNA_SDLC_SCOPE ───────────────────────────────────────────────


def test_env_scope_beats_autodetect(monkeypatch, tmp_path):
    _isolate_source(monkeypatch, tmp_path / "src")
    _mk_sdlc_scope(tmp_path / "src", "foundry-dev")
    monkeypatch.setenv("DNA_SDLC_SCOPE", "env-scope")
    scope = _invoke_and_capture_scope(monkeypatch)
    assert scope == "env-scope"


# ── 3. auto-detect: sole SDLC scope, arbitrary board name ───────────────


def test_autodetect_sole_sdlc_scope_arbitrary_name(monkeypatch, tmp_path):
    """The pilot case: adopter repo with ONE board scope named nothing
    like 'dna-development' — verbs must work without --scope."""
    base = tmp_path / "src"
    _isolate_source(monkeypatch, base)
    _mk_sdlc_scope(base, "foundry-dev", containers=("stories", "issues"))
    # A non-SDLC scope must not confuse detection.
    (base / "just-agents" / "agents").mkdir(parents=True)
    scope = _invoke_and_capture_scope(monkeypatch)
    assert scope == "foundry-dev"


def test_autodetect_ignores_hidden_and_reserved_dirs(monkeypatch, tmp_path):
    base = tmp_path / "src"
    _isolate_source(monkeypatch, base)
    _mk_sdlc_scope(base, "foundry-dev")
    # Reserved/hidden dirs mirror FilesystemWritableSource.list_scopes.
    (base / "tenants" / "acme" / "stories").mkdir(parents=True)
    (base / ".hidden" / "stories").mkdir(parents=True)
    scope = _invoke_and_capture_scope(monkeypatch)
    assert scope == "foundry-dev"


# ── 4. ambiguous resolution → a clear, actionable error ─────────────────
#
# No branded fallback survives: when detection can't pick a sole scope,
# the CLI must fail honestly (naming both escape hatches) rather than
# silently defaulting to this repo's own board name.


def _invoke_and_expect_failure(monkeypatch, *args):
    """Run `story check` against a fake session that should never be
    reached (scope resolution fails before a session opens); return the
    invoke result so callers can assert on exit_code + output."""
    @contextmanager
    def _unreachable(scope=None, *, tenant=None, timeout=30.0):
        raise AssertionError("session opened despite ambiguous scope")
        yield  # pragma: no cover — contextmanager shape only

    return CliRunner().invoke(
        sdlc_cmd.sdlc,
        ["story", "check", "s-x", "--ac", "1", "--evidence", "e", *args],
        obj={SESSION_PROVIDER_KEY: _unreachable},
    )


def test_two_sdlc_scopes_raises_a_clear_error(monkeypatch, tmp_path):
    """Ambiguous (2+ SDLC scopes) → no guess, no branded default — a
    clear error naming both escape hatches."""
    base = tmp_path / "src"
    _isolate_source(monkeypatch, base)
    _mk_sdlc_scope(base, "board-a")
    _mk_sdlc_scope(base, "board-b")
    result = _invoke_and_expect_failure(monkeypatch)
    assert result.exit_code != 0
    assert "--scope" in result.output
    assert "DNA_SDLC_SCOPE" in result.output


def test_no_sdlc_scope_raises_a_clear_error(monkeypatch, tmp_path):
    base = tmp_path / "src"
    _isolate_source(monkeypatch, base)
    (base / "just-agents" / "agents").mkdir(parents=True)
    result = _invoke_and_expect_failure(monkeypatch)
    assert result.exit_code != 0
    assert "--scope" in result.output
    assert "DNA_SDLC_SCOPE" in result.output


def test_missing_source_dir_raises_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.setenv("DNA_SOURCE_URL", f"file://{tmp_path / 'nope'}")
    monkeypatch.delenv("DNA_SDLC_SCOPE", raising=False)
    result = _invoke_and_expect_failure(monkeypatch)
    assert result.exit_code != 0
    assert "--scope" in result.output
    assert "DNA_SDLC_SCOPE" in result.output


def test_no_branded_default_scope_constant_survives():
    """The compat literal must be gone entirely, not just unused."""
    assert not hasattr(sdlc_cmd, "DEFAULT_SCOPE")


# ── helper unit: the resolution is ONE shared helper ────────────────────


def test_every_sdlc_verb_shares_the_resolver(monkeypatch, tmp_path):
    """_scope_option is the single decorator every sdlc verb uses; its
    default resolution must route through _resolve_scope_default (one
    helper, not N copies)."""
    assert hasattr(sdlc_cmd, "_resolve_scope_default")
    base = tmp_path / "src"
    _isolate_source(monkeypatch, base)
    _mk_sdlc_scope(base, "foundry-dev")
    assert sdlc_cmd._resolve_scope_default() == "foundry-dev"
    monkeypatch.setenv("DNA_SDLC_SCOPE", "env-scope")
    assert sdlc_cmd._resolve_scope_default() == "env-scope"


def test_resolve_scope_default_raises_when_ambiguous(monkeypatch, tmp_path, capsys):
    """Direct-call regression for the helper itself (not just through a
    click command): ambiguous detection raises SystemExit and the
    printed message names both escape hatches — no branded guess."""
    base = tmp_path / "src"
    _isolate_source(monkeypatch, base)
    _mk_sdlc_scope(base, "board-a")
    _mk_sdlc_scope(base, "board-b")
    with pytest.raises(SystemExit):
        sdlc_cmd._resolve_scope_default()
    err = capsys.readouterr().err
    assert "--scope" in err
    assert "DNA_SDLC_SCOPE" in err
