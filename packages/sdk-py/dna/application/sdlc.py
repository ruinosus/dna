"""``dna.application.sdlc`` — the transport-agnostic SDLC **write** core.

The shared write logic for the DNA SDLC board (Story / Issue / Feature), factored
out of the CLI (``dna_cli.sdlc_cmd``) so BOTH faces call ONE core — exactly the
``dna.memory.remember`` pattern (a kernel-level verb the CLI *and* the MCP server
share), applied to the board.

Two layers, mirroring the rest of :mod:`dna.application`:

* **pure builders** (no I/O, no clock/env access — the caller injects ``now`` /
  ``actor`` / ``source``): :func:`build_raw`, :func:`append_event`,
  :func:`build_story_spec` / :func:`build_issue_spec` / :func:`build_feature_spec`,
  :func:`next_issue_number`, :func:`validate_transition`. The CLI's own
  ``_build_raw`` / ``_append_timeline`` / ``_next_issue_number`` now delegate here,
  so the envelope + timeline + spec shape + transition rules live in ONE place.

* **async kernel-level cores** — :func:`create_story` / :func:`create_issue` /
  :func:`create_feature` / :func:`set_status` / :func:`add_comment`. Each takes a
  bare ``kernel`` + ``scope`` (like ``dna.memory.remember``) and routes the write
  through ``kernel.write_instance`` (so cache invalidation, hooks + validation
  fire) — into the caller's tenant overlay via ``kernel.with_tenant(tenant)`` when
  ``tenant`` is set (the MCP auth bridge injects it), or the base board otherwise.

The MCP server (``dna_cli._mcp_server``) wires these as write TOOLS through the
same ``_guard`` tenancy + quota seam every other tool passes through; the LiveDna
``*_impl`` wrappers at the bottom resolve the scope + delegate, matching the
``recall_impl`` / ``remember_impl`` convention.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from dna.application.gates import (
    GATE_EXIT_CRITERIA,
    GATE_TEST_ON_CLOSE,
    CLOSING_STATUSES,
    closing_warnings,
    has_passing_product_run,
    kind_is_gated,
    refuse_close_without_tests,
    refuse_without_exit_criteria,
)
from dna.application.live import LiveDna
from dna.kernel.errors import InstanceNameTaken
from dna.application.sdlc_family import (
    dated_spec_fields,
    status_enum_for,
    transitionable_kinds,
    work_item_kinds,
)

# ── constants (single source of truth — the CLI imports these) ─────────────

logger = logging.getLogger(__name__)

SDLC_API_VERSION = "github.com/ruinosus/dna/sdlc/v1"

VALID_STORY_STATUS = (
    "needs-triage", "todo", "in-progress", "review",
    "done", "blocked", "deferred", "cancelled",
)
VALID_FEATURE_STATUS = ("discovery", "in-development", "done", "cancelled", "blocked")
VALID_EPIC_STATUS = ("planning", "in-progress", "done", "cancelled", "deprecated")
VALID_ISSUE_STATUS = (
    "open", "triaged", "in-progress", "resolved", "wont-fix", "duplicate",
)
VALID_ISSUE_TYPE = ("bug", "enhancement", "question", "task")
VALID_ISSUE_SEVERITY = ("low", "medium", "high", "critical")
VALID_PRIORITIES = ("highest", "high", "medium", "low", "lowest")

# The spec fields a READ surface dates, sorts or filters a board instance by —
# the contract every write path owes the readers, per Kind.
#
# It exists because the reverse held for Issue and nobody noticed (i-078):
# ``build_issue_spec`` never stamped ``created_at``, the Issue Kind's schema
# declared it, and ``_digest.build_digest`` dates a filed Issue BY it —
# ``parse_iso_utc(None)`` → ``_in_window`` False → **no Issue ever reached the
# digest's ``found`` bucket**, permanently, in every window. A field that lives
# in the schema and the reader but in no writer is invisible until someone
# spends a session bisecting a digest.
#
# This is not documentation. ``_digest.build_digest`` reads an instance's date
# THROUGH this mapping, and two guard suites hold every write path to it:
# ``packages/sdk-py/tests/test_dated_spec_fields.py`` (the pure builders below)
# and ``packages/cli/tests/test_dated_spec_fields_cli.py`` (every
# ``dna sdlc … create`` verb, which hand-builds its own specs). Adding a Kind
# here without covering it in the CLI guard fails that suite by design.
#
# Who reads what, as of i-078:
#   * ``created_at`` — ``_digest.build_digest`` (ADR → ``decided``; Kaizen +
#     Issue → ``found``), ``dna.extensions.sdlc.journey_derive`` (the first
#     phase of the derived journey for Story / Issue / Spike / Plan),
#     ``dna_cli.sdlc.narrative`` (recency sort, after ``closed_at`` /
#     ``updated_at``).
#   * ``updated_at`` — ``dna_cli.sdlc.narrative`` recency sort; the board's
#     "last touched" everywhere an instance has not closed yet.
#
# Read-dated Kinds whose writers live OUTSIDE this core are deliberately absent
# and were audited clean at i-078: ``Engram`` (``created_at``, stamped by
# ``dna.memory.verbs.remember``), ``StatusReport`` (``generated_at``, stamped by
# the digest's own writer) and ``AgentSession`` (``started_at``, whose capture
# surface is a host-platform adapter that does not ship in this distribution).
DATED_SPEC_FIELDS: dict[str, tuple[str, ...]] = {
    "Story": ("created_at", "updated_at"),
    "Issue": ("created_at", "updated_at"),
    "Feature": ("created_at", "updated_at"),
    "Epic": ("created_at", "updated_at"),
    "Initiative": ("created_at", "updated_at"),
    "Spike": ("created_at", "updated_at"),
    "Bug": ("created_at", "updated_at"),
    "Task": ("created_at", "updated_at"),
    "ADR": ("created_at", "updated_at"),
    "Spec": ("created_at", "updated_at"),
    "Plan": ("created_at", "updated_at"),
    # A Kaizen is an observation, not a work item — it has no `updated_at`
    # arc; `kaizen route` / `resolve` stamp one on transition, the create does
    # not, and no reader asks for it on a freshly observed Kaizen.
    "Kaizen": ("created_at",),
}

# The KERNEL-LESS fallback for the valid target-status set per board Kind.
#
# The live answer is DERIVED: ``sdlc_family.status_enum_for(kernel, kind)`` reads
# ``spec.properties.status.enum`` off the Kind's own schema — the place a Kind
# already declares its arc — so ``set_status`` cannot validate against a
# vocabulary the schema disagrees with, and the four board Kinds that had no
# named write tool (Spike / Bug / Task / Initiative) became writable by
# DECLARATION rather than by four more entries here.
#
# This map survives only for a caller with no kernel to ask (the pure
# :func:`validate_transition`, which the CLI's own option parsing uses). It is
# held to the derived table by ``test_sdlc_family_is_declarative``, so it cannot
# drift the way the thirteen work-item lists did.
_STATUS_ENUMS: dict[str, tuple[str, ...]] = {
    "Story": VALID_STORY_STATUS,
    "Issue": VALID_ISSUE_STATUS,
    "Feature": VALID_FEATURE_STATUS,
    "Epic": VALID_EPIC_STATUS,
}

# Statuses that close a work item — the core auto-stamps ``closed_at`` on entry
# (mirrors the CLI's ``story done`` / ``issue resolve`` / ``feature ship``).
_TERMINAL_STATUS: frozenset[str] = frozenset(
    {"done", "resolved", "cancelled", "wont-fix", "duplicate", "deprecated"}
)

_WRITABLE_KINDS: frozenset[str] = frozenset(_STATUS_ENUMS)


class InstanceExists(ValueError):
    """A ``create_*`` verb was pointed at a name that is already taken.

    ``kernel.write_instance`` is an UPSERT keyed on the instance name, so a
    create with no existence check is a silent destroyer: an agent guessing a
    name (or retrying, or working from a stale board) replaced the live
    instance's status, timeline, acceptance_criteria and definition_of_done and
    got a success back. "Create" is the one verb that must never be an update.

    The message NAMES the existing instance and its current status, and points at
    the verbs that DO update (``set_status`` / ``comment`` / ``write_instance``) —
    a refusal that does not say what to do instead just buys another guess."""


class InvalidTransition(ValueError):
    """A requested ``set_status`` target is not a valid status for the Kind.

    Raised by :func:`validate_transition`. The MCP edge maps it to a clean
    ``ToolError`` so a client sees the honest denial, never a masked 500 / a bad
    write. The message names the Kind, the rejected status, and the valid set."""


# ── pure helpers ────────────────────────────────────────────────────────────


def now_iso(now: datetime | None = None) -> str:
    """UTC ISO-8601 timestamp (seconds precision) — the board's ``at`` stamp."""
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def build_raw(
    kind: str, name: str, spec: dict[str, Any], *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The kernel instance envelope for a board write (apiVersion + metadata).

    ``existing`` is the instance being UPDATED, when there is one. Pass it and
    the envelope is carried forward instead of rebuilt:

    * ``metadata`` keeps every key it had (``labels``, ``description``,
      ``group``, ``icon``, anything an adapter or a human put there), with
      ``name`` re-asserted. Without this, ``set_status`` and ``comment`` — the
      two verbs that load-modify-write — replaced the whole mapping with
      ``{"name": name}``, so a single status transition silently deleted every
      other metadata key the instance carried.
    * ``apiVersion`` keeps the instance's own. Forcing :data:`SDLC_API_VERSION`
      re-homed any board instance living under a different apiVersion (a
      tenant-authored work-item Kind, a federated import) onto DNA's, which is
      not a status change — it is a change of owner.

    Omit ``existing`` for a CREATE, where there is nothing to carry forward and
    the DNA envelope is the right default."""
    api_version = SDLC_API_VERSION
    metadata: dict[str, Any] = {"name": name}
    if isinstance(existing, dict):
        prior_av = existing.get("apiVersion")
        if isinstance(prior_av, str) and prior_av:
            api_version = prior_av
        prior_meta = existing.get("metadata")
        if isinstance(prior_meta, dict):
            metadata = {**prior_meta, "name": name}
    return {
        "apiVersion": api_version,
        "kind": kind,
        "metadata": metadata,
        "spec": spec,
    }


def append_event(
    spec: dict[str, Any], event_type: str, *,
    now: str, actor: str, source: str, **fields: Any,
) -> None:
    """Append an event to ``spec.timeline[]`` (creating the list if absent).

    Mutates ``spec`` in place — the shared timeline-append the CLI's
    ``_append_timeline`` now delegates to. Stamps ``at`` / ``actor`` / ``type`` /
    ``source``; per-event extras come via ``fields`` and FALSY extras are dropped
    (so a brand-new doc never stamps an empty ``from``), byte-for-byte matching the
    CLI's prior behavior."""
    timeline = list(spec.get("timeline", []) or [])
    entry: dict[str, Any] = {
        "at": now,
        "actor": actor,
        "type": event_type,
        "source": source,
    }
    for k, v in fields.items():
        if v not in (None, "", [], {}):
            entry[k] = v
    timeline.append(entry)
    spec["timeline"] = timeline


def _timeline_stamps(spec: dict[str, Any]) -> list[str]:
    """Every usable ``at`` on ``spec.timeline``, unordered."""
    return [
        ev["at"]
        for ev in (spec.get("timeline") or [])
        if isinstance(ev, dict) and isinstance(ev.get("at"), str) and ev["at"]
    ]


def earliest_timeline_at(spec: dict[str, Any]) -> str | None:
    """The ``at`` of the earliest event on ``spec.timeline`` — ``None`` if the
    timeline is empty or carries no usable stamp.

    The honest stand-in for a ``created_at`` that was never written (i-078).
    Every board write path appends a ``status_change`` event as the FIRST thing
    it does, so the earliest ``at`` is the moment the instance entered the
    board — recorded by the writer itself, not inferred after the fact. Pure:
    the caller decides what to do when it returns ``None``.

    Deliberately takes the MINIMUM rather than ``timeline[0]``: the list is
    append-ordered in practice, but a hand-edited or merged board can reorder
    it, and the earliest stamp is the claim we actually want to make."""
    stamps = _timeline_stamps(spec)
    return min(stamps) if stamps else None


def latest_timeline_at(spec: dict[str, Any]) -> str | None:
    """The ``at`` of the most recent timeline event — the honest stand-in for a
    missing ``updated_at`` (the last time the instance demonstrably moved)."""
    stamps = _timeline_stamps(spec)
    return max(stamps) if stamps else None


def backfill_created_at(spec: dict[str, Any]) -> bool:
    """Self-heal a legacy instance's missing ``created_at`` in place, from its
    own timeline. Returns True when it stamped something.

    Called on every load-modify-write (``set_status`` / ``add_comment``) so a
    instance filed before the i-078 fix repairs itself the next time anybody
    touches it. It NEVER falls back to "now": that would date a months-old
    Issue as filed today and pollute every future digest window — the exact
    dishonesty the backfill exists to avoid. No timeline, no stamp."""
    if spec.get("created_at"):
        return False
    first = earliest_timeline_at(spec)
    if not first:
        return False
    spec["created_at"] = first
    return True


def plan_date_repair(
    kind: str, spec: dict[str, Any], *,
    git_added_at: str | None = None, git_touched_at: str | None = None,
) -> tuple[dict[str, str], str]:
    """Decide the honest repair for one already-written instance.

    Returns ``(fields_to_stamp, provenance)``; ``fields_to_stamp`` is empty
    unless the instance is genuinely missing something :data:`DATED_SPEC_FIELDS`
    declares for its Kind. Pure — the caller supplies the git signals and does
    the writing (``dna sdlc backfill-dates``).

    The date is taken from the closest available witness to the event:

    1. ``timeline`` — the instance's OWN record, appended by the create path at
       create time. Nothing is closer.
    2. ``git_added_at`` — the commit that ADDED the file to the board. An
       external witness, typically the same day, and verifiable by anyone with
       the repo.
    3. nothing → provenance ``undatable``, and the instance is left alone.

    ``now`` is deliberately NOT on that list. Stamping today's date on 51
    Issues would make them all look filed today, put them all in the current
    digest window, and hide them from every window they actually belong to —
    a louder version of the bug this repairs (i-078). An undated instance that
    says so is honest; a confidently wrong date is not.
    """
    declared = DATED_SPEC_FIELDS.get(kind, ())
    missing = [field for field in declared if not spec.get(field)]
    if not missing:
        return {}, "complete"

    created = earliest_timeline_at(spec)
    provenance = "timeline"
    if not created:
        created, provenance = git_added_at, "git"
    if not created:
        return {}, "undatable"

    fields: dict[str, str] = {}
    if "created_at" in missing:
        fields["created_at"] = created
    if "updated_at" in missing:
        # The last movement the instance can prove; an instance that never moved
        # was last updated when it was created.
        fields["updated_at"] = latest_timeline_at(spec) or git_touched_at or created
    return fields, provenance


async def existing_or_none(
    kernel: Any, scope: str, kind: str, name: str,
) -> dict[str, Any] | None:
    """``kernel.get_instance`` treating an ABSENT SCOPE as an absent instance.

    A create is very often the FIRST write into a scope — a brand-new
    per-workspace board under Model B — and a source may signal "this scope holds
    nothing yet" by raising rather than returning ``None`` (the filesystem adapter
    raises ``FileNotFoundError`` for a directory that does not exist). An empty
    scope contains nothing to overwrite, so that is an absent instance.

    ``FileNotFoundError`` ONLY: every other read failure propagates. Treating a
    transient read error as "nothing there" would hand the overwrite hole straight
    back — one flaky read would license the destruction the check exists to stop."""
    try:
        return await kernel.get_instance(scope, kind, name)
    except FileNotFoundError:
        return None


async def refuse_if_exists(
    kernel: Any, scope: str, kind: str, name: str, *, overwrite: bool = False,
) -> None:
    """Raise :class:`InstanceExists` when ``(scope, kind, name)`` is already taken.

    The one existence check every ``create_*`` core runs before it writes. It uses
    ``kernel.get_instance`` — the same read the update verbs use — so an instance
    the caller could read is an instance the create refuses to bury.

    ``overwrite=True`` skips it. That door exists because a backfill / migration
    genuinely means "replace this", and refusing outright would only push such a
    caller into hand-rolling ``kernel.write_instance`` — which is how an instance
    ends up with no timeline at all. It is off by default and no MCP tool exposes
    it: over the wire, the update verbs cover every legitimate case.

    NOT a transaction. Two creates racing on the same name can both find it free;
    the kernel has no unique-name constraint to lean on, and inventing a lock here
    would be a distributed-systems claim this function cannot honour. What it does
    remove is the entire class of NON-concurrent overwrites — the guessed name, the
    retry, the stale board — which is what actually destroyed instances."""
    if overwrite:
        return
    existing = await existing_or_none(kernel, scope, kind, name)
    if existing is None:
        return
    spec = existing.get("spec") if isinstance(existing, dict) else None
    status = (spec or {}).get("status") if isinstance(spec, dict) else None
    title = (spec or {}).get("title") if isinstance(spec, dict) else None
    raise InstanceExists(
        f"{kind} {name!r} already exists in scope {scope!r}"
        + (f" (status: {status})" if status else "")
        + (f" — {title!r}" if title else "")
        + ". Refusing to create over it: that would replace its status, timeline "
          "and exit criteria. To CHANGE it use set_status (status), comment "
          "(narration) or write_instance (any field, merged); to file something "
          "new, pick a name that is free."
    )


def next_number(prefix: str, existing_names: list[str]) -> int:
    """Next free ``<prefix>-NNN`` number given the existing doc names (pure).

    ``max + 1``. Note what that implies for any check built on the SAME read:
    the answer is free BY CONSTRUCTION, so no "is this number taken?" filter
    over ``existing_names`` can ever reject it. Rejecting a colliding number
    needs information this list does not carry.

    Which is the whole point of passing a WIDER list. The collision measured on
    the dna-cloud board is not a race — it is a blind spot: two agents in two
    git worktrees each enumerate their OWN ``.dna/`` and neither name appears in
    the other's list. ``max+1`` is not wrong; the list was short. Feed it the
    union of every worktree's names (``dna_cli.sdlc_cmd._sibling_worktree_names``)
    and the same arithmetic stops colliding — see :func:`duplicate_numbers` for
    the detection that still has to run on the merged tree, because a list this
    function never saw (another clone, CI) is still possible."""
    max_n = 0
    pat = re.compile(rf"^{re.escape(prefix)}-(\d+)")
    for nm in existing_names:
        m = pat.match(nm or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def duplicate_numbers(prefix: str, existing_names: list[str]) -> dict[int, list[str]]:
    """``{NNN: [names…]}`` for every ``<prefix>-NNN`` claimed by >1 doc (pure)."""
    by_number: dict[int, list[str]] = {}
    pat = re.compile(rf"^{re.escape(prefix)}-(\d+)")
    for nm in sorted(existing_names):
        m = pat.match(nm or "")
        if m:
            by_number.setdefault(int(m.group(1)), []).append(nm)
    return {n: names for n, names in sorted(by_number.items()) if len(names) > 1}


def next_issue_number(existing_names: list[str]) -> int:
    """:func:`next_number` for Issues (``i-NNN``). Kept as its own name because
    it is the published primitive both faces import."""
    return next_number("i", existing_names)


def duplicate_issue_numbers(existing_names: list[str]) -> dict[int, list[str]]:
    """``{NNN: [names…]}`` for every ``i-NNN`` claimed by more than one doc (pure).

    The id of an Issue is its NUMBER; the only thing a write path can claim
    atomically is its NAME, ``i-NNN-<slug>``. Two different slugs on the same
    number are two different names, so every guarantee in this module —
    #242's probe, the ``if_absent`` claim, the SQL primary key — grants both
    writes, and is right to. Measured on the dna-cloud board 05/08/2026: 13
    Issues sharing 4 numbers (``i-094`` ×4, ``i-097`` ×5).

    Nothing at ALLOCATION time can prevent it while the writers cannot SEE each
    other, and the case that produced those 13 is the extreme of it: agents in
    separate git WORKTREES are separate filesystems — no lock, no ``O_EXCL``,
    no primary key spans them — and because the file names differ, ``git
    merge`` joins both without a conflict.

    What CAN be fixed is the seeing: worktrees of one clone are enumerable
    (``git worktree list``, one shared ``.git``), so the allocator can read the
    union instead of one tree — that is what ``next_number`` is fed now, and it
    is a wider READ, not a lock. Two clones (a laptop and CI, two machines) have
    no shared arbiter at all.

    So this stays, deliberately: cheap, exact, and it runs on the one artifact
    where every writer finally meets — the MERGED tree. Belongs in CI.

    The structural cure is to make the id the whole name (``i-NNN``: one path,
    so ``if_absent`` becomes a real number lock AND git raises a real conflict)
    or a number-keyed allocator Kind. Both are data-model decisions."""
    return duplicate_numbers("i", existing_names)


async def issue_number_is_free(kernel: Any, scope: str, number: int) -> bool:
    """Is ``i-NNN`` unclaimed *right now*, by ANY slug? (probe-then-write path)

    The number-keyed counterpart of :func:`existing_or_none`. The probe #242
    installed asked ``get_instance("i-NNN-<our slug>")``, which answers a
    question nobody was asking: the collision that actually happens is a
    DIFFERENT slug on the same number, and that probe returns ``None`` for it
    every time.

    Its only real power is being LATER than the enumeration that chose the
    candidate, so it can see a write that landed in between. It cannot see a
    writer this source never observes (another worktree), and the atomic path
    has no equivalent — ``if_absent`` arbitrates the NAME, by definition."""
    prefix = f"i-{number:03d}-"
    bare = f"i-{number:03d}"
    async for row in kernel.query(scope, "Issue", projection=["name"]):
        meta = row.get("metadata") if isinstance(row, dict) else None
        nm = (meta or {}).get("name") if isinstance(meta, dict) else None
        nm = nm or (row.get("name") if isinstance(row, dict) else "") or ""
        if nm == bare or nm.startswith(prefix):
            return False
    return True


def looks_like_decision(body: str) -> bool:
    """Heuristic: a decision-shaped comment auto-promotes to a ``decision`` event.

    Mirrors the CLI's ``_looks_like_decision`` — a body that opens with a decision
    verb ("decidi", "decided", "chose", "vamos", "will") reads as a decision, not a
    plain comment. Kept deliberately small + language-tolerant (pt-BR + en)."""
    head = body.strip().lower()[:40]
    return any(
        head.startswith(v)
        for v in ("decidi", "decided", "decision:", "chose", "escolhi",
                  "vamos ", "we will", "will ", "opt", "optamos")
    )


def validate_transition(
    kind: str, target: str, *,
    valid: tuple[str, ...] | None = None,
    writable: tuple[str, ...] | None = None,
) -> None:
    """Raise :class:`InvalidTransition` unless ``target`` is a valid status for
    ``kind``. The Kind must itself be a transitionable board Kind.

    ``valid`` / ``writable`` are the DERIVED answers, supplied by a caller that
    has a kernel (:mod:`dna.application.sdlc_family` reads them off each Kind's
    own schema and traits). Omit them and the pure fallback map applies —
    correct for the four Kinds it lists, and honest about not knowing the rest."""
    valid_for_kind = valid if valid is not None else _STATUS_ENUMS.get(kind)
    if not valid_for_kind:
        known = writable if writable is not None else tuple(sorted(_WRITABLE_KINDS))
        raise InvalidTransition(
            f"{kind!r} is not a status-bearing board Kind "
            f"(writable: {list(known)})"
        )
    if target not in valid_for_kind:
        raise InvalidTransition(
            f"{target!r} is not a valid {kind} status — valid: {list(valid_for_kind)}"
        )


# ── the SERVES gate (i-117) — a close must SAY what design it served ────────
#
# THE DEFECT. A Spec's execution is DERIVED, never stored: the portal reads the
# Spec's ``references`` ∪ ``cited_by``, crosses each citation with the cited
# item's own delivery state, and calls the Spec executed when a citation is
# delivered. That design is right — "executed" is PROVED by a delivered
# citation, not asserted by a status somebody flipped. What was missing is that
# NOTHING OBLIGED THE CITATION. A Story that shipped a Spec without citing it
# left the Spec looking untouched, so the bucket "accepted, not executed"
# quietly merged two incompatible facts: *nobody did it* and *somebody did it
# and did not say so*. That number drove work selection twice, and twice it sent
# an agent at something already built.
#
# THE CURE, and why it is shaped this way. The obvious fix — make every close
# demand a field — is the fix that destroys itself: a field everyone must fill
# is a field everyone fills with anything, and a citation that means nothing is
# worse than one that is absent, because it also LOOKS like evidence. Prior art
# agrees on the shape of the escape rather than on the demand: Azure DevOps
# ships "Check for linked work items" as a THREE-state knob (off /
# optional-warn / required-block) precisely because always-required is
# unusable; Jira's Linked-Issues validator scopes the demand to one link TYPE
# rather than to every transition; GitHub never asks at all and DERIVES the link
# from a `Closes #N` already written in the prose.
#
# So this gate asks only where there is already EVIDENCE, and it takes the
# evidence from the prose, GitHub-style:
#
#   already cited  → silent. The trace exists; there is nothing to ask.
#   prose NAMES a live Spec verbatim → REFUSE until the closer says something.
#   neither        → silent. Not "warn": a close already prints up to three
#                    warnings, and the citation-free case is ALREADY narrated by
#                    the i-113 produces guard (``spec_refs``/``references`` are
#                    among the back-refs it counts). A fourth line that fires on
#                    every close is how a person learns to skip all four.
#
# And the answer it demands cannot be filled with noise. ``dna sdlc spec
# executed --summary`` is the precedent for "a terminal claim owes proof", but
# its proof is FREE TEXT, and free text under obligation degrades into "done".
# ``--serves`` takes a REFERENCE: it must name a Spec that exists, or the
# literal ``none``. No cheap string satisfies it — a wrong ``--serves`` is a
# visible wrong citation on two documents, an auditable mistake rather than
# noise.
#
# ``--serves none`` is the third state, and it is the point: it turns the
# ABSENCE of a citation from a gap into an assertion — the same move
# ``revoked_by`` made on KindDefinition. "Nobody said" and "somebody said no"
# stop reading alike.

#: The literal a closer passes to declare that this delivery served NO Spec.
SERVES_NONE = "none"

#: Where a work item stores a Spec citation today. ``spec_refs`` is the Story's
#: declared M:N link, ``references`` is what ``dna sdlc cite`` writes (and the
#: side the portal's derivation reads back off the Spec), ``produces`` is the
#: generic output hub. All three count as "already traced" — the gate exists to
#: obtain a trace, not to obtain one particular field.
_SPEC_REF_LIST_FIELDS = ("spec_refs", "references")

#: Authored prose scanned for a Spec name. Deliberately includes the timeline:
#: measured against the real dna-cloud board, the two cases i-117 was filed over
#: (``spec-grafo-1-arestas-e-travessia``, ``spec-conversa-como-dado-do-dna``)
#: name their Spec ONLY in a timeline comment. A scan that trusted only
#: title/description would be blind on exactly the defect it was built for.
_SERVES_TEXT_FIELDS = (
    "title", "description", "resolution", "body",
    "as_a", "i_want", "so_that",
)
_SERVES_CHECKLIST_FIELDS = ("acceptance_criteria", "definition_of_done")


def _as_str_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str)]
    return [v] if isinstance(v, str) else []


