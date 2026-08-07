"""``spec.presentation`` — how a Kind's data READS, declared once.

A Kind used to be described twice: once for a screen, once for a card. The two
runtimes cannot be unified and should not be — a screen is a component tree in
someone's framework, a card is declarative JSON rendered inside a sandboxed
iframe wearing a foreign host's theme. What they genuinely share is not the
framework. It is **what the data means**: which fields a human reads, in what
order, what to call them, which one NAMES the instance, which one is its STATE,
and which ones are machinery nobody should be shown.

So this module holds a vocabulary of MEANING, and deliberately not a layout
language. There is no column here, no width, no section, no colour, no variant
and no widget — and an unknown key is refused rather than tolerated, so none of
those can arrive later as a de-facto extension. A schema that described how a
card looks would be wrong for the first surface that adopted it afterwards; the
Kind says what a field IS and every surface decides for itself what that
becomes on it. A table turns ``role: status`` into a column, a detail screen
into a state line, a card may turn it into a badge — none of that is declared
here, and none of it is this module's business.

**The line, stated so it can be held.** On the KIND: the reading ORDER, the
human LABEL, the semantic ROLE, and which fields are HIDDEN. Those are facts
about the data, true on every surface. On the SURFACE: how many of the declared
fields fit, what a role renders as, sorting, search, pagination, grouping,
colour. A declaration that starts answering the second list has crossed the
line.

**Tenant-authored Kinds are first-class.** The identical block is a first-class
field of ``KindDefinition`` (``spec.presentation``, in both copies of
``kind-definition.schema.json``), normalized by the identical function here and
landing on the identical port attribute. A presentation only a builtin
extension could declare would make every tenant Kind second-class and the
feature would serve nobody but its author.

Typed home: ``KindPresentation.presentation`` in ``dna.kernel.protocols`` —
optional, capability-only, and never on the runtime_checkable ``KindPort``
(the ``is_runtime_artifact`` precedent: a member there becomes REQUIRED by the
H1 isinstance gate).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "PRESENTATION_ROLES",
    "SINGULAR_ROLES",
    "PresentationField",
    "Presentation",
    "derive_label",
    "normalize_presentation",
    "presentation_of",
    "presentation_wire",
    "project_row",
]

#: The CLOSED role vocabulary. Closed because an open one would let every
#: surface guess at a word nobody defined, and the guesses would differ; small
#: because a large one is speculation about surfaces that do not exist yet.
#: Every role below is evidenced by a field a Kind in this repo already carries
#: — the ones that named the columns of the hand-written cards, plus the ones
#: the existing ``summary`` projections already single out.
#:
#: Each says what the VALUE MEANS, never what to paint:
#:
#: * ``identifier`` — the stable handle a human uses to name this instance to
#:   another human (``metadata.name`` on nearly every Kind).
#: * ``title`` — the headline; what the instance is called in prose.
#: * ``subtitle`` — one line elaborating the title.
#: * ``status`` — the instance's own lifecycle state (an OPEN value vocabulary:
#:   any workflow defines its own words, which is exactly why no colour map
#:   belongs anywhere near this module).
#: * ``owner`` — the actor responsible for it.
#: * ``parent`` — the instance this one belongs to.
#: * ``rank`` — relative importance or ordering among siblings.
#: * ``tag`` — free-form categorical labels.
#: * ``timestamp`` — a moment in time.
#: * ``metric`` — a measured quantity.
#: * ``body`` — long prose; not a cell, and a compact surface may say so.
PRESENTATION_ROLES: frozenset[str] = frozenset({
    "identifier",
    "title",
    "subtitle",
    "status",
    "owner",
    "parent",
    "rank",
    "tag",
    "timestamp",
    "metric",
    "body",
})

#: An instance has one name, one headline, one subtitle and one state. Two
#: fields claiming ``status`` is a DECLARATION error — refusing it here is
#: cheaper than making every surface invent a tie-break, and a tie-break
#: invented twice is two different answers.
SINGULAR_ROLES: tuple[str, ...] = ("identifier", "title", "subtitle", "status")

#: The instance's envelope identity. It is not a ``spec`` field on any Kind,
#: and every list surface in this repo already reads it from ``metadata.name``
#: — so a presentation entry naming it resolves there rather than looking for a
#: spec key that never exists.
ENVELOPE_NAME_FIELD = "name"

_ENTRY_KEYS = frozenset({"field", "label", "role"})
_TOP_KEYS = frozenset({"fields", "hidden"})


def derive_label(field: str) -> str:
    """The human label for a field that declared none.

    Deterministic and overridable: ``spec_refs`` → ``Spec refs``. This exists
    so a tenant who declares only field NAMES still gets a usable surface —
    the alternative is a card that prints raw snake_case at a person, which is
    the machine's vocabulary leaking into the product."""
    words = str(field).replace("-", "_").split("_")
    joined = " ".join(w for w in words if w)
    return joined[:1].upper() + joined[1:] if joined else str(field)


