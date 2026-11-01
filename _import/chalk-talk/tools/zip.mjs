// Packs the skill for claude.ai (Settings › Skills) and the API: dist/chalk-talk.zip, by the kit.
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { zip } from '../kit/tools/zip.mjs'

zip(resolve(dirname(fileURLToPath(import.meta.url)), '..'), 'chalk-talk')
