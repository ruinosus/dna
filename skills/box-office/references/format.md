# The .sim format, v1.1

A `.sim` file is a 10 to 25 line recipe that describes a process (what arrives, where it goes, who handles it, what it costs). `scripts/build.mjs` turns it, in seconds, into an animated simulation in the browser with "what if" controls.

Audience: whoever decides whether an agent or an automation is worth it (manager, client, steering committee) and will not read a spreadsheet.

v1.1 is v1 plus the four decisions the working prototype forced (see "Changes since v1" at the end).

## Principles

1. **The model writes, the engine draws.** The recipe holds no free code; all the weight sits in a deterministic engine.
2. **Mermaid speed.** Seconds to write and seconds to see; a typical recipe is under 25 lines.
3. **Readable by people.** A manager understands a recipe without training, and hand editing is normal.
4. **Reproducible.** The same recipe and seed always produce the same simulation, which enables snapshots and regression tests.
5. **Honest about being a model.** Results are ranges across several seeded runs, not single numbers.
6. **Errors the model fixes on its own.** The validator returns short, actionable messages so the write, check, fix loop closes without a human.
7. **English canonical, bilingual by design.** The canonical recipe is in English so global enterprise clients can adopt it as is. pt-BR is a first-class locale for keywords, screen labels and validator messages, and converts to and from English without loss.

## Grammar

One instruction per line. `#` starts a comment. Indentation only inside route branches and `labels` blocks.

| Block | Syntax | Example |
| --- | --- | --- |
| Header | `sim "name"`, `lang`, `horizon`, `seed`, `currency` | `sim "HR tickets"` · `horizon 1 year` |
| Arrival | `arrive item rate [during Ah-Bh] [peak when xfactor]... [-> step]` | `arrive ticket 500k/year peak jan,jul x1.8` |
| Mix | `mix attribute: value pct, ...` (must add up to 100%) | `mix intent: balance 30%, other 70%` |
| Resource | `pool name qty [shift Nh/day or Ah-Bh] [days mon-fri] [cost value/period]` | `pool analysts 100 shift 8h/day cost 4000/month` |
| Step | `step name [by resource] time duration [cost value]` | `step analyst by analysts time ~25min` |
| End | `end name` | `end resolved` |
| Simple route | `from -> to` | `analyst -> resolved` |
| Branching route | `from ->` then, indented, `to pct`, `to $knob` or `to rest` | `knowledge ->` · `answered $knowledge_rate` · `hr_review rest` |
| Route by attribute | `from ->` then `when attribute = value to` and `otherwise to` | `when intent = balance workday_read` |
| Abandonment | `step abandon after duration -> end` | `analyst abandon after 48h -> abandoned` |
| Control | `knob name min..max = initial`, used anywhere as `$name` | `knob knowledge_rate 0%..90% = 50%` |
| Scenario | `scenario "name": knob = value, ...` | `scenario "No knowledge answers": knowledge_rate = 0%` |
| Metric | `show metric` | `show wait p90 at analyst` |
| Labels | `labels locale:` then, indented, `id: display text` | `labels pt-BR:` · `analyst: Analista de RH` |

Rules:

- **Entry.** Items enter the step named after `->` on the `arrive` line, or the first declared `step` when there is none.
- **Capacity.** A step without `by` has unlimited capacity (the usual case for an AI agent). With `by`, each item takes one unit of the resource and waits in a FIFO queue when none is free.
- **Costs.** `cost` on a step is per item. `cost` on a resource is per unit per period (100 analysts at 4000/month cost 400,000 a month).
- **Branches.** `rest` takes whatever is left to reach 100% and may appear once per route. A route whose branches use a `$knob` must have a `rest`.
- **Loops** are not allowed in v1.
- **Metrics:** `count end X`, `share end X` (share of all finished items), `wait pNN at X` (queue wait), `queue X` (average queue length), `utilization X` (busy time over on-shift capacity), `cost per day|week|month|year`.

## Time, rates and variability

| Form | Meaning |
| --- | --- |
| `25min` | Always exactly that long |
| `20..40min` | Uniform between the two |
| `~25min` | Exponential with a mean of 25 min (typical service variation) |

- **Units:** `s`, `min`, `h`, `hour`, `day`, `week`, `month` (30 days), `year` (365 days); decimals allowed (`1.5h`).
- **Rates:** `quantity/unit` with `k` and `m` suffixes (`500k/year`, `30/hour`). Arrivals are Poisson around the rate.
- **The stated rate is the average while arrivals are open.** `during` and `peak` reshape it without changing the total: `500k/year peak jan,jul x1.8` still means about 500,000 a year, with January and July 1.8 times busier than the other months.
- **Arrival window:** `during 7h-15h` means items only arrive between those hours. Without it, items arrive around the clock.
- **Peaks** match months (`jan,jul`), weekdays (`mon`, `mon-fri`) or hour ranges (`8h-10h`). Several peaks multiply.
- **Shifts:** `shift 8h/day` starts at 08:00; `shift 7h-15h` sets the window explicitly. `days mon-fri` limits the days. Off shift, nobody starts new work and the queue grows.
- **Calendar:** the simulated clock starts at 00:00 on Thursday, 1 January (non-leap year).

