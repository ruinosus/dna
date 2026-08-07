"""``dna rename`` — the operation i-114 left behind (i-118).

Driven against a REAL filesystem store (``DNA_BASE_DIR`` → a ``.dna/`` tree in
``tmp_path``), not a fake session, because the property being bought is that
*the result shows up in the diff of a pull request*: the assertions read the
YAML back off disk. A fake session would prove the plan and not the file.

The guards are written to the granularity of the DEFECT, and the defect is
known by measurement rather than by imagination. On 06/08/2026 a vocabulary
rename run with ``sed`` over 650 files produced four failures that every test in
the repo stayed green through, and every one of them is a property of token
replacement:

  1. a token replaced INSIDE a longer word;
  2. the right token replaced where it meant something else;
  3. agreement broken in prose;
  4. a label drifted from the value of the data.

``test_a_longer_name_that_contains_the_old_one_is_untouched`` is (1).
``test_a_polymorphic_value_resolving_elsewhere_is_reported_not_rewritten``
is (2). ``test_prose_mentioning_the_old_name_is_left_exactly_as_written``
covers (3) and (4) at once — both are consequences of editing text nobody
declared to be a reference.

⭐ THE MUTANT this file exists for is
``test_no_declared_reference_in_the_scope_still_names_the_old_instance``: it
re-derives the reference set from ``dna.kernel.kinds.relations`` — the SDK's
declaration, NOT ``rename_cmd``'s finding path — and reads the YAML off disk.
Break ``referring_relations``, ``_candidates``, the scope partition or
``_set_value`` and that assertion goes red, because it shares no code with any
of them. A guard that asked ``build_plan`` whether ``build_plan`` was complete
would be the guard-that-goes-green-while-going-blind this house has already
paid for three times.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml
from click.testing import CliRunner

from dna_cli.rename_cmd import rename

_API = "github.com/ruinosus/dna/sdlc/v1"
_HOME = "alpha"
_SIBLING = "beta"


# ── the store ───────────────────────────────────────────────────────────────


def _write(path: pathlib.Path, raw: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")


def _feature(name: str, **spec) -> dict:
    return {
        "apiVersion": _API, "kind": "Feature", "metadata": {"name": name},
        "spec": {
            "title": name, "status": "discovery",
            "description": f"the {name} feature", **spec,
        },
    }


def _story(name: str, **spec) -> dict:
    return {
        "apiVersion": _API, "kind": "Story", "metadata": {"name": name},
        "spec": {
            "title": name, "status": "todo",
            "description": f"the {name} story",
            "acceptance_criteria": ["it works"],
            "definition_of_done": ["it is done"],
            **spec,
        },
    }


def _epic(name: str, **spec) -> dict:
    return {
        "apiVersion": _API, "kind": "Epic", "metadata": {"name": name},
        "spec": {
            "title": name, "status": "planning",
            "description": f"the {name} epic", **spec,
        },
    }


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Two scopes, and every shape the rename has to tell apart.

    ``alpha`` (home)
      * ``f-old`` — the Feature being renamed.
      * ``f-old-extended`` — a DIFFERENT Feature whose name CONTAINS the one
        being renamed. Nothing about it may move.
      * ``s-points-at-old`` — a scalar declared relation (``Story.feature``).
      * ``s-points-at-longer`` — points at ``f-old-extended``.
      * ``s-mentions-in-prose`` — the old name inside ``description``, and the
        Portuguese sentence whose agreement ``sed`` broke. Not a reference.
      * ``e-1`` — ``Epic.features``, a MANY relation with the target at
        ordinal 1, so a rewrite that ignored the ordinal would corrupt it.

    ``beta`` (sibling)
      * ``s-foreign`` — names ``f-old`` from another owner's scope.
    """
    dna = tmp_path / ".dna"
    for scope in (_HOME, _SIBLING):
        _write(dna / scope / "manifest.yaml", {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Genome", "metadata": {"name": scope},
            "spec": {"description": f"{scope} test scope"},
        })

    _write(dna / _HOME / "features" / "f-old.yaml", _feature("f-old"))
    _write(dna / _HOME / "features" / "f-old-extended.yaml",
           _feature("f-old-extended"))
    _write(dna / _HOME / "stories" / "s-points-at-old.yaml",
           _story("s-points-at-old", feature="f-old"))
    _write(dna / _HOME / "stories" / "s-points-at-longer.yaml",
           _story("s-points-at-longer", feature="f-old-extended"))
    _write(dna / _HOME / "stories" / "s-mentions-in-prose.yaml", _story(
        "s-mentions-in-prose",
        description=(
            "A f-old documenta a nova regra. O f-old velho continua citado "
            "aqui em prosa, e f-old-extended também."
        ),
    ))
    _write(dna / _HOME / "epics" / "e-1.yaml",
           _epic("e-1", features=["f-old-extended", "f-old"]))
    _write(dna / _SIBLING / "stories" / "s-foreign.yaml",
           _story("s-foreign", feature="f-old"))

    monkeypatch.setenv("DNA_BASE_DIR", str(dna))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.setenv("DNA_SCOPE_DEFAULT", _HOME)
    return dna


