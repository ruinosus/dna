# DNA Protocol (DNAP) 1.0 — draft

**Status:** draft, unapproved. Revised 2026-08-12 after the first **clean-room
implementation** — 2.021 lines of dependency-free TypeScript, written from this
text alone by someone forbidden to read the reference SDK. That implementation
returned 12 interoperability-breaking gaps and ~40 smaller decisions it had to
invent; this revision closes them. The gaps are listed in §11, because a
specification that hides where it was wrong teaches nothing.
**Framing:** JSON-RPC 2.0.
**Written:** 2026-08-12, from measurements against the DNA SDK at 0.80.0.

---

## 0. Why this exists

Three protocols already govern how an agent *runs*:

| protocol | governs | by |
|---|---|---|
| **MCP** | how tools are exposed to a model | Anthropic |
| **A2A** | how one agent delegates to another | Linux Foundation |
| **AHP** | how a live session is hosted and shared across clients | Microsoft |

None of them says **what the agent is**. Each assumes a definition arrived from
somewhere. AHP states it outright: *"AHP assumes agents already exist."*

That gap is what DNAP specifies: **the definition of an agent as a typed,
versioned, owned document, and the contract for resolving it into something a
runtime can execute.**

DNAP does **not** speak MCP, A2A or AHP. It **declares** them, the way a
`package.json` declares a registry it does not implement.

### The one method that justifies a new protocol

`resolve/agent`. MCP resolves *tools*; A2A resolves *cards*; AHP resolves
*sessions*. Nothing resolves *definitions*, and every runtime re-implements that
resolution privately — which is why the same agent cannot move between them
without being copied.

---

## 1. Scope

### In scope

- The document shape every participant shares.
- A registry of **Kinds** (types), advertised by the server, never hardcoded by
  the client.
- Reading, writing, **searching** and watching instances of those Kinds.
- **Resolution**: projecting a definition into a runtime-neutral shape.

### Deliberately out of scope

- **Execution.** DNAP never runs an agent, never calls a model, never holds a
  session. A resolved definition is handed to a runtime; what happens next is
  that runtime's protocol.
- **Tool invocation.** That is MCP.
- **Delegation between agents.** That is A2A.
- **Session sharing.** That is AHP.
- **Prompt composition strategy.** The server MAY compose; how it composes is
  implementation, not protocol.

> ⚠️ A protocol that also executed would grow without bound, because every
> runtime would want its own verbs. The line is drawn at *resolution* on
> purpose: it is the last point at which all runtimes still agree.

---

## 2. Transport and framing

DNAP uses **JSON-RPC 2.0** for message framing. Transport is unspecified;
`stdio` and HTTP (with a streaming lane for notifications) are the expected
bindings.

Requests, responses, and notifications follow JSON-RPC 2.0 exactly. Batch
requests MUST be supported by servers and MAY be used by clients.

---

## 3. Addressing: channels

Every request carries a `channel` URI naming what it acts on.

```
dnap-root://                    connection-level operations (initialize, kinds/*)
dnap-scope:/<scope>             one scope's instances
dnap-scope:/<scope>#<tenant>    the tenant overlay of that scope
```

### The tenant overlay

`dnap-scope:/<scope>#<tenant>` is the same scope seen through one tenant's
layer, and the semantics are three rules:

- **read-through** — an instance absent from the overlay resolves to the base
  channel's. A tenant sees everything the scope has, plus what it changed.
- **write-local** — a write on the overlay channel lands in the overlay and
  never touches the base. This is the whole point: a tenant cannot edit the
  platform's copy by accident.
- **no tombstones** — `instances/delete` on the overlay removes the tenant's
  own version, revealing the base one again. It cannot hide a base instance.
  Hiding would make "this tenant has no X" and "this tenant deleted X"
  indistinguishable to every reader, which is §7's rule wearing another face.

Each channel carries its **own** `revision` sequence; a base write does not
advance the overlay's.

⚠️ These semantics were invented by the first independent implementation from a
single line of text. Any of the three could have been decided the other way, and
two servers would then disagree about what a tenant sees.

