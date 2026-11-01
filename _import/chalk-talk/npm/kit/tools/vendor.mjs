// A skill carries the kit's runtime files itself (claude.ai installs no packages): `vendor` copies them into the skill
// and says which kit they came from. Part of the skills kit (chalk-talk/kit), used by a skill's tools/assets.mjs.
import { copyFileSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const kit = join(dirname(fileURLToPath(import.meta.url)), '..')

/** The kit's version: the chalk-talk package it ships in (or the repository's plugin when used from source). */
export function kitVersion() {
  for (const p of [join(kit, '../package.json'), join(kit, '../.claude-plugin/plugin.json')]) {
    try {
      const { name, version } = JSON.parse(readFileSync(p, 'utf8'))
      if (version && (name === 'chalk-talk' || p.endsWith('plugin.json'))) return version
    } catch {}
  }
  return 'unknown'
}

/** Copies the kit's `files` (e.g. ['browser.mjs', 'page.mjs']) into `into`; returns the line for assets/VERSION. */
export function vendor(into, files) {
  for (const f of files) copyFileSync(join(kit, f), join(into, f))
  return `kit chalk-talk ${kitVersion()} (${files.join(', ')})`
}
