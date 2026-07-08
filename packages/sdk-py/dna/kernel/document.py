"""Document — unified wrapper for all manifest documents."""
from __future__ import annotations

import dataclasses
from functools import cached_property
from typing import Any, Generic, TypeVar, cast


class SpecDict(dict):
    """Dict with attribute access. Unifies spec/metadata access patterns.

    Supports all access styles:
        spec.soul           — attribute (raises AttributeError if missing)
        spec.get("soul")    — safe access (returns None if missing)
        getattr(spec, "soul", None)  — safe access (respects default)
        spec["soul"]        — dict (raises KeyError if missing)
        isinstance(spec, dict)  — True
    """

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def _to_spec_dict(obj: Any, fallback: dict[str, Any]) -> SpecDict:
    """Convert a typed dataclass or raw dict to SpecDict."""
    if obj is not None and dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return SpecDict(dataclasses.asdict(obj))
    if isinstance(obj, dict):
        return SpecDict(obj)
    return SpecDict(fallback)


# v1.0 — Document[SpecT] generic typing.
#
# `Document` becomes `Generic[SpecT]` so consumers can type spec
# access at the call site without a runtime cost:
#
#     spec: PageIndexSpec = doc.spec  # type-checker validated when
#                                     # `doc: Document[PageIndexSpec]`
#
# Bare `Document` continues working — Python typing defaults the
# unbound type variable to `Any`, matching pre-generic behavior. This
# is purely additive: existing code that uses `Document` without
# brackets sees no signature change.
SpecT = TypeVar("SpecT", default=SpecDict)
"""Spec type for `Document[SpecT]`. Default = `SpecDict` so bare
`Document` keeps the existing dict-with-attribute-access shape."""


class Document(Generic[SpecT]):
    """Universal wrapper. Works for parsed BaseKind AND raw dict.

    `doc.spec` and `doc.metadata` always return `SpecDict` at runtime
    — a dict subclass with attribute access. When typed via
    `Document[MySpec]`, the type checker treats `doc.spec` as `MySpec`,
    enabling autocomplete + typo detection at edit time without a
    runtime cast.

    The typed model is still available via `doc.typed`.
    """

    __slots__ = (
        "api_version", "kind", "name", "_metadata_raw", "_spec_raw",
        "raw", "typed", "origin", "__dict__",
    )

    def __init__(
        self,
        api_version: str,
        kind: str,
        name: str,
        metadata: dict[str, Any] | None = None,
        spec: dict[str, Any] | None = None,
        raw: dict[str, Any] | None = None,
        typed: Any | None = None,
        origin: str = "local",
    ) -> None:
        self.api_version = api_version
        self.kind = kind
        self.name = name
        self._metadata_raw = metadata or {}
        self._spec_raw = spec or {}
        self.origin = origin
        self.raw = raw or {}
        self.typed = typed

    @cached_property
    def metadata(self) -> SpecDict:
        """Always returns SpecDict — typed metadata when available, raw dict otherwise."""
        if (
            self.typed is not None
            and not isinstance(self.typed, dict)
            and hasattr(self.typed, "metadata")
        ):
            return _to_spec_dict(self.typed.metadata, self._metadata_raw)
        return SpecDict(self._metadata_raw)

    @cached_property
    def spec(self) -> SpecDict:
        """Always returns SpecDict — typed spec when available, raw dict otherwise."""
        if (
            self.typed is not None
            and not isinstance(self.typed, dict)
            and hasattr(self.typed, "spec")
        ):
            return _to_spec_dict(self.typed.spec, self._spec_raw)
        return SpecDict(self._spec_raw)

    @classmethod
    def from_raw(cls, raw: dict[str, Any], typed: Any | None = None) -> Document[Any]:
        """Create a Document from a raw dict.

        Returns `Document[Any]` because the spec type is determined at
        the call site by the consumer's annotation; the factory itself
        cannot infer it. Consumers using typed access:
            doc: Document[PageIndexSpec] = Document.from_raw(raw)
        get the right type via the annotation.
        """
        metadata = raw.get("metadata", {}) or {}
        return cast(
            "Document[Any]",
            cls(
                api_version=raw.get("apiVersion", ""),
                kind=raw.get("kind", ""),
                name=metadata.get("name", ""),
                metadata=metadata,
                spec=raw.get("spec", {}) or {},
                raw=raw,
                typed=typed,
            ),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Document):
            return NotImplemented
        return (self.api_version, self.kind, self.name) == (
            other.api_version, other.kind, other.name
        )

    def __hash__(self) -> int:
        return hash((self.api_version, self.kind, self.name))

    def __repr__(self) -> str:
        return f"Document({self.api_version}/{self.kind}: {self.name})"