**Scope is an address, not a parameter.** This is a correction of a measured
defect in DNA's REST face: a `?scope=` query parameter was accepted and silently
ignored, returning one scope's content under another scope's name. An address
cannot be silently ignored — a server that does not serve a channel MUST answer
`-32004 CHANNEL_NOT_SERVED` rather than substituting one it does serve.

---

## 4. Lifecycle

### `initialize`

The first message on a connection. The client states what it can do; the server
answers with what it serves.

```jsonc
// →
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
  "protocolVersion":"1.0",
  "client":{"name":"opentag-agent","version":"2.1.0"},
  "capabilities":{"resolve":{},"search":{},"watch":{},"write":{}}
}}

// ←
{"jsonrpc":"2.0","id":1,"result":{
  "protocolVersion":"1.0",
  "server":{"name":"dna-cloud","version":"0.80.0"},
  "channels":["dnap-scope:/dna-cloud"],
  "capabilities":{
    "resolve":{"agent":true,"copilot":true},
    "search":{"planes":["lexical","semantic"]},
    "watch":{},
    "write":{"validate":true}
  },
  "kinds":["Agent","Tool","MCPFederation","Copilot","Genome","RuntimeBinding"]
}}
```

⭐ **`kinds` is what makes Kind-agnosticism a mechanism instead of an
aspiration.** The client learns the type vocabulary at connect time and never
writes a Kind name of its own. A client that names an unadvertised Kind gets
`-32003 KIND_NOT_SERVED`.

Following AHP's rule, **a method outside every advertised capability MUST be
rejected with `-32601` Method not found** — not silently ignored, and not
answered with a degraded result.

**The effective capability set is the INTERSECTION of what the client sent and
what the server answered.** A client that did not ask for `write` cannot write,
even against a server that offers it. The alternative reading — the client's
field is decorative — is equally defensible from the text and *disagrees about
whether a call succeeds*, so it is fixed here: a client declares the surface it
intends to use, and the server holds it to that.

⚠️ **The vocabulary is live, and a client is not wrong to race it.** A Kind
legal at `initialize` may answer `-32003` after a `kinds/changed`. That is the
registry moving, not a client bug; a client SHOULD re-read `kinds/list` on that
notification rather than treat the refusal as its own error.

---

## 5. The document

Every instance is a JSON object with four top-level members:

```jsonc
{
  "apiVersion": "github.com/ruinosus/dna/v1",
  "kind": "Agent",
  "metadata": {
    "name": "opentag-triage",     // unique within (channel, kind)
    "id": "01J8…",                // server-minted, stable, opaque
    "revision": "4172",           // opaque, monotonic per channel
    "description": "…"
  },
  "spec": { /* governed by the Kind's schema */ }
}
```

`metadata.name` is authored; `metadata.id` and `metadata.revision` are derived
and MUST NOT be supplied on write.

⚠️ **`metadata.id` is minted, stable and opaque — and no method accepts one.**
It exists so an external system can hold a reference that survives a rename,
and today that reference cannot be redeemed over this protocol. Either a
lookup-by-id belongs in 1.0, or the member should not be specified. Left
unresolved on purpose, in §10. Servers MAY carry additional `metadata`
members; clients MUST preserve unknown members on round-trip.

---

## 6. Methods

### 6.1 Kinds

#### `kinds/list`

Returns the Kinds this channel serves, with the shape of each.

```jsonc
// ← result
{"kinds":[
  {"kind":"Agent","apiVersion":"github.com/ruinosus/dna/v1",
   "plane":"composition","promptTarget":true,"writable":true},
  {"kind":"Tool","apiVersion":"github.com/ruinosus/dna/v1",
   "plane":"composition","promptTarget":false,"writable":true}
]}
```

`plane` is `composition` (participates in resolving an agent) or `record`
(stored, versioned, but never composed). Measured on the reference
implementation: 27 of 89 Kinds are `composition`; **3 are `promptTarget`**.

#### `kinds/describe`

