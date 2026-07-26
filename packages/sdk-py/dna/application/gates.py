"""Methodology gates — the project's own discipline, where BOTH faces reach it.

``dna sdlc story create`` refuses without acceptance criteria and a definition of
done. ``dna sdlc story done`` refuses without a passing product TestRun. Those
refusals were the CLI's, and only the CLI's: the MCP ``set_status(Story,"done")``
tool wrote straight through, and ``create_story`` accepted a Story with neither
AC nor DoD. As the MCP face becomes the primary write path, a gate that only one
face enforces is not a gate — it is a speed bump next to an open door.

So the gates live here, in the transport-agnostic core both faces already call
(``dna.application.sdlc``), and the CLI delegates to them rather than owning
them. Same refusal, same message, same escape hatches, whichever door you came
through.

**Which gates are genuinely CLI-only, and why they stayed there.** Three, all of
them because their evidence does not exist off the workstation:

* the ``prepare-commit-msg`` git hook that stamps ``Work-Item:`` trailers —
  it runs inside a git checkout, on a commit that has no representation over the
  wire;
* ``.dna/active-story.txt``, the FOCUS pointer — a file on the developer's disk;
  the hosted face has no shared filesystem to read it from (which is why
  ``_post_start_beat`` exists to mirror it over the API);
* the ``review`` PR guard (``gh pr list --head <branch>``) — it asks about the
  git branch the caller is standing on, and an MCP caller is not standing on one.

**Escapes are registered, not silent.** ``--allow-no-tests`` said "use only for
registered exceptions" and then recorded nothing. Here, exercising an escape
requires a reason, and the reason lands on the document's timeline as an
``exception`` event. An escape hatch you can audit is a hatch; one you cannot is
a hole.
"""
from __future__ import annotations

from typing import Any, Iterable

__all__ = [
    "GATE_EXIT_CRITERIA",
    "GATE_TEST_ON_CLOSE",
    "MethodologyRefusal",
    "closing_warnings",
    "has_narration_since_last_status_change",
    "has_passing_product_run",
    "kind_is_gated",
    "narration_warnings",
    "produces_warnings",
    "refuse_close_without_tests",
    "refuse_without_exit_criteria",
    "shipping_warnings",
]

#: A Kind carrying this trait refuses a create with no acceptance criteria and
#: no definition of done. Declared on Story — exactly what the CLI gates today.
GATE_EXIT_CRITERIA = "sdlc.exit-criteria-required"

#: A Kind carrying this trait refuses a close with no passing PRODUCT TestRun.
GATE_TEST_ON_CLOSE = "sdlc.test-gated"

#: Statuses that CLOSE a gated work item. A close is what the test gate guards:
#: "done" means shipped and accepted, and accepted means somebody ran it.
CLOSING_STATUSES: frozenset[str] = frozenset({"done", "resolved", "answered"})


class MethodologyRefusal(ValueError):
    """A write was refused by a methodology gate, not by a schema.

    A ``ValueError`` so every face that already maps ``ValueError`` to an honest
    client-facing denial (the MCP ``_refusing`` context manager, the REST error
    mapper, the CLI's ``fail``) carries it through with no new wiring. The
    message always names the gate, what is missing, and how to satisfy it — a
    refusal that does not say what to do instead just buys another guess."""


def kind_is_gated(kernel: Any, kind: str, gate: str) -> bool:
    """Whether ``kind`` declares ``gate``.

    Declarative on purpose: the CLI gated the literal string ``"Story"``, so a
    second Kind that deserved the same discipline would have had to be added to
    a branch nobody would think to look for. Now a Kind opts in by carrying the
    trait, and both faces see it at once."""
    try:
        return gate in kernel.traits_of(kind)
    except Exception:  # noqa: BLE001 — a kernel that cannot answer gates nothing
        return False


# ── gate 1: exit criteria on create (mirrors `dna sdlc story create`) ────────


