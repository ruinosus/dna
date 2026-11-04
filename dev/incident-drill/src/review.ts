// What does not hold in a drill, read from the file (and the runbook, when there is one): a scene nobody reaches, scenes
// from where no end can be reached, a choice that needs what no role can do, nobody ever told about the incident,
// «escalate» to nobody, a choice that cites a part the runbook does not have (or a list of steps without the step). Questions, not errors: the game still
// plays. Each says where and why, in English and Portuguese.
import { reachable, type Drill } from './drill'
import { findPassage } from './runbook'

export interface Look {
  key: 'unreachable' | 'noWayOut' | 'nobodyCan' | 'nobodyTold' | 'escalateNowhere' | 'notInRunbook' | 'whichStep'
  scene?: string
  en: string
  pt: string
}

// «Escalate» is always handing the incident to someone; in Portuguese «escalar» is that too («escalar para o time de
// pagamentos», «escalar o incidente») but also scaling up («escalar a instância»). So the Portuguese verb counts only
// when it goes to someone (para/pra/ao/à/com…), takes the incident as its object, or stands alone.
const ESCALATE_EN = /\bescalat\w*/i
const ESCALATE_PT = /\bescalon\w*|\bescal\w*\s+(?:(?:o|a|os|as)\s+)?(?:para|pra|pro|ao|aos|à|às|com)(?=\s|$)|\bescal\w*\s+(?:o|a)\s+(?:incidente|problema|chamado|caso|ocorrência)\b|\bescal\w*\s*[.!?]?$/i
const escalates = (label: string) => ESCALATE_EN.test(label) || ESCALATE_PT.test(label.trim())

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
    if (escalates(c.label) && !c.calls) out.push({ key: 'escalateNowhere', scene: s.id, en: `«${c.label}»: escalate to whom?`, pt: `«${c.label}»: escalar para quem?` })
    const found = runbook && c.runbook ? findPassage(runbook, c.runbook) : undefined
    if (runbook && c.runbook && !found) out.push({ key: 'notInRunbook', scene: s.id, en: `«${c.label}» cites «${c.runbook}», which is not in the runbook`, pt: `«${c.label}» cita «${c.runbook}», que não está no runbook` })
    if (found?.steps) out.push({ key: 'whichStep', scene: s.id, en: `«${c.label}» cites «${c.runbook}», a list of ${found.steps} steps: which one? (e.g. «${c.runbook} ${found.steps}»)`, pt: `«${c.label}» cita «${c.runbook}», uma lista de ${found.steps} passos: qual deles? (por exemplo «${c.runbook} ${found.steps}»)` })
  }
  if (!choices.some(({ c }) => c.notifies)) out.push({ key: 'nobodyTold', en: 'No choice tells the people affected: who tells the customers, and when?', pt: 'Nenhuma escolha avisa quem é afetado: quem avisa os clientes, e quando?' })
  return out
}
