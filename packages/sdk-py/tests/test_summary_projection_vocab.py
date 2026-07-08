"""Summary projection vocabulary (Chunk 2 / Task 4 — spec D2).

Pins EACH of the 7 projection primitives + the exact real-class behaviors
of the 6 kinds that migrate to descriptors in lotes 2-3:

- autoagent-experiment: `{format, all_or_empty}` (passed/total → "" if either
  missing), `{path, truncate, default}` (commit[:7] or ""), `{path, round}`
  (avg_score round 4).
- autolab-run / eval-evolve-run: `{format, placeholder_defaults}` → "0/0" on
  an empty doc; `{path, round}` (cost round 4 with default 0).
- eval-evolve-experiment: `{path: applied_change.action}` nested walk.
- affect-palette / engram-policy: `{count_of: palette}` over a LIST.
- prompt-template: `{count_of: body}` over a STRING (body_length).
- memory-policy: `{paths, filter_falsy}` leaf-keyed + `{path, default: shared}`.

Plain (non-projection) values keep today's meaning (the projected default), so
the 23 shipped descriptors stay untouched. The TS twin
(`summary-projection-vocab.test.ts`) mirrors these expectations byte-for-byte.
"""

from __future__ import annotations

from typing import Any

import pytest

from dna.kernel.meta import DeclarativeKindPort
from dna.kernel.models import TypedKindDefinition


def _doc(spec: dict[str, Any]) -> Any:
    class _D:
        pass

    d = _D()
    d.spec = spec
    return d


def _port(summary: dict[str, Any], schema: dict[str, Any] | None = None) -> DeclarativeKindPort:
    raw = {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "x-record"},
        "spec": {
            "target_api_version": "github.com/ruinosus/dna/x/v1",
            "target_kind": "XRecord",
            "alias": "x-record",
            "origin": "github.com/ruinosus/dna/x",
            "storage": {"type": "yaml", "container": "x-records"},
            "schema": schema or {"type": "object", "properties": {}},
            "summary": summary,
        },
    }
    typed = TypedKindDefinition.from_raw(raw)
    return DeclarativeKindPort.from_typed(typed)


# --------------------------------------------------------------------------
# 1. Plain values (back-compat) — projected default
# --------------------------------------------------------------------------

def test_plain_value_is_projected_default() -> None:
    p = _port({"status": "pending", "program": ""})
    assert p.summary(_doc({"status": "running", "program": "foo"})) == {
        "status": "running",
        "program": "foo",
    }
    # Missing → declared default (today's behavior).
    assert p.summary(_doc({})) == {"status": "pending", "program": ""}


def test_bare_dict_doc_empty_spec() -> None:
    p = _port({"status": "pending"})
    # doc with no spec attr → empty spec → default.
    class _Bare:
        pass

    assert p.summary(_Bare()) == {"status": "pending"}


# --------------------------------------------------------------------------
# 2. count_of — list OR string; missing/None → 0
# --------------------------------------------------------------------------

def test_count_of_list() -> None:
    p = _port({"affect_count": {"count_of": "palette"}})
    assert p.summary(_doc({"palette": [1, 2, 3]})) == {"affect_count": 3}
    assert p.summary(_doc({"palette": []})) == {"affect_count": 0}
    # missing → 0
    assert p.summary(_doc({})) == {"affect_count": 0}
    # None → 0
    assert p.summary(_doc({"palette": None})) == {"affect_count": 0}


def test_count_of_string_body_length() -> None:
    p = _port({"body_length": {"count_of": "body"}})
    assert p.summary(_doc({"body": "hello"})) == {"body_length": 5}
    assert p.summary(_doc({"body": ""})) == {"body_length": 0}
    assert p.summary(_doc({})) == {"body_length": 0}


def test_count_of_non_str_list_target_is_zero() -> None:
    # PARITY PIN (Chunk 2 review): count_of's contract is "length of a
    # sequence". Over a NON-str/list target it must yield 0 in BOTH runtimes.
    # A bare len() in Python would element-count a dict and HARD CRASH on an
    # int/float (uncaught TypeError) — diverging from TS, which guards to 0.
    p = _port({"n": {"count_of": "target"}})
    # dict → 0 (NOT its key count)
    assert p.summary(_doc({"target": {"a": 1, "b": 2}})) == {"n": 0}
    # int → 0 (no crash)
    assert p.summary(_doc({"target": 42})) == {"n": 0}
    # float → 0
    assert p.summary(_doc({"target": 3.14})) == {"n": 0}