@pytest.fixture
def runner():
    return CliRunner()


def _read(store: pathlib.Path, scope: str, container: str, name: str) -> dict:
    return yaml.safe_load(
        (store / scope / container / f"{name}.yaml").read_text(encoding="utf-8")
    )


def _run(runner, *args):
    result = runner.invoke(rename, list(args))
    assert result.exit_code == 0, result.output + str(result.exception)
    return result


# ── what it does ────────────────────────────────────────────────────────────


def test_the_instance_moves_and_keeps_the_id_it_already_had(store, runner):
    """The rename is a rename, not a delete-and-recreate.

    ``metadata.id`` surviving is the whole reason the DERIVED layer needs no
    repair: every ``dna_edges.to_id`` still points at the same identity, which
    is exactly the Kubernetes ``uid`` argument i-114 imported.
    """
    path = store / _HOME / "features" / "f-old.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["metadata"]["id"] = "abcdefgh2345"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    _run(runner, "Feature", "f-old", "f-new", "--scope", _HOME)

    assert not path.exists()
    after = _read(store, _HOME, "features", "f-new")
    assert after["metadata"]["name"] == "f-new"
    assert after["metadata"]["id"] == "abcdefgh2345"
    assert after["spec"]["title"] == "f-old"


def test_an_instance_with_no_id_gets_the_derived_one_not_a_fresh_mint(
    store, runner,
):
    """⭐ The rename must not be able to ERASE an identity.

    An instance that predates i-114 carries no ``metadata.id``. Left to the
    write pipeline, the write of the NEW name reads the store under the new
    name, finds nothing, and takes its "genuinely new instance" branch — a
    random mint. The old row is then deleted and what remains has a different
    identity: *changing the address erased the identity*, which is the sentence
    i-114 was filed against, reproduced by the command built to fix it.

    Asserted against ``derived_instance_id`` of the OLD coordinates rather than
    against a literal, so the value stays the one the Postgres backfill and the
    pipeline's own migration branch converge on. A hardcoded string here would
    pass while the three stores disagreed.
    """
    from dna.kernel.identity import derived_instance_id

    assert "id" not in _read(store, _HOME, "features", "f-old")["metadata"]
    _run(runner, "Feature", "f-old", "f-new", "--scope", _HOME)

    after = _read(store, _HOME, "features", "f-new")
    assert after["metadata"]["id"] == derived_instance_id(
        tenant=None, scope=_HOME, api_version=_API,
        kind="Feature", name="f-old",
    )


