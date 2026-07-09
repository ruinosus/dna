---
apiVersion: github.com/ruinosus/dna/research/v1
kind: Research
metadata:
  name: rsh-doc-frameworks-oss
spec:
  title: Documentation frameworks & tooling for a public OSS SDK
  objective: Determine how to structure documentation for the public DNA SDK — organizing frameworks,
    community-health files, doc-site tooling, dual-language API reference, and the docs-quality loop.
  methodology: web-search-curated
  overall_confidence: high
  conducted_by: claude-code
  conducted_at: '2026-07-09T00:00:00+00:00'
  scope_ref: dna-development
  status: published
  visibility: shared
  owner: claude-code
  tags:
  - docs
  - oss
  - tooling
  - diataxis
  key_takeaways:
  - Diataxis (tutorials/how-to/reference/explanation) is the de-facto IA framework — use as compass, not
    law
  - Close the GitHub Community Standards checklist before going public (README/LICENSE/CONTRIBUTING/CODE_OF_CONDUCT/SECURITY/issue+PR
    templates)
  - Docs live in the monorepo, published to GitHub Pages, versioned with code
  - 'Docs must not rot: test every snippet OR generate reference from source'
  - MkDocs+Material is lowest-friction for a Python-centric team; mkdocstrings (Py) + TypeDoc (TS) for
    per-language API ref
  - Turn the conformance kit into a published parity matrix — proof, not prose
  executive_summary: 'For a public, dual-language (Python + TypeScript) SDK like DNA, the documentation
    should be organized with Diataxis as the information-architecture compass — four modes (tutorials,
    how-to guides, reference, explanation) that keep authoring intent explicit — without treating it as
    rigid law. Before the repo goes public, close the GitHub Community Standards checklist (README, LICENSE,
    CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, plus issue and PR templates); SECURITY.md is especially load-bearing
    here because DNA executes behavior declared in manifests, so a malicious manifest is a real injection
    vector that needs a disclosure channel. Keep docs in the monorepo, versioned with the code, and publish
    to GitHub Pages. The single most important quality property is that docs cannot silently rot: either
    test every code snippet in CI or generate the reference straight from source. A pragmatic, low-friction
    stack for a Python-centric team is MkDocs + Material, with mkdocstrings for the Python API reference
    and TypeDoc for TypeScript, wired to GitHub Pages and a docs CI job (link check + strict build + doctest).
    Finally, the SDK''s byte-parity conformance kit should be surfaced as a published language x requirement
    parity matrix — proof over prose.'
  findings:
  - id: f-diataxis-adoption
    title: Diataxis is the widely-adopted 4-quadrant docs IA framework
    evidence_rating: evidence-based
    summary: 'Diataxis separates docs into tutorials, how-to guides, reference, and explanation. Adopted
      by Django, Cloudflare, NumPy, and Canonical/Ubuntu among others. It is an organizing compass for
      authoring intent, not a rigid rulebook — apply it to keep each page''s job clear. Sources: https://diataxis.fr/
      and https://idratherbewriting.com/blog/what-is-diataxis-documentation-framework'
    source_refs: []
    tags:
    - ia
    - framework
  - id: f-security-md-critical
    title: SECURITY.md is critical because DNA executes declared config
    evidence_rating: evidence-based
    summary: 'The GitHub Community Standards checklist (README/LICENSE/CONTRIBUTING/CODE_OF_CONDUCT/ SECURITY
      + issue/PR templates) is table stakes for a public repo. SECURITY.md matters acutely for DNA specifically:
      because the SDK runs behavior declared in manifests, injection via a crafted manifest is a real
      attack vector, so a coordinated-disclosure channel is required. Source: https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories'
    source_refs: []
    tags:
    - community-health
    - security
  - id: f-readme-antipattern
    title: README 'becomes the manual' anti-pattern — move to the site + test the quickstart
    evidence_rating: evidence-based
    summary: 'A common failure is the README growing into an unmaintainable full manual. The fix is to
      keep the README a concise entry point and move depth to the versioned doc site, with a quickstart
      that is tested in CI so it cannot drift. Sources: https://github.com/matiassingers/awesome-readme
      and the docs-as-code practice at https://buildwithfern.com/post/docs-as-code'
    source_refs: []
    tags:
    - readme
    - docs-as-code
  - id: f-mkdocs-vs-docusaurus
    title: MkDocs-Material vs Docusaurus trade-off centers on versioning + language fit
    evidence_rating: opinion-practice
    summary: 'MkDocs + Material is the lowest-friction choice for a Python-centric team and pairs with
      mkdocstrings; Docusaurus (React/MDX) has stronger built-in doc versioning and a JS-native feel.
      For a dual-language SDK the deciding factors are versioning ergonomics and how the per-language
      API reference is generated. Source generator comparison: https://okidoki.dev/documentation-generator-comparison'
    source_refs: []
    tags:
    - tooling
    - doc-site
  recommendations:
  - id: rec-adopt-diataxis
    priority: high
    summary: Adopt Diataxis as the spine of the docs IA (tutorials/how-to/reference/explanation).
    backed_by_findings:
    - f-diataxis-adoption
    status: proposed
  - id: rec-close-community-health
    priority: high
    summary: Close the community-health checklist before going public — README/LICENSE/CONTRIBUTING/CODE_OF_CONDUCT/SECURITY
      + issue/PR templates.
    backed_by_findings:
    - f-security-md-critical
    status: proposed
  - id: rec-doc-stack
    priority: medium
    summary: Standardize on MkDocs + Material + mkdocstrings (Py) + TypeDoc (TS), published to GitHub
      Pages.
    backed_by_findings:
    - f-mkdocs-vs-docusaurus
    - f-readme-antipattern
    status: proposed
  - id: rec-docs-ci
    priority: medium
    summary: 'Add a docs CI job: lychee link-check + strict site build + doctest of every snippet.'
    backed_by_findings:
    - f-readme-antipattern
    status: proposed
  - id: rec-parity-matrix
    priority: medium
    summary: Generate a published parity matrix from the conformance kit — proof over prose.
    backed_by_findings:
    - f-diataxis-adoption
    status: proposed
  created_at: '2026-07-09T12:48:11+00:00'
  updated_at: '2026-07-09T12:48:11+00:00'
---

# Research — Documentation frameworks & tooling for a public OSS SDK

Methodology: web-search-curated · 0 sources · 4 findings.

This file's spec (frontmatter above) is the authoritative data. The prose below is for human reading and is regenerated on each write. Edit via `dna research` CLI or the Studio viewer; raw frontmatter edits are also supported.