def parse_serves(raw: str) -> str:
    """Normalize one ``--serves`` value to a bare Spec name (or ``SERVES_NONE``).

    Accepts ``none``, ``<name>`` or ``Spec/<name>``. Any OTHER qualified Kind is
    a refusal, not a coercion: ``--serves Feature/f-x`` is a person saying the
    wrong sentence, and silently rewriting it to a Spec name would invent a
    citation nobody made.

    :raises ValueError: on an empty value or a non-Spec qualified reference.
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("--serves precisa de um valor (Spec/<nome> ou 'none')")
    if s.lower() == SERVES_NONE:
        return SERVES_NONE
    if "/" in s:
        kind, _, name = s.partition("/")
        if kind.strip().lower() != "spec":
            raise ValueError(
                f"--serves nomeia uma Spec, não {kind.strip()!r} — "
                f"passe Spec/<nome> (ou 'none')"
            )
        s = name.strip()
    if not s:
        raise ValueError("--serves precisa de um valor (Spec/<nome> ou 'none')")
    return s


def cited_spec_names(wi_spec: Any) -> set[str]:
    """Spec names this work item ALREADY cites, in every shape the board stores.

    Pure. Reads ``spec_refs`` / ``references`` (bare or ``Spec/<name>``) and the
    ``produces`` hub (``{kind: Spec, name: …}``)."""
    if not isinstance(wi_spec, dict):
        return set()
    out: set[str] = set()
    for field in _SPEC_REF_LIST_FIELDS:
        for ref in _as_str_list(wi_spec.get(field)):
            ref = ref.strip()
            if "/" in ref:
                kind, _, name = ref.partition("/")
                if kind.strip().lower() == "spec" and name.strip():
                    out.add(name.strip())
            elif ref and field == "spec_refs":
                # A bare name in `spec_refs` IS a Spec — the field declares it.
                # A bare name in `references` is a Reference (the `cite`
                # default), so it is deliberately NOT read as a Spec here.
                out.add(ref)
    produces = wi_spec.get("produces")
    if isinstance(produces, list):
        for p in produces:
            if (isinstance(p, dict) and isinstance(p.get("kind"), str)
                    and p["kind"].lower() == "spec"
                    and isinstance(p.get("name"), str)):
                out.add(p["name"].strip())
    out.discard("")
    return out


def serves_scan_text(wi_spec: Any) -> str:
    """The prose of a work item, joined — authored fields, checklist items and
    every timeline ``summary``. Pure; the corpus
    :func:`mentioned_spec_names` reads."""
    if not isinstance(wi_spec, dict):
        return ""
    parts: list[str] = []
    for f in _SERVES_TEXT_FIELDS:
        v = wi_spec.get(f)
        if isinstance(v, str):
            parts.append(v)
    for f in _SERVES_CHECKLIST_FIELDS:
        for item in wi_spec.get(f) or []:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
    for ev in wi_spec.get("timeline") or []:
        if isinstance(ev, dict) and isinstance(ev.get("summary"), str):
            parts.append(ev["summary"])
    return "\n".join(parts)


def mentioned_spec_names(text: str, spec_names: Any) -> list[str]:
    r"""Spec names the ``text`` names VERBATIM, as whole identifiers.

    The boundary is ``[\w-]`` on BOTH sides and not ``\b``, because these names
    are hyphenated slugs: ``\b`` would let ``spec-grafo-1`` match inside
    ``spec-grafo-10-outra``, which is a citation to a DIFFERENT design. Matching
    is case-insensitive — the slugs are lowercase, and ``Spec/spec-x`` in prose
    is the same claim as ``spec-x``.

    Pure and I/O-free; the caller supplies the universe of names."""
    if not text:
        return []
    hits: list[str] = []
    for name in spec_names or ():
        if not isinstance(name, str) or not name:
            continue
        if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text, re.IGNORECASE):
            hits.append(name)
    return sorted(set(hits))


def derive_served_spec_candidates(wi_spec: Any, specs: Any) -> list[str]:
    """The Specs a closing work item PLAUSIBLY served and has not cited.

    ``specs`` maps Spec name → its ``status``. Only Specs whose board bucket is
    still ``open`` are candidates: the gate defends the DERIVATION, and a Spec
    already ``executed`` / ``shelved`` / ``deprecated`` / ``superseded`` is not
    in the bucket the derivation can get wrong. That eligibility is DERIVED from
    :func:`dna.extensions.sdlc.spec_board_bucket`, never re-enumerated here — a
    second list of "which statuses are terminal" is a list that goes stale in
    silence.

    Returns the sorted names, minus anything already cited. Pure."""
    from dna.extensions.sdlc import spec_board_bucket  # noqa: PLC0415 — cycle

    if not isinstance(specs, dict):
        return []
    open_names = [
        n for n, status in specs.items()
        if isinstance(n, str) and spec_board_bucket(
            status if isinstance(status, str) else None
        ) == "open"
    ]
    already = cited_spec_names(wi_spec)
    return [
        n for n in mentioned_spec_names(serves_scan_text(wi_spec), open_names)
        if n not in already
    ]


def serves_refusal(
    *, candidates: Any, kind: str = "work item", name: str = "",
) -> str | None:
    """The refusal text for a close that DECLARED NOTHING — or ``None`` to let it
    through.

    Refuses exactly when the prose named at least one open Spec the item does not
    already cite. An item with no candidate is not asked a question nobody can
    answer usefully.

    The caller passes ``candidates`` only for an undeclared close, and this
    function deliberately does NOT re-check ``declared`` itself. It did at first,
    and that branch was unreachable from every door: no mutation of it changed
    any behaviour, which is the shape of a guard nobody can trust. The
    "declared → no question" half of the rule is the caller's short-circuit, and
    it is covered at the door by the tests that close WITH ``--serves`` while a
    candidate sits in the prose.

    Pure; the caller prints + exits."""
    cands = _as_str_list(candidates)
    if not cands:
        return None
    lines = "\n".join(f"     --serves Spec/{c}" for c in cands)
    label = f"{kind}/{name}" if name else kind
    return (
        f"{label} NOMEIA uma Spec no próprio texto e não a cita — feche dizendo "
        f"o que a entrega serve.\n"
        f"  A execução de uma Spec é DERIVADA da citação: sem ela, uma Spec já "
        f"entregue segue contada como pendente (i-117).\n"
        f"  Candidatas achadas no texto deste item:\n{lines}\n"
        f"  Ou afirme que não serve nenhuma:   --serves none"
    )


def apply_spec_citation(
    *, caller_kind: str, caller_name: str, caller_spec: dict[str, Any],
    spec_name: str, spec_spec: dict[str, Any], now: str,
) -> tuple[bool, bool]:
    """Write the bidirectional citation ``caller ↔ Spec``, in place.

    THE SAME two lists ``dna sdlc cite`` maintains, and deliberately so: the
    portal's derivation reads the Spec's ``cited_by``, so a "serves" that landed
    anywhere else would be a record nobody reads. Forward is stored QUALIFIED
    (``Spec/<name>``) — a bare name in ``references`` means a Reference.

    Idempotent. Returns ``(caller_changed, spec_changed)``."""
    forward = f"Spec/{spec_name}"
    back = f"{caller_kind}/{caller_name}"

    caller_changed = False
    refs = list(caller_spec.get("references") or [])
    if forward not in refs:
        refs.append(forward)
        caller_spec["references"] = refs
        caller_spec["updated_at"] = now
        caller_changed = True

    spec_changed = False
    cited_by = list(spec_spec.get("cited_by") or [])
    if back not in cited_by:
        cited_by.append(back)
        spec_spec["cited_by"] = cited_by
        spec_spec["updated_at"] = now
        spec_changed = True

    return caller_changed, spec_changed


def stamp_serves_none(wi_spec: dict[str, Any], *, now: str) -> None:
    """Record ``--serves none`` ON the item, in place.

    A timeline event alone would not do: the question a later sweep asks is
    "which closes never declared anything?", and answering it needs a FIELD on
    the item, not an entry buried in its history."""
    wi_spec["serves_no_spec"] = True
    wi_spec["serves_declared_at"] = now


# ── pure spec builders (shared by the CLI create commands + the async cores) ─


def build_story_spec(
    *, title: str | None, description: str, feature: str,
    status: str = "todo", priority: str | None = None,
    labels: list[str] | None = None, reporter: str | None = None,
    owner: str | None = None,
    acceptance_criteria: list[str] | None = None,
    definition_of_done: list[str] | None = None,
    ac_source: str | None = None, dod_source: str | None = None,
    now: str, actor: str, source: str,
) -> dict[str, Any]:
    """Build a Story ``spec`` (title-fallback, created/updated stamps, initial
    timeline event) — the exact shape ``dna sdlc story create`` writes."""
    effective_title = title
    if effective_title is None:
        first_line = description.splitlines()[0] if description else ""
        effective_title = first_line[:80] if first_line else feature
    spec: dict[str, Any] = {
        "title": effective_title,
        "description": description,
        "status": status,
        "feature": feature,
    }
    if owner:
        spec["owner"] = owner
    if priority:
        spec["priority"] = priority
    if labels:
        spec["labels"] = list(labels)
    if reporter:
        spec["reporter"] = reporter
    if acceptance_criteria:
        spec["acceptance_criteria"] = list(acceptance_criteria)
        spec["acceptance_criteria_source"] = ac_source or "cli-create"
    if definition_of_done:
        spec["definition_of_done"] = list(definition_of_done)
        spec["definition_of_done_source"] = dod_source or "cli-create"
    spec["created_at"] = now
    spec["updated_at"] = now
    append_event(spec, "status_change", to=status, now=now, actor=actor, source=source)
    return spec


def build_issue_spec(
    *, description: str, issue_type: str = "bug", severity: str = "medium",
    status: str = "open", title: str | None = None, owner: str | None = None,
    related_feature: str | None = None, related_finding: str | None = None,
    now: str, actor: str, source: str,
) -> dict[str, Any]:
    """Build an Issue ``spec`` (type/severity/status, created/updated stamps,
    initial timeline event) — the exact shape ``dna sdlc issue file`` writes.

    ``title`` is optional and NOT synthesized when absent: the Issue schema does
    not require one and every read surface already falls back to the description
    (``_digest._title``), so fabricating ``description[:80]`` would only write
    the description twice under two keys.

    The ``created_at`` / ``updated_at`` stamps are not cosmetic (i-078): the
    digest dates a filed Issue by ``created_at``, so an Issue without one never
    reaches its ``found`` bucket in any window. See :data:`DATED_SPEC_FIELDS`."""
    spec: dict[str, Any] = {}
    if title:
        spec["title"] = title
    spec.update({
        "description": description,
        "type": issue_type,
        "severity": severity,
        "status": status,
    })
    if owner:
        spec["owner"] = owner
    if related_feature:
        spec["related_feature"] = related_feature
    if related_finding:
        spec["related_finding"] = related_finding
    spec["created_at"] = now
    spec["updated_at"] = now
    append_event(spec, "status_change", to=status, now=now, actor=actor, source=source)
    return spec


def build_feature_spec(
    *, title: str, description: str, status: str = "discovery",
    epic: str | None = None, owner: str | None = None,
    reporter: str | None = None, priority: str | None = None,
    labels: list[str] | None = None, business_value: int | None = None,
    now: str, actor: str, source: str,
) -> dict[str, Any]:
    """Build a Feature ``spec`` (roadmap noun; no AC/DoD guard) — the shape
    ``dna sdlc feature create`` writes."""
    spec: dict[str, Any] = {
        "title": title,
        "description": description,
        "status": status,
    }
    if epic:
        spec["epic"] = epic
    if owner:
        spec["owner"] = owner
    spec["reporter"] = reporter or "mcp"
    if priority:
        spec["priority"] = priority
    if labels:
        spec["labels"] = list(labels)
    if business_value is not None:
        spec["business_value"] = business_value
    spec["created_at"] = now
    spec["updated_at"] = now
    append_event(spec, "status_change", to=status, now=now, actor=actor, source=source)
    return spec


# ── async kernel-level cores (the write goes through kernel.write_instance) ──
#
# The SDLC board Kinds (Story / Issue / Feature) are TenantScope.GLOBAL — the
# board is a PROJECT-level artifact, not per-tenant data (SdlcExtension:
# "SDLC primitives are project-level, not per-tenant"). So a write is GLOBAL
# (no ``kernel.with_tenant`` overlay — that would raise TenantNotAllowed). Under
# Model B multi-workspace, isolation is by SCOPE instead: a workspace's board
# lives in its OWN scope (``live.default_scope(workspace)``), and the MCP
# ``_guard`` scope-binding denies a cross-workspace scope. The ``*_impl``
# wrappers below resolve that scope; these cores only take the resolved scope.


async def create_story(
    kernel: Any, scope: str, name: str, *, feature: str, description: str,
    title: str | None = None, status: str = "todo",
    priority: str | None = None, labels: list[str] | None = None,
    reporter: str | None = None, owner: str | None = None,
    acceptance_criteria: list[str] | None = None,
    definition_of_done: list[str] | None = None,
    actor: str = "mcp", source: str = "mcp",
    now: datetime | None = None, overwrite: bool = False,
    allow_no_ac_dod: bool = False,
) -> dict[str, Any]:
    """Create a Story doc — the shared core behind ``dna sdlc story create`` + the
    MCP ``create_story`` tool. Routes through ``kernel.write_instance`` (hooks +
    cache fire) into the resolved (per-workspace) ``scope``.

    Refuses an existing ``name`` (:func:`refuse_if_exists`) — a create is never
    an update — and refuses a Story with no exit criteria when the Kind declares
    ``sdlc.exit-criteria-required`` (:func:`gates.refuse_without_exit_criteria`).
    That gate used to live in the CLI's ``cmd_story_create`` only, so the MCP
    tool created criteria-less Stories the CLI would have rejected."""
    # Existence first: when a caller both reuses a taken name AND omits its
    # exit criteria, "that name is already s-one, status in-progress" is the
    # more specific, more actionable fact — and it is the refusal that protects
    # a live instance.
    await refuse_if_exists(kernel, scope, "Story", name, overwrite=overwrite)
    if kind_is_gated(kernel, "Story", GATE_EXIT_CRITERIA):
        refuse_without_exit_criteria(
            kind="Story", name=name,
            acceptance_criteria=acceptance_criteria,
            definition_of_done=definition_of_done,
            allow_no_ac_dod=allow_no_ac_dod,
        )
    ni = now_iso(now)
    spec = build_story_spec(
        title=title, description=description, feature=feature, status=status,
        priority=priority, labels=labels, reporter=reporter or actor, owner=owner,
        acceptance_criteria=acceptance_criteria,
        definition_of_done=definition_of_done,
        now=ni, actor=actor, source=source,
    )
    raw = build_raw("Story", name, spec)
    await kernel.write_instance(scope, "Story", name, raw, invalidate_mode="doc")
    return {"kind": "Story", "name": name, "status": status, "feature": feature}


async def create_issue(
    kernel: Any, scope: str, slug: str, *, description: str,
    issue_type: str = "bug", severity: str = "medium",
    title: str | None = None,
    related_feature: str | None = None, related_finding: str | None = None,
    owner: str | None = None, status: str = "open",
    actor: str = "mcp", source: str = "mcp",
    now: datetime | None = None, overwrite: bool = False,
    also_taken: list[str] | None = None,
) -> dict[str, Any]:
    """File an Issue with an auto-incremented ``i-NNN-<slug>`` name — the shared
    core behind ``dna sdlc issue file`` + the MCP ``create_issue`` tool.

    **The numbering is a hint; the WRITE is the guarantee.** ``max(i-NNN) + 1``
    is only correct if the enumeration saw every Issue, and a concurrent writer
    or a lagging replica yields a number that is already taken. #242 closed the
    non-concurrent half by probing each candidate before writing, and documented
    what it could not close: two calls can still probe the same free name in the
    same instant, and one overwrites the other. That needed "a unique constraint
    or a lock in the kernel's write path".

    It has one now. The write is an ATOMIC CREATE (``if_absent=True``): it claims
    the name or raises ``InstanceNameTaken``, arbitrated by the SQL adapter's
    composite primary key or the filesystem's ``O_CREAT|O_EXCL`` / ``mkdir``. So
    the loop no longer *probes and hopes* — it tries to WRITE, and a loser
    simply takes the next number. Two concurrent creates now produce two Issues,
    which is the correct outcome and was not previously reachable.

    An adapter that does not support ``if_absent`` falls back to the #242
    behavior (probe, then a plain write) rather than failing: the race stays
    open there, exactly as documented, but nothing that worked stops working.
    That fallback now probes the NUMBER (:func:`issue_number_is_free`) instead
    of the full name, which is the question that was actually worth asking.

    **What NONE of that protects, measured on the dna-cloud board 05/08/2026:
    the NUMBER.** ``if_absent`` claims the NAME, and ``i-095-egress-por-plano``
    and ``i-095-terraform-fases-2-4`` are two names. 13 Issues ended up sharing
    4 numbers with every write behaving exactly as promised. Filtering the
    candidate against the enumeration does not help either — ``max+1`` is free
    by construction in the very list it was computed from.

    ``also_taken`` is the one thing that does: names from a source this
    ``kernel`` cannot see. The measured collisions were not a race, they were a
    BLIND SPOT — agents in separate git worktrees each enumerate their own
    ``.dna/``, so ``i-101`` was ``max+1`` in both trees, hours apart, and the
    merge joined two different file names without a conflict. Widen the list and
    the same arithmetic stops colliding, without pretending to a lock: the CLI
    fills this from ``git worktree list`` (``_sibling_worktree_names``), and
    ``create_issue`` stays honest by not going looking for it — a caller that
    knows about other trees says so, and one that does not gets the old
    behavior. A number claimed in a clone nobody here can read stays invisible;
    :func:`duplicate_issue_numbers` on the merged tree is the backstop, and the
    structural cure (name == ``i-NNN``, or a number-keyed allocator Kind) is a
    data-model decision specced separately.

    The enumeration is still O(N) rows — documented rather than hidden — though
    it pushes a ``projection`` down, so it moves N names instead of N full Issue
    specs."""
    names: list[str] = []
    async for row in kernel.query(scope, "Issue", projection=["name"]):
        meta = row.get("metadata") if isinstance(row, dict) else None
        nm = (meta or {}).get("name") if isinstance(meta, dict) else None
        names.append(nm or (row.get("name") if isinstance(row, dict) else "") or "")
    n = next_issue_number(names + list(also_taken or ()))
    ni = now_iso(now)
    spec = build_issue_spec(
        description=description, issue_type=issue_type, severity=severity,
        status=status, title=title, owner=owner,
        related_feature=related_feature, related_finding=related_finding,
        now=ni, actor=actor, source=source,
    )

    if overwrite:
        name = f"i-{n:03d}-{slug}"
        await kernel.write_instance(
            scope, "Issue", name, build_raw("Issue", name, spec),
            invalidate_mode="doc",
        )
        return {"kind": "Issue", "name": name, "type": issue_type,
                "severity": severity}

    # Bounded so a pathological source can never spin: 1000 consecutive taken
    # names means something is wrong that a 1001st attempt will not fix.
    atomic = True
    for candidate_n in range(n, n + 1000):
        name = f"i-{candidate_n:03d}-{slug}"
        raw = build_raw("Issue", name, spec)
        if atomic:
            try:
                await kernel.write_instance(
                    scope, "Issue", name, raw, invalidate_mode="doc",
                    if_absent=True,
                )
                return {"kind": "Issue", "name": name, "type": issue_type,
                        "severity": severity}
            except NotImplementedError:
                # This adapter cannot promise an atomic create. Degrade to the
                # #242 probe-then-write for the REST of the loop, and say so
                # only here — degrading silently per attempt would hide which
                # guarantee is actually in force.
                atomic = False
                logger.info(
                    "create_issue: source does not support atomic creates; "
                    "falling back to probe-then-write (the concurrent race "
                    "documented in #242 remains open on this adapter)"
                )
            except InstanceNameTaken:
                continue  # somebody else took it between our read and our write
        if await issue_number_is_free(kernel, scope, candidate_n):
            await kernel.write_instance(
                scope, "Issue", name, raw, invalidate_mode="doc")
            return {"kind": "Issue", "name": name, "type": issue_type,
                    "severity": severity}
    raise InstanceExists(  # pragma: no cover — 1000 consecutive collisions
        f"no free Issue name found for slug {slug!r} in scope {scope!r} "
        f"after 1000 attempts from i-{n:03d} — the source is reporting every "
        f"candidate as taken."
    )


async def create_feature(
    kernel: Any, scope: str, name: str, *, title: str, description: str,
    epic: str | None = None, status: str = "discovery",
    priority: str | None = None, labels: list[str] | None = None,
    reporter: str | None = None, owner: str | None = None,
    actor: str = "mcp", source: str = "mcp",
    now: datetime | None = None, overwrite: bool = False,
) -> dict[str, Any]:
    """Create a Feature doc — the shared core behind ``dna sdlc feature create`` +
    the MCP ``create_feature`` tool.

    Refuses an existing ``name`` (:func:`refuse_if_exists`)."""
    await refuse_if_exists(kernel, scope, "Feature", name, overwrite=overwrite)
    ni = now_iso(now)
    spec = build_feature_spec(
        title=title, description=description, status=status, epic=epic,
        owner=owner, reporter=reporter or actor, priority=priority, labels=labels,
        now=ni, actor=actor, source=source,
    )
    raw = build_raw("Feature", name, spec)
    await kernel.write_instance(scope, "Feature", name, raw, invalidate_mode="doc")
    return {"kind": "Feature", "name": name, "status": status}


async def set_status(
    kernel: Any, scope: str, kind: str, name: str, status: str, *,
    reason: str | None = None, actor: str = "mcp", source: str = "mcp",
    now: datetime | None = None, tenant: str | None = None,
    commit_ref: str | None = None,
    allow_no_tests: bool = False, no_code: bool = False,
    gate_reason: str | None = None,
    skip_narration_warning: bool = False,
    skip_produces_warning: bool = False,
) -> dict[str, Any]:
    """Transition a board item to ``status`` (load-modify-write) — the shared
    core behind the CLI's ``start`` / ``done`` / ``block`` / ``review`` /
    ``triage`` / ``resolve`` / ``ship`` verbs + the MCP ``set_status`` tool.

    Validates the target against the Kind's OWN declared status enum
    (:func:`sdlc_family.status_enum_for`, falling back to the static map for a
    Kind the registry does not know), appends a ``status_change`` timeline event
    (with the ``from``), auto-stamps ``closed_at`` on a terminal status and
    ``blocked_reason`` when ``reason`` is given for a block. Raises
    ``LookupError`` if the doc is absent.

    **The close gate runs here** (decision A). A Kind declaring
    ``sdlc.test-gated`` refuses a CLOSING transition without a passing
    product-lane TestRun, exactly as ``dna sdlc story done`` does — because a
    gate only one face enforces is not a gate. The escapes (``allow_no_tests`` /
    ``no_code``) require ``gate_reason``, which is written to the timeline as an
    ``exception`` event.

    Returns the transition plus ``warnings`` — the WARN-only guards (no shipping
    commit, skipped review, no narration, no linked outputs) the CLI prints to
    stderr. Over MCP there is no stderr, so they travel in the result."""
    valid = status_enum_for(kernel, kind)
    validate_transition(
        kind, status, valid=valid,
        writable=transitionable_kinds(kernel) if valid is None else None,
    )
    existing = await kernel.get_instance(scope, kind, name)
    if existing is None:
        raise LookupError(f"{kind} {name!r} not found in scope {scope!r}")
    spec = dict(existing.get("spec") or {}) if isinstance(existing, dict) else {}
    prev = spec.get("status")
    ni = now_iso(now)

    closing = status in CLOSING_STATUSES
    escape_reason: str | None = None
    if closing and kind_is_gated(kernel, kind, GATE_TEST_ON_CLOSE):
        escape_reason = refuse_close_without_tests(
            kind=kind, name=name, status=status,
            has_passing_run=await has_passing_product_run(
                kernel, scope, kind, name, tenant=tenant,
            ),
            allow_no_tests=allow_no_tests, no_code=no_code,
            reason=gate_reason,
        )
    warnings = (
        closing_warnings(
            spec, prev_status=prev, commit_ref=commit_ref, no_code=no_code,
            skip_narration=skip_narration_warning,
            skip_produces=skip_produces_warning,
        )
        if closing
        else []
    )

    backfill_created_at(spec)   # legacy docs self-heal from their own timeline
    spec["status"] = status
    spec["updated_at"] = ni
    if status in _TERMINAL_STATUS:
        spec["closed_at"] = ni
    if reason:
        spec["blocked_reason" if status == "blocked" else "resolution"] = reason
    if escape_reason:
        # The escape is a RECORD, appended before the transition it licensed so
        # the timeline reads in the order things happened.
        append_event(
            spec, "exception", summary=escape_reason, now=ni, actor=actor,
            source=source, gate=GATE_TEST_ON_CLOSE,
        )
    extra: dict[str, Any] = {"from": prev, "to": status}
    if reason:
        extra["summary"] = reason
    if commit_ref:
        extra["commit_ref"] = commit_ref
    append_event(spec, "status_change", now=ni, actor=actor, source=source, **extra)
    raw = build_raw(kind, name, spec, existing=existing)
    await kernel.write_instance(scope, kind, name, raw, invalidate_mode="doc")
    out: dict[str, Any] = {"kind": kind, "name": name, "from": prev, "to": status}
    if warnings:
        out["warnings"] = warnings
    if escape_reason:
        out["gate_exception"] = {"gate": GATE_TEST_ON_CLOSE, "reason": escape_reason}
    return out


async def add_comment(
    kernel: Any, scope: str, kind: str, name: str, body: str, *,
    event_type: str | None = None, actor: str = "mcp", source: str = "mcp",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append a comment / decision to a board item's timeline WITHOUT changing
    status — the FOCUS-feed narration verb (``dna sdlc story comment`` /
    ``issue comment``) + the MCP ``comment`` tool. A decision-shaped body
    auto-promotes to a ``decision`` event unless ``event_type`` is explicit.

    Commentable = carries the ``sdlc.work-item`` trait, so the six board Kinds
    the digest reads but no write tool could touch (Spike / Bug / Task /
    Initiative, plus the two the CLI already handled) are reachable by
    DECLARATION rather than by extending a tuple."""
    commentable = work_item_kinds(kernel) or tuple(sorted(_WRITABLE_KINDS))
    if kind not in commentable:
        raise InvalidTransition(
            f"{kind!r} is not a commentable board Kind "
            f"(writable: {list(commentable)})"
        )
    et = event_type or ("decision" if looks_like_decision(body) else "comment")
    if et not in ("comment", "decision"):
        raise InvalidTransition(f"{et!r} is not a valid comment type (comment/decision)")
    existing = await kernel.get_instance(scope, kind, name)
    if existing is None:
        raise LookupError(f"{kind} {name!r} not found in scope {scope!r}")
    spec = dict(existing.get("spec") or {}) if isinstance(existing, dict) else {}
    ni = now_iso(now)
    backfill_created_at(spec)   # legacy docs self-heal from their own timeline
    append_event(spec, et, summary=body, now=ni, actor=actor, source=source)
    spec["updated_at"] = ni
    raw = build_raw(kind, name, spec, existing=existing)
    await kernel.write_instance(scope, kind, name, raw, invalidate_mode="doc")
    return {"kind": kind, "name": name, "event_type": et}


