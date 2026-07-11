# Recommended skills

DNA's own workflow ships as one plugin — the **`dna-sdlc-cli`** skill (in
[`.claude/`](.claude), distributed via
[`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)). But the
day-to-day DNA loop leans on a handful of **ecosystem skills** authored
elsewhere. This is a curated catalog of the ones we recommend.

We **reference** these — we do not vendor them. You install them from their
upstream repos so they stay current and their authors keep the credit.

## How the two install paths differ

Claude Code has two ways to add external skills, and which one applies depends
on whether the upstream repo ships a **plugin manifest**
(`.claude-plugin/plugin.json`):

- **Plugin repos** (have a manifest) → installable straight from a marketplace
  entry. We list these in
  [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json), so:

  ```
  /plugin marketplace add ruinosus/dna
  /plugin install superpowers@dna
  /plugin install impeccable@dna
  ```

- **Skill-only repos** (no manifest — just `SKILL.md` files) → cannot be a
  marketplace plugin entry as-is. Install them with the **find-skills** skill
  (below), or copy the `SKILL.md` into your own `.claude/skills/<name>/`.

## The catalog

| Skill | Upstream | Kind | Why we recommend it | Install |
|-------|----------|------|---------------------|---------|
| **superpowers** | [`obra/superpowers`](https://github.com/obra/superpowers) | Plugin | TDD, systematic debugging, brainstorming, writing/executing plans, code review, git worktrees — the engineering disciplines the DNA SDLC gates assume. | `/plugin install superpowers@dna` |
| **impeccable** | [`pbakaus/impeccable`](https://github.com/pbakaus/impeccable) | Plugin | Frontend design fluency (UX critique, hierarchy, typography, motion). Pairs with `dna sdlc gallery` when you author the HtmlArtifacts you later review. | `/plugin install impeccable@dna` |
| **find-skills** | [`vercel-labs/skills`](https://github.com/vercel-labs/skills) (`skills/find-skills/SKILL.md`) | Skill-only | Discovers + installs other agent skills on demand ("is there a skill that does X?"). The bootstrap for everything else here. | Copy `skills/find-skills/SKILL.md` into `.claude/skills/find-skills/`, or add via find-skills itself. |
| **task-observer** | [`rebelytics/one-skill-to-rule-them-all`](https://github.com/rebelytics/one-skill-to-rule-them-all) (root `SKILL.md`) | Skill-only | Watches a working session for reusable-skill opportunities and methodology worth preserving. Complements DNA's Kaizen loop. | Copy the root `SKILL.md` into `.claude/skills/task-observer/`. |

`find-skills` and `task-observer` are **catalog-only** here (not marketplace
plugin entries) precisely because their upstream repos don't ship a
`.claude-plugin/plugin.json` — listing them as installable plugins would be
dishonest. If those repos add a manifest, we'll promote them into
`marketplace.json`.

## Deliberately NOT bundled

- **claude-mem** — a persistent-memory tool that installs **hooks** requiring
  one-time harness wiring (a user action Claude Code's security model blocks an
  agent from doing itself). We keep the marketplace to zero-wiring,
  zero-surprise entries, so claude-mem is mentioned here as an **optional**
  add-on you may wire manually if you want cross-session memory — it is not a
  DNA dependency.
