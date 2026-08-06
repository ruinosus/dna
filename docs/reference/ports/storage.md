# Storage & retrieval — where instances live

The ports the kernel uses to answer *where is this, and how do I get it back*. This is the plane with the most shipped adapters and the only one with a full conformance battery, so it is also the best documented place to start if you are writing your first port.

!!! info "Generated from the source"

    Names, signatures and docstrings are parsed out of `packages/sdk-py/dna`
    by `scripts/gen_ports_docs.py`. The prose around each contract is
    hand-written in `scripts/ports_prose.py`, and the generator **fails**
    if a port has none — so a new port cannot ship undocumented.

## BundleHandle

`dna.kernel.bundle.handle.BundleHandle` · `@runtime_checkable` · :material-power-plug: **extension point**

A store-agnostic handle over a bundle's entries — the thing a Reader or Writer actually touches, so neither has to know whether the bundle is a directory on disk or a set of rows.

!!! quote "From the source"

    Source-agnostic interface for reading + writing a bundle's entries.

    Implementations:
      - ``FilesystemBundleHandle`` (this module) — wraps ``pathlib.Path``.
      - ``DictBundleHandle`` (this module) — in-memory, used in tests.
      - ``DictBundleHandle`` is also how the SQL adapter serves bundles —
        hydrated from ``dna_bundle_entries`` rows.

    Entry naming convention: a posix-style relative path inside the bundle.
    Top-level entries are bare names (``"SAFETYPOLICY.md"``,
    ``"IDENTITY.md"``); nested entries use forward slashes
    (``"scripts/run.py"``, ``"references/spec.md"``).

    An ``entry`` is a PATH, and that is what distinguishes it from an instance
    ``name`` — see the note on ``FilesystemBundleHandle._entry_path``. Every
    implementation is expected to hold ``dna.kernel.errors.validate_bundle_entry``:
    the rule is part of the CONTRACT, not one backend's defensive habit,
    because a traversing entry is a filesystem escape on one backend and a
    malformed ``dna_bundle_entries`` row on the others — an escape deferred
    until something materialises it.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `name` | <code>def name(self) -> str</code> | Bundle directory name (e.g. ``'talent-screener'``, ``'pii-ml-filter'``). Used by readers as a default doc name when the marker frontmatter omits ``metadata.name``. |
| `exists` | <code>def exists(self, entry: str) -> bool</code> | True if the named entry (file or directory) exists in this bundle. |
| `read_text` | <code>def read_text(self, entry: str, encoding: str='utf-8') -> str</code> | Read entry content as text. Raises ``FileNotFoundError`` if absent. |
| `read_bytes` | <code>def read_bytes(self, entry: str) -> bytes</code> | Read entry content as bytes. Raises ``FileNotFoundError`` if absent. |
| `iter_entries` | <code>def iter_entries(self, *, recursive: bool=False) -> Iterator[str]</code> | Yield entry names (relative to the bundle root). |
| `is_file` | <code>def is_file(self, entry: str) -> bool</code> | True if ``entry`` points at a regular file (not a directory). Used by readers that filter out subdirs from ``iter_entries()``. |
| `write_text` | <code>def write_text(self, entry: str, content: str, encoding: str='utf-8') -> None</code> | Write text content to the entry, creating parent dirs as needed. |
| `write_bytes` | <code>def write_bytes(self, entry: str, content: bytes) -> None</code> | Write bytes content. Read-only handles raise ``NotImplementedError``. |
| `path` | <code>def path(self) -> Path \| None</code> | Filesystem path when the handle wraps a real directory; ``None`` otherwise. |

**Swap it when** — You are writing a source adapter whose bundles are not directories. If your store keeps entries as blobs, rows or object-store keys, this is the shim that lets every shipped Reader and Writer work against it unchanged.

**The minimum that works** — The read side — `name`, `exists`, `read_text`, `read_bytes`, `iter_entries`, `is_file`. `write_text` / `write_bytes` only if bundles are writable in your store; `path` only if a real filesystem path exists (return `None` when it does not, rather than inventing one).

