"""StudioUIMetadata parity — Python companion to packages/sdk-ts/tests/studio-ui.test.ts.

Both runtimes read the SAME shared fixture
(packages/sdk-ts/tests/fixtures/studio-ui-parity.json) and assert
byte-identical ``to_dict()`` / ``resolve_label()`` output, so the net-new TS
twin cannot drift from the canonical Python dataclass.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dna.kernel.studio_ui import StudioUIMetadata

_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "sdk-ts"
    / "tests"
    / "fixtures"
    / "studio-ui-parity.json"
)


def _load_cases() -> list[dict]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return data["cases"]


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_to_dict_parity(case: dict) -> None:
    ui = StudioUIMetadata(**case["input"])
    assert ui.to_dict() == case["to_dict"]


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_resolve_label_parity(case: dict) -> None:
    ui = StudioUIMetadata(**case["input"])
    for locale, expected in case["resolve_label"].items():
        assert ui.resolve_label(locale) == expected, locale
