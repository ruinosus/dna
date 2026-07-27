"""Authoring a Kind — a dedicated door, not a hole in the generic one.

The generic write refuses BOOTSTRAP Kinds by construction, and that refusal
stays. This is a SEPARATE entry point with its own authorization: it writes
exactly one Kind (``KindDefinition``), always WITHOUT an approval marker, always
into the caller's own namespace.

What it writes is a real document — auditable, listable, diffable — that the
registry refuses to take until someone approves it (see the approval gate in
``dna/kernel/kinds/registry.py``). Absence of registration IS absence of effect:
an unregistered Kind neither validates documents nor routes the storage of its
documents.

**The apiVersion is BUILT here, not passed through.**
:func:`~dna.application.namespace_assignment.assign_namespace` returns an
apiVersion PREFIX (``ws-1a2b3c.dna.local``), never an apiVersion — a
``KindNamespace`` claim never carries a version segment, and
``namespace_of()`` (what ``NamespaceOwnershipGate`` resolves a write with)
strips the version off an apiVersion before looking the claim up. Storing
``target_api_version: <prefix>`` would therefore declare the Kind under a
namespace of ``""`` — a claim on nothing — and the gate would refuse the
workspace's own first Kind. The caller builds ``f"{namespace}/v1"``; that
caller is this module.

**No tenant argument on the write, deliberately.** ``KindDefinition`` is
structurally non-overlayable, so it cannot be forked into a layer at all: a
workspace's Kind is authored at the BASE of a scope the workspace owns, and the
namespace gate attributes that write through the scope's own declared owner
(``Genome.spec.owner_tenant``). Passing ``tenant=`` would turn this into a layer
write and be vetoed before the gate ever ran.
"""
from __future__ import annotations

from typing import Any

from dna.application.namespace_assignment import assign_namespace

__all__ = ["author_kind_impl", "list_authored_kinds_impl"]

_KIND = "KindDefinition"
_API_VERSION = "github.com/ruinosus/dna/core/v1"

#: The separator between a namespace and a Kind name in the document's NAME.
#: The name has to carry the namespace: two workspaces may both author
#: ``Contrato``, and the pair is what keeps their documents apart in a scope
#: (the registry key is ``(api_version, kind)`` for the same reason).
_NAME_SEP = "--"


def _alias_owner(namespace: str) -> str:
    """The ``<owner>`` half of the alias convention, derived from the namespace.

    The alias is declared GLOBALLY unique, so the owner half has to be the whole
    namespace and not a readable piece of it: ``acme.example`` and
    ``acme.other`` share a first label but are two different owners. Dots and
    slashes collapse to ``-`` so the result stays a single kebab token."""
    return "-".join(
        part for part in namespace.replace("/", ".").split(".") if part
    )


def kind_document_name(namespace: str, kind: str) -> str:
    """The document name an authored Kind is stored under.

    Exposed because approval (a separate act by a different actor) has to be
    able to address the very document this door wrote, and deriving that name in
    two places is how the two halves drift apart."""
    return f"{namespace}{_NAME_SEP}{kind}"


async def author_kind_impl(
    live: Any, *, kind: str, schema: dict, tenant: str, now: str,
    traits: list[str] | None = None,
) -> dict[str, Any]:
    """Write a tenant Kind, unapproved. It has no effect until approved.

    Raises ``ValueError`` for a missing tenant / Kind name (the face maps it to
    400); every policy refusal below this — the namespace gate, the schema
    validation — surfaces from the kernel unchanged.
    """
    kind = (kind or "").strip()
    if not kind:
        raise ValueError("kind is required to author a Kind")
    if not (tenant or "").strip():
        raise ValueError("tenant is required to author a Kind")
    if not isinstance(schema, dict):
        raise ValueError("schema must be a JSON Schema object")

    from dna.kernel.kinds.registry import generate_alias

    namespace = await assign_namespace(live.kernel, tenant, now=now)
    name = kind_document_name(namespace, kind)
    raw = {
        "apiVersion": _API_VERSION,
        "kind": _KIND,
        "metadata": {"name": name},
        "spec": {
            # A PREFIX plus the version segment — see the module docstring.
            "target_api_version": f"{namespace}/v1",
            "target_kind": kind,
            "alias": generate_alias(_alias_owner(namespace), kind),
            "origin": namespace,
            "schema": schema,
            "traits": list(traits or []),
            "storage": {"type": "yaml", "container": f"{kind.lower()}s"},
            "created_at": now,
            # Deliberately absent: approved_by / approved_at. This path CANNOT
            # set them — approval is a separate, privileged act by a different
            # actor. A caller-supplied value is dropped on the floor here: the
            # spec is BUILT field by field, never merged from the request body,
            # so there is no key an author can smuggle through.
        },
    }
    version = await live.kernel.write_document(
        live.default_scope(tenant), _KIND, name, raw,
    )
    return {
        "namespace": namespace, "kind": kind, "name": name,
        "approved": False, "version": version,
    }


async def list_authored_kinds_impl(
    live: Any, *, tenant: str | None = None, scope: str | None = None,
) -> dict[str, Any]:
    """Every ``KindDefinition`` document in the caller's scope, with its
    approval state — the audit surface the authoring door exists to produce.

    Reads DOCUMENTS, not the registry: an unapproved Kind is precisely the one
    the registry does not have, so a registry-backed listing would show every
    Kind except the ones a reviewer needs to see.
    """
    sc = scope or live.default_scope(tenant)
    kinds: list[dict[str, Any]] = []
    async for raw in live.kernel.query(sc, _KIND, tenant=tenant):
        if not isinstance(raw, dict):
            continue
        spec = raw.get("spec") or {}
        meta = raw.get("metadata") or {}
        approved_by = str(spec.get("approved_by") or "").strip()
        kinds.append({
            "name": (meta.get("name") if hasattr(meta, "get") else None)
                    or raw.get("name"),
            "kind": spec.get("target_kind"),
            "api_version": spec.get("target_api_version"),
            "namespace": spec.get("origin"),
            "approved": bool(approved_by),
            "approved_by": approved_by or None,
            "approved_at": spec.get("approved_at"),
            "created_at": spec.get("created_at"),
        })
    return {"scope": sc, "kinds": kinds}
