// The checks' one helper: print ✓ or ✗ with what failed, and exit 1 at the end when anything did.
let failed = 0
export const ok = (cond: boolean, what: string, detail: unknown = '') => {
  console.log(`${cond ? '✓' : '✗'} ${what}${!cond && detail !== '' ? `\n  ${typeof detail === 'string' ? detail : JSON.stringify(detail)}` : ''}`)
  if (!cond) failed++
}
export const done = () => process.exit(failed ? 1 : 0)
