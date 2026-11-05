# workday-integration (development)

The plugin is `plugins/workday-integration/`; its one-file CLI, `skills/workday-integration/scripts/wws.mjs`, is
built from `src/` (and saxes) by `tools/assets.mjs`. A port to Node of a Python catalog (an MCP server) of the Workday
Web Services: `schema` (WSDL/XSD, no network, no entities), `render` (trees, envelopes), `index` (JSON files, FTS5's
bm25 over the same columns and weights, Porter stems, PT/EN synonyms), `workflows` (trace, show, envelope, the Copilot
Studio spec) and `notes` (only what Workday's public schema shows; the rest «to confirm in the tenant»).

```
npm run assets -w dev/workday-integration/tools   # scripts/wws.mjs
npm run check -w dev/workday-integration/tools    # the checks, and the same answers as the Python port
npm run zip -w dev/workday-integration/tools      # dist/workday-integration.zip and -plugin.zip
```

`checks/golden.json` is what the Python port answered on the synthetic examples (`skills/…/examples/`): the check
asks the Node port for the same, the search with the same bm25 scores (ties in any order). Changed on purpose, and
checked on their own: the notes, a choice's comment (it names the alternatives), the Copilot Studio spec's requestBody
(the element alone by default), and two fixes seen on Workday's real WSDLs — the ID types of a reference are read
from xsd:appinfo, and an optional container that holds the required fields goes in the envelope. Its `fetch` reaches only Workday Community, never a tenant.

Never put a Workday WSDL, XSD or Operation Directory text in this repository, nor anything of a client.
