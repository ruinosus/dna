// The npm package house-lights carries each skill's build as the skill has it (scripts, assets, references, examples),
// without SKILL.md: npm/house-lights/skills/<skill>/. Run by npm before it packs (prepack), and by npm run zip.
import { cpSync, copyFileSync, readdirSync, rmSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const out = join(repo, 'npm/house-lights')
rmSync(join(out, 'skills'), { recursive: true, force: true })
const skills = readdirSync(join(repo, 'skills')).filter((s) => !s.startsWith('.'))
for (const s of skills) {
  cpSync(join(repo, 'skills', s), join(out, 'skills', s), { recursive: true, filter: (f) => !f.endsWith('/SKILL.md') && !f.endsWith('.DS_Store') })
}
copyFileSync(join(repo, 'LICENSE'), join(out, 'LICENSE'))
console.log(`✓ npm/house-lights: ${skills.join(', ')}`)
