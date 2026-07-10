"""``dna init`` — agent-ready onboarding for a consumer project.

``pip install dna-sdk dna-cli`` delivers a working kernel + CLI, but the
project's AI agent arrives blind: the SDLC skill, the AGENTS.md conventions
and the git hooks live in the DNA repo, not in the packages. ``dna init``
closes that gap with one command, and it does so the DNA way — the
onboarding assets travel as **Kinds inside an embedded onboarding scope**
(package-data at ``dna_cli/data/onboarding-scope/``) and are materialized
by the SDK's own market readers/writers, not by copying text templates:

  1. **Board** — creates ``.dna/<scope>/`` with a Genome written through
     ``kernel.write_document`` (the same scope-bootstrap ``dna install``
     performs; every write guard runs).
  2. **Skill** — reads the embedded ``skills/dna-sdlc-cli`` bundle with the
     ``agentskills-skill`` reader ONCE and projects it with the
     byte-faithful SkillWriter into the skill directory of each selected
     tool (``--tools``). The agentskills.io SKILL.md format is identical
     across ~40 tools — only the directory differs (see ``TOOL_SKILL_DIRS``);
     the Kind is the source of truth, the projections are regenerable.
  3. **AGENTS.md** — the CANONICAL instruction surface (agents.md/v1 —
     Linux Foundation stewardship, 28+ tools read it, Claude Code
     included): read with the ``agentsmd-agent`` reader, written to the
     project root with the AgentDefinitionWriter (the generated file
     parses back with the same reader — market fidelity on the front
     door). No per-tool instruction files are generated; a thin
     CLAUDE.md/GEMINI.md pointer is the user's optional call.
  4. **Git hooks** — wires ``core.hooksPath`` at the repo's versioned
     hooks dir (same semantics as ``dna sdlc hooks install``); skipped
     with a note when the directory is not a git repository.

``--from <uri>`` (i-015) swaps the EMBEDDED onboarding assets for a
distributed **onboarding pack** — a repository subtree carrying your
team's own Skill bundle(s) and (optionally) an AGENTS.md. The fetch and
the untrusted-input validation are the exact machinery of ``dna install``
(``install_cmd._fetch`` / ``_scan_tree`` / ``_validate_doc`` — one code
path, the defenses can never drift); only the DESTINATION differs:
``dna install`` writes documents into the ``.dna/`` source, ``dna init
--from`` PROJECTS Kinds into tool directories. The two compose: run
``dna install <uri>`` with the same ref when you also want the pack's
docs on the board.

SECURITY (``--from``) — pack content is UNTRUSTED DATA: only registered
Kinds pass, each ``spec`` is schema-validated before any projection,
document names must be plain slugs (path-shaped names never reach the
projection paths), and a Genome in the pack is ignored (a pack never
redefines the board scope). The residual risk is inherent to the
artifact: a Skill IS agent instructions — installing a third-party pack
is installing a dependency, and the summary says so ("review before
committing").

Design evidence: Research/rsh-cross-tool-agent-standards (dna-development
board) — the cross-tool adoption facts behind the multi-tool projection.

Idempotent by default: an existing file is never overwritten without
``--force``, and the summary says exactly what was created vs skipped.
"""
from __future__ import annotations

import asyncio
import re
import stat
from dataclasses import dataclass, field
from importlib.resources import files as _pkg_files
from pathlib import Path

import click

from dna_cli._ctx import build_source_from_env, fail, print_json

SKILL_NAME = "dna-sdlc-cli"

#: The (apiVersion, kind) pairs `dna init` knows how to PROJECT. Everything
#: else a pack may carry is board content — `dna install`'s territory.
_SKILL_KEY = ("agentskills.io/v1", "Skill")
_AGENTS_KEY = ("agents.md/v1", "AgentDefinition")

#: Container dirs seeded (with .gitkeep) so the fresh board is recognized by
#: the CLI's sole-SDLC-scope autodetection (``_autodetect_sdlc_scope`` probes
#: for these) and survives a git clone before the first Story lands.
_BOARD_CONTAINERS = ("stories", "features", "issues")

