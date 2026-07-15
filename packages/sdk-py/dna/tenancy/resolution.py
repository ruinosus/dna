"""``dna.tenancy.resolution`` — the pure workspace-resolution policy (Model B).

The heart of the ADR "Model B" tenancy rework (feature ``f-ws-resolution``, F2):
resolve the DNA tenancy dimension (a ``workspace_id``) from the caller's
**verified identity + WorkspaceMembership**, NOT from the Azure ``tid``.

    > INVARIANT. Every read/write executes against exactly one workspace id, and
    > is served ONLY if the request's verified identity holds an ``active``
    > WorkspaceMembership in that workspace; otherwise it is denied (fail-closed).
    > The workspace is resolved from the verified identity + membership BEFORE the
    > source is touched — never from an unverified caller argument (an explicit
    > ``requested`` workspace is only ever a *selector among the identity's own
    > memberships*, re-verified against membership).

This module is CORE (no FastMCP / HTTP / kernel import): the FastMCP context glue
(reading the live token, loading the memberships from the kernel) lives in
``dna_cli._mcp_auth``; the ``(scope, tenant=workspace_id)`` physical keying lives
in ``dna.application.live``. Here is only the decision.

Security notes:

* ``identity_from_token`` reads ONLY verified Entra token claims (``oid`` /
  ``email`` / ``preferred_username`` / ``upn`` / ``tid``). The email is an
  IdP-vouched claim — matching a membership on it is impersonation-proof.
* ``oid`` is the durable key; email is the invite handle. A membership whose
  ``identity_oid`` is already bound matches ONLY on ``oid`` (a later email
  reassignment cannot hijack it). A still-unbound but ``active`` grant (the F1
  founder seed, or a grant bound in a later phase) matches on the verified email
  until its ``oid`` is captured — exactly the F1 seed's documented contract.
* Only ``active`` grants authorize. A ``pending`` invite grants nothing until it
  is accepted+bound (feature ``f-ws-invite``, F3) — fail-closed.
* The Azure ``tid`` is retained as provenance only; it is NEVER the tenant.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

# The Entra claims an identity is read from. ``oid`` is the durable subject; the
# email is taken from the first present of these verified claims.
DEFAULT_OID_CLAIM = "oid"
DEFAULT_EMAIL_CLAIMS = ("email", "preferred_username", "upn")
DEFAULT_TID_CLAIM = "tid"


class CrossWorkspaceError(PermissionError):
    """A verified identity tried to reach a workspace it holds no active
    membership in (or holds none at all). Raised by the resolver and surfaced to
    the MCP/REST client as an access-denied error — the fail-closed half of the
    Model B tenancy contract."""


def normalize_email(email: str | None) -> str:
    """Case-fold + trim an email into its canonical comparison form.

    Emails are matched case-insensitively (the local part is technically
    case-sensitive per RFC, but every real IdP folds it; folding both sides is
    the safe, interoperable choice). Returns ``""`` for ``None``/blank."""
    if not email:
        return ""
    return email.strip().lower()


@dataclass(frozen=True)
class Identity:
    """A VERIFIED caller identity, distilled from an IdP token.

    ``oid`` — the stable Entra object id (the durable key). ``email`` — the
    verified email/``preferred_username`` (the invite handle). ``tid`` — the
    Azure org the token came from: **provenance only** under Model B, never the
    tenant."""

    oid: str | None = None
    email: str | None = None
    tid: str | None = None


@dataclass(frozen=True)
class Membership:
    """One identity→workspace grant — the pure-policy view of a
    ``WorkspaceMembership`` doc (``dna.extensions.tenant``).

    ``status`` is ``pending`` (invited, ``identity_oid`` unbound) or ``active``
    (accepted / seeded — authorizes). Only ``active`` grants ever authorize."""

    workspace_id: str
    identity_email: str | None = None
    identity_oid: str | None = None
    role: str = "member"
    status: str = "pending"

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> "Membership":
        """Build from a WorkspaceMembership doc ``spec`` dict (the kernel row)."""
        return cls(
            workspace_id=str(spec.get("workspace_id") or ""),
            identity_email=spec.get("identity_email"),
            identity_oid=spec.get("identity_oid"),
            role=str(spec.get("role") or "member"),
            status=str(spec.get("status") or "pending"),
        )


def identity_from_token(
    claims: dict[str, Any] | None,
    *,
    oid_claim: str | None = None,
    email_claims: Iterable[str] | None = None,
    tid_claim: str | None = None,
) -> Identity:
    """Distill a verified token's ``claims`` into an :class:`Identity`.

    Reads ONLY verified claims: the durable ``oid``, the email from the first
    present of ``email_claims`` (default email/preferred_username/upn), and the
    ``tid`` (provenance). Missing claims become ``None`` — the resolver then
    fails closed on an identity that can match no membership."""
    claims = claims or {}
    oid_key = oid_claim or DEFAULT_OID_CLAIM
    tid_key = tid_claim or DEFAULT_TID_CLAIM
    email_keys = tuple(email_claims) if email_claims is not None else DEFAULT_EMAIL_CLAIMS

    oid = _clean_str(claims.get(oid_key))
    tid = _clean_str(claims.get(tid_key))
    email = None
    for key in email_keys:
        candidate = _clean_str(claims.get(key))
        if candidate:
            email = candidate
            break
    return Identity(oid=oid, email=email, tid=tid)


def membership_matches_identity(m: Membership, identity: Identity) -> bool:
    """True when ``m`` is an ACTIVE grant that belongs to ``identity``.

    Matching rule (impersonation-proof, oid-durable):

    * a non-``active`` grant never matches (pending invites authorize nothing);
    * when the grant is bound (``identity_oid`` set), it matches ONLY the same
      verified ``oid`` — email is ignored, so a later email reassignment cannot
      hijack a bound membership;
    * when the grant is ``active`` but still UNBOUND (``identity_oid`` null — the
      F1 founder seed, or a grant awaiting first sign-in), it matches on the
      VERIFIED email (the handle) until the oid is captured.
    """
    if m.status != "active":
        return False
    if m.identity_oid:
        # bound grant → durable oid is the only key.
        return bool(identity.oid) and m.identity_oid == identity.oid
    # unbound-but-active grant → match on the verified email handle.
    if not identity.email or not m.identity_email:
        return False
    return normalize_email(m.identity_email) == normalize_email(identity.email)


def active_workspaces_for(
    identity: Identity, memberships: Iterable[Membership]
) -> list[str]:
    """The workspace ids ``identity`` holds an active membership in — ordered,
    de-duplicated (first-seen order preserved for a deterministic sole/default)."""
    seen: dict[str, None] = {}
    for m in memberships:
        if m.workspace_id and membership_matches_identity(m, identity):
            seen.setdefault(m.workspace_id, None)
    return list(seen.keys())


def workspace_for_identity(
    *,
    identity: Identity,
    requested_workspace: str | None,
    memberships: Iterable[Membership],
) -> str:
    """Resolve the single workspace this request runs against — fail-closed.

    * no active membership anywhere → deny (:class:`CrossWorkspaceError`);
    * ``requested_workspace`` given but not one the identity is an active member
      of → deny (a caller cannot select a workspace it does not belong to);
    * ``requested_workspace`` given and a member → return it (the selector,
      re-verified against membership);
    * no ``requested_workspace`` + exactly one membership → that workspace (the
      default/personal-workspace path);
    * no ``requested_workspace`` + multiple → deny (ambiguous — the caller must
      name one, e.g. via the per-workspace ``/w/<id>/mcp`` URL). Fail-closed
      rather than guessing which workspace's data to expose.
    """
    active = active_workspaces_for(identity, list(memberships))
    if not active:
        raise CrossWorkspaceError(
            "identity holds no active workspace membership — access denied"
        )
    if requested_workspace is not None:
        if requested_workspace not in active:
            raise CrossWorkspaceError(
                f"identity is not an active member of workspace "
                f"{requested_workspace!r} — access denied"
            )
        return requested_workspace
    if len(active) == 1:
        return active[0]
    raise CrossWorkspaceError(
        "identity belongs to multiple workspaces and named none — select one "
        "(e.g. the per-workspace .../w/<workspace-id>/mcp URL); access denied"
    )


def resolve_workspace(
    *,
    token_present: bool,
    identity: Identity | None,
    requested: str | None,
    memberships: Iterable[Membership],
) -> str | None:
    """Reconcile the effective workspace for a request — the policy front door.

    Mirrors the shape of the legacy ``resolve_tenant`` so the stdio/OSS path is
    untouched:

    * ``token_present=False`` (stdio / local / unauthenticated) → ``requested``
      passes through unchanged (the base/self-host path never engages Model B);
    * token present → delegate to :func:`workspace_for_identity` (deny on no /
      cross membership).
    """
    if not token_present:
        return requested
    return workspace_for_identity(
        identity=identity or Identity(),
        requested_workspace=requested,
        memberships=memberships,
    )


def _clean_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None
