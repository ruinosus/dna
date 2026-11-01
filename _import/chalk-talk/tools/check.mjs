// Checks the skill as someone installing it would get it: SKILL.md's frontmatter, every example built by
// scripts/build.mjs, a recipe that breaks the contract (exit 1) and one with a line across a text (exit 3).
import { checker, checkOneVersion, checkSkillMd, runNode } from '../kit/tools/checks.mjs'
import { mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const skill = resolve(here, '../skills/chalk-talk')
const build = join(skill, 'scripts/build.mjs')
const dir = mkdtempSync(join(tmpdir(), 'chalk-talk-check-'))
const { expect, done } = checker()
const run = (recipe, flags = []) => runNode(build, [recipe, ...flags])

const front = checkSkillMd(expect, join(skill, 'SKILL.md'), 'chalk-talk')
checkOneVersion(expect, {
  plugin: JSON.parse(readFileSync(join(skill, '../../.claude-plugin/plugin.json'), 'utf8')).version,
  npm: JSON.parse(readFileSync(join(skill, '../../npm/package.json'), 'utf8')).version,
  'SKILL.md': front.version,
  'SKILL.md CDN': readFileSync(join(skill, 'SKILL.md'), 'utf8').match(/chalk-talk@([\d.]+)\/player\.js/)?.[1],
})

// Onda C: the kit's runtime in the skill is the kit's, byte for byte; the page helpers escape and fill.
{
  const kit = join(skill, '../../kit')
  for (const f of ['browser.mjs', 'page.mjs']) expect(readFileSync(join(kit, f), 'utf8') === readFileSync(join(skill, 'scripts', f), 'utf8'), `scripts/${f} is the kit's`)
  const { fill, inline } = await import('../kit/page.mjs')
  expect(inline({ t: '</script>' }) === '{"t":"\\u003c/script>"}' && fill('a {{X}} b', { X: '$&' }) === 'a $& b', 'page.mjs: inline escapes <, fill keeps $ as it is')
  let threw = false
  try { fill('a', { X: '1' }) } catch { threw = true }
  expect(threw, 'page.mjs: a key the page does not have is an error')
  // the browser takes a picture of any page (a map, a still lesson): shot: { width, height } answers with a PNG
  const plainPage = join(dir, 'plain.html')
  writeFileSync(plainPage, '<!doctype html><meta charset="utf-8"><body style="margin:0;background:#2E8F62"><h1>shot</h1>')
  const { runPages } = await import('../kit/browser.mjs')
  const { results: shots } = await runPages([{ file: plainPage, shot: { width: 320, height: 200 } }])
  const png = shots?.[0]?.png ? Buffer.from(shots[0].png.split(',')[1], 'base64') : Buffer.alloc(0)
  if (shots) expect(png.length > 24 && png.readUInt32BE(16) === 320 && png.readUInt32BE(20) === 200, `browser.mjs: a picture of a page (${png.length > 24 ? `${png.readUInt32BE(16)}×${png.readUInt32BE(20)}` : JSON.stringify(shots?.[0])})`)
  const f = runNode(join(here, 'node_modules/tsx/dist/cli.mjs'), [join(kit, 'format.check.ts')], { env: { ...process.env, NODE_PATH: join(here, 'node_modules') } })
  expect(f.status === 0, 'format.ts: the line of a path, a syntax error, another format', f.stdout + f.stderr)
}

const examples = join(skill, 'references/examples')
for (const f of readdirSync(examples)) {
  const r = run(join(examples, f), [join(dir, f.replace('.json', '.html'))])
  expect(r.status === 0, `${f}: ${r.stdout.trim().split('\n').filter((l) => l.startsWith('✓ review') || l.startsWith('•') || l.startsWith('!')).join(' / ') || r.stderr.trim()}`)
}

// The text and Mermaid examples of the gallery build too.
const docs = join(skill, '../../docs/examples')
for (const f of readdirSync(docs).filter((f) => /\.(chalk|mmd)$/.test(f))) {
  const r = run(join(docs, f), [join(dir, f.replace(/\.[^.]+$/, '.html'))])
  expect(r.status === 0, `${f}: ${r.stdout.trim().split('\n').filter((l) => /review/.test(l)).join(' / ') || r.stderr.trim()}`)
}
// --svg: an SVG that draws itself with CSS and no script, with only the fonts it uses; a Markdown file gives one per block.
const svgOut = join(dir, 'coin.svg')
const sv = run(join(docs, 'coin-jar.chalk'), [svgOut, '--svg', '--no-review'])
if (sv.status === 4) expect(true, 'no browser here: the --svg check is skipped')
else {
  const svg = sv.status === 0 ? readFileSync(svgOut, 'utf8') : ''
  const timed = (svg.match(/animation:/g) ?? []).length
  expect(sv.status === 0 && !/<script/i.test(svg) && /@keyframes ct-draw/.test(svg) && /prefers-reduced-motion/.test(svg) && timed > 50 && /font-family:\s*'Caveat'/.test(svg),
    `--svg draws itself with no script (${timed} timed elements, ${Math.round(svg.length / 1024)} KB)${sv.status ? `: ${sv.stderr.trim()}` : ''}`)
  const page = join(dir, 'two.md')
  writeFileSync(page, '```chalk-talk\ntitle Um\nid um\ntext "um" at 40,60\n```\n\n```mermaid\nflowchart LR\n  %% title Dois\n  A --> B\n```\n')
  const two = run(page, ['--svg', '--no-review'])
  const names = readdirSync(dir).filter((f) => f.endsWith('.svg')).sort().join(', ')
  expect(two.status === 0 && names === 'coin.svg, dois.svg, um.svg', `a Markdown file gives one SVG per block (${names}${two.status ? `: ${two.stderr.trim()}` : ''})`)
}

// chalk-talk/embed: two lessons on one page (as two blocks in a note) — each moves on its own, the styles go in once,
// and a broken text says its line.
{
  const { runPage } = await import('../kit/browser.mjs')
  const embed = pathToFileURL(join(skill, '../../npm/embed.js')).href
  const coin = readFileSync(join(docs, 'coin-jar.chalk'), 'utf8')
  const page = join(dir, 'embed.html')
  writeFileSync(page, `<!doctype html><meta charset="utf-8"><body><div id="a"></div><div id="b"></div><script type="module">
import { mountLesson, readRecipe, ChalkTextError } from ${JSON.stringify(embed)}
const out = {}
try {
  const scene = readRecipe(${JSON.stringify(coin)})
  const [a, b] = [document.getElementById('a'), document.getElementById('b')]
  await mountLesson(a, scene, { compact: true, lang: 'pt' })
  const mb = await mountLesson(b, readRecipe(JSON.stringify(scene)), { compact: true, lang: 'en', onExpand: () => {} })
  a.querySelector('[data-part="next"]').click()
  await new Promise((r) => setTimeout(r, 4000))
  const on = (root) => [...root.querySelectorAll('.chapters button')].findIndex((x) => x.classList.contains('is-on'))
  out.chapters = [on(a), on(b)]
  out.drawn = [a, b].map((r) => r.querySelector('svg').querySelectorAll('path').length)
  out.styles = document.querySelectorAll('#chalk-talk-styles').length
  out.ids = [...document.body.querySelectorAll('[id]')].map((e) => e.id).filter((id) => !/^(a|b)$/.test(id) && !id.startsWith('dw'))
  out.expand = [a, b].map((r) => !r.querySelector('[data-part="expand"]').hidden)
  mb.destroy()
  out.destroyed = b.childElementCount
  try { readRecipe('title X\\nperson ana at 1') } catch (e) { out.error = e instanceof ChalkTextError ? e.line : e.message }
} catch (e) { out.failed = e.message }
const pre = document.createElement('pre'); pre.id = 'chalk-embed'; pre.textContent = encodeURIComponent(JSON.stringify(out)); document.body.append(pre)
</script>`)
  const r = await runPage(page, 'embed')
  if (!r) expect(true, 'no browser here: the embed check is skipped')
  else {
    const ok = !r.failed && r.chapters?.[0] === 1 && r.chapters?.[1] === 0 && r.drawn.every((n) => n > 5) && r.styles === 1 && !r.ids.length && r.expand[0] === false && r.expand[1] === true && r.destroyed === 0 && r.error === 2
    expect(ok, `chalk-talk/embed: two lessons on a page, each on its own (${JSON.stringify(r)})`)
  }
}

// chalk-talk/markdown: the two fences become blocks (escaped), any other fence is left alone — markdown-it and remark.
{
  const { blockHtml, fenceKind, markdownItChalkTalk, remarkChalkTalk } = await import(pathToFileURL(join(skill, '../../npm/markdown.js')).href)
  const html = blockHtml('text', 'text "<b>" at 1,1')
  const md = { renderer: { rules: { fence: () => 'PLAIN' } } }
  markdownItChalkTalk(md)
  const fence = (info) => md.renderer.rules.fence([{ info, content: 'A --> B' }], 0, {}, {}, {})
  const tree = { type: 'root', children: [{ type: 'code', lang: 'chalk-mermaid', value: 'flowchart LR\n A --> B' }, { type: 'code', lang: 'js', value: 'x' }] }
  remarkChalkTalk()(tree)
  const ok = fenceKind('chalk-talk') === 'text' && fenceKind('chalk-mermaid {x}') === 'mermaid' && fenceKind('mermaid') === undefined &&
    html.includes('data-chalk-talk="text"') && html.includes('&lt;b&gt;') && !html.includes('<b>') &&
    fence('chalk-mermaid').includes('data-chalk-talk="mermaid"') && fence('js') === 'PLAIN' &&
    tree.children[0].data?.hProperties?.dataChalkTalk === 'mermaid' && tree.children[0].data?.hChildren?.[0]?.children?.[0]?.value === 'flowchart LR\n A --> B' && !tree.children[1].data
  expect(ok, 'chalk-talk/markdown: the two fences become blocks, the others stay (markdown-it, remark)')
}

// chalk-talk/mount: blocks on the page become lessons, a block added later too, a broken one says its line.
{
  const { runPage } = await import('../kit/browser.mjs')
  const { blockHtml } = await import(pathToFileURL(join(skill, '../../npm/markdown.js')).href)
  const page = join(dir, 'mount.html')
  const coin = readFileSync(join(docs, 'coin-jar.chalk'), 'utf8')
  const coffee = readFileSync(join(docs, 'coffee-order.mmd'), 'utf8')
  writeFileSync(page, `<!doctype html><meta charset="utf-8"><body>${blockHtml('text', coin)}${blockHtml('mermaid', coffee)}${blockHtml('text', 'title X\nperson ana at 1')}
<script src="${pathToFileURL(join(skill, '../../npm/mount.global.js')).href}"></script>
<script>
setTimeout(() => document.body.insertAdjacentHTML('beforeend', ${JSON.stringify(blockHtml('text', 'title Later\ntext "later" at 40,60'))}), 1500)
setTimeout(() => {
  const blocks = [...document.querySelectorAll('[data-chalk-talk]')]
  const out = blocks.map((b) => b.querySelector('.chalk-talk-error') ? 'error:' + b.querySelector('.chalk-talk-error').textContent.match(/line \\d+/)?.[0] : (b.querySelector('.chalk-talk svg')?.querySelectorAll('path, text').length ?? 0) > 0 && b.querySelector('.chalk-talk-source').hidden ? 'lesson' : 'nothing')
  const pre = document.createElement('pre'); pre.id = 'chalk-mount'; pre.textContent = encodeURIComponent(JSON.stringify({ out, styles: document.querySelectorAll('#chalk-talk-styles').length })); document.body.append(pre)
}, 6000)
</script>`)
  const r = await runPage(page, 'mount')
  if (!r) expect(true, 'no browser here: the mount check is skipped')
  else expect(JSON.stringify(r.out) === JSON.stringify(['lesson', 'lesson', 'error:line 2', 'lesson']) && r.styles === 1, `chalk-talk/mount: blocks become lessons, one added later too (${JSON.stringify(r)})`)
}

// The review in a browser over the DevTools pipe: the coffee chain from a real session — its first version put the
// balloon on the café (found), the second above the person (clean) — with every chapter at every setting as PNG and a
// contact sheet, all in a few seconds.
{
  const { launchFlags } = await import('../kit/browser.mjs')
  const linux = launchFlags('linux', 0)
  expect(linux.includes('--no-sandbox') && linux.includes('--disable-dev-shm-usage') && !launchFlags('linux', 1000).includes('--no-sandbox') && !launchFlags('darwin', 0).includes('--no-sandbox'),
    'no sandbox only as root on Linux, where Chromium will not start without it')
  const fixtures = join(skill, '../../tools/fixtures')
  const left = run(join(fixtures, 'coffee-chain-left.chalk'), [join(dir, 'left.html')])
  if (/• review/.test(left.stdout)) expect(true, 'no browser here: the coffee chain checks are skipped')
  else {
    expect(left.status === 3 && /the text of step 3 \(«de onde veio isso\?»\) sits on the drawing of step 8/.test(left.stdout), 'the coffee chain with the balloon on the café is found (exit 3)')
    // onda B: the clean one is written with a chain and the new figures, with no house or desk standing in for them
    const recipe = readFileSync(join(fixtures, 'coffee-chain.chalk'), 'utf8')
    expect(/^chain at /m.test(recipe) && !/^\s*(house|desk) /m.test(recipe), 'the coffee chain is a chain of the new figures (no house or desk standing in)')
    const t0 = Date.now()
    const ok = run(join(fixtures, 'coffee-chain.chalk'), [join(dir, 'coffee.html'), '--snapshots'])
    const ms = Date.now() - t0
    const shots = join(dir, 'cadeia-cafe.snapshots')
    const files = ok.status === 0 ? readdirSync(shots) : []
    const sheet = files.includes('cadeia-cafe.contact-sheet.png') ? readFileSync(join(shots, 'cadeia-cafe.contact-sheet.png')) : Buffer.alloc(0)
    // A PNG's width and height are in its header; 4 settings across, 4 chapters down.
    const [w, h] = sheet.length > 24 ? [sheet.readUInt32BE(16), sheet.readUInt32BE(20)] : [0, 0]
    const blank = files.filter((f) => f.endsWith('.png')).filter((f) => statSync(join(shots, f)).size < 8000)
    expect(ok.status === 0 && /✓ review/.test(ok.stdout) && files.filter((f) => /\.ch\d\.[\w-]+\.png$/.test(f)).length === 16 && w === 150 + 4 * 316 && h === 44 + 4 * (Math.round(300 * 780 / 900) + 16) && !blank.length && ms < 8000,
      `the coffee chain is clean, with 16 snapshots and a ${w}×${h} contact sheet, in ${(ms / 1000).toFixed(1)} s${ok.status ? `: ${ok.stdout}${ok.stderr}` : ''}${blank.length ? ` (blank: ${blank.join(', ')})` : ''}`)
  }
  const missing = await (await import('../kit/browser.mjs')).runPage(join(dir, 'nowhere.html'), 'review')
  expect(!missing || /ERR_FILE_NOT_FOUND/.test(missing.error ?? ''), `a page that is not there says so at once (${JSON.stringify(missing)})`)
}

// Onda C: the two things the 0.13.0 tests found — a drawing on top of another is found, and a recipe that defines a
// figure gets its contact sheet without asking, with a line saying to look at it once.
{
  const two = join(dir, 'two.chalk')
  writeFileSync(two, 'title X\nperson a at 800,300 "você"\nperson b at 805,300 "você"\n')
  const t = run(two)
  if (!/• review/.test(t.stdout)) expect(t.status === 3 && /the drawings of steps 1 and 2 sit on each other/.test(t.stdout), 'two people drawn in one place are found (exit 3)', t.stdout)
  const def = join(dir, 'defined.chalk')
  writeFileSync(def, 'title X\nid defined\ndefine xicara\n  polygon 24,48 76,48 70,90 30,90 fill=#FFFFFF\n  curve 74,56 90,62 72,80\nxicara minha at 450,300 "minha xícara"\n')
  const d = run(def)
  if (!/• review/.test(d.stdout)) {
    const sheet = join(dir, 'defined.snapshots', 'defined.contact-sheet.png')
    let made = false
    try { made = statSync(sheet).size > 1000 } catch {}
    expect(d.status === 0 && made && /• figures +1 defined \(xicara\): open the contact sheet once/.test(d.stdout), 'a defined figure gets its contact sheet and a line asking for one look', d.stdout)
  }
}

// Animação: a lesson with `animate` keeps its drawing moving in place — the motions run in the lesson, the review and
// the contact sheet see it still.
{
  const moving = join(dir, 'moving.chalk')
  writeFileSync(moving, 'title X\nid moving\nfactory torra at 260,320 "torrefação"\ntruck caminhao at 600,320 "caminhão"\nanimate torra steam\nanimate caminhao drive\n')
  const m = run(moving, [join(dir, 'moving.html')])
  if (!/• review/.test(m.stdout)) {
    expect(m.status === 0 && /✓ review/.test(m.stdout), 'a lesson that moves passes the review (it is measured still)', m.stdout + m.stderr)
    const page = readFileSync(join(dir, 'moving.html'), 'utf8').replace('</body>', `<script>setTimeout(async () => { const els = [...document.querySelectorAll('[data-anim]')]
      const pos = () => els.map((e) => getComputedStyle(e).transform).join(' / '); const a = pos(); await new Promise((r) => setTimeout(r, 400))
      const p = document.createElement('pre'); p.id = 'chalk-probe'; p.textContent = encodeURIComponent(JSON.stringify({ kinds: els.map((e) => e.dataset.anim), moved: a !== pos() })); document.body.append(p) }, 2500)</script></body>`)
    writeFileSync(join(dir, 'moving-probe.html'), page)
    const { runPage } = await import('../kit/browser.mjs')
    const r = await runPage(join(dir, 'moving-probe.html'), 'probe', '', { timeout: 30 })
    expect(r && r.moved && [...(r.kinds ?? [])].sort().join() === 'drive,wisp,wisp,wisp', `in the lesson the truck drives and the steam rises (${JSON.stringify(r)})`)
  }
}

// Lottie (0.16.0): an animation of the pack plays inside the drawing, with its credit; a file beside the recipe too;
// the player goes in only when a lesson has one; an expression, an image from outside, a URL or a missing file is
// refused.
{
  writeFileSync(join(dir, 'mine.json'), readFileSync(join(here, 'noto/think.json'), 'utf8'))
  const lot = join(dir, 'party.chalk')
  writeFileSync(lot, 'title X\nid party\nlottie celebrate festa at 700,200 size=140\nlottie ./mine.json at 200,300 size=120\n')
  const l = run(lot, [join(dir, 'party.html')])
  const page = readFileSync(join(dir, 'party.html'), 'utf8')
  expect(l.status === 0 && page.includes('lottie-web') && page.includes('Noto Animated Emoji by Google'), 'a lesson with animations carries the player and the credit', l.stdout + l.stderr)
  expect(/^• lottie +2 animations in one drawing/m.test(l.stdout), 'two animations in one drawing are pointed out (not an error)', l.stdout)
  if (!/• review/.test(l.stdout)) {
    writeFileSync(join(dir, 'party-probe.html'), page.replace('</body>', `<script>setTimeout(async () => { const gs = [...document.querySelectorAll('[data-lottie]')]
      const shape = () => gs.map((g) => g.querySelector('svg')?.innerHTML.length ?? 0).join(); const a = shape(); await new Promise((r) => setTimeout(r, 500))
      const p = document.createElement('pre'); p.id = 'chalk-probe'; p.textContent = encodeURIComponent(JSON.stringify({ n: gs.length, drawn: gs.every((g) => g.querySelector('svg path')), moved: a !== shape(), credit: document.querySelector('[data-part="credits"]')?.textContent ?? '' })); document.body.append(p) }, 2500)</script></body>`))
    const { runPage } = await import('../kit/browser.mjs')
    const r = await runPage(join(dir, 'party-probe.html'), 'probe', '', { timeout: 30 })
    expect(r && r.n === 2 && r.drawn && r.moved && /CC BY 4.0/.test(r.credit), `the animations play in the lesson, credited (${JSON.stringify(r)})`)
  }
  const plain = run(join(dir, 'two.chalk'), [join(dir, 'plain.html'), '--no-review'])
  expect(plain.status !== 1 && !readFileSync(join(dir, 'plain.html'), 'utf8').includes('lottie-web'), 'a lesson with no animation has no player')
  const bad = (name, json, why) => {
    writeFileSync(join(dir, `${name}.json`), JSON.stringify(json))
    writeFileSync(join(dir, `${name}.chalk`), `title X\nlottie ./${name}.json at 400,200\n`)
    const r = run(join(dir, `${name}.chalk`))
    expect(r.status === 1 && why.test(r.stderr), `an animation ${name.replace(/-/g, ' ')} is refused (${r.stderr.trim().split('\n')[0]})`)
  }
  const base = { v: '5.7.4', fr: 30, ip: 0, op: 60, w: 100, h: 100 }
  bad('with-an-expression', { ...base, layers: [{ ks: { o: { a: 0, k: 100, x: 'time * 2' } } }] }, /expression/)
  bad('with-an-outside-image', { ...base, layers: [], assets: [{ id: 'i', w: 1, h: 1, u: 'https://x/', p: 'a.png' }] }, /image from outside/)
  writeFileSync(join(dir, 'url.chalk'), 'title X\nlottie https://x.test/a.json at 400,200\n')
  expect(/never from the internet/.test(run(join(dir, 'url.chalk')).stderr), 'an animation from a URL is refused')
  writeFileSync(join(dir, 'gone.chalk'), 'title X\nlottie ./gone.json at 400,200\n')
  expect(/no such file beside the recipe/.test(run(join(dir, 'gone.chalk')).stderr), 'a missing animation file says so')
}

// back-of-napkin (0.17.0): what each purpose usually misses is said (exit 3), a quiz outside a lesson is refused, and
// bars with no max keep one scale over the settings.
{
  const warn = (name, body, why) => {
    writeFileSync(join(dir, `${name}.chalk`), `title X\n${body}\ntext "x" at 40,60\n`)
    const r = run(join(dir, `${name}.chalk`), ['--no-review'])
    expect(r.status === 3 && why.test(r.stdout), `${name.replace(/-/g, ' ')}: «${(r.stdout.match(/^! .*$/m) ?? [''])[0].replace(/^! \S+\s+/, '')}»`, r.stdout + r.stderr)
  }
  warn('a-pitch-with-no-ask', 'kind pitch', /^! pitch +the pitch does not end with an ask/m)
  warn('an-architecture-with-no-failure', 'kind arch', /^! arch +no failure drawn/m)
  warn('a-decision-with-no-winner', 'kind decision', /^! decision +the decision does not say which option wins/m)
  warn('data-with-no-source', 'kind data', /^! data +where do these numbers come from/m)
  warn('a-timeline-with-no-line', 'kind timeline', /^! timeline +the timeline has no line/m)
  writeFileSync(join(dir, 'pitch-ok.chalk'), 'title X\nkind pitch\n# The ask\nhighlight 100,300 -> 500,300\ntext "a pilot" at 300,310 anchor=middle\n')
  const ok = run(join(dir, 'pitch-ok.chalk'), ['--no-review'])
  expect(ok.status === 0 && !/^! /m.test(ok.stdout), 'a pitch that ends with its ask has nothing to say', ok.stdout)
  writeFileSync(join(dir, 'pitch-quiz.chalk'), 'title X\nkind pitch\ntext "x" at 40,60\nquiz "q"\n  * a -- b\n  - c -- d\n')
  expect(/only a lesson has a quiz/.test(run(join(dir, 'pitch-quiz.chalk')).stderr), 'a quiz outside a lesson is refused')
  // bars with no max: at the switch's two settings, the taller bar is a different height (one scale), not the same
  writeFileSync(join(dir, 'bars.chalk'), 'title X\nid bars\nswitch dobro "o dobro" off\nvar v = "10 + 10*dobro"\nbars box 100,100,300,300 values v labels a\n')
  const b = run(join(dir, 'bars.chalk'), [join(dir, 'bars.html'), '--snapshots'])
  if (!/• review/.test(b.stdout)) {
    const shots = join(dir, 'bars.snapshots')
    const height = (f) => {
      const png = readFileSync(join(shots, f))
      return png.length // a taller hatched bar draws more strokes: a bigger picture
    }
    expect(b.status === 0 && height('bars.ch1.default.png') < height('bars.ch1.dobro-on.png') - 500, 'bars with no max keep one scale: off, the bar is shorter than on')
  }
}

// The cheat sheet: every example a mistake points to builds, and the ones meant for SKILL.md are in it, word for word.
{
  const { SYNTAX } = await import('../skills/chalk-talk/scripts/syntax.mjs')
  const skillText = readFileSync(join(skill, 'SKILL.md'), 'utf8')
  const broken = []
  const absent = []
  for (const [kind, { line, needs, sheet }] of Object.entries(SYNTAX)) {
    const file = join(dir, `syntax-${kind}.chalk`)
    // A recipe needs a step: the header lines get one after them.
    writeFileSync(file, `${kind === 'title' ? '' : 'title X\n'}${needs ? `${needs}\n` : ''}${line}\ntext "fim" at 40,500\n`)
    const r = run(file, ['--no-review'])
    if (r.status !== 0) broken.push(`${kind}: ${r.stderr.trim()}`)
    if (sheet !== false && !skillText.includes(line)) absent.push(kind)
  }
  expect(!broken.length, `every example of how a line is written builds${broken.length ? ` — ${broken.join(' / ')}` : ''}`)
  expect(!absent.length, `SKILL.md's cheat sheet has every example meant for it${absent.length ? ` — missing ${absent.join(', ')}` : ''}`)
  writeFileSync(join(dir, 'hint.chalk'), 'title X\nperson ana at 150,330\nana says\n')
  const hint = run(join(dir, 'hint.chalk'))
  expect(hint.status === 1 && hint.stderr.includes(SYNTAX.balloon.line), `a mistake shows how its line is written (${hint.stderr.trim().split('\n').join(' / ')})`)
}

// 0.17.2: a .chalk with no `id` line is named after its file; with one, after the id.
{
  writeFileSync(join(dir, 'my-drawing.chalk'), 'title X\ntext "algo" at 40,64\n')
  writeFileSync(join(dir, 'named.chalk'), 'title X\nid cafe\ntext "algo" at 40,64\n')
  const a = run(join(dir, 'my-drawing.chalk'), ['--no-review'])
  const b = run(join(dir, 'named.chalk'), ['--no-review'])
  expect(a.status === 0 && a.stdout.includes('my-drawing.html') && b.status === 0 && b.stdout.includes('cafe.html'), 'a .chalk is named after its file, or its id', a.stdout + b.stdout)
}

const badText = join(dir, 'bad.chalk')
writeFileSync(badText, 'title X\nperson ana at 1\n')
const bt = run(badText)
expect(bt.status === 1 && /✗ text: line 2:/.test(bt.stderr), `a broken text names its line (${bt.stderr.trim()})`)

const bad = join(dir, 'bad.json')
writeFileSync(bad, JSON.stringify({ id: 'bad', title: 'Bad', width: 900, height: 560, steps: [{ type: 'circle', center: [100, 100] }] }))
const b = run(bad)
expect(b.status === 1 && /✗ contract: .*r/.test(b.stderr), `a broken recipe stops with exit 1 (${b.stderr.trim()})`)

// The engine brings a text back inside the paper by itself; a line drawn across a text is left for the reviewer.
const across = join(dir, 'across.json')
writeFileSync(across, JSON.stringify({ id: 'across', title: 'Across', width: 900, height: 560, steps: [
  { type: 'text', at: [300, 300], text: 'a sentence with a line through it', size: 30 },
  { type: 'line', from: [250, 290], to: [800, 290] },
] }))
const o = run(across)
const reviewed = !/• review/.test(o.stdout)
expect(reviewed ? o.status === 3 && /crosses the text/.test(o.stdout) : o.status === 0, reviewed ? 'a line across a text is found (exit 3)' : 'no browser here: the review check is skipped')

rmSync(dir, { recursive: true, force: true })
done('chalk-talk')
