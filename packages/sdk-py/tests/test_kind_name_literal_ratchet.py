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

──────────────────────────────────────────────────────────────────────────────

**The third ratchet: Kind NAMES in the kernel, counted (i-107).**

The two instruments above are blind to the cheapest form of the same knowledge,
and i-109's own closing note said so out loud: it shipped with the Typed-model
ceiling at ONE and reported "39 Kind-name literals, 22 Kinds, still in the
kernel" as an open end. Both existing eyes were green over that number, because

* the FIRST ratchet only sees a collection of two-or-more names, so
  ``kernel.query(scope, "EvidencePolicy")``, ``if kind == "Evidence"`` and
  ``{"Engram": "..."}`` are invisible to it BY CONSTRUCTION;
* the SECOND sees ``Typed*`` classes, and a Kind name in a string is not a class.

:func:`test_the_kernel_knows_at_most_n_kind_names` closes that hole with
``scan_occurrences_in_tree``: every string literal under ``dna/kernel`` equal to
a registered Kind name, docstrings excluded, counted as OCCURRENCES. Three names
in one tuple is three, because it is three facts.

**Ceiling: 26, shrink-only.** i-107 took it from 39 by translating 13. What
remains is not undifferentiated debt — it is two decided groups plus five argued
survivors, so the number is a sum of decisions rather than a budget:

* **13 — bootstrap** (``Genome`` / ``KindDefinition`` / ``LayerPolicy``, across
  ``protocols.py``, ``compose/instance_builder.py``, ``compose/resolver.py``,
  ``compose/layer_policy.py``, ``catalog/cache.py``, ``models.py``). Same
  argument as ``BOOTSTRAP_KIND_NAMES`` in the allowlist below: a descriptor
  cannot bootstrap the reader that reads descriptors.
* **8 — ``registry/accessor.py``**, closed by the FOUNDER in i-108 as not
  commercial logic but the quota gate of the open-source MCP server — eight open
  consumers against one closed. ⛔ Do not reopen from this file.
* **5 — argued in place**, each next to its own code: ``manifest.py``'s ``Hook``
  and ``SafetyPolicy`` (i-109 shape — the kernel parses their schemas, so a trait
  would move two strings and leave every field read), ``reports.py``'s
  ``EvalRun`` (same), ``evidence.py``'s published ``kind="Evidence"`` default
  (the sole production caller passes it explicitly), and ``hard_delete.py``'s
  one-key ``INVALIDATE_VERBS``.

⚠️ This ceiling is a COUNT with no allowlist, and the asymmetry with the first
ratchet is deliberate. An allowlist demands an argument per site and is right
when every site is a standing decision; a count is right when the goal is a
number that falls. Both are here because they guard the same failure — a guard
that stays green while the promise it guards goes false — and neither sees what
the other sees.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dna.kernel import Kernel
from dna.testing.kind_literal_scan import scan_occurrences_in_tree, scan_tree

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


# ── the third ratchet: Kind NAMES in the kernel, counted (i-107) ───────────

#: How many individual registered-Kind-name string literals ``dna/kernel`` is
#: allowed to contain. Read the module docstring for the breakdown — 13
#: bootstrap + 8 accessor (i-108, founder) + 5 argued in place. **Shrink only.**
KERNEL_KIND_NAME_CEILING = 26


def _kernel_kind_name_uses():
    kernel = Kernel.auto()
    names = {p.kind for p in kernel.kind_ports()}
    assert len(names) > 50, (
        "the registry oracle looks empty — the count is blind. This is the "
        "shared-venv trap: a stale `dna-sdk` elsewhere on the machine resolves "
        "to another checkout and reports fewer Kinds. Use the worktree's venv."
    )
    return scan_occurrences_in_tree(_KERNEL_ROOT, kind_names=names)


def test_the_kernel_knows_at_most_n_kind_names():
    """The count only goes DOWN. A new one needs an argument next to the code
    AND a line in this file's docstring saying which group it joined."""
    uses = _kernel_kind_name_uses()
    assert len(uses) <= KERNEL_KIND_NAME_CEILING, (
        f"The kernel now names {len(uses)} Kinds, over the ceiling of "
        f"{KERNEL_KIND_NAME_CEILING}:\n"
        + "\n".join(f"  {u.describe()}" for u in uses)
        + "\n\nDerive it instead — `kernel.kinds_with_trait(...)`, or a per-Kind "
          "field the descriptor already carries (`version_retention`, "
          "`post_save_event`, `storage.body_field`, `scope_inheritable`). ⭐ ASK "
          "FIRST whether a mechanism already exists: a new trait for something "
          "that is already an attribute is a regression, not a fix. If the site "
          "is genuinely irreducible, write the argument WHERE THE CODE IS and "
          "raise this ceiling in the same commit, with the reason in the "
          "docstring above."
    )


def test_the_ceiling_is_not_slack():
    """⚠️ The half that makes the ceiling a ratchet rather than a budget.

    A ceiling above the real count is slack somebody can spend without review —
    which is how a "shrink-only" number quietly stops shrinking. Removing a
    literal must lower this constant in the same commit."""
    uses = _kernel_kind_name_uses()
    assert len(uses) == KERNEL_KIND_NAME_CEILING, (
        f"The kernel names {len(uses)} Kinds but the ceiling says "
        f"{KERNEL_KIND_NAME_CEILING}. If you REMOVED one: lower the constant "
        "to match — that is the ratchet clicking. If you added one, the test "
        "above already told you what to do."
    )


