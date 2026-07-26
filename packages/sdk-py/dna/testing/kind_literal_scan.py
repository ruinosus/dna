"""Find hardcoded Kind-name literals in source — the ratchet's eye.

The SDK keeps re-inventing "the set of Kinds that X applies to" as a literal
tuple in whichever module needed it. Thirteen such lists existed for the SDLC
work-item family alone, with thirteen different memberships; one of them carries
the tombstone of a rename that missed a sibling list and let ``Epic`` silently
inherit across scopes for a release. A declarative field is the cure, but a cure
nobody is forced to take does not get taken: ``embed_fields`` and
``version_retention`` both shipped as declarative fields and both had **zero**
adopters, because nothing failed when a new Kind ignored them.

So this module is the forcing function. It is not a linter's guess about what
"looks like" a Kind name — the oracle is the **live registry**: a literal
collection of two or more strings, *every one of which is a registered Kind
name*, is a hardcoded Kind-name set. That test has no vocabulary of its own to
drift, and it sees a new list the moment somebody writes one.

The paired test (``test_kind_name_literal_ratchet.py`` in each package) fails on
any finding that is not in an allowlist, and the allowlist carries **a reason per
entry** — an irreducible site says why it is irreducible, in the file, next to
its name. Entries may be removed, never added without an argument.

Deliberately NOT reported (they are not memberships):
  * a single-element literal — one name is a reference, not a set;
  * a mapping whose *values* are per-Kind data (``{"Story": ("created_at",)}``)
    is reported, because its KEYS are a membership;
  * a collection with any non-Kind string in it — the caller means something
    other than "these Kinds".
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Container, Iterable, Iterator

__all__ = [
    "KindLiteral",
    "scan_kind_name_literals",
    "scan_tree",
]


@dataclass(frozen=True)
class KindLiteral:
    """One hardcoded Kind-name collection found in source."""

    #: Path relative to the scanned root, POSIX-separated — stable across
    #: checkouts, which is what makes an allowlist key durable.
    module: str
    #: ``MODULE_CONSTANT`` for an assignment, or ``qualname::<inline>`` for a
    #: membership test written in place.
    symbol: str
    lineno: int
    members: tuple[str, ...]

    @property
    def key(self) -> str:
        """The allowlist key — path + symbol, deliberately WITHOUT the line
        number so an unrelated edit above never invalidates an entry."""
        return f"{self.module}::{self.symbol}"

    def describe(self) -> str:
        return (
            f"{self.module}:{self.lineno} {self.symbol} = "
            f"{', '.join(self.members)}"
        )


_LITERAL_NODES = (ast.Set, ast.List, ast.Tuple)
#: Calls whose single literal argument is still a Kind-name collection.
_WRAPPERS = frozenset({"frozenset", "set", "tuple", "list"})


def _string_members(node: ast.AST) -> tuple[str, ...] | None:
    """The string elements of ``node`` if it is a literal collection (possibly
    wrapped in ``frozenset(...)`` / ``set(...)``) of *only* strings, else None.

    A dict literal contributes its KEYS: ``{"Story": (...), "Issue": (...)}``
    is a per-Kind table, and its key set is exactly the membership the ratchet
    is looking for."""
    if isinstance(node, ast.Call):
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name in _WRAPPERS and len(node.args) == 1 and not node.keywords:
            return _string_members(node.args[0])
        return None
    if isinstance(node, ast.Dict):
        elts: Iterable[ast.expr | None] = node.keys
    elif isinstance(node, _LITERAL_NODES):
        elts = node.elts
    else:
        return None
    out: list[str] = []
    for elt in elts:
        if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
            return None
        out.append(elt.value)
    return tuple(out)


def _qualname(stack: list[str]) -> str:
    return ".".join(stack) if stack else "<module>"


class _Visitor(ast.NodeVisitor):
    def __init__(self, module: str, kind_names: Container[str], min_members: int):
        self.module = module
        self.kind_names = kind_names
        self.min_members = min_members
        self.found: list[KindLiteral] = []
        self._stack: list[str] = []

    # -- helpers ---------------------------------------------------------

    def _record(self, node: ast.AST, symbol: str, members: tuple[str, ...]) -> None:
        if len(members) < self.min_members:
            return
        if not all(m in self.kind_names for m in members):
            return
        self.found.append(
            KindLiteral(
                module=self.module,
                symbol=symbol,
                lineno=getattr(node, "lineno", 0),
                members=members,
            )
        )

    def _consider(self, node: ast.AST, symbol: str) -> None:
        members = _string_members(node)
        if members is not None:
            self._record(node, symbol, members)
        # A per-Kind TABLE hides its memberships in the values as well as the
        # keys (``{"sdlc.work-item": ("Story", "Issue", ...)}`` keys on traits
        # and lists Kinds). Looking only at the outer literal would let the
        # biggest tables through.
        inner = node.args[0] if (
            isinstance(node, ast.Call) and len(node.args) == 1
        ) else node
        if isinstance(inner, ast.Dict):
            for key, value in zip(inner.keys, inner.values):
                if isinstance(key, ast.Constant):
                    label = repr(key.value)
                elif isinstance(key, ast.Name):
                    label = key.id      # a table keyed on a named constant
                elif isinstance(key, ast.Attribute):
                    label = key.attr
                else:
                    label = "?"
                nested = _string_members(value)
                if nested is not None:
                    self._record(value, f"{symbol}[{label}]", nested)

    # -- scopes ----------------------------------------------------------

    def _scoped(self, node: ast.AST, name: str) -> None:
        self._stack.append(name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._scoped(node, node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._scoped(node, node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self._scoped(node, node.name)

    # -- the two shapes --------------------------------------------------

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        for target in node.targets:
            name = getattr(target, "id", None) or getattr(target, "attr", None)
            if name:
                prefix = _qualname(self._stack)
                symbol = name if prefix == "<module>" else f"{prefix}.{name}"
                self._consider(node.value, symbol)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        name = getattr(node.target, "id", None) or getattr(node.target, "attr", None)
        if name and node.value is not None:
            prefix = _qualname(self._stack)
            symbol = name if prefix == "<module>" else f"{prefix}.{name}"
            self._consider(node.value, symbol)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.In, ast.NotIn)):
                self._consider(comparator, f"{_qualname(self._stack)}::<inline>")
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:  # noqa: N802
        self._consider(node.iter, f"{_qualname(self._stack)}::<loop>")
        self.generic_visit(node)


def scan_kind_name_literals(
    source: str, *, module: str, kind_names: Container[str], min_members: int = 2,
) -> list[KindLiteral]:
    """Every hardcoded Kind-name collection in one Python ``source``."""
    visitor = _Visitor(module, kind_names, min_members)
    visitor.visit(ast.parse(source))
    return visitor.found


def scan_tree(
    root: Path, *, kind_names: Container[str], min_members: int = 2,
    skip_dirs: Iterable[str] = ("__pycache__", ".venv", "tests"),
) -> list[KindLiteral]:
    """Scan every ``*.py`` under ``root`` (recursively), sorted by key."""
    skip = set(skip_dirs)
    findings: list[KindLiteral] = []
    for path in _python_files(root, skip):
        rel = path.relative_to(root).as_posix()
        try:
            src = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover — unreadable file
            continue
        try:
            findings.extend(
                scan_kind_name_literals(
                    src, module=rel, kind_names=kind_names, min_members=min_members,
                )
            )
        except SyntaxError:  # pragma: no cover — a file this interpreter cannot parse
            continue
    findings.sort(key=lambda f: (f.module, f.lineno, f.symbol))
    return findings


def _python_files(root: Path, skip: set[str]) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if any(part in skip for part in path.relative_to(root).parts[:-1]):
            continue
        yield path