@dataclass(frozen=True)
class PresentationField:
    """One field, and what it MEANS. Frozen: a normalized declaration is shared
    by every surface that reads the Kind, and one of them mutating it would
    change what the others see."""

    field: str
    label: str
    role: str | None = None

    def to_wire(self) -> dict[str, Any]:
        """The wire shape, with ``role`` always present (``null`` when
        undeclared) — a stable key set is what lets a second consumer type it
        without probing."""
        return {"field": self.field, "label": self.label, "role": self.role}


@dataclass(frozen=True)
class Presentation:
    """A Kind's declared reading: an ORDERED field list plus the machinery to
    keep out of a human's way."""

    fields: tuple[PresentationField, ...] = ()
    hidden: frozenset[str] = frozenset()

    def field_with_role(self, role: str) -> PresentationField | None:
        """The field declared with ``role``, or ``None``. Meaningful for the
        :data:`SINGULAR_ROLES`; for a repeatable role it returns the first."""
        for f in self.fields:
            if f.role == role:
                return f
        return None

    def field_names(self) -> tuple[str, ...]:
        return tuple(f.field for f in self.fields)

    def to_declaration(self) -> dict[str, Any]:
        """The AUTHORING shape — what gets stored back in an instance's
        ``spec.presentation``, and what ``kind-definition.schema.json``
        validates.

        Not the same thing as :meth:`to_wire`, deliberately. The wire form is
        for a consumer and keeps every key present (a stable shape is easier to
        type against); the stored form is a DECLARATION and omits what was
        never declared — a ``"role": null`` would fail the schema's own role
        enum, and an empty ``hidden`` stored as ``[]`` would read as a
        deliberate "hide nothing" rather than as silence."""
        fields: list[dict[str, Any]] = []
        for f in self.fields:
            entry: dict[str, Any] = {"field": f.field, "label": f.label}
            if f.role is not None:
                entry["role"] = f.role
            fields.append(entry)
        out: dict[str, Any] = {"fields": fields}
        if self.hidden:
            out["hidden"] = sorted(self.hidden)
        return out

    def to_wire(
        self, *, label: str | None = None, icon: str | None = None,
    ) -> dict[str, Any]:
        """The single envelope both consumers read.

        ``label`` and ``icon`` are the two presentation attributes the protocol
        ALREADY carried (``display_label`` / ``ascii_icon``), composed in here
        rather than left as a third and fourth thing to fetch — a surface asks
        "how does this Kind read?" once.

        ``hidden`` travels SORTED: it has no reading order, and a deterministic
        wire is worth more than an authored sequence nobody consumes."""
        return {
            "label": label,
            "icon": icon,
            "fields": [f.to_wire() for f in self.fields],
            "hidden": sorted(self.hidden),
        }


def _entry(raw: Any, *, seen: set[str], singular: dict[str, str]) -> PresentationField:
    if isinstance(raw, str):
        raw = {"field": raw}
    if not isinstance(raw, dict):
        raise ValueError(
            "presentation.fields entries must be a field name or a "
            f"{{field, label, role}} mapping, got {type(raw).__name__}"
        )
    unknown = sorted(set(raw) - _ENTRY_KEYS)
    if unknown:
        raise ValueError(
            f"presentation.fields entry has unknown key(s) {unknown} — the "
            "vocabulary is {field, label, role} and is deliberately closed: it "
            "declares what a field MEANS, never how a surface paints it"
        )
    name = raw.get("field")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(
            f"presentation.fields entry needs a non-empty `field`, got {name!r}"
        )
    name = name.strip()
    if name in seen:
        raise ValueError(
            f"presentation.fields declares {name!r} twice — a field has one "
            "place in the reading order"
        )
    seen.add(name)
    role = raw.get("role")
    if role is not None:
        if not isinstance(role, str) or role not in PRESENTATION_ROLES:
            raise ValueError(
                f"presentation.fields[{name!r}].role {role!r} is not one of the "
                f"declared roles {sorted(PRESENTATION_ROLES)} — the vocabulary "
                "is closed so that every surface reads the same word the same way"
            )
        if role in SINGULAR_ROLES:
            if role in singular:
                raise ValueError(
                    f"presentation.fields declares role {role!r} on both "
                    f"{singular[role]!r} and {name!r} — an instance has one "
                    f"{role}, and a surface must not have to break the tie"
                )
            singular[role] = name
    label = raw.get("label")
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise ValueError(
            f"presentation.fields[{name!r}].label must be a non-empty string, "
            f"got {label!r}"
        )
    return PresentationField(
        field=name,
        label=label.strip() if isinstance(label, str) else derive_label(name),
        role=role,
    )