def test_a_scalar_declared_relation_is_repointed(store, runner):
    _run(runner, "Feature", "f-old", "f-new", "--scope", _HOME)
    story = _read(store, _HOME, "stories", "s-points-at-old")
    assert story["spec"]["feature"] == "f-new"


def test_a_many_relation_is_repointed_at_its_ordinal_only(store, runner):
    """``Epic.features`` is a list, and only position 1 named the target.

    Asserted as the WHOLE list rather than as ``"f-new" in features``: an
    implementation that replaced the field with a scalar, reordered it, or
    rewrote both entries would pass a membership check and has destroyed the
    instance.
    """
    _run(runner, "Feature", "f-old", "f-new", "--scope", _HOME)
    epic = _read(store, _HOME, "epics", "e-1")
    assert epic["spec"]["features"] == ["f-old-extended", "f-new"]


# ── defect (1): the token inside a longer word ──────────────────────────────


def test_a_longer_name_that_contains_the_old_one_is_untouched(store, runner):
    """``f-old-extended`` starts with ``f-old``. ``sed s/f-old/f-new/`` turns
    it into ``f-new-extended`` — an instance that does not exist — and this is
    the failure mode (1) that the measured 650-file rename actually shipped.

    Both halves are asserted: the Feature keeps its own name AND the Story
    pointing at it still points at it.
    """
    _run(runner, "Feature", "f-old", "f-new", "--scope", _HOME)
    assert (store / _HOME / "features" / "f-old-extended.yaml").exists()
    kept = _read(store, _HOME, "features", "f-old-extended")
    assert kept["metadata"]["name"] == "f-old-extended"
    story = _read(store, _HOME, "stories", "s-points-at-longer")
    assert story["spec"]["feature"] == "f-old-extended"


# ── defects (3) and (4): prose is not a reference ───────────────────────────


def test_prose_mentioning_the_old_name_is_left_exactly_as_written(store, runner):
    """Byte-for-byte, including the Portuguese sentence.

    The measured ``sed`` broke a verb into a non-word and broke gender
    agreement on screen, because it edited text that nobody declared to be a
    reference. This command does not edit prose — and does not search it
    either, which is why the string is compared whole instead of by absence of
    the old name: proving "the description was not touched" is a stronger and
    more honest claim than proving "the old name is gone from it".
    """
    before = _read(store, _HOME, "stories", "s-mentions-in-prose")
    _run(runner, "Feature", "f-old", "f-new", "--scope", _HOME)
    after = _read(store, _HOME, "stories", "s-mentions-in-prose")
    assert after["spec"]["description"] == before["spec"]["description"]
    assert "f-old documenta" in after["spec"]["description"]


# ── defect (2): the right token, meaning something else ─────────────────────


def test_a_polymorphic_value_resolving_elsewhere_is_reported_not_rewritten(
    store, runner,
):
    """``Membership.scope_ref`` is declared ``to: [Organization, Project]``.

    An Organization and a Project may legally share a name, and the write path
    resolves the value by probing the declared targets IN ORDER and taking the
    first hit — so ``scope_ref: shared-name`` on this store points at the
    ORGANIZATION. Renaming the PROJECT must therefore leave it alone: the
    string matches, the reference does not. That gap between "the token is
    there" and "the token means this" is failure mode (2) of the measured
    ``sed``, and the only thing that closes it is replaying the resolution
    instead of comparing strings.
    """
    api = "github.com/ruinosus/dna/portfolio/v1"
    # All three portfolio Kinds are TENANTED, so they live on the tenant lane.
    root = store / "tenants" / "t1" / "scopes" / _HOME

    def _doc(kind: str, name: str, spec: dict) -> dict:
        return {
            "apiVersion": api, "kind": kind, "metadata": {"name": name},
            "spec": spec,
        }

    _write(root / "organizations" / "shared-name.yaml",
           _doc("Organization", "shared-name",
                {"name": "Shared", "slug": "shared-name"}))
    _write(root / "projects" / "shared-name.yaml",
           _doc("Project", "shared-name",
                {"name": "Shared", "slug": "shared-name"}))
    _write(root / "memberships" / "m-1.yaml", _doc(
        "Membership", "m-1",
        {"user": "u-1", "scope_type": "org",
         "scope_ref": "shared-name", "role": "admin"},
    ))

    result = _run(runner, "Project", "shared-name", "p-renamed",
                  "--scope", _HOME, "--tenant", "t1")

    membership = yaml.safe_load(
        (root / "memberships" / "m-1.yaml").read_text(encoding="utf-8")
    )
    assert membership["spec"]["scope_ref"] == "shared-name"
    assert "left alone" in result.output
    assert "Organization/shared-name" in result.output
    # The Project itself still moved — the skip is about the REFERENCE.
    assert (root / "projects" / "p-renamed.yaml").exists()


