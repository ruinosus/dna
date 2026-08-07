"""``dna solution`` — scaffold and UPDATE a multi-app repo from Copier templates.

What this is, and what it deliberately is not
=============================================
It is a thin, opinionated shell over **Copier** (`copier.run_copy` /
`copier.run_update`), the official library. No rendering engine, no merge
algorithm and no answers format is written here — reimplementing a
well-supported tool from its docs is forbidden in this house, and a template
renderer is exactly the kind of thing whose subtle divergences only surface
against somebody else's template.

What the shell adds is the part Copier has no opinion about, and every item on
the list is a defect that was MEASURED before it was coded:

1. **`update` re-passes the recorded answers, always, and reports the defaults
   that MOVED.** Copier keeps a recorded answer forever: an `update` without
   `--data` leaves `dna_floor: "0.74"` at `0.74` even when the new template
   defaults it to `0.75`, with no output at all. The most common change in this
   house — moving a version floor — is an ANSWER, not template text, so the
   silence is the whole failure. :func:`_defaults_that_moved` compares the old
   ref's literal defaults with the new ref's and names every answer that stayed
   behind; ``--adopt-new-defaults`` takes them.
2. **It reports every answer the update DROPPED.** An answer behind ``when:``
   is erased when the condition stops holding, and comes back as the template
   DEFAULT — not as what the human said — if the condition returns. Measured:
   ``graph_obo: true`` → *(absent)* → ``false``, in one round trip. That loss
   cannot be undone from inside this command (the value is gone from the only
   place that stored it); it can be made loud, and it is.
3. **It never hands Copier a per-instance answers file without ``-a``.** The
   one-answers-file-per-app layout this house wants (three MCP doors over one
   image = three answers files, one template) breaks Copier's default lookup
   with a bare ``TypeError: Template not found`` and a traceback. Answers files
   are discovered here, and the ambiguous case is a refusal that lists them.
4. **It says out loud when the template has no tags.** Copier's real
   precondition for `update` is *git*, not *a tag*: an untagged template
   updates the fleet anyway, under a synthesised pseudo-version
   (``0.0.0.post1.dev0+a54909c``). ``new`` warns; ``update`` refuses unless
   ``--allow-untagged``, because rolling a fleet forward from an unnamed HEAD
   is not a release.
5. **⭐ It prints the COST when the app cannot sleep.** ``can_sleep: false``
   renders ``minReplicas: 1``, and a fixed replica is ~US$ 90/month, recurring,
   forever — measured. The dna-cloud gate says the question *"can it sleep?"*
   must be answered **with the number on screen**, before anybody provisions;
   generation is the moment that question is actually being answered, so this
   is where the number goes. Printed from the answers file, so it appears with
   or without ``--solution``: the bill does not wait for a record.

And the refusal that has no flag
================================
**There is no ``--trust``, and there will not be one.** A template declaring
``_tasks``, ``_migrations`` or ``_jinja_extensions`` is refused, exit 4 (the
same code Copier uses, so scripts can tell it apart). Two independent reasons,
either sufficient: it is arbitrary code from a template author executing on the
user's machine — the exact vector this project already refused when it declined
to give a Kind a code field — and it is unreliable even when benign, because
tasks run **three times per update, two of them in temp directories with no git
repo**. Effects belong outside the template.

The two places no template can reach
====================================
Wiring a new app into a monorepo of this shape touches seven places. A Copier
template renders FILES, so it reaches five of them outright and a sixth once
the root workspace list becomes a glob. The remaining two — the azd
``azure.yaml`` (fixed top-level keys, no include) and the ROOT bicep that
invokes the app's module (Bicep has `module`, but the invocation is a line in
the shared file) — are blocks inside shared root documents in formats with no
include mechanism, and no template reaches them. That is not a gap to route
around with a task; it is the boundary. Every successful run prints it, by
name, and points at the guard on the other side. See
:data:`UNREACHABLE_WIRING`.
"""
from __future__ import annotations

import json
import subprocess
import sys
import warnings
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import click

# ── exit codes ───────────────────────────────────────────────────────────────
# 1 — a precondition the command refuses to violate (dirty tree, no git, no
#     answers file, ambiguous answers files, untagged template on `update`).
# 3 — the run succeeded but something was LOST or LEFT BEHIND, and `--strict`
#     asked for that to be a failure.
# 4 — the template asks for arbitrary code execution. Copier's own code for it;
#     kept identical so a caller can distinguish "unsafe template" from "bad
#     invocation" without parsing prose.
EXIT_REFUSED = 1
EXIT_FINDINGS = 3
EXIT_UNSAFE_TEMPLATE = 4

ANSWERS_GLOB = ".copier-answers*.y*ml"

# How Copier 9.17 spells a `validator:` refusal. It raises a PLAIN ValueError —
# not a CopierError — so without this it reaches a user as a traceback with no
# command name and no answer name anywhere near the top. Pinned by
# tests/test_solution_cmd.py::test_um_validator_do_template_vira_recusa_legivel,
# which drives a real validator rather than asserting the constant.
_VALIDATION_PREFIX = "Validation error for question"

# Keys Copier writes into the answers file about ITSELF. They are not answers,
# and re-feeding them as `data=` would be feeding the template its own
# bookkeeping.
_COPIER_META_PREFIX = "_"


# ⛔ The two wiring places no Copier template can reach, and why. This is a
# constant rather than something read off the template because it is a property
# of the FORMATS (azd's JSON Schema, Bicep's module invocation), not of any one
# template — a template that claimed to cover them would be claiming something
# mechanically impossible.
UNREACHABLE_WIRING: tuple[tuple[str, str], ...] = (
    (
        "azure.yaml  →  services.<name>",
        "the azd schema fixes the root document's top-level keys; there is no "
        "include, glob or fragment directory",
    ),
    (
        "the ROOT bicep  →  module <name>App '.../wiring/containerapp.bicep'",
        "Bicep has modules, but the INVOCATION is a line inside the shared root "
        "file; there is no glob and no include of a resource",
    ),
)


class SolutionError(click.ClickException):
    """A refusal, printed as prose and exiting with a code that means something."""

    def __init__(self, message: str, exit_code: int = EXIT_REFUSED) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# ── findings ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MovedDefault:
    """An answer that stayed put while the template's default moved under it."""

    name: str
    recorded: Any
    old_default: Any
    new_default: Any


@dataclass(frozen=True)
class DivergentAnswer:
    """An answer that is simply not what the template would answer today.

    The second tier, and the one with no memory — which is exactly why it
    exists. :class:`MovedDefault` needs to compare two refs, so it can only
    speak at the update where the default actually moves; the moment `_commit`
    advances, an answer that stayed behind becomes indistinguishable from one a
    human pinned on purpose, and the warning goes quiet forever. That is the
    silent failure re-entering by the back door.

    This tier asks a question that needs no history: *is this answer what the
    template defaults to right now?* A version floor left behind is reported on
    every single update until somebody moves it. The price is that deliberate
    choices show up too (`identity: entra` against a `workos` default), which is
    why it is informational and never auto-adopted.
    """

    name: str
    recorded: Any
    current_default: Any


@dataclass(frozen=True)
class LostAnswer:
    """An answer present before the update and gone (or changed) after it."""

    name: str
    before: Any
    after: Any | None
    absent: bool


