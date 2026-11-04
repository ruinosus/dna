// The lesson's review as in a cloud sandbox (Linux, as root, Playwright's Chromium), by the kit: every example makes
// its map, workbook and lesson with the review run (exit 0). Needs Docker. Run after npm run assets.
import { readdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { linuxCheck } from '@ruinosus/visual-explainer/kit/tools/linux-check.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const skill = resolve(here, '../../../skills/service-blueprint')
const examples = join(skill, 'examples')
const ok = linuxCheck(skill, readdirSync(examples).filter((f) => f.endsWith('.blueprint.yaml')).map((f) => ({ file: join(examples, f), args: ['--lesson'], exit: 0 })))
if (!ok) process.exit(1)
