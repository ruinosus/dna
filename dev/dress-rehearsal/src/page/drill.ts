// The drill played in a page that opens with no internet: the clock, the scene (with its drawing), what just came in,
// the choices (1–9 on the keyboard); who is in the room (and calling someone in), the impact, what the runbook says
// for these choices. At the end, the debrief: the numbers, the timeline, what the runbook did not say, play again, and
// the debrief and the improvements to download. No score: the clock and what was left behind are the score.
import { readRecipe, stillLesson } from 'chalk-talk/embed'
import type { Drill } from '../drill'
import { call, canDo, choose, clockAt, debrief, startPlay, whoCan, type Lang, type Play } from '../play'
import type { Look } from '../review'

interface Data {
  id: string
  lang: Lang
  drill: Drill
  looks: Look[]
  /** The runbook's text for each mark a choice cites («§2» → the paragraph). */
  excerpts: Record<string, string>
}

const WORDS = {
  en: {
    scene: (n: number) => `Scene ${n}`, live: '● live', over: 'over', justIn: 'Just came in', room: 'Who is in the room', inSince: (t: string) => `in · ${t}`,
    callIn: (m: number) => `Call (+${m} min)`, impact: 'Impact', runbook: 'The runbook says', needs: (n: string, who: string) => `Needs «${n}» — call ${who}`, nobody: 'nobody can', minutes: (m: number) => `+${m} min`,
    debrief: 'Debrief', resolvedIn: 'To resolve', toldIn: 'To tell the people affected', lost: 'Impact', calls: 'People called', notHappened: 'did not happen', happened: 'What happened',
    gaps: 'What the runbook did not say', none: 'Nothing: the runbook covered this path.', again: 'Play again', md: '⬇ debrief.md', csv: '⬇ improvements.csv', resolved: 'Resolved', worse: 'It got worse',
  },
  pt: {
    scene: (n: number) => `Cena ${n}`, live: '● ao vivo', over: 'encerrado', justIn: 'Acabou de chegar', room: 'Quem está na sala', inSince: (t: string) => `na sala · ${t}`,
    callIn: (m: number) => `Chamar (+${m} min)`, impact: 'Impacto', runbook: 'O runbook diz', needs: (n: string, who: string) => `Precisa de «${n}» — chame ${who}`, nobody: 'ninguém pode', minutes: (m: number) => `+${m} min`,
    debrief: 'Debrief', resolvedIn: 'Até resolver', toldIn: 'Até avisar os afetados', lost: 'Impacto', calls: 'Pessoas chamadas', notHappened: 'não aconteceu', happened: 'O que aconteceu',
    gaps: 'O que o runbook não dizia', none: 'Nada: o runbook cobriu este caminho.', again: 'Jogar de novo', md: '⬇ debrief.md', csv: '⬇ melhorias.csv', resolved: 'Resolvido', worse: 'Piorou',
  },
}

const data: Data = JSON.parse(document.getElementById('drill')!.textContent!)
const { drill, lang, looks } = data
const w = WORDS[lang]
const app = document.getElementById('app')!
document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en'
document.title = drill.name
const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
const roleName = (id: string) => drill.roles.find((r) => r.id === id)?.name ?? id
// the impact bar's full width: everything every choice can lose
const scale = Math.max(1, drill.scenes.flatMap((s) => s.choices ?? []).reduce((n, c) => n + (c.lost ?? 0), 0) / 2)

let play: Play = startPlay(drill, lang)
let then: string | undefined
let seen = 1
const joined: Record<string, number> = {}

