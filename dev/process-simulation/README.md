# process-simulation

Write a process as a short `.sim` recipe — what arrives, the steps, who handles them, where each item goes, what it
costs — and watch it run: items arriving, queues forming, people and assistants handling the work, a slider for every
control, the p10 to p90 range of many seeded runs and the scenarios side by side. One HTML file that opens offline. The
recipe is in English or Portuguese (`lang pt-BR`), and the screen switches between EN and PT.

```
sim "Employee Self-Service with Workday"
arrive request 1500/day during 7h-20h peak mon x1.3
mix intent: balance 30%, time_off 20%, profile 20%, dependents 5%, facilities 10%, other 15%
pool hr_partners $hr_partners shift 8h/day days mon-fri cost 5000/month
step ess time ~20s cost 0.03
step hr_review by hr_partners time ~30min
…
knob knowledge_rate 0%..90% = 50%
scenario "Better knowledge": knowledge_rate = 80%
show wait p90 at hr_review
```

The whole example is [`employee-self-service.sim`](../../skills/process-simulation/examples/employee-self-service.sim): the
scenarios of [Microsoft's Employee Self-Service sample](https://github.com/microsoft/CopilotStudioSamples/tree/main/EmployeeSelfServiceAgent)
(MIT), with made-up numbers. The format is [`references/format.md`](../../skills/process-simulation/references/format.md).

| You run | You get |
|---|---|
| `node skills/process-simulation/scripts/build.mjs hr.sim [--lang pt]` | `hr.process-simulation.html`, opening on that recipe |
| `… hr.sim --check` | the validator's errors (exit 1) and warnings |
| `… hr.sim --run [--seeds N] [--set knob=value]` | the median and p10 to p90 of each metric |
| `… hr.sim --to pt-BR [--write]` | the recipe in the other language, round trip exact |
| `… hr.sim --run … --receipt r.json` | the same, and the run's receipt: the recipe's sha256, the engine, the seed, the runs, the controls, the numbers |
| `… hr.sim --attest r.json [--json]` | the recipe run again from the receipt: attested (exit 0) or the reason it is not (exit 3) |

## In Claude Code: the mod

The dna plugin carries a mod (Claude Code 2.1.287 or later), in `hooks/`:

| Feature | What it does |
| --- | --- |
| Recipe guard | When Claude writes or edits a `.sim`, the validator checks the result first. A recipe with errors is refused with the validator's messages, so Claude fixes it and writes again. Warnings pass, with a toast. It fails open: if the guard itself throws, the write goes through. |
| `/simulate [file.sim] [--seeds N] [--set knob=value]` | Runs the recipe at once, with no model turn, and prints the median and the p10 to p90 range of each metric; Claude receives the same numbers. It stops at 7 s. |
| `/attest <receipt.json> [file.sim]` | The verdict on a receipt: `--attest`, run on the host. |
| `/simulation-preview [file.sim]` | A pane with the recipe's flow: an SVG in the desktop app, VS Code and mobile, text lines in the terminal, the validator's messages and an EN/PT switch. It also opens after the first valid `.sim` written in a session. |

In GitHub Copilot, claude.ai and the API the skill works without it: the script checks and runs the recipe the same
way.

## Develop

```
npm run assets -w dev/process-simulation/tools     # src/ → assets/process-simulation.html, scripts/engine.mjs, hooks/process-simulation/sim-core.js
npm run check -w dev/process-simulation/tools      # the engine's checks, the examples, the page in a browser, the mod's tests
npm run typecheck -w dev/process-simulation/tools  # the mod, once Claude Code has laid .claude-plugin/types/ (claude --plugin-dir .)
node dev/process-simulation/checks/run.mjs --update   # an engine change that moves numbers: new snapshots, said in the commit
```

The engine and the parser (`src/engine.js`, `src/parser.js`) are browser-global scripts with no DOM: the page inlines
them, its workers load the engine from a Blob, and `assets.mjs` wraps them as an ES module for the script and the
mod — change them in `src/` only. Same recipe and seed, same numbers. A validator message exists in English and
Portuguese (`MSG` in `src/parser.js`), with a case in `checks/run.mjs`; a new keyword needs its entries in `PT2EN`
and `EN2PT` and a row in the format's keyword map.

Known: Node runs the engine several times slower than Chromium; a pool's utilization can pass 100% when work goes on
past the end of its shift; the metric cards refresh every 250 ms, the drawing every frame.
