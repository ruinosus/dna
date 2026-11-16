## What and why

<!-- what changed, and what someone saw that made it necessary -->

## Release checklist

- [ ] Changed anything the plugin ships (`skills/`, `hooks/`, `kit/`, `types/`, `.claude-plugin/`)? The version goes up in `.claude-plugin/plugin.json`, `npm/dna/package.json` and every `skills/*/SKILL.md` — otherwise nobody gets the change
- [ ] `CHANGELOG.md`: an entry for that version (and the skill's own `dev/<skill>/CHANGELOG.md`)
- [ ] `claude plugin validate . --strict`
- [ ] `node dev/dna/tools/check.mjs` (and the skill's own `npm run check -w dev/<skill>/tools`)

After the merge, to get it: `/plugin marketplace update dna`, then `/reload-plugins` in Claude Code; sync the `dna` marketplace in claude.ai's plugin settings. A page made before (a `map.html`…) is made again.
