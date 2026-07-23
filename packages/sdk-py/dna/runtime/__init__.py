"""dna.runtime — the high-level DNA copilot runtime (optional extra
`dna-sdk[runtime]`). `build_copilot(...)` assembles a ready LangGraph copilot
from a DNA def + host hooks. Heavy deps (langchain/langgraph) are imported
INSIDE the functions so importing dna core never pulls them.

`dna.runtime.port` layers a declarative RuntimePort over this: a registry of
framework adapters (LangChain, MAF, ...) each turning a neutral EmitContext
into a servable AG-UI app. `build_runtime` is the port-based counterpart of
`build_copilot` — it composes the full EmitContext and dispatches to the
adapter `serving.framework` names (default `"langchain"`); `build_copilot` is
now a back-compat shim over it."""

from dna.runtime.builder import build_copilot, build_runtime
from dna.runtime.port import (
    AGUIApp,
    RuntimeHooks,
    RuntimePort,
    UnknownRuntime,
    available_runtimes,
    get_runtime,
    register_runtime,
)

__all__ = [
    "build_copilot",
    "build_runtime",
    "AGUIApp",
    "RuntimeHooks",
    "RuntimePort",
    "UnknownRuntime",
    "available_runtimes",
    "get_runtime",
    "register_runtime",
]
