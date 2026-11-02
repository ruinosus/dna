// The lesson: a scene the drawing engine takes, in five chapters (the cast, what repeats, who is off, what is missing,
// what to decide); every agent drawn by name; a red × for each one off a pattern and nobody else; nothing off the
// paper; the screen words never say «agent»; and many agents fit (two rows past a row's room).
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { validateScene } from '@lib/drawing/recipe'
import { readCast, type Cast } from '../src/cast'
import { compare } from '../src/compare'
import { extractAgent, type AgentFacts } from '../src/extract'
import { agentsIn } from '../src/folder'
import { lessonOf } from '../src/lesson'
import { readProfile } from '../src/profile'
import { reviewCast } from '../src/review'
import { done, ok } from './ok'
import { plain, wave1 } from './wave1'

const examples = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/cast-list/examples')
const agents = agentsIn(join(examples, 'agents')).map((a) => extractAgent(a.id, a.files))
const profile = plain(readProfile(readFileSync(join(examples, 'profile.cast.yaml'), 'utf8')).profile!)
const demo = readCast(readFileSync(join(examples, 'demo.cast.yaml'), 'utf8')).cast!
type Step = { type: string; chapter?: string; say?: string; text?: string; at?: [number, number]; from?: [number, number]; to?: [number, number]; name?: string }
const sceneOf = (as: AgentFacts[], cast: Cast, lang: 'en' | 'pt') => {
  const r = compare(as, profile, cast)
  return validateScene(lessonOf(r, reviewCast(r), lang)) as unknown as { width: number; height: number; steps: Step[] }
}

const s = sceneOf(agents, demo, 'pt')
const chapters = s.steps.filter((x) => x.chapter).map((x) => x.chapter)
ok(chapters.join() === 'O elenco,O que se repete,Quem está fora,O que falta,O que decidir', 'five chapters, in order', chapters)
const texts = s.steps.filter((x) => x.type === 'text').map((x) => x.text!)
ok(agents.every((a) => texts.some((t) => t.includes(a.id) || a.id.startsWith(t))), 'every agent drawn by name', texts)
ok(s.steps.filter((x) => x.type === 'prop' && x.name === 'robot').length === 6, 'six robots on the paper')
ok(s.steps.filter((x) => x.type === 'arrow').length === 5, 'the orchestrator calls five')
const crosses = s.steps.filter((x) => x.type === 'text' && x.text === '×')
ok(crosses.length === 2, 'a red × for bodega-frete and bodega-loja-fisica, nobody else', crosses)
const red = s.steps.filter((x) => x.type === 'text' && x.text !== '×' && (x as { style?: { color?: string } }).style?.color === '#C8442C').map((x) => x.text).join(' ')
ok(red.includes('não escala para humano') && red.includes('não registra telemetria'), 'why each one is off, under it (the lines of the drawing read together)', red)
const all = texts.join(' ')
ok(all.includes('«Todo especialista tem KPI»: 4 especialistas não') && all.includes('cumprem'), 'what is missing: the KPI rule, in a few words and whole', all)
const repeats = texts.slice(texts.indexOf('O que se repete') + 1)
ok(['Escalonamento', 'Tratamento de erro', 'Registra telemetria', 'Tem instruções'].some((t) => repeats[0].includes(t)), 'what repeats: a behaviour first, not a setting', repeats.slice(0, 3))
// the items of a column: their first lines start at the column's left edge; a wrapped line is indented
const column = (title: string) => {
  const head = s.steps.find((x) => x.type === 'text' && x.text === title)!
  const next = s.steps.filter((x) => x.type === 'text' && x.at && x.at[0] === head.at![0] && x.at[1] > head.at![1] && x.text!.startsWith('· '))
  return next.map((x) => x.text!)
}
ok(all.includes('Registra telemetria') && column('O que decidir').some((t) => t.includes('sem uso')) && column('O que decidir').at(-1)!.startsWith('· e mais'), 'what to decide: what nobody uses, the patterns in the open, the solos on the map', column('O que decidir'))
ok(column('O que falta').some((t) => t.includes('O orquestrador chama')) && column('O que falta').some((t) => t.includes('descrição de roteamento')) && column('O que falta').some((t) => t.includes('O fluxo')), 'what is missing: the contract and the flow that returns nothing', column('O que falta'))
const repeated = column('O que se repete')
ok(repeated.length === 6 && repeated.at(-1) === '· e mais 20 no mapa', 'what repeats: five, then «e mais N no mapa»', repeated)
ok(column('O que decidir').length <= 6, 'what to decide: five at most, the rest on the map', column('O que decidir'))
const says = s.steps.filter((x) => x.say).map((x) => x.say!)
ok(says.length >= 5 && says[0].includes('1 orquestrador') && says[0].includes('5 especialistas'), 'narrated, from the first chapter', says)
const inside = (p?: [number, number]) => !p || (p[0] >= 0 && p[0] <= s.width && p[1] >= 0 && p[1] <= s.height)
ok(s.steps.every((x) => inside(x.at) && inside(x.from) && inside(x.to)), 'nothing off the paper')
ok(![...texts, ...says].some((t) => /\bagentes?\b/i.test(t)), 'the screen words never say «agent»', [...texts, ...says].filter((t) => /agente/i.test(t)))
const en = sceneOf(agents, demo, 'en')
ok(en.steps.filter((x) => x.chapter).map((x) => x.chapter).join() === 'The cast,What repeats,Who is off,What is missing,What to decide' && !en.steps.some((x) => /\bagents?\b/i.test(`${x.text ?? ''} ${x.say ?? ''}`)), 'and in English')

