# i-091 — `recall` was not read-your-writes on a TLS-shaped DSN

Branch `fix/i-091-index-ssl` (worktree `dna-wt-ssl`, off `origin/main` @ `1a93e581`).

## The defect

`recall` returned `index_refreshed: false` with
`index_error: CantChangeRuntimeParamError: parameter "ssl" cannot be changed now`.
The envelope was honest (`degraded: true`), and that honesty is untouched. The
defect was the failure itself: the search-index refresh could never run, so
anything written since the last successful refresh could not appear. The
memory that *was* found in the reported session came from the lexical plane
re-scored by the embed-based ecphory rerank — `semantic: true` only means a
provider is *registered* (`verbs.recall`, line ~403), so it was luck, not
guarantee.

## Reproduction (real, not constructed)

Local `pgvector/pgvector:pg16` started with TLS actually enabled
(self-signed cert, `-c ssl=on`), reached over `?ssl=require` — the production
DSN *shape*, no production credential involved. Script:
`scratchpad/i091_repro.py`. Output before the fix:

```
A  SQLAlchemy ordinary query: OK 1
A  dialect create_connect_args: ([], {... 'ssl': 'require'})
B  asyncpg.create_pool FAILED: CantChangeRuntimeParamError: parameter "ssl" cannot be changed now
B  asyncpg DSN parse -> server_settings: {'ssl': 'require'}
C  source.connect(): OK
C  pg_search_binding(): ('postgresql://…/dna_test?ssl=require', 'public')
C  provider.index() FAILED: CantChangeRuntimeParamError: parameter "ssl" cannot be changed now
```

After the fix, line C reads `provider.index(): OK 1` — same DSN, same server.

## The two connection paths, and the difference

Both paths start from the *same* configured URL.

* **Ordinary query** → `SqlAlchemySource` → SQLAlchemy's asyncpg dialect.
  `PGDialect_asyncpg.create_connect_args` folds the whole `url.query` into the
  driver's **connection arguments**: `asyncpg.connect(ssl="require")`. `ssl` is
  a TLS mode. Works.
* **Index refresh** → `recall_impl` → `backfill_index` → `PgVecRecordSearchProvider.
  _get_pool` → `asyncpg.create_pool(dsn)` with the DSN rendered by
  `SqlAlchemySource.pg_search_binding()` (`engine.url.set(drivername="postgresql")`,
  query string intact). asyncpg's **own** DSN parser
  (`connect_utils._parse_connect_dsn_and_args`) understands a fixed libpq-ish
  vocabulary — `sslmode`, `host`, `user`, `target_session_attrs`, … — and
  forwards everything else, blindly, into **`server_settings`**
  (`connect_utils.py:443-447`). So `ssl=require` went into the startup packet;
  `ssl` is a real `PGC_SIGHUP` GUC, and Postgres answers 55P02
  `CantChangeRuntimeParamError`. Every pool connection died.

That is the whole difference: **the same query param is a connection argument
to one reader and a server setting to the other.** The hypothesis in the brief
was right about the mechanism and its hole is now filled: ordinary queries
never touch asyncpg's DSN parser, because SQLAlchemy parses the URL itself and
passes host/port/user/password/ssl as keywords.

**Second candidate ruled out.** pgbouncer is not involved: the failure
reproduces against a direct connection to a plain Postgres, and the refused
`SET` is a *startup parameter*, not a runtime `SET` issued in a session.

**Not a deployment misconfiguration.** The two consumers of the URL require
*opposite* spellings, so no operator setting can satisfy both:
`postgresql+asyncpg://…?sslmode=require` fails at the source with
`TypeError: connect() got an unexpected keyword argument 'sslmode'` (verified),
while `?ssl=require` fails at the raw asyncpg pool. Only code can translate.

## The layer fixed, and why that one

New module **`packages/sdk-py/dna/adapters/asyncpg_dsn.py`** —
`asyncpg_connect_args(dsn) -> (dsn, connect_kwargs)`. It owns exactly the
translation that was missing: DSN → asyncpg connect args.

