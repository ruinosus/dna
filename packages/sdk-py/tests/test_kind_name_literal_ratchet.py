"""The ratchet — a hardcoded Kind-name set must argue for itself, in writing.

This is the half that makes the trait work stick. ``embed_fields`` and
``version_retention`` were both shipped as declarative fields and both had ZERO
adopters, because nothing failed when a new Kind ignored them. A declarative
mechanism nobody is forced to use is a mechanism nobody uses.

So: every literal collection of two-or-more strings that are ALL registered Kind
names is a finding, and a finding must be in :data:`ALLOWLIST` with a REASON. The
oracle is the live registry rather than a pattern, so the check has no vocabulary
of its own to drift and it sees a new list the moment somebody writes one.

**The allowlist only shrinks.** ``test_no_stale_allowlist_entries`` fails on an
entry whose site is gone, so a converted site cannot leave its excuse behind.
Adding an entry means writing the argument for why that particular list cannot be
a declaration — which is the whole point: the cost of the shortcut is having to
defend it where the next reader will find it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.kernel import Kernel
from dna.testing.kind_literal_scan import scan_tree

_SDK_ROOT = Path(__file__).resolve().parents[1] / "dna"


#: key → why this literal Kind-name set is irreducible. Read them as claims to be
#: argued with, not as permanent grants.
ALLOWLIST: dict[str, str] = {
    # ── the kernel's own bootstrap triple (one definition, three importers) ──
    "kernel/protocols.py::BOOTSTRAP_KIND_NAMES": (
        "IRREDUCIBLE. These three Kinds are what the kernel must load in order "
        "to learn what any Kind is: a Genome declares the scope, a "
        "KindDefinition declares a Kind, a LayerPolicy declares who may write "
        "one. Deriving them from a trait would require reading a document whose "
        "Kind is not registered yet. The ORDER is load-bearing too. This is now "
        "the ONE definition — kernel/__init__.py, kernel/manifest.py and "
        "kernel/query/resolver.py import it rather than repeating it, which is "
        "the drift the v1.3 Milestone->Epic rename actually caused."
    ),

    # ── kernel-less fallbacks, each pinned to the live derivation by a test ──
    "application/sdlc.py::DATED_SPEC_FIELDS": (
        "FALLBACK. The live table is derived from the `sdlc.dated` / "
        "`sdlc.dated-create-only` traits (`sdlc_family.dated_spec_fields`). This "
        "one survives for the PURE builders and the two guard suites that hold "
        "every write path to it, which run without a kernel. "
        "`test_sdlc_family_is_declarative` asserts it equals the derived table, "
        "so it cannot drift the way the thirteen work-item lists did."
    ),
    "application/sdlc.py::_STATUS_ENUMS": (
        "FALLBACK. `set_status` reads each Kind's arc off its OWN schema "
        "(`spec.properties.status.enum`); this map only answers for a caller "
        "with no kernel — the pure `validate_transition`, used by the CLI's "
        "option parsing. Pinned to the derivation by "
        "`test_sdlc_family_is_declarative`."
    ),
    "application/sdlc_family.py::FALLBACK_FAMILIES[TRAIT_WORK_ITEM]": (
        "FALLBACK, and the ONE place they live. Some consumers are pure by "
        "design (`_digest.build_digest` takes documents and a window, not a "
        "kernel) and some take a narrow duck-typed kernel. Every entry is "
        "asserted equal to the live derivation by "
        "`test_sdlc_family_is_declarative` — a fallback nobody checks is just "
        "the fourteenth list."
    ),
    "application/sdlc_family.py::FALLBACK_FAMILIES[TRAIT_ROLLUP]": (
        "FALLBACK. One row of the same table as TRAIT_WORK_ITEM above: the kernel-less answer for a pure consumer, asserted equal to the live derivation by `test_sdlc_family_is_declarative`."
    ),
    "application/sdlc_family.py::FALLBACK_FAMILIES[TRAIT_FILED]": (
        "FALLBACK. One row of the same table as TRAIT_WORK_ITEM above: the kernel-less answer for a pure consumer, asserted equal to the live derivation by `test_sdlc_family_is_declarative`."
    ),
    "application/sdlc_family.py::FALLBACK_FAMILIES[TRAIT_JOURNEY_DERIVED]": (
        "FALLBACK. One row of the same table as TRAIT_WORK_ITEM above: the kernel-less answer for a pure consumer, asserted equal to the live derivation by `test_sdlc_family_is_declarative`."
    ),
    "memory/verbs.py::MEMORY_KINDS": (
        "FALLBACK. The live answer is the `memory.recallable` trait "
        "(`recallable_kinds(kernel)`); this constant is public API and answers "
        "for a kernel with no trait registry. "
        "`test_embeddable_is_not_recallable` pins it to the declarations."
    ),
    "extensions/guardrails/write_guards.py::_GOVERNED_KINDS_FALLBACK": (
        "FALLBACK. The live answer is the `governance.spec-traced` trait; a "
        "pre_save context does not always carry a kernel, and a governance "
        "guard that cannot resolve its own scope must fail OPEN to the "
        "documented set rather than veto everything or nothing."
    ),

    # ── genuinely not a Kind family ──────────────────────────────────────────
    "kernel/boot/events.py::_FIXED_EVENTS": (
        "IRREDUCIBLE, and arguably not a Kind list at all: these are the two "
        "boot EVENT names that happen to coincide with Kind names. A trait on "
        "EvalRun would be a statement about the Kind, and this is a statement "
        "about the boot sequence."
    ),
}


def _findings():
    kernel = Kernel.auto()
    names = {p.kind for p in kernel.kind_ports()}
    assert len(names) > 50, "the registry oracle looks empty — the scan is blind"
    return scan_tree(_SDK_ROOT, kind_names=names)


def test_no_unjustified_hardcoded_kind_name_sets():
    offenders = [f for f in _findings() if f.key not in ALLOWLIST]
    assert not offenders, (
        "New hardcoded Kind-name set(s):\n"
        + "\n".join(f"  {f.describe()}" for f in offenders)
        + "\n\nDeclare a trait on the Kinds instead and ask "
          "`kernel.kinds_with_trait(...)` — see dna/kernel/kinds/traits.py and "
          "dna/application/sdlc_family.py. If the site is genuinely "
          "irreducible, add its key to ALLOWLIST in this file WITH THE REASON."
    )


def test_no_stale_allowlist_entries():
    """The allowlist only shrinks: a converted site must not leave its excuse
    behind, or the next reader inherits an argument for a list that is gone."""
    live = {f.key for f in _findings()}
    stale = sorted(set(ALLOWLIST) - live)
    assert not stale, (
        f"ALLOWLIST entries whose site no longer exists: {stale}. Delete them."
    )


def test_every_allowlist_entry_carries_a_real_reason():
    thin = sorted(k for k, v in ALLOWLIST.items() if len(v.strip()) < 40)
    assert not thin, (
        f"ALLOWLIST entries with no argument: {thin}. 'legacy' is not a reason."
    )


# ── the scanner itself (it is the ratchet's eye; it has to see) ─────────────


@pytest.mark.parametrize("source, expected", [
    ('X = ("Story", "Issue")', "X"),
    ('X = frozenset({"Story", "Issue"})', "X"),
    ('X: tuple = ["Story", "Issue"]', "X"),
    ('X = {"Story": 1, "Issue": 2}', "X"),
])
def test_the_scanner_sees_the_shapes_people_actually_write(source, expected):
    from dna.testing.kind_literal_scan import scan_kind_name_literals

    found = scan_kind_name_literals(
        source, module="m.py", kind_names={"Story", "Issue"})
    assert [f.symbol for f in found] == [expected]


def test_the_scanner_sees_an_inline_membership_test():
    from dna.testing.kind_literal_scan import scan_kind_name_literals

    found = scan_kind_name_literals(
        'def f(k):\n    return k in ("Story", "Issue")\n',
        module="m.py", kind_names={"Story", "Issue"})
    assert len(found) == 1
    assert found[0].symbol == "f::<inline>"


def test_the_scanner_sees_a_nested_per_kind_table():
    """The biggest tables hide their memberships in the VALUES."""
    from dna.testing.kind_literal_scan import scan_kind_name_literals

    found = scan_kind_name_literals(
        'T = {"a": ("Story", "Issue"), "b": ("Issue",)}',
        module="m.py", kind_names={"Story", "Issue"})
    assert [f.symbol for f in found] == ["T['a']"]


def test_the_scanner_ignores_a_collection_that_is_not_about_kinds():
    from dna.testing.kind_literal_scan import scan_kind_name_literals

    assert scan_kind_name_literals(
        'X = ("Story", "done")', module="m.py", kind_names={"Story", "Issue"}) == []
    assert scan_kind_name_literals(
        'X = ("Story",)', module="m.py", kind_names={"Story", "Issue"}) == []