#: Tool → skill-projection directory. The agentskills.io SKILL.md FORMAT is
#: identical across tools; only the discovery directory is tool-specific
#: (Research/rsh-cross-tool-agent-standards). One Skill Kind, N projections.
TOOL_SKILL_DIRS: dict[str, str] = {
    "claude": ".claude/skills",
    "copilot": ".github/skills",
    "cursor": ".cursor/skills",
    "opencode": ".opencode/skills",
}

#: Sensible default: Claude Code + GitHub Copilot cover the two biggest
#: agent populations; the rest are one ``--tools`` flag away.
DEFAULT_TOOLS = ("claude", "copilot")


def _parse_tools(value: str) -> list[str]:
    """Parse ``--tools`` into a validated, order-preserving tool list."""
    if value.strip().lower() == "all":
        return list(TOOL_SKILL_DIRS)
    tools: list[str] = []
    for part in value.split(","):
        tool = part.strip().lower()
        if not tool:
            continue
        if tool not in TOOL_SKILL_DIRS:
            raise fail(
                f"--tools: unknown tool {tool!r} — pick from "
                f"{', '.join(TOOL_SKILL_DIRS)} (or 'all')"
            )
        if tool not in tools:
            tools.append(tool)
    if not tools:
        raise fail("--tools: no tools selected")
    return tools

#: Step outcome labels used in the summary + --json payload.
_CREATED = "created"
_SKIPPED = "skipped"


def _onboarding_root() -> Path:
    """Root of the embedded onboarding scope shipped as package-data."""
    return Path(str(_pkg_files("dna_cli").joinpath("data/onboarding-scope")))


# ─── onboarding pack (embedded or --from) ─────────────────────────────


@dataclass
class OnboardingPack:
    """What `dna init` projects: skills + the AGENTS.md instruction surface.

    ``skills`` are raw ``agentskills.io/v1`` Skill docs (already validated
    when the pack is remote); ``agents_raw`` is the raw AgentDefinition or
    ``None`` (the caller falls back to the embedded one, with a note).
    ``label`` names the pack origin for the summary; ``notes`` carry
    per-document rejections/ignores so nothing disappears silently.
    """
    skills: list[dict]
    agents_raw: dict | None
    label: str
    remote: bool = False
    notes: list[str] = field(default_factory=list)


def _load_embedded_pack() -> OnboardingPack:
    """The onboarding scope shipped inside dna-cli (the default pack)."""
    from dna.extensions.agentskills import SkillReader
    from dna.extensions.agentsmd import AgentDefinitionReader
    from dna.kernel.bundle_handle import FilesystemBundleHandle

    root = _onboarding_root()
    skill = SkillReader().read(FilesystemBundleHandle(root / "skills" / SKILL_NAME))
    agents = AgentDefinitionReader().read(FilesystemBundleHandle(root))
    return OnboardingPack(skills=[skill], agents_raw=agents, label="embedded")


def _normalize_from_uri(value: str) -> str:
    """Accept ``github:``/``local:`` URIs plus a bare existing directory
    (sugar for ``local:<abspath>`` — the offline-friendly authoring loop)."""
    if value.startswith(("github:", "local:")):
        return value
    path = Path(value).expanduser()
    if path.is_dir():
        return f"local:{path.resolve()}"
    raise fail(
        f"--from {value!r}: not a github:owner/repo[/subdir][@ref] or "
        f"local:<path> URI, and not an existing directory either"
    )


