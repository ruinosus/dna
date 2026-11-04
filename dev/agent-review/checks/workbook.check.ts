// The workbook and its way back: the sheets of the spec, in order and in either language; the matrix with who has
// each fact and who is off a pattern; then, read back from the .xlsx as Excel would keep it, nothing changes — and a
// line filled in «Declared» and a decision in «Patterns» come back as two changes that, taken, write the review file.
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
import { plain, wave1 } from './wave1'
import { run } from './example'

const skills = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills')
const examples = join(skills, 'agent-review/examples')
const { readXlsx } = (await import(join(skills, 'agent-review/scripts/read-xlsx.mjs'))) as { readXlsx: (b: Buffer) => SheetRows[] }
const agents = agentsIn(join(examples, 'agents')).map((a) => extractAgent(a.id, a.files))
const profile = plain(readProfile(readFileSync(join(examples, 'team.standard.yaml'), 'utf8')).profile!)
const demoText = readFileSync(join(examples, 'demo.review.yaml'), 'utf8')
const demo = readCast(demoText).cast!
const result = compare(agents, profile, demo)
const sheets = (lang: 'en' | 'pt', r = result, cast: Cast = demo) => workbookOf(r, reviewCast(r), cast, lang)
const back = (lang: 'en' | 'pt') => readXlsx(Buffer.from(workbookFile(sheets(lang))))

// the sheets
const pt = sheets('pt')
ok(pt.map((s) => s.name).join() === 'Resumo,Matriz,Padrões,Texto,Roteamento,Telemetria,Fora do padrão,Lacunas,Conflitos,Sem uso,Agentes,Quadro de pessoal,PDI,Evidências,Declarado', 'the sheets of the spec, in order (pt)', pt.map((s) => s.name))
ok(sheets('en').map((s) => s.name).join() === 'Summary,Matrix,Patterns,Text,Routing,Telemetry,Off pattern,Gaps,Conflicts,Unused,Agents,Staff,Development plan,Evidence,Declared', 'and in English')
const odd = compare([...agents, extractAgent('odd', [{ path: 'agent.mcs.yml', text: 'kind: GptComponentMetadata\n' }, { path: 'a.txt', text: '' }])], profile, demo)
ok(workbookOf(odd, reviewCast(odd), demo, 'pt').at(-1)?.name === 'Não entendeu', '«Not understood» only when something was not')
// the telemetry: each event as written, its form, its fields; with the export, the times
const tsheet = pt.find((s) => s.key === 'telemetry')!
const trow = (agent: string) => tsheet.rows.find((x) => x[0] === agent)?.map((c) => (typeof c === 'object' && c ? (c as { v: unknown }).v : c))
ok(trow('rh-admissao')?.slice(1, 4).join(' | ') === 'rh_admissao_onerror | ‹nome›_OnError | Agente, ErrorMessage, ErrorCode, TimeUTC' && tsheet.columns.length === 5, 'the Telemetry sheet: as written, the form it counts as, its fields (no times without the export)', trow('rh-admissao'))
const fired = { days: 30, file: 't.csv', rows: [{ agent: 'rh-ferias', event: 'RhFerias_OnError', count: 7, line: 2 }, { agent: 'rh-folha', event: 'TopicStart', count: 3, line: 3 }] }
const withTimes = workbookOf(compare(agents, profile, demo, fired), [], demo, 'pt').find((s) => s.key === 'telemetry')!
const times = (agent: string) => withTimes.rows.find((x) => x[0] === agent)?.at(-1)
ok((withTimes.rows[0].at(-1) as { v: string }).v === 'Disparou (30 dias)' && times('rh-ferias') === 7 && (times('rh-folha') as { v: number }).v === 0 && times('rh-admissao') === '—', 'with the export: the times, 0 in red, «—» for who has no line', withTimes.rows)
const summary = pt[0].rows.map((r) => r.map((c) => (typeof c === 'object' ? c.v : c)).join(' | ')).join('\n')
ok(summary.includes('dados do cliente') && summary.includes('não escala para humano (rh-folha)'), 'the summary: what to look at, and that it holds the client’s data', summary)

