# DNA Protocol (DNAP) 1.0 — draft

**Status:** draft, unapproved. Nothing implements this yet.
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
and MUST NOT be supplied on write. Servers MAY carry additional `metadata`
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

#### `instances/get`

`{"channel":…,"kind":"Agent","name":"opentag-triage"}` → the document verbatim,
including `metadata.revision`.

Supports conditional reads: `"ifNoneMatch":"4172"` → `{"notModified":true}`
with no body.

#### `instances/write`

Upsert, validated against the Kind's schema. `-32010 VALIDATION_FAILED` carries
the failing path and the rule, never a bare "invalid".

Optimistic concurrency: `"ifMatch":"<revision>"` → `-32011 REVISION_CONFLICT`
when the stored revision moved.

#### `instances/delete`

`{"channel":…,"kind":…,"name":…,"ifMatch":…}`.

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
  "knowledge":["politicas-internas"],
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
- `knowledge` — the corpora this agent may read. An allowlist, resolved, so no
  binding invents its own reach.
- `revision` — a resolution is **of a moment**, and a client that caches it must
  be able to say which.

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
applied, the result reports how many hits it removed — a filter that hides its
own effect turns a policy into a fact.

**3. Two scores travel, because they are two quantities.** `score` is a fused
rank (comparable only within one call — the top hit of a two-document corpus and
of a thousand-document corpus receive the same number). `similarity` is the raw
measure and is comparable across calls. A caller given only the first cannot
tell "first among bad" from "first among good".

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
| `-32003` | `KIND_NOT_SERVED` | the Kind is not in the advertised vocabulary |
| `-32004` | `CHANNEL_NOT_SERVED` | this server does not serve that scope/tenant |
| `-32005` | `CURSOR_EXPIRED` | restart the listing |
| `-32010` | `VALIDATION_FAILED` | with `path` and `rule` |
| `-32011` | `REVISION_CONFLICT` | with the current `revision` |
| `-32020` | `RESOLUTION_INCOMPLETE` | resolution ran and could not finish |
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
5. **Multi-scope.** One connection serves one scope's channels. Inheritance
   across scopes — which the reference implementation supports locally — does
   not cross a connection, and the measured refusal is loud rather than silent.
   Whether that is the right trade is unanswered.
