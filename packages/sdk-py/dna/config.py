"""``dna.config.yaml`` — declarative port wiring (``s-dx-kernel-from-config``).

A DNA host used to wire its ports imperatively::

    kernel = Kernel.auto()
    source = SqlAlchemySource("postgresql+asyncpg://…"); await source.connect()
    kernel.source(source)
    kernel.record_search_provider(PgVecRecordSearchProvider(kernel, dsn=…))
    kernel.embedding_provider(OnnxEmbeddingProvider())

``dna.config.yaml`` externalizes that choice so the SAME file drives both the
Python and the TypeScript SDK (the schema is language-agnostic)::

    # dna.config.yaml
    source: postgresql://user:pass@host/db   # or sqlite:///./dev.db, file://.dna
    search: pgvector        # pgvector | sqlite-vec | off   (default: off)
    embedding: onnx         # onnx | fake | off             (default: off / fake floor)

Only ``source`` is required. This module parses + VALIDATES the file (unknown
keys and bad enum values fail loud with a didactic message); the wiring itself
lives in :func:`dna.kernel.Kernel.from_config`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["DnaConfig", "load_config", "find_config", "CONFIG_FILENAME"]

CONFIG_FILENAME = "dna.config.yaml"

_VALID_SEARCH = ("off", "pgvector", "sqlite-vec")
_VALID_EMBEDDING = ("off", "fake", "onnx")
_KNOWN_KEYS = {"source", "search", "embedding", "auth", "graph"}


@dataclass(frozen=True)
class DnaConfig:
    """Parsed + validated ``dna.config.yaml``.

    ``source`` is a scheme URL (``file://`` / ``sqlite://`` / ``postgresql://``).
    ``search`` / ``embedding`` are validated enum strings (see module docstring).
    ``auth`` is an **opaque passthrough** mapping (the ``auth:`` section) — the SDK
    only checks it is a mapping; its detailed schema (``providers[]`` — the
    pluggable N-provider IdP layer of the MCP runtime face) is owned and validated
    by the consumer (``dna_cli._mcp_auth.parse_auth_providers``). ``None`` when the
    file has no ``auth:`` section.
    ``graph`` is the SIBLING opaque passthrough for the MCP server's Microsoft
    On-Behalf-Of (OBO) enablement (the ``graph:`` section) — its schema
    (``enabled`` / ``client_id_env`` / ``credential_env`` / ``groups[]``) is owned
    and validated by ``dna_cli.graph._config.parse_graph_config``. ``None`` when the
    file has no ``graph:`` section (OBO off — the default).
    ``path`` is where it was loaded from (``None`` for a synthesized default).
    """

    source: str
    search: str = "off"
    embedding: str = "off"
    auth: dict[str, Any] | None = None
    graph: dict[str, Any] | None = None
    path: Path | None = None


def find_config(start: str | Path | None = None) -> Path | None:
    """Return the path to ``dna.config.yaml`` in ``start`` (default: cwd), or
    ``None`` if absent. Deliberately NOT a walk-up: a config's meaning is tied
    to the directory a host boots from — an accidental parent-dir hit would be
    surprising."""
    base = Path(start) if start is not None else Path.cwd()
    candidate = base / CONFIG_FILENAME
    return candidate if candidate.is_file() else None


def load_config(path: str | Path | None = None) -> DnaConfig | None:
    """Load + validate ``dna.config.yaml``.

    - ``path`` given → it MUST exist (a typo'd ``--config`` is an error, not a
      silent fallback); parsed and validated.
    - ``path`` omitted → look for ``dna.config.yaml`` in the cwd. Found →
      parsed. Absent → ``None`` (the caller keeps its default behavior — a
      filesystem ``.dna`` source, unchanged).

    Fails loud (``ValueError``) on: not-a-mapping, missing ``source``, unknown
    keys, or an out-of-enum ``search`` / ``embedding`` value.
    """
    if path is not None:
        resolved = Path(path)
        if not resolved.is_file():
            raise ValueError(
                f"dna config not found at {resolved} — pass a path to an "
                f"existing {CONFIG_FILENAME}, or omit --config to auto-discover "
                f"one in the current directory."
            )
    else:
        resolved = find_config()
        if resolved is None:
            return None

    import yaml  # PyYAML ships with the SDK

    raw: Any = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    return _parse(raw, resolved)


def _parse(raw: Any, path: Path) -> DnaConfig:
    if raw is None:
        raise ValueError(
            f"{path} is empty — it must at least declare a `source:` URL "
            f"(e.g. `source: file://.dna`)."
        )
    if not isinstance(raw, dict):
        raise ValueError(
            f"{path} must be a YAML mapping (key: value), got {type(raw).__name__}."
        )

    unknown = sorted(set(raw) - _KNOWN_KEYS)
    if unknown:
        raise ValueError(
            f"{path}: unknown key(s) {unknown} — supported keys are "
            f"{sorted(_KNOWN_KEYS)}."
        )

    source = raw.get("source")
    if not source or not isinstance(source, str):
        raise ValueError(
            f"{path}: `source:` is required and must be a URL string "
            f"(file:// | sqlite:// | postgresql://)."
        )

    search = str(raw.get("search", "off")).strip() or "off"
    if search not in _VALID_SEARCH:
        raise ValueError(
            f"{path}: `search: {search}` is not valid — choose one of "
            f"{list(_VALID_SEARCH)}."
        )

    embedding = str(raw.get("embedding", "off")).strip() or "off"
    if embedding not in _VALID_EMBEDDING:
        raise ValueError(
            f"{path}: `embedding: {embedding}` is not valid — choose one of "
            f"{list(_VALID_EMBEDDING)}."
        )

    auth = raw.get("auth")
    if auth is not None and not isinstance(auth, dict):
        raise ValueError(
            f"{path}: `auth:` must be a mapping (its `providers:` list configures "
            f"the MCP IdP layer), got {type(auth).__name__}."
        )

    graph = raw.get("graph")
    if graph is not None and not isinstance(graph, dict):
        raise ValueError(
            f"{path}: `graph:` must be a mapping (it configures the MCP server's "
            f"Microsoft On-Behalf-Of tool-groups), got {type(graph).__name__}."
        )

    return DnaConfig(
        source=source, search=search, embedding=embedding, auth=auth, graph=graph,
        path=path,
    )
