// The facilitator's script, in Markdown: everything in the drill with the paths spelled out (spoilers), what to watch
// for, and what the check found — to run the drill projected for a team.
import { reachable, type Drill } from './drill'
import type { Lang } from './play'
import type { Look } from './review'

export function facilitator(drill: Drill, looks: Look[], lang: Lang = 'en'): string {
  const pt = lang === 'pt'
  const role = (id: string) => drill.roles.find((r) => r.id === id)?.name ?? id
  // the scenes in the order the players meet them, then any nobody reaches
  const order = [...reachable(drill, drill.start), ...drill.scenes.map((s) => s.id)].filter((id, i, xs) => xs.indexOf(id) === i)
  const out = [
    `# ${pt ? 'Roteiro do facilitador' : 'Facilitator’s script'}: ${drill.name}`,
    '',
    ...(drill.about ? [drill.about, ''] : []),
    ...(drill.from ? [`${pt ? 'Feito a partir de' : 'Made from'} \`${drill.from}\`.`, ''] : []),
    `${pt ? 'Começa às' : 'Starts at'} **${drill.clock}**${drill.impact ? ` · ${pt ? 'impacto contado em' : 'impact counted in'} ${drill.impact}` : ''}.`,
    '',
    `## ${pt ? 'Papéis' : 'Roles'}`,
    '',
    ...drill.roles.map((r) => `- **${r.name}**${r.you ? (pt ? ' — quem joga' : ' — the player') : r.in ? (pt ? ' — já na sala' : ' — in the room') : ''}${r.can?.length ? ` · ${pt ? 'pode' : 'can'}: ${r.can.join(', ')}` : ''}`),
    '',
    `## ${pt ? 'Cenas' : 'Scenes'}`,
    '',
  ]
  for (const id of order) {
    const s = drill.scenes.find((x) => x.id === id)!
    out.push(`### ${s.id}${s.end ? ` — ${s.end === 'resolved' ? (pt ? 'fim: resolvido' : 'end: resolved') : pt ? 'fim: piorou' : 'end: worse'}` : ''}`, '', s.says, '')
    for (const i of s.injects ?? []) out.push(`> ${i.at ? `**${i.at}** ` : ''}${i.says}`, '')
    for (const c of s.choices ?? []) {
      const bits = [c.minutes ? `+${c.minutes} min` : '', c.lost ? `+${c.lost} ${drill.impact ?? ''}`.trim() : '', c.calls ? `${pt ? 'chama' : 'calls'} ${role(c.calls)}` : '', c.needs ? `${pt ? 'precisa de' : 'needs'} ${c.needs}` : '', c.notifies ? (pt ? 'avisa os afetados' : 'tells the people affected') : '', c.runbook ? `runbook ${c.runbook}` : ''].filter(Boolean)
      out.push(`- **${c.label}** → ${c.go}${bits.length ? ` _(${bits.join(' · ')})_` : ''}${c.then ? `  \n  ${c.then}` : ''}`)
    }
    if ((s.choices ?? []).length) out.push('')
  }
  const gaps = [...(drill.gaps ?? []).map((g) => `${g.says}${g.source ? ` _(${g.source})_` : ''}`), ...looks.map((l) => l[lang])]
  out.push(`## ${pt ? 'O que o runbook não diz' : 'What the runbook does not say'}`, '', ...(gaps.length ? gaps.map((g) => `- ${g}`) : [pt ? '- Nada encontrado.' : '- Nothing found.']), '')
  return out.join('\n')
}