**What it lights up** — Every registered Reader and Writer over your store. Skip it and bundle formats — `SKILL.md`, `SOUL.md`, `AGENTS.md` trees — are unreachable, though single-instance Kinds still work.

**How you prove it** — `dna.testing.reader_writer_conformance_suite(...)` runs every registered Reader/Writer pair against real market bundles; point it at a handle from your store and the whole registry becomes your test.

**Shipped implementations** — `FilesystemBundleHandle` (`dna.kernel.bundle.handle`) — a directory on disk; `DictBundleHandle` (`dna.kernel.bundle.handle`) — entries held in memory, the shape a row-backed store follows

## CachePort

`dna.kernel.protocols.CachePort` · `@runtime_checkable` · :material-power-plug: **extension point**

The local store for bundles pulled from outside — what a `ResolverPort` fetches lands here, keyed so a second install is a lookup.

!!! quote "From the source"

    WHERE — store/retrieve installed deps.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `load_all` | <code>async def load_all(self, scope: str, readers: list[ReaderPort] \| None=None) -> list[dict[str, Any]]</code> |  |
| `load_key` | <code>async def load_key(self, scope: str, key: str, readers: list[ReaderPort] \| None=None) -> list[dict[str, Any]]</code> |  |
| `store` | <code>async def store(self, scope: str, key: str, items: list[CacheItem]) -> None</code> |  |
| `has` | <code>async def has(self, scope: str, key: str) -> bool</code> |  |

**Swap it when** — Your deployment has no writable local disk (a read-only container, a serverless function) or you want the cache shared between replicas. This is one of the rarer swaps.

**The minimum that works** — All four: `load_all`, `load_key`, `store`, `has`.

**What it lights up** — Installing from a repository at all. There is a private no-op cache the kernel falls back to for non-filesystem sources, so a missing cache degrades to *nothing is ever cached* rather than to an error — slow, not broken.

**How you prove it** — No dedicated kit. `FilesystemCache` (`dna.adapters.filesystem.cache`) is small enough to read end to end and is the reference; exercise yours through `dna install` against a real bundle.

**Shipped implementations** — `_NoopCache` (`dna.kernel.boot.bootstrap`) — the private fallback for non-filesystem sources; a second implementation, but not a second *store*

## EmbeddingPort

`dna.kernel.protocols.EmbeddingPort` · `@runtime_checkable` · :material-power-plug: **extension point**

The sibling of `RecordSearchProvider`: one turns text into vectors, the other searches over them. Kept separate so you can change the model without changing the store.

!!! quote "From the source"

    Sibling port to ``RecordSearchProvider`` (rsh-memory-similarity-evolution
    → rec-embedding-port): turn text into dense vectors so the search plane can
    do real similarity instead of the lexical fallback. The kernel core gains
    NO ML deps — a real provider (ONNX all-MiniLM-L6-v2 via fastembed, an opt-in
    ``embed-onnx`` extra) registers itself on the kernel at app boot; when none
    is registered, ``kernel.embed()`` uses the deterministic hash-based
    ``FakeEmbeddingProvider`` (the zero-dep offline floor that runs in CI).

    Parity: the FAKE is bit-exact Py↔TS by construction (integer feature-hashing
    + IEEE-754 ops — see ``dna.kernel.embedding``); a real ONNX provider is
    parity-by-artifact (same model id, cosine ≈ 1 across runtimes).

    Contract:
      - ``embed(texts)`` returns one vector per input text, each of length
        ``dims``, in input order. Empty input → empty list.
      - ``dims`` is the fixed output dimensionality (same for every vector).
      - ``model_id`` identifies the embedding space; vectors from providers
        with different ``model_id`` are NOT comparable.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `embed` | <code>async def embed(self, texts: list[str]) -> list[list[float]]</code> |  |

**Swap it when** — You want a different embedding model, a hosted embedding API, or a multilingual model. The shipped ONNX provider is all-MiniLM and runs locally.

**The minimum that works** — `embed`. Dimensionality must match whatever your search provider indexed — changing the model without reindexing produces results that are wrong rather than absent.

**What it lights up** — Real semantic similarity. The default is `FakeEmbeddingProvider`, a deterministic zero-dependency floor: it is stable, it is not meaningful, and it will not tell you so. This is the same shape of trap as the search fallback — verify which provider is live.

