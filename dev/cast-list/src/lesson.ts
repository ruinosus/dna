// The comparison explained by drawing it — a chalk-talk lesson on one paper, in five chapters: the cast (the
// orchestrator on top, an arrow to each specialist it calls, every agent a robot with its name), what repeats (the
// patterns), who is off (a red × and why, under the agent), what is missing (the rules not met) and what to decide
// (the patterns in the open, what only one has). Many agents go in rows, so the paper stays one the engine takes.
import { arrow, GREEN, GREY, RED, text, wrap, type Obj, type XY } from '@lib/drawing/mermaidKit'
import type { Result } from './compare'
import { isBehaviour, labelOf, lacks, type Lang } from './labels'
import { roleWord } from './words'
import { groupPatterns, type Look } from './review'

const COL = 150
const LEFT = 40
const PER_ROW = 24 // 24 columns of 150: under the engine's 4000
const ROW = 250 // a robot, its name and why it is off
const ITEM = 17 // the size of a list's words: read from the back of the room
const SECTION_LINE = 23
const MAX_ITEMS = 5 // the five that matter most; the rest is on the map
const MAX_LINES = 4
// settings and the parts of a connector say less than what an agent does: drawn last
const QUIET = /^(auth|model|setting|topics|connref|operation):/

const WORDS = {
  en: {
    chapters: ['The cast', 'What repeats', 'Who is off', 'What is missing', 'What to decide'],
    cast: (o: number, n: number) => (o ? `${o} ${o === 1 ? 'orchestrator calls' : 'orchestrators call'} ${n} ${n === 1 ? 'specialist' : 'specialists'}.` : `${n} ${n === 1 ? 'specialist' : 'specialists'}, with no orchestrator.`),
    repeats: (p: number, pl: number, sp: number) => (p ? `${p} patterns: ${pl} of the platform, ${sp} of the specialists.` : 'Nothing repeats enough to be a pattern yet.'),
    off: (ids: string[]) => (ids.length ? `Off a pattern: ${ids.join(', ')}.` : 'Nobody is off a pattern.'),
    missing: (n: number) => (n ? `${n} ${n === 1 ? 'rule is' : 'rules are'} not met.` : 'Every rule is met.'),
    decide: (n: number) => (n ? `${n} ${n === 1 ? 'thing' : 'things'} to decide.` : 'Nothing left to decide.'),
    pattern: (l: string) => `A pattern? «${l}»`, platform: 'platform', specialist: 'specialists', more: (n: number) => `and ${n} more on the map`, none: 'nothing',
  },
  pt: {
    chapters: ['O elenco', 'O que se repete', 'Quem está fora', 'O que falta', 'O que decidir'],
    cast: (o: number, n: number) => (o ? `${o} ${o === 1 ? 'orquestrador chama' : 'orquestradores chamam'} ${n} ${n === 1 ? 'especialista' : 'especialistas'}.` : `${n} ${n === 1 ? 'especialista' : 'especialistas'}, sem orquestrador.`),
    repeats: (p: number, pl: number, sp: number) => (p ? `${p} padrões: ${pl} da plataforma, ${sp} dos especialistas.` : 'Nada se repete o bastante para ser padrão ainda.'),
    off: (ids: string[]) => (ids.length ? `Fora do padrão: ${ids.join(', ')}.` : 'Ninguém está fora do padrão.'),
    missing: (n: number) => (n ? `${n} ${n === 1 ? 'regra não é cumprida' : 'regras não são cumpridas'}.` : 'Todas as regras são cumpridas.'),
    decide: (n: number) => (n ? `${n} ${n === 1 ? 'coisa' : 'coisas'} para decidir.` : 'Nada em aberto para decidir.'),
    pattern: (l: string) => `Padrão? «${l}»`, platform: 'plataforma', specialist: 'especialistas', more: (n: number) => `e mais ${n} no mapa`, none: 'nada',
  },
}

