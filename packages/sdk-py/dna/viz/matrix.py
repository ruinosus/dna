"""Matrix views — standalone functions operating on ManifestInstance.

Extracted from ManifestInstance to keep the kernel class focused.
1:1 parity with TypeScript viz/matrix.ts.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from dna.kernel.instance import ManifestInstance


def matrix(mi: ManifestInstance) -> dict[str, Any]:
    """Agent x dependency matrix showing which agent uses what.

    Returns:
        {
            "agents": ["swe-agent", "reviewer-agent"],
            "dependencies": {"Skill": ["pr-review", ...], "Guardrail": [...], ...},
            "matrix": {
                "swe-agent": {"pr-review": true, "safety": true, ...},
                "reviewer-agent": {"pr-review": true, ...}
            }
        }
    """
    tree = mi.dependency_tree()
    if not tree:
        return {"agents": [], "dependencies": {}, "matrix": {}}

    agents = sorted(tree.keys())
    # Collect all deps grouped by kind
    deps_by_kind: dict[str, set[str]] = {}
    for info in tree.values():
        for deps in info.get("depends_on", {}).values():
            for dep_name, dep_info in deps.items():
                kind = dep_info.get("kind", "Unknown")
                deps_by_kind.setdefault(kind, set()).add(dep_name)

    # Build matrix
    matrix_data: dict[str, dict[str, bool]] = {}
    for agent_name, info in tree.items():
        row: dict[str, bool] = {}
        for deps in info.get("depends_on", {}).values():
            for dep_name in deps:
                row[dep_name] = True
        matrix_data[agent_name] = row

    return {
        "agents": agents,
        "dependencies": {k: sorted(v) for k, v in sorted(deps_by_kind.items())},
        "matrix": matrix_data,
    }


def matrix_markdown(mi: ManifestInstance) -> str:
    """Agent x dependency matrix as a Markdown table."""
    data = matrix(mi)
    if not data["agents"]:
        return "No agents with dependencies found."

    # Flatten all dep names in kind order
    all_deps: list[tuple[str, str]] = []  # (kind, name)
    for kind, names in data["dependencies"].items():
        for name in names:
            all_deps.append((kind, name))

    # Header
    dep_headers = [f"{n}" for _, n in all_deps]
    header = "| Agent | " + " | ".join(dep_headers) + " |"
    sep = "|-------|" + "|".join([":---:" for _ in all_deps]) + "|"

    rows = []
    for agent in data["agents"]:
        cells = []
        for _, dep_name in all_deps:
            cells.append("\u25cf" if data["matrix"].get(agent, {}).get(dep_name) else " ")
        rows.append(f"| **{agent}** | " + " | ".join(cells) + " |")

    # Kind legend row
    kind_row = "| *Kind* | " + " | ".join(
        f"*{k[0].upper()}*" for k, _ in all_deps
    ) + " |"

    return "\n".join([header, sep, kind_row, *rows])
