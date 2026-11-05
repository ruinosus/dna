# Changelog

## 0.2.2 — 2026-11-05

Each note shows what proves it, for the agent too: besides a schema note's `evidence`, the operations it says are
absent (`absent_operations`), the fields it says the request lacks (`absent_fields`), and a description note's
`quote` of Workday's words; the CLI prints them beside the note. The tenant note reads as one sentence.

## 0.2.1 — 2026-11-05

**Each note says what it is.** A note's `kind` is one of: `schema` (Workday's WSDLs show it, and its `evidence`
names the fields), `description` (Workday's own words, quoted), `inferred` (a deduction: check it), `sensitive`
(what a response may carry about a person), `tenant` (not in the schema); the connector's notes are `documentation`
(linked) or `practice`. Two notes that said «checked against the WSDLs» were deductions — the questionnaire step
that lands in the inbox, and changing an arrangement by ending it — and are now `inferred`; a field name that was not
exact (Company_Insider → Company_Insider_Data) is fixed. `tools/check-notes.mjs` checks every note against an index
of Workday's real WSDLs (29/29 on v47.0).

## 0.2.0 — 2026-11-05

**The facts are the WSDL's; the decisions are the agent's.** The catalog no longer concludes for the agent: it hands
over what the WSDLs say, says what it chose by default, and lets the agent change it.

- `search` takes the words as they are (the agent writes Workday's terms), and each result says what matched and
  where; `--expand` keeps the Portuguese synonym list.
- `trace` is gone: `related <Operation>` gives the facts around an operation — the business process Workday's
  description names, the operations on the same noun, whether a `Get_` exists among what is indexed, the operations on
  business process events with Workday's descriptions. No «primary», no fixed steps, no connector action it could not
  check.
- New, to browse without reading XML: `operations <Service>`, `type <Type>`, `where <Element or Type>`.
- `envelope`, `copilot` and `ess` list their `decisions` (an ID type among its options, a choice's alternative, an
  optional container taken in) and take `--id-type Ref=Type` and `--choose Alt`; a wrong one is refused with the
  options.
- Each note says its source: curated (checked by hand, dated), Microsoft's documentation (linked), or to confirm in the
  tenant.
- MCP: `wws_related_operations`, `wws_list_operations`, `wws_get_type`, `wws_find_element`; `id_types` and `choose`
  on the envelope, spec and template tools; `wws_trace_use_case` is gone.

## 0.1.1 — 2026-11-05

The search understands the short forms of the verbs people use — «pede», «peço», «aprova», «cancela», «encerra»… —
so «colaborador pede trabalho flexível e o gestor aprova» finds `Add_Flexible_Work_Arrangement` first (it found the
`End_` one: the inflection rule reaches only words of 6 letters or more).

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
