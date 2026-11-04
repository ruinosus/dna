# house-lights

The command behind the [house-lights](https://github.com/ruinosus/house-lights) skills: seven ways of showing an idea
to people, each one an HTML page that opens offline. See the
[gallery](https://ruinosus.github.io/house-lights/).

```
npx house-lights <skill> <file> [options]      # the options are the skill's own; with no skill, the list
npx house-lights cast-list <agents-folder> [options]
```

| Skill | What it makes |
|---|---|
| `chalk-talk` | a hand-drawn lesson that appears stroke by stroke, with chapters and values to move |
| `back-of-napkin` | a drawing to present: a pitch, an architecture, a decision, data, a timeline or a story |
| `dress-rehearsal` | an incident drill to play, made from a runbook, and its debrief |
| `gates-and-handoffs` | a team's way of working: stages, gates, roles and outputs, with a workbook |
| `service-blueprint` | a customer journey and who makes each moment happen, with a workbook |
| `cast-list` | Copilot Studio agents compared: what repeats, who is off a pattern, what is missing, with a workbook |
| `box-office` | a process to watch and ask «what if»: queues, people, assistants and costs, with sliders and scenarios |
| `opening-night` | a solution: one process seen by every skill, each piece checked, one page with a tab per piece |

```
npx house-lights chalk-talk lesson.chalk                       # lesson.html, checked and offline
npx house-lights chalk-talk lesson.chalk --svg                 # an SVG that draws itself, for a README
npx house-lights back-of-napkin pitch.chalk                    # pitch.html, opens presenting (PageDown, speaker notes)
npx house-lights back-of-napkin pitch.chalk --pptx steps       # pitch.pptx: static, steps or video, notes included
npx house-lights dress-rehearsal checkout.drill.yaml --all     # the game and the facilitator's script
npx house-lights gates-and-handoffs team.way.yaml --all        # the map, the workbook (.xlsx) and the lesson
npx house-lights gates-and-handoffs team.way.yaml --from edited.xlsx   # what the edited workbook changes
npx house-lights service-blueprint returns.blueprint.yaml --all       # the map, the workbook and the lesson
npx house-lights cast-list agents/ --profile team.cast.yaml --all     # the agents compared: map, workbook, lesson
npx house-lights box-office hr.sim --lang pt                          # hr.box-office.html: the simulation, offline
npx house-lights box-office hr.sim --run --set hr_partners=8          # the median and p10–p90 of each metric
npx house-lights cast-list agents/ --from filled.xlsx --take all      # the decisions filled in Excel, kept
npx house-lights gates-and-handoffs team.way.yaml --lens sim --write   # the way as a simulation (also blueprint, drill)
npx house-lights opening-night --new service-desk my-desk             # start from a solution accelerator
npx house-lights opening-night my-desk/service-desk.solution.yaml     # every piece checked, one page with them all
```

Exit codes: 0 made and checked; 1 the file breaks its format (each problem with its line); 2 the command line is
wrong; 3 made, with something to fix. Chrome, Chromium or Edge, when installed, lets a build check the drawing and make snapshots and PowerPoint.
Node.js 18 or later, nothing else to install.

The drawing engine alone (to embed lessons in a page, VS Code or Obsidian) is the
[chalk-talk](https://www.npmjs.com/package/chalk-talk) package.

**Em português:** os mesmos comandos, com `--lang pt` nas quatro que fazem mapa e jogo. As receitas podem ser escritas
em português; a tela segue o `locale` da receita.

MIT.
