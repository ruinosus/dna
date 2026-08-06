# The reference graph — what points at this document?

A Kind can declare that one of its fields names another document:

```yaml
spec:
  schema:
    properties:
      feature:
        type: string
        x-dna-ref: Feature        # this string names a Feature
```

That declaration has been enforced on write for a while: save a `Story` whose
`spec.feature` names nothing and the kernel says so. What it could not do was
answer the question a product actually asks —

> **What breaks if I delete or change this document?**

The Kind screen could say `Story.feature → Feature` exists as a *rule*. It
could not say that **these forty-seven Stories** point at **this** Feature.
This page explains the mechanism that closes that gap, and — just as
importantly — what it deliberately refuses to claim.

## The edge costs no extra read

Validating a declared reference means loading the target document. The write
path was already doing that, checking `is not None`, and throwing away both the
document *and* — for a polymorphic reference — which of the declared Kinds
actually matched.

So the producer is not a second mechanism that scans documents and derives
relationships. It is the *same* pass, keeping its result:

```
resolve_declared_edges(...) -> (edges, problems, complete)
                                  │        │        └── a read failed part-way
                                  │        └── what the validator vetoes on
                                  └── what the edge table stores
```

One pass, one set of reads, two consumers. That matters for a reason beyond
cost: an edge derived separately from the check could **disagree** with the
check. Here it cannot — the edge *is* the validator's own finding.

The rows are written by the storage adapter **inside the same transaction as
the document**, alongside the event outbox. Either the document and its
relations both land, or neither does.

!!! warning "This table existed once before, empty"
    `dna_edges` was created in 2026 by a migration whose own comment described
    a producer that was never written, and dropped fourteen months later with
    zero rows in it. Nothing distinguished "this document has no relations"
    from "nobody ever filled the table". That is why the producer, the
    migration and the test that proves a write puts a row in it ship together,
    and why the acceptance test fails if the table exists without the producer.

## Asking the graph

=== "CLI"

    ```console
    $ dna graph refs Feature f-poder-de-grafo --direction in --depth 2
    [1] Story/s-canvas --feature[0]--> Feature/f-poder-de-grafo
    [1] Story/s-blueprint --feature[0]--> Feature/f-poder-de-grafo
    [2] Task/t-77 --story_ref[0]--> Story/s-canvas
    (3 edge(s); stop: complete)
    ```

=== "REST"

    ```
    GET /v1/kinds/Feature/documents/f-poder-de-grafo/refs?direction=in&depth=2
    ```

The walk is one recursive CTE in standard SQL — identical on PostgreSQL and
SQLite, no server extension, no second query language. (Apache AGE was
considered and rejected: it is a server extension the hosting platform
allowlists rather than we do, and it would strand the SQLite and filesystem
adapters that the SDK carries as first-class citizens.)

Three things about that walk are refusals rather than features:

- **Depth is mandatory and capped.** `Spec.supersedes → Spec` and
  `Story.dependencies → Story` are self-referential *by design*, so an
  unbounded walk is an incident waiting for the first cyclic board. Default 1,
  ceiling from `DNA_GRAPH_MAX_DEPTH`.
- **Cycles terminate, and are still reported.** The edge that closes a cycle
  comes back flagged `closes_cycle` and is simply not expanded from. Dropping
  it would hide the cycle instead of surviving it.
- **`scope` and `tenant` are filtered in every branch**, not only in the
  anchor — the classic cross-tenant leak of this query shape is one forgotten
  line in the recursive step.

## What the answer refuses to pretend

The graph is only worth having if it is honest about its own edges, so four
signals travel with every answer.

**A dangling reference is a row, not a gap.** With `DNA_REF_VALIDATION=warn`
(the default) a document with an unresolvable reference *persists*. Its edge is
stored with a null target and returned with `resolved: false`. Hiding it would
render a graph tidier than the data deserves — and those rows are precisely the
list of what is broken. Delete a Feature that forty-seven Stories cite and the
forty-seven edges remain, now dangling: the delete path validates no references
at all, so this is the only trace that anything broke.

**A store that keeps no edges answers `unsupported`, never `[]`.** An empty
list reads as "nothing points at this document" — a claim only a store that
actually records edges is entitled to make. The filesystem adapter has neither
a transaction to write edges in nor a table to write them to, so it says so
(HTTP 501).

**`stop` says why the walk ended** — `complete`, `depth_reached` or
`truncated`. A caller that cannot tell "this is everything" from "this is where
I stopped" will render the second as the first.

**`graph_producer` says whether the producer is even on.** With
`DNA_REF_VALIDATION=off` the write path performs no lookups, so it produces no
edges. That is a defensible operational choice; a screen rendering the
resulting emptiness as "no relations" is not.

And one refusal on the write side: if a read fails part-way through resolving a
document's references, the stored edges are **not replaced**. A partial edge set
stored as though it were whole is a graph that lies while looking finished —
strictly worse than one that is honestly absent, because the absent one can be
labelled.

## Documents written before the producer existed

They have no edges, and there is exactly one honest way to give them some:

```console
$ dna graph backfill --scope my-workspace --dry-run
9 declared (Kind, field) pair(s) · 214 document(s) · would write 231 edge(s), 6 dangling
```

The backfill asks the **same declaration** the producer reads. For each
declared `(Kind, field)` pair it queries the documents whose `spec` carries that
field — on PostgreSQL a JSONB key-existence predicate the existing GIN index
serves directly, so it is a handful of queries rather than a walk over every
document. It is idempotent (the same delete-then-insert per document the
producer uses) and runs cold: nothing in it needs the write path to have been
warm.

It is emphatically **not** a scanner that guesses relations from name prefixes.
That mechanism is what got the first edge table cancelled: guessing produces
adivinhação, not a model, and it makes every reference that does not follow the
convention invisible to the graph.

A document whose references cannot be resolved completely is left alone and its
scope is reported as pending, so a screen can say *"still being filled"* rather
than showing a confident nothing.

## What is deliberately out of scope

- **No inference engine.** No rules, no subsumption, no derived facts, no
  materialized transitivity. One row corresponds to one field value somebody
  wrote.
- **Declared references only.** The *schema* graph also carries composition
  edges (`dep_filters`, never checked against data) and name-convention
  guesses. Calling this "the relations" would claim a completeness the producer
  does not have — which is why every surface qualifies it as *declared
  relations (`x-dna-ref`)*.
- **Top-level fields only.** `references_from_schema` reads
  `schema["properties"]` and does not recurse into `items`, sub-objects,
  `$ref` or `oneOf`. A reference at `spec.foo.bar` is invisible, and stays so.
- **Current state, not history.** An edge carries the document version it was
  derived from (so drift is detectable), but the table holds the present.

## See also

- [Kinds — identity and composition](kinds.md) — where `x-dna-ref` is declared.
- [Tenancy and layers](tenancy-layers.md) — why `to_scope` can differ from the
  scope you asked from.
- `dna graph --help` — `backfill` and `refs`.
