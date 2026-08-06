# AGENTS.md — working in the DNA repo

DNA (Domain Notation of Anything) is **Kubernetes CRDs for agentic
behavior**: a declarative, typed notation in which every participant of an
agentic system — agents, skills, souls, guardrails, tools, policies — is a
YAML/Markdown instance identified by `(apiVersion, kind)`, validated on
write against a per-Kind schema, and composed on read into prompts by a
microkernel that itself knows no Kinds (extensions register them).
Standards DNA did not invent are consumed byte-faithful under their owners'
namespaces — including this very file, which is a live `agents.md/v1`
instance that the repo's own SDK parses and round-trips
(`packages/sdk-py/tests/test_agents_md_root.py`). The runtime is Python;
other languages reach it over the REST and MCP faces.

## Layout

```
packages/sdk-py/   # THE runtime — kernel + adapters + extensions (import dna)
packages/cli/      # `dna` binary — instance CRUD + declarative SDLC (dna sdlc)
packages/client-py/ packages/client-ts/   # REST clients, generated from docs/openapi.json
docs/              # Quick start, Kinds guide, port contract, readers/writers
examples/          # hello-genome — minimal runnable scope
scopes/            # Fixture scopes, incl. 31 real marketplace skills
scripts/           # Repo guards + versioned git hooks (git-hooks/)
tests/             # Golden fixtures (behavioral + market conformance)
.dna/              # This repo's own SDLC scope (dna-development)
```

## Build & test (what CI runs)

```bash
# Python SDK
cd packages/sdk-py && uv venv && uv pip install -e ".[dev]"
uv run --no-project pytest tests -q --timeout=120

# REST client (TypeScript)
cd packages/client-ts && bun install
bun test && bun run typecheck

# CLI (installs the `dna` binary into the venv)
cd packages/cli && uv venv && uv pip install -e ../sdk-py -e ".[dev]"
uv run --no-project pytest tests -q

# Repo guards
python3 scripts/brand_guard.py
```

## Release (the version lives in FOUR files, six values)

A release is a tag; the tag drives three workflows. Before tagging, the version
must agree **everywhere** — a mismatch does not fail the build, it fails the
publish, and one of the three workflows already fails on every release for
exactly this reason (see below).

| file | value(s) |
|---|---|
| `packages/sdk-py/pyproject.toml` | `version` |
| `packages/cli/pyproject.toml` | `version`, **plus** the `dna-sdk>=X,<Y` ceiling **twice** — once in `dependencies`, once repeated in a comment further down |
| `packages/client-py/pyproject.toml` | `version` |
| `packages/client-ts/package.json` | `version` |

**Minor moves the ceiling; patch does not.** The comment that repeats the
ceiling has gone stale before — a ceiling that disagrees with its own comment is
a lie that compiles, so grep for the OLD value after bumping and expect **zero**
hits.

⚠️ **`release-client` fails on EVERY release today.** It asserts the tag matches
both client versions, and the clients sit at `0.26.0` while the SDK is at
`0.38.0` — they have never been in lockstep, and the workflow fires on every
`v*` tag. Verified failing identically at 0.35.3, 0.36.0, 0.37.0, 0.37.1 and
0.38.0. **Do not spend time debugging it as if a release broke it.** The real fix
is one of: give the clients their own tag pattern (`client-v*`), or bring them
into the lockstep. A permanently red guard is worse than no guard — nobody reads
it.

**After tagging**, wait on the **PyPI SIMPLE index**, never the JSON API:

```bash
curl -s -H "Accept: application/vnd.pypi.simple.v1+json" \
  https://pypi.org/simple/dna-sdk/ | grep -o "dna_sdk-<version>"
```

And wait with SLACK after it answers: the index responding to **you** does not
mean it responds to a CI runner. A downstream CI hit a stale CDN edge five
minutes after 0.38.0 published and failed to resolve `dna-cli` — the install
step, not the tests. A cold `uv pip install --no-cache` into a fresh venv is the
check that the package is actually **served**, not merely listed.

## Gotcha: `pytest` needs `uv run`

Bare `python -m pytest` does not work in this repo — the ambient interpreter has
no pytest, and a shared venv elsewhere on the machine may carry a STALE
`dna-sdk` install whose entry points silently generate wrong docs (it briefly
made a Kind disappear from the generated reference). Always:

```bash
cd packages/sdk-py && uv run python -m pytest tests -q
cd packages/sdk-py && uv run python ../../scripts/<guard>.py
```

## ⭐ Vocabulary — the pair is **Kind / Instance**

A **Kind** is the type. An **Instance** is a thing of that type. Nothing in
this repo calls an instance a "document" any more (i-111, 06/08/2026), and the
reason is measured: `select count(*) from dna_instances where kind =
'KindDefinition'` returns 6 — a Kind IS an instance, stored in the same table
as the instances it defines. "Document" therefore named the layer AND the
thing that defines the layer, one level apart, which is why the sentence
"create a document that is a Kind that defines documents" never closed.
Kind/Instance closes it, reflexive case included: *the KindDefinition is an
instance of the Kind KindDefinition*.

