// The workbook and its way back: the sheets of the spec, in order and in either language; the matrix with who has
// each fact and who is off a pattern; then, read back from the .xlsx as Excel would keep it, nothing changes — and a
// line filled in «Declared» and a decision in «Patterns» come back as two changes that, taken, write the cast file.
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readCast, writeCast, type Cast } from '../src/cast'
import { compare } from '../src/compare'
import { extractAgent } from '../src/extract'
import { agentsIn } from '../src/folder'
import { applyChanges, fromSheets, type SheetRows } from '../src/fromSheets'
import { readProfile } from '../src/profile'
import { reviewCast } from '../src/review'
import { workbookFile, workbookOf } from '../src/workbook'
import { done, ok } from './ok'

const skills = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills')
const examples = join(skills, 'cast-list/examples')
const { readXlsx } = (await import(join(skills, 'cast-list/scripts/read-xlsx.mjs'))) as { readXlsx: (b: Buffer) => SheetRows[] }
const agents = agentsIn(join(examples, 'agents')).map((a) => extractAgent(a.id, a.files))
const profile = readProfile(readFileSync(join(examples, 'profile.cast.yaml'), 'utf8')).profile!
const demoText = readFileSync(join(examples, 'demo.cast.yaml'), 'utf8')
const demo = readCast(demoText).cast!
const result = compare(agents, profile, demo)
const sheets = (lang: 'en' | 'pt', r = result, cast: Cast = demo) => workbookOf(r, reviewCast(r), cast, lang)
const back = (lang: 'en' | 'pt') => readXlsx(Buffer.from(workbookFile(sheets(lang))))

// the sheets
const pt = sheets('pt')
ok(pt.map((s) => s.name).join() === 'Resumo,Matriz,Padrões,Fora do padrão,Lacunas,Conflitos,Elenco,Evidências,Declarado', 'the sheets of the spec, in order (pt)', pt.map((s) => s.name))
ok(sheets('en').map((s) => s.name).join() === 'Summary,Matrix,Patterns,Off pattern,Gaps,Conflicts,Cast,Evidence,Declared', 'and in English')
const odd = compare([...agents, extractAgent('odd', [{ path: 'agent.mcs.yml', text: 'kind: GptComponentMetadata\n' }, { path: 'a.txt', text: '' }])], profile, demo)
ok(workbookOf(odd, reviewCast(odd), demo, 'pt').at(-1)?.name === 'Não entendeu', '«Not understood» only when something was not')
const summary = pt[0].rows.map((r) => r.map((c) => (typeof c === 'object' ? c.v : c)).join(' | ')).join('\n')
ok(summary.includes('dados do cliente') && summary.includes('não escala para humano (bodega-frete)'), 'the summary: what to look at, and that it holds the client’s data', summary)

// the matrix: a column per agent (the orchestrator first), a row per fact, its dimension first
const m = pt[1]
const title = (c: unknown) => (typeof c === 'object' && c ? (c as { v: string }).v : String(c))
const head = m.rows[0].map(title)
ok(head.slice(0, 3).join() === 'Dimensão,Fato,Chave' && head[3] === 'bodega-orquestrador' && head.length === 3 + 6, 'the matrix: dimension, fact, key, then the six agents', head)
const row = (key: string) => m.rows.find((r) => title(r[2]) === key)!.map(title)
const frete = head.indexOf('bodega-frete')
ok(row('trigger:OnEscalate')[frete] === '×' && row('trigger:OnEscalate')[head.indexOf('bodega-pedidos')] === '●', 'bodega-frete: × on escalation, where the others have ●')
ok(row('mcp:shared_bodegapromocoesmcp')[head.indexOf('bodega-cupons')] === '●' && row('mcp:shared_bodegapromocoesmcp')[frete] === '', 'a solo: ● for the one, nothing (not ×) for the others')
ok(row('declared:kpi')[head.indexOf('bodega-pedidos')] === '◐', 'a declared fact: ◐')
ok(title(row('trigger:OnEscalate')[0]) === 'A. Conversa', 'each fact with its dimension')

