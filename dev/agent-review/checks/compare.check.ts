// The comparison over the six example agents and the example profile: the patterns of a role and their scope, who is
// off them, what only one specialist has, what only the orchestrator does, the rules not met, what people said that
// the YAML contradicts, and the decisions — an accepted pattern is checked even when it would no longer be one.
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readCast, type Cast } from '../src/cast'
import { compare, type Result } from '../src/compare'
import { extractAgent } from '../src/extract'
import { agentsIn } from '../src/folder'
import { DEFAULT_PROFILE, readProfile } from '../src/profile'
import { plain, wave1 } from './wave1'
import { done, ok } from './ok'

const examples = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/agent-review/examples')
const agents = agentsIn(join(examples, 'agents')).map((a) => extractAgent(a.id, a.files))
const profile = plain(readProfile(readFileSync(join(examples, 'team.standard.yaml'), 'utf8')).profile!)
const demo = readCast(readFileSync(join(examples, 'demo.review.yaml'), 'utf8')).cast!
const empty: Cast = { agents: [], blocks: [], declared: [], decisions: [] }
const SPECIALISTS = ['bodega-pedidos', 'bodega-devolucoes', 'bodega-frete', 'bodega-cupons', 'bodega-loja-fisica']

const r = compare(agents, profile, empty)
const pattern = (res: Result, key: string) => res.patterns.find((p) => p.key === key)
const keys = (xs: { key: string }[]) => xs.map((x) => x.key).sort()

// patterns of the specialists, and their scope
ok(pattern(r, 'trigger:OnEscalate')?.share === 0.8 && pattern(r, 'trigger:OnEscalate')?.role === 'specialist', 'escalating is a pattern of the specialists (4 of 5)', pattern(r, 'trigger:OnEscalate'))
ok(pattern(r, 'node:LogCustomTelemetryEvent')?.share === 0.8, 'telemetry is a pattern too (4 of 5)')
ok(!pattern(r, 'trigger:OnConversationStart') && !r.agents.some((a) => 'trigger:OnConversationStart' in a.facts), 'what the profile ignores is left out everywhere')
const platform = ['trigger:OnEscalate', 'trigger:OnError', 'node:LogCustomTelemetryEvent', 'instructions:present', 'var:CategoriaSolicitacao']
ok(platform.every((k) => pattern(r, k)?.scope === 'platform'), 'platform: the specialists do it and so does the orchestrator', platform.map((k) => `${k}: ${pattern(r, k)?.scope}`))
ok(['connector:shared_office365', 'trigger:OnRedirect', 'knowledge:SharePointSearchSource'].every((k) => pattern(r, k)?.scope === 'specialist'), 'specialist: only the specialists do it')
ok(!r.patterns.some((p) => p.role === 'orchestrator'), 'one orchestrator makes no majority: no pattern of orchestrators')

// who is off a pattern
const off = (res: Result) => [...new Set(res.offPattern.map((o) => o.agent))].sort()
ok(off(r).join() === 'bodega-cupons,bodega-frete,bodega-loja-fisica', 'off a pattern: only bodega-cupons (a telemetry field), bodega-frete and bodega-loja-fisica', r.offPattern)
ok(keys(r.offPattern.filter((o) => o.agent === 'bodega-frete' && !o.key.startsWith('text:') && !o.key.startsWith('called-with:'))).join() === 'trigger:OnEscalate', 'bodega-frete: off once — it does not escalate (the fallback that would lead there is part of it)', r.offPattern)
const part = pattern(r, 'reaches:OnEscalate')
ok(part?.partOf === 'trigger:OnEscalate' && part.share === 1 && part.scope === 'platform', 'reaching escalation is a part of escalating, checked on the agents that escalate', part)
ok(!r.solos.some((s) => s.key.startsWith('reaches:')) && !r.orchestratorDoes.some((s) => s.key.startsWith('reaches:')), 'a part is never a solo')
// pedidos keeps its escalation topic but its fallback no longer leads there: that is still a finding, of the part
const lost = agents.map((a) => (a.id === 'bodega-pedidos' ? { ...a, facts: Object.fromEntries(Object.entries(a.facts).filter(([k]) => k !== 'reaches:OnEscalate')) } : a))
const l = compare(lost, profile, demo)
ok(l.offPattern.some((o) => o.agent === 'bodega-pedidos' && o.key === 'reaches:OnEscalate' && o.partOf === 'trigger:OnEscalate') && !l.offPattern.some((o) => o.agent === 'bodega-pedidos' && o.key === 'trigger:OnEscalate'), 'has the topic, nothing leads to it: off the part, not the fact', l.offPattern)
ok(pattern(l, 'reaches:OnEscalate')?.decision?.status === 'accepted', "the fact's decision covers its part")
ok(r.names.shared_office365 === 'Office 365 Outlook' && r.names.cr7b2_bodegaCupons === 'Bodega Azul - Cupons', 'readable names: connectors and agents')
ok(keys(r.offPattern.filter((o) => o.agent === 'bodega-loja-fisica')).join() === 'node:LogCustomTelemetryEvent', 'bodega-loja-fisica: no telemetry')

