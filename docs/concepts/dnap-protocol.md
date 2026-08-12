# DNAP — DNA as a protocol

Three protocols already govern how an agent *runs*. **MCP** says how tools are
exposed to a model, **A2A** how one agent delegates to another, **AHP** how a
live session is hosted and shared. None of them says **what the agent is**;
each assumes a definition arrived from somewhere. AHP states it outright:
*"AHP assumes agents already exist."*

**DNAP** — the DNA Protocol — specifies that gap: the definition of an agent as
a typed, versioned, owned instance, and the contract for resolving it into
something a runtime can execute. It is framed as JSON-RPC 2.0, and it declares
MCP/A2A/AHP the way a `package.json` declares a registry it does not implement.

The normative draft is [`docs/spec/dnap-1.0-draft.md`](../spec/dnap-1.0-draft.md).
This page is the orientation; the spec is the contract.

!!! note "Status"
    Wave 1 — the dispatcher, `initialize`, `kinds/*`, `instances/*`, channels,
    cursors and the error table — ships in `dna.protocol`. `resolve/*` and
    `search/*` are specified and not yet built.

## The shape

A DNAP server is a **dispatcher plus a method table**. `dna.protocol.DnapServer`
turns a decoded JSON-RPC payload into a decoded JSON-RPC response and does five
things: validate the envelope, look the method up, resolve and refuse the
channel, call the handler, translate a failure into an error object. It never
names a method — `initialize`, `kinds/list`, `kinds/describe`,
`instances/list`, `instances/get`, `instances/write` and `instances/delete` are
*registered*, exactly the way `resolve/agent` and `search/instances` will be.

```python
from dna.application.live import LiveDna
from dna.protocol import DnapServer, serve_stdio

server = DnapServer(LiveDna(base_scope="my-scope", kernel=kernel))
await serve_stdio(server)
```

Every read and write goes through the same use-cases the MCP and REST faces
use (`dna.application.instances`). DNAP is a **third face over one
implementation**, not a second implementation — what it adds is the part that
is protocol rather than behaviour.

### Capabilities are derived, not listed

`MethodRegistry` is the extension point, and the `capabilities` block of
`initialize` is computed from it:

```python
from dna.protocol import DnapServer, builtin_registry

registry = builtin_registry().extended()

@registry.method("resolve/agent", capability="resolve")
async def resolve_agent(ctx, params): ...

registry.declare_capability("resolve", lambda ctx: {"agent": True})
server = DnapServer(live, registry=registry)
```

Registering the method is what makes the server advertise `resolve`. A
capability can never be advertised with no method behind it, nor a method
served outside an advertised capability — spec §4 requires the second case to
answer `-32601 Method not found`, following AHP, and the registry is where that
gate lives.

### Capabilities are an INTERSECTION

`initialize` is a declaration in each direction, and the effective set is the
intersection of the two: a client that did not ask for `write` cannot write,
even against a server that offers it. The alternative reading — the client's
field is decorative — is equally defensible from a loose text and *disagrees
about whether a call succeeds*, which is exactly why the specification fixed
one.

## Addressing: scope is an address

```
dnap-root://                    connection-level operations
dnap-scope:/<scope>             one scope's instances
dnap-scope:/<scope>#<tenant>    the tenant overlay of that scope
```

This corrects a **measured** defect in DNA's REST face: a `?scope=` query
parameter was accepted and silently ignored, returning one scope's content
under another scope's name. A parameter can be dropped by a framework and
nobody notices. An address cannot — a request naming a channel the server does
not serve answers `-32004 CHANNEL_NOT_SERVED`, and there is no code path from
"you asked for A" to "here is B".

