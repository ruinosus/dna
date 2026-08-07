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
* **Only the cost commitment moves.** ``pode_dormir`` leaves ``services[]`` and
  becomes ``App.can_sleep``, because *the invoice is per deployment and the App
  IS the deployment.* One fact, one house — the failure a second house creates
  is two answers to "does this sleep?" that disagree.
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

The App descriptor is `Story/s-kinds-a-conta-declarada`'s to move. Until it
has, the cost stays in ``services[].pode_dormir`` and every run says so out
loud. Never silently — see :func:`app_kind_absent_fields`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOLUTION_KIND = "Solution"
APP_KIND = "App"
SOLUTION_API_VERSION = "github.com/ruinosus/dna/v1"

#: ⭐ The `App` fields a layer writes — the service's IDENTITY, and nothing else.
#: Promoted out of the free answers map because a reader of the FLEET has to
#: answer "which port? which module? which of these never sleeps?" without
#: knowing that THIS template spelled the questions the way it did.
#:
#: ⚠️ FOUR, not seven. ``answers_file``, ``template`` and ``answers`` stay in
#: ``Solution.services[]`` — they are the provenance of the RENDER, and
#: ``answers`` in particular is the only place a ``when:``-erased answer
#: survives. Founder decision 07/08/2026: the ledger does not move; only the
#: cost commitment does, because the invoice is per deployment and the App is
#: the deployment.
APP_SERVICE_FIELDS: tuple[str, ...] = (
    "service_name",
    "python_module",
    "port",
    "can_sleep",
)

#: What a fixed replica costs, measured: the dna-cloud copilot with
#: ``minReplicas: 1`` was US$ 94,43 of a US$ 230,29 invoice — the largest single
#: line on it. Rounded down, stated once, and read from here by every message
#: that mentions it, so the number cannot drift between them.
NO_SLEEP_USD_PER_MONTH = 90

#: The answer this house's reference template uses for the cost commitment.
#: A GUESS, and a loud one: when it is absent from a layer's answers nothing is
#: presumed — ``pode_dormir`` is left unwritten and reported as unanswered on
#: every run. A silent ``False`` here would be the cheap side of a ~US$ 90/month
#: decision, invented by a default.
DEFAULT_SLEEP_ANSWER = "can_sleep"


class SolutionRecordError(Exception):
    """A refusal from the record side, translated by the caller."""


