// Packs workday-integration: dist/workday-integration.zip (the skill alone, for claude.ai's Settings › Skills and the
// API) and dist/workday-integration-plugin.zip (the whole plugin, for a manual install).
import { execFileSync } from 'node:child_process'
import { mkdirSync, rmSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = join(dirname(fileURLToPath(import.meta.url)), '../../..')
const plugin = join(repo, 'plugins/workday-integration')
mkdirSync(join(repo, 'dist'), { recursive: true })
for (const [name, cwd, what] of [['workday-integration.zip', join(plugin, 'skills'), ['workday-integration']], ['workday-integration-plugin.zip', plugin, ['.claude-plugin', '.mcp.json', 'skills', 'README.md']]]) {
  const out = join(repo, 'dist', name)
  rmSync(out, { force: true })
  execFileSync('zip', ['-qr', out, ...what, '-x', '*.DS_Store'], { cwd })
  console.log(`✓ ${out} (${Math.round(statSync(out).size / 1024)} KB)`)
}
