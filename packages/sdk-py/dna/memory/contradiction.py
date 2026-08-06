"""Contradiction detection — the OTHER half of "the memory aged in silence".

DNA has always been able to RECORD that one memory replaced another
(``valid_to`` + ``superseded_by_memory``, written by ``forget``). What it could
never do is NOTICE that two memories it believes right now disagree. The
founder's living proof (2026-08-05): the assistant said *"the Kind Livro still
needs approval"* — a memory that was true when it was written and false when it
was recalled. Nothing in the system was capable of raising a hand.

This module raises the hand. It never lowers it for you: a contradiction is
REPORTED, with the evidence and a proposal, and the resolution is a human's
(the story's words — *"apresenta em vez de sobrescrever"*).

What "contradict" MEANS here (and where the definition comes from)
------------------------------------------------------------------
Searched before building, and the search paid (the result is recorded in the
story). Nothing in this package's dependency tree detects contradiction:
``mem0`` rides in transitively under the optional ``maf`` extra, but its
mechanism is an LLM prompt that DELETES the loser — both halves are exactly
what this story forbids. Every mature third party (Graphiti/Zep/mem0) puts a
language model on the write path. The one deterministic-with-a-human design
(``RichSchefren/atlas``, Apache-2.0) is alpha, Neo4j-bound and carries its own
domain schema.

What the search DID find is the definition, already formalised:

    **TOKI — A Bitemporal Operator Algebra for Contradiction Resolution in
    LLM-Agent Persistent Memory** (Ziming Wang, arXiv:2606.06240, §2.1):
    two bitemporal facts contradict when they *agree on subject and predicate,
    disagree on object, and their valid-time periods share a common instant* —
    which under the closed-open convention ``[valid_from, valid_to)`` holds for
    NINE of Allen's thirteen base relations, all but ``before``, ``after``,
    ``meets`` and ``met-by``, the four that share no interior instant. And, in
    the paper's own words, *"contradiction detection is syntactic and requires
    no language model."*

That is implemented here verbatim, and it is why this is not a heuristic:
:func:`claims_contradict` is a comparison of two triples and two intervals.
Of TOKI's four resolution operators this codebase takes ``⊕?`` —
*await-confirmation*, the one that blocks on a human callback — because that is
what the story asked for. ``⊕t`` (last-writer-wins) shows up only as the
PROPOSAL's suggested survivor, never as an action.

Where the structure comes from — and why not from prose
-------------------------------------------------------
A claim is DECLARED (``Engram.spec.claims``), never mined out of a sentence.
Two reasons, both fences this degrau must not climb:

* deterministic entity/relation EXTRACTION from text is degrau 4 of
  ``f-poder-de-grafo``, deliberately sequenced last;
* cardinality/subsumption ontology (OWL/SHACL — the machinery that would say
  "a Kind has ONE approval state") is degrau 3, and degrau 3 is a founder gate.

So the deterministic core decides only what a declared claim makes decidable,
and what it cannot decide it NAMES (:func:`contradiction_report`'s
``undecided``) instead of guessing. That list is the input of the external
:class:`ContradictionScribe` — the exact same seam shape as
:class:`dna.memory.merge.MergeScribe`, a caller-supplied callable, never a
model bound into the kernel.

Why the subject is a *referent* and not lexical overlap
-------------------------------------------------------
``dna.memory.merge`` groups by Jaccard overlap and ``dna.extensions.intel.dedup``
by 0.97 cosine — both find REPETITION. The research that opened this feature
(``Research/rsh-semantica-agi-avaliacao``, finding
``f-lacuna-deteccao-de-contradicao``) separates the two explicitly: repetition
is not disagreement, and two memories that disagree usually share very little
vocabulary ("still needs approval" vs "was approved"). So subject identity here
comes only from DECLARED pointers — a claim's ``subject``, and the ``Kind/name``
referents the Engram already carries in ``area`` / ``source_refs``.

Everything in this module is pure: no kernel, no IO, no clock of its own. The
kernel-bound wiring (transaction time per member, the report's place in the
consolidate dry-run) lives in :func:`dna.memory.verbs.consolidate`.

s-grafo-2-contradicao · degrau 2 de f-poder-de-grafo (2026-08-06).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

__all__ = [
    "ASSERTS",
    "DENIES",
    "WHEN_TO_CLAIM",
    "WHEN_TO_CLAIM_SHORT",
    "Claim",
    "ContradictionScribe",
    "claims_contradict",
    "contradiction_report",
    "intervals_overlap",
    "parse_claims",
    "referents",
    "validate_claims",
]

#: The claim affirms ``object`` of ``subject``. The default — a memory that says
#: something says it positively unless it says otherwise.
ASSERTS = "asserts"

#: The claim DENIES ``object`` of ``subject``. Explicit negation, so "the Kind is
#: NOT approved" can be stated as a claim instead of as prose nobody can compare.
DENIES = "denies"

_POLARITIES = (ASSERTS, DENIES)


# ──────────────────── when a claim is worth declaring ────────────────────
#
# Degrau 2 shipped the ALGEBRA and the field, and the field stayed empty: the
# real memories in the founder's workspace carry no ``claims``, so the detector
# answers ``undecided`` about all of them — correct, and useless. Nothing in any
# face told a model WHEN to declare one, and a model declares what it is asked
# to declare.
#
# Writing that instruction is not the easy half. The failure mode of "declare
# claims" is WORSE than the failure mode of silence: a claim on every recorded
# fact turns the pass into a machine that reports "Barna likes tea" as a
# conflict with "Barna likes coffee", and a detector that flags the normal
# trains its reader to ignore the next one — including the true one. That is the
# same defect this repo already paid for twice (i-101's red error for a normal
# state; the blueprint warning nobody reads).
#
# So the instruction is built around a DISCRIMINANT, never around a category
# list. "Declare when you record a state that can change" is a category list in
# disguise — a preference IS a state that can change, and it is exactly the case
# that must NOT be claimed. The only question that separates the four cases is
# the one :func:`claims_contradict` actually decides:
#
#     does a LATER value of this same (subject, predicate) make this one FALSE?
#
# ⚠️ ONE text, interpolated — never four copies. This string is announced by the
# MCP ``remember`` tool (``dna_cli._mcp_server``), by ``POST /v1/memories``
# (``dna_cli._rest_api``, hence by ``docs/openapi.json`` and both generated
# clients) and by ``dna memory remember --help``. It lives HERE, beside the rule
# it paraphrases, so that changing :func:`claims_contradict` stares at the
# sentence that promised its behavior. It is CODE and not a ``PromptTemplate``
# on purpose — see the note under :data:`WHEN_TO_CLAIM_SHORT`.

#: The full instruction, as every face announces it verbatim.
WHEN_TO_CLAIM = """\
**When to declare one — the test is SUBSTITUTION, not importance.** Declare a \
claim when a LATER value of the same `(subject, predicate)` would make this one \
FALSE. Nothing else. A memory with no claims is the normal case, not a lapse.

