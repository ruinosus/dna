"""``dna specify install-templates`` / ``export-templates`` — the **Layer 3**
Spec Kit *toolkit* bridge (ADR ``ADR-spec-kit-adoption`` §5, Layer 3).

Where ``dna specify import`` / ``export`` (#116) bridge a *run* — the
per-feature ``constitution/spec/plan/tasks`` output — Layer 3 bridges the
**toolkit itself**: the templates, the slash-command definitions, the shared
scripts, and the constitution. Once ingested they are durable, queryable Kinds
served LIVE over ``dna mcp serve`` (``list_templates`` / ``get_template`` /
``list_skills`` / ``get_skill``) and **overridable per scope/tenant** through the
kernel's existing overlay machinery — the spec-kit toolkit stops being a
per-repo pile of files and becomes versioned, governed, portable policy.

Mapping (ADR §4, extended to the toolkit):

    .specify/templates/*.md          → PromptTemplate  speckit-<stem>
    templates/commands/*.md          → Skill           speckit-<cmd>  (verbatim)
    (or projected .claude/commands/speckit.*.md)
    .specify/scripts/**              → Skill           speckit-scripts (bundle)
    .specify/memory/constitution.md  → Guardrail(+Soul) speckit-constitution

Every produced doc carries ``spec.origin`` = its ``.specify/``-relative source
path, so ``export-templates`` replays each body byte-for-byte back to disk —
``install-templates`` then ``export-templates`` reproduces the source toolkit
byte-identically (a round-trip acceptance test). No new Kinds: PromptTemplate,
Skill and Guardrail all pre-exist with TS twins, and Skill/PromptTemplate are in
``DEFAULT_INHERITABLE_KINDS_V1`` — so the per-scope/tenant override is free.

The scan/parse helpers are reused from ``specify_cmd`` so the untrusted-input
defenses never fork.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
import yaml

from dna_cli._ctx import dna_session, fail, print_json
from dna_cli.specify_cmd import (
    CORE_API_VERSION,
    METHODOLOGY,
    SDLC_API_VERSION,
    SOUL_API_VERSION,
    Artifact,
    _find_project_root,
    _first_title,
    _rel,
    parse_constitution_rules,
)

SKILL_API_VERSION = "agentskills.io/v1"
PROMPT_API_VERSION = SDLC_API_VERSION  # PromptTemplate targets the sdlc api

#: Non-template subdirs under .specify/templates/ that are NOT prompt templates.
_NON_TEMPLATE_DIRS = {"commands", "overrides", "presets", "extensions"}

#: Where slash-command definitions live, in resolution order. The first that
#: exists (and holds command markdown) wins; ``--commands-from`` overrides all.
_COMMAND_DIRS = (
    ".specify/templates/commands",     # spec-kit toolkit source
    ".claude/commands",                # projected Claude commands
    ".github/prompts",                 # projected Copilot prompts
    ".cursor/commands",                # projected Cursor commands
    ".opencode/command",               # projected opencode commands
)


# ─── frontmatter split (byte-faithful) ───────────────────────────────────────

_FM_RE = re.compile(r"^(---\n.*?\n---\n?)(.*)$", re.DOTALL)


def split_frontmatter(content: str) -> tuple[dict[str, Any], str, str]:
    """Split a markdown doc into ``(metadata, frontmatter_block, body)``.

    ``frontmatter_block`` is the verbatim ``---\\n…\\n---\\n`` prefix (empty when
    absent); ``body`` is the exact remainder. ``frontmatter_block + body`` always
    reconstructs the input byte-for-byte.
    """
    m = _FM_RE.match(content)
    if not m:
        return {}, "", content
    block, body = m.group(1), m.group(2)
    inner = block
    # strip the leading/trailing --- fences for the yaml parse
    inner = re.sub(r"^---\n", "", inner)
    inner = re.sub(r"\n?---\n?$", "", inner)
    try:
        meta = yaml.safe_load(inner) or {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception:  # noqa: BLE001 — malformed frontmatter → no metadata
        meta = {}
    return meta, block, body


# ─── scan ─────────────────────────────────────────────────────────────────────


@dataclass
class ToolkitScan:
    root: Path
    templates: list[Artifact] = field(default_factory=list)
    commands: list[Artifact] = field(default_factory=list)
    scripts: list[Artifact] = field(default_factory=list)   # rel under .specify/scripts kept in .rel
    constitution: Artifact | None = None
    commands_dir_rel: str | None = None

    @staticmethod
    def command_name(art: Artifact) -> str:
        """`specify.md` → `specify`; `speckit.specify.md` → `specify`."""
        stem = Path(art.rel).name
        stem = re.sub(r"\.md$", "", stem)
        stem = re.sub(r"^speckit\.", "", stem)
        return stem


def _read(root: Path, p: Path) -> Artifact:
    return Artifact(_rel(root, p), p.read_text(encoding="utf-8"))


def scan_toolkit(path: Path, *, commands_from: str | None = None) -> ToolkitScan:
    """Walk a Spec Kit tree and collect the toolkit (templates + commands +
    scripts + constitution). Accepts the project root or the ``.specify/`` dir."""
    path = path.resolve()
    if not path.is_dir():
        raise fail(f"path is not a directory: {path}")
    root = _find_project_root(path)
    scan = ToolkitScan(root=root)

    # templates: top-level *.md under .specify/templates/ (skip command/override dirs)
    tdir = root / ".specify" / "templates"
    if tdir.is_dir():
        for p in sorted(tdir.glob("*.md")):
            if p.is_file():
                scan.templates.append(_read(root, p))

    # slash-command definitions
    cmd_dir: Path | None = None
    if commands_from:
        cmd_dir = (root / commands_from) if not Path(commands_from).is_absolute() else Path(commands_from)
        if not cmd_dir.is_dir():
            raise fail(f"--commands-from directory not found: {cmd_dir}")
    else:
        for rel in _COMMAND_DIRS:
            cand = root / rel
            if cand.is_dir() and any(cand.glob("*.md")):
                cmd_dir = cand
                break
    if cmd_dir is not None:
        scan.commands_dir_rel = _rel(root, cmd_dir)
        for p in sorted(cmd_dir.glob("*.md")):
            name = p.name
            # In a projected agent dir, only pick spec-kit's own commands.
            if scan.commands_dir_rel != ".specify/templates/commands" and not name.startswith("speckit."):
                continue
            if p.is_file():
                scan.commands.append(_read(root, p))

    # scripts: the whole .specify/scripts/ tree, verbatim (text files only)
    sdir = root / ".specify" / "scripts"
    if sdir.is_dir():
        for p in sorted(sdir.rglob("*")):
            if p.is_file():
                try:
                    scan.scripts.append(_read(root, p))
                except (UnicodeDecodeError, ValueError):
                    continue  # skip binaries

    # constitution
    con = root / ".specify" / "memory" / "constitution.md"
    if con.is_file():
        scan.constitution = _read(root, con)

    return scan


# ─── mapping plan (pure) ──────────────────────────────────────────────────────


@dataclass
class ToolkitWrite:
    """One planned ``kernel.write_document`` for a toolkit artifact."""

    kind: str
    name: str
    spec: dict[str, Any]
    api_version: str
    metadata: dict[str, Any] = field(default_factory=dict)
    detail: str = ""

    def raw(self) -> dict[str, Any]:
        meta = {"name": self.name, **self.metadata}
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": meta,
            "spec": self.spec,
        }


def build_toolkit_plan(scan: ToolkitScan, *, constitution_as: str) -> list[ToolkitWrite]:
    """Compute every write for a toolkit ingest (pure — no I/O)."""
    writes: list[ToolkitWrite] = []

    # templates → PromptTemplate (body verbatim, byte-source for export)
    for art in scan.templates:
        stem = re.sub(r"\.md$", "", Path(art.rel).name)
        title = _first_title(art.content, stem.replace("-", " ").title())
        writes.append(ToolkitWrite(
            kind="PromptTemplate", name=f"speckit-{stem}",
            api_version=PROMPT_API_VERSION,
            spec={
                "body": art.content,
                "description": f"Spec Kit {stem} (served by DNA).",
                "tags": [METHODOLOGY],
                "origin": art.rel,
                "pattern": METHODOLOGY,
            },
            detail=f"{Path(art.rel).name} → PromptTemplate speckit-{stem}",
        ))

    # slash-commands → Skill (FULL verbatim file = the command definition; the
    # frontmatter `scripts:` block is part of the contract, so the whole file is
    # the served instruction. metadata.description is harvested for listing.)
    for art in scan.commands:
        cmd = ToolkitScan.command_name(art)
        meta_fm, _block, _body = split_frontmatter(art.content)
        description = str(meta_fm.get("description") or f"Spec Kit /{cmd} command.")
        # origin lives in METADATA (frontmatter round-trips through the SKILL.md
        # bundle; unknown *spec* fields are dropped by the typed SkillWriter).
        writes.append(ToolkitWrite(
            kind="Skill", name=f"speckit-{cmd}",
            api_version=SKILL_API_VERSION,
            metadata={"description": description, "pattern": METHODOLOGY,
                      "tags": [METHODOLOGY, "slash-command"], "origin": art.rel},
            spec={"instruction": art.content},
            detail=f"{Path(art.rel).name} → Skill speckit-{cmd}",
        ))

    # scripts → ONE Skill bundle (scripts/ subdir = whole tree, verbatim)
    if scan.scripts:
        prefix = ".specify/scripts/"
        files = {a.rel[len(prefix):]: a.content for a in scan.scripts if a.rel.startswith(prefix)}
        writes.append(ToolkitWrite(
            kind="Skill", name="speckit-scripts",
            api_version=SKILL_API_VERSION,
            metadata={"description": "Spec Kit helper scripts (bash + powershell).",
                      "pattern": METHODOLOGY, "tags": [METHODOLOGY, "scripts"],
                      "origin": ".specify/scripts"},
            spec={
                "instruction": (
                    "Spec Kit workflow scripts, served by DNA. The slash-command "
                    "Skills reference these by path (e.g. `scripts/bash/"
                    "create-new-feature.sh`)."
                ),
                "scripts": files,
            },
            detail=f".specify/scripts/ → Skill speckit-scripts ({len(files)} files)",
        ))

    # constitution → PromptTemplate (servable/overridable + byte-faithful export
    # source; a record-plane Kind preserves origin+body verbatim, unlike the
    # bundle-stored Guardrail) + Guardrail (live governance) + optional Soul.
    if scan.constitution is not None:
        con = scan.constitution
        writes.append(ToolkitWrite(
            kind="PromptTemplate", name="speckit-constitution-template",
            api_version=PROMPT_API_VERSION,
            spec={
                "body": con.content,
                "description": "Spec Kit constitution — servable, overridable governance template.",
                "tags": [METHODOLOGY, "constitution"],
                "origin": con.rel,
                "pattern": METHODOLOGY,
            },
            detail="constitution.md → PromptTemplate (servable/overridable; byte-source)",
        ))
        want_guard = constitution_as in ("guardrail", "both")
        want_soul = constitution_as in ("soul", "both")
        # NB: no ``origin`` on the Soul/Guardrail — the PromptTemplate above is
        # the single byte-source for constitution.md on export; these are the
        # identity + live-governance projections.
        if want_soul:
            writes.append(ToolkitWrite(
                kind="Soul", name="speckit-constitution",
                api_version=SOUL_API_VERSION,
                spec={"soul_content": con.content, "pattern": METHODOLOGY},
                detail="constitution.md → Soul (identity/voice)",
            ))
        if want_guard:
            writes.append(ToolkitWrite(
                kind="Guardrail", name="speckit-constitution",
                api_version=CORE_API_VERSION,
                spec={
                    "rules": parse_constitution_rules(con.content),
                    "instruction": con.content,
                    "severity": "warn", "scope": "both",
                    "pattern": METHODOLOGY,
                },
                detail="constitution.md → Guardrail (live, enforced governance)",
            ))

    return writes


# ─── execution ────────────────────────────────────────────────────────────────


def _execute(writes: list[ToolkitWrite], *, scope: str | None) -> int:
    written = 0
    with dna_session(scope) as s:
        for w in writes:
            s.run(s.kernel.write_document(scope, w.kind, w.name, w.raw()))
            written += 1
    return written


# ─── CLI: install-templates ───────────────────────────────────────────────────


def _plan_json(scan: ToolkitScan, writes: list[ToolkitWrite], *, dry_run: bool) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "root": str(scan.root),
        "documents": [
            {"kind": w.kind, "name": w.name, "origin": w.spec.get("origin"),
             "detail": w.detail}
            for w in writes
        ],
    }


@click.command("install-templates")
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@click.option("--constitution-as", "constitution_as",
              type=click.Choice(["guardrail", "soul", "both"]), default="both",
              show_default=True, help="Map constitution.md to a Guardrail, a Soul, or both.")
@click.option("--commands-from", default=None,
              help="Directory of slash-command markdown (default: auto-detect "
                   ".specify/templates/commands or a projected agent dir).")
@click.option("--dry-run", is_flag=True, help="Preview the toolkit→Kind mapping; write nothing.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable mapping output.")
@click.option("--scope", default=None, help="Scope to write into (default: env / sole scope).")
def install_templates(path, constitution_as, commands_from, dry_run, as_json, scope) -> None:
    """Ingest a Spec Kit **toolkit** (``.specify/templates/`` + slash-commands +
    ``.specify/scripts/`` + constitution) into durable, servable DNA Kinds
    (ADR §5, Layer 3). Served live over ``dna mcp serve`` and overridable per
    scope/tenant. Every write goes through ``kernel.write_document``."""
    scan = scan_toolkit(Path(path), commands_from=commands_from)
    writes = build_toolkit_plan(scan, constitution_as=constitution_as)
    if not writes:
        raise fail(
            f"no Spec Kit toolkit found under {path} (looked for "
            f".specify/templates/, slash-commands, .specify/scripts/, "
            f".specify/memory/constitution.md)"
        )

    if as_json:
        print_json(_plan_json(scan, writes, dry_run=dry_run))
        if dry_run:
            return
    elif dry_run:
        click.secho(f"Spec Kit toolkit → DNA (dry-run) — root: {scan.root}", fg="cyan", bold=True)
        for w in writes:
            click.echo(f"    {w.kind:14} {w.name:30} {w.detail}")
        click.secho(f"\n{len(writes)} documents would be written (dry-run).", fg="yellow")
        return

    written = _execute(writes, scope=scope)
    if not as_json:
        click.secho(f"\nInstalled Spec Kit toolkit: {written} Kinds.", fg="green", bold=True)
        for w in writes:
            click.secho(f"  {w.kind}/{w.name}", fg="cyan")


# ─── CLI: export-templates ────────────────────────────────────────────────────

#: kind → the spec field carrying the verbatim single-file body for export.
_BODY_FIELD = {"PromptTemplate": "body", "Skill": "instruction", "Guardrail": "instruction"}


@click.command("export-templates")
@click.option("--out", "out_dir", default=".", show_default=True,
              help="Directory to project the .specify/ toolkit into.")
@click.option("--force", is_flag=True, help="Overwrite existing files.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@click.option("--scope", default=None, help="Scope to read from (default: env / sole scope).")
def export_templates(out_dir, force, as_json, scope) -> None:
    """Project the DNA-stored Spec Kit toolkit back to a byte-faithful
    ``.specify/`` tree — the inverse of ``install-templates``. Reads every
    ``speckit-*`` PromptTemplate/Skill/Guardrail carrying a ``spec.origin`` and
    replays its verbatim body to that path (round-trips byte-for-byte)."""
    out = Path(out_dir).resolve()
    projected: list[str] = []

    def _write(rel: str, body: str) -> None:
        dest = out / rel
        if dest.exists() and not force:
            raise fail(f"refusing to overwrite {dest} (use --force)")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        projected.append(rel)

    with dna_session(scope) as s:
        for kind in ("PromptTemplate", "Skill", "Guardrail"):
            for doc in s.query_list(kind):
                name = getattr(doc, "name", None) or (getattr(doc, "metadata", {}) or {}).get("name")
                if not name or not str(name).startswith("speckit-"):
                    continue
                # Read the RAW stored doc — typed Kinds (Skill/Guardrail)
                # normalize their spec on parse and drop the ``origin``/verbatim
                # fields the export replays. The source persisted the raw dict.
                raw = s.run(s.kernel.get_document(s.scope, kind, name))
                spec = (raw or {}).get("spec") if isinstance(raw, dict) else None
                if not isinstance(spec, dict):
                    continue
                meta = (raw or {}).get("metadata") if isinstance(raw, dict) else None
                meta = meta if isinstance(meta, dict) else {}
                # origin lives in spec for record-plane Kinds (PromptTemplate) and
                # in metadata for bundle Kinds (Skill, whose SKILL.md frontmatter
                # is the only field that round-trips).
                origin = spec.get("origin") or meta.get("origin")
                if not origin:
                    continue
                # scripts bundle: origin is a DIR; replay each script file.
                scripts = spec.get("scripts")
                if kind == "Skill" and isinstance(scripts, dict) and scripts:
                    for rel, content in scripts.items():
                        _write(f"{origin}/{rel}", content)
                    continue
                body = spec.get(_BODY_FIELD[kind])
                if isinstance(body, str):
                    _write(origin, body)

    if as_json:
        print_json({"out": str(out), "files": sorted(projected)})
        return
    click.secho(f"Projected Spec Kit toolkit → {out} ({len(projected)} files):",
                fg="green", bold=True)
    for f in sorted(projected):
        click.echo(f"  {f}")