def _load_pack_from(from_uri: str) -> OnboardingPack:
    """Fetch + validate a distributed onboarding pack (the i-015 channel).

    Reuses ``dna install``'s machinery verbatim — ``_fetch`` (GitHubResolver
    / local trees), ``_scan_tree`` (reader-driven walk) and ``_validate_doc``
    (the first defense against untrusted input: registered-Kind-only, JSON
    Schema, slug-only names). One deliberate difference from install's scan:
    the walk runs with the SkillReader only, and the pack root is probed for
    AGENTS.md separately — a reader that claims a directory stops the
    recursion there, so scanning with the agentsmd reader would let a
    root-level AGENTS.md hide the pack's skills.
    """
    from dna.extensions.agentsmd import AgentDefinitionReader
    from dna.extensions.agentskills import SkillReader
    from dna.kernel import Kernel
    from dna.kernel.bundle_handle import FilesystemBundleHandle
    from dna_cli.install_cmd import ScannedDoc, _fetch, _scan_tree, _validate_doc

    fetched = _fetch(_normalize_from_uri(from_uri))
    kernel = Kernel.auto()  # Kind registry only — no source is touched

    pack = OnboardingPack(
        skills=[], agents_raw=None, label=fetched.describe, remote=True,
    )
    seen: set[str] = set()
    scanned = _scan_tree(fetched.root, [SkillReader()])

    # The instruction surface: AGENTS.md at the pack ROOT (the agents.md
    # convention), read with the same reader the embedded path uses.
    agents_reader = AgentDefinitionReader()
    root_handle = FilesystemBundleHandle(fetched.root)
    if agents_reader.detect(root_handle):
        raw = agents_reader.read(root_handle)
        reason = _validate_doc(kernel, ScannedDoc(raw=raw, rel_path="AGENTS.md"))
        if reason:
            pack.notes.append(f"AGENTS.md: rejected — {reason}")
        else:
            pack.agents_raw = raw

    for sd in scanned:
        raw = sd.raw
        key = (str(raw.get("apiVersion", "")), str(raw.get("kind", "")))
        label = f"{sd.rel_path}"
        if key == _AGENTS_KEY:
            continue  # root AGENTS.md is the surface; bundles stay skills-only
        if key != _SKILL_KEY:
            kp = kernel.kind_port_for(key[1], api_version=key[0])
            if kp is not None and getattr(kp, "is_root", False):
                pack.notes.append(
                    f"{label}: Genome ignored — a pack never redefines the "
                    f"board scope"
                )
            else:
                pack.notes.append(
                    f"{label}: {key[1]} is not projectable by `dna init` — "
                    f"only Skill bundles + AGENTS.md are; `dna install` is "
                    f"the channel for board content"
                )
            continue
        reason = _validate_doc(kernel, sd)
        if reason:
            pack.notes.append(f"{label}: rejected — {reason}")
            continue
        name = str(raw["metadata"]["name"])
        if name in seen:
            pack.notes.append(
                f"{label}: duplicate skill {name!r} — the first one wins"
            )
            continue
        seen.add(name)
        pack.skills.append(raw)

    if not pack.skills:
        detail = "\n".join(f"  - {n}" for n in pack.notes) or "  (empty tree)"
        raise fail(
            f"no valid Skill found in {fetched.describe} — an onboarding "
            f"pack must carry at least one agentskills.io Skill bundle "
            f"(skills/<name>/SKILL.md).\n{detail}"
        )
    return pack


def _derive_scope(target: Path) -> str:
    """Default board-scope name: ``<dirname>-dev``, slugified.

    Follows the pilot precedent (repo ``foundry-assured`` → board scope
    ``foundry-dev``): the board is the *dev-time* SDLC scope, distinct
    from any runtime prompt scope the project may later add.
    """
    base = re.sub(r"[^a-z0-9]+", "-", target.resolve().name.lower()).strip("-")
    base = base or "project"
    return base if base.endswith("-dev") else f"{base}-dev"


def _board_exists(target: Path, scope: str) -> bool:
    """Same dual-marker contract as ``dna install`` / ``dna scope detect``."""
    scope_dir = target / ".dna" / scope
    return (scope_dir / "Genome.yaml").exists() or (scope_dir / "manifest.yaml").exists()


