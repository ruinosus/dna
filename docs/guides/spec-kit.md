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

## The journey badge

Because the ingester creates the Spec/Plan/Story refs with the right links, the
[derived journey](sdlc.md) auto-fills `specify → plan → build` with **zero manual
upkeep**, and a `WorkflowEvent(methodology="spec-kit")` overlay pins each phase to
its `.specify/` artifact. Leaving the `specify`/`plan` phase under
`methodology=spec-kit` requires the run's `spec.md`/`plan.md` to exist — the same
artifact gate Superpowers uses.
