"""``dna.memory.interchange`` — the Engram ↔ MIF projection.

Pure, deterministic, **no network, no LLM**: ``to_mif(spec, mif_id=...)`` /
``from_mif(doc)`` map between the native ``Engram`` spec (the schema in
``dna/extensions/helix/kinds/engram.kind.yaml``) and a MIF Memory Unit dict
shaped like the Markdown frontmatter profile registered by
``dna/extensions/mif/kinds/memory.kind.yaml`` — the REAL descriptor, fetched
live against MIF v1.0.0. Every field below was checked against that
descriptor, not against the (explicitly non-authoritative) mapping table in
``docs/design/2026-07-18-portable-memory-design.md`` §2 — two further
divergences from that table were found here and are corrected in the design
doc alongside the two the passthrough story already fixed:

1. **The id pin (§6).** The design table's row for ``name``/``@id`` assumed
   the MIF id minted on export IS the ``urn:mif:<uuid>`` form and is pinned
   onto the Engram's ``name``. Both are wrong per the real descriptor:

   - The Markdown frontmatter ``id`` field is a **plain identifier string**
     (MIF's own examples use slugs like ``decision-react-over-vue``, not only
     UUIDs — no ``format: uuid`` on the schema). ``urn:mif:<uuid>`` is the
     JSON-LD **``@id``**, a *separately derived* projection (see the
     descriptor's correction #1) — never written into this frontmatter.
   - ``Engram.name`` is DNA's own storage key (the bundle directory slug,
     ``rem-<hash>``) — a *different* concept from a MIF identity, and specs
     handled by this module never see it (it lives in ``metadata.name``,
     outside ``spec``).

   **Decision:** on export, mint a plain id (an opaque string — the CLI
   layer's default factory is ``uuid4``, but nothing here requires that
   shape) and pin it back onto the *Engram spec* at
   ``encoding_context["mif_id"]`` — a flat scalar key, not a nested
   ``extensions`` sub-object as the design prose speculated: the Engram
   schema already declares ``encoding_context.additionalProperties: true``,
   so this needs no schema change, and a flat key is the simplest home for a
   single scalar (mirroring the MIF side's own pragmatism: ``extensions`` is
   a namespace for provider-defined DATA, not a place to reinvent a second
   nesting level for one string). :func:`resolve_or_mint_mif_id` reads it
   back on the next export so re-exporting the SAME Engram reuses the SAME
   id. On import, :func:`from_mif` pins the doc's OWN ``id`` into
   ``encoding_context["mif_id"]`` on the projected Engram, so re-exporting an
   IMPORTED memory is stable too. ``--dedupe id`` (the CLI verb) compares
   this pinned value: for ``--as native``/``both`` against
   ``encoding_context.mif_id`` on existing Engrams, for ``--as
   passthrough``/``both`` against the passthrough Memory doc's own ``id``
   field directly (they are the SAME field there — no pin needed).

2. **``homophonic_links`` needs no vault.** The design table claimed the
   ``resonance_score`` is dropped into ``extensions`` because relationships
   can't carry it. The real descriptor's ``relationships[]`` items DO have a
   ``strength`` (0.0-1.0) field — an exact fit for ``resonance_score`` — plus
   an open ``metadata`` object that fits ``basis``. So homophonic_links round
   -trips natively through ``relationships[type=relates-to]`` with no vault
   entry at all; seeing the same field survive twice (once natively, once in
   ``x-dna``) would be redundant, not "extra safe".

The ``extensions.x-dna`` vault used here therefore carries only the Engram
fields that genuinely have **no MIF-side home**: the DNA cognitive-physics
fields the task called out (``confidence_score``, ``relevance_decay_seed``,
``surface_count``, ``cues_history``, ``encoding_context``, ``affect``,
``affect_reason``, ``visibility``) PLUS three more real Engram fields the
task's list didn't happen to enumerate but that equally have no MIF slot —
``affect_evidence_refs``, ``surface_when``, ``revisions``, ``last_surfaced``
— found while checking every row of the schema, not just the ones already
named. Omitting them would silently break the "loses nothing" bar the task
sets. ``encoding_context`` is vaulted WITHOUT its ``mif_id`` key (that key is
reconstructed from the doc's own ``id`` on import — see point 1 — so vaulting
it too would let the two copies drift).

What is **deliberately not** round-tripped by ``from_mif`` alone: MIF
Level-3 fields with no Engram equivalent (``entities``, ``ontology``,
``embedding``, ``citations``, ``aliases``, ``compressed_at``, and the
``temporal`` sub-fields beyond ``validFrom``/``validUntil``). This is not an
oversight — ``dna memory import --as both`` (the default) ALSO stores the
MIF doc byte-for-byte verbatim as ``mif-spec.dev/v1 · Memory`` (the
passthrough Kind), so system-level fidelity for those fields is already
guaranteed by the verbatim copy; ``from_mif``'s job is only to project what
Engram *can* represent, not to reinvent the passthrough copy's job.
Similarly, an unrecognized ``relationships[].type`` (anything other than
``derived-from`` / ``supersedes`` / ``relates-to``) is dropped by the
projection for the same reason.

s-memory-interchange-verbs (2026-07-19, feature f-portable-memory).
"""
from __future__ import annotations

