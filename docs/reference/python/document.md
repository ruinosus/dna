# Document &amp; ManifestInstance

`Document` is the universal wrapper for every manifest document —
`doc.kind`, `doc.name`, `doc.spec`, `doc.metadata`, `doc.typed`,
`doc.origin`. `ManifestInstance` is the **blessed query surface**: the one
documented read API (`all`, `one`, `root`, `default_agent`, `find_agent`,
`build_prompt`, `resolve`) that the guides and examples teach.

## Document

::: dna.kernel.document.Document
    options:
      show_root_heading: true
      show_source: false
      filters:
        - "!^_"

## ManifestInstance

::: dna.kernel.instance.ManifestInstance
    options:
      show_root_heading: true
      show_source: false
      members_order: source
      docstring_section_style: table
      filters:
        - "!^_"
