"""Author-time validation of an AUTHORED JSON Schema (i-080, item 4).

A ``KindDefinition`` carries the JSON Schema every instance of that Kind is
validated against. Until this module the schema was only checked to be a *dict*
(``models.KindDefinitionSpec.from_raw``); ``Draft202012Validator.check_schema``
ran exclusively on DNA's own descriptor meta-schema (``kinds/schema.py``). The
consequence was a silent deferral: a schema that is not a schema was stored
happily and then failed **per instance**, at parse time, through the fail-soft
``parse_error`` channel — a warning in a log, far from the person who wrote it.

Three checks run here, each on evidence rather than folklore:

1. **It is a schema.** ``Draft202012Validator.check_schema`` — the same
   authority DNA already applies to its own meta-schema, now applied to the
   authored one.

2. **Every ``$ref`` is a local fragment.** MEASURED on jsonschema 4.26: a remote
   ``$ref`` is NOT fetched (the ``referencing`` library resolves nothing without
   an explicit retrieve function), so this is not an SSRF *today* — but it is a
   crash, and the crash is worse than it looks. The raised
   ``_WrappedReferencingError`` is **not** a ``ValidationError``, so it sails
   straight through the write path's handler
   (``WritePipeline._validate_spec_schema`` catches ``ValidationError`` only)
   and out of the face as an unhandled error. Refusing non-local ``$ref`` at
   author time fixes the crash AND forecloses the SSRF the moment somebody
   configures a retriever for a legitimate reason.

3. **No ``pattern`` with catastrophic backtracking.** MEASURED: ``^(a+)+$``
   against 26 ``a`` and one mismatch takes ~1.5s in CPython, and every further
   character multiplies the cost — a tenant-authored regex is a denial of
   service on a shared process. :func:`redos_risk` refuses the shapes that can
   be recognised structurally.

**What the ReDoS check is and is not.** It recognises the three shapes measured
to be exponential — a group quantified unboundedly whose body (a) ends in an
unbounded quantifier, (b) can match the empty string, or (c) has two literal
alternatives one of which prefixes the other — plus a blunt length bound on
anything too large to reason about. It is NOT a proof of linearity: deciding
regex ambiguity in general is the analysis a linear-time engine (RE2) does for
you. Closing the remaining gap is a dependency decision, not a code change.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "MAX_PATTERN_LENGTH",
    "SchemaGuardError",
    "redos_risk",
    "validate_authored_schema",
]


class SchemaGuardError(ValueError):
    """An authored JSON Schema was refused at author time.

    A ``ValueError`` so every existing catch site around
    ``KindDefinitionSpec.from_raw`` — the builtin-descriptor funnel that raises
    at boot and the per-scope funnel that warns and skips — keeps its contract
    with no new wiring."""


#: A ``pattern`` longer than this is refused unanalysed. Not a claim that long
#: regexes are dangerous — a bound on what the structural check below is willing
#: to vouch for. DNA's own descriptors top out around 60 characters, so this is
#: an order of magnitude of headroom.
MAX_PATTERN_LENGTH = 512


# ---------------------------------------------------------------------------
# A minimal regex reader — enough structure to answer "is this shape known to
# backtrack catastrophically?", deliberately not a full regex parser.
# ---------------------------------------------------------------------------


class _Group:
    """A parenthesised group: a list of top-level alternation branches, each a
    list of ``(atom, quantifier)`` elements."""

    __slots__ = ("branches",)

    def __init__(self, branches: list[list[tuple[Any, str]]]) -> None:
        self.branches = branches


#: Atom kinds. ``_ZERO_WIDTH`` atoms (anchors) neither consume input nor make a
#: sequence non-nullable, so they are skipped when asking what a branch "ends
#: with".
_ZERO_WIDTH = "anchor"


def _parse_quantifier(pattern: str, i: int) -> tuple[str, int]:
    """The quantifier at ``pattern[i:]`` (``""`` if none) and the next index.

    Normalised to one of ``""`` / ``"?"`` / ``"*"`` / ``"+"`` / ``"{bounded}"``
    / ``"{unbounded}"``. A trailing ``?`` (lazy) or ``+`` (possessive) is
    consumed but does not change the shape: laziness reorders the search, it
    does not bound it."""
    if i >= len(pattern):
        return "", i
    ch = pattern[i]
    if ch in "*+?":
        i += 1
        quant = ch
    elif ch == "{":
        close = pattern.find("}", i)
        if close == -1:
            return "", i  # a literal '{' — not a quantifier
        body = pattern[i + 1:close]
        if not body or not all(c.isdigit() or c == "," for c in body):
            return "", i  # a literal '{...}' — not a quantifier
        i = close + 1
        quant = "{unbounded}" if body.endswith(",") else "{bounded}"
    else:
        return "", i
    if i < len(pattern) and pattern[i] in "?+":
        i += 1  # lazy / possessive marker — shape unchanged
    return quant, i


def _parse(pattern: str, i: int = 0, depth: int = 0) -> tuple[_Group, int]:
    """Read one group body (or the whole pattern at ``depth == 0``).

    Returns the group and the index just past its closing ``)`` (or the end of
    the pattern at depth 0)."""
    branches: list[list[tuple[Any, str]]] = [[]]
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == ")" and depth > 0:
            return _Group(branches), i + 1
        if ch == "|":
            branches.append([])
            i += 1
            continue
        atom: Any
        if ch == "\\":
            atom = ("literal", pattern[i + 1: i + 2])
            i += 2
        elif ch == "[":
            j = i + 1
            if j < n and pattern[j] == "^":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1  # a leading ']' is a literal member
            while j < n and pattern[j] != "]":
                j += 2 if pattern[j] == "\\" else 1
            atom = ("class", pattern[i:j + 1])
            i = min(j + 1, n)
        elif ch == "(":
            j = i + 1
            if pattern.startswith("(?", i):
                # (?:  (?=  (?!  (?<=  (?<!  (?P<name>  (?<name>  (?i) ...
                j = i + 2
                while j < n and pattern[j] not in ":)" and pattern[j] != "<":
                    j += 1
                if j < n and pattern[j] == "<":
                    close = pattern.find(">", j)
                    j = close + 1 if close != -1 else j + 1
                elif j < n and pattern[j] == ":":
                    j += 1
            inner, i = _parse(pattern, j, depth + 1)
            atom = ("group", inner)
        elif ch in "^$":
            atom = (_ZERO_WIDTH, ch)
            i += 1
        else:
            atom = ("literal", ch)
            i += 1
        quant, i = _parse_quantifier(pattern, i)
        branches[-1].append((atom, quant))
    return _Group(branches), i


_UNBOUNDED = {"*", "+", "{unbounded}"}
_OPTIONAL = {"*", "?", "{bounded}"}  # {bounded} may have min 0; assume it can


def _atom_nullable(atom: Any) -> bool:
    kind = atom[0]
    if kind == _ZERO_WIDTH:
        return True
    if kind == "group":
        return _group_nullable(atom[1])
    return False


def _group_nullable(group: _Group) -> bool:
    return any(
        all(quant in _OPTIONAL or _atom_nullable(atom) for atom, quant in branch)
        for branch in group.branches
    )


def _ends_with_unbounded(branch: list[tuple[Any, str]]) -> bool:
    """Whether ``branch``'s last input-consuming element is unbounded — i.e.
    nothing mandatory separates one iteration of the enclosing loop from the
    next. This is exactly what distinguishes the measured-catastrophic
    ``([a-z]+)*`` from the measured-fast ``([a-z]+\\.)+``."""
    for atom, quant in reversed(branch):
        if atom[0] == _ZERO_WIDTH:
            continue
        return quant in _UNBOUNDED
    return False


def _literal_text(branch: list[tuple[Any, str]]) -> str | None:
    """``branch`` rendered as plain text if it is a sequence of unquantified
    literals, else ``None``."""
    out = []
    for atom, quant in branch:
        if atom[0] != "literal" or quant:
            return None
        out.append(atom[1])
    return "".join(out)


def _ambiguous_alternation(group: _Group) -> bool:
    """Two literal branches where one prefixes the other — the ``(a|aa)+``
    shape, measured exponential."""
    literals = [t for t in (_literal_text(b) for b in group.branches) if t is not None]
    for i, a in enumerate(literals):
        for b in literals[i + 1:]:
            if a.startswith(b) or b.startswith(a):
                return True
    return False


def _scan(group: _Group) -> str | None:
    for branch in group.branches:
        for atom, quant in branch:
            if atom[0] != "group":
                continue
            inner: _Group = atom[1]
            if quant in _UNBOUNDED:
                if any(_ends_with_unbounded(b) for b in inner.branches):
                    return (
                        "a group with an unbounded quantifier whose body itself "
                        "ends in an unbounded quantifier — each iteration can "
                        "be split in exponentially many ways"
                    )
                if _group_nullable(inner):
                    return (
                        "a group with an unbounded quantifier whose body can "
                        "match the empty string — the loop has no progress "
                        "guarantee"
                    )
                if _ambiguous_alternation(inner):
                    return (
                        "a group with an unbounded quantifier whose alternatives "
                        "overlap (one is a prefix of another) — the same input "
                        "matches in exponentially many ways"
                    )
            found = _scan(inner)
            if found:
                return found
    return None


def redos_risk(pattern: str) -> str | None:
    """A human reason why ``pattern`` is refused, or ``None`` if it is accepted.

    **Two regimes, and which one is in force is a fact about the install.**

    With ``dna-sdk[re2]`` present, RE2 both validates and applies the pattern
    (``dna.kernel.kinds.regex_engine``): it compiles to an automaton and matches
    in time linear in the input, so there is no backtracking to be catastrophic
    and no shape to recognise. A pattern RE2 compiles is accepted — including the
    long ones and the exotic ones the heuristic below refuses because it cannot
    reason about them. What RE2 refuses (backreferences, lookaround) it refuses
    for the same reason the heuristic exists: those are the constructs whose cost
    cannot be bounded.

    Without it, the measured heuristic from #244 applies unchanged: the three
    shapes known to explode, plus a length bound on anything too large to vouch
    for. See the module docstring for exactly what that does and does not claim.

    The regimes are never mixed. Accepting a pattern because RE2 finds it linear
    and then running it on Python's backtracking ``re`` would be a safety
    certificate issued for the wrong engine — so the relaxation is gated on
    :func:`~dna.kernel.kinds.regex_engine.accepts_any_linear_pattern`, which is
    true only when the applying engine is RE2 too."""
    import re

    if not isinstance(pattern, str):
        return f"must be a string, got {type(pattern).__name__}"

    from dna.kernel.kinds.regex_engine import (
        accepts_any_linear_pattern,
        re2_rejection,
    )

    if accepts_any_linear_pattern():
        return re2_rejection(pattern)

    if len(pattern) > MAX_PATTERN_LENGTH:
        return (
            f"is {len(pattern)} characters long (limit {MAX_PATTERN_LENGTH}) — "
            f"too large for the backtracking check below to vouch for. Install "
            f"`dna-sdk[re2]` and a linear-time engine decides this instead of a "
            f"length bound"
        )
    try:
        re.compile(pattern)
    except re.error as e:
        return f"does not compile: {e}"
    group, _ = _parse(pattern)
    return _scan(group)


# ---------------------------------------------------------------------------
# The schema walk
# ---------------------------------------------------------------------------


def _check_ref(value: Any, where: str) -> None:
    if not isinstance(value, str):
        raise SchemaGuardError(
            f"$ref at {where} must be a string, got {type(value).__name__}"
        )
    if value.startswith("#"):
        return
    raise SchemaGuardError(
        f"$ref at {where} points outside this schema ({value!r}). Only local "
        f"fragments (\"#/$defs/...\") are allowed: nothing resolves a remote "
        f"reference at validation time, so every instance of this Kind would "
        f"fail with an error the write path does not even recognise as a "
        f"validation failure — and a resolver added later would turn the field "
        f"into an outbound-request surface. Inline the definition under "
        f"$defs."
    )


#: Keywords whose value IS a subschema.
_SUBSCHEMA = frozenset({
    "additionalItems", "additionalProperties", "contains", "contentSchema",
    "else", "if", "items", "not", "propertyNames", "then",
    "unevaluatedItems", "unevaluatedProperties",
})
#: Keywords whose value is a LIST of subschemas.
_SUBSCHEMA_LIST = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
#: Keywords whose value is a MAP of arbitrary NAME → subschema. The names are
#: user data (a property may legitimately be called "pattern" — DNA's own Plan
#: Kind has one), so the walk must never mistake a name for a keyword.
_SUBSCHEMA_MAP = frozenset({"$defs", "definitions", "dependentSchemas", "properties"})


def _walk(node: Any, where: str) -> None:
    """Recurse through the SCHEMA-BEARING keywords only.

    Descending blindly would read arbitrary instance data (``default``,
    ``const``, ``examples``) as schema, and — the bug this shape exists to
    avoid — would read ``properties.pattern`` (a property NAMED "pattern") as
    the ``pattern`` keyword."""
    if not isinstance(node, dict):
        return
    if "$ref" in node:
        _check_ref(node["$ref"], where or "the schema root")
    pattern = node.get("pattern")
    if pattern is not None:
        reason = redos_risk(pattern)
        if reason is not None:
            raise SchemaGuardError(
                f"pattern at {where or 'the schema root'} {reason}. Rewrite it "
                f"so each repetition consumes something mandatory (e.g. "
                f"'([a-z]+\\.)+' rather than '([a-z]+)+')."
            )
    for key, value in node.items():
        child = f"{where}.{key}" if where else key
        if key == "patternProperties" and isinstance(value, dict):
            for prop_pattern, sub in value.items():
                reason = redos_risk(prop_pattern)
                if reason is not None:
                    raise SchemaGuardError(
                        f"patternProperties key {prop_pattern!r} at {child} "
                        f"{reason}."
                    )
                _walk(sub, f"{child}[{prop_pattern!r}]")
        elif key in _SUBSCHEMA_MAP and isinstance(value, dict):
            for name, sub in value.items():
                _walk(sub, f"{child}.{name}")
        elif key in _SUBSCHEMA_LIST and isinstance(value, list):
            for i, sub in enumerate(value):
                _walk(sub, f"{child}[{i}]")
        elif key in _SUBSCHEMA:
            _walk(value, child)


def validate_authored_schema(schema: Any) -> None:
    """Refuse an authored JSON Schema that is malformed, reaches outside itself,
    or carries a regex known to backtrack catastrophically.

    ``None`` / ``{}`` is permissive — declaring no schema stays legal, exactly
    as it was before this guard existed. Raises :class:`SchemaGuardError`."""
    if not schema:
        return
    if not isinstance(schema, dict):
        raise SchemaGuardError(
            f"schema must be a JSON Schema object, got {type(schema).__name__}"
        )
    import jsonschema  # core dep (pyproject: jsonschema>=4.0)

    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.exceptions.SchemaError as e:
        path = "".join(
            f"[{p}]" if isinstance(p, int) else f".{p}" for p in e.absolute_path
        )
        raise SchemaGuardError(
            f"is not a valid JSON Schema (draft 2020-12) at "
            f"$schema{path}: {e.message}"
        ) from e
    _walk(schema, "")
