"""``dna.load_tools`` — the agent-facing tool surface, as data.

The DNA already governs persona, instruction and guardrails declaratively.
A **Tool** (record-plane Kind, ``kinds/tool.kind.yaml``) moves the last
hard-coded piece into the same plane: the ``description`` the model reads to
decide whether to call a tool, and the JSON Schema of its ``parameters``.
``load_tools`` is the consumer one-liner — the twin of :func:`load_prompts`::

    from dna import load_tools

    tools = load_tools("open-swe")
    surface = tools["github-search"]      # or raises ToolNotFound
    surface.description                   # the text the model reads
    surface.parameters                    # the args JSON Schema

Because a Tool is one declarative document, the SAME surface is served to a
Python backend (a ``@tool`` function's ``description=``) and a TypeScript
frontend (CopilotKit ``useCopilotAction``) from ONE source of truth — the
first place the Py↔TS descriptor parity pays off in a real consumer (see
``examples/tools_as_data``).

``load_tools`` boots a filesystem kernel for ``scope`` and returns a
:class:`ToolLibrary` — a lazy, cached, read-only mapping from tool name to its
:class:`ToolSurface`. A missing tool raises :class:`~dna.ToolNotFound` (never
an empty surface). Overlay-aware: a tenant overlay that overrides a tool's
``metadata.description`` / ``spec.input_schema`` is reflected here, because a
Tool is an overlayable Kind — the SaaS value hook.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

from dna.kernel.errors import ToolNotFound

__all__ = ["ToolSurface", "ToolLibrary", "load_tools", "ToolNotFound"]


@dataclass(frozen=True)
class ToolSurface:
    """The agent-facing surface of a Tool — exactly what a tool-calling model
    is shown to decide whether, and how, to call it.

    - ``description``: the natural-language description (``metadata.description``
      of the Tool doc) — the text the model reads.
    - ``parameters``: the JSON Schema of the arguments (``spec.input_schema``)
      — what the model fills in. Empty ``{}`` when the tool takes no args.
    """

    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


class ToolLibrary(Mapping[str, ToolSurface]):
    """Lazy, cached mapping ``tool name -> ToolSurface`` over one scope.

    ``lib["github-search"]`` reads the Tool document on first access, projects
    its agent-facing surface, caches it, and returns it. A missing tool raises
    :class:`~dna.ToolNotFound`. ``"x" in lib`` and ``list(lib)`` / ``lib.names()``
    enumerate the Tool documents without projecting them.

    Read-only and side-effect-free beyond the internal cache — safe to build
    once and share.
    """

    def __init__(self, mi: object) -> None:
        #: the underlying ManifestInstance (kept for callers that need the
        #: full kernel surface, e.g. the tool's invocation metadata).
        self.mi = mi
        self._cache: dict[str, ToolSurface] = {}

    # -- Mapping protocol -----------------------------------------------------

    def __getitem__(self, name: str) -> ToolSurface:
        cached = self._cache.get(name)
        if cached is not None:
            return cached
        # ``_one`` is the SDK-internal, non-deprecated twin of ``one`` — it
        # delegates record-plane reads to the kernel query surface and
        # propagates the MI's tenant, so a tenant-bound library reads the
        # overlay-merged Tool.
        doc = self.mi._one("Tool", name)  # type: ignore[attr-defined]
        if doc is None:
            raise ToolNotFound(
                name, scope=getattr(self.mi, "scope", None), available=self.names()
            )
        meta = getattr(doc, "metadata", None) or {}
        spec = getattr(doc, "spec", None) or {}
        description = (meta.get("description") if hasattr(meta, "get") else "") or ""
        raw_params = (spec.get("input_schema") if hasattr(spec, "get") else None) or {}
        surface = ToolSurface(description=description, parameters=dict(raw_params))
        self._cache[name] = surface
        return surface

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in set(self.names())

    def __iter__(self) -> Iterator[str]:
        return iter(self.names())

    def __len__(self) -> int:
        return len(self.names())

    # -- Introspection --------------------------------------------------------

    def names(self) -> list[str]:
        """Names of every Tool document in the scope, sorted. Does NOT project
        their surfaces — cheap enough to call for discovery."""
        return sorted(getattr(d, "name", "") for d in self.mi._all("Tool"))  # type: ignore[attr-defined]

    def __repr__(self) -> str:  # pragma: no cover — cosmetic
        scope = getattr(self.mi, "scope", "?")
        return f"ToolLibrary(scope={scope!r}, tools={self.names()})"


def load_tools(scope: str, base_dir: str | None = None) -> ToolLibrary:
    """Load the Tool surfaces of ``scope`` behind a mapping.

    ``base_dir`` follows the :py:meth:`Kernel.quick` convention: the directory
    that holds ``<scope>/`` (the ``.dna`` scopes root). Omitted → the
    ``DNA_BASE_DIR`` environment variable, then ``".dna"`` in the cwd — the
    same precedence :func:`load_prompts` and the ``dna`` CLI use.

    Returns a :class:`ToolLibrary`; see its docstring for the access contract
    (lazy, cached, fail-loud on a missing tool, overlay-aware).
    """
    if base_dir is None:
        base_dir = os.environ.get("DNA_BASE_DIR") or ".dna"
    # Imported lazily to keep ``import dna`` cheap and avoid a hard cycle.
    from dna.kernel import Kernel

    mi = Kernel.quick(scope, base_dir=base_dir)
    return ToolLibrary(mi)
