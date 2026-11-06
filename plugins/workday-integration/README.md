# workday-integration

A sibling of [DNA](https://github.com/ruinosus/dna) for whoever designs a Workday integration — and for the agent
helping them: a catalog of the **Workday Web Services (SOAP)** and of **Workday's REST APIs** on your machine, so the
agent finds and reads an operation or an endpoint without reading WSDL, XSD or OpenAPI. It hands over **what the WSDLs say** and lets the agent decide:

- **search** by words, each result with what matched and where; **related**: what is around an operation (the
  business process Workday's description names, the operations on the same noun, whether a `Get_` exists, the
  operations on business process events) — facts, no verdict;
- **browse**: a service's operations, a type's fields, which operations carry a field (`operations`, `type`,
  `where`), and an operation's request and response with every field (`show`);
- a **SOAP envelope** with `{{placeholders}}` (only what is required, or `--include` / `--all`, an optional
  WS-Security header), with every **decision** it made — a reference's ID type, a choice's alternative, an optional
  container taken in — each one changed with `--id-type` and `--choose`;
- the spec of the **Copilot Studio Workday connector's «Execute SOAP operation»**: service and version, typed inputs,
  the XML template (the operation's element, as the connector takes it), the **Power Fx** of `requestBody` (free text
  escaped, dates as text), what to read back, and the identity and security notes;
- a **template of Microsoft's Employee Self-Service Workday pack** (`workdayEntityConfigurationTemplate`);
- for REST: an endpoint with its parameters (what each ID accepts, `me` too), body and response, and **the security
  domains and scope** Workday's description names; and the spec of the connector's **Execute REST request (Preview)**
  (`relativePath` with `{tenant}`, the JSON body, the Power Fx); the connector's ready-made actions (`connector`).

It reads the Operation Directory text and the WSDLs **you** give it, and **calls no tenant**: no credential, no
token, nothing of a person in what it writes. It carries no Workday file: the examples are synthetic, with made-up
fields. **Not affiliated with Workday**; Workday is a trademark of Workday, Inc.

## Install

```
/plugin marketplace add ruinosus/dna
/plugin install workday-integration@dna
```

Without Claude Code, from npm: `npx @ruinosus/workday-integration <command>` (the same commands as `node scripts/wws.mjs`),
and the MCP server as `npx -y -p @ruinosus/workday-integration workday-wws-mcp`.

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
node scripts/wws.mjs search "request flexible work arrangement"
node scripts/wws.mjs related Add_Flexible_Work_Arrangement
node scripts/wws.mjs where Flexible_Work_Arrangement_Type_Reference
node scripts/wws.mjs show Add_Flexible_Work_Arrangement --depth 3
node scripts/wws.mjs envelope Add_Flexible_Work_Arrangement --id-type Worker_Reference=WID
node scripts/wws.mjs copilot End_Flexible_Work_Arrangement --json
node scripts/wws.mjs copilot Get_Time_Off_Plan_Balances --read <path to Time_Off_Plan_Balance>
node scripts/wws.mjs ess Approve_Business_Process
node scripts/wws.mjs fetch --rest
node scripts/wws.mjs rest GET "/workers/{ID}/timeOffPlans"
node scripts/wws.mjs copilot-rest GET "/workers/{ID}/timeOffPlans" --id-form ID=me --read data.timeOffBalance
```

Every command takes `--json`. The index is in `~/.cache/dna/workday-integration` (or `--index <folder>`, or
`$WWS_INDEX`). Node 18 or later; nothing to install.

## As an MCP server

The same catalog as MCP tools (`wws_search_operations`, `wws_related_operations`, `wws_list_operations`,
`wws_get_type`, `wws_find_element`, `wws_get_operation`, `wws_build_envelope`, `wws_get_rest_endpoint`,
`wws_rest_action_spec`, `wws_list_connector_actions`, `wws_copilot_action_spec`, `wws_ess_template`, `wws_list_services`, `wws_index_status`), all
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