# ── the sibling scope: reported, never touched ──────────────────────────────


def test_a_reference_from_a_sibling_scope_is_listed_and_left_alone(store, runner):
    """Another scope is another owner. The list IS the deliverable there — so
    both halves are asserted: the file is byte-identical, AND the human was
    told, by scope and by field."""
    before = (store / _SIBLING / "stories" / "s-foreign.yaml").read_text(
        encoding="utf-8"
    )
    result = _run(runner, "Feature", "f-old", "f-new", "--scope", _HOME)
    after = (store / _SIBLING / "stories" / "s-foreign.yaml").read_text(
        encoding="utf-8"
    )
    assert after == before
    assert _SIBLING in result.output
    assert "s-foreign" in result.output
    assert "spec.feature" in result.output


# ── --dry-run: the plan, and not one byte ───────────────────────────────────


def test_dry_run_writes_nothing_and_prints_the_same_plan(store, runner):
    """The promise is that the result appears in a PR diff, so the preview has
    to be the plan itself rather than a summary of it — same rows, same fields,
    same ordinals — and it must leave the tree untouched."""
    snapshot = {
        p: p.read_text(encoding="utf-8")
        for p in store.rglob("*.yaml")
    }
    dry = _run(runner, "Feature", "f-old", "f-new", "--scope", _HOME,
               "--dry-run", "--json")
    assert {p: p.read_text(encoding="utf-8") for p in store.rglob("*.yaml")} \
        == snapshot

    import json

    planned = json.loads(dry.output)
    assert planned["dry_run"] is True
    real = _run(runner, "Feature", "f-old", "f-new", "--scope", _HOME, "--json")
    done = json.loads(real.output)
    assert done["rewrite"] == planned["rewrite"]
    assert done["foreign"] == planned["foreign"]


# ── the refusals ────────────────────────────────────────────────────────────


def test_renaming_onto_a_name_that_already_exists_is_refused(store, runner):
    """A verdict about the REQUEST, not about the store: the write would have
    worked, and it would have merged two instances into one."""
    result = runner.invoke(
        rename, ["Feature", "f-old", "f-old-extended", "--scope", _HOME],
    )
    assert result.exit_code != 0
    assert "already exists" in result.output
    # And nothing moved on the way to refusing.
    assert (store / _HOME / "features" / "f-old.yaml").exists()
    assert _read(store, _HOME, "features", "f-old-extended")["spec"]["title"] \
        == "f-old-extended"


def test_renaming_an_instance_that_does_not_exist_is_refused(store, runner):
    result = runner.invoke(
        rename, ["Feature", "f-ghost", "f-new", "--scope", _HOME],
    )
    assert result.exit_code != 0
    assert "no Feature named" in result.output


def test_renaming_an_unregistered_kind_is_refused(store, runner):
    """Without the declarations there is no model saying what points at the
    instance, so the operation would degrade into a file move."""
    result = runner.invoke(
        rename, ["Nonesuch", "a", "b", "--scope", _HOME],
    )
    assert result.exit_code != 0
    assert "no Kind named" in result.output


