"""The shared YAML seam (``dna._yaml``) — fast, safe, and identical.

PyYAML ships two implementations of the same grammar: a pure-Python
scanner/parser and a binding over libyaml (C). They are *meant* to agree.
"Meant to" is not evidence, and a silent divergence here would corrupt
instances rather than fail loudly — so this module asserts equality on the
repository's own YAML corpus, not on a toy string.

Three properties are locked:

1. **Fast** — when libyaml is available the seam resolves to ``CSafeLoader``.
2. **Safe** — always a *safe* loader. Never ``CLoader``/``FullLoader``, which
   can construct arbitrary Python objects out of author-supplied YAML.
3. **Portable** — a wheel installed where libyaml is absent must keep working,
   silently and correctly, on the pure-Python loader.
"""
from __future__ import annotations

import importlib
import math
from pathlib import Path

import pytest
import yaml

from dna import _yaml as dna_yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SDK_ROOT = Path(__file__).resolve().parents[1]

# Directories that are not part of this repo's authored YAML corpus.
_SKIP_PARTS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "site-packages",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
}


def _corpus(root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in ("*.yaml", "*.yml"):
        for path in root.rglob(pattern):
            if any(part in _SKIP_PARTS for part in path.parts):
                continue
            files.append(path)
    return sorted(set(files))


def _shape(obj: object) -> object:
    """Types-only mirror of ``obj`` — ``1 == True == 1.0`` in Python, so plain
    equality alone would not catch a resolver divergence."""
    if isinstance(obj, dict):
        return {k: _shape(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_shape(v) for v in obj]
    return type(obj).__name__


def _eq(a: object, b: object) -> bool:
    """Equality that treats NaN as equal to NaN (``.nan`` appears in YAML)."""
    if isinstance(a, float) and isinstance(b, float):
        return a == b or (math.isnan(a) and math.isnan(b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_eq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b))
    return a == b


# --------------------------------------------------------------------------
# 1. fast


def test_the_seam_resolves_to_the_c_safe_loader_when_libyaml_is_available():
    if not yaml.__with_libyaml__:  # pragma: no cover - environment dependent
        pytest.skip("PyYAML in this environment was built without libyaml")
    assert dna_yaml.HAVE_LIBYAML is True
    assert dna_yaml.SafeLoader is yaml.CSafeLoader


# --------------------------------------------------------------------------
# 2. safe


def test_the_seam_never_resolves_to_a_loader_that_can_build_python_objects():
    unsafe = {yaml.Loader, yaml.UnsafeLoader, yaml.FullLoader}
    if yaml.__with_libyaml__:
        unsafe |= {yaml.CLoader}
    assert dna_yaml.SafeLoader not in unsafe
    assert issubclass(dna_yaml.SafeLoader, yaml.constructor.SafeConstructor)


def test_the_seam_refuses_to_construct_arbitrary_python_objects():
    """The load-bearing property: author-supplied YAML is data, never code."""
    payload = "!!python/object/apply:os.system ['echo pwned']\n"
    with pytest.raises(yaml.YAMLError):
        dna_yaml.safe_load(payload)
    with pytest.raises(yaml.YAMLError):
        list(dna_yaml.safe_load_all(payload))


def test_the_seam_raises_the_documented_yaml_error_on_malformed_input():
    """Call sites catch ``yaml.YAMLError``; the C parser must honour that."""
    with pytest.raises(yaml.YAMLError):
        dna_yaml.safe_load("a: [1, 2\nb: {\n")


# --------------------------------------------------------------------------
# 3. identical — on the real corpus, not a toy string


def test_both_loaders_agree_on_every_yaml_document_in_the_repository():
    if not yaml.__with_libyaml__:  # pragma: no cover - environment dependent
        pytest.skip("PyYAML in this environment was built without libyaml")

    files = _corpus(REPO_ROOT)
    # Guard the guard: an empty/pruned corpus would make this test vacuous.
    assert len(files) > 300, f"corpus looks wrong: only {len(files)} YAML files"

    divergences: list[str] = []
    compared = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):  # pragma: no cover - defensive
            continue

        pure_err = c_err = None
        try:
            pure = list(yaml.load_all(text, Loader=yaml.SafeLoader))
        except yaml.YAMLError as exc:
            pure, pure_err = None, exc
        try:
            fast = list(yaml.load_all(text, Loader=yaml.CSafeLoader))
        except yaml.YAMLError as exc:
            fast, c_err = None, exc

        rel = path.relative_to(REPO_ROOT)
        if bool(pure_err) != bool(c_err):
            divergences.append(
                f"{rel}: accepted by one loader and rejected by the other "
                f"(pure={pure_err!r} libyaml={c_err!r})"
            )
            continue
        if pure_err:
            continue  # both reject — same verdict, that is the contract
        compared += 1
        if not _eq(pure, fast):
            divergences.append(f"{rel}: values differ")
        elif _shape(pure) != _shape(fast):
            divergences.append(f"{rel}: resolved types differ")

    assert compared > 300, f"only {compared} instances actually compared"
    assert not divergences, "loader divergence on the real corpus:\n" + "\n".join(
        divergences[:20]
    )


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("a: 2026-07-25\nb: 2026-07-25T10:20:30.5Z\nc: 2026-07-25 10:20:30 -3\n", id="timestamps"),
        pytest.param("base: &b {x: 1, y: 2}\nchild:\n  <<: *b\n  y: 3\n", id="merge-keys"),
        pytest.param("k: 1\nk: 2\n", id="duplicate-keys"),
        pytest.param('s: "caf\u00e9 \u2014 \u00e7\u00e3o \U0001f9ec"\nplain: na\u00efve\n', id="unicode"),
        pytest.param("a: 0o17\nb: 017\nc: 0x1f\nd: 1_000\n", id="int-forms"),
        pytest.param("a: 12:30\nb: 1:2:3\n", id="sexagesimal"),
        pytest.param("a: yes\nb: no\nc: on\nd: off\ne: true\nf: null\ng: ~\nh: NO\n", id="bools-and-nulls"),
        pytest.param("a: .inf\nb: -.Inf\nc: .nan\nd: 1e3\ne: 1.0\n", id="floats"),
        pytest.param("a: |\n  l1\n  l2\nb: >\n  f1\n  f2\nc: |-\n  x\nd: |+\n  y\n\n", id="block-scalars"),
        pytest.param("a: &x [1,2]\nb: *x\n", id="anchors-and-aliases"),
        pytest.param("", id="empty"),
        pytest.param("? ~\n: v\n", id="explicit-null-key"),
        pytest.param("a: !!str 1\nb: !!int '3'\nc: !!binary aGk=\nd: !!set {x, y}\n", id="explicit-tags"),
        pytest.param('a: "line\\u2028sep"\nb: "nel\\u0085here"\n', id="unicode-line-breaks"),
        pytest.param("---\na: 1\n---\nb: 2\n", id="multi-document"),
        pytest.param('a: "tab\\there"\nb: "\\x41"\nc: \'single \'\' quote\'\n', id="escapes"),
        pytest.param("a:\nb: ''\nc: []\nd: {}\n", id="empty-values"),
        pytest.param("1: one\ntrue: yes\n2026-07-25: date\n", id="non-string-keys"),
    ],
)
def test_both_loaders_agree_on_the_semantics_that_could_diverge_silently(source: str):
    """The failure modes that would corrupt data instead of raising."""
    if not yaml.__with_libyaml__:  # pragma: no cover - environment dependent
        pytest.skip("PyYAML in this environment was built without libyaml")
    pure = list(yaml.load_all(source, Loader=yaml.SafeLoader))
    fast = list(yaml.load_all(source, Loader=yaml.CSafeLoader))
    assert _eq(pure, fast)
    assert _shape(pure) == _shape(fast)
    # …and the seam itself returns what the pure loader would.
    assert _eq(list(dna_yaml.safe_load_all(source)), pure)


