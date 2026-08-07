#!/usr/bin/env python3
"""Generate the Ports catalogue (docs/reference/ports/) from the source tree.

Every extension point DNA has is a ``typing.Protocol``. There are dozens, and
until this generator existed the docs named **seven** of them — so anybody who
wanted to swap the conversation purge, the eval target, the contradiction
scribe or the scaffold resolver had no way to learn those were seams at all.
This closes that the only way a catalogue of this size can stay closed:
**derived**, so a new port cannot ship invisible.

What is DERIVED (from the code, never hand-typed):
  * the port's name, module, line, and whether it is ``@runtime_checkable``;
  * the Protocols it composes (``ThreadStorePort`` = transcript + index);
  * every method, with its **verbatim source signature** and the first
    paragraph of its docstring;
  * the class docstring;
  * the shipped implementations — every class in ``dna`` that names the port
    as a base.

What is HAND-WRITTEN (``scripts/ports_prose.py``, one entry per port):
  the questions no signature answers — *when would I swap this? what is the
  minimum that works? what capability does it light up, and what does the
  face do if I skip it? how do I prove my implementation?* — plus the
  **group** each port belongs to, which is a reader-first judgement (what
  am I trying to change?) and deliberately not the package layout.

## Why AST and not ``import dna``

``gen_kinds_docs.py`` boots ``Kernel.auto()`` because a Kind's schema only
exists at runtime. A Protocol's shape does not: it is entirely in the source.
Parsing means the generator is **deterministic**, needs **no optional extra
installed** (a port behind ``[postgres]``/``[embed-onnx]`` is catalogued
either way), and reproduces the signature exactly as the author wrote it,
annotations and all — which is the thing a third-party implementer copies.

## The two ratchets

Deriving the list is only half. The generator also **fails**:

  * a Protocol in the code with no entry in ``ports_prose.py`` — a new port
    cannot land invisible, which is the whole defect this fixes;
  * an entry in ``ports_prose.py`` naming a Protocol that no longer exists —
    a renamed port cannot leave a dead name behind in the docs.

Both are the same guarantee read from opposite ends, and the second is not
theoretical: this repo has shipped a table keyed on a name the code had
already renamed.

Usage:
    python3 scripts/gen_ports_docs.py            # (re)generate the pages
    python3 scripts/gen_ports_docs.py --check    # fail if regeneration would change anything
    python3 scripts/gen_ports_docs.py --self-test  # prove the two ratchets still bite

Pure stdlib. No ``dna`` install required.
"""
from __future__ import annotations

import argparse
import ast
import io
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PKG_ROOT = _REPO_ROOT / "packages" / "sdk-py"
_SRC = _PKG_ROOT / "dna"
_OUT_DIR = _REPO_ROOT / "docs" / "reference" / "ports"


# --- model --------------------------------------------------------------------


class Port:
    """One ``Protocol`` found in the source tree."""

    def __init__(
        self,
        name: str,
        module: str,
        lineno: int,
        bases: list[str],
        runtime_checkable: bool,
        doc: str,
        methods: list[tuple[str, str, str]],
    ) -> None:
        self.name = name
        self.module = module
        self.lineno = lineno
        self.bases = bases  # other Protocols this one composes
        self.runtime_checkable = runtime_checkable
        self.doc = doc
        self.methods = methods  # (name, signature, first docstring paragraph)


