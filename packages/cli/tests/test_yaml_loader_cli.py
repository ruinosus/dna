"""The CLI parses YAML through the SDK's shared seam (``dna._yaml``).

``yaml.safe_load`` hardcodes PyYAML's pure-Python loader. The SDK resolves the
libyaml-backed *safe* loader once in ``dna._yaml`` (with a transparent fallback
where libyaml is absent); the CLI reuses that decision instead of making its
own. Ratchet, so a new command does not silently reintroduce the slow path.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from dna._yaml import HAVE_LIBYAML, SafeLoader, safe_load, safe_load_all

CLI_ROOT = Path(__file__).resolve().parents[1] / "dna_cli"

_SKIP_PARTS = {"__pycache__", ".venv", "node_modules", "build", "dist"}


def _sources() -> list[Path]:
    return [
        p for p in sorted(CLI_ROOT.rglob("*.py"))
        if not any(part in _SKIP_PARTS for part in p.parts)
    ]


def _offenders(tokens: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for path in _sources():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if any(token in code for token in tokens):
                out.append(f"{path.relative_to(CLI_ROOT)}:{lineno}: {line.strip()}")
    return out


def test_no_command_parses_yaml_through_the_slow_pure_python_entry_points():
    offenders = _offenders((
        "yaml.safe_load(", "yaml.safe_load_all(",
        "yaml.full_load(", "yaml.unsafe_load(",
    ))
    assert not offenders, (
        "parse YAML through dna._yaml.safe_load / safe_load_all so libyaml is "
        "used when available:\n" + "\n".join(offenders)
    )


def test_no_command_parses_yaml_with_a_loader_that_can_build_python_objects():
    offenders = _offenders((
        "Loader=yaml.Loader", "Loader=yaml.CLoader", "Loader=yaml.FullLoader",
        "Loader=yaml.UnsafeLoader", "Loader=Loader", "Loader=CLoader",
        "Loader=FullLoader", "Loader=UnsafeLoader",
    ))
    assert not offenders, "unsafe YAML loader in use:\n" + "\n".join(offenders)


def test_the_shared_seam_is_a_safe_loader_and_is_accelerated_when_available():
    assert issubclass(SafeLoader, yaml.constructor.SafeConstructor)
    assert HAVE_LIBYAML is yaml.__with_libyaml__
    assert safe_load("a: 1\n") == {"a": 1}
    assert list(safe_load_all("a: 1\n---\nb: 2\n")) == [{"a": 1}, {"b": 2}]