async def _bootstrap_board(target: Path, scope: str) -> None:
    """Create ``.dna/<scope>/`` with a Genome, written through the kernel.

    Mirrors the scope-bootstrap in ``install_cmd`` ("a scope is born from
    its Genome"): a full ``Kernel.auto()`` boot + ``write_document``, so
    schema validation and every write guard run — never a hand-rolled YAML
    dump. The source is pinned to ``<target>/.dna`` explicitly (NOT the
    ambient ``DNA_SOURCE_URL``), because ``--dir`` names the project being
    initialized, wherever the caller's env points.
    """
    from dna.kernel import Kernel

    kernel = Kernel.auto()
    source = await build_source_from_env(
        kernel, _source_url=f"file://{(target / '.dna').resolve()}"
    )
    kernel.source(source)
    await kernel.write_document(scope, "Genome", scope, {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {
            "name": scope,
            "description": (
                f"Dev-time SDLC board for {target.resolve().name} — "
                f"Features/Stories/Issues tracked via `dna sdlc`. "
                f"Created by `dna init`."
            ),
        },
        "spec": {},
    })
    # Seed the SDLC containers: `dna sdlc` autodetects the sole scope that
    # HAS them (adopter boards have arbitrary names — i-012), and a fresh
    # board must be detectable before its first Story. .gitkeep makes the
    # empty dirs survive a git clone.
    scope_dir = target / ".dna" / scope
    for container in _BOARD_CONTAINERS:
        d = scope_dir / container
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()


def _materialize_skills(
    target: Path, force: bool, tools: list[str], pack: OnboardingPack,
) -> list[tuple[str, str, str]]:
    """Skill Kind(s) → one projection per selected tool, via reader→writer.

    Each pack skill was parsed ONCE with the registered ``agentskills-skill``
    reader and is re-emitted with the byte-faithful SkillWriter into each
    tool's skill directory — the same round-trip machinery the
    market-conformance suites enforce. Returns one ``(step, outcome,
    relative path)`` per (skill, tool). The embedded pack keeps the historic
    ``skill[<tool>]`` step ids; a remote pack may carry several skills, so
    its step ids are ``skill[<tool>:<name>]`` (unique in ``--json``).
    """
    from dna.extensions.agentskills import SkillWriter
    from dna.kernel.bundle_handle import FilesystemBundleHandle

    writer = SkillWriter()
    results: list[tuple[str, str, str]] = []
    for raw in pack.skills:
        name = str(raw["metadata"]["name"])
        for tool in tools:
            step = f"skill[{tool}:{name}]" if pack.remote else f"skill[{tool}]"
            rel = f"{TOOL_SKILL_DIRS[tool]}/{name}"
            dest = target / TOOL_SKILL_DIRS[tool] / name
            if (dest / "SKILL.md").exists() and not force:
                results.append((step, _SKIPPED, rel))
                continue
            dest.mkdir(parents=True, exist_ok=True)
            writer.write(FilesystemBundleHandle(dest), raw)
            results.append((step, _CREATED, rel))
    return results


def _materialize_agents_md(
    target: Path, force: bool, pack: OnboardingPack,
) -> tuple[str, str]:
    """AgentDefinition Kind → ``<target>/AGENTS.md`` via reader→writer.

    A pack without an AGENTS.md falls back to the EMBEDDED one (with an
    explicit note): the project must still end up with the canonical
    instruction surface — a team distributing only a skill inherits the
    default conventions file rather than an agent-blind root.
    """
    from dna.extensions.agentsmd import AgentDefinitionReader, AgentDefinitionWriter
    from dna.kernel.bundle_handle import FilesystemBundleHandle

    detail = "AGENTS.md"
    raw = pack.agents_raw
    if raw is None:
        raw = AgentDefinitionReader().read(FilesystemBundleHandle(_onboarding_root()))
        detail = "AGENTS.md (embedded default — the pack ships none)"
    if (target / "AGENTS.md").exists() and not force:
        return _SKIPPED, detail
    AgentDefinitionWriter().write(FilesystemBundleHandle(target), raw)
    return _CREATED, detail


