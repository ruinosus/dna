"""Every MCP tool that ACCEPTS a ``scope`` must hand it to ``_guard``.

The bug this pins was invisible to every behavioural test, because the code it
broke never ran: ``list_templates`` / ``get_template`` / ``list_skills`` /
``get_skill`` each declared a ``scope`` parameter, forwarded it to their impl,
and called ``_guard("definitions", tenant)`` **without** ``scope=scope``. The
guard's scope-binding step reads its ``scope`` argument — with ``None`` it is a
documented no-op — so the cross-workspace check simply did not happen. Measured:
a member of one workspace holding NO grant read another workspace's Skill.

Their four siblings (``compose_prompt``, ``list_agents``, ``list_tools``,
``get_tool``) passed it correctly, which is why this reads as a call-site
omission rather than a design gap — and why a source guard is the right shape.
A behavioural test would have to be written once per tool and would miss the
fifth tool somebody adds next month; this fails on the *pattern*.

Deliberately a source guard, not a runtime one: the failure mode is an argument
that is absent, and an absent argument has no runtime signature to assert on.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_DNA_CLI = Path(__file__).resolve().parents[1] / "dna_cli"
_SERVER = _DNA_CLI / "_mcp_server.py"

#: EVERY module that declares ``@server.tool`` functions, not just the one the
#: bug was found in. The face grew a second and third home for tools
#: (``register_document_tools``, ``register_kind_tools``) after this guard was
#: written, and a guard that reads one file while the tools live in three is a
#: fence around an empty field: ``list_my_kinds`` declares a ``scope`` and was
#: invisible here until this list existed. A module with no ``_guard(`` call in
#: it contributes nothing and costs nothing, so listing a file is always safe;
#: OMITTING one is what silently narrows the guard.
_SOURCES = [
    _SERVER,
    _DNA_CLI / "_mcp_kinds.py",
    _DNA_CLI / "_mcp_documents.py",
]

#: A tool body may legitimately omit ``scope=`` only if it takes no ``scope``.
#: Nothing is allowlisted today — if you add an entry, write why here.
_ALLOWLIST: dict[str, str] = {}


def _tool_bodies(src: str) -> dict[str, str]:
    """Map each ``@server.tool``-decorated function to ITS OWN body.

    Block-scoped on indentation rather than split on the decorator: a naive
    split leaves the final chunk running to end-of-file, which swept the
    `_graph_guard` pass-through wrapper into `forget`'s body and made this
    guard report a bug that was not there. Attributing code to the wrong
    function is exactly the failure a guard must not have.
    """
    lines = src.splitlines(keepends=True)
    bodies: dict[str, str] = {}
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("@server.tool"):
            # Find the def that this decorator introduces.
            j = i + 1
            while j < len(lines) and not re.match(r"\s*(async )?def \w+\(", lines[j]):
                j += 1
            if j >= len(lines):
                break
            m = re.match(r"(\s*)(?:async )?def (\w+)\(", lines[j])
            assert m is not None
            indent, name = len(m.group(1)), m.group(2)
            # Walk past the signature FIRST. A multi-line parameter list closes
            # with `) -> X:` sitting at the def's own indent, so a naive dedent
            # scan stops there and yields a body of just the signature — which
            # then contains no `_guard` call and reads as "clean". A guard that
            # passes by seeing nothing is worse than no guard, so track paren
            # depth and only start looking for the end once the def is closed.
            depth, k = 0, j
            while k < len(lines):
                depth += lines[k].count("(") - lines[k].count(")")
                if depth <= 0 and lines[k].rstrip().endswith(":"):
                    break
                k += 1
            # Now the body: until a non-blank line indented at or above the def.
            k += 1
            while k < len(lines):
                line = lines[k]
                if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                    break
                k += 1
            bodies[name] = "".join(lines[j:k])
            i = k
            continue
        i += 1
    return bodies


def test_every_tool_taking_a_scope_binds_it() -> None:
    bodies: dict[str, str] = {}
    for source in _SOURCES:
        assert source.exists(), f"{source} is listed in _SOURCES but is not there"
        bodies.update(_tool_bodies(source.read_text(encoding="utf-8")))
    assert bodies, "found no @server.tool functions — did the decorator change?"
    # The tools that live OUTSIDE _mcp_server.py are the ones this guard used to
    # miss entirely. Naming one pins that the list above is still reaching them:
    # a body-count assertion would keep passing if `_SOURCES` silently lost an
    # entry, because the other files still supply plenty of bodies.
    assert "list_my_kinds" in bodies, (
        "the Kind-authoring tools are no longer being read — check _SOURCES"
    )

    offenders: list[str] = []
    for name, body in bodies.items():
        if name in _ALLOWLIST:
            continue
        # Does this tool accept a scope argument at all?
        signature = body.split(") ->")[0]
        if not re.search(r"\bscope\s*:", signature):
            continue
        # It does. Every _guard CALL inside it must carry scope=.
        #
        # Two things deliberately excluded, each for a reason:
        #  • `_personal_guard` — the identity-keyed personal-memory seam. It
        #    resolves an oid, never a workspace, so scope-binding does not
        #    apply to it (ADR-personal-memory). The lookbehind drops it.
        #  • a `def _guard(...)` line — a nested helper's own signature is not
        #    a call, and matching it made this guard cry wolf on `forget`.
        for m in re.finditer(r"(?<![\w])_guard\((.*?)\)", body, re.S):
            line_start = body.rfind("\n", 0, m.start()) + 1
            if body[line_start:m.start()].lstrip().startswith("def "):
                continue
            if "scope=" not in m.group(1):
                offenders.append(f"{name}: _guard({m.group(1).strip()[:60]}…)")

    assert not offenders, (
        "these tools accept a `scope` but call _guard without passing it, so "
        "the cross-workspace scope-binding check never runs for them:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    "tool",
    ["list_templates", "get_template", "list_skills", "get_skill"],
)
def test_the_four_that_were_broken_stay_fixed(tool: str) -> None:
    """Name them explicitly, so a regression says which one and not just 'a tool'."""
    body = _tool_bodies(_SERVER.read_text(encoding="utf-8"))[tool]
    guards = re.findall(r"_guard\((.*?)\)", body, re.S)
    assert guards, f"{tool} no longer calls _guard at all"
    assert all("scope=" in g for g in guards), (
        f"{tool} calls _guard without scope= — it reads a caller-supplied scope "
        f"and would not check it against the caller's workspace"
    )
