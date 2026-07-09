# Testing &amp; conformance kit

`dna.testing` ships the SDK's **port-adapter compliance suites** — in the
spirit of the Python DB-API compliance suite. An adapter author hands a
*factory* for their adapter and gets back the battery of cases every
conforming implementation must pass. See
[Running the conformance kit](../../getting-started/conformance-kit.md) for a
walkthrough.

::: dna.testing
    options:
      show_root_heading: true
      show_source: false
      members_order: source
      filters:
        - "!^_"
