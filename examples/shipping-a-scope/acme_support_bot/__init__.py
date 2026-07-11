"""acme_support_bot — a minimal app that ships a DNA scope as PACKAGE DATA.

The ``support`` scope lives at ``acme_support_bot/.dna/support`` and is declared
as package data in ``pyproject.toml`` (hatch ``force-include``), so a
``pip install`` / ``uv build`` carries it into the wheel and into a Docker
image. The app resolves it WITHOUT path navigation:

    from dna import load_prompts

    prompts = load_prompts("support", anchor="acme_support_bot")
    TRIAGE = prompts["triage"]        # composed, clean, or raises

``anchor="acme_support_bot"`` resolves the scope from inside THIS installed
package (via ``importlib.resources``) — identical from a source checkout, an
installed wheel, or a container whose CWD is not the repo. Contrast the old
brittle pattern this replaces::

    # DON'T: fragile path navigation + a manual `COPY .dna` in the Dockerfile
    _BAKED = Path(__file__).resolve().parents[2] / ".dna"
    mi = Kernel.quick("support", base_dir=str(_BAKED))
"""
from __future__ import annotations

from dna import load_prompts

__all__ = ["triage_prompt"]


def triage_prompt() -> str:
    """The composed system prompt for the ``triage`` agent of the embedded
    ``support`` scope — resolved via package data, no path navigation."""
    return load_prompts("support", anchor="acme_support_bot")["triage"]
