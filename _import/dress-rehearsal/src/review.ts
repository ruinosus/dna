// What does not hold in a drill, read from the file (and the runbook, when there is one): a scene nobody reaches, scenes
// from where no end can be reached, a choice that needs what no role can do, nobody ever told about the incident,
// «escalate» to nobody, a choice that cites a part the runbook does not have. Questions, not errors: the game still
// plays. Each says where and why, in English and Portuguese.
import { reachable, type Drill } from './drill'

export interface Look {
  key: 'unreachable' | 'noWayOut' | 'nobodyCan' | 'nobodyTold' | 'escalateNowhere' | 'notInRunbook'
  scene?: string
  en: string
  pt: string
}

const ESCALATE = /\b(escal\w*)\b/i

export function reviewDrill(drill: Drill, runbook?: string): Look[] {
  const out: Look[] = []
  const ends = new Set(drill.scenes.filter((s) => s.end).map((s) => s.id))
  const reach = new Set(reachable(drill, drill.start))
  for (const s of drill.scenes) {
    if (!reach.has(s.id)) out.push({ key: 'unreachable', scene: s.id, en: `No choice leads to the scene «${s.id}»`, pt: `Nenhuma escolha leva à cena «${s.id}»` })
    else if (!s.end && !reachable(drill, s.id).some((id) => ends.has(id)))
      out.push({ key: 'noWayOut', scene: s.id, en: `From «${s.id}» no end can be reached: the players would go round forever`, pt: `De «${s.id}» não se chega a nenhum fim: os jogadores ficariam dando voltas` })
  }
  const can = new Set(drill.roles.flatMap((r) => r.can ?? []))
  const choices = drill.scenes.flatMap((s) => (s.choices ?? []).map((c) => ({ s, c })))
  for (const { s, c } of choices) {
    if (c.needs && !can.has(c.needs)) out.push({ key: 'nobodyCan', scene: s.id, en: `«${c.label}» needs «${c.needs}» and no role can do it: who has that access?`, pt: `«${c.label}» precisa de «${c.needs}» e nenhum papel pode: quem tem esse acesso?` })
    if (ESCALATE.test(c.label) && !c.calls) out.push({ key: 'escalateNowhere', scene: s.id, en: `«${c.label}»: escalate to whom?`, pt: `«${c.label}»: escalar para quem?` })
    if (runbook && c.runbook && !runbook.includes(c.runbook)) out.push({ key: 'notInRunbook', scene: s.id, en: `«${c.label}» cites «${c.runbook}», which is not in the runbook`, pt: `«${c.label}» cita «${c.runbook}», que não está no runbook` })
  }
  if (!choices.some(({ c }) => c.notifies)) out.push({ key: 'nobodyTold', en: 'No choice tells the people affected: who tells the customers, and when?', pt: 'Nenhuma escolha avisa quem é afetado: quem avisa os clientes, e quando?' })
  return out
}
