"""Py↔TS Kind registry parity (s-kind-registry-parity-test).

The shared manifest ``packages/sdk-ts/kind-registry-parity.json`` declares the
TS builtin Kind aliases (``ts_aliases``) and the Kinds registered in Python but
intentionally NOT yet ported to TS (``py_only_allowlist``). This test locks the
PYTHON side:

  - every TS Kind must have a Python twin (``ts_aliases ⊆ Py registry``);
  - no undocumented drift: a new Python Kind must be ported to TS (added to
    ``ts_aliases`` + a TS extension) OR documented in ``py_only_allowlist``;
  - the allowlist stays honest (nothing in it that TS now has).

Was the root cause of the silent drift the sweep found (9 unexported TS
extensions, ~53 Py-only Kinds). Future porting stories shrink the allowlist.

i-132 (F3 lote-2): descriptor-backed Kinds (``*/kinds/*.kind.yaml``,
byte-identical Py↔TS package data enforced by test_descriptor_hash_parity)
exist in BOTH runtimes by construction — their aliases are DERIVED here by
scanning the descriptor files instead of being hand-listed in the manifest.
``ts_aliases`` stays hand-maintained only for class-based TS Kinds; a new
descriptor Kind needs NO registry edit.
"""
from __future__ import annotations

import json
import pathlib

import yaml

from dna.kernel import Kernel

_PARITY = (
    pathlib.Path(__file__).resolve().parents[2]
    / "sdk-ts"
    / "kind-registry-parity.json"
)

_EXTENSIONS_DIR = (
    pathlib.Path(__file__).resolve().parents[1] / "dna" / "extensions"
)


def _py_aliases() -> set[str]:
    k = Kernel.auto()
    return {
        kp.alias
        for kp in getattr(k, "_kinds", {}).values()
        if getattr(kp, "alias", "")
    }


def _descriptor_aliases() -> set[str]:
    """Aliases of builtin descriptor Kinds (i-132) — scanned from the
    ``*/kinds/*.kind.yaml`` package data. Both runtimes register these via
    the same byte-identical files, so parity holds by construction."""
    aliases: set[str] = set()
    for f in _EXTENSIONS_DIR.glob("*/kinds/*.kind.yaml"):
        raw = yaml.safe_load(f.read_text())
        alias = ((raw or {}).get("spec") or {}).get("alias")
        assert alias, f"descriptor without spec.alias: {f}"
        aliases.add(alias)
    return aliases


def _effective_ts_aliases(manifest: dict) -> set[str]:
    """Hand-maintained class aliases ∪ derived descriptor aliases."""
    return set(manifest["ts_aliases"]) | _descriptor_aliases()


def test_parity_manifest_exists():
    assert _PARITY.exists(), f"parity manifest missing: {_PARITY}"


def test_every_ts_kind_has_a_py_twin():
    manifest = json.loads(_PARITY.read_text())
    ts = _effective_ts_aliases(manifest)
    py = _py_aliases()
    missing = sorted(ts - py)
    assert not missing, f"TS Kinds with no Python twin: {missing}"


def test_no_undocumented_py_only_drift():
    manifest = json.loads(_PARITY.read_text())
    ts = _effective_ts_aliases(manifest)
    allow = set(manifest["py_only_allowlist"])
    py = _py_aliases()
    undocumented = sorted(py - ts - allow)
    assert not undocumented, (
        "New Python Kind(s) neither ported to TS nor allowlisted: "
        f"{undocumented}. Port them (add to ts_aliases + the TS extension), "
        "express them as a kinds/*.kind.yaml descriptor (no registry edit "
        "needed), or add to py_only_allowlist in "
        "packages/sdk-ts/kind-registry-parity.json."
    )


def test_allowlist_has_no_stale_entries():
    manifest = json.loads(_PARITY.read_text())
    ts = _effective_ts_aliases(manifest)
    allow = set(manifest["py_only_allowlist"])
    stale = sorted(allow & ts)
    assert not stale, (
        f"py_only_allowlist lists aliases now in TS (remove them): {stale}"
    )


def test_descriptor_aliases_never_need_manual_registry_entries():
    """i-132 pin: a descriptor Kind's alias comes from the scan — hand-listing
    it in ts_aliases (or py_only_allowlist) is redundant-by-construction and
    would rot when batches migrate. The manifest stays class-only."""
    manifest = json.loads(_PARITY.read_text())
    derived = _descriptor_aliases()
    assert derived, "descriptor scan found nothing — loader path broken?"
    hand_listed = sorted(set(manifest["ts_aliases"]) & derived)
    assert not hand_listed, (
        "descriptor-backed alias(es) hand-listed in ts_aliases — remove them; "
        f"the scan derives them: {hand_listed}"
    )
    allowlisted = sorted(set(manifest["py_only_allowlist"]) & derived)
    assert not allowlisted, (
        "descriptor-backed alias(es) in py_only_allowlist — impossible state "
        f"(descriptors exist in BOTH runtimes): {allowlisted}"
    )
