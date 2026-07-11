# How to install bundles from a repository

`dna install` is the ecosystem's front door: it takes a repository URI,
detects the DNA documents inside the fetched tree, validates each one, and
writes the valid ones into your local source — through the same
`kernel.write_document` path a locally-authored document takes, so every
write guard runs. This guide covers the URI grammar, the install pipeline,
how conflicts and invalid documents are handled, and the provenance record
each install leaves behind.

For a quick taste, see the [CLI tour](cli-tour.md#dna-install-install-bundles-from-a-repository);
for every flag, the [generated reference](../reference/cli/install.md).

## `dna install` vs `dna init` — write to source, or project to tools

These two commands both take the *same* `github:owner/repo[/subdir][@ref]`
grammar and share the exact same fetch + untrusted-input validation code,
so it is easy to reach for the wrong one. They differ in **where the
content lands**, and that difference is the whole point:

| | `dna install <uri>` | `dna init` (and `dna init --from <uri>`) |
| --- | --- | --- |
| **Goal** | Add Kinds (Skills, Agents, …) to *your project's data* | Make your project *agent-ready* — the coding agent learns how to operate it |
| **Writes to** | Your **source** — documents under `.dna/<scope>/`, plus an `installed.lock` provenance record | **Tool directories** — the skill into `.claude/skills/`, `.github/skills/`, …, and `AGENTS.md` at the project root |
| **Also creates** | The target scope (a minimal `Genome`) if it doesn't exist | An **empty SDLC board** (a `Genome` under `.dna/<scope>/`) + git hooks — but the pack's Skills/AGENTS are **never** written into your source as documents |
| **Regenerable?** | No — installed documents are real, versioned source you own and edit | Yes — projections are regenerable from the Kind; re-run to refresh them |
| **What you get** | A Skill/Soul/Agent you can compose, query, and evaluate like any other document | A `dna-sdlc-cli` skill your agent reads, and `AGENTS.md` conventions every tool honors |

Put another way:

| I want to… | Use |
| --- | --- |
| …add a marketplace Skill (or any Kind) from a repo **into my project** so I can compose/query/evaluate it | `dna install github:owner/repo` |
| …make my AI coding agent **know how to operate this project** (the story-first workflow, the SDLC verbs) | `dna init` |
| …hand my team its **own** onboarding skill + `AGENTS.md`, projected into every tool | `dna init --from github:owner/repo` |
| …do the last one **and** also keep the pack's documents on my board | `dna init --from <ref>` **and** `dna install <ref>` (same ref — they compose) |

"Install" = the content becomes part of your **source**. "Init" =
regenerable **projections** land in each agent tool's directory. The
[`dna init` tutorial](../getting-started/agent-onboarding.md) covers the
agent-readiness side (including `--from` onboarding packs) in full; the
rest of *this* guide is the install pipeline in detail.

## The URI grammar

```text
github:owner/repo[/subdir][@ref]    # shallow clone of a public GitHub repo
local:<path>                        # a directory already on disk
```

The `github:` form is the **same grammar** `Genome` dependencies have
always used (`dna/adapters/resolvers/github.py` parses both), so a URI
that works in a `spec.dependencies` entry works here too:

```bash
dna install github:anthropics/skills/skills/pdf --scope market --dry-run
dna install github:anthropics/skills/skills/pdf --scope market
dna install local:~/checkouts/some-skills --scope playground
```

- `subdir` narrows the install to one subtree of the repo — point it at a
  single bundle (`.../skills/pdf`) or a whole collection (`.../skills`).
- `ref` is a branch or tag, passed to the shallow clone. Provenance is
  always pinned to the **resolved commit**, never the moving ref.
- `local:` needs no network at all — ideal for testing a drop before you
  publish it, or for air-gapped machines working from checkouts.

## What the pipeline does

1. **Fetch** — `github:` URIs shallow-clone via the same `GitHubResolver`
   the composition engine uses; `local:` just resolves the directory.
2. **Scan** — the fetched tree is walked with the kernel's registered
   readers (the exact same detection that loads your own scopes): a
   directory with a `SKILL.md` becomes a Skill, a `SOUL.md` a Soul, and
   so on; standalone `*.yaml` files with `apiVersion` + `kind` +
   `metadata.name` are collected as documents too. Dot-directories
   (`.git`, `.github`) are skipped. Mixed trees work: a claim consumes
   its **bundle**, not the subtree — an `AGENTS.md` at the tree root
   installs as an AgentDefinition *and* the `skills/` bundles next to it
   still install, while a Skill bundle (SKILL.md + companion files) is
   always exactly one document.
3. **Build the plan** — every detected document is validated (below) and checked
   against the target scope for conflicts. `--dry-run` prints this plan
   and stops; nothing is written.
4. **Write** — valid documents go through `kernel.write_document`, one by
   one. A document the kernel's own `pre_save` veto guards reject is
   reported and skipped; the install continues with the rest.
5. **Record provenance** — `<scope>/installed.lock` is upserted (see
   below).

The target scope comes from `--scope`, or is derived from the URI
(`<owner>-<repo>` for `github:`, the directory name for `local:`). A scope
that does not exist yet is created with a minimal `Genome` of its own.

## Untrusted input — validation is the first defense

A manifest is executable behavior, so a third-party manifest is an
injection vector — that is the core of the
[threat model](https://github.com/ruinosus/dna/blob/main/SECURITY.md).
`dna install` therefore rejects, **before any write**:

- documents whose `(apiVersion, kind)` is not registered in your kernel —
  nothing is guessed or coerced;
- documents whose `spec` fails the Kind's JSON Schema (the reported reason
  names the failing field);
- documents whose `metadata.name` is not a plain slug — path-shaped names
  (`../evil`) never reach the filesystem layout;
- **root Kinds** (`Genome`) found in the fetched tree — an install adds
  content to your scope; it never lets a remote repo redefine the scope's
  identity.

Rejections are per-document and didactic: the plan shows each one with its
reason, the valid documents still install, and the exit code is non-zero
only when *nothing* usable landed. The kernel's `pre_save` veto guards run
on every write as the second layer — exactly as they would for a local
edit.

## Conflicts

A document that already exists in the target scope is **skipped with a
warning** by default — re-running an install is idempotent. Pass `--force`
to overwrite existing documents with the fetched versions.

## Provenance — `installed.lock`

Every successful install upserts `<scope>/installed.lock`, reusing the
kernel's lockfile v3 shape (`dna.kernel.lock`) so the same tooling that
verifies scope lockfiles can read it:

```yaml
# Generated by dna install — DO NOT EDIT
lockVersion: 3
generated_at: '2026-07-10T05:02:11+00:00'
scope: market
documents:
- name: pdf
  kind: Skill
  apiVersion: agentskills.io/v1
  origin: github:anthropics/skills/skills/pdf@9d2f1ae18723…   # pinned commit
  path: .
  sha256: 4f0b0f2b…                                           # canonical raw-doc digest
```

`origin` is pinned to the commit that was actually fetched (even when the
URI said `@main` — or nothing), `path` is where the document lived inside
the fetched tree, and `sha256` digests the installed raw document, so you
can always answer *what came from where, at which revision, and has it
changed since*. Entries merge by `(kind, name)`: reinstalls and installs
from additional sources update their own entries and leave the rest.

## Offline behavior

No network is not an error state: `github:` fetches fail with a didactic
message (check the URI, the repo, your connectivity — or use `local:`
against a checkout), never a traceback. The test suite's `github:` path is
gated behind a `requires_network` marker and skips under `DNA_OFFLINE=1`,
which is how CI runs it.
