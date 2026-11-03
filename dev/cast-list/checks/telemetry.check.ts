// Wave 3: the telemetry events by name — their form (the agent's own name taken out) and the fields of their record —
// in the example agents and in files made here.
import { readFileSync } from 'node:fs'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Cast } from '../src/cast'
import { compare, type Fired } from '../src/compare'
import { extractAgent } from '../src/extract'
import { agentsIn } from '../src/folder'
import { applyChanges } from '../src/fromSheets'
import { labelOf } from '../src/labels'
import { lessonOf } from '../src/lesson'
import { readProfile } from '../src/profile'
import { reviewCast } from '../src/review'
import { declaredFrom, firedFrom, mergeDeclared, readCsv } from '../src/tables'
import { fieldsOf, formOf, normal } from '../src/telemetry'
import { plain } from './wave1'
import { done, ok } from './ok'

const skill = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/cast-list')
const pedidos = { id: 'bodega-pedidos', schemaName: 'cr7b2_bodegaPedidos', displayName: 'Bodega Azul - Pedidos' }

// the form
ok(formOf('BodegaPedidos_OnError', pedidos) === '{agent}_OnError', 'the form takes out the schema name with no prefix (or the folder)')
ok(formOf('bodega_pedidos_onerror', pedidos) === '{agent}_onerror', 'with no case and no separators')
ok(formOf('Erro - Bodega Azul - Pedidos', pedidos) === 'Erro - {agent}', 'the display name, the longest first')
ok(formOf('Devolução_OnError', { id: 'bodega-devolucoes', displayName: 'Devolução' }) === '{agent}_OnError', 'with no accents')
ok(formOf('OnError', pedidos) === 'OnError', 'a name with none of the names is its own form')
ok(normal('{agent}_OnError') === normal('{agent}-onerror') && normal('{agent}_OnError') !== normal('{agent}_OnErr'), 'two spellings are the same only with no case and no separators')

// the record's fields
ok(fieldsOf('={Agente: "x", ErrorMessage: System.Error.Message, ConversationId: System.Conversation.Id}')?.join() === 'Agente,ErrorMessage,ConversationId', 'the fields of a record')
ok(fieldsOf('={A: If(x, {B: 1}, "a, b"), \'C d\': [1, 2], "E": "say ""hi"", ok"}')?.join() === 'A,C d,E', 'nested records, lists, quoted names and commas inside a text')
ok(fieldsOf('=Topic.ErrorRecord') === undefined && fieldsOf('={A x}') === undefined && fieldsOf(undefined) === undefined, 'a formula, a broken record or nothing: not a record')
ok(fieldsOf('={}')?.length === 0, 'an empty record has no fields')

// in the examples
const agents = Object.fromEntries(agentsIn(join(skill, 'examples/agents')).map((a) => [a.id, extractAgent(a.id, a.files)]))
const forms = (id: string) => agents[id].telemetry.map((t) => t.form).join()
ok(['bodega-orquestrador', 'bodega-pedidos', 'bodega-devolucoes', 'bodega-frete'].every((id) => forms(id) === '{agent}_OnError' && `telemetry:event:{agent}_OnError` in agents[id].facts), 'four write «{agent}_OnError»', Object.fromEntries(Object.keys(agents).map((id) => [id, forms(id)])))
ok(forms('bodega-cupons') === '{agent}_onerror' && agents['bodega-cupons'].telemetry[0].name === 'bodega_cupons_onerror', 'the cupons writes it another way, and keeps its own name')
ok(!agents['bodega-loja-fisica'].telemetry.length, 'the loja-fisica logs no event')
ok('telemetry:field:{agent}_OnError/ConversationId' in agents['bodega-pedidos'].facts && !('telemetry:field:{agent}_onerror/ConversationId' in agents['bodega-cupons'].facts) && 'telemetry:field:{agent}_onerror/ErrorCode' in agents['bodega-cupons'].facts, 'the fields as facts; the cupons has no ConversationId')
ok(agents['bodega-pedidos'].telemetry[0].file === 'topics/OnError.topic.mcs.yml' && !!agents['bodega-pedidos'].telemetry[0].line, 'with the file and the line')

