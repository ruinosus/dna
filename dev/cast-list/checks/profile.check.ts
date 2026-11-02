// The profile (the team's standard) and the cast file (what people said, what was decided): read with the line of every
// problem; who is the orchestrator; and the cast file written back without losing the comments people wrote in it.
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readCast, writeCast, type Cast } from '../src/cast'
import { extractAgent } from '../src/extract'
import { agentsIn } from '../src/folder'
import { problemText } from '../src/problems'
import { DEFAULT_PROFILE, readProfile, rolesOf, typesOf } from '../src/profile'
import { done, ok } from './ok'

const examples = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/cast-list/examples')
const text = (f: string) => readFileSync(join(examples, f), 'utf8')
const agents = agentsIn(join(examples, 'agents')).map((a) => extractAgent(a.id, a.files))

// the example profile
const p = readProfile(text('profile.cast.yaml'))
ok(!p.problems.length && p.profile?.threshold === 0.7 && p.profile.minAgents === 3 && p.profile.rules.length === 3 && p.profile.markers.length === 3 && p.profile.blocks[0]?.id === 'links' && p.profile.types.length === 3 && p.profile.focusAreas[0]?.facts.length === 3
  && p.profile.ignore.join() === 'trigger:OnConversationStart' && p.profile.microsoftPatterns, 'the example profile is read', p)
const roles = rolesOf(agents, p.profile!)
ok(roles.roles['bodega-orquestrador'] === 'orchestrator' && Object.values(roles.roles).filter((r) => r === 'specialist').length === 5 && !roles.unmatched.length, 'by the profile: one orchestrator, five specialists', roles)

// with no profile: the orchestrator is who calls another agent (a topic call does not count)
const auto = rolesOf(agents, DEFAULT_PROFILE)
ok(auto.roles['bodega-orquestrador'] === 'orchestrator' && auto.roles['bodega-frete'] === 'specialist' && Object.keys(auto.roles).length === 6, 'with no profile: whoever calls an agent is the orchestrator', auto)
ok(DEFAULT_PROFILE.threshold === 0.7 && DEFAULT_PROFILE.minAgents === 3, 'the defaults: 0.7 and 3')
const bare = readProfile('format: cast-list/profile-v1\n')
ok(!bare.problems.length && bare.profile?.threshold === 0.7 && !bare.profile.rules.length, 'a profile with only its format is the defaults')
// the cast file's role counts when the profile does not name the agent; a name in the profile wins
const given = rolesOf(agents, { ...DEFAULT_PROFILE, roles: { orchestrator: ['bodega-orquestrador'] } }, { 'bodega-frete': 'orchestrator', 'bodega-orquestrador': 'specialist' })
ok(given.roles['bodega-frete'] === 'orchestrator' && given.roles['bodega-orquestrador'] === 'orchestrator', "the cast file's role, under the profile's", given.roles)
// a profile naming an agent that is not there says so
const ghost = rolesOf(agents, { ...p.profile!, roles: { orchestrator: ['orquestrador-antigo'], specialist: '*' } })
ok(ghost.unmatched.join() === 'orquestrador-antigo', 'a profile naming an agent that is not in the folder: told', ghost.unmatched)

// what is wrong says its line
const wrong = `format: cast-list/profile-v1
treshold: 0.7
threshold: 1.5
min_agents: 0
rules:
  - { id: escala, role: especialista, has: "trigger:OnEscalate", says: x }
  - { id: escala, role: specialist, says: y }
focus_areas:
  - { id: f, name: F }
`
const w = readProfile(wrong)
const at = Object.fromEntries(w.problems.map((x) => [`${x.key}${'what' in x ? `:${x.what}` : ''}`, x.line]))
ok(at['unknownKey:treshold'] === 2 && at['threshold'] === 3 && at['minAgents'] === 4 && at['role:rules[0].role'] === 6 && at['duplicate:rules'] === 7
  && at['rule:rules[1]'] === 7 && at['missing:focus_areas[0].facts'] === 9, 'a typo, a share over 1, 0 agents, an unknown role, a repeated id, what is missing: each with its line', w.problems)
