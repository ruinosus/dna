"""The `Solution` side of ``dna solution`` — the record that outlives the file.

Why there is a second copy of the answers
=========================================
``dna solution new`` writes ``.copier-answers.<service>.yml``; this module
writes a ``Solution`` instance holding the same answers. Two copies of one
fact looks like a mistake until you read what fatia 3 measured:

    an answer behind ``when:`` is ERASED from the answers file when its
    condition stops holding, and comes back as the template's DEFAULT — not as
    what the human said — if the condition returns.
    (``graph_obo: true`` → *(absent)* → ``false``, in one round trip.)

``dna solution update`` could name that loss and print the value; it could not
undo it, because *the answers file was the only place holding it and the update
rewrites that file*. The guide says so in as many words, and then says what
would fix it: **"a record that outlives the answers file is the only place such
a value can survive."** This module is that record, and restoring the value is
the one thing it does that nothing else can.

Two consequences the same measurement forces on the shape, both live in
``solution.kind.yaml`` and are restated here because this is the file that
would break them:

* ``services[].answers`` is a FREE map and requires no key — a schema that
  required a gated answer would refuse to store exactly the case this record
  exists to rescue;
* the write-back ACCUMULATES (``{**recorded, **after}``). Recording only the
  post-update file would drop the gated value from here too, on the very
  update that dropped it from there, and the record would be a slower copy of
  the file instead of a longer memory than it. (Verified against copier 9.17:
  a ``data=`` key the template does not ask about is ignored and is not
  written back to the answers file, so an accumulated answer costs nothing
  when its question goes away.)

Where the merge happens, and why it is one line
===============================================
:func:`merged_before` is folded into ``update``'s ``before`` — the single
variable that already feeds *every* comparison the report makes
(``defaults_that_moved``, ``divergent_answers``) and the ``data=`` Copier
receives. So the recorded answers are compared, re-passed and reported through
the paths fatia 3 already built, rather than through a second set this file
would own.

⚠️ ``lost_answers`` is deliberately NOT given the merged view: it asks what the
FILE lost between this run's start and end, and merging would make an answer
this record restored look like a loss forever.

⭐ Two halves, and the line between them is ONE FACT, ONE HOUSE
==============================================================
Founder decision, 07/08/2026, with the numbers on screen — and it is narrower
than the spec that preceded it, deliberately:

* ``services[]`` **stays**, and keeps ``name``, ``answers_file``,
  ``template{src,ref}`` and ``answers``. That is the **provenance of the
  render**: which template, at which ref, answering what. ``required: [title,
  services]`` stays, and ``dna solution`` does not break.
* **Only the cost commitment moved.** ``pode_dormir`` is gone from
  ``services[]`` and the fact is ``App.can_sleep``, because *the invoice is per
  deployment and the App IS the deployment.* One fact, one house — the failure a
  second house creates is two answers to "does this sleep?" that disagree. The
  Copier answer that produced it is still in ``answers``, verbatim; what ended
  was the PROMOTION of it.
* ``services[].name`` and ``apps[]`` carry the same set of names — and
  **``apps[]`` is the join the kernel can enforce.** ⚠️ Measured in #351:
  ``relation_values`` reads ``spec.get(rel.name)`` at the TOP LEVEL, always, so
  a pointer inside ``services[].items`` cannot be a relation. Declaring one
  there lints green, reports ``resolved/enforced = True/True`` and resolves
  ``[]`` — a guard that announces it vetoes writes and reads nothing.

So this module writes **both halves**: the ledger here, the four identity
fields (``service_name``, ``python_module``, ``port``, ``can_sleep``) on the
App, ``apps[]`` carrying the COMPLETE set, and
:func:`join_disagreements` making sure the two lists never drift.

⚠️ ``apps[]`` is not a "sellable subset". Sellability already has a house —
``App.requires_plan``, which is optional; an App without one is a container that
runs and is not sold, which is what ``worker`` is.

⚠️ An earlier reading of the spec had the whole ledger moving onto the App.
That is off the table, and the reason is the paragraph at the top of this file:
``answers`` is the ONLY place a ``when:``-erased answer survives, and it stays
exactly where it is. Nothing about the fatia-3 rescue changes.

⭐ The descriptor landed (#351), so :func:`app_is_the_deployment` is normally
True and the App IS written. The predicate stays anyway, and it is not
ceremony: ``dna-cli`` and ``dna-sdk`` are SEPARATE wheels with independent
floors, so a user can perfectly well install a CLI newer than the SDK that
carries the descriptors. In that install the write would be refused by schema —
``App`` declares ``additionalProperties: false`` — and the predicate is what
turns that into a named sentence instead of a traceback. See
:func:`app_kind_absent_fields`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOLUTION_KIND = "Solution"
APP_KIND = "App"
SOLUTION_API_VERSION = "github.com/ruinosus/dna/v1"

#: The Kind that OWNS the cost commitment since ``spec-app-e-o-servico``
#: (07/08/2026). It used to live here, promoted out of ``answers`` into
#: ``services[].pode_dormir``, and that promotion was right only while there
#: was nowhere else for it: an entry in ``services[]`` is one per DEPLOYMENT
#: (*"nove serviços sobre quatro imagens são nove entradas aqui"*), an ``App``
#: is now the deployment, and one fact in two places is two names for one fact.
#: So this record keeps the PROVENANCE OF THE RENDER — the Copier answer stays
#: verbatim inside ``answers`` — and the COMMITMENT is read off the ``App``.
#:
#: ⚠️ An ALIAS of :data:`APP_KIND`, never a second literal. It reads as the
#: cost's owner at the call sites that ask about cost, and the two can never
#: drift apart into two Kinds.
COST_KIND = APP_KIND

#: The field on :data:`COST_KIND` that answers it.
COST_FIELD = "can_sleep"

#: ⭐ The `App` fields this command writes — the service's IDENTITY, and nothing
#: else. Spelled EXACTLY as the reference template's questions spell them, which
#: is the whole point: an App declared and a tree rendered are two views of one
#: fact, so the projection is a copy under the same names rather than a mapping
#: somebody has to remember.
#:
#: ⭐ **THE RULER** (`Story/s-campos-opcionais-por-evidencia`, 07/08/2026):
#: *the App carries what the WIRING needs; ``answers`` carries what the TEMPLATE
#: needs.* Measured by asking every `copier.yml` question whether it appears in
#: any of the three wiring fragments::
#:
#:     service_name   3 wiring uses   → deployment fact
#:     port           2               → deployment fact
#:     can_sleep      1               → deployment fact
#:     python_module  0               → ONLY a render answer
#:
#: ⚠️ So ``python_module`` is NOT here, and it is not "optional" either — it
#: left. It lives in ``services[].answers``, where the template's own vocabulary
#: already lives (free map, no required key, exactly for this). That is what
#: makes `portal` fit with NO exception at all: Next.js does not answer a
#: question the Kind stopped asking, and one of the dogfood's three gaps
#: disappears instead of being tolerated. It is also what keeps a Node or Go
#: template from bloating the App with `package_name` / `module_path`.
#:
#: ⚠️ ``answers_file``, ``template`` and ``answers`` are not here either — the
#: ledger is the provenance of the RENDER and stays in ``Solution.services[]``,
#: where a ``when:``-erased answer survives. Founder decision 07/08/2026.
APP_SERVICE_FIELDS: tuple[str, ...] = (
    "service_name",
    "port",
    COST_FIELD,
)

#: What a fixed replica costs, measured: the dna-cloud copilot with
#: ``minReplicas: 1`` was US$ 94,43 of a US$ 230,29 invoice — the largest single
#: line on it. Rounded down, stated once, and read from here by every message
#: that mentions it, so the number cannot drift between them.
NO_SLEEP_USD_PER_MONTH = 90


class SolutionRecordError(Exception):
    """A refusal from the record side, translated by the caller."""


def _is_typed_answer(field: str, value: Any) -> bool:
    """Whether a Copier answer is the TYPE the `App` field declares.

    ⚠️ Type-checked, not truth-checked, and the two differ exactly where it
    matters: ``can_sleep: False`` and ``port: 0`` are falsy and are ANSWERS.
    A `if value:` here would drop the expensive half of the cost question —
    the one that costs ~US$ 90/month — and the App would come out looking
    unanswered, which is the failure the whole field exists to prevent.

    ``bool`` is excluded from the integer case on purpose: in Python
    ``isinstance(True, int)`` is True, so ``port: true`` would otherwise be
    written as a port.
    """
    if field == COST_FIELD:
        return isinstance(value, bool)
    if field == "port":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, str) and bool(value)


@dataclass(frozen=True)
class Layer:
    """One answers file, as the ``Solution`` stores it.

    ⚠️ No ``pode_dormir``. The cost commitment moved to ``App.can_sleep``
    (:data:`COST_KIND` / :data:`COST_FIELD`) — see the module constants. What
    the template answered is not lost: it is in :attr:`answers`, under whatever
    key that template used, which is all this record ever claimed to hold.
    """

    name: str
    answers_file: str
    template_src: str
    template_ref: str | None
    answers: dict[str, Any]

    def to_spec(self) -> dict[str, Any]:
        """The layer as ``Solution.services[]`` holds it — the render provenance.

        ⚠️ No cost field, in either direction. It is not conditionally omitted
        here; it simply does not live here any more, and the Copier answer that
        produced it is still in :attr:`answers` verbatim. A ``pode_dormir``
        written beside the App's ``can_sleep`` would be the second house that
        `spec-app-e-o-servico` removed.
        """
        template: dict[str, Any] = {"src": self.template_src}
        if self.template_ref:
            template["ref"] = self.template_ref
        return {
            "name": self.name,
            "answers_file": self.answers_file,
            "template": template,
            "answers": dict(self.answers),
        }

    def to_app_spec(self, *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
        """The service's IDENTITY, as the ``App`` that IS this deployment.

        Four fields, and the ledger is not among them: ``answers_file``,
        ``template`` and ``answers`` stay in ``Solution.services[]``, which is
        where the provenance of the render belongs and where a ``when:``-erased
        answer survives.

        Merged OVER ``existing`` rather than replacing it: an `App` is also a
        portal record — ``title``, ``description``, ``icon``, ``requires_plan``,
        ``nav_order``, the copilots it composes — and a scaffolding run knows
        nothing about any of that. A write that replaced the spec would delete
        the entitlement of a live App because somebody re-rendered its
        Dockerfile.

        ``title`` is seeded from the template's one-line description on the
        FIRST write only, and never overwritten: it is what a human sees, and
        the human's version of it outranks a copier answer forever after.
        """
        spec: dict[str, Any] = dict(existing or {})
        spec["service_name"] = self.name

        # ⭐ Copied under the SAME names the template asked them under. That is
        # what replaced the old `--sleep-answer` knob: there is no key to name
        # any more, because the questions and the App's fields are one
        # vocabulary (`copier.yml` says so, and a test asserts it). A template
        # that spells them differently simply answers nothing here — and the
        # cost question then reports the service as unanswered, which is the
        # loud side and the correct one.
        for field in APP_SERVICE_FIELDS:
            if field == "service_name":
                continue
            value = self.answers.get(field)
            if not _is_typed_answer(field, value):
                continue
            spec[field] = value

        if not spec.get("title"):
            described = self.answers.get("description")
            spec["title"] = described if isinstance(described, str) and described else self.name
        return spec


def service_name_of(answers_relpath: Path | str) -> str:
    """The layer's name, from the answers file that IS the layer.

    ``.copier-answers.mcp-entra.yml`` → ``mcp-entra``; the bare
    ``.copier-answers.yml`` → ``default``. Not a general parser and not
    trying to be: the same spelling ``resolve_answers_file`` builds from
    ``--service``, read the other way, so the two cannot mean different
    things.
    """
    stem = Path(answers_relpath).name
    for suffix in (".yml", ".yaml"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    stem = stem.removeprefix(".copier-answers")
    return stem.lstrip(".") or "default"


def layer_from_answers_file(
    destination: Path,
    answers_relpath: Path,
    *,
    service: str | None = None,
) -> Layer:
    """Read one answers file off disk into the shape the Kind stores."""
    from dna_cli.solution_cmd import _load_yaml  # noqa: PLC0415 — one loader

    raw = _load_yaml(destination / answers_relpath)
    answers = {k: v for k, v in raw.items() if not str(k).startswith("_")}
    src = raw.get("_src_path")
    if not src:
        raise SolutionRecordError(
            f"{answers_relpath} records no `_src_path`, so there is no template "
            "pointer to store. A tree generated without one can be regenerated "
            "but never updated, and a Solution that claimed otherwise would be "
            "the wrong kind of record."
        )
    return Layer(
        name=service or service_name_of(answers_relpath),
        answers_file=str(answers_relpath),
        template_src=str(src),
        template_ref=raw.get("_commit"),
        answers=answers,
    )


# ── can the `App` carry the deployment's identity yet? ───────────────────────


def app_kind_absent_fields() -> tuple[str, ...]:
    """The :data:`APP_SERVICE_FIELDS` the live ``App`` descriptor does not accept.

    ⚠️ ASKED of the descriptor, never assumed, and never caught-and-ignored.
    ``App`` declares ``additionalProperties: false``, so writing a field it does
    not know is a refused write, not a tolerated extra — measured 07/08/2026::

        write vetoed for board/App/api: schema validation failed at spec:
        Additional properties are not allowed ('can_sleep', 'port',
        'python_module', 'service_name' were unexpected)

    ⭐ #351 landed, so this is normally empty. It is NOT dead code, and the
    reason is packaging: ``dna-cli`` and ``dna-sdk`` are separate wheels with
    independent version floors, so an install can carry a CLI that knows about
    these fields and an SDK whose descriptors do not. In that install writing
    the App is a refused write, and this is what turns it into a named sentence
    (see :func:`dna_cli.solution_cmd._echo_report`) instead of a traceback in
    the middle of a scaffold.

    That is the difference between a bridge and a fallback: a fallback goes
    quiet, and a value that renders the same whether it reached the right house
    or none at all is the failure this house pays most for.
    """
    from dna.kernel import Kernel  # noqa: PLC0415 — the kernel is lazy

    port = Kernel.auto()._kinds.get((SOLUTION_API_VERSION, APP_KIND))
    if port is None:
        return APP_SERVICE_FIELDS
    properties = (port.schema() or {}).get("properties") or {}
    return tuple(field for field in APP_SERVICE_FIELDS if field not in properties)


# ═══════════════════════════════════════════════════════════════════════════
# ⭐ THE SWAP POINT — "this question does not apply", and how it is spelled.
#
# Everything the codebase knows about it is BELOW, in two constants and one
# reader. The report calls :func:`not_applicable_fields` and never inspects a
# field name itself; the printed help interpolates the constants rather than
# spelling them. So the form is swappable here and nowhere else.
#
# ⭐ AND IT WAS SWAPPED, on 07/08/2026 (#355), exactly as this block predicted.
# The generic `not_applicable` map is GONE and was never built. The measurement
# that killed it: once `python_module` moved to ``answers`` by the
# wiring-vs-render ruler, ONE case was left — `worker` with no `port` — and one
# case does not pay for a general mechanism. The real fact is that `worker`
# **does not serve**; "no port" is the CONSEQUENCE.
#
# ⚠️ The replacement is not a new boolean: ``copier.yml`` ALREADY asks
# ``ingress`` (`choices: [internal, external]`), so ``none`` is a third value
# of a vocabulary that exists. ``ingress`` has 1 use in the wiring and 0 in
# generated code, so it is an App field by the same ruler that expelled
# ``python_module``. And ``ingress: none`` together with a ``port`` is REFUSED
# at write time by the descriptor (`allOf`/`if`/`then`) — so this reader is not
# hiding a question, it is declining to ask for something the schema forbids.
#
# ⭐ What the swap BOUGHT, and it is the argument this module made for
# per-field granularity, now made structural instead of conventional: a
# per-App `not_applicable` would have been a back door for silencing the COST
# question, defended only by getting an enum right. Here that door does not
# exist — :func:`not_applicable_fields` cannot return :data:`COST_FIELD` by any
# input, because `ingress` answers one question and only one.
#
# ⚠️ ``can_sleep`` and ``service_name`` have NO way to say "does not apply",
# and that is deliberate: measured, there is no case for either across the nine
# services. If one appears, the form to adopt is NAMED AND NOT BUILT — FHIR's
# `dataAbsentReason`, recorded in the descriptor. Do not invent one here.
# ═══════════════════════════════════════════════════════════════════════════

#: The `App` field that says what a deployment is reachable from — and, at
#: :data:`INGRESS_NONE`, that it is not reachable at all.
INGRESS_FIELD = "ingress"

#: The value that means "this deployment does not serve". The dna-cloud
#: `worker` is exactly this: it scales on KEDA and answers nobody, so asking it
#: for a port is asking for a fact that does not exist — *"uma porta que
#: ninguém chama é só uma porta aberta"*.
INGRESS_NONE = "none"

#: Which question each ``ingress`` value makes inapplicable. A MAP, so the
#: relationship is data rather than a chain of ifs — and so the blast radius of
#: any future value is visible in one place.
#:
#: ⚠️ It maps to ``port`` and can map to nothing else without somebody
#: deliberately writing it here, which is what makes "ingress cannot silence
#: the cost question" a property of the code instead of a promise about it.
_INGRESS_SILENCES: dict[str, frozenset[str]] = {
    INGRESS_NONE: frozenset({"port"}),
}


def not_applicable_fields(app_spec: dict[str, Any] | None) -> set[str]:
    """The questions this `App`'s own declaration makes inapplicable.

    ⭐ THE ONLY reader of the mechanism — see the block above. Callers ask for
    a set of field names and never learn how it was decided, so the day the
    form changes again, it changes here.

    ``Spec/spec-campo-opcional-por-evidencia`` condition 1: an empty field means
    two opposite things (*the question does not apply* and *nobody answered*),
    and a report that does not separate them talks about everything. A report
    that talks about everything nobody reads — and then it is WORSE than the
    refusal it replaced, because it feels like somebody is looking.

    ⚠️ Read, never written, by this module: ``ingress`` is the App descriptor's
    field. Reading a descriptor that does not carry it yet is harmless and
    self-healing — it answers "nothing declared", every field is reported, and
    the day it lands the declarations start being honoured with no change here.
    """
    return set(_INGRESS_SILENCES.get((app_spec or {}).get(INGRESS_FIELD), frozenset()))


def reportable_fields() -> tuple[str, ...]:
    """The :data:`APP_SERVICE_FIELDS` the schema does NOT require — DERIVED.

    ⭐ This is `Spec/spec-campo-opcional-por-evidencia` in one expression: *the
    schema prevents nonsense, the report chases completeness.* Whatever the
    descriptor marks `required` is the schema's business and can never be
    missing; everything else in this set is expected-but-optional, which is
    precisely what a report exists to chase.

    Derived so the two can never drift: the day a field earns its optionality
    on evidence (`port`, because `worker` has no ingress on purpose) it appears
    here by itself, and a field that goes back to required disappears from the
    report without anybody remembering to delete a line. A hand-kept list would
    be the enumeration this house has been bitten by — a list that looks
    authoritative and covers whatever it covered the day it was written.
    """
    from dna.kernel import Kernel  # noqa: PLC0415 — the kernel is lazy

    port = Kernel.auto()._kinds.get((SOLUTION_API_VERSION, APP_KIND))
    if port is None:
        return ()
    schema = port.schema() or {}
    properties = set(schema.get("properties") or {})
    required = set(schema.get("required") or [])
    return tuple(
        field
        for field in APP_SERVICE_FIELDS
        if field in properties and field not in required
    )


def app_is_the_deployment() -> bool:
    """True once the ``App`` descriptor can hold the service's identity.

    ⚠️ It gates ONE thing: which house the cost commitment is written in. The
    ledger in ``services[]`` is written either way — it is not part of this
    handover and never was.
    """
    return not app_kind_absent_fields()


# ── reading the record ───────────────────────────────────────────────────────


def read_solution(name: str, *, scope: str | None = None) -> dict[str, Any] | None:
    """The recorded ``Solution`` spec, or ``None`` when it does not exist.

    Returned verbatim. There is nothing to join in: the cost commitment lives
    on the ``App`` and :func:`unanswered_cost_question` reads it there, so
    copying it back into a layer on the way out would rebuild the second house
    inside the reader — the same fact, twice, free to disagree.
    """
    from dna_cli._ctx import open_session  # noqa: PLC0415 — the kernel is lazy

    with open_session(scope) as session:
        doc = session.get_doc(SOLUTION_KIND, name)
        return dict(doc.spec or {}) if doc is not None else None


def recorded_layer(spec: dict[str, Any] | None, service: str) -> dict[str, Any] | None:
    """The entry in ``services[]`` for ``service``, or ``None``."""
    for entry in (spec or {}).get("services") or []:
        if isinstance(entry, dict) and entry.get("name") == service:
            return entry
    return None


def recorded_answers_of(spec: dict[str, Any] | None, service: str) -> dict[str, Any]:
    """The answers this record holds for one layer — ``{}`` when it holds none."""
    entry = recorded_layer(spec, service) or {}
    answers = entry.get("answers")
    return dict(answers) if isinstance(answers, dict) else {}


def merged_before(
    *, recorded: dict[str, Any], from_file: dict[str, Any]
) -> dict[str, Any]:
    """The effective answers an update starts from.

    The FILE wins: it is what the tree was last rendered with, and the record
    is the longer memory underneath it, not an override on top of it. What the
    record therefore contributes is exactly the set of keys the file no longer
    has — which is the set ``when:`` erased.
    """
    return {**recorded, **from_file}


def restored_keys(
    *, recorded: dict[str, Any], from_file: dict[str, Any]
) -> list[str]:
    """The names this record put back that the file had lost."""
    return sorted(k for k in recorded if k not in from_file)


# ── the two lists, and the guard that keeps them one fact ────────────────────


def join_disagreements(spec: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    """``(services with no App, apps with no service)`` — DERIVED from both.

    ⭐ Why this exists at all. ``apps[]`` and the set of ``services[].name``
    denote the same things once an `App` is a deployment, and they cannot be
    collapsed into one list: ``apps`` is the only place a relation can be
    DECLARED (``relation_values`` reads ``spec.get(rel.name)`` — top level,
    always), and ``services[]`` is the only place the render ledger fits.

    So the risk is real and stays real: one fact in two lists disagrees on the
    first run that touches only one. The answer is a mechanism, not a retreat —
    this check, derived from both sides rather than enumerated, run before every
    write, naming BOTH sides when they part company. A guard that reported only
    "they differ" would leave the reader diffing two lists by eye, which is the
    step people skip.

    ⚠️ An ABSENT (or empty) ``apps`` is not a disagreement — it is the join not
    being declared, which the schema allows and §6-B measured as the common
    case (*"o dna-cloud gera 9 serviços e nenhum App"*). Reporting every
    service as missing there would make the guard fire loudest on the records
    that are simply older than it, and a guard that cries wolf on the normal
    case is a guard that gets switched off. Disagreement is about a list that
    IS declared and does not cover the set.
    """
    spec = spec or {}
    apps = list(spec.get("apps") or [])
    if not apps:
        return ([], [])
    services = [
        entry.get("name")
        for entry in (spec.get("services") or [])
        if isinstance(entry, dict) and entry.get("name")
    ]
    return (
        sorted({s for s in services if s not in apps}),
        sorted({a for a in apps if a not in services}),
    )


def _refuse_join_disagreement(name: str, spec: dict[str, Any]) -> None:
    """Raise when ``apps[]`` and ``services[].name`` stop denoting one set."""
    missing, orphaned = join_disagreements(spec)
    if not missing and not orphaned:
        return
    lines = [
        f"Solution {name!r} would be written with `apps` and `services[].name` "
        "disagreeing, and they denote the same things — an App IS a deployment."
    ]
    if missing:
        lines.append(
            "  services with no entry in `apps`: " + ", ".join(missing)
        )
    if orphaned:
        lines.append(
            "  `apps` entries with no service: " + ", ".join(orphaned)
        )
    lines.append(
        "  `apps` is the only join the kernel can enforce — a pointer inside\n"
        "  `services[].items` is NOT declarable as a relation (`relation_values`\n"
        "  reads the top level), so an incomplete `apps` is the enforced relation\n"
        "  being incomplete on purpose.\n"
        "  Sellability is not the reason to leave one out: that lives in\n"
        "  `App.requires_plan`, and an App without one is a container that runs\n"
        "  and is not sold."
    )
    raise SolutionRecordError("\n".join(lines))


# ── writing the record ───────────────────────────────────────────────────────


def upsert_solution(
    name: str,
    layers: list[Layer],
    *,
    scope: str | None = None,
    title: str | None = None,
    description: str | None = None,
    repo: str | None = None,
    apps: list[str] | None = None,
    author: str | None = None,
) -> dict[str, Any]:
    """Merge ``layers`` into the ``Solution`` called ``name`` and write it.

    Upsert per LAYER, never wholesale: a repo is generated one app at a time,
    so every run knows about exactly one layer and must not be able to erase
    the eight it did not run. ``services[]`` keeps the order it was built in,
    with a re-recorded layer replaced in place.

    ``criado_por`` / ``criado_em`` follow ``SourceArtifact.uploaded_by`` /
    ``uploaded_at`` — the mould fatia 1 used for ``CopilotBlueprint`` — and are
    stamped ONCE: a later run that adds a layer does not re-create the
    solution, so the timestamp keeps meaning what it says.
    """
    from dna_cli._ctx import open_session  # noqa: PLC0415

    app_ready = app_is_the_deployment()

    with open_session(scope) as session:
        # ⭐ The App goes FIRST, and the order is load-bearing — MORE so now that
        # `apps[]` is the enforced relation and is populated on every write.
        # `apps` resolves `to: App` `by: name` with `enforced = True`, so under
        # DNA_REF_VALIDATION=enforce a Solution naming an App that does not
        # exist yet is a REFUSED write, and this whole record fails. Writing the
        # deployment before the record that points at it is the only order in
        # which both halves land.
        #
        # ⚠️ Do not "tidy" this into one loop after the Solution write. The
        # dangling pointer it would create is exactly what `enforced` exists to
        # veto, and the veto is correct.
        if app_ready:
            for layer in layers:
                app_doc = session.get_doc(APP_KIND, layer.name)
                app_spec = layer.to_app_spec(
                    existing=dict(app_doc.spec or {}) if app_doc is not None else None
                )
                session.run(
                    session.kernel.write_instance(
                        session.scope,
                        APP_KIND,
                        layer.name,
                        {
                            "apiVersion": SOLUTION_API_VERSION,
                            "kind": APP_KIND,
                            "metadata": {
                                "name": layer.name,
                                "description": app_spec.get("description") or "",
                            },
                            "spec": app_spec,
                        },
                    )
                )

        existing = session.get_doc(SOLUTION_KIND, name)
        spec: dict[str, Any] = dict(existing.spec or {}) if existing is not None else {}

        services: list[dict[str, Any]] = [
            dict(entry)
            for entry in (spec.get("services") or [])
            if isinstance(entry, dict)
        ]
        by_name = {entry.get("name"): index for index, entry in enumerate(services)}
        for layer in layers:
            entry = layer.to_spec()
            index = by_name.get(layer.name)
            if index is None:
                by_name[layer.name] = len(services)
                services.append(entry)
            else:
                services[index] = entry
        spec["services"] = services

        spec["title"] = title or spec.get("title") or name
        if description:
            spec["description"] = description
        if repo:
            spec["repo"] = repo
        # ⭐ `apps` is the COMPLETE set of this solution's deployments, and it is
        # populated here — accumulated over every recorded layer, not just this
        # run's, so a record written before this existed heals on the next
        # `record` instead of staying half-declared.
        #
        # ⚠️ It is not a "sellable subset", and there is no second list. `apps`
        # is the ONLY declarable join: `relation_values` reads
        # `spec.get(rel.name)` at the TOP LEVEL, so a pointer inside
        # `services[].items` cannot be a relation — measured in #351, and its
        # failure mode is the worst kind: declaring it lints green, reports
        # `resolved/enforced = True/True`, and resolves NOTHING. A guard that
        # says it is enforced and reads zero.
        #
        # Sellability needs no list of its own: it already has a house in
        # `App.requires_plan`, which is optional. An App without one is a
        # container that runs and is not sold — `worker` is exactly that.
        #
        # ⚠️ Gated on `app_ready`, and MEASURED rather than assumed. `apps` is
        # enforced, so naming an App this run did not write is a dangling
        # pointer — with DNA_REF_VALIDATION=warn the kernel says so and persists
        # it anyway, and under `enforce` it refuses the whole record::
        #
        #     write vetoed for board/Solution/s: unresolved relation(s):
        #     spec.apps → `api` (no App named `api` in scope `board`)
        #
        # So while the installed descriptor cannot hold the identity, `apps` is
        # left alone — populating a relation whose targets do not exist is not a
        # half-migration, it is a broken record.
        if app_ready:
            declared = list(spec.get("apps") or [])
            for entry in services:
                service = entry.get("name")
                if service and service not in declared:
                    declared.append(service)
            if declared:
                spec["apps"] = declared
        if apps is not None:
            spec["apps"] = list(apps)

        # ⭐ The guard that makes ONE fact in two lists safe. The lists cannot be
        # collapsed — `apps` is the only enforceable relation and `services[]` is
        # the only place the ledger fits — so what stops them disagreeing is a
        # check, DERIVED from both, that names both sides. It runs before the
        # write, so an inconsistent record is never stored in the first place.
        if spec.get("apps"):
            _refuse_join_disagreement(name, spec)
        if existing is None:
            spec["criado_em"] = datetime.now(timezone.utc).isoformat()
            if author:
                spec["criado_por"] = author

        raw = {
            "apiVersion": SOLUTION_API_VERSION,
            "kind": SOLUTION_KIND,
            "metadata": {"name": name, "description": spec.get("description") or ""},
            "spec": spec,
        }
        session.run(
            session.kernel.write_instance(session.scope, SOLUTION_KIND, name, raw)
        )
        return spec


def unanswered_cost_question(
    spec: dict[str, Any] | None, *, scope: str | None = None
) -> list[str]:
    """Deployments whose ``App`` never said whether they may sleep.

    ⚠️ ONE of the three questions in :func:`declaration_gaps`, and it is a
    NARROWER reading than the report: it cannot express *"there were no
    deployments to look at"*, which comes back from here as an empty list and
    reads like "all answered". Callers that decide anything — ``--strict``, the
    printed report — must use :func:`declaration_gaps` and its
    :attr:`DeclarationGaps.nothing_to_look_at`. This exists because the cost
    question has an audience of its own.

    Reported rather than refused, and on every run rather than once — the same
    shape as ``divergent_answers``, and for the same reason: a finding that
    speaks only at the moment it appears is a finding that goes quiet while the
    condition stays true.

    A store that cannot be read is not silently "all answered": the read is
    attempted once, and a failure leaves every service reported as unanswered,
    which is the loud side.
    """
    return declaration_gaps(spec, scope=scope).gaps.get(COST_FIELD, [])


@dataclass(frozen=True)
class DeclarationGaps:
    """What the fleet has not said yet — three questions, ONE report.

    ``Story/s-relatorio-do-que-falta``. The questions are `can_sleep` (what
    does this cost?), `python_module` and `port` — asked of every deployment,
    answered on the `App`, and reported together because they are read by one
    person at one moment.
    """

    #: The deployments looked at — ``apps[]``, which IS the set of deployments.
    deployments: tuple[str, ...]
    #: field name → the deployments that neither answered it nor said it does
    #: not apply. Sorted, so output is stable.
    gaps: dict[str, list[str]]
    #: ⚠️ The store could not be read. Every deployment is then reported as
    #: missing every field — the loud side — and this says WHY, so "unreadable"
    #: never renders as "undeclared".
    unreadable: bool = False

    @property
    def nothing_to_look_at(self) -> bool:
        """⭐ No deployments at all — and this is a FINDING, not a pass.

        ⚠️ Deliberately the OPPOSITE of :func:`join_disagreements`, where an
        absent ``apps`` is not a disagreement. Do not "unify" them: they answer
        different questions, and the answers legitimately differ.

        * *"Do the two lists agree?"* — of an absent list there is no answer.
          Reporting one would fire on every record older than the guard, and a
          guard that cries wolf on the normal case gets switched off.
        * *"Has anyone answered about cost?"* — of an empty set there IS an
          answer: **nobody looked.** Returning "all answered" for zero
          deployments is the green-by-vacuity that has blinded three guards in
          this house already.
        """
        return not self.deployments

    @property
    def has_findings(self) -> bool:
        return self.nothing_to_look_at or any(self.gaps.values())


def declaration_gaps(
    spec: dict[str, Any] | None, *, scope: str | None = None
) -> DeclarationGaps:
    """The three questions, asked of ``apps[]``.

    ⭐ **The source is ``apps[]``, and that is the whole point.** It used to be
    ``services[].name``, which meant a `Solution` with no ``services`` answered
    *"everything is declared"* — measured, and exactly the vacuity
    `Spec/spec-campo-opcional-por-evidencia` exists to close. ``apps`` is the
    ENFORCED relation and is the set of deployments by definition: it exists in
    a repo generated from a template and in one that never was, which is the
    case that produced the finding (the dna-cloud has nine services and no
    `.copier-answers` anywhere).

    ⚠️ Absent is UNANSWERED, and absent is never ``False``. For ``can_sleep``
    three states collapse into "unanswered" and none of them into "may not
    sleep": no ``App`` by that name, an ``App`` that omits the field, or an
    explicit ``null``. ``can_sleep: False`` is an ANSWER, and an expensive one
    (a fixed replica, ~US$ 90/month, forever) — reporting it as unanswered
    would cry wolf until nobody listens, and presuming it hides the replica
    nobody decided.

    A question the App's own declaration makes INAPPLICABLE is silenced for
    that deployment only — see :func:`not_applicable_fields`. Today that is
    ``ingress: none`` silencing ``port``, and nothing silences the cost.
    """
    from dna_cli._ctx import open_session  # noqa: PLC0415 — the kernel is lazy

    deployments = tuple(
        str(name) for name in ((spec or {}).get("apps") or []) if name
    )
    fields = reportable_fields()
    if not deployments or not fields:
        return DeclarationGaps(deployments=deployments, gaps={f: [] for f in fields})

    gaps: dict[str, list[str]] = {field: [] for field in fields}
    try:
        with open_session(scope) as session:
            for name in sorted(set(deployments)):
                doc = session.get_doc(APP_KIND, name)
                app = dict(doc.spec or {}) if doc is not None else {}
                exempt = not_applicable_fields(app)
                for field in fields:
                    if field in exempt:
                        continue
                    if app.get(field) is None:
                        gaps[field].append(name)
    except Exception:  # noqa: BLE001 — an unreadable store reports the loud side
        return DeclarationGaps(
            deployments=deployments,
            gaps={field: sorted(set(deployments)) for field in fields},
            unreadable=True,
        )
    return DeclarationGaps(deployments=deployments, gaps=gaps)