@dataclass
class RunReport:
    """Everything a run wants to say, in one place, so ``--json`` is free."""

    action: str
    destination: str
    template: str
    answers_file: str | None = None
    template_version: str | None = None
    template_ref: str | None = None
    template_untagged: bool = False
    moved_defaults: list[MovedDefault] = field(default_factory=list)
    divergent_answers: list[DivergentAnswer] = field(default_factory=list)
    lost_answers: list[LostAnswer] = field(default_factory=list)
    missing_external_data: list[str] = field(default_factory=list)
    conflicted_paths: list[str] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)

    #: The ``Solution`` instance this run read from and wrote back to. ``None``
    #: when the run was not asked to keep a record — the record is opt-in; the
    #: reporting about it is not.
    solution: str | None = None
    #: Answers the record put back that the answers file had LOST. The one
    #: thing a record buys that a file cannot: a ``when:``-gated answer erased
    #: from the file returns as the human's value instead of the template's
    #: default.
    restored_answers: list[str] = field(default_factory=list)
    #: Recorded layers that never said whether they may sleep. A fixed replica
    #: is ~US$ 90/month, forever, so a layer with no answer here is a cost
    #: decision nobody made — reported on every run, never presumed.
    unanswered_cost: list[str] = field(default_factory=list)
    #: ⭐ Layers this run rendered that answered `can_sleep: false`. They cost a
    #: FIXED replica — ~US$ 90/month, recurring — and the whole reason the
    #: question is in the template is so the number can be on screen at the
    #: moment somebody decides. Read from the answers file, so it is reported
    #: with or without `--solution`: the bill does not wait for a record.
    no_sleep: list[str] = field(default_factory=list)
    #: The `App` fields the installed descriptor cannot hold. Non-empty means no
    #: `App` was written and nothing declares the cost — reported, never silent.
    #: Normally empty since #351; it fires on a `dna-cli` newer than its
    #: `dna-sdk`, which separate wheels make perfectly possible.
    app_kind_missing_fields: list[str] = field(default_factory=list)

    #: The command line that would take every default this run left behind.
    #: Printed rather than merely described, because it stays correct after
    #: ``_commit`` advances — which the two-ref comparison above does not.
    adopt_command: str | None = None

    @property
    def has_findings(self) -> bool:
        """What ``--strict`` fails on.

        Deliberately excludes :attr:`divergent_answers`: an answer differing
        from today's default is the normal state of any customised app, and a
        `--strict` that failed on it would be a `--strict` nobody could use.

        :attr:`unanswered_cost` IS included, and the asymmetry is deliberate:
        a divergent answer is a choice somebody made, an unanswered cost
        question is a choice nobody made. :attr:`restored_answers` is excluded
        for the opposite reason — a restore is the record WORKING.

        :attr:`no_sleep` is excluded on the same test: `can_sleep: false` is a
        cost somebody accepted, printed loudly so it stays accepted on purpose.
        A `--strict` that failed on it could never be run by a fleet that
        legitimately has one, which is how a gate gets switched off for good.
        :attr:`app_kind_missing_fields` is excluded because it is a fact about
        the installed descriptors, not about this run — failing every pipeline
        until another story lands is not a finding, it is an outage.
        """
        return bool(
            self.moved_defaults
            or self.lost_answers
            or self.missing_external_data
            or self.conflicted_paths
            or self.unanswered_cost
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "destination": self.destination,
            "template": self.template,
            "answers_file": self.answers_file,
            "template_version": self.template_version,
            "template_ref": self.template_ref,
            "template_untagged": self.template_untagged,
            "moved_defaults": [
                {
                    "name": m.name,
                    "recorded": m.recorded,
                    "old_default": m.old_default,
                    "new_default": m.new_default,
                }
                for m in self.moved_defaults
            ],
            "divergent_answers": [
                {
                    "name": d.name,
                    "recorded": d.recorded,
                    "current_default": d.current_default,
                }
                for d in self.divergent_answers
            ],
            "adopt_command": self.adopt_command,
            "lost_answers": [
                {"name": a.name, "before": a.before, "after": a.after, "absent": a.absent}
                for a in self.lost_answers
            ],
            "missing_external_data": self.missing_external_data,
            "conflicted_paths": self.conflicted_paths,
            "changed_paths": self.changed_paths,
            "solution": self.solution,
            "restored_answers": self.restored_answers,
            "unanswered_cost": self.unanswered_cost,
            "no_sleep": self.no_sleep,
            "app_kind_missing_fields": self.app_kind_missing_fields,
            "unreachable_wiring": [place for place, _ in UNREACHABLE_WIRING],
        }


# ── copier, imported late ────────────────────────────────────────────────────


def _copier() -> Any:
    """Import Copier, or refuse with the install line.

    Late + guarded so the base ``dna`` install never carries it: the extra is
    ``dna-cli[scaffold]``, exactly like ``[mcp]`` and ``[api]``.
    """
    try:
        import copier  # noqa: PLC0415
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised by the guard test
        raise SolutionError(
            "`dna solution` needs Copier, the official templating library.\n"
            "  Install the extra:  pip install 'dna-cli[scaffold]'"
        ) from exc
    return copier


def _copier_errors() -> Any:
    import copier.errors  # noqa: PLC0415

    return copier.errors


def _copier_template_class() -> Any:
    """Copier's read-only ``Template`` accessor.

    ⚠️ ``copier._template`` is private API, used here for READING only —
    resolved version, git tags, and the questions' declared defaults at a given
    ref. Copier exposes no public equivalent, and the alternative is
    re-deriving template resolution (clone, ref selection, `copier.yml`
    merging) by hand, which is the reimplementation this house forbids.

    Two things keep the risk honest rather than hidden: the ``scaffold`` extra
    pins ``copier>=9.17,<10``, and ``tests/test_solution_cmd.py`` asserts every
    private attribute named here still exists — so an upgrade that moves them
    fails a test instead of a user.
    """
    from copier._template import Template  # noqa: PLC0415

    return Template


# ── git, the thin part ───────────────────────────────────────────────────────


def _git(dst: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(dst), *args], capture_output=True, text=True, check=False
    )


def _is_git_repo(path: Path) -> bool:
    return _git(path, "rev-parse", "--git-dir").returncode == 0


def _porcelain(dst: Path) -> list[tuple[str, str]]:
    """``(status, path)`` pairs, ONE ROW PER PATH.

    ⚠️ Deliberately not ``git ls-files``: with a path in conflict, ls-files
    lists it three times (stages 1/2/3), so a naive count overstates the change
    set by two per conflict. Measured — it is how a first reading of the
    adversarial experiment reported 9.1 % instead of 11.1 %.
    """
    out = _git(dst, "status", "--porcelain")
    rows: list[tuple[str, str]] = []
    for line in out.stdout.splitlines():
        if len(line) < 4:
            continue
        status, path = line[:2], line[3:].strip()
        # A rename reads "R  old -> new"; the path that exists now is the new one.
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        rows.append((status, path.strip('"')))
    return rows


def _conflicted_paths(dst: Path) -> list[str]:
    """Paths git reports as unmerged, deduplicated."""
    unmerged = {"UU", "AA", "DD", "AU", "UA", "DU", "UD"}
    return sorted({p for s, p in _porcelain(dst) if s in unmerged})


def _template_has_tags(local_abspath: Path) -> bool:
    return bool(_git(Path(local_abspath), "tag", "--list").stdout.strip())


# ── answers files ────────────────────────────────────────────────────────────


def _load_yaml(path: Path) -> dict[str, Any]:
    # Through the SDK's shared seam, never `yaml.safe_load` — that hardcodes
    # PyYAML's pure-Python loader, and `dna._yaml` is where this repo made the
    # libyaml decision once. Ratcheted by tests/test_yaml_loader_cli.py.
    from dna._yaml import safe_load  # noqa: PLC0415

    data = safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SolutionError(f"{path} does not hold a mapping of answers.")
    return data


