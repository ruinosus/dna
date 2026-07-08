"""F3 (spec D3): builtin Kind descriptors are parity-critical package data.

Like the template trees (test_*_templates_migration.py /
test_autoagent_template_config_driven.py), every ``kinds/*.kind.yaml``
shipped inside a Python extension package MUST have a byte-identical twin
in the TS package — the descriptor IS the cross-language contract (one
file, two mirrors, sha256-equal).

Guards:
  - the SET of descriptor files is identical on both sides (one side
    having a file the other doesn't is a nominal failure, not a skip);
  - each pair is byte-identical (sha256 over raw bytes).

With no descriptors shipped yet this passes vacuously — the first real
pair (kaizen.kind.yaml, F3 P2 pilot) makes it bite.
"""
from __future__ import annotations

import hashlib
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_PY_EXT = _ROOT / "packages/sdk-py/dna/extensions"
_TS_EXT = _ROOT / "packages/sdk-ts/src/extensions"


def _descriptor_set(ext_root: pathlib.Path) -> dict[str, pathlib.Path]:
    """Map ``<extension>/<file>.kind.yaml`` → absolute path."""
    return {
        f"{p.parent.parent.name}/{p.name}": p
        for p in sorted(ext_root.glob("*/kinds/*.kind.yaml"))
    }


def test_descriptor_sets_identical_across_languages():
    py = _descriptor_set(_PY_EXT)
    ts = _descriptor_set(_TS_EXT)
    only_py = sorted(set(py) - set(ts))
    only_ts = sorted(set(ts) - set(py))
    assert not only_py and not only_ts, (
        "kinds/*.kind.yaml must exist on BOTH sides (byte-identical mirrors). "
        f"Py-only: {only_py} · TS-only: {only_ts}"
    )


def test_descriptors_byte_identical_across_languages():
    py = _descriptor_set(_PY_EXT)
    ts = _descriptor_set(_TS_EXT)
    for rel in sorted(set(py) & set(ts)):
        py_sha = hashlib.sha256(py[rel].read_bytes()).hexdigest()
        ts_sha = hashlib.sha256(ts[rel].read_bytes()).hexdigest()
        assert py_sha == ts_sha, (
            f"descriptor {rel} diverged between Py and TS "
            f"(py={py_sha[:12]}… ts={ts_sha[:12]}…) — descriptors are "
            "parity-critical: edit one, copy to the other byte-for-byte"
        )