@dataclass(frozen=True)
class Layer:
    """One answers file, as the ``Solution`` stores it."""

    name: str
    answers_file: str
    template_src: str
    template_ref: str | None
    answers: dict[str, Any]
    pode_dormir: bool | None

    def to_spec(self, *, cost_on_app: bool = False) -> dict[str, Any]:
        """The layer as ``Solution.services[]`` holds it — the render provenance.

        ``cost_on_app`` is the ONE thing that moved: once the `App` descriptor
        can hold ``can_sleep``, the cost commitment lives there and is not
        written here as well. Two houses for one fact is two answers to "does
        this sleep?" that can disagree, and the one that disagrees is always
        found by the invoice.
        """
        template: dict[str, Any] = {"src": self.template_src}
        if self.template_ref:
            template["ref"] = self.template_ref
        entry: dict[str, Any] = {
            "name": self.name,
            "answers_file": self.answers_file,
            "template": template,
            "answers": dict(self.answers),
        }
        if self.pode_dormir is not None and not cost_on_app:
            entry["pode_dormir"] = self.pode_dormir
        return entry

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
        if self.pode_dormir is not None:
            spec["can_sleep"] = self.pode_dormir
        module = self.answers.get("python_module")
        if isinstance(module, str) and module:
            spec["python_module"] = module
        port = self.answers.get("port")
        if isinstance(port, int) and not isinstance(port, bool):
            spec["port"] = port
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
    sleep_answer: str = DEFAULT_SLEEP_ANSWER,
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
    sleeps = answers.get(sleep_answer)
    return Layer(
        name=service or service_name_of(answers_relpath),
        answers_file=str(answers_relpath),
        template_src=str(src),
        template_ref=raw.get("_commit"),
        answers=answers,
        pode_dormir=bool(sleeps) if isinstance(sleeps, bool) else None,
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

    The descriptor is `Story/s-kinds-a-conta-declarada`'s to move; this command
    is `Story/s-template-dirigido-pelo-app`'s. Until it lands, the cost stays
    in ``services[].pode_dormir`` and every run SAYS SO — see
    :func:`dna_cli.solution_cmd._echo_report`. That is the difference between a
    bridge and a fallback: a fallback goes quiet, and a value that renders the
    same whether it is in the right house or the wrong one is the failure this
    house pays most for.
    """
    from dna.kernel import Kernel  # noqa: PLC0415 — the kernel is lazy

    port = Kernel.auto()._kinds.get((SOLUTION_API_VERSION, APP_KIND))
    if port is None:
        return APP_SERVICE_FIELDS
    properties = (port.schema() or {}).get("properties") or {}
    return tuple(field for field in APP_SERVICE_FIELDS if field not in properties)


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

    ``services`` is a stored field and stays one — the render provenance lives
    here. What is joined in on read is the ONE fact that moved houses: each
    layer's ``pode_dormir`` is filled from the `App` its ``name`` points at.

    ⭐ Joined here rather than at each call site so ``recorded_layer``,
    ``recorded_answers_of`` and ``unanswered_cost_question`` keep reading ONE
    shape. A reader that had to know which house the cost was in would be a
    reader that gets it wrong on the run after the descriptor moves.
    """
    from dna_cli._ctx import open_session  # noqa: PLC0415 — the kernel is lazy

    with open_session(scope) as session:
        doc = session.get_doc(SOLUTION_KIND, name)
        if doc is None:
            return None
        return _with_cost_joined(session, dict(doc.spec or {}))


def _with_cost_joined(session: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """Fill each layer's ``pode_dormir`` from its `App`, when the App holds it.

    ⚠️ The App WINS when it has an answer, and that is the point of moving the
    fact: a stale ``pode_dormir`` left in an old ``services[]`` entry must not
    outvote the house that now owns it. When the App has no answer the stored
    value stands — which is what a record written before the move looks like,
    and it is still true.
    """
    if not app_is_the_deployment():
        return spec
    layers = [dict(e) for e in (spec.get("services") or []) if isinstance(e, dict)]
    for entry in layers:
        app_doc = session.get_doc(APP_KIND, entry.get("name"))
        sleeps = dict(app_doc.spec or {}).get("can_sleep") if app_doc else None
        if isinstance(sleeps, bool):
            entry["pode_dormir"] = sleeps
    if layers:
        spec = dict(spec)
        spec["services"] = layers
    return spec


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

    cost_on_app = app_is_the_deployment()

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
        if cost_on_app:
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
            entry = layer.to_spec(cost_on_app=cost_on_app)
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
        # ⚠️ Gated on `cost_on_app`, and MEASURED rather than assumed. `apps` is
        # enforced, so naming an App this run did not write is a dangling
        # pointer — with DNA_REF_VALIDATION=warn the kernel says so and persists
        # it anyway, and under `enforce` it refuses the whole record::
        #
        #     write vetoed for board/Solution/s: unresolved relation(s):
        #     spec.apps → `api` (no App named `api` in scope `board`)
        #
        # So while the descriptor cannot hold the identity, `apps` is left
        # alone — populating a relation whose targets do not exist is not a
        # half-migration, it is a broken record.
        if cost_on_app:
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
        # The caller reports on layers, and the cost may now live on the App —
        # so hand back the JOINED view, not the stored spec. Returning the
        # stored one would make `unanswered_cost_question` report every layer as
        # never having answered, on the very run that answered.
        return _with_cost_joined(session, spec)


def unanswered_cost_question(spec: dict[str, Any] | None) -> list[str]:
    """Layers that never said whether they may sleep.

    Reported rather than refused, and on every run rather than once — the same
    shape as ``divergent_answers``, and for the same reason: a finding that
    speaks only at the moment it appears is a finding that goes quiet while the
    condition stays true.
    """
    out: list[str] = []
    for entry in (spec or {}).get("services") or []:
        if isinstance(entry, dict) and entry.get("pode_dormir") is None:
            out.append(str(entry.get("name")))
    return sorted(out)