export function lessonOf(r: Result, looks: Look[], lang: Lang = 'en'): Obj {
  const w = WORDS[lang]
  const orchestrators = r.agents.filter((a) => a.role === 'orchestrator').sort((a, b) => a.id.localeCompare(b.id))
  const specialists = r.agents.filter((a) => a.role === 'specialist').sort((a, b) => a.id.localeCompare(b.id))
  const rows = Math.max(1, Math.ceil(specialists.length / PER_ROW))
  const perRow = Math.max(1, Math.ceil(specialists.length / rows))
  const width = Math.max(1000, LEFT * 2 + Math.max(perRow, orchestrators.length) * COL)
  const centred = (i: number, n: number) => width / 2 + (i - (n - 1) / 2) * COL
  const steps: Obj[] = [{ ...text([LEFT, 52], r.name ?? w.chapters[0], 30), chapter: w.chapters[0], say: `${r.name ? `${r.name}: ` : ''}${w.cast(orchestrators.length, specialists.length)}` }]

  // 1. the cast
  const name = (id: string, at: XY, color?: string) => wrap(id, 15, COL - 12).slice(0, 2).forEach((t, k) => steps.push(text([at[0], at[1] + k * 18], t, 15, 'middle', color)))
  const top = 170
  const spot = new Map<string, XY>()
  orchestrators.forEach((o, i) => {
    const x = centred(i, orchestrators.length)
    spot.set(o.id, [x, top])
    steps.push({ type: 'prop', name: 'robot', at: [x, top], size: 70 })
    name(o.id, [x, top + 24], GREY)
  })
  specialists.forEach((s, i) => {
    const row = Math.floor(i / perRow)
    const inRow = Math.min(perRow, specialists.length - row * perRow)
    const at: XY = [centred(i % perRow, inRow), 340 + row * ROW]
    spot.set(s.id, at)
    steps.push({ type: 'prop', name: 'robot', at, size: 64 })
    name(s.id, [at[0], at[1] + 24])
  })
  // an arrow from an orchestrator to each specialist it calls (to the first row; a lower row is called the same way)
  for (const o of orchestrators) {
    const from = spot.get(o.id)!
    for (const s of specialists.filter((x) => x.schemaName && `calls:${x.schemaName}` in o.facts)) {
      const to = spot.get(s.id)!
      if (to[1] === 340) steps.push(arrow([from[0], from[1] + 44], [to[0], to[1] - 76], { color: GREY }))
    }
  }

  // 2. what repeats, 4. what is missing, 5. what to decide: three columns under the cast
  const sectionTop = 340 + (rows - 1) * ROW + 160
  const third = (width - LEFT * 2) / 3
  let lowest = sectionTop
  const section = (i: number, chapter: string, say: string, items: string[], color?: string) => {
    const x = LEFT + i * third
    steps.push({ ...text([x, sectionTop], chapter, 22, 'start', color), chapter, say })
    let y = sectionTop + 34
    const shown = items.slice(0, MAX_ITEMS)
    if (items.length > MAX_ITEMS) shown.push(w.more(items.length - MAX_ITEMS))
    if (!shown.length) shown.push(w.none)
    for (const item of shown) {
      // a long item ends with «…» rather than losing words quietly
      const lines = wrap(item, ITEM, third - 30)
      const shownLines = lines.length > MAX_LINES ? [...lines.slice(0, MAX_LINES - 1), `${lines[MAX_LINES - 1]}…`] : lines
      shownLines.forEach((t, k) => steps.push(text([x + (k ? 14 : 0), y + k * SECTION_LINE], `${k ? '' : '· '}${t}`, ITEM, 'start', GREY)))
      y += shownLines.length * SECTION_LINE + 6
    }
    lowest = Math.max(lowest, y)
  }
  const rank = (k: string) => (isBehaviour(k) ? 0 : QUIET.test(k) ? 2 : 1)
  const repeats = r.patterns.filter((p) => !p.partOf).sort((a, b) => rank(a.key) - rank(b.key) || (a.scope === b.scope ? 0 : a.scope === 'platform' ? -1 : 1) || b.share - a.share || a.key.localeCompare(b.key))
  const scopeWord = (s: string) => (s === 'platform' ? w.platform : w.specialist)
  section(0, w.chapters[1], w.repeats(r.patterns.length, r.patterns.filter((p) => p.scope === 'platform').length, r.patterns.filter((p) => p.scope !== 'platform').length),
    repeats.map((p) => `${labelOf(p.key, lang, r.names)} · ${scopeWord(p.scope)}${p.share < 1 ? ` · ${Math.round(p.share * 100)}%` : ''}`), GREEN)

  // 3. who is off: a red × by the robot, and why under its name
  const offIds = [...new Set(r.offPattern.map((o) => o.agent))].sort()
  offIds.forEach((id, i) => {
    const at = spot.get(id)!
    const reasons = r.offPattern.filter((o) => o.agent === id).flatMap((o) => wrap(lacks(o.key, lang, 1, r.names), 13, COL - 10)).slice(0, 4)
    steps.push({ ...text([at[0] + 34, at[1] - 50], '×', 30, 'middle', RED), ...(i === 0 ? { chapter: w.chapters[2], say: w.off(offIds) } : {}) })
    reasons.forEach((t, k) => steps.push(text([at[0], at[1] + 66 + k * 16], t, 13, 'middle', RED)))
  })
  if (!offIds.length) steps.push({ ...text([width - LEFT, 92], w.off([]), 16, 'end', GREY), chapter: w.chapters[2], say: w.off([]) })

  // a rule in a few words (the names are on the map); a rule that only repeats a pattern someone is off is said there
  const gaps = r.gaps.flatMap((g) => {
    const n = g.agents.filter((a) => !r.offPattern.some((o) => o.agent === a && o.key === g.rule.has)).length
    return n ? [lang === 'pt' ? `«${g.rule.says}»: ${n} ${roleWord(g.rule.role, lang, n)} não ${n === 1 ? 'cumpre' : 'cumprem'}` : `«${g.rule.says}»: ${n} ${roleWord(g.rule.role, lang, n)} ${n === 1 ? 'does' : 'do'} not meet it`] : []
  })
  const unknownFiles = r.unknown.length
  if (unknownFiles) gaps.push(lang === 'pt' ? `${unknownFiles} ${unknownFiles === 1 ? 'arquivo não entendido' : 'arquivos não entendidos'}` : `${unknownFiles} ${unknownFiles === 1 ? 'file' : 'files'} not understood`)
  section(1, w.chapters[3], w.missing(looks.filter((l) => l.key === 'gap').length), gaps, RED)
  const { look } = groupPatterns(r)
  // what people and the YAML disagree on first, then the patterns in the open, then what only one has
  const open = [...looks.filter((l) => l.key === 'conflict').map((l) => l[lang]), ...look.filter((p) => !p.decision).map((p) => w.pattern(labelOf(p.key, lang, r.names))), ...looks.filter((l) => l.key === 'solo').map((l) => l[lang])]
  section(2, w.chapters[4], w.decide(open.length), open)

  const id = (r.name ?? 'cast').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'cast'
  return { id, title: r.name ?? w.chapters[0], width, height: Math.min(4000, lowest + 40), background: 'plain', locale: lang === 'pt' ? 'pt-BR' : 'en-US', steps }
}

