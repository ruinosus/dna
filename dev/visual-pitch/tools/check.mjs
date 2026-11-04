// Checks the skill as someone installing it would get it: SKILL.md's frontmatter and one version everywhere; every
// example drawn clean (no review problem, nothing the purpose misses); one recipe per purpose warning (exit 3); a
// lesson, a drawing with no purpose, a quiz and a Mermaid file refused (exit 1); and the cheat sheet in SKILL.md, word
// for word. Run after npm run assets.
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { checker, checkOneVersion, checkSkillMd, runNode } from '@ruinosus/visual-explainer/kit/tools/checks.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const repo = resolve(here, '../../..') // the dna repository
const skill = join(repo, 'skills/visual-pitch')
const build = join(skill, 'scripts/build.mjs')
const dir = mkdtempSync(join(tmpdir(), 'visual-pitch-check-'))
const { expect, done } = checker()
const run = (recipe, flags = []) => runNode(build, [recipe, ...flags])
const recipe = (name, text) => {
  const file = join(dir, name)
  writeFileSync(file, text)
  return file
}

const front = checkSkillMd(expect, join(skill, 'SKILL.md'), 'visual-pitch')
checkOneVersion(expect, {
  plugin: JSON.parse(readFileSync(join(repo, '.claude-plugin/plugin.json'), 'utf8')).version,
  npm: JSON.parse(readFileSync(join(repo, 'npm/dna/package.json'), 'utf8')).version,
  'SKILL.md': front.version,
})

// One example per purpose, each drawn clean: exit 0, no warning.
const KINDS = ['pitch', 'arch', 'decision', 'data', 'timeline', 'story']
const examples = readdirSync(join(skill, 'examples')).filter((f) => f.endsWith('.chalk')).sort()
const kinds = examples.map((f) => readFileSync(join(skill, 'examples', f), 'utf8').match(/^kind\s+(\S+)/m)?.[1]).sort()
expect(kinds.join() === [...KINDS].sort().join(), `one example per purpose (${kinds.join(', ')})`)
for (const f of examples) {
  const r = run(join(skill, 'examples', f), ['--out', join(dir, f.replace('.chalk', '.html'))])
  expect(r.status === 0 && !/^! /m.test(r.stdout), `${f}: drawn clean`, r.stdout + r.stderr)
}
for (const k of KINDS) expect(readFileSync(join(skill, 'arcs', `${k}.md`), 'utf8').length > 200, `arcs/${k}.md`)

// What each purpose usually misses: one recipe each, drawn (exit 3) with its line.
const plain = (kind) => `kind ${kind}\ntitle X\n# Um\n> Uma frase.\ntext "algo" at 40,64 size=36\n`
for (const [kind, says] of [
  ['pitch', 'does not end with an ask'],
  ['arch', 'no failure drawn'],
  ['decision', 'does not say which option wins'],
  ['data', 'where do these numbers come from'],
  ['timeline', 'has no line'],
]) {
  const r = run(recipe(`warn-${kind}.chalk`, plain(kind)), ['--no-review'])
  expect(r.status === 3 && new RegExp(`^! ${kind}\\s.*${says}`, 'm').test(r.stdout), `kind ${kind}: what it misses is told (exit 3)`, r.stdout + r.stderr)
}
const story = run(recipe('story.chalk', plain('story')), ['--no-review'])
expect(story.status === 0, 'a story has nothing to miss', story.stdout + story.stderr)
expect(story.stdout.includes('story.html'), 'a recipe with no id is named after its file (story.chalk → story.html)', story.stdout)
for (const f of ['text.md', 'recipe.md']) expect(readFileSync(join(skill, 'references', f), 'utf8').length > 1000, `references/${f}`)

// Refused, with a line saying how to write it.
const refused = [
  ['a lesson', recipe('lesson.chalk', plain('lesson')), /✗ purpose: a lesson is visual-explainer's/],
  ['a drawing with no purpose', recipe('none.chalk', 'title X\ntext "algo" at 40,64\n'), /✗ purpose: say what the drawing is for[\s\S]*kind pitch/],
  ['an unknown purpose', recipe('odd.chalk', plain('memo')), /✗ purpose: kind memo is not one of/],
  ['a quiz outside a lesson', recipe('quiz.chalk', `${plain('pitch')}quiz "Qual?" options "a","b" answer 1\n`), /quiz/],
  ['a Mermaid file', recipe('flow.mmd', 'flowchart LR\n  a --> b\n'), /a Mermaid diagram is not drawn by visual-pitch/],
]
for (const [what, file, says] of refused) {
  const r = run(file, ['--no-review'])
  expect(r.status === 1 && says.test(r.stdout + r.stderr), `${what} is refused`, r.stdout + r.stderr)
}

// 0.2.0: the pitch presents (0.2.1: with no flag), and goes to PowerPoint with a slide per chapter and the narration as
// notes; --no-present makes a page that does not.
{
  const { browser } = await import('../../../skills/visual-pitch/scripts/browser.mjs')
  if (!browser()) console.log('• no Chrome here: presenting and the PowerPoint were not checked')
  else {
    const pitch = recipe('pitch.chalk', readFileSync(join(skill, 'examples/pitch-hr-self-service.chalk'), 'utf8'))
    const r = run(pitch, ['--pptx', '--no-review'])
    const id = readFileSync(pitch, 'utf8').match(/^id\s+(\S+)/m)?.[1] ?? 'pitch'
    const html = readFileSync(join(dir, `${id}.html`), 'utf8')
    const { inspectPptx } = await import(pathToFileURL(join(skill, 'scripts/pptx.mjs')).href)
    const got = r.status === 0 ? await inspectPptx(readFileSync(join(dir, `${id}.pptx`))) : {}
    const chapters = (readFileSync(pitch, 'utf8').match(/^# /gm) ?? []).length
    const q = run(recipe('note.chalk', readFileSync(pitch, 'utf8')), ['--no-present', '--no-review'])
    const noteHtml = readFileSync(join(dir, `${id}.html`), 'utf8')
    expect(q.status === 0 && !noteHtml.includes('data-present="1"'), '--no-present makes a page that does not open presenting', q.stdout + q.stderr)
    expect(r.status === 0 && html.includes('<body data-present="1">') && got.slides === chapters && got.notes === chapters, `the pitch presents and becomes a ${chapters}-slide PowerPoint with notes`, r.stdout + r.stderr + JSON.stringify(got))
  }
}

// The cheat sheet: every line meant for SKILL.md is in it, word for word (a quiz is a lesson's, so it is left out).
{
  const { SYNTAX } = await import('../../../skills/visual-pitch/scripts/syntax.mjs')
  const text = readFileSync(join(skill, 'SKILL.md'), 'utf8')
  const absent = Object.entries(SYNTAX).filter(([k, { line, sheet }]) => sheet !== false && !['quiz', 'learning'].includes(k) && !text.includes(line)).map(([k]) => k)
  expect(!absent.length, `SKILL.md's cheat sheet has every example meant for it${absent.length ? ` — missing ${absent.join(', ')}` : ''}`)
}

rmSync(dir, { recursive: true, force: true })
done('visual-pitch')
