// The words the map, the workbook and the lesson share, in English and Portuguese.
export type Lang = 'en' | 'pt'
export const WORDS = {
  en: {
    evidence: 'Evidence', customer: 'The customer does', feels: 'Feels', front: 'On stage (what they see)', back: 'Backstage', support: 'Systems and partners',
    lineInteraction: 'line of interaction', lineVisibility: 'line of visibility', lineInternal: 'line of internal interaction',
    fail: 'failure point', wait: 'wait', none: 'nothing', nobody: 'nobody', promise: 'Promise', within: 'Within', owner: 'Owner', pains: 'Pains', pain: 'Pain', source: 'Source',
    action: 'Action', actions: 'Actions', due: 'Due', moment: 'Moment', phase: 'Phase', system: 'System', moments: 'Moments', count: 'How many', way: 'Way of working',
    summary: 'Summary', blueprint: 'Blueprint', painsActions: 'Pains and actions', promises: 'Promises', systems: 'Systems', name: 'Blueprint', who: 'Who lives it',
    phases: 'Phases', look: 'To look at', nothing: 'Nothing to look at', marks: 'Marks', noFeels: 'nobody said how the customer feels',
  },
  pt: {
    evidence: 'Evidência', customer: 'O cliente faz', feels: 'Sente', front: 'Palco (quem ele vê)', back: 'Bastidores', support: 'Sistemas e parceiros',
    lineInteraction: 'linha de interação', lineVisibility: 'linha de visibilidade', lineInternal: 'linha de interação interna',
    fail: 'ponto de falha', wait: 'espera', none: 'nada', nobody: 'ninguém', promise: 'Promessa', within: 'Prazo', owner: 'Dono', pains: 'Dores', pain: 'Dor', source: 'Fonte',
    action: 'Ação', actions: 'Ações', due: 'Até', moment: 'Momento', phase: 'Fase', system: 'Sistema', moments: 'Momentos', count: 'Quantos', way: 'Jeito de trabalhar',
    summary: 'Resumo', blueprint: 'Blueprint', painsActions: 'Dores e ações', promises: 'Promessas', systems: 'Sistemas', name: 'Blueprint', who: 'Quem vive',
    phases: 'Fases', look: 'Para olhar', nothing: 'Nada para olhar', marks: 'Marcas', noFeels: 'ninguém disse como o cliente se sente',
  },
}
/** How a moment feels, as a face. */
export const FACES: Record<number, string> = { 1: '😣', 2: '😕', 3: '😐', 4: '🙂', 5: '😄' }
/** How a moment feels, as a background (RRGGBB). */
export const FEEL_FILLS: Record<number, string> = { 1: 'FFD5CC', 2: 'FFE9D1', 3: 'F1F1F1', 4: 'DDF3E6', 5: 'C9EBD6' }