- yes — "the workspace plan is Pro" → `{"subject": "Workspace/acme", \
"predicate": "plan", "object": "Pro"}`. A plan replaces the plan.
- yes — "Barna is in Lisbon this week" → `{"predicate": "whereabouts", \
"object": "Lisbon"}`. One whereabouts at a time, so next week's city makes this \
one false.
- no — "Barna likes tea". Liking tea does not stop him liking coffee: values \
that ACCUMULATE never contradict, and claiming them makes the pass report a \
normal preference as a conflict.
- no — "met the client on 2026-08-03". An event HAPPENED, and a later meeting \
does not un-happen it. Events and observations go in the summary alone.

If the same subject can honestly hold two values of that predicate at once, use \
distinct predicates or declare nothing — a pass that flags the normal trains \
its reader to ignore it, including the time it is right.

Format: `subject` may be omitted when the memory's area already names the \
target in `Kind/name` form. Omit `object` only for an EXISTENCE claim ("this \
subject HAS this predicate"), which compares against another existence claim of \
the opposite polarity and never against a valued one. `polarity: "denies"` \
states a negation you want compared ("NOT approved") — `asserts X` beside \
`denies X` is a contradiction, beside `denies Y` it is not."""

#: The same rule at the size of a CLI flag's help. A separate string because
#: ``--claim``'s help sits beside a dozen other options and 1.3 KB there buries
#: them; it is kept adjacent to the long form so an edit to one is read next to
#: the other. The long form still reaches the CLI user, on the command's own
#: ``--help``.
#:
#: ⚠️ Why this is CODE and not a ``PromptTemplate``/``prompt_defaults`` entry,
#: even though a model reads it: the house maxim ("a voz do agente é dado")
#: covers what an agent SAYS — a briefing, a guidance block, something a tenant
#: may legitimately reword. This is the tool CONTRACT: it paraphrases what
#: :func:`claims_contradict` decides, and a tenant rewording it would make the
#: door promise a semantics the detector does not implement, with nothing able
#: to notice. It is the twin of the JSON Schema printed beside it, not of a
#: voice. It is also unreachable as data at the moment it is needed: FastMCP
#: fixes tool descriptions when ``build_server`` runs, before any scope or
#: tenant exists to resolve a template against.
WHEN_TO_CLAIM_SHORT = (
    "Declare one only when a LATER value of the same predicate would make this "
    "one false (a plan, a location, a status, an approval) — never for values "
    "that ACCUMULATE (likes tea AND coffee) nor for events that happened."
)

