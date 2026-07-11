"""``source_from_url`` — the URL → SourcePort factory, as a PUBLIC SDK surface.

This logic used to live PRIVATELY inside the ``dna`` CLI (``dna_cli._ctx.
build_source_from_env``) and only understood ``file://``. Promoting it here
(``s-dx-kernel-from-config``):

  - makes ``Kernel.from_config`` and the CLI share ONE factory (no duplication);
  - actually SUPPORTS ``sqlite://`` and ``postgresql://`` by delegating to the
    :class:`~dna.adapters.sqlalchemy_.SqlAlchemySource` that already ships in
    ``dna.adapters`` — previously reachable only by hand-wiring.

Scheme map:

  ==================  ======================================================
  config URL          adapter
  ==================  ======================================================
  ``file://<path>``   :class:`FilesystemWritableSource` (read+write on disk)
  ``fs://<path>``     alias of ``file://``
  ``<plain path>``    treated as ``file://<path>``
  ``sqlite://<path>`` :class:`SqlAlchemySource` (``sqlite+aiosqlite``)
  ``postgresql://…``  :class:`SqlAlchemySource` (``postgresql+asyncpg``)
  ``postgres://…``    alias of ``postgresql://``
  ==================  ======================================================

An unknown scheme fails loud with the supported set. A URL that already carries
a SQLAlchemy driver (``sqlite+aiosqlite://``, ``postgresql+asyncpg://``) is
passed through untouched.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

__all__ = ["source_from_url", "UnsupportedSourceScheme"]


class UnsupportedSourceScheme(ValueError):
    """Raised when a source URL uses a scheme the SDK has no adapter for."""


def _url_to_fs_path(url: str) -> str:
    """Resolve a ``file://`` / ``fs://`` / plain-path URL to a filesystem path.

    Mirrors the CLI's original rule (join ``netloc`` + ``path`` so ``fs://./x``
    resolves to the RELATIVE ``./x``, not the absolute ``/x`` — the i-006 fix).
    """
    parsed = urlparse(url)
    if parsed.scheme:
        return (parsed.netloc + parsed.path) if parsed.netloc else parsed.path
    return url


def _normalize_sql_url(url: str, scheme: str) -> str:
    """Map a bare ``sqlite://`` / ``postgresql://`` URL to the driver-qualified
    form SQLAlchemy needs. A URL that already names a driver (``+aiosqlite`` /
    ``+asyncpg``) is returned unchanged."""
    if "+" in scheme:
        return url  # already driver-qualified — trust the caller
    if scheme == "sqlite":
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    # postgres / postgresql → asyncpg
    return url.replace(f"{scheme}://", "postgresql+asyncpg://", 1)


async def source_from_url(
    url: str,
    *,
    kernel: Any | None = None,
    connect: bool = True,
    schema: str | None = None,
) -> Any:
    """Build a writable source from a scheme URL (see module docstring).

    ``kernel`` — when given and the source is a filesystem source, its active
    writers are threaded in so bundle writes round-trip (the CLI's original
    behavior). SQL sources fill writers/readers via ``attach_kernel`` when the
    kernel wires them, so ``kernel`` is optional there.

    ``connect`` — SQL sources run their schema migrations on first use; when
    ``True`` (default) ``connect()`` is awaited here so the returned source is
    ready. Pass ``False`` to defer (e.g. to connect on your own loop).

    ``schema`` — Postgres schema namespace (SQL sources only).
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "file").lower()

    if scheme in ("file", "fs", ""):
        from dna.adapters.filesystem.writable import FilesystemWritableSource

        writers = list(getattr(kernel, "active_writers", []) or []) if kernel else []
        return FilesystemWritableSource(
            _url_to_fs_path(url), writers=writers, kernel=kernel,
        )

    if scheme.split("+", 1)[0] in ("sqlite", "postgresql", "postgres"):
        from dna.adapters.sqlalchemy_ import SqlAlchemySource

        driver_url = _normalize_sql_url(url, scheme)
        src = SqlAlchemySource(driver_url, schema=schema)
        if connect:
            await src.connect()
        return src

    raise UnsupportedSourceScheme(
        f"unsupported source URL scheme '{scheme}://' — the SDK ships adapters "
        f"for file:// (filesystem), sqlite:// and postgresql:// (via "
        f"SqlAlchemySource). Got: {url!r}."
    )


def resolve_default_fs_url(base_dir_override: str | None = None) -> str:
    """The ``file://`` URL the SDK falls back to with no explicit config.

    Priority: explicit override > ``DNA_BASE_DIR`` env > ``./.dna``. A project
    dir that CONTAINS a ``.dna/`` child is rewritten to point at that child
    (the classic convention), so ``DNA_BASE_DIR=/my/project`` Just Works.
    """
    import os

    base = base_dir_override or os.getenv("DNA_BASE_DIR")
    if base:
        p = Path(base).resolve()
        if (p / ".dna").is_dir():
            p = p / ".dna"
        return f"file://{p}"
    return f"file://{Path('.dna').resolve()}"
