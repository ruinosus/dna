// The passage of the runbook a choice cites (`runbook:`), shown in the game beside the choice and checked by the review.
// A mark is a heading («## §2 Houve deploy?»: the heading and its first paragraph), any line holding it, or — when the
// steps are a numbered list under a heading — the heading and the step's number («Passos 4»: the 4th step).

const STEP = /^\s*(\d+)[.)]\s+(.+)$/

export interface Passage {
  text: string
  /** The cited heading's body is a numbered list and the mark names no step: the game would show step 1. */
  steps?: number
}

export function findPassage(runbook: string, ref: string): Passage | undefined {
  const lines = runbook.split('\n')
  const at = lines.findIndex((l) => l.includes(ref))
  if (at >= 0) {
    const own = lines[at].replace(/^#+\s*/, '').replace(ref, '').trim()
    if (!/^#/.test(lines[at])) return { text: own }
    const body = sectionOf(lines, at)
    const next = body.find((l) => l.trim()) ?? ''
    const steps = body.filter((l) => STEP.test(l)).length
    return { text: [own, next.trim()].filter(Boolean).join(' — ').slice(0, 300), ...(steps > 1 && STEP.test(next) ? { steps } : {}) }
  }
  const m = ref.match(/^(.*\S)\s+(\d+)$/)
  if (!m) return undefined
  const head = lines.findIndex((l) => /^#/.test(l) && l.includes(m[1]))
  if (head < 0) return undefined
  const step = sectionOf(lines, head).map((l) => l.match(STEP)).find((s) => s && s[1] === m[2])
  return step ? { text: step[2].trim().slice(0, 300) } : undefined
}

/** The lines under a heading, up to the next heading. */
function sectionOf(lines: string[], head: number): string[] {
  const end = lines.findIndex((l, k) => k > head && /^#/.test(l))
  return lines.slice(head + 1, end < 0 ? undefined : end)
}
