"""``dna specify`` — the bidirectional GitHub Spec Kit ↔ DNA bridge.

Spec Kit (github.com/github/spec-kit) is a *methodology*: a spec-driven flow
(constitution → spec → plan → tasks → implement) that scaffolds a ``.specify/``
toolkit and per-feature ``specs/<f>/`` runs. DNA is a *layer* — memory,
definitions, governance, tracking — stored as versioned Kinds. They compose:
Spec Kit owns the run; DNA mirrors it into durable, queryable, governed Kinds.

Two directions (ADR ``ADR-spec-kit-adoption``, Accepted 2026-07-15):

    dna specify import <path>     # Spec Kit .specify/ → DNA Kinds  (§4 mapping)
    dna specify export <feature>  # DNA Kinds → byte-faithful .specify/ projection

Import maps (ADR §4):

    .specify/memory/constitution.md → Guardrail + Soul  (--constitution-as, default both)
    specs/<f>/spec.md               → Spec   (pattern="spec-kit")
    specs/<f>/plan.md               → Plan   (methodology="spec-kit")
    research/data-model/quickstart/contracts/* → Reference via Plan.produces[]
    tasks.md (each `T### [P]? …`)   → Story per task under the Feature
    the whole run                   → WorkflowEvent(s) methodology=spec-kit (journey overlay)

Export reuses the "one source → N byte-faithful projections" philosophy of
``dna init`` / ``dna emit``: the Feature carries a ``spec.specify_run`` manifest
(source path → Kind/name/body_field) written at import time, and export replays
each mapped doc's verbatim body back to its ``.specify/`` path. Round-trip
(``import`` then ``export`` = byte-identical ``.specify/``) is an acceptance test.

The ingester is a sibling of ``emit_cmd``/``dna sdlc backfill`` — it reuses the
same markdown parse (title/status/date) and the ``dna_session`` →
``kernel.write_document`` pipeline, so the untrusted-input defenses never fork.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click

from dna_cli._ctx import dna_session, fail, print_json

SDLC_API_VERSION = "github.com/ruinosus/dna/sdlc/v1"
SOUL_API_VERSION = "soulspec.org/v1"
CORE_API_VERSION = "github.com/ruinosus/dna/v1"

#: The methodology tag stamped on every artifact this bridge produces.
METHODOLOGY = "spec-kit"

# ─── parsing helpers (pure, mirror `dna sdlc backfill`) ──────────────────────

_STATUS_RE = re.compile(r"^\*\*Status\*\*\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_AUTHOR_RE = re.compile(r"^\*\*Authors?\*\*\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
# A spec-kit tasks.md line: `- [ ] T001 [P] Do the thing` (checkbox + optional
# T-id + optional [P] parallel marker + description). Tolerant of `[x]`/`[X]`.
_TASK_RE = re.compile(
    r"^\s*[-*]\s*\[[ xX]?\]\s*(?:(T\d+)\b\s*)?(\[P\]\s*)?(.+?)\s*$",
)

_STATUS_MAP = {
    "shipped": "accepted", "rejected": "deprecated", "wip": "draft",
    "draft": "draft", "proposed": "proposed", "accepted": "accepted",
    "deprecated": "deprecated", "in progress": "draft", "in-progress": "draft",
    "superseded": "superseded",
}


def _slugify(dirname: str) -> str:
    """`001-taskify` → `taskify`; `taskify` → `taskify`. Strips a leading
    numeric ordinal and normalizes to a lowercase kebab slug."""
    stem = re.sub(r"^\d+[-_]", "", dirname.strip())
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower()
    return stem or "feature"


def _first_title(text: str, fallback: str) -> str:
    m = _TITLE_RE.search(text)
    return m.group(1).strip() if m else fallback


def _parse_status(text: str, default: str = "accepted") -> str:
    m = _STATUS_RE.search(text)
    raw = (m.group(1) if m else default).strip().lower()
    return next((v for k, v in _STATUS_MAP.items() if k in raw), default)


def _parse_authors(text: str) -> list[str]:
    m = _AUTHOR_RE.search(text)
    if not m:
        return []
    return [a.strip() for a in re.split(r"[,;]|\band\b", m.group(1)) if a.strip()]


def parse_tasks(text: str) -> list[dict[str, Any]]:
    """Parse a spec-kit ``tasks.md`` body into ordered task dicts.

    Returns ``[{"id": "T001"|None, "parallel": bool, "desc": str}, ...]`` in
    file order. Non-task lines (headings, prose, blank) are skipped. A ``[P]``
    marker anywhere at the head of the description flags a parallel task.
    """
    tasks: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.lstrip().startswith(("-", "*")):
            continue
        m = _TASK_RE.match(line)
        if not m:
            continue
        tid, parallel, desc = m.group(1), m.group(2), m.group(3)
        desc = desc.strip()
        if not desc:
            continue
        tasks.append({"id": tid, "parallel": bool(parallel), "desc": desc})
    return tasks


def parse_constitution_rules(text: str) -> list[str]:
    """Extract the governance principles from a ``constitution.md`` body.

    Spec Kit constitutions list principles as markdown bullets (often under a
    ``## Principles`` heading). We harvest every top-level bullet line as a
    Guardrail rule; if none are found, the whole body becomes a single rule so
    governance is never silently empty.
    """
    rules: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            rule = stripped[2:].strip()
            if rule:
                rules.append(rule)
    if not rules:
        collapsed = " ".join(t.strip() for t in text.splitlines() if t.strip())
        if collapsed:
            rules.append(collapsed)
    return rules


# ─── scan ────────────────────────────────────────────────────────────────────


@dataclass
class Artifact:
    """One ingested file: its ``.specify``-run-relative path + verbatim body."""

    rel: str          # path relative to the project root (e.g. "specs/001-x/spec.md")
    content: str      # verbatim file body — the byte source for export


@dataclass
class FeatureRun:
    slug: str
    dir_rel: str                       # "specs/001-taskify"
    spec: Artifact | None = None
    plan: Artifact | None = None
    tasks: Artifact | None = None
    references: list[tuple[str, Artifact]] = field(default_factory=list)  # (role, artifact)


@dataclass
class SpecifyScan:
    root: Path
    constitution: Artifact | None
    features: list[FeatureRun]


# Auxiliary Plan-attached artifacts (role → filename).
_REFERENCE_FILES = {
    "research": "research.md",
    "data-model": "data-model.md",
    "quickstart": "quickstart.md",
}


def _rel(root: Path, p: Path) -> str:
    return p.resolve().relative_to(root.resolve()).as_posix()


def _find_project_root(path: Path) -> Path:
    """Resolve the Spec Kit *project root* (the dir that holds ``.specify/``
    and/or ``specs/``) from whatever the user pointed at.

    Accepts: the project root, the ``.specify/`` dir itself, or a single
    ``specs/<feature>/`` run dir.
    """
    path = path.resolve()
    if path.name == ".specify":
        return path.parent
    # A feature run dir (contains spec.md/plan.md/tasks.md) whose parent is specs/
    if path.parent.name == "specs":
        return path.parent.parent
    return path


def scan_specify(path: Path) -> SpecifyScan:
    """Walk a Spec Kit tree and collect the constitution + every feature run."""
    path = path.resolve()
    if not path.is_dir():
        raise fail(f"path is not a directory: {path}")
    root = _find_project_root(path)

    # constitution.md — always at <root>/.specify/memory/constitution.md.
    constitution = None
    con_path = root / ".specify" / "memory" / "constitution.md"
    if con_path.is_file():
        constitution = Artifact(_rel(root, con_path), con_path.read_text(encoding="utf-8"))

    # Which feature dirs to ingest?
    feature_dirs: list[Path] = []
    if path.parent.name == "specs" and _looks_like_feature(path):
        feature_dirs = [path]                        # a single specs/<f>/ run
    else:
        specs_dir = root / "specs"
        if specs_dir.is_dir():
            feature_dirs = sorted(
                d for d in specs_dir.iterdir() if d.is_dir() and _looks_like_feature(d)
            )

    features = [_scan_feature(root, d) for d in feature_dirs]
    return SpecifyScan(root=root, constitution=constitution, features=features)


def _looks_like_feature(d: Path) -> bool:
    return any((d / f).is_file() for f in ("spec.md", "plan.md", "tasks.md"))


def _scan_feature(root: Path, d: Path) -> FeatureRun:
    run = FeatureRun(slug=_slugify(d.name), dir_rel=_rel(root, d))

    def _read(name: str) -> Artifact | None:
        p = d / name
        if p.is_file():
            return Artifact(_rel(root, p), p.read_text(encoding="utf-8"))
        return None

    run.spec = _read("spec.md")
    run.plan = _read("plan.md")
    run.tasks = _read("tasks.md")
    for role, fname in _REFERENCE_FILES.items():
        art = _read(fname)
        if art is not None:
            run.references.append((role, art))
    contracts = d / "contracts"
    if contracts.is_dir():
        for cf in sorted(contracts.rglob("*")):
            if cf.is_file():
                run.references.append(
                    ("contract", Artifact(_rel(root, cf), cf.read_text(encoding="utf-8")))
                )
    return run


# ─── mapping plan (pure) ─────────────────────────────────────────────────────


@dataclass
class DocWrite:
    """One planned ``kernel.write_document`` call plus export metadata."""

    kind: str
    name: str
    spec: dict[str, Any]
    api_version: str = SDLC_API_VERSION
    source: str | None = None       # .specify-relative path this doc mirrors
    body_field: str | None = None   # spec field holding the verbatim body
    export_source: bool = False     # True → this doc is the byte-source for `source`
    detail: str = ""                # human one-liner for dry-run

    def raw(self) -> dict[str, Any]:
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": {"name": self.name},
            "spec": self.spec,
        }


@dataclass
class FeaturePlan:
    slug: str
    feature_name: str
    reuse_feature: bool
    writes: list[DocWrite]
    workflow_events: list[DocWrite]


def _constitution_name(scan: SpecifyScan) -> str:
    return "speckit-constitution"


def build_feature_plan(
    scan: SpecifyScan,
    run: FeatureRun,
    *,
    feature_override: str | None,
    constitution_as: str,
) -> FeaturePlan:
    """Compute every DocWrite for one feature run (ADR §4). Pure — no I/O."""
    slug = run.slug
    feature_name = feature_override or f"f-{slug}"
    writes: list[DocWrite] = []
    manifest_files: list[dict[str, str]] = []
    produces_plan: list[dict[str, Any]] = []   # Plan.produces[] entries
    story_names: list[str] = []

    # constitution → Guardrail (+ Soul), per --constitution-as. The Soul holds
    # the verbatim body (byte-source for export); the Guardrail is the live,
    # enforced governance projection (rules list).
    if scan.constitution is not None:
        cname = _constitution_name(scan)
        con = scan.constitution
        want_guard = constitution_as in ("guardrail", "both")
        want_soul = constitution_as in ("soul", "both")
        if want_soul:
            writes.append(DocWrite(
                kind="Soul", name=cname, api_version=SOUL_API_VERSION,
                spec={"soul_content": con.content, "origin": con.rel, "pattern": METHODOLOGY},
                source=con.rel, body_field="soul_content", export_source=True,
                detail="constitution.md → Soul (identity/voice; verbatim byte-source)",
            ))
        writes.append(DocWrite(
            kind="Guardrail", name=cname, api_version=CORE_API_VERSION,
            spec={
                "rules": parse_constitution_rules(con.content),
                "instruction": con.content,
                "severity": "warn", "scope": "both",
                "origin": con.rel, "pattern": METHODOLOGY,
            },
            source=con.rel, body_field="instruction",
            # Soul is the export byte-source when present; else the Guardrail is.
            export_source=not want_soul,
            detail="constitution.md → Guardrail (live, enforced governance)",
        ))
        manifest_files.append({
            "path": con.rel, "kind": "Soul" if want_soul else "Guardrail",
            "name": cname, "body_field": "soul_content" if want_soul else "instruction",
        })

    # spec.md → Spec (pattern=spec-kit)
    spec_doc_name: str | None = None
    if run.spec is not None:
        spec_doc_name = f"speckit-{slug}"
        art = run.spec
        writes.append(DocWrite(
            kind="Spec", name=spec_doc_name,
            spec={
                "title": _first_title(art.content, slug.replace("-", " ").title()),
                "date": _today(),
                "status": _parse_status(art.content),
                "pattern": METHODOLOGY,
                "body": art.content,
                "origin": art.rel,
                **({"authors": _parse_authors(art.content)} if _parse_authors(art.content) else {}),
            },
            source=art.rel, body_field="body", export_source=True,
            detail="spec.md → Spec (pattern=spec-kit)",
        ))
        manifest_files.append({"path": art.rel, "kind": "Spec", "name": spec_doc_name, "body_field": "body"})

    # research/data-model/quickstart/contracts → Reference (verbatim) via Plan.produces[]
    ref_counters: dict[str, int] = {}
    for role, art in run.references:
        base = f"speckit-{slug}-{role}"
        # contracts/ may have several files → suffix with the file stem.
        if role == "contract":
            stem = _slugify(Path(art.rel).stem)
            ref_name = f"speckit-{slug}-contract-{stem}"
        else:
            ref_counters[role] = ref_counters.get(role, 0) + 1
            ref_name = base if ref_counters[role] == 1 else f"{base}-{ref_counters[role]}"
        writes.append(DocWrite(
            kind="Reference", name=ref_name,
            spec={
                "title": _first_title(art.content, f"{slug} {role}"),
                "kind_of": "internal-doc",
                "summary": f"Spec Kit {role} artifact for {slug} ({Path(art.rel).name}).",
                "body": art.content,
                "origin": art.rel,
                "tags": [METHODOLOGY, role],
            },
            source=art.rel, body_field="body", export_source=True,
            detail=f"{Path(art.rel).name} → Reference (role={role})",
        ))
        produces_plan.append({"kind": "Reference", "name": ref_name, "role": role})
        manifest_files.append({"path": art.rel, "kind": "Reference", "name": ref_name, "body_field": "body"})

    # plan.md → Plan (methodology=spec-kit), links Spec + carries produces[]
    if run.plan is not None:
        plan_doc_name = f"speckit-{slug}"
        art = run.plan
        plan_spec: dict[str, Any] = {
            "title": _first_title(art.content, f"{slug} plan"),
            "date": _today(),
            "status": _parse_status(art.content),
            "pattern": METHODOLOGY,
            "methodology": METHODOLOGY,
            "body": art.content,
            "origin": art.rel,
        }
        if spec_doc_name:
            plan_spec["spec_ref"] = spec_doc_name
        if produces_plan:
            plan_spec["produces"] = produces_plan
        writes.append(DocWrite(
            kind="Plan", name=plan_doc_name,
            spec=plan_spec, source=art.rel, body_field="body", export_source=True,
            detail="plan.md → Plan (methodology=spec-kit)",
        ))
        manifest_files.append({"path": art.rel, "kind": "Plan", "name": plan_doc_name, "body_field": "body"})

    # tasks.md → one Story per task (under the Feature) + a verbatim tasks
    # Reference (the byte-source for export; Stories are the tracking view).
    feature_produces: list[dict[str, Any]] = []
    if run.tasks is not None:
        art = run.tasks
        tasks = parse_tasks(art.content)
        for i, t in enumerate(tasks, start=1):
            tid = (t["id"] or f"t{i:03d}").lower()
            story_name = f"s-speckit-{slug}-{tid}"
            labels = [METHODOLOGY] + (["parallel"] if t["parallel"] else [])
            story_spec: dict[str, Any] = {
                "description": t["desc"],
                "title": t["desc"][:80],
                "status": "todo",
                "feature": feature_name,
                "labels": labels,
                "reporter": "claude-code",
            }
            if spec_doc_name:
                story_spec["spec_refs"] = [spec_doc_name]
            writes.append(DocWrite(
                kind="Story", name=story_name, spec=story_spec,
                detail=f"task {t['id'] or i} → Story {story_name}"
                       + (" [parallel]" if t["parallel"] else ""),
            ))
            story_names.append(story_name)
        # verbatim tasks.md — byte-source for export
        tasks_ref = f"speckit-{slug}-tasks"
        writes.append(DocWrite(
            kind="Reference", name=tasks_ref,
            spec={
                "title": _first_title(art.content, f"{slug} tasks"),
                "kind_of": "internal-doc",
                "summary": f"Spec Kit tasks.md for {slug} ({len(tasks)} tasks).",
                "body": art.content, "origin": art.rel, "tags": [METHODOLOGY, "tasks"],
            },
            source=art.rel, body_field="body", export_source=True,
            detail="tasks.md → Reference (verbatim byte-source)",
        ))
        feature_produces.append({"kind": "Reference", "name": tasks_ref, "role": "tasks"})
        manifest_files.append({"path": art.rel, "kind": "Reference", "name": tasks_ref, "body_field": "body"})

    # the specs/<f>/ dir itself → Feature hub, carrying the export manifest.
    feature_spec: dict[str, Any] = {
        "description": f"Spec Kit run: {slug} (imported from {run.dir_rel}).",
        "status": "in-development",
        "labels": [METHODOLOGY],
        "reporter": "claude-code",
        "stories": story_names,
        "specify_run": {
            "feature_dir": run.dir_rel,
            "slug": slug,
            "files": manifest_files,
        },
    }
    if feature_produces:
        feature_spec["produces"] = feature_produces
    writes.append(DocWrite(
        kind="Feature", name=feature_name, spec=feature_spec,
        detail=f"specs/{slug}/ → Feature {feature_name} (hub + export manifest)",
    ))

    # WorkflowEvent journey overlay (methodology=spec-kit, .specify/ trail).
    workflow_events = _build_workflow_events(
        run, feature_name=feature_name, spec_doc=spec_doc_name,
        plan_doc=(f"speckit-{slug}" if run.plan else None),
    )

    return FeaturePlan(
        slug=slug, feature_name=feature_name,
        reuse_feature=bool(feature_override),
        writes=writes, workflow_events=workflow_events,
    )


def _build_workflow_events(
    run: FeatureRun, *, feature_name: str, spec_doc: str | None, plan_doc: str | None,
) -> list[DocWrite]:
    """One WorkflowEvent per phase present in the run, forming a linked list.

    parent_ref = Feature/<name>; methodology = spec-kit; methodology_artifact =
    the ``.specify/`` path. The derived journey lights from the Spec/Plan/Story
    refs; this overlay renders the honest badge + per-phase artifact trail.
    """
    parent_ref = f"Feature/{feature_name}"
    now = _now_iso()
    phases: list[tuple[str, str | None, str | None]] = []
    if run.spec is not None:
        phases.append(("specify", f"Spec/{spec_doc}" if spec_doc else None, run.spec.rel))
    if run.plan is not None:
        phases.append(("plan", f"Plan/{plan_doc}" if plan_doc else None, run.plan.rel))
    if run.tasks is not None:
        phases.append(("build", parent_ref, run.tasks.rel))

    events: list[DocWrite] = []
    prev_name: str | None = None
    for idx, (phase, ref, artifact) in enumerate(phases):
        name = f"{feature_name}-{phase}-speckit-{idx + 1}".replace("/", "-").lower()
        spec: dict[str, Any] = {
            "phase": phase,
            "parent_ref": parent_ref,
            "methodology": METHODOLOGY,
            "actor": "claude-code",
            "started_at": now,
            "created_at": now,
        }
        if ref:
            spec["ref"] = ref
        if artifact:
            spec["methodology_artifact"] = artifact
        if prev_name:
            spec["transitioned_from"] = prev_name
        events.append(DocWrite(kind="WorkflowEvent", name=name, spec=spec, detail=f"journey {phase} → {artifact}"))
        prev_name = name
    return events


# ─── date helpers ────────────────────────────────────────────────────────────


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─── CLI group ───────────────────────────────────────────────────────────────


@click.group("specify", help="Bidirectional GitHub Spec Kit ↔ DNA bridge (import / export).")
def specify() -> None:
    """The ``.specify/`` ↔ DNA Kinds bridge.

    \b
      dna specify import .specify/            # ingest the whole toolkit + runs
      dna specify import specs/001-taskify/   # ingest one feature run
      dna specify import . --dry-run --json   # preview the mapping, write nothing
      dna specify export f-taskify --out .    # project Kinds back to .specify/
    """


def _scope_opt(f):  # small local decorator, mirrors sdlc's --scope
    return click.option("--scope", default=None, help="Scope to write into (default: env / sole scope).")(f)


@specify.command("import")
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@click.option("--feature", "feature_override", default=None,
              help="Attach the run(s) to this existing Feature instead of creating f-<slug>.")
@click.option("--constitution-as", "constitution_as",
              type=click.Choice(["guardrail", "soul", "both"]), default="both", show_default=True,
              help="Map constitution.md to a Guardrail, a Soul, or both.")
@click.option("--dry-run", is_flag=True, help="Preview the full artifact→Kind mapping; write nothing.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable mapping output.")
@_scope_opt
def import_(path, feature_override, constitution_as, dry_run, as_json, scope) -> None:
    """Ingest a Spec Kit ``.specify/`` toolkit (or one ``specs/<feature>/`` run)
    into durable DNA Kinds (ADR §4). Every write goes through
    ``kernel.write_document`` so all guards fire."""
    scan = scan_specify(Path(path))
    if not scan.features and scan.constitution is None:
        raise fail(f"no Spec Kit artifacts found under {path} "
                   f"(looked for .specify/memory/constitution.md and specs/<f>/spec.md)")

    plans = [
        build_feature_plan(scan, run, feature_override=feature_override,
                           constitution_as=constitution_as)
        for run in scan.features
    ]
    # constitution-only import (no feature run) still writes the Guardrail/Soul.
    if not scan.features and scan.constitution is not None:
        plans = [_constitution_only_plan(scan, constitution_as)]

    if as_json:
        print_json(_plan_json(scan, plans, dry_run=dry_run))
        if dry_run:
            return
    elif dry_run:
        _print_dry_run(scan, plans)
        return

    written = _execute(plans, scope=scope)
    if not as_json:
        click.secho(
            f"\nImported Spec Kit run{'s' if len(scan.features) != 1 else ''}: "
            f"{written} documents across {len(plans)} feature(s).",
            fg="green", bold=True,
        )
        for p in plans:
            click.secho(f"  Feature/{p.feature_name}  ({p.slug})", fg="cyan")


def _constitution_only_plan(scan: SpecifyScan, constitution_as: str) -> FeaturePlan:
    dummy = FeatureRun(slug="constitution", dir_rel=".specify/memory")
    fp = build_feature_plan(scan, dummy, feature_override=None, constitution_as=constitution_as)
    # Drop the empty Feature/WorkflowEvent scaffolding — only the governance docs.
    fp.writes = [w for w in fp.writes if w.kind in ("Soul", "Guardrail")]
    fp.workflow_events = []
    return fp


def _execute(plans: list[FeaturePlan], *, scope: str | None) -> int:
    written = 0
    with dna_session(scope) as s:
        existing_features = {f.name for f in s.query_list("Feature")}
        for p in plans:
            for w in p.writes:
                if w.kind == "Feature" and p.reuse_feature and w.name in existing_features:
                    # Reuse: merge stories/produces/specify_run into the existing Feature.
                    _merge_feature(s, scope, w)
                    written += 1
                    continue
                s.run(s.kernel.write_document(scope, w.kind, w.name, w.raw()))
                written += 1
            for ev in p.workflow_events:
                s.run(s.kernel.write_document(scope, "WorkflowEvent", ev.name, ev.raw()))
                written += 1
    return written


def _merge_feature(s, scope: str | None, w: DocWrite) -> None:
    existing = s.get_doc("Feature", w.name)
    base = dict(existing.spec) if existing and isinstance(existing.spec, dict) else {}
    new = w.spec
    merged = {**base}
    merged["stories"] = sorted(set(base.get("stories", []) or []) | set(new.get("stories", []) or []))
    # produces: dedupe by (kind, name)
    seen = {(p.get("kind"), p.get("name")): p for p in (base.get("produces", []) or [])}
    for p in new.get("produces", []) or []:
        seen[(p.get("kind"), p.get("name"))] = p
    if seen:
        merged["produces"] = list(seen.values())
    merged["specify_run"] = new.get("specify_run", base.get("specify_run"))
    merged.setdefault("labels", base.get("labels", new.get("labels", [])))
    raw = {"apiVersion": SDLC_API_VERSION, "kind": "Feature", "metadata": {"name": w.name}, "spec": merged}
    s.run(s.kernel.write_document(scope, "Feature", w.name, raw))


# ─── dry-run / json rendering ────────────────────────────────────────────────


def _plan_json(scan: SpecifyScan, plans: list[FeaturePlan], *, dry_run: bool) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "root": str(scan.root),
        "constitution": scan.constitution.rel if scan.constitution else None,
        "features": [
            {
                "slug": p.slug,
                "feature": p.feature_name,
                "reuse_feature": p.reuse_feature,
                "documents": [
                    {"kind": w.kind, "name": w.name, "source": w.source,
                     "body_field": w.body_field, "detail": w.detail}
                    for w in p.writes
                ],
                "workflow_events": [
                    {"name": e.name, "phase": e.spec.get("phase"),
                     "methodology_artifact": e.spec.get("methodology_artifact")}
                    for e in p.workflow_events
                ],
            }
            for p in plans
        ],
    }


def _print_dry_run(scan: SpecifyScan, plans: list[FeaturePlan]) -> None:
    click.secho(f"Spec Kit → DNA mapping (dry-run) — root: {scan.root}", fg="cyan", bold=True)
    if scan.constitution:
        click.echo(f"  constitution: {scan.constitution.rel}")
    for p in plans:
        click.secho(f"\n▸ Feature/{p.feature_name}  (slug={p.slug})", fg="yellow", bold=True)
        for w in p.writes:
            click.echo(f"    {w.kind:11} {w.name:34} {w.detail}")
        for e in p.workflow_events:
            click.echo(f"    {'WorkflowEvent':11} {e.name:34} {e.detail}")
    total = sum(len(p.writes) + len(p.workflow_events) for p in plans)
    click.secho(f"\n{total} documents would be written (dry-run — nothing persisted).", fg="yellow")


# ─── export ──────────────────────────────────────────────────────────────────


@specify.command("export")
@click.argument("feature")
@click.option("--out", "out_dir", default=".", show_default=True,
              help="Directory to project the .specify/ tree into.")
@click.option("--force", is_flag=True, help="Overwrite existing files.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@_scope_opt
def export(feature, out_dir, force, as_json, scope) -> None:
    """Project a DNA-stored Spec Kit run back to a byte-faithful ``.specify/`` tree.

    Reads the Feature's ``spec.specify_run`` manifest (written at import time)
    and replays each mapped doc's verbatim body to its original path. Round-trip
    (``import`` then ``export``) reproduces the source ``.specify/`` byte-for-byte.
    """
    out = Path(out_dir).resolve()
    projected: list[str] = []
    with dna_session(scope) as s:
        feat = s.get_doc("Feature", feature)
        if feat is None:
            raise fail(f"Feature/{feature} not found in scope {s.scope}")
        run = (feat.spec or {}).get("specify_run")
        if not run or not run.get("files"):
            raise fail(f"Feature/{feature} has no specify_run manifest — not a Spec Kit import.")
        for entry in run["files"]:
            body = _load_body(s, entry["kind"], entry["name"], entry["body_field"])
            if body is None:
                raise fail(f"missing export source {entry['kind']}/{entry['name']} "
                           f"for {entry['path']}")
            dest = out / entry["path"]
            if dest.exists() and not force:
                raise fail(f"refusing to overwrite {dest} (use --force)")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body, encoding="utf-8")
            projected.append(entry["path"])

    if as_json:
        print_json({"feature": feature, "out": str(out), "files": projected})
        return
    click.secho(f"Projected Feature/{feature} → {out} ({len(projected)} files):", fg="green", bold=True)
    for f in projected:
        click.echo(f"  {f}")


def _load_body(s, kind: str, name: str, body_field: str) -> str | None:
    doc = s.get_doc(kind, name)
    if doc is None:
        return None
    spec = doc.spec if isinstance(doc.spec, dict) else {}
    val = spec.get(body_field)
    return val if isinstance(val, str) else None
