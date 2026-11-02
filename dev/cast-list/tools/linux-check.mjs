// The lesson's review as in a cloud sandbox (Linux, as root, Playwright's Chromium), by the kit: the example agents
// make the map, the workbook and the lesson with the review run (exit 0). Needs Docker. Run after npm run assets.
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { linuxCheck } from 'chalk-talk/kit/tools/linux-check.mjs'

const skill = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/cast-list')
if (!linuxCheck(skill, [{ file: join(skill, 'examples/agents'), args: ['--lesson'], exit: 0 }])) process.exit(1)
