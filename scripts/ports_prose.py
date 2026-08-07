#!/usr/bin/env python3
"""Hand-written prose for the port catalogue. Consumed by ``gen_ports_docs.py``.

Everything a signature can state — name, module, methods, annotations,
docstrings, who already implements it — is **derived** by the generator and
must not be typed here. This file carries only what no signature answers:

  ``group``       which reader-first family the port belongs to. Deliberately
                  NOT the package layout: somebody arrives asking "how do I
                  change where instances live", not "what is in dna.kernel".
  ``role``        ``extend`` (you implement it) · ``receive`` (the kernel
                  implements it and hands it to you) · ``internal`` (a seam
                  between the kernel and its own collaborators).
  ``one_line``    the index-table cell: what this port DECIDES.
  ``summary``     a sentence or two of orientation above the contract.
  ``when``        when a real person would swap it.
  ``minimum``     the smallest thing that actually works.
  ``lights_up``   the capability it turns on — **and what the face does if you
                  skip it**. This is the field that makes port docs
                  trustworthy: "unimplemented" and "implemented, found
                  nothing" are different answers, and a catalogue that does
                  not say which one you get is worse than no catalogue.
  ``prove``       the suite that grades it. Not "write tests" — the name of
                  the battery, and how to run it.
  ``not_for_you`` required for ``internal``/``receive``. Say it plainly.
  ``adapters_extra``  implementations the generator cannot see, because they
                  satisfy the Protocol structurally instead of inheriting it.
                  The generator checks each named class still exists.

The generator FAILS if a Protocol in the source has no entry here, and FAILS
if an entry here names a Protocol that is gone. Adding a port therefore means
answering these questions — which is the point.
"""
from __future__ import annotations

# ── the reader-first families ────────────────────────────────────────────
# Order here is the order of the index page and the nav.

