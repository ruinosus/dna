"""Phase 3b ch1 (i-112) — the Catalog tier as a set of resolution scopes.

``resolve_catalog_scopes`` is the PURE transform from "what's installed for a
tenant" → the ordered list of ``(scope, target_tenant)`` tuples that the query
engine / resolver splice in BETWEEN the Local and Base passes (precedence
``Local > Catalog > Base``).

The Catalog set for a tenant = UNION of:
  - **mandatory platform packages** — ``owner_tenant is None ∧ spec.mandatory``;
    universal (installed for every tenant), resolved at ``tenant=None``.
  - **the tenant's lockfile installs** — each ``GenomeEntry`` maps to its
    package scope (``source.split("/", 1)[-1]``) and the tenant the artifact
    landed in (``target_tenant or None``).

Deduped by scope (a scope that is BOTH mandatory and lock-installed resolves
once, mandatory winning → ``tenant=None``), with any scope in ``exclude``
dropped (the scope being resolved + the base/``_lib`` scope), then sorted
by scope for deterministic conflict resolution downstream.

This is the 3b twin of 3a's ``build_installed_capabilities`` — a DIFFERENT pure
transform of the same "what's installed" data (3a → display capabilities, takes
``installed_sources: list[str]``; 3b → ``(scope, tenant)`` tuples for injection,
takes the ``GenomeEntry`` list so it can read ``target_tenant``). The two are
intentionally kept separate (DRY note in the plan).
"""
from __future__ import annotations

from typing import Any, Iterable


def _scope_of(source: str) -> str:
    """``<owner>/<name>`` → scope (the scope IS the package name)."""
    return source.split("/", 1)[-1] if "/" in source else source


def resolve_catalog_scopes(
    all_packages: Iterable[Any],
    installed_sources: Iterable[Any],
    *,
    exclude: set[str],
) -> list[tuple[str, str | None]]:
    """Pure resolver of the ordered Catalog scope set for a tenant.

    Args:
        all_packages: every ``Genome`` doc across all scopes — each exposes
            ``.name`` (the scope) and ``.spec`` (dict with ``owner_tenant`` /
            ``mandatory``).
        installed_sources: the tenant lockfile's ``GenomeEntry`` list — each
            exposes ``.source`` (``<owner>/<name>``) and ``.target_tenant``.
        exclude: scopes to drop (the scope being resolved + the base scope).

    Returns:
        ``[(scope, target_tenant), ...]`` sorted by scope, deduped (mandatory
        wins → ``target_tenant=None``).
    """
    # scope → target_tenant. We process mandatory platform packages FIRST so a
    # later lock entry for the same scope does not clobber its tenant=None.
    out: dict[str, str | None] = {}

    for pkg in all_packages:
        spec = pkg.spec if isinstance(getattr(pkg, "spec", None), dict) else {}
        is_mandatory = (
            spec.get("owner_tenant") is None and bool(spec.get("mandatory"))
        )
        if not is_mandatory:
            continue
        scope = pkg.name
        if scope in exclude:
            continue
        out[scope] = None

    for entry in installed_sources:
        source = getattr(entry, "source", None)
        if not source:
            continue
        scope = _scope_of(source)
        if scope in exclude:
            continue
        if scope in out:
            # Mandatory already claimed this scope → keep tenant=None.
            continue
        target_tenant = getattr(entry, "target_tenant", "") or None
        out[scope] = target_tenant

    return [(scope, out[scope]) for scope in sorted(out)]
