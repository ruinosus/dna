// The RH of the cast on one page that opens with no internet: the staff board on top; the org chart and the post of each
// role and type on the side; one résumé at a time — the title, the manager, the team, the tools, the conduct, the goal,
// the performance from the telemetry and the development plan. A person in the org chart opens their résumé.
import type { Lang } from '../labels'
import type { Playbill, Resume, Situation } from '../playbill'

interface Data { id: string; lang: Lang; playbill: Playbill; map?: string }
const UI = {
  en: {
    title: 'The cast’s HR', sub: 'The same cast, as people: staff board, org chart, post, résumé and development plan. Everything comes from the files, the telemetry and the team’s spreadsheets.',
    privacy: 'This file holds the client’s data: keep it in the client’s environment.',
    staff: { cast: 'on the staff', hiring: 'being hired', noOwner: 'with no owner', neverPublished: 'never published', pdi: 'with a development plan', ok: 'in good standing' } as Record<string, string>,
    tag: { hiring: 'being hired', noOwner: 'no owner', neverPublished: 'never published', pdi: 'plan', ok: 'in good standing' } as Record<Situation, string>,
    missing: { inventory: 'the admin center’s inventory (owner, environment, published)', team: 'the team’s spreadsheet (team, goal)', telemetry: 'the export of Application Insights (performance)' } as Record<string, string>,
    more: 'More with', org: 'Org chart', client: 'Customer', clientSub: 'who is served', manager: 'manager', ghost: 'called, not in the folder', noType: 'no type',
    post: 'The post', postNote: 'The post is the accepted pattern of the role and type, and the profile’s rules. A newcomer is «hired» when they meet it.', proposal: 'proposal — no decision yet',
    manager_: 'Manager', team: 'Team', owner: 'Owner', created: 'Hired', published: 'Last published', schema: 'Badge', env: 'Unit', nobody: 'nobody calls it',
    summary: 'Summary', tools: 'Tools and access', conduct: 'Languages and conduct', goal: 'Goal', noGoal: 'no goal declared', perf: (d: number) => `Performance · ${d} days`, starts: 'topic starts', errors: 'errors logged', notFired: 'did not fire', measured: 'goal measured', noLine: 'no line in the telemetry', noPerf: 'The performance comes with the export of Application Insights (--telemetry).',
    pdi: 'Development plan', nothing: 'Nothing to develop.', sources: 'Sources', seal: { ok: 'IN GOOD STANDING', pdi: 'PLAN' }, orchestrator: 'Orchestrator', specialist: 'Specialist', map: '← Map', foot: 'cast-list · no model: what is here is what the files and tables say.',
  },
  pt: {
    title: 'RH do elenco', sub: 'O mesmo elenco, visto como pessoas: quadro de pessoal, organograma, vaga, currículo e plano de desenvolvimento. Tudo sai dos arquivos, da telemetria e das planilhas do time.',
    privacy: 'Este arquivo tem dados do cliente: deixe-o no ambiente dele.',
    staff: { cast: 'no quadro', hiring: 'em admissão', noOwner: 'sem responsável', neverPublished: 'nunca publicado', pdi: 'em PDI', ok: 'em dia' } as Record<string, string>,
    tag: { hiring: 'em admissão', noOwner: 'sem responsável', neverPublished: 'nunca publicado', pdi: 'PDI', ok: 'em dia' } as Record<Situation, string>,
    missing: { inventory: 'o inventário do admin center (responsável, ambiente, publicação)', team: 'a planilha do time (equipe, meta)', telemetry: 'a exportação do Application Insights (desempenho)' } as Record<string, string>,
    more: 'Mais com', org: 'Organograma', client: 'Cliente', clientSub: 'quem é atendido', manager: 'gestor', ghost: 'chamado, fora da pasta', noType: 'sem tipo',
    post: 'A vaga', postNote: 'A vaga é o padrão aceito do papel e do tipo, mais as regras do perfil. Quem chega é «contratado» quando cumpre a vaga.', proposal: 'proposta — sem decisão ainda',
    manager_: 'Gestor', team: 'Equipe', owner: 'Responsável', created: 'Admissão', published: 'Última publicação', schema: 'Matrícula', env: 'Lotação', nobody: 'ninguém chama',
    summary: 'Resumo', tools: 'Ferramentas e acessos', conduct: 'Idiomas e conduta', goal: 'Meta', noGoal: 'sem meta declarada', perf: (d: number) => `Desempenho · ${d} dias`, starts: 'inícios de tópico', errors: 'erros registrados', notFired: 'não disparou', measured: 'meta medida', noLine: 'nenhuma linha na telemetria', noPerf: 'O desempenho aparece com a exportação do Application Insights (--telemetry).',
    pdi: 'Plano de desenvolvimento', nothing: 'Nada a desenvolver.', sources: 'Fontes', seal: { ok: 'EM DIA', pdi: 'PDI' }, orchestrator: 'Orquestrador', specialist: 'Especialista', map: '← Mapa', foot: 'cast-list · sem modelo: o que está aqui é o que os arquivos e as planilhas dizem.',
  },
}

