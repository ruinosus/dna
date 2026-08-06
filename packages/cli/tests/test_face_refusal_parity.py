"""Whatever REST refuses HONESTLY, the MCP face must refuse honestly too.

The defect this exists to stop is not "``AsOfUnsupported`` was missing". It is
the SHAPE of that miss: a refusal is declared once, mapped on the face somebody
happened to be looking at, and the other face keeps working — right up to the
moment a client asks the question the mapping was for and gets a masked failure
instead of the answer the documentation promised. It has happened repeatedly in
this repo, on both faces, and every time the ENUMERATION was what went stale.

**So this guard enumerates nothing.** Both halves are read out of source:

* the REST refusal map — every ``except X`` in ``_rest_api.py`` that raises an
  ``HTTPException`` with a status code, from the file's own AST;
* the MCP translations — every ``except`` in the face's modules that raises,
  with caught names resolved through the module, so a tuple constant
  (``WRITE_REFUSALS`` / ``NO_REGISTRY`` / ``CAPABILITY_REFUSALS``) counts as the
  types it holds, which is what it means at runtime.

⚠️ THE UNIT OF MEASUREMENT IS THE POINT, AND THE FIRST VERSION OF THIS FILE GOT
IT WRONG. It asked "does ANY handler anywhere on the MCP face catch this type?"
and passed — on the exact build where ``recall(as_of=…)`` reached the client
masked. The reason is instructive rather than embarrassing: ``_mcp_portfolio``
catches ``(Exception,)`` on purpose, with a long and correct docstring about why
naming ``type(exc).__name__`` beats enumerating a hierarchy somebody else owns.
A catch-all in one door made every other door look covered. **A guard whose
scope is "the face" cannot see a hole in one relay.** So the sharp assertion
below counts only handlers that catch a refusal BY NAME, and a catch-all buys
nothing on behalf of a door it does not sit in.

WHY 501 AND 410 ARE THE FILTER, and not a list of type names. The ports
catalogue's contract is about CAPABILITY: the store wired into this deployment
cannot produce the answer, and the alternative to refusing is a confident lie
(``[]`` reading as *nothing points here*; today's instance under a past
timestamp; ``LookupError`` reading as *it never existed*). REST already spells
that distinction in its own status codes — **501** for *this deployment cannot*,
**410** for *it could, and that stretch of history is gone* — so the set of
capability refusals is DERIVED from REST's source instead of copied into this
file. A fifth one mapped to 501 tomorrow is in scope the moment the route is
written.

WHAT THIS STILL DOES NOT PROVE, stated because a guard read as stronger than it
is does more harm than none. It is a claim about TYPES and NAMED handlers, not
about tools: it shows the face names a given refusal somewhere, not that the
particular tool which can raise it routes through that somewhere. And if BOTH
faces forget a refusal, both halves stay silent — the direction "a new exception
must be classified at all" belongs to
``sdk-py/tests/test_kernel_refusal_base.py``, and this is its cross-face
sibling, not its replacement.

THE FIX THIS GUARD WAS STANDING IN FOR, AND WHAT IT GUARDS NOW. ``KernelRefusal``
made the verdict-shaped refusals derivable with one ``except``. The
capability-shaped ones had no such base — they inherit from ``RuntimeError`` /
``NotImplementedError`` / ``LookupError`` and scatter across the builtin
hierarchy — so ``dna_cli._mcp_refusals`` held a hand-written tuple of four, and
a hand-written tuple is exactly what this file distrusts. That tuple is now ONE
name: ``dna.kernel.errors.CapabilityRefusal``, sibling to ``KernelRefusal``,
which the four inherit additively.

Which MOVES this guard's job rather than ending it. The face can no longer go
stale by forgetting to widen a tuple; it can go stale one level up, if a new
capability refusal is declared without the base. So
``test_every_rest_capability_refusal_carries_the_marker_base`` walks from the
same REST source as everything else here and requires the base of whatever REST
answers 501/410 with. Same derivation, same direction, one rung higher.
"""
from __future__ import annotations

import ast
import builtins
import collections
import importlib
import inspect
import pathlib
import pkgutil
import warnings

import pytest

_FACE = pathlib.Path(__file__).resolve().parents[1] / "dna_cli"
_REST = _FACE / "_rest_api.py"

