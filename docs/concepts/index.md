# Concepts

Understanding-oriented explanation — the *why* behind DNA. Read these when
you want the mental model, not a task recipe.

Start with the thesis; the rest expand its pieces.

- **[The thesis — CRDs, but for agentic behavior](thesis.md)** — the primer.
  A short normative core (RFC-2119) plus the teaching that anchors DNA to
  the Kubernetes CRD model: the owner names the schema, `spec` is authored
  intent, behavior is derived.
- **[Kinds — identity and composition](kinds.md)** — how `(apiVersion,
  kind)`, `dep_filters` and prompt templates turn cross-references into a
  single composed prompt.
- **[The microkernel and its five ports](microkernel-ports.md)** — the
  closed core that knows no Kinds, and the ports extensions plug into.
- **[Market fidelity](market-fidelity.md)** — how "consume standards
  byte-faithful under their owner's namespace" is enforced against real
  marketplace bundles.
- **[Tenancy and layers](tenancy-layers.md)** — scopes, the orthogonal
  tenant dimension, and layer overlays.
- **[Search & memory](search-and-memory.md)** — semantic recall and agent
  memory as two kernel ports with pluggable adapters: offline-first
  sqlite-vec + FTS5 + RRF, pgvector for scale, and memory as the Kinds you
  already have.
- **[Agent-facing knowledge](agent-knowledge.md)** — why DNA represents
  knowledge as curated, cited Kinds rather than generated wiki prose.

For the procedures that put these ideas to work, see the
[How-to guides](../guides/index.md).