// thirty specialists: two rows, still on a paper the engine takes
const many = Array.from({ length: 30 }, (_, i) => ({ ...agents.find((a) => a.id === 'bodega-pedidos')!, id: `especialista-${String(i + 1).padStart(2, '0')}` }))
const big = sceneOf([agents.find((a) => a.id === 'bodega-orquestrador')!, ...many], { agents: [], blocks: [], declared: [], decisions: [] }, 'pt')
const rows = new Set(big.steps.filter((x) => x.type === 'prop' && x.name === 'robot').map((x) => x.at![1]))
ok(big.width <= 4000 && rows.size === 3, `thirty-one: the orchestrator and two rows (${big.width} wide)`, [...rows])
// wave 1: the cast drawn by type — each specialist once, under its first type's name
const r1 = compare(agents, wave1(profile), demo)
const t1 = validateScene(lessonOf(r1, reviewCast(r1), 'pt')) as unknown as { width: number; height: number; steps: Step[] }
const robots = t1.steps.filter((x) => x.type === 'prop' && x.name === 'robot')
ok(robots.length === 6, 'six robots: cupons, with two types, is drawn once')
const textAt = (t: string) => t1.steps.find((x) => x.type === 'text' && x.text === t)
const nameX = (id: string) => textAt(id)?.at?.[0] ?? -1
const [tr, gd, tg] = ['transação', 'orientação', 'triagem'].map(textAt)
ok(!!tr && !!gd && !!tg, 'the types named over their groups', t1.steps.filter((x) => x.type === 'text').map((x) => x.text).slice(0, 14))
ok(nameX('bodega-cupons') < nameX('bodega-loja-fisica') && nameX('bodega-pedidos') < nameX('bodega-loja-fisica') && nameX('bodega-loja-fisica') < nameX('bodega-frete'), 'transação first (cupons, devolucoes, pedidos), then orientação, then triagem')
ok(tr!.at![0] > nameX('bodega-cupons') && tr!.at![0] < nameX('bodega-pedidos') && Math.abs(gd!.at![0] - nameX('bodega-loja-fisica')) < 1 && Math.abs(tg!.at![0] - nameX('bodega-frete')) < 1, 'each type name centred over its group')
const arrowsEnd = Math.max(...t1.steps.filter((x) => x.type === 'arrow').map((x) => x.to![1]))
ok(arrowsEnd < tr!.at![1] - 10, 'the arrows stop above the type names: no line through a word', [arrowsEnd, tr!.at![1]])
const inside1 = (p?: [number, number]) => !p || (p[0] >= 0 && p[0] <= t1.width && p[1] >= 0 && p[1] <= t1.height)
ok(t1.steps.every((x) => inside1(x.at) && inside1(x.from) && inside1(x.to)), 'nothing off the paper, with the types')
ok(!s.steps.some((x) => x.type === 'text' && ['transação', 'orientação', 'triagem'].includes(x.text!)), 'with no types in the profile, no type names')
const w1all = t1.steps.filter((x) => x.type === 'text').map((x) => x.text).join(' ')
ok(w1all.includes('unificar?') && w1all.includes('qual vale?'), 'what to decide: «unify?» and «which one holds?» come in it', w1all)
done()