import copy
import uuid
from typing import Any, Callable

from dna.memory.memory_type import classify_memory_type

#: CoALA taxonomy — identical enum on both sides (design §1: "identity, not
#: conversion").
_ALLOWED_MEMORY_TYPES = ("episodic", "semantic", "procedural")

#: Reserved MIF namespace roots (SPECIFICATION.md §10.2) that this module's
#: reversible area<->namespace scheme keys off.
_NAMESPACE_ROOTS = _ALLOWED_MEMORY_TYPES

#: Engram fields with no MIF-side field — the "cognitive physics" vault
#: (module docstring point above). Copied verbatim (deep-copied) both ways.
_VAULT_FIELDS: tuple[str, ...] = (
    "confidence_score",
    "relevance_decay_seed",
    "surface_count",
    "cues_history",
    "affect",
    "affect_reason",
    "affect_evidence_refs",
    "visibility",
    "surface_when",
    "revisions",
    "last_surfaced",
)

#: Default affect + reason stamped on a projected Engram when the source MIF
#: doc carries no ``x-dna.affect`` (i.e. a genuinely foreign memory, not a
#: DNA export). "surprise" reads honestly for "a fact arrived from outside"
#: without claiming a triumph/regret framing the importer has no basis for.
_DEFAULT_IMPORT_AFFECT = "surprise"


# ─────────────────────────── id stability (§6) ───────────────────────────


def resolve_or_mint_mif_id(
    spec: dict[str, Any], *, id_factory: Callable[[], str] | None = None,
) -> tuple[str, bool]:
    """Resolve the MIF id an export should use for this Engram spec.

    Returns ``(mif_id, newly_minted)``. If ``encoding_context.mif_id`` is
    already pinned (a prior export, or an id inherited from an import), it is
    reused verbatim — a re-export is stable. Otherwise a fresh id is minted
    via ``id_factory`` (default: ``uuid4``, injectable for deterministic
    tests — the same pattern ``dna.memory.verbs`` uses for ``now``).

    Pure GIVEN a factory; the default factory is the only source of
    non-determinism, exactly as scoped ("no network, no LLM" — randomness for
    id minting is not excluded, matching how ``remember`` accepts
    ``now: datetime | None`` for the same reason). Does NOT mutate ``spec``
    or persist anything — the caller (the CLI verb, which has kernel write
    access) is responsible for pinning a newly-minted id back onto the
    Engram doc so the NEXT export sees it via this same function.
    """
    ec = spec.get("encoding_context")
    existing = ec.get("mif_id") if isinstance(ec, dict) else None
    if existing:
        return str(existing), False
    factory = id_factory or (lambda: str(uuid.uuid4()))
    return factory(), True


