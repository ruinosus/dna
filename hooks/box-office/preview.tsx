// Feature 3: a pane beside the chat that draws the current recipe's flow (SVG on the
// desktop app, VS Code and mobile; text lines in the terminal) and its validator messages.
// It redraws whenever Claude writes a valid .sim or /sim runs one.
import { atom, read, update } from 'claude-code'
import type { On } from 'claude-code'

import type { PreviewLang } from '../../types'

import { PANE, PLUGIN, check, diagLines } from './core'
import { flowSvg, flowText } from './flow-svg'

const last = atom({ plugin: 'house-lights', key: 'last' } as const, null, { shape: 'last-1' })
const lang = atom({ plugin: 'house-lights', key: 'lang' } as const, 'en' as PreviewLang)

export function preview(on: On) {
  on('command.run', { command: 'sim-preview' }, async ($, e) => {
    const path = e.args.trim()
    if (path) {
      const src = await $.fs.read(path).catch(() => undefined)
      if (typeof src !== 'string') return { text: `${PLUGIN}: could not read ${path}` }
      const at = await $.clock.now()
      await update($, last, () => ({ path, src, at }))
    }
    await $.ui.open({ id: PANE, title: 'Process preview' })
    return { text: `${PLUGIN}: preview pane opened.` }
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
    const c = check(doc.src)
    const pt = locale === 'pt-BR'
    const file = doc.path.split('/').pop()
    const head = (
      <Box flexDirection="row" gap={1}>
        <Text bold>{file}</Text>
        <Text dimColor>{pt ? (c.ok ? (c.warnings.length ? `${c.warnings.length} aviso(s)` : 'válida') : `${c.errors.length} erro(s)`) : c.ok ? (c.warnings.length ? `${c.warnings.length} warning(s)` : 'valid') : `${c.errors.length} error(s)`}</Text>
        <Button key="lang" label={locale === 'en' ? 'PT' : 'EN'} onPress={() => update($, lang, l => (l === 'en' ? 'pt-BR' : 'en'))} />
      </Box>
    )
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
          <Text dimColor>{pt ? 'Rode /sim para ver os números.' : 'Run /sim for the numbers.'}</Text>
        </Box>
      )
    }
    return (
      <Box flexDirection="column" gap={1}>
        {head}
        <Text bold>{c.model.name}</Text>
        {flowText(c, locale).map(line => <Text>{line}</Text>)}
        {messages}
        <Text dimColor>{pt ? 'Rode /sim para ver os números.' : 'Run /sim for the numbers.'}</Text>
      </Box>
    )
  })
}
