/**
 * Internal text helpers used by the kernel parse pipeline.
 */

/**
 * Return the first useful line of a markdown/text blob.
 *
 * Strips leading heading markers (`#`) and surrounding whitespace, skips
 * empty lines and divider-only lines (`---`, `===`, etc.). Truncates to
 * `maxLen` chars with an ellipsis suffix.
 *
 * Returns `null` if no meaningful line is found.
 */
export function deriveFirstLine(
  text: string | null | undefined,
  maxLen = 160,
): string | null {
  if (!text) return null;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim().replace(/^#+/, "").trim();
    if (!line) continue;
    if (/^[-=*_]+$/.test(line)) continue;
    return line.length > maxLen ? line.slice(0, maxLen) + "..." : line;
  }
  return null;
}