def refuse_without_exit_criteria(
    *,
    kind: str,
    name: str,
    acceptance_criteria: Iterable[str] | None,
    definition_of_done: Iterable[str] | None,
    allow_no_ac_dod: bool = False,
) -> None:
    """Refuse a create that declares no exit criteria.

    A work item that ships ``todo`` without saying what "done" means is the root
    of the silent-skip-DoD pattern the gate was written for: nobody can tell
    whether it was finished or abandoned, including the person who filed it.

    ``allow_no_ac_dod`` is the back-compat / backfill door — the CLI's
    ``--allow-no-ac-dod``, unchanged."""
    if allow_no_ac_dod:
        return
    missing: list[str] = []
    if not list(acceptance_criteria or ()):
        missing.append("acceptance_criteria (Given/When/Then, at least one)")
    if not list(definition_of_done or ()):
        missing.append("definition_of_done (Code/Tests/Docs/CI, at least one)")
    if not missing:
        return
    raise MethodologyRefusal(
        f"{kind} {name!r} rejected — missing exit criteria:\n"
        + "\n".join(f"  - {m}" for m in missing)
        + "\n\nA work item that does not declare what 'done' means cannot be "
          "shown to be done. Examples:\n"
          "  acceptance_criteria: ['Given X, when Y, then Z']\n"
          "  definition_of_done:  ['Code merged + tests', 'Docs updated']\n"
          "Backfill / migration only: pass allow_no_ac_dod."
    )


# ── gate 2: a passing product TestRun before a close ─────────────────────────

#: A TestRun proves the gate only when its guide is in the HUMAN product lane.
#: The automated lane (integration / e2e / regression) is proven by CI on the
#: PR, not by a hand-recorded run — so an integration ``pass`` does NOT satisfy
#: this gate. Imported lazily from the testkit extension so the core keeps no
#: hardcoded copy of the vocabulary.
def _product_test_kinds() -> frozenset[str]:
    try:
        from dna.extensions.testkit import PRODUCT_TEST_KINDS

        return frozenset(PRODUCT_TEST_KINDS)
    except Exception:  # noqa: BLE001 — testkit absent in a minimal distribution
        return frozenset()


async def has_passing_product_run(
    kernel: Any, scope: str, kind: str, name: str, *, tenant: str | None = None,
) -> bool:
    """Whether a PRODUCT-lane TestRun with ``outcome=pass`` verifies this item.

    The async, kernel-level twin of the CLI's ``passing_run_for_story`` — same
    predicate, same product-lane restriction, reachable from the MCP face (which
    has no ``open_session``).

    **Fails CLOSED on an unreadable registry.** The CLI's version fails open
    ("never crash the gate"), which is defensible for a developer at a terminal
    who can see the warning scroll past. It is not defensible for an automated
    write path: a query hiccup would silently license exactly the close the gate
    exists to refuse, and nobody would ever see it. A caller that genuinely has
    no testkit registered gets a refusal that says so and an escape that records
    why."""
    product_kinds = _product_test_kinds()
    if not product_kinds:
        return False
    ref = f"{kind}/{name}"
    guides: set[str] = set()
    async for row in kernel.query(scope, "TestGuide", tenant=tenant):
        spec = row.get("spec") if isinstance(row, dict) else None
        if not isinstance(spec, dict):
            continue
        if str(spec.get("kind_of_test")) in product_kinds:
            meta = row.get("metadata") if isinstance(row, dict) else None
            guide_name = (meta or {}).get("name") if isinstance(meta, dict) else None
            if guide_name:
                guides.add(str(guide_name))
    if not guides:
        return False
    async for row in kernel.query(scope, "TestRun", tenant=tenant):
        spec = row.get("spec") if isinstance(row, dict) else None
        if not isinstance(spec, dict):
            continue
        if str(spec.get("outcome")) != "pass":
            continue
        verifies = spec.get("verifies") or []
        if not isinstance(verifies, (list, tuple)):
            continue
        if ref not in verifies and name not in verifies:
            continue
        if str(spec.get("guide_ref")) in guides:
            return True
    return False


def refuse_close_without_tests(
    *,
    kind: str,
    name: str,
    status: str,
    has_passing_run: bool,
    allow_no_tests: bool = False,
    no_code: bool = False,
    reason: str | None = None,
) -> str | None:
    """Refuse a close with no passing product TestRun; return the escape reason.

    Returns ``None`` when the gate simply passed, or the (required) reason when
    an escape was exercised — the caller stamps that on the timeline, which is
    what turns "registered exception" from an instruction into a record.

    ``no_code=True`` is the CLI's ``--no-commit``: a work item with no code has
    nothing for a product smoke to exercise. It still needs a reason, for the
    same audit trail."""
    if has_passing_run:
        return None
    if allow_no_tests or no_code:
        if not (reason or "").strip():
            raise MethodologyRefusal(
                f"closing {kind} {name!r} as {status!r} without a passing "
                f"TestRun needs a REASON. The escape exists for genuine "
                f"exceptions (no code to exercise, a deferred verification), "
                f"and an exception nobody recorded is indistinguishable from "
                f"skipping the gate — so the reason is written to the item's "
                f"timeline as an `exception` event."
            )
        return reason.strip()
    raise MethodologyRefusal(
        f"{kind} {name!r} has no PRODUCT smoke (a TestRun with outcome=pass "
        f"whose guide is in the product lane) verifying it — closing to "
        f"{status!r} requires the human validation of the product. (The "
        f"automated lane is already proven by CI on the PR.)\n"
        f"  Record one:\n"
        f"    dna sdlc test-guide create tg-{name} --product --from-ac {name}\n"
        f"    dna sdlc test-run record tg-{name} --outcome pass --evidence <file>\n"
        f"  Escapes (both REQUIRE a reason, both land on the timeline):\n"
        f"    allow_no_tests — a registered exception\n"
        f"    no_code        — a work item with no code to exercise"
    )