#: A referent looks like ``Kind/name`` — the shape ``Engram.area`` is documented
#: with ("Scoped target: Feature/X, Epic/Y, or Roadmap/Z") and the shape
#: ``source_refs`` holds. The filter is load-bearing, not cosmetic: the MCP
#: ``remember`` tool defaults ``area`` to the literal ``"general"`` and copies it
#: into ``source_refs``, so an unfiltered referent would put EVERY default memory
#: in one bucket and call it a shared subject.
_REFERENT_RE = re.compile(r"^[^/\s][^/]*/[^/\s].*$")

#: Claim keys the schema declares. Anything else is an authoring mistake worth a
#: refusal, not a silently dropped field (``additionalProperties: false`` says
#: the same thing on the storage side; this says it at the verb, with a message).
_CLAIM_KEYS = frozenset(
    {"subject", "predicate", "object", "polarity", "valid_from", "valid_to"}
)


# ─────────────────────────── the claim ───────────────────────────


@dataclass(frozen=True)
class Claim:
    """One declared assertion, normalized for comparison.

    ``subject``/``predicate``/``object`` keep the author's text for DISPLAY;
    the ``*_key`` fields are what :func:`claims_contradict` compares (stripped +
    casefolded, so ``Approved`` and ``approved`` are the same answer and not a
    contradiction anybody has to adjudicate).

    ``object`` is ``None`` for an existence claim ("this subject HAS this
    predicate", or under :data:`DENIES`, "it does not"). Two such claims are
    comparable to each other; an existence claim and a valued one are not, and
    the module says so rather than inventing a comparison.
    """

    memory: str
    subject: str
    predicate: str
    object: Any = None
    polarity: str = ASSERTS
    #: World-time window this claim is asserted over. Inherited from the
    #: memory's own ``valid_from``/``valid_to`` unless the claim narrows it.
    valid_from: str | None = None
    valid_to: str | None = None

    @property
    def subject_key(self) -> str:
        return _norm_text(self.subject)

    @property
    def predicate_key(self) -> str:
        return _norm_text(self.predicate)

    @property
    def object_key(self) -> str | None:
        return None if self.object is None else _norm_value(self.object)

    def as_evidence(self) -> dict[str, Any]:
        """The display projection carried in the report."""
        out: dict[str, Any] = {
            "memory": self.memory,
            "subject": self.subject,
            "predicate": self.predicate,
            "polarity": self.polarity,
        }
        if self.object is not None:
            out["object"] = self.object
        if self.valid_from:
            out["valid_from"] = self.valid_from
        if self.valid_to:
            out["valid_to"] = self.valid_to
        return out


