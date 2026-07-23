"""s-invert-layer-resolver-dep — kernel↛extensions boundary guard (ratchet).

The microkernel must work with ZERO extensions loaded. Historically the
kernel lazy-imported ``dna.extensions.helix.layers`` for its
CORE function (layer resolution) — that resolver now lives at
``dna.kernel.compose.layer_resolver``. This test is the ratchet that
keeps the boundary inverted: it AST-walks every module in
``dna/kernel/`` and FAILS if any of them imports
``dna.extensions.*`` (or escapes relatively via
``from ..extensions import ...``) outside a ``TYPE_CHECKING`` block.

BASELINE is shrink-only: it lists the known remaining offender(s). New
kernel modules must NOT import extensions; when a baseline file is
cleaned up, remove it from the set so it can't regress.
"""
from __future__ import annotations

import ast
from pathlib import Path

KERNEL_DIR = Path(__file__).resolve().parents[1] / "dna" / "kernel"

# Shrink-only baseline — now EMPTY. The last offender (evidence_capture.py)
# was inverted in s-invert-evidence-capture-dep: the generic evidence helpers
# (compute_content_hash/build_evidence/should_capture) moved into the kernel
# (mirroring the TS twin), and EvidenceExtension re-exports them for its public
# API. No kernel module imports dna.extensions anymore. Keep this at
# frozenset() — any new offender must be inverted, never baselined.
BASELINE: frozenset[str] = frozenset()


def _type_checking_spans(tree: ast.Module) -> list[tuple[int, int]]:
    """Line spans of ``if TYPE_CHECKING:`` bodies (imports there are fine)."""
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if is_tc and node.body:
            spans.append((node.body[0].lineno, node.body[-1].end_lineno or node.body[-1].lineno))
    return spans


def _extension_imports(path: Path) -> list[tuple[int, str]]:
    """All (lineno, module) imports of dna.extensions outside TYPE_CHECKING."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tc_spans = _type_checking_spans(tree)
    offenders: list[tuple[int, str]] = []

    def _record(lineno: int, mod: str) -> None:
        if any(start <= lineno <= end for start, end in tc_spans):
            return
        offenders.append((lineno, mod))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "dna.extensions" or alias.name.startswith(
                    "dna.extensions."
                ):
                    _record(node.lineno, alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level == 0 and (
                mod == "dna.extensions"
                or mod.startswith("dna.extensions.")
            ):
                _record(node.lineno, mod)
            elif node.level >= 2 and (
                mod == "extensions" or mod.startswith("extensions.")
            ):
                # ``from ..extensions import X`` — relative escape out of kernel/
                _record(node.lineno, "." * node.level + mod)
    return offenders


def _kernel_modules() -> list[Path]:
    files = sorted(KERNEL_DIR.glob("*.py"))
    assert files, f"no kernel modules found at {KERNEL_DIR}"
    return files


def test_kernel_modules_do_not_import_extensions():
    """No kernel module may import dna.extensions (outside TYPE_CHECKING)."""
    violations: dict[str, list[tuple[int, str]]] = {}
    for path in _kernel_modules():
        if path.name in BASELINE:
            continue
        offenders = _extension_imports(path)
        if offenders:
            violations[path.name] = offenders

    assert not violations, (
        "Kernel modules import dna.extensions — the microkernel must "
        "work with zero extensions loaded (s-invert-layer-resolver-dep). "
        "Move the generic code into dna/kernel/ (leave a deprecated "
        "reexport shim in the extension), or define a Protocol port the "
        "extension registers on the kernel. Violations: "
        + "; ".join(
            f"{fname}: " + ", ".join(f"L{ln} {mod}" for ln, mod in offs)
            for fname, offs in sorted(violations.items())
        )
    )


def test_boundary_baseline_is_shrink_only():
    """Every BASELINE entry must still offend — remove cleaned files from the set."""
    for fname in sorted(BASELINE):
        path = KERNEL_DIR / fname
        assert path.exists(), (
            f"BASELINE entry {fname!r} no longer exists in dna/kernel/ — "
            "remove it from BASELINE in this test."
        )
        assert _extension_imports(path), (
            f"BASELINE entry {fname!r} no longer imports dna.extensions — "
            "great! Remove it from BASELINE so the boundary can't regress."
        )
