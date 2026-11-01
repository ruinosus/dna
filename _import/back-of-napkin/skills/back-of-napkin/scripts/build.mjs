#!/usr/bin/env node
// Checks a back-of-napkin recipe and builds one HTML file that draws itself — with chalk-talk's engine
// (engine-build.mjs). This file only checks the purpose first: a drawing here says what it is for (`kind pitch`, arch,
// decision, data, timeline or story — a lesson is chalk-talk's), then hands over to the engine, which checks the
// recipe, draws it, reviews it and says what the purpose usually misses.
//
//   node build.mjs <id>.chalk [out.html] [--no-present] [--snapshots [folder]] [--no-review] [--svg]
//                 [--pptx [static|steps|video|all]] [--settings a,b] [--slides <folder> [--slides-steps]]
//
// A drawing here is made to be shown: the page opens presenting (the engine's --present) unless --no-present (a
// document, a note).
//
// Exit codes: 0 drawn and checked; 1 the recipe breaks the format (or has no purpose); 2 bad arguments; 3 drawn, with
// something to fix (the review, or what the purpose misses); 4 --svg or --snapshots with no browser.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const KINDS = ['pitch', 'arch', 'decision', 'data', 'timeline', 'story']
const recipes = process.argv.slice(2).filter((a) => /\.(chalk|json|md|mmd)$/.test(a))
for (const file of recipes) {
  if (file.endsWith('.mmd')) continue // the engine says Mermaid is not drawn here
  let text
  try {
    text = readFileSync(resolve(file), 'utf8')
  } catch {
    continue // the engine says the file is not there
  }
  const kind = file.endsWith('.json') ? (() => { try { return JSON.parse(text).kind } catch { return undefined } })() : text.match(/^kind\s+(\S+)/m)?.[1]
  const fail = (msg) => {
    console.error(`✗ purpose: ${msg}\n  write it like:\n    kind pitch`)
    process.exit(1)
  }
  if (kind === undefined || kind === 'lesson') {
    fail(kind === 'lesson'
      ? 'a lesson is chalk-talk\'s (to teach); back-of-napkin draws to present, convince, decide, document or tell what happened.'
      : `say what the drawing is for, on a line of its own: kind ${KINDS.join('|')}.`)
  }
  if (!KINDS.includes(kind)) fail(`kind ${kind} is not one of ${KINDS.join(', ')}.`)
}
const quiet = process.argv.indexOf('--no-present')
if (quiet >= 0) process.argv.splice(quiet, 1)
else if (!process.argv.includes('--present')) process.argv.push('--present')
await import('./engine-build.mjs')
