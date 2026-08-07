# `app-container` — the reference Copier template

One python container app: its package, its Dockerfile, its version floor, and
the three wiring fragments a running service needs.

```bash
dna solution new templates/app-container ./my-repo --defaults --data service_name=mcp
dna solution update ./my-repo --service mcp
```

## The questions ARE the `App`'s fields

An `App` **is the service** (`Spec/spec-app-e-o-servico`) — the unit with a
Dockerfile, a port, wiring and a bill at the end of the month. So
`service_name`, `python_module`, `port` and `can_sleep` are spelled here exactly
as the descriptor spells them: a declared App and a rendered tree are two views
of one fact, not two vocabularies somebody has to translate.

⚠️ `container_port` was renamed to **`port`** on 07/08/2026 for that alignment.
An already-generated tree does not carry the value across by magic — `dna
solution update` reports `container_port` as an answer that changed unasked, and
`port` takes the template default until you pass `--data port=<the old value>`.

## `owns_code` — one code directory, N services

A service is not a directory. Measured in dna-cloud: **nine deployable services
over four `apps/` directories** (`apps/mcp/` alone serves `mcp`, `mcp-entra` and
`mcp-ws` — one image, one identity authority per door). Eight of the nine are
another deployment of an image that already exists, so:

```bash
# the door that owns the code — everything
dna solution new templates/app-container ./my-repo --defaults \
    --data service_name=mcp

# a second door over the SAME image — the three wiring fragments, nothing else
dna solution new templates/app-container ./my-repo --defaults \
    --data service_name=mcp-ws --data image_name=mcp --data owns_code=false \
    --data port=8001
```

The second run never writes into `apps/mcp/`: the code paths carry a
`{% if owns_code %}` segment, and Copier skips a path whose rendered name is
empty. Regenerating `apps/mcp/src/` because somebody declared `mcp-ws` would
overwrite production code.

`port` and `can_sleep` stay **per service**, never per image — two doors over one
image legitimately disagree, and each renders its own bicep.

## `can_sleep` — the cost, on screen

`can_sleep: false` renders `minReplicas: 1`. That is **~US$ 90/month, recurring,
forever** (measured: the dna-cloud copilot with a fixed replica was US$ 94,43 of
a US$ 230,29 invoice). Every run that renders such an app prints the number,
because the gate this house wrote says the question *"can it sleep?"* must be
answered with the number on screen — and generation is when it is answered.

Prose lives in [`docs/guides/solution-scaffolding.md`](../../docs/guides/solution-scaffolding.md).
Read it before changing anything here: the rendered tree is frozen as a golden
(`packages/cli/tests/goldens/solution/app-container/`), so a change to this
template has to be re-frozen deliberately —

```bash
DNA_FREEZE_GOLDEN=1 packages/cli/.venv/bin/python -m pytest \
    packages/cli/tests/test_solution_golden.py
```

— and the diff of that re-freeze is the review.

## What it deliberately does not do

* **No `_tasks`, `_migrations` or `_jinja_extensions`.** They force `--trust`,
  and `dna solution` has no such flag. Tasks also run three times per update,
  two of them in temp directories with no git repo.
* **No full `server.py`.** The template stops where your reasoning starts;
  generating the whole server would program a merge conflict into the first
  update.
* **It cannot reach `azure.yaml` or the root bicep.** Two of the seven wiring
  places have no include mechanism. `wiring/azure.service.yaml` is a fragment
  a human pastes; the root `module` line is printed by `dna solution new`.

  ⚠️ So the honest claim is: this template **emits a fragment**, and nothing
  here knows whether it was ever pasted. A guard in the consuming repo
  (`scripts/guard-app-wiring.mjs` in dna-cloud) is what checks arrival.
  Measured cost of the gap: the **A2A door spent three days in production
  without existing**, every line of code in place, because one entry was
  missing from `azure.yaml`.
