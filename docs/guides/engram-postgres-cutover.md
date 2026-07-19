# How to cut over a Postgres-backed deployment from `LessonLearned` to `Engram`

`s-engram-rename` renamed the memory Kind `LessonLearned` → `Engram` and
moved its identity to `github.com/ruinosus/dna/v1`. Kind resolution is an
exact `(apiVersion, kind)` 2-tuple lookup with **no fallback**
(`dna/kernel/instance.py:686` — `self._kinds.get((doc.api_version,
doc.kind))`): the instant a deployment's pin advances to an SDK version that
only registers `Engram`, every stored document still carrying the old
`(apiVersion, kind)` pair becomes invisible — not an error, just silently
absent from every `instance()`/`recall()`/prompt build.

There is **no window where both identities resolve at once**. This is a
**hard cutover**, and the four steps below must happen in this order, in
lockstep, for any deployment whose `DNA_SOURCE_URL` is Postgres (a
filesystem-only deployment only needs step 2, run against its `.dna/` tree,
before bumping the pin).

## Prerequisites

- `scripts/migrate_engram.py` (this repo) — the unified entry point. It
  dispatches to `scripts/migrate_lesson_learned_to_engram.py` (filesystem)
  or `scripts/migrate_engram_postgres.py` (Postgres) based on whether
  `--source` looks like a `postgresql://`/`postgres://` DSN or a directory.
- A **maintenance window**. Step 1 stops all writes to the store; nothing in
  the deployment should be writing DNA documents between steps 1 and 4.
- `pg_dump`/`pg_restore` (matching the target server's major version) and
  somewhere to store the dump OUTSIDE the database being migrated.
- `az` CLI access to the deployment's Container Apps (or your platform's
  equivalent) to scale writers down and verify they actually stopped.
- Read `scripts/migrate_engram_postgres.py`'s module docstring for the full
  schema analysis (which tables carry the identity, the collision
  pre-flight, and the `dna_outbox` decision) before running this against a
  real database.

## Step 1 — freeze writes, verify the freeze, and back up

### 1a. Scale down every writer

```bash
# dna-cloud example (Azure Container Apps, rg-dnacloud) — adjust names/RG
# for your deployment:
az containerapp update -n ca-dna-mcp-<env>    -g rg-dnacloud --min-replicas 0 --max-replicas 0
az containerapp update -n ca-dna-mcp-ws-<env> -g rg-dnacloud --min-replicas 0 --max-replicas 0
az containerapp update -n ca-dna-api-<env>    -g rg-dnacloud --min-replicas 0 --max-replicas 0
```

Any writer left running during steps 2–3 can race the migration: a write
that lands between the pre-flight read and the transaction commit is
invisible to the pre-flight and could either (a) collide with the rename
mid-flight, or (b) get silently skipped by the migration and then become
unresolvable the moment the new pin ships. The pre-flight assumes a frozen
store — it is not a substitute for the freeze.

