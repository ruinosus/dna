# Spec Kit — the supported spec-driven flow

[GitHub **Spec Kit**](https://github.com/github/spec-kit) is a spec-driven
*methodology*: you drive an AI coding agent through `constitution → spec → plan →
tasks → implement`, scaffolded by the `specify` CLI into a `.specify/` toolkit
and per-feature `specs/<feature>/` runs. DNA is a *layer* — memory, definitions,
governance and tracking, stored as versioned Kinds and served over MCP.

They occupy **different layers** and **compose, not compete**. DNA officially
names Spec Kit as *the* supported spec-driven flow and sits **underneath** it,
adding portability, memory, governance and tracking — **without changing how
Spec Kit runs**.

> The founder's thesis: *"DNA não está para substituir nada. Skills, agents, mds
> não são criação nossa e operam conforme foram desenhados."* Spec Kit stays
> untouched; DNA is the durable layer beneath it.

## Prerequisites — install the real Spec Kit CLI

DNA does **not** bundle, vendor, or reimplement Spec Kit. You install the real
[`specify` CLI](https://github.com/github/spec-kit) yourself — it is a separate
tool that does the scaffolding and authoring:

```console
# Persistent install from PyPI (recommended):
$ uv tool install specify-cli

# …or pin to a specific Spec Kit release tag:
$ uv tool install --from git+https://github.com/github/spec-kit.git@v0.0.55 specify-cli

$ specify --version        # confirm the real Spec Kit CLI is on PATH
```

**Who does what — the composition is explicit:**

| | The real `specify` CLI (you install it) | `dna specify` (ships with DNA) |
|---|---|---|
| **Owns** | Scaffolding + authoring: `specify init` creates `.specify/`, the slash-commands (`/speckit.*`) drive your agent through the flow | The DNA-side **bridge**: reads/writes that `.specify/` tree ↔ durable DNA Kinds |
| **Runs** | The methodology (constitution → spec → plan → tasks → implement) | `import`/`export` a run; `install-templates`/`export-templates` the toolkit |

`dna specify` **never invokes or depends on the `specify` binary at runtime** —
it only reads and writes the `.specify/` files on disk. That is the whole point:
*don't reinvent the wheel, compose with it.* Run Spec Kit exactly as its docs
describe; point DNA at the result.

## The two-command compose story

```console
# 1. Run Spec Kit exactly as its docs describe — DNA is not involved yet.
$ specify init taskify --integration claude
$ # …drive /speckit.constitution, /speckit.specify, /speckit.plan, /speckit.tasks…

# 2. Durably capture the run into DNA Kinds (portability + memory + governance).
$ dna specify import .specify/
Imported Spec Kit run: 17 documents across 1 feature(s).
  Feature/f-taskify  (taskify)
```

You can run Spec Kit with **zero** DNA, then `import` and get portability,
memory, governance and board tracking for free. Preview first with
`--dry-run --json` — it prints the full mapping and writes nothing.

## Worked example — end to end

This is a full, verified round-trip: author a feature with the real Spec Kit,
capture it in DNA, project it back, and wire the agent to live DNA. Every step
below was run against a live DNA source.

```console
# 1. Install the real Spec Kit and scaffold a spec-driven project.
$ uv tool install specify-cli
$ specify init dna-cloud-invite --integration claude   # creates .specify/ + the speckit-* skills

# 2. Author the run via Spec Kit's own flow (constitution → spec → plan → tasks).
$ bash .specify/scripts/bash/create-new-feature.sh "portal member-invite UI"
$ #  …drive /speckit.constitution, /speckit.specify, /speckit.plan, /speckit.tasks
$ #    which fill .specify/memory/constitution.md and specs/001-*/spec.md|plan.md|tasks.md

# 3. Capture the run into DNA — Spec Kit is untouched; DNA mirrors it.
$ dna specify import ./dna-cloud-invite --scope my-scope
Imported Spec Kit run: 24 documents across 1 feature(s).
  Feature/f-portal-member-invite-ui  (portal-member-invite-ui)

# 4. The run is now tracked work: a Feature + one Story per task, journey filled.
$ dna sdlc feature show f-portal-member-invite-ui --scope my-scope
  Feature: f-portal-member-invite-ui   status: in-development
  Stories (15) — todo:15   # T001…T015, [P] tasks carry a `parallel` label

# 5. Round-trip: DNA reprojects a byte-identical .specify/ (DNA is the source now).
$ dna specify export f-portal-member-invite-ui --scope my-scope --out /tmp/rt
$ diff .specify/memory/constitution.md /tmp/rt/.specify/memory/constitution.md   # identical
$ diff specs/001-portal-member-invite-ui/spec.md /tmp/rt/specs/001-portal-member-invite-ui/spec.md  # identical

# 6. Point the agent at live DNA memory/soul/board for the next run (Layer 2).
$ dna specify wire --tools claude   # writes a `dna` MCP server into .mcp.json
```

After step 3 the constitution is a live **Guardrail** (`speckit-constitution`),
the spec/plan are queryable Kinds, and the 15 tasks are Stories on the board —
authored by Spec Kit, owned by DNA.

## What maps to what

`dna specify import` mirrors each Spec Kit artifact into the durable Kind that
already models it (ADR *ADR-spec-kit-adoption* §4):

| Spec Kit artifact | → DNA Kind | Notes |
|---|---|---|
| `.specify/memory/constitution.md` | **Guardrail** + **Soul** | `--constitution-as` (default `both`): the Guardrail is live, enforced, no-deploy governance; the Soul carries the identity/voice. |
| `specs/<f>/spec.md` | **Spec** (`pattern="spec-kit"`) | Title from `# H1`, status from `**Status**`. |
| `specs/<f>/plan.md` | **Plan** (`methodology="spec-kit"`) | Linked to the Spec (`spec_ref`). |
| `research.md`, `data-model.md`, `quickstart.md`, `contracts/*` | **Reference** via `Plan.produces[]` | Attached to the Plan as produced artifacts. |
| each `tasks.md` item (`T### [P]? …`) | **Story** under the Feature | `[P]` → a `parallel` label; every Story cites the Spec. |
| the `specs/<f>/` run itself | **Feature** `f-<slug>` | The hub; carries the `specify_run` export manifest. |
| the whole run | **WorkflowEvent**(s) `methodology=spec-kit` | Overlays the derived journey with the honest `.specify/` per-phase trail. |

Every write goes through `kernel.write_document`, so all guards fire — the
constitution *becomes* enforced policy instead of a passive markdown file.

### Options

```console
$ dna specify import specs/001-taskify/          # ingest one feature run
$ dna specify import . --feature f-taskify       # attach to an existing Feature
$ dna specify import . --constitution-as soul    # constitution → Soul only
$ dna specify import . --dry-run --json          # preview the mapping, write nothing
```

## The other direction — export

DNA is the **authoritative store**; `.specify/` is one of its **byte-faithful
projections** — the same "one source → N projections" philosophy behind
`dna init` and `dna emit`. `dna specify export` replays a DNA-stored run back to
a valid `.specify/` tree:

```console
$ dna specify export f-taskify --out ./regenerated
Projected Feature/f-taskify → ./regenerated (8 files):
  .specify/memory/constitution.md
  specs/001-taskify/spec.md
  …
```

Round-trip fidelity is guaranteed: **`import` then `export` reproduces the
source `.specify/` artifacts byte-for-byte** (an acceptance test in the suite).

## Serving the *toolkit* itself — Layer 3

`import`/`export` bridge a *run*. You can also bridge the **toolkit** — the
templates, slash-commands, scripts and constitution — so they become versioned
Kinds served live over MCP and overridable per workspace, instead of files that
drift per-repo. See **[Spec Kit templates, served by DNA](spec-kit-templates.md)**.

## What DNA adds over raw Spec Kit

Run Spec Kit alone and you get an excellent, ephemeral, single-repo,
single-agent-family feature run. Point it at DNA and you *additionally* get:

- **Portability across AI clients** — the run's spec/plan/tasks + memory are
  reachable from Claude, Copilot, Cursor, Codex… over MCP, not locked to the one
  agent Spec Kit projected into.
- **Durable memory + semantic search + versioning** — the run becomes queryable
  history (`dna cognitive search`, versioned Kinds), not files that rot in a branch.
- **Live governance** — the constitution becomes an enforced Guardrail
  (no-deploy, per-scope/tenant overridable), not a passive file.
- **Board tracking** — tasks become Stories on a real board with the derived
  journey, FOCUS feed and DoD gates. The journey renders a `spec-kit` badge.

Every one of these is **additive**. Spec Kit's process is untouched; DNA is the
layer beneath it.

## Feeding DNA *into* the run (Layer 2)

`import`/`export` capture a run *after* it happens. To feed DNA's live memory,
soul and board *into* a Spec Kit run *while* it happens — pointing whichever
agent Spec Kit drives at the DNA MCP — see
[Spec Kit + DNA's live memory over MCP](spec-kit-live-memory.md) (`dna specify
wire`).

## The journey badge

Because the ingester creates the Spec/Plan/Story refs with the right links, the
[derived journey](sdlc.md) auto-fills `specify → plan → build` with **zero manual
upkeep**, and a `WorkflowEvent(methodology="spec-kit")` overlay pins each phase to
its `.specify/` artifact. Leaving the `specify`/`plan` phase under
`methodology=spec-kit` requires the run's `spec.md`/`plan.md` to exist — the same
artifact gate Superpowers uses.
