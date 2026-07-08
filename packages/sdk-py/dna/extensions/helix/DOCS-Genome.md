# Genome

A Module is the ROOT document of a helix manifest — every manifest has
exactly one (`is_root=true`). It lives at `.dna/<scope>/manifest.yaml` and
declares: the scope name, the default agent, the custom kinds the manifest
defines inline, the external dependencies to resolve (GitHub, HTTP, registry,
helix, local), and any layer policies for multi-tenant overlays
(`OPEN`, `RESTRICTED`, `LOCKED`).

**Not a prompt target.** The Module is metadata wiring: everything else the
kernel loads hangs off of it through `dep_filters`. A Module references
agents (`helix-agent`), skills (`agentskills-skill`), actors
(`helix-actor`), and use cases (`helix-usecase`).

**Layer resolution:** `kernel.resolve_layers(mi, {tenant: "team-b"})` merges
overlay documents from the layer directory into a new ManifestInstance,
respecting the policies declared in `spec.layers`. This is how multi-tenant
customization works without forking the base manifest.

Canonical api version: `github.com/ruinosus/dna/v1`.
