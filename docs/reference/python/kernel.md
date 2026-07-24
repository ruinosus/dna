# Kernel &amp; Runtime

The `Kernel` is the mediator that connects the five ports and the hook
registry. `Runtime` is a thin convenience wrapper that owns a kernel plus an
event loop for host code that wants a batteries-included entry point.

## Kernel

::: dna.kernel.Kernel
    options:
      show_root_heading: true
      show_source: false
      members_order: source
      docstring_section_style: table
      filters:
        - "!^_"

## Runtime

::: dna.kernel.boot.runtime.Runtime
    options:
      show_root_heading: true
      show_source: false
      filters:
        - "!^_"
