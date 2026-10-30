// Packs the skill for claude.ai (Settings › Skills) and the API: dist/dress-rehearsal.zip with the dress-rehearsal/ folder inside.
import { execFileSync } from 'node:child_process'
import { mkdirSync, rmSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const out = join(root, 'dist/dress-rehearsal.zip')
mkdirSync(dirname(out), { recursive: true })
rmSync(out, { force: true })
execFileSync('zip', ['-qr', out, 'dress-rehearsal', '-x', '*.DS_Store'], { cwd: join(root, 'skills') })
console.log(`✓ ${out} (${Math.round(statSync(out).size / 1024)} KB)`)
