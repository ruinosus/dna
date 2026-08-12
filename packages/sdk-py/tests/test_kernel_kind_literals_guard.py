"""s-kernel-promise-honest — the kernel's Kind literals are a RATCHET.

README/AGENTS.md used to promise "a microkernel that itself knows no
Kinds". Measured, that was false: the kernel names Kinds in plain string
literals in a dozen places — scope-inheritance defaults, the registry
accessor's commercial lookups, the evidence write path, the boot event
map. The promise was rewritten to what is true (a small set of BUILT-IN
Kinds, everything else by descriptor) and this guard is what stops the
gap widening again.

⭐ WHY THE GUARD IS DERIVED, NOT ENUMERATED

The vocabulary of "what counts as a Kind name" comes from
``Kernel.auto()`` — the live registry, every discoverable extension
loaded. Nobody maintains a list of Kind names here. Register a Kind
called ``Sprocket`` tomorrow and the day the kernel says ``"Sprocket"``
this guard fails, with no edit to this file.

That is deliberate and it is the whole point. This repo has shipped
guards that were green because they enumerated what to look for and the
list went stale (see the sibling suites' notes on enumeration vs
derivation). An enumerated list of Kind names would go stale the same
way: the ONE case it must catch — a Kind nobody thought of when the list
was written — is exactly the case it would miss.

The scanned surface is derived too: the whole ``dna/kernel`` package
tree, not a list of files. A new kernel module is covered on creation.

⭐ IT RATCHETS IN BOTH DIRECTIONS

- A pair in the code but NOT in the baseline fails: the kernel learned a
  Kind it did not know.
- A pair in the baseline but NOT in the code fails too: someone did the
  work of removing a literal and the baseline must record the win. A
  baseline that only ever grows is a budget, not a ratchet.

Fixing a violation means one of: move the knowledge into the extension
that registers the Kind, derive it from a declared trait, or — if it is
genuinely structural — add it to the baseline WITH a reason in the PR.

⛔ What this guard does NOT claim: that the kernel is Kind-agnostic. It
is not, and the docs now say so. The guard measures the size of the lie
and refuses to let it grow quietly.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from dna.kernel import Kernel

KERNEL_ROOT = pathlib.Path(__file__).parent.parent / "dna" / "kernel"
PKG_ROOT = pathlib.Path(__file__).parent.parent
BASELINE = pathlib.Path(__file__).parent / "goldens" / "kernel_kind_literals.json"


def _derived_vocabulary() -> set[str]:
    """Every Kind name the live registry knows — the DERIVED half.

    ``Kernel.auto()`` loads every extension discoverable through the
    ``dna.extensions`` entry-point group, so this set grows by itself as
    Kinds are added. It is never written down.
    """
    return {kp.kind for kp in Kernel.auto()._kinds.values()}


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """ids of the Constant nodes that are docstrings.

    Prose is excluded on purpose: a docstring that NAMES a Kind is
    documentation, not coupling. Only literals the interpreter can act on
    count as the kernel "knowing" a Kind. (Comments never reach the AST,
    so they need no handling.)
    """
    out: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _scan(vocab: set[str]) -> set[tuple[str, str]]:
    """(kind, path) pairs for every executable string literal in the
    kernel tree whose value is a registered Kind name."""
    found: set[tuple[str, str]] = set()
    for py in sorted(KERNEL_ROOT.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        skip = _docstring_nodes(tree)
        rel = str(py.relative_to(PKG_ROOT))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or id(node) in skip:
                continue
            if isinstance(node.value, str) and node.value in vocab:
                found.add((node.value, rel))
    return found


def _load_baseline() -> set[tuple[str, str]]:
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    return {(k, p) for k, paths in data["pairs"].items() for p in paths}


def test_the_derived_vocabulary_is_actually_populated():
    """Fail loud if the registry came up empty or near-empty.

    Without this, a boot failure or a stripped-down install would make
    the vocabulary tiny, the scan find nothing, and the guard pass while
    measuring NOTHING — the green-because-blind failure mode this repo
    has hit before. The floor is deliberately far below the real count
    (89 at authoring time) so it tracks "the registry booted", not "the
    registry has exactly N Kinds", which would be enumeration again.
    """
    vocab = _derived_vocabulary()
    assert len(vocab) >= 40, (
        f"only {len(vocab)} Kinds registered — the extension registry did not "
        f"boot properly, so this guard would scan against an empty vocabulary "
        f"and pass blind. Got: {sorted(vocab)}"
    )
    # Structural Kinds that exist with zero extensions installed.
    assert {"Genome", "KindDefinition", "LayerPolicy"} <= vocab


def test_no_new_kind_literal_enters_the_kernel():
    """The ratchet. New (kind, file) pair → fail."""
    vocab = _derived_vocabulary()
    found = _scan(vocab)
    baseline = _load_baseline()

    new = sorted(found - baseline)
    assert not new, (
        "The kernel just learned about Kind(s) it did not know before.\n\n"
        + "\n".join(f"  {kind!r} now appears in {path}" for kind, path in new)
        + "\n\nThe kernel is meant to hold a SMALL, closed set of built-in "
        "Kinds; everything else arrives by descriptor from the extension "
        "that registers it. Before widening the baseline, try:\n"
        "  1. move the knowledge into that extension;\n"
        "  2. derive it from a declared trait on the Kind (the way scope "
        "inheritance should work) instead of naming the Kind;\n"
        "  3. if it is genuinely structural (bootstrap Kinds that must be "
        "known before any descriptor can parse), add it to "
        f"{BASELINE.name} in this PR and say why."
    )


def test_the_baseline_tightens_when_a_literal_is_removed():
    """The other direction. A baseline that only grows is a budget.

    If you removed a Kind literal from the kernel — good — this fails
    until the baseline records it, so the ceiling comes down with the
    code and can never be re-spent silently.
    """
    vocab = _derived_vocabulary()
    found = _scan(vocab)
    baseline = _load_baseline()

    # Only judge Kinds the registry currently knows: if an optional
    # extension is not installed its Kinds leave the vocabulary, and its
    # baseline rows would look "removed" without any code changing.
    stale = sorted(p for p in (baseline - found) if p[0] in vocab)
    assert not stale, (
        "These Kind literals are in the baseline but no longer in the code:\n\n"
        + "\n".join(f"  {kind!r} no longer in {path}" for kind, path in stale)
        + f"\n\nThat is progress — record it by removing these rows from "
        f"{BASELINE.name}. The baseline is a ratchet, not a budget: "
        "unspent room must be given back, or the next widening spends it "
        "without anyone deciding to."
    )


@pytest.mark.parametrize("kind", ["Genome", "KindDefinition", "LayerPolicy"])
def test_the_bootstrap_kinds_are_the_reason_the_promise_had_to_change(kind):
    """These three CANNOT be moved out, and that is why the docs now say
    "a small set of built-in Kinds" instead of "no Kinds".

    A descriptor-declared Kind is read from an instance; reading an
    instance requires knowing the scope (``Genome``), the layer policy
    (``LayerPolicy``) and how to parse a Kind (``KindDefinition``). You
    cannot derive from a descriptor the rules for loading descriptors.
    Any future attempt at full agnosticism has to answer this first —
    it is a chicken-and-egg, not an unfinished refactor.
    """
    vocab = _derived_vocabulary()
    assert kind in vocab
    found = {k for k, _ in _scan(vocab)}
    assert kind in found, (
        f"{kind} vanished from the kernel's literals. If that is real, the "
        "bootstrap argument in the docs is now wrong and the promise can be "
        "strengthened — update docs/concepts/thesis.md and AGENTS.md too."
    )
