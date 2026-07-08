"""Shared CLI context — kernel session + output formatting (kernel-local).

The ``dna`` CLI is a thin wrapper over the DNA kernel: every command
boots a local Kernel against ``DNA_SOURCE_URL`` / ``DNA_BASE_DIR``
(filesystem source), runs one command, exits. No service, no HTTP —
the kernel IS the backend.

Two session patterns:

  - ``dna_session(scope)`` — context manager that owns ONE event loop
    for the entire command. Use for any command that does writes /
    deletes / async ops.

        with dna_session(scope) as s:
            s.run(s.kernel.write_document(...))

  - ``get_holder(scope)`` — sync helper for read-only commands that
    only touch ``query_list`` / ``get_doc`` (no async afterwards).

Plus ``dna_client()`` — a LOCAL facade with the resource shape some
commands consume (``client.docs(scope).get/put/delete/list`` and
``client.scopes.list/tree/kinds/kind_schema``), backed by the same
local kernel. In the upstream platform this surface is an HTTP API
client; here it resolves in-process.

Output helpers: ``print_json``, ``print_table``, ``fail``.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

import click


# ─── source resolution ────────────────────────────────────────────────
#
# Priority: DNA_SOURCE_URL > DNA_BASE_DIR (rewritten to file://<dir>) >
# ./.dna. This distribution ships the filesystem adapter on the boot
# path; the sqlite/postgres adapters are importable from dna.adapters
# and can be wired programmatically (kernel.source(...)) by host code.


def _resolve_source_url(base_dir_override: str | None = None) -> str:
    url = os.getenv("DNA_SOURCE_URL")
    if url:
        return url
    base = base_dir_override or os.getenv("DNA_BASE_DIR")
    if base:
        p = Path(base).resolve()
        # mirror the classic convention: a project dir with a .dna/ child
        if (p / ".dna").is_dir():
            p = p / ".dna"
        return f"file://{p}"
    return f"file://{Path('.dna').resolve()}"


async def build_source_from_env(kernel: Any, *, _source_url: str | None = None) -> Any:
    """Build a writable source from the environment (filesystem-only boot
    path — see module docstring). Async for signature uniformity with the
    upstream factory this replaces."""
    url = _source_url or _resolve_source_url()
    parsed = urlparse(url)
    scheme = parsed.scheme or "file"
    if scheme in ("file", "fs", ""):
        from dna.adapters.filesystem.writable import FilesystemWritableSource

        path = parsed.path if parsed.scheme else url
        if parsed.netloc and not parsed.path:
            path = parsed.netloc
        return FilesystemWritableSource(
            path,
            writers=list(getattr(kernel, "active_writers", []) or []),
            kernel=kernel,
        )
    raise click.ClickException(
        f"unsupported DNA_SOURCE_URL scheme '{scheme}://' — the dna CLI "
        f"boots filesystem sources (file:// or a plain path). The sqlite/"
        f"postgres adapters ship in dna.adapters and can be wired "
        f"programmatically via kernel.source(...)."
    )


async def _build_holder_async(scope: str | None = None):
    """Boot a full kernel (every installed extension via entry-points) on
    the caller's event loop and return a holder for ``scope``."""
    from dna.kernel import Kernel
    from dna.adapters.filesystem import FilesystemCache

    kernel = Kernel.auto()
    url = _resolve_source_url()
    source = await build_source_from_env(kernel, _source_url=url)
    kernel.source(source)
    try:
        kernel.cache(FilesystemCache(str(getattr(source, "base_dir", ".dna"))))
    except Exception:  # noqa: BLE001 — cache is optional for CLI reads
        pass

    resolved = scope or os.getenv("DNA_SCOPE_DEFAULT")
    if resolved is None:
        scopes = await source.list_scopes()
        if not scopes:
            raise click.ClickException(
                f"No scopes found in source ({url}). Create one with a "
                f"manifest.yaml under <base>/<scope>/ first."
            )
        resolved = scopes[0]

    mi = await kernel.instance_async(resolved, lazy=True)
    return _Holder(kernel, resolved, mi)


