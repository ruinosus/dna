"""TDD for `dna sdlc produces` helpers (s-produces-cli).

Pure spec mutation: append/remove a {kind,name,role?} entry to spec.produces[],
deduped by (kind,name). The HTTP/session write is covered by dogfood; here we
pin the pure builders + the ref parsing.
"""
from __future__ import annotations

from dna_cli.sdlc_cmd import _append_produces, _remove_produces, _split_ref


def test_split_ref() -> None:
    assert _split_ref("Story/s-foo") == ("Story", "s-foo")
    assert _split_ref("Research/rsh-a-b") == ("Research", "rsh-a-b")


def test_append_creates_list() -> None:
    spec: dict = {"status": "todo"}
    _append_produces(spec, "Research", "rsh-x", role="investigation")
    assert spec["produces"][0]["kind"] == "Research"
    assert spec["produces"][0]["name"] == "rsh-x"
    assert spec["produces"][0]["role"] == "investigation"


def test_append_dedups_by_kind_name() -> None:
    spec: dict = {"produces": [{"kind": "Plan", "name": "plan-x"}]}
    _append_produces(spec, "Plan", "plan-x")
    assert len([p for p in spec["produces"] if p["name"] == "plan-x"]) == 1


def test_append_backfills_role_on_existing() -> None:
    spec: dict = {"produces": [{"kind": "Plan", "name": "plan-x"}]}
    _append_produces(spec, "Plan", "plan-x", role="explicit")
    assert spec["produces"][0]["role"] == "explicit"


def test_append_preserves_others() -> None:
    spec: dict = {"produces": [{"kind": "Spec", "name": "spec-a"}]}
    _append_produces(spec, "HtmlArtifact", "ha-b")
    assert {(p["kind"], p["name"]) for p in spec["produces"]} == {("Spec", "spec-a"), ("HtmlArtifact", "ha-b")}


def test_remove() -> None:
    spec: dict = {"produces": [{"kind": "Spec", "name": "spec-a"}, {"kind": "Plan", "name": "plan-b"}]}
    _remove_produces(spec, "Spec", "spec-a")
    assert {(p["kind"], p["name"]) for p in spec["produces"]} == {("Plan", "plan-b")}


def test_remove_absent_is_noop() -> None:
    spec: dict = {"produces": [{"kind": "Plan", "name": "plan-b"}]}
    _remove_produces(spec, "Spec", "nope")
    assert len(spec["produces"]) == 1
