#!/usr/bin/env node
// solution: a solution — one process seen by every skill that has something to say about it — kept in one short
// file, <id>.solution.yaml, that names its pieces: the way of working, the simulation, the service blueprint, the drill,
// the Copilot Studio agents, the lesson. Each piece is an ordinary recipe of its skill, beside the solution.
//
//   node build.mjs <id>.solution.yaml --check [--json] [--lang en|pt]   each piece there, passing its skill's check,
//                                                                       and each lens up to date with the way
//   node build.mjs <id>.solution.yaml --check --format                  only the solution file itself (the mod's guard)
//   node build.mjs <id>.solution.yaml [--lang en|pt] [--out <folder>]   the page: <id>.solution.html, every piece in a tab
//   node build.mjs --list                                               the solution accelerators that come with it
//   node build.mjs --new <accelerator> <folder>                         copy one to start your own
//
// Exit codes: 0 done (what to look at is printed, and is not an error); 1 the solution file breaks its format (each
// problem with its line); 2 bad arguments; 4 a piece is missing or fails its own check. Needs Node 18 or later and
// nothing else; each piece is checked and drawn by its own skill, when that skill is beside this one.
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const skills = resolve(here, '../..')
const examples = resolve(here, '../examples')
const VERSION = (() => { try { return /version: "([^"]+)"/.exec(readFileSync(join(here, '../SKILL.md'), 'utf8'))?.[1] ?? '' } catch { return '' } })()

// ---- the pieces: which skill reads each, how it is checked and how its page is made ----
export const PIECES = {
  way: { skill: 'way-of-working', test: /\.way\.ya?ml$/i, check: (f, o) => [f, '--check', '--lang', o.lang], page: (f, o) => [f, '--html', '--lang', o.lang, '--out', o.dir] },
  sim: { skill: 'process-simulation', test: /\.sim$/i, check: (f) => [f, '--check'], page: (f, o) => [f, '--lang', o.lang, '--out', o.dir] },
  blueprint: { skill: 'service-blueprint', test: /\.blueprint\.ya?ml$/i, check: (f, o) => [f, '--check', '--lang', o.lang], page: (f, o) => [f, '--html', '--lang', o.lang, '--out', o.dir] },
  drill: { skill: 'incident-drill', test: /\.drill\.ya?ml$/i, check: (f, o) => [f, '--check', '--lang', o.lang], page: (f, o) => [f, '--lang', o.lang, '--out', o.dir] },
  agents: { skill: 'agent-review', folder: true, check: (f, o) => [f, '--check', '--lang', o.lang, ...o.profile], page: (f, o) => [f, '--html', '--lang', o.lang, ...o.profile, '--out', o.dir] },
  lesson: { skill: 'visual-explainer', test: /\.(chalk|json|mmd)$/i, check: (f, o) => [f, join(o.dir, 'out.html'), '--no-review'], page: (f, o) => [f, join(o.dir, 'lesson.html'), '--no-review'] },
}
const KEYS = ['apiVersion', 'kind', 'metadata', 'format', 'name', 'about', 'lang', ...Object.keys(PIECES), 'profile']
// What the file says it is: DNA's header (apiVersion, kind Solution, the name in metadata) or the format line of before.
const DNA_API = 'github.com/ruinosus/dna/v1'
const KIND = 'Solution'
const FORMAT = 'opening-night/v1'
const LENSES = ['sim', 'blueprint', 'drill'] // the pieces way-of-working --lens writes from the way

const T = {
  en: {
    usage: `usage: node build.mjs <id>.solution.yaml --check [--json] [--format] [--lang en|pt]
       node build.mjs <id>.solution.yaml [--lang en|pt] [--out <folder>]
       node build.mjs <id>.solution.yaml --okf [--lang en|pt] [--out <folder>]
       node build.mjs --list
       node build.mjs --new <accelerator> <folder>
       node build.mjs <id>.solution.yaml --upgrade [--write]`,
    syntax: (l) => `line ${l}: write it as «key: value» (one per line; # starts a comment)`,
    unknown: (k) => `«${k}» is not a field of a solution; the fields are ${KEYS.join(', ')}`,
    twice: (k) => `«${k}» is written twice`,
    format: `the file starts with «apiVersion: ${DNA_API}» and «kind: ${KIND}» (or «format: ${FORMAT}», from before)`,
    upgraded: (f) => `✓ ${f}: now apiVersion ${DNA_API} and kind ${KIND}; the rest as it was`,
    already: (f) => `✓ ${f} already has DNA's header`,
    name: '«name» is missing: the solution\'s name, as people say it',
    lang: '«lang» is en or pt',
    none: `a solution names at least one piece: ${Object.keys(PIECES).join(', ')}`,
    kind: (k, f) => `«${k}: ${f}» is not a ${k === 'agents' ? 'folder of agents' : `${k} file`} (${PIECES[k].test})`,
    profile: '«profile» goes with «agents»',
    missing: (k, f) => `${k}: ${f} is not there`,
    broken: (k, f, s) => `${k}: ${f} does not pass ${s}'s check`,
    ok: (k, f) => `${k.padEnd(9)} ${f}`,
    unchecked: (k, f, s) => `${k.padEnd(9)} ${f} — not checked: ${s} is not beside this skill`,
    stale: (k, f, w) => `${f} came from an earlier version of ${w}: refresh it with way-of-working ${w} --lens ${k} --write --force (it may have been edited by hand: look first)`,
    notLens: (k, f, w) => `${f} came from another way, not ${w}: is it the right one?`,
    summary: (n, name) => `✓ «${name}»: ${n} ${n === 1 ? 'piece' : 'pieces'}`,
    look: 'to look at',
    nothing: '✓ every piece passes its check, and every lens is up to date with the way',
    page: (p) => `✓ page      ${p}`,
    pieceFailed: (k, s) => `the ${k} could not be drawn by ${s}`,
    list: 'The solution accelerators — copy one with --new <name> <folder>:',
    copied: (a, d) => `✓ ${a} copied to ${d}: open ${d}/${a}.solution.yaml and replace the bets (# bet:) with your own`,
    noAcc: (a) => `no accelerator named «${a}»: --list shows them`,
    notEmpty: (d) => `${d} is not empty: name a new folder`,
    model: '• a model, not a forecast: each piece says where its numbers came from',
  },
  pt: {
    usage: `uso: node build.mjs <id>.solution.yaml --check [--json] [--format] [--lang en|pt]
     node build.mjs <id>.solution.yaml [--lang en|pt] [--out <pasta>]
     node build.mjs <id>.solution.yaml --okf [--lang en|pt] [--out <pasta>]
     node build.mjs --list
     node build.mjs --new <accelerator> <pasta>
     node build.mjs <id>.solution.yaml --upgrade [--write]`,
    syntax: (l) => `linha ${l}: escreva como «chave: valor» (uma por linha; # começa um comentário)`,
    unknown: (k) => `«${k}» não é um campo de solution; os campos são ${KEYS.join(', ')}`,
    twice: (k) => `«${k}» está escrito duas vezes`,
    format: `o arquivo começa com «apiVersion: ${DNA_API}» e «kind: ${KIND}» (ou com «format: ${FORMAT}», de antes)`,
    upgraded: (f) => `✓ ${f}: agora com apiVersion ${DNA_API} e kind ${KIND}; o resto como estava`,
    already: (f) => `✓ ${f} já tem o cabeçalho do DNA`,
    name: 'falta «name»: o nome da solution, como as pessoas falam',
    lang: '«lang» é en ou pt',
    none: `uma solution nomeia ao menos uma peça: ${Object.keys(PIECES).join(', ')}`,
    kind: (k, f) => `«${k}: ${f}» não é ${k === 'agents' ? 'uma pasta de agentes' : `um arquivo de ${k}`} (${PIECES[k].test})`,
    profile: '«profile» vai junto com «agents»',
    missing: (k, f) => `${k}: ${f} não está lá`,
    broken: (k, f, s) => `${k}: ${f} não passa no check do ${s}`,
    ok: (k, f) => `${k.padEnd(9)} ${f}`,
    unchecked: (k, f, s) => `${k.padEnd(9)} ${f} — não conferido: o ${s} não está ao lado desta skill`,
    stale: (k, f, w) => `${f} veio de uma versão anterior de ${w}: refaça com way-of-working ${w} --lens ${k} --write --force (pode ter sido editado à mão: olhe antes)`,
    notLens: (k, f, w) => `${f} veio de outro way, não de ${w}: é o certo?`,
    summary: (n, name) => `✓ «${name}»: ${n} ${n === 1 ? 'peça' : 'peças'}`,
    look: 'para olhar',
    nothing: '✓ todas as peças passam no check, e todas as lentes estão em dia com o way',
    page: (p) => `✓ página    ${p}`,
    pieceFailed: (k, s) => `o ${s} não conseguiu desenhar a peça ${k}`,
    list: 'Os solution accelerators — copie um com --new <nome> <pasta>:',
    copied: (a, d) => `✓ ${a} copiado para ${d}: abra ${d}/${a}.solution.yaml e troque as apostas (# bet:) pelas suas`,
    noAcc: (a) => `não há accelerator «${a}»: --list mostra os que há`,
    notEmpty: (d) => `${d} não está vazia: dê uma pasta nova`,
    model: '• um modelo, não uma previsão: cada peça diz de onde vieram os números',
  },
}

/** A value as written: plain, or in quotes ("…" as JSON, '…' as YAML); null when the quotes do not close. */
function unquote(value) {
  if (/^".*"$/.test(value)) { try { return JSON.parse(value) } catch { return null } }
  if (/^'.*'$/.test(value)) return value.slice(1, -1).replace(/''/g, "'")
  return value
}

/** The header of before as DNA's: `format: opening-night/v1` becomes apiVersion and kind, and the top-level name moves
 * into metadata where it was — comments and the rest as they are. Undefined when there is nothing to change. */
export function upgradeHeader(text) {
  const lines = text.split('\n')
  const at = lines.findIndex((l) => /^format:\s*["']?opening-night\/v1["']?\s*(#.*)?$/.test(l))
  if (at < 0 || lines.some((l) => /^apiVersion:/.test(l))) return undefined
  lines.splice(at, 1, `apiVersion: ${DNA_API}`, `kind: ${KIND}`)
  const n = lines.findIndex((l) => /^name:\s*\S/.test(l))
  if (n >= 0) lines.splice(n, 1, 'metadata:', `  name:${lines[n].slice('name:'.length)}`)
  return lines.join('\n')
}

/** The solution file: flat «key: value» lines, a value plain or quoted. Gives what it read and the problems, with lines. */
export function readSolution(text, lang = 'en') {
  const t = T[lang]
  const def = {}
  const problems = []
  let inMetadata = false
  text.split(/\r?\n/).forEach((raw, i) => {
    const line = raw.replace(/^﻿/, '')
    if (!line.trim() || /^\s*#/.test(line)) return
    // metadata: is the one block, with the name inside (DNA's header)
    const sub = inMetadata ? /^\s+([a-z_]+):\s*(.*?)\s*$/.exec(line) : null
    if (sub) {
      if (sub[1] !== 'name') return problems.push({ line: i + 1, text: t.unknown(`metadata.${sub[1]}`) })
      if ('name' in def) return problems.push({ line: i + 1, text: t.twice('name') })
      const value = unquote(sub[2].replace(/\s+#.*$/, ''))
      if (value === null) return problems.push({ line: i + 1, text: t.syntax(i + 1) })
      def.name = { value, line: i + 1 }
      return
    }
    inMetadata = false
    const m = /^([A-Za-z_]+):\s*(.*?)\s*$/.exec(line)
    if (!m) return problems.push({ line: i + 1, text: t.syntax(i + 1) })
    const value = unquote(m[2].replace(/\s+#.*$/, ''))
    if (value === null) return problems.push({ line: i + 1, text: t.syntax(i + 1) })
    if (!KEYS.includes(m[1])) return problems.push({ line: i + 1, text: t.unknown(m[1]) })
    if (m[1] in def) return problems.push({ line: i + 1, text: t.twice(m[1]) })
    if (m[1] === 'metadata') return void (inMetadata = true)
    def[m[1]] = { value, line: i + 1 }
  })
  const at = (k) => def[k]?.line ?? 1
  const dna = 'apiVersion' in def || 'kind' in def
  if (dna ? def.apiVersion?.value !== DNA_API || def.kind?.value !== KIND || 'format' in def : def.format?.value !== FORMAT) problems.push({ line: at(dna ? 'apiVersion' : 'format'), text: t.format })
  if (!def.name?.value) problems.push({ line: 1, text: t.name })
  if (def.lang && !['en', 'pt'].includes(def.lang.value)) problems.push({ line: at('lang'), text: t.lang })
  const pieces = Object.keys(PIECES).filter((k) => def[k]?.value)
  if (!pieces.length) problems.push({ line: 1, text: t.none })
  for (const k of pieces) if (PIECES[k].test && !PIECES[k].test.test(def[k].value)) problems.push({ line: at(k), text: t.kind(k, def[k].value) })
  if (def.profile && !def.agents) problems.push({ line: at('profile'), text: t.profile })
  const value = (k) => def[k]?.value
  return { problems, solution: { name: value('name'), about: value('about') ?? '', lang: value('lang') ?? 'en', profile: value('profile'), pieces: pieces.map((k) => ({ kind: k, file: value(k) })) } }
}

const versionOf = (text) => createHash('sha256').update(text).digest('hex').slice(0, 8)
const run = (skill, args) => spawnSync(process.execPath, [join(skills, skill, 'scripts/build.mjs'), ...args], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
const linesOf = (r) => `${r.stdout ?? ''}${r.stderr ?? ''}`.split('\n').map((l) => l.trimEnd()).filter(Boolean)

/** Every piece of a solution: there or not, passing its skill's check or not, and each lens up to date with the way. */
export function checkPieces(sol, folder, lang) {
  const t = T[lang]
  const way = sol.pieces.find((p) => p.kind === 'way')
  const wayText = way && existsSync(join(folder, way.file)) ? readFileSync(join(folder, way.file), 'utf8') : undefined
  const work = mkdtempSync(join(tmpdir(), 'solution-'))
  try {
    return sol.pieces.map((p) => {
      const spec = PIECES[p.kind]
      const path = resolve(folder, p.file)
      const out = { kind: p.kind, file: p.file, skill: spec.skill, state: 'ok', said: [], looks: [] }
      if (!existsSync(path) || (spec.folder ? !statSync(path).isDirectory() : !statSync(path).isFile())) return { ...out, state: 'missing', said: [t.missing(p.kind, p.file)] }
      if (!existsSync(join(skills, spec.skill, 'scripts/build.mjs'))) return { ...out, state: 'unchecked' }
      const r = run(spec.skill, spec.check(path, { lang, dir: work, profile: sol.profile ? ['--profile', resolve(folder, sol.profile)] : [] }))
      out.said = linesOf(r).map((l) => l.split(work + '/').join('').split(folder + '/').join(''))
      if (r.status !== 0) out.state = 'broken'
      if (way && LENSES.includes(p.kind) && wayText !== undefined) {
        const from = /^# from: (.+)@([0-9a-f]{8})\s*$/m.exec(readFileSync(path, 'utf8'))
        // no «# from:» at all: written by hand, kept as it is; one that names another way is said
        if (from && from[1] !== basename(way.file)) out.looks.push(t.notLens(p.kind, p.file, basename(way.file)))
        else if (from && from[2] !== versionOf(wayText)) { out.stale = true; out.looks.push(t.stale(p.kind, p.file, way.file)) }
      }
      return out
    })
  } finally {
    rmSync(work, { recursive: true, force: true })
  }
}

// ---- the page: one file, a tab per piece, each piece drawn by its own skill ----
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
const TAB = {
  en: { way: 'The process', sim: 'What if', blueprint: 'The journey', drill: 'The drill', agents: 'The agents', lesson: 'The lesson', summary: 'Summary', asks: { way: 'Who does what, and where it is decided', sim: 'Where the queue forms, and what would change it', blueprint: 'What the person lives at each step', drill: 'What the team does when it goes wrong', agents: 'How the agents compare, and who is off the pattern', lesson: 'The idea, explained by drawing' }, made: 'Made with DNA · solution', missing: 'not there', broken: 'does not pass its check', unchecked: 'not checked', stale: 'behind the way', ok: 'passes its check', notDrawn: 'This piece could not be drawn.', of: 'by' },
  pt: { way: 'O processo', sim: 'E se', blueprint: 'A jornada', drill: 'O ensaio', agents: 'Os agentes', lesson: 'A explicação', summary: 'Resumo', asks: { way: 'Quem faz o quê, e onde se decide', sim: 'Onde a fila se forma, e o que mudaria isso', blueprint: 'O que a pessoa vive em cada passo', drill: 'O que o time faz quando dá errado', agents: 'Como os agentes se comparam, e quem está fora do padrão', lesson: 'A ideia, explicada desenhando' }, made: 'Feito com DNA · solution', missing: 'não está lá', broken: 'não passa no check', unchecked: 'não conferido', stale: 'atrás do way', ok: 'passa no check', notDrawn: 'Esta peça não pôde ser desenhada.', of: 'por' },
}

function pageOf(sol, checked, drawn, lang) {
  const w = TAB[lang]
  const state = (c) => (c.state !== 'ok' ? w[c.state] : c.stale ? w.stale : w.ok)
  const tone = (c) => (c.state === 'missing' || c.state === 'broken' ? 'bad' : c.stale || c.state === 'unchecked' ? 'warn' : 'good')
  const cards = checked.map((c) => `<li class="card ${tone(c)}"><button type="button" data-tab="${c.kind}"><span class="k">${esc(w[c.kind])}</span><span class="q">${esc(w.asks[c.kind])}</span><span class="f">${esc(c.file)}</span><span class="s"><i></i>${esc(state(c))}</span></button>${[...c.looks, ...(c.state === 'ok' ? [] : c.said.slice(0, 3))].map((l) => `<p>${esc(l)}</p>`).join('')}<small>${esc(c.skill)}</small></li>`).join('')
  const tabs = [`<button type="button" role="tab" data-tab="summary" aria-selected="true">${esc(w.summary)}</button>`, ...checked.map((c) => `<button type="button" role="tab" data-tab="${c.kind}" aria-selected="false"${drawn[c.kind] ? '' : ' disabled'}><i class="${tone(c)}"></i>${esc(w[c.kind])}</button>`)].join('')
  const data = Object.entries(drawn).map(([k, html]) => `<script type="application/octet-stream" id="piece-${k}">${Buffer.from(html, 'utf8').toString('base64')}</script>`).join('\n')
  return `<!doctype html>
<html lang="${lang === 'pt' ? 'pt-BR' : 'en'}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="solution ${esc(VERSION)}">
<title>${esc(sol.name)}</title>
<style>
:root { --bg: #f6f5f2; --paper: #ffffff; --ink: #1d232a; --muted: #5d6670; --line: #dcdad4; --accent: #2f5d8a; --good: #2e7d4f; --warn: #a8660b; --bad: #b3261e; color-scheme: light; }
@media (prefers-color-scheme: dark) { :root { --bg: #15181c; --paper: #1e2228; --ink: #e9ecef; --muted: #a3acb6; --line: #333a42; --accent: #8db8e6; --good: #6cc28f; --warn: #e3a64a; --bad: #f08a80; color-scheme: dark; } }
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body { background: var(--bg); color: var(--ink); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; display: flex; flex-direction: column; }
header { padding: 20px 24px 0; background: var(--paper); border-bottom: 1px solid var(--line); }
h1 { margin: 0; font-size: 22px; letter-spacing: -0.01em; }
header p { margin: 4px 0 14px; color: var(--muted); max-width: 70ch; }
nav { display: flex; gap: 2px; overflow-x: auto; }
nav button { font: inherit; font-size: 14px; border: 0; background: none; color: var(--muted); padding: 10px 14px; border-bottom: 2px solid transparent; cursor: pointer; white-space: nowrap; display: flex; align-items: center; gap: 7px; }
nav button[aria-selected="true"] { color: var(--ink); border-bottom-color: var(--accent); font-weight: 600; }
nav button:disabled { opacity: .45; cursor: default; }
nav button:focus-visible, .card button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; background: var(--good); flex: none; }
i.warn, .warn i { background: var(--warn); } i.bad, .bad i { background: var(--bad); }
main { flex: 1; min-height: 0; position: relative; }
#summary { padding: 24px; overflow: auto; height: 100%; }
#summary ul { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.card { background: var(--paper); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.card button { all: unset; display: grid; gap: 2px; cursor: pointer; width: 100%; }
.card .k { font-weight: 600; } .card .q { color: var(--ink); font-size: 14px; margin-bottom: 4px; } .card .f { font-family: ui-monospace, Menlo, monospace; font-size: 13px; color: var(--muted); overflow-wrap: anywhere; }
.card .s { display: flex; align-items: center; gap: 7px; font-size: 13px; margin-top: 6px; }
.card p { margin: 8px 0 0; font-size: 13px; color: var(--muted); overflow-wrap: anywhere; }
.card small { display: block; margin-top: 10px; font-size: 12px; color: var(--muted); }
iframe { border: 0; width: 100%; height: 100%; display: block; background: var(--paper); }
footer { padding: 6px 24px; font-size: 12px; color: var(--muted); border-top: 1px solid var(--line); background: var(--paper); }
[hidden] { display: none !important; }
@media (max-width: 600px) { header { padding: 16px 16px 0; } #summary { padding: 16px; } footer { padding: 6px 16px; } }
</style>
</head>
<body>
<header>
<h1>${esc(sol.name)}</h1>
${sol.about ? `<p>${esc(sol.about)}</p>` : '<p></p>'}
<nav role="tablist">${tabs}</nav>
</header>
<main>
<section id="summary"><ul>${cards}</ul></section>
<iframe id="frame" title="${esc(sol.name)}" hidden></iframe>
</main>
<footer>${esc(w.made)}${VERSION ? ` ${esc(VERSION)}` : ''}</footer>
${data}
<script>
(function () {
  var frame = document.getElementById('frame'), summary = document.getElementById('summary'), shown = {};
  function piece(k) {
    var el = document.getElementById('piece-' + k);
    if (!el) return null;
    var bin = atob(el.textContent.trim()), bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder('utf-8').decode(bytes);
  }
  function show(k) {
    document.querySelectorAll('nav button').forEach(function (b) { b.setAttribute('aria-selected', String(b.dataset.tab === k)); });
    if (k === 'summary') { summary.hidden = false; frame.hidden = true; return; }
    var html = piece(k);
    if (!html) return;
    summary.hidden = true; frame.hidden = false;
    if (shown.now !== k) { frame.srcdoc = html; shown.now = k; }
    try { history.replaceState(null, '', '#' + k); } catch (e) {}
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-tab]');
    if (b && !b.disabled) show(b.dataset.tab);
  });
  var first = (location.hash || '').slice(1);
  if (first && document.getElementById('piece-' + first)) show(first);
})();
</script>
</body>
</html>
`
}

// ---- the command ----
const argv = process.argv.slice(2)
const valued = new Set(['--lang', '--out', '--new'])
const flags = new Set(['--check', '--json', '--format', '--list', '--upgrade', '--write', '--okf', ...valued])
const option = (name) => (argv.includes(name) ? argv[argv.indexOf(name) + 1] : undefined)
const args = argv.filter((a, i) => !a.startsWith('--') && !valued.has(argv[i - 1]))
const fail = (msg, code = 2) => {
  console.error(msg)
  process.exit(code)
}
const accelerators = () => (existsSync(examples) ? readdirSync(examples).filter((d) => existsSync(join(examples, d, `${d}.solution.yaml`))) : [])
// run as a command (not imported): compared by real paths, since a folder may be reached through a link (/var → /private/var)
const isMain = (() => { try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)) } catch { return false } })()

if (isMain) {
  const bad = argv.find((a) => a.startsWith('--') && !flags.has(a))
  const ui = option('--lang') === 'pt' ? 'pt' : 'en'
  if (bad) fail(`✗ unknown option ${bad}\n${T[ui].usage}`)
  if (option('--lang') && !['en', 'pt'].includes(option('--lang'))) fail(`✗ --lang is en or pt\n${T[ui].usage}`)

  if (argv.includes('--list')) {
    console.log(T[ui].list)
    for (const a of accelerators()) {
      const r = readSolution(readFileSync(join(examples, a, `${a}.solution.yaml`), 'utf8'))
      console.log(`  ${a.padEnd(24)} ${r.solution.name}${r.solution.about ? ` — ${r.solution.about}` : ''}`)
    }
    process.exit(0)
  }
  if (argv.includes('--new')) {
    const name = option('--new')
    const to = args[0]
    if (!name || !to) fail(T[ui].usage)
    if (!accelerators().includes(name)) fail(`✗ ${T[ui].noAcc(name)}`)
    const dest = resolve(to)
    if (existsSync(dest) && readdirSync(dest).length) fail(`✗ ${T[ui].notEmpty(to)}`)
    cpSync(join(examples, name), dest, { recursive: true })
    console.log(T[ui].copied(name, to))
    process.exit(0)
  }

  if (args.length !== 1) fail(T[ui].usage)
  const file = resolve(args[0])
  if (!existsSync(file)) fail(`✗ ${args[0]}: no such file`)
  // --upgrade: the header of before as DNA's, the rest as it is (written with --write)
  if (argv.includes('--upgrade')) {
    const text = readFileSync(file, 'utf8')
    const up = upgradeHeader(text)
    if (up === undefined) {
      if (/^apiVersion:/m.test(text)) { console.log(T[ui].already(basename(file))); process.exit(0) }
    } else {
      const a = readSolution(text), b = readSolution(up)
      if (JSON.stringify(a) !== JSON.stringify(b)) fail(`✗ ${basename(file)}: with the new header the file does not read the same; nothing written`, 1)
      if (!argv.includes('--write')) { process.stdout.write(up); process.exit(0) }
      writeFileSync(file, up)
      console.log(T[ui].upgraded(basename(file)))
      process.exit(0)
    }
  }
  const folder = dirname(file)
  const read = readSolution(readFileSync(file, 'utf8'), ui)
  if (read.problems.length) {
    for (const p of read.problems) console.error(`✗ ${basename(file)}:${p.line}: ${p.text}`)
    process.exit(1)
  }
  const sol = read.solution
  const lang = option('--lang') ?? sol.lang
  const t = T[lang]
  if (argv.includes('--format')) {
    console.log(`✓ ${basename(file)}: ${sol.pieces.map((p) => p.kind).join(', ')}`)
    process.exit(0)
  }
  const checked = checkPieces(sol, folder, lang)
  const failing = checked.some((c) => c.state === 'missing' || c.state === 'broken')
  if (argv.includes('--check') && argv.includes('--json')) {
    console.log(JSON.stringify({ format: 'solution/read-v1', name: sol.name, about: sol.about, lang, file: basename(file), pieces: checked }))
    process.exit(failing ? 4 : 0)
  }
  console.log(t.summary(checked.length, sol.name))
  for (const c of checked) {
    if (c.state === 'missing') console.log(`✗ ${c.said[0]}`)
    else if (c.state === 'broken') {
      console.log(`✗ ${t.broken(c.kind, c.file, c.skill)}`)
      for (const l of c.said.filter((x) => /^✗|^\s/.test(x)).slice(0, 6)) console.log(`    ${l}`)
    } else if (c.state === 'unchecked') console.log(`• ${t.unchecked(c.kind, c.file, c.skill)}`)
    else console.log(`✓ ${t.ok(c.kind, c.file)}`)
  }
  const looks = checked.flatMap((c) => c.looks)
  for (const l of looks) console.log(`! ${t.look}: ${l}`)
  if (!looks.length && !failing && checked.every((c) => c.state === 'ok')) console.log(t.nothing)
  // --okf: the solution as an OKF v0.2 bundle (scripts/okf.mjs); a piece that fails its check goes as a draft
  if (argv.includes('--okf')) {
    const { exportOkf } = await import('./okf.mjs')
    const id = basename(file).replace(/\.solution\.ya?ml$/i, '')
    const out = resolve(option('--out') ?? join(folder, `${id}.okf`))
    const done = await exportOkf({ sol, file, folder, checked, out, lang, skills, reviewed: sol.reviewed })
    console.log(`✓ okf ${out}: ${done.concepts} concepts, ${done.written.length ? `${done.written.length} files written` : 'nothing changed'}`)
    for (const l of done.log) console.log(`  ${l}`)
    process.exit(failing ? 4 : 0)
  }
  if (failing) process.exit(4)
  if (argv.includes('--check')) process.exit(0)

  // the page: each piece drawn by its skill in a folder of its own, then all of them in one file
  const drawn = {}
  const work = mkdtempSync(join(tmpdir(), 'solution-page-'))
  try {
    for (const c of checked) {
      if (c.state !== 'ok') continue
      const spec = PIECES[c.kind]
      const dir = join(work, c.kind)
      cpSync(folder, dir, { recursive: true, filter: (src) => !relative(folder, src).startsWith('node_modules') })
      const out = join(work, `${c.kind}-out`)
      mkdirSync(out)
      const r = run(spec.skill, spec.page(join(dir, c.file), { lang, dir: out, profile: sol.profile ? ['--profile', join(dir, sol.profile)] : [] }))
      const pages = existsSync(out) ? readdirSync(out).filter((f) => f.endsWith('.html')) : []
      if (r.status !== 0 && r.status !== 3 || !pages.length) { console.log(`! ${t.look}: ${t.pieceFailed(c.kind, c.skill)}`); continue }
      drawn[c.kind] = readFileSync(join(out, pages.sort((a, b) => statSync(join(out, b)).size - statSync(join(out, a)).size)[0]), 'utf8')
    }
  } finally {
    rmSync(work, { recursive: true, force: true })
  }
  const id = basename(file).replace(/\.solution\.ya?ml$/i, '')
  const page = join(resolve(option('--out') ?? folder), `${id}.solution.html`)
  writeFileSync(page, pageOf(sol, checked, drawn, lang))
  console.log(t.page(page))
  console.log(t.model)
}