ok(readProfile('format: other\n').problems[0]?.key === 'format' && readProfile('roles: [x\n').problems[0]?.key === 'syntax', 'another format, or YAML that does not read')
ok(problemText(w.problems.find((x) => x.key === 'role')!, 'pt') === '«rules[0].role» é orchestrator ou specialist (está «especialista»)', 'a problem in Portuguese', w.problems.map((x) => problemText(x, 'pt')))

// the cast file
const c = readCast(text('demo.cast.yaml'))
ok(!c.problems.length && c.cast?.declared.length === 2 && c.cast.decisions[0]?.status === 'accepted' && c.cast.decisions[0].scope === 'platform', 'the example cast file is read', c)
const bad = readCast(`format: cast-list/cast-v1
declared:
  - { agent: bodega-frete, value: sim }
decisions:
  - { key: "trigger:OnEscalate", status: aceito, scope: platform }
  - { key: "trigger:OnEscalate", status: rejected, scope: everywhere }
`)
const b = Object.fromEntries(bad.problems.map((x) => [`${x.key}${'what' in x ? `:${x.what}` : ''}`, x.line]))
ok(b['missing:declared[0].key'] === 3 && b['status'] === 5 && b['duplicate:decisions'] === 6 && b['scope'] === 6, 'a declared line with no key, a status in Portuguese, a repeated decision, an unknown scope: each with its line', bad.problems)

// written back: the same thing, and the comments stay
const cast = c.cast!
const again = writeCast(cast, text('demo.cast.yaml'))
ok(again === text('demo.cast.yaml'), 'written back unchanged, it is the same file byte for byte', again)
const more: Cast = {
  ...cast,
  agents: agents.map((a) => ({ id: a.id, role: roles.roles[a.id] })),
  declared: [...cast.declared, { agent: 'bodega-frete', key: 'kpi', value: 'cotação em < 5 s', source: 'planilha' }],
  decisions: [{ ...cast.decisions[0], why: 'Sempre há uma pessoa' }, { key: 'node:LogCustomTelemetryEvent', status: 'accepted', scope: 'platform', why: '' }],
}
const written = writeCast(more, text('demo.cast.yaml'))
const back = readCast(written)
ok(!back.problems.length && JSON.stringify(back.cast) === JSON.stringify(more), 'written with changes, it reads back as what was written', { written })
ok(written.includes('# the handoff document says frete escalates') && written.includes('# What people said about the agents'), "the person's comments stay", written)
ok(readCast(writeCast(more)).cast !== undefined && JSON.stringify(readCast(writeCast(more)).cast) === JSON.stringify(more), 'a new cast file (no previous one) reads back too')
// wave 1: markers, official blocks, types, and rules with a condition
const w1 = readProfile(`format: cast-list/profile-v1
markers:
  - { id: size, name: Tamanho da resposta, in: instructions, pattern: 'no máximo\\s*(\\d+)\\s*(bullets?|frases?)', value: "$1 $2" }
  - { id: no-emoji, name: Sem emojis, pattern: '(sem|não use)\\s+emojis?' }
blocks:
  - { id: links, name: Formatação de links, text: "Formate links assim: [título](url), nunca a URL crua." }
types:
  - { id: transaction, name: transação, when: { any: ["flow:*"] } }
  - { id: guidance, name: orientação, when: { all: ["text:link-domain:*", "node:SearchAndSummarizeContent"], none: ["flow:*"] }, min_agents: 3 }
rules:
  - { id: knowledge-only, when: "text:knowledge-only", not: "setting:model-knowledge=on", says: Quem pede só o conhecimento tem o conhecimento geral desligado }
`)
const pf = w1.profile!
ok(!w1.problems.length && pf.markers.length === 2 && pf.markers[0].in === 'instructions' && pf.markers[1].in === 'instructions' && pf.markers[0].value === '$1 $2', 'markers are read; «in» is instructions unless said', w1)
ok(pf.blocks[0]?.id === 'links' && pf.blocks[0].role === 'specialist', 'an official block, for the specialists unless said')
ok(pf.types.length === 2 && pf.types[0].minAgents === 2 && pf.types[1].minAgents === 3 && pf.types[1].when.none?.join() === 'flow:*', 'types: when all / any / none, min_agents 2 unless said')
ok(pf.rules[0].when?.join() === 'text:knowledge-only' && pf.rules[0].not === 'setting:model-knowledge=on' && !pf.rules[0].has && !pf.rules[0].role, 'a rule with a condition and a «not», for every role')
const broken = readProfile(`format: cast-list/profile-v1
markers:
  - { id: m, name: M, pattern: "(unclosed" }
  - { id: n, name: N, in: everywhere, pattern: "x" }
types:
  - { id: t, name: T }
  - { id: u, name: U, when: { any: ["nonsense:thing"] } }
rules:
  - { id: r, says: nothing to check }
`)
const by = Object.fromEntries(broken.problems.map((x) => [x.key, x.line]))
ok(by.regex === 3 && by.in === 4 && by.when === 6 && by.prefix === 7 && by.rule === 9, 'a broken regex, an unknown «in», a type with no when, a key no kind has, a rule with nothing to check: each with its line', broken.problems)
ok(problemText(broken.problems.find((x) => x.key === 'prefix')!, 'pt').includes('nonsense:thing'), 'the unknown key is named', broken.problems.map((x) => problemText(x, 'pt')))

