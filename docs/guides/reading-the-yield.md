# Reading the yield — cost, return, and when the honest answer is "not calculable"

`dna.runtime.roi` is the one place where four separate facts meet: what a turn
**cost** (tokens, from `dna_turn`), what it **achieved** (`outcome`, since
revision 0012), what a human **thought of it** (`dna_approval`), and what one
successful outcome is **worth** (`Copilot.value_per_outcome`).

Most of what this module does is refuse to make things up.

```python
from dna.runtime.roi import ModelPrice, read_yield, render, sample_from_turns

sample = sample_from_turns(turn_rows, approval_rows)
reading = read_yield(
    sample,
    copilot=copilot_spec,           # the Copilot's `spec`
    app=app_spec,                   # the `App` its `runs_in` points at
    prices={"gpt-5-mini": ModelPrice(0.25, 2.0, "USD")},
)
print("\n".join(render(reading)))
```

---

## The three market techniques, and which one this answers

ROI for an agent is not measured by looking at the agent. It is measured by
counting the work it finished on its own and multiplying by what a human would
have cost doing the same. There are three established ways to do it, and they
are **not** worth the same:

| technique | what it measures | what it requires | rigour |
|---|---|---|---|
| **containment / deflection** | % of tasks completed without escalating | a definition of "completed" + an escalation signal | **proxy** |
| **AHT reduction** | the same work, with and without the agent | a baseline | better proxy |
| **holdout / A-B** | causal difference in a business metric | half your users without the agent | **proof** |

> **This reading answers the FIRST, and only the first.**
> `dna.runtime.roi.TECHNIQUE_ANSWERED` says so in code, and `render()` prints
> it under every report.

The other two are declared *not answered*, with the reason, in
`TECHNIQUES_NOT_ANSWERED`: there is no baseline of the same work done without
the agent (so no AHT reduction), and there is no volume for a holdout.

⚠️ **Most companies do the first and call it ROI.** That is a defensible proxy,
not a proof — and the difference has to be written where the number appears, not
only in a document nobody opens next to the dashboard. That is why every proxy
number carries `basis=PROXY` and `render()` prints the label on the same line.

---

## The three rules

### 1. No declared value → NOT CALCULABLE, with the reason

`Copilot.value_per_outcome` (`human_minutes`, `hourly_cost`, `currency`) is the
**only number in the whole chain that cannot be measured**: what a human would
have spent doing the work by hand exists in no telemetry, because the system
that would have timed it is the one that replaced the human.

So it is declared, or there is no ROI:

```python
reading.value
# NotCalculable(reason="no_value_per_outcome",
#               detail="this Copilot never declared what an outcome is worth …",
#               missing=("value_per_outcome",))
```

Never zero, never an estimate. A presumed zero would render every copilot in the
fleet as pure cost. And **half a declaration is not half a value** — missing
`currency`, the reading refuses rather than defaulting to USD, which would be
wrong by a factor of five in the first fleet that mixes two.

A *declared* zero (`human_minutes: 0`) is an answer, and it passes. Absent is not
zero; zero is zero.

### 2. Every proxy-derived number carries its label

`Number` cannot be constructed without `basis` and `source` — the constructor
raises. There are four bases:

| basis | meaning |
|---|---|
| `MEASURED` | counted in the record: `dna_turn`, `dna_approval` |
| `DECLARED` | stated by a human in a descriptor: `value_per_outcome`, `can_sleep` |
| `PROXY` | **derived, and not measuring what it looks like it measures** |
| `CONSTANT` | measured once, elsewhere, carried by hand — see below |

Containment and HITL acceptance are `PROXY`. Containment measures *work finished
without escalating*, not *value delivered*; acceptance measures *agreement of
whoever reviewed*, not *quality*. `render()` prints `[PROXY]` on the same line as
the number, because a `basis` stored on an object and dropped from the screen is
rule 2 obeyed where nobody is looking.

### 3. ⭐ Empty is never zero

**Measured on the development Postgres on 2026-08-08: 85 turns, ZERO with a
declared outcome.** The column exists since revision 0012 and nothing fills it
yet — `stamp_outcome()` is the write seam and no host calls it.

So this reading runs on empty data on day one, and the defect it must not have is
returning "containment 0%":

```python
reading.containment
# NotCalculable(reason="no_outcome_declared",
#               detail="no turn declared an outcome — containment is UNDEFINED. …")
reading.no_outcome_declared   # True
```

"0%" would assert *the copilot resolved nothing*. What actually happened is
*nobody declared*. Two opposite statements, and the same zero writes both.

The same applies one level up: `sample.turns == 0` is `reading.nothing_to_look_at`
— every answer comes back `NotCalculable(reason="no_turns")` and `render()` leads
with **NÃO HÁ O QUE OLHAR**. This mirrors `DeclarationGaps.nothing_to_look_at`
in `dna_cli.solution_kind`, and exists for the same reason: green-by-vacuity has
blinded three guards in this house already.

---

## The two zeros of a token count

`input_tokens = 0` means two incompatible things, and `tokens_partial`
(revision 0012) is what tells them apart:

