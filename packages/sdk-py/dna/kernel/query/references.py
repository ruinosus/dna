"""Declared cross-Kind references — the ``x-dna-ref`` schema annotation (i-040).

Until this module, a reference between two Kinds was a field holding a name
and nothing else: ``Story.spec.feature`` is the string ``"f-thing"``, and the
kernel had no idea that string was supposed to name a Feature. It could not
type it, could not validate it, and could not stop it dangling. The graph was
real but undeclared — which is why ``dna_edges`` was specified to be populated
by regex-matching slug prefixes, and why it was never built: there was nothing
factual to derive edges FROM.

This module adds the missing declaration and nothing else. It is deliberately
pure — reading declarations off a ``KindPort`` and resolving target Kinds. The
write-time enforcement lives in ``write_pipeline.py``; the derivation of an
edge table (``dna_edges``) is a separate concern that can now read fact
instead of guessing.

The annotation
--------------
A reference is declared **on the field**, inside the Kind's own JSON Schema::

    spec:
      schema:
        properties:
          feature:
            type: string
            x-dna-ref: Feature          # single target
          spec_refs:
            type: array
            items: {type: string}
            x-dna-ref: Spec             # array → every item is a reference
          ref:
            type: string
            x-dna-ref: [Spec, Plan, Story]   # polymorphic → any one of them

**Why on the field, and why ``x-``.** Three properties matter here:

1. *Zero meta-schema change.* ``kind-definition.schema.json`` pins ``spec``
   with ``additionalProperties: false`` and 35 known fields, so a new
   top-level key would be a breaking edit to the public descriptor contract.
   But ``spec.schema`` is declared as an unconstrained ``{"type": "object"}``
   — a JSON Schema — and the ``x-`` prefix is that ecosystem's reserved
   extension convention (as in OpenAPI). Validators ignore unknown keywords
   by specification, so an ``x-dna-ref`` annotation cannot change how any
   existing document validates.
2. *Field granularity.* The reference belongs to the field, next to its type
   and description, where an author writing a ``.kind.yaml`` will see it.
3. *It does not disturb ``dep_filters``.* ``dep_filters`` looks like the
   natural home — it already maps a spec field to a target Kind alias — but
   it is load-bearing for PROMPT COMPOSITION: ``prompt_builder`` uses an
   Agent's ``dep_filters`` to decide which documents get folded into the
   Mustache context. Attaching write-time existence enforcement to it would
   change composition behaviour for every Agent and UseCase, where a missing
   optional Skill is legitimately filtered out rather than being an error.
   The two concerns overlap in appearance and differ in semantics, so they
   stay separate. Where both are present they should agree; that agreement is
   checked by ``tests/test_references.py`` rather than assumed.

Back-compatibility is by construction: a Kind that declares no ``x-dna-ref``
produces an empty reference list here, and the write path then does no reads
and behaves exactly as it did before.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: The schema keyword that declares a reference.
REF_KEYWORD = "x-dna-ref"


@dataclass(frozen=True)
class DeclaredReference:
    """One declared reference: a spec field pointing at one or more Kinds."""

    field: str
    #: Target Kind names, sorted. More than one = polymorphic (any one matches).
    targets: tuple[str, ...]
    #: True when the field is an array — every item is a reference.
    is_array: bool

    @property
    def polymorphic(self) -> bool:
        return len(self.targets) > 1


def _coerce_targets(value: Any) -> tuple[str, ...]:
    """Normalize an ``x-dna-ref`` value to a sorted tuple of Kind names."""
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = [v for v in value if isinstance(v, str)]
    else:
        return ()
    return tuple(sorted({v.strip() for v in items if v and v.strip()}))


def declared_references(port: Any) -> list[DeclaredReference]:
    """Every ``x-dna-ref`` declared by ``port``'s schema, sorted by field.

    Fail-soft on purpose: a Kind whose ``schema()`` raises, returns a
    non-dict, or carries a malformed annotation yields no references rather
    than breaking a write. A declaration this module cannot understand must
    never be able to take the write path down with it.
    """
    if port is None:
        return []
    try:
        schema = port.schema()
    except Exception:  # noqa: BLE001 — a broken schema stays permissive
        return []
    return references_from_schema(schema)


def references_from_schema(schema: Any) -> list[DeclaredReference]:
    """``declared_references`` against a raw schema dict (the testable core)."""
    if not isinstance(schema, dict):
        return []
    props = schema.get("properties")
    if not isinstance(props, dict):
        return []

    out: list[DeclaredReference] = []
    for field in sorted(props):
        spec = props[field]
        if not isinstance(spec, dict) or REF_KEYWORD not in spec:
            continue
        targets = _coerce_targets(spec.get(REF_KEYWORD))
        if not targets:
            continue
        out.append(
            DeclaredReference(
                field=field,
                targets=targets,
                is_array=spec.get("type") == "array",
            )
        )
    return out


def reference_values(ref: DeclaredReference, spec: Any) -> list[str]:
    """The non-empty string values ``ref`` points at, for one document's spec.

    An absent field, an explicit ``null``, an empty string and an empty list
    all yield ``[]`` — an OPTIONAL reference that is simply not set is not a
    dangling reference, and must never be reported as one.
    """
    if not isinstance(spec, dict):
        return []
    value = spec.get(ref.field)
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    return [v.strip() for v in items if isinstance(v, str) and v.strip()]


def resolve_target_kinds(
    ref: DeclaredReference, resolve: Any,
) -> tuple[list[str], list[str]]:
    """Split ``ref.targets`` into (known Kind names, unknown declarations).

    ``resolve`` maps a declared token to a real Kind name, accepting either a
    Kind name (``Feature``) or an alias (``sdlc-feature``). Declaring a target
    that no registered Kind provides is an authoring error worth surfacing,
    so it is returned rather than silently dropped.
    """
    known: list[str] = []
    unknown: list[str] = []
    for token in ref.targets:
        resolved = resolve(token)
        (known if resolved else unknown).append(resolved or token)
    return sorted(set(known)), sorted(set(unknown))