**How you prove it** — `dna.testing.memory_scoring_conformance_suite(...)` grades ranking quality, which is the property an embedding change actually moves.

**Shipped implementations** — `FakeEmbeddingProvider` (`dna.kernel.embedding`) — the deterministic zero-dependency default, meaningful only as a floor; `OnnxEmbeddingProvider` (`dna.adapters.embedding.onnx`) — all-MiniLM, behind the `embed-onnx` extra

## KernelEventBus

`dna.kernel.boot.eventbus.KernelEventBus` · `@runtime_checkable` · :material-power-plug: **extension point**

How a *second* process learns that the first one wrote. Without it every replica caches independently and serves stale composition until something evicts it.

!!! quote "From the source"

    Cross-process invalidation bus.

    Implementations are environment-specific (Postgres LISTEN/NOTIFY,
    Redis pub-sub, in-memory for tests, etc.). The Kernel only depends
    on this Protocol.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `start` | <code>async def start(self, kernel: 'Kernel') -> None</code> | Begin consuming events and dispatching them to `kernel.invalidate(...)`. Must not block; the consume loop runs as a background asyncio.Task. Idempotent: calling start twice is a no-op (or restarts cleanly — implementation choice as long as the contract holds). |
| `stop` | <code>async def stop(self) -> None</code> | Cancel the consume loop and release any held resources (connections, etc). After stop, the bus may be restarted with another `start()` call. |

**Swap it when** — You run more than one replica against a store whose adapter cannot notify — which today means any store that is not Postgres.

**The minimum that works** — `start` and `stop`. `PostgresEventBus` is the only implementation: a durable outbox row plus `pg_notify`, both written inside the write transaction so a crash cannot lose the notification.

**What it lights up** — Cache coherence across processes, declared by the adapter as `supports_cross_process_invalidation`. **This is the catalogue's live known gap:** the filesystem and SQLite adapters declare it `False` and carry a `strict=True` xfail in the conformance matrix (`s-sqlite-cross-process-invalidation`). They declare `False` rather than staying quiet precisely so the gap is visible — a multi-process deployment on either serves stale data, silently, and always has. **A new adapter inherits this gap or solves it**, and nobody discovers which by reading code at random, so decide deliberately and declare the answer.

**How you prove it** — `tests/test_cross_process_invalidation_capability.py` pins the declared flag per adapter and needs no database. `test_adapter_conformance_matrix.py::test_cross_process_invalidation_capability` is the behavioural row.

**Shipped implementations** — PostgresEventBus (`dna.adapters.postgres.eventbus`)

## ReaderPort

`dna.kernel.protocols.ReaderPort` · `@runtime_checkable` · :material-power-plug: **extension point**

Given a bundle, decide whether you recognise it and turn it into a raw dict. Ten shipped, and unlike most ports here they all inherit the Protocol explicitly.

!!! quote "From the source"

    Reads a bundle and produces a raw dict.

    Phase 8 (PR1) — ``detect`` and ``read`` now receive a
    ``BundleHandle`` instead of a ``pathlib.Path``. The handle abstracts
    over filesystem, Postgres, S3, in-memory dict — same reader works
    regardless of where the bundle lives. See ``dna.kernel.bundle.handle``.

    Backward-compat: ``BundleHandle.path`` returns the underlying
    filesystem ``Path`` when FS-backed (``None`` otherwise) — escape
    hatch for code that genuinely needs Path semantics. New readers
    SHOULD use ``handle.read_text(...)`` / ``handle.iter_entries(...)``.

    Implementations MUST inherit this Protocol explicitly
    (``class MyReader(ReaderPort)``) — the same convention source
    adapters follow (s-dna-source-conformance-kit). Inheriting also
    provides the ``_owner_container`` default below.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `detect` | <code>def detect(self, bundle: 'BundleHandle') -> bool</code> |  |
| `read` | <code>def read(self, bundle: 'BundleHandle') -> dict[str, Any]</code> |  |

**Swap it when** — You are adding a Kind whose on-disk shape is not plain YAML — a Markdown file with front-matter, a multi-file convention, somebody else's existing format you want DNA to read in place.

