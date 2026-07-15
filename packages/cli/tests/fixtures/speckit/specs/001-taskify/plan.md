# Taskify — implementation plan

**Status**: Accepted

## Approach

A React front-end over a REST API. The board state is a single aggregate
persisted per team. Drag-and-drop uses optimistic updates reconciled against
the server.

## Phases

1. Data model + REST contracts.
2. Board rendering.
3. Drag-and-drop with reconciliation.
