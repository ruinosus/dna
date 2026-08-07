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

### ⭐ One code directory, N services — `owns_code`

A service is not a directory. Measured in dna-cloud on 07/08/2026: **nine
deployable services over four `apps/` directories.**

| directory | services | why |
|---|---|---|
| `apps/web/` | `web` | |
| `apps/mcp/` | `mcp`, `mcp-entra`, `mcp-ws` | one image, one identity authority per door |
| `apps/api/` | `rest`, `rest-user` | one image, two auth lanes |
| `apps/copilot/` | `copilot`, `worker`, `a2a` | |

So **eight of the nine** are *another deployment of an image that already
exists*, and for those, generating `Dockerfile` / `pyproject.toml` / `src/` /
`tests/` would **overwrite production code** because somebody declared a new
door. `owns_code` is the answer that says which case you are in:

```bash
# the door that owns the code
dna solution new templates/app-container ./my-repo --defaults \
    --data service_name=mcp

# a second door over the SAME image — wiring only
dna solution new templates/app-container ./my-repo --defaults \
    --data service_name=mcp-ws --data image_name=mcp --data owns_code=false \
    --data port=8001 --data can_sleep=true
```

The second run writes exactly three files:

```
apps/mcp-ws/wiring/compose.fragment.yml     build context → ./apps/mcp
apps/mcp-ws/wiring/azure.service.yaml       project       → ./apps/mcp
apps/mcp-ws/wiring/containerapp.bicep       its OWN port and minReplicas
```

Nothing under `apps/mcp/` is written or touched. The mechanism is Copier's, not
ours: a file or directory whose rendered name is **empty** is skipped, so the
code paths carry a `{% if owns_code %}` segment. Measured against copier 9.17.

⚠️ **`port` and `can_sleep` are per SERVICE, never per image.** Two doors over
one image legitimately disagree about both — they are `App` fields, and the
answers file is per service, so each door's wiring carries its own. A template
that derived them from the image would give a whole fleet one sleep answer,
which is how a fixed replica gets into a bill with nobody choosing it.

`owns_code: false` requires `image_name` to name *another* service. Otherwise
the fragment's build context is its own empty directory: a tree that looks
complete and cannot build. The template refuses it.

### ⭐ The cost, on screen, at the moment it is decided

`can_sleep: false` renders `minReplicas: 1`, and a fixed replica is
**~US$ 90/month, recurring, forever** — measured: the dna-cloud copilot with a
fixed replica was US$ 94,43 of a US$ 230,29 invoice, the largest single line on
it. Every run that renders such an app prints it:

```
⭐ COST — 1 app(s) answered `can_sleep: false`, so the generated bicep says
   `minReplicas: 1`:
    worker
  A fixed replica is ~US$ 90/month, RECURRING, forever — not a one-off.
```

It is printed from the **answers file**, so it appears with or without
`--solution`: `dna solution` runs against repos with no `.dna` anywhere, and
that is exactly the run where the person generating has least context about
what a replica costs here.

An **absent** answer is not a cheap answer. It produces no cost line and is
reported separately as an unanswered cost question — see *"The cost question"*
below; presuming `true` is the failure the field exists to prevent.

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
| `apps` — every `App` the solution deploys, the complete set | the **cost commitment** — it lives on `App.can_sleep` |
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

Nothing is presumed, and that is the part that had to survive the move. It is
now one of **three** questions in a single report — see below.

⚠️ **Absent is never `false`.** `can_sleep: false` is an *answer*, and an
expensive one; absent means nobody was asked. Collapsing the two is exactly how
a fixed replica enters the fleet with nobody deciding it.

`--sleep-answer KEY` is **gone**: it named the answer key to lift out of the
template's answers, and there is no longer anything to lift.

### ⭐ The report of what is missing

`Spec/spec-campo-opcional-por-evidencia` (07/08/2026), after the dna-cloud
dogfood measured the nine real services against the model: **six fitted whole,
three had a gap, and none of the gaps was an error.**

