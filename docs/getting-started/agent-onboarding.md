# Make your project agent-ready with `dna init`

`pip install dna-sdk dna-cli` gives you a working kernel and CLI — but the
AI coding agent working in *your* project still arrives blind: it does not
know the story-first workflow, the `dna sdlc` verbs, or that commits should
carry `Work-Item:` trailers. Those conventions live in documents, and until
now they only existed inside the DNA repository itself.

`dna init` closes that gap with one command — for **every** agent tool at
once. The market has converged on two centralizing standards, and DNA
already speaks both natively as Kinds:

- **[AGENTS.md](https://agents.md/)** (`agents.md/v1`, Linux Foundation
  stewardship) is *the* instruction standard — read by 28+ tools including
  Codex CLI, GitHub Copilot, Cursor, Windsurf, Aider, Zed, VS Code,
  JetBrains Junie… and Claude Code.
- **[SKILL.md](https://agentskills.io/specification)** (`agentskills.io/v1`)
  is *the* skill standard — ~40 tools. The format is identical everywhere;
  only the discovery *directory* is tool-specific.

So `dna init` materializes **one Kind, N projections**: the onboarding
assets ship inside `dna-cli` as an embedded scope of real Kinds, and the
SDK's own byte-faithful readers and writers — the same
[market-fidelity](../concepts/market-fidelity.md) machinery that
round-trips third-party bundles — write them to disk. The writers are the
product.

!!! tip "`dna init` or `dna install`?"

    `dna init` **projects** regenerable onboarding assets — the skill and
    `AGENTS.md` — into your agent tools' directories, so the coding agent
    *knows how to operate the project*. It does **not** write those Kinds
    into your source. If instead you want to **add a Skill or any other
    Kind from a repo into your project's data** (`.dna/`) — to compose,
    query or evaluate it — that is
    [`dna install`](../guides/installing-scopes.md). The two share a fetch
    path and compose at the same ref; see the
    [side-by-side comparison](../guides/installing-scopes.md#dna-install-vs-dna-init-write-to-source-or-project-to-tools).

## What it creates

```console
$ cd my-project
$ dna init
dna init — /home/you/my-project  (board scope: my-project-dev)
  created board          .dna/my-project-dev
  created skill[claude]  .claude/skills/dna-sdlc-cli
  created skill[copilot] .github/skills/dna-sdlc-cli
  created agents-md      AGENTS.md
  created hooks          core.hooksPath = scripts/git-hooks

5 created · 0 skipped
```

| Artifact | What it is |
| --- | --- |
| `.dna/<scope>/` | Your project's SDLC board: a `Genome` written through the kernel (every write guard runs), plus seeded `stories/`, `features/`, `issues/` containers so the [scope auto-detection](../guides/sdlc.md) recognizes the board immediately. |
| `<tool>/skills/dna-sdlc-cli/` | The SDLC workflow skill (Kind `agentskills-skill`) — teaches the agent the story-first lifecycle: AC/DoD at create, the plan gate, narration, the test gate, `story pr`, git trailers. Projected once per tool selected with `--tools`; byte-identical everywhere. |
| `AGENTS.md` | The **canonical instruction surface** at your project root — a live `agents.md/v1` instance (Kind `agentsmd-agent`) that the SDK parses and round-trips byte-faithfully. One file serves every tool that reads the standard. |
| Git hooks | `core.hooksPath` wired at the versioned `scripts/git-hooks/` (same as `dna sdlc hooks install`): while a Story is active, every commit is stamped with `Work-Item:` + `dna-sdlc[bot]` trailers. |

## Choosing tools — `--tools`

The skill is projected into the skills directory of each selected tool
(default `claude,copilot`; use `all` for every supported tool):

| Tool | Skill projection directory |
| --- | --- |
| `claude` (Claude Code) | `.claude/skills/dna-sdlc-cli/` |
| `copilot` (GitHub Copilot / VS Code) | `.github/skills/dna-sdlc-cli/` |
| `cursor` (Cursor) | `.cursor/skills/dna-sdlc-cli/` |
| `opencode` (OpenCode) | `.opencode/skills/dna-sdlc-cli/` |

```bash
dna init --tools all              # every supported tool directory
dna init --tools claude,cursor    # an explicit projection set
```

The projections are regenerable artifacts; the Skill Kind in the embedded
onboarding scope is the source of truth. All generated content is
tool-agnostic — core spec fields only, no proprietary frontmatter, no
tool-specific personas.

**What about instruction files per tool?** None are generated, on purpose:
AGENTS.md *is* the cross-tool instruction surface (Claude Code reads it
too). If you want a `CLAUDE.md`, make it a thin pointer to AGENTS.md —
never a duplicate. Gemini CLI still reads `GEMINI.md`; point it at
AGENTS.md the same way (a one-line file, or Gemini's `contextFileName`
setting).

## Idempotent by design

Re-running `dna init` never destroys customizations: an existing file is
skipped with a note, and only `--force` overwrites the skill projections
and `AGENTS.md` from the embedded assets. The board is **never**
rewritten — an existing `.dna/<scope>/` is verified and kept, `--force`
or not.

```console
$ dna init
  skipped board          .dna/my-project-dev already exists
  skipped skill[claude]  .claude/skills/dna-sdlc-cli
  skipped skill[copilot] .github/skills/dna-sdlc-cli
  skipped agents-md      AGENTS.md
  skipped hooks          already wired (core.hooksPath = scripts/git-hooks)

0 created · 5 skipped  (re-run with --force to overwrite files)
```

In a directory that is not yet a git repository, the hooks step is skipped
with a pointer to run `git init` and `dna sdlc hooks install` later — the
board, skill and `AGENTS.md` are still created.

The board scope defaults to `<dirname>-dev` (`--scope acme-dev` to
choose); `--dir` initializes a directory other than the current one.

## First story on the new board

The board is immediately usable — the `dna sdlc` verbs auto-detect it as
the sole SDLC scope in the source:

```bash
dna sdlc feature create f-my-area --title "..." --desc "..."
dna sdlc story create s-my-first-story --feature f-my-area --desc "..." \
  --ac "Given/When/Then ..." --dod "code + tests + docs"
dna sdlc story start s-my-first-story --plan "plan of attack"
```

From here, the full loop is the one described in
[Your git log is your SDLC](../guides/sdlc.md).

## Distribute your team's onboarding — `--from`

The embedded assets are the *default* onboarding. A team can distribute its
**own** pack — the house skill(s) plus, optionally, a custom AGENTS.md —
and consumers bootstrap from it directly:

```console
$ dna init --from github:ruinosus/dna/examples/onboarding-pack
dna init — /home/you/my-project  (board scope: my-project-dev)
  pack: ruinosus/dna/examples/onboarding-pack (commit 95232daf6e2b)
  created board                           .dna/my-project-dev
  created skill[claude:acme-conventions]  .claude/skills/acme-conventions
  created skill[copilot:acme-conventions] .github/skills/acme-conventions
  created agents-md                       AGENTS.md
  created hooks                           core.hooksPath = scripts/git-hooks

5 created · 0 skipped

⚠ pack content is third-party — review the projected files before
  committing (a skill is agent instructions; treat a pack like a dependency)
```

An onboarding pack is just a repository subtree — see the live example at
[`examples/onboarding-pack/`](https://github.com/ruinosus/dna/tree/main/examples/onboarding-pack):

- **at least one Skill bundle** (`skills/<name>/SKILL.md`,
  `agentskills.io/v1`) — packs without one are refused;
- **optionally an `AGENTS.md` at the pack root** — it replaces the embedded
  instruction surface; without one, the embedded default is used (the
  summary says so explicitly).

`--from` accepts `github:owner/repo[/subdir][@ref]`, `local:<path>`, or a
bare directory path — the offline authoring loop while you draft the pack.
Everything else about `dna init` is unchanged: idempotence, `--force`,
`--tools`, and the board is always born from the **local** Genome (a pack
never redefines the board scope — a `Genome.yaml` in the pack is ignored,
with a note).

**`--from` vs `dna install`.** The two channels share the fetch and the
untrusted-input validation (registered Kinds only, JSON-Schema-checked
specs, slug-only names — see [`dna install`](../guides/installing-scopes.md)) but
write to different places:

| | `dna install <uri>` | `dna init --from <uri>` |
| --- | --- | --- |
| Writes to | Your `.dna/` **source** — documents + `installed.lock` | Agent **tool directories** — skill(s) + `AGENTS.md` |
| Result | Real, versioned source you compose/query/evaluate | Regenerable projections your agent reads |
| Accepts | Any registered Kind the tree carries | Skill bundles + a root `AGENTS.md` only |

When you want both — the pack's docs on the board *and* the projections —
combine them at the same ref:

```bash
dna install github:acme/onboarding-pack@v1        # docs → .dna/ (+ lockfile)
dna init   --from github:acme/onboarding-pack@v1  # projections → tool dirs
```

Because a skill *is* agent instructions, a third-party pack carries the
same inherent risk as any dependency — the validation stops path traversal
and malformed documents, not hostile prose. Review what was projected
before committing it.

## Already driving a Spec Kit run?

If your project uses [GitHub Spec Kit](https://github.com/github/spec-kit) for
its spec-driven flow, DNA composes underneath it: run Spec Kit as usual, then
`dna specify import .specify/` to durably capture the run (constitution → a live
Guardrail + Soul, spec/plan/tasks → Spec/Plan/Story Kinds on the board). See the
[Spec Kit guide](../guides/spec-kit.md) for the full mapping and the
`dna specify export` round-trip.

## Python-only, by construction

The `dna` binary is part of the Python distribution (`dna-cli`); the
TypeScript SDK (`dna-sdk` on npm) is a library and deliberately ships no
CLI — see the [parity matrix](../reference/parity-matrix.md). `dna init`
is therefore Python-only, but everything it materializes is
runtime-agnostic markdown/YAML: the TypeScript SDK reads the same board,
skill and `AGENTS.md` byte-for-byte.