`{"kind":"Agent"}` → the JSON Schema of `spec`, plus declared relations.

> The schema travels because a client that cannot see it must guess, and a
> guessing client writes documents the server will reject.

#### Creating a Kind — `KindDefinition`

⭐ **The reflexive rule.** A Kind is an instance of the Kind `KindDefinition`.
Writing one **registers a type**; there is no other way, and no out-of-band
mechanism is permitted. This is what §0 means by a typed document system that
governs its own vocabulary.

```jsonc
{"apiVersion":"github.com/ruinosus/dna/core/v1",
 "kind":"KindDefinition",
 "metadata":{"name":"ReviewChecklist"},
 "spec":{
   "kind":"ReviewChecklist",           // the type this defines
   "apiVersion":"example.com/acme/v1", // the apiVersion its instances carry
   "plane":"record",                   // "composition" | "record"
   "schema":{ /* the JSON Schema of its instances' spec */ }}}
```

**`metadata.name` MUST equal `spec.kind`.** One name, no mapping. A second
spelling of the same thing is a place for the two to drift, and every reader
would then have to know which one is authoritative.

A successful write MUST be followed by `notifications/kinds/changed` with
`change: "registered"`, and the Kind MUST appear in `kinds/list` from that
moment. Deleting the `KindDefinition` fires `change: "revoked"`; whether stored
instances of a revoked Kind remain readable is the server's policy, but it MUST
NOT accept new ones.

⚠️ **`spec.schema` is bounded, not "JSON Schema" at large.** A server MUST
support exactly: `type`, `enum`, `const`, `required`, `properties`,
`additionalProperties`, `items`, `minItems`, `maxItems`, `uniqueItems`,
`minLength`, `maxLength`, `pattern`, `minimum`, `maximum`. A `KindDefinition`
carrying any other keyword MUST be rejected at write with `-32010` on
`spec.schema`. A keyword the server stores, hands out through `kinds/describe`,
and does not enforce is a lie told to every client that reads the schema to
pre-validate.

⛔ **Kinds built into a server MAY be advertised without a stored
`KindDefinition`**, but they MUST be describable through `kinds/describe` under
the same bounded schema. A built-in that cannot describe itself is invisible to
every client that does not already know it.

### 6.2 Instances

#### `instances/list`

```jsonc
// → params
{"channel":"dnap-scope:/dna-cloud","kind":"Agent",
 "select":"full",              // "names" | "full" | ["spec.model","spec.tools"]
 "limit":200,"cursor":null}

// ← result
{"instances":[ /* … */ ],
 "revision":"4172",            // the snapshot these results belong to
 "cursor":"eyJvIjo…",          // absent when exhausted
 "selected":"full"}
```

**Three rules, each correcting a measured defect:**

1. **`select` is a contract, not a hint.** A server that cannot honour the
   requested projection MUST answer `-32602`. It MUST NOT return a narrower
   shape while echoing the request. *(Measured: `?fields=spec` returned
   `[{"name":…}]` and echoed `"projected":["spec"]`.)*

2. **`cursor`, never offset.** Offset pagination is `OFFSET n` in SQL and
   degrades quadratically. A cursor MAY expire; an expired cursor MUST answer
   `-32005 CURSOR_EXPIRED` so the client restarts rather than silently skipping.

3. **`revision` is constant across a paginated read.** All pages of one listing
   belong to one snapshot. Without this a client assembles a quilt of moments
   and calls it a state.

   ⚠️ This MUST is what `-32005` exists for, and the two are load-bearing
   together: honouring it requires the server to hold a snapshot, which has a
   lifetime and a memory bound. A server that keeps no snapshot passes every
   naive test and violates this rule the first time anyone writes mid-listing.
   `CURSOR_EXPIRED` is not a courtesy — it is how a server with finite memory
   stays honest.

4. **Order is lexicographic by `metadata.name`, ascending.** Rules 2 and 3 are
   both meaningless without a total order, and `metadata.name` is the only
   member §5 guarantees unique within `(channel, kind)`.

