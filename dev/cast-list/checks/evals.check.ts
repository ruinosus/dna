// The evaluations of Copilot Studio's Evaluate tab, with no model: who, when, how many passed — and nothing of what
// was asked or answered, which is the client's conversation.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { compare } from '../src/compare'
import { evalsFrom, withEvals } from '../src/evals'
import { readCsv } from '../src/tables'
import { examples, found, profile } from './example'
import { done, ok } from './ok'

const dir = join(examples, 'avaliacoes')
const files = readdirSync(dir).sort().map((name) => ({ name: `avaliacoes/${name}`, table: readCsv(readFileSync(join(dir, name), 'utf8'), '') }))
const ev = evalsFrom(files, found)
const of = (id: string) => ev.sets.find((s) => s.agent === id)
ok(of('bodega-pedidos')?.passed === 4 && of('bodega-pedidos')?.total === 4 && of('bodega-pedidos')?.date === '2026-10-30', 'pedidos: 4 of 4, on 2026-10-30, the agent and the date from the file name', of('bodega-pedidos'))
const frete = of('bodega-frete')
ok(frete?.passed === 2 && frete.total === 4 && frete.methods.map((m) => `${m.name}:${m.passed}/${m.total}`).join() === 'GeneralQuality:3/4,CompareMeaning:2/4', 'frete: a row passes when every method passes (2 of 4); each method counted', frete)
ok(!ev.unknown.length && ev.sets.length === 2, 'both files read', ev)
const asExported = evalsFrom([{ name: 'Evaluate Bodega Azul - Pedidos 2026-10-30 (1).csv', table: files[1].table }], found)
ok(asExported.sets[0]?.agent === 'bodega-pedidos' && asExported.sets[0].date === '2026-10-30', 'the name the Evaluate tab gives, with spaces and a copy\'s « (1)», reads the same', asExported)
const odd = evalsFrom([{ name: 'Evaluate Ninguém 2026-10-30.csv', table: files[0].table }, { name: 'Evaluate Bodega Azul - Cupons 2026-10-30.csv', table: { name: '', rows: [['question', 'answer'], ['x', 'y']] } }], found)
ok(odd.sets.length === 0 && odd.unknown.map((u) => u.why).join() === 'who,format', 'a file that names nobody in the folder, and one with no result_1: not understood, never stopping', odd.unknown)
// a test set (what the Evaluate tab imports: prompts and expected answers), as Microsoft's samples ship them: told as
// such, whatever its name — it has no results yet
const sets = evalsFrom([{ name: 'Workday.csv', table: { name: '', rows: [['\uFEFFPrompt', 'Expected response ', 'Test Method Type', 'Passing Score'], ['What is my cost center?', 'Cost center', 'CompareMeaning', '70']] } }], found)
ok(sets.sets.length === 0 && sets.unknown.map((u) => u.why).join() === 'testset', 'a test set with no results: told as a test set, not as a file that names nobody', sets.unknown)
const words = JSON.stringify(ev)
ok(!/Onde está meu pedido|Manaus|saiu para entrega|Seems|Same meaning|Question not answered/.test(words), 'nothing asked, answered or explained is kept', words.slice(0, 300))

// the fact, and the rule that asks for it
const withRule = { ...profile, rules: [...profile.rules, { id: 'eval', role: 'specialist' as const, has: 'eval:*', says: 'Todo especialista passou por uma avaliação' }] }
const r = compare(withEvals(found, ev.sets), withRule, { agents: [], blocks: [], declared: [], decisions: [] })
const gap = r.gaps.find((g) => g.rule.id === 'eval')
ok(r.agents.find((a) => a.id === 'bodega-frete')?.facts['eval:run']?.[0]?.file === 'avaliacoes/evaluate-bodega-azul-frete-2026-10-30.csv' && gap?.agents.sort().join() === 'bodega-cupons,bodega-devolucoes,bodega-loja-fisica', 'eval:run with the file as its source; the rule «eval:*» misses the three with none', [gap, r.agents.find((a) => a.id === 'bodega-frete')?.facts['eval:run']])
done()