// solos and what only the orchestrator does
const solo = (agent: string) => keys(r.solos.filter((s) => s.agents.join() === agent))
ok(solo('bodega-cupons').join() === 'connector:shared_sharepointonline,connref:shared_bodegapromocoesmcp,connref:shared_sharepointonline,mcp:shared_bodegapromocoesmcp,operation:shared_sharepointonline/GetItems', 'bodega-cupons alone: SharePoint items and the MCP server', solo('bodega-cupons'))
ok(solo('bodega-loja-fisica').join() === 'yaml-only:triggerCondition', 'bodega-loja-fisica alone: the YAML-only triggerCondition')
ok(r.solos.every((s) => SPECIALISTS.includes(s.agents[0])) && !r.solos.some((s) => s.key.startsWith('calls:') || s.key === 'trigger:OnToolSelected'), 'no solo of the orchestrator, nor of its child agent', keys(r.solos))
const does = keys(r.orchestratorDoes)
ok(['calls:cr7b2_bodegaPedidos', 'calls:cr7b2_bodegaDevolucoes', 'calls:cr7b2_bodegaFrete', 'calls:cr7b2_bodegaCupons', 'calls:cr7b2_bodegaLojaFisica', 'child:SobreBodegaAzul', 'ms:orchestrator-variables'].every((k) => does.includes(k)), 'what only the orchestrator does: the five calls, its child agent, the orchestrator-variables pattern', does)

// rules
const gap = (res: Result, id: string) => res.gaps.find((g) => g.rule.id === id)?.agents.sort().join()
ok(gap(r, 'escala') === 'bodega-frete', 'the rule «escala»: bodega-frete')
ok(gap(r, 'kpi') === [...SPECIALISTS].sort().join(), 'the rule «kpi»: nobody declared one, all five specialists')

// with the demo review file: what people said, and what was decided
const d = compare(agents, profile, demo)
ok(gap(d, 'kpi') === SPECIALISTS.filter((s) => s !== 'bodega-pedidos').sort().join(), 'bodega-pedidos declared its KPI: the rule now names four', gap(d, 'kpi'))
ok('declared:kpi' in d.agents.find((a) => a.id === 'bodega-pedidos')!.facts && !d.solos.some((s) => s.key === 'declared:kpi'), 'a declared fact is a fact of the agent, and not a solo')
ok(d.conflicts.length === 1 && d.conflicts[0].agent === 'bodega-frete' && d.conflicts[0].key === 'trigger:OnEscalate' && d.conflicts[0].observed === false && d.conflicts[0].source === 'handoff do frete, seção 4', 'the handoff says bodega-frete escalates; the YAML says it does not', d.conflicts)
ok(!('trigger:OnEscalate' in d.agents.find((a) => a.id === 'bodega-frete')!.facts), 'what was seen wins: a declared claim never changes an observed fact')
ok(pattern(d, 'trigger:OnEscalate')?.decision?.status === 'accepted' && d.offPattern.some((o) => o.agent === 'bodega-frete' && o.key === 'trigger:OnEscalate'), 'the accepted pattern is marked, and bodega-frete is still off it')

// the limits
const strict = compare(agents, { ...profile, threshold: 0.9 }, empty)
ok(!pattern(strict, 'trigger:OnEscalate') && pattern(strict, 'trigger:OnRedirect')?.share === 1, 'with threshold 0.9, 4 of 5 is no longer a pattern')
const accepted = compare(agents, { ...profile, threshold: 0.9 }, demo)
ok(pattern(accepted, 'trigger:OnEscalate')?.decision?.status === 'accepted' && accepted.offPattern.some((o) => o.agent === 'bodega-frete' && o.key === 'trigger:OnEscalate'), 'an accepted pattern is still checked when it would no longer be one')
const few = compare(agents, { ...profile, minAgents: 6 }, empty)
ok(!few.patterns.length && !few.offPattern.length, 'with min_agents 6, five specialists make no pattern')
const rejected = compare(agents, profile, { ...empty, decisions: [{ key: 'node:LogCustomTelemetryEvent', status: 'rejected', scope: 'platform', why: 'telemetria vai por fora' }] })
ok(pattern(rejected, 'node:LogCustomTelemetryEvent')?.decision?.status === 'rejected' && !rejected.offPattern.some((o) => o.key === 'node:LogCustomTelemetryEvent'), 'a rejected pattern is shown as rejected, and nobody is off it')

