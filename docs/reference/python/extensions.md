# Extensions

Extensions register Kinds with the kernel. `Kernel.auto()` discovers and
loads every installed extension via entry points
(`[project.entry-points."dna.extensions"]`); host code can also load
one explicitly with `kernel.load(ext)`. Each class below registers one or
more `KindPort`s — see the [Kinds reference](../kinds/index.md) for the Kinds
they contribute.

## Behaviour Kinds

::: dna.extensions.agentskills.AgentSkillsExtension
    options:
      show_root_heading: true
      show_source: false

::: dna.extensions.soulspec.SoulSpecExtension
    options:
      show_root_heading: true
      show_source: false

::: dna.extensions.agentsmd.AgentsMdExtension
    options:
      show_root_heading: true
      show_source: false

::: dna.extensions.guardrails.GuardrailExtension
    options:
      show_root_heading: true
      show_source: false

::: dna.extensions.safety.SafetyPolicyExtension
    options:
      show_root_heading: true
      show_source: false

::: dna.extensions.recognizer.RecognizerExtension
    options:
      show_root_heading: true
      show_source: false

::: dna.extensions.hooks.HookExtension
    options:
      show_root_heading: true
      show_source: false

## Kind machinery

::: dna.extensions.kinddef.KindDefinitionExtension
    options:
      show_root_heading: true
      show_source: false

## Lifecycle &amp; knowledge Kinds

::: dna.extensions.sdlc.SdlcExtension
    options:
      show_root_heading: true
      show_source: false

::: dna.extensions.research.ResearchExtension
    options:
      show_root_heading: true
      show_source: false

::: dna.extensions.evidence.EvidenceExtension
    options:
      show_root_heading: true
      show_source: false

::: dna.extensions.collab.CollabExtension
    options:
      show_root_heading: true
      show_source: false

::: dna.extensions.federation.FederationExtension
    options:
      show_root_heading: true
      show_source: false
