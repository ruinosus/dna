<h1 align="center">DNA — Domain Notation of Anything</h1>

<p align="center"><b>A process, written as files you can check: the way of working, the customer's journey, the incident
drill, the «what if» simulation, the Copilot Studio agents compared and the solution that puts them together — each
checked as it is written, and shown as one HTML file that opens offline. Eight Agent Skills for Claude.</b></p>

<p align="center">
  <img src="dev/visual-explainer/gallery/images/hero.gif" alt="A hand-drawn lesson drawing itself on a board, stroke by stroke" width="760">
</p>

<p align="center">
  A Claude Code plugin of <a href="https://agentskills.io">Agent Skills</a>, also for claude.ai, the Claude API and other
  tools that load skills.<br><a href="https://ruinosus.github.io/dna/">Open the gallery</a> to play every example.
</p>

---

## The eight skills

| Skill | Ask for | You get |
|---|---|---|
| [visual-explainer](dev/visual-explainer/README.md) | "explain compound interest by drawing it" | a hand-drawn lesson that appears stroke by stroke, chapter by chapter, with values you can move |
| [visual-pitch](dev/visual-pitch/README.md) | "draw the architecture so I can present it to the client" | a pitch, an architecture, a decision, data, a timeline or a story drawn to be shown — it opens presenting, and becomes a PowerPoint |
| [incident-drill](dev/incident-drill/README.md) | "make a drill from our checkout runbook" | an incident drill to play, with a clock and choices, and a debrief of what the runbook does not say |
| [way-of-working](dev/way-of-working/README.md) | "who approves what in our delivery?" | a team's way of working — stages, gates, roles, outputs — as a checkable file, a map, a workbook and a lesson |
| [service-blueprint](dev/service-blueprint/README.md) | "where does our onboarding hurt?" | a customer journey and who makes each moment happen on stage, backstage and in the systems |
| [agent-review](dev/agent-review/README.md) | "which of our Copilot Studio agents is off the pattern?" | the agents compared: what repeats, who is off it, the contract, the telemetry, what nobody uses — a map, a workbook to decide in, and a lesson; Node alone, no model |
| [process-simulation](dev/process-simulation/README.md) | "what if the assistant answered half the HR questions?" | a process to watch: items arriving, queues forming, people and assistants at work, a slider for every control, the ranges of many runs and the scenarios side by side — and, in Claude Code, a mod that checks every `.sim` as it is written |
| [solution](dev/solution/README.md) | "put our HR self-service together as one solution" | one process seen by every skill: a `.solution.yaml` that names the way, the simulation, the journey, the drill and the agents, checks each with its skill, says which fell behind the way, and makes one page with a tab per piece — with solution accelerators to start from |

Claude picks the skill by what you ask. To call one by name: `/dna:visual-pitch …`.

In Claude Code (2.1.287 or later) the plugin also carries a **mod**: every recipe Claude writes (`.way.yaml`,
`.blueprint.yaml`, `.drill.yaml`, `.chalk`, a visual-explainer `.json`, a `.sim`) is checked first by its skill and refused
with the messages when it breaks its format; in a repository that runs the names audit, a write with a name of your
private list is refused (`/names` says what it watches); a way of working or a service blueprint opens a preview pane
(`/way-preview`, `/blueprint-preview`); `/agent-review <folder> [--profile <file>]` shows agent-review's comparison in a pane, with the team's profile and a toast when an
agent edited there changes it; `/drill <file>` plays an incident drill in a pane, to its debrief; `/lenses <file.way.yaml>` shows a way of
working as a simulation, a service blueprint and a drill, and writes each beside it; and `/simulate` and
`/simulation-preview` run and show a `.sim`, with a −/+ for each control that runs it again; `/solution <file>` shows a
solution's pieces, each with where it stands.
Elsewhere the skills work without it.

<p align="center">
  <img src="https://ruinosus.github.io/dna/visual-pitch/thumbs/pitch-pharmacy-queue.png" alt="A hand-drawn pitch ending on «pilot: 5 stores, 3 months»" width="400">
  <img src="https://ruinosus.github.io/dna/way-of-working/images/feature-delivery-map.png" alt="A way of working as a map: stages, gates and who approves them" width="400">
</p>

## Install

**Claude Code** — all seven at once:

```
/plugin marketplace add ruinosus/dna
/plugin install dna@dna
```

**VS Code (GitHub Copilot)** — the same plugin, in agent mode: run **Chat: Add Plugin Marketplace** with
`ruinosus/dna` (or add it to `chat.plugins.marketplaces` in your settings), then install **dna** from
Agent Customizations › Browse. The Copilot CLI takes the same marketplace:

```
copilot plugin marketplace add ruinosus/dna
copilot plugin install dna@dna
```