// with no profile at all, the same agents and the same people off
const bare = compare(agents, DEFAULT_PROFILE, empty)
ok(bare.roles['bodega-orquestrador'] === 'orchestrator' && off(bare).join() === 'bodega-cupons,bodega-frete,bodega-loja-fisica', 'with no profile: the same orchestrator, the same three off a pattern')
// what the analysis did not understand comes with the agent
const odd = compare([...agents, extractAgent('odd', [{ path: 'agent.mcs.yml', text: 'kind: GptComponentMetadata\n' }, { path: 'x.txt', text: '' }])], profile, empty)
ok(odd.unknown.length === 1 && odd.unknown[0].agent === 'odd' && odd.unknown[0].file === 'x.txt', 'what was not understood says the agent and the file', odd.unknown)
ok(compare(agents, { ...profile, microsoftPatterns: false }, empty).agents.every((a) => !Object.keys(a.facts).some((k) => k.startsWith('ms:'))), 'microsoft_patterns: off leaves the Microsoft patterns out')
// wave 1: the text facts in the same count, the types, the official block, the rule with a condition
const w1 = wave1(profile)
const t = compare(agents, w1, empty)
ok(t.types['bodega-pedidos'].join() === 'transaction' && t.types['bodega-devolucoes'].join() === 'transaction' && t.types['bodega-cupons'].join() === 'transaction,guidance'
  && t.types['bodega-loja-fisica'].join() === 'guidance' && t.types['bodega-frete'].join() === 'triage' && !t.types['bodega-orquestrador'].length, 'the types: transaction 3, guidance 2 (cupons is both), triage 1', t.types)
const flow = t.patterns.find((p) => p.key.startsWith('flow:'))
ok(flow?.scope === 'type:transaction' && flow.share === 1, 'calling the flow is a pattern of the transaction type', flow)
const help = pattern(t, 'text:link-domain:ajuda.bodega-azul.example')
ok(help?.scope === 'type:guidance', 'the help link is a pattern of the guidance type', help)
ok(!t.offPattern.some((o) => (o.key.startsWith('flow:') || o.key.startsWith('text:link-domain')) && ['bodega-loja-fisica', 'bodega-pedidos', 'bodega-frete'].includes(o.agent)), 'a pattern of a type never blames who is not of the type', t.offPattern)
ok(t.typeNotes.length === 1 && t.typeNotes[0].type === 'triage' && t.typeNotes[0].agents.join() === 'bodega-frete', 'the triage type has 1 specialist: nothing to compare in it', t.typeNotes)
const links = pattern(t, 'text:block:links')
ok(links?.official === 'Formatação de links' && links.scope === 'specialist', 'the official block is a pattern of its role', links)
ok(t.offPattern.some((o) => o.agent === 'bodega-frete' && o.key === 'text:block:links' && o.variant), 'frete is off the official block, with a variation', t.offPattern.filter((o) => o.key === 'text:block:links'))
ok(t.blocks.some((b) => b.id === 'links' && b.official) && t.blocks.length >= 3, 'the families of blocks come with the result', t.blocks.map((b) => b.id))
const lonely = compare(agents, { ...w1, blocks: [{ id: 'aviso', name: 'Aviso legal', text: 'Este atendimento é automático e pode errar; confirme os dados importantes com uma pessoa antes de decidir.', role: 'specialist' }] }, empty)
ok(lonely.offPattern.filter((o) => o.key === 'text:block:aviso').length === 5, 'an official block nobody has: every specialist is off it, with no majority', lonely.offPattern.filter((o) => o.key === 'text:block:aviso'))
ok(pattern(t, 'text:no-emoji')?.scope === 'platform' && t.offPattern.some((o) => o.agent === 'bodega-loja-fisica' && o.key === 'text:no-emoji'), '«no emojis» is the platform\'s; loja-fisica is off it')
ok(gap(t, 'knowledge-only') === 'bodega-devolucoes', 'the rule with a condition: only devolucoes asks for the knowledge alone with the general knowledge on')
ok(t.markerFindings.some((m) => m.kind === 'values') && t.markerFindings.some((m) => m.kind === 'twice' && m.agent === 'bodega-loja-fisica'), 'the marker findings come with the result')
ok(!t.patterns.some((p) => p.key.endsWith('~variant')) && !t.solos.some((x) => x.key.endsWith('~variant')), 'a variation is neither a pattern nor a solo')
const decided = compare(agents, w1, { ...empty, decisions: [{ key: 'text:link-domain:ajuda.bodega-azul.example', status: 'accepted', scope: 'type:guidance', why: 'orientação sempre aponta a ajuda' }] })
ok(pattern(decided, 'text:link-domain:ajuda.bodega-azul.example')?.decision?.scope === 'type:guidance', 'a decision with a type scope marks the pattern of that type')
const given = compare(agents, w1, { ...empty, agents: [{ id: 'bodega-frete', role: 'specialist', types: ['guidance'] }], decisions: [{ key: 'text:link-domain:ajuda.bodega-azul.example', status: 'accepted', scope: 'type:guidance', why: '' }] })
ok(given.types['bodega-frete'].join() === 'guidance' && given.offPattern.some((o) => o.agent === 'bodega-frete' && o.key === 'text:link-domain:ajuda.bodega-azul.example'), 'the review file makes frete a guidance specialist: off the accepted help-link pattern of its new type')

