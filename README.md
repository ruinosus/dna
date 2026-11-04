<h1 align="center">house-lights</h1>

<p align="center"><b>The lights that come up so everyone can see. Seven skills for Claude that show an idea to people — by
drawing it, playing it, mapping it, comparing it or simulating it — each one an HTML file that opens offline.</b></p>

<p align="center">
  <img src="dev/chalk-talk/gallery/images/hero.gif" alt="A hand-drawn lesson drawing itself on a board, stroke by stroke" width="760">
</p>

<p align="center">
  A Claude Code plugin of <a href="https://agentskills.io">Agent Skills</a>, also for claude.ai, the Claude API and other
  tools that load skills.<br><a href="https://ruinosus.github.io/house-lights/">Open the gallery</a> to play every example.
</p>

---

## The seven skills

| Skill | Ask for | You get |
|---|---|---|
| [chalk-talk](dev/chalk-talk/README.md) | "explain compound interest by drawing it" | a hand-drawn lesson that appears stroke by stroke, chapter by chapter, with values you can move |
| [back-of-napkin](dev/back-of-napkin/README.md) | "draw the architecture so I can present it to the client" | a pitch, an architecture, a decision, data, a timeline or a story drawn to be shown — it opens presenting, and becomes a PowerPoint |
| [dress-rehearsal](dev/dress-rehearsal/README.md) | "make a drill from our checkout runbook" | an incident drill to play, with a clock and choices, and a debrief of what the runbook does not say |
| [gates-and-handoffs](dev/gates-and-handoffs/README.md) | "who approves what in our delivery?" | a team's way of working — stages, gates, roles, outputs — as a checkable file, a map, a workbook and a lesson |
| [service-blueprint](dev/service-blueprint/README.md) | "where does our onboarding hurt?" | a customer journey and who makes each moment happen on stage, backstage and in the systems |
| [cast-list](dev/cast-list/README.md) | "which of our Copilot Studio agents is off the pattern?" | the agents compared: what repeats, who is off it, the contract, the telemetry, what nobody uses — a map, a workbook to decide in, and a lesson; Node alone, no model |
| [box-office](dev/box-office/README.md) | "what if the assistant answered half the HR questions?" | a process to watch: items arriving, queues forming, people and assistants at work, a slider for every control, the ranges of many runs and the scenarios side by side — and, in Claude Code, a mod that checks every `.sim` as it is written |

Claude picks the skill by what you ask. To call one by name: `/house-lights:back-of-napkin …`.

In Claude Code (2.1.287 or later) the plugin also carries a **mod**: every recipe Claude writes (`.way.yaml`,
`.blueprint.yaml`, `.drill.yaml`, `.chalk`, a chalk-talk `.json`, a `.sim`) is checked first by its skill and refused
with the messages when it breaks its format; in a repository that runs the names audit, a write with a name of your
private list is refused (`/names` says what it watches); and `/sim` and `/sim-preview` run and show a `.sim`.
Elsewhere the skills work without it.

<p align="center">
  <img src="https://ruinosus.github.io/house-lights/back-of-napkin/thumbs/pitch-pharmacy-queue.png" alt="A hand-drawn pitch ending on «pilot: 5 stores, 3 months»" width="400">
  <img src="https://ruinosus.github.io/house-lights/gates-and-handoffs/images/feature-delivery-map.png" alt="A way of working as a map: stages, gates and who approves them" width="400">
</p>

## Install

**Claude Code** — all seven at once:

```
/plugin marketplace add ruinosus/house-lights
/plugin install house-lights@house-lights
```

**VS Code (GitHub Copilot)** — the same plugin, in agent mode: run **Chat: Add Plugin Marketplace** with
`ruinosus/house-lights` (or add it to `chat.plugins.marketplaces` in your settings), then install **house-lights** from
Agent Customizations › Browse. The Copilot CLI takes the same marketplace:

```
copilot plugin marketplace add ruinosus/house-lights
copilot plugin install house-lights@house-lights
```

**claude.ai** — each skill is a zip in the [latest release](https://github.com/ruinosus/house-lights/releases)
(`chalk-talk.zip`, `back-of-napkin.zip`, …): Settings › Capabilities › Skills › Upload, with code execution on.
**Claude API**: the same zips with the Skills API. **Other tools** (Codex, Cursor, Gemini CLI…): copy
`skills/<skill>` where the tool reads skills; they need Node.js 18 or later.

**npm** — the same builds, outside Claude:

```
npx house-lights back-of-napkin pitch.chalk --pptx steps
npx house-lights gates-and-handoffs team.way.yaml --all
npx house-lights cast-list agents/ --all
npx house-lights box-office hr.sim --lang pt
```

The drawing engine alone, to embed lessons in a page, is the [chalk-talk](https://www.npmjs.com/package/chalk-talk)
package (it also powers the VS Code and Obsidian extensions).

## Moved here

These skills had a repository each until 1.0.0. `stage-door` is now **gates-and-handoffs** and `front-of-house` is
**service-blueprint**; their files keep working (the formats did not change). If you installed one of the old
plugins, install `house-lights` instead and remove the old one (`/plugin uninstall <old>@<old>`); the npm packages
`back-of-napkin`, `stage-door`, `front-of-house` and `dress-rehearsal` point to `npx house-lights`.

## Em português

Sete skills para mostrar uma ideia a alguém: **chalk-talk** ensina desenhando, **back-of-napkin** desenha para
apresentar (e vira PowerPoint), **dress-rehearsal** transforma o runbook num ensaio de incidente, **gates-and-handoffs**
mapeia o jeito de trabalhar do time, **service-blueprint** mapeia a jornada do cliente e **cast-list** compara os
agentes do Copilot Studio (o que se repete, quem está fora do padrão) e **box-office** simula um processo para perguntar «e se»
(filas, pessoas, assistentes e custos). Peça em português ("desenha a
decisão entre as duas opções", "monta o blueprint da devolução"): a tela segue o idioma da receita. A instalação é a
de cima.

## Develop

The seven skills are npm workspaces; each one's tools are in `dev/<skill>/tools`.

```
npm install
npm run assets      # the generated files of each skill (chalk-talk first: the others take its engine from here);
                    # again after a pull or a branch switch, since the built files are not kept in git
npm run check       # every skill's checks, and dev/house-lights: one version, the npm package, npx house-lights
npm run typecheck
npm run site        # docs/: a gallery per skill and the front page (made here, never kept in main)
npm run pages       # docs/ to the gh-pages branch, which GitHub Pages serves
npm run zip         # dist/<skill>.zip for claude.ai and dist/house-lights.zip
npm run linux       # the builds as in a cloud sandbox (Linux, root, Playwright's Chromium); needs Docker
npm run audit       # before a push: no name from your local list in the tracked files
claude plugin eval . --scaffold --allow-tools Bash Write Edit --runs 1   # the evals in evals/, all seven skills loaded
                    # (--scaffold runs the cases' own setup: cast-list's copies its example agents in)
```

The engine's source is not published yet, so `npm run assets` works only where it is; everything else works from
this repository alone. What changed: [CHANGELOG.md](CHANGELOG.md); before 1.0.0, `dev/<skill>/CHANGELOG.md`.

## License

MIT. Third parties: Rough.js (MIT); the fonts Caveat and Shantell Sans (SIL Open Font License); lottie-web (MIT); the
animated emoji are Animated Noto Emoji by Google (CC BY 4.0); pptxgenjs (MIT, with JSZip under MIT); the Copilot Studio
schema and its reader in `skills/cast-list/vendor/microsoft` (MIT, Microsoft Corporation).
