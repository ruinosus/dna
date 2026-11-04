<h1 align="center">agent-review</h1>

<p align="center"><b>Point Claude at your Copilot Studio agents, cloned. See what they all do, who is off the pattern,
what only one has, what the orchestrator passes on, which events they log and whether they fire, and what nobody uses —
with the file and line behind every finding.</b></p>

<p align="center">
  <img src="https://ruinosus.github.io/dna/agent-review/images/rh-agents-map.png" alt="Six agents of a made-up shop compared: a matrix of who has what, with a red × where one specialist does not escalate and another logs no telemetry" width="860">
</p>

<p align="center">
  An <a href="https://agentskills.io">Agent Skill</a> for Claude Code, claude.ai, the Claude API and other tools that load skills.<br>
  <a href="https://ruinosus.github.io/dna/agent-review/">Open the gallery</a> to click through the map, play the lesson and download the workbook.
</p>

---

## What it does

A team with many agents in Copilot Studio — an orchestrator and its specialists — needs to know **what repeats** (a
pattern to agree on), **who does it differently** (to correct, or to learn from) and **what is missing**, to set
architecture and delivery standards from evidence rather than opinion. agent-review reads the agents as the VS Code
extension clones them, compares them and shows it, with the file and line behind each finding. Once the team accepts a
pattern, every run checks it — on every agent, a new one included.

It runs on **Node alone**: no model, no install, no network. The client's data never leaves the machine, so it fits a
locked-down environment where a model has few credits or none.

## What you get

