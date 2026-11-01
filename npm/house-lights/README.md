# house-lights

The command behind the [house-lights](https://github.com/ruinosus/house-lights) skills: five ways of showing an idea
to people, each one a file you write and an HTML page that opens offline. See the
[gallery](https://ruinosus.github.io/house-lights/).

```
npx house-lights <skill> <file> [options]      # the options are the skill's own; with no skill, the list
```

| Skill | What it makes |
|---|---|
| `chalk-talk` | a hand-drawn lesson that appears stroke by stroke, with chapters and values to move |
| `back-of-napkin` | a drawing to present: a pitch, an architecture, a decision, data, a timeline or a story |
| `dress-rehearsal` | an incident drill to play, made from a runbook, and its debrief |
| `gates-and-handoffs` | a team's way of working: stages, gates, roles and outputs, with a workbook |
| `service-blueprint` | a customer journey and who makes each moment happen, with a workbook |

```
npx house-lights chalk-talk lesson.chalk                       # lesson.html, checked and offline
npx house-lights chalk-talk lesson.chalk --svg                 # an SVG that draws itself, for a README
npx house-lights back-of-napkin pitch.chalk                    # pitch.html, opens presenting (PageDown, speaker notes)
npx house-lights back-of-napkin pitch.chalk --pptx steps       # pitch.pptx: static, steps or video, notes included
npx house-lights dress-rehearsal checkout.drill.yaml --all     # the game and the facilitator's script
npx house-lights gates-and-handoffs team.way.yaml --all        # the map, the workbook (.xlsx) and the lesson
npx house-lights gates-and-handoffs team.way.yaml --from edited.xlsx   # what the edited workbook changes
npx house-lights service-blueprint returns.blueprint.yaml --all       # the map, the workbook and the lesson
```

Exit codes: 0 made and checked; 1 the file breaks its format (each problem with its line); 2 the command line is
wrong; 3 made, with something to fix. Chrome, Chromium or Edge, when installed, lets a build check the drawing and make snapshots and PowerPoint.
Node.js 18 or later, nothing else to install.

The drawing engine alone (to embed lessons in a page, VS Code or Obsidian) is the
[chalk-talk](https://www.npmjs.com/package/chalk-talk) package.

**Em português:** os mesmos comandos, com `--lang pt` nas três que fazem mapa e jogo. As receitas podem ser escritas
em português; a tela segue o `locale` da receita.

MIT.
