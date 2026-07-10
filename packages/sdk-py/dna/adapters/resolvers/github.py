"""GitHubResolver — ResolverPort for github: URIs."""
from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dna.kernel.protocols import ResolvedItem, ResolveError

logger = logging.getLogger(__name__)

# The one grammar for github: URIs — ``github:owner/repo[/subdir][@ref]``.
# Shared by ``resolve()`` (dependency resolution) and ``fetch_tree()``
# (the imperative fetch behind `dna install`) so the two can never drift.
_URI_RE = re.compile(
    r"^(?P<owner>[^/]+)/(?P<repo>[^/@]+)(?:/(?P<path>[^@]+))?(?:@(?P<ref>.+))?$"
)


@dataclass(frozen=True)
class FetchedTree:
    """Result of ``GitHubResolver.fetch_tree`` — a cloned working tree.

    ``root`` points INSIDE a persistent temp clone (``dna-github-*``; the OS
    cleans /tmp — callers copy what they keep). ``commit`` is the resolved
    HEAD sha, so callers can pin provenance to an immutable revision even
    when the URI used a moving ref (branch/tag) or no ref at all.
    """
    root: Path
    owner: str
    repo: str
    subdir: str | None
    ref: str | None
    commit: str | None


def parse_github_uri(uri: str) -> tuple[str, str, str | None, str | None]:
    """Parse ``github:owner/repo[/subdir][@ref]`` → (owner, repo, subdir, ref).

    Raises ResolveError on anything that doesn't match the grammar.
    """
    raw = uri.removeprefix("github:")
    match = _URI_RE.match(raw)
    if not match:
        raise ResolveError(f"Invalid github URI: {uri}")
    return (
        match.group("owner"),
        match.group("repo"),
        match.group("path"),
        match.group("ref"),
    )


class GitHubResolver:
    """Resolves dependencies from GitHub repositories.

    Clones the repo to a persistent temp dir (not auto-cleaned) so that
    the cache.store() step can copy files from source_path. The Kernel
    manages the lifecycle: resolve → cache.store(copies files) → done.
    """

    def cache_key(self, uri: str) -> str:
        raw = uri.removeprefix("github:")
        safe = re.sub(r"[^a-zA-Z0-9_-]", "-", raw).strip("-")
        return f"github-{safe}"

    def fetch_tree(self, uri: str, *, timeout: int = 60) -> FetchedTree:
        """Shallow-clone the repo behind a ``github:`` URI and return the
        requested working tree (repo root, or ``subdir`` when the URI names
        one) plus provenance metadata (the resolved HEAD commit).

        This is the imperative fetch entry used by ``dna install``: the
        caller scans the returned tree with the kernel's registered readers
        instead of consuming pre-listed ``ResolvedItem``s. It is NOT part of
        the ``ResolverPort`` Protocol (that surface is parity-locked); it is
        an adapter-level helper.

        Raises ResolveError on bad URIs, clone failures (offline / missing
        repo / unknown ref) and when ``subdir`` does not exist in the repo.
        """
        owner, repo, sub_path, ref = parse_github_uri(uri)
        clone_url = f"https://github.com/{owner}/{repo}.git"

        # mkdtemp (not TemporaryDirectory context manager) so the tree
        # outlives this call; the OS cleans /tmp — callers copy what they
        # keep (same lifecycle contract resolve() has always had).
        tmp = tempfile.mkdtemp(prefix="dna-github-")
        ref_args = ["--branch", ref] if ref else []
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", *ref_args, clone_url, tmp],
                check=True, capture_output=True, timeout=timeout,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise ResolveError(f"Git clone failed for {clone_url}: {e}") from e

        commit: str | None = None
        try:
            out = subprocess.run(
                ["git", "-C", tmp, "rev-parse", "HEAD"],
                check=True, capture_output=True, timeout=10, text=True,
            )
            commit = out.stdout.strip() or None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # Provenance degrades to ref-only; the clone itself succeeded.
            logger.warning("Could not resolve HEAD commit for %s", clone_url)

        root = Path(tmp) / sub_path if sub_path else Path(tmp)
        if not root.is_dir():
            raise ResolveError(
                f"Subdirectory {sub_path!r} does not exist in "
                f"{owner}/{repo}" + (f"@{ref}" if ref else "")
            )
        return FetchedTree(
            root=root, owner=owner, repo=repo,
            subdir=sub_path, ref=ref, commit=commit,
        )

    async def resolve(self, uri: str, dep: dict[str, Any]) -> list[ResolvedItem]:
        # fetch_tree owns the parse + clone (one code path). Side benefit:
        # a URI naming a nonexistent subdir now raises ResolveError (which
        # instance building reports as a resolve error) instead of leaking
        # FileNotFoundError from the directory walk below.
        fetched = self.fetch_tree(uri)
        source = fetched.root

        from dna.adapters.resolvers.local import LocalResolver
        local = LocalResolver()
        items_filter = dep.get("items")
        if items_filter:
            requested = local._collect_requested(dep)
            if requested:
                return local._resolve_by_category(source, requested)
        return local._resolve_all(source)