def _install_hooks(target: Path) -> tuple[str, str]:
    """Wire the git↔SDLC hook — same semantics as ``dna sdlc hooks install``,
    with an explicit ``cwd`` (``--dir`` may not be the CWD) and skip-with-note
    instead of hard failure, so ``dna init`` degrades gracefully in a dir
    that is not (yet) a git repository. Returns ``(outcome, detail)``.
    """
    from dna_cli import _git_symbiosis as gs

    root = gs.repo_root(cwd=target)
    if root is None:
        return _SKIPPED, "not a git repository — run `git init`, then `dna sdlc hooks install`"
    current_raw = gs._run_git(["config", "--get", "core.hooksPath"], cwd=root)
    current = (current_raw or "").strip() or None
    if current not in (None, gs.HOOKS_DIR):
        return _SKIPPED, (
            f"core.hooksPath already set to '{current}' — merge your hooks into "
            f"{gs.HOOKS_DIR}/ and run `dna sdlc hooks install`"
        )
    # Materialize the versioned hook from the packaged copy when absent
    # (same file `dna sdlc hooks install` ensures).
    hook = root / gs.HOOKS_DIR / gs.HOOK_NAME
    if not hook.exists():
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_bytes(gs.hook_source_path().read_bytes())
    mode = hook.stat().st_mode
    if not mode & stat.S_IXUSR:
        hook.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if current is None:
        if gs._run_git(["config", "core.hooksPath", gs.HOOKS_DIR], cwd=root) is None:
            return _SKIPPED, "git config core.hooksPath failed"
        return _CREATED, f"core.hooksPath = {gs.HOOKS_DIR}"
    return _SKIPPED, f"already wired (core.hooksPath = {gs.HOOKS_DIR})"


