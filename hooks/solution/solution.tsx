// /solution: an solution solution in a pane — each piece (the way, the simulation, the journey, the drill, the
// agents, the lesson) with where it stands, by solution's own check (--check --json), and the command that shows
// it. A lens that fell behind the way has a button that makes it again from the way (way-of-working --lens --write
// --force) — asking first, since it may have been edited by hand.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'

import type { SolutionPiece } from '../../types'
import { pathOf, scriptOf } from '../recipes/run'

export const SOLUTION_PANE = 'dna-solution'
const solution = atom({ plugin: 'dna', key: 'solution' } as const, null, { shape: 'solution-1' })

const SHOW: Record<string, string> = { way: '/way-preview', sim: '/sim-preview', blueprint: '/blueprint-preview', drill: '/drill', agents: '/cast', lesson: '' }
const W = {
  en: { kinds: { way: 'The process', sim: 'What if', blueprint: 'The journey', drill: 'The drill', agents: 'The agents', lesson: 'The lesson' } as Record<string, string>, ok: 'passes its check', missing: 'not there', broken: 'does not pass its check', unchecked: 'not checked', stale: 'behind the way', redo: 'Make it again from the way', sure: 'Sure? It may have been edited by hand', redone: 'made again from the way', see: 'see it', page: (f: string) => `The page: ask Claude to run solution on ${f}`, none: 'Run /solution with a .solution.yaml.' },
  pt: { kinds: { way: 'O processo', sim: 'E se', blueprint: 'A jornada', drill: 'O ensaio', agents: 'Os agentes', lesson: 'A explicação' } as Record<string, string>, ok: 'passa no check', missing: 'não está lá', broken: 'não passa no check', unchecked: 'não conferido', stale: 'atrás do way', redo: 'Refazer a partir do way', sure: 'Certeza? Pode ter sido editado à mão', redone: 'refeito a partir do way', see: 'para ver', page: (f: string) => `A página: peça ao Claude para rodar o solution em ${f}`, none: 'Rode /solution com um .solution.yaml.' },
}
const dirOf = (p: string) => p.split('/').slice(0, -1).join('/') || '.'

async function load($: EngineInterface, path: string, lang?: 'en' | 'pt') {
  const run = await $.process.run(['node', scriptOf($, 'solution'), path, '--check', '--json', ...(lang ? ['--lang', lang] : [])], { timeoutMs: 8000 })
  if (run.exitCode !== 0 && run.exitCode !== 4) return { error: (run.stderr || run.stdout).trim().split('\n').slice(0, 6).join('\n') }
  const doc = JSON.parse(run.stdout)
  return { doc: { path, name: doc.name, lang: doc.lang === 'pt' ? 'pt' : 'en', way: (doc.pieces as SolutionPiece[]).find((p) => p.kind === 'way')?.file ?? '', pieces: doc.pieces as SolutionPiece[], armed: '' } as const }
}

async function redo($: EngineInterface, kind: string) {
  const doc = await read($, solution)
  if (!doc || !doc.way) return
  if (doc.armed !== kind) return void (await update($, solution, (x) => (x ? { ...x, armed: kind } : x)))
  const dir = dirOf(doc.path)
  await $.process.run(['node', scriptOf($, 'way-of-working'), `${dir}/${doc.way}`, '--lens', kind, '--lang', doc.lang, '--write', '--force'], { timeoutMs: 6000 })
  const r = await load($, doc.path, doc.lang)
  if ('error' in r) return
  await update($, solution, () => ({ ...r.doc, pieces: r.doc.pieces.map((p) => (p.kind === kind ? { ...p, redone: true } : p)) }))
}

export function solutionCommand(on: On) {
  on('command.run', { command: 'solution' }, async ($, e) => {
    const args = e.args.trim().split(/\s+/).filter(Boolean)
    const lang = args.includes('--lang') ? (args[args.indexOf('--lang') + 1] === 'pt' ? 'pt' : 'en') : undefined
    const typed = args.filter((a, i) => !a.startsWith('--') && args[i - 1] !== '--lang')[0]
    if (!typed) {
      if (await read($, solution)) return (await $.ui.open({ id: SOLUTION_PANE, title: 'Solution' }), { text: 'the solution is in the pane.' })
      return { text: 'name a solution, for example /solution service-desk.solution.yaml' }
    }
    const path = await pathOf($, typed)
    if (!(await $.fs.exists(path))) return { text: `could not read ${typed}: no such file` }
    const r = await load($, path, lang).catch((err) => ({ error: String(err) }))
    if ('error' in r) return { text: `${typed} is not a solution yet:\n${r.error}` }
    await update($, solution, () => r.doc)
    await $.ui.open({ id: SOLUTION_PANE, title: 'Solution' })
    const w = W[r.doc.lang]
    const text = [`«${r.doc.name}»`, ...r.doc.pieces.map((p) => `${p.kind}: ${p.file} — ${p.state !== 'ok' ? w[p.state] : p.stale ? w.stale : w.ok}`)].join('\n')
    return { text, context: [`The person ran /solution on ${path}. solution says:\n${text}`] }
  })

  on('ui.render', { component: 'Pane', requestId: SOLUTION_PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const doc = await read($, solution)
    if (!doc) return <Text dimColor>{W.en.none}</Text>
    const w = W[doc.lang]
    const file = doc.path.split('/').pop()!
    return (
      <Box flexDirection="column" gap={1}>
        <Text bold>{doc.name}</Text>
        {doc.pieces.map((p) => {
          const mark = p.state === 'missing' || p.state === 'broken' ? '✗' : p.stale || p.state === 'unchecked' ? '!' : '✓'
          const state = p.redone ? w.redone : p.state !== 'ok' ? w[p.state] : p.stale ? w.stale : w.ok
          return (
            <Box flexDirection="column">
              <Text>{`${mark} ${w.kinds[p.kind] ?? p.kind} · ${p.file} — ${state}`}</Text>
              {p.state === 'broken' ? p.said.filter((l) => /^✗|^\s/.test(l)).slice(0, 3).map((l) => <Text dimColor>{`    ${l.trim()}`}</Text>) : []}
              {p.stale && !p.redone ? <Button key={`r:${p.kind}`} label={doc.armed === p.kind ? w.sure : w.redo} onPress={() => redo($, p.kind)} /> : []}
              {p.state === 'ok' && SHOW[p.kind] ? <Text dimColor>{`    ${w.see}: ${SHOW[p.kind]} ${dirOf(doc.path)}/${p.file}`}</Text> : []}
            </Box>
          )
        })}
        <Text dimColor>{w.page(file)}</Text>
      </Box>
    )
  })
}