# ─────────────────────────── namespace <-> area ───────────────────────────


def _namespace_for(area: str, memory_type: str) -> str:
    """Reversible ``area`` -> MIF ``namespace`` encoding.

    The design table's example (``Feature/X`` -> ``_episodic/feature-x``)
    lowercases/slugifies the area, which is LOSSY (case + separators are not
    recoverable) — incompatible with the round-trip-losslessly bar this
    story is held to. Instead: prefix the reserved base-type root
    (SPECIFICATION.md §10.2, ``_semantic``/``_episodic``/``_procedural``) in
    front of the area STRING VERBATIM. Still honors the descriptor's own
    documented convention (reserved root prefix) while staying exactly
    invertible by :func:`_area_from_namespace`.
    """
    root = memory_type if memory_type in _NAMESPACE_ROOTS else "semantic"
    return f"_{root}/{area}" if area else f"_{root}"


def _area_from_namespace(namespace: str | None) -> str | None:
    """Inverse of :func:`_namespace_for`. Returns ``None`` when ``namespace``
    is absent; for a namespace this module didn't produce (a foreign MIF
    doc with no reserved-root prefix), the whole string is treated as the
    area verbatim — the best honest guess, never silently dropped."""
    if not namespace:
        return None
    if namespace.startswith("_"):
        root, sep, rest = namespace[1:].partition("/")
        if root in _NAMESPACE_ROOTS:
            return rest if sep else ""
    return namespace


# ─────────────────────────── relationships <-> refs ───────────────────────


def _relationships_for_export(
    spec: dict[str, Any], id_lookup: dict[str, str] | None,
) -> list[dict[str, Any]]:
    """Build MIF ``relationships[]`` from ``source_refs`` /
    ``superseded_by_memory`` / ``homophonic_links``.

    ``id_lookup`` (optional, ``Engram name -> MIF id``) lets a batch export
    resolve cross-references to real MIF ids; without it (a single-doc
    export), targets fall back to the raw ref/name string — still a stable,
    reversible value for a round trip that stays within this module's own
    ``to_mif``/``from_mif`` pair, just not necessarily meaningful to a
    foreign MIF consumer (a known, documented MVP limit — field-faithful,
    not graph-resolving).
    """
    lookup = id_lookup or {}
    rels: list[dict[str, Any]] = []
    for ref in spec.get("source_refs") or []:
        rels.append({"type": "derived-from", "target": lookup.get(ref, ref)})
    superseded_by = spec.get("superseded_by_memory")
    if superseded_by:
        rels.append({
            "type": "supersedes",
            "target": lookup.get(superseded_by, superseded_by),
        })
    for link in spec.get("homophonic_links") or []:
        target_name = link.get("target_name")
        if not target_name:
            continue
        rel: dict[str, Any] = {
            "type": "relates-to",
            "target": lookup.get(target_name, target_name),
        }
        if link.get("resonance_score") is not None:
            rel["strength"] = link["resonance_score"]
        if link.get("basis"):
            rel["metadata"] = {"basis": link["basis"]}
        rels.append(rel)
    return rels


