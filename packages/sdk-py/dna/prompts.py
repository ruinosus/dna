"""``dna.load_prompts`` — the one-liner that collapses the prompt shim.

A DNA consumer that composes agent prompts from a scope used to hand-write a
~166-line module: boot the kernel, resolve the base dir, guard every agent
lookup (``mi.one("Agent", x) is None``) because a miss returned a placeholder
string, then ``.rstrip("\\n")`` every result because composition leaked
trailing newlines.

With the fail-loud builder (``s-dx-build-prompt-fail-loud``) and clean output
(``s-dx-clean-composition-output``) in place, that whole shim becomes::

    from dna import load_prompts

    prompts = load_prompts("helpdesk")
    TRIAGE_INSTRUCTIONS = prompts["triage"]      # composed, clean, or raises

``load_prompts`` boots a filesystem kernel for ``scope`` and returns a
:class:`PromptLibrary` — a lazy, cached, read-only mapping from agent name to
its composed system prompt. A missing agent raises :class:`~dna.AgentNotFound`
(never a placeholder string); the returned text is already stripped of trailing
newlines.
"""
from __future__ import annotations

import os
from typing import Iterator, Mapping

__all__ = ["PromptLibrary", "load_prompts"]


class PromptLibrary(Mapping[str, str]):
    """Lazy, cached mapping ``agent name -> composed prompt`` over one scope.

    ``lib["triage"]`` composes the ``triage`` agent's prompt on first access
    (delegating to :py:meth:`ManifestInstance.build_prompt`), caches it, and
    returns it already clean. A missing agent raises
    :class:`~dna.AgentNotFound`. ``"triage" in lib`` and ``list(lib)`` /
    ``lib.names()`` enumerate the prompt-target agents in the scope without
    composing them.

    Read-only and side-effect-free beyond the internal cache — safe to build
    once at import time and share.
    """

    def __init__(self, mi: object) -> None:
        #: the underlying ManifestInstance (kept for callers that need to drop
        #: down to the full kernel surface).
        self.mi = mi
        self._cache: dict[str, str] = {}

    # -- Mapping protocol -----------------------------------------------------

    def __getitem__(self, name: str) -> str:
        cached = self._cache.get(name)
        if cached is not None:
            return cached
        # build_prompt raises AgentNotFound on a miss and returns clean text
        # (the two quick-wins this helper is built on).
        text = self.mi.build_prompt(agent=name)  # type: ignore[attr-defined]
        self._cache[name] = text
        return text

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in set(self.names())

    def __iter__(self) -> Iterator[str]:
        return iter(self.names())

    def __len__(self) -> int:
        return len(self.names())

    # -- Introspection --------------------------------------------------------

    def names(self) -> list[str]:
        """Names of every prompt-target document (Agent-like) in the scope,
        sorted. Does NOT compose them — cheap enough to call for discovery."""
        seen: set[str] = set()
        kinds = getattr(self.mi, "_kinds", {})
        for doc in getattr(self.mi, "documents", []):
            kp = kinds.get((doc.api_version, doc.kind))
            if kp is not None and getattr(kp, "is_prompt_target", False):
                seen.add(doc.name)
        return sorted(seen)

    def __repr__(self) -> str:  # pragma: no cover — cosmetic
        scope = getattr(self.mi, "scope", "?")
        return f"PromptLibrary(scope={scope!r}, agents={self.names()})"


def load_prompts(scope: str, base_dir: str | None = None) -> PromptLibrary:
    """Compose the prompts of ``scope`` behind a mapping.

    ``base_dir`` follows the same convention as :py:meth:`Kernel.quick`: it is
    the directory that holds ``<scope>/`` (the ``.dna`` scopes root). When
    omitted it falls back to the ``DNA_BASE_DIR`` environment variable, then to
    ``".dna"`` in the current working directory — the same precedence the
    ``dna`` CLI uses.

    Returns a :class:`PromptLibrary`; see its docstring for the access
    contract (lazy, cached, fail-loud on a missing agent).
    """
    if base_dir is None:
        base_dir = os.environ.get("DNA_BASE_DIR") or ".dna"
    # Imported lazily to keep ``import dna`` cheap and avoid a hard cycle
    # (kernel imports pull in the whole extension graph).
    from dna.kernel import Kernel

    mi = Kernel.quick(scope, base_dir=base_dir)
    return PromptLibrary(mi)
