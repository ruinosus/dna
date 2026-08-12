# DNAP conformance — testing a protocol, not an implementation

DNAP is the DNA spoken as a JSON-RPC 2.0 protocol. The draft specification lives
at [`docs/spec/dnap-1.0-draft.md`](../spec/dnap-1.0-draft.md); this page is
about the two things the SDK ships **around** it:

- `dna.testing.dnap_conformance` — the suite that holds a DNAP **server** to
  §8's obligations;
- `dna.dnap.DnapClient` — a **client** held to §8's other four.

## The order they were written in, and why it is the point

The suite and the client were written **from the specification, by an author who
did not read the server**, while the server was being implemented in parallel.

That is not process theatre. A conformance suite derived from an implementation
passes by construction: it encodes whatever the implementation happens to do,
including the parts that are wrong, and its green tells you only that the code
still does what it did yesterday. The whole reason a *protocol* is worth having
is that a third party can speak it — and a third party writes against the
document. So the suite has to as well, or it is testing the wrong thing.

Everywhere the document turned out not to determine an answer, the result is a
**finding against the specification** (below), not a decision quietly taken in a
test.

## Consuming the suite

```python
from dna.testing import DnapHarness, dnap_conformance_suite

async def my_server():
    server = MyDnapServer(...)
    return DnapHarness(
        endpoint=server.handle,          # required: the WIRE
        cleanup=server.close,
        break_store=server.break_store,  # optional hooks — see below
    )

import pytest

@pytest.mark.asyncio
@pytest.mark.parametrize("case", dnap_conformance_suite(my_server),
                         ids=lambda c: c.name)
async def test_dnap_conformance(case):
    await case.run()
```

The seam is the **wire**: `endpoint` takes a decoded JSON-RPC request and
returns the decoded response. stdio, HTTP and an in-process call all plug in
identically, and the suite never learns what is behind it. Envelopes are built
and read with the standard library on purpose — a JSON-RPC helper would
normalise away exactly the framing defects §2 exists to catch.

## Four outcomes, because two of them lie

A suite whose only outcomes are *pass* and *skip* tells two untruths: it lets
"never ran" read as "passed", and it lets "cannot be seen from outside" read as
"is fine". So a case ends in one of four states.

| outcome | means | counts as conformant? |
|---|---|---|
| pass | the obligation was observed to hold | ✅ |
| fail | the obligation was observed to be violated | ❌ |
| **NOT RUN** | the server honestly does not advertise what the case needs | — |
| **unverified** | the obligation is not observable, and no hook was offered | ❌ |

`DnapCaseNotApplicable` **cannot be constructed without a reason.** It takes two
mandatory strings — what was missing, and what obligation therefore went
unchecked — and raises `ValueError` on either being blank. So the report reads

```
NOT RUN — the server does not advertise the 'search' capability (wave 2).
UNCHECKED: that a caller-supplied minSimilarity is honoured (§6.4 rule 2)
```

and never just "skipped".

`DnapRuleUnverified` is deliberately **not** a skip. It is an `AssertionError`,
it fails a pytest run, and `report.ok` is False while any exist. A server does
not earn a green on §7's central rule by declining to be testable.

A fifth outcome, `DnapSpecGap`, reports a case that cannot be written because
the *document* is underdetermined. It is never a pass either.

## The rule that outranks the error table, and how it is actually tested

> An empty result and an unanswerable question are different values, and a
> server MUST NOT collapse them. — §7

This is the easiest rule in the specification to test uselessly. Asking a
healthy server a healthy question and observing that it did not lie proves
nothing. It is tested in four layers:

1. **A positive control.** Every "must refuse" case first asserts that the
   *same request shape*, on a served channel with a served Kind, **succeeds**.
   Without it, a server that errors on absolutely everything passes every
   negative probe in the suite. `test_a_server_that_errors_on_everything_fails_
   the_positive_control` proves that server now fails — and that the only cases
   still passing against it are the ones about framing and the handshake, which
   it genuinely still does correctly.