GROUPS: list[tuple[str, dict]] = [
    (
        "storage",
        {
            "title": "Storage & retrieval — where instances live",
            "blurb": (
                "The ports the kernel uses to answer *where is this, and how do I get "
                "it back*. This is the plane with the most shipped adapters and the "
                "only one with a full conformance battery, so it is also the best "
                "documented place to start if you are writing your first port."
            ),
            "appendix": """
## Proving a storage adapter

Three batteries exist, and they answer different questions. Running one and
skipping the others is the common mistake.

**1. The boot gate — names only.** `kernel.source(src)` checks that six methods
*exist*. That is all `runtime_checkable` can check, and passing it says your
adapter is shaped right, not that it works.

**2. The conformance kit — behaviour, one adapter.** `dna.testing` ships the
same battery the in-tree adapters are graded by, and it is public API precisely
so an out-of-tree adapter runs the identical cases:

```bash
# in your own package
pip install dna-sdk
pytest tests/test_my_adapter_conformance.py
```

The suite is **capability-aware**: it reads your declared `capabilities()`,
skips the cases you did not claim, and fails the ones you claimed but did not
honour. The `capabilities_declared_honestly` case is the interesting one — it
compares your declaration against a reflection oracle, so an adapter cannot
quietly over-claim.

**3. The cross-adapter matrix — behaviour, all adapters, one suite.**
`packages/sdk-py/tests/test_adapter_conformance_matrix.py` runs four dimensions
(numeric query push-down, order/limit, tenant overlay, bundle-entry tenant
isolation, plus the cross-process-invalidation flag) against filesystem, SQLite
and Postgres. Adapters used to diverge silently and the gap surfaced in
production; this is the answer to that.

To enrol a fourth adapter, add an async factory returning `(source, cleanup)`
next to `_build_fs_source`, then append one line to `_source_factories`:

```python
_source_factories = [
    pytest.param(_build_fs_source, id="filesystem"),
    pytest.param(_build_sqlite_source, id="sqlite"),
    pytest.param(_build_postgres_source, id="postgres"),
    pytest.param(_build_my_source, id="mystore"),      # ← yours
]
```

Every dimension picks it up. Run it with:

```bash
cd packages/sdk-py
uv run pytest tests/test_adapter_conformance_matrix.py -v
# the Postgres row needs a live database:
DATABASE_URL=postgresql://dna:dna@localhost:5432/dna \\
  uv run pytest tests/test_adapter_conformance_matrix.py -v
```

The suite runs under `pytest-xdist` by default (`-n auto` in `addopts`); use
`-n 0` when you need `-x` or `--pdb`.

### The divergences you are joining

Two rows are **`strict=True` xfails** today. They are marked strict on purpose:
a strict xfail fails the build if it starts passing, so a fix cannot land
unnoticed. A new adapter either inherits these gaps or resolves them — and the
only way to make that a decision rather than an accident is to know they are
here.

| Gap | Backends | Tracked as |
|---|---|---|
| **No cross-process invalidation.** Postgres writes a durable outbox row plus `pg_notify` inside the write transaction, so a second process learns to drop its caches. Filesystem and SQLite have no such channel: a multi-process deployment serves stale data, and nothing says so. Both declare `supports_cross_process_invalidation = False` rather than staying silent. | filesystem, sqlite | `s-sqlite-cross-process-invalidation` |
| **Tenant overlay clobbers the base row.** The SQLite `instances` primary key is `(scope, kind, name)` without `tenant`, so publishing an overlay overwrites the base instead of shadowing it. Postgres passes with identical kernel logic — this is inherited schema debt, not a limit of the design. | sqlite | `i-092` |

If your store can key an instance by tenant, key it by tenant, and the second
row never applies to you.
""",
        },
    ),
    (
        "capabilities",
        {
            "title": "Source capabilities — the optional slices",
            "blurb": (
                "A source adapter's **mandatory** contract is `WritableSourcePort`. "
                "Everything a store might additionally be able to do — keep versions, "
                "hold drafts, resolve overlays, store bundle entries — is a separate, "
                "opt-in Protocol here.\n\n"
                "These exist so the kernel never has to ask `hasattr(source, ...)`. "
                "That matters more than it sounds: the kernel needs to know what your "
                "store *cannot* do **before** it reads, so a face can refuse honestly "
                "instead of serving a confident empty answer. Read "
                "[what your declaration turns on]"
                "(capabilities.md#what-your-declaration-turns-on) "
                "before you implement any of them."
            ),
            "appendix": """
## What your declaration turns on

Every capability above is declared, not sniffed. Your adapter returns one
`SourceCapabilities` literal from `capabilities()`, and the kernel consults
that declaration — never `hasattr`, never `inspect`.

That indirection is the point. It exists because the previous design was a
per-adapter dict of magic strings whose keys and sync/async shape drifted
between backends, and which **lied**: the filesystem adapter claimed
`versions: False` while implementing `get_version`. A declaration can be
checked against reality; a `hasattr` cannot.

### The declaration

```python
def capabilities(self) -> SourceCapabilities:
    return SourceCapabilities(
        source="mystore",
        drafts=False, versions=False, layers=True,
        bundle_read=True, bundle_write=True, kernel_attachable=True,
        granular_list=True, granular_one=True,
        query_pushdown=True, tenant_layer_writes=True,
        api_version_identity=True, as_of_reads=False, edge_graph=False,
        valid_time=False, key_lookup=False, key_lookup_indexed=False,
        write_kwargs=frozenset({"tenant", "layer", "if_absent"}),
        delete_kwargs=frozenset({"tenant"}),
    )
```

⚠️ `valid_time` and `key_lookup_indexed` are the two flags whose value may
depend on the **binding** rather than on the class. `SqlAlchemySource` serves
Postgres and SQLite from one class, and only Postgres has the `tstzrange`
column plus the `EXCLUDE` constraint that makes overlapping validity periods
impossible — so it declares `valid_time=self._is_pg` and sets an instance
attribute (`supports_valid_time`) that the reflection oracle reads. Probing for
the *method* would derive `True` on SQLite, where `load_one_valid_at` exists
and refuses, and the oracle would then certify a declaration that lies.

`key_lookup_indexed` has the identical shape and the identical reason.
`find_instances_by_spec_key` — the read that lets a relation declared
`by: workspace_id` be **followed** rather than merely declared — is defined for
both bindings, but only Postgres serves it from an index: `dna_insts_spec_gin_idx`
(baseline revision 0001) is a GIN over `(content::jsonb->'spec')`, generic over
the *key*, and answers a containment lookup over 200 000 instances in 1,8 ms
against 15 ms scanned. SQLite has no GIN and no containment operator, and the
filesystem adapter has no index at all: both answer honestly by walking, and
both say so through the flag rather than through a profiler.

The pair is deliberately not one flag. `key_lookup=False` means *"cannot
answer"* and changes what a face may claim; `key_lookup_indexed=False` means
*"answers the slow way"* and changes what a deployment may be asked to hold.
Collapsing them would leave an honest O(N) store with no way to be honest.

Declare conservatively. An undeclared capability means a feature is off; an
over-declared one means the kernel hands you work you will silently drop, and
the conformance kit's `capabilities_declared_honestly` case exists to catch
exactly that before a user does.

### ⭐ Why an honest `False` is a feature, not an admission

This is the part of the port contract that is genuinely non-obvious, and it is
what separates a trustworthy adapter from a merely working one.

> **A store that cannot answer must refuse, not approximate.**

Take the reference graph. A store with no edge table does **not** return an
empty list. The kernel's own words:

!!! quote "`dna/kernel/query/graph.py`"

    A store without an edge table does not return an empty list. `[]` reads as
    "nothing points at this instance", which is a claim only a store that
    actually records edges may make; the filesystem adapter has neither a
    transaction to write edges in nor a table to write them to, so the answer
    is `GraphUnsupported` and the face says so. Serving a confident empty
    answer from a store that cannot know is the fail-open silence this codebase
    treats as a defect, not a convenience.

The same reasoning produced `as_of_reads` as a flag separate from `versions`,
and it is why these questions must be askable **before** the read rather than
discovered during it.

| You declare | Asked anyway, the face answers | Not |
|---|---|---|
| `edge_graph=False` | `GraphUnsupported` → REST **501** | `[]` |
| `as_of_reads=False` | `AsOfUnsupported` → REST **501** | today's instance under a past timestamp |
| history pruned | `AsOfTruncated` → REST **410** | `LookupError` — *"it did not exist yet"* is a different answer from *"I no longer hold the record"* |
| no `find_instances_by_id_prefix` | `InstanceIdLookupUnsupported` → REST **501** | an empty result set |
| `valid_time=False` | `ValidTimeUnsupported` → REST **501** | the instance unfiltered — which asserts *"yes, it was true then"* |
| `key_lookup=False` | `KeyLookupUnsupported` → REST **501**, and the write path records the edge with reason `unsupported` | `None` — which reads as *"no instance carries that key"* |
| `edges` not in `write_kwargs` | the kernel never hands you edges | your adapter silently dropping them |

Neither `GraphUnsupported` nor `InstanceIdLookupUnsupported` is a
`KernelRefusal`, and the distinction is deliberate: a refusal is a verdict on
*the request*, which the caller might appeal. These are statements about *the
deployment*. The caller's remedy is a different adapter, not a different
request.

### The three tiers

The eight Protocols on this page are not equally optional.

| Tier | Protocols | What it means |
|---|---|---|
| **Mandatory** | `KernelAttachable`, `BundleEntryReadable`, `BundleEntryWritable` | Gated by a real `isinstance` in production. The port-contract test asserts every shipped adapter implements them. Treat them as part of the floor. |
| **Optional, declaration-driven** | `Versionable`, `Draftable`, `Layered` | No `isinstance` anywhere today — the runtime gate is the corresponding flag (`versions` / `drafts` / `layers`). Implement the Protocol for typing and clarity; the flag is what actually decides. |
| **Typing only — do not gate on these** | `TenantAware`, `LayerAware` | ⚠️ `runtime_checkable` checks that a *method exists*, never that it accepts a *keyword*. `isinstance(src, TenantAware)` is `True` for any source with a `save_instance` at all. Use `write_kwarg_support(src)`. The source file warns about this in both classes. |
""",
        },
    ),
    (
        "kinds",
        {
            "title": "Kinds & extensions — what behaviour DNA knows about",
            "blurb": (
                "The kernel knows no Kinds. Every unit of identity and composition "
                "arrives through these ports, which is why adding a Kind never touches "
                "the core."
            ),
        },
    ),
    (
        "emit",
        {
            "title": "Emit — materializing an agent into a runtime",
            "blurb": (
                "Where the storage ports face *inward*, these face **out**: the kernel "
                "composes a neutral agent, and an emitter turns it into the native "
                "artifact one specific runtime consumes. Author once, emit per runtime."
            ),
        },
    ),
    (
        "runtime",
        {
            "title": "Runtime & threads — serving a live copilot",
            "blurb": (
                "Emitting produces a file. These ports produce a **running** agent, and "
                "the conversation state that outlives a single request. The thread "
                "ports are split along a real fault line — what the framework knows "
                "versus what only the host knows — and the split is the whole design."
            ),
        },
    ),
    (
        "judgement",
        {
            "title": "Judgement — where something decides",
            "blurb": (
                "Four seams where DNA deliberately declines to ship an opinion. Each is "
                "a place a model, a heuristic, or a human gets to be the authority — "
                "and DNA's position is that the authority is **yours to supply**, not "
                "ours to bundle."
            ),
        },
    ),
    (
        "internal",
        {
            "title": "Internal seams — not extension points",
            "blurb": (
                "These are Protocols, and they are not for you.\n\n"
                "They exist because the kernel was decomposed into collaborators "
                "(instance builder, query engine, write pipeline, …) and each "
                "collaborator's back-reference to the kernel was published as a narrow, "
                "typed slice instead of passing the whole kernel around. That keeps the "
                "decomposition honest and testable — a collaborator can only reach what "
                "its slice names.\n\n"
                "They are listed here for one reason: **invisible is worse than \"this "
                "is not for you\"**. If you go looking for the extension point and find "
                "twenty-two Protocols nobody explains, you cannot tell the seams from "
                "the scaffolding. Now you can. Implementing one of these means "
                "substituting a piece of the kernel for itself, which is a fork, not an "
                "extension."
            ),
        },
    ),
]


# ── shared prose fragments ────────────────────────────────────────────────

_SOURCE_KIT = (
    "`dna.testing.source_conformance_suite(factory)` — 26 cases, capability-aware "
    "(it reads your declared `capabilities()` and skips what you did not claim, "
    "fails what you claimed and did not honour). Wire it as one pytest case each:\n\n"
    "```python\n"
    "from dna.testing import source_conformance_suite\n\n"
    "CASES = source_conformance_suite(my_factory)\n\n"
    "@pytest.mark.asyncio\n"
    '@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)\n'
    "async def test_conformance(case):\n"
    "    await case.run()\n"
    "```\n\n"
    "Then add your adapter to the cross-adapter matrix — see "
    "[Proving a storage adapter](#proving-a-storage-adapter)."
)

_COLLABORATOR = (
    "A back-reference from one kernel collaborator to the narrow slice of the kernel "
    "it is allowed to reach. Published as a Protocol so the slice is typed and "
    "enforceable, not so anybody outside the kernel implements it."
)


def _internal(group_one_line: str, summary: str, why: str = _COLLABORATOR) -> dict:
    return {
        "group": "internal",
        "role": "internal",
        "one_line": group_one_line,
        "summary": summary,
        "not_for_you": why,
    }


# ── the catalogue ─────────────────────────────────────────────────────────

