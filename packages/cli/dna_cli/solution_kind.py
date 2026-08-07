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

⭐ Where a layer LIVES — and why it moves to ``App``
===================================================
``Spec/spec-app-e-o-servico`` (approved 07/08/2026): **an App IS the service** —
the unit with a Dockerfile, a port, wiring and a bill at the end of the month —
so ``Solution.services[]`` stops being a field and becomes a VIEW derived from
the ``App`` instances ``apps[]`` points at.

⚠️ One thing the spec assumed and the code does not support: it describes
``services[]`` as "uma lista de strings". It never was. It is the layer ledger —
``answers_file``, the template pointer, the answers verbatim, and the cost
commitment — and the paragraph above is why. So the migration MOVES that ledger
onto the App; it does not drop it. An `App` that took the four identity fields
and left the ledger behind would delete the measured fix for the ``when:``
defect on the way to a tidier schema.

Both ends are the descriptors' to move (`Story/s-kinds-a-conta-declarada`).
Until they have, :func:`app_is_the_service` is False, the layer is recorded the
old way, and every run says so out loud. Never silently — see
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

#: ⭐ The `App` fields a layer becomes once `App` IS the service
#: (`Spec/spec-app-e-o-servico`). Four of them are the service's identity —
#: promoted out of the free answers map because a reader of the FLEET has to
#: answer "which port? which module? which of these never sleeps?" without
#: knowing that THIS template spelled the questions this way. The other three
#: are the layer ledger moving over from ``Solution.services[]``: the answers
#: file, the template pointer, and the answers verbatim.
#:
#: ⚠️ The ledger is not decoration and cannot be dropped. It is the ONLY place a
#: ``when:``-gated answer survives being erased from the answers file — measured
#: in fatia 3, and the entire reason this record exists. An `App` that took the
#: four identity fields and left the ledger behind would move the service and
#: delete the fix.
APP_SERVICE_FIELDS: tuple[str, ...] = (
    "service_name",
    "python_module",
    "port",
    "can_sleep",
    "answers_file",
    "template",
    "answers",
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

    def to_spec(self) -> dict[str, Any]:
        template: dict[str, Any] = {"src": self.template_src}
        if self.template_ref:
            template["ref"] = self.template_ref
        entry: dict[str, Any] = {
            "name": self.name,
            "answers_file": self.answers_file,
            "template": template,
            "answers": dict(self.answers),
        }
        if self.pode_dormir is not None:
            entry["pode_dormir"] = self.pode_dormir
        return entry

    def to_app_spec(self, *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
        """The same layer, as the ``App`` that IS this service.

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
        template: dict[str, Any] = {"src": self.template_src}
        if self.template_ref:
            template["ref"] = self.template_ref

        spec["service_name"] = self.name
        spec["answers_file"] = self.answers_file
        spec["template"] = template
        spec["answers"] = dict(self.answers)
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


# ── is `App` the service yet? ────────────────────────────────────────────────


def app_kind_absent_fields() -> tuple[str, ...]:
    """The :data:`APP_SERVICE_FIELDS` the live ``App`` descriptor does not accept.

    ⚠️ ASKED of the descriptor, never assumed, and never caught-and-ignored.
    ``App`` declares ``additionalProperties: false``, so writing a field it does
    not know is a refused write, not a tolerated extra — measured 07/08/2026::

        write vetoed for board/App/api: schema validation failed at spec:
        Additional properties are not allowed ('can_sleep', 'port',
        'python_module', 'service_name' were unexpected)

    The descriptors are `Story/s-kinds-a-conta-declarada`'s to move; this
    command is `Story/s-template-dirigido-pelo-app`'s. Until they land, the
    layer is recorded the old way and every run SAYS SO — see
    :func:`dna_cli.solution_cmd._echo_report`. That is the difference between a
    bridge and a fallback: a fallback goes quiet, and a name that renders the
    same whether it is right or wrong is the failure this house pays most for.
    """
    from dna.kernel import Kernel  # noqa: PLC0415 — the kernel is lazy

    kinds = Kernel.auto()._kinds
    port = kinds.get((SOLUTION_API_VERSION, APP_KIND))
    if port is None:
        return APP_SERVICE_FIELDS
    properties = (port.schema() or {}).get("properties") or {}
    return tuple(field for field in APP_SERVICE_FIELDS if field not in properties)


def solution_kind_still_requires_services() -> bool:
    """Whether ``Solution`` still declares ``services`` as a required field.

    The other half of the same handover: while it is required, a `Solution`
    written with only ``apps[]`` is refused outright, so the layers stay where
    the schema can hold them.
    """
    from dna.kernel import Kernel  # noqa: PLC0415

    port = Kernel.auto()._kinds.get((SOLUTION_API_VERSION, SOLUTION_KIND))
    if port is None:
        return True
    return "services" in ((port.schema() or {}).get("required") or [])


def app_is_the_service() -> bool:
    """True once BOTH descriptors have moved, and only then.

    Both, deliberately. Writing the App while ``Solution.services`` is still
    required would record every layer twice; dropping ``services`` while the App
    cannot hold the ledger would delete the only copy of a ``when:``-erased
    answer. Half a migration is worse than either end of it.
    """
    return not app_kind_absent_fields() and not solution_kind_still_requires_services()


# ── reading the record ───────────────────────────────────────────────────────


def read_solution(name: str, *, scope: str | None = None) -> dict[str, Any] | None:
    """The recorded ``Solution`` spec, or ``None`` when it does not exist.

    ⭐ ``services`` in the returned mapping is a VIEW, not necessarily a field.
    Once ``App`` is the service the layers live in the `App` instances that
    ``apps[]`` points at, and this function assembles the same shape from them —
    which is what "``services`` vira derivado, não campo" means in code. Every
    caller below (``recorded_layer``, ``recorded_answers_of``,
    ``unanswered_cost_question``) therefore keeps reading one shape, and the
    storage change does not ripple into the update path.
    """
    from dna_cli._ctx import open_session  # noqa: PLC0415 — the kernel is lazy

    with open_session(scope) as session:
        doc = session.get_doc(SOLUTION_KIND, name)
        if doc is None:
            return None
        spec = dict(doc.spec or {})
        if not app_is_the_service():
            return spec
        spec["services"] = [
            _layer_view(session.get_doc(APP_KIND, app_name), app_name)
            for app_name in (spec.get("apps") or [])
        ]
        spec["services"] = [entry for entry in spec["services"] if entry is not None]
        return spec


def _layer_view(doc: Any, app_name: str) -> dict[str, Any] | None:
    """One ``App`` read back in the layer shape ``services[]`` used to hold."""
    if doc is None:
        return None
    app = dict(doc.spec or {})
    if "answers_file" not in app:
        # An App that is a portal record and nothing else — a composition of
        # copilots, never generated from a template. It delivers no layer, and
        # inventing an empty one would put a service in the fleet count that
        # has no code, no port and no bill.
        return None
    entry: dict[str, Any] = {
        "name": app.get("service_name") or app_name,
        "answers_file": app["answers_file"],
        "template": dict(app.get("template") or {}),
        "answers": dict(app.get("answers") or {}),
    }
    if isinstance(app.get("can_sleep"), bool):
        entry["pode_dormir"] = app["can_sleep"]
    return entry


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

    as_apps = app_is_the_service()

    with open_session(scope) as session:
        existing = session.get_doc(SOLUTION_KIND, name)
        spec: dict[str, Any] = dict(existing.spec or {}) if existing is not None else {}

        if as_apps:
            # ⭐ One `App` per layer, because an App IS the service. The write
            # is per layer for the same reason `services[]` was: a run knows
            # about one app and must not be able to erase the eight it did not
            # touch — and now those eight are separate instances, so it cannot.
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
            spec.pop("services", None)
        else:
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
        # `apps` ACCUMULATES the layers this run recorded, in first-seen order.
        # An explicit `--app` list still REPLACES it wholesale (a partial list
        # read as complete is worse than none) — that is the `apps is not None`
        # branch, and it runs after, so the operator's word wins.
        if as_apps:
            declared = list(spec.get("apps") or [])
            for layer in layers:
                if layer.name not in declared:
                    declared.append(layer.name)
            spec["apps"] = declared
        if apps is not None:
            spec["apps"] = list(apps)
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
        if as_apps:
            # The caller reports on layers; hand back the derived view rather
            # than the stored spec, so `unanswered_cost_question` reads the same
            # shape on both sides of the handover.
            spec = dict(spec)
            spec["services"] = [
                _layer_view(session.get_doc(APP_KIND, app_name), app_name)
                for app_name in spec.get("apps") or []
            ]
            spec["services"] = [e for e in spec["services"] if e is not None]
        return spec


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
