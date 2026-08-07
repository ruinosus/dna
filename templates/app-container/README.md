# `app-container` — the reference Copier template

One python container app: its package, its Dockerfile, its version floor, and
the three wiring fragments a running service needs.

```bash
dna solution new templates/app-container ./my-repo --set service_name=mcp
dna solution update ./my-repo --service mcp
```

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
