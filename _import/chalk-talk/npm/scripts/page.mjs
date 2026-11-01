// Making the one HTML file a skill delivers: a value as JSON that can sit inside a <script> tag, and a page template
// with its {{KEYS}} filled. Part of the skills kit (chalk-talk/kit): copied into each skill by its tools/assets.mjs.

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