class _Holder:
    """Kernel-local stand-in for the upstream MIHolder: the surface the
    CLI commands actually use (.mi / .kernel / .scope / .query_list /
    .get_doc / .reload)."""

    def __init__(self, kernel: Any, scope: str, mi: Any = None):
        self._kernel = kernel
        self._scope = scope
        self._mi = mi

    @property
    def kernel(self) -> Any:
        return self._kernel

    @property
    def scope(self) -> str:
        return self._scope

    @property
    def mi(self) -> Any:
        if self._mi is None:
            self._mi = self._kernel.instance(self._scope)
        return self._mi

    def query_list(
        self, kind: str, *, filter: dict | None = None,
        tenant: str | None = None,
    ) -> list:
        effective = tenant if tenant is not None else (os.getenv("DNA_TENANT") or None)
        return self._kernel.query_list_sync(
            self._scope, kind, filter=filter, tenant=effective,
        )

    def get_doc(self, kind: str, name: str, *, tenant: str | None = None):
        effective = tenant if tenant is not None else (os.getenv("DNA_TENANT") or None)
        return self._kernel.get_document_sync(
            self._scope, kind, name, tenant=effective,
        )

    def reload(self) -> None:
        self._mi = None


@dataclass
class Session:
    """Owns the holder + event loop for one CLI command.

    Use ``s.run(coro)`` to execute async ops on the same loop the
    kernel was built in. Sync helpers (``s.mi``, ``s.kernel``,
    ``s.holder``, ``s.scope``) are passthroughs.
    """
    holder: Any
    _loop: asyncio.AbstractEventLoop

    @property
    def mi(self):
        return self.holder.mi

    @property
    def kernel(self):
        return self.holder.kernel

    @property
    def scope(self) -> str:
        return self.holder.scope

    def query_list(
        self, kind: str, *, filter: dict | None = None,
        tenant: str | None = None,
    ) -> list:
        return self.holder.query_list(kind, filter=filter, tenant=tenant)

    def get_doc(self, kind: str, name: str, *, tenant: str | None = None):
        return self.holder.get_doc(kind, name, tenant=tenant)

    def run(self, coro):
        """Run an async coroutine on the session's event loop."""
        return self._loop.run_until_complete(coro)


