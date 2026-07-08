"""i-076 — the kernel_writes NOTIFY payload must carry the author.

The dna_outbox ROW always stored the actor/author, but the pg_notify
payload dropped it. The ObserverBus bridge (cognitive-api) reads author
from that payload to honor each hook's skip_if_authored_by_self /
skip_if_authored_by_any_hook loop guards. With author missing, every
cross-process event looked human-authored → guards defeated → scribe
writes drove a feedback loop that saturated kinds-api.

These lock the payload contract without needing a live Postgres.
"""
import json

from dna.adapters.postgres.source import _build_notify_payload


def _payload(**over):
    base = dict(
        outbox_id=42, scope="dna-development", tenant="", kind="LessonLearned",
        name="rem-foo", op="write", doc_version=3, author="hook:forgetting-tick",
    )
    base.update(over)
    return json.loads(_build_notify_payload(**base))


def test_payload_includes_author():
    d = _payload()
    assert d["author"] == "hook:forgetting-tick"


def test_payload_carries_all_identity_fields():
    d = _payload()
    assert d == {
        "id": 42, "scope": "dna-development", "tenant": "",
        "kind": "LessonLearned", "name": "rem-foo", "op": "write",
        "doc_version": 3, "author": "hook:forgetting-tick",
        # s-buswrite-class-substantive-cue — write_class rides the payload too.
        "write_class": "substantive",
    }


def test_payload_defaults_write_class_substantive():
    # Omitting write_class → "substantive" (back-compat for older writers).
    d = _payload()
    assert d["write_class"] == "substantive"


def test_payload_carries_cue_write_class():
    d = _payload(write_class="cue")
    assert d["write_class"] == "cue"


def test_none_author_serializes_as_empty_string():
    # The bridge does d.get("author", "") and treats "" as non-hook; a None
    # author must round-trip to "" (not the JSON literal null) so the bridge's
    # is_hook_authored check is well-defined.
    d = _payload(author=None)
    assert d["author"] == ""