def discover_answers_files(dst: Path) -> list[Path]:
    """Every answers file in ``dst``, as paths RELATIVE to it, sorted.

    The per-instance layout (``.copier-answers.<service>.yml``) is the point of
    the design — one template overlaid N times — and it is also what makes
    Copier's default lookup miss. Discovery here is what turns that miss into a
    named choice instead of a ``TypeError``.
    """
    return sorted(p.relative_to(dst) for p in dst.glob(ANSWERS_GLOB) if p.is_file())


def resolve_answers_file(
    dst: Path, *, answers_file: str | None, service: str | None
) -> Path:
    """Pick the one answers file this invocation is about, or refuse.

    Never guesses between several: a wrong guess would update the wrong app,
    and the whole reason there are several is that they are independent.
    """
    if answers_file and service:
        raise SolutionError("Pass either --answers-file or --service, not both.")
    if answers_file:
        chosen = Path(answers_file)
        if not (dst / chosen).is_file():
            raise SolutionError(f"No answers file at {dst / chosen}.")
        return chosen
    if service:
        chosen = Path(f".copier-answers.{service}.yml")
        if not (dst / chosen).is_file():
            found = discover_answers_files(dst)
            hint = (
                "\n  Found: " + ", ".join(str(p) for p in found) if found else ""
            )
            raise SolutionError(
                f"No answers file for service '{service}' "
                f"(expected {dst / chosen}).{hint}"
            )
        return chosen

    found = discover_answers_files(dst)
    if not found:
        raise SolutionError(
            f"{dst} records no Copier answers — there is nothing to update.\n"
            "  An answers file is written by `dna solution new`; a tree generated "
            "without one can be regenerated but never updated."
        )
    if len(found) > 1:
        listing = "\n".join(f"    {p}" for p in found)
        raise SolutionError(
            f"{dst} carries {len(found)} answers files — one per app, which is the "
            "design. Say which one:\n"
            f"{listing}\n"
            "  e.g.  dna solution update "
            f"{dst} --service {str(found[0]).removeprefix('.copier-answers.').removesuffix('.yml')}"
        )
    return found[0]


def _answers_contents(dst: Path) -> dict[str, str]:
    """Every answers file's raw text, keyed by relative path.

    Content rather than mtime: a render that rewrites a file with the same
    bytes did not produce a new layer, and second-resolution timestamps would
    say it did.
    """
    if not dst.exists():
        return {}
    out: dict[str, str] = {}
    for path in dst.glob(ANSWERS_GLOB):
        if path.is_file():
            out[str(path.relative_to(dst))] = path.read_text(encoding="utf-8")
    return out


def _answers_file_written(dst: Path, before: dict[str, str]) -> Path | None:
    """The ONE answers file this run created or changed, or ``None``.

    ``None`` on both ambiguous ends, and neither is guessed at: no file
    changed (nothing to record), or several did (a run that touched two layers
    is not a layer). Every caller turns ``None`` into a refusal that names the
    explicit command, because recording the wrong layer would point a future
    `update` at the wrong app — the same thing ``resolve_answers_file`` already
    refuses to guess about.
    """
    after = _answers_contents(dst)
    changed = [rel for rel, text in after.items() if before.get(rel) != text]
    return Path(changed[0]) if len(changed) == 1 else None


def recorded_answers(dst: Path, answers_relpath: Path) -> dict[str, Any]:
    """The answers a previous run recorded, without Copier's own bookkeeping."""
    raw = _load_yaml(dst / answers_relpath)
    return {k: v for k, v in raw.items() if not k.startswith(_COPIER_META_PREFIX)}


def recorded_ref(dst: Path, answers_relpath: Path) -> str | None:
    return _load_yaml(dst / answers_relpath).get("_commit")


def recorded_src(dst: Path, answers_relpath: Path) -> str | None:
    return _load_yaml(dst / answers_relpath).get("_src_path")


# ── the two comparisons that make the silent failures loud ───────────────────


def literal_defaults(questions_data: dict[str, Any]) -> dict[str, Any]:
    """The declared defaults that are LITERALS, not Jinja expressions.

    A default like ``"{{ image_name | replace('-', '_') }}"`` cannot be
    compared without rendering it in the full answer context, and rendering it
    to produce a warning would risk being wrong in a message whose whole value
    is being right. Templated defaults are therefore skipped, and the guide
    says so. Every version-floor default this house actually bumps is a
    literal, which is the case that matters.
    """
    out: dict[str, Any] = {}
    for name, spec in (questions_data or {}).items():
        if not isinstance(spec, dict):
            # copier's shorthand: `name: value` IS the default.
            out[name] = spec
            continue
        if "default" not in spec:
            continue
        default = spec["default"]
        if isinstance(default, str) and ("{{" in default or "{%" in default):
            continue
        out[name] = default
    return out


def defaults_that_moved(
    *,
    recorded: dict[str, Any],
    old_defaults: dict[str, Any],
    new_defaults: dict[str, Any],
    overridden: set[str],
) -> list[MovedDefault]:
    """Answers the update will silently leave behind.

    The condition is deliberately narrow — three clauses, each removing a false
    positive rather than adding a catch:

    * the default MOVED between the two refs (otherwise there is no news);
    * the recorded answer equals the OLD default, i.e. the human never
      customised it and was riding the template's judgement (a customised
      answer staying put is correct behaviour, not a finding);
    * this invocation is not already moving it explicitly.

    What survives all three is exactly the version-floor case: recorded 0.74
    because 0.74 was the default, template now says 0.75, nobody asked for
    0.74, and Copier will keep 0.74 without a word.
    """
    moved: list[MovedDefault] = []
    for name, new_default in new_defaults.items():
        if name in overridden or name not in old_defaults or name not in recorded:
            continue
        old_default = old_defaults[name]
        if old_default == new_default:
            continue
        if recorded[name] != old_default:
            continue
        moved.append(
            MovedDefault(
                name=name,
                recorded=recorded[name],
                old_default=old_default,
                new_default=new_default,
            )
        )
    return sorted(moved, key=lambda m: m.name)


def divergent_answers(
    *,
    recorded: dict[str, Any],
    new_defaults: dict[str, Any],
    overridden: set[str],
    exclude: set[str],
) -> list[DivergentAnswer]:
    """Answers that are not what the template would answer today.

    No history is consulted, and that is the point — see
    :class:`DivergentAnswer`. Entries already reported as
    :class:`MovedDefault` are excluded so the same fact is not stated twice
    with two different degrees of alarm.
    """
    out: list[DivergentAnswer] = []
    for name, current in new_defaults.items():
        if name in overridden or name in exclude or name not in recorded:
            continue
        if recorded[name] == current:
            continue
        out.append(
            DivergentAnswer(name=name, recorded=recorded[name], current_default=current)
        )
    return sorted(out, key=lambda d: d.name)


def lost_answers(
    *, before: dict[str, Any], after: dict[str, Any], asked_for: set[str]
) -> list[LostAnswer]:
    """Answers that vanished or changed value WITHOUT being asked to.

    This is the ``when:`` trap made visible. A gated answer is erased the
    moment its condition stops holding; if the condition ever returns, Copier
    answers the template's default, not the human's original. Nothing in this
    command can undo that — the value existed in one place and that place is
    the file being rewritten — so the finding names it and prints the value, so
    a human (or the `Solution` record, once it exists) can carry it forward.
    """
    lost: list[LostAnswer] = []
    for name, old in before.items():
        if name in asked_for:
            continue
        if name not in after:
            lost.append(LostAnswer(name=name, before=old, after=None, absent=True))
        elif after[name] != old:
            lost.append(
                LostAnswer(name=name, before=old, after=after[name], absent=False)
            )
    return sorted(lost, key=lambda a: a.name)