// patterns: the ones to look at first, the decision filled in
const p = pt[2].rows.map((r) => r.map(title))
ok(p[0].includes('Decisão') && p[0].includes('Por quê') && p[0].includes('Escopo'), 'patterns: scope, decision and why, to fill in')
const decided = p.find((r) => r[0] === 'trigger:OnEscalate')!
ok(decided.includes('aceito') && decided.includes('Ninguém fica sem saída para uma pessoa'), 'the accepted pattern says so', decided)
ok(['trigger:OnEscalate', 'node:LogCustomTelemetryEvent', 'calls:topic:Escalate'].includes(p[1][0]) && p.findIndex((r) => r[0] === 'auth:None') > 3, 'the patterns someone is off come first')

// the way back: nothing changed, nothing to take — in either language
ok(!fromSheets(demo, back('pt')).changes.length && !fromSheets(demo, back('en')).changes.length && !fromSheets(demo, back('pt')).problems.length, 'read back as written, the workbook changes nothing (pt and en)', fromSheets(demo, back('pt')))

// a person fills a line in «Declared» and accepts telemetry in «Patterns»
const edited = back('pt')
const declared = edited.find((s) => s.name === 'Declarado')!
declared.rows.push(['bodega-frete', 'kpi', 'cotação em menos de 5 s', 'planilha do time'])
const pats = edited.find((s) => s.name === 'Padrões')!
const col = (t: string) => pats.rows[0].indexOf(t)
const tel = pats.rows.find((r) => r[0] === 'node:LogCustomTelemetryEvent')!
tel[col('Decisão')] = 'aceito'
tel[col('Por quê')] = 'Sem telemetria não se mede nada'
const got = fromSheets(demo, edited)
ok(got.changes.length === 2 && !got.problems.length && got.changes.every((c) => /^[dp]\d+$/.test(c.key)), 'two changes, each with its key', got)
const all = applyChanges(demo, got.changes, got.changes.map((c) => c.key))
const written = readCast(writeCast(all, demoText)).cast!
ok(written.declared.some((d) => d.agent === 'bodega-frete' && d.key === 'kpi' && d.value === 'cotação em menos de 5 s' && d.source === 'planilha do time')
  && written.decisions.some((d) => d.key === 'node:LogCustomTelemetryEvent' && d.status === 'accepted' && d.scope === 'platform' && d.why === 'Sem telemetria não se mede nada')
  && written.declared.length === 3 && written.decisions.length === 2, 'taken, exactly what was filled in is written to the cast file', written)
const one = applyChanges(demo, got.changes, [got.changes[0].key])
ok(one.declared.length + one.decisions.length === 4, 'taking one key takes only that change')

// a decision cleared and a declared line deleted are changes too; a decision that is not one is a problem
const cleared = back('pt')
const pc = cleared.find((s) => s.name === 'Padrões')!
pc.rows.find((r) => r[0] === 'trigger:OnEscalate')![pc.rows[0].indexOf('Decisão')] = ''
const dc = cleared.find((s) => s.name === 'Declarado')!
dc.rows = dc.rows.filter((r) => r[1] !== 'kpi')
const c2 = fromSheets(demo, cleared)
const after = applyChanges(demo, c2.changes, c2.changes.map((c) => c.key))
ok(c2.changes.length === 2 && !after.decisions.length && after.declared.length === 1, 'a decision cleared and a line deleted: two changes, and they take it away', c2)
const wrong = back('pt')
const pw = wrong.find((s) => s.name === 'Padrões')!
pw.rows.find((r) => r[0] === 'node:LogCustomTelemetryEvent')![pw.rows[0].indexOf('Decisão')] = 'talvez'
ok(fromSheets(demo, wrong).problems.some((x) => x.includes('talvez')), 'a decision that is not aceito/rejeitado is told', fromSheets(demo, wrong).problems)
done()
