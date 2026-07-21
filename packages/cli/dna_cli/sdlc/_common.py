"""Shared spine for the ``dna sdlc`` command groups.

Everything here was lifted verbatim out of ``sdlc_cmd.py`` — the helpers that
nearly every group depends on: the clock, the actor, the git/gh probes, the
timeline appender, the document envelope, the post-transition hook registry
and the scope-resolution chain behind ``--scope``.

Kept deliberately free of any ``@sdlc.*`` command definition so group modules
can import it without cycles.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import click

# The SDLC write PRIMITIVES live in the transport-agnostic core
# ``dna.application.sdlc`` (adr-faces-reorg) so the CLI + the MCP server share
# ONE write path. The thin wrappers below adapt them to the CLI's clock +
# actor + ``source="cli"``.
from dna.application.sdlc import (
    append_event as _core_append_event,
    build_raw as _core_build_raw,
)

DEFAULT_SCOPE = "dna-development"

# Journey phases + methodologies — defined early because story/plan command
# decorators (cmd_story_start, cmd_plan_create) reference them in click.Choice.
VALID_JOURNEY_PHASES = ("discover", "specify", "plan", "build", "reflect")
VALID_JOURNEY_METHODOLOGIES = (
    "superpowers", "bmad", "spec-kit", "kiro",
    "rfc", "adr", "ad-hoc", "custom",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cli_actor() -> str:
    """Resolve who's filing/grooming the doc. Override via env when
    a human is using the CLI directly (default 'claude-code' since
    the agent is the canonical CLI consumer in this repo)."""
    import os
    return os.environ.get("DNA_CLI_REPORTER", "claude-code")


def _git_head_sha() -> str | None:
    """Return short SHA of git HEAD when invoked inside a git working
    tree; None otherwise. Best-effort: any exception → None (the CLI
    keeps working from non-git directories like /tmp test fixtures)."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if result.returncode != 0:
            return None
        sha = result.stdout.strip()
        return sha if sha else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _git_current_branch() -> str | None:
    """Current git branch name; None outside a working tree (best-effort,
    mirrors ``_git_head_sha``)."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        if result.returncode != 0:
            return None
        branch = result.stdout.strip()
        return branch if branch and branch != "HEAD" else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _gh_open_prs_for_branch(branch: str) -> list[dict[str, Any]] | None:
    """Open PRs whose head is ``branch``, via the ``gh`` CLI.

    Fail-soft (i-133): returns ``None`` when gh is missing / errors / times
    out (≤3s) — the Acme gateway intermittently blocks api.github.com and
    the guard must never brick the review transition on network weather.
    """
    import json as _json
    import subprocess
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--head", branch, "--state", "open",
             "--json", "number"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        if result.returncode != 0:
            return None
        parsed = _json.loads(result.stdout or "[]")
        return parsed if isinstance(parsed, list) else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, ValueError):
        return None


def _parse_iso_utc(value: str | None) -> datetime | None:
    """Parse an ISO timestamp (gh emits ``Z``-suffixed) to aware UTC;
    None on anything unparsable."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _gh_open_prs() -> list[dict[str, Any]] | None:
    """ALL open PRs on the repo, via the ``gh`` CLI (i-127).

    The brief's "PR aberto esquecido" radar — the board covers "Story em
    review sem PR" but not the inverse (PR #278 ficou 1 dia órfão).
    Fail-soft like ``_gh_open_prs_for_branch``: None when gh is missing /
    errors / times out (≤3s — the gateway intermittently blocks
    api.github.com).
    """
    import json as _json
    import subprocess
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "open",
             "--json", "number,title,headRefName,createdAt"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        if result.returncode != 0:
            return None
        parsed = _json.loads(result.stdout or "[]")
        return parsed if isinstance(parsed, list) else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, ValueError):
        return None


def review_pr_guard(
    prs: list[dict[str, Any]] | None,
    *, no_pr: bool, reason: str | None,
) -> tuple[bool, list[str]]:
    """Pure decision for the review transition (i-133): review = PR aberto.

    Returns ``(allowed, warnings)``. ``prs is None`` means gh was
    unavailable — allow with a warning (fail-soft). Empty list means no
    open PR on the current branch: block unless ``--no-pr --reason`` was
    given (the explicit escape hatch).
    """
    if prs is None:
        return True, [
            "gh indisponível — não consegui verificar PR aberto pra branch "
            "(guard pulado, fail-soft).",
        ]
    if prs:
        return True, []
    if no_pr:
        if not (reason or "").strip():
            return False, [
                "--no-pr exige --reason \"<por que está marcando review sem PR>\".",
            ]
        return True, [
            f"review SEM PR aberto (escape --no-pr): {reason}",
        ]
    return False, [
        "nenhum PR aberto pra branch corrente — regra do repo: review = PR "
        "aberto. Abra o PR primeiro (gh pr create) ou use "
        '--no-pr --reason "<por quê>" pra prosseguir mesmo assim.',
    ]


def _append_timeline(spec: dict[str, Any], event_type: str, **fields: Any) -> None:
    """Append an event to ``spec.timeline[]`` (creates the list if absent).

    Thin CLI adapter over the shared core ``append_event`` — stamps ``at`` (now),
    ``actor`` (env-driven), ``type``, ``source: cli`` and drops falsy extras
    (byte-identical to the prior inline impl). The timeline-append logic itself
    lives ONCE in ``dna.application.sdlc``, shared with the MCP write tools."""
    _core_append_event(
        spec, event_type,
        now=_now_iso(), actor=_cli_actor(), source="cli", **fields,
    )


