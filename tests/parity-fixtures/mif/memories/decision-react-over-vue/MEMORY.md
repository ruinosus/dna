---
id: decision-react-over-vue
type: semantic
created: "2026-01-10T09:00:00Z"
modified: "2026-01-12T14:30:00Z"
namespace: _semantic/decisions
title: Use React over Vue for the dashboard
tags:
  - frontend
  - architecture
relationships:
  - type: relates-to
    target: /semantic/frontend-architecture.md
  - type: supersedes
    target: /semantic/vue-exploration.md
entities:
  - "@type": EntityReference
    entity: { "@id": "urn:mif:entity:technology:react" }
    entityType: Technology
    name: React
  - "@type": EntityReference
    entity: { "@id": "urn:mif:entity:technology:vuejs" }
    entityType: Technology
    name: Vue.js
extensions:
  x-dna:
    confidence_score: 0.92
    visibility: shared
---

# Use React over Vue for the dashboard

## Context

We need to choose a frontend framework for the new dashboard.

## Decision

We will use React because:
- Team has more React experience
- Better TypeScript integration
- Larger ecosystem for our needs

## Consequences

- Need to set up Create React App or Vite
- Will use React Query for data fetching
- Component library: Radix UI

## Relationships

- relates-to [Frontend Architecture](/semantic/frontend-architecture.md)
- supersedes [Vue Exploration](/semantic/vue-exploration.md)
