"""``dna.memory.personal`` — the personal / private per-user memory partition.

Personal memory is the ONE DNA construct whose partition key is the *human*, not
the *workspace*: keyed on the durable Entra ``oid``, it is literally the SAME
partition in workspace A, workspace B, and a bare MCP client — "your memory
follows *you*" as a primary-key value (ADR ``docs/adr/ADR-personal-memory.md``).

This module is the **pure core** of the model — no kernel / FastMCP / HTTP
import — so it is fully unit-testable and mirror-able 1:1 in TypeScript
(``packages/sdk-ts/src/memory/personal.ts``). It holds three things:

1. the reserved partition namespace ``personal:<oid>`` (a value-namespace inside
   the EXISTING ``tenant`` partition — zero schema migration), plus the helpers
   to build/recognize it;
2. the :data:`MemoryScope` selector (``workspace`` default / ``personal``) and
   the :func:`resolve_memory_tenant` decision (ADR §5) — personal maps to
   ``personal:<oid>`` with the oid resolved SERVER-SIDE, fail-closed on a missing
   identity; workspace is the current behavior, unchanged;
3. :func:`assert_no_personal_override` — the layer-4 guard that a caller-supplied
   raw ``tenant`` may never name the ``personal:`` scheme (personal partitions
   are reachable ONLY through ``memory_scope=personal``, whose oid is derived
   server-side).

INV-PERSONAL (ADR §7) is enforced by four independent layers; this module owns
layer 1 (server-derived oid — the oid is never a caller param) and layer 4 (raw
override rejection). Layer 2 (the ``tenant IN ('', X)`` union predicate provably
excludes ``personal:*`` from a workspace request) is a property of the source
adapter; layer 3 (the validator reserves the ``personal:`` scheme) lives in
``dna.kernel.protocols.validate_tenant_slug``.
"""
from __future__ import annotations

from typing import Literal

#: The reserved tenant *scheme* (the segment before the first ``:``) that marks a
#: personal partition. Reserved at the validator so no Workspace can be named to
#: shadow/alias it (ADR §3.4).
PERSONAL_TENANT_SCHEME = "personal"

#: The concrete prefix a personal partition value carries: ``personal:<oid>``.
PERSONAL_TENANT_PREFIX = f"{PERSONAL_TENANT_SCHEME}:"

#: The memory-targeting selector on every memory verb (ADR §3.1). ``workspace``
#: is the default — every existing call keeps its behavior; ``personal`` is
#: strictly additive.
MemoryScope = Literal["workspace", "personal"]

WORKSPACE_SCOPE: MemoryScope = "workspace"
PERSONAL_SCOPE: MemoryScope = "personal"


class PersonalIdentityRequired(PermissionError):
    """Raised when ``memory_scope=personal`` is requested but NO identity could
    be resolved server-side (no verified ``oid`` claim on an authenticated
    request, and no ``DNA_PERSONAL_ID`` offline).

    Personal memory REQUIRES an identity — it must never resolve to a null/blank
    partition (that would collapse every identity's private memory into one
    shared bucket). Fail-closed, mirroring the tenant bridge's discipline.
    Subclasses ``PermissionError`` so the surfaces can map it to the same
    access-denied channel as ``CrossTenantError``/``CrossWorkspaceError``.
    """


class PersonalOverrideRejected(PermissionError):
    """Raised when a caller supplies a raw ``tenant`` naming the reserved
    ``personal:`` scheme (INV-PERSONAL layer 4, ADR §7.4).

    Personal partitions are reachable ONLY through the ``memory_scope=personal``
    selector, whose oid is derived server-side — never through a raw ``tenant``
    param. This closes the "pass ``tenant=personal:<victim-oid>`` directly"
    attack. Subclasses ``PermissionError`` for the same denial channel.
    """


#: The identity family that keeps the BARE ``personal:<id>`` value (no family
#: segment) — Entra, the original lane. Keeping it bare means zero migration of
#: existing personal partitions (decision D6). Any OTHER family (e.g. ``google``)
#: is namespaced as ``personal:<family>:<id>`` so the families never collide.
PERSONAL_IMPLICIT_FAMILY = "entra"


def personal_tenant(oid: str, family: str | None = None) -> str:
    """Build the reserved personal partition value for a durable identity.

    Two lanes, one reserved scheme:

    * Entra (default / ``family="entra"``) → the bare ``personal:<oid>`` — the
      original value, so existing partitions need **no migration**;
    * any other family → ``personal:<family>:<id>``, so no two families' identities
      can ever collide — including two families that both read a token's ``sub``
      claim. The CLI auth bridge deliberately keeps ``family="google"`` (a direct
      Google sign-in, numeric ``sub``) and ``family="workos"`` (the WorkOS/AuthKit
      consumer lane; its ``sub`` is the WorkOS user id, NOT a Google subject, even
      when the user signed in *through* Google) as TWO SEPARATE families for
      exactly this reason — see ``dna_cli._mcp_auth.identity_claim_for_family``.

    ``personal_tenant("abc") == "personal:abc"``;
    ``personal_tenant("abc", family="google") == "personal:google:abc"``.
    Raises :class:`PersonalIdentityRequired` for a blank/empty identity in any
    family — a personal partition must always carry a concrete identity.
    """
    ident = (oid or "").strip()
    if not ident:
        raise PersonalIdentityRequired(
            "personal memory needs a non-empty identity to key the partition"
        )
    fam = (family or PERSONAL_IMPLICIT_FAMILY).strip().lower()
    if fam == PERSONAL_IMPLICIT_FAMILY:
        return f"{PERSONAL_TENANT_PREFIX}{ident}"
    return f"{PERSONAL_TENANT_PREFIX}{fam}:{ident}"


