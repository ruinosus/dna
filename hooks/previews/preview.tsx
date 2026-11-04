// The recipes' preview: a pane beside the chat with the last way of working or service blueprint Claude wrote (or one
// named to /way-preview, /blueprint-preview), as its skill's check read it — an SVG on the desktop app, VS Code and the
// phone, text lines in the terminal — with what to look at, and the EN/PT switch the .sim preview shares.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'

import type { PreviewLang } from '../../types'
import { checkRecipe, recipeOf, showRecipe } from '../recipes/guard'
import { PLUGIN } from '../recipes/text'
import { PREVIEW_PANE, blueprintSvg, blueprintText, lookWord, waySvg, wayText } from './draw'

const recipe = atom({ plugin: 'house-lights', key: 'recipe' } as const, null, { shape: 'recipe-1' })
const lang = atom({ plugin: 'house-lights', key: 'lang' } as const, 'en' as PreviewLang)

/** /way-preview and /blueprint-preview: check the named file (or show the last one) and open the pane. */
async function open($: EngineInterface, path: string, kind: 'way' | 'blueprint') {
  if (path) {
    const text = await $.fs.read(path).catch(() => undefined)
    if (typeof text !== 'string') return { text: `${PLUGIN}: could not read ${path}` }
    const r = recipeOf(path, text)
    if (!r || r.kind !== kind) return { text: `${PLUGIN}: ${path} is not a ${kind === 'way' ? '.way.yaml' : '.blueprint.yaml'}` }
    const checked = await checkRecipe($, path, text, r).catch(() => undefined)
    if (!checked) return { text: `${PLUGIN}: ${r.skill}'s check could not run (is node on the PATH?)` }
    if (checked.problems.length) return { text: `${PLUGIN}: ${path} has errors:\n${checked.problems.join('\n')}` }
    await showRecipe($, path, kind, checked.read)
  }
  await $.ui.open({ id: PREVIEW_PANE, title: kind === 'way' ? 'Way of working' : 'Service blueprint' })
  return { text: `${PLUGIN}: preview pane opened.` }
}

export function recipePreview(on: On) {
  on('command.run', { command: 'way-preview' }, async ($, e) => open($, e.args.trim(), 'way'))
  on('command.run', { command: 'blueprint-preview' }, async ($, e) => open($, e.args.trim(), 'blueprint'))

  on('ui.render', { component: 'Pane', requestId: PREVIEW_PANE }, async ($, e) => {
    const els = $.ui.resolve(e)
    const { Box, Text, Button } = els
    const doc = await read($, recipe)
    const locale = await read($, lang)
    if (!doc) {
      return (
        <Box flexDirection="column">
          <Text>{locale === 'pt-BR' ? 'Nenhuma receita ainda.' : 'No recipe yet.'}</Text>
          <Text dimColor>{locale === 'pt-BR' ? 'Peça ao Claude um .way.yaml ou .blueprint.yaml, ou rode /way-preview arquivo' : 'Ask Claude for a .way.yaml or .blueprint.yaml, or run /way-preview file'}</Text>
        </Box>
      )
    }
    const data: any = doc.read
    const looks: { en: string; pt: string }[] = Array.isArray(data?.looks) ? data.looks : []
    const head = (
      <Box flexDirection="row" gap={1}>
        <Text bold>{doc.path.split('/').pop()}</Text>
        <Text dimColor>{lookWord(looks.length, locale)}</Text>
        <Button key="lang" label={locale === 'en' ? 'PT' : 'EN'} onPress={() => update($, lang, (l) => (l === 'en' ? 'pt-BR' : 'en'))} />
      </Box>
    )
    const notes = looks.slice(0, 3).map((l) => <Text dimColor>{`! ${locale === 'pt-BR' ? l.pt : l.en}`}</Text>)
    const drawn = doc.kind === 'way' ? (e.surface === 'terminal' ? undefined : waySvg(data.way, data.name ?? '', locale)) : e.surface === 'terminal' ? undefined : blueprintSvg(data.blueprint, locale)
    if (drawn && 'Svg' in els && els.Svg) {
      const Svg = els.Svg
      const slot = Math.max(240, (e.props.bodyColumns ?? 60) * 8)
      return (
        <Box flexDirection="column" gap={1}>
          {head}
          <Svg source={drawn.svg} alt={doc.kind === 'way' ? 'The way of working: its stages in lanes, and its gates' : 'The service blueprint: its moments, on stage and behind'} width={Math.min(drawn.width, slot)} />
          {notes}
        </Box>
      )
    }
    const lines = doc.kind === 'way' ? wayText(data.way, data.name ?? '', locale) : blueprintText(data.blueprint, locale)
    return (
      <Box flexDirection="column" gap={1}>
        {head}
        {lines.map((l) => <Text>{l}</Text>)}
        {notes}
      </Box>
    )
  })
}
