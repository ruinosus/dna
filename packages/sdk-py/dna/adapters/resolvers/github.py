"""GitHubResolver — ResolverPort for github: URIs."""
from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from dna.kernel.protocols import ResolvedItem, ResolveError

logger = logging.getLogger(__name__)


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

    async def resolve(self, uri: str, dep: dict[str, Any]) -> list[ResolvedItem]:
        raw = uri.removeprefix("github:")
        match = re.match(
            r"^(?P<owner>[^/]+)/(?P<repo>[^/@]+)(?:/(?P<path>[^@]+))?(?:@(?P<ref>.+))?$",
            raw,
        )
        if not match:
            raise ResolveError(f"Invalid github URI: {uri}")

        owner = match.group("owner")
        repo = match.group("repo")
        sub_path = match.group("path")
        ref = match.group("ref")
        clone_url = f"https://github.com/{owner}/{repo}.git"

        try:
            # Use mkdtemp (not TemporaryDirectory context manager) so the dir
            # persists until cache.store() copies the files. The OS cleans
            # /tmp on reboot; the cache is the permanent copy.
            tmp = tempfile.mkdtemp(prefix="dna-github-")
            ref_args = ["--branch", ref] if ref else []
            subprocess.run(
                ["git", "clone", "--depth", "1", *ref_args, clone_url, tmp],
                check=True, capture_output=True, timeout=60,
            )
            source = Path(tmp) / sub_path if sub_path else Path(tmp)

            from dna.adapters.resolvers.local import LocalResolver
            local = LocalResolver()
            items_filter = dep.get("items")
            if items_filter:
                requested = local._collect_requested(dep)
                if requested:
                    return local._resolve_by_category(source, requested)
            return local._resolve_all(source)

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise ResolveError(f"Git clone failed for {clone_url}: {e}") from e
