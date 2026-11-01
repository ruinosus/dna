# front-of-house

A service blueprint, clear and checkable — the command behind the
[front-of-house skill](https://github.com/ruinosus/front-of-house). See the [gallery](https://ruinosus.github.io/front-of-house/).

```
npx front-of-house returns.blueprint.yaml --check                 # check it (each problem with its line)
npx front-of-house returns.blueprint.yaml                         # the map: returns.html, offline
npx front-of-house returns.blueprint.yaml --all --lang pt         # map, workbook (.xlsx) and lesson
```

The format is [`format.md`](https://github.com/ruinosus/front-of-house/blob/main/skills/front-of-house/references/format.md).
Node.js 18 or later, nothing else. MIT.
