# workday-integration

A catalog of the **Workday Web Services (SOAP)** and of **Workday's REST APIs** on your machine, as a command and as
an MCP server, for whoever designs a Workday integration — and for the agent helping them. It finds the operation or
the endpoint by words, shows every field of its request and response, and writes what an integration needs: a SOAP
envelope with `{{placeholders}}`, or the spec of the Copilot Studio Workday connector's «Execute SOAP operation» or
«Execute REST request (Preview)» (typed inputs, the template, the Power Fx, what to read back), each with the
decisions it made.

It reads the Operation Directory and the WSDLs **you** give it (or downloads them from Workday Community with
`fetch`), and **calls no tenant**: no credential, no token. It carries no Workday file: the examples are synthetic.
**Not affiliated with Workday**; Workday is a trademark of Workday, Inc.

## Start

```
npx @ruinosus/workday-integration fetch --services hr --version v47.0   # the HR services' directory and WSDLs
npx @ruinosus/workday-integration fetch --rest                          # and the REST specifications
```

`fetch` is the only command that uses the network. Or index what you have:
`npx @ruinosus/workday-integration ingest <the directory page or its text, and the WSDLs>`.

## Use

```
npx @ruinosus/workday-integration search "request time off"
npx @ruinosus/workday-integration related Enter_Time_Off
npx @ruinosus/workday-integration show Enter_Time_Off --depth 3
npx @ruinosus/workday-integration envelope Enter_Time_Off --id-type Worker_Reference=WID
npx @ruinosus/workday-integration copilot Enter_Time_Off --json
npx @ruinosus/workday-integration rest POST "/workers/{ID}/requestTimeOff"
npx @ruinosus/workday-integration copilot-rest POST "/workers/{ID}/requestTimeOff" --id-form ID=me --include days.date
npx @ruinosus/workday-integration connector
```

Every command takes `--json`; with no command, the list. Installed (`npm i -g @ruinosus/workday-integration`), the
command is also `wws`. The index is in `~/.cache/dna/workday-integration` (or `--index <folder>`, or `$WWS_INDEX`).
Node 18 or later.

## As an MCP server

The same catalog as read-only MCP tools over stdio — VS Code's Copilot (`.vscode/mcp.json`):

```json
{ "servers": { "workday-wws": { "type": "stdio", "command": "npx", "args": ["-y", "-p", "@ruinosus/workday-integration", "workday-wws-mcp"] } } }
```

Claude Desktop takes the same command and arguments under `mcpServers`. It reads the index the command fills: run
`fetch` or `ingest` first.

For Claude Code, the plugin brings the skill and the server together:
`/plugin marketplace add ruinosus/dna` then `/plugin install workday-integration@dna`. More in the
[plugin's README](https://github.com/ruinosus/dna/tree/main/plugins/workday-integration).
