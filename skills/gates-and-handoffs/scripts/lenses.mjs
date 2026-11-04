// The same way of working seen by the other skills: a .way.yaml (as readWay read it) written as a box-office simulation,
// a service blueprint and a dress-rehearsal drill. Each lens is an ordinary recipe of its skill, checked by that skill.
//
// Each lens starts with `# from: <file>.way.yaml@<hash>`: the way it came from and the version (the first 8 of the
// sha256 of its text), so a lens left behind by a change of the way can be told.
//
// Deriving is not inventing: every number or line the way does not have (a volume, a time, a team size, what the
// customer does, a scene) comes out as a bet, marked `# bet:` in the recipe and counted, so the person replaces it.

const T = {
  en: {
    from: (f) => `Derived from ${f} by gates-and-handoffs --lens.`,
    bpHead: 'bet: «customer» is what whoever the work is for does at each stage; the way says what the team does.',
    bpHead2: 'feels and pains are left out: they come from interviews, never from the way.',
    drHead: 'bet: the scenes are a draft: rewrite them with what really happens when this gate says no.',
    betsHead: 'bet: the volumes, the times and the team sizes are made up: replace them with your own.',
    one: (r) => `One more ${r}`,
    delivered: 'Delivered',
    noWay: (g) => `Nothing says where the work goes when «${g}» says no.`,
    noCriteria: (g) => `«${g}» has no criteria written: nobody knows what it needs to say yes.`,
    noApprover: (g) => `«${g}» has no approver: who decides?`,
    who: 'Whoever the work is for',
    about: (n) => `The way «${n}», seen from the side of whoever the work is for.`,
    customer: (s) => `Waits while «${s}» happens`,
    customerQ: (s, q) => `Waits for «${s}»: ${q}`,
    impact: 'days late',
    drillName: (g) => `«${g}» says no`,
    drillAbout: (g, n) => `On the eve of the delivery, «${g}» of the way «${n}» says no.`,
    reproved: (g, l, item) => `«${g}» comes back «${l}» for the ${item} due tomorrow.`,
    item: 'work',
    back: (s) => `Go back to «${s}» and redo it`,
    ask: (r) => `Call ${r} to understand what was missing`,
    push: 'Go ahead anyway',
    tell: 'Tell whoever is waiting that it will be late',
    told: 'Whoever is waiting knows it will be late. The gate still says no.',
    explains: (r, g, needs) => `${r} explains what «${g}» needs: ${needs}.`,
    needsNothing: 'nothing is written; it was a feeling',
    redone: (s, g) => `«${s}» is redone and comes back to «${g}», which says yes. A day late.`,
    worse: (g, next) => `It went ahead without «${g}»${next ? `: the problem shows up at «${next}»` : ''}.`,
    rework: (s) => `rework «${s}»`,
    decide: (g) => `decide «${g}»`,
    source: (f) => `${f}`,
  },
  pt: {
    from: (f) => `Derivado de ${f} pelo gates-and-handoffs --lens.`,
    bpHead: 'bet: «customer» é o que faz quem recebe o trabalho em cada etapa; o way diz o que o time faz.',
    bpHead2: 'feels e pains ficam de fora: vêm de entrevistas, nunca do way.',
    drHead: 'bet: as cenas são um rascunho: reescreva com o que acontece de fato quando este gate diz não.',
    betsHead: 'bet: os volumes, os tempos e o tamanho das equipes são apostas: troque pelos seus.',
    one: (r) => `Mais um ${r}`,
    delivered: 'Entregue',
    noWay: (g) => `Nada diz para onde o trabalho vai quando «${g}» diz não.`,
    noCriteria: (g) => `«${g}» não tem critério escrito: ninguém sabe o que precisa para dizer sim.`,
    noApprover: (g) => `«${g}» não tem quem aprove: quem decide?`,
    who: 'Quem recebe o trabalho',
    about: (n) => `O fluxo «${n}», visto do lado de quem recebe o trabalho.`,
    customer: (s) => `Espera enquanto «${s}» acontece`,
    customerQ: (s, q) => `Espera «${s}»: ${q}`,
    impact: 'dias de atraso',
    drillName: (g) => `«${g}» diz não`,
    drillAbout: (g, n) => `Na véspera da entrega, «${g}» do fluxo «${n}» diz não.`,
    reproved: (g, l, item) => `«${g}» volta «${l}» para o ${item} que entrega amanhã.`,
    item: 'trabalho',
    back: (s) => `Voltar para «${s}» e refazer`,
    ask: (r) => `Chamar ${r} para entender o que faltou`,
    push: 'Seguir mesmo assim',
    tell: 'Avisar quem espera que vai atrasar',
    told: 'Quem espera já sabe do atraso. O gate continua dizendo não.',
    explains: (r, g, needs) => `${r} explica o que «${g}» precisa: ${needs}.`,
    needsNothing: 'nada está escrito; era impressão',
    redone: (s, g) => `«${s}» é refeito e volta a «${g}», que diz sim. Um dia de atraso.`,
    worse: (g, next) => `Seguiu sem «${g}»${next ? `: o problema aparece em «${next}»` : ''}.`,
    rework: (s) => `refazer «${s}»`,
    decide: (g) => `decidir «${g}»`,
    source: (f) => `${f}`,
  },
}

