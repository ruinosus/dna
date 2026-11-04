export type SimDoc = { path: string; src: string; at: number }
export type PreviewLang = 'en' | 'pt-BR'
/** A way of working or a service blueprint as its skill's check read it (--check --json), for the preview pane. */
export type RecipeDoc = { path: string; kind: 'way' | 'blueprint'; read: unknown; at: number }
export type CastGroup = { name: string; looks: string[] }
/** The last /cast: the folder compared and what cast-list said about it. */
export type CastDoc = { folder: string; lang: 'en' | 'pt'; summary: string[]; groups: CastGroup[]; at: number }

declare module 'claude-code' {
  interface PluginState {
    'house-lights': {
      last: Shaped<SimDoc | null>
      lang: PreviewLang
      recipe: Shaped<RecipeDoc | null>
      cast: Shaped<CastDoc | null>
      castOpen: string
    }
  }
}