**Is `mcp` + `mcp-ws` + `api` the complete list? What about `copilot`?**
Verified (read-only, against the actual dna-cloud repo — `infra/*.bicep`,
`infra/copilot.Dockerfile`, `infra/emit_copilot_langgraph.py`): the
`copilot` Container App's env DOES include `DNA_SOURCE_URL` (bicep injects
it, alongside `DNA_MCP_URL` and the separate `DNA_PRIMARY_PG_URL`), which
looks alarming at a glance — but nothing the copilot runs at request time
ever reads it. `DNA_SOURCE_URL` is only ever consumed by
`emit_copilot_langgraph.py`'s `Kernel.quick(SCOPE, base_dir=BASE_DIR)`,
which runs **once, at `docker build`** (`RUN python
/app/emit_copilot_langgraph.py` in `copilot.Dockerfile`) against the
**filesystem** `.dna/` baked into the image (`DNA_BASE_DIR=/app/.dna`) —
not against Postgres at all, and not at runtime. At request time the
running copilot's only path to DNA content is `MultiServerMCPClient` over
`DNA_MCP_URL`, which the emitted agent's own docstring confirms explicitly
("Tool bodies live on the remote DNA MCP server, not in \[the copilot\]") —
i.e. every DNA read/write the copilot makes is proxied through `mcp` /
`mcp-ws`, which are already frozen above. Its other direct Postgres
connection, `DNA_PRIMARY_PG_URL` (a **separate** secret from
`dna-source-url`), opens LangGraph's own `AsyncPostgresSaver` /
`AsyncPostgresStore` — a completely different schema (LangGraph's
checkpoint/store tables) with zero overlap with `dna_documents` /
`dna_edges` / any table this migration touches. **Conclusion: freezing
`mcp` + `mcp-ws` fully covers `copilot`'s write path; `copilot` itself does
not need to be scaled down.** This was verified against this repo's
emitter output and dna-cloud's committed patch script as they exist today
— if either changes (e.g. the Dockerfile comment's noted "optional switch
to emit-from-Postgres-source at container start" ever gets wired up),
re-verify before relying on this.

### 1b. Verify the freeze actually took

Scaling to zero does not guarantee zero in-flight writers instantly — a
request already in progress can still complete after the scale command
returns. Before proceeding to the backup/migration, confirm no replicas are
actually running:

```bash
az containerapp replica list -n ca-dna-mcp-<env>    -g rg-dnacloud -o table
az containerapp replica list -n ca-dna-mcp-ws-<env> -g rg-dnacloud -o table
az containerapp replica list -n ca-dna-api-<env>    -g rg-dnacloud -o table
# all three must return an EMPTY list before continuing.
```

For extra confidence, confirm at the database itself that nothing is
actively writing:

```sql
-- Run against $DNA_SOURCE_URL. Expect zero rows (or only this session).
SELECT pid, application_name, state, query_start, state_change
FROM pg_stat_activity
WHERE datname = current_database()
  AND state != 'idle'
  AND pid != pg_backend_pid();
```

Do not proceed to Step 1c/Step 2 until both checks are clean.

### 1c. Back up before writing anything

The single-transaction guarantee in Step 2 protects against a *bug in this
script surfacing mid-run* (a collision it failed to pre-flight, a raised
exception) — it does NOT protect against operator error, a concurrent
incident unrelated to this migration, or a correctness gap in the script's
own reasoning that testing and review did not catch. That last one is not
hypothetical: during development, the pre-flight initially missed a
`dna_edges`-specific collision shape (two currently-distinct rows renaming
INTO each other, since `from_kind`/`to_kind` are independent columns) —
caught by review, not by the original test suite. See
`_preflight_edges`'s docstring in `scripts/migrate_engram_postgres.py` for
the fixed reasoning. Irreplaceable production data gets a real backup
regardless of how much the tooling has been tested:

```bash
# Managed Azure Postgres: a point-in-time-restore checkpoint is implicit
# (the service retains PITR automatically), but take an explicit logical
# dump too — it's cheap, portable, and gives you a restore target that
# doesn't depend on Azure's retention window:
pg_dump --format=custom --file="dna-pre-engram-migration-$(date -u +%Y%m%dT%H%M%SZ).dump" "$DNA_SOURCE_URL"
```

To restore (only if something is wrong with the *result* — the migration's
own transaction already means a failed run itself leaves the store
untouched):

```bash
pg_restore --clean --if-exists --dbname="$DNA_SOURCE_URL" dna-pre-engram-migration-<timestamp>.dump
```

Confirm the dump file is non-trivially sized and store it somewhere outside
the database being migrated before proceeding.

## Step 2 — run the Postgres migration

Dry run first — always. It writes nothing and reports per-table candidate
counts so you can sanity-check the scope of the change before committing to
it:

```bash
python3 scripts/migrate_engram.py --source "$DNA_SOURCE_URL"
```

Read the report. It tells you, per table (`dna_documents`, `dna_versions`,
`dna_layer_documents`, `dna_bundle_entries`, `dna_edges`, `dna_search_docs`
if present), how many rows are candidates, how many are already migrated,
how many are orphans (half-migrated — `kind: Engram` with a stale/missing
`apiVersion`, needs manual attention, see the FS script's docstring for what
that state means), and — the load-bearing part — **whether any collision
was found**. `dna_outbox`'s count is reported for visibility only; it is
never rewritten (see the "dna_outbox decision" in
`scripts/migrate_engram_postgres.py`).

**If the report shows any collision**: STOP. A collision means a document
already exists under the new identity with the same key a candidate would
be renamed into (e.g. a `LessonLearned/rem-x` and an `Engram/rem-x` already
both present in the same scope/tenant). Resolve it manually (rename or merge
the conflicting document) before re-running — the migration will not touch
anything, collision or not, until this is clean. This is enforced
structurally: `migrate_postgres()` always runs the full read-only pre-flight
across every table before it ever opens a write transaction, and refuses to
proceed if `has_collisions()` is true, regardless of `--apply`.

Once the dry run is clean:

```bash
python3 scripts/migrate_engram.py --source "$DNA_SOURCE_URL" --apply
```

This re-runs the same pre-flight (data may have theoretically changed since
the dry run — it hasn't, because writes are frozen) and then, only if it is
still collision-free, rewrites every table in **one Postgres transaction**:
all of it commits together, or none of it does. A half-migrated store is
strictly worse than an unmigrated one — a document whose `dna_documents` row
renamed but whose `dna_edges` rows didn't resolves *confusingly* (matched by
`kind_for()`, which ignores `apiVersion`) rather than cleanly (simply
absent).

If the schema is not `public`, pass `--schema <name>`.

## Step 3 — bump the pins and deploy

Bump the three dna-cloud pins in lockstep
(`infra/mcp.Dockerfile`, `infra/api.Dockerfile`,
`infra/copilot.Dockerfile`) to the SDK version that carries `Engram` as
`Kind`, then `azd up`. See dna-cloud's own `CLAUDE.md` — "The DNA SDK
dependency" — for the pin mechanics; this repo does not own that step.

## Step 4 — run the filesystem migration against dna-cloud's `.dna/`, in the SAME commit as the pin bump

This is the step that's easy to forget, and forgetting it ships the old
identity silently: the copilot container image does `COPY .dna /app/.dna`
and emits the composed agent from that tree **at build time**. If
dna-cloud's own `.dna/` still carries `LessonLearned` docs when the pin bump
is built, the shipped copilot image has the old identity baked in — no
Postgres data is even involved, and no error will surface, because
`.dna/` was never in scope for step 2 (that step is Postgres-only).

```bash
python3 scripts/migrate_engram.py --source path/to/dna-cloud/.dna --apply
```

Run this **in the same commit** as the pin bump (step 3), not before and not
after — a separate commit reintroduces the same "no window where both
identities resolve" problem at the repo level: a commit that has the new pin
but the old `.dna/` content builds an inconsistent image.

## After cutover

Scale the frozen services (step 1) back up. Verify with a read against a
document that used to be `LessonLearned` — it should resolve under `Engram`
now, and a Postgres query for `kind = 'LessonLearned'` in every table above
should return zero rows (`migrate_engram.py --source "$DNA_SOURCE_URL"`
dry-run again is the cheapest way to confirm: it should report zero
candidates and zero orphans across every table).