def test_renaming_onto_a_traversing_name_is_refused(store, runner):
    """The kernel's own path-component rule, reached through this door.

    Reused rather than re-implemented: ``validate_instance_name`` is where the
    rule lives, and a second spelling of it here is how two doors drift.
    """
    result = runner.invoke(
        rename, ["Feature", "f-old", "../escaped", "--scope", _HOME],
    )
    assert result.exit_code != 0
    assert "contains '/'" in result.output
    assert (store / _HOME / "features" / "f-old.yaml").exists()


def test_renaming_to_the_same_name_is_refused(store, runner):
    result = runner.invoke(
        rename, ["Feature", "f-old", "f-old", "--scope", _HOME],
    )
    assert result.exit_code != 0
    assert "already called that" in result.output


def test_a_bundle_kind_is_refused_rather_than_half_moved(store, runner):
    """``Spec`` is stored as a bundle DIRECTORY. Read + write + delete carries
    the envelope and not the files, so running it would move the instance and
    destroy its entries — refusing is the only honest answer this slice has."""
    result = runner.invoke(
        rename, ["Spec", "sp-a", "sp-b", "--scope", _HOME],
    )
    assert result.exit_code != 0
    assert "BUNDLE" in result.output


def test_the_refusals_are_kernel_refusals_not_capability_refusals():
    """The family matters, and the two are not interchangeable.

    Every refusal this command raises is a verdict about the REQUEST — the
    store could have done it, and policy said no — so the remedy is a different
    call. A ``CapabilityRefusal`` would send the caller looking for a different
    deployment, which would not help: the same answer travels with the data.

    Derived from the errors module rather than restated, so a re-parenting of
    either class in the SDK turns this red instead of leaving a stale comment.
    """
    from dna.kernel.errors import (
        CapabilityRefusal, InstanceNameTaken, InvalidInstanceName,
        KernelRefusal,
    )

    for refusal in (InstanceNameTaken, InvalidInstanceName):
        assert issubclass(refusal, KernelRefusal)
        assert not issubclass(refusal, CapabilityRefusal)


# ── the reach of the mechanism, stated honestly ─────────────────────────────


def test_an_undeclared_reference_field_is_reported_not_silently_missed(
    store, runner,
):
    """``Issue.related_feature`` holds a Feature name and declares no relation.

    The kernel does not resolve it, so this command cannot reach it — and the
    difference between "nothing points at this" and "something points at this
    and never said so" is the whole value of saying it out loud. The remedy is
    one line of ``spec.relations`` and a re-run.
    """
    result = _run(runner, "Feature", "f-old", "f-new", "--scope", _HOME)
    assert "WITHOUT" in result.output
    assert "Issue.spec.related_feature" in result.output


def test_prose_is_declared_unsearched_rather_than_silently_skipped(store, runner):
    """The report must name the territory it did not enter.

    A command that simply says nothing about prose reads as "there was none",
    which is the confident-empty-answer this codebase treats as a defect. It
    hands over ``git grep`` instead of a substring list, because a substring
    list's obvious next step is the ``sed`` this command replaces.
    """
    result = _run(runner, "Feature", "f-old", "f-new", "--scope", _HOME)
    assert "neither rewritten nor searched" in result.output
    assert "git grep f-old" in result.output


# ── ⭐ the mutant ────────────────────────────────────────────────────────────


