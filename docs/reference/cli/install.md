# `dna install`

Install bundles/Kinds from a repository into the local source.

URI is `github:owner/repo[/subdir][@ref]` (shallow clone) or
`local:<path>` (a directory on disk). The fetched tree is scanned with the kernel's
registered readers (Skill/Soul/AGENTS.md bundles, standalone YAML docs,
...); each detected document is validated and then written through
kernel.write_document, so every write guard runs.

Third-party manifests are UNTRUSTED DATA: schema validation is the first
defense (an invalid doc is rejected with the reason; the install
continues with the valid ones), the kernel's pre-save veto guards are
the second. Root Kinds (Genome) in the fetched tree are never installed.
Provenance lands in <scope>/installed.lock (origin pinned to the fetched
commit). See SECURITY.md for the threat model this implements.

Examples:


  dna install github:anthropics/skills/skills/pdf --scope market --dry-run
  dna install github:anthropics/skills/skills/pdf --scope market
  dna install local:../some-checkout/skills --scope playground --force

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna install --help`.

## `dna install`

Install bundles/Kinds from a repository into the local source.

URI is `github:owner/repo[/subdir][@ref]` (shallow clone) or
`local:<path>` (a directory on disk). The fetched tree is scanned with the kernel's
registered readers (Skill/Soul/AGENTS.md bundles, standalone YAML docs,
...); each detected document is validated and then written through
kernel.write_document, so every write guard runs.

Third-party manifests are UNTRUSTED DATA: schema validation is the first
defense (an invalid doc is rejected with the reason; the install
continues with the valid ones), the kernel's pre-save veto guards are
the second. Root Kinds (Genome) in the fetched tree are never installed.
Provenance lands in <scope>/installed.lock (origin pinned to the fetched
commit). See SECURITY.md for the threat model this implements.

Examples:


  dna install github:anthropics/skills/skills/pdf --scope market --dry-run
  dna install github:anthropics/skills/skills/pdf --scope market
  dna install local:../some-checkout/skills --scope playground --force

```text
dna install [OPTIONS] URI
```

**Arguments**

| Argument | Required |
| --- | --- |
| `URI` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--dry-run` | Print the install plan (what would be written where, what gets rejected and why) and stop — nothing is fetched into the source. |
| `--force` | Overwrite documents that already exist locally (default: skip them with a warning). |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable summary. |
| `--scope` | Target scope (default: derived from the URI — <owner>-<repo> for github:, the directory name for local:). Created with a minimal Genome when it does not exist yet. |