def _build_raw(kind: str, name: str, spec: dict[str, Any]) -> dict[str, Any]:
    """The kernel document envelope — delegates to the shared core ``build_raw``
    so the CLI + MCP write the SAME apiVersion + metadata shape."""
    return _core_build_raw(kind, name, spec)


# ─── Post-transition hook point ──────────────────────────────────────
# Extension point for side-effects that fire AFTER a lifecycle transition
# persists (``story done``, ``feature ship``, ``session capture``, ...).
# The registry ships EMPTY in this distribution — host platforms
# register their own scribes (e.g. realtime lesson synthesis)
# without patching the CLI (explicit contract, extraction design
# spec §10.3).
#
# Contract: ``fn(kind: str, name: str, transition: str, doc: dict, ctx:
# dict) -> None``. ``doc`` is the freshest spec/raw available at fire
# time; ``ctx`` always carries ``scope`` (plus call-site extras).
# Firing is FAIL-SOFT: a crashing hook warns and never blocks the
# command — same contract the inline try/except blocks used to honor.

_POST_TRANSITION_HOOKS: list[Any] = []


def register_post_transition_hook(fn: Any) -> None:
    """Register a post-transition hook (idempotent — same fn once)."""
    if fn not in _POST_TRANSITION_HOOKS:
        _POST_TRANSITION_HOOKS.append(fn)


def _fire_post_transition(
    kind: str, name: str, transition: str,
    doc: dict[str, Any] | None, ctx: dict[str, Any] | None = None,
) -> None:
    """Fire every registered hook, fail-soft (warn, never raise)."""
    for fn in list(_POST_TRANSITION_HOOKS):
        try:
            fn(kind, name, transition, doc or {}, ctx or {})
        except Exception as e:  # noqa: BLE001 — fail-soft is the contract
            click.secho(
                f"⚠ post-transition hook "
                f"{getattr(fn, '__name__', repr(fn))} crashed (non-fatal): {e}",
                fg="yellow",
            )


#: Directory containers whose presence marks a scope as holding SDLC
#: structure (the Kinds `dna sdlc` operates on live in these).
_SDLC_CONTAINERS = ("stories", "features", "epics", "issues", "roadmaps")


def _autodetect_sdlc_scope() -> str | None:
    """Return the SOLE scope in the source with SDLC structure, else None.

    i-012 (pilot phase-2): adopter repos have arbitrary board-scope names
    ('foundry-dev', ...) — when the source holds exactly ONE scope with
    SDLC containers, use it. Ambiguous (0 or 2+) → None (caller falls
    back). Filesystem probe only (the CLI boots filesystem sources —
    see _ctx module docstring); scope enumeration mirrors
    FilesystemWritableSource.list_scopes (non-hidden dirs, minus the
    reserved 'tenants'/'_legacy').
    """
    from pathlib import Path
    from urllib.parse import urlparse

    from dna_cli._ctx import _resolve_source_url

    url = _resolve_source_url()
    parsed = urlparse(url)
    if parsed.scheme not in ("file", "fs", ""):
        return None  # non-filesystem source — no cheap probe
    path = (parsed.netloc + parsed.path) if parsed.netloc else (parsed.path or url)
    base = Path(path)
    if not base.is_dir():
        return None
    reserved = {"tenants", "_legacy"}
    candidates = [
        d.name
        for d in sorted(base.iterdir())
        if d.is_dir()
        and not d.name.startswith(".")
        and d.name not in reserved
        and any((d / c).is_dir() for c in _SDLC_CONTAINERS)
    ]
    return candidates[0] if len(candidates) == 1 else None


def _resolve_scope_default() -> str:
    """Resolve the scope for sdlc verbs when --scope is absent (i-012).

    Precedence (documented in docs/guides/sdlc.md):
      1. --scope explicit          (click passes it through; this helper
                                    only runs when the flag is absent)
      2. env DNA_SDLC_SCOPE
      3. auto-detect               (sole SDLC scope in the source)
      4. DEFAULT_SCOPE             ('dna-development' — compat fallback)
    """
    env = os.environ.get("DNA_SDLC_SCOPE")
    if env:
        return env
    detected = _autodetect_sdlc_scope()
    if detected is not None:
        if detected != DEFAULT_SCOPE:
            click.secho(
                f"scope: {detected} (auto-detected sole SDLC scope; "
                f"override with --scope or DNA_SDLC_SCOPE)",
                fg="cyan", err=True,
            )
        return detected
    return DEFAULT_SCOPE


def _scope_callback(ctx: Any, param: Any, value: str | None) -> str:
    del ctx, param
    return value if value else _resolve_scope_default()


def _scope_option(f):
    return click.option(
        "--scope", default=None, callback=_scope_callback,
        help="Scope holding the SDLC docs (default: $DNA_SDLC_SCOPE, else "
             "the auto-detected sole SDLC scope in the source, else "
             "dna-development).",
    )(f)


def _csv(value: str | None) -> list[str] | None:
    """Parse comma-separated CLI input. None/empty → None (not stamped)."""
    if value is None:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts or None