#: The MCP face, as files. Derived from the naming convention the face already
#: uses (``_mcp_*.py``) plus the one tool module that lives in a subpackage, so
#: a new ``_mcp_something.py`` is in scope the moment it exists.
_MCP_FILES = sorted(_FACE.glob("_mcp_*.py")) + [_FACE / "graph" / "_tools.py"]

#: The statuses REST uses to say *this deployment cannot answer that*. See the
#: module docstring: this is the derivation that replaces a list of type names.
_CAPABILITY_STATUSES = frozenset({501, 410})


# ── resolving a NAME to a class, without a hand-written table ───────────────


def _exception_index() -> dict[str, type]:
    """Every exception class declared under ``dna`` / ``dna_cli``, by name.

    Walked, not listed — same reasoning as ``test_kernel_refusal_base``'s
    ``_kernel_modules``: a table of modules cannot see the module added after it
    was written, and a resolver that silently fails to resolve is a guard that
    silently stops guarding.
    """
    out: dict[str, type] = {}
    for name in dir(builtins):
        obj = getattr(builtins, name)
        if inspect.isclass(obj) and issubclass(obj, BaseException):
            out.setdefault(name, obj)
    for pkgname in ("dna", "dna_cli"):
        pkg = importlib.import_module(pkgname)
        modules = [pkg]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for info in pkgutil.walk_packages(pkg.__path__, pkgname + "."):
                try:
                    modules.append(importlib.import_module(info.name))
                except Exception:  # noqa: BLE001 — an optional extra is absent
                    continue
        for module in modules:
            for name, obj in vars(module).items():
                if inspect.isclass(obj) and issubclass(obj, BaseException):
                    out.setdefault(name, obj)
    return out


def _tuple_constants(tree: ast.AST) -> dict[str, list[str]]:
    """``NAME = (A, B, C)`` anywhere in the file → ``{"NAME": ["A", "B", "C"]}``.

    At ANY scope on purpose. ``_mcp_server``'s ``_REFUSALS`` and
    ``_mcp_portfolio``'s ``REFUSALS`` are both defined inside the registration
    function, and a resolver that only saw module level would read those two
    doors as translating nothing — a false GAP, which trains people to ignore
    the guard, which is worse than a false pass.

    Starred elements (``*CAPABILITY_REFUSALS``) are followed, because that is
    what splicing one tuple into another means at runtime.
    """
    out: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Tuple):
            continue
        names: list[str] = []
        for element in node.value.elts:
            inner = element.value if isinstance(element, ast.Starred) else element
            if isinstance(inner, ast.Name):
                names.append(inner.id)
        for target in node.targets:
            if isinstance(target, ast.Name):
                out[target.id] = names
    return out


def _imported_names(tree: ast.AST) -> dict[str, str]:
    """``from X import NAME`` anywhere in the file → ``{"NAME": "X"}``.

    At ANY scope, and this one is not a nicety. The face imports
    ``CAPABILITY_REFUSALS`` inside the function that uses it (the whole MCP
    surface is lazily imported so the base SDK install never carries FastMCP),
    so a resolver that only consulted module globals resolved the name to
    nothing — and "resolved to nothing" is indistinguishable, in a naive scan,
    from "this face catches nothing". Measured: without this the guard failed on
    the FIXED code, naming the very refusals the fix had just wired up. A
    resolver that cannot see the code's own idiom reports noise, and a guard
    that reports noise gets muted.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                out[alias.asname or alias.name] = node.module
    return out


def _resolve(name: str, *, module, constants: dict[str, list[str]],
             imports: dict[str, str], index) -> list[type]:
    """A caught NAME → the exception classes it stands for at runtime."""
    if name in constants:
        resolved: list[type] = []
        for inner in constants[name]:
            resolved.extend(_resolve(
                inner, module=module, constants=constants,
                imports=imports, index=index))
        return resolved
    obj = getattr(module, name, None) if module is not None else None
    if obj is None and name in imports:
        try:
            obj = getattr(importlib.import_module(imports[name]), name, None)
        except Exception:  # noqa: BLE001 — an optional extra is absent
            obj = None
    if obj is None:
        obj = index.get(name)
    if obj is None:
        return []
    if isinstance(obj, tuple):
        return [c for c in obj if inspect.isclass(c) and issubclass(c, BaseException)]
    if inspect.isclass(obj) and issubclass(obj, BaseException):
        return [obj]
    return []


def _import(path: pathlib.Path):
    rel = path.relative_to(_FACE).as_posix()[: -len(".py")].replace("/", ".")
    try:
        return importlib.import_module("dna_cli." + rel)
    except Exception:  # noqa: BLE001 — an optional extra is absent
        return None


def _caught_names(handler: ast.ExceptHandler) -> list[str]:
    caught = handler.type
    if isinstance(caught, ast.Name):
        return [caught.id]
    if isinstance(caught, ast.Tuple):
        return [e.id for e in caught.elts if isinstance(e, ast.Name)]
    return []


# ── half 1: the REST refusal map, read out of REST's own source ────────────


def _rest_refusal_map() -> dict[str, set[int]]:
    tree = ast.parse(_REST.read_text())
    found: dict[str, set[int]] = collections.defaultdict(set)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        codes = {
            keyword.value.value
            for sub in ast.walk(node)
            if isinstance(sub, ast.Call) and getattr(sub.func, "id", None) == "HTTPException"
            for keyword in sub.keywords
            if keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant)
        }
        for name in _caught_names(node):
            found[name] |= codes
    # ``Exception`` is REST's catch-all, not a refusal it names.
    return {name: codes for name, codes in found.items() if codes and name != "Exception"}


def _rest_capability_refusals() -> dict[str, set[int]]:
    """The subset REST answers with 501/410 — the catalogue's contract."""
    return {
        name: codes
        for name, codes in _rest_refusal_map().items()
        if codes & _CAPABILITY_STATUSES
    }


