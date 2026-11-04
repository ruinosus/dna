// The profiles for the checks: `plain` is the example profile as it was in 1.2 (no markers, blocks, types or rule with a
// condition), so the checks of 1.2 stay what they were; `wave1` adds them back, as the spec's examples write them.
import type { Profile } from '../src/profile'

export const LINKS = `Links:
- Formate links assim: [título](url), nunca a URL crua.
- Um link de ação vai no topo; o link da base de ajuda vai no fim.
- Nunca escreva as palavras «clique aqui».
- No máximo 3 links por resposta.`
export const wave1 = (profile: Profile): Profile => ({
  ...profile,
  markers: [
    { id: 'size', name: 'Tamanho da resposta', in: 'instructions', pattern: '(no máximo)\\s*(\\d+)\\s*(bullets?|frases?)', value: '$2 $3' },
    { id: 'no-emoji', name: 'Sem emojis', in: 'instructions', pattern: '(sem|não use)\\s+emojis?' },
    { id: 'knowledge-only', name: 'Só o conhecimento', in: 'instructions', pattern: '(somente|apenas)[^.]{0,40}conhecimento' },
  ],
  blocks: [{ id: 'links', name: 'Formatação de links', text: LINKS, role: 'specialist' }],
  types: [
    { id: 'transaction', name: 'transação', when: { any: ['flow:*'] }, minAgents: 2 },
    { id: 'guidance', name: 'orientação', when: { all: ['text:link-domain:*', 'node:SearchAndSummarizeContent'] }, minAgents: 2 },
    { id: 'triage', name: 'triagem', when: { any: ['trigger:OnSelectIntent'] }, minAgents: 2 },
  ],
  rules: [...profile.rules, { id: 'knowledge-only', when: ['text:knowledge-only'], not: 'setting:model-knowledge=on', says: 'Quem pede só o conhecimento tem o conhecimento geral desligado' }],
})

/** The example profile with the wave 1 parts taken out. */
export const plain = (profile: Profile): Profile => ({ ...profile, markers: [], blocks: [], types: [], rules: profile.rules.filter((r) => r.has) })
