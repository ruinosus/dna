"""Public async facade for consuming DNA definitions from any runtime."""
from __future__ import annotations

import asyncio
import inspect
import os
from types import TracebackType
from typing import Any, Self

from dna.application import (
    LiveDna,
    get_instance_impl,
    list_instances_impl,
    list_kinds_impl,
    read_registered_kind_impl,
)
from dna.definitions import (
    KindDescriptor,
    ResolvedAgent,
    ResolvedGenUIBinding,
    ResolvedGenUIComponent,
    ResolvedRuntimeBinding,
    ResolvedTool,
    resolve_agent,
    resolve_copilot,
)


class KindCatalog:
    """Scope-aware discovery of registered, effective Kinds."""

    def __init__(self, client: DnaClient) -> None:
        self._client = client

    async def list(self) -> tuple[KindDescriptor, ...]:
        result = await list_kinds_impl(
            self._client.live,
            scope=self._client.scope,
            tenant=self._client.tenant,
        )
        return tuple(self._descriptor(row) for row in result["kinds"])

    async def describe(
        self, kind: str, *, api_version: str | None = None,
    ) -> KindDescriptor:
        catalog = await list_kinds_impl(
            self._client.live,
            scope=self._client.scope,
            tenant=self._client.tenant,
        )
        matches = [
            row for row in catalog["kinds"]
            if row["kind"] == kind
            and (api_version is None or row["api_version"] == api_version)
        ]
        if not matches:
            raise LookupError(f"no registered Kind named {kind!r}")
        if len(matches) > 1:
            versions = sorted(row["api_version"] for row in matches)
            raise ValueError(
                f"Kind {kind!r} is ambiguous; pass api_version from {versions}"
            )
        details = await read_registered_kind_impl(
            self._client.live,
            kind=kind,
            api_version=matches[0]["api_version"],
            scope=self._client.scope,
        )
        return self._descriptor(matches[0], details)

    @staticmethod
    def _descriptor(
        row: dict[str, Any], details: dict[str, Any] | None = None,
    ) -> KindDescriptor:
        details = details or {}
        return KindDescriptor(
            kind=row["kind"],
            api_version=row["api_version"],
            alias=row.get("alias"),
            origin=row.get("origin"),
            registration_status=row.get("registration_status", "builtin"),
            family=row.get("family"),
            plane=row.get("plane", details.get("plane", "composition")),
            display_label=row.get("display_label"),
            tenant_scope=row.get("tenant_scope"),
            storage_pattern=row.get("storage_pattern"),
            traits=tuple(row.get("traits") or ()),
            schema=dict(details.get("schema") or {}),
            ui_schema=dict(details.get("ui_schema") or {}),
            docs=details.get("docs"),
            writable=bool(row.get("writable")),
            write_refusal=row.get("write_refusal"),
            deletable=bool(row.get("deletable")),
            delete_refusal=row.get("delete_refusal"),
        )


