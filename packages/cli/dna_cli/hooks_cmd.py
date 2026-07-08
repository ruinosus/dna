"""``dna sdlc hooks`` — install/uninstall/status of the git↔SDLC hook.

One command wires the symbiosis into a clone::

    dna sdlc hooks install     # git config core.hooksPath scripts/git-hooks
    dna sdlc hooks status      # what's wired + active story + coauthor
    dna sdlc hooks uninstall   # git config --unset core.hooksPath

``install`` points ``core.hooksPath`` at the repo-versioned hooks dir
(``scripts/git-hooks/``). NOTE: that directory becomes the clone's ONLY
hooks dir — git stops looking at ``.git/hooks`` entirely. If you keep
personal hooks there, move them into ``scripts/git-hooks/`` (they are
runnable from a versioned dir like any other) or skip the installer and
wire the ``prepare-commit-msg`` script by hand.

When ``scripts/git-hooks/prepare-commit-msg`` doesn't exist yet (e.g. a
project other than the DNA repo adopting the convention), ``install``
materializes it from the copy packaged inside dna-cli.

Registered onto the ``sdlc`` group at import time (same pattern as
``testkit_cmd``) — see ``dna_cli/__init__.py``.
"""
from __future__ import annotations

import stat
from pathlib import Path

import click

from dna_cli import _git_symbiosis as gs
from dna_cli._active_story import read_active_story
from dna_cli._ctx import fail
from dna_cli.sdlc_cmd import sdlc


def _hooks_path_config(root: Path) -> str | None:
    out = gs._run_git(["config", "--get", "core.hooksPath"], cwd=root)
    if out is None:
        return None
    return out.strip() or None


def _require_repo_root() -> Path:
    root = gs.repo_root()
    if root is None:
        raise fail("not inside a git repository (git rev-parse --show-toplevel failed)")
    return root


def _ensure_hook_file(root: Path) -> tuple[Path, bool]:
    """Make sure ``scripts/git-hooks/prepare-commit-msg`` exists + is
    executable. Returns ``(path, created)``."""
    hook = root / gs.HOOKS_DIR / gs.HOOK_NAME
    created = False
    if not hook.exists():
        src = gs.hook_source_path()
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_bytes(src.read_bytes())
        created = True
    mode = hook.stat().st_mode
    if not mode & stat.S_IXUSR:
        hook.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook, created


@sdlc.group("hooks")
def hooks_group() -> None:
    """Git hooks that close the git↔SDLC loop (Work-Item trailers)."""


@hooks_group.command("install")
def cmd_hooks_install() -> None:
    """Wire the repo's versioned hooks dir into this clone.

    Sets ``git config core.hooksPath scripts/git-hooks`` — from then on
    every ``git commit`` runs the versioned ``prepare-commit-msg``, which
    stamps ``Work-Item:`` + the dna-sdlc[bot] provenance trailer whenever
    a Story is active (``dna sdlc story start``).
    """
    root = _require_repo_root()
    hook, created = _ensure_hook_file(root)
    current = _hooks_path_config(root)
    if current not in (None, gs.HOOKS_DIR):
        raise fail(
            f"core.hooksPath is already set to '{current}' — refusing to overwrite. "
            f"Unset it first (git config --unset core.hooksPath) or merge your hooks "
            f"into {gs.HOOKS_DIR}/."
        )
    if gs._run_git(["config", "core.hooksPath", gs.HOOKS_DIR], cwd=root) is None:
        raise fail("git config core.hooksPath failed")
    if created:
        click.secho(f"  created {gs.HOOKS_DIR}/{gs.HOOK_NAME} (from dna-cli packaged copy)", fg="cyan")
    click.secho(f"INSTALLED — core.hooksPath = {gs.HOOKS_DIR}", fg="green")
    click.echo(
        f"  note: {gs.HOOKS_DIR}/ is now this clone's ONLY hooks dir "
        f"(.git/hooks is no longer consulted)."
    )
    click.echo(
        "  commits made with an active story (dna sdlc story start) now get "
        f"'{gs.WORK_ITEM_TRAILER}:' + '{gs.COAUTHOR_TRAILER}: {gs.sdlc_coauthor()}'."
    )


@hooks_group.command("uninstall")
def cmd_hooks_uninstall() -> None:
    """Remove the ``core.hooksPath`` wiring (git falls back to .git/hooks)."""
    root = _require_repo_root()
    current = _hooks_path_config(root)
    if current is None:
        click.secho("core.hooksPath not set — nothing to uninstall", fg="yellow")
        return
    if current != gs.HOOKS_DIR:
        raise fail(
            f"core.hooksPath points at '{current}' (not '{gs.HOOKS_DIR}') — "
            f"not ours to remove; unset it manually if intended."
        )
    if gs._run_git(["config", "--unset", "core.hooksPath"], cwd=root) is None:
        raise fail("git config --unset core.hooksPath failed")
    click.secho("UNINSTALLED — core.hooksPath unset (git uses .git/hooks again)", fg="green")


@hooks_group.command("status")
def cmd_hooks_status() -> None:
    """Show the symbiosis wiring: hooksPath, hook file, active story, coauthor."""
    root = _require_repo_root()
    current = _hooks_path_config(root)
    hook = root / gs.HOOKS_DIR / gs.HOOK_NAME
    installed = current == gs.HOOKS_DIR
    click.secho("git↔SDLC symbiosis", fg="cyan", bold=True)
    click.echo(f"  repo:            {root}")
    click.echo(f"  core.hooksPath:  {current or '(not set)'}"
               + ("" if installed else f"  → run `dna sdlc hooks install`"))
    if hook.exists():
        exec_ok = bool(hook.stat().st_mode & stat.S_IXUSR)
        click.echo(f"  hook file:       {gs.HOOKS_DIR}/{gs.HOOK_NAME}"
                   + ("" if exec_ok else "  (NOT executable!)"))
    else:
        click.echo(f"  hook file:       MISSING ({gs.HOOKS_DIR}/{gs.HOOK_NAME})")
    active = read_active_story(start=root)
    if active:
        click.echo(f"  active story:    {active[0]}:{active[1]}  → commits get "
                   f"'{gs.WORK_ITEM_TRAILER}: Story/{active[1]}'")
    else:
        click.echo("  active story:    (none — commits are not stamped)")
    click.echo(f"  coauthor:        {gs.sdlc_coauthor()}"
               + (f"  (via ${gs.COAUTHOR_ENV})" if gs.sdlc_coauthor() != gs.DEFAULT_SDLC_COAUTHOR else ""))
