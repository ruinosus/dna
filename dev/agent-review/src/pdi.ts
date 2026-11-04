// The development plan (PDI) of each one of the cast, with no model: what «to look at» says about one alone, written as
// an action. One item per fact (a handoff's claim and the pattern about the same fact are one), the inputs the
// orchestrator does not pass in one call as one, in the order of the groups; what is the team's call (a solo, a type
// with one, a marker set in ways across the cast) or was not understood is not anyone's plan.
import type { Result } from './compare'
import { formText, labelOf, type Lang } from './labels'
import type { Look } from './review'

export type PdiGroup = 'contradictions' | 'contract' | 'off' | 'rules' | 'text' | 'telemetry' | 'cleanup'
export const PDI_GROUPS: PdiGroup[] = ['contradictions', 'contract', 'off', 'rules', 'text', 'telemetry', 'cleanup']
export interface PdiItem {
  agent: string
  group: PdiGroup
  /** The facts it is about. */
  keys: string[]
  en: string
  pt: string
  /** What «to look at» said: the evidence. */
  why: { en: string; pt: string }
}

const isTelemetry = (l: Look) => l.key === 'spelling' || l.key === 'telemetry' || !!l.fact?.startsWith('telemetry:') || l.fact === 'node:LogCustomTelemetryEvent'
function groupOf(l: Look): PdiGroup | undefined {
  if (l.key === 'conflict' || l.key === 'contradiction') return 'contradictions'
  if (isTelemetry(l)) return 'telemetry'
  if (l.key === 'contract' || l.key === 'flow' || (l.key === 'off' && l.fact?.startsWith('called-with:'))) return 'contract'
  if (l.key === 'off') return 'off'
  if (l.key === 'gap') return 'rules'
  if (l.key === 'twice') return 'text'
  if (l.key === 'unused') return 'cleanup'
  return undefined // values, solo, type, unknown, unmatched: the team's call, or nobody's
}

// the first «…» of a sentence: the name «to look at» already gives
const quoted = (s: string) => /«([^»]*)»/.exec(s)?.[1] ?? ''
type Two = { en: string; pt: string }

