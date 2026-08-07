"""The ASK for ``traits`` — projected from the live vocabulary, and never a list.

Slice 4 of ``spec-kind-taxonomia-o-que-eu-sou`` §8.1(2). The measurement that
justifies the slice is not an opinion about docstrings:

    of 47 Kind descriptors, **47 declare ``plane`` and 8 declare ``traits``**.
    Same file, same author, same mechanism — 100% against 17%.

The difference is that ``plane`` is asked for. Inside ``author_kind`` itself,
``presentation`` had ~25 lines with its closed vocabulary enumerated and
``traits`` had ONE line with no vocabulary at all. **Coverage follows the ask,
not the capability.**

So this suite pins two things, and they are different things:

1. **the ask exists** — the paragraph is there, and it carries the vocabulary;
2. ⭐ **the ask DERIVES** — register a trait and it appears; delete one and it
   goes. This is the property a hand-written list would fail one trait from now
   and pass every test written on the day it was typed. It is why
   :func:`~dna.kernel.kinds.traits.describe_traits` exists at all, and slice 3
   left it with no production caller.

And §8.4, which is the rule that keeps this from becoming a form nobody fills:

    **Pedir sempre. Recusar nunca.** A Kind that declares no trait must still be
    born. The ask has to SAY so, in the ask, or the next reader closes the gap by
    making the field mandatory — and a field everyone must fill is a field
    everyone fills with anything.
"""
from __future__ import annotations

import inspect

import pytest

from dna.application.kind_authoring import (
    TRAIT_ASK_SLOT,
    author_kind_impl,
    splice_trait_ask,
    trait_ask,
)
from dna.kernel.kinds.traits import (
    TRAIT_REQUIRED_ENFORCED,
    _TRAITS,
    known_traits,
    register_trait,
    trait_registry,
)


def _offered_names(text: str) -> set[str]:
    """The names the ask OFFERS — the entry heads, not every mention.

    The distinction is load-bearing in both directions: a description may name
    another trait in prose (``governance.policy`` names ``record.append-only``),
    so "the string appears" is not "the name is offered", and a test that
    conflated the two would fail for a reason unrelated to what it pins.
    ``describe_traits`` indents an entry head by two and its wrapped description
    by four more, which is what makes the heads separable at all."""
    return {
        line.strip().split("  ")[0]
        for line in text.splitlines()
        if line.startswith("    ") and not line.startswith("        ")
    }


@pytest.fixture
def registry_sandbox():
    """Restore the process-global trait registry after a test mutates it.

    The registry is module-global on purpose (it is the same open registry
    ``register_schema_fragment`` is), so a test that adds or removes a name has
    to put it back or every later test in the process reads a vocabulary this
    file invented."""
    snapshot = dict(_TRAITS)
    try:
        yield _TRAITS
    finally:
        _TRAITS.clear()
        _TRAITS.update(snapshot)


# ── 1. the ask exists, and it is the vocabulary ─────────────────────────────


def test_every_registered_trait_reaches_the_ask():
    """Not "some traits appear" — ALL of them, by enumeration of the registry.

    Asserting on three names by hand would pass against a hand-written list of
    those three names, which is precisely the implementation this test has to be
    able to fail."""
    text = trait_ask()
    missing = [name for name in known_traits() if name not in text]
    assert not missing, missing


def test_the_ask_carries_each_traits_own_DESCRIPTION_not_just_its_name():
    """A list of names answers "what may I write"; it does not answer "which one
    am I". The 17% came from a parameter documented in one line — a bare
    enumeration would be that line, wider."""
    text = trait_ask()
    for name, description in known_traits().items():
        # The first real sentence of each description, whitespace-collapsed the
        # same way `describe_traits` collapses it before wrapping.
        head = " ".join(description.split())[:40]
        assert head.split(" ")[0] in text, name
    # and the trait that CARRIES says so, which is the half slice 2 added
    assert "[carries" in text


# ── 2. ⭐ it DERIVES — the mutant ─────────────────────────────────────────────


def test_a_trait_ADDED_to_the_vocabulary_appears_in_the_ask(registry_sandbox):
    """The forward half. A hand-written list passes every test written the day
    it was written and silently stops offering the vocabulary the day after."""
    register_trait("probe.freshly-registered", "A name invented by this test.")
    text = trait_ask()
    assert "probe.freshly-registered" in text
    assert "A name invented by this test." in text


def test_a_trait_REMOVED_from_the_vocabulary_leaves_the_ask(registry_sandbox):
    """⭐ The mutant this slice is measured by: delete a trait and the ask has to
    change. A version of ``trait_ask`` with the thirteen core names typed into it
    would survive this deletion — which is exactly the failure mode, because
    nothing else in the tree would notice either."""
    victim = "record.append-only"
    assert victim in _offered_names(trait_ask())
    registry_sandbox.pop(victim)
    offered = _offered_names(trait_ask())
    # On the ENTRY, not on the whole text: `governance.policy`'s own description
    # MENTIONS `record.append-only` in prose, so a substring assertion here
    # would fail for a reason that has nothing to do with the mutant. What has
    # to disappear is the name being OFFERED.
    assert victim not in offered
    # and the rest of the vocabulary is untouched — a mutant that emptied the
    # whole block would also pass the line above
    assert "sdlc.work-item" in offered


