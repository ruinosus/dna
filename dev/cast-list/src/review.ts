// What the run asks, with no model («to look at»): where people and the YAML disagree, who is off a pattern, the
// rules not met, what only one specialist has (innovation or debt?), what the analysis did not understand, and a
// profile naming what is not in the folder. Questions, not errors; each names the agents, in English and Portuguese.
import type { Pattern, Result } from './compare'
import { labelOf, lacks } from './labels'
import type { Role } from './profile'
import { roleWord } from './words'

export interface Look {
  key: 'conflict' | 'off' | 'gap' | 'solo' | 'unknown' | 'unmatched'
  agents: string[]
  /** The fact it is about, when it is about one (the map opens it). */
  fact?: string
  en: string
  pt: string
}

const names = (xs: string[]) => xs.join(', ')

export function reviewCast(r: Result): Look[] {
  const out: Look[] = []

  for (const c of r.conflicts) {
    const said = c.source ? `«${c.source}»` : null
    const [en, pt] = [labelOf(c.key, 'en', r.names), labelOf(c.key, 'pt', r.names)]
    out.push(c.observed
      ? { key: 'conflict', agents: [c.agent], fact: c.key, en: `${c.agent}: ${said ?? 'what was declared'} says it does not have «${en}», but the YAML has it`, pt: `${c.agent}: ${said ?? 'o declarado'} diz que não tem «${pt}», mas o YAML tem` }
      : { key: 'conflict', agents: [c.agent], fact: c.key, en: `${c.agent}: ${said ?? 'what was declared'} says it has «${en}», but the YAML does not`, pt: `${c.agent}: ${said ?? 'o declarado'} diz que tem «${pt}», mas o YAML não tem` })
  }

  // off a pattern: one question per key and role
  const off = new Map<string, { key: string; role: Role; agents: string[] }>()
  for (const o of r.offPattern) {
    const role = r.roles[o.agent]
    const g = off.get(`${o.key} ${role}`) ?? { key: o.key, role, agents: [] }
    g.agents.push(o.agent)
    off.set(`${o.key} ${role}`, g)
  }
  for (const g of off.values()) {
    const n = g.agents.length
    const accepted = r.patterns.find((p) => p.key === g.key)?.decision?.status === 'accepted'
    const who = (lang: 'en' | 'pt') => `${n} ${roleWord(g.role, lang, n)} ${lacks(g.key, lang, n, r.names)} (${names(g.agents)})`
    out.push({
      key: 'off', agents: g.agents, fact: g.key,
      en: accepted ? `${who('en')}, and the pattern was accepted: correct it?` : `${who('en')}: on purpose?`,
      pt: accepted ? `${who('pt')}, e o padrão foi aceito: corrigir?` : `${who('pt')}: é intencional?`,
    })
  }

  // a rule only says again what an agent off a pattern already shows: said once
  for (const g of r.gaps) {
    const agents = g.agents.filter((a) => !r.offPattern.some((o) => o.agent === a && o.key === g.rule.has)).sort()
    const n = agents.length
    if (!n) continue
    out.push({
      key: 'gap', agents, fact: g.rule.has,
      en: `Rule «${g.rule.says}»: ${n}${g.rule.role ? ` ${roleWord(g.rule.role, 'en', n)}` : ''} ${n === 1 ? 'does' : 'do'} not meet it (${names(agents)})`,
      pt: `Regra «${g.rule.says}»: ${n}${g.rule.role ? ` ${roleWord(g.rule.role, 'pt', n)}` : ''} não ${n === 1 ? 'cumpre' : 'cumprem'} (${names(agents)})`,
    })
  }

  // a solo connector or MCP server brings its connection and its operations along: asked once
  const covered = new Set(r.solos.filter((s) => /^(connector|mcp):/.test(s.key)).map((s) => `${s.agents[0]} ${s.key.slice(s.key.indexOf(':') + 1)}`))
  for (const s of r.solos) {
    const agent = s.agents[0]
    const api = s.key.startsWith('connref:') ? s.key.slice(8) : s.key.startsWith('operation:') ? s.key.slice(10).split('/')[0] : undefined
    if (api && covered.has(`${agent} ${api}`)) continue
    out.push({ key: 'solo', agents: [agent], fact: s.key, en: `Only ${agent} has «${labelOf(s.key, 'en', r.names)}»: innovation or debt?`, pt: `Só ${agent} tem «${labelOf(s.key, 'pt', r.names)}»: inovação ou dívida?` })
  }

  const unknown = new Map<string, string[]>()
  for (const u of r.unknown) unknown.set(u.agent, [...(unknown.get(u.agent) ?? []), u.file])
  for (const [agent, files] of unknown) {
    const n = files.length
    out.push({ key: 'unknown', agents: [agent], en: `${agent}: the analysis did not understand ${n} ${n === 1 ? 'file' : 'files'} (${names(files)})`, pt: `${agent}: a análise não entendeu ${n} ${n === 1 ? 'arquivo' : 'arquivos'} (${names(files)})` })
  }
  for (const id of r.unmatched) out.push({ key: 'unmatched', agents: [], en: `The profile names «${id}», which is not in the folder`, pt: `O perfil cita «${id}», que não está na pasta` })
  return out
}

/** The patterns to look at (someone is off, or it was decided) before the ones everybody already follows. */
export function groupPatterns(r: Result): { look: Pattern[]; everyone: Pattern[] } {
  // a part of a fact (a topic that leads to it) goes with that fact: someone off the part makes the fact one to look at
  const offOf = (p: Pattern) => r.offPattern.some((o) => o.key === p.key || o.partOf === p.key)
  const quiet = (p: Pattern) => p.share === 1 && !p.decision && !offOf(p)
  const facts = r.patterns.filter((p) => !p.partOf)
  return { look: facts.filter((p) => !quiet(p)), everyone: facts.filter(quiet) }
}
