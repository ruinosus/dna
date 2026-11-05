---
name: process-simulation
description: Turns a process — what arrives, where it goes, who handles it, what it costs — into an animated what-if simulation that opens offline, from a short .sim recipe of 10 to 25 lines - items arriving, queues forming, people and assistants handling the work, a slider for every control, ranges across seeded runs (p10 to p90) and the scenarios side by side. In English or Portuguese. Use when someone wants to show whether an assistant, an automation or more people is worth it, to see where a queue forms, or to ask «what if» about a service desk, an approval, a back office or a counter ("simulate our HR tickets with the self-service assistant", "what if we had two more reviewers?", "simula a fila do RH com o agente").
license: MIT
compatibility: Needs code execution and Node.js 18 or later; nothing to install. In Claude Code (2.1.287 or later) the dna mod also checks every .sim as it is written and adds /simulate and /simulation-preview.
metadata:
  version: "2.3.0"
---

# process-simulation: a process you can watch, and ask «what if»

You write **one file**, `<id>.sim`: what arrives, the steps, who handles them, where each item goes, what it costs,
the controls to move and the metrics to show. `scripts/build.mjs` checks it, runs it and makes the page. You write only
the `.sim`.

Paths below are relative to this skill's folder (the folder this file is in). Write the recipe in English (`lang en`,
the default) or Portuguese (`lang pt-BR`) — never mixed — and pass `--lang pt` for a page whose screen starts in
Portuguese.

## 1. Read, then write the recipe

Read what the person gives (a description, a volume, a team, a cost). Then write the whole recipe at once
(`references/format.md`; `examples/` has four, from an HR help desk to an employee self-service with Workday):

- **What arrives** (`arrive`), with its rate and, when the material says so, its window (`during 7h-20h`) and its
  peaks (`peak mon x1.3`). The stated rate is the average: peaks reshape it, never add to it.
- **The kinds** of item (`mix`) when they go different ways, adding up to 100%.
- **Who works** (`pool`): how many, their shift, their days, their cost. A step with no pool has no limit — usually an
  assistant or a system.
- **The steps** (`step`), each with its time (`25min` exact, `20..40min` uniform, `~25min` typical variation) and its
  cost per item; **the ends** (`end`); **the routes** — simple, by share (`rest` takes what is left), by kind
  (`when … otherwise`), and who gives up after a wait (`abandon after 48h`).
- **The controls** (`knob`) are what the person wants to move — a rate, a team size — used as `$name`; **scenarios**
  set them («No assistant», «Two more reviewers»); **metrics** (`show`) are what decides: a share, a wait p90, a queue,
  a utilization, the cost per month.
- **Labels** (`labels en:`, `labels pt-BR:`) give each id its name on screen; keep them under about 22 characters.
- **Never present a made-up number as theirs.** When the material has no volume, time or cost, bet one, say so in a
  comment at the top («# The volumes are made up: replace them with your own») and ask for the real one.

- **Rework** is a route back: `review ->` · `work $sent_back` · `done rest`. Every step must still reach an end.
- **From a way of working:** a team's `.way.yaml` (way-of-working) becomes a draft recipe with
  `node ../way-of-working/scripts/build.mjs <id>.way.yaml --lens sim --write` — its stages, gates and roles, the
  rework of each gate, and every number a bet (`# bet:`) to replace.

## 2. Check, then run

```
node scripts/build.mjs <id>.sim --check
node scripts/build.mjs <id>.sim --run [--set knob=value …]
```

`--check` prints each error with what to do (exit 1) and the warnings (a control never used, a pool asked for more than
it can do). Fix every error and check again. `--run` gives the median and the p10 to p90 range of each metric over
seeded runs: the same recipe and seed always give the same numbers.

**A number someone can check.** `--run … --receipt <file.json>` also writes the run's receipt (the recipe's sha256, the
engine, the seed, the runs, the controls and the numbers); `--attest <receipt.json>` runs the recipe again from it and
says whether it holds — the recipe swapped, a control that is not one or out of its range, another engine, a number
that does not come out again (exit 3). When you quote a simulation's numbers to someone, give them the receipt. In an
OKF bundle (the solution's `--okf`) the simulation is an Attested Computation, and its attester does the same.

## 3. The page

```
node scripts/build.mjs <id>.sim [<another>.sim …] [--lang en|pt] [--out <folder>]
```

It writes `<id>.process-simulation.html`: one file that opens offline, on the first recipe (the others in its Example menu).
It draws the flow and animates the items; every control is a slider; the background runs give the ranges; the
scenarios are compared side by side; the screen switches between EN and PT; the recipe can be edited, translated and
copied on the page. Tell the person what to look at first (where the queue forms, the metric that decides) and that it
is **a model, not a forecast**: the ranges are honest about chance, not about the numbers put in.

## 4. Translate

```
node scripts/build.mjs <id>.sim --to pt-BR|en [--write]
```

The keywords, units, weekdays and months change; the ids and labels do not; the round trip is exact.

## In Claude Code

With the dna plugin, the mod checks every `.sim` you write or edit: a recipe with errors is refused with the
validator's messages — fix them and write it again; warnings pass with a toast. `/simulate [file.sim] [--seeds N]
[--set knob=value]` runs it at once and gives you the same numbers; `/attest <receipt.json> [file.sim]` says whether a
receipt holds; `/simulation-preview [file.sim]` opens a pane with the flow and a −/+ for each
control: a press runs the recipe again with the new value and shows the numbers.
