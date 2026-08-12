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
`tests/dnap_stub.py` is an in-memory DNAP server with a dial of **deliberate
defects**, one per rule, several of them the defects the specification cites as
measured. `tests/test_dnap_conformance_kit.py` asserts that each mutation makes
its case, *by name*, fail.

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
The five search rules of §6.4 are the richest material in the document, and two
of the cases are worth calling out:

- **no relevance floor** (rule 1) is expressed falsifiably: over a corpus known
  to be non-empty, a query of nonsense must still return hits, because ranking
  without a floor always produces an order. A server with a hidden floor returns
  nothing — and returns it with `degraded: false`.
- **`narrow` applies at candidate selection** (rule 4) is caught by *counting*,
  because a post-filter is invisible in the envelope: `mode` still reads
  `hybrid` and `degraded` still reads `false` while a voluminous slice crowds
  every other row out. The expected count comes from `instances/list` — ground
  truth — never from the search whose correctness is in question.

## Findings against the specification

Written down here because a hole in the document costs more than a hole in the
code: two servers will fill it two ways and neither client will read either.

| § | the hole |
|---|---|
| **6.4 rule 2** | *"the result reports how many hits it removed"* is normative, and the envelope names **no member** to carry the count. Filed by the suite as a `DnapSpecGap`; it is the one case that cannot be written at all. |
| 7 | there is **no NOT_FOUND code**. `instances/get` for a missing name and `resolve/agent` for a missing definition must not answer a blank — but the document never says what they *do* answer, so two servers pick two codes. |
| 5 | `metadata.id` / `metadata.revision` "MUST NOT be supplied on write" names no error code, and — since `instances/get` returns them — never says **who strips them** on a read-modify-write. This client does; the spec should say so, or client rule 3 and §5 read as contradicting each other. |
| 6.2 | only an **expired** cursor has a code. A cursor the server never minted is equally uninterpretable and gets `-32005` or `-32602` by coin flip. |
| 4 vs 6.1 | the relationship between connection-level `kinds` and per-channel `kinds/list` is unstated. Client rule 1 makes it load-bearing: a Kind served on a channel but absent from `initialize` is **unreachable by construction**. The suite asserts subset. |
| 6.2 | the **result shapes** of `instances/get` / `write` / `delete` are unspecified. `get` says "the document verbatim", but the `notModified` answer is plainly a wrapper, so a client cannot tell whether to unwrap. |
| 6.2 rule 1 | the field-path form of `select` does not say whether `["metadata.name"]` returns a nested object or a flat key. |
| 6.5 | how a client **receives** a notification over a request/response binding is unstated, so §6.5 is unreachable without a harness hook. |
| 6.4 | `k`'s default, and `narrow`'s vocabulary beyond `namePrefix`, are unspecified. |

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
