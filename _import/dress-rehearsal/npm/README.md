# dress-rehearsal

Test your incident runbook by playing it — the command behind the
[dress-rehearsal skill](https://github.com/ruinosus/dress-rehearsal). [Play the examples](https://ruinosus.github.io/dress-rehearsal/).

```
npx dress-rehearsal checkout.drill.yaml --check                 # check it (each problem with its line)
npx dress-rehearsal checkout.drill.yaml                         # the game: checkout.drill.html, offline
npx dress-rehearsal checkout.drill.yaml --all --lang pt         # the game and the facilitator's script
```

The format is [`format.md`](https://github.com/ruinosus/dress-rehearsal/blob/main/skills/dress-rehearsal/references/format.md).
Node.js 18 or later, nothing else. MIT.
