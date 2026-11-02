// The profile (the team's standard) and the cast file (what people said, what was decided): read with the line of every
// problem; who is the orchestrator; and the cast file written back without losing the comments people wrote in it.
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readCast, writeCast, type Cast } from '../src/cast'
import { extractAgent } from '../src/extract'
import { agentsIn } from '../src/folder'
import { problemText } from '../src/problems'
import { DEFAULT_PROFILE, readProfile, rolesOf } from '../src/profile'
import { done, ok } from './ok'

const examples = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/cast-list/examples')
const text = (f: string) => readFileSync(join(examples, f), 'utf8')
const agents = agentsIn(join(examples, 'agents')).map((a) => extractAgent(a.id, a.files))

// the example profile
const p = readProfile(text('profile.cast.yaml'))
ok(!p.problems.length && p.profile?.threshold === 0.7 && p.profile.minAgents === 3 && p.profile.rules.length === 2 && p.profile.focusAreas[0]?.facts.length === 3
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
  && at['missing:rules[1].has'] === 7 && at['missing:focus_areas[0].facts'] === 9, 'a typo, a share over 1, 0 agents, an unknown role, a repeated id, what is missing: each with its line', w.problems)
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
done()
