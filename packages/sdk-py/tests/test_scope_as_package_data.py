"""Scope-as-package-data — the deploy dogfood (``s-scope-as-package-data`` +
``s-pkg-source-scheme``).

The bug this reproduces: a DNA consumer that deploys an app used to make its
scope travel by hand — ``Path(__file__).resolve().parents[N] / ".dna"`` plus a
manual ``COPY .dna`` in the Dockerfile. The image is the *app*, not the repo;
CWD is not the repo; forget the COPY and the app boots with NO scope.

The heart of this suite is :func:`test_resolves_from_installed_package_diff_cwd`:
it materializes the example package at an install location UNRELATED to the repo
(exactly what a wheel install / Docker layer does — files unpacked onto
``sys.path``), then runs a subprocess from an EMPTY CWD and proves the scope
resolves via ``importlib.resources`` — no path navigation, no ``.dna`` in the
CWD. The negative control proves the OLD path-based resolution fails there.

``test_wheel_ships_the_scope`` closes the loop for real: it builds the example
wheel and asserts the embedded scope is inside it (proving the hatch
``force-include`` config actually ships the data). It needs the build backend
from PyPI, so it is marked ``requires_network`` and auto-skips in offline CI.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

# examples/shipping-a-scope/ — the example app that embeds the ``support`` scope.
_EXAMPLE = (
    Path(__file__).resolve().parents[3]
    / "examples"
    / "shipping-a-scope"
)
_PKG_DIR = _EXAMPLE / "acme_support_bot"


def _run_from(cwd: Path, pythonpath: Path, code: str) -> subprocess.CompletedProcess:
    """Run ``code`` in a subprocess with ``cwd`` + a single-entry PYTHONPATH.

    The subprocess uses THIS interpreter (the venv where ``dna`` is installed),
    so the only thing PYTHONPATH adds is the "installed" example package — the
    repo's own copy is never on ``sys.path``.
    """
    env = {
        "PATH": __import__("os").environ.get("PATH", ""),
        "PYTHONPATH": str(pythonpath),
        # Keep resolution honest: no DNA_BASE_DIR leaking a scopes-root in.
    }
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def installed_pkg(tmp_path: Path) -> Path:
    """Materialize ``acme_support_bot`` at a fresh install location (a stand-in
    for site-packages / an unpacked wheel layer), INCLUDING its ``.dna`` data.
    Returns the dir to put on PYTHONPATH."""
    site = tmp_path / "site-packages"
    site.mkdir()
    shutil.copytree(_PKG_DIR, site / "acme_support_bot")
    return site


def test_resolves_from_installed_package_diff_cwd(installed_pkg: Path, tmp_path: Path):
    """THE reproduction: scope resolves from the installed package, from an
    empty CWD, via ``anchor=`` — no path navigation, no ``.dna`` in cwd."""
    empty_cwd = tmp_path / "container-workdir"  # like Docker WORKDIR /app
    empty_cwd.mkdir()
    assert not (empty_cwd / ".dna").exists()  # nothing to find via the cwd

    proc = _run_from(
        empty_cwd,
        installed_pkg,
        """
        from dna import load_prompts
        prompts = load_prompts("support", anchor="acme_support_bot")
        text = prompts["triage"]
        assert "ACME support triage agent" in text, text
        print("ANCHOR_OK::" + text.splitlines()[0])
        """,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "ANCHOR_OK::" in proc.stdout


def test_pkg_scheme_resolves_from_installed_package(installed_pkg: Path, tmp_path: Path):
    """``pkg://`` source scheme resolves the embedded scope end-to-end through
    ``Kernel.from_config`` (``source: pkg://acme_support_bot``), from an empty
    CWD — the ``dna.config.yaml`` declares it, the source reads package data."""
    empty_cwd = tmp_path / "container-workdir"
    empty_cwd.mkdir()
    # The only thing in the CWD is a config that points at the PACKAGE, not a
    # local .dna — proving the scope rides the package, not the working dir.
    (empty_cwd / "dna.config.yaml").write_text(
        "source: pkg://acme_support_bot\n", encoding="utf-8"
    )
    assert not (empty_cwd / ".dna").exists()

    proc = _run_from(
        empty_cwd,
        installed_pkg,
        """
        from dna import Kernel
        k = Kernel.from_config()               # auto-discovers ./dna.config.yaml
        mi = k.instance("support")
        text = mi.build_prompt(agent="triage")
        assert "ACME support triage agent" in text, text
        print("PKG_OK::" + text.splitlines()[0])
        """,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "PKG_OK::" in proc.stdout


def test_negative_control_old_path_resolution_fails(installed_pkg: Path, tmp_path: Path):
    """Control: WITHOUT the anchor, resolving from the empty CWD finds no scope
    — the exact failure the anchor cures (an empty PromptLibrary / no docs)."""
    empty_cwd = tmp_path / "container-workdir"
    empty_cwd.mkdir()

    proc = _run_from(
        empty_cwd,
        installed_pkg,
        """
        from dna import load_prompts
        # No anchor, no DNA_BASE_DIR, cwd has no .dna → the scope is NOT found.
        # Whether that surfaces as an empty library or a raise, the point holds:
        # the triage prompt the anchor DID resolve is unreachable here.
        resolved_triage = False
        try:
            prompts = load_prompts("support")
            text = prompts["triage"]
            resolved_triage = "ACME support triage agent" in text
        except Exception:
            resolved_triage = False
        assert resolved_triage is False, "old path resolution unexpectedly worked"
        print("CONTROL_OK::not-resolved")
        """,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "CONTROL_OK::not-resolved" in proc.stdout


def test_anchor_fail_loud_missing_package():
    """A bad anchor fails loud with a didactic, packaging-oriented message."""
    from dna import PackageScopeNotFound, load_prompts

    with pytest.raises(PackageScopeNotFound) as exc:
        load_prompts("support", anchor="no_such_package_xyz")
    msg = str(exc.value)
    assert "no_such_package_xyz" in msg
    assert "package data" in msg


def test_precedence_base_dir_beats_anchor(tmp_path: Path):
    """``base_dir`` (explicit) wins over ``anchor`` — the documented order."""
    from dna.prompts import _resolve_scope_base_dir

    # base_dir explicit beats everything (anchor never consulted → no import).
    assert _resolve_scope_base_dir(anchor="whatever", base_dir="/x/.dna") == "/x/.dna"


def test_precedence_env_beats_anchor(monkeypatch, tmp_path: Path):
    from dna.prompts import _resolve_scope_base_dir

    monkeypatch.setenv("DNA_BASE_DIR", "/from/env/.dna")
    assert _resolve_scope_base_dir(anchor="whatever", base_dir=None) == "/from/env/.dna"


def test_precedence_anchor_beats_default(monkeypatch):
    import dna.package_scope as ps
    from dna.prompts import _resolve_scope_base_dir

    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    monkeypatch.setattr(ps, "anchor_scopes_root", lambda a: f"<pkg:{a}>")
    resolved = _resolve_scope_base_dir(anchor="some_pkg", base_dir=None)
    # anchor consulted (not the bare ".dna" default).
    assert resolved == "<pkg:some_pkg>"


def test_precedence_default_when_nothing_set(monkeypatch):
    from dna.prompts import _resolve_scope_base_dir

    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    assert _resolve_scope_base_dir(anchor=None, base_dir=None) == ".dna"


def test_source_from_url_pkg_fail_loud_missing_package():
    """``pkg://`` with no package name fails loud (before any import)."""
    import asyncio

    from dna.adapters.source_url import UnsupportedSourceScheme, source_from_url

    with pytest.raises(UnsupportedSourceScheme) as exc:
        asyncio.run(source_from_url("pkg://"))
    assert "package name" in str(exc.value)


def test_source_from_url_pkg_fail_loud_unknown_package():
    """``pkg://<missing>`` fails loud with the packaging-oriented message."""
    import asyncio

    from dna import PackageScopeNotFound
    from dna.adapters.source_url import source_from_url

    with pytest.raises(PackageScopeNotFound):
        asyncio.run(source_from_url("pkg://no_such_package_xyz"))


def test_source_from_url_pkg_happy_and_subpath(tmp_path, monkeypatch):
    """``pkg://<pkg>`` (and ``pkg://<pkg>/<subpath>``) resolve a scope embedded
    in a synthesized on-``sys.path`` package to a read-only FilesystemSource."""
    import asyncio

    from dna.adapters.filesystem import FilesystemSource
    from dna.adapters.source_url import source_from_url

    # A throwaway installed package: <pkg>/.dna/demo/Genome.yaml
    pkg = tmp_path / "myembeddedpkg"
    (pkg / ".dna" / "demo").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / ".dna" / "demo" / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        "metadata:\n  name: demo\nspec: {}\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    src = asyncio.run(source_from_url("pkg://myembeddedpkg"))
    assert isinstance(src, FilesystemSource)
    assert Path(src.base_dir) == (pkg / ".dna").resolve()

    # explicit subpath form resolves the same dir
    src2 = asyncio.run(source_from_url("pkg://myembeddedpkg/.dna"))
    assert Path(src2.base_dir) == (pkg / ".dna").resolve()


@pytest.mark.requires_network  # `uv build` fetches the build backend from PyPI
def test_wheel_ships_the_scope(tmp_path: Path):
    """Build the example wheel for real and assert the embedded scope is inside
    it — proof the hatch ``force-include`` config actually ships the data."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv not on PATH")

    out = tmp_path / "dist"
    proc = subprocess.run(
        [uv, "build", "--wheel", "--out-dir", str(out), str(_EXAMPLE)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"uv build failed: {proc.stderr}"

    wheels = list(out.glob("*.whl"))
    assert wheels, "no wheel produced"
    names = zipfile.ZipFile(wheels[0]).namelist()
    assert "acme_support_bot/.dna/support/Genome.yaml" in names, names
    assert "acme_support_bot/.dna/support/agents/triage.yaml" in names, names
