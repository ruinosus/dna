// What changed between two texts, word by word (the longest common subsequence): the words both have, the ones only
// the first has (del) and the ones only the second has (add), runs of the same kind joined.

export interface Piece { op: 'same' | 'add' | 'del'; text: string }

const MAX = 2000 // past this many words a side, the table would be too big: the whole text changed

export function wordDiff(a: string, b: string): Piece[] {
  const x = a.split(/\s+/).filter(Boolean)
  const y = b.split(/\s+/).filter(Boolean)
  if (x.length > MAX || y.length > MAX) return [{ op: 'del', text: x.join(' ') }, { op: 'add', text: y.join(' ') }]
  // lcs[i][j]: the common words of x[i..] and y[j..]
  const lcs = Array.from({ length: x.length + 1 }, () => new Uint16Array(y.length + 1))
  for (let i = x.length - 1; i >= 0; i--) for (let j = y.length - 1; j >= 0; j--) lcs[i][j] = x[i] === y[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
  const out: Piece[] = []
  const push = (op: Piece['op'], word: string) => {
    const last = out[out.length - 1]
    if (last?.op === op) last.text += ` ${word}`
    else out.push({ op, text: word })
  }
  let i = 0
  let j = 0
  while (i < x.length || j < y.length) {
    if (i < x.length && j < y.length && x[i] === y[j]) push('same', (i++, j++, x[i - 1]))
    else if (j < y.length && (i === x.length || lcs[i][j + 1] >= lcs[i + 1][j])) push('add', y[j++])
    else push('del', x[i++])
  }
  // a word swapped for another reads «del, then add»
  for (let k = 0; k + 1 < out.length; k++) if (out[k].op === 'add' && out[k + 1].op === 'del') [out[k], out[k + 1]] = [out[k + 1], out[k]]
  return out
}
