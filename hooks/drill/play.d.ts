// Types for the generated play.js (dress-rehearsal's src/play.ts): the game of a drill, pure.
export type Lang = 'en' | 'pt'
export type PlayEvent = { minute: number; kind: 'start' | 'choice' | 'call' | 'blocked' | 'end'; text: string }
export type Play = { scene: string; minute: number; lost: number; room: string[]; events: PlayEvent[]; told?: number; ended?: 'resolved' | 'worse'; blocked: { needs: string; minute: number }[] }
export type Debrief = { numbers: { resolved?: number; told?: number; lost: number; calls: number }; timeline: { at: string; kind: PlayEvent['kind']; text: string }[]; gaps: { says: string; source: string }[]; markdown: string; csv: string }
export declare function startPlay(drill: any, lang?: Lang): Play
export declare function canDo(drill: any, play: Play, choice: any): boolean
export declare function choose(drill: any, play: Play, index: number, lang?: Lang): Play
export declare function call(drill: any, play: Play, role: string, lang?: Lang): Play
export declare function clockAt(drill: any, minutes: number): string
export declare function debrief(drill: any, play: Play, looks: { en: string; pt: string }[], lang?: Lang): Debrief