def test_the_ask_is_recomputed_per_call_not_cached_at_import(registry_sandbox):
    """A module-level constant would be a hand-written list with extra steps: it
    freezes at import, which is before extensions register anything."""
    before = trait_ask()
    register_trait("probe.late-arrival", "Registered after the first call.")
    assert "probe.late-arrival" not in before
    assert "probe.late-arrival" in trait_ask()


# ── 3. §8.4 — asking is not requiring ───────────────────────────────────────


def test_the_ask_SAYS_that_declaring_nothing_is_an_answer():
    """§8.4 lives in the text or it does not live. An ask that enumerates
    thirteen roles and never says "none of them" is read as a requirement, and
    the author picks the nearest name — which is worse than silence, because a
    declared-and-unexercised role also LOOKS like a declaration."""
    text = trait_ask().lower()
    assert "declaring nothing is a legitimate answer" in text
    assert "never refused" in text


def test_the_ask_does_not_turn_traits_into_a_required_argument():
    """The signature is the other half of §8.4: an ask cannot be enforced by a
    docstring, but it can be contradicted by one. ``traits`` stays optional and
    stays defaulted to ``None``."""
    param = inspect.signature(author_kind_impl).parameters["traits"]
    assert param.default is None
    assert param.kind is inspect.Parameter.KEYWORD_ONLY


def test_the_founders_enforcement_switch_is_still_off():
    """``TRAIT_REQUIRED_ENFORCED`` is the founder's, and slice 4 is the slice
    most tempted to flip it — "we asked, now make them answer". Pinned here, in
    the suite that would benefit, so flipping it is a decision and not a
    side effect."""
    assert TRAIT_REQUIRED_ENFORCED is False


# ── 4. the splice — and the interpreter that dedents docstrings ─────────────


def test_the_core_docstring_actually_carries_the_ask():
    """``guard existe, porta não chama``, applied to prose: a projection nothing
    splices is a function with tests and no readers, which is what
    ``describe_traits`` was between slice 2 and this one."""
    doc = author_kind_impl.__doc__ or ""
    assert TRAIT_ASK_SLOT not in doc, "the slot survived — nothing spliced"
    assert "``traits`` (optional) declares WHAT YOUR KIND IS" in doc
    for name in known_traits():
        assert name in doc, name


def test_a_docstring_without_the_slot_is_a_LOUD_failure():
    """The silent version of this failure is the defect: a door rewritten
    without the slot ships an ask that quietly went back to one line, and
    nothing anywhere reports it."""
    with pytest.raises(ValueError, match="slot"):
        splice_trait_ask("A docstring nobody left room in.")
    with pytest.raises(ValueError, match="slot"):
        splice_trait_ask(None)


@pytest.mark.parametrize("indent", ["", "    ", "        "])
def test_the_block_is_indented_to_match_ITS_OWN_SLOT(indent):
    """⭐ Not a formatting nicety — an interpreter difference this package spans.

    **Python 3.13 dedents docstrings in the compiler (gh-81283); 3.12 does
    not**, and ``requires-python`` is ``>=3.12,<3.14``. The same nested ``def``
    therefore hands the splice a body indented by eight spaces on one
    interpreter and by zero on the other. An indentation passed in by the caller
    (who can only see its own source) is right on one and ragged on the other,
    and NOTHING fails — the tool simply reads badly to the only reader that
    matters and the one that cannot file a bug.

    So the indentation is read off the slot's own line, and this proves it for
    every indentation the two interpreters produce."""
    doc = f"Summary.\n\n{indent}{TRAIT_ASK_SLOT}\n\n{indent}Tail paragraph.\n"
    out = splice_trait_ask(doc)
    body = [
        line for line in out.splitlines()
        if line.strip() and "Summary." not in line and "Tail" not in line
    ]
    # every prose line of the block sits exactly at the slot's indentation; the
    # vocabulary sits deeper (describe_traits indents its own entries)
    assert body[0].startswith(indent + "``traits``")
    assert all(line.startswith(indent) for line in body), body[:5]
    assert any(line.startswith(indent + "    sdlc.") for line in body)


def test_the_slot_is_a_slot_and_not_an_fstring():
    """If the vocabulary were interpolated into the literal docstring, the slot
    would never appear in the source and the ask would freeze at import — before
    any extension has registered a name. The token existing IS the mechanism."""
    src = inspect.getsource(author_kind_impl)
    assert TRAIT_ASK_SLOT in src


# ── 5. the projection is the registry's, not this module's ──────────────────


def test_the_ask_offers_no_name_the_registry_does_not_know(registry_sandbox):
    """The reverse direction of test 1, and it catches the opposite mutant: a
    door that pads the vocabulary with names of its own would send an author
    after a trait nothing looks up."""
    registered = set(trait_registry())
    offered = _offered_names(trait_ask())
    assert offered <= registered, offered - registered
    assert offered == registered
