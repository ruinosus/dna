// /drill: an incident drill of incident-drill, played in a pane beside the chat — the clock, the scene, who is in the
// room, the choices and who to call as buttons — and at the end the debrief, which can be saved beside the drill. The
// drill is read by incident-drill's own check (--check --json); the game is played here with the same pure functions
// the drill's page and its checks use (dev/incident-drill/src/play.ts, built into hooks/drill/play.js). The game is kept in the session's state, so
// closing the pane and opening it again (/drill) goes on where it was.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'

import type { DrillDoc } from '../../types'
import { call, canDo, choose, clockAt, debrief, startPlay } from './play.js'
import { pathOf, scriptOf } from '../recipes/run'

export const DRILL_PANE = 'dna-drill'
const game = atom({ plugin: 'dna', key: 'drill' } as const, null, { shape: 'drill-1' })

const W = {
  en: { room: 'In the room', call: 'Call', needs: 'needs', lost: (n: number, u: string) => `${n} ${u}`, debrief: 'Debrief', resolved: 'To resolve', told: 'To tell the people affected', notHappened: 'did not happen', gaps: 'What the runbook did not say', again: 'Play again', save: 'Save the debrief', saved: (f: string) => `Saved: ${f}`, none: 'Run /drill with a .drill.yaml.', ended: { resolved: 'Resolved', worse: 'It got worse' } },
  pt: { room: 'Na sala', call: 'Chamar', needs: 'precisa de', lost: (n: number, u: string) => `${n} ${u}`, debrief: 'Debrief', resolved: 'Até resolver', told: 'Até avisar os afetados', notHappened: 'não aconteceu', gaps: 'O que o runbook não dizia', again: 'Jogar de novo', save: 'Salvar o debrief', saved: (f: string) => `Salvo: ${f}`, none: 'Rode /drill com um .drill.yaml.', ended: { resolved: 'Resolvido', worse: 'Piorou' } },
}

/** The debrief's file, beside the drill: checkout.drill.yaml → checkout.debrief.md. */
export const debriefFile = (path: string) => path.replace(/(\.drill)?\.(ya?ml|json)$/i, '') + '.debrief.md'

async function start($: EngineInterface, path: string, lang: 'en' | 'pt') {
  const run = await $.process.run(['node', scriptOf($, 'incident-drill'), path, '--check', '--json', '--lang', lang], { timeoutMs: 7000 })
  if (run.exitCode !== 0) return { error: (run.stderr || run.stdout).trim().split('\n').slice(0, 8).join('\n') }
  const readIt = JSON.parse(run.stdout)
  return { doc: { path, lang, read: readIt, play: startPlay(readIt.drill, lang), then: '', saved: '' } as DrillDoc }
}

export function drillGame(on: On) {
  on('command.run', { command: 'drill' }, async ($, e) => {
    const args = e.args.trim().split(/\s+/).filter(Boolean)
    const lang = args.includes('--lang') && args[args.indexOf('--lang') + 1] === 'pt' ? 'pt' : 'en'
    const typed = args.filter((a, i) => !a.startsWith('--') && args[i - 1] !== '--lang')[0]
    if (typed) {
      const path = await pathOf($, typed)
      if (!(await $.fs.exists(path))) return { text: `could not read ${typed}: no such file` }
      const r = await start($, path, lang).catch((err) => ({ error: String(err) }))
      if ('error' in r) return { text: `${path} cannot be played:\n${r.error}` }
      await update($, game, () => r.doc)
    } else if (!(await read($, game))) return { text: `name a drill, for example /drill checkout.drill.yaml --lang pt` }
    await $.ui.open({ id: DRILL_PANE, title: 'Incident drill' })
    return { text: `the drill is in the pane.` }
  })

  on('ui.render', { component: 'Pane', requestId: DRILL_PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const doc = await read($, game)
    if (!doc) return <Text dimColor>{W.en.none}</Text>
    const w = W[doc.lang]
    const d = doc.read.drill
    const play = doc.play
    const scene = d.scenes.find((s: any) => s.id === play.scene)
    const roleName = (id: string) => d.roles.find((r: any) => r.id === id)?.name ?? id
    const head = (
      <Box flexDirection="column">
        <Text bold>{d.name}</Text>
        <Text dimColor>{`${clockAt(d, play.minute)} · ${w.lost(play.lost, d.impact ?? '')} · ${w.room}: ${play.room.map(roleName).join(', ')}`}</Text>
      </Box>
    )
    if (play.ended) {
      const b = debrief(d, play, doc.read.looks, doc.lang)
      const min = (n?: number) => (n === undefined ? w.notHappened : `${n} min`)
      return (
        <Box flexDirection="column" gap={1}>
          {head}
          <Text bold>{`${w.ended[play.ended]} · ${w.debrief}`}</Text>
          <Text>{`${w.resolved}: ${min(b.numbers.resolved)} · ${w.told}: ${min(b.numbers.told)} · ${w.lost(b.numbers.lost, d.impact ?? '')}`}</Text>
          <Box flexDirection="column">{b.timeline.map((t) => <Text dimColor>{`${t.at} — ${t.text}`}</Text>)}</Box>
          <Text bold>{w.gaps}</Text>
          <Box flexDirection="column">{b.gaps.map((g) => <Text>{`- ${g.says} (${g.source})`}</Text>)}</Box>
          <Box flexDirection="row" gap={1}>
            <Button key="again" label={w.again} onPress={() => update($, game, (x) => (x ? { ...x, play: startPlay(x.read.drill, x.lang), then: '', saved: '' } : x))} />
            <Button key="save" label={w.save} onPress={async () => {
              const cur = await read($, game)
              if (!cur) return
              const file = debriefFile(cur.path)
              await $.fs.write(file, debrief(cur.read.drill, cur.play, cur.read.looks, cur.lang).markdown)
              await update($, game, (x) => (x ? { ...x, saved: file } : x))
            }} />
          </Box>
          {doc.saved ? <Text dimColor>{w.saved(doc.saved)}</Text> : []}
        </Box>
      )
    }
    const choices: any[] = scene?.choices ?? []
    const outside = d.roles.filter((r: any) => !play.room.includes(r.id))
    return (
      <Box flexDirection="column" gap={1}>
        {head}
        <Text>{scene?.says ?? ''}</Text>
        {(scene?.injects ?? []).map((i: any) => <Text dimColor>{`${i.at ? `${i.at} ` : ''}${i.says}`}</Text>)}
        {doc.then ? <Text dimColor>{doc.then}</Text> : []}
        <Box flexDirection="column">
          {choices.map((c, i) => (
            <Button key={`c:${i}`} label={`${c.label}${c.runbook ? ` (${c.runbook})` : ''}${canDo(d, play, c) ? '' : ` — ${w.needs} «${c.needs}»`}`} onPress={() => update($, game, (x) => (x ? { ...x, play: choose(x.read.drill, x.play, i, x.lang), then: x.read.drill.scenes.find((s: any) => s.id === x.play.scene)?.choices?.[i]?.then ?? '' } : x))} />
          ))}
        </Box>
        {outside.length ? (
          <Box flexDirection="row" gap={1}>
            {outside.map((r: any) => <Button key={`r:${r.id}`} label={`${w.call} ${r.name}`} onPress={() => update($, game, (x) => (x ? { ...x, play: call(x.read.drill, x.play, r.id, x.lang) } : x))} />)}
          </Box>
        ) : []}
      </Box>
    )
  })
}
