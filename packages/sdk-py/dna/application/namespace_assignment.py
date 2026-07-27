"""Assigning a workspace its namespace — the identity half of i-080.

ASSIGNED and stored, never derived. ``apiVersion`` participates in a document's
identity key, so a derived namespace would make renaming or migrating a
workspace change the identity of every document in it. Nothing reads the
workspace id back out of the namespace, and the stored value survives any later
change to the workspace.

**What is assigned is a PREFIX, not an apiVersion.** ``KindNamespace``'s
descriptor says ``namespace`` never contains a version and never ends in ``/``,
and :func:`dna.kernel.kinds.namespaces.namespace_of` — the function
``NamespaceOwnershipGate`` resolves a write with — strips the version segment
off an ``apiVersion`` before looking a claim up. So a claim stored as
``ws-1a2b.dna.local/v1`` would be a claim on nothing: the gate would look up
``ws-1a2b.dna.local``, find no row, and refuse the workspace's very first Kind.
The assigned value is the prefix; the apiVersion a Kind is declared under is
``f"{namespace}/v1"``, built by the caller.

That is also what keeps the value out of trouble as a document NAME. The claim
is stored at ``_lib/kind-namespaces/<name>.yaml``; a ``/`` in the name would
address a directory that does not exist (measured — the write raises
``FileNotFoundError``). A prefix has no ``/`` in it, so name and value can stay
the same string.

The ``.dna.local`` suffix is deliberate: NON-ROUTABLE, so an assigned namespace
never looks like a domain somebody could claim later. A workspace that wants a
public identity (``acme.example``) goes through the proof-of-ownership flow and
gets a second claim; nothing here constrains the count, and the descriptor says
so.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any

from dna.kernel.protocols import SYSTEM_SCOPE

__all__ = ["TENANT_API_VERSION", "assign_namespace"]

logger = logging.getLogger(__name__)

_KIND = "KindNamespace"

#: The apiVersion of the TENANT plane — the one every tenancy record is declared
#: under: ``KindNamespace`` here, ``Workspace``/``WorkspaceMembership`` in
#: :mod:`dna.application.runtime`, which imports this name. Defined ONCE: it is a
#: wire value, and two constants for one wire value drift.
TENANT_API_VERSION = "github.com/ruinosus/dna/tenant/v1"

#: The non-routable suffix every assigned namespace carries. Kept OUT of the
#: random token so the whole value stays opaque.
_SUFFIX = ".dna.local"

#: How many times a mint may lose a name race before giving up. A 12-hex-digit
#: token makes one collision improbable and two effectively impossible; the loop
#: exists so the improbable case self-corrects instead of surfacing.
_MINT_ATTEMPTS = 4


async def assign_namespace(kernel: Any, workspace_id: str, *, now: str) -> str:
    """Return the namespace THIS FUNCTION ASSIGNED to the workspace, minting and
    storing one on first call.

    Idempotent: a second call returns the stored value, never a second mint.
    The returned value is an apiVersion PREFIX (``ws-1a2b3c.dna.local``) — see
    the module docstring for why it is not the full apiVersion.

    NOT "the workspace's namespace". A workspace MAY OWN SEVERAL — the
    ``KindNamespace`` descriptor says nothing constrains the count — so no
    function can return *the* one, and a function that returned whichever claim
    the registry yielded first would let two authoring sessions land Kinds under
    two different apiVersions, which participate in document identity. So the
    contract is narrower and stable: candidates are filtered to the ASSIGNED
    shape (the ``.dna.local`` suffix) and reduced to a fixed choice. A workspace
    that later proves ownership of a public namespace (``acme.example``) does
    not silently change what this answers — authoring under that other claim is
    a CALLER's explicit decision, never a side effect of a second row appearing.
    """
    if not workspace_id:
        raise ValueError("workspace_id is required to assign a namespace")

    existing = await _stored_for(kernel, workspace_id)
    if existing is not None:
        return existing

    from dna.kernel.errors import DocumentNameTaken

    for _ in range(_MINT_ATTEMPTS):
        # A short random token, not a slug of the id: the value must not invite
        # anyone (including us) to parse a workspace out of it later.
        namespace = f"ws-{secrets.token_hex(6)}{_SUFFIX}"
        raw = {
            "apiVersion": TENANT_API_VERSION,
            "kind": _KIND,
            "metadata": {"name": namespace},
            "spec": {
                # `owner` is the schema's field for the owning workspace, and it
                # is the field `owner_of` resolves against — the same value the
                # kernel `tenant` column carries, matched whole, never parsed.
                "owner": workspace_id,
                "namespace": namespace,
                "claimed_at": now,
                # Free-form and never read by the enforcement path; it exists so
                # an operator reading the registry can tell a MINT from a proven
                # claim without inferring it from the name's shape.
                "notes": "assigned automatically at workspace creation",
            },
        }
        try:
            # ATOMIC CREATE. Not for idempotency — the read above covers the
            # ordinary repeat — but so a token collision can never hand this
            # workspace a namespace another one already owns. Two rows naming
            # one namespace resolve to a REFUSAL for BOTH owners, so silently
            # overwriting would take a third party down with us.
            await kernel.write_document(
                SYSTEM_SCOPE, _KIND, namespace, raw,
                invalidate_mode="doc", if_absent=True,
            )
        except DocumentNameTaken:
            logger.warning(
                "namespace assignment: minted name %r was already taken — "
                "re-minting for workspace %r", namespace, workspace_id,
            )
            continue
        return namespace

    raise RuntimeError(
        f"could not mint a free namespace for workspace {workspace_id!r} after "
        f"{_MINT_ATTEMPTS} attempts — every candidate name was already claimed, "
        f"which at this token width means the registry is not what we think it "
        f"is. Refusing to reuse an existing claim."
    )


async def _stored_for(kernel: Any, workspace_id: str) -> str | None:
    """The namespace already ASSIGNED to ``workspace_id``, or None.

    Filtered to the assigned shape and reduced with ``min``, never "the first row
    that matched". A workspace may own several claims, so the unfiltered answer
    would depend on query order and could flip between two calls — see
    :func:`assign_namespace`'s docstring for why a flipping apiVersion is a
    document-identity problem, not a cosmetic one. ``min`` makes the answer a
    function of the SET of assigned rows, not of the order they arrive in.

    READ-THEN-WRITE, deliberately unlocked: two simultaneous FIRST calls both
    read nothing and both mint, leaving the workspace owning two assigned
    namespaces. Unreachable from ``create_workspace_impl`` (one call per
    creation), and unfixable without a deterministic — i.e. DERIVED — name, which
    is the one thing this module exists to refuse. It is also the same edge as
    the paragraph above seen from the other side: even with two assigned rows,
    the answer is still one namespace and still the same one every time.

    Reads ``_lib``-direct: ``KindNamespace`` is GLOBAL and not inheritable, so a
    per-scope query would silently return nothing and mint a duplicate.
    """
    assigned: list[str] = []
    async for doc in kernel.query(SYSTEM_SCOPE, _KIND):
        spec = (doc.get("spec") or {}) if isinstance(doc, dict) else {}
        namespace = spec.get("namespace")
        if spec.get("owner") != workspace_id or not namespace:
            continue
        if str(namespace).endswith(_SUFFIX):
            assigned.append(str(namespace))
    return min(assigned) if assigned else None
