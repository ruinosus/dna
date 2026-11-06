---
name: workday-integration
description: Finds which Workday Web Service (SOAP) operation does what someone wants, and writes what an integration needs from it — the request and response with every field, a SOAP envelope with {{placeholders}}, and the spec of the Copilot Studio Workday connector's «Execute SOAP operation» (typed inputs, the XML template, the Power Fx of requestBody, what to read back) — from a local catalog of the Operation Directory text and the WSDLs the person has. In English or Portuguese. Use when someone designs or documents a Workday integration, a business process and its approvals, or a Copilot Studio action on Workday ("which Workday operation lets an employee request flexible work and the manager approve?", "build the SOAP envelope for Approve_Business_Process", "Execute SOAP operation spec for End_Flexible_Work_Arrangement", "qual operação do Workday para pedir férias?", "monta o envelope SOAP do Get_Event_Detail").
license: MIT
compatibility: Needs code execution and Node.js 18 or later; nothing to install. Reads only the files the person gives it; calls no Workday tenant. Not affiliated with Workday.
metadata:
  version: "0.3.6"
---

# workday-integration: the Workday operation for a use case, and what to send it

A catalog on this machine: `scripts/wws.mjs` indexes the **Operation Directory** and the **WSDLs** of the Workday Web
Services (SOAP), and the **OpenAPI specifications** of Workday's REST APIs, then answers with **what they say** — the operations, their descriptions, their fields, what is around
them. **You** read it and decide which operation fits, what the chain is, and what to send: the tool does not decide
for you, and what it ranks or chooses by default is a lead, not an answer. It **calls no tenant** and asks for no
credential; what it writes has only `{{placeholders}}`, never a person's data. Paths are relative to this skill's
folder; every command takes `--json` (read that) and `--index <folder>` (the index is in
`~/.cache/dna/workday-integration` by default, never in this skill). Not affiliated with Workday.

## 1. The index first

```
node scripts/wws.mjs status --json
```

Nothing indexed: say so, and offer the two ways —

```
node scripts/wws.mjs fetch --services hr --version v47.0     # downloads from Workday Community: uses the network
node scripts/wws.mjs ingest <files or folders>               # what the person already has
```

