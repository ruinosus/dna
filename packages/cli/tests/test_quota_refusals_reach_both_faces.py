"""Every refusal ``dna_cli._mcp_quota`` can raise reaches the caller, on BOTH faces.

The metered-call policy is ONE core (``enforce_plan``) with TWO callers — the
MCP ``_guard`` and the REST ``_plan_gate`` — and each caller keeps only the
transport mapping, by hand::

    except (OverQuotaError, FeatureNotInPlanError, MemoryModeError, ...) as exc:

That hand-written tuple is the defect this file exists to make impossible.
Declaring a new refusal in the shared core does not update it, nothing goes
red, and the refusal escapes as whatever the transport does with an unhandled
exception — a 500 on REST, ``Error calling tool 'x'`` on MCP. It is precisely
the failure ``dna.kernel.errors.KernelRefusal`` was created to end one layer
down, and it was LIVE here when this file was written: ``InstanceModeError``
had been declared and wired into the MCP ``_guard``, and REST's ``_plan_gate``
— which reaches it through ``family_op`` on the generic write — had never
named it. A plan omitting ``definitions_mode`` refused a REST generic write
with a 500 instead of the 403 whose message names the missing cap.

**So this guard enumerates nothing.** Both halves are derived:

* the refusal set, from the CLASSES ``_mcp_quota`` itself declares — a type
  added to that module tomorrow is in scope the moment the ``class`` statement
  exists;
* the relay set, from each face's own AST — the names it catches in a handler
  that RAISES, resolved to classes through the module.

A refusal counts as relayed when the face names IT or one of its ANCESTORS,
because inheriting is a legitimate — and here deliberate — way to be relayed:
``MarginBreakerTripped`` extends ``OverQuotaError`` and
``MarginBreakerUnreadable`` extends ``TierRegistryUnavailableError`` exactly so
that faces written before the margin breaker existed relay it correctly with
no tuple to widen. This guard is what keeps that claim true: re-parent either
one onto a base no face names and it fails here.

WHAT IT DOES NOT PROVE, said plainly so it is not read as more than it is: it
is a claim about TYPES and NAMED handlers. It shows the face names the refusal
somewhere, not that the particular route which raises it flows through that
somewhere — and if BOTH faces forget a refusal, both halves are silent
together. Its sibling ``test_face_refusal_parity.py`` makes the same trade for
the kernel's refusals; this one covers the family that file does not reach,
because the quota exceptions live in ``dna_cli`` and never touch the kernel.
"""
from __future__ import annotations

import ast
import builtins
import importlib
import inspect
import pathlib

import pytest

from dna_cli import _mcp_quota as Q

_FACE = pathlib.Path(__file__).resolve().parents[1] / "dna_cli"

#: The two faces that run the shared metered-call core. Each is (file, module):
#: the module resolves a caught NAME that the file imported.
_FACES = (
    ("_mcp_server.py", "dna_cli._mcp_server"),
    ("_rest_api.py", "dna_cli._rest_api"),
)


def _quota_refusals() -> dict[str, type]:
    """Every exception class ``_mcp_quota`` DECLARES, by name.

    Derived from the module, not listed. ``__module__`` filters out the
    builtins and the re-exports it merely imports, so the set is "what this
    policy can raise on its own behalf" — which is exactly the set a face has
    to be able to relay.
    """
    return {
        name: obj
        for name, obj in vars(Q).items()
        if inspect.isclass(obj)
        and issubclass(obj, BaseException)
        and obj.__module__ == Q.__name__
    }


def _caught_names(handler: ast.ExceptHandler) -> list[str]:
    caught = handler.type
    if isinstance(caught, ast.Name):
        return [caught.id]
    if isinstance(caught, ast.Tuple):
        return [e.id for e in caught.elts if isinstance(e, ast.Name)]
    return []


