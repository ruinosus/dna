# Reading the yield — cost, return, and when the honest answer is "not calculable"

`dna.runtime.roi` is the one place where four separate facts meet: what a turn
**cost** (tokens, from `dna_turn`), what it **achieved** (`outcome`, since
revision 0012), what a human **thought of it** (`dna_approval`), and what one
successful outcome is **worth** (`Copilot.value_per_outcome`).

Most of what this module does is refuse to make things up.

```python
from dna.runtime.roi import gather_prices, read_yield, render, sample_from_turns

sample = sample_from_turns(turn_rows, approval_rows)
reading = read_yield(
    sample,
    copilot=copilot_spec,               # the Copilot's `spec`
    app=app_spec,                       # the `App` its `runs_in` points at
    prices=await gather_prices(kernel, sample),   # from the ModelProfile registry
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
raises. There are five bases:

| basis | meaning |
|---|---|
| `MEASURED` | counted in the record: `dna_turn`, `dna_approval` |
| `DECLARED` | stated by a human in a descriptor: `value_per_outcome`, `can_sleep` |
| `PROXY` | **derived, and not measuring what it looks like it measures** |
| `CONSTANT` | measured once, elsewhere, carried by hand — see below |
| `INCIDENTAL` | **a by-product**: it measures exactly what it claims, from a record nobody wrote *in order to be measured* — see `edited_args` below |

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

**Token counts are exact.** Money is not, because **no price table is embedded in
this code** — no constant, no file, no literal. Token prices change week to week
and are a fact about the operator's *contract*; a table hardcoded here would age
in silence and produce wrong money wearing the face of a measurement.

```python
reading.tokens   # Number(1500.0, "tokens", MEASURED, …)   ← always available
reading.cost     # NotCalculable(reason="no_model_price", missing=("gpt-5.4",))
```

A model that appears in the sample with **no** declared price makes the whole
money answer not-calculable — never a partial sum, which would be smaller than
the truth and is the kind of wrong that fools people most. Prices in two
currencies do the same (`currency_mismatch`), because adding them produces a
number that is not money at all.

---

## Where the price comes from: `ModelProfile`, not "the caller"

The paragraph above is right about everything except one word. Until
`s-preco-vem-do-modelprofile`, the price was declared *by the caller* — and **a
price each caller assembles is a price in nobody's code**. That is exactly the
lesson the `ModelProfile` descriptor already carried, with the outage that
motivated it: a 17,269-token voice persona silently blew past a 16,384 cap
*because the cap lived in nobody's code*. A price is the same class of fact as a
cap: **first-class global data**, declared in a Kind.

The two fields have always been there:

| `ModelProfile.spec` field | |
|---|---|
| `cost_per_1m_input_usd` | USD per 1M input tokens — `type: [number, "null"]` |
| `cost_per_1m_output_usd` | USD per 1M output tokens — same |

Two functions turn them into the price the reading consumes:

| | for | needs |
|---|---|---|
| `price_book(profiles)` | raw `ModelProfile` rows already in hand | nothing — **pure** |
| `await gather_prices(kernel, sample)` | resolving only the models the sample used, through `kernel.model_profile()` | a kernel |

Both return a `PriceBook`, and it has **two** maps on purpose — because "no
price" has two causes that ask different things of the reader:

```python
PriceBook(
    prices={"gpt-5.4": ModelPrice(0.25, 2.0, "USD", source="ModelProfile 'gpt-5.4' …")},
    incomplete={"claude-x": ("cost_per_1m_output_usd",)},   # exists, never quoted
)
```

A model absent from both needs a profile **created**; a model in `incomplete`
needs its profile **completed**, and the reading names the field. Collapsing the
two into "missing" hands out the wrong instruction, which is nearly as expensive
as none.

### The four refusals

1. **A model without a price never becomes a partial sum.** If any model in the
   sample lacks a price, the *whole* money answer is `NotCalculable`, naming the
   ones that are missing. Partial is smaller than real, and understated cost is
   the kind of wrong that fools people most.
2. **`null` is ABSENT, never zero.** The schema declares `type: [number, "null"]`
   deliberately. A `null` read as `0.0` would report "free" for the most
   expensive model in the fleet. Half a quote is not half a price either: input
   declared and output `null` yields *unknown*, exactly like a half-declared
   `value_per_outcome`. Anything that is not a number — a bool (`float(True)` is
   `1.0`), a string, a negative — is not a quote.
3. **"I don't know" becomes "declare THIS."** Measured on the development
   Postgres on 2026-08-08: **zero `ModelProfile` instances exist.** The field is
   there and nobody has declared a model. So the reading answers *not calculable*
   on day one — which is correct — but it must not stay silent about which model
   to declare. `missing` carries the exact `model_id` `dna_turn` stamped, and
   `detail` carries the path (`_lib`, `model-profiles/<model_id>.yaml`) and the
   two field names.
4. **The currency is in the field NAME.** `cost_per_1m_input_usd` ends in `_usd`;
   `PROFILE_PRICE_CURRENCY` reads that and presumes nothing.

⚠️ **Aliases are not optional, and the measurement says so.** On the same
database `dna_turn` stamped 74 turns of `gpt-5.4` and **one** of
`gpt-5.4-2026-03-05` — a dated snapshot. Without the second pass over
`aliases[]` (the same one `kernel.model_profile()` does), that single turn would
make the entire account not-calculable even with `gpt-5.4` declared, by rule 1.
`gather_prices` keys the book by **the name the turn stamped**, even when the
match came through an alias.

### How old is the price? — `i-101`, decided 2026-08-08

While `cost_per_1m_*` was *"(informational)"* a stale price hurt nobody. The
resolution above makes it **accountable**, and a stale accountable number
produces a wrong account **wearing the face of a measurement** — precisely the
defect PR #359 refused by not embedding a table. So the Kind gained two fields:

| field | |
|---|---|
| `cost_quoted_at` | ISO-8601 — **when** this price was quoted |
| `cost_source` | **where** it came from: pricing page, contract, estimate |

Past an age ceiling the reading marks the money **suspect** — and it does so in
the **mould of `is_floor`**, which already existed and was already printed:

```python
reading.cost.is_suspect          # True
reading.cost.source              # "… ⚠️ PREÇO VELHO acima do teto de 90d: gpt-5.4 (219d)"
render(reading)                  # "Custo (tokens): 0.0004 USD [MEASURED ⚠ SUSPEITO]"
```

Three decisions worth stating, because each had an easy wrong answer:

* **The ceiling is a default, not a law.** `PRICE_STALE_AFTER_DAYS` is 90 days —
  and it is labelled **policy, not measurement**, with its reason and its date
  next to it, the same way `STANDING_REPLICA_USD_MONTH` is labelled `CONSTANT`
  rather than `MEASURED`. `read_yield(..., price_max_age_days=...)` overrides it,
  because a negotiated contract price is stable for a year and a public pricing
  page is not, and one ceiling for both is the same hardcoding this module
  refuses for the price itself.
* **Absent `cost_quoted_at` is UNKNOWN age, and unknown is not recent.** It is
  suspect too. Reading absent as fresh would presume the good side — the same
  error as presuming `can_sleep: true`, which hides exactly the replica nobody
  decided. The two states share the mark and carry different sentences, just as
  the two floors (unreadable usage, pre-0012 rows) share `is_floor`.
* **Suspect does not refuse the number.** The tokens were measured and the price
  was declared; only the *age* is in doubt. Refusing would throw away a
  measurement over a metadata gap — that is the line between "not calculable"
  and "calculable, with a caveat".

Both fields are **optional in the schema on purpose.** With zero live instances,
adding a *required* field is free today — but `required` in JSON Schema is
unconditional, and this Kind serves two audiences from one object: whoever
registers a token cap (the outage that created it) and whoever registers a price.
Requiring a quote date from someone declaring only `instruction_token_cap` pushes
them to invent one, and an invented date reads as knowledge. The requirement is
conditional, so it lives where conditions can be expressed: the reading.

> **On `models.dev`** (MIT, `cost.input` / `cost.output` in USD per 1M, plus
> `last_updated`): it maps almost 1:1 onto these fields, and importing it is its
> own story. Note that it does not remove the need for `cost_quoted_at` — it is a
> community catalogue with no declared refresh cadence, so a price can be stale
> there too. We do not trust the catalogue; we import **the date it declares**
> and let the age ceiling do the work.

A hand-built `ModelPrice` still works — a test needs to declare a price without
assembling a Kind — and its `source` says `PRICE_FROM_CALLER` precisely so the
screen can tell the two apart. There is deliberately **one** price parameter and
not two: two sources for the same number is drift waiting to happen, and the one
that lost would be wrong in silence.

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
* ⚠️ **It does not price prompt CACHE — because nothing counts it.** Measured
  2026-08-08: `dna_turn` has `input_tokens` and `output_tokens` and no cache
  column; `dna.runtime.telemetry` reads `gen_ai.usage.input_tokens` /
  `output_tokens` and nothing else. A `cost_per_1m_cache_read_usd` on the Kind
  today would price a quantity nobody counts — a decorative field, which is worse
  than an absent one because absent is visible. And the consequence is bigger
  than a missing field: **the direction of the error stops being known for cached
  traffic.** The floor claim above holds while every input token costs the input
  price. With prompt cache it depends on the provider — some report cache reads
  *outside* `input_tokens` (the account understates, the floor holds), some
  *inside* (the account overstates, charging 1× what was billed at a fraction,
  and the floor is wrong). In a copilot this is not a detail: the same
  instruction ships on every turn. Closing it is migration + telemetry +
  `TokenUse` + price, in that order. Note the "adding a field is free while there
  are zero `ModelProfile` instances" argument does **not** transfer to the hard
  half: `dna_turn` already has rows, and its window has closed.
---

## `edited_args` — the signal nobody read, and what it actually says (`i-151`)

`dna_approval` stores `arguments` (what the agent proposed) and `edited_args`
(what got recorded). The promise is big: *the difference between the two is
literally how wrong the agent was, measured by a human, in production, with
nobody running an experiment.* `compare_args()` is the reader that was missing,
and `reading.correction` is the answer.

⚠️ **And today the answer is a refusal — because the comparison was made.**

```python
reading.correction
# NotCalculable(reason="no_correction_to_measure",
#               detail="the 3 compared `edit`s rewrote NO value (3 identical
#                       field(s), 0 rewritten, 0 added) …")
```

**Measured on the development Postgres, 2026-08-08: 20 `approve` · 3 `edit` ·
0 `reject`.** The three `edit` rows differ from their proposals by 65% of their
text, and **the entire difference is machinery**:

| # | what the naive diff would have counted | what it really is |
|---|---|---|
| 1 | 100% divergence at the top level, on every row, forever | the two columns **have different shapes**: `arguments` is the request's `args`, `edited_args` is the whole `edited_action` (`{"name": …, "args": {…}}`) — see `dna.runtime.audit.settle` |
| 2 | a field the human deleted, in 3 of 3 rows | `rationale` is **not a tool argument**: `DnaMcpToolsMiddleware` injects it into the model-facing schema and strips it before execution |
| 3 | — | ⭐ **`edit` here does not mean "I corrected it"** |

The third is the finding that decides everything. The only emitter of
`{"type": "edit"}` in the product is the composer's *accept* button
(`canvas.ts` / `suggestionDecision`), which builds `edited_action` from a
**subset of the agent's own patch**, copying the values verbatim. Through the
door that exists, a human-rewritten value is **impossible by construction**.
`edit` there means *"I accept these fields, not those"*.

Net of (1) and (2), the three edits are **identical** to what the agent
proposed. A "correction rate: 0%" would be true in the arithmetic and false on
the screen — it would read *"the agent got everything right"* when what happened
was *"the editing door cannot rewrite"*. Same class of error as "containment 0%",
same answer: `NotCalculable`, carrying the exact counts and saying what would
have to change for a number to exist.

**The machinery ships ready.** The day a host writes an `edited_action` with a
human's value, `compare_args` sees it and `reading.correction` becomes a
`Number` with `basis=INCIDENTAL`.

### How to compare — three choices with an easy wrong answer

* **By JSON PATH, never by string distance.** An `edit` that only reorders keys
  is no error at all; dicts are unordered and a path diff is immune for free.
  String distance would score reordering — and reindenting — as a total rewrite.
* **A list is ONE leaf, compared whole.** Pairing element by element needs an
  identity the arguments do not carry: `["a","b"] → ["b","a"]` is a reorder in
  `tags` and a rewrite in a pipeline. Not knowing which, do not invent the
  alignment.
* **⚠️ REMOVAL does not enter the magnitude.** A field that vanished is
  indistinguishable from a form that does not round-trip it — and that is not
  hypothetical: 3 of 3 measured removals were `rationale`, which the machinery
  itself strips. The magnitude counts only what a human alone produces (a value
  **rewritten** or **added**); removals are counted alongside, with the
  ambiguity stated.

### ⚠️ Tenant content: the text travels, only the COUNT stays

Both columns carry what the user typed. So `ArgsDelta` holds **numbers and
nothing else** — not the values, and not the *paths* either: a JSON object key
can itself be user data (`{"fields": {"<what they typed>": …}}`), and "just the
field names" would leak exactly there. No `source`, `detail` or `render()` line
of this reading contains text from `arguments` or `edited_args`; the comparison
reads, counts and discards. `gather_sample` is where the text travels — one
extra query, restricted to `decision = 'edit'`, the rarest decision.

### Small sample: a mark, not a silence

`MIN_EDITS_FOR_CORRECTION` is 10, and it is **policy, not measurement**, dated
and reasoned like `PRICE_STALE_AFTER_DAYS`: below ten, a single `edit` moves the
rate by more than ten points, and a number one click can swing that far is an
anecdote with decimals. Below the floor the number still comes out — carrying
`Number.is_small_sample`, printed as `⚠ AMOSTRA PEQUENA` on the same line, in the
mould of `is_floor`. Suppressing it would make the reading go quiet exactly while
the sample grows, which is when someone is watching.
`read_yield(..., min_edits_for_correction=...)` overrides it.

### Why a new basis and not `PROXY`

Containment is `PROXY` because it **measures something other** than it appears
to. This number has no such defect: the difference between proposed and recorded
is exactly what it says. Its defect is different — it is a **by-product**. The
two rows were not written to be compared, and what they admit as a reading
depends on a write path (the screen that assembles `edited_action`) that nobody
keeps stable for the measurement's sake. A `PROXY` fails by definition and fails
the same way every time; an `INCIDENTAL` is valid until someone changes the form,
and then it **fails in silence**. Those are different warnings for the reader,
and the three measured `edit`s are the proof that the second one is the one
needed here.
