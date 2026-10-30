// chalk-talk/mount.global.js: one script for a page or a Markdown preview — it starts watching on its own. A docs site
// that renders its pages on the server too (Docusaurus' clientModules) loads it there: there it does nothing.
import { watch } from './mount'

if (typeof window !== 'undefined' && typeof document !== 'undefined') watch()
