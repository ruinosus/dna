# Contributing

## A release, every time the plugin changes

Claude Code and claude.ai update a marketplace plugin **only when its version changes**. A change to a skill with the
same version reaches nobody. So any change to what the plugin ships — `skills/`, `hooks/`, `kit/`, `types/`,
`.claude-plugin/` — goes out as a new version:

1. Raise the version (a fix: the patch) in `.claude-plugin/plugin.json`, `npm/dna/package.json` and every
   `skills/*/SKILL.md` (`metadata.version`).
2. Add its entry at the top of `CHANGELOG.md` (`## x.y.z — date`), and to the skill's own `dev/<skill>/CHANGELOG.md`.
3. Run `claude plugin validate . --strict` and `node dev/dna/tools/check.mjs` (and the skill's
   `npm run check -w dev/<skill>/tools`).

`dev/dna/tools/release.mjs` holds the rules and fails when one does not hold; `check.mjs` runs it, and so does CI on
every pull request (`.github/workflows/release-rules.yml`):

- what the plugin ships changed since `main` and the version is not above `main`'s;
- `plugin.json`, `npm/dna/package.json` and the CHANGELOG's latest version differ;
- another `.claude-plugin/plugin.json` is in the tree: the marketplace lists `dna` alone with `source: "./"`, and
  claude.ai skips a plugin that holds another one (sibling plugins live in their own repositories).

## After the merge

- Claude Code: `/plugin marketplace update dna`, then `/reload-plugins` (or a new session).
- claude.ai: sync the `dna` marketplace in the plugin settings.
- A page made before the fix (a `map.html`, an explainer) does not change by itself: make it again.
