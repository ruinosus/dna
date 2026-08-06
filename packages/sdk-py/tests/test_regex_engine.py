"""Decision C — a regex engine that cannot backtrack, on both sides.

#244 shipped a MEASURED refusal: a hand-written reader that recognises the three
shapes measured to explode. Its own docstring named the limit — "deciding regex
ambiguity in general is the analysis a linear-time engine (RE2) does for you".
This closes it with RE2 where RE2 is available, and keeps the heuristic exactly
where it is not.

The load-bearing property is that the two halves AGREE: RE2 may relax the
author-time refusal only if RE2 is also the engine that runs the pattern. A
pattern accepted as linear and then executed by Python's backtracking ``re``
would be a safety certificate issued for the wrong engine.
"""
from __future__ import annotations

import time

import pytest

from dna.kernel.kinds import regex_engine as R
from dna.kernel.kinds.schema_guard import SchemaGuardError, redos_risk, validate_authored_schema

re2_installed = pytest.mark.skipif(
    not R.accepts_any_linear_pattern(), reason="dna-sdk[re2] not installed",
)


@pytest.fixture
def heuristic(monkeypatch):
    """Force the #244 heuristic regardless of what is installed.

    Skipping when RE2 is present would delete the heuristic's coverage from a
    machine that has the extra — and the heuristic is what protects every
    deployment that cannot take it (Alpine has no musllinux wheel; a pre-2.28
    glibc has no manylinux wheel). Both regimes ship, so both are tested."""
    monkeypatch.setattr(R, "accepts_any_linear_pattern", lambda: False)


def test_the_engine_reports_itself():
    """An operator must be able to see which regime is in force — 'it depends
    on the install' is only honest if the install can be asked."""
    assert R.engine_name() in (R.ENGINE_RE2, R.ENGINE_HEURISTIC)
    assert (R.engine_name() == R.ENGINE_RE2) == R.accepts_any_linear_pattern()


# ── with RE2: linear time is a fact, not a shape ────────────────────────────


@re2_installed
def test_re2_accepts_the_pattern_the_heuristic_had_to_refuse():
    """``^(a+)+$`` is the canonical catastrophic backtracker — and under RE2 it
    is simply a regex, matched in linear time."""
    assert redos_risk("^(a+)+$") is None


@re2_installed
def test_re2_actually_matches_the_evil_input_fast():
    """Not a claim about RE2, a measurement of it. The same input takes ~1.5s
    on CPython's `re` at 26 characters and doubles per character after that."""
    schema = {"type": "object", "properties": {"x": {"type": "string", "pattern": "^(a+)+$"}}}
    payload = {"x": "a" * 64 + "b"}
    start = time.perf_counter()
    with pytest.raises(Exception):  # noqa: B017 — jsonschema.ValidationError
        R.validate_instance(payload, schema)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"linear-time engine took {elapsed:.3f}s"


@re2_installed
def test_re2_refuses_what_it_cannot_bound():
    """Backreferences and lookaround are exactly the constructs whose cost RE2
    cannot bound — refusing them is the same refusal the heuristic reached for,
    made by an engine that can decide it."""
    assert redos_risk(r"(a)\1") is not None
    assert redos_risk(r"(?=foo)bar") is not None


@re2_installed
def test_the_length_bound_does_not_apply_under_re2():
    """The 512-char bound was a statement about what the READER could vouch for,
    not about long regexes. An engine that decides does not need it."""
    long_but_fine = "|".join(f"opt{i}" for i in range(200))
    assert len(long_but_fine) > 512
    assert redos_risk(long_but_fine) is None


# ── without RE2: #244 stands, unchanged ─────────────────────────────────────


def test_the_heuristic_still_refuses_the_measured_shapes(heuristic):
    assert redos_risk("^(a+)+$") is not None
    assert redos_risk("^([a-z]*)*$") is not None
    assert redos_risk("^(a|aa)+$") is not None


def test_the_heuristic_still_accepts_the_measured_fast_shape(heuristic):
    assert redos_risk(r"^([a-z]+\.)+[a-z]+$") is None


# ── both regimes: a broken pattern is still refused ─────────────────────────


def test_an_uncompilable_pattern_is_refused_either_way():
    assert redos_risk("(unclosed") is not None


def test_a_non_string_pattern_is_refused_either_way():
    assert redos_risk(123) is not None  # type: ignore[arg-type]


def test_the_schema_walk_still_finds_patterns_in_nested_positions():
    bad = "(a)\\1" if R.accepts_any_linear_pattern() else "^(a+)+$"
    with pytest.raises(SchemaGuardError, match="pattern at"):
        validate_authored_schema({
            "type": "object",
            "properties": {"outer": {"items": {"type": "string", "pattern": bad}}},
        })


def test_a_property_literally_named_pattern_is_still_not_a_keyword():
    """The walk must not read ``properties.pattern`` as the ``pattern`` keyword
    — DNA's own Plan Kind has such a property."""
    validate_authored_schema({
        "type": "object",
        "properties": {"pattern": {"type": "string"}},
    })


# ── the applying engine ─────────────────────────────────────────────────────


def test_validate_instance_matches_jsonschema_semantics():
    """``pattern`` is an unanchored SEARCH in JSON Schema. If the RE2 path used
    ``fullmatch`` it would silently reject instances the stock validator accepts."""
    schema = {"type": "object", "properties": {"x": {"type": "string", "pattern": "b+"}}}
    R.validate_instance({"x": "aaabbbccc"}, schema)  # substring match: valid
    with pytest.raises(Exception):  # noqa: B017 — ValidationError
        R.validate_instance({"x": "aaaccc"}, schema)


def test_validate_instance_honours_pattern_properties():
    schema = {
        "type": "object",
        "patternProperties": {"^x_": {"type": "integer"}},
    }
    R.validate_instance({"x_a": 1, "other": "free"}, schema)
    with pytest.raises(Exception):  # noqa: B017 — ValidationError
        R.validate_instance({"x_a": "not an integer"}, schema)


def test_validate_instance_still_enforces_every_other_keyword():
    """The RE2 validator is the stock one with TWO keywords swapped — extending
    rather than replacing is what keeps `required`, `type`, `enum` and every
    future jsonschema fix working."""
    schema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}
    R.validate_instance({"a": 1}, schema)
    with pytest.raises(Exception):  # noqa: B017 — ValidationError
        R.validate_instance({}, schema)
    with pytest.raises(Exception):  # noqa: B017 — ValidationError
        R.validate_instance({"a": "x"}, schema)
