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

──────────────────────────────────────────────────────────────────────────────

**The second ratchet: Kind knowledge in the KERNEL, counted (i-109).**

A Kind name in a literal is the cheap kind of domain knowledge. The expensive
kind is a Kind's SCHEMA: ``kernel/models.py`` held 17 ``Typed*`` classes and
eleven extension files imported them back out of the kernel to register the very
Kinds those classes describe. The dependency pointed the wrong way, and the
first ratchet was blind to it — ``TypedGuardrail`` contains no Kind-name string.

i-109 moved them to the extensions that register each Kind. Two ceilings hold
the ground, and they are deliberately different instruments because each is
blind to what the other sees:

* :func:`test_the_kernel_defines_one_typed_model_for_a_registered_kind` is
  DERIVED — its oracle is the live registry, exactly like the first ratchet, so
  it needs no vocabulary of its own. It cannot see a model for a Kind that was
  never registered.
* :func:`test_the_kernel_defines_one_typed_class_at_all` is a PREFIX sweep, and
  it exists because of what the derived one missed: ``TypedTextBlock``,
  ``TypedHtmlBlock`` and ``TypedHtmlTemplate`` sat in ``kernel/models.py`` for
  Kinds that are **not registered anywhere in this repo** — 6 dead classes the
  registry-driven check could never name. They were deleted; this sweep is what
  keeps the next three from arriving.

**Ceiling: ONE, and it is ``TypedKindDefinition``.** That one is bootstrap and
stays by decision, the same nature as the three names in
``protocols.py::BOOTSTRAP_KIND_NAMES``: a Kind is born from a ``KindDefinition``,
so ``kernel/kinds/registry.py``, ``kernel/meta.py`` and
``kernel/write/namespace_gate.py`` genuinely parse one. Moving it would make the
kernel import an extension to learn what a Kind is.

⚠️ Being a bootstrap NAME is not the argument — being parsed BY the kernel is.
``Genome`` and ``LayerPolicy`` are in ``BOOTSTRAP_KIND_NAMES`` and their models
moved to ``extensions/helix`` without incident, because that constant is a load
ORDER of names and the kernel never imported their schemas.

Like the allowlist, the ceiling only comes DOWN. If a reason is ever found to
move ``TypedKindDefinition`` too, set it to zero.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dna.kernel import Kernel
from dna.testing.kind_literal_scan import scan_tree

_SDK_ROOT = Path(__file__).resolve().parents[1] / "dna"
_KERNEL_ROOT = _SDK_ROOT / "kernel"

#: The ONE Kind whose typed model the kernel is allowed to define. Read the
#: module docstring for the argument; lower this to an empty set, never grow it.
KERNEL_BOOTSTRAP_MODELS = frozenset({"TypedKindDefinition", "KindDefinitionSpec"})