def _first_para(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    return text.split("\n\n")[0].replace("\n", " ").strip()


def _cell(text: str) -> str:
    """Escape a value for a markdown table cell."""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """The method's signature exactly as written, minus the body.

    ``ast.unparse`` on the whole function would drag the body in; unparsing a
    body-less copy gives ``def name(args) -> T:`` and nothing else. The point
    is that a third-party implementer can copy this line and have a signature
    that type-checks against the Protocol, annotations included.
    """
    shell = type(node)(
        name=node.name,
        args=node.args,
        body=[ast.Expr(value=ast.Constant(value=Ellipsis))],
        decorator_list=[],
        returns=node.returns,
        type_comment=None,
        type_params=getattr(node, "type_params", []),
    )
    ast.fix_missing_locations(shell)
    text = ast.unparse(shell)
    # Drop the `...` body, keep the signature line(s).
    return text.rsplit(":", 1)[0].strip() if text.endswith("...") else text
    # (unreachable-safe: unparse always emits the ellipsis body)


def _is_protocol(node: ast.ClassDef) -> bool:
    return any(
        ast.unparse(b).split(".")[-1] == "Protocol" for b in node.bases
    )


def _collect() -> tuple[list[Port], dict[str, list[str]]]:
    """(ports, implementations) — every Protocol, and who inherits from each.

    ``implementations`` maps a port name to the concrete classes in ``dna``
    that name it as a base. Structural (duck-typed) adapters are invisible to
    this — a Protocol is satisfied without inheriting — so ``ports_prose.py``
    can name those explicitly under ``adapters_extra``. Inheritance is the
    half that can be derived, and deriving half beats hand-typing all of it.
    """
    ports: list[Port] = []
    impls: dict[str, list[str]] = {}
    protocol_names: set[str] = set()

    files = sorted(p for p in _SRC.rglob("*.py") if "__pycache__" not in str(p))
    parsed = [(p, ast.parse(p.read_text(encoding="utf-8"))) for p in files]

    for path, tree in parsed:
        module = str(path.relative_to(_PKG_ROOT)).replace("/", ".")[: -len(".py")]
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not _is_protocol(node):
                continue
            protocol_names.add(node.name)
            bases = [
                ast.unparse(b).split(".")[-1]
                for b in node.bases
                if ast.unparse(b).split(".")[-1] != "Protocol"
            ]
            decorators = [ast.unparse(d) for d in node.decorator_list]
            methods = [
                (
                    m.name,
                    _signature(m),
                    _first_para(ast.get_docstring(m) or ""),
                )
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            ports.append(
                Port(
                    name=node.name,
                    module=module,
                    lineno=node.lineno,
                    bases=bases,
                    runtime_checkable=any("runtime_checkable" in d for d in decorators),
                    doc=(ast.get_docstring(node) or "").strip(),
                    methods=methods,
                )
            )

    # Second pass: who implements what. A Protocol subclassing a Protocol is a
    # composed PORT, not an implementation of it, so those are excluded.
    for path, tree in parsed:
        module = str(path.relative_to(_PKG_ROOT)).replace("/", ".")[: -len(".py")]
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or _is_protocol(node):
                continue
            for base in node.bases:
                short = ast.unparse(base).split(".")[-1]
                if short in protocol_names:
                    impls.setdefault(short, []).append(f"{node.name} (`{module}`)")

    ports.sort(key=lambda p: p.name)
    for key in impls:
        impls[key] = sorted(set(impls[key]))

    all_classes = {
        node.name
        for _, tree in parsed
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }
    return ports, impls, all_classes


# --- rendering ----------------------------------------------------------------

_ROLE_LABEL = {
    "extend": "extension point",
    "receive": "handed to you",
    "internal": "internal seam",
}

_ROLE_BADGE = {
    "extend": ":material-power-plug: **extension point**",
    "receive": ":material-hand-extended: handed to you",
    "internal": ":material-lock: internal seam",
}


def _anchor(name: str) -> str:
    return name.lower()


def _port_section(port: Port, prose: dict, impls: dict[str, list[str]]) -> str:
    out = io.StringIO()
    role = prose["role"]
    out.write(f"## {port.name}\n\n")

    checkable = (
        "`@runtime_checkable`" if port.runtime_checkable else "typing-only (not `@runtime_checkable`)"
    )
    out.write(f"`{port.module}.{port.name}` · {checkable} · {_ROLE_BADGE[role]}\n\n")

    if port.bases:
        composed = ", ".join(f"[`{b}`](#{_anchor(b)})" for b in port.bases)
        out.write(f"Composes {composed}.\n\n")

    out.write(prose["summary"].strip() + "\n\n")

    if port.doc:
        out.write("!!! quote \"From the source\"\n\n")
        for line in port.doc.splitlines():
            out.write(f"    {line}\n" if line.strip() else "\n")
        out.write("\n")

    if role == "internal":
        out.write(f"**Not an extension point.** {prose['not_for_you'].strip()}\n\n")
    elif role == "receive":
        out.write(
            f"**You do not implement this — the kernel does.** {prose['not_for_you'].strip()}\n\n"
        )

    if port.methods:
        out.write("**The contract**\n\n")
        out.write("| Member | Signature | What it must do |\n| --- | --- | --- |\n")
        for name, sig, doc in port.methods:
            out.write(f"| `{name}` | <code>{_cell(sig)}</code> | {_cell(doc)} |\n")
        out.write("\n")
    elif port.bases:
        out.write("_No members of its own — it is the union of the Protocols above._\n\n")
    else:
        out.write(
            "_No methods: this Protocol is satisfied by **attributes**, not calls "
            "(see the source docstring above)._\n\n"
        )

    if role != "internal":
        for label, key in (
            ("Swap it when", "when"),
            ("The minimum that works", "minimum"),
            ("What it lights up", "lights_up"),
            ("How you prove it", "prove"),
        ):
            value = (prose.get(key) or "").strip()
            if value:
                out.write(f"**{label}** — {value}\n\n")

    shipped = list(impls.get(port.name, []))
    shipped += [f"{a}" for a in prose.get("adapters_extra", ())]
    if shipped:
        out.write("**Shipped implementations** — " + "; ".join(shipped) + "\n\n")
    elif role == "extend":
        out.write(
            "**Shipped implementations** — none in-tree. This port has no reference "
            "adapter yet: you would be writing the first one.\n\n"
        )
    return out.getvalue()


def _group_page(group_key: str, group_meta: dict, ports: list[Port], prose_by_name: dict, impls) -> str:
    out = io.StringIO()
    out.write(f"# {group_meta['title']}\n\n")
    out.write(group_meta["blurb"].strip() + "\n\n")
    out.write(
        "!!! info \"Generated from the source\"\n\n"
        "    Names, signatures and docstrings are parsed out of `packages/sdk-py/dna`\n"
        "    by `scripts/gen_ports_docs.py`. The prose around each contract is\n"
        "    hand-written in `scripts/ports_prose.py`, and the generator **fails**\n"
        "    if a port has none — so a new port cannot ship undocumented.\n\n"
    )
    for port in ports:
        out.write(_port_section(port, prose_by_name[port.name], impls))
    appendix = (group_meta.get("appendix") or "").strip()
    if appendix:
        out.write(appendix + "\n")
    return out.getvalue()


def _index_page(groups, ports_by_group, prose_by_name, impls, total: int) -> str:
    out = io.StringIO()
    out.write("# The port catalogue\n\n")
    n_extend = sum(
        1 for p in prose_by_name.values() if p["role"] == "extend"
    )
    out.write(
        "DNA's kernel is a **microkernel**: it knows how to store, validate, version "
        "and compose instances, and nothing else. Everything else is a "
        "`typing.Protocol` — a **port** — that something outside the core satisfies. "
        f"There are **{total}** of them.\n\n"
        f"Most of this page exists to answer one question: *I want to change X — "
        f"what do I implement?* **{n_extend}** of the {total} are things you are "
        f"meant to implement. The rest are listed anyway, marked as what they are, "
        "because a seam you cannot see is indistinguishable from a seam that does "
        "not exist — and guessing wrong costs more than being told no.\n\n"
    )

    out.write("## What the three roles mean\n\n")
    out.write("| Role | Meaning |\n| --- | --- |\n")
    out.write(
        "| :material-power-plug: **extension point** | You implement it. A third party "
        "can ship one without touching the kernel. |\n"
        "| :material-hand-extended: handed to you | The kernel implements it and passes "
        "it in. You call it; you never satisfy it. |\n"
        "| :material-lock: internal seam | A back-reference between the kernel and one of "
        "its own collaborators, published as a Protocol so the decomposition stays "
        "honest and testable. Not a plug-in surface. |\n\n"
    )

    out.write(f"## All {total} ports\n\n")
    for key, meta in groups:
        group_ports = ports_by_group.get(key, [])
        if not group_ports:
            continue
        out.write(f"### {meta['title']} ({len(group_ports)})\n\n")
        out.write(meta["blurb"].strip() + "\n\n")
        out.write("| Port | Module | Role | What it decides | Shipped |\n")
        out.write("| --- | --- | --- | --- | --- |\n")
        for port in group_ports:
            prose = prose_by_name[port.name]
            shipped = len(impls.get(port.name, [])) + len(prose.get("adapters_extra", ()))
            link = f"[{port.name}]({key}.md#{_anchor(port.name)})"
            out.write(
                f"| {link} | `{port.module}` | {_ROLE_LABEL[prose['role']]} "
                f"| {_cell(prose['one_line'])} | {shipped or '—'} |\n"
            )
        out.write("\n")

    out.write(
        "## Before you implement one\n\n"
        "Two house rules apply to every port on this page.\n\n"
        "1. **If the thing you are adapting to has an official SDK, use it.** A port "
        "exists so DNA's core does not have to know your backend; it does not exist so "
        "you can re-derive somebody else's protocol from its specification. Conformance "
        "with a third party is the whole product, and a subtle misreading of a spec only "
        "surfaces when a real external client tries to talk to you.\n"
        "2. **Search before you build.** Check whether an adapter already exists — in "
        "this tree, in a dependency this package already declares, or on GitHub — before "
        "you write the first line. Record the result either way; a port implementation "
        "that does not say whether it looked leaves the next reader unable to tell a "
        "decision from an oversight.\n"
    )
    return out.getvalue()


# --- build --------------------------------------------------------------------


def build() -> dict[str, str]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ports_prose import GROUPS, PROSE  # noqa: PLC0415

    ports, impls, all_classes = _collect()
    found = {p.name for p in ports}
    documented = set(PROSE)

    missing = sorted(found - documented)
    dead = sorted(documented - found)
    if missing or dead:
        _fail_coverage(missing, dead)
    _check_adapters_extra(PROSE, all_classes)
    _check_prose_counts(
        len(ports), sum(1 for e in PROSE.values() if e["role"] == "extend")
    )

    ports_by_group: dict[str, list[Port]] = {}
    for port in ports:
        ports_by_group.setdefault(PROSE[port.name]["group"], []).append(port)

    pages = {
        "index.md": _index_page(GROUPS, ports_by_group, PROSE, impls, len(ports)),
    }
    for key, meta in GROUPS:
        group_ports = ports_by_group.get(key, [])
        if group_ports:
            pages[f"{key}.md"] = _group_page(key, meta, group_ports, PROSE, impls)
    return pages


def _check_adapters_extra(prose: dict, all_classes: set[str]) -> None:
    """Third ratchet: a hand-listed adapter must still exist.

    ``adapters_extra`` is the one place the prose names code, because a class
    that satisfies a Protocol *structurally* cannot be found by looking at
    bases. Hand-typed names rot exactly like a hand-typed table does, so the
    first backticked token of each entry is checked against the class names
    actually in the tree.

    Convention: an entry that STARTS with a backticked name is a class and is
    checked. An entry that starts with anything else is free prose (a count, a
    pointer to an entry-point group) and is left alone — there is no class name
    in it to go stale.
    """
    dead: list[tuple[str, str]] = []
    for port_name, entry in sorted(prose.items()):
        for line in entry.get("adapters_extra", ()):
            if not line.startswith("`"):
                continue
            cls = line.split("`")[1]
            if cls and cls not in all_classes:
                dead.append((port_name, cls))
    if not dead:
        return
    print(
        f"gen_ports_docs: {len(dead)} hand-listed adapter(s) in scripts/ports_prose.py "
        "name a class that no longer exists:",
        file=sys.stderr,
    )
    for port_name, cls in dead:
        print(f"  - {port_name}.adapters_extra → {cls}", file=sys.stderr)
    print(
        "\nIt was renamed or removed. A docs table listing an adapter nobody can "
        "import\nis worse than one listing none.",
        file=sys.stderr,
    )
    raise SystemExit(1)


#: Hand-written pages that quote the catalogue's counts, and the sentence
#: shape they quote them in. A count typed into prose is a fact that rots the
#: moment a port is added — so the generator owns it here too, and the prose
#: is checked against the code rather than trusted.
_COUNT_CLAIMS: tuple[tuple[str, str], ...] = (
    ("docs/concepts/microkernel-ports.md", "has **{total}** `Protocol`s"),
    ("docs/concepts/microkernel-ports.md", "**{extend}** of which are things"),
    ("docs/concepts/microkernel-ports.md", "all {total} ports, grouped by"),
)


def _check_prose_counts(total: int, extend: int) -> None:
    """Fail if a hand-written page quotes a count the code no longer supports."""
    wrong: list[tuple[str, str]] = []
    for rel, shape in _COUNT_CLAIMS:
        path = _REPO_ROOT / rel
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if shape.format(total=total, extend=extend) not in text:
            wrong.append((rel, shape.format(total=total, extend=extend)))
    if not wrong:
        return
    print(
        f"gen_ports_docs: prose quotes a stale count (the code has {total} ports, "
        f"{extend} of them extension points):",
        file=sys.stderr,
    )
    for rel, expected in wrong:
        print(f"  - {rel} should contain: {expected!r}", file=sys.stderr)
    print(
        "\nUpdate the sentence, or drop the claim and link to the generated index\n"
        "instead. A number typed into prose is a fact with no owner.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _fail_coverage(missing: list[str], dead: list[str]) -> None:
    if missing:
        print(
            f"gen_ports_docs: {len(missing)} Protocol(s) in the source have NO entry in "
            "scripts/ports_prose.py:",
            file=sys.stderr,
        )
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        print(
            "\nAdd one. Every port needs a group, a role, a one-liner and a summary; an\n"
            "extension point also needs `when` / `minimum` / `lights_up` / `prove`, and an\n"
            "internal seam needs `not_for_you`. A port nobody can discover is the exact\n"
            "defect this catalogue exists to prevent.",
            file=sys.stderr,
        )
    if dead:
        print(
            f"\ngen_ports_docs: {len(dead)} entr(y/ies) in scripts/ports_prose.py name a "
            "Protocol that no longer exists:",
            file=sys.stderr,
        )
        for name in dead:
            print(f"  - {name}", file=sys.stderr)
        print(
            "\nThe port was renamed or removed. Update or delete the entry — a docs table\n"
            "keyed on a dead name renders exactly like a correct one, which is why this\n"
            "is a hard failure and not a warning.",
            file=sys.stderr,
        )
    raise SystemExit(1)


# --- self-test ------------------------------------------------------------------


def self_test() -> int:
    """Prove the derivation and both ratchets still work. No writes."""
    failures: list[str] = []

    ports, impls, _all = _collect()
    by_name = {p.name: p for p in ports}

    # 1. Derivation finds the ports the old prose already named by hand — and
    #    the one the repo's own `grep "class .*(Protocol)"` MISSES, because in
    #    a basic regex `(Protocol)` is literal and never matches a Protocol
    #    that extends another Protocol. That undercount is why this generator
    #    parses instead of grepping.
    for expected in ("SourcePort", "KindPort", "EmitterPort", "WritableSourcePort"):
        if expected not in by_name:
            failures.append(f"derivation missed {expected}")
    wsp = by_name.get("WritableSourcePort")
    if wsp and wsp.bases != ["SourcePort"]:
        failures.append(f"composed port bases not derived: {wsp.bases if wsp else None}")

    # 2. Signatures carry annotations (the thing an implementer copies).
    src = by_name.get("SourcePort")
    if src and not any("->" in sig for _, sig, _ in src.methods):
        failures.append("signatures lost their return annotations")

    # 3. Implementations are derived, not typed.
    if not impls.get("SourcePort"):
        failures.append("no shipped implementation derived for SourcePort")

    # 4. Both ratchets bite.
    try:
        _fail_coverage(["PhantomPort"], [])
    except SystemExit as exc:
        if exc.code != 1:
            failures.append("undocumented-port ratchet did not exit 1")
    else:
        failures.append("undocumented-port ratchet did not fire")
    try:
        _fail_coverage([], ["GhostPort"])
    except SystemExit as exc:
        if exc.code != 1:
            failures.append("dead-name ratchet did not exit 1")
    else:
        failures.append("dead-name ratchet did not fire")

    if failures:
        print("gen_ports_docs SELF-TEST FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(
        f"gen_ports_docs self-test OK — {len(ports)} ports derived (composed ports "
        "included), signatures keep annotations, implementations derived, and both "
        "ratchets (undocumented port / dead name) fire."
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="fail if regeneration would change files")
    ap.add_argument("--self-test", action="store_true", help="prove derivation + the two ratchets")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    pages = build()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    known = set(pages)
    changed = []
    for rel, content in sorted(pages.items()):
        path = _OUT_DIR / rel
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old != content:
            changed.append(rel)
            if not args.check:
                path.write_text(content, encoding="utf-8")
    # A group emptied by a regroup would otherwise leave an orphan page that
    # mkdocs --strict then flags as omitted-from-nav.
    for stale in sorted(_OUT_DIR.glob("*.md")):
        if stale.name not in known:
            changed.append(f"{stale.name} (orphan)")
            if not args.check:
                stale.unlink()

    if args.check and changed:
        print(
            f"Ports docs are stale — run scripts/gen_ports_docs.py. Drifted: {', '.join(changed)}",
            file=sys.stderr,
        )
        return 1
    if not args.check:
        print(f"Wrote {len(pages)} port reference pages to {_OUT_DIR.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