A tenant overlay is **read-through** (absent instances resolve to the base),
**write-local** (a tenant cannot edit the platform's copy by accident) and
carries **no tombstones** (deleting reveals the base again, rather than hiding
it — hiding would make "this tenant has no X" and "this tenant deleted X"
indistinguishable, which is the §7 rule wearing another face). Each channel
carries its own `revision` sequence.

!!! warning "Read-through is also how substitution sneaks back in"
    A server serves **no** tenant channel unless a deployment declares it.
    Because the layer resolution reads through, a request for a tenant the
    server has never heard of came back carrying the base scope's content — the
    caller asked for a tenant's shelf and was handed the shared one, with
    nothing in the answer to say so. That is §3's substitution arriving through
    the one door §3's own refusal did not cover, and it was found by the
    conformance suite rather than by this server's own tests, which is the
    argument for a second implementation in one sentence.

## Conformance

`dna.protocol` runs the DNAP conformance suite
(`dna.testing.dnap_conformance`), which was written from the specification by
someone who had not read this server — and which the clean-room TypeScript
implementation runs too. A specification with one implementation is described,
not validated; what makes it a contract is two servers, built independently,
submitting to one set of questions.

The suite reports in five buckets rather than two, and `ok` is false while
anything is failed **or unverified** — an obligation that could not be observed
is not an obligation that was met.

## Creating a Kind — the reflexive rule

A Kind is an instance of the Kind `KindDefinition`. Writing one **registers a
type**, and there is no other way. `metadata.name` MUST equal `spec.kind` — one
name, no mapping — and `spec.schema` is bounded to fifteen JSON Schema
keywords, because *a keyword the server stores, hands out through
`kinds/describe`, and does not enforce is a lie told to every client that reads
the schema to pre-validate*.

!!! warning "An open conflict, stated rather than resolved"
    §6.1 says no out-of-band mechanism for registering a type is permitted. The
    DNA SDK refuses a generic write of `KindDefinition` and routes Kind
    authoring through `dna.application.kind_authoring`, where what a tenant
    writes is inert until a human approves it. That approval gate is a product
    decision, not an oversight. `dna.protocol.kinddef` enforces the two rules
    the specification states; whether the write proceeds is the SDK's own gate
    to answer, and this server reports `-32006 NOT_WRITABLE` rather than
    pretending either side away.

## The five rules of a listing

`instances/list` carries five rules, and each corrects something that was
measured rather than imagined.

**`select` is a contract, not a hint.** A server that cannot honour the
requested projection answers `-32602`; it never returns a narrower shape while
echoing the request. The measurement is in this repo: DNA's projector resolves
an unprefixed path under `spec.`, so a *bare* `select: ["spec"]` becomes
`spec.spec`, resolves to nothing, and is dropped in silence — while the caller
is handed back `"projected": ["spec"]`. `dna.protocol.select` refuses that path
by name, before the store is read, and explains why.

**Cursor, never offset.** Offset pagination is `OFFSET n` in SQL and degrades
quadratically. DNAP's cursor is opaque, which is what makes the offset
underneath replaceable without a wire change, and it pins the listing's
address, Kind and `select` shape so a page cannot be reinterpreted mid-flight.
An expired cursor answers `-32005 CURSOR_EXPIRED` so the client restarts rather
than silently skipping.

**`revision` is constant across a paginated read.** All pages of one listing
belong to one snapshot; without that a client assembles a quilt of moments and
calls it a state. The cursor pins the revision and every page re-checks it, so
a channel that moved ends the listing with `-32005` rather than continuing
against a different state.

Where the store exposes a sequence, that is the revision — O(1), and the number
is the store's own. Where it does not (no adapter in this repo does yet), the
revision is **computed**: a digest over the slice's `(name, etag)` pairs. Three
answers were possible and two were dishonest — `null` makes rule 3 vacuous
(two pages both reporting nothing agree about nothing), a minted token is
opaque and constant and *means nothing*, and only the digest is a true
statement about which state the rows came from. The digest costs a pass over
the slice; `initialize` reports which mechanism a connection is getting, so the
cost is visible rather than discovered in a latency graph.

**Order is lexicographic by `metadata.name`, ascending** — pushed down to the
store, never applied per page. Cursors and snapshots are both meaningless
without a total order, and `metadata.name` is the only member guaranteed unique
within `(channel, kind)`.

**The shape of `select` is part of the contract.** `"names"` returns plain
strings, not one-member documents — *a document-shaped object carrying only a
name is exactly the narrower shape rule 1 forbids, wearing a disguise*. A path
list returns exactly the requested paths and nothing added: a server that
helpfully attaches identity and one that does not return different rows for the
same request.

## The rule that outranks the error table

Spec §7 lists the codes — `-32002 NOT_FOUND`, `-32003 KIND_NOT_SERVED`,
`-32004 CHANNEL_NOT_SERVED`, `-32005 CURSOR_EXPIRED`, `-32006 NOT_WRITABLE`,
`-32010 VALIDATION_FAILED`, `-32011 REVISION_CONFLICT`, `-32020
RESOLUTION_INCOMPLETE`, `-32030 SEARCH_UNAVAILABLE` — and then says the thing
that matters more:

> **An empty result and an unanswerable question are different values, and a
> server MUST NOT collapse them.**

`instances/list` returning `[]` is a *claim*: nothing of this Kind exists here.
A server that could not read its store must error instead. This is the one rule
the reference implementation paid for repeatedly — every place a failure was
reported as an empty collection, a caller eventually read it as an answer — and
it is why `dna.protocol.server`'s catch-all answers `-32603` and why there is no
path in the package from an exception to a default value.

## Transport

`stdio` first, framed as **newline-delimited JSON**. One JSON value per line,
which is what MCP's stdio transport uses (so a host that already muxes MCP
needs no second framer), which is safe by construction (RFC 8259 escapes
control characters inside strings, so a serialised JSON value provably contains
no raw newline), and which stays readable under `tee` and `grep`.

The framing is a seam: `DnapServer` deals in decoded payloads and knows nothing
about lines, so an HTTP binding with a streaming lane for change notifications
is a new module beside `dna.protocol.stdio`, not a change to anything under it.

## Relationship to the SDK

The SDK already contains most of DNAP in the wrong clothes: `kinds/list` and
`instances/*` exist as MCP tools (a menu for a model rather than a protocol for
a program); `resolve/agent` exists as `dna.definitions.resolve_agent`, which its
own docstring calls a *compatibility projection*; the neutral shape exists as
`EmitContext`, with three hand-synchronised projections of it. Channels,
revisions, cursors and watch are absent.

Adopting DNAP does not mean rewriting the SDK. It means **naming the contract
that three copies are currently approximating**, and letting everything that is
not that contract — the board, the memory verbs, the cost accounting, the code
emitters — become separate servers speaking the same protocol. Today those
separations are conventions; under a protocol they are verifiable.