def test_the_seam_matches_yaml_safe_load_on_a_packaged_kind_descriptor():
    descriptors = sorted((SDK_ROOT / "dna" / "extensions").rglob("*.kind.yaml"))
    assert descriptors, "no packaged Kind descriptors found"
    for path in descriptors:
        text = path.read_text(encoding="utf-8")
        assert _eq(dna_yaml.safe_load(text), yaml.safe_load(text)), path


# --------------------------------------------------------------------------
# 4. portable — the fallback branch, forced, not assumed


def test_the_seam_falls_back_to_the_pure_python_loader_when_libyaml_is_absent(
    monkeypatch: pytest.MonkeyPatch,
):
    """Force the branch rather than trusting that it reads correctly.

    ``importlib.reload`` refreshes the module dict in place, so for the
    duration of this test the *whole process* is on the pure-Python loader —
    which is exactly the environment a libyaml-less wheel install lives in.
    """
    for attr in ("CSafeLoader", "CLoader", "CSafeDumper", "CDumper"):
        monkeypatch.delattr(yaml, attr, raising=False)
    monkeypatch.setattr(yaml, "__with_libyaml__", False, raising=False)

    try:
        importlib.reload(dna_yaml)
        assert dna_yaml.HAVE_LIBYAML is False
        assert dna_yaml.SafeLoader is yaml.SafeLoader
        # Still safe, still correct.
        assert dna_yaml.safe_load("a: 1\nb: [x, y]\n") == {"a": 1, "b": ["x", "y"]}
        assert list(dna_yaml.safe_load_all("a: 1\n---\nb: 2\n")) == [{"a": 1}, {"b": 2}]
        with pytest.raises(yaml.YAMLError):
            dna_yaml.safe_load("!!python/object/apply:os.system ['echo pwned']\n")
        # And the kernel still boots through the fallback.
        from dna.kernel.source.descriptor_loader import load_descriptors

        assert load_descriptors("dna.extensions.helix")
    finally:
        monkeypatch.undo()
        importlib.reload(dna_yaml)

    assert dna_yaml.HAVE_LIBYAML is yaml.__with_libyaml__


