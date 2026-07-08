# Open SWE — Agent Context

This module provides autonomous software engineering agents for the Helix platform.

## Agents

- **swe-agent**: Primary coding agent. Reads GitHub issues, creates branches, implements solutions, and opens PRs.
- **reviewer-agent**: Code review specialist. Reviews PRs and provides structured feedback (BLOCKER/SUGGESTION/PRAISE/QUESTION).

## Conventions

- Never push directly to `main` or `develop`
- Use conventional commits format
- Branch pattern: `feat/<issue-id>-<slug>`
- Always include tests with implementations

## Repository

https://github.com/acme/helix
