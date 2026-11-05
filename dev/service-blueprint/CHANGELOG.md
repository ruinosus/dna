# Changelog

## 0.2.0 — 2026-11-01

The explainer's review no longer hangs in cloud sandboxes.

- The headless browser is chalk-talk's kit (`chalk-talk/kit`, from its npm package): it talks to the browser over the
  DevTools pipe instead of `--dump-dom`, finds Playwright's Chromium, runs without the sandbox as root on Linux, and
  tries the next browser when one fails. A review that could not run now says «not checked».
- The blueprint is read by the kit's YAML reader, with the same messages and the same lines.
- The check, the gallery's pictures, the zip, the name audit and a Linux check (`npm run linux`) use the kit.
- The explainer uses chalk-talk 0.14.1.

## 0.1.0 — 2026-10-30

First version: a service blueprint file (`front-of-house/v1`) made from interviews, tickets and process notes, checked
by code (the worst moment with no action, a silent wait, a promise with no owner or time, nobody behind a moment, a
system behind almost everything, a pain with no source, an action with no owner); an offline map with the line of how
the customer feels and the five layers, a workbook, a chalk-talk explainer; two fictional examples; evals; the gallery.
