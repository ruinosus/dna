"""Internal YAML helpers — one seam that resolves the fastest *safe* loader.

PyYAML ships two implementations of the same grammar: a pure-Python
scanner/parser, and ``CSafeLoader``, a binding over libyaml. Both feed the
*same* Python ``SafeConstructor`` and ``Resolver``, so what changes is the
scanner/parser — not how a scalar becomes a value. Measured on this repo's
own corpus (789 YAML files) the C parser is **9-10x** faster, with an
identical result on every file.

``yaml.safe_load`` hardcodes the pure-Python loader, so the accelerated path
is invisible unless it is asked for explicitly. Rather than pass
``Loader=`` at every call site, every module that parses YAML goes through
this seam — the choice, and its fallback, are made once, here.

**Safe is not negotiable.** These helpers always resolve a *safe* loader.
Documents parsed by the runtime are author-supplied; a loader that can
construct arbitrary Python objects (``yaml.Loader``/``CLoader``/
``FullLoader``) would turn a stored document into a code-execution path.

**libyaml is optional.** The SDK is published as a pure-Python wheel and
installs on machines where libyaml was never compiled in. There, ``import
yaml`` simply exposes no ``CSafeLoader`` and this module falls back to the
pure-Python ``SafeLoader``: slower, byte-for-byte the same result, no
warning, no configuration.

Locked by ``tests/test_yaml_loader.py`` — including the fallback branch,
which is forced rather than assumed.
"""
from __future__ import annotations

from typing import IO, Any, Iterator

import yaml

try:  # pragma: no cover - the branch taken depends on the installed PyYAML
    from yaml import CSafeLoader as SafeLoader

    HAVE_LIBYAML = True
except ImportError:  # pragma: no cover - exercised by a forced-fallback test
    from yaml import SafeLoader  # type: ignore[assignment]

    HAVE_LIBYAML = False


__all__ = ["HAVE_LIBYAML", "SafeLoader", "safe_load", "safe_load_all"]


def safe_load(stream: str | bytes | IO[str] | IO[bytes]) -> Any:
    """``yaml.safe_load`` on the fastest safe loader available.

    Same contract as ``yaml.safe_load``: returns the single document (or
    ``None`` for an empty stream) and raises ``yaml.YAMLError`` on malformed
    input.
    """
    return yaml.load(stream, Loader=SafeLoader)


def safe_load_all(stream: str | bytes | IO[str] | IO[bytes]) -> Iterator[Any]:
    """``yaml.safe_load_all`` on the fastest safe loader available."""
    return yaml.load_all(stream, Loader=SafeLoader)
