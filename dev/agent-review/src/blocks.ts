// The blocks of text agents share. Each text (the instructions, the descriptions for the model) is cut into blocks —
// a paragraph, a list, a heading with its list — of 8 words or more, normalised (lower case, no accents or
// punctuation, numbers as #n, URLs as #url) and compared by their 5-word shingles: the same block when their Jaccard
// is 0.85 or more; a variation when at least half of the smaller one's shingles are in the other (containment: a copy
// that lost one of four lines is still a variation, where Jaccard alone would call it another block); else another. Blocks of two agents or more make a family; its text is
// the form most of them share, its id survives small edits (kept in the review file), and an official block from the
// profile gives the family its id and name. The same meaning in other words is another block: text, not meaning.
import type { AgentFacts, Facts, Source, Text } from './extract'
import { wordDiff, type Piece } from './diff'

export const SAME = 0.85
export const VARIANT = 0.5
const MIN_WORDS = 8
const SHINGLE = 5

export interface Block { agent?: string; file: string; line: number; text: string; words: string[]; shingles: Set<string> }
export interface BlockFamily {
  id: string
  /** The first eight words of the family's text, for a title. */
  label: string
  /** The form most share (or the official text). */
  text: string
  /** The official block's name, when the profile gives one. */
  official?: string
  holders: Record<string, Source>
  variants: Record<string, { source: Source; similarity: number; text: string; diff: Piece[] }>
}
export interface Official { id: string; name: string; text: string }

export function normalize(text: string): string[] {
  return text
    .normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/https?:\/\/\S+|www\.\S+/g, ' #url ')
    .replace(/\d+([.,]\d+)?/g, ' #n ')
    .replace(/[^a-z#\s]+/g, ' ')
    .split(/\s+/).filter(Boolean)
}

const shinglesOf = (words: string[]) => {
  if (words.length <= SHINGLE) return new Set([words.join(' ')])
  const out = new Set<string>()
  for (let i = 0; i + SHINGLE <= words.length; i++) out.add(words.slice(i, i + SHINGLE).join(' '))
  return out
}
const common = (a: Set<string>, b: Set<string>) => {
  let n = 0
  for (const s of a) if (b.has(s)) n++
  return n
}
/** Jaccard: the shingles both have, of all they have — near 1 only for nearly the same text. */
const similarity = (a: Set<string>, b: Set<string>) => {
  const n = common(a, b)
  return n / (a.size + b.size - n || 1)
}
/** Containment: the shingles both have, of the smaller one's — a shortened copy still scores high. */
const containment = (a: Set<string>, b: Set<string>) => common(a, b) / (Math.min(a.size, b.size) || 1)
/** How alike two texts are, 0 to 1. */
export const jaccard = (a: string, b: string) => similarity(shinglesOf(normalize(a)), shinglesOf(normalize(b)))

const blockOf = (text: string, file: string, line: number, agent?: string): Block => {
  const words = normalize(text)
  return { agent, file, line, text, words, shingles: shinglesOf(words) }
}

/** A text cut into blocks (blank lines part them), each with the line it starts on; under 8 words is not a block. */
export function splitBlocks(t: Pick<Text, 'file' | 'line' | 'text'> & { source?: Text['source'] }, agent?: string): Block[] {
  const out: Block[] = []
  let start = -1
  const lines = t.text.split('\n')
  const flush = (end: number) => {
    if (start < 0) return
    const text = lines.slice(start, end).join('\n').trim()
    const b = blockOf(text, t.file, t.line + start, agent)
    if (b.words.length >= MIN_WORDS) out.push(b)
    start = -1
  }
  lines.forEach((l, i) => {
    if (!l.trim()) flush(i)
    else if (start < 0) start = i
  })
  flush(lines.length)
  return out
}

const idOf = (words: string[], taken: Set<string>) => {
  const base = words.filter((w) => !w.startsWith('#')).slice(0, 5).join('-') || 'block'
  let id = base
  for (let n = 2; taken.has(id); n++) id = `${base}-${n}`
  taken.add(id)
  return id
}
const labelOf = (text: string) => {
  const w = text.split(/\s+/).filter(Boolean)
  return w.slice(0, 8).join(' ') + (w.length > 8 ? '…' : '')
}

/**
 * The families of blocks the agents share, and each agent's facts: `text:block:<id>` when it has the block,
 * `text:block:<id>~variant` when it has a variation. `known` are the blocks kept in the review file (their ids stay);
 * `official` the profile's (they are families even when nobody has them).
 */
export function blocksOf(agents: AgentFacts[], known: { id: string; text: string }[], official: Official[]): { families: BlockFamily[]; facts: Record<string, Facts> } {
  const blocks = agents.flatMap((a) => a.texts.flatMap((t) => splitBlocks(t, a.id)))
  // clusters, in a fixed order: each block joins the first cluster whose first block is alike enough
  const clusters: Block[][] = []
  for (const b of blocks) {
    const c = clusters.find((x) => containment(x[0].shingles, b.shingles) >= VARIANT)
    if (c) c.push(b)
    else clusters.push([b])
  }
  const officials = official.map((o) => ({ ...o, block: blockOf(o.text, 'profile', 0) }))
  const stored = known.map((k) => ({ ...k, block: blockOf(k.text, 'cast', 0) }))
  const taken = new Set([...official.map((o) => o.id), ...known.map((k) => k.id)])
  const families: BlockFamily[] = []
  const used = new Set<string>()
  for (const c of clusters) {
    const off = officials.find((o) => !used.has(o.id) && containment(o.block.shingles, c[0].shingles) >= VARIANT)
    if (new Set(c.map((b) => b.agent)).size < 2 && !off) continue
    // the form most share: the block alike (SAME) to the most others; ties go to the first
    const score = (b: Block) => c.filter((x) => similarity(x.shingles, b.shingles) >= SAME).length
    const rep = off?.block ?? c.reduce((best, b) => (score(b) > score(best) ? b : best), c[0])
    const keep = !off ? stored.find((k) => !used.has(k.id) && containment(k.block.shingles, rep.shingles) >= VARIANT) : undefined
    const id = off?.id ?? keep?.id ?? idOf(rep.words, taken)
    used.add(id)
    const f: BlockFamily = { id, label: labelOf(rep.text), text: rep.text, ...(off ? { official: off.name } : {}), holders: {}, variants: {} }
    for (const b of c) {
      const agent = b.agent!
      const s = similarity(rep.shingles, b.shingles) >= SAME ? 1 : containment(rep.shingles, b.shingles)
      if (s === 1) {
        f.holders[agent] ??= { file: b.file, line: b.line }
        delete f.variants[agent]
      } else if (!f.holders[agent] && (!f.variants[agent] || s > f.variants[agent].similarity))
        f.variants[agent] = { source: { file: b.file, line: b.line }, similarity: s, text: b.text, diff: wordDiff(rep.text, b.text) }
    }
    families.push(f)
  }
  // an official block nobody has is still a family: everybody of its scope is off it
  for (const o of officials.filter((x) => !used.has(x.id))) families.push({ id: o.id, label: labelOf(o.text), text: o.text, official: o.name, holders: {}, variants: {} })
  const facts: Record<string, Facts> = Object.fromEntries(agents.map((a) => [a.id, {}]))
  for (const f of families) {
    for (const [agent, s] of Object.entries(f.holders)) facts[agent][`text:block:${f.id}`] = [s]
    for (const [agent, v] of Object.entries(f.variants)) facts[agent][`text:block:${f.id}~variant`] = [v.source]
  }
  return { families, facts }
}
