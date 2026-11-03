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
import { DIMENSIONS, dimensionOf, keysMarkdown, labelOf } from '../src/labels'
import { readProfile } from '../src/profile'
import { GROUPS, groupLooks, groupPatterns, reviewCast } from '../src/review'
import { done, ok } from './ok'
import { plain, wave1 } from './wave1'

const examples = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/cast-list/examples')
const agents = agentsIn(join(examples, 'agents')).map((a) => extractAgent(a.id, a.files))
const profile = plain(readProfile(readFileSync(join(examples, 'profile.cast.yaml'), 'utf8')).profile!)
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
ok(!looks.filter((l) => l.key !== 'unused').some((l) => l.pt.includes('Escalate') || l.pt.includes('nenhum tópico leva')), "bodega-frete's escalation: asked once, not again for its fallback", pt)
ok(has('Só bodega-cupons tem «Servidor MCP Bodega Azul Promocoes MCP»: inovação ou dívida?') && has('Só bodega-cupons tem «Conector SharePoint»: inovação ou dívida?'), 'what only bodega-cupons has: asked, by the names the files give', pt)
ok(!pt.some((s) => /shared_|cr7b2_/.test(s)), 'no technical name on screen when the files give a readable one')
ok(!pt.some((s) => s.includes('Referência de conexão') || s.includes('Operação GetItems')), "the connection and the operation of a solo connector are not asked again", pt)
ok(has('Só bodega-loja-fisica tem «Condição de busca só no YAML (a tela pode apagar)»: inovação ou dívida?'), 'the YAML-only condition: asked')
ok(has('Regra «Todo especialista tem KPI»: 5 especialistas não cumprem (bodega-cupons, bodega-devolucoes, bodega-frete, bodega-loja-fisica, bodega-pedidos)'), 'the KPI rule: asked', pt)
ok(!pt.some((s) => s.startsWith('Regra «Todo especialista escala')), 'the rule «escala» only repeats a pattern bodega-frete is already off: said once')
ok(has('Só bodega-frete tem «Desambiguação («você quis dizer…»)»: inovação ou dívida?'), 'the triage topic only frete has: asked')
ok(has('Só bodega-devolucoes tem «Conhecimento geral do modelo ligado»: inovação ou dívida?'), 'a setting only one has, by its name')
// wave 2: the contract, the flows, what nothing uses — said as the plan says them
for (const s of [
  '1 especialista não recebe o histórico da conversa do orquestrador (bodega-frete): é intencional?',
  '1 especialista não recebe «CategoriaSolicitacao» do orquestrador (bodega-frete): é intencional?',
  'O orquestrador chama «Bodega Azul - Fidelidade», que não está na pasta',
  'A descrição de roteamento de bodega-cupons tem só 7 caracteres',
  'O fluxo «Abrir chamado no ERP» de bodega-cupons não devolve nada',
  'Ninguém chama o tópico «AvisoAntigo» (bodega-loja-fisica): remover ou ligar?',
  'Ninguém chama o fluxo «Listar lojas» (bodega-loja-fisica): remover ou ligar?',
  'Ninguém usa a variável «PreferenciaAntiga» (bodega-frete): remover?',
  'bodega-pedidos tem um nó desligado em «topics/Escalate» (SendActivity): remover?',
]) ok(has(s), `asked: ${s}`, pt)
const at = (k: string) => looks.findIndex((l) => l.key === k)
ok(at('contract') < at('off') && at('flow') < at('off') && at('contract') > -1 && at('unused') > at('solo'), 'the contract and the flows come with the contradictions, what nothing uses after the solos')
ok(labelOf('called-with:history', 'pt') === 'Recebe o histórico da conversa' && labelOf('called-with:input:CategoriaSolicitacao', 'pt') === 'Recebe «CategoriaSolicitacao» do orquestrador' && labelOf('flow-uses:http:erp.bodega-azul.example', 'pt') === 'Fluxo chama erp.bodega-azul.example',
  'the names of the contract and the flows')
