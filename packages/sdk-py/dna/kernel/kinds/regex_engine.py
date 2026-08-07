"""The regex engine authored patterns are validated AND applied with.

#244 shipped a *measured* ReDoS refusal: a hand-written reader that recognises
the three shapes measured to explode (``(a+)+``, a nullable loop body, an
ambiguous alternation) plus a blunt length bound on anything too large to reason
about. It closed what it could see. It said so, in its own docstring: "It is NOT
a proof of linearity: deciding regex ambiguity in general is the analysis a
linear-time engine (RE2) does for you."

This module does that. RE2 compiles a pattern to an automaton and matches in time
linear in the input — there is no backtracking to be catastrophic. When it is
present, a pattern it compiles is SAFE, full stop, and the heuristic's guesses
(including the length bound) become unnecessary.

**Why an optional extra rather than a core dependency.** ``google-re2`` ships
binary wheels for CPython 3.10–3.14 on macOS 13/14/15 (arm64 + x86_64), Windows
(win32/amd64/arm64) and **manylinux_2_28** (x86_64 + aarch64). Two real gaps
follow from that list:

* **no musllinux wheels** — an Alpine-based image, which is a normal way to ship
  a Python service, would have to build from source;
* **glibc ≥ 2.28** — no manylinux_2_17, so an older LTS base image is also a
  source build;

and a source build needs the RE2 C++ library *and* Abseil present at build time.
Making it a hard dependency would turn `pip install dna-sdk` from "always works"
into "works unless", on platforms that have nothing to do with regex safety. So
it is `dna-sdk[re2]`, and its ABSENCE is not silent:

**The two halves must agree.** RE2 may only be the acceptance authority if RE2 is
also the engine that APPLIES the pattern. Accepting a pattern because RE2 finds
it linear and then handing it to Python's backtracking ``re`` at write time would
be worse than the heuristic — it would issue a safety certificate for the wrong
engine. So :func:`accepts_any_linear_pattern` is true only when this module can
guarantee BOTH, and :func:`validate_instance` is what the write path calls, which
routes ``pattern`` / ``patternProperties`` through RE2 whenever it is available.

Without the extra, everything falls back to #244's heuristic and Python's ``re``,
unchanged — a working, honest, slightly conservative system, exactly as shipped.
"""
from __future__ import annotations

import functools
from typing import Any

__all__ = [
    "ENGINE_HEURISTIC",
    "ENGINE_RE2",
    "accepts_any_linear_pattern",
    "engine_name",
    "linear_time_validator_class",
    "re2_module",
    "re2_rejection",
    "validate_instance",
]

ENGINE_RE2 = "google-re2"
ENGINE_HEURISTIC = "python-re+heuristic"


@functools.lru_cache(maxsize=1)
def re2_module() -> Any | None:
    """The ``re2`` module, or ``None`` when the extra is not installed.

    Cached: the import is attempted once per process. A failed import stays
    failed — a mid-process ``pip install`` is not a scenario worth a retry on
    every pattern."""
    try:
        import re2  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 — an unimportable extra is simply absent
        return None
    return re2


def accepts_any_linear_pattern() -> bool:
    """Whether a linear-time engine both VALIDATES and APPLIES patterns here.

    The single predicate the schema guard consults before relaxing. False keeps
    #244's heuristic in force, which is the correct answer when the engine that
    will run the pattern can still backtrack."""
    return re2_module() is not None


def engine_name() -> str:
    """Which engine is in force — reportable, so an operator can see it."""
    return ENGINE_RE2 if accepts_any_linear_pattern() else ENGINE_HEURISTIC


def re2_rejection(pattern: str) -> str | None:
    """Why RE2 refuses to compile ``pattern``, or ``None`` if it compiles.

    RE2 rejects a small set of constructs it cannot execute in linear time —
    backreferences and lookaround, chiefly. That is not RE2 being fussy: those
    are exactly the features whose cost cannot be bounded, so a rejection here
    is the same refusal the heuristic was reaching for, made by an engine that
    can actually decide it.

    Returns ``None`` when RE2 is absent — this function answers only for RE2;
    the caller decides what silence means."""
    re2 = re2_module()
    if re2 is None:
        return None
    try:
        re2.compile(pattern)
    except Exception as exc:  # noqa: BLE001 — re2.error and friends
        return (
            f"is not a linear-time regex: {exc}. RE2 refuses the constructs "
            f"whose cost cannot be bounded (backreferences, lookaround) — "
            f"rewrite the pattern without them."
        )
    return None


# ── applying a pattern ──────────────────────────────────────────────────────


@functools.lru_cache(maxsize=512)
def _compiled(pattern: str) -> Any:
    """RE2-compiled ``pattern``. Cached — jsonschema recompiles per validate."""
    re2 = re2_module()
    assert re2 is not None  # guarded by every caller
    return re2.compile(pattern)


def _matches(pattern: str, value: str) -> bool:
    """``pattern`` found anywhere in ``value``, RE2 semantics.

    JSON Schema's ``pattern`` is an unanchored SEARCH, which is what ``re2
    .search`` does — the same contract ``re.search`` gives jsonschema today."""
    return _compiled(pattern).search(value) is not None


@functools.lru_cache(maxsize=1)
def linear_time_validator_class() -> Any | None:
    """A ``Draft202012Validator`` whose ``pattern`` / ``patternProperties`` run
    on RE2, or ``None`` when the extra is absent.

    Built by EXTENDING the stock validator rather than replacing it, so every
    other keyword — and every future jsonschema fix — is inherited untouched.
    Only the two keywords that execute author-supplied regexes are overridden,
    because those two are the entire attack surface."""
    re2 = re2_module()
    if re2 is None:
        return None
    try:
        import jsonschema
        from jsonschema import validators
    except Exception:  # noqa: BLE001 — jsonschema is a core dep; be safe anyway
        return None

    def _pattern(validator, patrn, instance, schema):
        if not validator.is_type(instance, "string"):
            return
        try:
            hit = _matches(patrn, instance)
        except Exception:  # noqa: BLE001 — an uncompilable pattern is the
            # author's problem, and the schema guard already refused it; fall
            # back rather than crash a read.
            return
        if not hit:
            yield jsonschema.ValidationError(f"{instance!r} does not match {patrn!r}")

    def _pattern_properties(validator, patternProperties, instance, schema):
        if not validator.is_type(instance, "object"):
            return
        for patrn, subschema in patternProperties.items():
            for key, value in instance.items():
                try:
                    hit = _matches(patrn, key)
                except Exception:  # noqa: BLE001 — see above
                    continue
                if hit:
                    yield from validator.descend(
                        value, subschema, path=key, schema_path=patrn,
                    )

    return validators.extend(
        jsonschema.Draft202012Validator,
        {"pattern": _pattern, "patternProperties": _pattern_properties},
    )


def validate_instance(instance: Any, schema: dict[str, Any]) -> None:
    """``jsonschema.validate`` with the linear-time engine when it is available.

    THE application-side entry point: every place DNA validates an instance
    against an AUTHORED schema calls this instead of ``jsonschema.validate``, so
    "we accepted this pattern because it cannot backtrack" and "we run it on an
    engine that cannot backtrack" are the same statement.

    Raises ``jsonschema.ValidationError`` exactly as before — the extended
    validator is the stock one with two keywords swapped, so every existing
    ``except ValidationError`` site keeps working."""
    cls = linear_time_validator_class()
    if cls is None:
        import jsonschema

        jsonschema.validate(instance, schema)
        return
    cls(schema).validate(instance)
