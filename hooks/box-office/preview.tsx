// Feature 3: a pane beside the chat that draws the current recipe's flow (SVG on the
// desktop app, VS Code and mobile; text lines in the terminal) and its validator messages.
// It redraws whenever Claude writes a valid .sim or /sim runs one.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'

import type { PreviewLang } from '../../types'

import { PANE, check, diagLines, knobText, runMetrics, stepKnob } from './core'
import { pathOf } from '../recipes/run'
import { flowSvg, flowText } from './flow-svg'

const last = atom({ plugin: 'house-lights', key: 'last' } as const, null, { shape: 'last-1' })
const lang = atom({ plugin: 'house-lights', key: 'lang' } as const, 'en' as PreviewLang)

/** A control moved on the pane (dir 0 goes back to the recipe's values): the recipe runs again with them, and the
 * numbers stay in the state beside the recipe until it is written again. */
async function move($: EngineInterface, name: string, dir: 1 | -1 | 0) {
  const doc = await read($, last)
  if (!doc) return
  const base = check(doc.src)
  if (!base.ok) return
  const K = base.model.knobs[name]
  const sets: Record<string, number> = dir === 0 ? {} : { ...(doc.sets ?? {}) }
  if (dir !== 0 && K) sets[name] = stepKnob(K, name in sets ? sets[name]! : K.init, dir)
  const c = check(doc.src, sets)
  const r = c.ok ? await runMetrics(() => $.clock.now(), c, undefined, 6000) : undefined
  await update($, last, (x) => (x && x.path === doc.path ? { ...x, sets, rows: r?.rows ?? [] } : x))
}

export function preview(on: On) {
  on('command.run', { command: 'sim-preview' }, async ($, e) => {
    const path = await pathOf($, e.args.trim())
    if (path) {
      const src = await $.fs.read(path).catch(() => undefined)
      if (typeof src !== 'string') return { text: `could not read ${path}` }
      const at = await $.clock.now()
      await update($, last, () => ({ path, src, at }))
    }
    await $.ui.open({ id: PANE, title: 'Process preview' })
    return { text: `preview pane opened.` }
  })

  on('ui.render', { component: 'Pane', requestId: 'box-office-preview' }, async ($, e) => {
    const els = $.ui.resolve(e)
    const { Box, Text, Button } = els
    const doc = await read($, last)
    const locale = await read($, lang)
    if (!doc) {
      return (
        <Box flexDirection="column">
          <Text>No recipe yet.</Text>
          <Text dimColor>Ask Claude to write a .sim file, or run /sim-preview path/to/file.sim</Text>
        </Box>
      )
    }
    const c = check(doc.src, doc.sets ?? {})
    const pt = locale === 'pt-BR'
    const file = doc.path.split('/').pop()
    const head = (
      <Box flexDirection="row" gap={1}>
        <Text bold>{file}</Text>
        <Text dimColor>{pt ? (c.ok ? (c.warnings.length ? `${c.warnings.length} aviso(s)` : 'válida') : `${c.errors.length} erro(s)`) : c.ok ? (c.warnings.length ? `${c.warnings.length} warning(s)` : 'valid') : `${c.errors.length} error(s)`}</Text>
        <Button key="lang" label={locale === 'en' ? 'PT' : 'EN'} onPress={() => update($, lang, l => (l === 'en' ? 'pt-BR' : 'en'))} />
      </Box>
    )
    const sets = doc.sets ?? {}
    const controls = c.ok && c.model.knobOrder.length ? (
      <Box flexDirection="column">
        {c.model.knobOrder.map((k: string) => {
          const K = c.model.knobs[k]
          const v = k in sets ? sets[k]! : K.init
          return (
            <Box flexDirection="row" gap={1}>
              <Button key={`k-:${k}`} label="−" onPress={() => move($, k, -1)} />
              <Button key={`k+:${k}`} label="+" onPress={() => move($, k, 1)} />
              <Text>{`${k} = ${knobText(K, v)}${k in sets ? '' : pt ? ' (da receita)' : ' (recipe)'}`}</Text>
            </Box>
          )
        })}
        {Object.keys(sets).length ? <Button key="k0" label={pt ? 'Voltar à receita' : 'Back to the recipe'} onPress={() => move($, '', 0)} /> : []}
        {(doc.rows ?? []).map((r) => <Text>{r}</Text>)}
      </Box>
    ) : []
    const foot = doc.rows?.length ? [] : <Text dimColor>{pt ? 'Rode /sim para ver os números, ou mexa num controle.' : 'Run /sim for the numbers, or move a control.'}</Text>
    const messages = diagLines(c).map(line => <Text dimColor={line.startsWith('warn')}>{line}</Text>)
    if (!c.ok) {
      return (
        <Box flexDirection="column" gap={1}>
          {head}
          {messages}
        </Box>
      )
    }
    if (e.surface !== 'terminal' && 'Svg' in els && els.Svg) {
      const Svg = els.Svg
      const { svg, width } = flowSvg(c, locale)
      const slot = Math.max(240, (e.props.bodyColumns ?? 60) * 8)
      return (
        <Box flexDirection="column" gap={1}>
          {head}
          <Svg source={svg} alt={`Flow of ${c.model.name}`} width={Math.min(width, slot)} />
          {messages}
          {controls}
          {foot}
        </Box>
      )
    }
    return (
      <Box flexDirection="column" gap={1}>
        {head}
        <Text bold>{c.model.name}</Text>
        {flowText(c, locale).map(line => <Text>{line}</Text>)}
        {messages}
        {controls}
        {foot}
      </Box>
    )
  })
}