// wave 2: the orchestrator's contract, as facts of the agent called
const fact = (id: string, key: string) => r.agents.find((a) => a.id === id)!.facts[key]
ok(SPECIALISTS.filter((id) => id !== 'bodega-frete').every((id) => fact(id, 'called-with:history') && fact(id, 'called-with:input:CategoriaSolicitacao')) && !fact('bodega-frete', 'called-with:history') && !fact('bodega-frete', 'called-with:input:CategoriaSolicitacao'),
  'four specialists are called with the history and the category; frete with neither')
ok(fact('bodega-pedidos', 'called-with:history')[0].file === 'bodega-orquestrador/actions/AgentePedidos.mcs.yml', 'the evidence is in the orchestrator\'s file', fact('bodega-pedidos', 'called-with:history'))
ok(pattern(r, 'called-with:history')?.share === 0.8 && pattern(r, 'called-with:input:CategoriaSolicitacao')?.share === 0.8 && pattern(r, 'routing:described')?.share === 1, 'the contract is a pattern of the specialists', r.patterns.filter((p) => /^(called|routing)/.test(p.key)))
ok(['called-with:history', 'called-with:input:CategoriaSolicitacao'].every((k) => r.offPattern.some((o) => o.agent === 'bodega-frete' && o.key === k)), 'frete is off both')
ok(r.contract.routes.length === 6 && r.contract.missing.map((m) => m.calls).join() === 'cr7b2_bodegaFidelidade' && r.contract.missing[0].caller === 'bodega-orquestrador', 'the orchestrator calls one that is not in the folder', r.contract.missing)
ok(r.contract.short.map((x) => `${x.agent}:${x.description.length}`).join() === 'bodega-cupons:7', 'a short routing description: cupons, 7 characters', r.contract.short)
ok(!r.contract.uncalled.length, 'every specialist of the folder is called')
const lonelyOne = compare(agents.filter((a) => a.id !== 'bodega-orquestrador').concat({ ...agents.find((a) => a.id === 'bodega-orquestrador')!, contract: agents.find((a) => a.id === 'bodega-orquestrador')!.contract.filter((c) => c.calls !== 'cr7b2_bodegaFrete') }), profile, empty)
ok(lonelyOne.contract.uncalled.join() === 'bodega-frete', 'a specialist no orchestrator calls', lonelyOne.contract.uncalled)
const noOrchestrator = compare(agents.filter((a) => a.id !== 'bodega-orquestrador'), profile, empty)
ok(!noOrchestrator.contract.uncalled.length, 'with no orchestrator, nobody is «not called»')

// wave 2: the flows and what nothing uses
const silent = r.flows.filter((f) => f.called && !f.returns)
ok(silent.map((f) => `${f.agent}:${f.name}`).join() === 'bodega-cupons:Abrir chamado no ERP', 'the flow that returns nothing: cupons, «Abrir chamado no ERP»', r.flows)
ok(r.flows.length === 4, 'four flows, the unused one too')
ok(!r.patterns.some((p) => /^(orphan|disabled):/.test(p.key)) && !r.solos.some((x) => /^(orphan|disabled):/.test(x.key) || x.key.includes('commondataservice') || x.key === 'var:PreferenciaAntiga'), 'what nothing uses is never a pattern nor a solo — nor what an unused flow uses', keys(r.solos))
ok(r.unused.map((u) => `${u.agent} ${u.how} ${u.what} ${u.name}`).join('|') === 'bodega-frete orphan variable PreferenciaAntiga|bodega-loja-fisica orphan flow ListarLojas|bodega-loja-fisica orphan topic AvisoAntigo|bodega-pedidos disabled node SendActivity',
  'the unused and the switched off, each with its file', r.unused)
ok(r.unused.every((u) => u.sources[0]?.file), 'each with its file')

done()