# ── half 2: what the MCP face translates ───────────────────────────────────


def _mcp_translations(*, named_only: bool) -> dict[type, set[str]]:
    """Exception class → the face files that turn it into a client-facing error.

    A handler counts only if it RAISES something: ``except Exception: pass`` and
    the bare ``raise`` that re-throws an already-honest ``ToolError`` are not
    translations, and counting them made every gap disappear.

    ``named_only`` drops any handler that reaches the type through bare
    ``Exception``. That is the sharp reading — see the module docstring — and it
    is the difference between a guard that fails on the defect and one that
    reports full parity while the defect ships.
    """
    index = _exception_index()
    out: dict[type, set[str]] = collections.defaultdict(set)
    for path in _MCP_FILES:
        tree = ast.parse(path.read_text())
        constants = _tuple_constants(tree)
        imports = _imported_names(tree)
        module = _import(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not any(
                isinstance(sub, ast.Raise) and sub.exc is not None
                for sub in ast.walk(node)
            ):
                continue
            for name in _caught_names(node):
                for cls in _resolve(name, module=module, constants=constants,
                                    imports=imports, index=index):
                    if named_only and cls is Exception:
                        continue
                    out[cls].add(path.name)
    return out


# ── the guard ──────────────────────────────────────────────────────────────


def test_the_derivation_itself_still_sees_something():
    """The blindness check, first — a scan that resolves nothing passes vacuously.

    Every guard this house lost was lost this way: it kept running, kept
    reporting green, and had stopped looking. These floors are numbers a working
    scan clears easily and a broken one cannot reach at all.
    """
    assert len(_rest_refusal_map()) > 20, "the REST scan stopped finding refusals"
    assert len(_rest_capability_refusals()) >= 3, "the 501/410 filter found almost nothing"
    assert len(_mcp_translations(named_only=True)) > 10, "the MCP scan stopped finding handlers"
    assert len(_MCP_FILES) > 5, _MCP_FILES


def test_every_rest_mapped_refusal_is_named_by_a_name_the_scan_can_resolve():
    """No refusal may be skipped for being unresolvable.

    Without this, a rename upstream would turn a real gap into a silent
    ``continue`` — the guard would go on passing while covering less.
    """
    index = _exception_index()
    unresolved = sorted(name for name in _rest_refusal_map() if name not in index)
    assert not unresolved, (
        f"the REST face maps {unresolved}, which this guard cannot resolve to a "
        "class — it is not skipping them, it is telling you it went partly blind"
    )


def _rest_local(cls: type) -> bool:
    """Declared inside the REST module = that face's own vocabulary.

    ``MemoryNotFound`` is constructed by a REST route and by nothing else, so no
    MCP tool can raise it. Derived from where the class lives, not from a list.
    """
    return cls.__module__ == "dna_cli._rest_api"


@pytest.mark.parametrize("name", sorted(_rest_capability_refusals()))
def test_the_mcp_face_names_every_capability_refusal_rest_maps(name):
    """THE sharp assertion: a 501/410 refusal must be caught BY NAME on MCP.

    ``AsOfUnsupported`` failed here. REST answered **501** — "this deployment
    keeps no history" — and no MCP handler caught a ``RuntimeError`` by name, so
    ``recall(as_of=…)`` reached the client as FastMCP's ``Error calling tool
    'recall'``: under ``mask_error_details`` with no reason at all, and even at
    the default with the type name — the part an agent acts on — stripped off.
    """
    index = _exception_index()
    cls = index[name]
    if _rest_local(cls):
        pytest.skip(f"{name} is declared in the REST face itself")

    translations = _mcp_translations(named_only=True)
    hits = sorted(
        {base.__name__ for base, _ in translations.items() if issubclass(cls, base)}
    )
    assert hits, (
        f"REST maps {name} -> HTTP {sorted(_rest_capability_refusals()[name])}, but "
        f"no MCP handler catches it by name ({name} inherits from "
        f"{cls.__mro__[1].__name__}). Over MCP the client gets a masked failure "
        "with no cause and no remedy. Its home is "
        "dna_cli._mcp_refusals.CAPABILITY_REFUSALS — 'this deployment cannot "
        "answer that at all' — which _refusing() already splices in."
    )


@pytest.mark.parametrize("name", sorted(_rest_refusal_map()))
def test_every_rest_mapped_refusal_reaches_the_mcp_client_somehow(name):
    """The wider, weaker half: nothing REST refuses may be wholly unhandled here.

    Catch-alls DO count in this one, deliberately. ``_mcp_portfolio`` catches
    ``(Exception,)`` and names the type in the message — a decision it argues
    for at length and which this guard has no business overruling. What it must
    not do is stand in for a door it does not sit in, which is why the test
    above exists and refuses to count it.
    """
    index = _exception_index()
    cls = index[name]
    if _rest_local(cls):
        pytest.skip(f"{name} is declared in the REST face itself")

    translations = _mcp_translations(named_only=False)
    assert any(issubclass(cls, base) for base in translations), (
        f"REST maps {name} -> HTTP {sorted(_rest_refusal_map()[name])}; the MCP "
        "face has no handler that catches it at all."
    )


def test_the_capability_refusals_tuple_is_relayed_by_the_face():
    """The catalogue walked inward, so the tuple cannot rot from its own end.

    The parity tests walk from REST. This one walks from
    ``CAPABILITY_REFUSALS``, so a name added there and wired nowhere is red too
    — a tuple nobody catches is documentation, not a mapping.
    """
    from dna_cli._mcp_refusals import CAPABILITY_REFUSALS

    translations = _mcp_translations(named_only=True)
    missing = [
        cls.__name__
        for cls in CAPABILITY_REFUSALS
        if not any(issubclass(cls, base) for base in translations)
    ]
    assert not missing, f"declared in CAPABILITY_REFUSALS, relayed by nothing: {missing}"


@pytest.mark.parametrize("name", sorted(_rest_capability_refusals()))
def test_every_rest_capability_refusal_carries_the_marker_base(name):
    """The guard that lets the face stop enumerating — derived from REST's own AST.

    ``CAPABILITY_REFUSALS`` is ONE name now
    (``dna.kernel.errors.CapabilityRefusal``) instead of the four it started as,
    and a collapse like that is only safe if something keeps the base COMPLETE.
    This is that something, and it deliberately walks from the same place the
    tests above do: whatever REST answers **501/410** with — its own signature
    for *this deployment cannot* — must carry the marker base, or the MCP face's
    single ``except`` silently stops covering it.

    Note what this refuses to be: a list of type names. A fifth refusal mapped
    to 501 tomorrow is in scope the moment somebody writes the route, and it is
    red HERE — at the declaration — rather than in a client's log.
    """
    from dna.kernel.errors import CapabilityRefusal

    index = _exception_index()
    cls = index[name]
    if _rest_local(cls):
        pytest.skip(f"{name} is declared in the REST face itself")

    assert issubclass(cls, CapabilityRefusal), (
        f"REST answers {name} with HTTP "
        f"{sorted(_rest_capability_refusals()[name])} — 'this deployment cannot "
        f"answer that' — but {name} does not inherit CapabilityRefusal. The MCP "
        "face catches that ONE base, so this refusal reaches an agent as a "
        "masked failure. Give it the base (additively, keeping its builtin one) "
        "rather than re-growing a per-face list."
    )