const sid = (id) => String(id).replace(/[^\p{L}\p{N}_]/gu, '_') // a .sim id: letters, digits and _
const did = (id) => String(id).toLowerCase().replace(/[^a-z0-9-]/g, '-') // a blueprint or drill id: a-z0-9-
const q = (s) => JSON.stringify(String(s)) // a YAML string, safe for any text
const approverOf = (g) => g.approver ?? g.approvals?.[0]?.by ?? null
const failures = (g) => (g.results?.length ? g.results.filter((r) => !r.ok) : [{ id: 'no', label: 'No' }])
const roleName = (way, id) => way.roles.find((r) => r.id === id)?.name ?? id
const stageName = (way, id) => way.stages.find((s) => s.id === id)?.name ?? id
const gateAfter = (way, stage) => way.gates.find((g) => g.after === stage)

/** The way as a .sim: stages and gates in their order, the roles as teams, each gate's «no» going back to its on_fail
 * (a loop: rework) or out to an end of its own. */
export function simOf(way, name, from, lang = 'en') {
  const file = from.split('@')[0]
  const t = T[lang]
  const bets = []
  const bet = (what) => (bets.push(what), `   # bet: ${what}`)
  const order = way.stages.map((s) => s.id)
  const used = new Set()
  const lines = [`# from: ${from}`, `# ${t.from(file)}`, `# ${t.betsHead}`, `sim ${q(name)}`, 'lang en', 'horizon 3 months', 'seed 1', '']
  lines.push(`arrive item 5/week${bet('5 items a week')}`)
  for (const s of way.stages) if (s.roles?.[0]) used.add(s.roles[0])
  for (const g of way.gates) if (approverOf(g)) used.add(approverOf(g))
  const roles = way.roles.filter((r) => used.has(r.id))
  for (const r of roles) lines.push(`pool ${sid(r.id)} $${sid(r.id)} shift 8h/day days mon-fri`)
  lines.push('')
  for (const s of way.stages) {
    const by = s.roles?.[0] ? ` by ${sid(s.roles[0])}` : ''
    lines.push(`step ${sid(s.id)}${by} time ~4h${bet(`«${s.name}» takes about 4h of work`)}`)
    if (s.wip) lines.push(`# wip ${s.wip} in the way: the team's limit of items at once; here the team's size sets it`)
    const g = gateAfter(way, s.id)
    if (g) {
      const a = approverOf(g)
      lines.push(`step ${sid(g.id)}${a ? ` by ${sid(a)}` : ''} time ~1h${bet(`deciding «${g.name}» takes about 1h`)}`)
    }
  }
  lines.push('', 'end delivered')
  const outEnds = []
  for (const g of way.gates) if (!g.on_fail) for (const f of failures(g)) outEnds.push(`${sid(g.id)}_${sid(f.id)}`)
  for (const e of outEnds) lines.push(`end ${e}`)
  lines.push('')
  // where each step goes: a stage to its gate or the next stage (an optional one is skipped by a share), a gate to the
  // next stage, its «no» back to on_fail or out
  const knobs = []
  const after = (i) => (i + 1 < order.length ? order[i + 1] : null)
  const entering = (id) => sid(id)
  way.stages.forEach((s, i) => {
    const g = gateAfter(way, s.id)
    const nextStage = after(i)
    const toNext = (from) => {
      const n = nextStage ? way.stages[i + 1] : null
      if (!n) return [`${from} -> delivered`]
      if (n.optional) {
        const k = `${sid(n.id)}_share`
        knobs.push(`knob ${k} 0%..100% = 50%${bet(`half the items go through «${n.name}»`)}`)
        const skip = after(i + 1)
        return [`${from} ->`, `  ${entering(n.id)} $${k}`, `  ${skip ? entering(skip) : 'delivered'} rest`]
      }
      return [`${from} -> ${entering(n.id)}`]
    }
    if (!g) return lines.push(...toNext(sid(s.id)))
    lines.push(`${sid(s.id)} -> ${sid(g.id)}`)
    const fails = failures(g)
    const n = way.stages[i + 1]
    const okTarget = !n ? 'delivered' : n.optional ? null : entering(n.id)
    lines.push(`${sid(g.id)} ->`)
    // the «no» answers share the gate: together, at the top of their ranges, never all of it
    const top = Math.floor(90 / fails.length), init = Math.min(20, Math.floor(top / 2))
    for (const f of fails) {
      const k = `${sid(g.id)}_${sid(f.id)}`
      knobs.push(`knob ${k} 0%..${top}% = ${init}%${bet(`«${g.name}» says «${f.label ?? f.id}» to ${init}%`)}`)
      lines.push(`  ${g.on_fail ? entering(g.on_fail) : k} $${k}`)
    }
    if (okTarget) lines.push(`  ${okTarget} rest`)
    else if (g.on_fail === n.id) {
      // the gate's «no» is the way into the optional stage: its «yes» goes past it
      const skip = after(i + 1)
      lines.push(`  ${skip ? entering(skip) : 'delivered'} rest`)
    } else {
      // the next stage is optional: the gate's yes goes through it by a share of its own
      const k = `${sid(n.id)}_share`
      const skip = after(i + 1)
      lines.push(`  ${entering(n.id)} $${k}`, `  ${skip ? entering(skip) : 'delivered'} rest`)
      knobs.push(`knob ${k} 0%..100% = 50%${bet(`half the items go through «${n.name}»`)}`)
    }
  })
  lines.push('')
  for (const r of roles) knobs.push(`knob ${sid(r.id)} 1..20 = 3${bet(`3 people as ${r.name}`)}`)
  lines.push(...[...new Set(knobs)])
  for (const r of roles) lines.push(`scenario ${q(t.one(r.name))}: ${sid(r.id)} = 4`)
  lines.push('')
  lines.push(outEnds.length ? 'show share end delivered' : 'show count end delivered')
  for (const g of way.gates) if (approverOf(g)) lines.push(`show wait p90 at ${sid(g.id)}`)
  for (const r of roles) lines.push(`show utilization ${sid(r.id)}`)
  // labels: the names as the way has them, and its English names when it has them
  const label = (id, nm, en) => [`  ${id}: ${String(nm).replace(/\n/g, ' ')}`, `  ${id}: ${String(en ?? nm).replace(/\n/g, ' ')}`]
  const pt = [], en = []
  const push = (id, nm, enName) => { const [a, b] = label(id, nm, enName); pt.push(a); en.push(b) }
  const E = way.en ?? {}
  push('item', lang === 'pt' ? 'Item' : 'Item')
  for (const r of roles) push(sid(r.id), r.name, E[r.id])
  for (const s of way.stages) push(sid(s.id), s.name, E[s.id])
  for (const g of way.gates) push(sid(g.id), g.name, E[g.id])
  push('delivered', T.pt.delivered, T.en.delivered)
  // a «no» answer: the end it leads to, or (when it goes back) the control of its share — the same id, so one label
  for (const g of way.gates) for (const f of failures(g)) push(`${sid(g.id)}_${sid(f.id)}`, `${g.name}: ${f.label ?? f.id}`)
  for (const s of way.stages) if (s.optional && s !== way.stages[0]) push(`${sid(s.id)}_share`, s.name)
  lines.push('', 'labels en:', ...en, 'labels pt-BR:', ...pt, '')
  return { text: lines.join('\n'), bets }
}