@click.command("init")
@click.option(
    "--scope", "scope_opt", default=None,
    help="Board scope name (default: '<dirname>-dev', slugified — the "
         "pilot convention for a dev-time SDLC board).",
)
@click.option(
    "--dir", "dir_opt", default=".",
    help="Project directory to initialize (default: current directory).",
)
@click.option(
    "--tools", "tools_opt", default=",".join(DEFAULT_TOOLS), show_default=True,
    help="Comma-separated agent tools to project the SDLC skill for "
         f"({', '.join(TOOL_SKILL_DIRS)} — or 'all'). The SKILL.md format "
         "is identical across tools; only the directory differs.",
)
@click.option(
    "--force", is_flag=True,
    help="Overwrite existing onboarding files (skill projections, "
         "AGENTS.md). The board Genome is never rewritten — an existing "
         "board is verified and kept.",
)
@click.option(
    "--from", "from_opt", default=None, metavar="URI",
    help="Project a DISTRIBUTED onboarding pack instead of the embedded "
         "one: `github:owner/repo[/subdir][@ref]`, `local:<path>`, or a "
         "bare directory path. The pack must carry at least one agentskills.io "
         "Skill bundle; a root AGENTS.md replaces the embedded instruction "
         "surface (absent: the embedded one is used, with a note). Pack "
         "content is validated with the same defenses as `dna install` and "
         "only PROJECTED into tool directories — combine with `dna install "
         "<same-uri>` when you also want it on the board.",
)
@click.option("--json", "as_json", is_flag=True, help="Machine-readable summary.")
def init(scope_opt: str | None, dir_opt: str, tools_opt: str,
         force: bool, from_opt: str | None, as_json: bool) -> None:
    """Make a project agent-ready: board + skill + AGENTS.md + git hooks.

    One command bootstraps everything an AI coding agent needs to work
    DNA-style in this project:

    \b
      .dna/<scope>/               SDLC board (Genome via the kernel)
      <tool>/skills/dna-sdlc-cli/ the SDLC workflow skill (agentskills.io),
                                  projected per --tools (.claude/skills,
                                  .github/skills, .cursor/skills, ...)
      AGENTS.md                   the canonical instruction surface
                                  (agents.md/v1 — read by 28+ agent tools)
      git hooks                   Work-Item commit trailers

    The assets ship inside dna-cli as an embedded onboarding scope of real
    Kinds and are materialized by the SDK's own byte-faithful
    readers/writers — one Kind, N regenerable projections. AGENTS.md serves
    every tool at once; Gemini CLI users can point GEMINI.md at it.

    With --from, the skills + AGENTS.md come from a DISTRIBUTED onboarding
    pack (your team's own conventions) instead of the embedded scope. The
    pack is fetched and validated with the same machinery as `dna install`
    (untrusted-input defenses included) but only PROJECTED into tool
    directories — nothing from the pack is written to the .dna/ source.
    Review the projected files before committing: a skill is agent
    instructions; treat a third-party pack like a dependency.

    Idempotent: re-running never overwrites an existing file unless
    --force is given; the summary reports what was created vs skipped.

    Examples:

    \b
      dna init                              # here, board '<dirname>-dev'
      dna init --scope acme-dev             # explicit board scope
      dna init --tools all                  # every supported tool dir
      dna init --tools claude,cursor        # explicit projection set
      dna init --dir ../other-project       # initialize another directory
      dna init --from github:acme/onboarding-pack@v1   # your team's pack
      dna init --from local:../onboarding-pack         # offline authoring loop
    """
    target = Path(dir_opt)
    if not target.is_dir():
        raise fail(f"--dir {dir_opt!r} is not an existing directory")
    target = target.resolve()
    scope = scope_opt or _derive_scope(target)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", scope):
        raise fail(
            f"--scope {scope!r} must be a slug (lowercase letters, digits, '-')"
        )
    tools = _parse_tools(tools_opt)

    # 0. The onboarding pack — embedded, or fetched + validated via --from.
    pack = _load_pack_from(from_opt) if from_opt else _load_embedded_pack()

    results: list[tuple[str, str, str]] = []  # (step, outcome, detail)

    # 1. Board — create when missing, verify + keep when present. Always the
    #    LOCAL Genome (derived scope): a pack never redefines the board.
    board_rel = f".dna/{scope}"
    if _board_exists(target, scope):
        results.append(("board", _SKIPPED, f"{board_rel} already exists"))
    else:
        asyncio.run(_bootstrap_board(target, scope))
        results.append(("board", _CREATED, board_rel))

    # 2. Skill Kind(s) → one projection per tool (byte-faithful writer).
    results.extend(_materialize_skills(target, force, tools, pack))

    # 3. AGENTS.md (agentsmd-agent Kind) — the canonical instruction surface.
    outcome, detail = _materialize_agents_md(target, force, pack)
    results.append(("agents-md", outcome, detail))

    # 4. Git hooks (Work-Item trailers).
    outcome, detail = _install_hooks(target)
    results.append(("hooks", outcome, detail))

    review_note = (
        "pack content is third-party — review the projected files before "
        "committing (a skill is agent instructions; treat a pack like a "
        "dependency)"
    ) if pack.remote else None

    if as_json:
        payload = {
            "dir": str(target),
            "scope": scope,
            "steps": [
                {"step": s, "outcome": o, "detail": d} for s, o, d in results
            ],
        }
        if pack.remote:
            payload["from"] = pack.label
            payload["notes"] = pack.notes
            payload["review_note"] = review_note
        print_json(payload)
        return

    header = f"dna init — {target}  (board scope: {scope})"
    if pack.remote:
        header += f"\n  pack: {pack.label}"
    click.secho(header, bold=True)
    step_width = max(len(s) for s, _, _ in results)
    for step, outcome, detail in results:
        color = "green" if outcome == _CREATED else "yellow"
        click.secho(f"  {outcome:<7} {step:<{step_width}} {detail}", fg=color)
    for note in pack.notes:
        click.secho(f"  note    {note}", fg="yellow", dim=True)
    n_created = sum(1 for _, o, _ in results if o == _CREATED)
    n_skipped = len(results) - n_created
    click.secho(
        f"\n{n_created} created · {n_skipped} skipped"
        + ("" if force or not n_skipped else "  (re-run with --force to overwrite files)"),
        bold=True,
    )
    if review_note:
        click.secho(f"\n⚠ {review_note}", fg="yellow", bold=True)
    skill_names = ", ".join(
        str(raw["metadata"]["name"]) for raw in pack.skills
    )
    click.echo(
        "\nNext steps:\n"
        "  dna sdlc feature create f-my-area --title \"...\" --desc \"...\"\n"
        "  dna sdlc story create s-my-first-story --feature f-my-area --desc \"...\" \\\n"
        "    --ac \"Given/When/Then ...\" --dod \"code+tests+docs\"\n"
        "  dna sdlc story start s-my-first-story --plan \"plan of attack\"\n"
        f"  (your agent: read AGENTS.md + the {skill_names} skill"
        f"{'s' if len(pack.skills) > 1 else ''} in its tool's skills dir)"
    )
