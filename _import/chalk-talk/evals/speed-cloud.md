# Speed in claude.ai (by hand)

The `speed-*` cases run in Claude Code with `claude plugin eval` and `kit/tools/eval-metrics.mjs`. claude.ai has no eval
runner, so the same requests are run there by hand, in a new chat each, with the skill's zip installed.

## The requests

1. `Desenha pra mim como funciona a cadeia de suprimentos de um cafezinho, da fazenda até a xícara.`
2. `Draw how a web cache works, so I can show it to a new teammate.`
3. `Explica juros compostos desenhando, com a taxa mensal que eu possa mexer.`
4. `Draw the TCP three-way handshake.`
5. `Turn this into a lesson I can step through, one chapter per stage.` followed by the flowchart of
   `speed-mermaid-en/prompt.md`.
6. `Quero explicar frações para a minha turma do 6º ano, desenhando.` — this one must **ask** before drawing.

## What to write down for each

| Measure | How |
|---|---|
| Seconds to the first drawing | a stopwatch from sending the request until the first `.html` is offered |
| Files read before writing | the `references/…` files Claude opens (the tool calls, expanded) before it writes the recipe |
| Rounds of fixes | how many times `build.mjs` runs after the first one |
| Quality | open the lesson: does it pass the case's `graders/quality.md`? (yes / no) |
| The review | the last build's `review` line: `✓`, `!`, `✗ not checked` or `• no browser` |

Before 0.12.0 a request draws only after a round of questions and an outline; write down the time to the first
drawing including those rounds (answer «you decide» and «go» at once).