## Internationalization

| Layer | How it works |
| --- | --- |
| Keywords | `lang en` (default) or `lang pt-BR` picks the keyword set for the whole file. Never mix. |
| Numbers | Decimals use `.` in en and `,` in pt-BR. |
| Identifiers | Free text, never translated. |
| Display labels | Optional `labels en:` and `labels pt-BR:` blocks map ids to screen names. Both can live in the same file. |
| Screen | The viewer switches EN / PT; the run does not change. |
| Validator | Messages follow the recipe's `lang`. |
| Conversion | `node scripts/build.mjs file.sim --to en` rewrites keywords, units, weekdays and months, and round-trips exactly. |

Keyword map:

| en (canonical) | pt-BR |
| --- | --- |
| `sim` · `lang` · `horizon` · `seed` · `currency` | `sim` · `lang` · `horizonte` · `semente` · `moeda` |
| `arrive` · `during` · `peak` · `mix` | `chegada` · `durante` · `pico` · `mistura` |
| `pool` · `shift` · `days` | `equipe` · `turno` · `dias` |
| `step` · `by` · `time` · `cost` | `etapa` · `com` · `tempo` · `custo` |
| `end` · `rest` · `when` · `otherwise` · `abandon after` | `fim` · `resto` · `quando` · `senão` · `desiste após` |
| `knob` · `scenario` · `show` · `labels` | `controle` · `cenário` · `mostrar` · `rótulos` |
| `count` · `share` · `wait` · `at` · `queue` · `utilization` · `per` | `contagem` · `fração` · `espera` · `em` · `fila` · `utilização` · `por` |
| `hour` · `day` · `week` · `month` · `year` | `hora` · `dia` · `semana` · `mês` · `ano` |
| `mon tue wed thu fri sat sun` | `seg ter qua qui sex sáb dom` |
| `feb apr may aug sep oct dec` | `fev abr mai ago set out dez` |

## Validation

Errors block the run; warnings do not.

| Check | Severity |
| --- | --- |
| Unreadable line, bad duration, number, rate or calendar spec | error |
| Unknown step, end, pool or metric target | error |
| A step with no route; routes that loop | error |
| Branches that do not add up to 100% (no `rest`), `rest` twice, a `$knob` branch without `rest`, branches over 100% at the top of a control's range | error |
| Attribute route that does not cover every mix value and has no `otherwise` | error |
| Undeclared control; scenario setting an unknown control | error |
| Declared control never used; unreachable step; keyword from the other locale | warning |
| Average demand above a pool's on-shift capacity | warning |

## Engine

- Seeded discrete-event simulation (mulberry32 RNG, binary heap of events).
- Arrivals by thinning a non-homogeneous Poisson process.
- Abandonment is FIFO: everyone at a step has the same patience, so the head of the queue always leaves first. No per-item timer events.
- Wait samples use a 20,000-item reservoir per step.
- Speed: about 0.4 s per run for 500,000 arrivals in Chromium (Node 22 is several times slower).
- Ranges: the page runs 10 seeds, or 6 when a run has more than 200,000 arrivals, in background workers. Scenario comparisons use the same seeds.

## Out of scope for v1

| Not in v1 | When |
| --- | --- |
| Free code and expressions | Never |
| Priority and preemption between queues | v2 |
| Items that split or merge | v2 |
| Different patience per item | v2 |
| Real data from CSV (`from csv`) | v2 |
| Several linked processes | v2 |
| Automatic optimization | v3 |
| Continuous dynamics (stocks, flows) | Another format |
| Narrated chapters | Integration with the chalk-talk engine |

## Changes since v1

| Gap found while building the prototype | Decision in v1.1 |
| --- | --- |
| Customers arrived at 3 a.m. at a café that opens at 7 | New `during Ah-Bh` clause on `arrive` (`durante` in pt-BR) |
| Nothing said which step items enter | `arrive ... -> step`, defaulting to the first declared step |
| `shift 8h/day` had no start time | Starts at 08:00; `shift 7h-15h` sets it explicitly |
| `500k/year peak x1.8` produced about 566k a year | The stated rate is the average; peaks redistribute it |
| 20 seeds was too slow for large models | 10 seeds, or 6 above 200,000 arrivals per run |
