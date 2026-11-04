# dna

The command behind the [dna](https://github.com/ruinosus/dna) skills: seven ways of showing an idea
to people, each one an HTML page that opens offline. See the
[gallery](https://ruinosus.github.io/dna/).

```
npx @ruinosus/dna <skill> <file> [options]      # the options are the skill's own; with no skill, the list
npx @ruinosus/dna agent-review <agents-folder> [options]
```

| Skill | What it makes |
|---|---|
| `visual-explainer` | a lesson that draws itself, chapter by chapter, with values to move |
| `visual-pitch` | a drawing to present: a pitch, an architecture, a decision, data, a timeline or a story |
| `incident-drill` | an incident drill to play, made from a runbook, and its debrief |
| `way-of-working` | a team's way of working: stages, gates, roles and outputs, with a workbook |
| `service-blueprint` | a customer journey and who makes each moment happen, with a workbook |
| `agent-review` | Copilot Studio agents compared: what repeats, who is off a pattern, what is missing, with a workbook |
| `process-simulation` | a process to watch and ask «what if»: queues, people, assistants and costs, with sliders and scenarios |
| `solution` | a solution: one process seen by every skill, each piece checked, one page with a tab per piece |

```
npx @ruinosus/dna visual-explainer lesson.chalk                       # lesson.html, checked and offline
npx @ruinosus/dna visual-explainer lesson.chalk --svg                 # an SVG that draws itself, for a README
npx @ruinosus/dna visual-pitch pitch.chalk                    # pitch.html, opens presenting (PageDown, speaker notes)
npx @ruinosus/dna visual-pitch pitch.chalk --pptx steps       # pitch.pptx: static, steps or video, notes included
npx @ruinosus/dna incident-drill checkout.drill.yaml --all     # the game and the facilitator's script
npx @ruinosus/dna way-of-working team.way.yaml --all        # the map, the workbook (.xlsx) and the lesson
npx @ruinosus/dna way-of-working team.way.yaml --from edited.xlsx   # what the edited workbook changes
npx @ruinosus/dna service-blueprint returns.blueprint.yaml --all       # the map, the workbook and the lesson
npx @ruinosus/dna agent-review agents/ --profile team.standard.yaml --all     # the agents compared: map, workbook, lesson
npx @ruinosus/dna process-simulation hr.sim --lang pt                          # hr.process-simulation.html: the simulation, offline
npx @ruinosus/dna process-simulation hr.sim --run --set hr_partners=8          # the median and p10–p90 of each metric
npx @ruinosus/dna agent-review agents/ --from filled.xlsx --take all      # the decisions filled in Excel, kept
npx @ruinosus/dna way-of-working team.way.yaml --lens sim --write   # the way as a simulation (also blueprint, drill)
npx @ruinosus/dna solution --new service-desk my-desk             # start from a solution accelerator
npx @ruinosus/dna solution my-desk/service-desk.solution.yaml     # every piece checked, one page with them all
```

Exit codes: 0 made and checked; 1 the file breaks its format (each problem with its line); 2 the command line is
wrong; 3 made, with something to fix. Chrome, Chromium or Edge, when installed, lets a build check the drawing and make snapshots and PowerPoint.
Node.js 18 or later, nothing else to install.

The drawing engine alone (to embed lessons in a page, VS Code or Obsidian) is the
[visual-explainer](https://www.npmjs.com/package/@ruinosus/visual-explainer) package.

**Em português:** os mesmos comandos, com `--lang pt` nas quatro que fazem mapa e jogo. As receitas podem ser escritas
em português; a tela segue o `locale` da receita.

MIT.
