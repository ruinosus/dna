// How fast a skill delivers, from an eval run kept with --keep-temp and --json: for each run, the seconds until the
// first page (the first build that wrote an .html), the files read before the source was written, the rounds of fixes
// (builds after the first page) and the quality grader. Per case, the mean of its runs. Part of the skills kit
// (chalk-talk/kit).
//
//   node eval-metrics.mjs <run.json> [<another run.json> …]
import { readFileSync } from 'node:fs'

const isBuild = (u) => u.name === 'Bash' && /build\.mjs/.test(u.input?.command ?? '')
const isRecipe = (u) => (u.name === 'Write' || u.name === 'Edit') && /\.(chalk|mmd|json|md|ya?ml)$/.test(u.input?.file_path ?? '')
const text = (c) => (typeof c === 'string' ? c : (c ?? []).map((x) => x.text ?? '').join(''))

function metrics(tracePath, startedAt) {
  let lines
  try {
    lines = readFileSync(tracePath, 'utf8').trim().split('\n').map((l) => JSON.parse(l))
  } catch {
    return undefined
  }
  const uses = new Map()
  let reads = 0
  let wrote = false
  let first
  let builds = 0
  let drawnAt
  for (const e of lines) {
    for (const c of e.message?.content ?? []) {
      if (c.type === 'tool_use') {
        uses.set(c.id, c)
        // what the skill had to read before writing: files opened with Read, or with cat/sed/head/grep in a shell
        if (!wrote && c.name === 'Read') reads++
        if (!wrote && c.name === 'Bash') reads += (c.input?.command?.match(/(?:references|SKILL)[\w./-]*\.(?:md|json|chalk|mmd)/g) ?? []).length
        if (isRecipe(c)) wrote = true
        if (isBuild(c)) builds++
      }
      if (c.type === 'tool_result' && !drawnAt) {
        const u = uses.get(c.tool_use_id)
        if (u && isBuild(u) && /\.html\b/.test(text(c.content)) && !/^✗ (?!review)/m.test(text(c.content))) {
          drawnAt = Date.parse(e.timestamp)
          first = builds
        }
      }
    }
  }
  return {
    firstDrawing: drawnAt ? (drawnAt - Date.parse(startedAt)) / 1000 : undefined,
    reads,
    fixes: first ? builds - first : undefined,
  }
}

const mean = (xs) => {
  const v = xs.filter((x) => typeof x === 'number')
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : undefined
}
const show = (x, digits = 0) => (x === undefined ? '—' : x.toFixed(digits))

for (const file of process.argv.slice(2)) {
  const run = JSON.parse(readFileSync(file, 'utf8'))
  console.log(`\n${file} — ${run.claudeVersion ?? ''}, ${run.durationSeconds ?? '?'} s, US$ ${(run.costUsd ?? 0).toFixed(2)}`)
  console.log('case                     | 1st drawing s | reads before writing | fixes | quality | runs drawn')
  for (const c of run.cases) {
    const runs = (c.arms?.with ?? []).map((r) => ({ ...r, m: metrics(r.tracePath, r.startedAt) }))
    const ms = runs.map((r) => r.m).filter(Boolean)
    const drawn = ms.filter((m) => m.firstDrawing !== undefined).length
    // the score is the quality grader (or, for a case that should ask, every grader)
    const quality = runs.map((r) => { const q = r.graders?.find((g) => g.name === 'quality'); return q ? Number(q.passed) : r.score })
    console.log(`${c.name.padEnd(24)} | ${show(mean(ms.map((m) => m.firstDrawing))).padStart(13)} | ${show(mean(ms.map((m) => m.reads)), 1).padStart(20)} | ${show(mean(ms.map((m) => m.fixes)), 1).padStart(5)} | ${show(mean(quality), 2).padStart(5)} | ${drawn}/${runs.length}`)
  }
}
