// A solution as an OKF v0.2 bundle (github.com/GoogleCloudPlatform/open-knowledge-format): a concept per piece, with
// what its skill's check says, its trust (machine-confirmed when the check passes, human-reviewed when a person's
// review still holds) and its sources; the simulation as an Attested Computation, with the executor and the attester
// inside the bundle; the recipes copied into references/dna/, so the bundle stands alone. Written by
// `build.mjs <id>.solution.yaml --okf [--out <folder>]`. Nothing here asks a model.
//
// The dates stay put: a concept's generated.at (and its machine verified.at) is the export's moment only when the piece
// changed — the previous bundle's dna.version and actor are compared — so exporting twice with nothing changed writes
// the same bytes, and log.md only grows when something did. DNA_NOW (ISO 8601) fixes the clock, for the checks.
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { copyFileSync, cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, normalize, relative, resolve, sep } from 'node:path'
import { pathToFileURL } from 'node:url'

const DNA_API = 'github.com/ruinosus/dna/v1'
const KINDS = { way: 'WayOfWorking', blueprint: 'ServiceBlueprint', drill: 'IncidentDrill' }
export const CONCEPTS = {
  way: { file: 'process.md', type: 'Way of Working', role: { en: 'the process', pt: 'o processo' } },
  blueprint: { file: 'journey.md', type: 'Service Blueprint', role: { en: 'the journey', pt: 'a jornada' } },
  drill: { file: 'drill.md', type: 'Incident Drill', role: { en: 'when it goes wrong', pt: 'quando dá errado' } },
  agents: { file: 'agents.md', type: 'Agent Review', role: { en: 'the agents', pt: 'os agentes' } },
  lesson: { file: 'lesson.md', type: 'Lesson', role: { en: 'the lesson', pt: 'a explicação' } },
  sim: { file: 'computations/simulation.md', type: 'Attested Computation', role: { en: 'what if', pt: 'e se' } },
}
const T = {
  en: {
    about: { way: 'Who does what, the stages in order, and the gates that decide.', blueprint: 'What the person lives at each step, who makes it happen, and where it hurts.', drill: 'What the team does when it goes wrong, played as a drill.', agents: 'The Copilot Studio agents, compared with each other.', lesson: 'The idea explained by drawing, chapter by chapter.', sim: 'The what-if simulation of the process.' },
    phases: 'Phases and stages', gates: 'Gates', after: 'after', approves: 'approved by', onFail: 'if not', moments: 'Moments', feels: 'feels', actions: 'Actions', owner: 'owner', due: 'due', roles: 'Roles', scenes: (n) => `${n} scenes`, gaps: 'What the runbook does not say', said: 'What the check says', look: 'To look at', broken: 'This piece fails its check: it is a draft until it passes.', params: 'Parameters', scenarios: 'Scenarios', run: (seed, runs) => `The default run (seed ${seed}, ${runs} runs)`, metric: 'Metric', median: 'Median', range: 'p10 to p90', recipe: (f) => `The recipe: [${f}](${f}).`, attest: 'A run of it is attested by the attester: `node ../references/attesters/process-simulation.mjs <receipt.json>`.', lessonOf: (f) => `Drawn by visual-explainer from \`${f}\`.`,
    rootHead: 'The solution', compHead: 'Computations', refHead: 'References', compIndex: 'The simulation as an Attested Computation.', refIndex: 'The DNA recipes, the executor and the attester.', dnaDir: 'The recipes as DNA writes them, the source of each concept.', skillsDir: 'How to run the simulation and get a receipt.', attDir: 'The deterministic attester and the engine it runs.',
    created: (l) => `Exported ${l}.`, updated: (l) => `${l} changed.`, reviewed: (l, by) => `${l} reviewed by ${by}.`, removed: (t) => `«${t}» left the solution.`,
  },
  pt: {
    about: { way: 'Quem faz o quê, as etapas em ordem e os gates que decidem.', blueprint: 'O que a pessoa vive a cada passo, quem faz acontecer e onde dói.', drill: 'O que o time faz quando dá errado, jogado como um ensaio.', agents: 'Os agentes do Copilot Studio, comparados entre si.', lesson: 'A ideia explicada desenhando, capítulo a capítulo.', sim: 'A simulação «e se» do processo.' },
    phases: 'Fases e etapas', gates: 'Gates', after: 'depois de', approves: 'aprovado por', onFail: 'se não', moments: 'Momentos', feels: 'sente', actions: 'Ações', owner: 'dono', due: 'prazo', roles: 'Papéis', scenes: (n) => `${n} cenas`, gaps: 'O que o runbook não diz', said: 'O que o check diz', look: 'A olhar', broken: 'Esta peça não passa no check: é rascunho até passar.', params: 'Parâmetros', scenarios: 'Cenários', run: (seed, runs) => `A execução padrão (semente ${seed}, ${runs} rodadas)`, metric: 'Métrica', median: 'Mediana', range: 'p10 a p90', recipe: (f) => `A receita: [${f}](${f}).`, attest: 'Uma execução dela é atestada pelo attester: `node ../references/attesters/process-simulation.mjs <recibo.json>`.', lessonOf: (f) => `Desenhada pelo visual-explainer a partir de \`${f}\`.`,
    rootHead: 'A solução', compHead: 'Computações', refHead: 'Referências', compIndex: 'A simulação como Attested Computation.', refIndex: 'As receitas do DNA, o executor e o attester.', dnaDir: 'As receitas como o DNA as escreve, a fonte de cada conceito.', skillsDir: 'Como rodar a simulação e obter um recibo.', attDir: 'O attester determinístico e o motor que ele roda.',
    created: (l) => `Exportado: ${l}.`, updated: (l) => `${l} mudou.`, reviewed: (l, by) => `${l} revisado por ${by}.`, removed: (t) => `«${t}» saiu da solução.`,
  },
}

