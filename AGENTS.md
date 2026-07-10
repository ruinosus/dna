# AGENTS.md — working in the DNA repo

DNA (Domain Notation of Anything) is **Kubernetes CRDs for agentic
behavior**: a declarative, typed notation in which every participant of an
agentic system — agents, skills, souls, guardrails, tools, policies — is a
YAML/Markdown document identified by `(apiVersion, kind)`, validated on
write against a per-Kind schema, and composed on read into prompts by a
microkernel that itself knows no Kinds (extensions register them).
Standards DNA did not invent are consumed byte-faithful under their owners'
namespaces — including this very file, which is a live `agents.md/v1`
instance that the repo's own SDK parses and round-trips
(`packages/sdk-py/tests/test_agents_md_root.py`). Two SDKs, Python and
TypeScript, implement the same kernel 1:1.

## Layout

```
packages/sdk-py/   # Python SDK — kernel + adapters + extensions (import dna)
packages/sdk-ts/   # TypeScript SDK — 1:1 twin (dna-sdk)
packages/cli/      # `dna` binary — document CRUD + declarative SDLC (dna sdlc)
docs/              # Quick start, Kinds guide, port contract, readers/writers
examples/          # hello-genome — minimal runnable scope
scopes/            # Fixture scopes, incl. 31 real marketplace skills
scripts/           # Repo guards + versioned git hooks (git-hooks/)
tests/             # Shared cross-SDK fixtures (parity + market conformance)
.dna/              # This repo's own SDLC scope (dna-development)
```

## Build & test (what CI runs)

```bash
# Python SDK
cd packages/sdk-py && uv venv && uv pip install -e ".[dev]"
uv run --no-project pytest tests -q --timeout=120

# TypeScript SDK
cd packages/sdk-ts && bun install
bun test && bun run typecheck

# CLI (installs the `dna` binary into the venv)
cd packages/cli && uv venv && uv pip install -e ../sdk-py -e ".[dev]"
uv run --no-project pytest tests -q

# Repo guards
python3 scripts/brand_guard.py
```

## Conventions

- **Py↔TS parity is test-enforced, not aspirational.** Both SDKs share the
  fixtures in `tests/`; Kind descriptors are hash-compared byte-identical
  and a kind-registry parity manifest fails the suite on undocumented
  drift. A behavior change lands in **both** SDKs in the same PR.
- **Brand guard.** This is the extracted public core of a production
  system; `scripts/brand_guard.py` fails CI on any internal brand token in
  tracked content or paths. Run it before pushing docs.
- **Blessed query surface.** Consume documents through the public instance
  API (`documents`, `all`, `one`, `build_prompt`, `doc.typed`) — private
  kernel internals are guarded by `test_blessed_query_surface.py`.
- **Conformance kits are the safety net.** New adapters, readers and
  writers plug into the existing kits (`test_adapter_conformance_matrix.py`,
  `test_rw_conformance_kit.py`, the market-conformance suites) instead of
  bespoke tests — market bundles must round-trip byte-identical.

## SDLC protocol — work is tracked in-repo via `dna sdlc`

The repo tracks its own lifecycle as DNA documents in `.dna/dna-development`
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