5. **The shape of `select`:**
   - `"names"` → an array of plain strings. Not one-member documents: a
     document-shaped object carrying only a name is exactly the narrower shape
     rule 1 forbids, wearing a disguise.
   - `"full"` → whole documents.
   - a path list → **exactly** the requested paths, nothing added. A server that
     helpfully attaches identity and one that does not return different rows for
     the same request; ask for `metadata.name` when you want it.

#### `instances/get`

`{"channel":…,"kind":"Agent","name":"opentag-triage"}` → the document verbatim,
including `metadata.revision`.

Supports conditional reads: `"ifNoneMatch":"4172"` → `{"notModified":true}`
with no body.

#### `instances/write`

```jsonc
// → params
{"channel":"dnap-scope:/acme","document":{ /* the whole document */ },
 "ifMatch":null}

// ← result
{"instance":{ /* stored, with metadata.id and metadata.revision */ },
 "created":true}
```

`kind` is read from `document.kind`; a separate `kind` param would be a second
spelling that can disagree with the first. `metadata.id` and `metadata.revision`
supplied by the client MUST be rejected with `-32010`.

Upsert, validated against the Kind's schema. `-32010 VALIDATION_FAILED` carries
the failing path and the rule, never a bare "invalid".

Optimistic concurrency: `"ifMatch":"<revision>"` → `-32011 REVISION_CONFLICT`
when the stored revision moved.

#### `instances/delete`

`{"channel":…,"kind":…,"name":…,"ifMatch":…}` → `{"deleted":true,"revision":"…"}`
— the revision the channel advanced to, so a watcher can order the delete
against its own reads.

### 6.3 Resolution — the reason this protocol exists

#### `resolve/agent`

Projects a definition into the **runtime-neutral shape**: everything a binding
needs, and nothing about any particular runtime.

```jsonc
// → params
{"channel":"dnap-scope:/dna-cloud","name":"opentag-triage"}

// ← result
{"resolved":{
  "name":"opentag-triage",
  "instructions":"You are OpenTag, …",        // composed, ready to use
  "model":"openai/gpt-5.5",                   // a COORDINATE, not a client id
  "tools":[{"name":"web_search","description":"…","inputSchema":{…}}],
  "mcpServers":[{"ref":"github","transport":"http","url":"…",
                 "allowedTools":["search_code"],"propagateTenant":true}],
  "toolsRequiringConfirmation":["write_review_report"],
  "knowledge":[{"collection":"politicas-internas",
                "kind":"KnowledgeChunk",
                "narrow":{"namePrefix":"politicas-internas/"}}],
  "sourceKind":"Copilot","sourceName":"opentag-copilot",
  "revision":"4172"
}}
```

**Why each member is here, and why nothing else is:**

- `instructions` — **composed**, not the raw template. Composition is where
  overlays, personas and tenant text merge; leaving it to the client would put
  the same merge in every binding.
- `model` is a **coordinate** (`provider/name`), never a vendor client
  identifier. The binding maps it. *(Measured precedent: the reference binding
  does `model.split("/",1)[-1]` in one line.)*
- `toolsRequiringConfirmation` — **policy travels with the definition.** A
  binding that had to be told separately which tools are gated would default to
  ungated the day someone forgot.
- `knowledge` — the corpora this agent may read: an allowlist, resolved, so no
  binding invents its own reach.

  ⭐ **And each entry is a searchable ADDRESS, not a bare name.** This closes a
  contradiction the first independent implementation found: §8 forbids a client
  naming a Kind of its own, yet a client holding only `"politicas-internas"`
  could not search it without hardcoding the Kind that holds chunks. Carrying
  `kind` and `narrow` here makes the client a **conduit** — it passes to
  `search/instances` exactly what `resolve/agent` handed it, and still names
  nothing.
- `revision` — a resolution is **of a moment**, and a client that caches it must
  be able to say which.

**The resolved shape is CLOSED.** A server MUST NOT add members to it. An open
shape would let one server's extra field become another binding's requirement,
and the agent stops being portable the day someone depends on it.

