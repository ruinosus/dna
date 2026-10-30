// What does not hold in a blueprint, read from the file: the worst moment with no action, a moment with nobody behind
// it, a wait or a failure where the customer is told nothing, a promise with no owner or no time, a system in almost
// every moment, a pain with no source, an action with no owner. Questions, not errors; each says where, in English and
// Portuguese.
import type { Blueprint } from './blueprint'

export interface Look {
  key: 'worstNoAction' | 'nobodyBehind' | 'silentWait' | 'promiseNoOwner' | 'promiseNoTime' | 'systemEverywhere' | 'painNoSource' | 'actionNoOwner'
  moment?: string
  en: string
  pt: string
}

export function reviewBlueprint(b: Blueprint): Look[] {
  const out: Look[] = []
  const acted = new Set(b.actions.map((a) => a.moment))
  const felt = b.moments.filter((m) => m.feels !== undefined).map((m) => m.feels!)
  const worst = felt.length ? Math.min(...felt) : undefined
  for (const m of b.moments) {
    const q = `«${m.customer}»`
    if (worst !== undefined && worst <= 2 && m.feels === worst && !acted.has(m.id))
      out.push({ key: 'worstNoAction', moment: m.id, en: `${q} is the worst moment for the customer and no action is tied to it`, pt: `${q} é o pior momento para o cliente e nenhuma ação está ligada a ele` })
    if (!(m.front ?? []).length && !(m.back ?? []).length && !(m.support ?? []).length)
      out.push({ key: 'nobodyBehind', moment: m.id, en: `${q}: the customer does it and nobody behind answers — not on stage, backstage or in a system`, pt: `${q}: o cliente faz e ninguém responde — nem no palco, nem nos bastidores, nem num sistema` })
    if ((m.marks ?? []).length && !(m.evidence ?? []).length)
      out.push({ key: 'silentWait', moment: m.id, en: `${q} is a ${m.marks!.includes('fail') ? 'failure point' : 'wait'} and the customer gets nothing — not even an email`, pt: `${q} é ${m.marks!.includes('fail') ? 'um ponto de falha' : 'uma espera'} e o cliente não recebe nada — nem um e-mail` })
    if (m.promise && !m.promise.owner) out.push({ key: 'promiseNoOwner', moment: m.id, en: `«${m.promise.says}»: who answers for this promise?`, pt: `«${m.promise.says}»: quem responde por essa promessa?` })
    if (m.promise && !m.promise.within) out.push({ key: 'promiseNoTime', moment: m.id, en: `«${m.promise.says}»: within how long?`, pt: `«${m.promise.says}»: em quanto tempo?` })
    for (const p of m.pains ?? []) if (!p.source) out.push({ key: 'painNoSource', moment: m.id, en: `The pain «${p.says}» has no source (an interview, a ticket, a survey)`, pt: `A dor «${p.says}» não tem fonte (uma entrevista, um ticket, uma pesquisa)` })
  }
  // a system in more than half of the moments (and at least three) holds the whole journey
  for (const s of b.systems) {
    const n = b.moments.filter((m) => (m.support ?? []).includes(s.id)).length
    if (n >= 3 && n > b.moments.length / 2) out.push({ key: 'systemEverywhere', en: `«${s.name}» is behind ${n} of ${b.moments.length} moments: if it stops, what does the customer see?`, pt: `«${s.name}» está por trás de ${n} de ${b.moments.length} momentos: se ele parar, o que o cliente vê?` })
  }
  for (const a of b.actions) if (!a.owner) out.push({ key: 'actionNoOwner', moment: a.moment, en: `The action «${a.does}» has no owner`, pt: `A ação «${a.does}» não tem dono` })
  return out
}
