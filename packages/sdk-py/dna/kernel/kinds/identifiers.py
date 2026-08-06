"""``spec.identifiers`` — a field's way of saying **I am not a reference**.

The other half of ``spec.relations``, and the half that makes the gap list
finite. ``kind_graph`` reports a field whose NAME ends in ``_id``/``_ref``/
``_slug`` and which no relation declares, as an ``undeclared`` gap: *somebody
should look*. That is an honest invitation and it had no way of being
ANSWERED — so on 06/08/2026 the list held 21 rows and every one of them was
permanent, because a Kind could say where a field points and could not say that
it points nowhere.

Two thirds of that list are not references at all, and they are not references
for two DIFFERENT reasons:

* ``Sprint.sprint_id``, ``Role.role_id``, ``Workspace.workspace_id``,
  ``AgentSession.session_id``, ``ModelProfile.model_id``,
  ``PricingPlan.tier_id`` — the instance's OWN key. It does not point at
  another instance; it names THIS one. Pointing it at its own Kind would be a
  self-loop that says nothing.
* ``AgentGrant.client_id``, ``PlanBinding.stripe_customer_id``,
  ``UserProfile.user_id``, ``WorkspaceMembership.identity_oid`` — an
  identifier minted by a system OUTSIDE DNA. There is no Kind to point at,
  today or ever, and the useful fact is WHICH system minted it.

Why this is not the denylist coming back
----------------------------------------
``kind_graph``'s docstring retired a suppression table and said why: *"a
suppression table is the shape of a mechanism that should not be producing the
thing being suppressed."* That argument is about a mechanism CLAIMING something
false — the name-shape guess drew ``KindDefinition.docs → Doc`` as an edge, and
the denylist existed to unsay it. Three differences make this the opposite
move:

1. **It suppresses no claim.** The gap row asserts nothing about a target; it
   asks a question. This is the ANSWER, not a gag.
2. **It lives on the Kind, not in the kernel.** The old denylist was a central
   table of other people's fields, maintained by whoever noticed. This is the
   Kind speaking about its own field, in its own file, next to the schema — so
   it cannot go stale against a Kind it no longer describes, which is exactly
   how ``UNDECLARABLE`` came to cite a Kind called ``Tier``.
3. **It carries the reason, and the reason is machine-readable.** ``role`` and
   ``system`` are data a screen can rank and group. "Suppressed" was not.

The vocabulary — two keys, one of them conditional
--------------------------------------------------
``role`` (REQUIRED, closed: :data:`ROLES`)
    ``self`` — the field holds THIS instance's own key.
    ``external`` — the field holds an identifier minted outside DNA.

    Closed, and only two, for the reason ``cardinality`` has only two words: a
    third role would be describing a validation rule, and the JSON Schema next
    door owns those.

    **The tie-break, because both can be true at once.**
    ``UserRoleAssignment.user_id`` is minted by the identity provider AND is
    the doc's own name; ``Workspace.account_id`` is minted by the identity
    provider and is not. The question is always *"is it THIS instance's key?"*
    — yes ⇒ ``self``, regardless of who minted the value; no ⇒ ``external``,
    and then ``system`` records who did. Written down here rather than
    discovered per field, because a rule that lives only in the reviewer's head
    is how two Kinds start classifying the same shape differently.

``system`` (REQUIRED for ``external``, FORBIDDEN for ``self``)
    Who mints it — ``stripe``, ``oauth``, ``entra``, ``workos``. Free text on
    purpose: the set of systems a deployment integrates with is open, and a
    closed enum here would be this package deciding which SaaS a tenant may
    use. Required, because "some other system" is the part a reader already
    guessed from the field name; WHICH one is the part worth writing down.

    Forbidden on ``self`` rather than ignored: a ``system`` beside ``role:
    self`` means the author believes the key comes from somewhere, and silently
    dropping it would leave that belief in the file, unread and wrong.

The search, including the nothing
---------------------------------
*Already installed:* nothing to adopt. ``jsonschema`` has no notion of a
primary key or of an external identifier (``$id`` identifies the SCHEMA, not an
instance field). ``pydantic`` has no key concept. ``sqlalchemy`` has
``primary_key=True``, which is the ``self`` role's precedent and not a component
we can use — the SDK builds ``sa.Table`` by hand and no Kind maps to a table.

*Designs borrowed, with the reason:* LinkML's ``identifier: true`` is exactly
``role: self`` — a slot flagged as the instance's own key rather than a link —
and this package already borrowed LinkML's slot vocabulary for ``relations``,
so the pairing is deliberate rather than coincidental. FHIR's ``Identifier``
datatype supplies the ``external`` half: its ``system`` (the namespace that
minted the value) plus ``value`` is the identical modelling problem, solved by
naming the minting authority rather than by resolving anything. Neither is
being implemented; both are being cited for the SHAPE.

*Not adopted, and why:* JSON Schema's ``$id``/``$anchor`` (identity of the
schema document, a different noun); OpenAPI ``x-`` extensions (that is where
``x-dna-ref`` lived, and moving a model out of schema annotations is the whole
reason ``relations`` exists); a central registry of "known external id
prefixes" (the hand-kept table this file's design argues against).

What this deliberately does NOT do
----------------------------------
It does not validate the VALUE. A ``stripe_customer_id`` that is empty, or
shaped wrong, or belonging to another account, is the JSON Schema's business
(``pattern``, ``minLength``) or the integration's. This block answers exactly
one question — *does this field point at another instance?* — and answering
one question well is what keeps it from becoming the fourth mechanism the
``relations`` docstring spent itself retiring.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

__all__ = [
    "ROLES",
    "ROLE_EXTERNAL",
    "ROLE_SELF",
    "Identifier",
    "identifiers_of",
    "normalize_identifiers",
    "schema_contradictions",
]

#: The field holds THIS instance's own key — it names the instance, it does not
#: point at another one.
ROLE_SELF = "self"

#: The field holds an identifier minted OUTSIDE DNA. There is no Kind to point
#: at; ``system`` says who mints it.
ROLE_EXTERNAL = "external"

#: The closed role vocabulary. Two, for the reason ``CARDINALITIES`` has two.
ROLES: tuple[str, ...] = (ROLE_SELF, ROLE_EXTERNAL)

_IDENTIFIER_KEYS = frozenset({"role", "system"})
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Identifier:
    """ONE declared identifier — a field stating that it is not a pointer.

    Frozen for the reason :class:`~dna.kernel.kinds.relations.Relation` is: the
    normalized declaration is shared by every reader of the Kind."""

    #: The field name, which IS the spec field this describes.
    name: str
    #: :data:`ROLE_SELF` | :data:`ROLE_EXTERNAL`.
    role: str
    #: Who mints the value — set only for :data:`ROLE_EXTERNAL`.
    system: str | None = None

    @property
    def is_external(self) -> bool:
        return self.role == ROLE_EXTERNAL

    def to_declaration(self) -> dict[str, Any]:
        """The AUTHORING shape — what an instance stores back in
        ``spec.identifiers[name]``, and what the meta-schema validates. Omits
        what was never declared, exactly as ``Relation.to_declaration`` does."""
        out: dict[str, Any] = {"role": self.role}
        if self.system:
            out["system"] = self.system
        return out

    def to_wire(self) -> dict[str, Any]:
        """The wire shape, every key present (``null`` where undeclared) — a
        stable key set is what lets a consumer type it without probing."""
        return {"field": self.name, "role": self.role, "system": self.system}


def _identifier(name: Any, raw: Any) -> Identifier:
    if not isinstance(name, str) or not _NAME_RE.match(name.strip()):
        raise ValueError(
            f"identifiers key {name!r} is not a spec field name — an identifier "
            "is named by the field it describes"
        )
    name = name.strip()
    if not isinstance(raw, Mapping):
        raise ValueError(
            f"identifiers[{name!r}] must be a {{role, system}} mapping, got "
            f"{type(raw).__name__}. There is no shorthand: `role` is required "
            "precisely because 'not a reference' has two different reasons"
        )
    unknown = sorted(set(raw) - _IDENTIFIER_KEYS)
    if unknown:
        raise ValueError(
            f"identifiers[{name!r}] has unknown key(s) {unknown} — the "
            f"vocabulary is {sorted(_IDENTIFIER_KEYS)} and is deliberately "
            "closed. A key describing how the value is VALIDATED (pattern, "
            "minLength) belongs in the JSON Schema, which keeps the data"
        )
    role = raw.get("role")
    if role not in ROLES:
        raise ValueError(
            f"identifiers[{name!r}].role must be one of {list(ROLES)}, got "
            f"{role!r}. `self` = this instance's own key; `external` = minted "
            "by a system outside DNA"
        )
    system = raw.get("system")
    if role == ROLE_EXTERNAL:
        if not isinstance(system, str) or not system.strip():
            raise ValueError(
                f"identifiers[{name!r}] is `external` and needs a `system` — "
                "which authority mints it (`stripe`, `oauth`, `entra`). That "
                "the value comes from somewhere else is already legible in the "
                "field name; WHICH somewhere is the part worth declaring"
            )
        system = system.strip()
    else:
        if system is not None:
            raise ValueError(
                f"identifiers[{name!r}] is `{ROLE_SELF}` and declares "
                f"system={system!r}. An instance's own key is minted by this "
                "runtime, so naming an authority for it is a belief about the "
                "data that nothing can honour — and dropping it silently would "
                "leave that belief in the file, unread and wrong"
            )
    return Identifier(name=name, role=role, system=system)


def normalize_identifiers(raw: Any) -> dict[str, Identifier] | None:
    """Validate + normalize a declared ``identifiers`` block.

    ``None`` in, ``None`` out; an empty mapping normalizes to ``None`` as well
    — declaring no identifiers and declaring an empty set of them are the same
    statement, and two representations of one statement is one too many.

    Raises ``ValueError`` — fail LOUD, at load time, for the reason
    ``normalize_relations`` fails loud: a declaration that only breaks when
    something reads it breaks far from the author who could fix it."""
    if raw is None:
        return None
    if isinstance(raw, Mapping) and raw and all(
        isinstance(v, Identifier) for v in raw.values()
    ):
        return dict(raw)
    if not isinstance(raw, Mapping):
        raise ValueError(
            "identifiers must be a mapping of field name → {role, system}, got "
            f"{type(raw).__name__}"
        )
    if not raw:
        return None
    out = {
        ident.name: ident
        for ident in (_identifier(name, spec) for name, spec in raw.items())
    }
    return dict(sorted(out.items()))


def identifiers_of(kp: Any) -> dict[str, Identifier]:
    """The Kind's declared identifiers, keyed by field — ``{}`` when it
    declares none.

    Typed access with a default, never ``hasattr`` — the convention every
    optional port member follows, and fail-SOFT on a malformed attribute for
    the reason ``relations_of`` is: loading is where a bad declaration is
    refused, and refusing again in front of a reader would turn an authoring
    error into an outage."""
    if kp is None:
        return {}
    try:
        return normalize_identifiers(getattr(kp, "identifiers", None)) or {}
    except Exception:  # noqa: BLE001 — see the docstring
        return {}


def schema_contradictions(
    identifiers: Mapping[str, Identifier] | None,
    relations: Mapping[str, Any] | None,
    schema: Any,
    *, partial: bool = False,
) -> list[str]:
    """Where a Kind's ``identifiers`` and the rest of its declaration disagree.

    Two contradictions, and the second is the one worth having:

    * an identifier names a field the schema does not declare — the value has
      nowhere to live (suppressed under ``partial``, for the ``schema_fragments``
      reason ``relations.schema_contradictions`` documents);
    * **a field is declared BOTH a relation and an identifier** — "it points at
      Story" and "it points nowhere" cannot both be true, and a registry that
      let them coexist would be back to two mechanisms answering one question,
      which is the disease this whole area was written to cure.

    Returns messages rather than raising, so one caller can refuse a descriptor
    and another can report a registry-wide list."""
    if not identifiers:
        return []
    out: list[str] = []
    for name in sorted(identifiers):
        if relations and name in relations:
            out.append(
                f"`{name}` is declared BOTH a relation and an identifier — one "
                "says it points at another instance, the other says it points "
                "nowhere. Exactly one of them is true"
            )
    props = schema.get("properties") if isinstance(schema, Mapping) else None
    if not isinstance(props, Mapping) or partial:
        return out
    for name in sorted(identifiers):
        if not isinstance(props.get(name), Mapping):
            out.append(
                f"identifiers[{name!r}] has no `{name}` property in the schema "
                "— an identifier is named by the spec field it describes"
            )
    return out
