// What the run asks, with no model («to look at»): where people and the YAML disagree, who is off a pattern, the
// rules not met, what only one specialist has (innovation or debt?), what the analysis did not understand, and a
// profile naming what is not in the folder. Questions, not errors; each names the agents, in English and Portuguese.
import type { Pattern, Result } from './compare'
import { labelOf, lacks, matches } from './labels'
import type { Role } from './profile'
import { roleWord } from './words'

export interface Look {
  key: 'conflict' | 'contradiction' | 'off' | 'gap' | 'values' | 'twice' | 'solo' | 'type' | 'unknown' | 'unmatched'
  agents: string[]
  /** The fact it is about, when it is about one (the map opens it). */
  fact?: string
  en: string
  pt: string
}

const names = (xs: string[]) => xs.join(', ')
// the order of «to look at»: what disagrees first, what is only told last
const ORDER: Look['key'][] = ['conflict', 'contradiction', 'off', 'gap', 'values', 'twice', 'solo', 'type', 'unknown', 'unmatched']

export function reviewCast(r: Result): Look[] {
  const out: Look[] = []
  const label = (k: string, lang: 'en' | 'pt') => labelOf(k, lang, r.names)

  for (const c of r.conflicts) {
    const said = c.source ? `«${c.source}»` : null
    const [en, pt] = [label(c.key, 'en'), label(c.key, 'pt')]
    out.push(c.observed
      ? { key: 'conflict', agents: [c.agent], fact: c.key, en: `${c.agent}: ${said ?? 'what was declared'} says it does not have «${en}», but the YAML has it`, pt: `${c.agent}: ${said ?? 'o declarado'} diz que não tem «${pt}», mas o YAML tem` }
      : { key: 'conflict', agents: [c.agent], fact: c.key, en: `${c.agent}: ${said ?? 'what was declared'} says it has «${en}», but the YAML does not`, pt: `${c.agent}: ${said ?? 'o declarado'} diz que tem «${pt}», mas o YAML não tem` })
  }

  // a rule that forbids (`not`) found broken: the agent says one thing and is set up another way
  const holds = (agent: string, pattern: string) => Object.keys(r.agents.find((a) => a.id === agent)?.facts ?? {}).filter((k) => matches(k, pattern))
  for (const g of r.gaps.filter((x) => x.rule.not && !x.rule.has)) {
    for (const agent of [...g.agents].sort()) {
      const not = holds(agent, g.rule.not!)[0] ?? g.rule.not!
      const when = (g.rule.when ?? []).map((w) => holds(agent, w)[0] ?? w)
      const both = (lang: 'en' | 'pt') => (when.length ? `«${when.map((w) => label(w, lang)).join(lang === 'pt' ? '» e «' : '» and «')}», ${lang === 'pt' ? 'mas também' : 'but also'} «${label(not, lang)}»` : `«${label(not, lang)}»`)
      out.push({ key: 'contradiction', agents: [agent], fact: not, en: `${agent} has ${both('en')} (rule «${g.rule.says}»)`, pt: `${agent} tem ${both('pt')} (regra «${g.rule.says}»)` })
    }
  }

  // off a pattern: one question per key, role and type — and a variation of a block is asked as one
  const typeName = (scope: string) => (scope.startsWith('type:') ? r.typeNames[scope.slice(5)] ?? scope.slice(5) : undefined)
  const off = new Map<string, { key: string; role: Role; type?: string; variant: boolean; agents: string[] }>()
  for (const o of r.offPattern) {
    const role = r.roles[o.agent]
    const id = `${o.key} ${role} ${o.scope} ${o.variant ? 'v' : ''}`
    const g = off.get(id) ?? { key: o.key, role, type: typeName(o.scope), variant: !!o.variant, agents: [] }
    g.agents.push(o.agent)
    off.set(id, g)
  }
  for (const g of off.values()) {
    const n = g.agents.length
    const p = r.patterns.find((x) => x.key === g.key)
    const accepted = p?.decision?.status === 'accepted'
    const people = (lang: 'en' | 'pt') => (g.type ? (lang === 'pt' ? `${n} ${roleWord(g.role, lang, n)} de ${g.type}` : `${n} ${g.type} ${roleWord(g.role, lang, n)}`) : `${n} ${roleWord(g.role, lang, n)}`)
    const official = !!p?.official
    if (g.variant) {
      const block = (lang: 'en' | 'pt') => (lang === 'pt' ? `do bloco${official ? ' oficial' : ''} «${label(g.key, lang)}»` : `of the${official ? ' official' : ''} block «${label(g.key, lang)}»`)
      out.push({
        key: 'off', agents: g.agents, fact: g.key,
        en: `${people('en')} ${n === 1 ? 'has' : 'have'} a variation ${block('en')} (${names(g.agents)}): align it?`,
        pt: `${people('pt')} ${n === 1 ? 'tem' : 'têm'} uma variação ${block('pt')} (${names(g.agents)}): alinhar?`,
      })
      continue
    }
    const who = (lang: 'en' | 'pt') => `${people(lang)} ${lacks(g.key, lang, n, r.names)} (${names(g.agents)})`
    out.push({
      key: 'off', agents: g.agents, fact: g.key,
      en: accepted ? `${who('en')}, and the pattern was accepted: correct it?` : official ? `${who('en')}: add it?` : `${who('en')}: on purpose?`,
      pt: accepted ? `${who('pt')}, e o padrão foi aceito: corrigir?` : official ? `${who('pt')}: incluir?` : `${who('pt')}: é intencional?`,
    })
  }

  // a rule only says again what an agent off a pattern already shows: said once
  for (const g of r.gaps.filter((x) => x.rule.has)) {
    const agents = g.agents.filter((a) => !r.offPattern.some((o) => o.agent === a && o.key === g.rule.has)).sort()
    const n = agents.length
    if (!n) continue
    out.push({
      key: 'gap', agents, fact: g.rule.has,
      en: `Rule «${g.rule.says}»: ${n}${g.rule.role ? ` ${roleWord(g.rule.role, 'en', n)}` : ''} ${n === 1 ? 'does' : 'do'} not meet it (${names(agents)})`,
      pt: `Regra «${g.rule.says}»: ${n}${g.rule.role ? ` ${roleWord(g.rule.role, 'pt', n)}` : ''} não ${n === 1 ? 'cumpre' : 'cumprem'} (${names(agents)})`,
    })
  }

  // a marker set in different ways by a role, and twice by one agent
  for (const m of r.markerFindings) {
    if (m.kind === 'values') {
      const who = [...new Set(Object.values(m.byValue).flat())]
      const n = who.length
      // the most common way first
      const ways = Object.entries(m.byValue).sort(([a, x], [b, y]) => y.length - x.length || a.localeCompare(b)).map(([v, as]) => `${v} ${'{in}'} ${as.length}`)
      const k = Object.keys(m.byValue).length
      out.push({
        key: 'values', agents: who.sort(), fact: `text:${m.marker.id}`,
        en: `${n} ${roleWord(m.role, 'en', n)} set «${m.marker.name}» in ${k} ways (${ways.join('; ').replace(/\{in\}/g, 'in')}): unify?`,
        pt: `${n} ${roleWord(m.role, 'pt', n)} definem «${m.marker.name}» de ${k} jeitos (${ways.join('; ').replace(/\{in\}/g, 'em')}): unificar?`,
      })
    } else {
      out.push({
        key: 'twice', agents: [m.agent], fact: `text:${m.marker.id}`,
        en: `${m.agent} sets «${m.marker.name}» ${m.values.length === 2 ? 'twice' : `${m.values.length} times`} (${m.values.join('; ')}): which one holds?`,
        pt: `${m.agent} define «${m.marker.name}» ${m.values.length === 2 ? 'duas vezes' : `${m.values.length} vezes`} (${m.values.join('; ')}): qual vale?`,
      })
    }
  }

  // a solo connector or MCP server brings its connection and its operations along: asked once; and what a broken
  // «not» rule already told about an agent is not asked again
  const covered = new Set(r.solos.filter((s) => /^(connector|mcp):/.test(s.key)).map((s) => `${s.agents[0]} ${s.key.slice(s.key.indexOf(':') + 1)}`))
  const told = r.gaps.filter((g) => g.rule.not).flatMap((g) => g.agents.map((a) => ({ agent: a, keys: [...(g.rule.when ?? []), g.rule.not!] })))
  for (const s of r.solos) {
    const agent = s.agents[0]
    const api = s.key.startsWith('connref:') ? s.key.slice(8) : s.key.startsWith('operation:') ? s.key.slice(10).split('/')[0] : undefined
    if (api && covered.has(`${agent} ${api}`)) continue
    if (told.some((t) => t.agent === agent && t.keys.some((k) => matches(s.key, k)))) continue
    out.push({ key: 'solo', agents: [agent], fact: s.key, en: `Only ${agent} has «${label(s.key, 'en')}»: innovation or debt?`, pt: `Só ${agent} tem «${label(s.key, 'pt')}»: inovação ou dívida?` })
  }

  // a type with too few to compare in
  for (const t of r.typeNotes) {
    const name = r.typeNames[t.type] ?? t.type
    const n = t.agents.length
    out.push({
      key: 'type', agents: t.agents,
      en: `The type «${name}» has ${n} ${roleWord('specialist', 'en', n)} (${names(t.agents)}): nothing to compare in it`,
      pt: `O tipo «${name}» tem ${n} ${roleWord('specialist', 'pt', n)} (${names(t.agents)}): nada a comparar dentro dele`,
    })
  }

  const unknown = new Map<string, string[]>()
  for (const u of r.unknown) unknown.set(u.agent, [...(unknown.get(u.agent) ?? []), u.file])
  for (const [agent, files] of unknown) {
    const n = files.length
    out.push({ key: 'unknown', agents: [agent], en: `${agent}: the analysis did not understand ${n} ${n === 1 ? 'file' : 'files'} (${names(files)})`, pt: `${agent}: a análise não entendeu ${n} ${n === 1 ? 'arquivo' : 'arquivos'} (${names(files)})` })
  }
  for (const id of r.unmatched) out.push({ key: 'unmatched', agents: [], en: `The profile names «${id}», which is not in the folder`, pt: `O perfil cita «${id}», que não está na pasta` })
  return out.sort((a, b) => ORDER.indexOf(a.key) - ORDER.indexOf(b.key))
}

/** The patterns to look at (someone is off, or it was decided) before the ones everybody already follows. */
export function groupPatterns(r: Result): { look: Pattern[]; everyone: Pattern[] } {
  // a part of a fact (a topic that leads to it) goes with that fact: someone off the part makes the fact one to look at
  const offOf = (p: Pattern) => r.offPattern.some((o) => o.key === p.key || o.partOf === p.key)
  const quiet = (p: Pattern) => p.share === 1 && !p.decision && !offOf(p)
  const facts = r.patterns.filter((p) => !p.partOf)
  return { look: facts.filter((p) => !quiet(p)), everyone: facts.filter(quiet) }
}
