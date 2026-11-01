// The pages and pictures of a skill's GitHub Pages gallery: each example's page in <docs>/<pages>/ and a PNG of it in
// <docs>/thumbs/, in a headless browser (the kit's browser.mjs, over the DevTools pipe). Either the page draws its own
// picture (`mode`, the #mode that answers with it, and `pick`, which takes the PNG data: URL from the answer) or the
// browser takes one (`shot: { width, height }`, after `mode` if any). The gallery's index stays the skill's own. Part
// of the skills kit (chalk-talk/kit).
import { mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { browser, runPages } from '../browser.mjs'

/** `items`: [{ name, html }]. Writes every page, then every picture in one opening of the browser. */
export async function gallery(docs, items, { pages = 'lessons', mode, pick = (r) => r.png, shot, timeout = 60 }) {
  if (!browser()) throw new Error('No Chrome, Chromium or Edge: the pictures need one (set CHROME_PATH).')
  for (const dir of [pages, 'thumbs']) {
    rmSync(join(docs, dir), { recursive: true, force: true })
    mkdirSync(join(docs, dir), { recursive: true })
  }
  const files = items.map(({ name, html }) => {
    const file = join(docs, pages, `${name}.html`)
    writeFileSync(file, html)
    return file
  })
  const { results } = await runPages(files.map((file) => ({ file, mode, shot })), { timeout })
  items.forEach(({ name }, k) => {
    const r = results[k]
    const png = r && !r.error ? pick(r) : undefined
    if (!png) throw new Error(`${name}: the picture failed (${r?.error ?? 'no picture in the answer'})`)
    writeFileSync(join(docs, 'thumbs', `${name}.png`), Buffer.from(png.replace(/^data:image\/png;base64,/, ''), 'base64'))
    console.log(`✓ ${name}`)
  })
  return files
}