// made here: a formula name, a record that is not one, a node switched off
const topic = (nodes: string) => `kind: AdaptiveDialog\nbeginDialog:\n  kind: OnError\n  id: main\n  actions:\n${nodes}`
const node = (name: string, props: string, off = '') => `    - kind: LogCustomTelemetryEvent\n      id: t${Math.random().toString(36).slice(2, 6)}\n${off}      eventName: ${name}\n      properties: ${props}\n`
const made = extractAgent('abc', [
  { path: 'topics/One.topic.mcs.yml', text: topic(node('"=Concatenate(\\"x\\", \\"y\\")"', '"={A: 1}"')) },
  { path: 'topics/Two.topic.mcs.yml', text: topic(node('ABC_Error', '=Topic.ErrorRecord')) },
  { path: 'topics/Three.topic.mcs.yml', text: topic(node('ABC_Off', '"={A: 1}"', '      disabled: true\n')) },
])
ok(made.unknown.some((u) => u.file === 'topics/One.topic.mcs.yml' && u.why === 'telemetry') && made.telemetry.length === 1, 'a name made by a formula goes to «unknown», and is no event', made)
ok(made.telemetry[0]?.form === '{agent}_Error' && made.telemetry[0].fields === undefined && !Object.keys(made.facts).some((k) => k.startsWith('telemetry:field:')), 'a record made by a formula: the event counts, its fields are not known')
ok(!Object.keys(made.facts).some((k) => k.includes('Off')), 'a node switched off is no event')
// the comparison: a spelling counts as the most common one, a field is compared among who has the event
const found = Object.values(agents)
const profile = plain(readProfile(readFileSync(join(skill, 'examples/profile.cast.yaml'), 'utf8')).profile!)
const empty: Cast = { agents: [], blocks: [], declared: [], decisions: [] }
const r = compare(found, profile, empty)
const event = r.patterns.find((p) => p.key === 'telemetry:event:{agent}_OnError')
ok(event?.partOf === 'node:LogCustomTelemetryEvent' && event.agents.includes('bodega-cupons') && event.agents.length === 5, 'the event is a part of logging telemetry, the cupons counted in it', event)
ok(r.telemetry.spellings.length === 1 && r.telemetry.spellings[0].agent === 'bodega-cupons' && r.telemetry.spellings[0].as === '{agent}_OnError', 'who wrote it another way', r.telemetry.spellings)
ok(r.offPattern.filter((o) => o.key.startsWith('telemetry:')).map((o) => `${o.agent} ${o.key}`).join() === 'bodega-cupons telemetry:field:{agent}_OnError/ConversationId', 'off: only the cupons, for the field it lacks; the loja-fisica is off telemetry once, not for the event', r.offPattern)
ok(!r.solos.some((x) => x.key.startsWith('telemetry:')), 'an event or a field is never a solo')
const looks = reviewCast(r)
ok(looks.find((l) => l.key === 'spelling')?.pt === 'bodega-cupons registra «bodega_cupons_onerror»; os outros, «‹nome›_OnError»: é o mesmo evento?', 'the spelling, said', looks.map((l) => l.pt))
ok(looks.some((l) => l.pt === '1 especialista registra «‹nome›_OnError» sem «ConversationId» (bodega-cupons): é intencional?'), 'the field it lacks, said')
ok(labelOf('telemetry:event:{agent}_OnError', 'pt') === 'Registra o evento «‹nome›_OnError»' && labelOf('telemetry:field:{agent}_OnError/ConversationId', 'en') === '«‹name›_OnError» carries «ConversationId»', 'the names on screen never say «agent»')
// a record not read lacks no field
const blind = found.map((a) => (a.id !== 'bodega-frete' ? a : { ...a, facts: Object.fromEntries(Object.entries(a.facts).filter(([k]) => !k.startsWith('telemetry:field:'))), telemetry: a.telemetry.map((t) => ({ ...t, fields: undefined })) }))
ok(!compare(blind, profile, empty).offPattern.some((o) => o.agent === 'bodega-frete' && o.key.startsWith('telemetry:field:')), 'an agent whose record was not read is left out of its fields')

// what fired: the example export of Application Insights
const csv = (f: string) => readCsv(readFileSync(join(skill, 'examples', f), 'utf8'), '')
const fired = firedFrom(csv('telemetria.csv'), found, { file: 'telemetria.csv', days: 30 }) as Fired
ok('rows' in fired && fired.rows.length === 9 && fired.rows.every((x) => found.some((a) => a.id === x.agent)), 'every row of the export is an agent of the folder, by its display name', fired)
const withFired = compare(found, profile, empty, fired)
ok(withFired.telemetry.notFired.map((e) => e.agent).join() === 'bodega-frete' && withFired.telemetry.silent.join() === 'bodega-loja-fisica', 'the frete event did not fire; the loja-fisica has no line', withFired.telemetry)
ok(withFired.telemetry.events.find((e) => e.agent === 'bodega-cupons')?.fired === 5 && withFired.telemetry.events.find((e) => e.agent === 'bodega-pedidos')?.fired === 7, 'the times each fired, by the name as written')
const tl = reviewCast(withFired).filter((l) => l.key === 'telemetry').map((l) => l.pt)
ok(tl.join('|') === 'O evento «BodegaFrete_OnError» de bodega-frete não disparou em 30 dias|bodega-loja-fisica não tem nenhuma linha na telemetria: está ligado ao Application Insights?', 'said', tl)
ok(!r.telemetry.notFired.length && !r.telemetry.silent.length, 'with no export, nothing is said about what fired')
const lesson = (lessonOf(withFired, reviewCast(withFired), 'pt').steps as { text?: string }[]).map((x) => x.text ?? '').join(' ')
ok(lesson.includes('é o mesmo evento?') && lesson.includes('não disparou em 30 dias'), 'the lesson: the spelling in «what to decide», what did not fire in «what is missing»')
ok('problem' in firedFrom({ name: '', rows: [['agente', 'vezes'], ['Bodega Azul - Pedidos', '3'], ['Bodega Azul - Frete', '1']] }, found, { file: 'x', days: 30 }), 'an export with no event column says so')

