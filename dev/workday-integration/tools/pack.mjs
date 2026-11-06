// The npm package workday-integration carries the skill's two scripts as the plugin has them (the CLI and the MCP
// server, one file each) and the synthetic examples: npm/workday-integration/. Run by npm before it packs (prepack).
import { cpSync, copyFileSync, existsSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const skill = join(repo, 'plugins/workday-integration/skills/workday-integration')
const out = join(repo, 'npm/workday-integration')
for (const f of ['scripts/wws.mjs', 'scripts/mcp.mjs']) if (!existsSync(join(skill, f))) throw new Error(`${f} is missing: run node dev/workday-integration/tools/assets.mjs`)
for (const d of ['scripts', 'examples']) {
  rmSync(join(out, d), { recursive: true, force: true })
  cpSync(join(skill, d), join(out, d), { recursive: true, filter: (f) => !f.endsWith('.DS_Store') })
}
copyFileSync(join(repo, 'LICENSE'), join(out, 'LICENSE'))
console.log('✓ npm/workday-integration: scripts/wws.mjs, scripts/mcp.mjs, examples/')