const sha = (text) => createHash('sha256').update(text).digest('hex')
export const versionOf = (text) => sha(text).slice(0, 8)
const q = (s) => JSON.stringify(String(s))
const iso = (d) => d.toISOString().replace(/\.\d{3}Z$/, 'Z')
const posix = (p) => p.split(sep).join('/')

/** Every file under dir (not node_modules), sorted, as [relative path, text]. */
function filesOf(dir) {
  const out = []
  const visit = (d) => {
    for (const name of readdirSync(d).sort()) {
      if (name === 'node_modules' || name.startsWith('.')) continue
      const p = join(d, name)
      if (statSync(p).isDirectory()) visit(p)
      else out.push([posix(relative(dir, p)), readFileSync(p)])
    }
  }
  visit(dir)
  return out
}

/** A skill's version: its SKILL.md's, or (in the npm package, which carries no SKILL.md) the package's. */
export function skillVersion(skills, skill) {
  try {
    return /version: "([^"]+)"/.exec(readFileSync(join(skills, skill, 'SKILL.md'), 'utf8'))[1]
  } catch {
    try {
      return JSON.parse(readFileSync(join(skills, '../package.json'), 'utf8')).version
    } catch {
      return '0.0.0'
    }
  }
}

/** What the previous bundle wrote of a concept: { version, by, at } (our own frontmatter, read back by its lines). */
function previous(path) {
  if (!existsSync(path)) return undefined
  const text = readFileSync(path, 'utf8')
  const g = /^generated: \{ by: ([^,]+), at: ([^ }]+) \}$/m.exec(text)
  const v = /^dna: \{.*\bversion: ([0-9a-f]{8})\b/m.exec(text)
  return g && v ? { by: g[1], at: g[2], version: v[1] } : undefined
}

