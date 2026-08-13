# DNAP 1.0 — draft

**Two methods.** JSON-RPC 2.0.

**Status:** draft, unapproved. This is a **rewrite**. The previous draft specified
nine methods and, measured against prior art, reimplemented roughly 80% of the
Kubernetes API in order to add one operation nobody else had. Git history keeps
it; §7 says what changed and why.

---

## 0. What this is

Five open standards already specify **what an agent looks like**:

| | defines | where an instance lives |
|---|---|---|
| **Agent Format** (`.agf.yaml`) — Snap Inc. | the file | *"version it in git and ship it"* |
| **OASF + Directory** — Linux Foundation | the Record | published, and **frozen at publish** |
| **ADL** | the "passport" document | it is a document |
| **A2A AgentCard** | the card | a file at a well-known URL |
| **Open Agent Specification** — Oracle Labs | a declarative DSL | — |

DNAP defines **none of that**, deliberately. It specifies the one operation all
five leave to the reader:

> **`resolve` — given a stored definition and a context, return the form that is
> ready to use.**

MCP already standardizes this for *messages*: `prompts/get` takes a name plus
arguments and returns server-composed messages. **DNAP is that same move for a
typed document of any kind** — the market names the type, the server composes
the instance.

### Why this is not a sixth format

A format competes with the other five. This one **consumes** them. A server
advertises which types it can resolve, and those types are the market's —
`oasf.agntcy.org/v1alpha1/Record`, `agentformat.org/v1/Agent`, or a type a
tenant defined for itself. A new standard appearing is a new catalogue entry,
not a threat.

⚠️ **The previous draft got this wrong** and defined its own `Agent`, `Tool` and
`Copilot`. That put it back in the format fight — the fight with no winner and
no need.

---

## 1. Scope

**In:** announcing what a server can resolve; resolving it.

**Out, and each has an owner:** storing and listing instances (Kubernetes, Git,
a database — DNAP has no opinion); tool invocation (MCP); delegation (A2A);
session hosting (AHP); how composition works internally (implementation).

> A protocol that also stored would have to specify pagination, watch,
> concurrency and a type registry — and every one of those already has a
> standard with adoption. The line is drawn where the gap actually is.

---

## 2. Framing

JSON-RPC 2.0. Transport unspecified; `stdio` and HTTP are the expected bindings.

---

## 3. `initialize`

```jsonc
// →
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
  "protocolVersion":"1.0",
  "client":{"name":"opentag","version":"2.1.0"}}}

// ←
{"jsonrpc":"2.0","id":1,"result":{
  "protocolVersion":"1.0",
  "server":{"name":"acme-definitions","version":"0.4.0"},
  "resolvable":[
    {"kind":"Agent","apiVersion":"agentformat.org/v1"},
    {"kind":"Record","apiVersion":"oasf.agntcy.org/v1alpha1"},
    {"kind":"ReviewChecklist","apiVersion":"acme.example/v1"}
  ]}}
```

⭐ **`resolvable` is the whole type system of this protocol.** The client learns
the vocabulary here and **MUST NOT name a type of its own**. A client that does
is not portable — it works against one server and calls that conformance.

A type absent from `resolvable` MUST answer `-32003 NOT_RESOLVABLE`, never an
empty or partial result.

⚠️ **DNAP does not say where those types come from.** They may be built into the
server, imported from a public catalogue, or authored by a tenant. That is the
server's business, and keeping it out is what lets DNAP sit *under* all five
standards instead of beside them.

The list MAY change while a connection is open — a catalogue imported, a type
revoked. A server SHOULD announce it:

```jsonc
{"jsonrpc":"2.0","method":"notifications/resolvable/changed"}
```

A client that named a type legal at `initialize` and now gets `-32003` is not
buggy; the vocabulary moved. It SHOULD re-`initialize`.

---

## 4. `resolve`

```jsonc
// →
{"jsonrpc":"2.0","id":2,"method":"resolve","params":{
  "kind":"Agent",
  "apiVersion":"agentformat.org/v1",
  "name":"triage",
  "context":{"tenant":"acme","locale":"pt-BR"}}}

// ←
{"jsonrpc":"2.0","id":2,"result":{
  "resolved":{ /* an instance of that type, composed and ready to use */ },
  "provenance":{
    "sources":[
      {"kind":"Agent","name":"triage","revision":"4172"},
      {"kind":"PromptTemplate","name":"tone-formal","revision":"88"}
    ],
    "context":{"tenant":"acme","locale":"pt-BR"},
    "composedAt":"2026-08-12T18:04:11Z"},
  "revision":"4172"}}
```

### The four rules

