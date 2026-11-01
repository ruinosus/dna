// The review as in a cloud sandbox (Linux, as root, Playwright's Chromium), by the kit: every example is drawn with the
// review run and comes out clean (exit 0), and the pitch presents and becomes a PowerPoint (exit 0). Needs Docker.
// Run after npm run assets.
import { readdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { linuxCheck } from 'chalk-talk/kit/tools/linux-check.mjs'

const skill = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/back-of-napkin')
const examples = join(skill, 'examples')
const ok = linuxCheck(skill, [
  ...readdirSync(examples).filter((f) => f.endsWith('.chalk')).map((f) => ({ file: join(examples, f), exit: 0 })),
  { file: join(examples, 'pitch-pharmacy-queue.chalk'), args: ['--pptx', '--no-review'], exit: 0 },
])
if (!ok) process.exit(1)
