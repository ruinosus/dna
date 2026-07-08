"""s-kind-alias-convention-fix — every registered Kind alias must follow the
`<owner>-<kind>` convention: an owner prefix + a hyphen (no bare names), all
lowercase, and globally unique. Bare names like ``tenant`` break the global-
uniqueness intent (the alias is what dep_filters / templates / cross-kind refs
key on — see CLAUDE.md "Mandatory Kind alias convention").

The convention is deliberately loose on the *kind* token (the registry uses both
kebab — ``sdlc-prompt-template`` — and collapsed — ``eval-evalcase`` — forms), so
this lint enforces only the invariants the whole registry actually upholds, not a
strict kebab formula (which would falsely flag ~33 idiomatic aliases).
"""
from __future__ import annotations

import re

from dna.kernel import Kernel

# owner prefix + at least one more hyphenated segment, lowercase alnum.
_ALIAS_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")


def _aliases() -> list[tuple[str, str]]:
    k = Kernel.auto()
    return [(getattr(kp, "alias", ""), getattr(kp, "kind", "")) for kp in k._kinds.values()]


def test_no_bare_or_malformed_aliases():
    bad = [
        f"{alias!r} (kind={kind})"
        for alias, kind in _aliases()
        if not _ALIAS_RE.match(alias)
    ]
    assert not bad, (
        "Kind aliases must be `<owner>-<kind>` (owner prefix, lowercase, no bare "
        "names):\n  " + "\n  ".join(bad)
    )


def test_aliases_are_globally_unique():
    aliases = [a for a, _ in _aliases()]
    dupes = sorted({a for a in aliases if aliases.count(a) > 1})
    assert not dupes, f"Duplicate Kind aliases (must be globally unique): {dupes}"


def test_known_violations_are_fixed():
    # The three the anti-pattern sweep flagged — locked in so they can't regress.
    by_kind = {kind: alias for alias, kind in _aliases()}
    assert by_kind.get("Tenant") == "tenant-tenant"          # was bare "tenant"
    assert by_kind.get("LayerPolicy") == "policy-layer-policy"  # was reversed "policy-layer"