# --------------------------------------------------------------------------
# 3. path — dict-only walk; missing → None
# --------------------------------------------------------------------------

def test_path_nested_walk() -> None:
    p = _port({"applied_change": {"path": "applied_change.action"}})
    assert p.summary(_doc({"applied_change": {"action": "swap"}})) == {
        "applied_change": "swap"
    }
    # missing leaf → None
    assert p.summary(_doc({"applied_change": {}})) == {"applied_change": None}
    # missing parent → None
    assert p.summary(_doc({})) == {"applied_change": None}
    # parent present but None / falsy → None (eval-evolve-experiment class
    # returns None when applied_change is falsy).
    assert p.summary(_doc({"applied_change": None})) == {"applied_change": None}


def test_path_single_segment() -> None:
    p = _port({"program": {"path": "program"}})
    assert p.summary(_doc({"program": "foo"})) == {"program": "foo"}
    assert p.summary(_doc({})) == {"program": None}


# --------------------------------------------------------------------------
# 4. format — plain / all_or_empty / placeholder_defaults
# --------------------------------------------------------------------------

def test_format_plain_per_missing_blank() -> None:
    p = _port({"r": {"format": "{a}/{b}"}})
    assert p.summary(_doc({"a": 1, "b": 2})) == {"r": "1/2"}
    # plain: per-missing field → "" (so "/2", "1/", "/")
    assert p.summary(_doc({"b": 2})) == {"r": "/2"}
    assert p.summary(_doc({"a": 1})) == {"r": "1/"}
    assert p.summary(_doc({})) == {"r": "/"}


def test_format_all_or_empty_autoagent_passed_total() -> None:
    # autoagent: passed_fmt = f"{passed}/{total}" if BOTH not None else ""
    p = _port({"passed": {"format": "{passed}/{total}", "all_or_empty": True}})
    assert p.summary(_doc({"passed": 5, "total": 10})) == {"passed": "5/10"}
    # either missing → whole string ""
    assert p.summary(_doc({"passed": 5})) == {"passed": ""}
    assert p.summary(_doc({"total": 10})) == {"passed": ""}
    assert p.summary(_doc({})) == {"passed": ""}
    # present-but-None → also ""
    assert p.summary(_doc({"passed": None, "total": 10})) == {"passed": ""}
    # zero is NOT missing — 0/0 renders
    assert p.summary(_doc({"passed": 0, "total": 0})) == {"passed": "0/0"}


def test_format_placeholder_defaults_autolab_iter() -> None:
    # autolab: f"{spec.get('total_iterations_completed',0)}/{spec.get('max_iterations',0)}"
    p = _port(
        {
            "iter": {
                "format": "{total_iterations_completed}/{max_iterations}",
                "placeholder_defaults": {
                    "total_iterations_completed": 0,
                    "max_iterations": 0,
                },
            }
        }
    )
    assert p.summary(_doc({})) == {"iter": "0/0"}
    assert p.summary(_doc({"total_iterations_completed": 3, "max_iterations": 5})) == {
        "iter": "3/5"
    }
    # partial: missing uses its per-field default
    assert p.summary(_doc({"total_iterations_completed": 3})) == {"iter": "3/0"}
    # present-but-None uses the per-field default too
    assert p.summary(_doc({"total_iterations_completed": None, "max_iterations": 5})) == {
        "iter": "0/5"
    }


# --------------------------------------------------------------------------
# 5. truncate — string[:N]
# --------------------------------------------------------------------------

def test_truncate_with_default_commit() -> None:
    # autoagent: commit[:7] if commit else ""  → path+truncate+default:""
    p = _port({"commit": {"path": "commit", "truncate": 7, "default": ""}})
    assert p.summary(_doc({"commit": "abcdef1234567"})) == {"commit": "abcdef1"}
    # short string passes through
    assert p.summary(_doc({"commit": "abc"})) == {"commit": "abc"}
    # missing → default "" (truncate of "" is "")
    assert p.summary(_doc({})) == {"commit": ""}
    # present-but-None → default "" fires first, truncate of "" is ""
    assert p.summary(_doc({"commit": None})) == {"commit": ""}
    # empty string → default fires (default fires on missing OR None only,
    # NOT on ""), so "" stays "" and truncate of "" is ""
    assert p.summary(_doc({"commit": ""})) == {"commit": ""}