def _project_relationships(
    relationships: list[dict[str, Any]] | None,
) -> tuple[list[str], str | None, list[dict[str, Any]]]:
    """Inverse of :func:`_relationships_for_export`.

    Returns ``(source_refs, superseded_by_memory, homophonic_links)``.
    Relationship types outside the three this module maps
    (``derived-from``/``supersedes``/``relates-to`` — the tokens
    :func:`_relationships_for_export` emits) are skipped: they have no
    Engram-side field, and are preserved instead by the verbatim passthrough
    copy ``--as both`` stores (see module docstring).
    """
    source_refs: list[str] = []
    superseded_by_memory: str | None = None
    homophonic_links: list[dict[str, Any]] = []
    for rel in relationships or []:
        rtype = rel.get("type")
        target = rel.get("target")
        if not target:
            continue
        if rtype == "derived-from":
            source_refs.append(target)
        elif rtype == "supersedes":
            superseded_by_memory = target
        elif rtype == "relates-to":
            link: dict[str, Any] = {"target_name": target}
            strength = rel.get("strength")
            if strength is not None:
                link["resonance_score"] = strength
            basis = (rel.get("metadata") or {}).get("basis")
            if basis:
                link["basis"] = basis
            homophonic_links.append(link)
    return source_refs, superseded_by_memory, homophonic_links


# ─────────────────────────── provenance <-> owner/refs ────────────────────


def _provenance_for_export(spec: dict[str, Any]) -> dict[str, Any] | None:
    prov: dict[str, Any] = {}
    if spec.get("owner"):
        prov["wasAttributedTo"] = spec["owner"]
    if spec.get("source_refs"):
        prov["wasDerivedFrom"] = list(spec["source_refs"])
    return prov or None


def _derive_summary(content: str) -> str:
    """First non-empty line of ``content``, truncated to Engram's
    ``summary`` bound (280 chars) — the fallback when a MIF doc has no
    ``title``."""
    for line in (content or "").splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:280]
    return (content or "")[:280]


# ─────────────────────────── the vault ─────────────────────────────────────


def _build_x_dna(spec: dict[str, Any]) -> dict[str, Any]:
    vault: dict[str, Any] = {}
    for field in _VAULT_FIELDS:
        if field in spec and spec[field] is not None:
            vault[field] = copy.deepcopy(spec[field])
    ec = spec.get("encoding_context")
    if isinstance(ec, dict):
        ec_clean = {k: v for k, v in ec.items() if k != "mif_id"}
        if ec_clean:
            vault["encoding_context"] = copy.deepcopy(ec_clean)
    return vault


def _apply_x_dna(vault: dict[str, Any], spec: dict[str, Any]) -> None:
    for field in _VAULT_FIELDS:
        if field in vault:
            spec[field] = copy.deepcopy(vault[field])
    if "encoding_context" in vault and isinstance(vault["encoding_context"], dict):
        spec["encoding_context"] = copy.deepcopy(vault["encoding_context"])


# ─────────────────────────── the public projection ────────────────────────


def to_mif(spec: dict[str, Any], *, mif_id: str, id_lookup: dict[str, str] | None = None) -> dict[str, Any]:
    """Project a native ``Engram`` spec to a MIF Memory Unit dict (the
    Markdown frontmatter profile shape — see module docstring).

    Pure + deterministic: same ``spec``/``mif_id``/``id_lookup`` always
    produces the same dict. ``mif_id`` is REQUIRED (not minted here — see
    :func:`resolve_or_mint_mif_id`) so this function never touches
    randomness. ``id_lookup`` is the optional batch-export cross-reference
    map (Engram name -> MIF id); omit it for a single-doc export.
    """
    memory_type = spec.get("memory_type") or classify_memory_type(spec)
    if memory_type not in _ALLOWED_MEMORY_TYPES:
        memory_type = "semantic"
    area = spec.get("area") or ""
    body = spec.get("body")
    summary = spec.get("summary") or ""

    doc: dict[str, Any] = {
        "id": mif_id,
        "type": memory_type,
        "content": body if body else summary,
        "created": spec.get("created_at") or "",
    }
    if summary:
        doc["title"] = summary
    doc["namespace"] = _namespace_for(area, memory_type)
    if spec.get("tags"):
        doc["tags"] = list(spec["tags"])

    temporal: dict[str, Any] = {}
    if spec.get("valid_from"):
        temporal["validFrom"] = spec["valid_from"]
    if spec.get("valid_to"):
        temporal["validUntil"] = spec["valid_to"]
    if temporal:
        doc["temporal"] = temporal

    relationships = _relationships_for_export(spec, id_lookup)
    if relationships:
        doc["relationships"] = relationships

    provenance = _provenance_for_export(spec)
    if provenance:
        doc["provenance"] = provenance

    vault = _build_x_dna(spec)
    if vault:
        doc["extensions"] = {"x-dna": vault}

    return doc