# ── the WARN-only guards (they narrate, they never block) ────────────────────


def has_narration_since_last_status_change(timeline: Any) -> bool:
    """True when a ``comment``/``decision`` follows the last ``status_change``.

    Without one the FOCUS feed reads ``start → silence → done``: the work item
    records that it moved and never records why."""
    if not isinstance(timeline, list):
        return False
    last_status_idx: int | None = None
    for i in range(len(timeline) - 1, -1, -1):
        event = timeline[i]
        if isinstance(event, dict) and event.get("type") == "status_change":
            last_status_idx = i
            break
    if last_status_idx is None:
        return False
    return any(
        isinstance(e, dict) and e.get("type") in ("comment", "decision")
        for e in timeline[last_status_idx + 1:]
    )


def narration_warnings(spec: dict[str, Any]) -> list[str]:
    """WARN when nothing narrates the last transition."""
    timeline = spec.get("timeline") if isinstance(spec, dict) else None
    if has_narration_since_last_status_change(timeline):
        return []
    return [
        "no narration (comment/decision) since the last status change — the "
        "FOCUS feed goes silent. Say why: `comment` on this item, or pass a "
        "note with the transition."
    ]


#: Spec fields that back-reference an output, alongside ``produces[]``.
_OUTPUT_BACKREF_FIELDS = (
    "spec_refs", "research_refs", "html_artifacts", "references",
    "follow_up_story", "follow_up_adr", "follow_up_spec",
)


def _has_linked_outputs(spec: dict[str, Any]) -> bool:
    if not isinstance(spec, dict):
        return False
    produces = spec.get("produces")
    if isinstance(produces, list) and produces:
        return True
    return any(spec.get(f) for f in _OUTPUT_BACKREF_FIELDS)


def produces_warnings(spec: dict[str, Any]) -> list[str]:
    """WARN when an item closes with nothing linked — an empty outputs panel."""
    if _has_linked_outputs(spec):
        return []
    return [
        "closing with no linked outputs (produces[] and back-refs are empty) — "
        "the outputs panel will be blank. Link what shipped: "
        "`sdlc produces add <Kind>/<name> <Kind>/<ref>`."
    ]


def shipping_warnings(
    *, prev_status: str | None, commit_ref: str | None, no_code: bool,
) -> list[str]:
    """WARN on a close that skipped the shipping evidence or the review step.

    done = shipped + accepted. Neither of these blocks: a warning that fires on
    a legitimate close would train people to ignore it."""
    warns: list[str] = []
    if not no_code and not commit_ref:
        warns.append(
            "closing with no shipping commit — done means shipped. Pass the "
            "post-merge commit ref, or declare the item has no code."
        )
    if prev_status and prev_status != "review":
        warns.append(
            f"closing without passing through review (was {prev_status!r}) — "
            f"the market flow is PR open -> review -> done (post-merge)."
        )
    return warns


def closing_warnings(
    spec: dict[str, Any], *,
    prev_status: str | None = None,
    commit_ref: str | None = None,
    no_code: bool = False,
    skip_narration: bool = False,
    skip_produces: bool = False,
) -> list[str]:
    """Every WARN-only guard a close should surface, in the CLI's order.

    Returned rather than printed: the CLI writes them to stderr, the MCP face
    puts them in the tool result. A warning nobody transports is a warning
    nobody reads."""
    warns = shipping_warnings(
        prev_status=prev_status, commit_ref=commit_ref, no_code=no_code,
    )
    if not skip_narration:
        warns.extend(narration_warnings(spec))
    if not skip_produces:
        warns.extend(produces_warnings(spec))
    return warns
