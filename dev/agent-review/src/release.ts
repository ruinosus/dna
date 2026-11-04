// The plugin's version, put in by tools/assets.mjs when it builds; «dev» when the source runs as it is (the checks).
declare const __RELEASE__: string | undefined
export const RELEASE = typeof __RELEASE__ === 'string' ? __RELEASE__ : 'dev'