# ── LiveDna wrappers (the MCP `*_impl` convention — resolve scope + delegate) ─
#
# The board is GLOBAL, so ``tenant`` (the resolved workspace) selects the SCOPE
# via ``live.default_scope(tenant)`` — it is NOT threaded into the write (that
# would raise TenantNotAllowed on a GLOBAL Kind). Under Model B this routes each
# workspace's board into its own scope; single-workspace / OSS resolves to the
# base scope unchanged.


async def create_story_impl(
    live: LiveDna, name: str, *, feature: str, description: str,
    title: str | None = None, priority: str | None = None,
    labels: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    definition_of_done: list[str] | None = None,
    scope: str | None = None, tenant: str | None = None,
    actor: str = "mcp", allow_no_ac_dod: bool = False,
) -> dict[str, Any]:
    """LiveDna wrapper for :func:`create_story` — resolves the (per-workspace)
    scope and writes the GLOBAL board doc there."""
    sc = scope or live.default_scope(tenant)
    return await create_story(
        live.kernel, sc, name, feature=feature, description=description,
        title=title, priority=priority, labels=labels,
        acceptance_criteria=acceptance_criteria,
        definition_of_done=definition_of_done, actor=actor,
        allow_no_ac_dod=allow_no_ac_dod,
    )


async def create_issue_impl(
    live: LiveDna, slug: str, *, description: str, issue_type: str = "bug",
    severity: str = "medium", title: str | None = None,
    related_feature: str | None = None,
    scope: str | None = None, tenant: str | None = None, actor: str = "mcp",
) -> dict[str, Any]:
    """LiveDna wrapper for :func:`create_issue`."""
    sc = scope or live.default_scope(tenant)
    return await create_issue(
        live.kernel, sc, slug, description=description, issue_type=issue_type,
        severity=severity, title=title, related_feature=related_feature,
        actor=actor,
    )