# --------------------------------------------------------------------------
# 6. round — numeric; None passes through; banker's rounding (== Python round)
# --------------------------------------------------------------------------

def test_round_avg_score() -> None:
    p = _port({"avg_score": {"path": "avg_score", "round": 4}})
    assert p.summary(_doc({"avg_score": 0.123456789})) == {"avg_score": 0.1235}
    # None passes through (default fires first if declared; here no default)
    assert p.summary(_doc({"avg_score": None})) == {"avg_score": None}
    assert p.summary(_doc({})) == {"avg_score": None}
    # int passes round fine
    assert p.summary(_doc({"avg_score": 1})) == {"avg_score": 1}


def test_round_with_default_cost() -> None:
    # autolab: round(spec.get("total_cost_usd", 0.0) or 0.0, 4)
    p = _port({"cost_usd": {"path": "total_cost_usd", "round": 4, "default": 0.0}})
    assert p.summary(_doc({"total_cost_usd": 1.234567})) == {"cost_usd": 1.2346}
    # missing → default 0.0 → round → 0.0
    assert p.summary(_doc({})) == {"cost_usd": 0.0}
    # None → default 0.0
    assert p.summary(_doc({"total_cost_usd": None})) == {"cost_usd": 0.0}


def test_round_bankers_half_to_even() -> None:
    # PIN the round rule: banker's rounding (round-half-to-even), matching
    # Python's built-in round(). 2.5 → 2, 3.5 → 4, 0.125@2 → 0.12, 0.135@2 → 0.14.
    p0 = _port({"v": {"path": "v", "round": 0}})
    assert p0.summary(_doc({"v": 2.5})) == {"v": 2}
    assert p0.summary(_doc({"v": 3.5})) == {"v": 4}
    assert p0.summary(_doc({"v": 0.5})) == {"v": 0}
    assert p0.summary(_doc({"v": 1.5})) == {"v": 2}
    p2 = _port({"v": {"path": "v", "round": 2}})
    assert p2.summary(_doc({"v": 0.125})) == {"v": 0.12}
    assert p2.summary(_doc({"v": 0.135})) == {"v": 0.14}


def test_round_2_drift_cases_match_cpython() -> None:
    # PARITY PIN (Chunk 2 review): round:2 is the spec's #1 stated parity risk
    # and where a naive TS rounder drifts from CPython. These are CPython's
    # exact round(x, 2) results, pinned identically in the TS twin:
    #   0.005 → 0.01 (stored 0.005000…0002, just over the half)
    #   0.025 → 0.03 (stored 0.025000…0004)
    #   2.675 → 2.67 (stored 2.67499…, just under the half)
    p2 = _port({"v": {"path": "v", "round": 2}})
    assert p2.summary(_doc({"v": 0.005})) == {"v": 0.01}
    assert p2.summary(_doc({"v": 0.025})) == {"v": 0.03}
    assert p2.summary(_doc({"v": 2.675})) == {"v": 2.67}


# --------------------------------------------------------------------------
# 7. default — fires on missing OR None (post-resolve)
# --------------------------------------------------------------------------

def test_default_missing_or_none() -> None:
    p = _port({"vis": {"path": "defaults.visibility", "default": "shared"}})
    assert p.summary(_doc({"defaults": {"visibility": "private"}})) == {"vis": "private"}
    # missing → default
    assert p.summary(_doc({})) == {"vis": "shared"}
    assert p.summary(_doc({"defaults": {}})) == {"vis": "shared"}
    # present-but-None → default fires (port canonical semantics, per spec D2)
    assert p.summary(_doc({"defaults": {"visibility": None}})) == {"vis": "shared"}
    # falsy-but-not-None (e.g. "") does NOT fire default
    assert p.summary(_doc({"defaults": {"visibility": ""}})) == {"vis": ""}


# --------------------------------------------------------------------------
# 8. filter_falsy — leaf-keyed, drops falsy
# --------------------------------------------------------------------------

def test_filter_falsy_leaf_keys() -> None:
    p = _port(
        {
            "applies_to": {
                "paths": [
                    "applies_to.scope",
                    "applies_to.owner",
                    "applies_to.memory_type",
                ],
                "filter_falsy": True,
            }
        }
    )
    # full: all present → leaf-keyed
    assert p.summary(
        _doc({"applies_to": {"scope": "acme", "owner": "bob", "memory_type": "episodic"}})
    ) == {"applies_to": {"scope": "acme", "owner": "bob", "memory_type": "episodic"}}
    # partial: falsy values DROPPED (not just null — "" and missing too)
    assert p.summary(
        _doc({"applies_to": {"scope": "acme", "owner": "", "memory_type": None}})
    ) == {"applies_to": {"scope": "acme"}}
    # empty → empty dict
    assert p.summary(_doc({})) == {"applies_to": {}}
    assert p.summary(_doc({"applies_to": {}})) == {"applies_to": {}}