**The minimum that works** — `detect` must be **cheap and certain**: it runs against every bundle, and a reader that claims bundles it cannot parse breaks unrelated Kinds. `read` then does the work.

**What it lights up** — Your format becoming loadable. Without one, a bundle in your layout is invisible — not an error, simply not found, which is the failure mode hardest to debug from the outside. Test `detect` against bundles that are *not* yours before you test it against ones that are.

**How you prove it** — `dna.testing.reader_writer_conformance_suite(...)` — it runs every registered pair, so registering yours enrols it automatically. `packages/sdk-py/tests/test_rw_conformance_kit.py` is the in-tree example.

**Shipped implementations** — AgentDefinitionReader (`dna.extensions.agentsmd.__init__`); AgentReader (`dna.extensions.helix.__init__`); GenericBundleReader (`dna.kernel.source.generic_rw`); HtmlArtifactReader (`dna.extensions.sdlc.__init__`); KindDefinitionReader (`dna.extensions.kinddef.__init__`); MarkdownBundleReader (`dna.kernel.source.generic_rw`); SkillReader (`dna.extensions.agentskills.__init__`); SoulReader (`dna.extensions.soulspec.__init__`); TenantMembershipReader (`dna.extensions.tenant.__init__`); TenantReader (`dna.extensions.tenant.__init__`)

## RecordSearchProvider

`dna.kernel.protocols.RecordSearchProvider` · `@runtime_checkable` · :material-power-plug: **extension point**

Semantic (not lexical) retrieval over records. Two shipped — sqlite-vec and pgvector — sharing **zero code** and graded by one suite, which is about the strongest evidence a port is genuinely pluggable rather than one implementation wearing an interface.

!!! quote "From the source"

    Two-planes F2 (spec D2): semantic search over record docs. The PG
    adapter (pgvector+RRF) lives in harness-shared and registers itself on
    the kernel at app boot — the kernel core gains NO LLM/embedding deps.
    Without a provider, kernel.search() degrades to an in-memory lexical
    scan (explicit ``degraded: True`` — never fake similarity).

    Hit shape: the guaranteed intersection across providers and the lexical
    fallback is ``{scope, kind, name, score}`` — RRF hits carry extra fields
    (title/snippet/rank components) that callers must treat as optional.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `search` | <code>async def search(self, *, scope: str, query_text: str, kind: str \| None=None, k: int=10, tenant: str='') -> list[dict[str, Any]]</code> |  |

**Swap it when** — You have a vector store already — Qdrant, Weaviate, Elasticsearch, a managed search service — and would rather DNA use it than run a second one.

**The minimum that works** — `search`. Register it on the kernel; a provider that fails to register is simply absent.

**What it lights up** — Semantic `recall` and record search. **The degradation here is the polite one and you should know it is happening:** with no provider the kernel falls back to a lexical scan, which returns plausible results that are not semantic ones. Nothing errors. Check which provider is live rather than assuming embeddings are in play.

**How you prove it** — `dna.testing.record_search_conformance_suite(...)` plus `run_record_search_conformance(...)` for a non-pytest runner. `test_pgvector_search_conformance.py` shows a provider that needs a live database wiring itself in.

**Shipped implementations** — `SqliteVecRecordSearchProvider` (`dna.adapters.search.sqlite_vec`); `PgVecRecordSearchProvider` (`dna.adapters.search.pgvector`) — the two share zero code, which is what makes this port demonstrably pluggable

## ResolverPort

`dna.kernel.protocols.ResolverPort` · `@runtime_checkable` · :material-power-plug: **extension point**

One resolver per URI scheme. `local:`, `github:`, `http(s):`, the Helix and registry resolvers — five shipped, none of which inherit the Protocol, which makes this the clearest example in the tree of structural typing doing its job.

!!! quote "From the source"

    FROM — fetch external deps.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `resolve` | <code>async def resolve(self, uri: str, dep: dict[str, Any]) -> list[ResolvedItem]</code> |  |
| `cache_key` | <code>def cache_key(self, uri: str) -> str</code> |  |