@contextmanager
def dna_session(scope: str | None = None) -> Iterator[Session]:
    """Open a CLI-scoped kernel session (one loop for the whole block)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    holder = None
    try:
        holder = loop.run_until_complete(_build_holder_async(scope))
        # Register the session's loop as the kernel's main loop so sync
        # helpers (query_list_sync / get_document_sync) dispatch onto it
        # instead of spawning fresh loops.
        kernel = getattr(holder, "kernel", None)
        if kernel is not None and hasattr(kernel, "register_main_loop"):
            try:
                kernel.register_main_loop(loop)
            except Exception:  # noqa: BLE001 — never block session boot
                pass
        yield Session(holder=holder, _loop=loop)
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            for t in pending:
                t.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        finally:
            loop.close()


def get_holder(scope: str | None = None):
    """Sync helper for read-only commands (loop closed on return)."""
    return asyncio.run(_build_holder_async(scope))


def run_async(coro):
    """Block until ``coro`` completes — sync wrapper around asyncio.

    Reuses the current thread's event loop when one is already set
    (typical flow: ``dna_client()`` installs a loop, then every
    ``run_async`` call within the with-block uses that same loop).
    Falls back to ``asyncio.run()`` when no loop is set.
    """
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        loop = None
    if loop is None or loop.is_closed():
        return asyncio.run(coro)
    if loop.is_running():
        return asyncio.run(coro)
    return loop.run_until_complete(coro)


# ─── dna_client — LOCAL facade with the resource-client shape ─────────


class _LocalDocs:
    """``client.docs(scope)`` — document CRUD against the local kernel.

    Methods are async and run INSIDE the client's event loop, so they use
    the kernel's async surface (``query`` / ``get_document``) — the sync
    wrappers would trip ``_run_sync_helper`` from a running loop."""

    def __init__(self, client: "_LocalClient", scope: str):
        self._c = client
        self._scope = scope

    async def list(self, kind: str | None = None) -> dict:
        if not kind:
            return {"items": []}
        kernel = self._c._holder.kernel
        items: list[dict] = []
        async for row in kernel.query(self._scope, kind, tenant=self._c._tenant):
            meta = row.get("metadata") if isinstance(row, dict) else None
            name = (meta or {}).get("name") if isinstance(meta, dict) else None
            name = name or (row.get("name") if isinstance(row, dict) else None)
            items.append({"kind": kind, "metadata": {"name": name}})
        return {"items": items}

    async def get(self, kind: str, name: str) -> dict:
        raw = await self._c._holder.kernel.get_document(
            self._scope, kind, name, tenant=self._c._tenant,
        )
        if raw is None:
            raise KeyError(f"404 not found: {kind}/{name}")
        return {"raw": raw}

    async def put(self, kind: str, name: str, raw: dict) -> Any:
        kernel = self._c._holder.kernel
        if self._c._tenant:
            kernel = kernel.with_tenant(self._c._tenant)
        return await kernel.write_document(self._scope, kind, name, raw)

    async def delete(self, kind: str, name: str) -> Any:
        kernel = self._c._holder.kernel
        if self._c._tenant:
            kernel = kernel.with_tenant(self._c._tenant)
        return await kernel.delete_document(self._scope, kind, name)


class _LocalScopes:
    """``client.scopes`` — scope/kind introspection against the kernel."""

    def __init__(self, client: "_LocalClient"):
        self._c = client

    async def list(self) -> list[str]:
        source = getattr(self._c._holder.kernel, "_source", None)
        if source is None:
            return []
        return list(await source.list_scopes())

    async def tree(self, scope: str) -> dict[str, list[str]]:
        mi = await self._c._holder.kernel.instance_async(scope)
        by_kind: dict[str, list[str]] = {}
        for d in mi.documents:
            by_kind.setdefault(d.kind, []).append(d.name)
        return {k: sorted(v) for k, v in by_kind.items()}

    async def kinds(self, scope: str) -> dict[str, list]:
        del scope  # kinds are kernel-global in the local facade
        kernel = self._c._holder.kernel
        return {kp.kind: [] for kp in kernel._kinds.values() if getattr(kp, "kind", None)}

    async def kind_schema(self, scope: str, kind: str) -> dict:
        del scope
        kernel = self._c._holder.kernel
        kp = next(
            (k for k in kernel._kinds.values() if getattr(k, "kind", None) == kind),
            None,
        )
        if kp is None:
            raise KeyError(f"404 not found: kind {kind!r}")
        try:
            schema = kp.schema() or {}
        except Exception:  # noqa: BLE001
            schema = {}
        sd = getattr(kp, "storage", None)
        return {
            "kind": kp.kind,
            "alias": getattr(kp, "alias", None),
            "api_version": getattr(kp, "api_version", None),
            "display_label": getattr(kp, "display_label", None),
            "schema": schema,
            "is_root": bool(getattr(kp, "is_root", False)),
            "is_runtime_artifact": bool(getattr(kp, "is_runtime_artifact", False)),
            "storage": {
                "marker": getattr(sd, "marker", None),
                "directory": getattr(sd, "directory", None),
            } if sd is not None else None,
        }


class _LocalClient:
    """Local (in-process) twin of the upstream API client surface."""

    def __init__(self, holder: Any, tenant: str | None):
        self._holder = holder
        self._tenant = tenant
        self.scopes = _LocalScopes(self)

    def docs(self, scope: str) -> _LocalDocs:
        return _LocalDocs(self, scope)


@contextmanager
def dna_client(timeout: float = 30.0, tenant: str | None = None):
    """Yield a local-kernel client facade (see class docstrings).

    ``timeout`` is accepted for signature compatibility and ignored —
    there is no network here. Installs a dedicated event loop for the
    with-block so every ``run_async`` call reuses the SAME loop.
    """
    del timeout
    effective_tenant = tenant if tenant is not None else os.getenv("DNA_TENANT")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        holder = loop.run_until_complete(_build_holder_async(None))
        kernel = getattr(holder, "kernel", None)
        if kernel is not None and hasattr(kernel, "register_main_loop"):
            try:
                kernel.register_main_loop(loop)
            except Exception:  # noqa: BLE001
                pass
        yield _LocalClient(holder, effective_tenant)
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            for t in pending:
                t.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        finally:
            loop.close()
            asyncio.set_event_loop(None)


# ─── output helpers ───────────────────────────────────────────────────


def print_json(value: Any) -> None:
    """Serialize to stdout. Used as default for machine-readable output."""
    click.echo(json.dumps(value, default=str, indent=2, ensure_ascii=False))


def print_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
    """Render rows as a borderless aligned table (no rich dependency)."""
    if not rows:
        click.echo("(no rows)", err=True)
        return
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows)) for c in columns}
    header = "  ".join(c.ljust(widths[c]) for c in columns)
    click.echo(header)
    click.echo("  ".join("-" * widths[c] for c in columns))
    for r in rows:
        click.echo("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in columns))


def fail(message: str, code: int = 1) -> "click.exceptions.Exit":
    """Print an error to stderr and exit. Returns an exception instance
    so callers can `raise fail("...")` for static analyzers."""
    click.secho(message, fg="red", err=True)
    sys.exit(code)