/** The frontmatter, in a fixed order, values quoted where they are free text. */
function frontmatter(f) {
  const lines = ['---', `type: ${f.type}`, `title: ${q(f.title)}`, `description: ${q(f.description)}`]
  if (f.resource) lines.push(`resource: ${f.resource}`)
  for (const k of ['runtime', 'computation']) if (f[k]) lines.push(`${k}: ${f[k]}`)
  if (f.parameters) {
    lines.push('parameters:')
    for (const p of f.parameters) lines.push(`  - { name: ${p.name}, type: ${p.type}, required: false, min: ${p.min}, max: ${p.max}, default: ${p.default} }`)
  }
  if (f.executor) lines.push('executor:', `  resource: ${f.executor.resource}`, `  receipt: [${f.executor.receipt.join(', ')}]`)
  if (f.attester) lines.push('attester:', `  resource: ${f.attester.resource}`)
  lines.push(`tags: [${f.tags.join(', ')}]`)
  lines.push(`generated: { by: ${f.generated.by}, at: ${f.generated.at} }`)
  if (f.verified?.length) {
    lines.push('verified:')
    for (const v of f.verified) lines.push(`  - { by: ${v.by}, at: ${v.at} }`)
  }
  if (f.status) lines.push(`status: ${f.status}`)
  if (f.stale_after) lines.push(`stale_after: ${f.stale_after}`)
  if (f.sources?.length) {
    lines.push('sources:')
    for (const s of f.sources) lines.push(`  - { id: ${s.id}, resource: ${q(s.resource)}, title: ${q(s.title)} }`)
  }
  if (f.dna) lines.push(`dna: { ${Object.entries(f.dna).map(([k, v]) => `${k}: ${v}`).join(', ')} }`)
  lines.push('---', '')
  return lines.join('\n')
}