`fetch` downloads the Operation Directory page and the WSDLs of the HR services (or `--services A,B`, `all`) and
indexes them; `fetch --rest` the REST specifications too (the latest version of each HR service); run it only when the
person agrees to go to the network. `ingest` takes the directory page (`.html`, or
its text as `.txt`) and the `<Service>.wsdl` (and `.xsd`) files. To try the commands without real files, `examples/`
has synthetic ones (made-up fields: never quote them as Workday's).

## 2. Find, check, then write

1. **Translate first.** Put the person's words into Workday's English terms yourself — «pedir trabalho flexível» is
   «flexible work arrangement», «férias» is «time off», «aprovar» is «approve business process». Try two or three
   phrasings when the first finds little.
2. **Search**: `search "<Workday's words>" --json`. Each result has its verb (Add, End, Get, Approve…) and says what
   matched and where (the operation's name, Workday's description, its fields); an operation whose name is your words
   comes first and says so. Beyond that the order is bm25, nothing more: read the descriptions and pick yourself — an
   `Import_` operation is the batch version of the one without it. `--scope all` beyond HR; `--expand` adds a Portuguese synonym list when you have nothing better.
3. **See what is around it**: `related <Operation> --json` — the business process Workday's description names, the
   operations on the same noun (Add_, End_, Get_…), whether a Get_ for it exists **among what is indexed**, and the
   operations on business process events (approve, deny, send back, cancel, rescind, the event's detail, a worker's
   event history), each with Workday's own description. From these, you work out the chain; say which steps you
   inferred.
4. **Check before you state anything**: `show <Operation> --json` (depth 3–4; `--path A/B` to go down a big request,
   `--response` for what comes back; a tree too big comes cut, with `cut` saying to which depth and where to go down). To browse: `operations <Service>` (all of a service, `--filter word`),
   `type <Type>` (a type's fields), `where <Element or Type>` (which operations carry a field, by which path). A field,
   an ID type or a cardinality you name must be one `show`, `type` or `where` showed you.
5. **Write**, then read its **decisions**:
   - Copilot Studio: `copilot <Operation> --json` → `parameters`, `inputs`, `power_fx` (the requestBody — the
     operation's element alone, as the connector takes it; `--envelope` only if asked for the whole envelope),
     `response.read_paths`; `--include A/B/C` for an optional field. To read values back (a balance, a date, a name),
     name them: `--read <path>` (repeatable; paths as `show --response` gives them) — checked, with the connector's
     path, an ESS-style XPath, the value's type, and whether it repeats (one per plan, per event…); without `--read`,
     the spec reads the references the response returns.
   - Microsoft's Employee Self-Service agent: `ess <Operation>` writes a template of the ESS Workday pack
     (`workdayEntityConfigurationTemplate`: the scenario, the request template with `{Placeholders}`, the
     `extractPath`s — the fields of `--read`, or the references).
   - A test in SoapUI or Postman: `envelope <Operation> --wsse` (the whole envelope, the WS-Security header with
     placeholders).

   Every one of them lists its `decisions`: the **ID type** of each reference among its options (a default: WID for
   an event, Employee_ID for a person), the **alternative kept** in a choice (the first, by default), an **optional
   container** taken in because it holds required fields. Decide each for the use case and change it —
   `--id-type Worker_Reference=WID`, `--choose Job_Reference` — and tell the person the ones that matter.

### SOAP or REST

The search gives both, each result with `api: soap|rest` (a REST one: `GET common/v1 /workers/{ID}/timeOffPlans`).
Weigh them for the use case and say why you chose one:

- REST: `rest <METHOD> <path>` shows the endpoint — its parameters (what each ID accepts: a WID, a Reference ID such as
  `Employee_ID=…`, or `me` for the signed-in person), its body and response, and **the security domains and scope
  Workday's description names** — and the business process types that secure it — (facts: say them); the description
  whole, which may hold a value the request needs (the WID of the Submitted action); `--field body.a` for one part of
  a tree cut to fit. `copilot-rest <METHOD> <path>` writes the spec of the connector's
  **Execute REST request (Preview)**: `relativePath` with `{tenant}`, the body in JSON with placeholders, the Power Fx;
  decide each ID's form (`--id-form ID=me`), the optional query parameters — paging: `limit`, `offset` — and body fields
  (`--include limit`, `--include a.b`), what to read (`--read data[].id`, as `rest` shows the path; a value, not an object: `data[].unit.id`).
  The Power Fx writes each value with `JSON()` (escaped text, a number with a point, a date as yyyy-mm-dd), and the body
  template writes a number or a boolean without quotes; an optional input left blank goes as `null`, or is left out
  when named in `--omit-if-blank a.b` (MCP `omit_if_blank`: the Power Fx writes it with `If(IsBlank(…))`). A value that never
  changes — the WID of the Submitted action the description gives — goes in as a fixed value
  (`--value businessProcessParameters.action.id=<WID>`, MCP `values`), not an input. Show the body as the spec's
  `body_template` gives it; do not write it again by hand. The
  action sends no headers: a header the endpoint takes is said in the notes. It needs an OAuth 2.0 connection with the
  REST base URL, and runs as the signed-in user; a write has no idempotency key.
- `connector` lists the connector's ready-made actions (Get my worker profile, Get worker inbox tasks, Get worker
  direct reports, Transfer employee…), from Microsoft's documentation: one of them may do the job with no request to
  write. Each with the REST endpoint it likely calls (inferred: say it as likely); `connector <action>` gives one in
  full — Microsoft's words for each parameter, what it returns, and what the page does not say (which form of worker
  ID `workerID` takes: do not assume `me`).

`✗ … not found` (exit 2): say the name is not in the catalog and show the closest ones it lists. `No WSDL ingested for
<Service>` (exit 3): the operation is known only from the directory — give the person the command it prints; do not
write fields for it.

## 3. What to always say

- **Identity**: self-service and approval run **as the user** — a per-user OAuth connection (Microsoft Entra ID
  Integrated, as Microsoft's Employee Self-Service setup uses) — never as an integration system user, or Workday's
  «self» rules and «no approving your own request» stop seeing the real person. As the user, the employees' security
  group needs the domain's Integration Permissions in Workday; without them the answer is «Task not authorized».
- **Sensitive data**: say what a response may carry about a person (the «sensitive» notes — pay, events, comments and
  reasons); ask for the smallest response group that answers; in Copilot Studio turn on **Secure
  inputs and Secure outputs** and give the agent back only the fields it uses, never the raw XML.
- Every note has a `kind` and a `source`: **schema** (Workday's WSDLs show it; its `evidence` names the fields),
  **description** (Workday's own words), **inferred** (a deduction: check it before saying it), **sensitive** (what a
  response may carry about a person), **tenant** (not in the schema: say it as a question for the tenant). Connector
  notes cite Microsoft's documentation. Say an inferred note as «likely», never as a fact.
- Connector actions outside SOAP (REST, Preview: the worker's profile, the inbox tasks…) are not in the WSDLs: if you
  suggest one, say to check it exists in the person's Workday connector.

## 4. Deliver

The operation chain in a few lines (what runs, as whom, in which service), saying what came from the WSDLs and what
you inferred; then what was asked — the spec, the envelope, the fields — as the command wrote it, with the decisions
you kept or changed; and one sentence on what to confirm in the tenant.

## Never

- Never invent a field, an element or an ID type: if the WSDL of that service is not indexed, say so.
- Never present the search's order or a default decision as the answer: check it, and say what you decided.
- Never call a tenant, ask for a password or a token, or put a person's data in an envelope or a spec.
- Never present a synthetic example's fields as Workday's, nor copy Workday's WSDLs or directory into a repository.
