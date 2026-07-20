"""document_hash — golden lock on the canonical form and its digest.

``document_hash`` is the sync/dedup identity of a document: the canonical JSON
below (key order, separators, scalar rendering) and its sha256 are a WIRE
contract, not an implementation detail — a change silently invalidates every
stored hash. Each fixture pins the exact canonical string AND the digest.

History: these fixtures were mirrored by a TypeScript twin. The TypeScript SDK
was frozen (tag ``sdk-ts-final``); the canonical form is Python's to keep.
"""
import pytest
from dna.sync.hash import document_hash


FIXTURES = [
    {
        "doc": {"kind": "Genome", "name": "test", "spec": {"agents": ["bot"]}},
        "canonical": '{"kind": "Genome", "name": "test", "spec": {"agents": ["bot"]}}',
    },
    {
        "doc": {"kind": "Agent", "name": "bot", "spec": {"model": "gpt-4o", "skills": ["search"]}},
        "canonical": '{"kind": "Agent", "name": "bot", "spec": {"model": "gpt-4o", "skills": ["search"]}}',
    },
    {
        "doc": {"spec": {"description": "Web search"}, "name": "search", "kind": "Skill"},
        "canonical": '{"kind": "Skill", "name": "search", "spec": {"description": "Web search"}}',
    },
    {
        "doc": {"kind": "Agent", "name": "api", "spec": {"endpoint": "https://api.example.com:8080/v1"}},
        "canonical": '{"kind": "Agent", "name": "api", "spec": {"endpoint": "https://api.example.com:8080/v1"}}',
    },
    {
        "doc": {"kind": "Agent", "name": "tags", "spec": {"labels": "red, green, blue"}},
        "canonical": '{"kind": "Agent", "name": "tags", "spec": {"labels": "red, green, blue"}}',
    },
    {
        "doc": {"kind": "X", "name": "types", "spec": {"flag": True, "debug": False, "count": 42, "opt": None, "temp": 0.7}},
        "canonical": '{"kind": "X", "name": "types", "spec": {"count": 42, "debug": false, "flag": true, "opt": null, "temp": 0.7}}',
    },
    {
        "doc": {"kind": "X", "name": "deep", "spec": {"a": {"b": {"c": "val"}}, "empty_obj": {}, "empty_arr": []}},
        "canonical": '{"kind": "X", "name": "deep", "spec": {"a": {"b": {"c": "val"}}, "empty_arr": [], "empty_obj": {}}}',
    },
]


class TestHashGolden:
    @pytest.mark.parametrize("fixture", FIXTURES, ids=[f["doc"]["kind"] for f in FIXTURES])
    def test_matches_canonical(self, fixture):
        import hashlib
        expected = hashlib.sha256(fixture["canonical"].encode()).hexdigest()
        assert document_hash(fixture["doc"]) == expected

    def test_key_order_irrelevant(self):
        a = {"kind": "X", "name": "y", "spec": {"b": 2, "a": 1}}
        b = {"name": "y", "spec": {"a": 1, "b": 2}, "kind": "X"}
        assert document_hash(a) == document_hash(b)
