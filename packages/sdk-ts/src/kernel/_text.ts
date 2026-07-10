/**
 * Internal text helpers used by the kernel parse pipeline.
 */

/**
 * Normalize trailing whitespace of a text block entering PROMPT
 * COMPOSITION (i-013).
 *
 * Bundle bodies (SOUL.md, AGENTS.md, ...) are stored byte-faithfully —
 * editors re-add a trailing newline, and the rw conformance kit requires
 * the WRITE path to round-trip it. But at composition time the prompt
 * template supplies its own joiners (`{{{soul_content}}}\n\n`), so a
 * body's trailing newline stacked into `\n\n\n` in the composed prompt.
 * Strip ONLY here, at the consumption boundary — never at read/write,
 * which must stay byte-identical to storage.
 *
 * Twin of `strip_prompt_block` in packages/sdk-py/dna/kernel/_text.py.
 */
export function stripPromptBlock(value: string): string {
  return value.trimEnd();
}

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
