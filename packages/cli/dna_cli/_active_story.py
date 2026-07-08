"""Active-Story pointer — `.dna/active-story.txt` at the repo root.

Written by ``dna sdlc story start <name>`` so that out-of-band tools
(Claude Code hooks, IDE plugins, dashboards) can attribute their
events to the Story the human-or-agent is currently working on.

File format (single line, plain text)::

    <scope>:<story-name>

Examples::

    dna-development:s-foo
    hr-screening:s-bar

A trailing newline is optional. The file is gitignored — it is per-
workstation state, not source-of-truth, so a fresh clone has no
active Story until ``story start`` is invoked.

Discovery walks up from ``cwd`` looking for ``.git`` to anchor the
``.dna/`` directory; this matches the convention used by source
replicas (``.dna-replicas.yaml`` discovery in ``source_replicas.py``).
Override via ``DNA_ACTIVE_STORY_PATH`` for tests.
"""
from __future__ import annotations

import os
from pathlib import Path

_ENV = "DNA_ACTIVE_STORY_PATH"
_FILENAME = ".dna/active-story.txt"


def _find_repo_root(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` looking for ``.git`` (file or dir).

    Returns ``None`` when no repo root is found. Symmetric with the
    discovery used in ``source_replicas.py``.
    """
    cur = (start or Path.cwd()).resolve()
    for parent in (cur, *cur.parents):
        if (parent / ".git").exists():
            return parent
    return None


def get_active_story_path(*, start: Path | None = None) -> Path:
    """Resolve the canonical pointer path. Order of precedence:

    1. ``DNA_ACTIVE_STORY_PATH`` env var (tests + advanced setups)
    2. ``<repo-root>/.dna/active-story.txt`` if walking up finds ``.git``
    3. ``<cwd>/.dna/active-story.txt`` as fallback (loose-tree mode)
    """
    env = os.environ.get(_ENV)
    if env:
        return Path(env)
    root = _find_repo_root(start)
    if root is not None:
        return root / _FILENAME
    return (start or Path.cwd()).resolve() / _FILENAME


def write_active_story(scope: str, name: str, *, start: Path | None = None) -> Path:
    """Stamp ``<scope>:<name>`` to the pointer file. Creates the
    parent directory if missing. Returns the resolved path. Atomic
    via tmpfile + rename.
    """
    if not scope or not name:
        raise ValueError("scope and name must both be non-empty")
    if ":" in scope or ":" in name:
        # Reserve `:` as the field separator. Story slugs use `s-` /
        # `f-` / `e-` prefixes by convention so this never collides
        # in practice; defensive guard just in case.
        raise ValueError("scope/name must not contain ':'")
    path = get_active_story_path(start=start)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(f"{scope}:{name}\n", encoding="utf-8")
    tmp.replace(path)
    return path


def read_active_story(
    *, start: Path | None = None
) -> tuple[str, str] | None:
    """Read the pointer; returns ``(scope, name)`` or ``None`` when
    absent / empty / malformed. Non-fatal — callers (hooks) treat
    ``None`` as "no active story; broadcast as ephemeral".
    """
    path = get_active_story_path(start=start)
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if not raw:
        return None
    if ":" not in raw:
        return None
    scope, _, name = raw.partition(":")
    scope = scope.strip()
    name = name.strip()
    if not scope or not name:
        return None
    return scope, name


def clear_active_story(*, start: Path | None = None) -> bool:
    """Remove the pointer file. Returns True if a file was removed,
    False if it was already absent. Idempotent.
    """
    path = get_active_story_path(start=start)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def clear_if_matches(
    scope: str, name: str, *, start: Path | None = None
) -> bool:
    """Clear the pointer ONLY when it currently points at the given
    Story. Used by ``dna sdlc story done|block|cancel`` so that
    closing some other Story (not the active one) doesn't blank the
    pointer. Returns True when cleared.
    """
    cur = read_active_story(start=start)
    if cur is None:
        return False
    if cur != (scope, name):
        return False
    return clear_active_story(start=start)
