# stage-door

A team's way of working, clear and checkable — the command behind the
[stage-door skill](https://github.com/ruinosus/stage-door). See the [gallery](https://ruinosus.github.io/stage-door/).

```
npx stage-door team.way.yaml --check                 # only check it
npx stage-door team.way.yaml                         # check it, and make the map (team.html, offline)
npx stage-door team.way.yaml --all [--lang pt]       # the map, the workbook (team.xlsx) and the lesson (team.lesson.html)
npx stage-door team.way.yaml --from edited.xlsx      # each change the edited workbook makes, with its key
npx stage-door team.way.yaml --from edited.xlsx --take <key>,<key>   # write the chosen ones (or --take all)
```

A problem in the file says its line (exit 1); what does not hold — a gate nobody approves, a stage that delivers nothing,
DEV/QA/PRD as phases — is printed as «to look at». Node.js 18 or later, nothing else. The format is
[`format.schema.json`](https://github.com/ruinosus/stage-door/blob/main/skills/stage-door/references/format.schema.json).

MIT.