def from_mif(doc: dict[str, Any]) -> dict[str, Any]:
    """Project a MIF Memory Unit dict back to a native ``Engram`` spec.

    Pure + deterministic. Always produces a spec satisfying the Engram
    schema's ``required`` set (``area``, ``surface_when``, ``source_refs``,
    ``affect``, ``summary``) — filling honest, documented defaults for
    fields a genuinely foreign (non-DNA) MIF doc has no equivalent for
    (see module docstring: ``_DEFAULT_IMPORT_AFFECT``, the
    ``mif:<id>``-tagged ``source_refs`` fallback, ``surface_when`` default
    matching ``dna memory remember``'s own CLI default).
    """
    doc_id = doc.get("id") or ""
    memory_type = doc.get("type")
    if memory_type not in _ALLOWED_MEMORY_TYPES:
        memory_type = "semantic"

    namespace = doc.get("namespace")
    area = _area_from_namespace(namespace)
    content = doc.get("content") or ""
    title = doc.get("title")

    spec: dict[str, Any] = {
        "memory_type": memory_type,
        "area": area if area else "imported/mif",
        "summary": (title or _derive_summary(content) or "(untitled MIF memory)")[:280],
        "body": content,
        "created_at": doc.get("created") or "",
    }
    if doc.get("tags"):
        spec["tags"] = list(doc["tags"])

    temporal = doc.get("temporal") or {}
    if temporal.get("validFrom"):
        spec["valid_from"] = temporal["validFrom"]
    if temporal.get("validUntil"):
        spec["valid_to"] = temporal["validUntil"]

    source_refs, superseded_by_memory, homophonic_links = _project_relationships(
        doc.get("relationships"),
    )
    provenance = doc.get("provenance") or {}
    if not source_refs:
        was_derived_from = provenance.get("wasDerivedFrom")
        if isinstance(was_derived_from, list):
            source_refs = [str(x) for x in was_derived_from]
        elif isinstance(was_derived_from, str):
            source_refs = [was_derived_from]
    if not source_refs:
        source_refs = [f"mif:{doc_id}" if doc_id else "mif:unknown"]
    spec["source_refs"] = source_refs

    if superseded_by_memory:
        spec["superseded_by_memory"] = superseded_by_memory
    if homophonic_links:
        spec["homophonic_links"] = homophonic_links

    owner = provenance.get("wasAttributedTo")
    if isinstance(owner, str):
        spec["owner"] = owner

    vault = ((doc.get("extensions") or {}).get("x-dna")) or {}
    if isinstance(vault, dict):
        _apply_x_dna(vault, spec)

    spec.setdefault("affect", _DEFAULT_IMPORT_AFFECT)
    spec.setdefault("surface_when", ["feature_touched"])
    if not spec.get("affect_reason"):
        spec["affect_reason"] = (
            f"Imported from external MIF memory {doc_id or 'unknown'} (mif-spec.dev/v1) — "
            "no affect/reason was carried on the source doc's x-dna vault."
        )

    # Pin the id LAST — self-healing even if a copied doc's x-dna.encoding_context
    # carried a stale mif_id from elsewhere; the doc's own `id` always wins.
    ec = dict(spec.get("encoding_context") or {})
    ec["mif_id"] = doc_id
    spec["encoding_context"] = ec

    return spec


__all__ = [
    "resolve_or_mint_mif_id",
    "to_mif",
    "from_mif",
]