**1. `resolved` carries the MARKET TYPE's shape, not DNAP's.** If the type is
`agentformat.org/v1/Agent`, the answer is a valid Agent Format document. DNAP
adds no members, removes none, renames nothing. A protocol that reshaped the
payload would be a format with extra steps.

**2. ⭐ `resolved` is DERIVED, and `provenance` says from what.** This is the
whole reason the operation is worth standardizing. A *stored* document can be
fetched from anywhere; a *composed* one is a claim — overlays merged, templates
expanded, references followed — and a claim without its sources cannot be
audited, cached, or debugged.

`provenance.sources` MUST list every document that contributed, with the
revision each was read at. `provenance.context` MUST echo the context actually
used, which may differ from what was sent (unknown members ignored, defaults
filled in) — echoing it is how a caller learns what the server understood.

**3. ⛔ A partial resolution is a FAILURE, never a filled-in answer.** If a
reference cannot be followed or a variable has no value, the server MUST answer
`-32020` with **every** gap:

```jsonc
{"error":{"code":-32020,"message":"resolution of 'triage' is incomplete",
  "data":{"missing":[{"kind":"Tool","name":"web_search","via":"spec.tools"}]}}}
```

A resolved document with a silently empty field is worse than an error, because
the caller cannot tell. This is the rule this project paid for repeatedly:
every place a failure was reported as an empty value, someone eventually read it
as an answer.

**4. `context` is opaque to the protocol.** DNAP fixes no key. `tenant`,
`locale`, `as_of` are conventions a server MAY honour; the protocol requires
only that whatever was honoured comes back in `provenance.context`.

### `revision`

Opaque, and it identifies **the resolution** — not any one source. Two
resolutions with the same `revision` and the same `context` MUST be identical.
That is what makes a resolved form cacheable at all.

---

## 5. Errors

| code | name | means |
|---|---|---|
| `-32002` | `NOT_FOUND` | no instance by that name |
| `-32003` | `NOT_RESOLVABLE` | the type is not in `resolvable` |
| `-32020` | `RESOLUTION_INCOMPLETE` | with `data.missing` — **all** gaps, never the first |

Plus the JSON-RPC standard codes.

**The rule that outranks the table:** an empty answer and an unanswerable
question are different values, and a server MUST NOT collapse them. There is no
shape of success that means *"I could not"*.

---

## 6. Conformance

**A server MUST** answer `initialize` with `resolvable`; refuse an unlisted type
with `-32003`; return the market type's shape unaltered; list every contributing
document in `provenance.sources`; and fail a partial resolution rather than
complete it.

**A client MUST** take its vocabulary from `initialize` and **name no type of its
own**; treat `revision` as opaque; and re-`initialize` after
`notifications/resolvable/changed` rather than read `-32003` as its own bug.

⭐ The client rule is the one worth testing, and it is testable: scan a client
for a literal type name. It is the difference between *"works with our server"*
and *"works with any server"*.

---

## 7. What changed from the previous draft, and why

The first draft had nine methods — `kinds/*`, `instances/{list,get,write,delete}`,
`search/instances` — and defined its own `Agent`, `Tool` and `Copilot`.

Two measurements killed it.

**A clean-room implementation** (2.021 lines of dependency-free TypeScript,
written from the text by someone forbidden to read the reference SDK) returned
12 interoperability-breaking gaps. Useful in itself — and it also showed how
much surface was being invented: pagination, cursors, snapshots, optimistic
concurrency, a type registry.

**A prior-art survey** then found that surface already standardized — by
Kubernetes, by AT Protocol's Lexicon/XRPC, by AGNTCY's Directory — and five
published formats where the draft had claimed *"nobody has standardized what an
agent is"*. That sentence was the load-bearing claim of the document. It was
false, and it had never been checked.

What survived both is one operation nobody covers. This draft is that operation.
**It is small because the gap is small.**

⚠️ **The removed parts were not wrong — they were someone else's.** A server
implementing DNAP still needs storage, listing and search. It should get them
where they already exist.

---

## 8. Open questions

1. **Is `resolve` an MCP extension rather than a protocol?** MCP already carries
   `prompts/get`, capability negotiation and a notification lane. A
   `definitions/resolve` method inside MCP would inherit its clients on day one.
   The cost: resolution becomes something only MCP hosts can do.
2. **Does `initialize` need to DESCRIBE the types, or only name them?** A client
   that cannot see a schema must trust the payload's shape. Adding `describe`
   makes it three methods.
3. **Is `revision` computable?** Identity across a set of composed sources is
   easy to state and expensive to implement.
4. ⭐ **Who is the second implementer?** A protocol with one server is a library
   wearing ceremony. This draft is worth finishing only if someone other than
   its author speaks it.
