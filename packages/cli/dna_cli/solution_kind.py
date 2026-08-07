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
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOLUTION_KIND = "Solution"
SOLUTION_API_VERSION = "github.com/ruinosus/dna/v1"

#: The Kind that OWNS the cost commitment since ``spec-app-e-o-servico``
#: (07/08/2026). It used to live here, promoted out of ``answers`` into
#: ``services[].pode_dormir``, and that promotion was right only while there
#: was nowhere else for it: an entry in ``services[]`` is one per DEPLOYMENT
#: (*"nove serviços sobre quatro imagens são nove entradas aqui"*), an ``App``
#: is now the deployment, and one fact in two places is two names for one fact.
#: So this record keeps the PROVENANCE OF THE RENDER — the Copier answer stays
#: verbatim inside ``answers`` — and the COMMITMENT is read off the ``App``.
COST_KIND = "App"

#: The field on :data:`COST_KIND` that answers it.
COST_FIELD = "can_sleep"


class SolutionRecordError(Exception):
    """A refusal from the record side, translated by the caller."""


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
        template: dict[str, Any] = {"src": self.template_src}
        if self.template_ref:
            template["ref"] = self.template_ref
        return {
            "name": self.name,
            "answers_file": self.answers_file,
            "template": template,
            "answers": dict(self.answers),
        }


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


# ── reading the record ───────────────────────────────────────────────────────


def read_solution(name: str, *, scope: str | None = None) -> dict[str, Any] | None:
    """The recorded ``Solution`` spec, or ``None`` when it does not exist."""
    from dna_cli._ctx import open_session  # noqa: PLC0415 — the kernel is lazy

    with open_session(scope) as session:
        doc = session.get_doc(SOLUTION_KIND, name)
        if doc is None:
            return None
        return dict(doc.spec or {})


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

    with open_session(scope) as session:
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
        return spec


def unanswered_cost_question(
    spec: dict[str, Any] | None, *, scope: str | None = None
) -> list[str]:
    """Services whose ``App`` never said whether they may sleep.

    Reads :data:`COST_FIELD` off the ``App`` named by each ``services[].name``
    — the two are the same string, because an entry here is one per DEPLOYMENT
    and an ``App`` is the deployment. Before ``spec-app-e-o-servico`` this read
    ``services[].pode_dormir``; the question is the same and the owner moved.

    ⚠️ **Absent is UNANSWERED, and absent is never ``False``.** Three states
    collapse into "unanswered" and none of them into "may not sleep":

    * no ``App`` by that name — the deployment has no declaration at all;
    * an ``App`` that omits ``can_sleep`` — nobody was asked;
    * ``can_sleep: null``.

    ``can_sleep: False`` is an ANSWER, and an expensive one (a fixed replica,
    ~US$ 90/month, forever). Reporting it as unanswered would be as wrong as
    presuming it: the first cries wolf, the second hides the replica nobody
    decided. That distinction is the whole point of this function and is the
    thing that had to survive the move between Kinds.

    Reported rather than refused, and on every run rather than once — the same
    shape as ``divergent_answers``, and for the same reason: a finding that
    speaks only at the moment it appears is a finding that goes quiet while the
    condition stays true.

    A store that cannot be read is not silently "all answered": the read is
    attempted once, and a failure leaves every service reported as unanswered,
    which is the loud side.
    """
    from dna_cli._ctx import open_session  # noqa: PLC0415 — the kernel is lazy

    names = [
        str(entry.get("name"))
        for entry in (spec or {}).get("services") or []
        if isinstance(entry, dict) and entry.get("name")
    ]
    if not names:
        return []

    answered: set[str] = set()
    try:
        with open_session(scope) as session:
            for name in names:
                doc = session.get_doc(COST_KIND, name)
                if doc is not None and isinstance(
                    (doc.spec or {}).get(COST_FIELD), bool
                ):
                    answered.add(name)
    except Exception:  # noqa: BLE001 — unreadable store reports the loud side
        return sorted(set(names))
    return sorted(set(names) - answered)
