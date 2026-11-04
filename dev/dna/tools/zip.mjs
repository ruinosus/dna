// The whole plugin for a manual install: dist/dna.zip with .claude-plugin/, skills/, README.md and LICENSE.
// (Each skill alone, for claude.ai, is dist/<skill>.zip, made by that skill's zip.)
import { execFileSync } from 'node:child_process'
import { mkdirSync, rmSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const out = join(repo, 'dist/dna.zip')
mkdirSync(dirname(out), { recursive: true })
rmSync(out, { force: true })
execFileSync('zip', ['-qr', out, '.claude-plugin', 'skills', 'README.md', 'LICENSE', '-x', '*.DS_Store'], { cwd: repo })
console.log(`✓ ${out} (${Math.round(statSync(out).size / 1024)} KB)`)