def is_personal_tenant(tenant: str | None) -> bool:
    """True when ``tenant`` names the reserved personal partition scheme
    (``personal:<oid>``). ``None`` / a workspace id / base ``''`` → False."""
    return bool(tenant) and tenant.startswith(PERSONAL_TENANT_PREFIX)


def tenant_scheme(tenant: str | None) -> str | None:
    """The scheme segment of ``tenant`` (before the first ``:``), or ``None`` when
    the value carries no ``:`` (an ordinary workspace id / base ``''``)."""
    if not tenant or ":" not in tenant:
        return None
    return tenant.split(":", 1)[0]


def resolve_memory_tenant(
    *,
    memory_scope: MemoryScope,
    oid: str | None,
    workspace_tenant: str | None,
    family: str | None = None,
) -> str | None:
    """Resolve the physical ``tenant`` a memory request runs against — the ADR §5
    decision, pure and workspace-independent for the personal case.

    * ``memory_scope="personal"`` → ``personal:<oid>``, with ``oid`` the durable
      identity resolved SERVER-SIDE (token claim / ``DNA_PERSONAL_ID``). A missing
      oid FAILS CLOSED (:class:`PersonalIdentityRequired`) — never a null
      partition. The result is the SAME partition in every workspace + client
      (the portability thesis made physical).
    * ``memory_scope="workspace"`` (default) → ``workspace_tenant`` unchanged (the
      current behavior — the workspace id the auth bridge already resolved).

    The oid is a parameter here only because this pure function does not read
    tokens; the SURFACES derive it server-side and are the sole callers — a
    caller can never inject the oid (INV-PERSONAL layer 1). ``family`` (the
    provider family the identity came from, also server-derived) namespaces the
    partition for non-Entra lanes: Entra/None → bare ``personal:<oid>``,
    ``"google"`` → ``personal:google:<sub>``, ``"workos"`` →
    ``personal:workos:<sub>`` — each its OWN namespace, so none of the three ever
    collide even for the same raw id string. ``"google"`` and ``"workos"`` both
    read a token's ``sub`` claim, but for different reasons: Google Workspace
    direct sign-in — Google's own OIDC subject; WorkOS/AuthKit, the consumer
    sign-in lane (Lane B) — the WorkOS user id (``user_...``). They are kept
    SEPARATE families deliberately: WorkOS is the token issuer even when the user
    signed in *through* Google, so it is never a Google identity, and a deployment
    running both IdPs at once must not let them alias the same partition.
    Migrating off WorkOS as the consumer IdP would orphan ``personal:workos:*``
    partitions (they are not portable to a future direct-Google ``sub``).
    """
    if memory_scope == PERSONAL_SCOPE:
        if oid is None or not str(oid).strip():
            raise PersonalIdentityRequired(
                "memory_scope=personal requires a server-resolved identity (oid) — "
                "authenticated requests read it from the verified token; offline/stdio "
                "reads DNA_PERSONAL_ID. None was available — access denied (fail-closed)."
            )
        return personal_tenant(str(oid), family=family)
    # workspace (default) — unchanged behavior.
    return workspace_tenant


def assert_no_personal_override(tenant: str | None) -> None:
    """Reject a caller-supplied raw ``tenant`` that names the reserved
    ``personal:`` scheme (INV-PERSONAL layer 4, ADR §7.4).

    The memory surfaces call this on any raw ``tenant`` a caller passes for a
    WORKSPACE-scoped request: a ``personal:*`` value there is always an attempt to
    reach a personal partition by naming it directly, which the model forbids —
    personal partitions are reached ONLY via ``memory_scope=personal`` (oid
    derived server-side). No-op for ``None`` / a workspace id / base ``''``.
    """
    if is_personal_tenant(tenant):
        raise PersonalOverrideRejected(
            f"tenant {tenant!r} names the reserved 'personal:' scheme — personal "
            "memory is reachable only via memory_scope=personal (identity derived "
            "server-side), never a raw tenant override — access denied."
        )


__all__ = [
    "PERSONAL_TENANT_SCHEME",
    "PERSONAL_TENANT_PREFIX",
    "MemoryScope",
    "WORKSPACE_SCOPE",
    "PERSONAL_SCOPE",
    "PersonalIdentityRequired",
    "PersonalOverrideRejected",
    "personal_tenant",
    "is_personal_tenant",
    "tenant_scheme",
    "resolve_memory_tenant",
    "assert_no_personal_override",
]