const data: Data = JSON.parse(document.getElementById('cast')!.textContent!)
const { playbill: pb, lang } = data
const u = UI[lang]
document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en'
document.title = `${u.title} · ${pb.name ?? data.id}`
const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
const app = document.getElementById('app')!
const situationOf = (id: string) => [...pb.org.orchestrators, ...pb.org.types.flatMap((t) => t.people)].find((p) => p.id === id)?.situation ?? []
// the résumé shown first: the one the address names (the stage's «See the résumé»), else the first with a plan
const named = decodeURIComponent(location.hash.slice(1))
let picked = (pb.resumes.find((r) => r.id === named) ?? pb.resumes.find((r) => r.seal === 'pdi' && r.role === 'specialist') ?? pb.resumes[0])?.id
let post = pb.posts[0]?.scope

const COUNT: Record<string, string> = { cast: '', hiring: 'warn', noOwner: 'bad', neverPublished: 'warn', pdi: 'bad', ok: 'good' }
function staff() {
  const cards = pb.staff.map((s) => `<div class="pb-count ${COUNT[s.key]}"><b>${s.people.length}</b><span>${esc(u.staff[s.key])}${s.key !== 'cast' && s.people.length ? ` — ${esc(s.people.map((p) => p.name).join(', '))}` : ''}</span></div>`).join('')
  const missing = pb.missing.length ? `<p class="pb-missing">${esc(u.more)}: ${pb.missing.map((m) => esc(u.missing[m])).join(' · ')}</p>` : ''
  return `<section class="pb-staff" aria-label="${esc(u.title)}">${cards}</section>${missing}`
}

const tags = (s: Situation[]) => s.filter((x) => x !== 'ok' || s.length === 1).map((x) => `<span class="pb-tag ${x}">${esc(u.tag[x])}</span>`).join(' ')
const node = (id: string, name: string, cls = '') => `<button class="pb-node ${cls}" data-who="${esc(id)}" aria-pressed="${id === picked}"><span>${esc(name)}</span>${tags(situationOf(id))}</button>`
function org() {
  const heads = pb.org.orchestrators.map((p) => `<button class="pb-node manager" data-who="${esc(p.id)}" aria-pressed="${p.id === picked}"><span>${esc(p.name)}<br><small>${esc(u.manager)}</small></span>${tags(p.situation)}</button>`).join('')
  const types = pb.org.types.map((t) => `<p class="pb-type">${esc(t.name || u.noType)}</p>${t.people.map((p) => node(p.id, p.name)).join('')}`).join('')
  const ghosts = pb.org.ghosts.map((g) => `<div class="pb-node ghost"><span>${esc(g.name)}</span><span class="pb-tag hiring">${esc(u.ghost)}</span></div>`).join('')
  return `<section class="cl-card"><h2>${esc(u.org)}</h2><div class="pb-org"><div class="pb-node ghost" style="justify-content:center"><span>${esc(u.client)} · <small>${esc(u.clientSub)}</small></span></div>${heads}${types}${ghosts}</div></section>`
}

function posts() {
  const p = pb.posts.find((x) => x.scope === post) ?? pb.posts[0]
  if (!p) return ''
  const pick = pb.posts.map((x) => `<button data-post="${esc(x.scope)}" aria-pressed="${x.scope === p.scope}">${esc(x.name[lang])}</button>`).join('')
  const reqs = p.requirements.map((r) => `<li class="${r.proposal ? 'proposal' : ''}">${esc(r[lang])}${r.proposal ? ` <span class="pb-src">(${esc(u.proposal)})</span>` : ''}</li>`).join('')
  return `<section class="cl-card"><h2>${esc(u.post)}</h2><div class="pb-posts">${pick}</div><ul class="pb-req">${reqs}</ul><p class="pb-note">${esc(u.postNote)}</p></section>`
}

