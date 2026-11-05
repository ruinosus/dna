# Changelog

## 0.1.0 — 2026-11-05

First version: `scripts/wws.mjs` with `ingest`, `status`, `search`, `trace`, `show`, `envelope`, `copilot`, `ess`
and `fetch`, `--json` on all, and `scripts/mcp.mjs`, the same as MCP tools (stdio, read-only), declared in the plugin.

- The same answers as the Python catalog it ports, on synthetic examples (the search with the same bm25 scores).
- `fetch` downloads the Operation Directory page and the WSDLs from Workday Community (never a tenant); `ingest`
  reads the directory's page or its text.
- The Copilot Studio spec's `requestBody` is the operation's element alone (as the connector takes it); `--envelope`
  for the whole one. `ess` writes a template of Microsoft's Employee Self-Service Workday pack.
- Seen on Workday's real WSDLs, and fixed from the Python: a reference's ID types are read from `xsd:appinfo`
  (`wd:enumeration`), and an optional container that holds the required fields goes in the envelope (Workday's
  `Add_…_Event_Data`); `Employee_ID` is the ID chosen for a person.
- A choice names its alternatives; an `xsd:any` is marked.
- Notes from Workday's public schema (v47.0): what the schema cannot show is marked «to confirm in the tenant»; what a
  response may carry about a person, «Sensitive:»; the identity as the signed-in user, the domain security
  (Integration Permissions, «Task not authorized») and the connector's limit.
