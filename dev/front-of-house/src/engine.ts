// What scripts/build.mjs uses, bundled into scripts/engine.mjs by tools/assets.mjs.
export { FORMAT, readBlueprint, problemText } from './blueprint'
export { reviewBlueprint } from './review'
export { workbookOf, workbookFile } from './workbook'
export { lessonOf } from './lesson'
export { validateScene } from '@lib/drawing/recipe'
