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

/** /lenses: a way of working written by gates-and-handoffs --lens as another skill's recipe, and where it stands beside
 * the way (new; the same; from an earlier version of the way; different, maybe edited by hand). */
export type LensKind = 'sim' | 'blueprint' | 'drill'
export type LensItem = { kind: LensKind; file: string; text: string; bets: number; state: 'new' | 'same' | 'older' | 'edited' | 'error'; said: string[]; armed?: boolean; wrote?: boolean }
export type LensDoc = { path: string; lang: 'en' | 'pt'; items: LensItem[] }

/** /solution: an opening-night solution as its --check --json read it — each piece, where it stands, and the lens
 * the pane's button is waiting to be pressed again for (`armed`) before making it again from the way. */
export type SolutionPiece = { kind: string; file: string; skill: string; state: 'ok' | 'missing' | 'broken' | 'unchecked'; stale?: boolean; said: string[]; looks: string[]; redone?: boolean }
export type SolutionDoc = { path: string; name: string; lang: 'en' | 'pt'; way: string; pieces: SolutionPiece[]; armed: string }

declare module 'claude-code' {
  interface PluginState {
    'house-lights': {
      last: Shaped<SimDoc | null>
      lang: PreviewLang
      recipe: Shaped<RecipeDoc | null>
      cast: Shaped<CastDoc | null>
      castOpen: string
      drill: Shaped<DrillDoc | null>
      lenses: Shaped<LensDoc | null>
      solution: Shaped<SolutionDoc | null>
    }
  }
}
