// The catalog as an MCP server over stdio, for a client without a shell or skills (Claude Desktop, VS Code's Copilot,
// any MCP client): the same core as the CLI, the tools of the Python server it replaces (wws_*), every one read-only.
// The index is the CLI's ($WWS_INDEX, else ~/.cache/dna/workday-integration): fill it with `wws.mjs ingest` or `fetch`.
// It calls no tenant and never goes to the network.
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import { z } from 'zod'
import { HR_SERVICES } from './config.mjs'
import { defaultIndexDir, Index } from './index.mjs'
import { LookupError } from './render.mjs'
import { copilotActionSpec, essTemplate, getOperation, makeEnvelope, traceUseCase } from './workflows.mjs'

const VERSION = typeof __WWS_VERSION__ === 'string' ? __WWS_VERSION__ : '0.0.0'
const READ_ONLY = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false }
const EMPTY = 'Nothing indexed yet. Run: node <plugin>/skills/workday-integration/scripts/wws.mjs ingest <the Operation Directory and the WSDLs> (or fetch --services hr), then call again.'

const index = () => new Index(process.env.WWS_INDEX || defaultIndexDir())
const answer = (value) => ({ content: [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }] })
const failure = (text) => ({ content: [{ type: 'text', text }], isError: true })

/** One tool: the index read fresh at each call (an ingest may have run meanwhile), a missing name an error, not a crash. */
function tool(server, name, description, shape, run) {
  server.registerTool(name, { description, inputSchema: shape, annotations: READ_ONLY }, async (args) => {
    const ix = index()
    if (ix.empty && name !== 'wws_index_status') return failure(EMPTY)
    try {
      return answer(run(ix, args))
    } catch (e) {
      if (e instanceof LookupError) return failure(e.message)
      throw e
    }
  })
}

export function server() {
  const s = new McpServer({ name: 'workday-wws', version: VERSION })
  const operation = z.string().describe('The operation, e.g. Add_Flexible_Work_Arrangement')
  const service = z.string().optional().describe('The service, when the operation is in more than one')
  const version = z.string().optional().describe('The version, e.g. v47.0 (the latest indexed by default)')
  const include = z.array(z.string()).optional().describe('Optional elements to add, as paths: ["Business_Process_Parameters/Auto_Complete"]')
  const scope = z.enum(['hr', 'all']).optional().describe("'hr' (the default) or 'all' services")

  tool(s, 'wws_search_operations', 'Search Workday Web Services operations by intent, in Portuguese or English ("aprovar home office", "time off balance", Add_Flexible_Work_Arrangement). HR services by default.', { query: z.string(), scope, limit: z.number().int().min(1).max(50).optional() },
    (ix, a) => ({ results: ix.search(a.query, { scope: a.scope ?? 'hr', limit: a.limit ?? 10 }) }))
  tool(s, 'wws_trace_use_case', "Map a use case, in the person's words, to the chain of operations: identify the user, the operation, the approver's inbox, the business process lifecycle (approve, deny, send back, cancel, rescind), related operations and gaps (no Get_ → RaaS).", { goal: z.string(), scope },
    (ix, a) => traceUseCase(ix, a.goal, { scope: a.scope ?? 'hr' }))
  tool(s, 'wws_get_operation', "An operation's request (or response) tree: cardinality, types, enumerations, each reference's ID @type options; `path` to go down a big one.", { operation, service, version, response: z.boolean().optional(), path: z.string().optional(), depth: z.number().int().min(1).max(12).optional(), format: z.enum(['text', 'json']).optional() },
    (ix, a) => getOperation(ix, a.operation, { service: a.service, version: a.version, which: a.response ? 'response' : 'request', path: a.path, depth: a.depth ?? 4, fmt: a.format ?? 'text' }))
  tool(s, 'wws_build_envelope', 'A SOAP envelope with {{placeholders}}: only what is required (and the optional containers that hold it), or include=[…], or mode "all"; an optional WS-Security header with placeholders, for SoapUI or Postman.', { operation, service, version, include, mode: z.enum(['required', 'all']).optional(), with_wsse_header: z.boolean().optional(), body_only: z.boolean().optional() },
    (ix, a) => makeEnvelope(ix, a.operation, { service: a.service, version: a.version, include: a.include ?? [], mode: a.mode ?? 'required', withHeader: Boolean(a.with_wsse_header), bodyOnly: Boolean(a.body_only) }))
  tool(s, 'wws_copilot_action_spec', "The spec of the Copilot Studio Workday connector's «Execute SOAP operation»: service and version, typed inputs, the XML template, the Power Fx of requestBody (the element alone by default; body_style 'envelope' for the whole one) and what to read back, with the identity and security notes.", { operation, service, version, include, body_style: z.enum(['body', 'envelope']).optional() },
    (ix, a) => copilotActionSpec(ix, a.operation, { service: a.service, version: a.version, include: a.include ?? [], bodyStyle: a.body_style ?? 'body' }))
  tool(s, 'wws_ess_template', "The operation as a template of Microsoft's Employee Self-Service Workday pack (workdayEntityConfigurationTemplate): the scenario, the request template with {Placeholders}, what to read back as local-name() XPaths.", { operation, service, version, include },
    (ix, a) => essTemplate(ix, a.operation, { service: a.service, version: a.version, include: a.include ?? [] }))
  tool(s, 'wws_list_services', 'The services indexed, with how many operations each and whether its WSDL is in.', { scope },
    (ix, a) => {
      const st = ix.status()
      const withSchema = new Set(st.schemas.map((x) => x.service))
      const hr = new Set(HR_SERVICES)
      return { services: st.services.filter((x) => (a.scope ?? 'hr') === 'all' || hr.has(x.service)).map((x) => ({ ...x, schema: withSchema.has(x.service) })) }
    })
  tool(s, 'wws_index_status', 'What is indexed: operations, services, the WSDLs and when.', {}, (ix) => (ix.empty ? { empty: true, hint: EMPTY, index: ix.dir } : ix.status()))
  return s
}

export async function main() {
  await server().connect(new StdioServerTransport())
}

