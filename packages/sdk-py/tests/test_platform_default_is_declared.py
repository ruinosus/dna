"""i-107 — "ships a platform default in ``_lib``" is DECLARED, not listed.

``query/resolver.py`` carried ``DEFAULT_INHERITABLE_KINDS_V1``, eight literal
Kind names, read by ``Kernel.composition_summary`` (per-Kind local/inherited
counts) and by the invariant "an inheritable Kind may never be TENANTED"
(tests/test_inheritable_kinds_tenancy.py). It is now the trait
``composition.platform-default``.

⭐ THE MEASUREMENT THAT DECIDED THE SHAPE — and it went the other way from the
previous two slices, which is why it is worth writing down.

The obvious move was to delete the list and derive it from ``scope_inheritable``,
the way ``DEFAULT_NON_INHERITABLE_KINDS_V1`` was deleted in slice 1: the file's
own comment called this one a "display set", a vestige. Measuring first killed
that plan. 74 Kinds are scope-inheritable and **16 of them are TENANTED** —
Canvas, UserProfile, AuditLog, Project, Organization, Role… Deriving from
``scope_inheritable`` would have reported all sixteen as violations of an
invariant they do not break, because being ALLOWED to inherit across scopes is
not the same fact as SHIPPING a default in ``_lib`` for scopes to inherit.

So this list was RIGHT about its concept. It was wrong only about being a list —
and the honest fix for a correct concept with no declaration is to give it one,
not to derive it from the nearest thing that happens to be declarable. A trait
that restates an existing attribute is the overdo ``vocabulary.py`` refuses; a
trait that names a concept nothing else expresses is what the vocabulary is FOR.
``test_the_platform_defaults_are_not_the_scope_inheritable_set`` keeps that
distinction measured rather than remembered.

⚠️ And the thing a literal list can do that a declaration cannot: three of the
eight names — ``LottieAsset``, ``HtmlTemplate``, ``ImagePrompt`` — are not
registered anywhere in this repo. ``composition_summary`` issued three futile
queries per call and the tenancy invariant skipped them with
``if kp is None: continue``, so 37% of the set was dead and every reader of both
call sites saw a green test. This is the third dead-name finding of i-107, after
``Finding`` in the evidence set and ``VibeSession`` in the churn set.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.kinds.base import KindBase
from dna.kernel.protocols import StorageDescriptor, TenantScope
from dna.kernel.query.resolver import TRAIT_PLATFORM_DEFAULT

#: The literal set as it stood immediately before deletion. Frozen HERE, in the
#: test, on purpose: a parity proof whose "before" side can be edited by the
#: change it is proving is not a proof. Never import this from production code.
LITERAL_BEFORE_DELETION = frozenset({
    "Agent", "LottieAsset", "HtmlTemplate", "Skill", "ImagePrompt",
    "Theme", "PromptTemplate", "Automation",
})

#: The three that named no registered Kind. Deleting a name from here means
#: claiming it got registered — which is checkable, so check it.
DEAD_NAMES = frozenset({"LottieAsset", "HtmlTemplate", "ImagePrompt"})


@pytest.fixture(scope="module")
def kernel():
    return Kernel.auto()


def test_the_derived_set_equals_the_old_list_minus_its_dead_names(kernel):
    """FIDELITY — the assertion that had to pass BEFORE the list was deleted.

    Equality, not containment, in both directions: a Kind that used to be a
    platform default must still be one, and no Kind may have been swept in by
    the change.
    """
    derived = kernel.kinds_with_trait(TRAIT_PLATFORM_DEFAULT)
    registered = {p.kind for p in kernel.kind_ports()}
    assert len(registered) > 50, "the registry oracle looks empty"

    expected = LITERAL_BEFORE_DELETION & registered
    assert derived == expected, (
        f"the declared platform defaults {sorted(derived)} do not match the "
        f"literal list's registered members {sorted(expected)}.\n"
        f"  lost (declared nothing): {sorted(expected - derived)}\n"
        f"  gained (declared newly): {sorted(derived - expected)}\n"
        "A gain may be correct — say so in the PR. A loss is a behaviour change."
    )


def test_the_three_dead_names_are_the_finding(kernel):
    """The dead names were 37% of the set and nothing said so. If one is ever
    really registered, this fails and the docstring above must be retold."""
    registered = {p.kind for p in kernel.kind_ports()}
    still_dead = DEAD_NAMES - registered
    assert still_dead == DEAD_NAMES, (
        f"{sorted(DEAD_NAMES - still_dead)} are registered now — the "
        "measurement this file rests on has changed. Re-read the docstring "
        "and decide whether they should declare the trait."
    )
    assert DEAD_NAMES < LITERAL_BEFORE_DELETION


def test_the_platform_defaults_are_not_the_scope_inheritable_set(kernel):
    """⭐ THE MEASUREMENT THAT MADE THIS A TRAIT INSTEAD OF A DELETION.

    Kept as an assertion rather than a comment so that a future reader tempted
    by "surely this is just ``scope_inheritable``" is answered by the suite
    instead of by memory — and so the day the two sets DO coincide, somebody is
    told rather than left to assume.
    """
    registered = {p.kind for p in kernel.kind_ports()}
    inheritable = registered - set(kernel._NON_INHERITABLE_KINDS)
    defaults = kernel.kinds_with_trait(TRAIT_PLATFORM_DEFAULT)

    assert defaults < inheritable, (
        "every platform default must at least be scope-inheritable — it "
        f"promises a base others inherit. Offenders: {sorted(defaults - inheritable)}"
    )
    tenanted_but_inheritable = sorted(
        p.kind for p in kernel.kind_ports()
        if p.kind in inheritable
        and getattr(p, "scope", None) == TenantScope.TENANTED
    )
    assert tenanted_but_inheritable, (
        "the two sets have converged — scope-inheritable no longer contains a "
        "TENANTED Kind. That was the whole argument for a separate trait; "
        "re-measure and rewrite this file's docstring before trusting it."
    )
    assert not (defaults & set(tenanted_but_inheritable)), (
        "a platform default cannot be TENANTED: a TENANTED Kind refuses a write "
        "at the base layer, so the default it promises could never be written. "
        f"Offenders: {sorted(defaults & set(tenanted_but_inheritable))}"
    )


def test_a_kind_the_kernel_has_never_heard_of_can_declare_it():
    """⭐ THE POINT — a tenant Kind joins its own sidebar.

    ``composition_summary`` iterated a set defined in the kernel, so a
    tenant-authored Kind could not appear in the Studio's local-vs-inherited
    counts however much it behaved like a platform default. Declaring is the
    whole of it now.
    """
    class _MarketPreset(KindBase):
        api_version = "market.example/v1"
        kind = "MarketPreset"
        alias = "market-marketpreset"
        storage = StorageDescriptor.yaml("marketpresets")
        traits = frozenset({TRAIT_PLATFORM_DEFAULT})

    k = Kernel.auto()
    k.kind(_MarketPreset())
    assert "MarketPreset" in k.kinds_with_trait(TRAIT_PLATFORM_DEFAULT)


def test_the_literal_list_is_gone():
    """It must not come back — the three dead names are what a list buys."""
    import dna.kernel.query.resolver as res

    assert not hasattr(res, "DEFAULT_INHERITABLE_KINDS_V1"), (
        "DEFAULT_INHERITABLE_KINDS_V1 is back. A platform default is declared "
        "by the Kind (`composition.platform-default`) and derived by "
        "`kernel.kinds_with_trait`."
    )