2. **Falsifiability of `[]`.** An empty collection must be a *reading* of a
   store, not a constant: the suite writes an instance and requires the same
   listing to stop being empty. If nothing you can do makes the collection
   non-empty, the emptiness was never an observation.
3. **The three refusals servers turn into `[]`** — an unserved channel, an
   unadvertised Kind, and a cursor the server never minted. Each is separately
   asserted *not* to be an empty collection, so the report distinguishes "wrong
   error code" from "the failure was collapsed into a finding". They are
   different bugs: the first makes a client retry wrongly, the second makes a
   client believe an emptiness nobody observed.
4. **Induced failure.** With `break_store`, the suite breaks the store and
   requires an error. Without it, the case ends `unverified`.

## The suite is itself tested — by mutation

A conformance suite that has never failed is a suite nobody has checked.
`tests/dnap_stub.py` is an in-memory DNAP server with a dial of **45
deliberate defects**, one per rule, several of them the defects the
specification cites as measured — the `?scope=` that was silently ignored, the
`?fields=spec` that echoed the request and returned a name, the post-filter that
left `{Chunk:40}` while the envelope still read `degraded: false`.
`tests/test_dnap_conformance_kit.py` asserts that each mutation makes its case,
*by name*, fail.

A rule the suite does not catch is a rule the suite does not have, however well
it reads.

## The client, and the obligation that is a guard rather than a test

§8 asks four things of a client. Three are behaviour and are tested as such:
`revision` is carried opaquely, unknown `metadata` members survive a
round-trip (exactly `id` and `revision` are dropped, because §5 makes those
derived), and `list_all` **restarts** on `-32005` instead of assuming
exhaustion.

The first obligation is different:

> take its Kind vocabulary from `initialize`, and **name no Kind of its own**

No behavioural test can express that, because a client can pass every functional
test while carrying a literal type name that only fires on one branch. So it is
a **guard**: `test_the_client_names_no_kind` reads the client package's own AST
and asks the **live registry** whether any string constant in it is a registered
Kind. The oracle is the registry, so the guard has no vocabulary of its own to
drift, and it sees a violation the moment somebody writes one.

And because a guard nobody has watched go red is a guard nobody has tested,
`test_the_kind_scan_actually_bites` plants a literal and requires the scan to
find it — and requires it *not* to fire on a docstring, which is describing
rather than naming.

The client also enforces one **server** obligation on the server's behalf:
`list_all` refuses to hand back a listing whose pages reported different
revisions. Silently concatenating them is how nobody ever notices.

## What is waiting on wave 2

`resolve/*` and `search/*` are written and currently report **NOT RUN** against
a server that advertises neither, each naming the obligation it left unchecked.
The five search rules of §6.4 are the richest material in the document, and
three of the cases are worth calling out:

- **no relevance floor** (rule 1) is expressed falsifiably: over a corpus known
  to be non-empty, a query of nonsense must still return hits, because ranking
  without a floor always produces an order. A server with a hidden floor returns
  nothing — and returns it with `degraded: false`.
- **`narrow` applies at candidate selection** (rule 4) is caught by *counting*,
  because a post-filter is invisible in the envelope: `mode` still reads
  `hybrid` and `degraded` still reads `false` while a voluminous slice crowds
  every other row out. The expected count comes from `instances/list` — ground
  truth — never from the search whose correctness is in question.
- **`similarity` is a property, not an algorithm** (rule 3). The spec defines it
  as a corpus-independent measure in [0,1] precisely so `minSimilarity` means
  the same thing on a dense plane and on a lexical-only server, so the case must
  not test for a cosine. It tests the property: *the same query over the same
  document keeps its `similarity` when the candidate set changes, while `score`
  is free to move.* A server reporting a rank-derived number under that name
  fails — and that server is exactly the one that leaves a caller unable to tell
  "first among bad" from "first among good".