def test_memory_policy_real_shape() -> None:
    # The full memory-policy summary: applies_to (filter_falsy) +
    # default_visibility (path+default "shared").
    p = _port(
        {
            "applies_to": {
                "paths": [
                    "applies_to.scope",
                    "applies_to.owner",
                    "applies_to.memory_type",
                ],
                "filter_falsy": True,
            },
            "default_visibility": {"path": "defaults.visibility", "default": "shared"},
        }
    )
    assert p.summary(_doc({})) == {"applies_to": {}, "default_visibility": "shared"}
    assert p.summary(
        _doc(
            {
                "applies_to": {"scope": "acme", "owner": "bob"},
                "defaults": {"visibility": "private"},
            }
        )
    ) == {
        "applies_to": {"scope": "acme", "owner": "bob"},
        "default_visibility": "private",
    }


# --------------------------------------------------------------------------
# 9. Unknown key in a projection object → ValueError at descriptor load
# --------------------------------------------------------------------------

def test_unknown_projection_key_raises_at_load() -> None:
    with pytest.raises(ValueError, match="unknown"):
        _port({"x": {"path": "a", "bogus": 1}})


def test_format_exclusive_of_others_raises() -> None:
    # format cannot combine with path/count_of/round/truncate/default.
    with pytest.raises(ValueError):
        _port({"x": {"format": "{a}", "round": 2}})
    with pytest.raises(ValueError):
        _port({"x": {"format": "{a}", "path": "a"}})


def test_count_of_exclusive_of_path_raises() -> None:
    with pytest.raises(ValueError):
        _port({"x": {"count_of": "a", "path": "a"}})


# --------------------------------------------------------------------------
# 10. Mixed full real-class summaries (full/partial/empty docs)
# --------------------------------------------------------------------------

def test_autoagent_experiment_full_summary() -> None:
    p = _port(
        {
            "program": {"path": "program", "default": ""},
            "commit": {"path": "commit", "truncate": 7, "default": ""},
            "status": {"path": "status", "default": ""},
            "passed": {"format": "{passed}/{total}", "all_or_empty": True},
            "avg_score": {"path": "avg_score", "round": 4},
            "cost_usd": {"path": "cost_usd"},
        }
    )
    full = p.summary(
        _doc(
            {
                "program": "agent-x",
                "commit": "abcdef1234567",
                "status": "done",
                "passed": 5,
                "total": 10,
                "avg_score": 0.987654,
                "cost_usd": 1.23,
            }
        )
    )
    assert full == {
        "program": "agent-x",
        "commit": "abcdef1",
        "status": "done",
        "passed": "5/10",
        "avg_score": 0.9877,
        "cost_usd": 1.23,
    }
    # empty doc
    assert p.summary(_doc({})) == {
        "program": "",
        "commit": "",
        "status": "",
        "passed": "",
        "avg_score": None,
        "cost_usd": None,
    }


def test_autolab_run_full_summary() -> None:
    p = _port(
        {
            "program": {"path": "program"},
            "status": {"path": "status", "default": "pending"},
            "iter": {
                "format": "{total_iterations_completed}/{max_iterations}",
                "placeholder_defaults": {
                    "total_iterations_completed": 0,
                    "max_iterations": 0,
                },
            },
            "cost_usd": {"path": "total_cost_usd", "round": 4, "default": 0.0},
            "best": {"path": "best_experiment"},
        }
    )
    assert p.summary(_doc({})) == {
        "program": None,
        "status": "pending",
        "iter": "0/0",
        "cost_usd": 0.0,
        "best": None,
    }
    assert p.summary(
        _doc(
            {
                "program": "p1",
                "status": "running",
                "total_iterations_completed": 2,
                "max_iterations": 8,
                "total_cost_usd": 0.987654,
                "best_experiment": "exp-3",
            }
        )
    ) == {
        "program": "p1",
        "status": "running",
        "iter": "2/8",
        "cost_usd": 0.9877,
        "best": "exp-3",
    }