**claude.ai** — each skill is a zip in the [latest release](https://github.com/ruinosus/dna/releases)
(`visual-explainer.zip`, `visual-pitch.zip`, …): Settings › Capabilities › Skills › Upload, with code execution on.
**Claude API**: the same zips with the Skills API. **Other tools** (Codex, Cursor, Gemini CLI…): copy
`skills/<skill>` where the tool reads skills; they need Node.js 18 or later.

**npm** — the same builds, outside Claude:

```
npx @ruinosus/dna visual-pitch pitch.chalk --pptx steps
npx @ruinosus/dna way-of-working team.way.yaml --all
npx @ruinosus/dna agent-review agents/ --all
npx @ruinosus/dna process-simulation hr.sim --lang pt
```

The drawing engine alone, to embed lessons in a page, is the [visual-explainer](https://www.npmjs.com/package/@ruinosus/visual-explainer)
package (it also powers the VS Code and Obsidian extensions).

## From house-lights

Until 1.17 this was **house-lights**, with theatre names. 2.0.0 is the same work under DNA, with plain names:

| Before | Now |
|---|---|
| plugin `house-lights@house-lights` | `dna@dna` (`/plugin marketplace add ruinosus/dna`) |
| npm `house-lights` · `chalk-talk` | `@ruinosus/dna` · `@ruinosus/visual-explainer` |
| chalk-talk · back-of-napkin · gates-and-handoffs | visual-explainer · visual-pitch · way-of-working |
| service-blueprint · dress-rehearsal · cast-list | service-blueprint · incident-drill · agent-review |
| box-office · opening-night | process-simulation · solution |
| `/sim` · `/sim-preview` · `/cast` | `/simulate` · `/simulation-preview` · `/agent-review` |

**Every file you wrote still reads.** A recipe now says what it is under DNA's header — `apiVersion:
github.com/ruinosus/dna/v1`, a `kind` and the name in `metadata.name` — and the `format:` line of before (`stage-door/v1`,
`front-of-house/v1`, `dress-rehearsal/v1`, `cast-list/profile-v1`, `opening-night/v1`…) is still read. To rewrite a
file's header, `--upgrade --write` in its skill. In Claude Code: add the new marketplace, install `dna@dna` and remove
the old plugin (`/plugin uninstall house-lights@house-lights`). The older repositories (chalk-talk, back-of-napkin,
stage-door, front-of-house, dress-rehearsal) and house-lights itself point here.

## Em português

Oito skills para mostrar uma ideia a alguém: **visual-explainer** ensina desenhando, **visual-pitch** desenha para
apresentar (e vira PowerPoint), **incident-drill** transforma o runbook num ensaio de incidente, **way-of-working**
mapeia o jeito de trabalhar do time, **service-blueprint** mapeia a jornada do cliente e **agent-review** compara os
agentes do Copilot Studio (o que se repete, quem está fora do padrão), **process-simulation** simula um processo para perguntar «e se»
(filas, pessoas, assistentes e custos) e **solution** junta tudo numa solution: o processo visto por todas as
skills, numa página só, com accelerators para começar. Peça em português ("desenha a
decisão entre as duas opções", "monta o blueprint da devolução"): a tela segue o idioma da receita. A instalação é a
de cima.

## Develop

The eight skills are npm workspaces; each one's tools are in `dev/<skill>/tools`.

```
npm install
npm run assets      # the generated files of each skill (visual-explainer first: the others take its engine from here);
                    # again after a pull or a branch switch, since the built files are not kept in git
npm run check       # every skill's checks, and dev/dna: one version, the npm package, npx @ruinosus/dna
npm run typecheck
npm run site        # docs/: a gallery per skill and the front page (made here, never kept in main)
npm run pages       # docs/ to the gh-pages branch, which GitHub Pages serves
npm run zip         # dist/<skill>.zip for claude.ai and dist/dna.zip
npm run linux       # the builds as in a cloud sandbox (Linux, root, Playwright's Chromium); needs Docker
npm run audit       # before a push: no name from your local list in the tracked files
claude plugin eval . --scaffold --allow-tools Bash Write Edit --runs 1   # the evals in evals/, all seven skills loaded
                    # (--scaffold runs the cases' own setup: agent-review's copies its example agents in)
```

The engine's source is not published yet, so `npm run assets` works only where it is; everything else works from
this repository alone. What changed: [CHANGELOG.md](CHANGELOG.md); before 1.0.0, `dev/<skill>/CHANGELOG.md`.

## License

MIT. Third parties: Rough.js (MIT); the fonts Caveat and Shantell Sans (SIL Open Font License); lottie-web (MIT); the
animated emoji are Animated Noto Emoji by Google (CC BY 4.0); pptxgenjs (MIT, with JSZip under MIT); the Copilot Studio
schema and its reader in `skills/agent-review/vendor/microsoft` (MIT, Microsoft Corporation).
