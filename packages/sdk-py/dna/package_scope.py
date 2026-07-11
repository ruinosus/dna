"""Resolve a DNA scope embedded as PACKAGE DATA (``s-scope-as-package-data``).

A DNA consumer that deploys an app used to make the scope travel by hand: a
brittle ``_DNA_BAKED_BASE_DIR = Path(__file__).resolve().parents[N] / ".dna"``
plus a manual ``COPY .dna`` in the Dockerfile. The image is the *app*, not the
repo — forget the COPY and the app boots with no scope (silently missing
skills). Both halves are fragile deploy glue that the SDK should own.

This module owns the deploy-safe alternative: resolve the scope from INSIDE
the installed package via :mod:`importlib.resources`. A ``pip install`` /
``uv sync`` carries the declared package data into a wheel and into a Docker
image, so :func:`anchor_scopes_root` resolves identically from a source
checkout, an installed wheel, and a container whose CWD is not the repo — with
zero path navigation and zero manual copy.

The single public entry point, :func:`anchor_scopes_root`, maps an *anchor*
(the package/module name that embeds the scope) to a concrete filesystem path
for its ``.dna`` scopes-root — the same ``base_dir`` a :class:`FilesystemSource`
takes. It is reused by both ``dna.load_prompts(scope, anchor=...)`` and the
``pkg://`` source scheme.

Read-only by nature: package data is composition input, never a write target
(it may live in a zip/wheel). To WRITE a scope, use a filesystem or Postgres
source. Non-filesystem-backed resources (a package imported from a zip) fail
loud here rather than silently extracting to a temp dir that outlives its
context — the deploy story is "installed on disk", which pip/uv always give.
"""
from __future__ import annotations

import os

__all__ = ["anchor_scopes_root", "PackageScopeNotFound", "DEFAULT_SUBPATH"]

#: The conventional sub-directory a package embeds its scopes under (matches
#: the repo's own ``.dna/<scope>/`` layout).
DEFAULT_SUBPATH = ".dna"


class PackageScopeNotFound(ValueError):
    """Raised when an ``anchor`` package / subpath can't be resolved to a
    real on-disk scopes-root directory."""


def anchor_scopes_root(anchor: str, subpath: str = DEFAULT_SUBPATH) -> str:
    """Resolve the ``.dna`` scopes-root embedded in package ``anchor``.

    ``anchor`` is an importable package/module name (e.g. ``"app"``);
    ``subpath`` is the scopes-root dir inside it (default ``".dna"``). Returns
    the concrete filesystem path of ``<anchor-package>/<subpath>`` — the
    ``base_dir`` a filesystem source consumes.

    Fails loud (:class:`PackageScopeNotFound`) when the package is not
    importable, the resource is not filesystem-backed (imported from a zip),
    or the subpath does not exist in the installed package — each with a
    didactic message pointing at the packaging fix.
    """
    from importlib.resources import files

    try:
        root = files(anchor)
    except (ModuleNotFoundError, ImportError) as exc:
        raise PackageScopeNotFound(
            f"anchor package {anchor!r} is not importable — it must be an "
            f"INSTALLED package that embeds the scope as package data "
            f"(pip/uv install it, and declare the scope files in its build "
            f"config, e.g. hatch force-include or setuptools package-data). "
            f"Original import error: {exc}"
        ) from exc
    except TypeError as exc:  # not a package/str importlib.resources accepts
        raise PackageScopeNotFound(
            f"anchor {anchor!r} is not a valid package name for "
            f"importlib.resources.files(). Pass the installed package that "
            f"embeds the scope (e.g. anchor='app')."
        ) from exc

    resource = root.joinpath(subpath) if subpath else root

    try:
        fs_path = os.fspath(resource)  # concrete path iff filesystem-backed
    except TypeError as exc:
        raise PackageScopeNotFound(
            f"package data for {anchor!r} is not filesystem-backed (the "
            f"package looks zip-imported). A DNA scope embedded as package "
            f"data must be installed UNZIPPED on disk — which pip and uv do "
            f"by default. Reinstall the package normally (not as a zipped "
            f"egg / zipapp). Got resource: {resource!r}."
        ) from exc

    if not os.path.isdir(fs_path):
        raise PackageScopeNotFound(
            f"anchor {anchor!r} is installed, but its scopes-root "
            f"{subpath!r} was not found at {fs_path!r}. Declare the scope "
            f"files as package data so they ship in the wheel/image "
            f"(e.g. [tool.hatch.build.targets.wheel.force-include] "
            f'"{anchor}/{subpath}" = "{anchor}/{subpath}", or setuptools '
            f"package_data / MANIFEST.in). See the guide "
            f'"Shipping a scope with your app".'
        )

    return fs_path
