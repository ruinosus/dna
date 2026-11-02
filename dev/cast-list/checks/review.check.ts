// The names of the keys and what the run asks («to look at»), with no model: each in English and Portuguese, the
// agents named, a rule that only repeats a pattern said once, related keys of one solo said once — and the patterns
// with someone off before the ones everybody already follows.
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readCast, type Cast } from '../src/cast'
import { compare } from '../src/compare'
import { extractAgent } from '../src/extract'
import { agentsIn } from '../src/folder'
import { dimensionOf, keysMarkdown, labelOf } from '../src/labels'
import { readProfile } from '../src/profile'
import { groupPatterns, reviewCast } from '../src/review'
import { done, ok } from './ok'

const examples = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/cast-list/examples')
const agents = agentsIn(join(examples, 'agents')).map((a) => extractAgent(a.id, a.files))
const profile = readProfile(readFileSync(join(examples, 'profile.cast.yaml'), 'utf8')).profile!
const demo = readCast(readFileSync(join(examples, 'demo.cast.yaml'), 'utf8')).cast!
const empty: Cast = { agents: [], blocks: [], declared: [], decisions: [] }

// names
ok(labelOf('trigger:OnEscalate', 'pt') === 'Escalonamento para humano' && labelOf('trigger:OnEscalate', 'en') === 'Escalation to a person', 'a known key has its name')
ok(labelOf('mcp:shared_x', 'pt') === 'Servidor MCP shared_x' && labelOf('knowledge:count=1', 'pt') === '1 fonte de conhecimento' && labelOf('knowledge:count=3', 'en') === '3 knowledge sources', 'a key with a value: the name and the value')
ok(labelOf('trigger:OnSomethingNew', 'pt') === 'Gatilho OnSomethingNew' && labelOf('odd:thing', 'pt') === 'odd:thing', 'a key with no name says itself, and nothing breaks')
ok(dimensionOf('trigger:OnEscalate') === 'conversation' && dimensionOf('connector:x') === 'integrations' && dimensionOf('trigger:OnKnowledgeRequested') === 'knowledge'
  && dimensionOf('calls:x') === 'orchestration' && dimensionOf('calls:topic:x') === 'conversation' && dimensionOf('node:LogCustomTelemetryEvent') === 'governance'
  && dimensionOf('ms:date-context') === 'microsoft' && dimensionOf('declared:kpi') === 'declared', 'each key in its dimension')
const md = keysMarkdown()
ok(['Conversation', 'Integrations', 'Knowledge', 'Orchestrator', 'Governance', 'Microsoft', 'Declared'].every((d) => md.includes(`## `) && md.includes(d)) && md.includes('`trigger:OnEscalate`') && md.includes('date-context'), 'the key reference lists every dimension, the keys and the Microsoft patterns')

// to look at, with the example profile and no cast file
const looks = reviewCast(compare(agents, profile, empty))
const pt = looks.map((l) => l.pt)
const has = (s: string) => pt.includes(s)
ok(has('1 especialista não escala para humano (bodega-frete): é intencional?'), 'bodega-frete does not escalate: asked', pt)
ok(has('1 especialista não registra telemetria (bodega-loja-fisica): é intencional?'), 'bodega-loja-fisica logs no telemetry: asked')
ok(!pt.some((s) => s.includes('Escalate') || s.includes('nenhum tópico leva')), "bodega-frete's escalation: asked once, not again for its fallback", pt)
ok(has('Só bodega-cupons tem «Servidor MCP Bodega Azul Promocoes MCP»: inovação ou dívida?') && has('Só bodega-cupons tem «Conector SharePoint»: inovação ou dívida?'), 'what only bodega-cupons has: asked, by the names the files give', pt)
ok(!pt.some((s) => /shared_|cr7b2_/.test(s)), 'no technical name on screen when the files give a readable one')
ok(!pt.some((s) => s.includes('Referência de conexão') || s.includes('Operação GetItems')), "the connection and the operation of a solo connector are not asked again", pt)
ok(has('Só bodega-loja-fisica tem «Condição de busca só no YAML (a tela pode apagar)»: inovação ou dívida?'), 'the YAML-only condition: asked')
ok(has('Regra «Todo especialista tem KPI»: 5 especialistas não cumprem (bodega-cupons, bodega-devolucoes, bodega-frete, bodega-loja-fisica, bodega-pedidos)'), 'the KPI rule: asked', pt)
ok(!pt.some((s) => s.startsWith('Regra «Todo especialista escala')), 'the rule «escala» only repeats a pattern bodega-frete is already off: said once')
ok(has('Só bodega-frete tem «Desambiguação («você quis dizer…»)»: inovação ou dívida?'), 'the triage topic only frete has: asked')
ok(has('Só bodega-devolucoes tem «Conhecimento geral do modelo ligado»: inovação ou dívida?'), 'a setting only one has, by its name')
ok(looks.length === 8 && looks.every((l) => l.en && l.pt), `${looks.length} things to look at, each in English and Portuguese`, pt)
ok(!looks.some((l) => /\bagentes?\b|\bagents?\b/i.test(l.pt + l.en)), 'the screen words never say «agent»', looks.filter((l) => /agent/i.test(l.pt + l.en)))
ok(looks.findIndex((l) => l.key === 'off') < looks.findIndex((l) => l.key === 'gap') && looks.findIndex((l) => l.key === 'gap') < looks.findIndex((l) => l.key === 'solo'), 'off a pattern first, then the rules, then the solos')

// with the demo cast file
const d = reviewCast(compare(agents, profile, demo)).map((l) => l.pt)
ok(d[0] === 'bodega-frete: «handoff do frete, seção 4» diz que tem «Escalonamento para humano», mas o YAML não tem', 'what people said and the YAML do not agree: first', d)
ok(d.includes('1 especialista não escala para humano (bodega-frete), e o padrão foi aceito: corrigir?'), 'off an accepted pattern: correct it?')
ok(d.some((s) => s.startsWith('Regra «Todo especialista tem KPI»: 4 especialistas')), 'the KPI rule now names four')

// what was not understood, and a profile naming an agent that is not there
const odd = reviewCast(compare([...agents, extractAgent('odd', [{ path: 'agent.mcs.yml', text: 'kind: GptComponentMetadata\n' }, { path: 'a.txt', text: '' }, { path: 'topics/b.yml', text: '' }])], { ...profile, roles: { ...profile.roles, orchestrator: ['bodega-orquestrador', 'velho'] } }, empty))
ok(odd.some((l) => l.pt === 'odd: a análise não entendeu 2 arquivos (a.txt, topics/b.yml)') && odd.some((l) => l.pt === 'O perfil cita «velho», que não está na pasta'), 'files not understood, and a name in the profile that is not in the folder', odd.map((l) => l.pt))

// patterns: the ones with someone off (or decided) first, then what everybody already does
const g = groupPatterns(compare(agents, profile, empty))
ok(['trigger:OnEscalate', 'node:LogCustomTelemetryEvent'].every((k) => g.look.some((p) => p.key === k)) && g.look.length === 2, 'to decide: the two patterns someone is off — the part goes with its fact', g.look.map((p) => p.key))
ok(g.everyone.some((p) => p.key === 'auth:None') && g.everyone.length + g.look.length === compare(agents, profile, empty).patterns.filter((p) => !p.partOf).length, 'everybody already does the rest — none lost')
done()
