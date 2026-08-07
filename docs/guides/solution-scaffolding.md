# Scaffolding a repo — `dna solution new` and `dna solution update`

`dna solution` generates a real app — its package, its Dockerfile, its version
floor and its deployment wiring — from a [Copier](https://copier.readthedocs.io)
template, and can roll that app forward when the template moves.

It exists because of a measured defect. Wiring a new service into a monorepo of
this shape touches **seven** places, and getting six of them right ships a door
that returns 404 for three days while everyone reads the code that is correct.
A generator makes forgetting one of them impossible rather than unlikely.

Two things to know before you read further, because both change what you expect:

* **It reaches five of the seven places, not seven.** Two are unreachable by any
  template. [Below](#the-two-places-no-template-reaches) says which, why, and
  what covers them instead. Every run prints it too — a scaffolder that implied
  seven would be worse than none, because you would stop checking.
* **Copier does the rendering and the merging.** This command adds no engine.
  What it adds is reporting: four things Copier does silently, which were
  measured and found surprising, and which this command says out loud — plus
  the one place a report was not enough, [the `Solution`
  record](#keeping-the-declaration-the-solution-record).

```bash
pip install 'dna-cli[scaffold]'
```

---

## Generate

```bash
dna solution new templates/app-container ./my-repo \
    --defaults --data service_name=api --data identity=workos
```

`TEMPLATE` is anything Copier accepts — a local path, a git URL, `gh:owner/repo`.
The run writes `apps/api/` **and** `.copier-answers.api.yml`, the file recording
which template, at which ref, with which answers. Without that file an app can
be regenerated but never updated, which is the whole reason to generate it this
way.

### One template, many apps

Run `new` again with a different `service_name` and you get a **second layer**,
not a regeneration:

```bash
dna solution new templates/app-container ./my-repo --defaults --data service_name=mcp
dna solution list ./my-repo
```

```
2 template layer(s) in /path/to/my-repo:
  .copier-answers.api.yml
    template: templates/app-container
    ref:      v1.0.0
  .copier-answers.mcp.yml
    ...
```

Each layer updates alone. Nine services over four images is four templates and
nine answers files, and improving the MCP-door template rolls the three MCP
doors forward independently, touching nothing else. The per-instance answers
file (`_answers_file: ".copier-answers.{{ service_name }}.yml"`) is what makes
that work; it is the pattern
[`datarobot-community/af-component-*`](https://github.com/datarobot-community)
runs in production, and it is worth copying rather than inventing.

A template that needs values from the layer above it declares
`_external_data`, and Copier reads that layer's answers as defaults — inheritance
between layers, without template inheritance (which Copier does not have). When
such a file is missing Copier **warns and renders the inherited values as
empty** rather than failing, so `dna solution` surfaces the warning as a named
finding: generate the upper layer first.

---

## Update

```bash
dna solution update ./my-repo --service api
```

Preconditions, both refused rather than attempted:

| condition | what happens |
|---|---|
| destination is not a git repo | refused — `update` is a three-way merge and needs history |
| working tree is dirty | refused, with Copier's own message |
| template publishes no git tags | refused unless `--allow-untagged` — see [below](#4-a-template-with-no-tags) |
| template declares `_tasks` | refused, exit 4, and **no flag opens it** |

### What the report tells you

Four behaviours were measured before this command was written. Each is silent
in plain Copier, and each is a line of output here.

#### 1. A recorded answer never moves, and nothing says so

This is the important one. Copier keeps a recorded answer forever. If the
template bumps `dna_floor` from `0.74` to `0.75`, an `update` leaves your app on
`0.74` — correctly, by Copier's rules — and prints nothing. The most common
change in this house, moving a version floor, is an **answer**, not template
text, so it reaches nobody.

```
⚠ 1 answer(s) kept a recorded value while the template default moved:
    dna_floor: '0.74'   (template default '0.74' → '0.75')
  Take them:  dna solution update ./my-repo --service api --data dna_floor=0.75
```

Take them all at once with `--adopt-new-defaults`, in the **same run that
detects the move** — that warning compares two refs, so once this update writes
the new `_commit` there is nothing left to compare.

Which is why there is a second, quieter line, and it has no memory:

```
ℹ 2 answer(s) differ from the template's current default:
    dna_floor: '0.74'   (template default '0.75')
    ingress: 'external'   (template default 'internal')
```

It asks only *is this answer what the template says today?*, so a floor left
behind is reported on **every** update until somebody moves it. Most entries are
the point — an app that answered nothing differently would not need to exist —
but the one you forgot is in there, permanently, instead of vanishing after one
run.

Only **literal** defaults are compared. A default like
`{{ image_name | replace('-', '_') }}` cannot be evaluated without rendering it
in full context, and being wrong in a warning is worse than staying quiet.

#### 2. A `when:`-gated answer is erased

An answer behind `when:` disappears when its condition stops holding, and comes
back as the template's **default** — not as what you said — if the condition
returns. Measured, in one round trip:

```
identity=entra, graph_obo=true   →  graph_obo: true
update to identity=workos        →  (absent)
update back to identity=entra    →  graph_obo: false     ← was true
```

**On its own**, `dna solution update` cannot undo this: the answers file was the
only place holding the value, and the update rewrites that file. What it does is
refuse to let it happen quietly, printing the name **and the value** so you can
carry it forward:

```
⚠ 1 recorded answer(s) changed unasked:
    graph_obo: True → (absent)
```

Two consequences for anyone modelling these answers elsewhere: a schema must not
require a `when:`-gated field, because it legitimately disappears; and **a
record that outlives the answers file is the only place such a value can
survive.**

⭐ That record now exists — a `Solution` instance, see [Keeping the
declaration](#keeping-the-declaration-the-solution-record). With one recorded,
the same round trip ends on `graph_obo: true`, because the value was re-passed
from somewhere the update does not rewrite.

#### 3. Per-instance answers files need `-a`

Copier's default lookup is `.copier-answers.yml`. The per-instance layout this
design depends on breaks it with a bare `TypeError: Template not found` and a
traceback. `dna solution update` discovers the answers files itself, uses the
one when there is one, and refuses with a list when there are several:

```
./my-repo carries 2 answers files — one per app, which is the design. Say which one:
    .copier-answers.api.yml
    .copier-answers.mcp.yml
```

Never a guess: a wrong guess updates the wrong app.

#### 4. A template with no tags

Copier's real precondition for `update` is **git**, not **a tag**. An untagged
template updates anyway, under a synthesised pseudo-version
(`0.0.0.post1.dev0+a54909c`). `new` warns and proceeds — there is no fleet to
roll forward yet. `update` **refuses**, because a fleet rolled forward to a HEAD
nobody named cannot be described afterwards. `--allow-untagged` says you meant it.

### Conflicts

An update that touches a line you also touched produces a merge conflict, and
adjacent edits collapse into one coarse block (that is `git merge-file`, not a
Copier defect). Until they are resolved the tree does not build — conflict
markers are not valid source — so resolve per app, not in a batch. `--strict`
exits 3 when a run has findings, which is what makes this safe to script.

⭐ **A conflict inside `wiring/` is a different animal from one inside `src/`.**
It means a human had to express *structure* the template never asked about, and
the fix is a **new question in `copier.yml`**, not a merge — resolving it by hand
papers over a missing field and guarantees the same conflict forever.

⚠️ **And a wiring line you edit by hand becomes invisible.** Change
`maxReplicas: 2` to `4` and the template's later change to that line simply never
arrives: no conflict, no warning. Copier skips, but does not report what it
skipped. Reporting that is not something this command can do for you.

---

## Keeping the declaration — the `Solution` record

Everything above is a file on disk. `--solution NAME` adds a second view of the
same fact as **governed data**: a `Solution` instance holding, per layer, the
template pointer, the answers verbatim, and whether the app may sleep.

```bash
# record as you generate
dna solution new templates/app-container ./my-repo --defaults \
    --data service_name=api --solution dna-cloud

# or record a tree that already exists — every layer at once
dna solution record ./my-repo --solution dna-cloud

# and then update THROUGH the record
dna solution update ./my-repo --service api --solution dna-cloud
```

It is opt-in on purpose: rendering a tree must keep working with no kernel, no
scope and no `.dna` anywhere, which is what makes `dna solution` usable against
somebody else's repo.

### What it buys, and it is one thing

**An answer the file lost comes back as yours.** `update --solution` merges the
record *under* the answers file before anything is compared or re-passed, so the
`when:` round trip in [§2](#2-a-when-gated-answer-is-erased) ends where you left
it:

```
⭐ 1 answer(s) came back from the Solution record `dna-cloud` — the answers
   file no longer held them:
    graph_obo
```

The merge lands in the one variable every finding is computed from, which is why
a floor that lives only in the record still shows up in *"kept a recorded value
while the template default moved"*. A record whose answers were re-passed but
not compared would be the silent-floor defect with a nicer command line.

The write-back **accumulates** rather than mirrors: recording only the
post-update file would drop the gated value from the record on the very update
that dropped it from the file. An accumulated answer the template stopped asking
about is simply ignored by Copier, so keeping it costs nothing.

### What it stores, and what it refuses to

| stored | not stored |
|---|---|
| `template.src` + `template.ref` — a **pointer** | any rendered file, any template body |
| `answers` — free-form, the template's own vocabulary | a typed mirror of the template's questions |
| `apps` — which `App`s the solution delivers | the **cost commitment** — it lives on `App.can_sleep` |
| | `requires_plan` and anything else that would *look* enforced and not be |
| | the conflicts, the git state, the working copy |

`answers` requires no key and types none, for the reason §2 gives: a gated
answer legitimately disappears, and typing the questions would make the Kind one
particular `copier.yml` written twice — the second template would not fit.

### The cost question — asked here, answered on the `App`

An app that cannot scale to zero costs a fixed replica — **~US$ 90 a month,
forever**.

⚠️ **This changed on 07/08/2026** (`spec-app-e-o-servico`). The commitment used
to be `services[].pode_dormir`, promoted out of `answers` because nothing else
could hold it. Now the `App` **is** the deployment, and an entry in `services[]`
is one per deployment — the same granularity, nine and nine. One fact in two
places is two names for one fact, so:

* `Solution.services[]` keeps the **provenance of the render** — which template,
  which ref, which answers. The template's own `can_sleep` answer is still here,
  verbatim, inside `answers`, like every other answer. What ended was its
  promotion to a field of its own.
* **`App.can_sleep`** holds the **commitment**, authored on the App named by
  `services[].name` — the same string.

Nothing is presumed, and that is the part that had to survive the move. A
service whose `App` has no `can_sleep` — or no `App` at all — is reported on
**every** run:

```
⚠ 1 recorded service(s) have no App saying whether they may sleep:
    api
```

⚠️ **Absent is never `false`.** `can_sleep: false` is an *answer*, and an
expensive one; absent means nobody was asked. Collapsing the two is exactly how
a fixed replica enters the fleet with nobody deciding it. `--strict` turns the
finding into exit 3.

`--sleep-answer KEY` is **gone**: it named the answer key to lift out of the
template's answers, and there is no longer anything to lift.

---

## The two places no template reaches

Every successful run ends with this, and it is not boilerplate:

```
⛔ Two wiring places this (or any) template cannot reach:
    azure.yaml  →  services.<name>
    the ROOT bicep  →  module <name>App '.../wiring/containerapp.bicep'
```

A Copier template renders **files**. These two are *blocks inside shared root
documents*, in formats with no include mechanism: the azd JSON Schema fixes the
root document's top-level keys, and Bicep has modules but the *invocation* is a
line in the shared root file. Verified — this is a property of the formats, not
of any template.

The other five are fine, and one of them shows the shape to imitate:
`docker-compose` has `include:`, so a compose fragment is consumed by path with
nobody editing a shared file. Where a format allows that, use it. A root
`pyproject.toml` moves off the list too, by making its workspace members a glob
(`members = ["apps/*"]`) instead of a hand-kept list.

For the remaining two there are exactly two options and both cost:

* **A `_tasks` hook that mutates the root file.** Refused here, and not on taste:
  tasks run **three times per update, two of them in temp directories with no git
  repo**, so a task assuming project context breaks and a non-idempotent one
  corrupts. They also force `--trust`, which means running a template author's
  code on your machine. `dna solution` has no `--trust` flag.
* **A solution-level template that owns the root files.** Then every new app is
  a change to that template and the root `azure.yaml` becomes shared territory
  that conflicts on every addition.

**So cover them from the other side:** a guard in the consuming repo that fails
when a service exists under `apps/` and is missing from `azure.yaml` or the root
bicep. The template makes five places impossible to forget; the guard makes the
other two impossible to forget. Together that is the seven.

---

## Writing a template

Read [`templates/app-container/`](https://github.com/ruinosus/dna/tree/main/templates/app-container)
— it is the reference, and the one these commands were built against.

**Rule 1 — generate the maximum of what the consumer will not edit, and the
minimum of what they will.** Wiring is almost never hand-edited: perfect target,
and it merges clean. A server with real reasoning in it *will* be edited, so the
template ships a skeleton and stops. Generating the whole server programs a
conflict into the first update.

**Rule 2 — one template per app TYPE, overlaid N times.** Never one giant
template of the whole repo. Per-instance answers files are what make each app
independently updatable.

**Rule 3 — no `_tasks`, no `_migrations`, no `_jinja_extensions`.** See above.
Effects belong outside the template: render, then run your own step.

**Rule 4 — freeze the output.** The rendered tree of a fixed answer set is a
**golden file**, exactly as [emit is](writing-an-emitter.md):

```bash
DNA_FREEZE_GOLDEN=1 packages/cli/.venv/bin/python -m pytest \
    packages/cli/tests/test_solution_golden.py
```

Then read the diff — that reading *is* the review. Without it a template is the
only thing in the repo that produces source code with no contract, and a change
nobody looked at is a change nobody decided. Freeze at least two answer sets, so
that every `{% if %}` is rendered both ways; a single golden stays green while a
whole conditional block is deleted.

---

## Where rendering happens

On your machine, always. Nothing is uploaded and no server renders a template —
which keeps the generator open and uncapped, keeps a third party's Jinja out of
anyone else's container, and costs nothing to run.