/** What to do, for one look of one agent. */
function action(l: Look, agent: string, r: Result): Two {
  const label = (lang: Lang) => labelOf(l.fact ?? '', lang, r.names)
  const f = l.fact ?? ''
  if (f === 'trigger:OnEscalate') return { en: 'Learn to hand over to a person', pt: 'Aprender a encaminhar para uma pessoa' }
  if (l.key === 'contradiction') return { en: `Remove «${label('en')}»`, pt: `Tirar «${label('pt')}»` }
  if (l.key === 'contract' && f.startsWith('calls:')) {
    const name = quoted(l.en)
    return { en: `Bring «${name}» into the folder, or remove the call`, pt: `Trazer «${name}» para a pasta, ou tirar a chamada` }
  }
  if (f === 'routing:described') return { en: 'Write the routing description: what it solves', pt: 'Escrever a descrição de roteamento: o que ele resolve' }
  if (l.key === 'flow') {
    const name = quoted(l.en)
    return { en: `Make the flow «${name}» return its result`, pt: `Fazer o fluxo «${name}» devolver o resultado` }
  }
  if (l.key === 'spelling') return { en: `Name the event like the others: «${formText(f.slice('telemetry:event:'.length), 'en')}»`, pt: `Chamar o evento como os outros: «${formText(f.slice('telemetry:event:'.length), 'pt')}»` }
  if (l.key === 'telemetry' && !f) return { en: 'Connect the telemetry to Application Insights', pt: 'Ligar a telemetria ao Application Insights' }
  if (l.key === 'telemetry') {
    const name = quoted(l.en)
    return { en: `Check that the event «${name}» fires`, pt: `Conferir se o evento «${name}» dispara` }
  }
  if (f.startsWith('telemetry:field:')) {
    const [form, field] = f.slice('telemetry:field:'.length).split('/')
    return { en: `Log «${field}» in the event «${formText(form, 'en')}»`, pt: `Registrar «${field}» no evento «${formText(form, 'pt')}»` }
  }
  if (f === 'node:LogCustomTelemetryEvent') return { en: 'Log telemetry', pt: 'Registrar telemetria' }
  if (f.startsWith('text:block:') && r.offPattern.some((o) => o.agent === agent && o.key === f && o.variant)) return { en: `Align the official block «${label('en')}»`, pt: `Alinhar o bloco oficial «${label('pt')}»` }
  if (f.startsWith('text:block:')) return { en: `Use the official block «${label('en')}»`, pt: `Usar o bloco oficial «${label('pt')}»` }
  if (f === 'declared:kpi') return { en: 'Declare a goal (KPI)', pt: 'Declarar uma meta (KPI)' }
  if (l.key === 'twice') return { en: `Settle on one «${label('en')}»`, pt: `Escolher um só «${label('pt')}»` }
  if (l.key === 'unused') {
    const u = r.unused.find((x) => x.agent === agent && x.key === f)
    if (u?.how === 'disabled' && f.startsWith('disabled:node:')) {
      const place = (u.sources[0]?.file ?? '').replace(/(\.topic)?\.mcs\.ya?ml$/, '')
      return { en: `Remove the switched-off node in «${place}»`, pt: `Remover o nó desligado em «${place}»` }
    }
    const kind = f.split(':')[1]
    const name = u?.name ?? quoted(l.en)
    if (kind === 'variable') return { en: `Remove the variable «${name}»`, pt: `Remover a variável «${name}»` }
    const what: Record<string, Two> = { flow: { en: 'the flow', pt: 'o fluxo' }, topic: { en: 'the topic', pt: 'o tópico' }, action: { en: 'the tool', pt: 'a ferramenta' }, knowledge: { en: 'the knowledge source', pt: 'a fonte de conhecimento' } }
    const w = what[kind] ?? { en: '', pt: '' }
    return { en: `Remove or switch on ${w.en} «${name}»`.replace('  ', ' '), pt: `Remover ou ligar ${w.pt} «${name}»`.replace('  ', ' ') }
  }
  if (l.key === 'conflict') return { en: `Check «${label('en')}» against what was declared`, pt: `Conferir «${label('pt')}» com o declarado` }
  return { en: `Have «${label('en')}»`, pt: `Ter «${label('pt')}»` }
}

/** Each one's plan, in the order of the cast and, within each, of the groups. */
export function pdiOf(looks: Look[], r: Result): PdiItem[] {
  const out: PdiItem[] = []
  for (const l of looks) {
    const group = groupOf(l)
    if (!group) continue
    for (const agent of l.agents) {
      const mine = out.filter((p) => p.agent === agent)
      // a handoff's claim and the pattern, about the same fact: one item, where it came first
      if (l.fact && mine.some((p) => p.keys.includes(l.fact!))) continue
      // what the orchestrator does not pass in one call: one item
      if (l.fact?.startsWith('called-with:')) {
        const call = mine.find((p) => p.keys.some((k) => k.startsWith('called-with:')))
        const item = call ?? { agent, group, keys: [], en: '', pt: '', why: { en: '', pt: '' } }
        if (!call) out.push(item)
        item.keys.push(l.fact)
        const what = item.keys.map((k) => (k === 'called-with:history' ? { en: 'the conversation history', pt: 'o histórico da conversa' } : { en: `«${k.slice('called-with:input:'.length)}»`, pt: `«${k.slice('called-with:input:'.length)}»` }))
        const and = (lang: Lang) => what.map((w) => w[lang]).join(lang === 'pt' ? ' e ' : ' and ')
        item.en = `Receive ${and('en')} from the orchestrator`
        item.pt = `Receber do gestor ${and('pt')}`
        item.why = { en: `${item.why.en} ${l.en}`.trim(), pt: `${item.why.pt} ${l.pt}`.trim() }
        continue
      }
      out.push({ agent, group, keys: l.fact ? [l.fact] : [], ...action(l, agent, r), why: { en: l.en, pt: l.pt } })
    }
  }
  const order = [...new Set(r.agents.map((a) => a.id))]
  return out.sort((a, b) => order.indexOf(a.agent) - order.indexOf(b.agent) || PDI_GROUPS.indexOf(a.group) - PDI_GROUPS.indexOf(b.group))
}