def normalize_presentation(raw: Any) -> Presentation | None:
    """Validate + normalize a declared presentation. ``None`` in, ``None`` out.

    Accepts the bare-list shorthand (``presentation: [name, title, status]``)
    for the same reason ``spec.summary`` accepts one: the common case is a
    field order, and making a tenant write a mapping for it buys nothing.

    Raises ``ValueError`` — fail LOUD, at load time. A presentation that only
    breaks when a card renders it breaks in front of a user, on a surface with
    no way to say what was wrong with the declaration."""
    if raw is None:
        return None
    if isinstance(raw, Presentation):
        return raw
    if isinstance(raw, (list, tuple)):
        raw = {"fields": list(raw)}
    if not isinstance(raw, dict):
        raise ValueError(
            "presentation must be a list of field names or a "
            f"{{fields, hidden}} mapping, got {type(raw).__name__}"
        )
    unknown = sorted(set(raw) - _TOP_KEYS)
    if unknown:
        raise ValueError(
            f"presentation has unknown key(s) {unknown} — the vocabulary is "
            "{fields, hidden}. A key that describes a LAYOUT (sections, "
            "columns, widths) does not belong on the Kind: the Kind says what "
            "its data means, each surface decides what that looks like"
        )
    fields_raw = raw.get("fields")
    if fields_raw is None:
        fields_raw = []
    if not isinstance(fields_raw, (list, tuple)):
        raise ValueError(
            "presentation.fields must be an ORDERED list — the order IS the "
            f"declaration, got {type(fields_raw).__name__}"
        )
    seen: set[str] = set()
    singular: dict[str, str] = {}
    fields = tuple(_entry(e, seen=seen, singular=singular) for e in fields_raw)
    hidden_raw = raw.get("hidden") or []
    if not isinstance(hidden_raw, (list, tuple)) or not all(
        isinstance(h, str) and h.strip() for h in hidden_raw
    ):
        raise ValueError(
            "presentation.hidden must be a list of spec field names, got "
            f"{hidden_raw!r}"
        )
    hidden = frozenset(h.strip() for h in hidden_raw)
    both = sorted(hidden & seen)
    if both:
        raise ValueError(
            f"presentation declares {both} as both shown and hidden — the two "
            "statements contradict each other and there is no reading that "
            "satisfies both"
        )
    return Presentation(fields=fields, hidden=hidden)


def presentation_of(kp: Any) -> Presentation | None:
    """The Kind's declared presentation, or ``None``.

    Typed access with a default, never ``hasattr`` — the convention every other
    ``KindPresentation`` member follows. ``None`` is MEANINGFUL: the Kind
    declares no reading and the surface falls back to its own generic
    rendering, which is not the same thing as declaring an empty one."""
    return normalize_presentation(getattr(kp, "presentation", None))


def presentation_wire(kp: Any) -> dict[str, Any] | None:
    """The wire envelope for ``kp``, or ``None`` when it declares no
    presentation.

    Composes the declared reading with the two presentation attributes the
    protocol already carried, read off the SAME port — so a surface that
    renders a Kind's roster gets its label, its glyph and its fields from one
    place and cannot end up showing a heading from one Kind and columns from
    another."""
    p = presentation_of(kp)
    if p is None:
        return None
    label = getattr(kp, "display_label", None)
    icon = getattr(kp, "ascii_icon", None)
    return p.to_wire(
        label=label if isinstance(label, str) and label else None,
        icon=icon if isinstance(icon, str) and icon else None,
    )


def project_row(
    p: Presentation, *, name: Any, spec: dict[str, Any] | None,
) -> dict[str, Any]:
    """One instance, projected to exactly the fields the KIND declares.

    ``name`` resolves from the envelope (see :data:`ENVELOPE_NAME_FIELD`);
    every other entry resolves under ``spec``. A field the instance does not
    carry projects as ``None`` — absent is REPORTED, never invented, and the
    surface decides how to print nothing."""
    src = spec if isinstance(spec, dict) else {}
    return {
        f.field: (name if f.field == ENVELOPE_NAME_FIELD else src.get(f.field))
        for f in p.fields
    }
