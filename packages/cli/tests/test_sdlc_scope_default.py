"""i-012 — `dna sdlc` scope default is configurable, not hardcoded.

Pilot phase-2 friction: every sdlc verb demanded --scope because the
default was the hardcoded 'dna-development' (which only works in this
repo by name coincidence). Adopter repos have arbitrary board-scope
names ('foundry-dev', ...).

Documented precedence (single helper, applied to every sdlc verb via
_scope_option):

  1. --scope explicit            (always wins)
  2. env DNA_SDLC_SCOPE
  3. auto-detect                 (sole scope in the source with SDLC
                                  structure — stories/features/epics/
                                  issues containers)
  4. DEFAULT_SCOPE               ('dna-development' — compat fallback)
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from click.testing import CliRunner

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

    monkeypatch.setattr(sdlc_cmd, "dna_session", _fake)
    r = CliRunner().invoke(
        sdlc_cmd.sdlc,
        ["story", "check", "s-x", "--ac", "1", "--evidence", "e", *args],
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


# ── 4. fallback: hardcoded compat default ───────────────────────────────


def test_two_sdlc_scopes_fall_back_to_default(monkeypatch, tmp_path):
    """Ambiguous (2+ SDLC scopes) → no guess, compat default."""
    base = tmp_path / "src"
    _isolate_source(monkeypatch, base)
    _mk_sdlc_scope(base, "board-a")
    _mk_sdlc_scope(base, "board-b")
    scope = _invoke_and_capture_scope(monkeypatch)
    assert scope == sdlc_cmd.DEFAULT_SCOPE


def test_no_sdlc_scope_falls_back_to_default(monkeypatch, tmp_path):
    base = tmp_path / "src"
    _isolate_source(monkeypatch, base)
    (base / "just-agents" / "agents").mkdir(parents=True)
    scope = _invoke_and_capture_scope(monkeypatch)
    assert scope == sdlc_cmd.DEFAULT_SCOPE


def test_missing_source_dir_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.setenv("DNA_SOURCE_URL", f"file://{tmp_path / 'nope'}")
    monkeypatch.delenv("DNA_SDLC_SCOPE", raising=False)
    scope = _invoke_and_capture_scope(monkeypatch)
    assert scope == sdlc_cmd.DEFAULT_SCOPE


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
