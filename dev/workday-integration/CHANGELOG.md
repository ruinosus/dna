# Changelog

## 0.3.1 — 2026-11-05

- `copilot-rest` (MCP `wws_rest_action_spec`): `read` and `include` take a path as `rest` shows it (`data[].id`), and
  without the brackets (`data.id`) — before, the path the endpoint showed was refused.
- The query parameters: a required one is an input, in `relativePath` (`?asOf={{AsOf}}`); the optional ones left out
  are a decision (`optional_query`, with what Workday says of each — paging: `limit`, default 20, at most 100;
  `offset`), and `include` adds one by its name (`--include limit`). A number goes in the path as `EncodeUrl(Text(…))`.
  Before, the query parameters were left out with nothing said.

## 0.3.0 — 2026-11-05

**Workday's REST APIs beside the SOAP.**

- `fetch --rest` downloads Workday's REST specifications (OpenAPI 2.0) from Workday Community — the latest version of
  each HR service, or `--rest-services`, `--rest-all-versions`; their names are read from the directory page's script,
  and a page that changed is said, with `ingest` of the files as the way. `ingest` takes `.json` specifications too.
- `search` finds SOAP operations and REST endpoints together, each with `api: soap|rest` (a REST one as
  `GET common/v1 /workers/{ID}/timeOffPlans`, its domains with it); `--api` for one. A REST endpoint's name is its
  service and path.
- `rest <METHOD> <path>`: an endpoint — its parameters (what each ID accepts: a WID, a Reference ID, `me`), its body
  and response as trees ($ref and allOf resolved), and the security domains and scope Workday's description names, as
  facts.
- `copilot-rest <METHOD> <path>`: the spec of the connector's Execute REST request (Preview) — `relativePath` with
  `{tenant}`, the JSON body with placeholders (the required fields, `--include`), the Power Fx of both, what to read
  (`--read` dotted paths), and its decisions (`--id-form ID=me`, the optional fields left out).
- `connector`: the connector's actions as Microsoft documents them (SOAP, REST, RaaS and the ready-made ones).
- MCP: `wws_get_rest_endpoint`, `wws_rest_action_spec`, `wws_list_connector_actions`; `api` on the search.
- `status` shows the REST indexed. The bench has three REST cases (15/15 in the search); `check-real.mjs` checks a
  known endpoint's domains and the REST answers' sizes. A synthetic REST specification, written from scratch, for the
  checks.

## 0.2.4 — 2026-11-05

**Read the answer, and measure on real cases.**

- `copilot` and `ess` take `--read <path>` (MCP: `read`): the response's fields to read back — a balance, a date, a
  reference — checked against the tree, each with the connector's path, an XPath with `local-name()` (as Microsoft's
  ESS templates), its type, and whether it repeats; a container or a path that is not there is refused with the fields
  to pick. Without it, the references, said as the default.
- `search`: each result has its verb (Add, End, Get…); an operation whose name is the words (in any order) comes
  first, one that holds them all comes ahead (the fewer other words, the closer), and `matched` says so. `--expand`
  unchanged.
- `tools/bench-real.mjs` and `bench/cases.json`: 12 common HR use cases on Workday's real WSDLs — the search with
  Workday's terms (12/12 in the first three; 9/12 before the name rule), and with `--agent` Claude with the plugin
  from a request in Portuguese (12/12).

## 0.2.3 — 2026-11-05

**Answers that fit.** VS Code's Copilot cut the 0.2.2 Copilot Studio spec (11 KB) before its Power Fx. Now:

- The MCP answers in compact JSON.
- The spec puts the essential first — `power_fx`, `xml_template`, `inputs`, `decisions` — and the notes last; its
  request body has no XML comment (they were going to Workday); of the curated notes it keeps the ones to act on
  (`tenant`, `sensitive`) and says where the rest is (`related`, `show`).
- The source of each kind of note, and the rule behind each decision, are said once (`sources`, `decision_rules`), not
  on every note and decision; a reference's ID options list the first 12 and how many there are.
- `show` cuts a tree too big for an answer to a lower depth (about 8 KB), and says so and how to go down (`cut`); a
  field's documentation stops at 160 characters, an input's at 100.
- `tools/check-real.mjs` (was `check-notes.mjs`) also checks, on Workday's real WSDLs, that every answer of seven
  operations is within 9 KB (the spec of Add_Flexible_Work_Arrangement: 6.3 KB).

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