/** The way as a service blueprint: each stage a moment of the person the work is for, its lead on stage and the others
 * backstage, what it delivers as what they see, a wait after each gate, and each moment pointing at its stage. */
export function blueprintOf(way, name, from, id, lang = 'en') {
  const file = from.split('@')[0]
  const t = T[lang]
  const bets = []
  const lead = new Set(way.stages.map((s) => s.roles?.[0]).filter(Boolean))
  const systems = [...new Set(way.stages.flatMap((s) => (s.where ? [].concat(s.where) : [])))]
  const out = [`# from: ${from}`, `# ${t.from(file)}`, `# ${t.bpHead}`, `# ${t.bpHead2}`]
  out.push('format: front-of-house/v1', `name: ${q(name)}`, `who: ${q(t.who)}`, `about: ${q(t.about(name))}`)
  out.push(`phases: [${way.phases.map((p) => q(p.name)).join(', ')}]`)
  out.push('actors:')
  for (const r of way.roles) out.push(`  - { id: ${did(r.id)}, name: ${q(r.name)}, layer: ${lead.has(r.id) ? 'front' : 'back'} }`)
  if (systems.length) {
    out.push('systems:')
    for (const s of systems) out.push(`  - { id: ${did(s)}, name: ${q(s)} }`)
  }
  out.push('moments:')
  let afterGate = null // the gate just passed: what comes out of it is what the person sees while they wait
  for (const s of way.stages) {
    const phase = way.phases.find((p) => p.id === s.phase)?.name ?? s.phase
    bets.push(`what the customer does at «${s.name}»`)
    out.push(`  - id: ${did(s.id)}`, `    phase: ${q(phase)}`, `    customer: ${q(s.question ? t.customerQ(s.name, s.question) : t.customer(s.name))}   # bet`)
    if (afterGate) out.push('    marks: [wait]')
    const ev = [...(afterGate?.outputs ?? []).map((o) => o.name), ...(s.outputs ?? []).map((o) => o.name)]
    if (ev.length) out.push(`    evidence: [${ev.map(q).join(', ')}]`)
    const [first, ...rest] = s.roles ?? []
    if (first) out.push(`    front: [{ actor: ${did(first)}, does: ${q(s.name)} }]`)
    const backs = rest.filter((r) => !lead.has(r))
    const fronts = rest.filter((r) => lead.has(r))
    if (fronts.length) out.splice(out.length - 1, 1, `    front: [${[first, ...fronts].map((r) => `{ actor: ${did(r)}, does: ${q(s.name)} }`).join(', ')}]`)
    if (backs.length) out.push(`    back: [${backs.map((r) => `{ actor: ${did(r)}, does: ${q(s.name)} }`).join(', ')}]`)
    if (s.where) out.push(`    support: [${[].concat(s.where).map(did).join(', ')}]`)
    out.push(`    way: ${did(id)}#${did(s.id)}`)
    afterGate = gateAfter(way, s.id) ?? null
  }
  return { text: out.join('\n') + '\n', bets }
}

