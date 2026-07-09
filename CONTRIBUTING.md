# Contributing to DNA

Thanks for your interest in DNA — **Domain Notation of Anything**, a
declarative, typed notation for agentic behavior (Kubernetes CRDs, but for
agents). DNA is the extracted public core of a production system, shipped as
two behaviorally identical SDKs — Python (`packages/sdk-py`) and TypeScript
(`packages/sdk-ts`) — plus a `dna` CLI (`packages/cli`).

This guide covers how to build and test each package, the **Python↔TypeScript
parity contract** (the single most important rule in this repo), the
conformance kits, and the story-first SDLC workflow the repo dogfoods.

> **Pre-1.0.** Public APIs may still move and the packages are not yet
> published to PyPI/npm — work from the repo. See [CHANGELOG.md](CHANGELOG.md).

## Table of contents

- [Prerequisites](#prerequisites)
- [Build & test each package](#build--test-each-package)
- [The conformance kit](#the-conformance-kit)
- [The Python↔TypeScript parity contract](#the-pythontypescript-parity-contract-read-this)
- [The SDLC workflow (story-first)](#the-sdlc-workflow-story-first)
- [Commit & PR conventions](#commit--pr-conventions)
- [Repository guards](#repository-guards)
- [Do-nots](#do-nots)

## Prerequisites

| Tool | Why | Notes |
|---|---|---|
| [`uv`](https://github.com/astral-sh/uv) | Python env + deps for `sdk-py` and `cli` | Python 3.13 is what CI runs |
| [Bun](https://bun.sh) | Runtime + test runner + typecheck for `sdk-ts` | latest |
| `git` | Versioned commit hooks (`dna sdlc hooks install`) | — |
| `gh` (optional) | Opening PRs via `dna sdlc story pr` | GitHub CLI |

DNA is filesystem-first for everyday development: no database, no services,
no network. CI runs fully offline (`DNA_OFFLINE=1`); tests that would reach
Postgres, an LLM, or the network are skipped unless their resource is present.

## Build & test each package

Each package is tested exactly the way CI tests it
(`.github/workflows/*.yml`). Run all three before opening a PR.

### Python SDK — `packages/sdk-py`

```bash
cd packages/sdk-py
uv venv && uv pip install -e ".[dev]"
uv run --no-project pytest tests -q --timeout=120
```

### TypeScript SDK — `packages/sdk-ts`

```bash
cd packages/sdk-ts
bun install
bun test
bun run typecheck        # tsc --noEmit — the type surface is part of the contract
```

### CLI — `packages/cli`

The CLI is a path-dependency on the Python SDK; install the SDK editable
alongside it, which also puts the `dna` binary on your PATH.

```bash
cd packages/cli
uv venv && uv pip install -e ../sdk-py -e ".[dev]"
uv run --no-project pytest tests -q
```

### Postgres-backed tests (optional)

The Postgres source adapter has its own test lane, run against a real
`postgres:16`. Locally, point a DSN at a throwaway database and select the
marker:

```bash
DATABASE_URL=postgresql://dna:dna@localhost:5432/dna_test \
  uv run --no-project pytest tests -q -m requires_postgres
```

## The conformance kit

DNA ships its adapter test batteries **as part of the SDK** — the
`dna.testing` package — in the spirit of the Python DB-API compliance suite.
If you write a new port adapter (a source, or a bundle reader/writer), you do
**not** write bespoke tests: you plug your implementation into the existing
kit and it hands you every case a conforming implementation must pass.

```python
from dna.testing import source_conformance_suite

async def my_factory():
    src = MySource(...)
    async def cleanup():
        await src.close()
    return src, cleanup

# One pytest case per conformance case:
import pytest
CASES = source_conformance_suite(my_factory)

@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
async def test_source_conformance(case):
    await case.run()
```

The kit is **capability-aware**: it reads the adapter's declared
`SourceCapabilities` and fails when a declared capability isn't honored.
There is a matching `reader_writer_conformance_suite` for bundle
readers/writers, where **market bundles must round-trip byte-identical**.

The repo-side entry points, for reference:

- `packages/sdk-py/tests/test_source_conformance_kit.py`
- `packages/sdk-py/tests/test_rw_conformance_kit.py`
- `packages/sdk-py/tests/test_adapter_conformance_matrix.py`
- `packages/sdk-py/tests/test_market_conformance.py` and its TS twin
  `packages/sdk-ts/tests/market-conformance.test.ts`

If you touch an adapter, a reader, or a writer, **update or extend the
conformance kit** — never route around it with a one-off test.

## The Python↔TypeScript parity contract (read this)

DNA is one behavior with two runtimes. Parity is **test-enforced, not
aspirational** — a behavior change lands in **both** SDKs in the **same PR**.

Concretely, if you change the kernel, a port, a Kind's schema/composition, or
any extension behavior in one language, you must make the equivalent change in
its twin. These are the gates that will turn your PR red if you don't:

| Gate (test) | What it locks |
|---|---|
| `test_port_surface_parity.py` + `port-surface-parity.test.ts` | The **port surface**: each port's members must match across languages (snake_case ↔ camelCase), and every intentional asymmetry must carry a `justification` in `tests/parity-fixtures/port-surface-parity.json` — no silent one-sided members |
| `test_descriptor_hash_parity.py` | Record-Kind `*.kind.yaml` descriptors are **byte-identical** across the two SDKs (hash-compared) |
| `test_hash_parity.py` | Shared fixture trees hash-identical Py↔TS |
| `test_kind_registry_parity.py` | The kind-registry parity manifest — fails on **undocumented drift** in the set of registered Kinds |
| `test_composition_parity_fixtures.py` | Prompt composition produces the same output from the same inputs |

The public API is snake_case in Python (`build_prompt`, `documents`, `one`)
and camelCase in TypeScript (`buildPrompt`, `documents`, `one`). Consume
documents only through the **blessed query surface** (`documents`, `all`,
`one`, `build_prompt`, `doc.typed`) — private kernel internals are guarded by
`test_blessed_query_surface.py`.

If Python and TypeScript legitimately must differ, encode the asymmetry in the
parity fixture with a written `justification`. Asymmetries are documented,
never silent.

## The SDLC workflow (story-first)

This repo tracks its own lifecycle **as DNA documents** under
`.dna/dna-development/`, driven by the `dna sdlc` CLI. Non-trivial work is a
**Story**, opened *before* the code, and narrated on its timeline as you go.

```bash
dna sdlc brief                          # session start — what's in flight
dna sdlc hooks install                  # one-time per clone — commit trailers

dna sdlc story create s-my-work --feature f-x --desc "..." \
  --ac "Given/When/Then ..." --dod "code + tests + docs ..."   # AC + DoD are required
dna sdlc story start s-my-work --plan "plan of attack"          # the plan gate
dna sdlc story comment s-my-work --body "decided X because Y"   # narrate meaningful steps

# Test gate for done — record a guide + a passing run:
dna sdlc test-guide create tg-my-work --verifies Story/s-my-work \
  --step "run this :: expect that"
dna sdlc test-run record tg-my-work --outcome pass

dna sdlc story pr s-my-work             # gh pr create, pre-filled FROM the story
dna sdlc story done s-my-work           # ONLY after the PR merges
```

`dna sdlc story pr` assembles the whole PR from the Story document — title,
the description, the acceptance criteria as a checklist, and an attribution
footer — then stamps the PR URL back onto the Story timeline. When the PR
squash-merges, the landed commit carries the `Work-Item:` trailer, so
`dna sdlc story show` lists it with zero bookkeeping.

## Commit & PR conventions

- **Install the hooks** (`dna sdlc hooks install`). While a Story is active
  (`.dna/active-story.txt`, written by `story start`), the versioned
  `prepare-commit-msg` hook stamps every commit with two trailers — a
  machine-readable `Work-Item: Story/s-my-work` link and a
  `Co-Authored-By: dna-sdlc[bot] …` provenance seal. No active Story → no
  stamp; absence is signal.
- **Conventional-style subjects**: `feat(cli): …`, `fix(kernel): …`,
  `docs: …`. `dna sdlc story pr` titles PRs as
  `feat(<first-label>): <story title> (<s-my-work>)`.
- **Keep your identity clean.** `scripts/brand_guard.py --commits <range>`
  validates author/committer identities in CI; use a personal or
  `users.noreply.github.com` email.
- Fill in every box of [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) —
  tests passing (py + ts + cli), parity held, conformance kit updated if you
  touched an adapter/reader/writer, CHANGELOG updated, docs updated, Work-Item
  linked.

## Repository guards

DNA is the extracted public core of a larger system, so a few guards keep the
public repo clean (`.github/workflows/guards.yml`). Run the brand guard
before pushing anything with prose:

```bash
python3 scripts/brand_guard.py            # scan tracked content + paths
python3 scripts/brand_guard.py --self-test
```

It fails on the internal brand tokens of the SDK this was extracted from, in
file contents, file paths, and commit identities. If you must reference the
project's origin, call it "the internal SDK it was extracted from" — never by
its internal name. A `gitleaks` secret scan runs over history in the same
workflow.

## Do-nots

- **Never hand-edit `.dna/**.yaml` for status changes.** The `dna sdlc` CLI
  is the canonical write path — it routes through the kernel so validation,
  timeline, and journey events fire. Hand edits bypass all of that.
- **Never do non-trivial work without an active Story.** Unstamped commits
  are invisible to `story commits` / `story show`.
- **Never land a behavior change in only one SDK.** The parity gates will
  catch it; land the twin in the same PR.
- **Never route around the conformance kit** with a bespoke adapter test.
- **Never mark a Story `done` with a gap** — finish to market standard, or
  keep it `in-progress` / decompose into tracked child Stories.

Welcome aboard — and thank you for helping keep behavior as data.

### Secret-scanner hygiene (learned the hard way)

CI runs gitleaks over the **full git history**, not just the diff. Two rules
follow: never quote a secret-looking string (high-entropy text near words like
`token` or `key`) in commit messages, story narration, or docs — describe it
instead; and if the scanner flags something pre-merge, a follow-up fix commit
is not enough — amend/reword and force-push with lease so the flagged blob
leaves the branch history entirely.
