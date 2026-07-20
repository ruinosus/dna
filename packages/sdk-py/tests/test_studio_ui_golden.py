"""StudioUIMetadata — golden lock on ``to_dict()`` / ``resolve_label()``.

``StudioUIMetadata`` is presentation metadata that leaves the process (it is
serialized into Kind descriptors and served over the REST/MCP faces), so both
its dict projection and its locale-fallback rule are contracts. Every case in
``tests/goldens/studio-ui.json`` is asserted against the dataclass.

History: this began as a Py↔TS parity harness and the fixture lived in
``packages/sdk-ts``. The TypeScript SDK was frozen (tag ``sdk-ts-final``); the
canonical Python dataclass is what the fixture was really pinning, so the
fixture moved into this package and the suite stayed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dna.kernel.studio_ui import StudioUIMetadata

_FIXTURE = Path(__file__).parent / "goldens" / "studio-ui.json"


def _load_cases() -> list[dict]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return data["cases"]


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_to_dict_golden(case: dict) -> None:
    ui = StudioUIMetadata(**case["input"])
    assert ui.to_dict() == case["to_dict"]


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_resolve_label_golden(case: dict) -> None:
    ui = StudioUIMetadata(**case["input"])
    for locale, expected in case["resolve_label"].items():
        assert ui.resolve_label(locale) == expected, locale