**Swap it when** — You publish bundles somewhere with its own scheme or its own auth — an internal artifact registry, S3, an authenticated Git host, an OCI registry. This is the most commonly written port after `SourcePort`, and the cheapest.

**The minimum that works** — `resolve` (fetch and return the bundle) and `cache_key` (a stable, collision-free identity for what you fetched — get this wrong and the cache serves the wrong bundle, which is worse than not caching).

**What it lights up** — `dna install` for your scheme. Unregistered schemes fail loud with the list of known ones, so a missing resolver is never a silent no-op.

**How you prove it** — No dedicated kit — the five shipped resolvers are each ~40 lines and are the specification by example. Copy the shape of `dna.adapters.resolvers.http`.

**Shipped implementations** — `LocalResolver` (`dna.adapters.resolvers.local`); `GitHubResolver` (`dna.adapters.resolvers.github`); `HttpResolver` (`dna.adapters.resolvers.http`); `HelixResolver` (`dna.adapters.resolvers.helix`); `RegistryResolver` (`dna.adapters.resolvers.registry`)

## SourcePort

`dna.kernel.protocols.SourcePort` · `@runtime_checkable` · :material-power-plug: **extension point**

The read half of a store. Everything DNA knows about your instances arrives through this port, so it is the first thing to implement and the only one with a 26-case battery waiting for it.

!!! quote "From the source"

    WHERE — load instances from storage.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `supports_readers` | <code>def supports_readers(self) -> bool</code> | Whether this source uses ReaderPort plugins to detect bundles. |
| `load_bootstrap_docs` | <code>async def load_bootstrap_docs(self, scope: str, *, tenant: str \| None=None) -> list[dict[str, Any]]</code> | Return the docs the kernel needs registered/parsed BEFORE ``load_all`` fires. |
| `load_all` | <code>async def load_all(self, scope: str, readers: list[ReaderPort] \| None=None) -> list[dict[str, Any]]</code> |  |
| `resolve_ref` | <code>async def resolve_ref(self, scope: str, ref: str) -> str</code> |  |
| `load_layer` | <code>async def load_layer(self, scope: str, layer_id: str, layer_value: str, readers: list \| None=None) -> list[dict[str, Any]]</code> |  |
| `close` | <code>async def close(self) -> None</code> |  |
| `list_doc_refs` | <code>async def list_doc_refs(self, scope: str, *, kind: str \| None=None, tenant: str \| None=None) -> list[tuple[str, str]]</code> | Lista (kind, name) de todos os docs do scope. Filtrável por kind. Retorna metadata only — sem bundle entries, sem parse. |
| `load_one` | <code>async def load_one(self, scope: str, kind: str, name: str, *, readers: list[ReaderPort] \| None=None, tenant: str \| None=None) -> dict[str, Any] \| None</code> | Carrega UM doc específico com seu bundle (se aplicável). Retorna o raw dict (kind, name, spec, metadata) ou None se não encontrado. |
| `query` | <code>async def query(self, scope: str, kind: str, *, filter: QueryFilter \| None=None, projection: QueryProjection \| None=None, limit: int \| None=None, offset: int \| None=None, order_by: QueryOrder \| None=None, tenant: str \| None=None) -> AsyncIterator[dict[str, Any]]</code> | Push-down query sobre o storage do scope. |
| `count` | <code>async def count(self, scope: str, kind: str, *, filter: QueryFilter \| None=None, group_by: str \| None=None, tenant: str \| None=None) -> dict[str, Any]</code> | Aggregation push-down (two-planes F2, spec D2): total de docs que casam o ``filter``, opcionalmente agrupados por um field_path (``group_by``, mesma convenção do QueryFilter — ex.: ``spec.status``). |

**Swap it when** — You want DNA's instances to live somewhere the shipped adapters do not reach — a document database, an object store, a git host, an internal content service, a read-only mount inside a wheel. Note that changing *between* filesystem, SQLite and Postgres needs no new adapter: that is a `dna.config.yaml` line, covered in [How to configure ports](../../guides/configuring-ports.md).

