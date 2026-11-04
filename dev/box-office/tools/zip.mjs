// Packs the skill for claude.ai (Settings › Skills) and the API: dist/box-office.zip, by the kit.
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { zip } from 'chalk-talk/kit/tools/zip.mjs'

zip(resolve(dirname(fileURLToPath(import.meta.url)), '../../..'), 'box-office')
