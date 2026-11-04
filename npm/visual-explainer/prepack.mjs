// Before npm packs visual-explainer: every built file it ships is there. They are made by npm run assets at the repository's
// root (they need the drawing engine) and are not kept in git.
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const built = ['player.js', 'embed.js', 'embed-mermaid.js', 'mount.js', 'mount.global.js', 'markdown.js', 'scripts/build.mjs', 'scripts/mermaid.mjs', 'references', 'assets/player.html', 'assets/lottie', 'assets/lottie_light.js', 'LICENSE']
const missing = built.filter((f) => !existsSync(join(here, f)))
if (missing.length) {
  console.error(`✗ npm/visual-explainer is missing ${missing.join(', ')}: run npm run assets at the repository's root first`)
  process.exit(1)
}
console.log(`✓ npm/visual-explainer: the ${built.length} built files are there`)
