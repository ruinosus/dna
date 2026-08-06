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
  through ``kernel.write_document`` (so cache invalidation, hooks + validation
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
from dna.kernel.errors import DocumentNameTaken
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

# The spec fields a READ surface dates, sorts or filters a board document by —
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
# This is not documentation. ``_digest.build_digest`` reads a document's date
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
#     "last touched" everywhere a document has not closed yet.
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


class DocumentExists(ValueError):
    """A ``create_*`` verb was pointed at a name that is already taken.

    ``kernel.write_document`` is an UPSERT keyed on the document name, so a
    create with no existence check is a silent destroyer: an agent guessing a
    name (or retrying, or working from a stale board) replaced the live
    document's status, timeline, acceptance_criteria and definition_of_done and
    got a success back. "Create" is the one verb that must never be an update.

    The message NAMES the existing document and its current status, and points at
    the verbs that DO update (``set_status`` / ``comment`` / ``write_document``) —
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
    """The kernel document envelope for a board write (apiVersion + metadata).

    ``existing`` is the document being UPDATED, when there is one. Pass it and
    the envelope is carried forward instead of rebuilt:

    * ``metadata`` keeps every key it had (``labels``, ``description``,
      ``group``, ``icon``, anything an adapter or a human put there), with
      ``name`` re-asserted. Without this, ``set_status`` and ``comment`` — the
      two verbs that load-modify-write — replaced the whole mapping with
      ``{"name": name}``, so a single status transition silently deleted every
      other metadata key the document carried.
    * ``apiVersion`` keeps the document's own. Forcing :data:`SDLC_API_VERSION`
      re-homed any board document living under a different apiVersion (a
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
    it does, so the earliest ``at`` is the moment the document entered the
    board — recorded by the writer itself, not inferred after the fact. Pure:
    the caller decides what to do when it returns ``None``.

    Deliberately takes the MINIMUM rather than ``timeline[0]``: the list is
    append-ordered in practice, but a hand-edited or merged board can reorder
    it, and the earliest stamp is the claim we actually want to make."""
    stamps = _timeline_stamps(spec)
    return min(stamps) if stamps else None


def latest_timeline_at(spec: dict[str, Any]) -> str | None:
    """The ``at`` of the most recent timeline event — the honest stand-in for a
    missing ``updated_at`` (the last time the document demonstrably moved)."""
    stamps = _timeline_stamps(spec)
    return max(stamps) if stamps else None


def backfill_created_at(spec: dict[str, Any]) -> bool:
    """Self-heal a legacy document's missing ``created_at`` in place, from its
    own timeline. Returns True when it stamped something.

    Called on every load-modify-write (``set_status`` / ``add_comment``) so a
    document filed before the i-078 fix repairs itself the next time anybody
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
    """Decide the honest repair for one already-written document.

    Returns ``(fields_to_stamp, provenance)``; ``fields_to_stamp`` is empty
    unless the document is genuinely missing something :data:`DATED_SPEC_FIELDS`
    declares for its Kind. Pure — the caller supplies the git signals and does
    the writing (``dna sdlc backfill-dates``).

    The date is taken from the closest available witness to the event:

    1. ``timeline`` — the document's OWN record, appended by the create path at
       create time. Nothing is closer.
    2. ``git_added_at`` — the commit that ADDED the file to the board. An
       external witness, typically the same day, and verifiable by anyone with
       the repo.
    3. nothing → provenance ``undatable``, and the document is left alone.

    ``now`` is deliberately NOT on that list. Stamping today's date on 51
    Issues would make them all look filed today, put them all in the current
    digest window, and hide them from every window they actually belong to —
    a louder version of the bug this repairs (i-078). An undated document that
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
        # The last movement the document can prove; a document that never moved
        # was last updated when it was created.
        fields["updated_at"] = latest_timeline_at(spec) or git_touched_at or created
    return fields, provenance


async def existing_or_none(
    kernel: Any, scope: str, kind: str, name: str,
) -> dict[str, Any] | None:
    """``kernel.get_document`` treating an ABSENT SCOPE as an absent document.

    A create is very often the FIRST write into a scope — a brand-new
    per-workspace board under Model B — and a source may signal "this scope holds
    nothing yet" by raising rather than returning ``None`` (the filesystem adapter
    raises ``FileNotFoundError`` for a directory that does not exist). An empty
    scope contains nothing to overwrite, so that is an absent document.

    ``FileNotFoundError`` ONLY: every other read failure propagates. Treating a
    transient read error as "nothing there" would hand the overwrite hole straight
    back — one flaky read would license the destruction the check exists to stop."""
    try:
        return await kernel.get_document(scope, kind, name)
    except FileNotFoundError:
        return None


async def refuse_if_exists(
    kernel: Any, scope: str, kind: str, name: str, *, overwrite: bool = False,
) -> None:
    """Raise :class:`DocumentExists` when ``(scope, kind, name)`` is already taken.

    The one existence check every ``create_*`` core runs before it writes. It uses
    ``kernel.get_document`` — the same read the update verbs use — so a document
    the caller could read is a document the create refuses to bury.

    ``overwrite=True`` skips it. That door exists because a backfill / migration
    genuinely means "replace this", and refusing outright would only push such a
    caller into hand-rolling ``kernel.write_document`` — which is how a document
    ends up with no timeline at all. It is off by default and no MCP tool exposes
    it: over the wire, the update verbs cover every legitimate case.

    NOT a transaction. Two creates racing on the same name can both find it free;
    the kernel has no unique-name constraint to lean on, and inventing a lock here
    would be a distributed-systems claim this function cannot honour. What it does
    remove is the entire class of NON-concurrent overwrites — the guessed name, the
    retry, the stale board — which is what actually destroyed documents."""
    if overwrite:
        return
    existing = await existing_or_none(kernel, scope, kind, name)
    if existing is None:
        return
    spec = existing.get("spec") if isinstance(existing, dict) else None
    status = (spec or {}).get("status") if isinstance(spec, dict) else None
    title = (spec or {}).get("title") if isinstance(spec, dict) else None
    raise DocumentExists(
        f"{kind} {name!r} already exists in scope {scope!r}"
        + (f" (status: {status})" if status else "")
        + (f" — {title!r}" if title else "")
        + ". Refusing to create over it: that would replace its status, timeline "
          "and exit criteria. To CHANGE it use set_status (status), comment "
          "(narration) or write_document (any field, merged); to file something "
          "new, pick a name that is free."
    )


def next_issue_number(existing_names: list[str]) -> int:
    """Next free ``i-NNN`` number given the existing Issue doc names (pure).

    ``max + 1``. Note what that implies for any check built on the SAME read:
    the answer is free BY CONSTRUCTION, so no "is this number taken?" filter
    over ``existing_names`` can ever reject it. Rejecting a colliding number
    needs information this list does not carry — see
    :func:`duplicate_issue_numbers` for the detection that does."""
    max_n = 0
    for nm in existing_names:
        m = re.match(r"^i-(\d+)", nm or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def duplicate_issue_numbers(existing_names: list[str]) -> dict[int, list[str]]:
    """``{NNN: [names…]}`` for every ``i-NNN`` claimed by more than one doc (pure).

    The id of an Issue is its NUMBER; the only thing a write path can claim
    atomically is its NAME, ``i-NNN-<slug>``. Two different slugs on the same
    number are two different names, so every guarantee in this module —
    #242's probe, the ``if_absent`` claim, the SQL primary key — grants both
    writes, and is right to. Measured on the dna-cloud board 05/08/2026: 13
    Issues sharing 4 numbers (``i-094`` ×4, ``i-097`` ×5).

    Nothing at ALLOCATION time prevents that when the writers cannot see each
    other, and the case that produced those 13 is the extreme of it: agents in
    separate git WORKTREES are separate filesystems — no lock, no ``O_EXCL``,
    no primary key spans them — and because the file names differ, ``git
    merge`` joins both without a conflict.

    So this is DETECTION, deliberately: cheap, exact, and it runs on the one
    artifact where the writers finally meet — the MERGED tree. Belongs in CI.

    The structural cure is to make the id the whole name (``i-NNN``: one path,
    so ``if_absent`` becomes a real number lock AND git raises a real conflict)
    or a number-keyed allocator Kind. Both are data-model decisions."""
    by_number: dict[int, list[str]] = {}
    for nm in sorted(existing_names):
        m = re.match(r"^i-(\d+)", nm or "")
        if m:
            by_number.setdefault(int(m.group(1)), []).append(nm)
    return {n: names for n, names in sorted(by_number.items()) if len(names) > 1}


async def issue_number_is_free(kernel: Any, scope: str, number: int) -> bool:
    """Is ``i-NNN`` unclaimed *right now*, by ANY slug? (probe-then-write path)

    The number-keyed counterpart of :func:`existing_or_none`. The probe #242
    installed asked ``get_document("i-NNN-<our slug>")``, which answers a
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


# ── async kernel-level cores (the write goes through kernel.write_document) ──
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
    MCP ``create_story`` tool. Routes through ``kernel.write_document`` (hooks +
    cache fire) into the resolved (per-workspace) ``scope``.

    Refuses an existing ``name`` (:func:`refuse_if_exists`) — a create is never
    an update — and refuses a Story with no exit criteria when the Kind declares
    ``sdlc.exit-criteria-required`` (:func:`gates.refuse_without_exit_criteria`).
    That gate used to live in the CLI's ``cmd_story_create`` only, so the MCP
    tool created criteria-less Stories the CLI would have rejected."""
    # Existence first: when a caller both reuses a taken name AND omits its
    # exit criteria, "that name is already s-one, status in-progress" is the
    # more specific, more actionable fact — and it is the refusal that protects
    # a live document.
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
    await kernel.write_document(scope, "Story", name, raw, invalidate_mode="doc")
    return {"kind": "Story", "name": name, "status": status, "feature": feature}


async def create_issue(
    kernel: Any, scope: str, slug: str, *, description: str,
    issue_type: str = "bug", severity: str = "medium",
    title: str | None = None,
    related_feature: str | None = None, related_finding: str | None = None,
    owner: str | None = None, status: str = "open",
    actor: str = "mcp", source: str = "mcp",
    now: datetime | None = None, overwrite: bool = False,
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
    the name or raises ``DocumentNameTaken``, arbitrated by the SQL adapter's
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
    by construction in the very list it was computed from — so this function
    deliberately does NOT pretend to guard the id. The detection that works is
    :func:`duplicate_issue_numbers`, run over the merged tree in CI; the cure
    is structural (name == ``i-NNN``, or a number-keyed allocator Kind) and is
    specced separately.

    The enumeration is still O(N) rows — documented rather than hidden — though
    it pushes a ``projection`` down, so it moves N names instead of N full Issue
    specs."""
    names: list[str] = []
    async for row in kernel.query(scope, "Issue", projection=["name"]):
        meta = row.get("metadata") if isinstance(row, dict) else None
        nm = (meta or {}).get("name") if isinstance(meta, dict) else None
        names.append(nm or (row.get("name") if isinstance(row, dict) else "") or "")
    n = next_issue_number(names)
    ni = now_iso(now)
    spec = build_issue_spec(
        description=description, issue_type=issue_type, severity=severity,
        status=status, title=title, owner=owner,
        related_feature=related_feature, related_finding=related_finding,
        now=ni, actor=actor, source=source,
    )

    if overwrite:
        name = f"i-{n:03d}-{slug}"
        await kernel.write_document(
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
                await kernel.write_document(
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
            except DocumentNameTaken:
                continue  # somebody else took it between our read and our write
        if await issue_number_is_free(kernel, scope, candidate_n):
            await kernel.write_document(
                scope, "Issue", name, raw, invalidate_mode="doc")
            return {"kind": "Issue", "name": name, "type": issue_type,
                    "severity": severity}
    raise DocumentExists(  # pragma: no cover — 1000 consecutive collisions
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
    await kernel.write_document(scope, "Feature", name, raw, invalidate_mode="doc")
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
    existing = await kernel.get_document(scope, kind, name)
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
    await kernel.write_document(scope, kind, name, raw, invalidate_mode="doc")
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
    existing = await kernel.get_document(scope, kind, name)
    if existing is None:
        raise LookupError(f"{kind} {name!r} not found in scope {scope!r}")
    spec = dict(existing.get("spec") or {}) if isinstance(existing, dict) else {}
    ni = now_iso(now)
    backfill_created_at(spec)   # legacy docs self-heal from their own timeline
    append_event(spec, et, summary=body, now=ni, actor=actor, source=source)
    spec["updated_at"] = ni
    raw = build_raw(kind, name, spec, existing=existing)
    await kernel.write_document(scope, kind, name, raw, invalidate_mode="doc")
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
