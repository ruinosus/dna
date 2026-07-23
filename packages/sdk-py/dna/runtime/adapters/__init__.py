"""dna.runtime.adapters — the in-tree RuntimePort implementations
(dna.runtime.port). Each adapter module is imported lazily, ONLY from
`dna.runtime.port._ensure_runtimes`, so `import dna.runtime.port` never pulls
a heavy framework dependency (langchain, agent-framework) that may not even
be installed (each backend lives behind its own optional extra)."""
