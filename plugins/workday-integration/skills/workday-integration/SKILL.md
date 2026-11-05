---
name: workday-integration
description: Finds which Workday Web Service (SOAP) operation does what someone wants, and writes what an integration needs from it — the request and response with every field, a SOAP envelope with {{placeholders}}, and the spec of the Copilot Studio Workday connector's «Execute SOAP operation» (typed inputs, the XML template, the Power Fx of requestBody, what to read back) — from a local catalog of the Operation Directory text and the WSDLs the person has. In English or Portuguese. Use when someone designs or documents a Workday integration, a business process and its approvals, or a Copilot Studio action on Workday ("which Workday operation lets an employee request flexible work and the manager approve?", "build the SOAP envelope for Approve_Business_Process", "Execute SOAP operation spec for End_Flexible_Work_Arrangement", "qual operação do Workday para pedir férias?", "monta o envelope SOAP do Get_Event_Detail").
license: MIT
compatibility: Needs code execution and Node.js 18 or later; nothing to install. Reads only the files the person gives it; calls no Workday tenant. Not affiliated with Workday.
metadata:
  version: "0.2.1"
---

# workday-integration: the Workday operation for a use case, and what to send it

A catalog on this machine: `scripts/wws.mjs` indexes the **Operation Directory** and the **WSDLs** of the Workday Web
Services, then answers with **what the WSDLs say** — the operations, their descriptions, their fields, what is around
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
indexes them; run it only when the person agrees to go to the network. `ingest` takes the directory page (`.html`, or
its text as `.txt`) and the `<Service>.wsdl` (and `.xsd`) files. To try the commands without real files, `examples/`
has synthetic ones (made-up fields: never quote them as Workday's).

## 2. Find, check, then write

1. **Translate first.** Put the person's words into Workday's English terms yourself — «pedir trabalho flexível» is
   «flexible work arrangement», «férias» is «time off», «aprovar» is «approve business process». Try two or three
   phrasings when the first finds little.
2. **Search**: `search "<Workday's words>" --json`. Each result says what matched and where (the operation's name,
   Workday's description, its fields). The order is bm25 over those words, nothing more: read the descriptions and
   pick yourself. `--scope all` beyond HR; `--expand` adds a Portuguese synonym list when you have nothing better.
3. **See what is around it**: `related <Operation> --json` — the business process Workday's description names, the
   operations on the same noun (Add_, End_, Get_…), whether a Get_ for it exists **among what is indexed**, and the
   operations on business process events (approve, deny, send back, cancel, rescind, the event's detail, a worker's
   event history), each with Workday's own description. From these, you work out the chain; say which steps you
   inferred.
4. **Check before you state anything**: `show <Operation> --json` (depth 3–4; `--path A/B` to go down a big request,
   `--response` for what comes back). To browse: `operations <Service>` (all of a service, `--filter word`),
   `type <Type>` (a type's fields), `where <Element or Type>` (which operations carry a field, by which path). A field,
   an ID type or a cardinality you name must be one `show`, `type` or `where` showed you.
5. **Write**, then read its **decisions**:
   - Copilot Studio: `copilot <Operation> --json` → `parameters`, `inputs`, `power_fx` (the requestBody — the
     operation's element alone, as the connector takes it; `--envelope` only if asked for the whole envelope),
     `response.read_paths`; `--include A/B/C` for an optional field.
   - Microsoft's Employee Self-Service agent: `ess <Operation>` writes a template of the ESS Workday pack
     (`workdayEntityConfigurationTemplate`: the scenario, the request template with `{Placeholders}`, the
     `extractPath`s).
   - A test in SoapUI or Postman: `envelope <Operation> --wsse` (the whole envelope, the WS-Security header with
     placeholders).

   Every one of them lists its `decisions`: the **ID type** of each reference among its options (a default: WID for
   an event, Employee_ID for a person), the **alternative kept** in a choice (the first, by default), an **optional
   container** taken in because it holds required fields. Decide each for the use case and change it —
   `--id-type Worker_Reference=WID`, `--choose Job_Reference` — and tell the person the ones that matter.

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
