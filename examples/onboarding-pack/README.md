# onboarding-pack — a distributable `dna init --from` example

This directory is a minimal **onboarding pack**: a repository subtree a team
publishes so that every consumer project can bootstrap the team's own agent
conventions — instead of (or on top of) the defaults embedded in `dna-cli`.

```console
$ dna init --from github:ruinosus/dna/examples/onboarding-pack
```

That single command, run inside any project, projects this pack's Kinds with
the same byte-faithful writers `dna init` always uses:

| Pack content | Projected to |
| --- | --- |
| `skills/acme-conventions/` (an `agentskills.io/v1` Skill bundle) | the skills dir of each tool selected with `--tools` (`.claude/skills/`, `.github/skills/`, …) |
| `AGENTS.md` (an `agents.md/v1` instance) | the project root — the canonical instruction surface |

Everything else about `dna init` stays the same: the SDLC board is created
from the **local** Genome (a pack never redefines the board scope), the run
is idempotent (`--force` to overwrite), and the git hooks are wired.

## Authoring your own pack

1. Create a repo (or a subtree of one) with at least one Skill bundle:
   `skills/<name>/SKILL.md` with `name` + `description` frontmatter.
2. Optionally add an `AGENTS.md` at the pack root — it replaces the embedded
   instruction surface. Without one, consumers get the embedded default.
3. Consumers run `dna init --from github:you/your-pack[@ref]`. While
   authoring, iterate offline with `dna init --from local:../your-pack`.

Pack content is validated with the same defenses as `dna install` (only
registered Kinds, JSON-Schema-checked specs, slug-only names) and is only
**projected** into tool directories — nothing is written to the `.dna/`
source. To also track the pack's documents on the project board, combine
the two channels at the same ref:

```console
$ dna install github:you/your-pack@v1     # docs into .dna/ (with provenance lockfile)
$ dna init   --from github:you/your-pack@v1   # projections into tool dirs
```

> A skill is agent instructions. Installing a third-party pack is installing
> a dependency — review the projected files before committing them.
