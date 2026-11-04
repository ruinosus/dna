// The mod's types: checked against the contract Claude Code lays in .claude-plugin/types/ the first time it loads the
// mod from this folder (claude --plugin-dir .). Without it there is nothing to check against: said, and skipped.
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
if (!existsSync(resolve(here, '../../../.claude-plugin/types'))) {
  console.log('• the mod is not typechecked: open the repository once with claude --plugin-dir . to lay .claude-plugin/types/')
  process.exit(0)
}
const r = spawnSync('npx', ['tsc', '-p', join(here, 'tsconfig.json')], { stdio: 'inherit' })
process.exit(r.status ?? 1)