#: key → why this literal Kind-name set is irreducible. Read them as claims to be
#: argued with, not as permanent grants.
ALLOWLIST: dict[str, str] = {
    # ── the kernel's own bootstrap triple (one definition, three importers) ──
    "kernel/protocols.py::BOOTSTRAP_KIND_NAMES": (
        "IRREDUCIBLE. These three Kinds are what the kernel must load in order "
        "to learn what any Kind is: a Genome declares the scope, a "
        "KindDefinition declares a Kind, a LayerPolicy declares who may write "
        "one. Deriving them from a trait would require reading an instance whose "
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
        "design (`_digest.build_digest` takes instances and a window, not a "
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
    "application/sdlc_family.py::FALLBACK_FAMILIES[TRAIT_DECISION]": (
        "FALLBACK. One row of the same table as TRAIT_WORK_ITEM above, asserted "
        "equal to the live derivation by `test_sdlc_family_is_declarative`. "
        "It became VISIBLE to this ratchet only on 07/08/2026, when Spec joined "
        "ADR in the decision family (i-121) — a one-name tuple is not a set, so "
        "the row sat here unlisted for as long as the family had a single "
        "member. Worth reading as a property of the scanner rather than a new "
        "shortcut: this ratchet sees a list the moment it becomes one."
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

    # ── kernel/boot/events.py::_FIXED_EVENTS — ENTRY REMOVED, i-107 ──────────
    # Its argument was: "IRREDUCIBLE, and arguably not a Kind list at all: these
    # are the two boot EVENT names that happen to coincide with Kind names. A
    # trait on EvalRun would be a statement about the Kind, and this is a
    # statement about the boot sequence."
    #
    # That was wrong, and this file invited the argument — "read them as claims
    # to be argued with, not as permanent grants". The refutation: EvidencePolicy
    # selects which writes to capture BY event_type, so a Kind whose event_type
    # could only ever be `document_created` could not be named by any policy
    # written against a meaningful event. The event name is not a fact about the
    # boot sequence; it is the Kind's own vocabulary, and holding it here made
    # tenant-authored Kinds silently ineligible for evidence capture.
    #
    # It is now `post_save_event` on the KindPort / `spec.post_save_event` in a
    # descriptor. The dict is gone, so the excuse goes with it — which is what
    # `test_no_stale_allowlist_entries` is for, and it is how this was caught.
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


# ── the second ratchet: Kind SCHEMAS in the kernel (i-109) ──────────────────


def _kernel_classes() -> list[tuple[str, str]]:
    """``(module-relative-path, class name)`` for every class defined anywhere
    under ``dna/kernel/`` — nested classes included, since hiding a Kind model
    inside another class would evade a top-level-only walk."""
    out: list[tuple[str, str]] = []
    for py in sorted(_KERNEL_ROOT.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                out.append((str(py.relative_to(_SDK_ROOT)), node.name))
    assert out, "no classes found under dna/kernel — the sweep is blind"
    return out


def test_the_kernel_defines_one_typed_model_for_a_registered_kind():
    """DERIVED, same oracle as the first ratchet: for every REGISTERED Kind
    ``K``, a class named ``TypedK`` or ``KSpec`` defined inside ``dna/kernel``
    is the kernel holding that Kind's schema."""
    kernel = Kernel.auto()
    names = {p.kind for p in kernel.kind_ports()}
    assert len(names) > 50, "the registry oracle looks empty — the sweep is blind"
    model_names = {f"Typed{n}" for n in names} | {f"{n}Spec" for n in names}

    offenders = sorted(
        f"{path}::{cls}"
        for path, cls in _kernel_classes()
        if cls in model_names and cls not in KERNEL_BOOTSTRAP_MODELS
    )
    assert not offenders, (
        "The kernel defines the typed model of a Kind it does not own:\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n\nMove it to the extension that REGISTERS that Kind (i-109) — the "
          "extension already imports `Metadata` from `dna.kernel.models`, which "
          "is generic envelope structure and the only thing that should cross. "
          "If the kernel genuinely PARSES instances of this Kind itself, it is "
          "bootstrap: say so in this file's docstring and add it to "
          "KERNEL_BOOTSTRAP_MODELS."
    )


def test_the_kernel_defines_one_typed_class_at_all():
    """PREFIX sweep — deliberately NOT derived, because the derived check above
    is blind to exactly the case that was found: three ``Typed*`` classes for
    Kinds nobody registers. A model for an unregistered Kind is the same
    misplaced domain knowledge, and cheaper to spot than to explain later."""
    offenders = sorted(
        f"{path}::{cls}"
        for path, cls in _kernel_classes()
        if cls.startswith("Typed") and cls not in KERNEL_BOOTSTRAP_MODELS
    )
    assert not offenders, (
        "New Typed* class(es) in the kernel:\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n\nThe kernel knows no Kinds; extensions register them. Put the "
          "model next to the registration. See i-109 and this file's docstring."
    )


def test_the_bootstrap_ceiling_is_still_one_kind():
    """The ceiling only comes down. Two class names, ONE Kind — a rename that
    quietly admitted a second Kind would otherwise read as a no-op diff."""
    kinds = {n.removeprefix("Typed").removesuffix("Spec")
             for n in KERNEL_BOOTSTRAP_MODELS}
    assert kinds == {"KindDefinition"}, (
        f"KERNEL_BOOTSTRAP_MODELS now covers {sorted(kinds)}. Only "
        "KindDefinition is bootstrap by the argument written in this file's "
        "docstring; a second entry needs its own argument there."
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
