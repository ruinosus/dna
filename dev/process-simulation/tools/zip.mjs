// Packs the skill for claude.ai (Settings › Skills) and the API: dist/process-simulation.zip, by the kit.
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { zip } from '@ruinosus/visual-explainer/kit/tools/zip.mjs'

zip(resolve(dirname(fileURLToPath(import.meta.url)), '../../..'), 'process-simulation')
