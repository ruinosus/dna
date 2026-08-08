"""Entry point for `worker`.

⚠️ This file is a SKELETON, on purpose. The template owns the wiring — the
container, the bicep module, the compose fragment, the version floor — and
stops here, where your reasoning starts. Grow it freely.

The trade you accepted by generating this: a future `dna solution update` that
touches a line you also touched produces a merge conflict, and adjacent edits
collapse into one coarse block. That is the price of owning real code instead
of depending on a library. The wiring files below `wiring/` are the part you
are NOT expected to edit, and they are the part that merges clean.
"""
from __future__ import annotations

# ⭐ `ingress: none` — worker does NOT serve. No HOST, no PORT, no
# ASGI app to build: nothing calls in, so `main()` below IS the work, and what
# triggers it (a queue, a schedule, a KEDA scaler) is yours. The wiring says
# the same thing — no ingress block in the bicep, no published port in the
# compose fragment, and no `port` in the answers file.

# The NAME of the identity authority, decided at generation time. What it means
# operationally — issuer, audience, JWKS — is configuration this process reads
# at boot, never a literal baked in here.
IDENTITY = "none"


def main() -> None:
    """The work this process does.

    Replace the body. Nothing below this line is template-owned.
    """
    raise NotImplementedError("worker: main() is yours to write")


if __name__ == "__main__":
    main()
