export type SimDoc = { path: string; src: string; at: number }
export type PreviewLang = 'en' | 'pt-BR'

declare module 'claude-code' {
  interface PluginState {
    'house-lights': {
      last: Shaped<SimDoc | null>
      lang: PreviewLang
    }
  }
}
