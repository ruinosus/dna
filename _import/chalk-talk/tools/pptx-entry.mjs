// The PowerPoint maker, bundled by tools/assets.mjs into skills/chalk-talk/scripts/pptx.mjs (back-of-napkin 0.2.0):
// one slide per item, its title, a picture or a video (with a cover), and the speaker notes — all from data: URLs, so
// nothing is read from disk or the network.
import PptxGenJS from 'pptxgenjs'

/** `slides`: [{ title, notes, image?, video?, cover? }] (data: URLs); `width`/`height`: the drawing's size; `paper`: its
 * colour, behind the slide (#FBF7EE paper, #26372E chalkboard). */
export async function buildPptx({ title, width, height, paper = '#FBF7EE', slides }) {
  const pptx = new PptxGenJS()
  pptx.layout = 'LAYOUT_WIDE' // 13.33 × 7.5 in
  pptx.title = title
  const W = 13.333
  const H = 7.5
  const top = 0.9
  // The drawing as large as it fits under the title, centred.
  const scale = Math.min((W - 0.6) / width, (H - top - 0.3) / height)
  const w = width * scale
  const h = height * scale
  const box = { x: (W - w) / 2, y: top + (H - top - 0.3 - h) / 2, w, h }
  // A dark paper (the chalkboard) takes a light title.
  const dark = parseInt(paper.slice(1, 3), 16) < 128
  for (const s of slides) {
    const slide = pptx.addSlide()
    slide.background = { color: paper.replace('#', '') }
    slide.addText(s.title, { x: 0.3, y: 0.15, w: W - 0.6, h: 0.6, fontSize: 26, bold: true, color: dark ? 'F2EFE6' : '242424', fontFace: 'Calibri' })
    if (s.video) slide.addMedia({ type: 'video', data: s.video, cover: s.cover, extn: s.video.startsWith('data:video/mp4') ? 'mp4' : 'webm', ...box })
    else if (s.image) slide.addImage({ data: s.image, ...box })
    if (s.notes) slide.addNotes(s.notes)
  }
  return pptx.write({ outputType: 'nodebuffer' })
}

/** What a .pptx holds, for the build to check what it made: the slides, the notes and the media files by extension. */
export async function inspectPptx(buffer) {
  const JSZip = (await import('jszip')).default
  const zip = await JSZip.loadAsync(buffer)
  const names = Object.keys(zip.files)
  const count = (re) => names.filter((n) => re.test(n)).length
  return {
    slides: count(/^ppt\/slides\/slide\d+\.xml$/),
    notes: count(/^ppt\/notesSlides\/notesSlide\d+\.xml$/),
    media: Object.fromEntries(['png', 'mp4', 'webm'].map((e) => [e, count(new RegExp(`^ppt/media/.+\\.${e}$`))])),
  }
}