It also stops the word lying about content: an Engram is a memory, a
PricingPlan is a price table, a Sprint is a window of time. None of them is a
document in any sense.

| the thing | say | not |
|---|---|---|
| a stored thing of some Kind | instance | document, record, entity |
| the table it lives in | `dna_instances` | `dna_documents` |
| the Python class | `Instance` (`dna.kernel.instance`) | `Document` |
| the kernel verbs | `write_instance` / `get_instance` / `list_instances` / `delete_instance` | `*_document` |
| the REST collection | `/v1/kinds/{kind}/instances` | `/documents` |
| the CLI group | `dna instance` | `dna doc` |

**"Document" is still the right word where the thing IS a document** — a
`RESEARCH.md`, an attachment, an uploaded PDF, a `SourceArtifact`, a YAML
stream's `---`-separated documents, the noun in "documentation", and the VERB
("this guide documents X"). `ManifestInstance` keeps its name: it is an
instance of the manifest, not of a Kind — so `kernel.instance(scope)` returns
one, while `kernel.get_instance(scope, kind, name)` returns an `Instance`.
That neighbouring pair is the one ambiguity this rename did not resolve; if it
bites, it gets its own issue.

## Conventions

- **Behavior that crosses a boundary is golden-locked.** Public API
  surfaces, wire formats, composed prompts and scoring constants are frozen
  in committed goldens (`tests/golden-fixtures/`,
  `packages/sdk-py/tests/goldens/`). You change them by re-freezing them in
  the same PR, never by accident.
- **Brand guard.** This is the extracted public core of a production
  system; `scripts/brand_guard.py` fails CI on any internal brand token in
  tracked content or paths. Run it before pushing docs.
- **Blessed query surface.** Consume instances through the public instance
  API (`instances`, `all`, `one`, `build_prompt`, `doc.typed`) — private
  kernel internals are guarded by `test_blessed_query_surface.py`.
- **Conformance kits are the safety net.** New adapters, readers and
  writers plug into the existing kits (`test_adapter_conformance_matrix.py`,
  `test_rw_conformance_kit.py`, the market-conformance suites) instead of
  bespoke tests — market bundles must round-trip byte-identical.

## SDLC protocol — work is tracked in-repo via `dna sdlc`

The repo tracks its own lifecycle as DNA instances in `.dna/dna-development`
(the CLI's default source `./.dna`; run `dna` from the repo root). The flow
is **story-first**:

```bash
dna sdlc brief                          # session start — what's in flight
dna sdlc hooks install                  # one-time per clone — commit trailers
dna sdlc story create s-my-work --feature f-x --desc "..." \
  --ac "Given/When/Then ..." --dod "code+tests+docs ..."   # AC + DoD required
dna sdlc story start s-my-work --plan "plan of attack"      # plan gate
dna sdlc story comment s-my-work --body "decided X because Y"  # narrate as you go
dna sdlc test-guide create tg-my-work --verifies Story/s-my-work --step "run :: expect"
dna sdlc test-run record tg-my-work --outcome pass          # test gate for done
dna sdlc story pr s-my-work             # gh pr create, pre-filled FROM the story
dna sdlc story done s-my-work           # only after the PR merges
```

While a story is active, every commit is stamped with `Work-Item:` +
`dna-sdlc[bot]` trailers by the versioned hook — that is the provenance
seal linking git history to the work item (`dna sdlc story commits s-x`).

## Do not

- **Never hand-edit `.dna/**.yaml` for status changes** — the CLI is the
  canonical write path (validation, timeline and journey events fire there).
- **Never do non-trivial work without an active story** — unstamped commits
  are invisible to `story commits` / `story show`; absence is signal.
- **Never mark a story `done` with a gap** — finish to market standard or
  keep it `in-progress` / decompose into tracked child stories.
- **Never commit to `main` directly — every change lands via a feature
  branch → PR.** `main` tracks `origin/main`; work happens on a branch and
  merges through review (`dna sdlc story pr` opens the PR pre-filled from the
  story; `story done` only after it merges). Cherry-picking commits onto
  `main` to "keep momentum" is the exact anti-pattern — it bypasses review
  and is how the tree silently diverges from the remote. **This holds for
  EVERY repo you touch, each on its own gitflow:** `dna` and `dna-cloud` are
  PR-based (branch → PR → merge, no `--admin` bypass); a repo with no remote
  (a local-only app) merges to its local trunk with `--no-ff`. When you start
  in one repo's directory but the work belongs to another, state the repo +
  branch + path in every update so nobody loses the thread. (Regressed once —
  `i-respect-repo-gitflow`.)