⛔ **Absent on purpose:** checkpointers, stores, thread indexes, telemetry
sinks, cost tables. Those are the host's, and every one of them that leaked into
a definition contract in the reference implementation became a runtime the
definition could no longer leave.

#### `resolve/copilot`

Same shape. A `Copilot` is a served surface over an `Agent`; the result carries
`sourceKind: "Copilot"` and the mounted agent's name.

### 6.4 Search

#### `search/instances`

One method, not two. Searching a corpus of document chunks is searching
instances of the Kind that holds them, narrowed by name prefix — so a separate
"knowledge search" would be the same engine behind a second contract that could
drift from the first.

```jsonc
// → params
{"channel":"dnap-scope:/acme","kind":"KnowledgeChunk",
 "query":"o que a política diz sobre reembolso",
 "k":5,
 "narrow":{"namePrefix":"politicas-internas/"},
 "minSimilarity":null}

// ← result
{"hits":[
  {"kind":"KnowledgeChunk","name":"politicas-internas/8b4e7082/00008",
   "score":0.0325,          // fused rank score — comparable only WITHIN this call
   "similarity":0.4417,     // raw cosine — comparable across calls
   "title":"…","snippet":"…"}],
 "mode":"hybrid",           // "hybrid" | "lexical"
 "degraded":false,
 "degradedReason":null,
 "relevanceNotice":"RANKED_NOT_FILTERED",
 "revision":"4173"}
```

**Five rules, and every one of them is a measurement rather than an opinion.**

**1. A result is RANKED, not FILTERED, and the envelope MUST say so.** The
server ships **no relevance floor**, because on a real corpus none separates the
relevant from the irrelevant. Measured on the reference deployment over 24
queries: **8 of 12 irrelevant queries scored above the worst genuinely relevant
one**, and neither a corpus z-score nor a top-1 margin separated them either
(12/12 overlap). A server that silently dropped low results would be asserting a
judgement it cannot make.

**2. `minSimilarity` is the CALLER's policy, never the server's default.** A
caller with context may hold a threshold; the protocol MUST NOT invent one. When
applied, the result carries `minSimilarityRemoved` with the count — a filter
that hides its own effect turns a policy into a fact. The member is **absent**
when no threshold was applied; `0` would report a filter that never ran.

**3. Two scores travel, because they are two quantities.** `score` is a fused
rank (comparable only within one call — the top hit of a two-document corpus and
of a thousand-document corpus receive the same number). `similarity` is a
**corpus-independent measure in [0,1]**, comparable across calls. A caller given
only the first cannot tell "first among bad" from "first among good".

⚠️ `similarity` is defined by that PROPERTY, not by an algorithm. Cosine is the
dense plane's instance of it; a lexical plane MAY report query-token coverage.
Naming cosine normatively would leave `minSimilarity` — the caller's only policy
knob — meaning something different on every plane, or undefined on a
lexical-only server, which rule 5 explicitly contemplates.

**`mode` names the planes that actually RAN**: `"lexical"`, `"semantic"`, or
`"hybrid"` when more than one contributed. It is drawn from the same vocabulary
as `capabilities.search.planes`, and a server MUST NOT report a mode whose
planes it did not advertise.

**4. `narrow` applies where candidates are CHOSEN, never to the list already
chosen.** Every plane over-fetches a fixed number of candidates, so a
post-filter lets one voluminous slice fill the budget and crowd every other row
out — silently, while the envelope still reports a healthy search. Measured:
adding 1000 rows of one Kind to a 153-row scope took the dense plane's top-40
from `{Issue:37, Engram:2, App:1}` to `{Chunk:40}`, with `mode` still reading
`hybrid` and `degraded` still reading `false`.

**5. `degraded` separates "I searched and found nothing" from "I could not
search".** When the semantic plane is unavailable the server MAY answer from a
lexical plane, and it MUST then set `degraded: true` with a reason. An empty
`hits` with `degraded: true` is a blind spot, not a finding — this is the
protocol's central error rule (§7) applied where it is easiest to violate.

