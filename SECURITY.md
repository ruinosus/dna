# Security Policy

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Report privately through **GitHub Private Vulnerability Reporting**:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability** (under *Advisories*).
3. Fill in the form — affected version, a description, reproduction steps, and
   impact.

This opens a private advisory visible only to you and the maintainers, with a
built-in channel for coordinated disclosure. If Private Vulnerability
Reporting is unavailable to you, open a minimal public issue that says only
"security report — please open a private channel" (no details) and a
maintainer will follow up.

Please include, where possible:

- the affected package(s) — `sdk-py`, `cli`, `client-py` or `client-ts` — and version/commit;
- a minimal manifest or reproduction (see the threat model below);
- the impact and any suggested remediation.

### Response expectations

DNA is **pre-1.0** and maintained on a best-effort basis. We aim to
acknowledge a valid report within a few business days and to keep you updated
as we triage and fix. We will credit reporters who wish to be named once a fix
ships, and we ask that you give us reasonable time to remediate before any
public disclosure.

## Supported versions

While DNA is pre-1.0, **only the most recent release (the tip of `main`)
receives security fixes.** There are no long-term-support branches yet; once
DNA reaches 1.0 and follows SemVer, this section will list the supported
version ranges.

| Version | Supported |
|---|---|
| latest (`main`) | ✅ |
| any older commit / tag | ❌ |

## Threat model

DNA's core function is to **load, validate, and compose declared behavior** —
prompts, tool wiring, guardrails, personas, and composition rules — from
YAML/Markdown manifests, and to compose them on read into the system prompt
(and tool surface) of an agent. That design has a direct security
consequence:

> **A manifest is executable behavior. A malicious or attacker-controlled
> manifest is a real injection vector.**

Because "behavior is data," a crafted manifest can attempt to inject
instructions into a composed prompt, wire an agent to tools it should not
have, weaken or bypass guardrails, or smuggle content through a bundle
reader. Treat third-party manifests — Skills, Souls, Agents, Genomes,
descriptors, and any other bundle — **as untrusted code**, with the same
scrutiny you would give a third-party dependency or plugin.

**The defenses DNA provides:**

- **Schema validation on the write path.** Every document is validated
  against its per-Kind JSON Schema before it is written or accepted. This is
  the first line of defense against malformed or hostile manifests — keep it
  on; do not disable validation to "make a manifest load."
- **Guardrails as first-class, composed Kinds.** Safety/compliance rules are
  themselves declared Kinds composed into the prompt, so they can be reviewed,
  versioned, and diffed like any other artifact.
- **Byte-faithful, non-executing readers.** Market-format readers
  (`SKILL.md`, `SOUL.md`, `AGENTS.md`) parse and round-trip content; they do
  not execute it. The conformance kit enforces this round-trip.

**Responsibilities that stay with you, the operator:**

- **Vet the provenance of every manifest you load**, exactly as you would vet
  a code dependency. Do not compose prompts from manifests you did not author
  or review.
- **Do not feed secrets into manifests.** Manifests are versioned artifacts;
  treat them as world-readable. Use your runtime's secret management for
  credentials, never a `spec` field.
- **Sandbox the downstream execution.** DNA composes the *instruction* an
  agent runs on; the security of the model call, the tools it can reach, and
  the environment those tools run in is owned by the system that consumes
  DNA's output.

If you believe any of these defenses can be bypassed — for example, a manifest
shape that defeats schema validation, or a reader that can be made to execute
content — please report it through the private channel above.
