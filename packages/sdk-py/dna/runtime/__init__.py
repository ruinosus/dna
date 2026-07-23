"""dna.runtime — the high-level DNA copilot runtime (optional extra
`dna-sdk[runtime]`). `build_copilot(...)` assembles a ready LangGraph copilot
from a DNA def + host hooks. Heavy deps (langchain/langgraph) are imported
INSIDE the functions so importing dna core never pulls them.

`dna.runtime.port` layers a declarative RuntimePort over this: a registry of
framework adapters (LangChain, MAF, ...) each turning a neutral EmitContext
into a servable AG-UI app. `build_runtime` (the port-based counterpart of
`build_copilot`) will dispatch through it once the adapter chain lands."""

from dna.runtime.builder import build_copilot
from dna.runtime.port import (
    AGUIApp,
    RuntimeHooks,
    RuntimePort,
    UnknownRuntime,
    available_runtimes,
    get_runtime,
    register_runtime,
)

# build_runtime: forward reference — lands in Task 2 (dna.runtime.builder),
# once the LangChain adapter exists for it to dispatch to. Not imported yet:
# the module/function doesn't exist until then.
__all__ = [
    "build_copilot",
    "AGUIApp",
    "RuntimeHooks",
    "RuntimePort",
    "UnknownRuntime",
    "available_runtimes",
    "get_runtime",
    "register_runtime",
]