class InstanceCatalog:
    """Generic reads over instances of built-in or custom Kinds."""

    def __init__(self, client: DnaClient) -> None:
        self._client = client

    async def list(
        self,
        kind: str,
        *,
        api_version: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        fields: tuple[str, ...] | None = None,
        filter: dict[str, Any] | None = None,
        order_by: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        return await list_instances_impl(
            self._client.live,
            kind=kind,
            scope=self._client.scope,
            tenant=self._client.tenant,
            api_version=api_version,
            limit=limit,
            offset=offset,
            fields=fields,
            filter=filter,
            order_by=order_by,
        )

    async def get(
        self, kind: str, name: str, *, api_version: str | None = None,
    ) -> dict[str, Any]:
        return await get_instance_impl(
            self._client.live,
            kind=kind,
            name=name,
            scope=self._client.scope,
            tenant=self._client.tenant,
            api_version=api_version,
        )


class DnaClient:
    """A live, source-aware entry point to DNA's declarative mechanism."""

    def __init__(
        self,
        live: LiveDna,
        *,
        scope: str | None = None,
        tenant: str | None = None,
        source: Any | None = None,
    ) -> None:
        self.live = live
        self.scope = scope or live.base_scope
        self.tenant = tenant
        self._source = source
        self.kinds = KindCatalog(self)
        self.instances = InstanceCatalog(self)

    @classmethod
    async def from_env(
        cls,
        *,
        scope: str | None = None,
        tenant: str | None = None,
        base_dir: str | None = None,
    ) -> DnaClient:
        """Boot from ``DNA_SOURCE_URL`` or the filesystem fallback."""
        from dna.adapters.source_url import source_from_url
        from dna.kernel import Kernel
        from dna.runtime.config import resolve_source_url

        kernel = Kernel.auto()
        source = await source_from_url(resolve_source_url(base_dir), kernel=kernel)
        resolved_scope = scope or os.getenv("DNA_SCOPE_DEFAULT")
        if resolved_scope is None:
            scopes = await source.list_scopes()
            if not scopes:
                raise ValueError("No DNA scopes found in the configured source")
            resolved_scope = scopes[0]
        kernel.source(source)
        if getattr(source, "supports_readers", False):
            from dna.adapters.filesystem import FilesystemCache
            from dna.kernel.boot.bootstrap import wire_filesystem_resolvers

            source_base = str(getattr(source, "base_dir", ".dna"))
            kernel.cache(FilesystemCache(source_base))
            wire_filesystem_resolvers(kernel, source_base)
        else:
            from dna.kernel.boot.bootstrap import _NoopCache

            kernel.cache(_NoopCache())
        kernel._main_loop = asyncio.get_running_loop()
        live = LiveDna(base_scope=resolved_scope, kernel=kernel, provider=None)
        return cls(live, scope=resolved_scope, tenant=tenant, source=source)

    async def resolve_agent(
        self,
        name: str | None = None,
        *,
        model: str | None = None,
        provider: str | None = None,
    ) -> ResolvedAgent:
        manifest = await self.live.mi(self.scope, self.tenant)
        definition = await asyncio.to_thread(
            resolve_agent, manifest, name, model=model, provider=provider,
        )
        return await self._enrich_tools(definition)

    async def resolve_copilot(
        self, name: str, *, model: str | None = None, provider: str | None = None,
    ) -> ResolvedAgent:
        manifest = await self.live.mi(self.scope, self.tenant)
        definition = await asyncio.to_thread(
            resolve_copilot, manifest, name, model=model, provider=provider,
        )
        return await self._enrich_tools(definition)

    async def resolve_runtime_binding(self, name: str) -> ResolvedRuntimeBinding:
        """Resolve a binding while leaving host lookup to the deployment."""
        from dna.kernel.errors import RuntimeBindingNotFound

        try:
            result = await self.instances.get("RuntimeBinding", name)
        except LookupError as error:
            raise RuntimeBindingNotFound(name) from error
        return ResolvedRuntimeBinding.from_instance(
            result["instance"], scope=result["scope"],
        )

    async def list_gen_ui_bindings(
        self, *, agent: str | None = None,
    ) -> tuple[ResolvedGenUIBinding, ...]:
        """Resolve GenUI assignments, optionally restricted to one DNA Agent."""
        result = await self.instances.list(
            "GenUIBinding",
            fields=("agent", "components"),
            filter={"agent": agent} if agent else None,
            order_by=("name",),
        )
        return tuple(
            ResolvedGenUIBinding.from_instance(row, scope=result["scope"])
            for row in result["instances"]
        )

    async def list_gen_ui_components(
        self, *, agent: str | None = None,
    ) -> tuple[ResolvedGenUIComponent, ...]:
        """Resolve portable GenUI contracts, optionally assigned to an Agent."""
        fields = (
            "tool_name",
            "description",
            "input_schema",
            "renderer_ref",
            "protocols",
            "required_capabilities",
            "fallback",
            "contract_version",
        )
        result = await self.instances.list("GenUIComponent", fields=fields)
        components = tuple(
            ResolvedGenUIComponent.from_instance(row, scope=result["scope"])
            for row in result["instances"]
        )
        if agent is None:
            return components

        bindings = await self.list_gen_ui_bindings(agent=agent)
        assigned = {
            component_name
            for binding in bindings
            for component_name in binding.components
        }
        by_name = {component.name: component for component in components}
        missing = sorted(assigned - by_name.keys())
        if missing:
            raise ValueError(
                f"GenUIBinding for Agent {agent!r} references unknown "
                f"GenUIComponent instance(s): {', '.join(missing)}"
            )
        return tuple(by_name[name] for name in sorted(assigned))

    async def _enrich_tools(self, definition: ResolvedAgent) -> ResolvedAgent:
        tools: list[ResolvedTool] = []
        for surface in definition.tools:
            result = await get_instance_impl(
                self.live,
                kind="Tool",
                name=surface.name,
                scope=self.scope,
                tenant=self.tenant,
            )
            raw = result.get("instance") or {}
            tools.append(ResolvedTool.from_instance(raw))
        return definition.with_tools(tuple(tools))

    async def close(self) -> None:
        """Release a source connection owned by this client."""
        close = getattr(self._source, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()


__all__ = ["DnaClient", "InstanceCatalog", "KindCatalog"]