/** A drill on one gate (the first with an on_fail when none is named): the eve of the delivery, the gate says no, and
 * the room chooses — redo, ask the approver what was missing, or go ahead. The gaps are what the way does not say. */
export function drillOf(way, name, from, gateId, lang = 'en') {
  const file = from.split('@')[0]
  const t = T[lang]
  const g = gateId ? way.gates.find((x) => x.id === gateId) : way.gates.find((x) => x.on_fail) ?? way.gates[0]
  if (!g) return { error: gateId ? `no gate «${gateId}» in the way` : 'the way has no gate to drill' }
  const bets = ['the scenes: what happens when the gate says no']
  const a = approverOf(g)
  const back = g.on_fail ?? g.after
  const backStage = way.stages.find((s) => s.id === back)
  const reworker = backStage?.roles?.[0]
  const you = way.stages.find((s) => s.id === g.after)?.roles?.[0] ?? way.roles[0]?.id
  const fail = failures(g)[0]
  const idx = way.stages.findIndex((s) => s.id === g.after)
  const next = way.stages[idx + 1]?.name
  const needs = (g.criteria ?? []).flatMap((c) => (c.kind === 'outputs' ? c.outputs : c.kind === 'stage' ? [c.stage] : c.kind === 'kpis' ? c.kpis : []))
  const outputName = (oid) => way.stages.flatMap((s) => s.outputs ?? []).concat(way.gates.flatMap((x) => x.outputs ?? [])).find((o) => o.id === oid)?.name ?? stageName(way, oid)
  const out = [`# from: ${from}`, `# ${t.from(file)}`, `# ${t.drHead}`]
  out.push('format: dress-rehearsal/v1', `name: ${q(t.drillName(g.name))}`, `about: ${q(t.drillAbout(g.name, name))}`, 'clock: "09:00"', `impact: ${q(t.impact)}`, 'call_minutes: 30')
  out.push('roles:')
  for (const r of way.roles) {
    const can = []
    if (r.id === reworker) can.push(did(`rework-${back}`))
    if (r.id === a) can.push(did(`decide-${g.id}`))
    const bits = [`id: ${did(r.id)}`, `name: ${q(r.name)}`]
    if (r.id === you) bits.push('you: true')
    if (can.length) bits.push(`can: [${can.join(', ')}]`)
    out.push(`  - { ${bits.join(', ')} }`)
  }
  out.push('start: reproved', 'scenes:')
  out.push('  - id: reproved', `    says: ${q(t.reproved(g.name, fail.label ?? fail.id, t.item))}`, '    choices:')
  out.push(`      - { label: ${q(t.back(stageName(way, back)))}, go: redone, minutes: 240, lost: 1, needs: ${did(`rework-${back}`)} }`)
  if (a && a !== you) out.push(`      - { label: ${q(t.ask(roleName(way, a)))}, go: criteria, minutes: 30, calls: ${did(a)} }`)
  else out.push(`      - { label: ${q(t.ask(roleName(way, a ?? you)))}, go: criteria, minutes: 30 }`)
  out.push(`      - { label: ${q(t.push)}, go: worse, minutes: 10, lost: 3 }`)
  out.push(`      - { label: ${q(t.tell)}, go: told, minutes: 15, notifies: true }`)
  out.push('  - id: told', `    says: ${q(t.told)}`, '    choices:')
  out.push(`      - { label: ${q(t.back(stageName(way, back)))}, go: redone, minutes: 240, lost: 1, needs: ${did(`rework-${back}`)} }`)
  out.push(`      - { label: ${q(t.push)}, go: worse, minutes: 10, lost: 3 }`)
  out.push('  - id: criteria', `    says: ${q(t.explains(roleName(way, a ?? you), g.name, needs.length ? needs.map(outputName).join(', ') : t.needsNothing))}`, '    choices:')
  out.push(`      - { label: ${q(t.back(stageName(way, back)))}, go: redone, minutes: 240, lost: 1, needs: ${did(`rework-${back}`)} }`)
  out.push(`      - { label: ${q(t.push)}, go: worse, minutes: 10, lost: 3 }`)
  out.push('  - id: redone', `    says: ${q(t.redone(stageName(way, back), g.name))}`, '    end: resolved')
  out.push('  - id: worse', `    says: ${q(t.worse(g.name, next))}`, '    end: worse')
  const gaps = []
  if (!g.on_fail) gaps.push(t.noWay(g.name))
  if (!(g.criteria ?? []).length) gaps.push(t.noCriteria(g.name))
  if (!a) gaps.push(t.noApprover(g.name))
  if (gaps.length) {
    out.push('gaps:')
    for (const x of gaps) out.push(`  - { says: ${q(x)}, source: ${q(t.source(file))} }`)
  }
  return { text: out.join('\n') + '\n', bets, gate: g.id }
}
