# workday-integration

A sibling of [DNA](https://github.com/ruinosus/dna) for whoever designs a Workday integration: a catalog of the
**Workday Web Services (SOAP)** on your machine. Ask in Portuguese or English which operation does what you need, see
its request and response with every field, and get what the integration needs:

- the **chain** for a use case — who the user is, the operation, the approver's inbox, the business process (approve,
  deny, send back, cancel, rescind) and the gaps (no `Get_` → read with a RaaS report);
- a **SOAP envelope** with `{{placeholders}}` (only what is required, or `--include` / `--all`, an optional
  WS-Security header);
- the spec of the **Copilot Studio Workday connector's «Execute SOAP operation»**: service and version, typed inputs,
  the XML template (the operation's element, as the connector takes it), the **Power Fx** of `requestBody` (free text
  escaped, dates as text), what to read back, and the identity and security notes;
- a **template of Microsoft's Employee Self-Service Workday pack** (`workdayEntityConfigurationTemplate`).

It reads the Operation Directory text and the WSDLs **you** give it, and **calls no tenant**: no credential, no
token, nothing of a person in what it writes. It carries no Workday file: the examples are synthetic, with made-up
fields. **Not affiliated with Workday**; Workday is a trademark of Workday, Inc.

## Install

```
/plugin marketplace add ruinosus/dna
/plugin install workday-integration@dna
```

For claude.ai, upload `workday-integration.zip` from the [latest release](https://github.com/ruinosus/dna/releases)
(Settings › Capabilities › Skills, code execution on).

## Start

```
node scripts/wws.mjs fetch --services hr --version v47.0
```

downloads the Operation Directory and the WSDLs of the HR services from Workday Community and indexes them — the only
command that uses the network. Or index what you have: `ingest <the directory page or its text, and the WSDLs>`.

## Use

```
node scripts/wws.mjs trace "colaborador pede trabalho flexível e o gestor aprova"
node scripts/wws.mjs show Add_Flexible_Work_Arrangement --depth 3
node scripts/wws.mjs envelope Approve_Business_Process --wsse
node scripts/wws.mjs copilot End_Flexible_Work_Arrangement --json
node scripts/wws.mjs ess Approve_Business_Process
```

Every command takes `--json`. The index is in `~/.cache/dna/workday-integration` (or `--index <folder>`, or
`$WWS_INDEX`). Node 18 or later; nothing to install.

## As an MCP server

The same catalog as MCP tools (`wws_search_operations`, `wws_trace_use_case`, `wws_get_operation`,
`wws_build_envelope`, `wws_copilot_action_spec`, `wws_ess_template`, `wws_list_services`, `wws_index_status`), all
read-only, over stdio: `scripts/mcp.mjs`, one file. Claude Code starts it with the plugin (`.mcp.json`). Elsewhere —
VS Code's Copilot (`.vscode/mcp.json`), Claude Desktop:

```json
{ "servers": { "workday-wws": { "type": "stdio", "command": "node", "args": ["<plugin folder>/skills/workday-integration/scripts/mcp.mjs"] } } }
```

It reads the index the CLI fills (run `fetch` or `ingest` first). Copilot Studio takes only an MCP server over HTTP,
hosted somewhere; this one runs on your machine — for an agent in Copilot Studio, use what `copilot` and `ess`
write.

Tree legend: `?` 0..1, `*` 0..n, `+` 1..n, `|` a member of a choice, `@` an attribute, `↻` recursive.

## License

MIT. Bundled: [saxes](https://github.com/lddubeau/saxes) (ISC), the XML parser; and, in `mcp.mjs`, the
[MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) and [zod](https://github.com/colinhacks/zod) (MIT).
