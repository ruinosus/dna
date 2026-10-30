// A DOM for Node, before Mermaid and its converter load (they look for window and document as they are imported):
// imported first by scripts/mermaid.mjs. linkedom stands in for the browser.
import { DOMParser, parseHTML } from 'linkedom'

const { window, document } = parseHTML('<!doctype html><html><body></body></html>')
Object.assign(globalThis, { DOMParser, document, window })