// the matrix: a column per agent (the orchestrator first), a row per fact, its dimension first
const m = pt[1]
const title = (c: unknown) => (typeof c === 'object' && c ? (c as { v: string }).v : String(c))
const head = m.rows[0].map(title)
ok(head.slice(0, 3).join() === 'Dimensão,Fato,Chave' && head[3] === 'rh-orquestrador' && head.length === 3 + 6, 'the matrix: dimension, fact, key, then the six agents', head)
const row = (key: string) => m.rows.find((r) => title(r[2]) === key)!.map(title)
const folha = head.indexOf('rh-folha')
ok(row('trigger:OnEscalate')[folha] === '×' && row('trigger:OnEscalate')[head.indexOf('rh-ferias')] === '●', 'rh-folha: × on escalation, where the others have ●')
ok(row('mcp:shared_rhadmissaomcp')[head.indexOf('rh-admissao')] === '●' && row('mcp:shared_rhadmissaomcp')[folha] === '', 'a solo: ● for the one, nothing (not ×) for the others')
ok(row('declared:kpi')[head.indexOf('rh-ferias')] === '◐', 'a declared fact: ◐')
ok(title(row('trigger:OnEscalate')[0]) === 'A. Conversa', 'each fact with its dimension')

// patterns: the ones to look at first, the decision filled in
const p = pt[2].rows.map((r) => r.map(title))
ok(p[0].includes('Decisão') && p[0].includes('Por quê') && p[0].includes('Escopo'), 'patterns: scope, decision and why, to fill in')
const decided = p.find((r) => r[0] === 'trigger:OnEscalate')!
ok(decided.includes('aceito') && decided.includes('Ninguém fica sem saída para uma pessoa'), 'the accepted pattern says so', decided)
ok(['trigger:OnEscalate', 'node:LogCustomTelemetryEvent'].includes(p[1][0]) && !p.some((r) => r[0].startsWith('reaches:')) && p.findIndex((r) => r[0] === 'auth:None') > 2, 'the patterns someone is off come first; a part is decided with its fact, not on its own row')

// wave 2: routing, a row per call; what nobody uses; the flow facts in the matrix and the evidence
const sheetRows = (name: string) => pt.find((x) => x.name === name)!.rows.map((r) => r.map(title))
const routing = sheetRows('Roteamento')
ok(routing[0].join() === 'Quem chama,Chamado,Histórico,Entradas,Descrição de roteamento,Caracteres,Arquivo' && routing.length === 1 + 6, 'routing: who calls, who is called, the history, the inputs, the description and its size — a row per call', routing)
const fr = routing.find((r) => r[1] === 'rh-folha')!
ok(fr[2] === 'não' && fr[3] === '' && routing.some((r) => r[1] === 'RH - Mobilidade (não está na pasta)') && routing.find((r) => r[1] === 'rh-admissao')![5] === '9', 'folha with no history nor input; the call to one not in the folder; admissao with 9 characters', routing)
const unusedRows = sheetRows('Sem uso')
ok(unusedRows.length === 1 + 4 && unusedRows.some((r) => r.join() === 'rh-facilities,fluxo,Listar unidades,ninguém usa,workflows/ListarUnidades-3f2a9c1d-5e6f-4a7b-8c9d-0e1f2a3b4c5d/metadata.yml:1') && unusedRows.some((r) => r[0] === 'rh-ferias' && r[1] === 'nó' && r[3] === 'desligado' && r[4].startsWith('topics/Escalate.topic.mcs.yml:')),
  'unused: who, what, the name, how, the file', unusedRows)
ok(row('flow-uses:http:workday.empresa.example')[head.indexOf('rh-ferias')] === '●' && title(row('flow-uses:http:workday.empresa.example')[0]) === 'B. Integrações', 'the flow facts in the matrix, in B')
ok(sheetRows('Evidências').some((r) => r[2] === 'flow-returns' && r[3] === 'workflows/AbrirCasoWorkday-7d1c2a4e-3b5f-4c6d-8e9f-0a1b2c3d4e5f/workflow.json'), 'and in the evidence, with the file')

// the way back: nothing changed, nothing to take — in either language
ok(!fromSheets(demo, back('pt')).changes.length && !fromSheets(demo, back('en')).changes.length && !fromSheets(demo, back('pt')).problems.length, 'read back as written, the workbook changes nothing (pt and en)', fromSheets(demo, back('pt')))