| gap | the reason, and it is a good one |
|---|---|
| `portal` with no `python_module` | it is **Next.js** — there is no python package to name |
| `worker` with no `port` | it has no ingress, **on purpose** |
| the whole solution with no provenance | the dna-cloud was **never generated from a template** |

So: **the schema prevents nonsense, the report chases completeness.** A field
becomes optional when *reality presents a legitimate case* — never because it
is convenient — and what the schema stops requiring, the report starts asking:

```
⚠ 3 declaration(s) missing across the deployments:
    can_sleep — a deployment that cannot scale to zero costs a FIXED REPLICA…
        worker
    python_module — which python package `apps/<dir>/src/` installs
        mcp
```

The reported fields are **derived from the descriptor**, not listed here: what
`App` marks `required` can never be missing and is the schema's business;
everything else in the service identity is the report's. A field that earns its
optionality on evidence joins the report by itself.

#### "Does not apply" is the FACT — not an annotation about the field

An empty field means two opposite things — *the question does not apply* and
*nobody answered*. A report that does not separate them talks about everything,
and a report that talks about everything nobody reads; at that point it is
**worse** than the refusal it replaced, because it feels like somebody is
looking.

⭐ The way to separate them is to **state the fact**, and the question stops
being asked:

```yaml
# the App of a worker that scales on KEDA and answers nobody
ingress: none      # → its `port` is no longer asked for
```

`worker` is not "an App whose port does not apply" — it is an App that **does
not serve**, and having no port is the *consequence*. `ingress` was already a
`copier.yml` question (`internal` / `external`), so `none` is a third value of a
vocabulary that exists rather than a new mechanism; and the descriptor refuses
`ingress: none` together with a `port`, so the report is not hiding a question,
it is declining to ask for something the schema forbids.

⚠️ A generic `not_applicable` map was designed and **deliberately not built**.
Once `python_module` moved to `answers` by the wiring-vs-render ruler, exactly
one case was left — and one case does not pay for a general mechanism. What the
narrower answer buys is structural: `ingress` answers the port question and only
that one, so there is no way, by accident or on purpose, to silence the **cost**
question with it. A per-App exemption would have had exactly that back door,
defended only by getting an enum right.