async def create_feature_impl(
    live: LiveDna, name: str, *, title: str, description: str,
    epic: str | None = None, priority: str | None = None,
    labels: list[str] | None = None, scope: str | None = None,
    tenant: str | None = None, actor: str = "mcp",
) -> dict[str, Any]:
    """LiveDna wrapper for :func:`create_feature`."""
    sc = scope or live.default_scope(tenant)
    return await create_feature(
        live.kernel, sc, name, title=title, description=description, epic=epic,
        priority=priority, labels=labels, actor=actor,
    )


async def set_status_impl(
    live: LiveDna, kind: str, name: str, status: str, *,
    reason: str | None = None, scope: str | None = None,
    tenant: str | None = None, actor: str = "mcp",
    commit_ref: str | None = None,
    allow_no_tests: bool = False, no_code: bool = False,
    gate_reason: str | None = None,
) -> dict[str, Any]:
    """LiveDna wrapper for :func:`set_status` — including the close gate, which
    is the whole point: the hosted write path enforces the same methodology the
    workstation does."""
    sc = scope or live.default_scope(tenant)
    return await set_status(
        live.kernel, sc, kind, name, status, reason=reason, actor=actor,
        commit_ref=commit_ref, allow_no_tests=allow_no_tests, no_code=no_code,
        gate_reason=gate_reason,
    )


async def comment_impl(
    live: LiveDna, kind: str, name: str, body: str, *,
    event_type: str | None = None, scope: str | None = None,
    tenant: str | None = None, actor: str = "mcp",
) -> dict[str, Any]:
    """LiveDna wrapper for :func:`add_comment`."""
    sc = scope or live.default_scope(tenant)
    return await add_comment(
        live.kernel, sc, kind, name, body, event_type=event_type, actor=actor,
    )