# ── data on the command line ─────────────────────────────────────────────────


def parse_data(pairs: tuple[str, ...]) -> dict[str, Any]:
    """``KEY=VALUE`` pairs, with YAML scalar parsing so ``true`` is a bool.

    Copier types its questions; handing a ``bool`` question the string
    ``"true"`` is the kind of near-miss that renders subtly wrong output rather
    than failing.
    """
    from dna._yaml import safe_load  # noqa: PLC0415

    out: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SolutionError(f"--data expects KEY=VALUE, got {pair!r}.")
        key, _, raw = pair.partition("=")
        key = key.strip()
        if not key:
            raise SolutionError(f"--data expects KEY=VALUE, got {pair!r}.")
        try:
            out[key] = safe_load(raw)
        except Exception:  # noqa: BLE001 - a scalar that is not YAML is a string
            out[key] = raw
    return out


# ── rendering the report ─────────────────────────────────────────────────────


def _echo_unreachable_note() -> None:
    click.echo("")
    click.echo("⛔ Two wiring places this (or any) template cannot reach:")
    for place, why in UNREACHABLE_WIRING:
        click.echo(f"    {place}")
        click.echo(f"      — {why}")
    click.echo(
        "  They are blocks inside shared root documents, in formats with no include.\n"
        "  A `_tasks` hook could mutate them; this command refuses that road (it runs\n"
        "  3× per update, twice with no git repo, and it forces --trust).\n"
        "  Cover them from the other side: a wiring guard in the consuming repo that\n"
        "  fails when a service exists under apps/ and is missing from either file."
    )


def _echo_report(report: RunReport) -> None:
    if report.no_sleep:
        sk = _solution_kind()
        click.echo("")
        click.echo(
            f"⭐ COST — {len(report.no_sleep)} app(s) answered `can_sleep: false`, "
            "so the generated bicep says `minReplicas: 1`:"
        )
        for name in report.no_sleep:
            click.echo(f"    {name}")
        click.echo(
            f"  A fixed replica is ~US$ {sk.NO_SLEEP_USD_PER_MONTH}/month, "
            "RECURRING, forever — not a one-off.\n"
            "  Measured: the dna-cloud copilot with minReplicas 1 was US$ 94.43 of a\n"
            "  US$ 230.29 invoice, the largest single line on it.\n"
            "  ⭐ Provisioning it is the founder's decision, with the number on screen —\n"
            "     which is the whole reason `can_sleep` is a question and not a habit.\n"
            "     Re-answer it with --data can_sleep=true if this app can in fact sleep."
        )

    if report.app_kind_missing_fields:
        click.echo("")
        click.echo(
            "⚠ NO `App` was written, so nothing declares whether these services "
            "may sleep."
        )
        click.echo(
            "  The installed `App` descriptor cannot hold: "
            + ", ".join(report.app_kind_missing_fields)
        )
        click.echo(
            "  `App` declares `additionalProperties: false`, so writing those fields\n"
            "  against this descriptor is a REFUSED write, not a tolerated extra.\n"
            "  ⭐ The usual cause is a VERSION SKEW: `dna-cli` and `dna-sdk` are\n"
            "     separate wheels with independent floors, and this install has a CLI\n"
            "     newer than the SDK whose descriptors it writes against.\n"
            "     Raise the `dna-sdk` floor and re-run `dna solution record` — the\n"
            "     answers file on disk is the input, so nothing was lost.\n"
            "  ⚠️ The render's provenance WAS recorded: `answers_file`, `template` and\n"
            "     `answers` are in services[] as always. What is missing is the cost\n"
            "     commitment, and `dna solution record` is what fills it in later."
        )

    if report.restored_answers:
        click.echo("")
        click.echo(
            f"⭐ {len(report.restored_answers)} answer(s) came back from the "
            f"Solution record `{report.solution}` — the answers file no longer "
            "held them:"
        )
        for name in report.restored_answers:
            click.echo(f"    {name}")
        click.echo(
            "  A `when:`-gated answer is erased from the file when its condition\n"
            "  stops holding, and Copier answers the TEMPLATE's default if the\n"
            "  condition returns. The record outlives the file, so the human's\n"
            "  value is what was re-passed."
        )

    if report.unanswered_cost:
        click.echo("")
        click.echo(
            f"⚠ {len(report.unanswered_cost)} recorded service(s) have no App "
            "saying whether they may sleep:"
        )
        for name in report.unanswered_cost:
            click.echo(f"    {name}")
        click.echo(
            "  An app that cannot scale to zero costs a fixed replica — ~US$ 90 a\n"
            "  month, forever. Nothing here presumes the cheap side: absent is\n"
            "  said out loud, on every run, until somebody answers it. Answer it\n"
            "  by writing `can_sleep` on the App of the same name."
        )

    if report.template_untagged:
        click.echo(
            f"⚠ The template has NO git tags — Copier synthesised the version "
            f"{report.template_version}.\n"
            "  Copier's real precondition is git, not a tag; an untagged template "
            "will update a whole fleet from an unnamed HEAD."
        )

    if report.missing_external_data:
        click.echo("")
        click.echo(
            f"⚠ {len(report.missing_external_data)} external-data file(s) the template "
            "inherits from were NOT found:"
        )
        for name in report.missing_external_data:
            click.echo(f"    {name}")
        click.echo(
            "  Copier renders those inherited answers as EMPTY rather than failing, so\n"
            "  the tree above may be missing values it was meant to inherit. Generate\n"
            "  the layer above first, then re-run."
        )

    if report.moved_defaults:
        click.echo("")
        click.echo(
            f"⚠ {len(report.moved_defaults)} answer(s) kept a recorded value while the "
            "template default moved:"
        )
        for m in report.moved_defaults:
            click.echo(
                f"    {m.name}: {m.recorded!r}   (template default "
                f"{m.old_default!r} → {m.new_default!r})"
            )
        click.echo(
            "  A recorded answer always wins, so this update did NOT move them, and\n"
            "  without this line it would not have said so."
        )
        if report.adopt_command:
            click.echo(f"  Take them:  {report.adopt_command}")

    if report.divergent_answers:
        click.echo("")
        click.echo(
            f"ℹ {len(report.divergent_answers)} answer(s) differ from the template's "
            "current default:"
        )
        for d in report.divergent_answers:
            click.echo(
                f"    {d.name}: {d.recorded!r}   (template default {d.current_default!r})"
            )
        click.echo(
            "  Most of these are the point — an app that answered nothing differently\n"
            "  would not need to exist. They are listed because this line is the only\n"
            "  one that keeps saying so AFTER the update that moved the default: the\n"
            "  warning above can only speak once, this one speaks until you act."
        )

    if report.lost_answers:
        click.echo("")
        click.echo(f"⚠ {len(report.lost_answers)} recorded answer(s) changed unasked:")
        for a in report.lost_answers:
            if a.absent:
                click.echo(f"    {a.name}: {a.before!r} → (absent)")
            else:
                click.echo(f"    {a.name}: {a.before!r} → {a.after!r}")
        click.echo(
            "  A `when:`-gated answer is erased when its condition stops holding, and\n"
            "  returns as the template DEFAULT — not as the value above — if the\n"
            "  condition comes back."
        )
        if report.solution:
            click.echo(
                f"  The Solution `{report.solution}` kept it: the next update that\n"
                "  re-opens the condition will re-pass the value above, not the "
                "default."
            )
        else:
            click.echo(
                "  The value is printed here because this file is the only place that\n"
                "  held it. `--solution <name>` gives it a second one that survives."
            )

    if report.conflicted_paths:
        click.echo("")
        click.echo(f"⚠ {len(report.conflicted_paths)} file(s) in conflict:")
        for path in report.conflicted_paths:
            click.echo(f"    {path}")
        click.echo(
            "  Until they are resolved the tree does not build — conflict markers are\n"
            "  not valid source. Resolve per instance, not in a batch.\n"
            "  ⭐ A conflict in a wiring/ file is a different animal from one in src/:\n"
            "     it means a human expressed STRUCTURE the template never asked about.\n"
            "     The fix is a new question in copier.yml, not a merge."
        )


