# ADR: Official Adoption of GitHub Spec Kit

- **Status**: Proposed
- **Date**: 2026-07-15
- **Deciders**: Barna (owner/architect)
- **Author**: claude-code
- **Tracking**: `f-spec-kit-adoption` (board `dna-development`, under epic `e-dna-portability`)
- **Supersedes / relates to**: `f-dna-emitters`, `f-foundry-emit-adoption`, `f-dna-sdlc-expressiveness`

---

## 1. Context — the founder's thesis (the constraint this ADR must honor)

> "DNA não está para SUBSTITUIR nada. Skills, agents, mds não são criação nossa e
> operam conforme foram desenhados." — Barna

DNA is a **layer**, not a workflow tool. Concretely it is:

- **Memory** (owner-scoped + general, semantic search over embedded docs),
- **Definitions** (Kinds: Agent, Soul, Guardrail, Skill, PromptTemplate, Spec, Plan, Story/Feature/Epic…),
- **Governance** (write-guards, tenancy invariants, prompt-budget, no-deploy overrides),
- **Tracking** (the derived journey + the SDLC board),

…all **stored as versioned Kinds** and **served over MCP** (and a REST read-face).

**GitHub Spec Kit** is a *methodology* — a spec-driven workflow (constitution →
spec → plan → tasks → implement) delivered as a CLI (`specify`) that scaffolds a
`.specify/` toolkit and projects per-agent slash-commands into ~30 AI coding
agents. It is opinionated about **how you drive an agent through a feature**.

These two things occupy **different layers** and must **compose, not compete**:

| | Spec Kit | DNA |
|---|---|---|
| **Nature** | Methodology (a process + prompt toolkit) | Layer (memory + definitions + governance + tracking) |
| **Unit** | A feature run in `specs/<feature>/` | A versioned Kind in a scope |
| **Lifetime** | Ephemeral, per-repo, per-feature | Durable, cross-repo, cross-client |
| **Transport** | Slash-commands / agent-skills, per agent | MCP + REST, any client |
| **Governance** | `constitution.md` (a file) | Guardrail Kind (live, overridable, no-deploy) |

Barna's directive: **"Quero utilizar ele [spec-kit] oficialmente no DNA."** This
ADR designs that official adoption such that a Spec Kit run stays **untouched**,
and DNA sits **underneath** it adding portability, memory, governance and
tracking.

---

## 2. Spec Kit deep-dive (facts, so the design targets the real thing)

Source: `github.com/github/spec-kit` + `github.github.io/spec-kit` (fetched 2026-07-15).

### 2.1 The `specify` CLI

- **Init**: `specify init <name>` · `specify init .` / `--here` · `--force`
  (non-empty dirs).
- **Agent selection**: `--integration <agent>` (copilot, gemini, codex,
  **claude**, cursor, opencode, … 30+); `--integration-options="--skills"`
  deploys **agent-skills** instead of **slash-commands**; `--ignore-agent-tools`
  skips tool validation.
- **Script flavor**: `--script sh` | `--script ps` (OS-inferred).
- **Self-management**: `specify self check` (read-only update probe) ·
  `specify self upgrade [--dry-run] [--tag vX.Y.Z]`.
- **Extensibility**: `specify extension add/search`, `specify preset add/search`,
  `specify bundle install/list/validate/build` — a **priority-ordered catalog
  stack** (project > user > built-in; `install-allowed` vs `discovery-only`).

### 2.2 What `specify init` scaffolds

```
.specify/
├── memory/
│   └── constitution.md          # project principles / governance
├── templates/
│   ├── spec-template.md
│   ├── plan-template.md
│   ├── tasks-template.md
│   └── overrides/               # project-local template overrides
│                                # (+ presets/ , extensions/ in the resolution stack)
└── scripts/
    ├── bash/  (check-prerequisites.sh, common.sh,
    │           create-new-feature.sh, setup-plan.sh, setup-tasks.sh)
    └── powershell/  (.ps1 equivalents)
specs/
└── 001-<feature-slug>/          # per-feature artifact directory
.claude/commands/  (or per-agent dir)  # projected slash-commands
```