⛔ **Not specified:** re-ranking strategy, embedding model, index topology. Those
are how a server is good, not what makes it conformant.

### 6.5 Notifications

```jsonc
{"jsonrpc":"2.0","method":"notifications/instances/changed","params":{
  "channel":"dnap-scope:/dna-cloud",
  "kind":"Agent","name":"opentag-triage",
  "change":"updated","revision":"4173"}}
```

Sent only to clients that advertised `watch` at `initialize`.

**A notification carries the fact, not the document.** The client re-reads what
it cares about. Pushing bodies would make every watcher pay for every writer.

`notifications/kinds/changed` fires when the served vocabulary changes — a Kind
approved, revoked, or registered.

> ⚠️ Watch replaces the *poll*, not the *first read*. A client still lists once
> to build its picture, then follows changes from that `revision`. Measured on
> the reference implementation: a full scope read was 522 calls and 1.13 s; with
> watch that cost is paid once per connection instead of once per boot.

---

## 7. Errors

Standard JSON-RPC codes, plus:

| code | name | means |
|---|---|---|
| `-32002` | `NOT_FOUND` | no instance by that name on that channel |
| `-32003` | `KIND_NOT_SERVED` | the Kind is not in the advertised vocabulary |
| `-32006` | `NOT_WRITABLE` | the Kind is served but `writable: false` |
| `-32004` | `CHANNEL_NOT_SERVED` | this server does not serve that scope/tenant |
| `-32005` | `CURSOR_EXPIRED` | restart the listing |
| `-32010` | `VALIDATION_FAILED` | with `path` and `rule` |
| `-32011` | `REVISION_CONFLICT` | with the current `revision` |
| `-32020` | `RESOLUTION_INCOMPLETE` | with `data.missing: [{kind,name,via}]` — **all** of them, never the first |
| `-32030` | `SEARCH_UNAVAILABLE` | no plane could run — never an empty `hits` |

### The rule that outranks the table

**An empty result and an unanswerable question are different values, and a
server MUST NOT collapse them.**

`instances/list` returning `[]` is a claim: *nothing of this Kind exists here.*
A server that could not read its store MUST error instead. `-32020` exists for
the same reason at the resolution layer: a definition that resolved *partially*
is not a definition, and returning it with the gaps silently filled is worse
than failing, because the caller cannot tell.

> This is the one rule the reference implementation paid for repeatedly: every
> place a failure was reported as an empty collection, a caller eventually read
> it as an answer.

---

## 8. Conformance

A conforming server MUST:

1. answer `initialize` and advertise its `kinds` and `capabilities`;
2. reject unadvertised methods with `-32601` and unadvertised Kinds with
   `-32003`;
3. honour `select` exactly or reject it;
4. keep `revision` stable across the pages of one listing;
5. never answer a failure with an empty collection.

A conforming client MUST:

1. take its Kind vocabulary from `initialize`, and **name no Kind of its own**;
2. treat `revision` as opaque;
3. preserve unknown `metadata` members on round-trip;
4. restart a listing on `-32005` rather than assuming exhaustion.

⭐ Rule 1 for clients is the whole point. It is the difference between
"Kind-agnostic" as a claim and as a property a test can fail on. In the
reference implementation today, the kernel names 21 Kinds literally in its
inheritance resolver — under this specification that is a conformance failure,
which is a thing a guard catches, not a comment asks for.

---

## 9. Relationship to the reference implementation

The DNA SDK (0.80.0) already contains most of this, in the wrong clothes:

| DNAP | today |
|---|---|
| `kinds/list`, `instances/*` | exists — as **MCP tools** (`list_kinds`, `list_documents`, `get_document`, `write_document`), i.e. as a menu for a model rather than a protocol for a program |
| `resolve/agent` | exists — `dna.definitions.resolve_agent`, which the SDK's own docstring calls a *"compatibility projection"*, with one production caller |
| the neutral shape | exists — `EmitContext`, with **three** hand-synchronised projections of it |
| channels | absent — scope is a parameter, and one face ignores it |
| `revision`, cursor, watch | absent — offset pagination, no conditional read |

