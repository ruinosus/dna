// Making the one HTML file a skill delivers: a value as JSON that can sit inside a <script> tag, and a page template
// with its {{KEYS}} filled. Part of the skills kit (visual-explainer/kit): copied into each skill by its tools/assets.mjs.

/** `value` as JSON, with "<" escaped so no text in it can end the <script> tag it goes in. */
export const inline = (value) => JSON.stringify(value).replace(/</g, '\\u003c')

/** `template` with each {{KEY}} replaced by its value (a function replacer, so `$` in a value is kept as it is). */
export function fill(template, values) {
  let page = template
  for (const [key, value] of Object.entries(values)) {
    if (!page.includes(`{{${key}}}`)) throw new Error(`The page has no {{${key}}} to fill.`)
    page = page.replace(`{{${key}}}`, () => value)
  }
  return page
}

const SAYS = {
  en: (page) => `An explainer drawn with DNA's visual-explainer: a Markdown preview with DNA (VS Code, Obsidian) draws the block below; \`${page}\` is the same explainer as a page that opens offline.`,
  pt: (page) => `Uma explicação desenhada pelo visual-explainer do DNA: um preview de Markdown com o DNA (VS Code, Obsidian) desenha o bloco abaixo; \`${page}\` é a mesma explicação como uma página que abre offline.`,
}

/** The explainer as Markdown: its title, a line on how to see it, and the recipe in a ```visual-explainer block. */
export function explainerMarkdown(scene, page, lang = 'en') {
  const recipe = JSON.stringify(scene, null, 2)
  const fence = '`'.repeat(Math.max(3, ...[...recipe.matchAll(/`+/g)].map((m) => m[0].length + 1)))
  return [`# ${scene.title || page}`, '', (SAYS[lang] ?? SAYS.en)(page), '', `${fence}visual-explainer`, recipe, fence, ''].join('\n')
}
