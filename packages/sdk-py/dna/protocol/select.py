"""``select`` — the projection **contract** (spec §6.2 rule 1).

    *"A server that cannot honour the requested projection MUST answer
    ``-32602``. It MUST NOT return a narrower shape while echoing the
    request."*

⚠️ **The defect this corrects is in this repo, and it is still there.** DNA's
list surfaces take ``fields=[…]`` and echo it back as ``projected``. The
projector (:func:`dna.kernel.protocols._project_doc` →
``_resolve_field_path``) resolves a path by splitting on ``.`` and implicitly
prefixing an unprefixed one with ``spec.`` — so the *bare* path ``"spec"``
becomes ``spec.spec``, resolves to ``None``, and is dropped without a word.
Measured::

    _project_doc(doc, ["spec"])       -> {"name": "i-1"}                  # spec GONE
    _project_doc(doc, ["spec.title"]) -> {"name": "i-1", "spec": {…}}     # honoured

and the caller still receives ``"projected": ["spec"]``. That is precisely
"a narrower shape while echoing the request", and it is why ``select`` gets its
own module instead of being a pass-through parameter.

**The refusal is static, and that is deliberate.** Every path is checked
against the forms the projector actually honours *before* the store is
touched, so an unhonourable projection costs a client one round trip and no
read — and, more importantly, so the refusal cannot depend on whether some row
happened to carry the field. A path that is honoured but absent from a given
instance is a legitimately absent value; a path the projector cannot express is
a broken contract. Only the second is ``-32602``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from dna.protocol.errors import DnapError

__all__ = ["SELECT_FULL", "SELECT_NAMES", "Selection", "parse_select"]

SELECT_NAMES = "names"
SELECT_FULL = "full"

#: Envelope members the projector emits flat (``_project_doc``'s own branch).
_ENVELOPE_PATHS = frozenset({"name", "kind", "apiVersion"})

#: The two spellings of "the instance's name". Either one asked for keeps the
#: projector's injected ``name`` in the row; neither strips it.
_IDENTITY_PATHS = frozenset({"name", "metadata.name"})

#: Prefixes the projector walks literally. Anything else with no dot is
#: implicitly ``spec.<path>``.
_WALKABLE_PREFIXES = ("spec.", "metadata.")

#: The paths that LOOK addressable and are silently dropped — the measured
#: defect above. Named explicitly so the refusal can explain itself instead of
#: reading as a style rule.
_SILENTLY_DROPPED = {
    "spec": (
        "the projector implicitly prefixes an unprefixed path with 'spec.', so "
        "a bare 'spec' resolves as 'spec.spec' and is dropped without an error"
    ),
    "metadata": (
        "'metadata' is a container, not a leaf the projector can resolve; it "
        "resolves to None and is dropped without an error"
    ),
}


@dataclass(frozen=True, slots=True)
class Selection:
    """A validated ``select``."""

    mode: Literal["names", "full", "paths"]
    paths: tuple[str, ...] = ()

    @property
    def echo(self) -> str | list[str]:
        """What the result reports as ``selected`` — always what was asked for,
        because anything narrower would have been refused."""
        return list(self.paths) if self.mode == "paths" else self.mode

    def shape(self, rows: list[dict[str, Any]]) -> list[Any]:
        """⭐ §6.2 rule 5 — the RESULT shape of each ``select``, enforced here.

        ``"names"`` → **plain strings**. *"Not one-member documents: a
        document-shaped object carrying only a name is exactly the narrower
        shape rule 1 forbids, wearing a disguise."*

        a path list → **exactly** the requested paths, nothing added. ⚠️ The
        projector underneath always injects ``name`` into every projected row
        (``_project_doc``, ``dna/kernel/protocols.py``), which is the helpful
        behaviour the rule names: *"A server that helpfully attaches identity
        and one that does not return different rows for the same request; ask
        for `metadata.name` when you want it."* So identity is stripped back
        out unless it was asked for. This is the one place the cola reshapes
        what the implementation returned, and it does so to make the request
        the contract rather than a suggestion.

        ``"full"`` rows are shaped by the caller (they need the revision).
        """
        if self.mode == "names":
            return [r.get("name") for r in rows if isinstance(r, dict)]
        if self.mode != "paths":
            return list(rows)
        wants_name = bool(_IDENTITY_PATHS & set(self.paths))
        out: list[Any] = []
        for row in rows:
            trimmed = dict(row)
            if not wants_name:
                trimmed.pop("name", None)
            out.append(trimmed)
        return out

    @property
    def fingerprint(self) -> str:
        """A stable key for "this listing asked for this shape".

        Carried inside the cursor so a page-2 request that changes ``select``
        mid-listing is caught rather than served: the pages of one listing
        belong to one snapshot AND one shape.
        """
        return self.mode if self.mode != "paths" else "paths:" + "|".join(self.paths)


def parse_select(raw: object) -> Selection:
    """Validate ``select``, or raise ``-32602``.

    Absent → :data:`SELECT_NAMES`. Names-only is the cheapest answer and the
    historical default of the implementation underneath; defaulting to ``full``
    would make an unstated parameter the expensive one.
    """
    if raw is None:
        return Selection(mode="names")
    if isinstance(raw, str):
        if raw == SELECT_NAMES:
            return Selection(mode="names")
        if raw == SELECT_FULL:
            return Selection(mode="full")
        raise DnapError.invalid_params(
            f"`select` must be {SELECT_NAMES!r}, {SELECT_FULL!r}, or an array "
            f"of field paths — got {raw!r}",
            select=raw,
        )
    if isinstance(raw, list):
        if not raw:
            raise DnapError.invalid_params(
                "`select` as an array must name at least one field path; use "
                f"{SELECT_NAMES!r} to ask for names only",
                select=raw,
            )
        paths: list[str] = []
        for item in raw:
            if not isinstance(item, str) or not item:
                raise DnapError.invalid_params(
                    "every entry of a `select` array must be a non-empty "
                    f"field path string — got {item!r}",
                    select=raw,
                )
            _require_honourable(item, raw)
            paths.append(item)
        return Selection(mode="paths", paths=tuple(paths))
    raise DnapError.invalid_params(
        f"`select` must be a string or an array of field paths, got "
        f"{type(raw).__name__}",
        select=raw,
    )


def _require_honourable(path: str, whole: list[Any]) -> None:
    """Refuse a path the projector cannot express — rule 1, enforced."""
    if path in _ENVELOPE_PATHS:
        return
    if path in _SILENTLY_DROPPED:
        raise DnapError(
            -32602,
            f"`select` cannot honour the path {path!r}: "
            f"{_SILENTLY_DROPPED[path]}. Ask for {SELECT_FULL!r} to get the "
            f"whole instance, or name leaf paths such as '{path}.<field>'. "
            f"Refusing rather than returning a narrower shape while echoing "
            f"your request.",
            select=list(whole), path=path, rule="projection-unhonourable",
        )
    if any(seg == "" for seg in path.split(".")):
        raise DnapError.invalid_params(
            f"`select` path {path!r} has an empty segment",
            select=list(whole), path=path,
        )
    if path.startswith(_WALKABLE_PREFIXES) or "." not in path:
        # 'spec.a.b' / 'metadata.x' walk literally; a dotless path is
        # implicitly 'spec.<path>' — both are forms the projector resolves.
        return
    raise DnapError(
        -32602,
        f"`select` cannot honour the path {path!r}: the projector resolves "
        f"only envelope members ({', '.join(sorted(_ENVELOPE_PATHS))}), "
        f"'spec.…', 'metadata.…', and unprefixed leaves (read as 'spec.…'). "
        f"A dotted path under any other root resolves to nothing and would be "
        f"dropped silently.",
        select=list(whole), path=path, rule="projection-unhonourable",
    )