Adopting DNAP would not mean rewriting the SDK. It would mean **naming the
contract that three copies are currently approximating**, and letting everything
that is not that contract — the board, the memory verbs, the cost accounting,
the code emitters — become separate servers speaking the same protocol.

That last consequence is the real prize: today those separations are
conventions. Under a protocol they are **verifiable**.

---

## 10. Open questions

1. ~~**Write, or read-only?**~~ **DECIDED (founder, 2026-08-12): the protocol
   reads, writes AND searches.** Read-only would have halved the surface and
   closed the door on a third party *authoring* — and authoring is the act that
   makes the Kind system reflexive, since a Kind is itself a written document.
2. **Does `resolve/*` compose the prompt, or return the parts?** Composed is
   proposed above, and it hides overlay/persona/tenant merging behind the
   server. The cost is that a client cannot re-compose differently.
3. **Where do relations travel?** `kinds/describe` carries them; instances do
   not. A graph traversal method (`instances/refs`) is deliberately not
   specified until something needs it.
4. **Batch resolve.** A host mounting nine copilots resolves nine times.
5. **Redeeming `metadata.id`.** It is minted and stable and there is no method
   that takes one (see §5).
6. **Client conformance has no test surface.** §8 asks a client to treat
   `revision` as opaque and preserve unknown `metadata` — and a server cannot
   observe either. Only client rule 1 is checkable, and only because the server
   refuses. A specification that closes on *"a property a test can fail on"*
   should say which side runs the test.
7. **`instructions` composition is deliberately unspecified** (§1), which means
   `resolve/agent`'s most important field is by design not reproducible between
   two conforming servers. The clean-room implementation confirmed the cost is
   real, not theoretical.
5. **Multi-scope.** One connection serves one scope's channels. Inheritance
   across scopes — which the reference implementation supports locally — does
   not cross a connection, and the measured refusal is loud rather than silent.
   Whether that is the right trade is unanswered.

---

## 11. What the clean room found

The first independent implementation was given this document and nothing else,
and forbidden from reading the reference SDK. It shipped nine methods in 2.021
lines with zero runtime dependencies — which is the useful half of the result:
**the protocol is implementable from its text, in another language, without the
ecosystem it was born in.**

The other half is this list. Each entry is a place where two honest readers
would have built incompatible servers.

| # | the gap | closed in |
|---|---|---|
| A11 | ⭐ **how a Kind is created had no wire form** — the document argued for authoring as its foundation and never specified it | §6.1 |
| D6 | ⭐ **search contradicted conformance** — `knowledge` returned collection names, and searching them required the client to name a Kind, which §8 forbids | §6.3 |
| A1 | `instances/write` had no documented params | §6.2 |
| A2 | no code for *this instance does not exist* | §7 |
| A3–A5 | `select` result shapes, and listing order was never specified — cursors and snapshots are both meaningless without a total order | §6.2 |
| A6 | whose capabilities gate a method | §4 |
| A7–A8 | `similarity` was defined as cosine on a plane that has none; `mode` and `planes` were different vocabularies | §6.4 |
| A9 | the `minSimilarity` removal count had no field name | §6.4 |
| A10 | "JSON Schema" was named and never bounded | §6.1 |
| A12 | the tenant overlay was an address with **no semantics at all** — one line of text, three rules invented | §3 |
| A13–A15 | `write`/`delete` had no result shape; `-32020` carried nothing; the resolved shape's closedness was implied, never stated | §6.2, §6.3, §7 |
| D1 | rule 3 mandates a snapshot the document never mentioned, and `-32005` read as optional courtesy when it is the escape hatch that makes the MUST affordable | §6.2 |
| D2, D5 | `metadata.id` has no address; the live vocabulary races §8's client rule | §5, §4, §10 |

⚠️ **A11 is the one worth remembering.** The feature this specification argued
hardest for — *a Kind is itself a written document* — was the single feature it
did not specify. It took an implementer with no access to the reference to
notice, because everyone who could read the SDK already knew the answer and
never saw the hole.