function render() {
  if (play.ended) return renderDebrief()
  const scene = drill.scenes.find((s) => s.id === play.scene)!
  const choices = scene.choices ?? []
  const callMinutes = drill.call_minutes ?? 3
  const refs = [...new Set(choices.map((c) => c.runbook).filter((r): r is string => !!r && !!data.excerpts[r]))]
  app.innerHTML = `<div class="dr-wrap">
    <header class="dr-head"><h1>${esc(drill.name)}</h1>${drill.about ? `<p>${esc(drill.about)}</p>` : ''}</header>
    <div class="dr-body">
      <section class="dr-card" aria-live="polite">
        <div class="dr-top"><span class="dr-clock">${clockAt(drill, play.minute)}</span><span class="dr-count">${w.scene(seen)}</span><span class="dr-live">${w.live}</span></div>
        ${then ? `<p class="dr-then">${esc(then)}</p>` : ''}
        <div class="dr-scene">${scene.draw ? '<div class="dr-draw" id="draw"></div>' : ''}<p class="dr-says">${esc(scene.says)}</p></div>
        ${(scene.injects ?? []).map((i) => `<div class="dr-inject"><b>${w.justIn}${i.at ? ` · ${esc(i.at)}` : ''}</b>${esc(i.says)}</div>`).join('')}
        <div class="dr-choices">${choices.map((c, k) => {
          const ok = canDo(drill, play, c)
          const who = c.needs ? whoCan(drill, c.needs).map(roleName).join(' / ') || w.nobody : ''
          const meta = [c.minutes ? w.minutes(c.minutes) : '', c.runbook ? `runbook ${c.runbook}` : ''].filter(Boolean).join(' · ')
          return `<button class="dr-choice${ok ? '' : ' blocked'}" data-choice="${k}"><span class="dr-key">${k + 1}</span><b>${esc(c.label)}</b>${meta ? `<span>${esc(meta)}</span>` : ''}${ok ? '' : `<span class="dr-need">${esc(w.needs(c.needs!, who))}</span>`}</button>`
        }).join('')}</div>
      </section>
      <aside class="dr-card">
        <span class="dr-k">${w.room}</span>
        <div class="dr-room">${drill.roles.map((r) => `<div><span>${esc(r.name)}</span>${play.room.includes(r.id) ? `<span class="dr-in">${w.inSince(clockAt(drill, joined[r.id] ?? 0))}</span>` : `<button class="dr-call" data-call="${esc(r.id)}">${w.callIn(callMinutes)}</button>`}</div>`).join('')}</div>
        <span class="dr-k">${w.impact}</span>
        <div class="dr-bar"><i style="width:${Math.min(100, (play.lost / scale) * 100).toFixed(1)}%"></i></div>
        <span class="dr-small">${play.lost} ${esc(drill.impact ?? '')}</span>
        ${refs.length ? `<span class="dr-k">${w.runbook}</span>${refs.map((r) => `<div class="dr-runbook"><b>${esc(r)}</b> ${esc(data.excerpts[r])}</div>`).join('')}` : ''}
      </aside>
    </div>
  </div>`
  if (scene.draw) {
    const el = document.getElementById('draw')!
    try {
      void stillLesson(el, readRecipe(scene.draw))
    } catch {
      el.remove()
    }
  }
}

function renderDebrief() {
  const d = debrief(drill, play, looks, lang)
  const n = (m?: number) => (m === undefined ? `<strong>—</strong>${w.notHappened}` : `<strong>${m} min</strong>`)
  app.innerHTML = `<div class="dr-wrap">
    <header class="dr-head"><h1>${w.debrief}: ${esc(drill.name)}</h1><p>${play.ended === 'resolved' ? w.resolved : w.worse} · ${clockAt(drill, play.minute)}</p></header>
    <section class="dr-card">
      <div class="dr-nums"><div><span class="dr-k">${w.resolvedIn}</span>${n(d.numbers.resolved)}</div><div><span class="dr-k">${w.toldIn}</span>${n(d.numbers.told)}</div>
        <div><span class="dr-k">${w.lost}</span><strong>${d.numbers.lost}</strong>${esc(drill.impact ?? '')}</div><div><span class="dr-k">${w.calls}</span><strong>${d.numbers.calls}</strong></div></div>
    </section>
    <div class="dr-body">
      <section class="dr-card"><span class="dr-k">${w.happened}</span><div class="dr-tl">${d.timeline.map((t) => `<div><time>${t.at}</time><span class="dr-dot ${t.kind}"></span><span>${esc(t.text)}</span></div>`).join('')}</div></section>
      <section class="dr-card"><span class="dr-k">${w.gaps}</span>${d.gaps.length ? `<ul class="dr-gaps">${d.gaps.map((g) => `<li>${esc(g.says)} <em>(${esc(g.source)})</em></li>`).join('')}</ul>` : `<p>${w.none}</p>`}
        <div class="dr-actions"><button class="dr-btn primary" data-again>${w.again}</button><button class="dr-btn" data-get="md">${w.md}</button><button class="dr-btn" data-get="csv">${w.csv}</button></div></section>
    </div>
  </div>`
}

function save(text: string, file: string, type: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([text], { type }))
  a.download = file
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

function pick(k: number) {
  const scene = drill.scenes.find((s) => s.id === play.scene)!
  const c = (scene.choices ?? [])[k]
  if (!c) return
  const before = play
  play = choose(drill, play, k, lang)
  if (play.scene !== before.scene) {
    seen++
    then = c.then
    if (c.calls && !before.room.includes(c.calls)) joined[c.calls] = play.minute
  }
  render()
  ;(app.querySelector('.dr-choice') as HTMLElement | null)?.focus()
}

app.addEventListener('click', (e) => {
  const t = (e.target as HTMLElement).closest('button')
  if (!t) return
  const d = t.dataset
  if (d.choice) return pick(Number(d.choice))
  if (d.call) {
    play = call(drill, play, d.call, lang)
    joined[d.call] = play.minute
    return render()
  }
  if (d.again !== undefined) {
    play = startPlay(drill, lang)
    then = undefined
    seen = 1
    for (const k of Object.keys(joined)) delete joined[k]
    return render()
  }
  if (d.get) {
    const r = debrief(drill, play, looks, lang)
    if (d.get === 'md') save(r.markdown, `${data.id}.debrief.md`, 'text/markdown')
    else save(r.csv, `${data.id}.${lang === 'pt' ? 'melhorias' : 'improvements'}.csv`, 'text/csv')
  }
})
document.addEventListener('keydown', (e) => {
  if (play.ended || e.metaKey || e.ctrlKey || e.altKey) return
  const k = Number(e.key)
  if (k >= 1 && k <= 9) pick(k - 1)
})

render()
