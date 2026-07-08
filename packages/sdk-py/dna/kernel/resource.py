"""
Resource -- a concrete instance of a Kind.

Replaces Document with added self-awareness: a Resource knows its own
dependencies via kind_ref.

1:1 parity with TypeScript kernel/resource.ts.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Any, Protocol, runtime_checkable

from .document import SpecDict, _to_spec_dict


@runtime_checkable
class KindLike(Protocol):
    """Minimal Kind interface needed by Resource.deps()."""

    def dep_filters(self) -> dict[str, str] | None: ...


@dataclass
class ResourceDep:
    """One resolved dependency edge."""

    field: str
    target_alias: str
    names: list[str]


class Resource:
    """Self-aware document wrapper that knows its own dependencies."""

    __slots__ = (
        "api_version",
        "kind",
        "name",
        "_metadata_raw",
        "_spec_raw",
        "raw",
        "typed",
        "origin",
        "kind_ref",
        "__dict__",
    )

    def __init__(
        self,
        api_version: str,
        kind: str,
        name: str,
        metadata: dict[str, Any] | None = None,
        spec: dict[str, Any] | None = None,
        raw: dict[str, Any] | None = None,
        typed: Any = None,
        origin: str = "local",
        kind_ref: KindLike | None = None,
    ) -> None:
        self.api_version = api_version
        self.kind = kind
        self.name = name
        self._metadata_raw = metadata or {}
        self._spec_raw = spec or {}
        self.raw = raw or {}
        self.typed = typed
        self.origin = origin
        self.kind_ref = kind_ref

    @cached_property
    def metadata(self) -> SpecDict:
        """Always returns SpecDict -- typed metadata when available, raw dict otherwise."""
        if (
            self.typed is not None
            and not isinstance(self.typed, dict)
            and hasattr(self.typed, "metadata")
        ):
            return _to_spec_dict(self.typed.metadata, self._metadata_raw)
        return SpecDict(self._metadata_raw)

    @cached_property
    def spec(self) -> SpecDict:
        """Always returns SpecDict -- typed spec when available, raw dict otherwise."""
        if (
            self.typed is not None
            and not isinstance(self.typed, dict)
            and hasattr(self.typed, "spec")
        ):
            return _to_spec_dict(self.typed.spec, self._spec_raw)
        return SpecDict(self._spec_raw)

    def deps(self) -> list[ResourceDep]:
        """Resolve this resource's outgoing dependency edges using kind_ref.dep_filters().

        Returns one entry per dep_filter field that has a non-empty value in spec.
        Scalar spec values (e.g. ``soul: "brad"``) become single-element name lists.
        Returns empty list when kind_ref is None or dep_filters() returns None.
        """
        if self.kind_ref is None:
            return []
        # Try dependencies() first (new API), fall back to dep_filters()
        filters = None
        if hasattr(self.kind_ref, "dependencies") and callable(
            self.kind_ref.dependencies
        ):
            filters = self.kind_ref.dependencies()
        if filters is None:
            filters = self.kind_ref.dep_filters()
        if not filters:
            return []

        spec = self.spec
        result: list[ResourceDep] = []
        for fld, target_alias in filters.items():
            value = spec.get(fld)
            names: list[str] = []
            if isinstance(value, list):
                names = [v for v in value if isinstance(v, str)]
            elif isinstance(value, str) and value:
                names = [value]
            if not names:
                continue
            result.append(
                ResourceDep(field=fld, target_alias=target_alias, names=names)
            )
        return result

    @classmethod
    def from_raw(
        cls,
        raw: dict[str, Any],
        typed: Any = None,
        origin: str = "local",
        kind_ref: KindLike | None = None,
    ) -> Resource:
        """Create a Resource from a raw dict."""
        metadata = raw.get("metadata") or {}
        return cls(
            api_version=raw.get("apiVersion", ""),
            kind=raw.get("kind", ""),
            name=metadata.get("name", ""),
            metadata=metadata,
            spec=raw.get("spec") or {},
            raw=raw,
            typed=typed,
            origin=origin,
            kind_ref=kind_ref,
        )

    def __repr__(self) -> str:
        return f"Resource({self.api_version}/{self.kind}: {self.name})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Resource):
            return NotImplemented
        return (
            self.api_version == other.api_version
            and self.kind == other.kind
            and self.name == other.name
        )

    def __hash__(self) -> int:
        return hash((self.api_version, self.kind, self.name))
