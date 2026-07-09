<!--
Thanks for contributing to DNA! Fill in the summary, then check every box
that applies. See CONTRIBUTING.md for the full workflow — especially the
Python↔TypeScript parity contract and the conformance kit.
-->

## Summary

<!-- What does this PR change, and why? -->

## Work item

<!-- Link the DNA Story/Issue this PR is born from. If you used
     `dna sdlc story pr`, this is filled in and the commits are already
     stamped with the Work-Item trailer. -->

- Work-Item: Story/`s-...`

## Checklist

- [ ] **Tests pass locally** — Python (`sdk-py`), TypeScript (`sdk-ts`), and CLI (`cli`) suites are green.
- [ ] **Python↔TypeScript parity is maintained** — any behavior change to the kernel, a port, a Kind, or an extension landed in **both** SDKs in this PR; the parity gates (port-surface, descriptor-hash, kind-registry, composition) are green.
- [ ] **Conformance kit updated** — if I touched a source adapter, reader, or writer, I extended/updated the `dna.testing` conformance kit rather than adding a one-off test; market bundles still round-trip byte-identical.
- [ ] **CHANGELOG updated** — user-facing changes are noted under `## [Unreleased]` in `CHANGELOG.md`.
- [ ] **Docs updated** — README/`docs/` reflect the change where relevant (or N/A).
- [ ] **Brand guard clean** — `python3 scripts/brand_guard.py` passes; no internal brand tokens in content, paths, or commit identities.
- [ ] **No hand-edited `.dna/**.yaml`** — SDLC status changes went through the `dna sdlc` CLI.

## Notes for reviewers

<!-- Anything that needs context: trade-offs, follow-ups, intentional parity
     asymmetries (with their justification in the parity fixture), etc. -->
