# Resolving from a hosted DNA (`https://` source)

A separate repository can consume the definitions of a **hosted** DNA — the same
`Agent`, `Copilot`, `Tool` and `RuntimeBinding` instances a colocated app reads —
without holding a database credential. One environment variable changes:

```bash
DNA_SOURCE_URL=https://dna.example.com/v1
DNA_API_TOKEN=<the bearer the hosted door issued you>
```

Nothing else does. `DnaClient.from_env()`, `resolve_agent` and `resolve_copilot`
keep their exact shape:

```python
from dna.client import DnaClient

client = await DnaClient.from_env(scope="acme")
copilot = await client.resolve_copilot("front-desk")
print(copilot.instructions, copilot.tools, copilot.knowledge)
```

If a consumer has to change code to move from `postgresql://` to `https://`, the
adapter has failed. That is the whole design constraint.

## Why the token matters more than the convenience

The alternative — and until now the only option — was to hand the consumer the
Postgres DSN. Between two projects of the same owner that is untidy. For a third
party it is the wrong thing entirely: a DSN is the whole database, and taking it
throws away precisely what a hosted layer exists to give.

* an **authenticated door**, per consumer, revocable;
* the **tenant stitched in on the server**, so the consumer cannot widen its own
  boundary even by accident — the DSN model asks the consumer to enforce its own
  limit, which is the opposite of fail-closed;
* quota, metering and audit, which only exist where the read passes through a
  door.

## One credential, one scope

The REST instance routes take no `scope` parameter. The scope is derived from
the credential on the server, and that is the property above, not an oversight:
`GET /v1/kinds/App/instances?scope=other` answers with the SERVED scope's
instances. So the adapter asks the door which scope it serves and **refuses**
any read for a different one (`RemoteScopeMismatch`) rather than returning one
scope's content under another's name — and rather than returning an empty list,
which would assert that the other scope holds nothing.

Two consequences worth knowing before you deploy:

* **Scope inheritance does not cross this door.** The kernel walks a scope's
  declared parent chain; over HTTP each ancestor is refused, and the kernel logs
  that inherited instances are unavailable. That log line is true — read it as
  information, not as a bug.
* **A consumer that needs two scopes needs two doors** (two URLs, two tokens),
  or one door whose credential is bound to the scope it wants.

## What it costs

Measured against a live `dna api serve` (433 instances, 88 registered Kinds):

| read | calls | wall |
|---|---|---|
| `load_bootstrap_docs` (Genome + KindDefinition + LayerPolicy) | ~7 | ~40 ms |
| one instance (`load_one`) | 1 | ~2 ms |
| the names of one Kind (`list_doc_refs`) | 1 | ~3 ms |
| the whole scope (`load_all`) | **522** | **~1.1 s** (8 lanes) |

`load_all` is `1 + N + M` — one registry call, one listing per Kind, and one GET
per instance — because the list route's `fields` projection cannot return a
whole `spec`. `?fields=spec` and `?fields=*` were both tried against the real
face: each answered `[{"name": …}]` while echoing `"projected": ["spec"]`. Only
named leaf paths project, and they project through the Kind's view, which
normalizes. A source must return **documents**, so each one costs its own GET.

The kernel builds a scope's base manifest **once per process**, so this is a boot
cost. It grows linearly with the scope; a very large hosted scope is the case to
measure before shipping.

## Offline, and the definition of yesterday

The face publishes **no `ETag` header** today (the single-instance body carries
an `etag` field, but there is no header and no `If-None-Match` handling), so
conditional revalidation is not available. The behaviour is therefore decided
rather than inherited:

1. **Fail loud by default.** No network, no boot — `ResolveNetworkError`, naming
   the URL. Nothing stale is ever served silently.
2. **Stale is opt-in twice, and announced.**

   ```bash
   DNA_SOURCE_SNAPSHOT_DIR=/var/cache/dna    # writes a snapshot on every good read
   DNA_SOURCE_OFFLINE=stale-ok               # …and permits serving it when the door is down
   ```

   Every serve from the snapshot logs a WARNING with its age and sets
   `HttpSource.stale_since`, so a status page can say *"definitions are 4 hours
   old"* instead of implying they are current. A process that RESTARTS during an
   outage is covered too: the served scope is snapshotted alongside the
   documents.
3. **A refused credential is never answered from a snapshot.** A 401 is a
   decision about this caller; serving the cache would hand over exactly what
   the door just declined.
4. A short read memo (`DNA_SOURCE_HTTP_TTL`, default `30` seconds, `0` disables)
   collapses repeated fan-out inside one build. It is a declared staleness
   window, not a silent one.

A consumer that will not boot because the network blinked is worse than one
running yesterday's definitions. Serving yesterday's definitions without saying
so is worse than both. That is why the fallback exists and why it is loud.

## Everything else it will not do

`HttpSource` is **read-only**. It declares no write surface, no drafts, no
version history, no bundle entries and no query push-down — the list route
exposes no filter, so a native `query` could only fetch-then-filter, and taking
the query away from the kernel's reader-aware fallback to answer a narrower
question is a defect this repo has already paid for once. Writes still go
through the REST face's own write routes, the MCP tools, or the CLI.

## Environment variables

| variable | meaning |
|---|---|
| `DNA_SOURCE_URL` | `https://<host>/v1` — the API root, version prefix included |
| `DNA_API_TOKEN` | the bearer. The same name the REST face, both generated clients and the CLI docs already use |
| `DNA_TENANT` | optional; forwarded as the face's `tenant` query param |
| `DNA_SOURCE_HTTP_TIMEOUT` | per-request timeout, seconds (default `30`) |
| `DNA_SOURCE_HTTP_CONCURRENCY` | in-flight document GETs during `load_all` (default `8`) |
| `DNA_SOURCE_HTTP_TTL` | read-memo window, seconds (default `30`; `0` disables) |
| `DNA_SOURCE_SNAPSHOT_DIR` | where snapshots are written; unset means none |
| `DNA_SOURCE_OFFLINE` | `stale-ok` permits serving a snapshot on a NETWORK failure |

The token is never logged, not even masked: a diagnostic says only `setado` or
`ausente`.
