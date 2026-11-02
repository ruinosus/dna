// Copies into skills/cast-list/vendor/microsoft/ what the skill reuses from microsoft/skills-for-copilot-studio (MIT):
// the YAML schema (to tell a real kind from a made-up one) and its dependency-free reader, with the LICENSE and a NOTICE
// naming the commit. Run: node vendor-microsoft.mjs <commit>. Never edit the copied files by hand.
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const REPO = 'microsoft/skills-for-copilot-studio'
const FILES = ['reference/bot.schema.yaml-authoring.json', 'scripts/schema-lookup.bundle.js', 'LICENSE']
const commit = process.argv[2]
if (!/^[0-9a-f]{40}$/.test(commit ?? '')) {
  console.error('usage: node vendor-microsoft.mjs <full 40-character commit>')
  process.exit(2)
}
const out = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/cast-list/vendor/microsoft')
mkdirSync(out, { recursive: true })
for (const f of FILES) {
  const r = await fetch(`https://raw.githubusercontent.com/${REPO}/${commit}/${f}`)
  if (!r.ok) throw new Error(`${f}: HTTP ${r.status}`)
  const body = Buffer.from(await r.arrayBuffer())
  mkdirSync(dirname(join(out, f)), { recursive: true })
  writeFileSync(join(out, f), body) // the same paths as in the repository: the reader finds the schema at ../reference/
  console.log(`✓ ${f} (${(body.length / 1024).toFixed(0)} KB)`)
}
writeFileSync(join(out, 'NOTICE'), `These files are copied, unchanged, from ${REPO}
(https://github.com/${REPO}), commit ${commit}, under the MIT license in LICENSE
(Copyright Microsoft Corporation).

- reference/bot.schema.yaml-authoring.json
- scripts/schema-lookup.bundle.js  (CommonJS: package.json here says so)

cast-list reads the schema to tell a real Copilot Studio kind from one it does not know. They are updated by
dev/cast-list/tools/vendor-microsoft.mjs, never by hand.
`)
// the reader is CommonJS, and the house-lights repository is "type": "module"
writeFileSync(join(out, 'package.json'), '{ "type": "commonjs" }\n')
console.log(`✓ NOTICE (${commit.slice(0, 7)})`)