const said = (s?: { value: string; source: string }) => (s ? `${esc(s.value)} <span class="pb-src">(${esc(s.source)})</span>` : '—')
const fact = (label: string, value: string) => `<div><dt>${esc(label)}</dt><dd>${value}</dd></div>`
const section = (title: string, body: string) => `<div class="pb-section"><h3>${esc(title)}</h3>${body}</div>`
// what the client wrote (the instructions, a block's own words) is quoted as written; the rest are cast-list's words
const chips = (xs: { en: string; pt: string }[], quote = false) => (xs.length ? `<div class="pb-chips">${xs.map((x) => `<span class="pb-chip${quote ? ' pb-quote' : ''}">${esc(x[lang])}</span>`).join('')}</div>` : '<p class="pb-empty">—</p>')
function resume(r: Resume) {
  const role = r.role === 'orchestrator' ? u.orchestrator : u.specialist
  const sub = [r.title ?? '', `${role}${r.types.length ? ` · ${r.types.join(' · ')}` : ''}`].filter(Boolean)
  const facts = [
    fact(u.manager_, r.manager ? esc(r.manager) : r.role === 'orchestrator' ? '—' : esc(u.nobody)),
    fact(u.team, said(r.team)), fact(u.owner, said(r.owner)), fact(u.created, said(r.created)), fact(u.published, said(r.published)),
    fact(u.schema, esc(r.schemaName ?? '—')), fact(u.env, said(r.environment)),
  ].join('')
  const p = r.performance
  const perf = p
    ? p.silent
      ? `<p class="pb-empty">${esc(u.noLine)}</p>`
      : `<div class="pb-perf"><div><b>${p.starts}</b><span>${esc(u.starts)}</span></div><div class="${p.notFired.length ? 'bad' : ''}"><b>${p.errors}</b><span>${esc(u.errors)}${p.notFired.length ? ` — ${esc(p.notFired.join(', '))} ${esc(u.notFired)}` : ''}</span></div><div><b>—</b><span>${esc(u.measured)}</span></div></div>`
    : `<p class="pb-empty">${esc(u.noPerf)}</p>`
  const plan = r.pdi.length ? `<ol class="pb-pdi">${r.pdi.map((x) => `<li class="${x.group}"><span>${esc(x[lang])}<small>${esc(x.why[lang])}</small></span></li>`).join('')}</ol>` : `<p class="pb-empty">${esc(u.nothing)}</p>`
  return `<article class="cl-card pb-resume" aria-live="polite">
    <div class="pb-head"><div><h2>${esc(r.name)}</h2>${r.title ? `<p class="pb-quote">${esc(r.title)}</p>` : ''}<p>${esc(sub[sub.length - 1])}</p></div><span class="pb-seal ${r.seal}">${esc(u.seal[r.seal])}</span></div>
    <dl class="pb-facts">${facts}</dl>
    ${r.summary.length ? section(u.summary, `<ul class="pb-quote">${r.summary.map((s) => `<li>${esc(s)}</li>`).join('')}</ul>`) : ''}
    ${section(u.tools, chips(r.tools))}
    ${section(u.conduct, chips(r.conduct, true))}
    ${section(u.goal, r.goal ? `<p>${said(r.goal)}</p>` : `<p class="pb-empty">${esc(u.noGoal)}</p>`)}
    ${section(p ? u.perf(p.days) : u.perf(0).replace(/ · .*/, ''), perf)}
    ${section(u.pdi, plan)}
    <p class="pb-note">${esc(u.sources)}: ${esc(r.sources.join(', '))}</p>
  </article>`
}

function render() {
  const r = pb.resumes.find((x) => x.id === picked) ?? pb.resumes[0]
  app.innerHTML = `<div class="cl-wrap">
    <header>${data.map ? `<p class="cl-sub"><a href="${esc(data.map)}">${esc(u.map)}</a></p>` : ''}<h1 class="cl-title">${esc(u.title)} · ${esc(pb.name ?? data.id)}</h1><p class="cl-sub">${esc(u.sub)}</p><p class="cl-private">${esc(u.privacy)}</p></header>
    ${staff()}
    <div class="pb-body"><div class="pb-side">${org()}${posts()}</div>${r ? resume(r) : ''}</div>
    <p class="cl-foot">${esc(u.foot)}</p>
  </div>`
}

app.addEventListener('click', (e) => {
  const t = (e.target as HTMLElement).closest('button')
  if (!t) return
  if (t.dataset.who) picked = t.dataset.who
  else if (t.dataset.post) post = t.dataset.post
  else return
  render()
  if (t.dataset.who) app.querySelector('.pb-resume')?.scrollIntoView({ block: 'nearest' })
})

render()
