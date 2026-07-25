---
apiVersion: github.com/ruinosus/dna/research/v1
kind: Research
metadata:
  name: rsh-memory-similarity-evolution
spec:
  title: Evolving memory + similarity search into DNA, server-free
  objective: Determine how to bring the memory system and semantic/similarity search from the internal
    SDK it was extracted from into DNA as an EVOLUTION (not copy-paste) — embeddable-first, no mandatory
    server, behind the RecordSearchProvider port that already exists in the kernel.
  methodology: synthesis
  overall_confidence: high
  conducted_by: claude-code
  conducted_at: '2026-07-09T00:00:00+00:00'
  scope_ref: dna-development
  status: published
  visibility: shared
  owner: claude-code
  tags:
  - memory
  - search
  - embeddings
  - ports
  - evolution
  key_takeaways:
  - 'The search subsystem is already ~library-pure: the RecordSearchProvider port already lives in the
    DNA kernel (search_engine.py) and degrades honestly to a lexical scan (never fakes similarity); the
    RRF/cosine/lexical/decay logic in the source project is pure over a connection pool. What is ''server''
    is thin shell (a CLI-over-HTTP + FastAPI routes + a write-hook).'
  - The memory subsystem's cognitive CORE is deterministic pure functions (ecphory scoring, BM25 retrieval,
    Ebbinghaus decay, encoding-context stamping, CoALA classification) plus a declarative Kind (LessonLearned)
    that already carries affect, Semon reinforcement, Nader reconsolidation, and bi-temporality (valid_from/valid_to).
    It is currently packaged in the service layer next to genuinely-service pieces (LLM scribes, schedulers,
    workers).
  - 'The EVOLUTION: drop the pgvector-only + hosted-embeddings assumption. Go embeddable-first — sqlite-vec
    + FTS5 + RRF as the offline default (Py<->TS parity trivial: one C extension both sides), model2vec/ONNX
    embeddings (offline floor -> scale, lazy-download), pgvector as a SCALE adapter reusing the Postgres
    DNA already has — all behind the existing RecordSearchProvider port.'
  - 'Memory is NOT a new subsystem: it is the Kinds DNA already has (LessonLearned, Research, Evidence)
    indexed and recalled by the same provider, with verbs remember/recall/forget/consolidate and bi-temporality
    already in the schema. Leave the LLM scribes/schedulers/workers behind — those are service, not SDK.'
  - 'Two portability debts to own: (1) the embeddings sidecar table has no owning migration in the source
    repo (the edges table does; the embeddings one does not) — DNA must own that schema via its migration
    contract; (2) recall side-effects use kernel.write_document / post_save — portable, DNA has the kernel.'
  findings:
  - id: f-port-already-exists
    title: The RecordSearchProvider port + lexical fallback already exist in the DNA kernel
    evidence_rating: evidence-based
    summary: The kernel ships RecordSearchProvider (a runtime-checkable protocol) and a SearchEngine facade
      that uses the provider when registered (dense + RRF) or degrades to a token-set lexical scan when
      absent — honest degradation, never a fake similarity, never raising. This is the seam designed for
      exactly this evolution; DNA has it today with zero implementation (recall is lexical, per i-004).
    source_refs: []
    tags:
    - port
    - kernel
  - id: f-search-is-lib-pure
    title: The search logic is already library-pure; only a thin shell is server
    evidence_rating: evidence-based
    summary: 'In the source project the RRF fusion (vector cosine via pgvector, lexical BM25, graph BFS),
      the Ebbinghaus decay, the overlay/tenant merge, and the backfill are all pure functions over a connection
      pool — no web framework, no agent runtime. What is server is a thin shell: a CLI that speaks HTTP,
      FastAPI routes that are a thin cover over the pure functions, and a post_save write-hook that populates
      embeddings. Porting the pure core down is low-risk; it drags only Postgres+pgvector, not any agent
      framework.'
    source_refs: []
    tags:
    - portability
    - search
  - id: f-sqlite-vec-default
    title: sqlite-vec + FTS5 + RRF is the embeddable, offline, Py<->TS-parity default
    evidence_rating: evidence-based
    summary: 'sqlite-vec is C, zero-dependency, runs anywhere SQLite runs (incl. WASM), with first-class
      Python AND TS/Node bindings. FTS5 (BM25) lives in the same file, so sqlite-vec + FTS5 gives full
      hybrid search with no new dependency; RRF is a one-line pure function. This is the natural default
      RecordSearchProvider: one .db per scope, runs offline in CI, parity by shared C extension. https://github.com/asg017/sqlite-vec
      and https://alexgarcia.xyz/sqlite-vec/js.html'
    source_refs: []
    tags:
    - store
    - default
  - id: f-embeddings-no-server
    title: Quality embeddings without a hosted API, with Py<->TS parity by artifact
    evidence_rating: evidence-based
    summary: 'Offline floor = model2vec/potion (a distilled static lookup table, ~50x smaller/500x faster,
      no GPU, ideal for CI). Scale = all-MiniLM-L6-v2 ONNX shared by fastembed (Py) and transformers.js
      (TS) — same ONNX artifact, same vector, parity by artifact not reimplementation, lazy-download+cache
      (the Chroma pattern: model is a downloaded artifact, not an install dep). https://github.com/qdrant/fastembed,
      https://huggingface.co/docs/transformers.js, https://github.com/MinishLab/model2vec'
    source_refs: []
    tags:
    - embeddings
    - parity
  - id: f-memory-is-existing-kinds
    title: Memory frameworks converge on what DNA's LessonLearned already encodes
    evidence_rating: evidence-based
    summary: 'mem0, Letta/MemGPT, Zep/Graphiti, cognee converge on episodic/semantic/procedural memory
      + consolidation + bi-temporality (Zep''s valid_from/valid_to resolves stale/contradictory facts
      by supersession, not deletion). DNA''s LessonLearned Kind already encodes affect, Semon reinforcement,
      Nader reconsolidation (append-only revisions), CoALA memory_type, and bi-temporality. The lesson
      is NOT to adopt a framework: it is to unify recall behind the same RecordSearchProvider and formalize
      the verbs remember/recall/forget/consolidate over the Kinds that already exist. https://github.com/mem0ai/mem0,
      https://github.com/letta-ai/letta, https://github.com/getzep/graphiti'
    source_refs: []
    tags:
    - memory
    - kinds
  - id: f-embeddings-ddl-debt
    title: The embeddings sidecar table has no owning migration — a portability debt
    evidence_rating: evidence-based
    summary: In the source repo the graph-edges table is created by the migration baseline, but the embeddings
      sidecar table is created out-of-band (no migration owns its DDL, not in the baseline nor in the
      postgres-init). If DNA wants a portable pgvector adapter, it must own that schema via the migration
      contract already shipped in the SQLAlchemy source work.
    source_refs: []
    tags:
    - debt
    - migrations
  recommendations:
  - id: rec-embeddable-provider
    priority: high
    summary: Implement RecordSearchProvider with an EMBEDDABLE default — sqlite-vec + FTS5 + RRF — offline,
      Py<->TS parity by shared C extension. This is the evolution vs the pgvector-only original.
    backed_by_findings:
    - f-port-already-exists
    - f-sqlite-vec-default
  - id: rec-embedding-port
    priority: high
    summary: Add an EmbeddingPort with model2vec (offline/CI floor) and ONNX all-MiniLM (scale, lazy-download)
      adapters; parity by shared ONNX artifact; nothing heavy in the default install.
    backed_by_findings:
    - f-embeddings-no-server
  - id: rec-pgvector-scale
    priority: medium
    summary: Port the library-pure RRF as a pgvector SCALE adapter reusing DNA's Postgres, and own the
      embeddings DDL via the migration contract (closes the debt).
    backed_by_findings:
    - f-search-is-lib-pure
    - f-embeddings-ddl-debt
  - id: rec-memory-as-kinds
    priority: medium
    summary: Memory = existing Kinds recalled by the same provider; port the pure deterministic scoring
      (ecphory/BM25/decay/encoding-context/CoALA) into a DNA extension; verbs remember/recall/forget/consolidate;
      bi-temporality already present. Leave LLM scribes/schedulers behind.
    backed_by_findings:
    - f-memory-is-existing-kinds
  - id: rec-opt-in-extras
    priority: high
    summary: Everything heavy is an opt-in extra (dna[search-sqlite], dna[search-pgvector]; @dna/search-sqlite-vec,
      @dna/embed-transformersjs). Core stays zero-heavy-deps; the offline floor (sqlite-vec+FTS5+model2vec+RRF)
      runs in CI with no server.
    backed_by_findings:
    - f-sqlite-vec-default
    - f-embeddings-no-server
  body: |
    # Evolving memory + similarity search into DNA (server-free)

    Two research streams: (1) an excavation of the memory + search subsystems of the
    internal SDK DNA was extracted from; (2) the 2025/2026 state of the art for
    embeddable, server-free semantic search and agent memory. They converged.

    The evolution is not to re-import the old server design (pgvector + a hosted
    embeddings service) — it is to make similarity + memory a pluggable capability
    behind the RecordSearchProvider port that already exists in the DNA kernel, with
    an embeddable default that runs offline in CI and optional adapters for scale.

    ## Proposed architecture (ports + adapters)

    - RecordSearchProvider (exists): index / search (dense + BM25 + RRF) / delete.
      Default adapter = sqlite-vec + FTS5 + RRF (one .db file, offline, Py<->TS parity).
      Scale adapter = pgvector (reuse DNA's Postgres). Edge adapter = LanceDB (millions).
    - EmbeddingPort (new): embed(texts) -> vectors. Offline floor = model2vec/potion;
      scale = all-MiniLM-L6-v2 ONNX shared by fastembed (Py) + transformers.js (TS),
      lazy-download+cache. Parity by shared artifact.
    - RerankPort (optional): cross-encoder rerank (fastembed TextRerank, Py+JS), opt-in.
    - Memory = existing Kinds (LessonLearned, Research, Evidence, VibeSession) indexed
      and recalled by the same provider; verbs remember/recall/forget/consolidate;
      bi-temporality (valid_from/valid_to) already in the LessonLearned schema.

    The offline CI floor — sqlite-vec + FTS5 + model2vec + RRF — needs no server, no
    GPU, no network, and is Py<->TS parity-verified by output. Everything above it
    (ONNX lazy-download, pgvector, reranker, LanceDB) is an opt-in extra.

    This is DNA's answer to "agent memory + search" consistent with its thesis:
    declarative Kinds recalled through a pluggable port, not a bundled service.
  created_at: '2026-07-09T14:28:32+00:00'
  updated_at: '2026-07-09T14:28:32+00:00'
---

# Research — Evolving memory + similarity search into DNA, server-free

Methodology: synthesis · 0 sources · 6 findings.

This file's spec (frontmatter above) is the authoritative data. The prose below is for human reading and is regenerated on each write. Edit via `dna research` CLI or the Studio viewer; raw frontmatter edits are also supported.