# --------------------------------------------------------------------------
# 5. ratchet — the win is only kept if new call sites use the seam


def _python_sources(root: Path) -> list[Path]:
    return [
        p for p in sorted(root.rglob("*.py"))
        if not any(part in _SKIP_PARTS for part in p.parts)
    ]


def test_no_module_parses_yaml_through_the_slow_pure_python_entry_points():
    """``yaml.safe_load`` hardcodes the pure-Python loader.

    Route new parses through ``dna._yaml`` instead — one seam, so the loader
    choice (and its libyaml fallback) is decided in exactly one place.
    """
    banned = ("yaml.safe_load(", "yaml.safe_load_all(", "yaml.full_load(",
              "yaml.unsafe_load(")
    offenders: list[str] = []
    seam = (SDK_ROOT / "dna" / "_yaml.py").resolve()
    for path in _python_sources(SDK_ROOT / "dna"):
        if path.resolve() == seam:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if any(token in code for token in banned):
                offenders.append(f"{path.relative_to(SDK_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "parse YAML through dna._yaml.safe_load / safe_load_all so libyaml is "
        "used when available:\n" + "\n".join(offenders)
    )


def test_no_module_parses_yaml_with_a_loader_that_can_build_python_objects():
    """An unsafe loader on author-supplied YAML is a code-execution path."""
    banned = ("Loader=yaml.Loader", "Loader=yaml.CLoader", "Loader=yaml.FullLoader",
              "Loader=yaml.UnsafeLoader", "Loader=Loader", "Loader=CLoader",
              "Loader=FullLoader", "Loader=UnsafeLoader", "yaml.unsafe_load(",
              "yaml.full_load(")
    offenders: list[str] = []
    for path in _python_sources(SDK_ROOT / "dna"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if any(token in code for token in banned):
                offenders.append(f"{path.relative_to(SDK_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "unsafe YAML loader in use:\n" + "\n".join(offenders)
