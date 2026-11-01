// Packs a skill for claude.ai (Settings › Skills) and the API: <root>/dist/<name>.zip with the skills/<name>/ folder
// inside. Part of the skills kit (chalk-talk/kit).
import { execFileSync } from 'node:child_process'
import { mkdirSync, rmSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'

export function zip(root, name) {
  const out = join(root, 'dist', `${name}.zip`)
  mkdirSync(dirname(out), { recursive: true })
  rmSync(out, { force: true })
  execFileSync('zip', ['-qr', out, name, '-x', '*.DS_Store'], { cwd: join(root, 'skills') })
  console.log(`✓ ${out} (${Math.round(statSync(out).size / 1024)} KB)`)
  return out
}