def _norm_text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _norm_value(value: Any) -> str:
    """A scalar's canonical comparison string.

    Booleans FIRST — ``isinstance(True, int)`` is true in Python, so a bool that
    fell through to the numeric branch would compare as ``1`` and make
    ``object: true`` and ``object: 1`` the same claim.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # 2.0 and 2 are the same assertion; 2.5 keeps its point.
        return str(int(value)) if value.is_integer() else repr(value)
    return _norm_text(value)


def validate_claims(raw: Any) -> list[dict[str, Any]]:
    """Validate + canonicalize a caller-supplied ``claims`` block.

    Raises ``ValueError`` naming the offending index and field. This is the
    verb-level chokepoint every face funnels through (``remember`` →
    ``dna.memory.verbs.remember``), so a malformed claim is refused with a
    message at the MCP/REST/CLI door instead of being stored and quietly
    ignored by the detector later. The Engram schema declares the same shape,
    so a raw ``write_document`` is refused too — two doors, one contract.

    Returns the claims with defaults filled in (``polarity`` → ``asserts``),
    ready to be persisted.
    """
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise ValueError(
            f"claims must be a list of objects, got {type(raw).__name__}"
        )
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        where = f"claims[{i}]"
        if not isinstance(item, dict):
            raise ValueError(f"{where} must be an object, got {type(item).__name__}")
        unknown = sorted(set(item) - _CLAIM_KEYS)
        if unknown:
            raise ValueError(
                f"{where} has unknown field(s) {unknown}; "
                f"allowed: {sorted(_CLAIM_KEYS)}"
            )
        predicate = item.get("predicate")
        if not isinstance(predicate, str) or not predicate.strip():
            raise ValueError(f"{where}.predicate is required and must be a non-empty string")
        claim: dict[str, Any] = {"predicate": predicate.strip()}
        subject = item.get("subject")
        if subject is not None:
            if not isinstance(subject, str) or not subject.strip():
                raise ValueError(f"{where}.subject must be a non-empty string when present")
            claim["subject"] = subject.strip()
        if "object" in item:
            value = item["object"]
            if not isinstance(value, (str, int, float, bool)) and value is not None:
                raise ValueError(
                    f"{where}.object must be a string, number, boolean or null, "
                    f"got {type(value).__name__}"
                )
            claim["object"] = value
        polarity = item.get("polarity", ASSERTS)
        if polarity not in _POLARITIES:
            raise ValueError(
                f"{where}.polarity must be one of {list(_POLARITIES)}, got {polarity!r}"
            )
        claim["polarity"] = polarity
        for field in ("valid_from", "valid_to"):
            value = item.get(field)
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{where}.{field} must be an ISO-8601 timestamp string")
            claim[field] = value.strip()
        out.append(claim)
    return out


def referents(spec: dict[str, Any]) -> frozenset[str]:
    """The subjects this memory DECLARES it is about.

    A claim's ``subject`` always counts (the author named it deliberately).
    ``area`` and ``source_refs`` count only when they look like a reference —
    see :data:`_REFERENT_RE` for why the filter exists.
    """
    if not isinstance(spec, dict):
        return frozenset()
    found: set[str] = set()
    for claim in spec.get("claims") or []:
        if isinstance(claim, dict):
            subject = claim.get("subject")
            if isinstance(subject, str) and subject.strip():
                found.add(_norm_text(subject))
    candidates: list[Any] = [spec.get("area")]
    refs = spec.get("source_refs")
    if isinstance(refs, (list, tuple)):
        candidates.extend(refs)
    for value in candidates:
        if isinstance(value, str) and _REFERENT_RE.match(value.strip()):
            found.add(_norm_text(value))
    return frozenset(found)


def _document_referent(spec: dict[str, Any]) -> str:
    """The memory's own ``Kind/name`` referent, as the AUTHOR wrote it.

    Deliberately not ``sorted(referents(spec))[0]``: that set is casefolded for
    matching and also carries other claims' subjects, so a claim would silently
    default to a sibling claim's subject with the author's capitalisation lost.
    """
    candidates: list[Any] = [spec.get("area")]
    refs = spec.get("source_refs")
    if isinstance(refs, (list, tuple)):
        candidates.extend(refs)
    found = [
        value.strip() for value in candidates
        if isinstance(value, str) and _REFERENT_RE.match(value.strip())
    ]
    return sorted(found)[0] if found else ""


def parse_claims(name: str, spec: dict[str, Any]) -> tuple[Claim, ...]:
    """The comparable claims of ONE memory.

    Lenient by construction (never raises): this reads STORED documents, and a
    document that got past both doors with a malformed claim must not be able to
    take a consolidation pass down — the claim is skipped, and a skipped claim
    simply participates in no comparison.

    Two defaults do real work:

    * ``subject`` falls back to the memory's first ``Kind/name`` referent, so a
      memory whose ``area`` already names what it is about need only declare
      ``{predicate, object}``;
    * the world-time window falls back to the MEMORY's ``valid_from``/
      ``valid_to``, which is the bi-temporal window DNA has always kept — the
      claim inherits the memory's validity unless it narrows it.
    """
    if not isinstance(spec, dict):
        return ()
    raw = spec.get("claims")
    if not isinstance(raw, (list, tuple)):
        return ()
    default_subject = _document_referent(spec)
    memory_from = _as_text(spec.get("valid_from"))
    memory_to = _as_text(spec.get("valid_to"))

    out: list[Claim] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        predicate = item.get("predicate")
        if not isinstance(predicate, str) or not predicate.strip():
            continue
        subject = item.get("subject")
        subject = subject.strip() if isinstance(subject, str) and subject.strip() else default_subject
        if not subject:
            continue  # an unanchored claim compares with nothing.
        polarity = item.get("polarity", ASSERTS)
        if polarity not in _POLARITIES:
            continue
        value = item.get("object")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            continue
        out.append(Claim(
            memory=name,
            subject=subject,
            predicate=predicate.strip(),
            object=value,
            polarity=polarity,
            valid_from=_as_text(item.get("valid_from")) or memory_from,
            valid_to=_as_text(item.get("valid_to")) or memory_to,
        ))
    return tuple(out)


def _as_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


# ─────────────────────── the syntactic predicate ───────────────────────


def _instant(value: str | None, *, default: datetime) -> datetime:
    """An ISO-8601 boundary as an aware UTC datetime; unparseable → ``default``.

    An open boundary (``None``) and a boundary nobody can read are the same
    thing to an overlap test — "this end is not pinned" — and treating a typo as
    a CLOSED interval would silently stop reporting a real contradiction.
    """
    if not value:
        return default
    text = value.strip()
    if text.endswith(("z", "Z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return default
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


_MIN = datetime.min.replace(tzinfo=timezone.utc)
_MAX = datetime.max.replace(tzinfo=timezone.utc)


def intervals_overlap(
    a_from: str | None, a_to: str | None,
    b_from: str | None, b_to: str | None,
) -> bool:
    """Do two closed-open world-time windows ``[from, to)`` share an instant?

    This is TOKI §2.1's condition and Allen's thirteen base relations minus the
    four that share no interior instant (``before``, ``after``, ``meets``,
    ``met-by``) — nine of thirteen. ``meets`` is the one worth naming: a memory
    invalidated at exactly the instant its successor becomes valid is a clean
    SUCCESSION, not a disagreement, and reporting it would make every correctly
    superseded memory look like a conflict.

    Two comparisons, no dependency: the mature interval libraries on PyPI are
    LGPL (``portion``) and GPL (``pyintervals``) and this SDK is MIT — a licence
    the size of a licence, for an expression the size of an expression.
    """
    start_a, end_a = _instant(a_from, default=_MIN), _instant(a_to, default=_MAX)
    start_b, end_b = _instant(b_from, default=_MIN), _instant(b_to, default=_MAX)
    return start_a < end_b and start_b < end_a


def claims_contradict(a: Claim, b: Claim) -> str | None:
    """Why ``a`` and ``b`` contradict — or ``None`` when they do not.

    The three answers, in the order they are decided:

    * ``None`` — different subject, different predicate, or windows that share
      no instant. The last is the bi-temporal case that keeps an honest
      succession out of the report.
    * ``"polarity"`` — the SAME object, asserted by one and denied by the other
      (or both existence claims with opposite polarity). Explicit negation.
    * ``"object"`` — both assert the same (subject, predicate) with different
      objects. TOKI's condition, and the functional-dependency violation a
      relational database would name: one subject, one attribute, one value at
      an instant.

    Deliberately NOT a contradiction: ``asserts X`` beside ``denies Y`` for
    ``X ≠ Y``. Affirming one value and denying a different one is consistent,
    and a detector that flagged it would train its readers to dismiss it.
    """
    if a.memory == b.memory:
        return None
    if a.subject_key != b.subject_key or a.predicate_key != b.predicate_key:
        return None
    if not intervals_overlap(a.valid_from, a.valid_to, b.valid_from, b.valid_to):
        return None
    same_object = a.object_key == b.object_key
    if a.polarity != b.polarity:
        return "polarity" if same_object else None
    if a.polarity == DENIES:
        return None  # denying two different values is not a disagreement.
    if a.object_key is None or b.object_key is None:
        return None  # an existence claim and a valued one are not comparable.
    return None if same_object else "object"


# ─────────────────────────── the scribe seam ───────────────────────────


class ContradictionScribe(Protocol):
    """The EXTERNAL judgement seam — for the pairs the rule cannot decide.

    Input: the member specs of one ``undecided`` group (memories that share a
    declared referent but carry no comparable claims), each the full memory
    ``spec`` dict, read-only, sorted by name.

    Output: ``{"contradicts": bool, "reason": str, "predicate"?: str}``. A
    ``True`` verdict promotes the group into ``contradictions`` marked
    ``decided_by: "scribe"`` — never marked as a rule, because a reader must be
    able to tell the syntactic verdict from the modelled one.

    The caller (a service, never this SDK) owns the model, the prompt and the
    cost. A raising or malformed scribe leaves the group in ``undecided`` with a
    ``scribe_error`` — it never breaks the pass, and it never upgrades silence
    into a verdict.
    """

    def __call__(self, group: Sequence[dict[str, Any]]) -> dict[str, Any]: ...


# ─────────────────────────── the report ───────────────────────────


def _elect_survivor(
    names: Sequence[str],
    recorded_at: dict[str, str] | None,
    specs_by_name: dict[str, dict[str, Any]],
    *,
    approximate: frozenset[str] = frozenset(),
    now: datetime | None = None,
) -> tuple[str, str]:
    """Which belief a human would most likely keep, and on WHICH clock.

    Transaction time first (``recorded_at`` — when the system came to believe
    it, from ``dna_versions.created_at``, the axis degrau 0 opened). That is the
    clock that matters here and the spec's ``created_at`` is not a substitute:
    ``created_at`` is authored, so a memory can claim to be from last year and a
    correction filed today can claim to be from before the thing it corrects.

    ``approximate`` names the stamps that are an UPPER bound rather than the
    fact — a memory whose version 1 was pruned by ``VERSION_CHURN_RETENTION``
    (which caps Engram at 3, and recall's reconsolidation reaches that in three
    glances, so in production this is the common case, not the corner). Such a
    stamp reads NEWER than the truth, so it is sound in exactly one direction:

    * it LOSES the election → its true stamp is older still, so the loss holds;
    * it WINS the election → the win rests on the very error the bound carries,
      and the whole proposal falls back to the authored clock.

    Which of the two decided is reported as ``basis``, because a proposal whose
    basis is invisible is a proposal nobody can check.
    """
    from dna.memory.merge import canonical_name

    stamped = {n: recorded_at.get(n) for n in names} if recorded_at else {}
    if stamped and all(stamped.get(n) for n in names):
        # newest transaction time wins; name breaks a tie, so the election is total.
        winner = max(names, key=lambda n: (str(stamped[n]), n))
        if winner not in approximate:
            return winner, "recorded_at"
    return canonical_name(list(names), specs_by_name, now=now), "spec"


def contradiction_report(
    members: Sequence[tuple[str, dict[str, Any]]],
    *,
    recorded_at: dict[str, str] | None = None,
    recorded_at_approximate: Sequence[str] = (),
    scribe: ContradictionScribe | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The structured contradiction report — what a human adjudicates.

    ``members`` are the memories to compare as ``(name, spec)`` pairs. The
    caller decides the set; ``consolidate`` passes the CURRENTLY VALID ones, so
    "these are beliefs the system holds at the same time" is true by
    construction and the interval test then only has to rule out an honest
    succession within that set.

    ``recorded_at`` maps memory name → transaction timestamp
    (``dna_versions.created_at``, resolved by the kernel-bound caller). Optional:
    without it the report still detects, and says its proposal rests on the
    authored clock instead. ``recorded_at_approximate`` names the stamps that are
    an upper bound because the store pruned that memory's first version — see
    :func:`_elect_survivor` for the one direction such a stamp may still decide.

    Returns::

        {
          "contradictions": [
            {"subject", "predicate",
             "names": [...],                    # every memory in the conflict
             "pairs": [{"a","b","reason","a_claim","b_claim"}],
             "decided_by": "rule" | "scribe",
             "proposal": {"strategy": "await_confirmation",
                          "suggested_keep": name, "suggested_supersede": [...],
                          "basis": "recorded_at" | "spec"}}
          ],
          "undecided": [{"referent", "names", "reason", "scribe_error"?}],
          "claims": <how many comparable claims were read>,
        }

    ``basis`` lives on each PROPOSAL, not on the report: a pass can hold one
    conflict between two memories the store has version history for and another
    between two it does not, and a single report-level flag would have to lie
    about one of them.

    NOTHING here writes. ``proposal`` is TOKI's ``⊕?`` await-confirmation
    operator: the pair is detected, the loser is named, and the write waits for
    a human. ``suggested_keep`` is a suggestion in the literal sense — applying
    it is ``forget(loser, superseded_by=keep)``, which is the caller's call and
    the caller's alone.
    """
    specs_by_name = {name: (spec or {}) for name, spec in members}
    approximate = frozenset(recorded_at_approximate or ())
    all_claims: list[Claim] = []
    for name, spec in members:
        all_claims.extend(parse_claims(name, spec or {}))

    # ── the syntactic verdict, grouped by the key TOKI compares on ──────────
    by_key: dict[tuple[str, str], list[Claim]] = {}
    for claim in all_claims:
        by_key.setdefault((claim.subject_key, claim.predicate_key), []).append(claim)

    contradictions: list[dict[str, Any]] = []
    conflicted: set[str] = set()
    for key in sorted(by_key):
        claims = sorted(by_key[key], key=lambda c: (c.memory, c.predicate, str(c.object)))
        pairs: list[dict[str, Any]] = []
        for i, a in enumerate(claims):
            for b in claims[i + 1:]:
                reason = claims_contradict(a, b)
                if reason is None:
                    continue
                pairs.append({
                    "a": a.memory, "b": b.memory, "reason": reason,
                    "a_claim": a.as_evidence(), "b_claim": b.as_evidence(),
                })
        if not pairs:
            continue
        names = sorted({p["a"] for p in pairs} | {p["b"] for p in pairs})
        conflicted.update(names)
        keep, basis = _elect_survivor(
            names, recorded_at, specs_by_name, approximate=approximate, now=now,
        )
        contradictions.append({
            "subject": claims[0].subject,
            "predicate": claims[0].predicate,
            "names": names,
            "pairs": pairs,
            "decided_by": "rule",
            "proposal": {
                "strategy": "await_confirmation",
                "suggested_keep": keep,
                "suggested_supersede": [n for n in names if n != keep],
                "basis": basis,
            },
        })

    # ── what the rule could NOT decide — the scribe's input ─────────────────
    claimed_by_name = {c.memory for c in all_claims}
    by_referent: dict[str, list[str]] = {}
    for name, spec in members:
        for referent in referents(spec or {}):
            by_referent.setdefault(referent, []).append(name)

    undecided: list[dict[str, Any]] = []
    for referent in sorted(by_referent):
        names = sorted(set(by_referent[referent]))
        if len(names) < 2 or all(n in conflicted for n in names):
            continue
        reason = (
            "no comparable claims — every memory here declares claims, but none "
            "share a (subject, predicate)"
            if all(n in claimed_by_name for n in names)
            else "no claims to compare — the disagreement, if any, is only in prose"
        )
        entry: dict[str, Any] = {
            "referent": referent, "names": names, "reason": reason,
        }
        if scribe is not None:
            verdict, error = _ask_scribe(scribe, [specs_by_name[n] for n in names])
            if error is not None:
                entry["scribe_error"] = error
            elif verdict.get("contradicts"):
                keep, basis = _elect_survivor(
                    names, recorded_at, specs_by_name,
                    approximate=approximate, now=now,
                )
                contradictions.append({
                    "subject": referent,
                    "predicate": str(verdict.get("predicate") or ""),
                    "names": names,
                    "pairs": [],
                    "decided_by": "scribe",
                    "reason": str(verdict.get("reason") or ""),
                    "proposal": {
                        "strategy": "await_confirmation",
                        "suggested_keep": keep,
                        "suggested_supersede": [n for n in names if n != keep],
                        "basis": basis,
                    },
                })
                continue
        undecided.append(entry)

    contradictions.sort(key=lambda c: (c["subject"], c["predicate"], c["names"]))
    return {
        "contradictions": contradictions,
        "undecided": undecided,
        "claims": len(all_claims),
    }


def _ask_scribe(
    scribe: ContradictionScribe, group: list[dict[str, Any]],
) -> tuple[dict[str, Any], str | None]:
    """Call the external judge, converting every failure into a NAMED silence."""
    try:
        verdict = scribe(group)
    except Exception as exc:  # noqa: BLE001 — the scribe is optional; never break the pass
        return {}, f"{type(exc).__name__}: {exc}"
    if not isinstance(verdict, dict) or "contradicts" not in verdict:
        return {}, "scribe returned no verdict"
    return verdict, None
