"""dna.kernel.lock — locking (core + manager + module-lock), grouped.

`core` was the old top-level `lock` module; re-exported here so `dna.kernel.lock`
(now the package) keeps exposing the same public symbols — consumers of
`dna.kernel.lock` are unchanged.
"""
from .core import *  # noqa: F401,F403