// the types of each agent: every type that matches; the cast file's types first
const f = (keys: string[]) => Object.fromEntries(keys.map((k) => [k, [{ file: 'x' }]]))
const as = [
  { id: 'a', facts: f(['flow:1', 'text:link-domain:ajuda.example', 'node:SearchAndSummarizeContent']) },
  { id: 'b', facts: f(['text:link-domain:ajuda.example', 'node:SearchAndSummarizeContent']) },
  { id: 'c', facts: f(['flow:2']) },
  { id: 'd', facts: f(['node:SearchAndSummarizeContent']) },
]
const specialists = { a: 'specialist', b: 'specialist', c: 'specialist', d: 'specialist' } as const
const ts = typesOf(as, specialists, pf, { d: ['guidance'] })
ok(ts.a.join() === 'transaction' && ts.b.join() === 'guidance' && ts.c.join() === 'transaction' && ts.d.join() === 'guidance', 'a type when its keys match («none» rules out); the cast file gives d its type', ts)
const multi = typesOf(as, specialists, { ...pf, types: [pf.types[0], { ...pf.types[1], when: { all: ['text:link-domain:*'] } }] }, {})
ok(multi.a.join() === 'transaction,guidance', 'an agent gets every type that matches', multi)
ok(!typesOf([{ id: 'o', facts: f(['flow:1']) }], { o: 'orchestrator' }, pf, {}).o?.length, 'an orchestrator has no type')

// the cast file: types and the blocks kept
const castText = `format: cast-list/cast-v1
agents:
  - { id: a, role: specialist, types: [ transaction, guidance ] }
blocks:
  - { id: links, text: "Formate links assim: [título](url), nunca a URL crua." }
decisions:
  - { key: "text:block:links", status: accepted, scope: "type:guidance", why: Todos formatam igual }
`
const cr = readCast(castText)
ok(!cr.problems.length && cr.cast?.agents[0].types?.join() === 'transaction,guidance' && cr.cast.blocks[0].id === 'links' && cr.cast.decisions[0].scope === 'type:guidance', 'the cast file: types, the blocks kept, a type scope', cr)
ok(writeCast(cr.cast!, castText) === castText, 'written back unchanged, byte for byte (in the style it writes: [ a, b ])')
ok(readCast(castText.replace('type:guidance', 'tipo')).problems[0]?.key === 'scope', 'a scope that is not one is told')
done()