* Not `pg_search_binding`: it faithfully carries the whole URL, and *dropping*
  the params there would silently disable TLS. They must be carried to the
  point where the connect call is made.
* Not the provider alone: the same DSN reaches asyncpg from
  `bootstrap._wire_search` (`dsn=cfg.source`, raw config) and from the
  LISTEN/NOTIFY bus. A shared helper covers every construction path.
* **Not a special case for `ssl`.** The lifted set is derived at runtime from
  `asyncpg.connect`'s own signature minus the vocabulary asyncpg's DSN parser
  already consumes, so the *next* connection argument that appears in a URL
  cannot repeat the bug. Genuine server settings (`application_name`) stay in
  the DSN and still reach the server; asyncpg's own vocabulary (`sslmode`,
  `target_session_attrs`, `passfile`) is left for asyncpg to parse. URL strings
  are coerced to the types asyncpg expects (bool → int → float → str), so
  `direct_tls=false` cannot arrive as the truthy string `"false"`. A
  SQLAlchemy driver suffix is dropped; a libpq keyword/value DSN is returned
  untouched.

Call sites: `dna/adapters/search/pgvector.py::_get_pool` (the reported bug) and
`dna/adapters/postgres/eventbus.py::_connect_and_consume` (the identical live
defect — its reconnect loop swallows the error forever, so on such a
deployment cross-process invalidation was silently dead).

## Tests

* `tests/test_asyncpg_dsn_connect_args.py` (7 cases, offline). Includes the
  external fact the bug rests on, asserted against the **real driver**:
  `test_asyncpg_forwards_an_unknown_query_param_as_a_server_setting` →
  `server_settings == {"ssl": "require"}`; and, after the split, the same
  parser reports nothing extra in the startup packet.
* `tests/test_recall_read_your_writes_pg_ssl.py` (`requires_postgres`) — the
  failing shape end to end: `recall_impl` on a DSN carrying `ssl=` must report
  `index_refreshed is True` (not merely "returned"), and a memory written a
  moment earlier must come back. `ssl=prefer` so it runs against any Postgres —
  as a *server setting* it fails identically whether or not the server speaks
  TLS. The fixture seeds one unindexed memory on purpose: with an empty scope
  `backfill_index` returns 0 before opening a connection and the case would go
  green with the bug fully present. Watched failing with the exact production
  error, then passing.
* `tests/test_eventbus.py::test_connects_on_a_dsn_carrying_an_ssl_query_param`
  (`requires_postgres`) — asserts a **delivered** invalidation, because the
  bus's reconnect loop makes "no exception" meaningless. Mutation-checked:
  restoring `asyncpg.connect(self._dsn)` fails it with
  `CantChangeRuntimeParamError`.
* `tests/test_recall_is_honest_about_its_index.py::
  test_a_refresh_that_cannot_reach_its_store_is_reported_not_swallowed` — the
  honest-degradation pin, run through the **real** `backfill_index` (the other
  cases in that file monkeypatch it). Mutation-checked: wrapping
  `prov.index(records)` in `except Exception: return 0` fails this case and
  **only** this case — the pre-existing tests would not have caught a swallow
  inside `backfill_index`.

## Suites

* `packages/sdk-py`: `4668 passed, 100 skipped, 4 xfailed, 2 failed` (174s),
  with `DATABASE_URL` set so every `requires_postgres` case ran for real.
  The two failures are the known pre-existing ones, missing optional deps:
  `test_emit_agent_framework.py::test_emitted_yaml_loads_into_agent_framework`
  and `runtime/test_langchain_adapter.py::test_attach_registers_the_agui_route`.
  Stash evidence: with `git stash -u -- packages/sdk-py/dna packages/sdk-py/tests`
  (this branch's changes removed) both still fail — `2 failed in 8.94s`.
* `packages/cli`: `1371 passed, 19 skipped` — clean.
* `python3 scripts/brand_guard.py` → clean; `scripts/docs_coverage_guard.py` →
  clean (100 public items covered).

No version bump, no PR.
