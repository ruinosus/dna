// The skeleton every skill's tools/check.mjs shares: what passed and what did not, running the skill's own build,
// SKILL.md's frontmatter, one version everywhere, and a page probed in a headless browser. Part of the skills kit
// (chalk-talk/kit).
import { spawnSync } from 'node:child_process'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { runPage } from '../browser.mjs'

/** `expect(ok, what, detail)` prints ✓/✗; `done(name)` ends the process with 1 when anything failed. */
export function checker() {
  let failed = 0
  return {
    expect(ok, what, detail = '') {
      console.log(`${ok ? '✓' : '✗'} ${what}${!ok && detail ? `\n${detail}` : ''}`)
      if (!ok) failed++
      return ok
    },
    done(name) {
      if (failed) {
        console.error(`✗ ${failed} check${failed === 1 ? '' : 's'} failed`)
        process.exit(1)
      }
      console.log(`✓ ${name} checks ok`)
    },
  }
}

/** Runs a Node script (the skill's build.mjs) with `args`; the result of spawnSync, as text. */
export const runNode = (script, args = [], opts = {}) => spawnSync(process.execPath, [script, ...args], { encoding: 'utf8', ...opts })

/** SKILL.md's frontmatter as { name, description, version, … } (the version from metadata.version). */
export function skillFrontmatter(skillMd) {
  const head = readFileSync(skillMd, 'utf8').match(/^---\n([\s\S]*?)\n---/)?.[1] ?? ''
  const field = (k) => head.match(new RegExp(`^${k}: (.*)$`, 'm'))?.[1] ?? ''
  return { name: field('name'), description: field('description'), version: head.match(/version: "([^"]+)"/)?.[1] ?? '', lines: readFileSync(skillMd, 'utf8').split('\n').length }
}

/** The usual checks of SKILL.md: its name is the folder's, a description of at most 1024 characters, under 500 lines. */
export function checkSkillMd(expect, skillMd, name) {
  const f = skillFrontmatter(skillMd)
  expect(f.name === name, 'SKILL.md name is the folder name')
  expect(f.description.length > 0 && f.description.length <= 1024, `SKILL.md description has ${f.description.length} of 1024 characters`)
  expect(f.lines < 500, 'SKILL.md under 500 lines')
  return f
}

/** One version everywhere: { where: version } all equal. */
export function checkOneVersion(expect, versions) {
  const all = Object.values(versions)
  expect(all.every((v) => v && v === all[0]), `one version everywhere: ${Object.entries(versions).map(([k, v]) => `${k} ${v}`).join(', ')}`)
}

/** Opens `html` (with a script that writes <pre id="chalk-probe">) in a headless browser; what it wrote, parsed — null
 * without a browser. */
export async function pageProbe(html, { timeout = 60 } = {}) {
  const file = join(mkdtempSync(join(tmpdir(), 'skill-probe-')), 'probe.html')
  writeFileSync(file, html)
  return runPage(file, 'probe', '', { timeout })
}

/** The script a probed page ends with: `body` is async code that fills `out`; it is written for pageProbe to read. */
export const probeScript = (body) => `<script type="module">
const out = {}
try { ${body} } catch (e) { out.failed = String(e && e.message || e) }
const pre = document.createElement('pre'); pre.id = 'chalk-probe'; pre.textContent = encodeURIComponent(JSON.stringify(out)); document.body.append(pre)
</script>`