# ── the Solution record ──────────────────────────────────────────────────────
#
# ⚠️ The record is OPT-IN (`--solution NAME`). Rendering a tree must keep
# working with no kernel, no scope and no `.dna` anywhere — that is what makes
# `dna solution` usable against somebody else's repo — so the import below is
# late for the same reason Copier's is, and every helper here no-ops when no
# name was given.


def _record_options(fn: Any) -> Any:
    """The two options that turn a run into a recorded one.

    ``--sleep-answer`` was a third, and it is gone: it named the answer key
    that carried the cost commitment into ``services[].pode_dormir``. The
    commitment now lives on ``App.can_sleep``, authored on the App rather than
    lifted out of a template's answers, so there is no key to name. The
    template's answer is still recorded verbatim in ``answers``.
    """
    fn = click.option(
        "--scope",
        "scope",
        default=None,
        help="The DNA scope holding the Solution instance.",
    )(fn)
    fn = click.option(
        "--solution",
        "solution_name",
        default=None,
        metavar="NAME",
        help="Record this run in the Solution instance NAME — the declaration "
        "and the answers as governed data. It is what lets a `when:`-gated "
        "answer survive the update that erases it from the answers file.",
    )(fn)
    return fn


def _solution_kind() -> Any:
    from dna_cli import solution_kind  # noqa: PLC0415 — the kernel is lazy

    return solution_kind


def _cost_of(answers: dict[str, Any], *, service: str) -> list[str]:
    """``[service]`` when this layer said it may NOT sleep, else ``[]``.

    Read straight off the answers — no kernel, no record, no scope — because
    the bill does not wait for a `Solution` to exist. A `dna solution new` in
    somebody else's repo with no `.dna` anywhere still has to put the number on
    screen, since that run is exactly the moment the decision is being made.

    ⚠️ The key is not configurable, and that is the point rather than a
    shortcut: the template's questions and the `App`'s fields are ONE
    vocabulary (`copier.yml`, asserted by test), so the answer that becomes
    ``App.can_sleep`` is spelled ``can_sleep``. The old ``--sleep-answer`` knob
    named the key to PROMOTE, and there is nothing to promote any more.

    ⚠️ Only an explicit ``False`` counts. An ABSENT answer is not a cheap
    answer; it is the layer never having answered, which
    :func:`dna_cli.solution_kind.unanswered_cost_question` reports separately
    and never presumes.
    """
    return [service] if answers.get(_solution_kind().COST_FIELD) is False else []


def _record_layer(
    report: RunReport,
    destination: Path,
    answers_relpath: Path,
    *,
    solution_name: str,
    scope: str | None,
    service: str | None = None,
    extra_answers: dict[str, Any] | None = None,
) -> None:
    """Write one layer into the Solution, and report what the record says.

    ``extra_answers`` is what the record already held and the file no longer
    does — see :func:`dna_cli.solution_kind.upsert_solution` for why the
    write-back accumulates rather than mirrors.
    """
    sk = _solution_kind()
    try:
        layer = sk.layer_from_answers_file(
            destination,
            answers_relpath,
            service=service,
        )
        if extra_answers:
            layer = replace(layer, answers={**extra_answers, **layer.answers})
        spec = sk.upsert_solution(
            solution_name,
            [layer],
            scope=scope,
            repo=str(destination),
        )
    except sk.SolutionRecordError as exc:
        raise SolutionError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - a kernel failure is a refusal here
        raise SolutionError(
            f"the tree is written, but recording it in Solution "
            f"{solution_name!r} failed: {exc}\n"
            "  Re-run `dna solution record` once the scope is reachable — the "
            "answers file on disk is the input, so nothing was lost."
        ) from exc
    report.solution = solution_name
    report.unanswered_cost = sk.unanswered_cost_question(spec, scope=scope)
    report.app_kind_missing_fields = list(sk.app_kind_absent_fields())


# ── the group ────────────────────────────────────────────────────────────────


@click.group()
def solution() -> None:
    """Scaffold and update a repo from Copier templates.

    `dna solution new` renders one app; running it again with a different
    service name overlays a SECOND app from the same template, with its own
    answers file. `dna solution update` rolls one of them forward.

    Rendering always happens here, on this machine, from a template you point
    at — never on a server, and never with `--trust`.
    """


@solution.command("new")
@click.argument("template")
@click.argument("destination", type=click.Path(file_okay=False, path_type=Path))
@click.option(
    "-d",
    "--data",
    "data_pairs",
    multiple=True,
    metavar="KEY=VALUE",
    help="Answer a question without being asked. Repeatable.",
)
@click.option(
    "--answers-from",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="YAML file of answers, applied under --data. The hand-rolled precursor "
    "of a recorded Solution.",
)
@click.option(
    "--vcs-ref",
    default=None,
    help="Template ref to render (tag, branch or commit). Default: the latest tag.",
)
@click.option(
    "--defaults",
    "use_defaults",
    is_flag=True,
    help="Take the template's default for every question that was not answered.",
)
@click.option("--force", is_flag=True, help="Overwrite files that already exist.")
@click.option("--pretend", is_flag=True, help="Render nothing; report what would happen.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable report.")
@click.option(
    "--strict",
    is_flag=True,
    help=f"Exit {EXIT_FINDINGS} when the run has findings (missing inherited data, "
    "a recorded service whose App never answered the cost question).",
)
@_record_options
def new_(
    template: str,
    destination: Path,
    data_pairs: tuple[str, ...],
    answers_from: Path | None,
    vcs_ref: str | None,
    use_defaults: bool,
    force: bool,
    pretend: bool,
    as_json: bool,
    strict: bool,
    solution_name: str | None,
    scope: str | None,
) -> None:
    """Render TEMPLATE into DESTINATION, recording the answers.

    TEMPLATE is anything Copier accepts: a local path, a git URL, `gh:owner/repo`.
    Run it once per app; each run writes its own answers file, and each app is
    then updated independently.
    """
    data: dict[str, Any] = {}
    if answers_from:
        data.update(
            {k: v for k, v in _load_yaml(answers_from).items() if not k.startswith("_")}
        )
    data.update(parse_data(data_pairs))

    if not use_defaults and not sys.stdin.isatty():
        raise SolutionError(
            "Nothing to prompt with: stdin is not a terminal and --defaults was not "
            "given.\n"
            "  Answer up front instead:  --defaults  and/or  --data KEY=VALUE"
        )

    report = RunReport(action="new", destination=str(destination), template=template)
    copier = _copier()
    # ⚠️ Snapshotted BEFORE the render, because "which answers file did this run
    # write?" has no other answer once the repo holds several. The old
    # `found[0] if len(found) == 1` reported None from the SECOND `new`
    # onwards — harmless while nothing consumed it, wrong the moment a record
    # has to name the layer it just created.
    answers_before = _answers_contents(destination)

    tpl_cls = _copier_template_class()
    tpl = tpl_cls(url=str(template), ref=vcs_ref)
    try:
        _refuse_unsafe(tpl)
        report.template_version = str(tpl.version) if tpl.version else None
        report.template_ref = tpl.commit
        report.template_untagged = tpl.vcs == "git" and not _template_has_tags(
            Path(tpl.local_abspath)
        )
    finally:
        tpl._cleanup()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            copier.run_copy(
                str(template),
                destination,
                data=data,
                vcs_ref=vcs_ref,
                defaults=use_defaults,
                overwrite=force,
                pretend=pretend,
                unsafe=False,
                quiet=True,
            )
        except BaseException as exc:  # noqa: BLE001
            raise _translate(exc, destination) from exc
    report.missing_external_data = _missing_external_data(caught)

    if destination.exists() and _is_git_repo(destination):
        report.changed_paths = [p for _, p in _porcelain(destination)]
    written: Path | None = None
    if not pretend:
        written = _answers_file_written(destination, answers_before)
        report.answers_file = str(written) if written else None
        if written is not None:
            # ⭐ The cost gate, at the moment the tree is created. Read from the
            # answers file the run just wrote — not from `data`, which holds
            # only what was passed on the command line and would stay silent
            # about a `can_sleep: false` that came from `--answers-from` or from
            # a template default.
            report.no_sleep = _cost_of(
                recorded_answers(destination, written),
                service=_solution_kind().service_name_of(written),
            )

    if solution_name and not pretend:
        if written is None:
            raise SolutionError(
                f"the tree is written, but this run cannot tell which answers "
                f"file it produced, so it will not guess which layer to record "
                f"in Solution {solution_name!r}.\n"
                "  Name it and record it explicitly:  dna solution record "
                f"{destination} --solution {solution_name} --service <name>"
            )
        _record_layer(
            report,
            destination,
            written,
            solution_name=solution_name,
            scope=scope,
        )

    if as_json:
        click.echo(json.dumps(report.to_json(), indent=2, sort_keys=True, default=str))
    else:
        verb = "Would render" if pretend else "Rendered"
        click.echo(f"{verb} {template} → {destination}")
        if report.template_version:
            click.echo(f"  template version: {report.template_version}")
        _echo_report(report)
        _echo_unreachable_note()

    if strict and report.has_findings:
        raise SolutionError("Findings above, and --strict was given.", EXIT_FINDINGS)