def _imported_names(tree: ast.AST) -> dict[str, str]:
    """``from X import NAME`` at ANY scope → ``{"NAME": "X"}``.

    At any scope because both faces import the quota symbols INSIDE the
    function that builds the server (the whole MCP surface is lazily imported
    so a base SDK install never carries FastMCP). A resolver that read only
    module globals would resolve every quota name to nothing and report the
    faces as relaying nothing at all — noise, which gets a guard muted.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                out[alias.asname or alias.name] = node.module
    return out


def _resolve(name: str, *, module, imports: dict[str, str]) -> type | None:
    for source in (module, importlib.import_module(imports[name]) if name in imports else None):
        obj = getattr(source, name, None) if source is not None else None
        if inspect.isclass(obj) and issubclass(obj, BaseException):
            return obj
    obj = getattr(builtins, name, None)
    if inspect.isclass(obj) and issubclass(obj, BaseException):
        return obj
    return None


def _relayed_by(face_file: str, face_module: str) -> set[type]:
    """The exception classes this face names in a handler that RAISES.

    A handler counts only if it raises something: ``except X: pass`` and a bare
    ``raise`` that re-throws an already-honest error are not translations, and
    counting them makes every gap disappear.

    ``Exception`` is dropped. A catch-all in one door must not buy coverage on
    behalf of a door it does not sit in — the lesson
    ``test_face_refusal_parity`` paid for and states in its own docstring.
    """
    tree = ast.parse((_FACE / face_file).read_text())
    imports = _imported_names(tree)
    module = importlib.import_module(face_module)
    out: set[type] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not any(
            isinstance(sub, ast.Raise) and sub.exc is not None
            for sub in ast.walk(node)
        ):
            continue
        for name in _caught_names(node):
            if name == "Exception":
                continue
            cls = _resolve(name, module=module, imports=imports)
            if cls is not None:
                out.add(cls)
    return out


# ── the blindness check, first ─────────────────────────────────────────────


def test_the_derivation_itself_still_sees_something():
    """A scan that resolves nothing passes vacuously, and every guard this
    house lost was lost that way: still running, still green, no longer
    looking. These floors are numbers a working scan clears easily and a broken
    one cannot reach."""
    refusals = _quota_refusals()
    assert len(refusals) >= 6, sorted(refusals)
    for face_file, face_module in _FACES:
        relayed = _relayed_by(face_file, face_module)
        assert len(relayed) >= 4, (face_file, sorted(c.__name__ for c in relayed))


# ── the guard ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("face_file,face_module", _FACES)
def test_every_quota_refusal_is_relayed_by_this_face(face_file, face_module):
    """The property the shared core actually depends on: whatever
    ``enforce_plan`` raises, this face turns into an honest client error.

    Ancestors count — that is what subclassing a relayed type BUYS, and the
    margin breaker (i-134) is built on it deliberately."""
    relayed = _relayed_by(face_file, face_module)
    missing = sorted(
        name
        for name, cls in _quota_refusals().items()
        if not any(issubclass(cls, caught) for caught in relayed)
    )
    assert not missing, (
        f"{face_file} never names {missing} (nor any ancestor of them) in a "
        f"handler that raises — a refusal the shared metered-call core can "
        f"produce would escape this face as an unhandled exception"
    )


def test_the_margin_breaker_rides_the_bases_its_docstrings_claim():
    """The i-134 design claim, pinned where re-parenting it goes red.

    Both new refusals are relayed by faces written BEFORE they existed, and
    that is not luck: it is inheritance from the two types every face already
    named. Detach either and the faces above lose it — this assertion is the
    one that says WHY, so the failure above is not read as "just add it to the
    tuple"."""
    assert issubclass(Q.MarginBreakerTripped, Q.OverQuotaError)
    assert issubclass(Q.MarginBreakerUnreadable, Q.TierRegistryUnavailableError)
    # And the fail-safe is NOT a PermissionError: the caller did nothing wrong,
    # the deployment cannot decide. Faces map that to 503, never to a denial.
    assert not issubclass(Q.MarginBreakerUnreadable, PermissionError)