Template resolution walks **overrides → presets → extensions → core**, first
match wins (identical philosophy to DNA's layer/override resolution).

### 2.3 The slash-command set + the artifact chain

| Command | Reads | Writes |
|---|---|---|
| `/speckit.constitution` | — | `.specify/memory/constitution.md` |
| `/speckit.specify` | constitution | `specs/<f>/spec.md` (what & why) |
| `/speckit.clarify` | spec, constitution | appends **Clarifications** to `spec.md` |
| `/speckit.plan` | spec, constitution | `plan.md` + `research.md` + `data-model.md` + `contracts/` + `quickstart.md` |
| `/speckit.tasks` | plan, spec | `tasks.md` (dependency-ordered, `[P]` parallel markers) |
| `/speckit.analyze` | spec, plan, tasks | consistency/coverage annotations |
| `/speckit.checklist` | spec, plan, tasks | a quality checklist (md) |
| `/speckit.implement` | constitution, spec, plan, tasks | **source code + tests** |
| `/speckit.converge` | codebase + artifacts | appends remaining-work tasks |
| `/speckit.taskstoissues` | tasks | **GitHub issues** |

```
constitution.md → spec.md → plan.md (+research/data-model/contracts/quickstart) → tasks.md → code
```

### 2.4 The agent-agnostic mechanism (the exact parallel to DNA)

Spec Kit is agent-agnostic because it **projects one command set into N
agents**: at `init`/`extension add` time it writes the templated prompt files
into each agent's directory (`.claude/commands/`, `.github/…`, `.cursor/…`) — or,
in `--skills` mode, as agent-native skills. **One command definition, N
projections.**

**This is the same shape as DNA's `dna init`**, which reads a **Skill Kind**
once and projects it byte-faithfully into `TOOL_SKILL_DIRS`
(`.claude/skills`, `.github/skills`, `.cursor/skills`, `.opencode/skills`) plus
an `AGENTS.md` — "**one Skill Kind, N projections**". The two systems already
speak the same dialect (agentskills.io SKILL.md + agents.md/v1); they differ
only in **what** they project (Spec Kit: process commands; DNA: durable
skills/definitions). That congruence is what makes adoption an *integration*,
not a *port*.

---

## 3. What DNA already has (so we adopt, not reinvent)

The audit of `~/projects/dna` found the adoption surface is **~70% pre-built**:

1. **`spec-kit` is already a named methodology.** `JOURNEY_METHODOLOGIES`
   (`extensions/sdlc/__init__.py`) contains `"spec-kit"`; the `WorkflowEvent`
   kind's `methodology` enum lists it; and `WorkflowEvent.methodology_artifact`
   is **already documented** with the example `".specify/foo/plan.md"`. DNA's
   authors anticipated this exact wiring — the ledger is waiting for a producer.

2. **A Spec/Plan directory ingester already exists** — `dna sdlc backfill
   --from <dir> <pattern> [--kind Spec|Plan|auto]` walks a directory of markdown
   and writes **Spec**/**Plan** Kinds, auto-inferring `specs/ → Spec`,
   `plans/ → Plan`, parsing `**Status**` / `**Author**`, tagging a methodology
   `pattern`. This is the **direct prior art** for the Spec Kit ingester — the
   new command is a specialization of `backfill`, not a greenfield build.

3. **The journey is a derived pure function of signals** (`journey_derive.py`):
   `specify` lights from a linked **Spec** (`spec_refs`) or from AC/DoD; `plan`
   from a linked **Plan**; `build`/`verify`/`reflect` from timeline + TestRun +
   LessonLearned. So: **if the ingester creates Spec/Plan/Story docs with the
   right refs, the journey auto-fills — zero manual upkeep.** Explicit
   `WorkflowEvent(methodology="spec-kit", methodology_artifact=…)` docs overlay
   on top for the badge + the honest `.specify/` trail.

4. **Methodology gates are already a pattern** (`_methodology_gates.py`):
   `spec_gate` / `plan_gate` / `tdd_gate` are pure functions that today fire only
   for `methodology=superpowers`. A `spec-kit` profile (spec.md must exist to
   leave `specify`; plan.md to leave `plan`; …) is an **additive branch**, not
   new machinery.

5. **The Kinds the artifacts map onto all exist**: `Spec` (with a `pattern`
   field), `Plan` (with a `methodology` field), `Story`/`Feature`/`Epic`,
   `Guardrail` (`extensions/guardrails`), `Soul` (`soulspec-soul`), `Skill`
   (`agentskills-skill`), `PromptTemplate`, `Reference`.

6. **The projection machinery exists twice**: `dna init` (Skill/AGENTS.md → tool
   dirs, byte-faithful) and `dna emit` (Agent → runtime artifact via the
   `EmitterPort` registry, "1 source → N runtimes byte-identical", golden-tested).
   Either is a template for Layer 4 (projecting **into** `.specify/`).

**Conclusion:** adoption is **wiring + one new bridge command**, reusing
`backfill`'s ingestion, the derived journey, the methodology-gate pattern, and
the existing Kinds. No new subsystem.

---

## 4. The 1:1 mapping table (Spec Kit artifact → DNA Kind)

| Spec Kit artifact | → DNA Kind | Mechanism / notes |
|---|---|---|
| `.specify/memory/constitution.md` | **Guardrail** (optionally + **Soul**) | Live, overridable, no-deploy governance. `pattern=spec-kit`. |
| `specs/<f>/spec.md` (+ Clarifications) | **Spec** (`pattern="spec-kit"`) | `backfill`-style parse: title from `# H1`, status from `**Status**`. |
| `specs/<f>/plan.md` | **Plan** (`methodology="spec-kit"`) | Linked to the Spec + the parent Story/Feature. |
| `research.md`, `data-model.md`, `contracts/`, `quickstart.md` | **Reference** docs attached via `produces[]` | Hang off the Plan as produced artifacts (any-Kind hub). |
| `tasks.md` (task list, `[P]` markers) | **Story** per task, under one **Feature** | `[P]` → `parallel` label; dependency order → estimate/sequence. |
| the `specs/<f>/` feature dir itself | **Feature** `f-<slug>` (or reuse existing) | The hub the Stories + Spec + Plan attach to. |
| a whole Spec Kit run (a session) | **WorkflowEvent**(s) `methodology=spec-kit`, `methodology_artifact=.specify/<f>/…` | Overlays the derived journey with the honest per-phase `.specify/` trail. |
| `constitution.md` principles (governance) | **Guardrail** enforced at write-time | This is where DNA *adds* over raw Spec Kit: the constitution becomes live policy, not a passive file. |

Nothing in the table asks Spec Kit to change. The `.specify/` run is the
**source of truth for the run**; DNA **mirrors** it into durable, queryable,
governed Kinds.

---

## 5. The four candidate integration layers

Ordered from lightest/most-decoupled to deepest/most-authoritative. They are
**cumulative**, not exclusive — each builds on the last.

### Layer 1 — Spec Kit as a first-class DNA journey methodology (INGEST) ← the PoC

A **bridge command** (`dna specify import <.specify-dir>`, or a watcher) maps a
Spec Kit run into DNA Kinds per §4. **Spec Kit runs 100% untouched**; DNA
observes the `.specify/` output and materializes the mapping. The derived
journey fills from the real signals; a `WorkflowEvent` per phase records the
`methodology_artifact` trail. This is the "compose, don't compete" proof in its
purest form: you can run Spec Kit with **zero** DNA, then `import` and get
portability + memory + tracking for free.

### Layer 2 — DNA feeds Spec Kit's agent (MEMORY + DEFINITIONS)

The Spec Kit-driven coding agent is pointed at **DNA MCP**. Now, mid-run, the
agent has: portable **memory** (recall across sessions/clients), curated
**Skills**, and the live **Soul/Guardrails** — regardless of which of the 30+
agents Spec Kit projected into. Spec Kit still owns the *process*; DNA supplies
the *context and identity* the process operates on.

### Layer 3 — DNA serves Spec Kit's constitution + templates (GOVERNANCE, no-deploy)

`constitution.md` becomes a **Guardrail Kind** (live, overridable per
scope/tenant, enforced at `write_document` time — governance without redeploy);
Spec Kit's `spec/plan/tasks` templates become **PromptTemplate/Skill** Kinds
served over MCP. The `.specify/templates/overrides/` stack maps onto DNA's
layer/override resolution. Governance stops being a file you hope people read
and becomes policy the platform enforces.

### Layer 4 — Convergence / projection (DNA as authoritative store)

DNA becomes the authoritative store and `.specify/` becomes **one of its
byte-faithful projections** — the same machinery that already projects
`AGENTS.md`/skills (`dna init`) or runtime artifacts (`dna emit`). A
`dna specify export` (a `.specify` emitter target) regenerates a valid
`.specify/` tree from the DNA Kinds. This closes the loop: author once in DNA,
project to Spec Kit (and to any other methodology) on demand. **Deferred** —
earns its place only after Layers 1–3 prove the mapping in both directions.

---

## 6. Recommended PoC (concrete) — Layer 1, the ingester

**What ships in the PoC:**

1. **`dna specify import <path>` bridge command** (`packages/cli/dna_cli/` — a
   sibling of `emit_cmd.py`, reusing `backfill`/`install`'s scan+validate
   pipeline so the untrusted-input defenses never fork). Shape:

   ```
   dna specify import .specify/                 # ingest the whole toolkit + runs
   dna specify import specs/001-taskify/        # ingest one feature run
   dna specify import . --feature f-taskify     # attach to an existing Feature
   dna specify import . --dry-run --json        # preview the mapping, write nothing
   ```

   Flags: `--scope`, `--feature` (reuse vs create), `--dry-run`, `--json`,
   `--constitution-as guardrail|soul|both`.

2. **The mapping executor** (§4): constitution → Guardrail; `spec.md` → Spec
   (`pattern=spec-kit`); `plan.md` → Plan (`methodology=spec-kit`);
   research/data-model/contracts → Reference via `produces[]`; each `tasks.md`
   item → Story under the Feature; a `WorkflowEvent` per phase with
   `methodology_artifact` set to the `.specify/` path. Every write goes through
   `kernel.write_document` (all guards fire).

3. **Journey wiring**: no new code in `journey_derive.py` — the derived journey
   *already* lights `specify`/`plan`/`build` from the Spec/Plan/Story refs the
   ingester creates. The PoC's job is to create the refs correctly and add the
   `spec-kit` `WorkflowEvent` overlay. (A `spec-kit` profile in
   `_methodology_gates.py` is a fast-follow, not PoC-blocking.)

4. **Docs**: DNA's docs (`docs/guides/…`) name **Spec Kit as the supported
   spec-driven flow**, with the two-command story: `specify …` to run, `dna
   specify import` to durably capture. `RECOMMENDED-SKILLS.md` / onboarding
   references it.

**Where it plugs in (files):**

- New: `packages/cli/dna_cli/specify_cmd.py` (the bridge) + registration in
  `dna_cli/__init__.py`.
- Reuse: `sdlc_cmd.py::cmd_backfill` internals (Spec/Plan parse), `install_cmd`
  scan/validate, `extensions/sdlc/__init__.py` Kind writers,
  `journey_derive.py` (unchanged), `WorkflowEvent` (unchanged schema).
- New tests: `packages/cli/tests/test_specify_import.py` (dry-run mapping over a
  fixture `.specify/` tree; parity of the produced Kinds).

**"Officially adopt" means operationally:** (a) `dna` ships the `specify` bridge
subcommand; (b) DNA's docs name Spec Kit as *the* supported spec-driven flow and
show the compose story; (c) a `spec-kit` methodology badge renders on the
journey from real `.specify/` signals. Nothing forces Spec Kit users onto DNA;
DNA rewards them for pointing at it.

---

## 7. What DNA adds over raw Spec Kit (the "doesn't replace" proof)

Run Spec Kit alone and you get an excellent, ephemeral, single-repo,
single-agent-family feature run. Point it at DNA and you *additionally* get:

- **Portability across AI clients** — the same run's spec/plan/tasks + memory are
  reachable from Claude, Copilot, Cursor, Codex… over MCP, not locked to the one
  agent Spec Kit projected into.
- **Durable memory + semantic search + versioning** — the run becomes queryable
  history (`dna cognitive search`, versioned Kinds), not files that rot in a
  branch.
- **Live governance** — the constitution becomes an enforced Guardrail
  (no-deploy, per-scope/tenant overridable), not a passive markdown file.
- **Board tracking** — tasks become Stories on a real board with the derived
  journey, FOCUS feed, and DoD gates.

Every one of these is **additive**. Spec Kit's process is untouched; DNA is the
layer beneath it. **That is the literal demonstration of the founder's thesis.**

---

## 8. Open decisions for Barna

1. **Constitution mapping** — does `constitution.md` become a **Guardrail**
   (enforced policy), a **Soul** (identity/persona), or **both**? Recommendation:
   **Guardrail** for the PoC (it's governance), Soul deferred to Layer 3.
2. **Ingest trigger** — **manual `dna specify import`** (explicit, PoC-simple) vs
   a **watcher/git-hook** that auto-imports on `.specify/` change (seamless, more
   moving parts). Recommendation: **manual for the PoC**, watcher as a
   fast-follow once the mapping is proven.
3. **Directionality now vs later** — PoC is **import-only** (Spec Kit → DNA).
   Confirm we **defer** the `export`/projection direction (Layer 4) rather than
   building both at once. Recommendation: **defer** — prove one direction first.

*(Non-blocking, my call unless you object: task `[P]` markers → a `parallel`
label on the Story; one Story per `tasks.md` item vs one per checkpoint-group.)*

---

## 9. Rough size

| Story | Est. | Notes |
|---|---|---|
| Ingester bridge command (`dna specify import`, dry-run + scan/validate reuse) | M | Sibling of `emit_cmd`/`backfill`; most logic reused. |
| Artifact→Kind mapping executor (constitution/spec/plan/tasks + `produces[]`) | M | The core; `write_document` for every doc. |
| Journey wiring + `spec-kit` `WorkflowEvent` overlay | S | Derived journey unchanged; add overlay + (fast-follow) gate profile. |
| Docs: name Spec Kit as the supported spec-driven flow + compose story | S | Guide + onboarding + `RECOMMENDED-SKILLS.md`. |

**Total: ~S/M — a few days of focused work, no new subsystem.** Layers 2–4 are
separate, larger, and explicitly out of the PoC.

---

## 10. Decision

**Proposed:** adopt Spec Kit officially via **Layer 1 (the ingester PoC)** —
`dna specify import` mapping a Spec Kit run into DNA Kinds (§4), with Spec Kit
running untouched, the derived journey auto-filling, and DNA's docs naming Spec
Kit as the supported spec-driven flow. Layers 2–4 are the roadmap after the PoC
validates the mapping. Awaiting Barna's ruling on §8 before any build.