## The clean-room revision, and what it did to this suite

Between the first version of this suite and this one, the specification grew
from 479 to 676 lines: a **clean-room implementation** — 2 021 lines of
dependency-free TypeScript, written from the text alone by someone forbidden to
read the reference SDK — returned 12 interoperability-breaking gaps, and §11
lists them.

That is the same method as this suite, pointed at the document instead of at a
server, and the two agree in a useful way: of the nine holes this suite reported
against the 479-line draft, the clean room independently found **six** (the
unnamed `minSimilarity` removal count is its A9; the missing NOT_FOUND code is
its A2; the unspecified `select` shapes and write/delete result shapes are
A3–A5 and A13; the unbounded "JSON Schema" is A10). Two readers with no contact
converging on the same holes is evidence the holes were real rather than
either reader's confusion.

**The revision made this deliverable bigger, not smaller.** Almost every gap the
clean room closed is a rule a suite can now hold a server to, where before there
was nothing to hold it to:

| the revision added | the case it became |
|---|---|
| listing order is lexicographic by `metadata.name` | `listing_order_is_lexicographic_by_name` — ⭐ *rules 2 and 3 are both meaningless without a total order*, so this one carries the cursor and the snapshot |
| `"names"` returns plain strings; a path list adds nothing | `select_names_returns_plain_strings`, `select_paths_adds_nothing` |
| effective capabilities = client ∩ server | `effective_capabilities_are_the_intersection` — opens a second connection asking for nothing, and requires the same method to be `-32601` on it |
| `KindDefinition` has a wire form (gap A11) | `writing_a_kind_definition_registers_the_kind`, `kind_definition_name_must_equal_its_kind`, `kind_definition_schema_is_bounded`, `every_served_kind_can_describe_itself` |
| the tenant overlay has semantics (gap A12) | `tenant_overlay_reads_through_to_the_base`, `a_tenant_write_never_touches_the_base`, `a_tenant_delete_reveals_the_base_rather_than_hiding_it` |
| `-32002 NOT_FOUND`, `-32006 NOT_WRITABLE` | `deleted_instance_is_a_miss_not_a_blank`, `a_read_only_kind_refuses_writes_with_not_writable` |
| the resolved shape is CLOSED | `the_resolved_shape_is_closed` |
| `knowledge` entries are addresses (gap D6) | `resolved_knowledge_is_a_searchable_address`, `a_client_can_search_knowledge_naming_nothing` |
| `-32020` carries `data.missing`, **all** of them | `partial_resolution_is_resolution_incomplete` |
| `minSimilarityRemoved` has a name | `min_similarity_discloses_its_effect` — a real case now, where it was a `DnapSpecGap` |
| `mode` is drawn from the advertised `planes` | `mode_names_only_advertised_planes` |

⭐ Two of them land squarely on this suite's central rule, in places it had not
reached:

- **no tombstones.** *"Hiding would make 'this tenant has no X' and 'this tenant
  deleted X' indistinguishable to every reader."* That is §7's rule in the
  tenancy layer — an action recorded as a fact about the corpus — and it now has
  a case.
- **`-32020` reports ALL the missing parts.** Reporting the first turns one
  repair into *n* round trips and leaves the caller unable to tell whether it is
  nearly done or has barely started. Completeness is the half a black-box probe
  cannot judge, so `break_resolution` may return `(name, count)`; without the
  count that half is `unverified` rather than assumed.

The gap D6 fix is the one worth reading twice, because it was a **contradiction
rather than an omission**: §8 forbids a client naming a Kind of its own, and a
`knowledge` entry that was a bare collection name left the client no legal way
to search it. The fix is not a smarter client — it is an address, and a client
that is a pipe. `DnapClient.search_knowledge` is thirty lines of passing things
through.

## Findings against the specification

Written down here because a hole in the document costs more than a hole in the
code: two servers will fill it two ways and neither client will read either.

