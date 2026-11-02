// The words the review, the map, the workbook and the lesson share, in English and Portuguese.
import type { Role } from './profile'
export type { Lang } from './labels'

/** A role, for one or many: «1 especialista», «4 especialistas». */
export const ROLE_WORDS: Record<Role, { en: [string, string]; pt: [string, string] }> = {
  specialist: { en: ['specialist', 'specialists'], pt: ['especialista', 'especialistas'] },
  orchestrator: { en: ['orchestrator', 'orchestrators'], pt: ['orquestrador', 'orquestradores'] },
}
export const roleWord = (role: Role, lang: 'en' | 'pt', n: number) => ROLE_WORDS[role][lang][n === 1 ? 0 : 1]
