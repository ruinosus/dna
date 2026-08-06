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


@dataclass(frozen=True)
class ResolvedEdge:
    """ONE reference, after the write path already looked its target up.

    This is the fact ``_validate_references`` used to compute and throw away:
    it materialized the target document, checked ``is not None``, and dropped
    both the document AND — for a polymorphic reference — WHICH declared target
    matched. An edge therefore costs no extra read; it costs not discarding.

    ``to_kind`` is ``None`` for a DANGLING reference (declared, written, and
    resolving to nothing). That is a state worth recording, not a row worth
    skipping: with ``DNA_REF_VALIDATION=warn`` — the default — such a document
    persists, and a graph that quietly omitted the broken half would read as
    healthier than the data is.

    ``to_scope`` is the scope the target resolved IN, which is not always the
    writer's: ``Kernel.get_document`` falls back to parent scopes for
    inheritable Kinds. ``None`` means "resolved, but through the inheritance
    chain, and this producer did not record which parent" — never "the same
    scope". Claiming an intra-scope relation that does not exist is exactly the
    lie the column exists to prevent.
    """

    #: Spec field the reference was declared on (``"feature"``, ``"spec_refs"``).
    field: str
    #: Position within an array-valued reference; ``0`` for a scalar one.
    ordinal: int
    #: The target NAME, exactly as the author wrote it.
    value: str
    #: The Kind that actually resolved — ``None`` when nothing did (dangling).
    to_kind: str | None
    #: The scope the target resolved in — see the class docstring.
    to_scope: str | None
    #: Every declared target, sorted. More than one = a polymorphic reference.
    declared: tuple[str, ...]


async def resolve_declared_edges(
    port: Any,
    raw: Any,
    *,
    scope: str,
    tenant: str | None,
    getter: Any,
    port_for: Any = None,
    local_getter: Any = None,
) -> tuple[list[ResolvedEdge], list[str], bool]:
    """Resolve every ``x-dna-ref`` a document declares — ONCE, for TWO readers.

    Returns ``(edges, problems, complete)``:

    * ``edges`` — one :class:`ResolvedEdge` per declared reference VALUE,
      resolved or dangling. This is what the edge producer persists.
    * ``problems`` — the human-readable complaint per unresolved value, in the
      exact wording ``WritePipeline._validate_references`` has always emitted.
      This is what the validator vetoes or logs on.
    * ``complete`` — False when a document READ raised part-way through. The
      validator has always treated that as "say nothing" (infrastructure
      trouble must never become an authoring accusation), and the producer
      must treat it as "write nothing": a PARTIAL edge set stored as if it
      were whole is a graph that lies while looking finished, which is worse
      than a graph that is honestly absent.

    Why one function and not two: a second mechanism that re-derives edges
    from the same declaration is a second mechanism that can DISAGREE with the
    first. One pass, one set of reads, two consumers — the edge is then the
    validator's own finding, by construction.

    Injected collaborators, so this module stays free of kernel imports:

    * ``getter(scope, kind, name, tenant=...)`` — the document read.
    * ``port_for(kind)`` — narrows a polymorphic declaration to the targets the
      registry actually knows. Optional; without it every declared target is
      probed, exactly as before the narrowing existed.
    * ``local_getter(scope, kind, name, tenant=...)`` — the SAME read ``getter``
      performs first, WITHOUT the parent-scope fallback, so a hit can be
      attributed to the writer's own scope. Optional and near-free (the key was
      just loaded, so it is served from the granular cache); when absent, every
      resolved edge records ``to_scope=None``.
    """
    refs = declared_references(port)
    if not refs:
        # The back-compat fast path: no declaration, no reads, no cost.
        return [], [], True
    if not callable(getter):
        # An unavailable read is not a dangling reference and not an empty
        # graph. Say nothing, and say that nothing is not the whole story.
        return [], [], False

    spec = raw.get("spec") if isinstance(raw, dict) else None
    spec = spec if isinstance(spec, dict) else {}

    edges: list[ResolvedEdge] = []
    problems: list[str] = []

    for ref in refs:
        values = reference_values(ref, spec)
        if not values:
            continue
        targets = list(ref.targets)
        if callable(port_for):
            targets = [t for t in ref.targets if port_for(t) is not None] or targets
        for ordinal, value in enumerate(values):
            matched: str | None = None
            for target in targets:
                try:
                    doc = await getter(scope, target, value, tenant=tenant)
                except Exception:  # noqa: BLE001 — a read failure is not a
                    # dangling reference; never convert infrastructure trouble
                    # into an authoring error, and never into an edge set that
                    # claims to be whole.
                    return edges, [], False
                if doc is not None:
                    matched = target
                    break
            to_scope: str | None = None
            if matched is not None and callable(local_getter):
                try:
                    local = await local_getter(scope, matched, value, tenant=tenant)
                except Exception:  # noqa: BLE001 — attribution is a nicety;
                    # failing to attribute must not fail the write.
                    local = None
                if local is not None:
                    to_scope = scope
            edges.append(ResolvedEdge(
                field=ref.field,
                # Always the positional index, never a "0 for scalars" special
                # case: a scalar field yields exactly one value, so the index IS
                # 0 there, and a field declared scalar but WRITTEN as a list
                # (an authoring error the reader tolerates) still produces
                # distinct rows instead of colliding on the primary key.
                ordinal=ordinal,
                value=value,
                to_kind=matched,
                to_scope=to_scope,
                declared=ref.targets,
            ))
            if matched is None:
                expected = " | ".join(sorted(ref.targets))
                problems.append(
                    f"spec.{ref.field} → `{value}` (no {expected} "
                    f"named `{value}` in scope `{scope}`)"
                )

    return edges, problems, True


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
