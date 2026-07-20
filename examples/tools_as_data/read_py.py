#!/usr/bin/env python
"""Read the `generate-artifact` Tool surface via the DNA **Python** SDK.

    python examples/tools_as_data/read_py.py

Prints the agent-facing surface ({description, parameters}) as canonical JSON.
Run alongside `read_ts.ts` (the TypeScript twin) and diff the output: both
read the SAME Tool document (tools-demo/tools/generate-artifact.yaml) through
the byte-identical `Tool` Kind descriptor and produce byte-identical surfaces
— the governed Tool surface, read straight from the document.
"""
from __future__ import annotations

import json
import pathlib

from dna import load_tools

BASE_DIR = str(pathlib.Path(__file__).resolve().parent / ".dna")


def main() -> None:
    tools = load_tools("tools-demo", base_dir=BASE_DIR)
    surface = tools["generate-artifact"]
    out = {"description": surface.description, "parameters": surface.parameters}
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