const run = (skills, skill, args) => spawnSync(process.execPath, [join(skills, skill, 'scripts/build.mjs'), ...args], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
function factsOf(skills, skill, path, lang) {
  const r = run(skills, skill, [path, '--check', '--json', '--lang', lang])
  try {
    return JSON.parse(r.stdout)
  } catch {
    return undefined
  }
}

/** Distinct source texts as OKF sources (a scope descriptor is a valid resource) and a footnote label for each. */
function sourceList(texts, prefix = 's') {
  const ids = new Map()
  for (const t of texts) if (t && !ids.has(t)) ids.set(t, `${prefix}${ids.size + 1}`)
  return { sources: [...ids].map(([t, id]) => ({ id, resource: t, title: t })), id: (t) => ids.get(t) }
}
const footnotes = (sources) => (sources.length ? ['', ...sources.map((s) => `[^${s.id}]: ${s.title}`)] : [])

function wayBody(j, t) {
  const w = j.way
  const name = (list, id) => list.find((x) => x.id === id)?.name ?? id
  const out = [`## ${t.phases}`, '']
  for (const p of w.phases) {
    out.push(`### ${p.name}`, '')
    for (const s of w.stages.filter((x) => x.phase === p.id)) out.push(`- **${s.name}** (${name(w.lanes, s.lane)})${s.question ? ` — ${s.question}` : ''}`)
    out.push('')
  }
  if (w.gates.length) {
    out.push(`## ${t.gates}`, '')
    for (const g of w.gates) out.push(`- **${g.name}** — ${t.after} «${name(w.stages, g.after)}»${g.approver ? `, ${t.approves} ${name(w.roles, g.approver)}` : ''}${g.on_fail ? `; ${t.onFail}: ${typeof g.on_fail === 'string' ? g.on_fail : JSON.stringify(g.on_fail)}` : ''}`)
    out.push('')
  }
  return { body: out, sources: [] }
}

function blueprintBody(j, t) {
  const b = j.blueprint
  const moments = b.moments ?? []
  const { sources, id } = sourceList(moments.flatMap((m) => (m.pains ?? []).map((p) => p.source)))
  const out = [`## ${t.moments}`, '']
  for (const p of b.phases) {
    out.push(`### ${p.name}`, '')
    for (const m of moments.filter((x) => x.phase === p.id)) {
      out.push(`- **${m.customer}**${m.feels ? ` (${t.feels} ${m.feels}/5)` : ''}`)
      for (const pain of m.pains ?? []) out.push(`  - «${pain.says}»${pain.source ? `[^${id(pain.source)}]` : ''}`)
    }
    out.push('')
  }
  if (b.actions?.length) {
    out.push(`## ${t.actions}`, '')
    for (const a of b.actions) out.push(`- ${a.does}${a.owner ? ` (${t.owner}: ${a.owner}${a.due ? `, ${t.due} ${a.due}` : ''})` : ''}`)
    out.push('')
  }
  return { body: [...out, ...footnotes(sources)], sources }
}

function drillBody(j, t, runbook) {
  const d = j.drill
  const gaps = sourceList((d.gaps ?? []).map((g) => g.source), 'g')
  const sources = [...(runbook ? [{ id: 'runbook', resource: runbook, title: 'Runbook' }] : []), ...gaps.sources]
  const out = [`## ${t.roles}`, '', ...d.roles.map((r) => `- ${r.name}${r.you ? ' (you)' : ''}`), '', `${t.scenes((d.scenes ?? []).length)}${runbook ? `, from the runbook[^runbook]` : ''}.`, '']
  if (d.gaps?.length) {
    out.push(`## ${t.gaps}`, '')
    for (const g of d.gaps) out.push(`- ${g.says}${g.source ? `[^${gaps.id(g.source)}]` : ''}`)
    out.push('')
  }
  return { body: [...out, ...footnotes(sources)], sources }
}

const fmt = (x) => (Math.abs(x) >= 100 ? String(Math.round(x)) : String(Number(x.toPrecision(4))))

/** The bundle, written to `out`: { files: [paths written], log: [lines added] }. */
export async function exportOkf({ sol, folder, checked, out, lang, now = new Date(process.env.DNA_NOW ?? Date.now()), skills, reviewed = {} }) {
  const t = T[lang] ?? T.en
  const at = iso(now)
  const files = {} // relative path → text or Buffer
  const solVersion = skillVersion(skills, 'solution')
  const copies = [] // [from (absolute), to (relative to references/dna)]
  const addCopy = (abs) => {
    const rel = normalize(relative(folder, abs))
    if (rel.startsWith('..') || !existsSync(abs)) return undefined
    copies.push([abs, rel])
    return `references/dna/${posix(rel)}`
  }
  const entries = { created: [], updated: [], reviewed: [], removed: [] }
  const concepts = []
  let wayAt

  // the way first: a lens behind it is stale from the way's moment
  const order = [...checked].sort((a, b) => (a.kind === 'way' ? -1 : b.kind === 'way' ? 1 : 0))
  for (const c of order) {
    const def = CONCEPTS[c.kind]
    const skill = c.skill
    const actor = `dna/${skill}/${skillVersion(skills, skill)}`
    const path = resolve(folder, c.file)
    if (c.state === 'missing') continue
    const isDir = statSync(path).isDirectory()
    const extra = []
    let content = isDir ? filesOf(path).map(([p, b]) => `${p}\n${sha(b)}`).join('\n') : readFileSync(path, 'utf8')
    if (c.kind === 'agents' && sol.profile && existsSync(resolve(folder, sol.profile))) {
      extra.push(resolve(folder, sol.profile))
      content += `\n${readFileSync(resolve(folder, sol.profile), 'utf8')}`
    }
    const facts = ['way', 'blueprint', 'drill'].includes(c.kind) && c.state === 'ok' ? factsOf(skills, skill, path, lang) : undefined
    let runbook
    if (c.kind === 'drill' && facts?.drill?.from) {
      const rb = resolve(dirname(path), facts.drill.from)
      if (existsSync(rb)) {
        extra.push(rb)
        content += `\n${readFileSync(rb, 'utf8')}`
      }
    }
    const version = versionOf(content)
    const resource = addCopy(path)
    for (const e of extra) {
      const r = addCopy(e)
      if (c.kind === 'drill' && r) runbook = r
    }
    const prev = previous(join(out, def.file))
    const changed = !prev || prev.version !== version || prev.by !== actor
    const when = changed ? at : prev.at
    if (c.kind === 'way') wayAt = when
    const label = `[${sol.name} — ${def.role[lang] ?? def.role.en}](/${def.file})`
    if (!prev) entries.created.push(label)
    else if (changed) entries.updated.push(label)

    const ok = c.state === 'ok'
    const verified = ok ? [{ by: actor, at: when }] : []
    const review = reviewed[c.kind]
    if (ok && review && review.version === version) {
      verified.push({ by: review.by, at: review.at })
      if (!prev || !readFileSync(join(out, def.file), 'utf8').includes(`by: ${review.by}, at: ${review.at}`)) entries.reviewed.push([label, review.by])
    }
    let body = []
    let sources = []
    let description = t.about[c.kind]
    let extraFm = {}
    if (c.kind === 'way' && facts) ({ body, sources } = wayBody(facts, t))
    if (c.kind === 'blueprint' && facts) ({ body, sources } = blueprintBody(facts, t))
    if (c.kind === 'drill' && facts) ({ body, sources } = drillBody(facts, t, runbook))
    if ((c.kind === 'blueprint' || c.kind === 'drill') && facts?.[c.kind]?.about) description = facts[c.kind].about
    if (c.kind === 'agents') {
      const dir = path
      sources = readdirSync(dir).filter((d) => existsSync(join(dir, d, 'agent.mcs.yml'))).sort().map((d) => ({ id: d, resource: `${resource}/${d}/agent.mcs.yml`, title: d }))
      body = [`## ${t.said}`, '', ...c.said.filter((l) => /^✓/.test(l)).map((l) => `- ${l.replace(/^✓\s*/, '')}`), '']
    }
    if (c.kind === 'lesson') body = [t.lessonOf(c.file), '']
    if (c.kind === 'sim') {
      const { SIMLANG, ATTEST } = await import(pathToFileURL(join(skills, 'process-simulation/scripts/engine.mjs')).href)
      const src = readFileSync(path, 'utf8')
      const parsed = SIMLANG.parse(src)
      const comment = src.split('\n').map((l) => /^#\s*(.+)$/.exec(l)?.[1]?.trim()).find((l) => l && !/^(from|bet):|--lens/.test(l))
      if (comment) description = comment
      if (parsed.ok) {
        const m = parsed.model
        const engine = `dna/process-simulation/${skillVersion(skills, 'process-simulation')}`
        const done = ATTEST.run(src, { engine })
        extraFm = {
          runtime: 'dna/process-simulation',
          computation: `../${resource}`,
          parameters: m.knobOrder.map((k) => {
            const n = m.knobs[k]
            const type = n.pct ? 'percent' : [n.min, n.max, n.init].every(Number.isInteger) ? 'integer' : 'number'
            return { name: k, type, min: n.min, max: n.max, default: n.init }
          }),
          executor: { resource: '../references/skills/process-simulation.md', receipt: ['recipe_sha256', 'engine', 'seed', 'runs', 'set', 'rows'] },
          attester: { resource: '../references/attesters/process-simulation.mjs' },
          engine,
        }
        body = [
          t.recipe(`../${resource}`), '',
          `## ${t.params}`, '', ...m.knobOrder.map((k) => `- \`${k}\`: ${m.knobs[k].pct ? `${Math.round(m.knobs[k].min * 100)}%..${Math.round(m.knobs[k].max * 100)}%, ${Math.round(m.knobs[k].init * 100)}%` : `${m.knobs[k].min}..${m.knobs[k].max}, ${m.knobs[k].init}`}`), '',
          ...(m.scenarios.length ? [`## ${t.scenarios}`, '', ...m.scenarios.map((s) => `- **${s.name}**: ${Object.entries(s.sets).map(([k, v]) => `${k} = ${m.knobs[k]?.pct ? `${Math.round(v * 100)}%` : v}`).join(', ')}`), ''] : []),
          `## ${t.run(done.receipt.seed, done.receipt.runs)}`, '', `| ${t.metric} | ${t.median} | ${t.range} |`, '|---|---|---|',
          ...done.receipt.rows.map((r) => `| ${r.metric} | ${fmt(r.median)} | ${fmt(r.p10)} – ${fmt(r.p90)} |`), '', t.attest, '',
        ]
      }
    }
    const looks = [...c.looks, ...c.said.filter((l) => /^!/.test(l)).map((l) => l.replace(/^!\s*/, ''))]
    if (looks.length) body.push(`## ${t.look}`, '', ...looks.map((l) => `- ${l}`), '')
    if (!ok) body.unshift(t.broken, '', ...c.said.filter((l) => /^✗|^\s/.test(l)).slice(0, 8).map((l) => `    ${l.trim()}`), '')
    const fm = {
      type: def.type,
      title: `${sol.name} — ${def.role[lang] ?? def.role.en}`,
      description,
      resource: c.kind === 'sim' ? undefined : resource,
      ...extraFm,
      tags: ['dna', skill],
      generated: { by: actor, at: when },
      verified,
      status: ok ? undefined : 'draft',
      stale_after: c.stale && wayAt ? wayAt : undefined,
      sources,
      dna: { apiVersion: DNA_API, ...(KINDS[c.kind] ? { kind: KINDS[c.kind] } : {}), version, ...(extraFm.engine ? { engine: extraFm.engine } : {}) },
    }
    delete fm.engine
    files[def.file] = frontmatter(fm) + `# ${fm.title}\n\n${description}\n\n` + body.join('\n').replace(/\n{3,}/g, '\n\n').trimEnd() + '\n'
    concepts.push({ kind: c.kind, file: def.file, title: fm.title, description })
  }

  // references/: the recipes, and, with a simulation, its executor and attester
  const hasSim = concepts.some((c) => c.kind === 'sim')
  const references = ['# References', '', `* [DNA recipes](dna/) - ${t.dnaDir}`]
  if (hasSim) {
    const execText = [
      '---', 'type: Skill', `title: ${q('Run a DNA simulation and get a receipt')}`,
      `description: ${q('Executor of the Attested Computations with runtime dna/process-simulation: runs the recipe with only the declared parameters and writes the receipt the attester checks.')}`,
      'tags: [skill, executor, dna, process-simulation]', `generated: { by: dna/solution/${solVersion}, at: ${previous(join(out, 'references/skills/process-simulation.md'))?.at ?? at} }`, `dna: { version: ${versionOf(solVersion)} }`, '---', '',
      '# Run a DNA simulation and get a receipt', '',
      'The computation is a `.sim` recipe; its `parameters` are the recipe\'s controls (`knob`). Supply values only for them, within their range — never edit the recipe.', '',
      '```', 'npx @ruinosus/dna process-simulation <recipe.sim> --run [--seeds N] [--set name=value …] --receipt receipt.json', '```', '',
      'The receipt (`dna/process-simulation/receipt-v1`) carries `recipe_sha256` (the recipe\'s SHA-256), `engine`, `seed`, `runs`, `set` (the parameters given) and `rows` (median and p10 to p90 of each metric). Show the numbers of the receipt, and give it to the attester:', '',
      '```', 'node references/attesters/process-simulation.mjs receipt.json [--json]', '```', '',
      'Exit 0 attested; 3 refused, with the reason (the recipe swapped, a parameter that is not one or out of its range, another engine, a number that does not come out again); 2 a receipt that is not JSON.', '',
    ].join('\n')
    files['references/skills/process-simulation.md'] = execText
    files['references/skills/index.md'] = `# Skills\n\n* [Run a DNA simulation and get a receipt](process-simulation.md) - ${t.skillsDir}\n`
    files['references/attesters/process-simulation.mjs'] = readFileSync(join(skills, 'process-simulation/scripts/okf-attester.mjs'), 'utf8')
    files['references/attesters/engine.mjs'] = readFileSync(join(skills, 'process-simulation/scripts/engine.mjs'), 'utf8')
    files['references/attesters/index.md'] = `# Attesters\n\n* [process-simulation.mjs](process-simulation.mjs) - ${t.attDir}\n* [engine.mjs](engine.mjs) - The simulation engine (DNA's process-simulation).\n`
    files['computations/index.md'] = `# ${t.compHead}\n\n${concepts.filter((c) => c.kind === 'sim').map((c) => `* [${c.title}](simulation.md) - ${c.description}`).join('\n')}\n`
    references.push(`* [Skills](skills/index.md) - ${t.skillsDir}`, `* [Attesters](attesters/index.md) - ${t.attDir}`)
  }
  files['references/index.md'] = references.join('\n') + '\n'
  const root = concepts.filter((c) => c.kind !== 'sim')
  files['index.md'] = ['---', 'okf_version: "0.2"', '---', '', `# ${t.rootHead}`, '', ...root.map((c) => `* [${c.title}](${c.file}) - ${c.description}`), '',
    ...(hasSim ? [`# ${t.compHead}`, '', `* [${t.compHead}](computations/index.md) - ${t.compIndex}`, ''] : []),
    `# ${t.refHead}`, '', `* [${t.refHead}](references/index.md) - ${t.refIndex}`, ''].join('\n')

  // a piece that left the solution: its concept goes, and the log says so
  for (const [kind, def] of Object.entries(CONCEPTS)) {
    if (concepts.some((c) => c.kind === kind)) continue
    const p = join(out, def.file)
    if (existsSync(p)) {
      const title = /^title: (".*")$/m.exec(readFileSync(p, 'utf8'))?.[1]
      entries.removed.push(title ? JSON.parse(title) : def.file)
      rmSync(p)
    }
  }

  // log.md: today's entries on top, only when something changed
  const day = at.slice(0, 10)
  const lines = [
    ...entries.created.map((l) => `* **Creation**: ${t.created(l)}`),
    ...entries.updated.map((l) => `* **Update**: ${t.updated(l)}`),
    ...entries.reviewed.map(([l, by]) => `* **Review**: ${t.reviewed(l, by)}`),
    ...entries.removed.map((x) => `* **Deprecation**: ${t.removed(x)}`),
  ]
  const logPath = join(out, 'log.md')
  let log = existsSync(logPath) ? readFileSync(logPath, 'utf8') : '# Directory Update Log\n'
  if (lines.length) {
    const head = `## ${day}\n`
    if (log.includes(`\n${head}`)) log = log.replace(`\n${head}`, `\n${head}${lines.join('\n')}\n`)
    else log = log.replace(/^# Directory Update Log\n\n?/, `# Directory Update Log\n\n${head}${lines.join('\n')}\n\n`)
    log = log.replace(/\n{3,}/g, '\n\n')
  }
  files['log.md'] = log.endsWith('\n') ? log : log + '\n'

  // write: references/ is ours, made again; a concept only when its text changed
  rmSync(join(out, 'references'), { recursive: true, force: true })
  for (const [from, to] of copies) {
    const dest = join(out, 'references/dna', to)
    mkdirSync(dirname(dest), { recursive: true })
    if (statSync(from).isDirectory()) cpSync(from, dest, { recursive: true, filter: (s) => !/(^|[\\/])(node_modules|\.[^\\/]+)$/.test(s) })
    else copyFileSync(from, dest)
  }
  // a markdown file among the copies (a runbook, a NOTICE) is a concept of its own in OKF (§6.3, §11): it gets a
  // Reference frontmatter saying where it came from — unless it already has one with a type
  for (const [from, to] of copies) {
    const mds = statSync(from).isDirectory() ? filesOf(from).map(([p]) => [join(from, p), join(to, p)]).filter(([p]) => p.toLowerCase().endsWith('.md')) : to.toLowerCase().endsWith('.md') ? [[from, to]] : []
    for (const [src, rel] of mds) {
      if (/(^|[\\/])(index|log)\.md$/i.test(rel)) continue
      const text = readFileSync(src, 'utf8')
      if (/^---\r?\n[\s\S]*?^type:\s*\S/m.test(text.split(/\r?\n---\r?\n/)[0] + '\n')) continue
      const head = ['---', 'type: Reference', `title: ${q(posix(rel))}`, `description: ${q(`A copy of ${posix(rel)}, as the solution's pieces read it.`)}`, 'tags: [dna, reference]', '---', ''].join('\n')
      writeFileSync(join(out, 'references/dna', rel), head + text)
    }
  }
  if (!hasSim) rmSync(join(out, 'computations'), { recursive: true, force: true })
  const written = []
  for (const [rel, text] of Object.entries(files)) {
    const dest = join(out, rel)
    mkdirSync(dirname(dest), { recursive: true })
    if (existsSync(dest) && readFileSync(dest, 'utf8') === text) continue
    writeFileSync(dest, text)
    written.push(rel)
  }
  return { concepts: concepts.length, written, log: lines, out }
}