def test_the_count_is_occurrences_not_sites():
    """``BOOTSTRAP_KIND_NAMES`` is one tuple and THREE facts. Collapsing a
    literal collection to a single finding would let a growing list read as a
    flat number, which is the measurement error this ratchet exists to avoid."""
    uses = _kernel_kind_name_uses()
    bootstrap = [
        u for u in uses
        if u.module == "protocols.py" and "BOOTSTRAP_KIND_NAMES" in u.line
    ]
    assert {u.kind for u in bootstrap} == {"Genome", "KindDefinition", "LayerPolicy"}
    assert len(bootstrap) == 3, (
        "the three bootstrap names on one line must count as three — if this "
        "is 1, the scanner is deduplicating by site and the ceiling is a lie"
    )


def test_the_accessor_block_is_the_i108_decision_not_debt():
    """⛔ Eight of the twenty-six are ``registry/accessor.py``, and they are a
    FOUNDER decision (i-108), not a translation nobody got to.

    Pinned here because the next agent to read the ceiling will see the biggest
    single file and reach for it. The measurement that closed i-108:
    ``account_plan`` has 8 open-side consumers against 1 closed, and
    ``cli/_mcp_quota.py`` reads the ``PricingPlan`` Kind to enforce quota on the
    SELF-HOSTED MCP server. Moving it breaks the OSS server the open-core
    boundary exists to protect. The re-open trigger is written in i-108 and it is
    specific: ``_mcp_quota`` ceasing to exist on the open side."""
    uses = _kernel_kind_name_uses()
    accessor = [u for u in uses if u.module == "registry/accessor.py"]
    assert len(accessor) == 8, (
        f"registry/accessor.py now names {len(accessor)} Kinds, not 8. i-108's "
        "measurement was taken at 8; re-read the issue before adjusting."
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


# ── the THIRD eye, planted with the shapes the first two cannot see ─────────


@pytest.mark.parametrize("source, expected", [
    # each of these was a REAL site i-107 translated; the first scanner
    # reports zero findings for every one of them
    ('rows = kernel.query(scope, "Issue")', ["Issue"]),
    ('if kind == "Story":\n    return', ["Story"]),
    ('VERBS = {"Issue": "close it"}', ["Issue"]),
    ('def f(kind: str = "Story"): ...', ["Story"]),
    ('X = ("Story", "Issue")', ["Issue", "Story"]),
])
def test_the_occurrence_scanner_sees_what_the_set_scanner_cannot(source, expected):
    from dna.testing.kind_literal_scan import (
        scan_kind_name_literals,
        scan_kind_name_occurrences,
    )

    names = {"Story", "Issue"}
    uses = scan_kind_name_occurrences(source, module="m.py", kind_names=names)
    assert sorted(u.kind for u in uses) == expected
    if len(expected) == 1:
        assert scan_kind_name_literals(
            source, module="m.py", kind_names=names,
        ) == [], "the set scanner is supposed to be blind here — that is the point"


def test_the_occurrence_scanner_ignores_prose():
    """A docstring that mentions a Kind is documentation, not knowledge the
    runtime acts on. Without this the count would be dominated by the comments
    explaining why the count exists."""
    from dna.testing.kind_literal_scan import scan_kind_name_occurrences

    source = (
        '"""A module about Story and Issue.\n\nSecond line names Story again.\n"""\n'
        'def f():\n'
        '    """Docstring naming Issue."""\n'
        '    return "Story"\n'
    )
    uses = scan_kind_name_occurrences(
        source, module="m.py", kind_names={"Story", "Issue"})
    assert [u.kind for u in uses] == ["Story"]
    assert uses[0].lineno == 7


def test_the_occurrence_scanner_ignores_a_string_that_is_not_a_kind():
    """The oracle is the live registry, so the scanner has no vocabulary of its
    own to drift — the property the first ratchet was built around."""
    from dna.testing.kind_literal_scan import scan_kind_name_occurrences

    assert scan_kind_name_occurrences(
        'x = "Storybook"; y = "story"; z = "StoryPoint"',
        module="m.py", kind_names={"Story"}) == []


def test_a_planted_mutant_is_caught_by_the_ceiling(tmp_path):
    """MUTANT PROOF — the ceiling is only worth its docstring if a new literal
    actually trips it. Plant one in a throwaway tree and check the eye sees it,
    rather than trusting that it would."""
    from dna.testing.kind_literal_scan import scan_occurrences_in_tree

    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "m.py").write_text(
        '"""Prose about Story."""\ndef f(k):\n    return k\n', encoding="utf-8")
    assert scan_occurrences_in_tree(clean, kind_names={"Story", "Issue"}) == []

    (clean / "mutant.py").write_text(
        'def g(kernel, scope):\n    return kernel.query(scope, "Issue")\n',
        encoding="utf-8")
    caught = scan_occurrences_in_tree(clean, kind_names={"Story", "Issue"})
    assert [u.kind for u in caught] == ["Issue"]
    assert caught[0].module == "mutant.py"
