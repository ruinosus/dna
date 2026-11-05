---
name: workday-integration
description: Finds which Workday Web Service (SOAP) operation does what someone wants, and writes what an integration needs from it — the request and response with every field, a SOAP envelope with {{placeholders}}, and the spec of the Copilot Studio Workday connector's «Execute SOAP operation» (typed inputs, the XML template, the Power Fx of requestBody, what to read back) — from a local catalog of the Operation Directory text and the WSDLs the person has. In English or Portuguese. Use when someone designs or documents a Workday integration, a business process and its approvals, or a Copilot Studio action on Workday ("which Workday operation lets an employee request flexible work and the manager approve?", "build the SOAP envelope for Approve_Business_Process", "Execute SOAP operation spec for End_Flexible_Work_Arrangement", "qual operação do Workday para pedir férias?", "monta o envelope SOAP do Get_Event_Detail").
license: MIT
compatibility: Needs code execution and Node.js 18 or later; nothing to install. Reads only the files the person gives it; calls no Workday tenant. Not affiliated with Workday.
metadata:
  version: "0.1.0"
---

# workday-integration: the Workday operation for a use case, and what to send it

A catalog on this machine: `scripts/wws.mjs` indexes the **Operation Directory** text (copied from the Workday
Community page) and the **WSDLs** the person has, then answers. It **calls no tenant** and asks for no credential;
what it writes has only `{{placeholders}}`, never a person's data. Paths are relative to this skill's folder; every
command takes `--json` (read that) and `--index <folder>` (the index is in `~/.cache/dna/workday-integration` by
default, never in this skill). Not affiliated with Workday.

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

## 2. The order: trace → search → show → write

1. **Trace the use case**, in the person's words: `node scripts/wws.mjs trace "<the use case>" --json`. Read
   `primary`, `steps` (who the user is, the operation, the approver's inbox, the business process: approve, deny,
   send back, cancel, rescind), `related` and `notes` (a gap such as «no Get_ → read with RaaS» is there).
2. If the primary hit looks wrong, **search**: `search "<words>" --json`, with Workday's terms ("time off", "job
   change", "business process"); `--scope all` beyond HR.
3. **Show before writing**: `show <Operation> --json` (depth 3–4); for a big request go down with `--path A/B` rather
   than a deeper `--depth`; `--response` for what comes back. Check each reference's `@type` options (Employee_ID or
   WID).
4. **Write**:
   - Copilot Studio: `copilot <Operation> --json` → `parameters`, `inputs`, `power_fx` (the requestBody — the
     operation's element alone, as the connector takes it; `--envelope` only if asked for the whole envelope),
     `response.read_paths`; `--include A/B/C` for an optional field.
   - Microsoft's Employee Self-Service agent: `ess <Operation>` writes it as a template of the ESS Workday pack
     (`workdayEntityConfigurationTemplate`: the scenario, the request template with `{Placeholders}`, the
     `extractPath`s).
   - A test in SoapUI or Postman: `envelope <Operation> --wsse` (the whole envelope, the WS-Security header with
     placeholders).

In an envelope, `<!-- one of … — keep one -->` marks a choice (keep one alternative), and `<!-- optional in the
schema, but it holds the required fields -->` a container Workday makes optional that the request still needs.

`✗ … not found` (exit 2): say the name is not in the catalog and show the closest ones it lists. `No WSDL ingested for
<Service>` (exit 3): the operation is known only from the directory — give the person the command it prints; do not
write fields for it.

## 3. What to always say

- **Identity**: self-service and approval run **as the user** — a per-user OAuth connection (Microsoft Entra ID
  Integrated, as Microsoft's Employee Self-Service setup uses) — never as an integration system user, or Workday's
  «self» rules and «no approving your own request» stop seeing the real person. As the user, the employees' security
  group needs the domain's Integration Permissions in Workday; without them the answer is «Task not authorized».
- **Sensitive data**: say what a response may carry about a person (the notes that start with «Sensitive:» — pay,
  events, comments and reasons); ask for the smallest response group that answers; in Copilot Studio turn on **Secure
  inputs and Secure outputs** and give the agent back only the fields it uses, never the raw XML.
- A note marked **«to confirm in the tenant»** is not in the schema: say it as a question for the tenant, not a fact.

## 4. Deliver

The operation chain in a few lines (what runs, as whom, in which service), then what was asked — the spec, the
envelope, the fields — as the command wrote it, and one sentence on what to confirm in the tenant.

## Never

- Never invent a field, an element or an ID type: if the WSDL of that service is not indexed, say so.
- Never call a tenant, ask for a password or a token, or put a person's data in an envelope or a spec.
- Never present a synthetic example's fields as Workday's, nor copy Workday's WSDLs or directory into a repository.