| `tokens_partial` | meaning | effect on the reading |
|---|---|---|
| `false` | the account is closed — every model call reported its usage, including "no call at all" | exact |
| `true` | at least one model call ended without reporting usage. The provider charged for the prompt anyway | the number is a **FLOOR** |
| `NULL` | the row predates revision 0012 — nobody was watching | the number is a **FLOOR** |

A floor sets `Number.is_floor`, `render()` prints `≥ PISO`, and a note explains
which turns caused it. A reading that summed tokens without looking at this
column would keep understating the cost — and understating it precisely on the
bad turns, which is where measurement matters most.

⚠️ The asymmetry is deliberate and cuts both ways: the **value** is also a floor
whenever some turns declared no outcome. When *both* sides are floors, the
**ratio between them bounds nothing in either direction**, and the reading says
so instead of pretending a direction.

---

## Tokens are exact. Money is not, and that is not a bug

The spec that opened this work said *"cost is already exact (tokens × model) —
nothing is missing"*. Half of that survived contact with the code.

**Token counts are exact.** Money is not, because **there is no model price table
anywhere in this repository** — no Kind, no constant, no file. Token prices change
week to week and are a fact about the operator's *contract*, not about the SDK; a
table embedded here would age in silence and produce wrong money wearing the face
of a measurement.

So the price is declared by the caller, and without it:

```python
reading.tokens   # Number(1500.0, "tokens", MEASURED, …)   ← always available
reading.cost     # NotCalculable(reason="no_model_price", missing=("gpt-5-mini",))
```

A model that appears in the sample with **no** declared price makes the whole
money answer not-calculable — never a partial sum, which would be smaller than
the truth and is the kind of wrong that fools people most. Prices in two
currencies do the same (`currency_mismatch`), because adding them produces a
number that is not money at all.

---

## The App's standing cost — a CONSTANT, labelled as one

`App.can_sleep` is the other half of the account (`Spec/spec-app-e-o-servico`):
the `App` declares the **cost**, the `Copilot` declares the **return**.

```python
reading.standing_cost
# can_sleep: false → Number(90.0, "USD/mês", CONSTANT, "… measured 2026-07-31 …")
# can_sleep: true  → Number(0.0,  "USD/mês", DECLARED, "scales to zero …")
# can_sleep absent → NotCalculable(reason="can_sleep_undeclared")
# no runs_in       → NotCalculable(reason="no_app", missing=("Copilot.runs_in",))
```

The `90.0` is `STANDING_REPLICA_USD_MONTH`, and its basis is `CONSTANT` on
purpose: it was **measured once**, on 2026-07-31, on dna-cloud — the `copilot`
service with `minReplicas: 1` was US$ 94.43 of a US$ 230.29 invoice, alone the
largest line — and it is **not read from any invoice**. Nothing here talks to
billing, and the number does not update itself. Labelling it `MEASURED` would put
it in the same class as the token count, which *is* live.

⚠️ It is **monthly**, and the rest of the reading is **per turn**. It is therefore
deliberately left OUT of `reading.ratio`, and a note says so. Adding them would
mix units.

An absent `can_sleep` is never `true`. Presuming the cheap side hides exactly the
fixed replica nobody decided — ~US$ 90/month, recurring, forever.

---

## Where the numbers come from

`read_yield` computes nothing from I/O; it takes a `Sample`. Two things produce
one, and they must agree:

| producer | for | needs |
|---|---|---|
| `sample_from_turns(turns, approvals)` | rows already in hand — `Mapping` (a cursor row) or `Turn` (the recorder's object) | nothing |
| `gather_sample(connection, tables, …)` | a `GROUP BY` in the database; only aggregates travel back | an `AsyncConnection` + `build_metadata(is_pg=True)` |

The parity between the two is asserted against a live Postgres in
`tests/test_leitura_do_rendimento_pg.py`, and it is not ceremony: a `GROUP BY`
over `tokens_partial` produces separate `true`/`false`/`NULL` groups, and folding
those wrong would turn "unreadable usage" into "closed account".

⚠️ `dna_turn` and `dna_approval` are **Postgres-only** control-plane tables
(revisions 0004/0005). On SQLite `tables.turn` is `None` and `gather_sample`
**raises** rather than returning an empty sample — empty would read as "no
turns", and what happened is "this question is not asked here".

---

## What this does not do

* **It does not open a connection.** The rule lives here, the I/O belongs to
  whoever holds the client — the same boundary as `dna.runtime.telemetry`, and
  what makes all of it exercisable with no database and no network.
* **It does not infer an outcome.** `status = 'ok'` answers *"did it raise?"*,
  never *"did it resolve?"*. The vocabulary is imported from
  `dna.runtime.telemetry.OUTCOMES` — one list, never a second copy — and a value
  outside it (`ok`, `sucesso`, a typo) counts as unknown.
* **It does not read `edited_args`.** The difference between `arguments` and
  `edited_args` is literally how wrong the agent was, measured by a human, in
  production — the cheapest quality signal in the system, recorded and still
  never consulted. The acceptance rate counts `edit` without reading it. That is
  a known gap, not an oversight.