| | |
|---|---|
| **The map** (`.html`) | One page that opens offline: «to look at» on top, in groups with how many (Contradictions · Contract and telemetry · Off pattern · Rules · Only one has it · Unused · Not understood; «Only one has it» and «Unused» folded at first); the matrix of facts by dimension (conversation, integrations, knowledge, orchestrator, governance) and agent — ● has it, × off a pattern, ◐ declared — filtered by role and focus area; the patterns to decide; a click shows who has it and the file and line. Tabs for the patterns, the cast (each one's chain — agent → flow → system — and its events, with the times they fired), the Microsoft reference patterns, what nobody uses and what was not understood. |
| **The workbook** (`.xlsx`) | Summary, Matrix, Patterns (with a Decision column to fill), Text (the blocks agents share, who has a variation), Off pattern, Gaps, Conflicts, Cast (with each one's types), Routing (what the orchestrator passes to each), Telemetry (each event as written, its form, its fields and, with an export, the times it fired), Unused, Evidence, Declared (to fill). Read back with `--from`, taken with `--take`. |
| **The lesson** (`.lesson.html`) | A visual-explainer lesson: the cast, what repeats, who is off, what is missing, what to decide. |
| **The RH of the cast** (`.team.html`) | The same cast as people: the staff board (being hired, with no owner, never published, with a development plan, in good standing), the org chart by type, the post of each role and type, and a résumé each — the first sentence of its instructions, manager, team, owner, tools, goal, performance from the telemetry and its development plan (PDI): what «to look at» says about it alone, as actions. The workbook gets the Staff and PDI sheets. |
| **The stage** (`.topology.html`) | The cast on a stage, to show in a meeting: the traffic moving along the arrows (each one's topic starts, from the export), lenses that light who follows a pattern and who is off, a follow spot that walks each call of the orchestrator and stops where it breaks, and a card per actor. |
| **The diagrams** (`.diagrams.md`, `.diagrams/*.mmd`) | What was read, in plain Mermaid, for the team's docs (GitHub, a wiki, VS Code): the topology, a sequence per call of the orchestrator, a lens per pattern and the anatomy of each type — from the same data as the stage. Each one also draws in visual-explainer. |
| **The review file** (`.cast.yaml`) | What people declared (KPIs, owners, what a handoff claims) and what was decided — kept between runs. |

## How it decides

- **A pattern**: a fact in at least 70% of a role's agents, with at least 3 of them (the team's profile can change both).
  The **platform's** when the orchestrator has it too; the **specialists'** otherwise.
- **Off a pattern**: an agent of that scope without it. **Only one has it**: innovation or debt — someone has to say.
- **Rules**: what the team's profile says every agent of a role must have. **Conflicts**: what a document claims and
  the YAML does not show; what was seen wins.
- **The text**, too: the instructions and the descriptions the model reads, cut into blocks. A block two agents or more
  share is a fact; a copy that lost a line is a **variation**, and the map shows the words that went and came. The
  team's profile adds **markers** — patterns of words with the value they capture («at most 3 bullets») — so a rule
  written in two ways, or twice in one agent, is told; and the **official blocks** the team pastes everywhere. It
  compares text, not meaning.
- **Types** of specialist (transaction, guidance, triage…), from what their YAML and text show: patterns are also found
  within each type, and a pattern of a type never blames who is not of it. One may be of two types.
- A rule can confront the text with the setup: «asks for the knowledge alone» with the model's general knowledge on.
- **The orchestrator's contract**: what each call passes (the conversation history, the inputs, the routing
  description) is a fact of the specialist called, compared like any other. Told apart: a call to one not in the
  folder, a specialist nobody calls, a routing description under 80 characters.
- **Flows**: what a flow calls (connectors, operations, HTTP hosts, another flow) is compared too; a flow with no
  `Response` is told.
- **Unused**: a topic nobody can reach, a tool the model cannot choose, a variable no file names, a flow no node calls,
  a node or a component switched off. Never a pattern nor a solo.
- **Telemetry by name**: each event is compared by its name with the agent's own name taken out
  («RhFerias_OnError» and «RhFolha_OnError» are «‹name›_OnError»), and each field of its record too. A
  spelling that differs only in case or separators is asked about: «the same event?».
- A child agent's facts are the child's. A file it cannot read — broken YAML, a kind Copilot Studio does not have — is
  told, and the rest is read anyway.

The keys and their names are in [references/keys.md](../../skills/agent-review/references/keys.md); the profile in
[references/profile.md](../../skills/agent-review/references/profile.md); the review file in
[references/format.md](../../skills/agent-review/references/format.md).

## Install and use

agent-review is one of the six skills of the [dna](../../README.md) plugin. **Claude Code:**

```
/plugin marketplace add ruinosus/dna
/plugin install dna@dna
```

Then ask: "compare our Copilot Studio agents in ./agents". Or, with no Claude at all — in a clone of this repository,
or with npm:

```
node skills/agent-review/scripts/build.mjs agents/ --all --profile team.standard.yaml --lang pt
npx @ruinosus/dna agent-review agents/ --all
```

**Bring what you already have:**

```
node skills/agent-review/scripts/build.mjs agents/ --declared inventory.csv --declared team.xlsx   # proposes d1, d2…
node skills/agent-review/scripts/build.mjs agents/ --declared team.xlsx --take all                 # writes them
node skills/agent-review/scripts/build.mjs agents/ --all --telemetry events.csv                    # what fired
node skills/agent-review/scripts/build.mjs agents/ --all --evals evaluations/                       # the certifications
```

`--declared` reads the admin center's inventory or the team's own spreadsheet (CSV with `,` or `;`, or .xlsx, no
template): the agent's column is found by its values, every other column becomes a declared fact with its file and line.
`--evals <folder>` reads the exports of Copilot Studio's Evaluate tab — who passed how many, by method, the counts
only — for the résumés' certifications and a rule `has: "eval:*"`. `--telemetry` reads one export of Application Insights — the query is in
[references/telemetry.md](../../skills/agent-review/references/telemetry.md) — and holds for that run only.

The outputs hold the client's data: keep them in the client's environment. The
[Microsoft skills for Copilot Studio](https://github.com/microsoft/skills-for-copilot-studio) are recommended to
explain a kind or a pattern; agent-review works without them.

## Develop

```
npm install       # at the repository root: the six skills are npm workspaces
npm run assets -w dev/agent-review/tools   # scripts/engine.mjs, assets/map.html, the lesson page, references/keys.md
npm run check -w dev/agent-review/tools    # the engine's checks, the examples, the way back, a clean copy, no network
```

The source is `dev/agent-review/src/` (TypeScript); the example agents are fictional, made from Microsoft's MIT templates
(`dev/agent-review/fixtures/` has their answer key and the script that writes them).

## License

MIT. `skills/agent-review/vendor/microsoft/` holds the Copilot Studio schema and its reader from
microsoft/skills-for-copilot-studio, under its MIT license (see the NOTICE there).
