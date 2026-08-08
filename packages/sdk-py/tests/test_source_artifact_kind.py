"""``SourceArtifact`` — the record that makes "projection" a checkable claim.

The DNA Cloud assistant turns a file into typed instances. Those instances are
a projection: lossy and interpreted. This Kind is what stops "derived from"
being an assertion nobody can test.

Three properties carry the design, and each is pinned here because each is easy
to lose in a later edit that looks harmless:

1. **``sha256`` is required and is a real content address.** Without it the
   provenance claim is unfalsifiable, and an unfalsifiable provenance claim is
   worth less than none — it invites trust it has not earned. A value that is
   not 64 hex characters is refused rather than stored.

2. **The edge points FROM the artifact TO its derivations.** One upload
   commonly yields many instances; the fact "these came from one file" must be
   expressible once. The reverse shape (a ``source_ref`` field on each derived
   instance) would also force the agent to add that field to every schema it
   authors, and leave Kinds nobody authored unable to participate at all.

3. **The schema is closed.** ``additionalProperties: false`` means a caller
   cannot quietly attach a ``sas_token`` / ``signed_url`` next to ``uri``. The
   descriptor says ``uri`` is an identity and not a credential; a closed schema
   is what keeps that from being merely a comment.
"""
from __future__ import annotations

import pytest

from dna.kernel.kinds.registry import KindRegistry
from dna.kernel.source.descriptor_loader import load_descriptors

_API = "github.com/ruinosus/dna/artifact/v1"
_KIND = "SourceArtifact"

_GOOD_SHA = "a" * 64


@pytest.fixture
def port():
    """The registered port, through the same funnel the kernel uses."""
    registry = KindRegistry()
    registered = [
        registry.register_from_descriptor(raw)
        for raw in load_descriptors("dna.extensions.artifact")
    ]
    # ⚠️ This used to assert ``len(registered) == 1`` and take ``[0]``, which
    # froze the ANSWER (*how many* Kinds this package happens to ship) where the
    # QUESTION is *which* one this file tests. Adding ``KnowledgeChunk`` to the
    # same package broke it — correctly by its own words, and for a reason that
    # has nothing to do with SourceArtifact. Selecting by name makes a third
    # Kind here a non-event, while a MISSING SourceArtifact still fails, which
    # is the failure worth keeping.
    by_kind = {p.kind: p for p in registered}
    assert _KIND in by_kind, (
        f"{_KIND} is not registered by dna.extensions.artifact; "
        f"got {sorted(by_kind)}"
    )
    return by_kind[_KIND]


def _spec(**overrides):
    base = {"sha256": _GOOD_SHA, "uri": "blob://ws-abc/" + _GOOD_SHA}
    base.update(overrides)
    return base


def _validate(port, spec):
    """Validate a spec through the port's OWN seam, returning the error or None.

    ``parse()`` is where a declarative Kind validates — the same call the write
    path reaches. Asserting against a substitute validator would test the test's
    idea of the schema rather than the one the kernel enforces."""
    raw = {
        "apiVersion": _API,
        "kind": _KIND,
        "metadata": {"name": "artifact-under-test"},
        "spec": spec,
    }
    try:
        port.parse(raw)
    except Exception as exc:  # noqa: BLE001 — the refusal IS the result
        return exc
    return None


def test_the_kind_registers_under_its_own_namespace(port):
    """It is a first-class builtin, not a per-tenant authored Kind."""
    assert port.kind == _KIND
    assert port.api_version == _API


def test_a_content_address_is_required(port):
    """Drop ``sha256`` from ``required`` and this dies.

    An artifact record without one cannot be checked against any bytes, which
    is the single thing this Kind exists to make possible."""
    assert _validate(port, {"uri": "blob://ws-abc/x"}) is not None


def test_a_sha256_that_is_not_one_is_refused(port):
    """The pattern is the difference between a content ADDRESS and a string.

    Loosen it to a bare ``type: string`` and this dies — and the failure would
    be silent, because a wrong-shaped hash stores perfectly well and only
    fails much later, when someone tries to verify with it."""
    for bogus in ("not-a-hash", _GOOD_SHA.upper(), _GOOD_SHA[:63], _GOOD_SHA + "a"):
        assert _validate(port, _spec(sha256=bogus)) is not None, (
            f"{bogus!r} was accepted as a sha256"
        )


def test_the_derivations_hang_off_the_artifact(port):
    """One upload, many instances — stated once, on the artifact.

    This is the direction choice. Move the edge to a ``source_ref`` on each
    derived instance and this dies, along with the ability of any Kind the
    agent did not author to participate at all."""
    assert (
        _validate(
            port,
            _spec(derived_refs=[
                {"kind": "Invoice", "name": "inv-001"},
                {"kind": "Invoice", "name": "inv-002"},
            ]),
        )
        is None
    )


def test_an_artifact_with_nothing_extracted_yet_is_valid(port):
    """Stored, not yet read. An honest state, not an error — and the state every
    artifact passes through between upload and extraction."""
    assert _validate(port, _spec()) is None
    assert _validate(port, _spec(derived_refs=[])) is None


@pytest.mark.parametrize(
    "smuggled", ["sas_token", "signed_url", "access_token", "credential"]
)
def test_no_credential_can_be_smuggled_in_beside_the_uri(port, smuggled):
    """The descriptor says ``uri`` is an identity and never a credential. A
    CLOSED schema is what keeps that from being only a comment.

    Set ``additionalProperties: true`` and this dies — and the instance would
    then be able to carry its own access, so anyone the instance reaches would
    reach the original file with it."""
    assert _validate(port, _spec(**{smuggled: "sv=2024&sig=abc"})) is not None