@solution.command("update")
@click.argument(
    "destination",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
)
@click.option(
    "-a",
    "--answers-file",
    default=None,
    help="The answers file to update, relative to DESTINATION.",
)
@click.option(
    "-s",
    "--service",
    default=None,
    help="Shorthand for -a .copier-answers.<service>.yml.",
)
@click.option(
    "-d",
    "--data",
    "data_pairs",
    multiple=True,
    metavar="KEY=VALUE",
    help="Move an answer as part of this update. Repeatable.",
)
@click.option(
    "--answers-from",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="YAML file of answers to apply over the recorded ones.",
)
@click.option(
    "--adopt-new-defaults",
    is_flag=True,
    help="Take every default that moved since the recorded ref (see the report).",
)
@click.option("--vcs-ref", default=None, help="Update to this ref instead of the latest tag.")
@click.option(
    "--allow-untagged",
    is_flag=True,
    help="Proceed even though the template publishes no tags.",
)
@click.option(
    "--conflict",
    type=click.Choice(["inline", "rej"]),
    default="inline",
    help="How Copier records a conflict.",
)
@click.option("--pretend", is_flag=True, help="Change nothing; report what would happen.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable report.")
@click.option(
    "--strict",
    is_flag=True,
    help=f"Exit {EXIT_FINDINGS} when the run has findings (lost answers, conflicts, "
    "defaults left behind, a recorded service whose App never answered the "
    "cost question).",
)
@_record_options
def update(
    destination: Path,
    answers_file: str | None,
    service: str | None,
    data_pairs: tuple[str, ...],
    answers_from: Path | None,
    adopt_new_defaults: bool,
    vcs_ref: str | None,
    allow_untagged: bool,
    conflict: str,
    pretend: bool,
    as_json: bool,
    strict: bool,
    solution_name: str | None,
    scope: str | None,
) -> None:
    """Roll ONE app in DESTINATION forward to a newer template version.

    The recorded answers are always re-passed, so nothing is re-asked and
    nothing is silently re-defaulted. Whatever the update leaves behind or drops
    is named in the report — that reporting is the reason this command exists
    rather than a `copier update` alias.

    With `--solution NAME` the recorded instance joins the answers file as a
    second, LONGER memory: the two are merged before anything is compared or
    re-passed, so an answer `when:` erased from the file comes back as the
    human's value instead of the template's default, and the merged set is
    written back afterwards.
    """
    destination = destination.resolve()
    if not _is_git_repo(destination):
        raise SolutionError(
            f"{destination} is not a git repository, and `update` is a three-way "
            "merge:\n"
            "  it needs the previous state to merge against. Initialise git and commit "
            "the tree first."
        )

    answers_relpath = resolve_answers_file(
        destination, answers_file=answers_file, service=service
    )
    from_file = recorded_answers(destination, answers_relpath)
    old_ref = recorded_ref(destination, answers_relpath)
    src = recorded_src(destination, answers_relpath)
    if not src:
        raise SolutionError(
            f"{answers_relpath} records no `_src_path` — there is no template to "
            "update from."
        )

    report = RunReport(
        action="update",
        destination=str(destination),
        template=src,
        answers_file=str(answers_relpath),
    )

    # ⭐ The seam. `before` is the ONE variable every comparison and the `data=`
    # Copier receives are built from, so folding the record in here is what
    # makes a recorded answer compared, re-passed and reported through the
    # paths fatia 3 already built — instead of a second set living beside them
    # and agreeing with them only by luck. Merging anywhere further down would
    # leave an answer that lives only in the record out of `moved_defaults` and
    # `divergent_answers`, which is the version floor going quiet again by a
    # different door.
    layer_name = service or _solution_kind().service_name_of(answers_relpath)
    solution_spec: dict[str, Any] | None = None
    from_record: dict[str, Any] = {}
    if solution_name:
        sk = _solution_kind()
        solution_spec = sk.read_solution(solution_name, scope=scope)
        if solution_spec is None:
            raise SolutionError(
                f"no Solution {solution_name!r} in this scope.\n"
                "  Record the tree first:  dna solution record "
                f"{destination} --solution {solution_name}"
            )
        from_record = sk.recorded_answers_of(solution_spec, layer_name)
        report.solution = solution_name
        report.restored_answers = sk.restored_keys(
            recorded=from_record, from_file=from_file
        )
        before = sk.merged_before(recorded=from_record, from_file=from_file)
    else:
        before = from_file

    copier = _copier()
    tpl_cls = _copier_template_class()

    new_tpl = tpl_cls(url=src, ref=vcs_ref)
    try:
        _refuse_unsafe(new_tpl)
        report.template_version = str(new_tpl.version) if new_tpl.version else None
        report.template_ref = new_tpl.commit
        report.template_untagged = new_tpl.vcs == "git" and not _template_has_tags(
            Path(new_tpl.local_abspath)
        )
        new_defaults = literal_defaults(new_tpl.questions_data)
    finally:
        new_tpl._cleanup()

    if report.template_untagged and not allow_untagged:
        raise SolutionError(
            "The template publishes NO git tags, so this update would roll the tree "
            f"forward to an unnamed HEAD under a synthesised version "
            f"({report.template_version}).\n"
            "  Copier allows it — its real precondition is git, not a tag — and that "
            "is exactly why this refusal exists:\n"
            "  a fleet updated from an unnamed HEAD has no version anyone can name "
            "afterwards.\n"
            "  Tag the template, or say so on purpose with --allow-untagged."
        )

    old_defaults: dict[str, Any] = {}
    if old_ref:
        old_tpl = tpl_cls(url=src, ref=old_ref)
        try:
            old_defaults = literal_defaults(old_tpl.questions_data)
        except Exception:  # noqa: BLE001 - an unreachable old ref is not fatal
            old_defaults = {}
        finally:
            old_tpl._cleanup()

    overrides: dict[str, Any] = {}
    if answers_from:
        overrides.update(
            {k: v for k, v in _load_yaml(answers_from).items() if not k.startswith("_")}
        )
    overrides.update(parse_data(data_pairs))

    report.moved_defaults = defaults_that_moved(
        recorded=before,
        old_defaults=old_defaults,
        new_defaults=new_defaults,
        overridden=set(overrides),
    )
    if adopt_new_defaults:
        for moved in report.moved_defaults:
            overrides[moved.name] = moved.new_default
        report.moved_defaults = []
    elif report.moved_defaults:
        # The ready-made line, not a description of one. `--adopt-new-defaults`
        # only works in the run that DETECTS the move: once this update writes
        # the new `_commit`, the two-ref comparison has nothing left to compare
        # and the flag goes quiet. An explicit `--data` list does not, so it is
        # what gets printed.
        target = f"--service {service}" if service else f"-a {answers_relpath}"
        pairs = " ".join(
            f"--data {m.name}={m.new_default}" for m in report.moved_defaults
        )
        report.adopt_command = f"dna solution update {destination} {target} {pairs}"
    report.divergent_answers = divergent_answers(
        recorded=before,
        new_defaults=new_defaults,
        overridden=set(overrides),
        exclude={m.name for m in report.moved_defaults},
    )

    # ⭐ THE line. Copier keeps a recorded answer forever, so an update that
    # does not re-pass them is an update that can never move one — and it moves
    # nothing without saying so. Re-passing them explicitly makes this command,
    # not Copier's memory, the thing that decides what the answers are; the
    # overrides on top are then the only way an answer changes, which is what
    # makes the report above trustworthy.
    data = {**before, **overrides}

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            copier.run_update(
                destination,
                data=data,
                answers_file=answers_relpath,
                vcs_ref=vcs_ref,
                defaults=True,
                overwrite=True,
                conflict=conflict,
                pretend=pretend,
                unsafe=False,
                quiet=True,
            )
        except BaseException as exc:  # noqa: BLE001
            raise _translate(exc, destination) from exc
    report.missing_external_data = _missing_external_data(caught)

    after = recorded_answers(destination, answers_relpath)
    # ⚠️ `from_file`, NOT `before`. This finding asks what the FILE lost across
    # this run; handing it the merged view would report an answer the record
    # RESTORED as a loss, on every update, forever — a false alarm generated by
    # the fix for the real one.
    report.lost_answers = lost_answers(
        before=from_file, after=after, asked_for=set(overrides)
    )
    report.no_sleep = _cost_of(after, service=layer_name)
    report.conflicted_paths = _conflicted_paths(destination)
    report.changed_paths = [p for _, p in _porcelain(destination)]

    if solution_name and not pretend:
        _record_layer(
            report,
            destination,
            answers_relpath,
            solution_name=solution_name,
            scope=scope,
            service=layer_name,
            extra_answers=from_record,
        )

    if as_json:
        click.echo(json.dumps(report.to_json(), indent=2, sort_keys=True, default=str))
    else:
        verb = "Would update" if pretend else "Updated"
        click.echo(f"{verb} {answers_relpath} in {destination}")
        if report.template_version:
            click.echo(f"  template version: {report.template_version}")
        if solution_name:
            click.echo(
                f"  re-passed {len(before)} recorded answer(s) "
                f"({len(from_file)} from {answers_relpath}, "
                f"{len(report.restored_answers)} only in Solution {solution_name})"
            )
        else:
            click.echo(f"  re-passed {len(before)} recorded answer(s)")
        if overrides:
            click.echo(
                "  moved: "
                + ", ".join(f"{k}={v!r}" for k, v in sorted(overrides.items()))
            )
        _echo_report(report)
        _echo_unreachable_note()

    if strict and report.has_findings:
        raise SolutionError("Findings above, and --strict was given.", EXIT_FINDINGS)


