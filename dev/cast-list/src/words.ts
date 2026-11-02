// The words the review, the map, the workbook and the lesson share, in English and Portuguese.
import type { Role } from './profile'
export type { Lang } from './labels'

/** A role, for one or many: «1 especialista», «4 especialistas». */
export const ROLE_WORDS: Record<Role, { en: [string, string]; pt: [string, string] }> = {
  specialist: { en: ['specialist', 'specialists'], pt: ['especialista', 'especialistas'] },
  orchestrator: { en: ['orchestrator', 'orchestrators'], pt: ['orquestrador', 'orquestradores'] },
}
export const roleWord = (role: Role, lang: 'en' | 'pt', n: number) => ROLE_WORDS[role][lang][n === 1 ? 0 : 1]

/** The workbook's sheets and columns; fromSheets reads them back in either language. */
export const SHEET_WORDS = {
  en: {
    summary: 'Summary', matrix: 'Matrix', patterns: 'Patterns', text: 'Text', off: 'Off pattern', gaps: 'Gaps', conflicts: 'Conflicts', agents: 'Cast', evidence: 'Evidence', declared: 'Declared', unknown: 'Not understood',
    dimension: 'Dimension', fact: 'Fact', key: 'Key', agent: 'Who', name: 'Name', role: 'Role', scope: 'Scope', share: 'Share', have: 'Who has it', lack: 'Who lacks it',
    decision: 'Decision', why: 'Why', missing: 'Missing', accepted: 'Accepted pattern', rule: 'Rule', says: 'Says', notMet: 'Who does not meet it', value: 'Value', source: 'Source',
    inYaml: 'In the YAML', file: 'File', line: 'Line', facts: 'Facts', alone: 'Only it has', children: 'Children', kind: 'Kind',
    types: 'Types', id: 'Id', label: 'Label', body: 'Text', variant: 'Variation', official: 'Official', type: 'type',
    yes: 'yes', no: 'no', accept: 'accepted', reject: 'rejected', platform: 'platform', specialist: 'specialist', orchestrator: 'orchestrator',
    title: 'The cast, compared', look: 'To look at', nothing: 'Nothing to look at', privacy: 'This file holds the client’s data: keep it in the client’s environment.',
    count: { agents: 'In the cast', orchestrators: 'Orchestrators', specialists: 'Specialists', patterns: 'Patterns', off: 'Off a pattern', gaps: 'Rules not met', conflicts: 'Conflicts', solos: 'Only one has it' },
    why_: { yaml: 'YAML that does not read', empty: 'empty', kind: 'a kind Copilot Studio does not have', file: 'not a Copilot Studio file' },
  },
  pt: {
    summary: 'Resumo', matrix: 'Matriz', patterns: 'Padrões', text: 'Texto', off: 'Fora do padrão', gaps: 'Lacunas', conflicts: 'Conflitos', agents: 'Elenco', evidence: 'Evidências', declared: 'Declarado', unknown: 'Não entendeu',
    dimension: 'Dimensão', fact: 'Fato', key: 'Chave', agent: 'Quem', name: 'Nome', role: 'Papel', scope: 'Escopo', share: 'Quantos', have: 'Quem tem', lack: 'Quem falta',
    decision: 'Decisão', why: 'Por quê', missing: 'Falta', accepted: 'Padrão aceito', rule: 'Regra', says: 'Diz', notMet: 'Quem não cumpre', value: 'Valor', source: 'Fonte',
    inYaml: 'No YAML', file: 'Arquivo', line: 'Linha', facts: 'Fatos', alone: 'Só ele tem', children: 'Filhos', kind: 'Kind',
    types: 'Tipos', id: 'Id', label: 'Rótulo', body: 'Texto', variant: 'Variação', official: 'Oficial', type: 'tipo',
    yes: 'sim', no: 'não', accept: 'aceito', reject: 'rejeitado', platform: 'plataforma', specialist: 'especialista', orchestrator: 'orquestrador',
    title: 'Elenco comparado', look: 'Para olhar', nothing: 'Nada para olhar', privacy: 'Este arquivo tem dados do cliente: deixe-o no ambiente dele.',
    count: { agents: 'No elenco', orchestrators: 'Orquestradores', specialists: 'Especialistas', patterns: 'Padrões', off: 'Fora do padrão', gaps: 'Regras não cumpridas', conflicts: 'Conflitos', solos: 'Só um tem' },
    why_: { yaml: 'YAML que não se lê', empty: 'vazio', kind: 'um kind que o Copilot Studio não tem', file: 'não é arquivo do Copilot Studio' },
  },
}
