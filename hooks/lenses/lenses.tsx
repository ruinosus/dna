// /lenses: a way of working seen by the other skills — gates-and-handoffs' --lens writes it as a .sim (box-office), a
// .blueprint.yaml (service-blueprint) and a .drill.yaml (dress-rehearsal). The pane shows the three, how many of their
// numbers and lines are bets, and a button to write each beside the way, checked by its own skill. A lens already there
// that differs is never written over at one press: the button asks again, since it may have been edited by hand.
// After it, a .way.yaml Claude writes or edits that has a lens beside it from an earlier version gets a toast.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'

import type { LensItem, LensKind } from '../../types'
import { pathOf, scriptOf } from '../recipes/run'

export const LENS_PANE = 'house-lights-lenses'
const lenses = atom({ plugin: 'house-lights', key: 'lenses' } as const, null, { shape: 'lenses-1' })

const KINDS: LensKind[] = ['sim', 'blueprint', 'drill']
const SKILL: Record<LensKind, string> = { sim: 'box-office', blueprint: 'service-blueprint', drill: 'dress-rehearsal' }
const SHOW: Record<LensKind, string> = { sim: '/sim-preview', blueprint: '/blueprint-preview', drill: '/drill' }
const base = (p: string) => p.replace(/(\.way)?\.ya?ml$/i, '')
export const lensFile = (way: string, kind: LensKind) => `${base(way)}${kind === 'sim' ? '.sim' : kind === 'blueprint' ? '.blueprint.yaml' : '.drill.yaml'}`
const fromLine = (text: string) => /^# from: (.+)$/m.exec(text)?.[1] ?? ''

const W = {
  en: { title: 'The way seen by the other skills', bets: (n: number) => `${n} bet${n === 1 ? '' : 's'} (# bet:) to replace`, write: 'Write beside the way', over: 'Write over it', sure: 'Sure? It may have been edited by hand', same: 'already beside the way, the same', older: (f: string) => `${f} beside it came from an earlier version of the way`, edited: (f: string) => `${f} beside it differs (edited by hand?)`, wrote: (f: string) => `Written: ${f}`, show: (c: string) => `See it: ${c}`, none: 'Run /lenses with a .way.yaml.' },
  pt: { title: 'O fluxo visto pelas outras skills', bets: (n: number) => `${n} ${n === 1 ? 'aposta' : 'apostas'} (# bet:) para trocar`, write: 'Gravar ao lado do way', over: 'Escrever por cima', sure: 'Certeza? Pode ter sido editado à mão', same: 'já está ao lado do way, igual', older: (f: string) => `o ${f} ao lado veio de uma versão anterior do way`, edited: (f: string) => `o ${f} ao lado é diferente (editado à mão?)`, wrote: (f: string) => `Gravado: ${f}`, show: (c: string) => `Para ver: ${c}`, none: 'Rode /lenses com um .way.yaml.' },
}

async function derive($: EngineInterface, way: string, kind: LensKind, lang: 'en' | 'pt', gate?: string): Promise<LensItem> {
  const run = await $.process.run(['node', scriptOf($, 'gates-and-handoffs'), way, '--lens', kind, '--lang', lang, ...(gate ? ['--gate', gate] : [])], { timeoutMs: 3000 })
  const file = lensFile(way, kind)
  if (run.exitCode !== 0) return { kind, file, text: '', bets: 0, state: 'error', said: (run.stderr || run.stdout).trim().split('\n').slice(0, 4) }
  const there = await $.fs.read(file).catch(() => undefined)
  const state = typeof there !== 'string' ? 'new' : there === run.stdout ? 'same' : fromLine(there) !== fromLine(run.stdout) ? 'older' : 'edited'
  return { kind, file, text: run.stdout, bets: Number(/(\d+)/.exec(run.stderr)?.[1] ?? 0), state, said: [] }
}

async function write($: EngineInterface, kind: LensKind) {
  const doc = await read($, lenses)
  const item = doc?.items.find((i) => i.kind === kind)
  if (!doc || !item || item.state === 'error') return
  if ((item.state === 'older' || item.state === 'edited') && !item.armed) {
    await update($, lenses, (x) => (x ? { ...x, items: x.items.map((i) => (i.kind === kind ? { ...i, armed: true } : i)) } : x))
    return
  }
  await $.fs.write(item.file, item.text)
  const check = await $.process.run(['node', scriptOf($, SKILL[kind]), item.file, '--check', ...(kind === 'sim' ? [] : ['--lang', doc.lang])], { timeoutMs: 5000 })
  const said = `${check.stdout}${check.stderr}`.trim().split('\n').filter(Boolean).slice(0, 4)
  await update($, lenses, (x) => (x ? { ...x, items: x.items.map((i) => (i.kind === kind ? { ...i, state: 'same' as const, armed: false, wrote: true, said } : i)) } : x))
}

