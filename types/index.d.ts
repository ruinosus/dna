/** The recipe in the preview; `sets` are the controls moved on the pane and `rows` the numbers they gave. */
export type SimDoc = { path: string; src: string; at: number; sets?: Record<string, number>; rows?: string[] }
export type PreviewLang = 'en' | 'pt-BR'
/** A way of working or a service blueprint as its skill's check read it (--check --json), for the preview pane. */
export type RecipeDoc = { path: string; kind: 'way' | 'blueprint'; read: unknown; at: number }
export type CastGroup = { name: string; looks: string[] }
/** The last /cast: the folder compared and what cast-list said about it. */
export type CastDoc = { folder: string; lang: 'en' | 'pt'; profile?: string; summary: string[]; groups: CastGroup[]; at: number }

/** A drill being played in the pane: the drill as dress-rehearsal's check read it, and the game (play.ts's Play). */
export type DrillDoc = {
  path: string
  lang: 'en' | 'pt'
  read: { drill: any; looks: { en: string; pt: string }[]; excerpts: Record<string, string> }
  play: { scene: string; minute: number; lost: number; room: string[]; events: { minute: number; kind: 'start' | 'choice' | 'call' | 'blocked' | 'end'; text: string }[]; told?: number; ended?: 'resolved' | 'worse'; blocked: { needs: string; minute: number }[] }
  then: string
  saved: string
}

declare module 'claude-code' {
  interface PluginState {
    'house-lights': {
      last: Shaped<SimDoc | null>
      lang: PreviewLang
      recipe: Shaped<RecipeDoc | null>
      cast: Shaped<CastDoc | null>
      castOpen: string
      drill: Shaped<DrillDoc | null>
    }
  }
}