def _authored_references_to(
    dna: pathlib.Path, scope: str, name: str,
) -> list[tuple[str, str, str]]:
    """Every DECLARED relation value in ``scope`` that equals ``name``.

    Re-derived from the SDK's ``relations_of`` and read straight off disk —
    deliberately sharing NO code with ``rename_cmd``. If the command's registry
    walk, its candidate enumeration, its scope partition or its write-back is
    wrong, this sees it; if it merely disagreed with the command's own idea of
    what a reference is, it would see nothing, which is the guard going green
    while going blind.
    """
    from dna.kernel import Kernel
    from dna.kernel.kinds.relations import relation_values, relations_of

    kernel = Kernel.auto()
    by_container: dict[str, list] = {}
    for port in kernel.kind_ports():
        storage = getattr(port, "storage", None)
        container = getattr(storage, "container", None)
        if isinstance(container, str) and relations_of(port):
            by_container.setdefault(container, []).append(port)

    found: list[tuple[str, str, str]] = []
    for container, ports in by_container.items():
        for path in sorted((dna / scope / container).glob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            spec = raw.get("spec") or {}
            for port in ports:
                if raw.get("kind") != port.kind:
                    continue
                for rel in relations_of(port).values():
                    if not rel.resolved:
                        continue
                    for value in relation_values(rel, spec):
                        if value == name:
                            found.append((port.kind, path.stem, rel.name))
    return found


def test_the_fixture_really_does_hold_references_before_the_rename(store):
    """The mutant guard's own witness. Without this, a bug that made
    ``_authored_references_to`` find nothing would make the assertion below
    pass vacuously — the way eleven tests in this repo once passed for the
    wrong reason."""
    found = _authored_references_to(store, _HOME, "f-old")
    assert ("Story", "s-points-at-old", "feature") in found
    assert ("Epic", "e-1", "features") in found


def test_no_declared_reference_in_the_scope_still_names_the_old_instance(
    store, runner,
):
    """⭐ THE assertion: an authored reference the rename did not reach is red.

    Not "the ones I listed were rewritten" — that would only re-assert the
    plan. This walks the scope from the DECLARATIONS and demands that the old
    name has stopped being a reference target anywhere in it.
    """
    _run(runner, "Feature", "f-old", "f-new", "--scope", _HOME)
    assert _authored_references_to(store, _HOME, "f-old") == []
    # …and it landed on the new name rather than merely disappearing: a rename
    # that erased the field would also satisfy the line above.
    now = _authored_references_to(store, _HOME, "f-new")
    assert ("Story", "s-points-at-old", "feature") in now
    assert ("Epic", "e-1", "features") in now


def test_the_sibling_scope_reference_is_still_there_and_still_dangling(
    store, runner,
):
    """The other half of the same mutant, and it must NOT be repaired.

    The rename is deliberately incomplete across scopes, and a future change
    that quietly extended its reach would look like an improvement. It is not:
    it would edit a file the PR's reviewer never opened.
    """
    _run(runner, "Feature", "f-old", "f-new", "--scope", _HOME)
    assert _authored_references_to(store, _SIBLING, "f-old") == [
        ("Story", "s-foreign", "feature"),
    ]


# ── the registry walk, on its own ───────────────────────────────────────────


def test_referring_relations_is_derived_and_excludes_the_unresolvable():
    """Both conditions, because dropping either is a silent behaviour change.

    ``Story.feature`` names Feature and is resolvable → in. ``Story.spec_refs``
    names Spec, not Feature → out (a relation is not "any relation on a Kind
    that has one"). ``Story.produces`` is ``to: '*'`` — declared, real, and NOT
    resolved by the kernel — so it is out too: the command cannot know that
    such a value addresses this instance rather than something that merely
    looks like it.
    """
    from dna.kernel import Kernel

    from dna_cli.rename_cmd import referring_relations

    kernel = Kernel.auto()
    pairs = {(k, r.name) for k, r in referring_relations(kernel, "Feature")}
    assert ("Story", "feature") in pairs
    assert ("Epic", "features") in pairs
    assert ("Story", "spec_refs") not in pairs
    assert not any(name == "produces" for _, name in pairs)
    # And every pair it DID return is resolvable + actually names Feature.
    for kind, rel in referring_relations(kernel, "Feature"):
        assert rel.resolved
        assert "Feature" in rel.to
        assert isinstance(kind, str)
