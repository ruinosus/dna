#!/usr/bin/env python3
"""Generate ``docs/reference/parity-matrix.md`` from the parity fixtures.

The Python <-> TypeScript parity matrix is **generated, never hand-kept**: it
is emitted from the same fixtures that the CI parity suites read, so the
published page and the enforced contract can never disagree.

Primary source
    ``tests/parity-fixtures/port-surface-parity.json`` — the shared port /
    query-surface / hook-name manifest. Every member is a ``{py, ts}`` name
    pair; a one-sided member sets the other side to ``null`` and MUST carry a
    non-empty ``justification`` (undocumented drift reds both suites).

Secondary source
    ``packages/sdk-ts/kind-registry-parity.json`` — the class-backed Kind
    registry (``ts_aliases`` = both sides; ``py_only_allowlist`` = Python-only,
    documented). Descriptor-backed Kinds are byte-identical on both sides *by
    construction* and are intentionally NOT listed there, so they cannot drift.

The generator is pure stdlib, deterministic and idempotent: two runs over the
same fixtures produce byte-identical output. Wire it ahead of ``mkdocs build``
so the page regenerates on every docs build.

Usage::

    python scripts/gen_parity_matrix.py            # write the page
    python scripts/gen_parity_matrix.py --check     # exit 1 if the page is stale
    python scripts/gen_parity_matrix.py --stdout     # print, don't write
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# --- paths ------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
PORT_FIXTURE = os.path.join(_ROOT, "tests", "parity-fixtures", "port-surface-parity.json")
REGISTRY_FIXTURE = os.path.join(_ROOT, "packages", "sdk-ts", "kind-registry-parity.json")
OUT_PATH = os.path.join(_ROOT, "docs", "reference", "parity-matrix.md")

# --- legend -----------------------------------------------------------------

PRESENT = "✅"      # ✅ implemented on this side
ASYMMETRIC = "⚠️"   # ⚠️ intentionally absent — see the justification
NA = "➖"           # ➖ not applicable on this side


# --- helpers ----------------------------------------------------------------


def _cell(text: str) -> str:
    """Sanitise a string for a Markdown table cell (no pipes, single line)."""
    return " ".join(text.split()).replace("|", "\\|")


def _member_rows(members: list[dict]) -> tuple[list[str], int, int]:
    """Render member dicts as table rows. Returns (rows, shared, asymmetries)."""
    rows: list[str] = []
    shared = asymmetries = 0
    for m in members:
        py, ts = m.get("py"), m.get("ts")
        label = py or ts or "?"
        note = m.get("note")
        just = m.get("justification")
        if py and ts:
            shared += 1
            py_cell, ts_cell = PRESENT, PRESENT
            notes = f"ℹ️ {_cell(note)}" if note else ""
        elif py and not ts:
            asymmetries += 1
            py_cell, ts_cell = PRESENT, ASYMMETRIC
            notes = _cell(just or "Python-only (undocumented).")
        else:  # ts only
            asymmetries += 1
            py_cell, ts_cell = ASYMMETRIC, PRESENT
            notes = _cell(just or "TypeScript-only (undocumented).")
        rows.append(f"| `{label}` | {py_cell} | {ts_cell} | {notes} |")
    return rows, shared, asymmetries


def _table(members: list[dict]) -> tuple[list[str], int, int]:
    rows, shared, asym = _member_rows(members)
    out = ["| Member | Python | TypeScript | Notes |", "|---|:---:|:---:|---|", *rows]
    return out, shared, asym


# --- page sections ----------------------------------------------------------


def _emit(fixture: dict, registry: dict | None) -> str:
    tot_shared = tot_asym = 0
    # header is prepended after the body is built (it carries the summary counts)
    body: list[str] = []

    # 1. Ports -----------------------------------------------------------
    body.append("## Ports — the microkernel contract\n")
    body.append(
        "Each port is a `typing.Protocol` (Python) / `interface` (TypeScript). "
        "Rows are the contract members; a ✅ in both columns means the twin "
        "exists (Python members are `snake_case`, their TypeScript twins "
        "`camelCase`). The Python suite introspects the real Protocol members; "
        "the TypeScript suite is `keyof`-bound to the real interfaces, so `tsc` "
        "fails on drift.\n"
    )
    for name, port in fixture["ports"].items():
        doc = port.get("doc", "")
        body.append(f"### `{name}`\n")
        if doc:
            body.append(f"{_cell(doc)}\n")
        tbl, sh, asym = _table(port["members"])
        tot_shared += sh
        tot_asym += asym
        body.extend(tbl)
        body.append("")

    # 2. Blessed query surface ------------------------------------------
    bqs = fixture["blessed_query_surface"]
    body.append("## Blessed query surface — the public read API\n")
    body.append(
        "The `blessed` members are the ONE documented way to read manifest "
        "data; `deprecated` members still work but warn and are removed in "
        "1.0. Adding, renaming or removing any public member without editing "
        "the fixture reds the suite.\n"
    )
    for cls in ("ManifestInstance", "Kernel"):
        section = bqs.get(cls)
        if not section:
            continue
        body.append(f"### `{cls}` — blessed\n")
        tbl, sh, asym = _table(section.get("blessed", []))
        tot_shared += sh
        tot_asym += asym
        body.extend(tbl)
        body.append("")
        deprecated = section.get("deprecated") or []
        if deprecated:
            body.append(f"### `{cls}` — deprecated (removed in 1.0)\n")
            body.append("| Member | Python | TypeScript | Replacement |")
            body.append("|---|:---:|:---:|---|")
            for m in deprecated:
                py, ts = m.get("py"), m.get("ts")
                label = py or ts or "?"
                repl = _cell(m.get("replacement", ""))
                py_c = PRESENT if py else ASYMMETRIC
                ts_c = PRESENT if ts else ASYMMETRIC
                if py and ts:
                    tot_shared += 1
                else:
                    tot_asym += 1
                body.append(f"| `{label}` | {py_c} | {ts_c} | {repl} |")
            body.append("")
        # exact public surface — an unpaired set guard (casing differs; the
        # fixture pins each side member-for-member). Summarise, don't force a
        # fragile snake<->camel pairing.
        ps = section.get("public_surface")
        if isinstance(ps, dict) and "py" in ps and "ts" in ps:
            body.append(
                f"The exact public `{cls}` surface is pinned member-for-member "
                f"by the fixture: **{len(ps['py'])} Python** members and "
                f"**{len(ps['ts'])} TypeScript** members. Any public "
                "addition/removal/rename on either side without a matching "
                "fixture edit reds the suite.\n"
            )

    # 3. Hook names ------------------------------------------------------
    hooks = fixture.get("hook_names", {})
    hook_list = hooks.get("names", [])
    if hook_list:
        body.append("## Hook names — the shared event vocabulary\n")
        body.append(
            "The `HookRegistry` hook-name vocabulary is identical on both sides "
            "(event names are wire vocabulary, not API casing).\n"
        )
        body.append("| Hook | Python | TypeScript |")
        body.append("|---|:---:|:---:|")
        for h in hook_list:
            tot_shared += 1
            body.append(f"| `{h}` | {PRESENT} | {PRESENT} |")
        body.append("")

    # 4. Kinds registry --------------------------------------------------
    if registry:
        aliases = registry.get("ts_aliases", [])
        py_only = registry.get("py_only_allowlist", [])
        body.append("## Kind registry — class-backed Kinds\n")
        body.append(
            "Class-backed builtin Kinds registered on both runtimes. "
            "**Descriptor-backed Kinds** (`*/kinds/*.kind.yaml`, byte-identical "
            "Py↔TS package data) are byte-parity by construction and "
            "deliberately absent from this list — they cannot drift. "
            "`py_only_allowlist` Kinds are registered in Python (entry-points) "
            "and intentionally not yet ported to TypeScript.\n"
        )
        body.append("| Kind (alias) | Python | TypeScript | Notes |")
        body.append("|---|:---:|:---:|---|")
        for alias in aliases:
            tot_shared += 1
            body.append(f"| `{alias}` | {PRESENT} | {PRESENT} | |")
        for alias in py_only:
            tot_asym += 1
            body.append(
                f"| `{alias}` | {PRESENT} | {ASYMMETRIC} | "
                "Python-only (entry-point registered); documented in the "
                "registry allowlist, not yet ported to TypeScript. |"
            )
        body.append("")

    # 5. Excluded surfaces ----------------------------------------------
    excluded = fixture.get("excluded_surfaces", {})
    if excluded:
        body.append("## Excluded surfaces — deliberately not parity-tracked\n")
        body.append(
            "Surfaces where member parity is intentionally NOT enforced, each "
            "with a recorded reason. `➖` marks the side where the surface is "
            "absent or shaped differently on purpose.\n"
        )
        body.append("| Surface | Python | TypeScript | Reason |")
        body.append("|---|:---:|:---:|---|")
        for name, spec in excluded.items():
            py = spec.get("py")
            ts = spec.get("ts")
            py_c = PRESENT if py else NA
            ts_c = PRESENT if ts else NA
            reason = _cell(spec.get("justification", ""))
            body.append(f"| `{name}` | {py_c} | {ts_c} | {reason} |")
        body.append("")

    # --- assemble header + summary + body ------------------------------
    header = [
        "# Python ↔ TypeScript parity matrix",
        "",
        "!!! info \"Generated — not hand-kept\"",
        "",
        "    This page is **generated** by `scripts/gen_parity_matrix.py` from "
        "the same fixtures that the CI parity suites enforce",
        "    (`tests/parity-fixtures/port-surface-parity.json` and "
        "`packages/sdk-ts/kind-registry-parity.json`). The docs build "
        "regenerates it,",
        "    so the published matrix and the enforced contract cannot drift. "
        "Do not edit it by hand.",
        "",
        "DNA ships a Python SDK and a TypeScript SDK that are **behaviorally "
        "identical**. This matrix is the published proof — in the spirit of the "
        "OpenTelemetry spec-compliance matrix, it lists each contract member as "
        "a row and each language as a column, so \"1:1 parity\" is *shown*, not "
        "asserted.",
        "",
        "**Legend**",
        "",
        f"- {PRESENT} — implemented on this side.",
        f"- {ASYMMETRIC} — intentionally absent on this side; the asymmetry is "
        "documented (see the Notes column). Undocumented drift reds the parity "
        "suite in CI.",
        f"- {NA} — not applicable / shaped differently by design.",
        "",
        f"**Summary:** **{tot_shared}** shared members across the tracked "
        f"contracts, **{tot_asym}** documented asymmetries. Python is the "
        "semantic reference: a gap is closed by porting to TypeScript, or "
        "justified in the fixture — never by silence.",
        "",
    ]

    footer = [
        "## Behavioral proof — the conformance kit",
        "",
        "This matrix proves the two SDKs expose the **same surface**. That they "
        "**behave** the same is proven separately by the `dna.testing` "
        "conformance kits — source and reader/writer conformance suites that run "
        "the identical scenarios against both runtimes. See "
        "[Running the conformance kit](../getting-started/conformance-kit.md), "
        "and the guides on "
        "[reading document data](../guides/read-document-data.md) and "
        "[writing a source adapter](../guides/write-a-source-adapter.md) for the "
        "contracts these tables enforce.",
        "",
    ]

    out = header + body + footer
    text = "\n".join(out).rstrip() + "\n"
    # collapse any accidental >1 blank line for stable output
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def generate() -> str:
    with open(PORT_FIXTURE, encoding="utf-8") as fh:
        fixture = json.load(fh)
    registry = None
    if os.path.exists(REGISTRY_FIXTURE):
        with open(REGISTRY_FIXTURE, encoding="utf-8") as fh:
            registry = json.load(fh)
    return _emit(fixture, registry)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the committed page is stale (regenerate + diff)")
    ap.add_argument("--stdout", action="store_true", help="print to stdout, do not write")
    args = ap.parse_args()

    text = generate()

    if args.stdout:
        sys.stdout.write(text)
        return 0

    if args.check:
        try:
            with open(OUT_PATH, encoding="utf-8") as fh:
                current = fh.read()
        except FileNotFoundError:
            current = None
        if current != text:
            print(
                f"parity-matrix STALE: {os.path.relpath(OUT_PATH, _ROOT)} differs "
                "from the generator output. Run `python scripts/gen_parity_matrix.py`.",
                file=sys.stderr,
            )
            return 1
        print("parity-matrix: up to date")
        return 0

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote {os.path.relpath(OUT_PATH, _ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
