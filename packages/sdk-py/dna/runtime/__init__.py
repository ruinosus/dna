"""dna.runtime — the high-level DNA copilot runtime (optional extra
`dna-sdk[runtime]`). `build_copilot(...)` assembles a ready LangGraph copilot
from a DNA def + host hooks. Heavy deps (langchain/langgraph) are imported
INSIDE the functions so importing dna core never pulls them."""

from dna.runtime.builder import build_copilot

__all__ = ["build_copilot"]
