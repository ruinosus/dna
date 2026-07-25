---
apiVersion: github.com/ruinosus/dna/research/v1
kind: Research
metadata:
  name: rsh-exemplar-sdk-repos
spec:
  title: How exemplary OSS SDK repos structure their documentation
  objective: Extract concrete documentation patterns from 11 exemplary OSS projects to guide the DNA SDK's
    public docs, especially dual-language, conceptual-thesis, CLI, and methodology.
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
  - exemplars
  - dual-language
  key_takeaways:
  - 'Table stakes: README+CONTRIBUTING+LICENSE, docs in the (mono)repo, 4-quadrant IA'
  - 'Best-in-class = docs that can''t rot: Pydantic runs every snippet (pytest-examples), Ruff/uv generate
    reference from source, tRPC type-checks snippets (twoslash)'
  - llms.txt + root AGENTS.md/CLAUDE.md treated as first-class agent-facing docs
  - Concept/normative layer written ONCE language-agnostic (Temporal Encyclopedia, OTel spec, CloudEvents
    spec+primer)
  - Conformance published as a language x requirement matrix (OTel spec-compliance-matrix, CloudEvents
    SDK.md)
  - 'Dual-language: everyone keeps API reference per-language; LangChain authors prose once via :::python/:::js
    fences — best fit for a byte-parity SDK'
  executive_summary: 'Surveying 11 well-regarded OSS projects (Pydantic, Ruff, uv, tRPC, Zod, Bun, Temporal,
    CloudEvents, OpenTelemetry, Starlight, and LangChain) yields a consistent picture. The table stakes
    are unremarkable: a README, CONTRIBUTING, and LICENSE, docs kept in the (mono)repo, and a four-quadrant
    information architecture. What separates best-in-class projects is that their docs cannot rot — Pydantic
    executes every documentation snippet via pytest-examples, Ruff and uv generate their reference material
    directly from source, and tRPC type-checks its snippets with twoslash. Agent-facing docs are now first
    class: projects ship llms.txt and treat a root AGENTS.md / CLAUDE.md as real documentation. For concepts,
    the strongest projects write the normative/conceptual layer once in a language-agnostic form (Temporal''s
    Encyclopedia, the OpenTelemetry specification, the CloudEvents spec plus a primer) and publish conformance
    as a language x requirement matrix. On the dual-language question specifically, everyone keeps API
    reference per-language, but LangChain''s single-source authoring — one prose page with :::python and
    :::js fences — is the best fit for a byte-parity SDK like DNA, where the two runtimes are behaviorally
    identical.'
  findings:
  - id: f-single-source-dual-language
    title: 'Single-source dual-language authoring is the #1 win for DNA'
    evidence_rating: opinion-practice
    summary: 'LangChain authors prose once and switches code per-language with :::python/:::js fences,
      while keeping API reference generated per-language. For a byte-parity SDK where Python and TypeScript
      are behaviorally identical, single-source authoring avoids two drifting copies of the same conceptual
      page. Sources: https://github.com/langchain-ai/langchain-docs pattern; per-language reference precedent
      across the surveyed repos.'
    source_refs: []
    tags:
    - dual-language
    - authoring
  - id: f-crd-spec-status-framing
    title: K8s CRD spec-vs-status framing fits DNA's 'Kind is data not class'
    evidence_rating: evidence-based
    summary: 'The Kubernetes CRD model (declarative spec vs observed status; Namespaced vs Cluster scope)
      is a well-understood mental model that maps cleanly onto DNA''s Kinds-as-data design. Framing DNA''s
      concepts against CRDs gives readers an anchor. Reflected in CloudEvents/OTel normative specs: https://github.com/cloudevents/spec
      and https://github.com/open-telemetry/opentelemetry-specification'
    source_refs: []
    tags:
    - concepts
    - framing
  - id: f-cli-ref-from-source
    title: CLI reference generated-from-source (uv/Ruff pattern)
    evidence_rating: evidence-based
    summary: 'uv and Ruff generate their command reference directly from the command definitions, so the
      docs cannot drift from the actual CLI. DNA should generate `dna` command reference the same way.
      Sources: https://github.com/astral-sh/uv and https://github.com/astral-sh/ruff'
    source_refs: []
    tags:
    - cli
    - generated-docs
  - id: f-conformance-matrix
    title: Conformance matrix generated from the parity test suite
    evidence_rating: evidence-based
    summary: 'OpenTelemetry publishes a spec-compliance matrix and CloudEvents an SDK.md matrix — a language
      x requirement grid proving what each SDK implements. DNA''s byte-parity test suite can generate
      the equivalent parity matrix as published proof. Sources: https://github.com/open-telemetry/opentelemetry-specification
      and https://github.com/cloudevents/spec'
    source_refs: []
    tags:
    - conformance
    - parity
  - id: f-sdlc-methodology-pillar
    title: SDLC methodology as a first-class pillar, dogfooded
    evidence_rating: opinion-practice
    summary: 'Starlight and Temporal treat their methodology/conceptual material as a top-level docs pillar.
      DNA can make its SDLC methodology a first-class pillar, proven by dogfooding this repo''s own .dna/
      timeline. Source: https://github.com/withastro/starlight'
    source_refs: []
    tags:
    - methodology
    - sdlc
  recommendations:
  - id: rec-single-source-authoring
    priority: high
    summary: Adopt single-source :::python/:::js authoring for prose + per-language API reference.
    backed_by_findings:
    - f-single-source-dual-language
    status: proposed
  - id: rec-thesis-spec-primer
    priority: high
    summary: Write the thesis as a CloudEvents-style spec+primer opening with 'CRDs, but for agent behavior'.
    backed_by_findings:
    - f-crd-spec-status-framing
    status: proposed
  - id: rec-cli-generated
    priority: medium
    summary: Generate the CLI reference from command defs (uv/Ruff pattern).
    backed_by_findings:
    - f-cli-ref-from-source
    status: proposed
  - id: rec-publish-parity-matrix
    priority: medium
    summary: Turn the conformance kit into a published parity matrix (OTel style).
    backed_by_findings:
    - f-conformance-matrix
    status: proposed
  - id: rec-sdlc-pillar
    priority: medium
    summary: Make the SDLC methodology a top-level docs pillar, proven by dogfooding this repo's .dna/
      timeline.
    backed_by_findings:
    - f-sdlc-methodology-pillar
    status: proposed
  created_at: '2026-07-09T12:48:13+00:00'
  updated_at: '2026-07-09T12:48:13+00:00'
---

# Research — How exemplary OSS SDK repos structure their documentation

Methodology: web-search-curated · 0 sources · 5 findings.

This file's spec (frontmatter above) is the authoritative data. The prose below is for human reading and is regenerated on each write. Edit via `dna research` CLI or the Studio viewer; raw frontmatter edits are also supported.