// a CSV
const t = readCsv('﻿a;b;"c ""d"""\r\n1;"x;y";\n', 'x')
ok(JSON.stringify(t.rows) === JSON.stringify([['a', 'b', 'c "d"'], ['1', 'x;y', '']]), 'a CSV: the BOM, «;», quotes, \\r\\n', t.rows)
ok(readCsv('a,b\n1,2', '').rows.length === 2 && readCsv('a,b\n1,2', '').rows[1][1] === '2', 'with «,» and no last line break')

// declared: the inventory and the team's spreadsheet
const inv = declaredFrom(csv('inventario.csv'), found, empty, { file: 'inventario.csv', lang: 'pt' })
const said = (i: typeof inv, agent: string, key: string) => i.changes.flatMap((c) => (c.kind === 'declared' && c.after ? [c.after] : [])).find((d) => d.agent === agent && d.key === key)
ok(said(inv, 'bodega-pedidos', 'owner')?.value === 'pedidos@bodegaazul.example' && said(inv, 'bodega-pedidos', 'owner')?.source === 'inventario.csv › linha 3', 'the inventory: the owner, with the file and the line', inv.changes.slice(0, 3))
ok(!said(inv, 'bodega-cupons', 'owner') && !!said(inv, 'bodega-cupons', 'last-published'), 'an empty cell is no fact')
ok(inv.unmatched.map((u) => u.value).join() === 'Bodega Azul - Fidelidade' && !inv.changes.some((c) => c.kind === 'declared' && (c.after?.key === 'item-type' || c.after?.key === 'item-name')), 'the agent not in the folder is listed; the app and the flow are left out; the agent and type columns are no facts', inv)
const team = declaredFrom(csv('equipe.csv'), found, empty, { file: 'equipe.csv', lang: 'pt' })
ok(said(team, 'bodega-frete', 'kpi')?.value === 'cotação em menos de 5 s' && !said(team, 'bodega-loja-fisica', 'kpi') && said(team, 'bodega-loja-fisica', 'owner')?.value === 'Squad Lojas', 'the team spreadsheet, with «;»: the KPI, «Dono» as the owner; the loja-fisica has no KPI')
ok(team.unmatched.map((u) => u.value).join() === 'Sobre a Bodega Azul', 'the row that names nobody in the folder is listed')
const both = mergeDeclared([...inv.changes, ...team.changes])
const owners = both.flatMap((c) => (c.kind === 'declared' && c.after?.agent === 'bodega-pedidos' && c.after.key === 'owner' ? [c.after.value] : []))
ok(owners.join() === 'Squad Pedidos' && both.map((c) => c.key).join() === both.map((_, i) => `d${i + 1}`).join(), 'two tables saying the owner: the later holds, once; the keys numbered again', owners)
const cast2 = applyChanges(empty, both, both.map((c) => c.key))
ok(!declaredFrom(csv('equipe.csv'), found, cast2, { file: 'equipe.csv', lang: 'pt' }).changes.length, 'importing again changes nothing')
const kpis = compare(found, profile, cast2)
ok(kpis.gaps.some((g) => g.rule.has === 'declared:kpi' && g.agents.join() === 'bodega-loja-fisica'), 'the rule «every specialist has a KPI» now misses only the loja-fisica', kpis.gaps)
const tie = declaredFrom({ name: '', rows: [['a', 'b'], ['bodega-frete', 'bodega-cupons'], ['bodega-cupons', 'bodega-frete']] }, found, empty, { file: 'x', lang: 'en' })
ok(tie.problem?.problem === 'tie' && declaredFrom({ name: '', rows: [['a', 'b'], ['x', 'y']] }, found, empty, { file: 'x', lang: 'en' }).problem?.problem === 'none', 'two columns that disagree, or none: it asks for --agent-column')
ok(said(declaredFrom({ name: 'Agentes', rows: [['Quem', 'Área'], ['bodega-frete', 'Logística']] }, found, empty, { file: 'e.xlsx', lang: 'pt', agentColumn: 'quem' }), 'bodega-frete', 'area')?.source === 'e.xlsx › Agentes › linha 2', 'the column given, a sheet of an .xlsx in the source')
done()