@solution.command("list")
@click.argument(
    "destination",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
)
@click.option("--json", "as_json", is_flag=True, help="Machine-readable listing.")
def list_(destination: Path, as_json: bool) -> None:
    """List the template layers recorded in DESTINATION.

    One row per answers file — which is one row per app, because the design is
    one template overlaid N times, each with its own answers and its own
    independent update.
    """
    destination = destination.resolve()
    rows = []
    for relpath in discover_answers_files(destination):
        raw = _load_yaml(destination / relpath)
        rows.append(
            {
                "answers_file": str(relpath),
                "template": raw.get("_src_path"),
                "ref": raw.get("_commit"),
                "answers": {k: v for k, v in raw.items() if not k.startswith("_")},
            }
        )

    if as_json:
        click.echo(json.dumps(rows, indent=2, sort_keys=True, default=str))
        return
    if not rows:
        click.echo(f"{destination} records no Copier answers.")
        return
    click.echo(f"{len(rows)} template layer(s) in {destination}:")
    for row in rows:
        click.echo(f"  {row['answers_file']}")
        click.echo(f"    template: {row['template']}")
        click.echo(f"    ref:      {row['ref']}")
        click.echo(f"    answers:  {len(row['answers'])}")


@solution.command("record")
@click.argument(
    "destination",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
)
@click.option(
    "--solution",
    "solution_name",
    required=True,
    metavar="NAME",
    help="The Solution instance to write.",
)
@click.option("--scope", default=None, help="The DNA scope holding the instance.")
@click.option(
    "-a", "--answers-file", default=None, help="Record only this answers file."
)
@click.option("-s", "--service", default=None, help="Record only this service.")
@click.option("--title", default=None, help="Human title (default: the name).")
@click.option("--description", default=None, help="One line of what it delivers.")
@click.option(
    "--app",
    "apps",
    multiple=True,
    metavar="NAME",
    help="An App this solution delivers. Repeatable. REPLACES the recorded list "
    "when given — and must then name EVERY recorded service: `apps` is the only "
    "join the kernel can enforce, and an App IS a deployment. A list that leaves "
    "one out is refused with both sides named. Rarely needed; the recorded "
    "layers already fill it.",
)
@click.option("--json", "as_json", is_flag=True, help="Machine-readable report.")
@click.option(
    "--strict",
    is_flag=True,
    help=f"Exit {EXIT_FINDINGS} when a recorded service has no App answering "
    f"the cost "
    "question.",
)
def record(
    destination: Path,
    solution_name: str,
    scope: str | None,
    answers_file: str | None,
    service: str | None,
    title: str | None,
    description: str | None,
    apps: tuple[str, ...],
    as_json: bool,
    strict: bool,
) -> None:
    """Record DESTINATION's template layers in a `Solution` instance.

    The declaration and the answers become governed data — versioned,
    overlayable, and readable across the fleet without opening anybody's repo.

    Records EVERY layer by default: this is what an existing tree needs, and a
    record that covered some of a repo's apps would answer "which of them may
    sleep?" with a number that is wrong and looks right. `-a`/`-s` narrow it to
    one on purpose.

    It stores no code and no template body — a `template.src` + `ref` pointer
    and the answers verbatim. The cost commitment is NOT stored here: it is
    read off the `App` of the same name (`can_sleep`), and services whose App
    has not answered are reported on every run.
    """
    destination = destination.resolve()
    sk = _solution_kind()

    if answers_file or service:
        relpaths = [
            resolve_answers_file(
                destination, answers_file=answers_file, service=service
            )
        ]
    else:
        relpaths = discover_answers_files(destination)
        if not relpaths:
            raise SolutionError(
                f"{destination} records no Copier answers — there is nothing to "
                "record.\n"
                "  An answers file is written by `dna solution new`; a tree "
                "generated without one holds no declaration to govern."
            )

    layers = []
    for relpath in relpaths:
        try:
            layers.append(
                sk.layer_from_answers_file(
                    destination,
                    relpath,
                    service=service if (answers_file or service) else None,
                )
            )
        except sk.SolutionRecordError as exc:
            raise SolutionError(str(exc)) from exc

    try:
        spec = sk.upsert_solution(
            solution_name,
            layers,
            scope=scope,
            title=title,
            description=description,
            repo=str(destination),
            apps=list(apps) if apps else None,
        )
    except Exception as exc:  # noqa: BLE001
        raise SolutionError(f"recording Solution {solution_name!r} failed: {exc}") from exc

    unanswered = sk.unanswered_cost_question(spec, scope=scope)
    # ⚠️ Read from the ANSWERS, not from a `Layer` field: the cost commitment is
    # no longer promoted onto the layer (it is `App.can_sleep` now), and the
    # Copier answer that produced it stays in `answers` verbatim. `is False`,
    # never `not …` — an ABSENT answer is unanswered, which `unanswered` above
    # reports, and is not the same sentence as "this one costs a replica".
    no_sleep = sorted(
        layer.name
        for layer in layers
        if layer.answers.get(sk.COST_FIELD) is False
    )
    missing_app_fields = list(sk.app_kind_absent_fields())
    if as_json:
        click.echo(
            json.dumps(
                {
                    "solution": solution_name,
                    "destination": str(destination),
                    "recorded": [layer.name for layer in layers],
                    "services": [entry.get("name") for entry in spec["services"]],
                    "apps": list(spec.get("apps") or []),
                    "unanswered_cost": unanswered,
                    "no_sleep": no_sleep,
                    "app_kind_missing_fields": missing_app_fields,
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
    else:
        click.echo(
            f"Recorded {len(layers)} layer(s) in Solution {solution_name} "
            f"({len(spec['services'])} total)"
        )
        for layer in layers:
            # "sleeps" is deliberately NOT printed from the Copier answer any
            # more. It is the App's fact now, and echoing a second reading of
            # it here is how one fact grows two answers that can disagree. The
            # unanswered list below is what says something about cost.
            click.echo(
                f"    {layer.name}  ← {layer.answers_file}  "
                f"(ref {layer.template_ref or '—'}, {len(layer.answers)} answers)"
            )
        report = RunReport(
            action="record",
            destination=str(destination),
            template=layers[0].template_src,
            solution=solution_name,
            unanswered_cost=unanswered,
            no_sleep=no_sleep,
            app_kind_missing_fields=missing_app_fields,
        )
        _echo_report(report)

    if strict and unanswered:
        raise SolutionError(
            "A recorded service has no App answering the cost question, and --strict "
            "was "
            "given.",
            EXIT_FINDINGS,
        )


# ── the refusals ─────────────────────────────────────────────────────────────


def _refuse_unsafe(template: Any) -> None:
    """Refuse a template that asks to execute code. No flag opens this door.

    Checked here, BEFORE anything is written, rather than left to Copier's own
    check — so `new` refuses without having created a directory first, and so
    the message can say why the door has no handle instead of pointing at
    `--trust` the way Copier's does.
    """
    unsafe: list[str] = []
    if template.tasks:
        unsafe.append("_tasks")
    if template.jinja_extensions:
        unsafe.append("_jinja_extensions")
    if template.config_data.get("migrations"):
        unsafe.append("_migrations")
    if not unsafe:
        return
    raise SolutionError(
        f"This template declares {', '.join(unsafe)}, which means running code the "
        "template author wrote, on this machine.\n"
        "  `dna solution` refuses it, and has no --trust flag to change that. Two "
        "reasons, either sufficient:\n"
        "    • it is arbitrary code execution from a template you may not have "
        "written;\n"
        "    • it is unreliable even when benign — tasks run 3× per update, 2 of "
        "them in temp\n"
        "      directories with no git repo, so a task that assumes project context "
        "breaks and\n"
        "      a task that is not idempotent corrupts.\n"
        "  Effects belong outside the template: render, then run your own step.",
        EXIT_UNSAFE_TEMPLATE,
    )


def _missing_external_data(caught: list[warnings.WarningMessage]) -> list[str]:
    """External-data files Copier could not find, from its own warning.

    `_external_data` is how one template layer inherits the layer above it
    without template inheritance (which Copier does not have). When the file is
    absent Copier warns and renders the inherited values as EMPTY — it does not
    fail — so an app can be generated missing everything it was meant to
    inherit, and look fine.
    """
    errors = _copier_errors()
    missing: list[str] = []
    for entry in caught:
        if issubclass(entry.category, errors.MissingFileWarning):
            missing.append(str(entry.message))
    return missing


def _translate(exc: BaseException, destination: Path) -> BaseException:
    """Turn Copier's failures into refusals a human can act on.

    Three shapes, and the ordering matters:

    * ``UnsafeTemplateError`` — relayed with OUR reasoning and exit 4.
    * ``UserMessageError`` — Copier's own precondition messages (dirty tree, no
      git in the subproject) are already clear and correct. They are relayed
      verbatim, not rewritten: a message measured to be good is not improved by
      paraphrase.
    * ``TypeError: Template not found`` — the per-instance answers file hitting
      Copier's default lookup. Bare, with a traceback, and about as far from
      the actual problem as an error can get. Discovery upstream should make it
      unreachable; it is translated anyway, because "should be unreachable" is
      how tracebacks reach users.
    """
    errors = _copier_errors()
    if isinstance(exc, errors.UnsafeTemplateError):
        return SolutionError(
            f"{exc}\n"
            "  `dna solution` has no --trust flag: effects belong outside the "
            "template.",
            EXIT_UNSAFE_TEMPLATE,
        )
    if isinstance(exc, errors.UserMessageError):
        return SolutionError(str(exc))
    if isinstance(exc, TypeError) and "Template not found" in str(exc):
        found = discover_answers_files(destination)
        listing = (
            "\n  Answers files here:\n"
            + "\n".join(f"    {p}" for p in found)
            if found
            else ""
        )
        return SolutionError(
            "Copier could not find the template for this tree.\n"
            "  The usual cause is an answers file that is not the default "
            "`.copier-answers.yml` — which is the layout this command uses on "
            "purpose, one per app.\n"
            f"  Name it explicitly with -a/--service.{listing}"
        )
    if isinstance(exc, ValueError) and str(exc).startswith(_VALIDATION_PREFIX):
        # A `validator:` in the template said no. Copier raises a plain
        # ValueError for it, which reaches a user as a bare traceback — measured
        # on the `owns_code` validator, and true of `service_name`'s since the
        # day it was written. The message itself is the TEMPLATE AUTHOR's and is
        # the most specific thing anyone has about this answer, so it is relayed
        # verbatim and only framed.
        return SolutionError(
            f"{exc}\n"
            "  That refusal comes from the template's own `validator:`, not from "
            "`dna solution`.\n"
            "  Fix the answer (-d KEY=VALUE) — there is nothing here to override "
            "it with."
        )
    if isinstance(exc, errors.CopierError):
        return SolutionError(f"{type(exc).__name__}: {exc}")
    return exc
