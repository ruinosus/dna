// The review as in a cloud sandbox (Linux, as root, Playwright's Chromium), by the kit: the coffee chain with the
// balloon on the café is found (exit 3), the clean one passes with its snapshots (exit 0), and the coin jar becomes a
// PowerPoint with a video per chapter — the cloud's Chromium records MP4 (exit 0). Needs Docker. Run after npm run assets.
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { linuxCheck } from '../kit/tools/linux-check.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const ok = linuxCheck(resolve(here, '../skills/chalk-talk'), [
  { file: join(here, 'fixtures/coffee-chain-left.chalk'), exit: 3 },
  { file: join(here, 'fixtures/coffee-chain.chalk'), args: ['--snapshots'], exit: 0 },
  { file: join(here, '../docs/examples/coin-jar.chalk'), args: ['--pptx', 'video', '--no-review'], exit: 0 },
])
if (!ok) process.exit(1)