Six of the nine reported against the 479-line draft are **closed** by the
clean-room revision. These are what is left, plus what reading the revision
turned up.

| § | the hole |
|---|---|
| **6.2** | **is a fetched document wrapped, or is it the result?** `instances/get` is specified as *"the document verbatim"*, while `instances/write` now returns `{"instance": …, "created": bool}` and a conditional get returns `{"notModified": true}` — an envelope that is plainly not a document. Both readings are defensible, they disagree on **every read**, and a client cannot probe for it without already having a document to recognise. Filed by the suite as its one `DnapSpecGap`. |
| **6.2 rule 4** | **lexicographic by which collation?** Byte/codepoint order puts `"Z"` before `"a"`; a locale-aware order does not. For a protocol whose whole point is crossing languages and runtimes, two servers sorting the same names differently break the cursor in exactly the way rule 4 was added to prevent. |
| **4** | **the rule was fixed; its input was not.** The effective capability set is now the intersection — which decides whether a call *succeeds* — but the document never says which methods belong to which family. Is `instances/delete` under `write`? Is `kinds/describe` under anything? Each server will draw the line itself. |
| **3** | **which revision does an overlay `ifMatch` speak?** Each channel carries its own `revision` sequence, and read-through means an overlay listing returns base instances carrying revisions from the *base* sequence. A conditional write on the overlay against a read-through instance has two candidate revisions and the spec names neither. |
| **6.3** | **closed says no extras; nothing says the minimum.** Which resolved members are required and which may be omitted? One server sending `"tools": []` and one omitting `tools` are both "closed", and a binding written against one breaks on the other. |
| **6.1** | **where does a registration take effect?** A `KindDefinition` is written to a channel. Does it register for that channel, for the connection, or for the server? And a schema may not carry `description`/`title`/`default` under the bounded fifteen, so `kinds/describe` hands out schemas with no human-readable documentation of their own fields — probably not intended. |
| **6.4** | **`mode` versus `planes`, in the example.** The text says `mode` is *"drawn from the same vocabulary as `capabilities.search.planes`"*, and the example advertises `["lexical","semantic"]` while reporting `mode: "hybrid"`. The intent is legible, the literal reading is not, and a clean-room reader trips on exactly this class of thing. |
| 6.2 | only an **expired** cursor has a code. A cursor the server never minted is equally uninterpretable and gets `-32005` or `-32602` by coin flip. *(Still open.)* |
| 4 vs 6.1 | the relationship between connection-level `kinds` and per-channel `kinds/list` is unstated. Client rule 1 makes it load-bearing: a Kind served on a channel but absent from `initialize` is **unreachable by construction**. The suite asserts subset. *(Still open.)* |
| 6.5 | how a client **receives** a notification over a request/response binding is unstated, so §6.5 is unreachable without a harness hook. §10 q6 now acknowledges the neighbouring problem — that client conformance has no test surface at all. *(Still open.)* |
| 6.4 | `k`'s default, and `narrow`'s vocabulary beyond `namePrefix`, are unspecified. *(Still open.)* |
| 10 | editorial: the open-questions list has two items numbered 5. |

## Prior art — what was looked for before this was built

- **JSON-RPC conformance kits**: searched GitHub; the only hits are
  chain-specific (`web3-rpc-conformance`, `monad-rpc-conformance`, 1★ and 0★).
  Nothing general to adopt.
- **JSON-RPC libraries** (`jsonrpcserver`, `jsonrpcclient`, `jsonrpclib`): real
  and maintained, and deliberately **not** used here. They are absent from this
  SDK's dependency tree, and a library that normalises the envelope would hide
  the framing defects §2 makes a server MUST. Building `{"jsonrpc": "2.0", "id":
  n, ...}` is five lines of stdlib and is the thing under test.
- **Already in the tree**: `dna.testing.kind_literal_scan` already existed and
  is reused for the client guard, extended with `scan_kind_name_constants` — a
  strictly harder question for the one caller that must name *no* Kind at all.