**The minimum that works** — The six names the boot gate checks — `supports_readers`, `load_bootstrap_docs`, `load_all`, `resolve_ref`, `load_layer`, `close` — plus an honest `capabilities()`. Be aware that the boot gate checks **names only** (that is all `runtime_checkable` can do); passing it means your adapter is shaped right, not that it works. The conformance kit is what checks behaviour.

**What it lights up** — Nothing on its own: a read-only source is a complete, legitimate adapter (the `pkg://` package-data source is exactly that). Writing needs [`WritableSourcePort`](#writablesourceport); everything beyond the mandatory floor is declared through [the capability protocols](capabilities.md).

**How you prove it** — `dna.testing.source_conformance_suite(factory)` — 26 cases, capability-aware (it reads your declared `capabilities()` and skips what you did not claim, fails what you claimed and did not honour). Wire it as one pytest case each:

```python
from dna.testing import source_conformance_suite

CASES = source_conformance_suite(my_factory)

@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
async def test_conformance(case):
    await case.run()
```

Then add your adapter to the cross-adapter matrix — see [Proving a storage adapter](#proving-a-storage-adapter).

**Shipped implementations** — FilesystemSource (`dna.adapters.filesystem.source`); `SqlAlchemySource` (`dna.adapters.sqlalchemy_.source`) — one class, two dialects (aiosqlite, asyncpg), and the only adapter that declares `edge_graph` / `as_of_reads` / `api_version_identity`; `AsyncSourceAdapter` (`dna.adapters.async_adapter`) — a proxy, not a store

## WritableSourcePort

`dna.kernel.protocols.WritableSourcePort` · `@runtime_checkable` · :material-power-plug: **extension point**

Composes [`SourcePort`](#sourceport).

`SourcePort` plus writes, versions and drafts. This — not `SourcePort` — is what an adapter meant to back a real deployment implements; the adapter guide calls it mandatory for a reason.

!!! quote "From the source"

    SourcePort with write + versioning capabilities.

    Phase 2a (tenant first-class): ``tenant`` is now a first-class
    parameter on save/delete. Adapters route tenant-scoped writes to
    physically isolated storage (e.g. ``tenants/<X>/scopes/<S>/``);
    ``layer`` is reserved for non-tenant overlays (branch, region,
    user) — when both are passed the adapter combines them.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `save_instance` | <code>async def save_instance(self, scope: str, kind: str, name: str, raw: dict, author: str \| None=None, *, tenant: str \| None=None, layer: tuple[str, str] \| None=None, write_class: str='substantive', version_retention: int \| None=None, if_absent: bool=False, if_match: str \| None=None, edges: list \| None=None) -> str</code> | Persist one instance (an UPSERT by default). |
| `delete_instance` | <code>async def delete_instance(self, scope: str, kind: str, name: str, *, tenant: str \| None=None, layer: tuple[str, str] \| None=None, api_version: str \| None=None) -> None</code> | Delete one instance. |
| `save_manifest` | <code>async def save_manifest(self, scope: str, manifest: dict) -> str</code> |  |
| `list_versions` | <code>async def list_versions(self, scope: str, kind: str, name: str) -> list[dict]</code> |  |
| `get_version` | <code>async def get_version(self, scope: str, kind: str, name: str, version_id: str) -> dict</code> |  |
| `publish` | <code>async def publish(self, scope: str, kind: str, name: str) -> str</code> |  |
| `load_drafts` | <code>async def load_drafts(self, scope: str) -> list[dict]</code> |  |
| `list_scopes` | <code>async def list_scopes(self) -> list[str]</code> |  |
| `capabilities` | <code>def capabilities(self) -> 'SourceCapabilities'</code> |  |

**Swap it when** — Always, unless your store is genuinely read-only. A source that cannot write cannot host the SDLC board, the memory plane, or anything a user edits.

**The minimum that works** — `save_instance` and `delete_instance` honouring at least the `tenant` kwarg, plus a `capabilities()` that tells the truth. `list_versions` may return `[]` and `publish` may be a no-op — the filesystem adapter does both — but see the warning under `Versionable`: declaring `versions=True` while keeping no history is precisely why `as_of_reads` had to become a separate flag.

**What it lights up** — The optional write kwargs are individually declared and individually gated: `if_absent` (atomic create), `if_match` (guarded update), `edges` (persist the derived reference graph in the *same* transaction), `author`, `layer`, `write_class`, `version_retention`. The kernel reads your declared `write_kwargs` and **never passes a kwarg you did not declare** — so an unadopted kwarg degrades to the feature being off, not to your adapter silently dropping data. `edges` is the sharp one: an adapter that does not declare it is never handed edges, and the graph face answers `unsupported` rather than an empty edge list.

**How you prove it** — `dna.testing.source_conformance_suite(factory)` — 26 cases, capability-aware (it reads your declared `capabilities()` and skips what you did not claim, fails what you claimed and did not honour). Wire it as one pytest case each:

```python
from dna.testing import source_conformance_suite

CASES = source_conformance_suite(my_factory)

@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
async def test_conformance(case):
    await case.run()
```

Then add your adapter to the cross-adapter matrix — see [Proving a storage adapter](#proving-a-storage-adapter).

**Shipped implementations** — CompositeFilesystemSource (`dna.adapters.filesystem.composite`); FilesystemWritableSource (`dna.adapters.filesystem.writable`); SqlAlchemySource (`dna.adapters.sqlalchemy_.source`)

## WriterPort

`dna.kernel.protocols.WriterPort` · `@runtime_checkable` · :material-power-plug: **extension point**

The inverse of a Reader, and the half people forget. Eleven shipped. A Kind that reads but does not write is editable by hand and by nothing else.

!!! quote "From the source"

    Writes a raw dict back to a bundle. Inverse of ReaderPort.

    Phase 8 (PR1) — ``write`` receives a ``BundleHandle`` instead of
    ``Path``; same source-agnostic contract.

    s-dna-rw-roundtrip-suite — ``serialize`` is part of the contract
    (it was load-bearing but informal: ``kernel.serialize_instance``
    consumed it via ``hasattr``, so a Protocol-conforming writer could
    silently miss it and only fail at emission time).

    Implementations MUST inherit this Protocol explicitly
    (``class MyWriter(WriterPort)``) and keep ``write`` and ``serialize``
    COHERENT: ``write(bundle, raw)`` must produce exactly the entries
    ``serialize(raw)`` returns (the canonical implementation is
    ``write_entries_to_handle(bundle, self.serialize(raw))`` from
    ``dna.kernel.write.helpers``). The round-trip conformance
    suite (``dna.testing.reader_writer_conformance_suite``)
    enforces this equivalence for every registered pair.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `can_write` | <code>def can_write(self, raw: dict) -> bool</code> |  |
| `write` | <code>def write(self, bundle: 'BundleHandle', raw: dict) -> None</code> |  |
| `serialize` | <code>def serialize(self, raw: dict) -> list[dict[str, Any]]</code> | Return the bundle entries ``write`` would emit, WITHOUT writing. |

**Swap it when** — Whenever you write a Reader and the format is meant to be editable.

**The minimum that works** — `can_write`, `write`, `serialize`. The round trip is the contract: `read(write(x))` must equal `x`, and the conformance kit checks exactly that against real bundles.

**What it lights up** — Writes through the REST/MCP faces for your Kind, and the CLI's edit path. Without a Writer the kernel refuses the write rather than picking a format for you.

**How you prove it** — Same suite as `ReaderPort` — they are graded as a pair, on purpose.

**Shipped implementations** — AgentDefinitionWriter (`dna.extensions.agentsmd.__init__`); AgentWriter (`dna.extensions.helix.__init__`); GenericBundleWriter (`dna.kernel.source.generic_rw`); HtmlArtifactWriter (`dna.extensions.sdlc.__init__`); KindDefinitionWriter (`dna.extensions.kinddef.__init__`); LessonWriter (`dna.extensions.lesson.__init__`); ResearchWriter (`dna.extensions.research.__init__`); SkillWriter (`dna.extensions.agentskills.__init__`); SoulWriter (`dna.extensions.soulspec.__init__`); TenantMembershipWriter (`dna.extensions.tenant.__init__`); TenantWriter (`dna.extensions.tenant.__init__`)

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
DATABASE_URL=postgresql://dna:dna@localhost:5432/dna \
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