// a way written or edited: a lens beside it from an earlier version of it is said, once per write
async function stale($: EngineInterface, path: string) {
  if (!/\.way\.ya?ml$/i.test(path)) return
  const behind: string[] = []
  for (const kind of KINDS) {
    const file = lensFile(path, kind)
    const there = await $.fs.read(file).catch(() => undefined)
    if (typeof there !== 'string' || !fromLine(there)) continue
    const item = await derive($, path, kind, 'en')
    if (item.state === 'older') behind.push(file.split('/').pop()!)
  }
  if (behind.length) $.ui.toast(`gates-and-handoffs: ${behind.join(', ')} came from an earlier version of the way — /lenses ${path.split('/').pop()}`)
}

export function lensesCommand(on: On) {
  on('command.run', { command: 'lenses' }, async ($, e) => {
    const args = e.args.trim().split(/\s+/).filter(Boolean)
    const flag = (n: string) => (args.includes(n) ? args[args.indexOf(n) + 1] : undefined)
    const lang = flag('--lang') === 'pt' ? 'pt' : 'en'
    const typed = args.filter((a, i) => !a.startsWith('--') && !['--lang', '--gate'].includes(args[i - 1] ?? ''))[0]
    if (!typed) {
      if (await read($, lenses)) return (await $.ui.open({ id: LENS_PANE, title: 'Lenses' }), { text: 'the lenses are in the pane.' })
      return { text: 'name a way of working, for example /lenses delivery.way.yaml --lang pt' }
    }
    const path = await pathOf($, typed)
    if (!(await $.fs.exists(path))) return { text: `could not read ${typed}: no such file` }
    if (!/\.way\.ya?ml$/i.test(path)) return { text: `${typed} is not a .way.yaml` }
    const items: LensItem[] = []
    for (const kind of KINDS) items.push(await derive($, path, kind, lang, flag('--gate')))
    const broken = items.find((i) => i.state === 'error')
    if (broken && items.every((i) => i.state === 'error')) return { text: `${typed} cannot be seen by the other skills:\n${broken.said.join('\n')}` }
    await update($, lenses, () => ({ path, lang, items }))
    await $.ui.open({ id: LENS_PANE, title: 'Lenses' })
    const text = items.map((i) => `${i.kind}: ${i.state === 'error' ? i.said[0] : `${i.file.split('/').pop()} · ${W[lang].bets(i.bets)}`}`).join('\n')
    return { text, context: [`The person ran /lenses on ${path}. gates-and-handoffs --lens gives:\n${text}\nEach lens is a draft: its # bet: lines are made up and should be replaced with the person's own numbers.`] }
  })

  on('ui.render', { component: 'Pane', requestId: LENS_PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const doc = await read($, lenses)
    if (!doc) return <Text dimColor>{W.en.none}</Text>
    const w = W[doc.lang]
    return (
      <Box flexDirection="column" gap={1}>
        <Text bold>{`${doc.path.split('/').pop()} · ${w.title}`}</Text>
        {doc.items.map((i) => {
          const name = i.file.split('/').pop()!
          if (i.state === 'error') return <Text>{`✗ ${i.kind}: ${i.said[0] ?? ''}`}</Text>
          const note = i.state === 'same' ? w.same : i.state === 'older' ? w.older(name) : i.state === 'edited' ? w.edited(name) : ''
          return (
            <Box flexDirection="column">
              <Text bold>{`${i.kind} · ${name} (${SKILL[i.kind]})`}</Text>
              <Text dimColor>{`${w.bets(i.bets)}${note ? ` · ${note}` : ''}`}</Text>
              {i.state === 'same' && !i.wrote ? [] : i.wrote ? <Text>{w.wrote(i.file)}</Text> : <Button key={`w:${i.kind}`} label={i.armed ? w.sure : i.state === 'new' ? w.write : w.over} onPress={() => write($, i.kind)} />}
              {i.said.map((l) => <Text dimColor>{`  ${l}`}</Text>)}
              {i.wrote || i.state === 'same' ? <Text dimColor>{w.show(`${SHOW[i.kind]} ${name}`)}</Text> : []}
            </Box>
          )
        })}
      </Box>
    )
  })

  on('tool.call', { tool: 'Write' }, async ($, e, next) => {
    const ran = await next(e)
    if (ran && ran.deny === undefined && ran.isError !== true) await stale($, e.file_path).catch(() => undefined)
    return ran
  })
  on('tool.call', { tool: 'Edit' }, async ($, e, next) => {
    const ran = await next(e)
    if (ran && ran.deny === undefined && ran.isError !== true) await stale($, e.file_path).catch(() => undefined)
    return ran
  })
}