ok(dimensionOf('called-with:history') === 'orchestration' && dimensionOf('routing:described') === 'orchestration' && dimensionOf('flow-uses:http:x') === 'integrations' && dimensionOf('orphan:topic:x') === 'governance', 'the contract in D, the flows in B')
ok(['called-with:input:', 'flow-uses:http:', 'orphan:topic:', 'disabled:node:', 'called-with:history', 'flow-returns'].every((k) => md.includes(k)), 'keys.md lists the new keys')
ok(looks.length === 20 && looks.every((l) => l.en && l.pt), `${looks.length} things to look at, each in English and Portuguese`, pt)
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
ok(['trigger:OnEscalate', 'node:LogCustomTelemetryEvent', 'called-with:history', 'called-with:input:CategoriaSolicitacao'].every((k) => g.look.some((p) => p.key === k)) && g.look.some((p) => p.key.startsWith('text:block:links')) && g.look.length === 5, 'to decide: the five patterns someone is off (the links block and the contract too) — the part goes with its fact', g.look.map((p) => p.key))
ok(g.everyone.some((p) => p.key === 'auth:None') && g.everyone.length + g.look.length === compare(agents, profile, empty).patterns.filter((p) => !p.partOf).length, 'everybody already does the rest — none lost')
// wave 1: the text's names, and what the run asks about it
const r1 = compare(agents, wave1(profile), empty)
const n = r1.names
ok(dimensionOf('text:size=3 bullets') === 'text' && DIMENSIONS.text.pt === 'F. Texto' && DIMENSIONS.text.en === 'F. Text', 'the text is dimension F')
ok(labelOf('text:size=3 bullets', 'pt', n) === 'Tamanho da resposta = 3 bullets' && labelOf('text:no-emoji', 'pt', n) === 'Sem emojis', "a marker by the profile's name, with its value", [labelOf('text:size=3 bullets', 'pt', n), labelOf('text:no-emoji', 'pt', n)])
ok(labelOf('text:link-domain:ajuda.bodega-azul.example', 'pt', n) === 'Link para ajuda.bodega-azul.example' && labelOf('text:email', 'en', n) === 'Mentions an e-mail', 'the built-in markers')
ok(labelOf('text:block:links', 'pt', n) === 'Formatação de links' && labelOf('text:block:links~variant', 'pt', n) === 'Formatação de links (variação)', "the official block by its name; a variation says so")
const other = r1.blocks.find((b) => !b.official)!
ok(labelOf(`text:block:${other.id}`, 'pt', n) === other.label, 'a block with no name: its first words')
const l1 = reviewCast(r1).map((l) => l.pt)
const in1 = (x: string) => l1.includes(x)
ok(in1('bodega-devolucoes tem «Só o conhecimento», mas também «Conhecimento geral do modelo ligado» (regra «Quem pede só o conhecimento tem o conhecimento geral desligado»)'), 'the text and the setting disagree: said as a contradiction', l1)
ok(in1('1 especialista tem uma variação do bloco oficial «Formatação de links» (bodega-frete): alinhar?'), 'a variation of the official block: align it?')
ok(in1('1 especialista não tem «Sem emojis» (bodega-loja-fisica): é intencional?'), '«no emojis» missing: asked')
ok(in1('4 especialistas definem «Tamanho da resposta» de 2 jeitos (3 bullets em 3; 5 frases em 2): unificar?'), 'set in two ways: unify?')
ok(in1('bodega-loja-fisica define «Tamanho da resposta» duas vezes (3 bullets; 5 frases): qual vale?'), 'set twice: which one holds?')
ok(in1('O tipo «triagem» tem 1 especialista (bodega-frete): nada a comparar dentro dele'), 'a type with one specialist: told')
ok(!l1.some((x) => x.startsWith('Só bodega-devolucoes tem')), 'what the contradiction already says is not asked again as a solo', l1.filter((x) => x.startsWith('Só ')))
const kinds = reviewCast(r1).map((l) => l.key)
const first = (k: string) => kinds.indexOf(k as never)
ok(first('contradiction') === 0 && first('off') < first('values') && first('values') < first('twice') && first('twice') < first('type') && first('type') < first('gap') && first('gap') < first('solo'), 'contradictions first, then off, values, twice, types, rules, solos', kinds)

// «to look at» in groups: each key in one group, in the order of the list; only the groups with something; «only one
// has it» and «unused» folded
ok(GROUPS.flatMap((g) => g.keys).sort().join() === ['conflict', 'contradiction', 'spelling', 'contract', 'flow', 'telemetry', 'off', 'gap', 'values', 'twice', 'solo', 'unused', 'type', 'unknown', 'unmatched'].sort().join(), 'every kind of look is in exactly one group', GROUPS)
const looks1 = reviewCast(r1)
const groups1 = groupLooks(looks1)
ok(groups1.flatMap((g) => g.looks.map((x) => x.look)).every((x, i) => x === looks1[i]), 'the groups keep the list and its order', groups1.map((g) => g.key))
ok(groups1.every((g) => g.looks.length > 0) && groups1.flatMap((g) => g.looks.map((x) => x.at)).every((at, i) => at === i), 'only groups with something; each item keeps its place in the list', groups1.map((g) => [g.key, g.looks.length]))
ok(groups1.filter((g) => g.folded).map((g) => g.key).join() === 'solo,unused', 'only «only one has it» and «unused» start folded', groups1.map((g) => [g.key, g.folded]))
ok(groups1.map((g) => g.key).join() === GROUPS.map((g) => g.key).filter((k) => groups1.some((x) => x.key === k)).join(), 'the groups in their order', groups1.map((g) => g.key))
ok(groupLooks([]).length === 0, 'nothing to look at: no group')
ok(GROUPS.every((g) => g.en && g.pt && !/\bagentes?\b|\bagents?\b/i.test(g.en + g.pt)), 'each group named in English and Portuguese, never «agent»')
ok(!reviewCast(r1).some((l) => /\bagentes?\b|\bagents?\b/i.test(l.pt + l.en)), 'still never «agent» on screen')
ok(reviewCast(r1).every((l) => l.en && !/[ãçõ]/.test(l.en.replace(/«[^»]*»|\([^)]*\)/g, ''))), 'each in English too', reviewCast(r1).map((l) => l.en))
done()
