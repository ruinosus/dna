"""``KindDefinition`` — the reflexive rule (spec §6.1).

    *"A Kind is an instance of the Kind ``KindDefinition``. Writing one
    registers a type; there is no other way, and no out-of-band mechanism is
    permitted."*

This was clean-room gap **A11**, and the spec's own note on it is the one worth
keeping: *"The feature this specification argued hardest for — a Kind is itself
a written document — was the single feature it did not specify. It took an
implementer with no access to the reference to notice, because everyone who
could read the SDK already knew the answer and never saw the hole."*

Two rules are enforced here, both at write time, both before the store is
touched.

**1. ``metadata.name`` MUST equal ``spec.kind``.** *"One name, no mapping. A
second spelling of the same thing is a place for the two to drift, and every
reader would then have to know which one is authoritative."*

**2. ``spec.schema`` is BOUNDED.** Fifteen keywords, listed below, and nothing
else. *"A keyword the server stores, hands out through `kinds/describe`, and
does not enforce is a lie told to every client that reads the schema to
pre-validate."* The bound is checked **recursively** — a forbidden keyword
nested under ``properties`` or ``items`` is exactly as unenforced as one at the
top, and a check that only looked at the root would pass the schemas most
likely to carry one.

⚠️ **The open conflict, stated rather than resolved.** §6.1 says writing a
``KindDefinition`` registers a type and that *no out-of-band mechanism is
permitted*. The DNA SDK deliberately refuses a generic write of
``KindDefinition`` (``BootstrapKindWriteRefused``) and routes Kind authoring
through :mod:`dna.application.kind_authoring`, where what a tenant writes is
INERT until a human approves it in the portal. Those are two different answers
to *"who may create a type"*, and the second is a product decision, not an
oversight. This module therefore enforces the two rules the spec states — so a
malformed ``KindDefinition`` is refused for the right reason rather than
sailing through to a different refusal — and lets the SDK's own gate answer
whether the write proceeds. The conflict is reported, not decided here.
"""
from __future__ import annotations

from typing import Any

from dna.protocol.errors import VALIDATION_FAILED, DnapError

__all__ = ["BOUNDED_SCHEMA_KEYWORDS", "KIND_DEFINITION", "validate_kind_definition"]

KIND_DEFINITION = "KindDefinition"

#: §6.1, verbatim: *"A server MUST support exactly: …"* — fifteen keywords.
#: Anything else in a ``KindDefinition``'s ``spec.schema`` is rejected at write
#: with ``-32010`` on ``spec.schema``.
BOUNDED_SCHEMA_KEYWORDS: frozenset[str] = frozenset({
    "type", "enum", "const", "required", "properties", "additionalProperties",
    "items", "minItems", "maxItems", "uniqueItems", "minLength", "maxLength",
    "pattern", "minimum", "maximum",
})

#: Keywords whose VALUE is a schema (checked recursively) or a map of schemas.
_SCHEMA_VALUED = frozenset({"items", "additionalProperties"})
_SCHEMA_MAP_VALUED = frozenset({"properties"})


def validate_kind_definition(document: dict[str, Any]) -> None:
    """Enforce §6.1's two rules, or raise ``-32010``."""
    metadata = document.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    spec = document.get("spec")
    spec = spec if isinstance(spec, dict) else {}

    name, declared = metadata.get("name"), spec.get("kind")
    if name != declared:
        raise DnapError(
            VALIDATION_FAILED,
            f"a KindDefinition's metadata.name must equal spec.kind — got "
            f"{name!r} and {declared!r}. One name, no mapping: a second "
            f"spelling of the same thing is a place for the two to drift, and "
            f"every reader would then have to know which is authoritative.",
            path="metadata.name", rule="name-equals-spec-kind",
        )

    schema = spec.get("schema")
    if schema is None:
        return
    if not isinstance(schema, dict):
        raise DnapError(
            VALIDATION_FAILED,
            "spec.schema must be a JSON Schema object when present",
            path="spec.schema", rule="type",
        )
    _require_bounded(schema, "spec.schema")


def _require_bounded(schema: Any, path: str) -> None:
    """Recursive bound check. See the module docstring on why recursive."""
    if not isinstance(schema, dict):
        return
    for keyword, value in schema.items():
        here = f"{path}.{keyword}"
        if keyword not in BOUNDED_SCHEMA_KEYWORDS:
            raise DnapError(
                VALIDATION_FAILED,
                f"spec.schema carries the keyword {keyword!r} at {here}, which "
                f"this server does not enforce. DNAP §6.1 bounds a "
                f"KindDefinition's schema to exactly "
                f"{', '.join(sorted(BOUNDED_SCHEMA_KEYWORDS))} — a keyword a "
                f"server stores, hands out through `kinds/describe` and does "
                f"not enforce is a lie told to every client that reads the "
                f"schema to pre-validate.",
                path="spec.schema", rule="bounded-keywords",
                keyword=keyword, at=here,
            )
        if keyword in _SCHEMA_VALUED:
            _require_bounded(value, here)
        elif keyword in _SCHEMA_MAP_VALUED and isinstance(value, dict):
            for prop, sub in value.items():
                _require_bounded(sub, f"{here}.{prop}")
