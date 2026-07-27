"""Assigning a workspace its namespace — the identity half of i-080.

ASSIGNED and stored, never derived. ``apiVersion`` participates in a document's
identity key, so a derived namespace would make renaming or migrating a
workspace change the identity of every document in it. The workspace id is used
only as the SEED for the first assignment; nothing reads it back out, and the
stored value survives any later change to the workspace.

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

__all__ = ["assign_namespace"]

logger = logging.getLogger(__name__)

_KIND = "KindNamespace"
_API_VERSION = "github.com/ruinosus/dna/tenant/v1"

#: The non-routable suffix every assigned namespace carries. Kept OUT of the
#: seed so the whole value stays opaque.
_SUFFIX = ".dna.local"

#: How many times a mint may lose a name race before giving up. A 12-hex-digit
#: token makes one collision improbable and two effectively impossible; the loop
#: exists so the improbable case self-corrects instead of surfacing.
_MINT_ATTEMPTS = 4


async def assign_namespace(kernel: Any, workspace_id: str, *, now: str) -> str:
    """Return this workspace's namespace, minting and storing one on first call.

    Idempotent: a second call returns the stored value, never a second mint.
    The returned value is an apiVersion PREFIX (``ws-1a2b3c.dna.local``) — see
    the module docstring for why it is not the full apiVersion.
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
            "apiVersion": _API_VERSION,
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
    """The namespace already assigned to ``workspace_id``, or None.

    Reads ``_lib``-direct: ``KindNamespace`` is GLOBAL and not inheritable, so a
    per-scope query would silently return nothing and mint a duplicate.
    """
    async for doc in kernel.query(SYSTEM_SCOPE, _KIND):
        spec = (doc.get("spec") or {}) if isinstance(doc, dict) else {}
        if spec.get("owner") == workspace_id and spec.get("namespace"):
            return str(spec["namespace"])
    return None