PROSE: dict[str, dict] = {
    # ══ storage ══════════════════════════════════════════════════════════
    "SourcePort": {
        "group": "storage",
        "role": "extend",
        "one_line": "Where instances are read from",
        "summary": (
            "The read half of a store. Everything DNA knows about your instances "
            "arrives through this port, so it is the first thing to implement and the "
            "only one with a 26-case battery waiting for it."
        ),
        "when": (
            "You want DNA's instances to live somewhere the shipped adapters do not "
            "reach — a document database, an object store, a git host, an internal "
            "content service, a read-only mount inside a wheel. Note that changing "
            "*between* filesystem, SQLite and Postgres needs no new adapter: that is a "
            "`dna.config.yaml` line, covered in "
            "[How to configure ports](../../guides/configuring-ports.md)."
        ),
        "minimum": (
            "The six names the boot gate checks — `supports_readers`, "
            "`load_bootstrap_docs`, `load_all`, `resolve_ref`, `load_layer`, `close` — "
            "plus an honest `capabilities()`. Be aware that the boot gate checks "
            "**names only** (that is all `runtime_checkable` can do); passing it means "
            "your adapter is shaped right, not that it works. The conformance kit is "
            "what checks behaviour."
        ),
        "lights_up": (
            "Nothing on its own: a read-only source is a complete, legitimate adapter "
            "(the `pkg://` package-data source is exactly that). Writing needs "
            "[`WritableSourcePort`](#writablesourceport); everything beyond the "
            "mandatory floor is declared through "
            "[the capability protocols](capabilities.md)."
        ),
        "prove": _SOURCE_KIT,
        "adapters_extra": [
            "`SqlAlchemySource` (`dna.adapters.sqlalchemy_.source`) — one class, two "
            "dialects (aiosqlite, asyncpg), and the only adapter that declares "
            "`edge_graph` / `as_of_reads` / `api_version_identity`",
            "`AsyncSourceAdapter` (`dna.adapters.async_adapter`) — a proxy, not a store",
        ],
    },
    "WritableSourcePort": {
        "group": "storage",
        "role": "extend",
        "one_line": "…and how they are written back",
        "summary": (
            "`SourcePort` plus writes, versions and drafts. This — not `SourcePort` — "
            "is what an adapter meant to back a real deployment implements; the "
            "adapter guide calls it mandatory for a reason."
        ),
        "when": (
            "Always, unless your store is genuinely read-only. A source that cannot "
            "write cannot host the SDLC board, the memory plane, or anything a user "
            "edits."
        ),
        "minimum": (
            "`save_instance` and `delete_instance` honouring at least the `tenant` "
            "kwarg, plus a `capabilities()` that tells the truth. `list_versions` may "
            "return `[]` and `publish` may be a no-op — the filesystem adapter does "
            "both — but see the warning under `Versionable`: declaring `versions=True` "
            "while keeping no history is precisely why `as_of_reads` had to become a "
            "separate flag."
        ),
        "lights_up": (
            "The optional write kwargs are individually declared and individually "
            "gated: `if_absent` (atomic create), `if_match` (guarded update), `edges` "
            "(persist the derived reference graph in the *same* transaction), "
            "`author`, `layer`, `write_class`, `version_retention`. The kernel reads "
            "your declared `write_kwargs` and **never passes a kwarg you did not "
            "declare** — so an unadopted kwarg degrades to the feature being off, not "
            "to your adapter silently dropping data. `edges` is the sharp one: an "
            "adapter that does not declare it is never handed edges, and the graph "
            "face answers `unsupported` rather than an empty edge list."
        ),
        "prove": _SOURCE_KIT,
    },
    "BundleHandle": {
        "group": "storage",
        "role": "extend",
        "one_line": "Reading and writing one bundle's files",
        "summary": (
            "A store-agnostic handle over a bundle's entries — the thing a Reader or "
            "Writer actually touches, so neither has to know whether the bundle is a "
            "directory on disk or a set of rows."
        ),
        "when": (
            "You are writing a source adapter whose bundles are not directories. If "
            "your store keeps entries as blobs, rows or object-store keys, this is the "
            "shim that lets every shipped Reader and Writer work against it unchanged."
        ),
        "minimum": (
            "The read side — `name`, `exists`, `read_text`, `read_bytes`, "
            "`iter_entries`, `is_file`. `write_text` / `write_bytes` only if bundles "
            "are writable in your store; `path` only if a real filesystem path exists "
            "(return `None` when it does not, rather than inventing one)."
        ),
        "lights_up": (
            "Every registered Reader and Writer over your store. Skip it and bundle "
            "formats — `SKILL.md`, `SOUL.md`, `AGENTS.md` trees — are unreachable, "
            "though single-instance Kinds still work."
        ),
        "prove": (
            "`dna.testing.reader_writer_conformance_suite(...)` runs every registered "
            "Reader/Writer pair against real market bundles; point it at a handle from "
            "your store and the whole registry becomes your test."
        ),
        "adapters_extra": [
            "`FilesystemBundleHandle` (`dna.kernel.bundle.handle`) — a directory on disk",
            "`DictBundleHandle` (`dna.kernel.bundle.handle`) — entries held in memory, "
            "the shape a row-backed store follows",
        ],
    },
    "CachePort": {
        "group": "storage",
        "role": "extend",
        "one_line": "Where installed dependencies are cached",
        "summary": (
            "The local store for bundles pulled from outside — what a `ResolverPort` "
            "fetches lands here, keyed so a second install is a lookup."
        ),
        "when": (
            "Your deployment has no writable local disk (a read-only container, a "
            "serverless function) or you want the cache shared between replicas. This "
            "is one of the rarer swaps."
        ),
        "minimum": "All four: `load_all`, `load_key`, `store`, `has`.",
        "lights_up": (
            "Installing from a repository at all. There is a private no-op cache the "
            "kernel falls back to for non-filesystem sources, so a missing cache "
            "degrades to *nothing is ever cached* rather than to an error — slow, not "
            "broken."
        ),
        "prove": (
            "No dedicated kit. `FilesystemCache` (`dna.adapters.filesystem.cache`) is "
            "small enough to read end to end and is the reference; exercise yours "
            "through `dna install` against a real bundle."
        ),
        "adapters_extra": [
            "`_NoopCache` (`dna.kernel.boot.bootstrap`) — the private fallback for "
            "non-filesystem sources; a second implementation, but not a second *store*"
        ],
    },
    "ResolverPort": {
        "group": "storage",
        "role": "extend",
        "one_line": "How an external dependency is fetched",
        "summary": (
            "One resolver per URI scheme. `local:`, `github:`, `http(s):`, the Helix "
            "and registry resolvers — five shipped, none of which inherit the Protocol, "
            "which makes this the clearest example in the tree of structural typing "
            "doing its job."
        ),
        "when": (
            "You publish bundles somewhere with its own scheme or its own auth — an "
            "internal artifact registry, S3, an authenticated Git host, an OCI "
            "registry. This is the most commonly written port after `SourcePort`, and "
            "the cheapest."
        ),
        "minimum": (
            "`resolve` (fetch and return the bundle) and `cache_key` (a stable, "
            "collision-free identity for what you fetched — get this wrong and the "
            "cache serves the wrong bundle, which is worse than not caching)."
        ),
        "lights_up": (
            "`dna install` for your scheme. Unregistered schemes fail loud with the "
            "list of known ones, so a missing resolver is never a silent no-op."
        ),
        "prove": (
            "No dedicated kit — the five shipped resolvers are each ~40 lines and are "
            "the specification by example. Copy the shape of "
            "`dna.adapters.resolvers.http`."
        ),
        "adapters_extra": [
            "`LocalResolver` (`dna.adapters.resolvers.local`)",
            "`GitHubResolver` (`dna.adapters.resolvers.github`)",
            "`HttpResolver` (`dna.adapters.resolvers.http`)",
            "`HelixResolver` (`dna.adapters.resolvers.helix`)",
            "`RegistryResolver` (`dna.adapters.resolvers.registry`)",
        ],
    },
    "ReaderPort": {
        "group": "storage",
        "role": "extend",
        "one_line": "How a bundle format is detected and parsed",
        "summary": (
            "Given a bundle, decide whether you recognise it and turn it into a raw "
            "dict. Ten shipped, and unlike most ports here they all inherit the "
            "Protocol explicitly."
        ),
        "when": (
            "You are adding a Kind whose on-disk shape is not plain YAML — a Markdown "
            "file with front-matter, a multi-file convention, somebody else's existing "
            "format you want DNA to read in place."
        ),
        "minimum": (
            "`detect` must be **cheap and certain**: it runs against every bundle, and "
            "a reader that claims bundles it cannot parse breaks unrelated Kinds. "
            "`read` then does the work."
        ),
        "lights_up": (
            "Your format becoming loadable. Without one, a bundle in your layout is "
            "invisible — not an error, simply not found, which is the failure mode "
            "hardest to debug from the outside. Test `detect` against bundles that are "
            "*not* yours before you test it against ones that are."
        ),
        "prove": (
            "`dna.testing.reader_writer_conformance_suite(...)` — it runs every "
            "registered pair, so registering yours enrols it automatically. "
            "`packages/sdk-py/tests/test_rw_conformance_kit.py` is the in-tree example."
        ),
    },
    "WriterPort": {
        "group": "storage",
        "role": "extend",
        "one_line": "…and how it is written back",
        "summary": (
            "The inverse of a Reader, and the half people forget. Eleven shipped. A "
            "Kind that reads but does not write is editable by hand and by nothing else."
        ),
        "when": "Whenever you write a Reader and the format is meant to be editable.",
        "minimum": (
            "`can_write`, `write`, `serialize`. The round trip is the contract: "
            "`read(write(x))` must equal `x`, and the conformance kit checks exactly "
            "that against real bundles."
        ),
        "lights_up": (
            "Writes through the REST/MCP faces for your Kind, and the CLI's edit path. "
            "Without a Writer the kernel refuses the write rather than picking a format "
            "for you."
        ),
        "prove": "Same suite as `ReaderPort` — they are graded as a pair, on purpose.",
    },
    "RecordSearchProvider": {
        "group": "storage",
        "role": "extend",
        "one_line": "Semantic search over record-plane instances",
        "summary": (
            "Semantic (not lexical) retrieval over records. Two shipped — sqlite-vec "
            "and pgvector — sharing **zero code** and graded by one suite, which is "
            "about the strongest evidence a port is genuinely pluggable rather than "
            "one implementation wearing an interface."
        ),
        "when": (
            "You have a vector store already — Qdrant, Weaviate, Elasticsearch, a "
            "managed search service — and would rather DNA use it than run a second one."
        ),
        "minimum": (
            "`search`. Register it on the kernel; a provider that fails to register is "
            "simply absent."
        ),
        "lights_up": (
            "Semantic `recall` and record search. **The degradation here is the polite "
            "one and you should know it is happening:** with no provider the kernel "
            "falls back to a lexical scan, which returns plausible results that are not "
            "semantic ones. Nothing errors. Check which provider is live rather than "
            "assuming embeddings are in play."
        ),
        "prove": (
            "`dna.testing.record_search_conformance_suite(...)` plus "
            "`run_record_search_conformance(...)` for a non-pytest runner. "
            "`test_pgvector_search_conformance.py` shows a provider that needs a live "
            "database wiring itself in."
        ),
        "adapters_extra": [
            "`SqliteVecRecordSearchProvider` (`dna.adapters.search.sqlite_vec`)",
            "`PgVecRecordSearchProvider` (`dna.adapters.search.pgvector`) — the two "
            "share zero code, which is what makes this port demonstrably pluggable",
        ],
    },
    "EmbeddingPort": {
        "group": "storage",
        "role": "extend",
        "one_line": "Turning text into vectors",
        "summary": (
            "The sibling of `RecordSearchProvider`: one turns text into vectors, the "
            "other searches over them. Kept separate so you can change the model "
            "without changing the store."
        ),
        "when": (
            "You want a different embedding model, a hosted embedding API, or a "
            "multilingual model. The shipped ONNX provider is all-MiniLM and runs "
            "locally."
        ),
        "minimum": (
            "`embed`. Dimensionality must match whatever your search provider indexed "
            "— changing the model without reindexing produces results that are wrong "
            "rather than absent."
        ),
        "lights_up": (
            "Real semantic similarity. The default is `FakeEmbeddingProvider`, a "
            "deterministic zero-dependency floor: it is stable, it is not meaningful, "
            "and it will not tell you so. This is the same shape of trap as the search "
            "fallback — verify which provider is live."
        ),
        "prove": (
            "`dna.testing.memory_scoring_conformance_suite(...)` grades ranking "
            "quality, which is the property an embedding change actually moves."
        ),
        "adapters_extra": [
            "`FakeEmbeddingProvider` (`dna.kernel.embedding`) — the deterministic "
            "zero-dependency default, meaningful only as a floor",
            "`OnnxEmbeddingProvider` (`dna.adapters.embedding.onnx`) — all-MiniLM, "
            "behind the `embed-onnx` extra",
        ],
    },
    "KernelEventBus": {
        "group": "storage",
        "role": "extend",
        "one_line": "Cross-process cache invalidation",
        "summary": (
            "How a *second* process learns that the first one wrote. Without it every "
            "replica caches independently and serves stale composition until something "
            "evicts it."
        ),
        "when": (
            "You run more than one replica against a store whose adapter cannot notify "
            "— which today means any store that is not Postgres."
        ),
        "minimum": (
            "`start` and `stop`. `PostgresEventBus` is the only implementation: a "
            "durable outbox row plus `pg_notify`, both written inside the write "
            "transaction so a crash cannot lose the notification."
        ),
        "lights_up": (
            "Cache coherence across processes, declared by the adapter as "
            "`supports_cross_process_invalidation`. **This is the catalogue's live "
            "known gap:** the filesystem and SQLite adapters declare it `False` and "
            "carry a `strict=True` xfail in the conformance matrix "
            "(`s-sqlite-cross-process-invalidation`). They declare `False` rather than "
            "staying quiet precisely so the gap is visible — a multi-process deployment "
            "on either serves stale data, silently, and always has. **A new adapter "
            "inherits this gap or solves it**, and nobody discovers which by reading "
            "code at random, so decide deliberately and declare the answer."
        ),
        "prove": (
            "`tests/test_cross_process_invalidation_capability.py` pins the declared "
            "flag per adapter and needs no database. "
            "`test_adapter_conformance_matrix.py::test_cross_process_invalidation_capability` "
            "is the behavioural row."
        ),
    },
    # ══ capabilities ══════════════════════════════════════════════════════
    "BundleEntryReadable": {
        "group": "capabilities",
        "role": "extend",
        "one_line": "Read one entry out of a bundle",
        "summary": (
            "**Mandatory in practice.** The adapter guide lists it alongside "
            "`WritableSourcePort` and `KernelAttachable` as what every adapter "
            "implements, and the port-contract test asserts it of all of them."
        ),
        "when": "Always. Treat this as part of the floor, not as optional.",
        "minimum": (
            "`fetch_bundle_entry` and `list_bundle_entries`. Both may be sync or "
            "async — the kernel awaits what is awaitable, so the filesystem adapter "
            "returns bytes directly and the SQL ones return coroutines, and both are "
            "conformant."
        ),
        "lights_up": (
            "Declared as `bundle_read`. The production gate is an "
            "`isinstance(source, BundleEntryReadable)` in `dna.kernel.bundle.io`, "
            "**not** the flag — skip the Protocol and every bundle read raises "
            "`NotImplementedError` naming this Protocol, which is at least a good "
            "error message."
        ),
        "prove": "`source_conformance_suite` case `bundle_entry_round_trip`.",
    },
    "BundleEntryWritable": {
        "group": "capabilities",
        "role": "extend",
        "one_line": "Write or delete one entry in a bundle",
        "summary": "The write half of the pair above. Same rules, same gate.",
        "when": "Whenever your source is writable at all.",
        "minimum": "`write_bundle_entry` and `delete_bundle_entry`; sync or async.",
        "lights_up": (
            "Declared as `bundle_write`; gated in production by `isinstance` in "
            "`dna.kernel.bundle.io`. Skip it and bundle writes raise, naming the "
            "Protocol."
        ),
        "prove": "`source_conformance_suite` case `bundle_entry_round_trip`.",
    },
    "Versionable": {
        "group": "capabilities",
        "role": "extend",
        "one_line": "Per-Kind semver versioning",
        "summary": (
            "Your store can return a specific published version of an instance. Worth "
            "reading the caveat below before you declare it."
        ),
        "when": (
            "Your store keeps version rows and can hand back a past one by id. If it "
            "does not, do not declare `versions` — see the trap."
        ),
        "minimum": "`get_version`.",
        "lights_up": (
            "The `versions` flag, which says **version rows are readable** and nothing "
            "more. ⚠️ It does *not* mean history exists: the filesystem adapter "
            "declares `versions=True` and `list_versions` returns `[]`. That gap is "
            "exactly why the ability to answer *what did you believe at time T* became "
            "a **separate** flag, `as_of_reads` — a store that cannot reconstruct the "
            "past must let the face raise `AsOfUnsupported` (REST **501**) rather than "
            "serve today's instance under yesterday's timestamp. And when history "
            "existed but was pruned, that is `AsOfTruncated` (REST **410**), never a "
            "`LookupError`: *the instance did not exist yet* is an answer, and must not "
            "render the same as *I no longer hold the record*."
        ),
        "prove": "`source_conformance_suite` case `versions_surface`.",
    },
    "Draftable": {
        "group": "capabilities",
        "role": "extend",
        "one_line": "Draft / publish lifecycle",
        "summary": "Instances that exist before they are live.",
        "when": (
            "Your store can hold an unpublished instance that reads do not see. If "
            "publishing is a no-op for you (as on the filesystem), declare "
            "`drafts=False`."
        ),
        "minimum": "`load_drafts` **and** `publish` — the probe requires both.",
        "lights_up": (
            "The `drafts` flag and the draft lifecycle across the faces. Undeclared, "
            "everything written is immediately live."
        ),
        "prove": "`source_conformance_suite` case `drafts_lifecycle`.",
    },
    "Layered": {
        "group": "capabilities",
        "role": "extend",
        "one_line": "Overlay (tenant / layer) resolution",
        "summary": (
            "Resolving an instance through an overlay — the mechanism behind tenancy "
            "and per-customer forks."
        ),
        "when": "Your store can key an instance by an overlay dimension as well as by name.",
        "minimum": "`load_layer`, returning `None` for an unknown layer rather than raising.",
        "lights_up": (
            "The `layers` flag and the overlay engine. ⚠️ The known divergence to "
            "inherit or fix: the SQLite dialect's `instances` primary key omits "
            "`tenant`, so an overlay publish clobbers the base row. It is a "
            "`strict=True` xfail in both the matrix and the conformance kit's `_KNOWN` "
            "divergence table. Postgres passes with identical logic — this is schema "
            "debt, not a design limit — so if your store can key by tenant, key by "
            "tenant."
        ),
        "prove": (
            "`source_conformance_suite` case `tenant_overlay_shadows_base`, and the "
            "matrix's `test_tenant_overlay_shadows_base` row."
        ),
    },
    "KernelAttachable": {
        "group": "capabilities",
        "role": "extend",
        "one_line": "Accept the kernel after construction",
        "summary": (
            "**Mandatory.** The kernel hands itself to the adapter once wiring is done, "
            "so the adapter can reach the Kind registry it needs to interpret what it "
            "is storing."
        ),
        "when": "Always. The port-contract test asserts every adapter implements it.",
        "minimum": (
            "`attach_kernel(kernel)`, and it **must be idempotent** — it can be called "
            "more than once, and a non-idempotent implementation corrupts state in ways "
            "that surface far from the cause."
        ),
        "lights_up": (
            "Declared as `kernel_attachable`; gated by `isinstance` at boot. Uniquely "
            "on this page the failure is **fail-soft** — boot logs a warning and "
            "continues, so a missing `attach_kernel` shows up later as an adapter that "
            "cannot resolve Kinds rather than as a boot error. Do not rely on boot to "
            "tell you."
        ),
        "prove": (
            "`packages/sdk-py/tests/test_port_contract.py` asserts it of every adapter; "
            "the kit's `port_surface` case covers the shape."
        ),
    },
    "TenantAware": {
        "group": "capabilities",
        "role": "extend",
        "one_line": "Writes accept a first-class tenant",
        "summary": (
            "Documentation and static typing. Read the warning — this Protocol is the "
            "one place on this page where `isinstance` is the **wrong** tool, and the "
            "source says so itself."
        ),
        "when": (
            "You are writing a source adapter and want your editor and type-checker to "
            "hold you to the modern write contract. Declare the *behaviour* through "
            "`capabilities().write_kwargs`, which is what the kernel actually reads."
        ),
        "minimum": (
            "`save_instance` / `delete_instance` accepting `tenant=`, and `\"tenant\"` "
            "present in your declared `write_kwargs` / `delete_kwargs`."
        ),
        "lights_up": (
            "The `tenant_layer_writes` flag and the tenant kwarg being passed at all. "
            "⚠️ **Never gate on `isinstance(src, TenantAware)`.** A "
            "`runtime_checkable` Protocol checks that methods *exist*, never that they "
            "accept a keyword — so that check is `True` for any source with a "
            "`save_instance` at all, including ones that would reject the kwarg. The "
            "kernel uses `write_kwarg_support(src)`, a memoized signature probe, and so "
            "should you."
        ),
        "prove": (
            "`source_conformance_suite` case `declared_write_kwargs_accepted`, which "
            "checks your declaration against what your signatures really take."
        ),
    },
    "LayerAware": {
        "group": "capabilities",
        "role": "extend",
        "one_line": "Writes accept a layer overlay",
        "summary": "The `layer=` twin of `TenantAware`, with the identical caveat.",
        "when": "Same as `TenantAware` — you want the contract expressed in types.",
        "minimum": "`save_instance` accepting `layer=`, plus the matching `write_kwargs` entry.",
        "lights_up": (
            "The layer half of `tenant_layer_writes`. Same trap: use "
            "`write_kwarg_support`, not `isinstance`."
        ),
        "prove": "`source_conformance_suite` case `declared_write_kwargs_accepted`.",
    },
    # ══ kinds ════════════════════════════════════════════════════════════
    "KindPort": {
        "group": "kinds",
        "role": "extend",
        "one_line": "What a Kind is, and how it composes",
        "summary": (
            "Identity, schema and composition role for one Kind. The port that makes "
            "*the kernel knows no Kinds* true."
        ),
        "when": (
            "Only when your Kind needs custom behaviour — a bespoke bundle format, a "
            "typed parse step, a composition rule. A record-shaped Kind with none of "
            "that needs **no class at all**: write a `*.kind.yaml` descriptor and "
            "register it with `kind_from_descriptor()`. Reach for a class second, not "
            "first."
        ),
        "minimum": (
            "`kind`, `alias`, `api_version`, `plane` and `schema()`. Everything else "
            "has a default."
        ),
        "lights_up": (
            "Your Kind across every face at once — CLI, REST, MCP, the generic "
            "instance tools — because those faces are generic over the registry. It "
            "also enrols your Kind in "
            "[the generated Kinds reference](../kinds/index.md), so registering is "
            "what makes it documented."
        ),
        "prove": (
            "Register it and let `scripts/gen_kinds_docs.py` and "
            "`scripts/docs_coverage_guard.py` run — the first proves the kernel sees "
            "it, the second fails the build until prose exists for it."
        ),
        "adapters_extra": [
            "`KindBase` (`dna.kernel.kinds.base`) — the base every built-in Kind "
            "subclasses; third-party Kinds may satisfy the Protocol structurally instead"
        ],
    },
    "KindPresentation": {
        "group": "kinds",
        "role": "extend",
        "one_line": "How a Kind previews and draws itself",
        "summary": (
            "An optional slice of a Kind: the short preview a list renders, and the "
            "metadata a graph view needs."
        ),
        "when": "Your Kind shows up in a UI and the default rendering is unhelpful.",
        "minimum": "Either `preview` or `graph_meta`; both are optional.",
        "lights_up": (
            "Richer rendering in the console and graph views. Omitted, callers get the "
            "generic presentation — a real degradation, not a failure."
        ),
        "prove": "Covered by your Kind's own tests; there is no separate battery.",
    },
    "KindRelations": {
        "group": "kinds",
        "role": "extend",
        "one_line": "What a Kind points at",
        "summary": (
            "The declared relations of a Kind — attribute-shaped, which is why it has "
            "no methods."
        ),
        "when": (
            "Your Kind references other instances and you want those references in the "
            "derived reference graph."
        ),
        "minimum": "The declared relation attributes; see the source docstring above.",
        "lights_up": (
            "Edges in the reference graph — **if the active source records edges**. "
            "This is the sharpest instance of the catalogue's central rule: on a store "
            "that declares `edge_graph=False`, the graph face answers `unsupported` "
            "(REST **501**) and not an empty list, because `[]` reads as *nothing "
            "points at this instance*, and that is a claim only a store which actually "
            "keeps edges may make. Declaring relations on a filesystem-backed "
            "deployment is therefore not wrong — it is simply unanswerable, and the "
            "face says so."
        ),
        "prove": (
            "`dna graph` against a Postgres-backed source; "
            "`tests/test_graph_traversal.py` is the in-tree reference."
        ),
    },
    "Extension": {
        "group": "kinds",
        "role": "extend",
        "one_line": "A package of Kinds, readers, writers and hooks",
        "summary": (
            "The unit of packaging. One `register()` call contributes everything your "
            "extension adds; 21 ship in-tree, declared as entry points."
        ),
        "when": (
            "You are shipping more than one Kind, or any Kind plus its reader/writer, "
            "or you want your Kinds discovered by installation rather than by import."
        ),
        "minimum": (
            "`register(host)`. Declare it under the `dna.extensions` entry-point group "
            "and installing your package is all the wiring there is."
        ),
        "lights_up": (
            "Auto-discovery at `Kernel.auto()`. The kernel validates every registration "
            "at boot and fails loud on conflicts — duplicate `(apiVersion, kind)`, "
            "duplicate aliases, a Reader missing a required method — so a broken "
            "extension stops boot rather than half-registering."
        ),
        "prove": (
            "Boot `Kernel.auto()` and assert your Kinds are in `kernel.kind_ports()`. "
            "The 21 shipped extensions are the worked examples."
        ),
        "adapters_extra": [
            "21 in-tree extensions — helix, agentskills, soulspec, agentsmd, "
            "guardrails, kinddef, hooks, safety, recognizer, evidence, audit, collab, "
            "sdlc, federation, testkit, tenant, lesson, research, doc, modelreg — each "
            "declared under the `dna.extensions` entry-point group rather than "
            "subclassing anything",
        ],
    },
    "ExtensionHost": {
        "group": "kinds",
        "role": "receive",
        "one_line": "The registration surface handed to an Extension",
        "summary": (
            "The nine things you may do inside `Extension.register()`: register a Kind "
            "(from a class or a descriptor), a reader, a writer, a hook, a veto, a "
            "tool, a composition profile."
        ),
        "not_for_you": (
            "The kernel implements it and passes it into your `register()`. You call "
            "these methods; you never satisfy this Protocol. It is on this page because "
            "it is the **menu** — everything an extension is allowed to contribute is "
            "in the table below, and nothing else is."
        ),
    },
    "TemplateProvider": {
        "group": "kinds",
        "role": "extend",
        "one_line": "Scaffold file trees shipped by an extension",
        "summary": "An optional extra capability of an `Extension`: ship starter files.",
        "when": "Your extension has a `dna new`-style starting point worth shipping.",
        "minimum": "`templates()`.",
        "lights_up": (
            "Your templates in the scaffolding commands. Detected by feature test, so "
            "omitting it is invisible and harmless."
        ),
        "prove": (
            "`SafetyPolicyExtension.templates()` "
            "(`dna.extensions.safety`) is the only shipped implementation and the "
            "reference."
        ),
        "adapters_extra": [
            "`SafetyPolicyExtension` (`dna.extensions.safety`) — satisfies it "
            "structurally, via an optional `templates()` method"
        ],
    },
    "ToolPort": {
        "group": "kinds",
        "role": "extend",
        "one_line": "A tool an agent can invoke",
        "summary": (
            "A callable exposed to agents, wrapping a LangChain `StructuredTool` so "
            "framework compatibility is preserved while DNA adds discovery and policy "
            "on top."
        ),
        "when": (
            "Rarely as a *class*. `ToolDefinition` is the concrete implementation and "
            "almost everyone should instantiate it rather than write a second one — "
            "the pluralism here is in the tool instances, not in implementations of "
            "the port."
        ),
        "minimum": "`get_callable()`.",
        "lights_up": (
            "The tool over the MCP face and in emitted agents. Note that the tool "
            "*definition* is data — see "
            "[Tools as data](../../guides/tools-as-data.md) — so the usual answer is a "
            "declared tool, not a new class."
        ),
        "prove": "Exercise it through `dna mcp serve` and the `list_tools` face.",
    },
    # ══ emit ═════════════════════════════════════════════════════════════
    "EmitterPort": {
        "group": "emit",
        "role": "extend",
        "one_line": "How a composed agent becomes a runtime's native artifact",
        "summary": (
            "Seven targets ship. A new one is a class plus one `register_emitter(...)` "
            "call, and the emit core never changes — which is the claim the port exists "
            "to make good on."
        ),
        "when": (
            "You want to run DNA-authored agents on a runtime DNA does not emit for "
            "yet. Two flavours satisfy the same port: **config-declarative** (project "
            "onto a published YAML/JSON schema) and **scaffold-code** (fill a curated "
            "`{framework × case}` template)."
        ),
        "minimum": (
            "`emit(ctx)` and `extract_instructions(artifact)` — plus a `target` id. The "
            "second is not optional bookkeeping: it is how the invariant below is "
            "checked against your own output."
        ),
        "lights_up": (
            "`dna emit --target <yours>`. The **central invariant** is that the "
            "composed instruction in your artifact is **byte-equal** to `build_prompt`: "
            "the emit carries the composition verbatim, and one generic test runs that "
            "check over *every* registered target, yours included the moment you "
            "register. Return `None` from `extract_instructions` only when the target "
            "genuinely has no instruction slot — returning a re-serialized "
            "approximation defeats the check without failing it."
        ),
        "prove": (
            "Register the emitter and the generic round-trip test adopts it "
            "automatically. `packages/sdk-py/tests/test_emit_agent_framework.py` shows "
            "the shape, including how an upstream bug is carried as a documented "
            "`strict=True` xfail rather than worked around."
        ),
        "adapters_extra": [
            "`ScaffoldEmitter` (`dna.emit.scaffold`) — the base for code-first targets",
            "`AgentFrameworkEmitter` (`dna.emit.agent_framework`)",
            "`BedrockEmitter` (`dna.emit.bedrock`)",
            "`VertexEmitter` (`dna.emit.vertex`)",
            "`OpenAIAgentsEmitter` (`dna.emit.openai_agents`)",
            "`LanggraphEmitter` (`dna.emit.langgraph`)",
            "`AgnoEmitter` (`dna.emit.agno`)",
            "`DeepAgentsEmitter` (`dna.emit.deepagents`)",
        ],
    },
    "ScaffoldResolver": {
        "group": "emit",
        "role": "extend",
        "one_line": "Where a scaffold template's source comes from",
        "summary": (
            "Resolves a `{framework × case}` template to its Mustache source. One "
            "implementation ships, reading templates out of package data."
        ),
        "when": (
            "You want scaffold templates to come from somewhere else — a kernel-backed "
            "Kind so they are editable as data, a remote catalogue, a per-tenant "
            "override. Serving templates from the kernel is named future work "
            "(`s-scaffold-as-kind`), so this seam has a known intended second user."
        ),
        "minimum": "`resolve`. Install it with `set_scaffold_resolver(...)`.",
        "lights_up": (
            "Every scaffold-code emitter at once, since they all resolve through the "
            "active resolver. An unresolvable template fails the emit loudly."
        ),
        "prove": (
            "Emit through a scaffold target and assert the byte-equality invariant "
            "still holds — a resolver that returns the wrong template breaks it, which "
            "is the check you want."
        ),
        "adapters_extra": [
            "`PackageDataScaffoldResolver` (`dna.emit.scaffold`) — the default, reads "
            "from package data"
        ],
    },
    # ══ runtime ══════════════════════════════════════════════════════════
    "RuntimePort": {
        "group": "runtime",
        "role": "extend",
        "one_line": "How a composed agent becomes a *running* one",
        "summary": (
            "An emitter writes a file; a runtime adapter builds a live app. Two ship — "
            "LangChain and Microsoft Agent Framework — behind their own extras, and "
            "each import is independently guarded so a missing extra removes one "
            "backend instead of breaking the registry."
        ),
        "when": (
            "You want to serve DNA agents on a framework neither shipped adapter "
            "covers."
        ),
        "minimum": (
            "`build(ctx, hooks)` returning an `AGUIApp`, and a `target` id. Register "
            "with `register_runtime(...)`."
        ),
        "lights_up": (
            "`serving.framework: <yours>` becoming a valid declaration, and the copilot "
            "serving on your backend. An unregistered target fails with the list of "
            "available ones — which will be short if an extra is missing, so check what "
            "is installed before concluding a target is unsupported."
        ),
        "prove": (
            "Serve a real agent and drive it over AG-UI. There is no unit-level battery "
            "here; `dna.runtime.adapters.langchain_rt` is the reference to read."
        ),
        "adapters_extra": [
            "`LangChainRuntime` (`dna.runtime.adapters.langchain_rt`) — target "
            "`langchain`, needs the `[runtime]` extra",
            "`MafRuntime` (`dna.runtime.adapters.maf_rt`) — target `maf`, needs the "
            "`[maf]` extra",
        ],
    },
    "AGUIApp": {
        "group": "runtime",
        "role": "extend",
        "one_line": "The mountable app a runtime adapter returns",
        "summary": (
            "The handle a `RuntimePort` hands back: a framework-agnostic AG-UI app the "
            "host mounts on a path."
        ),
        "when": "Whenever you implement `RuntimePort` — you have to return one of these.",
        "minimum": "`attach(app, path)`.",
        "lights_up": (
            "The copilot being reachable over HTTP at all. Note the standing house "
            "rule: AG-UI has official client libraries, and the wire protocol is not "
            "something to re-derive from its specification. Your job is mounting, not "
            "re-implementing the protocol."
        ),
        "prove": "Drive it with an official AG-UI client, not with a hand-rolled one.",
    },
    "ThreadStorePort": {
        "group": "runtime",
        "role": "extend",
        "one_line": "The whole conversation contract",
        "summary": (
            "Index plus transcript plus the portability write. Implement this when one "
            "component can honestly answer all three; implement the halves separately "
            "when it cannot — which is the usual case, and the reason the halves exist."
        ),
        "when": (
            "You are backing conversations with a store that owns both the index and "
            "the messages."
        ),
        "minimum": "Both parent Protocols, plus `import_transcript`.",
        "lights_up": (
            "Conversation history, ownership checks, and thread export/import end to "
            "end."
        ),
        "prove": (
            "`InMemoryThreadStore` (`dna.runtime.thread_store`) implements the whole "
            "port and is the readable reference."
        ),
        "adapters_extra": [
            "`InMemoryThreadStore` (`dna.runtime.thread_store`) — the only complete "
            "implementation; satisfies the port structurally"
        ],
    },
    "ThreadTranscriptPort": {
        "group": "runtime",
        "role": "extend",
        "one_line": "Reading the messages of a conversation",
        "summary": (
            "The half the **framework** can answer. The transcript lives inside the "
            "framework's own mechanism — LangGraph checkpoints, say — so this port is a "
            "projection of it, not a second copy."
        ),
        "when": (
            "You are adapting a new agent framework and want its conversation history "
            "readable through DNA."
        ),
        "minimum": "`fetch_transcript`; `export_transcript` for portability.",
        "lights_up": (
            "History in the console, and thread export. Without it a conversation runs "
            "fine and is simply unreadable afterwards."
        ),
        "prove": (
            "`LangGraphTranscriptStore` (`dna.runtime.adapters.langgraph_threads`) is "
            "the worked example of projecting a framework's own store."
        ),
        "adapters_extra": [
            "`LangGraphTranscriptStore` (`dna.runtime.adapters.langgraph_threads`)",
            "`InMemoryThreadStore` (`dna.runtime.thread_store`)",
        ],
    },
    "ThreadIndexPort": {
        "group": "runtime",
        "role": "extend",
        "one_line": "Whose conversation is this, and what are mine",
        "summary": (
            "The half the framework **cannot** answer. A checkpointer knows messages; "
            "it does not know users. This index is the only place ownership is written "
            "down."
        ),
        "when": (
            "Always, if conversations belong to people. Ownership is an authorization "
            "input, not a display convenience."
        ),
        "minimum": "`index_thread`, `fetch_threads`, `thread_owner`.",
        "lights_up": (
            "\"My conversations\" lists, and the ownership check that stops one user "
            "reading another's thread. Skip it and there is nothing to check against — "
            "which is the failure mode to think hardest about on this page."
        ),
        "prove": (
            "`InMemoryThreadStore` is the reference; test ownership with two distinct "
            "users, not one."
        ),
        "adapters_extra": ["`InMemoryThreadStore` (`dna.runtime.thread_store`)"],
    },
    "ThreadPurgePort": {
        "group": "runtime",
        "role": "extend",
        "one_line": "Retention: find expired threads and drop them",
        "summary": (
            "The two primitives only the party holding the connection can perform, and "
            "everything the retention sweep needs from the host."
        ),
        "when": (
            "You have a retention policy — which, for conversation data, is usually a "
            "legal position rather than a preference."
        ),
        "minimum": "`expired_threads` and `delete_thread`.",
        "lights_up": (
            "`sweep_retention`. Without it the sweep has nothing to call and "
            "conversations are kept forever — silently, because nothing errors when "
            "deletion simply never happens."
        ),
        "prove": "Run `sweep_retention` against seeded expired threads and assert they are gone.",
        "adapters_extra": ["`InMemoryThreadStore` (`dna.runtime.thread_store`)"],
    },
    "TranscriptPurgePort": {
        "group": "runtime",
        "role": "extend",
        "one_line": "…and the half only the framework can delete",
        "summary": (
            "Deleting the thread row is not deleting the conversation. The messages "
            "live in the framework's store, and only the framework adapter can make "
            "them go."
        ),
        "when": (
            "You implement `ThreadPurgePort`. These two are a pair: index-side deletion "
            "without transcript-side deletion leaves the content on disk while the "
            "system reports it deleted, and that gap is the one worth being paranoid "
            "about."
        ),
        "minimum": "`delete_transcript` — really deleting, not tombstoning.",
        "lights_up": "Deletion that is true when someone asks whether the data is gone.",
        "prove": (
            "`LangGraphTranscriptPurge` (`dna.runtime.adapters.langgraph_threads`) "
            "removes the thread's checkpoint rows; assert at the store, not through "
            "the API that just told you it worked."
        ),
        "adapters_extra": [
            "`LangGraphTranscriptPurge` (`dna.runtime.adapters.langgraph_threads`)"
        ],
    },
    # ══ judgement ════════════════════════════════════════════════════════
    "ContradictionScribe": {
        "group": "judgement",
        "role": "extend",
        "one_line": "Deciding whether two memories actually contradict",
        "summary": (
            "The external judgement seam, for the pairs the deterministic rule cannot "
            "settle. **Zero in-tree implementations, by design** — DNA ships the "
            "question and declines to ship the judge."
        ),
        "when": (
            "You want a model or a human to adjudicate the ambiguous cases. Note it is "
            "a plain callable, not a class — the simplest port on this page to satisfy."
        ),
        "minimum": "One `__call__`. A function is enough.",
        "lights_up": (
            "Contradiction detection beyond what the rule decides on its own. Supply "
            "nothing and the ambiguous pairs are left undecided rather than guessed at "
            "— the intended behaviour, not a gap."
        ),
        "prove": (
            "`dna.testing.memory_conformance_suite(...)`, which grades the memory "
            "plane's behaviour as a whole."
        ),
    },
    "MergeScribe": {
        "group": "judgement",
        "role": "extend",
        "one_line": "Fusing two memories into one",
        "summary": (
            "The external synthesis seam, and the exact contract a fusion scribe fills. "
            "Also zero in-tree implementations, for the same reason."
        ),
        "when": "You want consolidation to synthesize rather than merely pick a winner.",
        "minimum": "One `__call__`.",
        "lights_up": (
            "Synthesizing consolidation. Without one, consolidation keeps to its "
            "deterministic behaviour."
        ),
        "prove": "`dna.testing.memory_conformance_suite(...)`.",
    },
    "EvalTargetPort": {
        "group": "judgement",
        "role": "extend",
        "one_line": "What an eval case is actually run against",
        "summary": (
            "Turns one `EvalCase` into the **text** the checks are applied to. The "
            "shipped target composes a prompt; anything you can produce text from can "
            "be a target."
        ),
        "when": (
            "You want to evaluate a live agent, a deployed endpoint, or a whole "
            "pipeline rather than a composed prompt — which is the common case once "
            "evaluation stops being about composition."
        ),
        "minimum": "`run`. Inject via `run_eval(..., targets=...)`.",
        "lights_up": (
            "`dna eval` against your target. The default `PromptCompositionTarget` "
            "evaluates the composed prompt — worth knowing, because an eval suite that "
            "is green against composition has not yet said anything about the running "
            "agent."
        ),
        "prove": (
            "`PromptCompositionTarget` (`dna.extensions.eval.runner`) is the sole "
            "built-in and the shape to copy."
        ),
        "adapters_extra": [
            "`PromptCompositionTarget` (`dna.extensions.eval.runner`) — the only "
            "built-in target"
        ],
    },
    "Analyzer": {
        "group": "judgement",
        "role": "extend",
        "one_line": "A pass over a source that proposes candidates",
        "summary": (
            "The pluggable stage of the intel pipeline: read a source spec plus "
            "engine-built context, return candidates. Two ship — a deterministic "
            "offline one and an LLM one — which is the pattern to copy when you want a "
            "pipeline testable without a model."
        ),
        "when": "You have a different extraction strategy, or a domain-specific one.",
        "minimum": "`analyze(source, context) -> list[Candidate]`.",
        "lights_up": (
            "Selection through `select_analyzer(mode)`. The offline `SeedAnalyzer` is "
            "what keeps the pipeline's tests hermetic; if you add a model-backed "
            "analyzer, add a deterministic sibling too or the pipeline's tests start "
            "needing an API key."
        ),
        "prove": (
            "`SeedAnalyzer` and `LLMAnalyzer` (`dna.extensions.intel.analyzer`) are "
            "both in one file — read them side by side."
        ),
        "adapters_extra": [
            "`SeedAnalyzer` (`dna.extensions.intel.analyzer`) — deterministic, offline",
            "`LLMAnalyzer` (`dna.extensions.intel.analyzer`) — model-backed",
        ],
    },
    # ══ internal seams ═══════════════════════════════════════════════════
    "KindLookup": _internal(
        "Kind identity, plane and storage, for kernel collaborators",
        "Registered-Kind identity, plane, storage descriptor, alias and port lookup.",
    ),
    "DocStore": _internal(
        "The kernel's own instance-reading surface",
        "The source port, reader/writer lists, the tenant binding, the sync↔async "
        "bridge and the granular-instance cache, as one slice.",
    ),
    "InheritanceCtx": _internal(
        "Scope inheritance and the resolution chain",
        "Scope-inheritance constants, the catalog scope set, the base-instance cache "
        "and the resolution-chain computation.",
    ),
    "WriteOps": _internal(
        "The kernel's write entry points",
        "The two write entry points a collaborator may reach.",
    ),
    "InstanceBuildCtx": _internal(
        "Manifest-assembly internals",
        "The cache port, composition profiles, the resolver map and the two "
        "lazy-registration hooks used while assembling a manifest instance.",
    ),
    "LayerObserverCtx": _internal(
        "The reverse-dependency observer graph",
        "The reverse-dependency graph used for cross-scope surgical invalidation. "
        "Attribute-shaped, so it declares no methods.",
    ),
    "InvalidationHost": _internal(
        "Cache-coherence state",
        "The cache-coherence state the invalidation controller fans out over. All of "
        "it stays on the kernel so `with_tenant`'s shallow-copy semantics survive.",
    ),
    "InstanceBuilderHost": _internal(
        "Everything the instance builder needs",
        "The widest back-reference in the kernel — sixteen members across Kind lookup, "
        "instance reading, inheritance and assembly, because building a manifest "
        "instance crosses the whole kernel.",
    ),
    "QueryEngineHost": _internal(
        "Everything the query engine needs",
        "Read push-down: the instance-reading surface plus the inheritance fallback.",
    ),
    "RecordQuery": _internal(
        "The record-query push-down",
        "The record-query push-down shared by the read-only satellites (search, "
        "catalog, registry, composition summary). Public in the sense that it is a "
        "cohesive slice — not in the sense that you implement it.",
    ),
    "CompositionResolverHost": _internal(
        "Everything the composition resolver needs",
        "Resolves and persists compositions, and registers the reverse-dependency "
        "observers cross-scope invalidation walks.",
    ),
    "BundleIOHost": _internal(
        "Everything bundle I/O needs",
        "Bundle-entry and instance (de)serialization I/O.",
    ),
    "SourceSyncHost": _internal(
        "Everything source sync needs",
        "Digest, diff and push over the source.",
    ),
    "LayerPolicyHost": _internal(
        "Everything layer-policy enforcement needs",
        "`LOCKED` / `RESTRICTED` / `OPEN` enforcement over the base manifest instance.",
    ),
    "RegistryHost": _internal(
        "Everything the Kind registry needs",
        "The narrow slice the Kind registry's registration funnel needs. The registry "
        "dict itself is owned by the kernel.",
    ),
    "WriteHost": _internal(
        "Everything the write pipeline needs",
        "Kind identity, the writable-source guard, layer policy, hooks, and the "
        "invalidation/observer fan-out.",
    ),
    "RegistryAccessorHost": _internal(
        "The three global registry reads",
        "The registry accessor's three global reads — model profile, voice policy, "
        "embedding profile.",
    ),
    "NamespaceGateHost": _internal(
        "Everything the namespace-ownership gate needs",
        "The write-time namespace-ownership check: three members, one per question the "
        "verdict has to answer.",
    ),
    "SearchEngineHost": _internal(
        "Everything the search engine needs",
        "Record search plus the lexical fallback, the tenant binding, and the "
        "registered provider.",
    ),
    "CatalogCacheHost": _internal(
        "Everything the catalog cache needs",
        "The catalog-tier scope set. The cache dict is owned by the kernel and shared "
        "by identity.",
    ),
    "SourceFacadeHost": _internal(
        "Read-only source introspection",
        "Read-only source-adapter introspection — source type, scope list, metadata. "
        "Attribute-shaped, so it declares no methods.",
    ),
    "KindLike": _internal(
        "The minimal Kind shape a Resource needs",
        "The smallest slice of a Kind that `Resource.deps()` needs, so dependency "
        "resolution does not depend on the whole `KindPort`.",
        why=(
            "A typing-only narrowing of `KindPort`. Any Kind you write already "
            "satisfies it — implementing it separately would mean writing a Kind that "
            "is not a Kind. If you are here to add a Kind, "
            "[`KindPort`](kinds.md#kindport) is the port you want."
        ),
    ),
}
