"""dna.kernel.kinds — grouped (was flat kind_base, kind_definition_schema, kind_registry))."""

# The PROPOSED trait vocabulary (slice 3 of spec-kind-taxonomia-o-que-eu-sou).
# Imported here, and only here, so the names reach `dna kind traits` /
# `describe_traits()` wherever the trait registry does — and so rejecting the
# proposal is deleting one file and this one line. Kept last and import-only:
# `vocabulary` imports `traits`, `traits` imports nothing from this package.
from dna.kernel.kinds import vocabulary as _proposed_vocabulary  # noqa: F401