⚠️ `can_sleep` and `service_name` have **no** way to say "does not apply", and
that is measured rather than an oversight: there is no case for either across
the nine real services. If one appears, the form to adopt is named in the
descriptor (FHIR's `dataAbsentReason`) — **named and not built**. Do not invent
one.

#### ⚠️ Empty is a finding, not a pass

The report reads **`apps[]`** — the enforced relation, which is the set of
deployments by definition and exists whether or not the repo came from a
template. It used to read `services[].name`, and that had a hole the founder
found:

```python
if not names:        # ← a Solution with no services[]
    return []        # ← "everything is declared"
```

With `services` optional that is **green by vacuity** — the class of defect
that has blinded three guards in this house. So an empty `apps[]` reports
**NOTHING TO LOOK AT**, loudly, and `--strict` exits 3 on it.

⚠️ And note this **diverges** from `join_disagreements`, where an absent `apps`
is *not* a disagreement. Both are right, because the questions differ:

| question | of an absent/empty list |
|---|---|
| *"do the two lists agree?"* | no answer — and firing here would cry wolf on every record older than the guard |
| *"has anyone answered about cost?"* | **yes: nobody looked** |

Do not "unify" them. The divergence is the decision.

### ⭐ Both halves, in one write

A recorded run writes the **two halves** of a deployment, joined by name:

| the fact | where it lives | why |
|---|---|---|
| `name`, `answers_file`, `template{src,ref}`, `answers` | `Solution.services[]` | the **provenance of the render** — which template, at which ref, answering what |
| `service_name`, `python_module`, `port`, `can_sleep` | the `App` | the **identity of the deployment** — readable across the fleet without opening a repo |
| the join | `Solution.apps[]` — the COMPLETE set, the same names as `services[].name` | the only level at which a relation can be **declared** |

The four App fields are copied under **the same names the template asked them
under** — which is why `copier.yml` spells its questions `service_name`,
`python_module`, `port` and `can_sleep`. One vocabulary, so the projection is a
copy rather than a mapping somebody has to remember.

⚠️ **Order matters, and it is not cosmetic.** The `App` is written **before**
the `Solution`: `apps` is an *enforced* relation, so a Solution naming an App
that does not exist yet is a refused write under `DNA_REF_VALIDATION=enforce`,
and the whole record fails.

**If the installed `App` descriptor cannot hold those fields**, no App is
written, `apps` is left alone — populating an enforced relation whose targets do
not exist is a broken record, not half a migration — and the run says so:

```
⚠ NO `App` was written, so nothing declares whether these services may sleep.
  The installed `App` descriptor cannot hold: service_name, python_module, …
```

Since #351 landed that is normally unreachable. It is kept because `dna-cli` and
`dna-sdk` are **separate wheels with independent floors**: a CLI newer than its
SDK is a real install, and this is what turns it into a sentence instead of a
traceback in the middle of a scaffold.

### ⚠️ Why the join is `apps[]`, and not `services[].name`

`services[].name` is the same string as the App's `metadata.name` — it is what
azd calls a service — so it *looks* like the natural place to declare the
relation. **It cannot be declared there.** `relation_values` reads
`spec.get(rel.name)`: top level, always. A pointer inside `services[].items` is
out of reach, and the kernel even names the rule — `top_level_properties_only`.

The failure mode is the worst kind, and it was measured (#351): declaring
`relations: {services: {to: App}}` **lints green**, reports
`resolved / enforced = True / True` — announcing that it vetoes bad writes —
and `relation_values` returns `[]`. It reads nothing, resolves nothing, vetoes
nothing. A guard that says it is enforced and is not.

So `apps[]` is the join, and therefore it must be **complete**: an `apps` that
listed only some of the deployments would be the system's one enforceable
relation left incomplete on purpose.

**Sellability does not need a second list.** It already has a house:
`App.requires_plan`, which is optional. An App without one is a container that
runs and is not sold — `worker` is exactly that.

Two lists for one fact would still drift, so that is prevented by a mechanism
rather than by leaving one empty: every write checks that `services[].name` and
`apps[]` denote the same set, **derived from both sides**, and refuses with
both sides named:

```
Solution 's' would be written with `apps` and `services[].name` disagreeing,
and they denote the same things — an App IS a deployment.
  services with no entry in `apps`: api
  `apps` entries with no service: algum-outro
```

An **absent** `apps` is not a disagreement — that is the join simply not being
declared, which the schema allows and §6-B measured as the common case. While
the `App` descriptor has not moved, no App instance is written, so `apps` is
left alone: populating an *enforced* relation whose targets do not exist is not
half a migration, it is a broken record (the kernel says so —
`unresolved relation(s): spec.apps → 'api' (no App named 'api')`).

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
bicep — `scripts/guard-app-wiring.mjs` in dna-cloud. The template makes five
places impossible to forget; the guard makes the other two impossible to forget.
Together that is the seven.

⚠️ **Say the true version of this, and only the true version.** The template
**emits a fragment**; it does not wire anything. Nothing in `dna solution`
knows whether the fragment was ever pasted into `azure.yaml`, and a doc that
implied otherwise would be worse than silence — because the failure it hides
is *invisible by construction*. Measured, in this house: **the A2A door spent
three days in production without existing**, with every line of code in place,
because one entry was missing from `azure.yaml` (03/08/2026; the compose entry
had gone missing the same way on 31/07). Nothing was broken. Nothing failed. It
simply was not there.

That is what the guard is for, and why it lives in the consuming repo rather
than here: only the repo that owns `azure.yaml` can check `azure.yaml`.

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