// a person fills a line in «Declared» and accepts telemetry in «Patterns»
const edited = back('pt')
const declared = edited.find((s) => s.name === 'Declarado')!
declared.rows.push(['rh-folha', 'kpi', 'resposta sobre o holerite em menos de 5 s', 'planilha do time'])
const pats = edited.find((s) => s.name === 'Padrões')!
const col = (t: string) => pats.rows[0].indexOf(t)
const tel = pats.rows.find((r) => r[0] === 'node:LogCustomTelemetryEvent')!
tel[col('Decisão')] = 'aceito'
tel[col('Por quê')] = 'Sem telemetria não se mede nada'
const got = fromSheets(demo, edited)
ok(got.changes.length === 2 && !got.problems.length && got.changes.every((c) => /^[dp]\d+$/.test(c.key)), 'two changes, each with its key', got)
const all = applyChanges(demo, got.changes, got.changes.map((c) => c.key))
const written = readCast(writeCast(all, demoText)).cast!
ok(written.declared.some((d) => d.agent === 'rh-folha' && d.key === 'kpi' && d.value === 'resposta sobre o holerite em menos de 5 s' && d.source === 'planilha do time')
  && written.decisions.some((d) => d.key === 'node:LogCustomTelemetryEvent' && d.status === 'accepted' && d.scope === 'platform' && d.why === 'Sem telemetria não se mede nada')
  && written.declared.length === 3 && written.decisions.length === 2, 'taken, exactly what was filled in is written to the review file', written)
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
// wave 1: the types, the blocks of text, and a type scope that comes back
const r1 = compare(agents, wave1(profile), demo)
const s1 = workbookOf(r1, reviewCast(r1), demo, 'pt')
const cells = (key: string) => s1.find((x) => x.key === key)!.rows.map((row) => row.map(title))
const elenco = cells('agents')
ok(elenco[0].includes('Tipos') && elenco.find((row) => row[0] === 'rh-admissao')!.includes('transação · orientação') && elenco.find((row) => row[0] === 'rh-orquestrador')![elenco[0].indexOf('Tipos')] === '', 'the Cast sheet has the types (admissao has two; the orchestrator none)', elenco)
const texto = cells('text')
const links = texto.find((row) => row[0] === 'links')!
ok(texto[0].join() === 'Id,Rótulo,Texto,Quem tem,Variação,Oficial' && links[1] === 'Formatação de links' && links[2].startsWith('Links:') && links[3] === 'rh-admissao, rh-beneficios, rh-facilities, rh-ferias' && links[4].startsWith('rh-folha (') && links[5] === 'sim', 'the Text sheet: id, label, the text, who has it, who has a variation (how alike), official', links)
const mx = cells('matrix')
const linkRow = mx.find((row) => row[2] === 'text:block:links')!
ok(linkRow[mx[0].indexOf('rh-folha')] === '≈' && !mx.some((row) => row[2].endsWith('~variant')), 'the matrix: ≈ for a variation, in the block\'s own row', linkRow)
const pats1 = cells('patterns')
const flow = pats1.find((row) => row[0].startsWith('flow:'))!
ok(flow[pats1[0].indexOf('Escopo')] === 'tipo:transação', 'a type scope reads «tipo:transação»', flow)
// filled in: «aceito» on the help link, scope tipo:orientação → a decision scoped type:guidance
const back1 = readXlsx(Buffer.from(workbookFile(s1)))
const ps1 = back1.find((x) => x.name === 'Padrões')!
const help = ps1.rows.find((row) => row[0] === 'text:link-domain:portal.empresa.example')!
help[ps1.rows[0].indexOf('Decisão')] = 'aceito'
const got1 = fromSheets(demo, back1, r1.typeNames)
const d1 = got1.changes.find((c) => c.kind === 'decision' && c.after?.key === 'text:link-domain:portal.empresa.example')
ok(!got1.problems.length && d1?.kind === 'decision' && d1.after?.scope === 'type:guidance', 'the scope «tipo:orientação» comes back as type:guidance', got1)
ok(!fromSheets(demo, readXlsx(Buffer.from(workbookFile(s1))), r1.typeNames).changes.length, 'read back as written, it still changes nothing')
// the RH in the workbook: each one's situation, and the plan
const rh = run()
const rhSheets = workbookOf(rh.result, rh.looks, rh.cast, 'pt')
const staffSheet = rhSheets.find((s) => s.key === 'staff')!
const pdiSheet = rhSheets.find((s) => s.key === 'pdi')!
const staffRow = (id: string) => staffSheet.rows.find((x) => x[0] === id)?.map((c) => (typeof c === 'object' && c ? (c as { v: unknown }).v : c))
ok(staffSheet.name === 'Quadro de pessoal' && staffRow('rh-admissao')?.[2] === 'sem responsável, em PDI' && staffRow('rh-ferias')?.[2] === 'em dia' && staffRow('rh-folha')?.[4] === 'Squad Folha' && staffRow('rh-folha')?.[8] === 5, 'the Staff sheet: situation, team and plan items of each', [staffRow('rh-admissao'), staffRow('rh-folha')])
ok(pdiSheet.name === 'PDI' && pdiSheet.rows.filter((x) => x[0] === 'rh-folha').length === 5 && pdiSheet.rows.some((x) => x[1] === 'Aprender a encaminhar para uma pessoa'), 'the PDI sheet: a row per item', pdiSheet.rows.slice(0, 3))
ok(!fromSheets(rh.cast, readXlsx(Buffer.from(workbookFile(rhSheets))), rh.result.typeNames).changes.length, 'with the RH sheets, the workbook still reads back as no change')

done()
