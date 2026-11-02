# Changelog

## 1.1.0 — 2026-11-02

- **gates-and-handoffs: more than one approves, or only sometimes.** A gate lists its `approvals` —
  `[{ by: tl }, { by: seg, when: change to payments }]` — all of them needed; `when` is the condition as people say it.
  `approver: tl` stays the shorthand of one, so every file made before reads and writes back the same. A second gate
  after the same stage is still refused, and now says to use `approvals`. The map shows «+ SEG if change to payments»
  under the gate and lists who approves in its detail; the workbook has a row per approval, a «When» column (only when
  some approval has a condition), «A (if …)» in the RACI and a checklist item that may not apply; the lesson says it.
  As the market does it (Azure DevOps, GitLab, ServiceNow, ITIL): one decision, a list of approvals, the condition on
  the approval.
- The engine is the hubs Ways engine 0.259.0.

## 1.0.1 — 2026-11-02

What the first run of all five in the cloud found.

- **PowerPoint (back-of-napkin, chalk-talk):** a slide's title is at the title placeholder's index 0, as PowerPoint
  numbers it: python-pptx's `slide.shapes.title`, the outline and screen readers find it (pptxgenjs numbered it 100).
  The build checks it the same way.
- **The words on screen:** the list of a course's lessons is labelled in the recipe's language too (it said
  «Lessons»); a check makes sure a pt lesson has no English word on screen.
- **dress-rehearsal:** «escalar a instância» is scaling up, not escalating: only «escalar» to someone (para, ao, à…),
  «escalar o incidente» or «escalar» alone asks «escalar para quem?». A choice can cite a numbered step under a
  heading («Passos 4»), and the game shows that step; citing only the heading of a list of steps asks which one.
- **service-blueprint:** with no `feels` at all, the «Sente» lane says «ninguém disse como o cliente se sente» instead of a
  flat red line; a moment nobody said it of gets no point on the line.
- The npm package `chalk-talk` 0.19.1 carries the player and PowerPoint fixes.

## 1.0.0 — 2026-11-01

The five skills become one plugin, **house-lights**, in one repository.

- **One install:** `/plugin install house-lights@house-lights` brings chalk-talk, back-of-napkin, dress-rehearsal,
  gates-and-handoffs and service-blueprint.
- **Two new names:** stage-door is **gates-and-handoffs**, front-of-house is **service-blueprint**. The file formats
  keep their ids (`stage-door/v1`, `front-of-house/v1`): every file made before still opens.
- **One command:** `npx house-lights <skill> <file>`, with each skill's own options and exit codes. The packages
  `back-of-napkin`, `stage-door`, `front-of-house` and `dress-rehearsal` move to it; `chalk-talk` stays the engine's
  package.
- **The engine of chalk-talk 0.18.1 everywhere:** dress-rehearsal, gates-and-handoffs and service-blueprint drew
  their lessons with the engine of 0.14.1; now every skill takes it from this repository, in the same commit.
- One gallery: https://ruinosus.github.io/house-lights/, with a page per skill.
- The npm package `chalk-talk` 0.19.0: the same engine as 0.18.1, now built in this repository.

Before 1.0.0, each skill's history is in `dev/<skill>/CHANGELOG.md` and its tags are `<skill>-v<version>`.
