// The diagrams, with no model: what agent-review read, written as plain Mermaid — the topology, a sequence per call of the
// orchestrator, a lens per pattern and the anatomy of each type — so the team's docs (GitHub, a wiki, a README, VS Code)
// show it with nothing of ours. Everything comes from the stage (stageOf): the same nodes, arrows, scenes and lenses, so
// the stage and the diagrams never disagree. Each one also carries `%% title`, `%% # chapter` and `%% > narration`,
// comments for Mermaid that visual-explainer and visual-pitch read to draw it as a lesson.
import type { Result } from './compare'
import { labelOf, shortNames, type Lang } from './labels'
import { groupLooks, type Look } from './review'
import { RELEASE } from './release'
import type { Lens, Stage, StageEdge, StageNode } from './stage'

export interface Diagram { name: string; title: string; intro: string; mermaid: string }

/** Text inside a Mermaid label or message: the characters Mermaid reads as syntax become its entity codes. */
const CODE: Record<string, string> = { '#': '#35;', '"': '#quot;', '<': '#lt;', '>': '#gt;', ';': '#59;', '%': '#37;', '`': '#96;' }
export function esc(s: string): string {
  return s.replace(/\s+/g, ' ').trim().replace(/[#"<>;%`]/g, (c) => CODE[c])
}
/** A file name: lower case, no accent, no space. */
export const slug = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'x'

const STYLE = [
  'classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px',
  'classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px',
  'classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532',
  'classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4',
  'classDef muted fill:#f4f4f4,stroke:#bbb,color:#666',
]
const TONE = { bad: 'stroke:#c0392b,stroke-width:2px', amber: 'stroke:#b7791f,stroke-width:2px', ghost: 'stroke:#888' }

const W = {
  en: {
    customer: 'Customer', orchestrators: 'Orchestrators', specialists: 'Specialists', flows: 'Flows', systems: 'Systems', outside: 'Not in the folder',
    starts: (n: number) => `${n} topic starts`, silent: 'no line in the telemetry', answer: 'the answer',
    topology: 'Topology', topologyIntro: (tel: boolean) => `Who serves the customer and what each one reaches. Thick arrows are calls; thin ones, what each one uses (a flow, a system); dashed, what nobody calls or is not in the folder. Red is what is missing in a call; amber, a short routing description or a flow that returns nothing.${tel ? ' The numbers are the topic starts in the telemetry.' : ''}`,
    scene: (who: string) => `The call to ${who}`, sceneIntro: (who: string) => `What happens, step by step, when the orchestrator hands over to ${who}. ⚠ marks what to look at.`,
    lens: (name: string) => `Lens: ${name}`, ok: 'follows it', amberWord: 'to look at', badWord: 'off',
    type: (t: string) => `The type «${t}»`, typeIntro: (t: string) => `The patterns of the type «${t}» (accepted or still a candidate), and in red who is off each one.`,
    members: (n: number) => `${n} specialist${n === 1 ? '' : 's'}`, accepted: 'accepted', candidate: 'candidate', of: (a: number, b: number) => `${a} of ${b}`,
    fewer: 'too few to compare: no pattern of its own yet', offEdge: 'off', variant: 'a variation',
    scenePrefix: 'scene', lensPrefix: 'lens', typePrefix: 'type', topologyFile: 'topology',
    doc: (n: string) => `${n}: what agent-review read`, privacy: 'These diagrams hold the client’s data: keep this file in the client’s environment.',
    summary: (n: number, o: number, s: number, p: number, off: number, solo: number) => `${n} in the cast (${o} orchestrator${o === 1 ? '' : 's'}, ${s} specialist${s === 1 ? '' : 's'}) · ${p} patterns · ${off} off a pattern · ${solo} only one has`,
    look: 'To look at', nothing: 'Nothing to look at.', diagrams: 'The diagrams', alone: (d: string) => `Each diagram is also on its own in \`${d}/\`, to paste anywhere Mermaid is read.`, made: (v: string) => `Written by agent-review ${v}.`,
  },
  pt: {
    customer: 'Cliente', orchestrators: 'Orquestradores', specialists: 'Especialistas', flows: 'Fluxos', systems: 'Sistemas', outside: 'Fora da pasta',
    starts: (n: number) => `${n} inícios de tópico`, silent: 'sem linha na telemetria', answer: 'a resposta',
    topology: 'Topologia', topologyIntro: (tel: boolean) => `Quem atende o cliente e o que cada um alcança. Setas grossas são chamadas; finas, o que cada um usa (um fluxo, um sistema); tracejadas, o que ninguém chama ou não está na pasta. Em vermelho o que falta numa chamada; em âmbar, uma descrição de roteamento curta ou um fluxo que não devolve nada.${tel ? ' Os números são os inícios de tópico na telemetria.' : ''}`,
    scene: (who: string) => `A chamada para ${who}`, sceneIntro: (who: string) => `O que acontece, passo a passo, quando o orquestrador encaminha para ${who}. ⚠ marca o que olhar.`,
    lens: (name: string) => `Lente: ${name}`, ok: 'cumpre', amberWord: 'para olhar', badWord: 'fora',
    type: (t: string) => `O tipo «${t}»`, typeIntro: (t: string) => `Os padrões do tipo «${t}» (aceitos ou ainda candidatos) e, em vermelho, quem está fora de cada um.`,
    members: (n: number) => `${n} ${n === 1 ? 'especialista' : 'especialistas'}`, accepted: 'aceito', candidate: 'candidato', of: (a: number, b: number) => `${a} de ${b}`,
    fewer: 'poucos para comparar: ainda sem padrão próprio', offEdge: 'fora', variant: 'variação',
    scenePrefix: 'cena', lensPrefix: 'lente', typePrefix: 'tipo', topologyFile: 'topologia',
    doc: (n: string) => `${n}: o que o agent-review leu`, privacy: 'Estes diagramas têm dados do cliente: deixe este arquivo no ambiente dele.',
    summary: (n: number, o: number, s: number, p: number, off: number, solo: number) => `${n} no elenco (${o} ${o === 1 ? 'orquestrador' : 'orquestradores'}, ${s} ${s === 1 ? 'especialista' : 'especialistas'}) · ${p} padrões · ${off} fora do padrão · ${solo} só um tem`,
    look: 'Para olhar', nothing: 'Nada para olhar.', diagrams: 'Os diagramas', alone: (d: string) => `Cada diagrama também está sozinho em \`${d}/\`, para colar onde o Mermaid for lido.`, made: (v: string) => `Escrito pelo agent-review ${v}.`,
  },
}

/** The diagrams of a run, in its language. */
export function diagramsOf(st: Stage, r: Result, lang: Lang): Diagram[] {
  const w = W[lang]
  const named = (id: string) => r.agents.find((a) => a.id === id)?.displayName ?? id
  const brief = shortNames([...r.agents.map((a) => named(a.id)), ...r.contract.missing.map((m) => m.name ?? m.calls)])
  const node = (id: string) => st.nodes.find((n) => n.id === id)
  const labelOfNode = (n: StageNode) => (n.kind === 'client' ? w.customer : n.labels ? n.labels[lang] : n.kind === 'flow' || n.kind === 'system' ? n.label : brief(n.label))
  const used = new Set<string>()
  const file = (base: string) => {
    let name = base
    for (let i = 2; used.has(name); i++) name = `${base}-${i}`
    used.add(name)
    return name
  }
  const head = (kind: string, title: string) => [kind, `  %% title ${title.replace(/\s+/g, ' ')}`, `  %% agent-review ${RELEASE}`]
  const out: Diagram[] = []

  // the topology: the stage's columns as subgraphs, its arrows as links
  {
    const ids = new Map(st.nodes.map((n, i) => [n.id, `n${i + 1}`]))
    const shape = (n: StageNode) => {
      const extra = n.volume !== undefined ? w.starts(n.volume) : n.silent ? w.silent : n.kind === 'client' ? '' : n.sub[lang]
      const text = `"${esc(labelOfNode(n))}${extra ? `<br/><small>${esc(extra)}</small>` : ''}"`
      const id = ids.get(n.id)!
      return n.kind === 'client' ? `${id}([${text}])` : n.kind === 'flow' ? `${id}[/${text}/]` : n.kind === 'system' ? `${id}[(${text})]` : `${id}[${text}]`
    }
    const lines = head('flowchart LR', `${w.topology}${st.name ? ` · ${st.name}` : ''}`)
    const sub = (title: string, list: StageNode[]) => {
      if (!list.length) return
      lines.push(`  subgraph s${lines.length} ["${esc(title)}"]`, ...list.map((n) => `    ${shape(n)}`), '  end')
    }
    const of = (k: StageNode['kind']) => st.nodes.filter((n) => n.kind === k)
    sub(w.customer, of('client'))
    sub(w.orchestrators, of('orchestrator'))
    const specialists = of('specialist')
    const firstType = (id: string) => (r.types[id] ?? [])[0] ?? ''
    for (const t of [...new Set(specialists.map((n) => firstType(n.id)))]) sub(t ? `${w.specialists} · ${r.typeNames[t] ?? t}` : w.specialists, specialists.filter((n) => firstType(n.id) === t))
    sub(w.outside, of('ghost'))
    sub(w.flows, of('flow'))
    sub(w.systems, of('system'))
    const styles: string[] = []
    st.edges.forEach((e, i) => {
      const thick = e.kind === 'traffic'
      const arrow = e.dashed ? '-.->' : thick ? '==>' : '-->'
      const text = [e.label?.[lang], e.volume !== undefined ? String(e.volume) : ''].filter(Boolean).join(' · ')
      lines.push(`  ${ids.get(e.from)} ${arrow}${text ? `|"${esc(text)}"|` : ''} ${ids.get(e.to)}`)
      if (e.tone) styles.push(`  linkStyle ${i} ${TONE[e.tone]}`)
    })
    lines.push(...styles, ...STYLE.map((s) => `  ${s}`))
    const cls = (c: string, list: StageNode[]) => list.length && lines.push(`  class ${list.map((n) => ids.get(n.id)).join(',')} ${c}`)
    cls('ghost', st.nodes.filter((n) => n.kind === 'ghost' || n.unused || n.silent))
    cls('bad', st.nodes.filter((n) => st.edges.some((e) => e.to === n.id && e.kind === 'traffic' && e.tone === 'bad')))
    cls('amber', st.nodes.filter((n) => !st.edges.some((e) => e.to === n.id && e.kind === 'traffic' && e.tone === 'bad') && st.edges.some((e) => e.to === n.id && e.tone === 'amber')))
    out.push({ name: file(w.topologyFile), title: w.topology, intro: w.topologyIntro(st.hasTelemetry), mermaid: `${lines.join('\n')}\n` })
  }

  // a sequence per scene: each step an arrow into the one it happens at, its sentence the message
  for (const sc of st.scenes) {
    const who = sc.title[lang]
    const lines = ['%%{init: {"sequence": {"wrap": true, "width": 220}}}%%', ...head('sequenceDiagram', w.scene(who))]
    const parts = [...new Set(sc.steps.map((s) => s.node))]
    const pid = (id: string) => `p${parts.indexOf(id) + 1}`
    for (const id of parts) {
      const n = node(id)
      lines.push(`  participant ${pid(id)} as ${esc(n ? labelOfNode(n) : id)}`)
    }
    sc.steps.forEach((s, i) => {
      const n = node(s.node)
      const text = `${s.warn ? '⚠ ' : ''}${s.text[lang]}`
      lines.push(`  %% # ${(n ? labelOfNode(n) : s.node).replace(/\s+/g, ' ')}`, `  %% > ${s.text[lang].replace(/\s+/g, ' ')}`)
      // the customer writes to the one the next step happens at; the orchestrator's choice is a note over it
      if (i === 0) return lines.push(`  ${pid(s.node)}->>${pid(sc.steps[1].node)}: ${esc(text)}`)
      if (s.from === 'client') return lines.push(`  Note over ${pid(s.node)}: ${esc(text)}${s.quote ? `<br/>«${esc(s.quote)}»` : ''}`)
      const back = i === sc.steps.length - 1 && s.node === sc.steps[1].node
      lines.push(`  ${pid(s.from!)}${back ? '-->>' : n?.kind === 'ghost' ? '-x' : '->>'}${pid(s.node)}: ${esc(text)}`)
      if (back) lines.push(`  ${pid(s.node)}-->>${pid('client')}: ${esc(w.answer)}`)
    })
    out.push({ name: file(`${w.scenePrefix}-${slug(who)}`), title: w.scene(who), intro: w.sceneIntro(who), mermaid: `${lines.join('\n')}\n` })
  }

  // a lens per pattern: the orchestrators and the specialists, painted
  for (const l of st.lenses) out.push(lensOf(l))
  function lensOf(l: Lens): Diagram {
    const cast = st.nodes.filter((n) => n.kind === 'orchestrator' || n.kind === 'specialist')
    const ids = new Map(cast.map((n, i) => [n.id, `n${i + 1}`]))
    const state = (id: string) => (l.bad.includes(id) ? 'bad' : l.amber.includes(id) ? 'amber' : l.ok.includes(id) ? 'ok' : 'muted')
    const word = { bad: w.badWord, amber: w.amberWord, ok: w.ok, muted: '' }
    const lines = head('flowchart LR', w.lens(l.name[lang]))
    for (const n of cast) {
      const s = state(n.id)
      lines.push(`  ${ids.get(n.id)}["${esc(brief(n.label))}${word[s] ? `<br/><small>${esc(word[s])}</small>` : ''}"]`)
    }
    for (const e of st.edges.filter((x: StageEdge) => ids.has(x.from) && ids.has(x.to))) lines.push(`  ${ids.get(e.from)} --> ${ids.get(e.to)}`)
    lines.push(...STYLE.map((s) => `  ${s}`))
    for (const c of ['ok', 'amber', 'bad', 'muted'] as const) {
      const list = cast.filter((n) => state(n.id) === c)
      if (list.length) lines.push(`  class ${list.map((n) => ids.get(n.id)).join(',')} ${c}`)
    }
    return { name: file(`${w.lensPrefix}-${slug(l.name[lang])}`), title: w.lens(l.name[lang]), intro: l.caption[lang], mermaid: `${lines.join('\n')}\n` }
  }

  // the anatomy of each type: its patterns and who is off each one
  const specialists = r.agents.filter((a) => a.role === 'specialist')
  for (const t of [...new Set(specialists.flatMap((a) => r.types[a.id] ?? []))]) {
    const tn = r.typeNames[t] ?? t
    const members = specialists.filter((a) => (r.types[a.id] ?? []).includes(t)).map((a) => a.id)
    const scope = `type:${t}`
    const pats = r.patterns.filter((p) => p.scope === scope && !p.partOf).filter((p, i, all) => all.findIndex((q) => q.key === p.key) === i)
    const lines = head('flowchart TD', w.type(tn))
    lines.push(`  t["«${esc(tn)}»<br/><small>${esc(`${w.members(members.length)}: ${members.map((m) => brief(named(m))).join(', ')}`)}</small>"]`)
    if (!pats.length) lines.push(`  t --- none["${esc(w.fewer)}"]`)
    const mid = (id: string) => `m${members.indexOf(id) + 1}`
    const offs = new Set<string>()
    const links: string[] = []
    pats.forEach((p, i) => {
      const off = r.offPattern.filter((o) => o.key === p.key && o.scope === scope)
      const has = members.filter((m) => !off.some((o) => o.agent === m)).length
      const status = p.decision?.status === 'accepted' ? w.accepted : w.candidate
      lines.push(`  %% # ${labelOf(p.key, lang, r.names).replace(/\s+/g, ' ')}`, `  t --> q${i + 1}["${esc(labelOf(p.key, lang, r.names))}<br/><small>${esc(`${status} · ${w.of(has, members.length)}`)}</small>"]`)
      for (const o of off) {
        offs.add(o.agent)
        links.push(`  q${i + 1} -.->|"${esc(o.variant ? w.variant : w.offEdge)}"| ${mid(o.agent)}`)
      }
    })
    for (const m of members.filter((x) => offs.has(x))) lines.push(`  ${mid(m)}["${esc(brief(named(m)))}"]`)
    lines.push(...links, ...STYLE.map((s) => `  ${s}`))
    const bad = members.filter((m) => r.offPattern.some((o) => o.agent === m && o.scope === scope && !o.variant))
    const amber = members.filter((m) => offs.has(m) && !bad.includes(m))
    if (bad.length) lines.push(`  class ${bad.map(mid).join(',')} bad`)
    if (amber.length) lines.push(`  class ${amber.map(mid).join(',')} amber`)
    out.push({ name: file(`${w.typePrefix}-${slug(tn)}`), title: w.type(tn), intro: w.typeIntro(tn), mermaid: `${lines.join('\n')}\n` })
  }
  return out
}

/** The delivery document: the summary, «to look at» in words and every diagram in a ```mermaid block. */
export function diagramsDoc(id: string, diagrams: Diagram[], r: Result, looks: Look[], lang: Lang): string {
  const w = W[lang]
  const roles = Object.values(r.roles)
  const out = [`# ${w.doc(r.name ?? id)}`, '', `> ${w.privacy}`, '',
    w.summary(r.agents.length, roles.filter((x) => x === 'orchestrator').length, roles.filter((x) => x === 'specialist').length, r.patterns.length, new Set(r.offPattern.map((o) => o.agent)).size, looks.filter((l) => l.key === 'solo').length), '',
    `## ${w.look}`, '']
  const groups = groupLooks(looks)
  if (!groups.length) out.push(w.nothing, '')
  for (const g of groups) out.push(`### ${g[lang]} · ${g.looks.length}`, '', ...g.looks.map(({ look }) => `- ${look[lang]}`), '')
  out.push(`## ${w.diagrams}`, '', w.alone(`${id}.diagrams`), '')
  for (const d of diagrams) out.push(`### ${d.title}`, '', d.intro, '', '```mermaid', d.mermaid.trimEnd(), '```', '')
  out.push('---', '', w.made(RELEASE), '')
  return out.join('\n')
}
