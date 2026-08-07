"""``dna new kind`` — the slice-5 command of ``spec-solucao-como-template``.

⭐ **What this file is guarding is mostly a NEGATIVE**, and that shapes every
assertion in it. The spec measured the founder's premise and refused half of
it: a `record` Kind is already one YAML file and the portal already renders 85
Kinds from one generic component, so "make Kinds faster" was spent, and spent
better. What was left was a missing door — and the danger of a missing door is
that it gets built as a second ROOM.

So the mutant this file is written against is not "the command is broken". It
is **"the command grew its own reading of something the core already reads"** —
its own KindDefinition envelope, its own refusal list, its own copy of the
trait vocabulary, its own default for ``plane``. Each of those mutants leaves
every naive test green, because a hand-rolled envelope produces a file that
looks right on the day it is written.

Each class below names the mutant it kills.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from dna_cli.new_cmd import new

_GENOME = (
    "apiVersion: github.com/ruinosus/dna/v1\n"
    "kind: Genome\n"
    "metadata:\n  name: {n}\n"
    "spec:\n  scope: {n}\n"
)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A filesystem store with a ``loja`` scope AND the ``_lib`` registry scope.

    ``_lib`` is here because authoring READS the ``KindNamespace`` claim
    registry before it mints — measured, and it is why
    :class:`TestSemRegistro` exists as its own case with ``_lib`` deliberately
    absent."""
    base = tmp_path / ".dna"
    for name in ("loja", "_lib"):
        (base / name).mkdir(parents=True)
        (base / name / "manifest.yaml").write_text(
            _GENOME.format(n=name), encoding="utf-8")
    monkeypatch.setenv("DNA_SOURCE_URL", f"file://{base.resolve()}")
    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    monkeypatch.setenv("DNA_TENANT", "acme")
    return base


def _run(runner, *args):
    return runner.invoke(new, list(args), catch_exceptions=False)


def _kind_files(base: Path) -> list[Path]:
    return sorted((base / "loja" / "kinds").rglob("KIND.yaml"))


def _claims(base: Path) -> list[Path]:
    return sorted((base / "_lib").rglob("*.yaml"))


# ── the mutant: a SECOND authoring path ──────────────────────────────────────


class TestUmaSoPortaDeAutoria:
    """MUTANT: ``new_cmd`` builds its own ``KindDefinition`` envelope.

    It would pass any test that only looks at the file that lands, because a
    hand-rolled envelope is easy to make look right — and it would silently
    lose the CamelCase path guard, the meta-schema check, the
    relation/schema contradiction check, the namespace gate and the
    ``approved: false`` invariant, each of which lives in
    ``author_kind_impl`` and in no other place.

    So the assertion is not about the file. It is that **nothing lands when
    the impl does not write it**: the spy below answers without delegating,
    and if a byte still reaches disk there is a second path.
    """

    def test_the_write_comes_from_author_kind_impl_and_nowhere_else(
        self, runner, store, monkeypatch,
    ):
        seen: list[dict] = []

        async def _spy(live, **kwargs):
            seen.append(kwargs)
            return {"namespace": "ws-dead.dna.local", "kind": kwargs["kind"],
                    "name": "ws-dead.dna.local--" + kwargs["kind"],
                    "approved": False, "proposed_by": "x", "version": "1",
                    "schema": kwargs["schema"], "relations": None, "plane": None}

        monkeypatch.setattr(
            "dna.application.kind_authoring.author_kind_impl", _spy)
        r = _run(runner, "kind", "Contrato", "--scope", "loja",
                 "-d", "Um contrato", "-f", "titulo:string!")
        assert r.exit_code == 0, r.output
        assert len(seen) == 1, "the command must reach the shared door exactly once"
        assert _kind_files(store) == [], (
            "a KIND.yaml landed while the authoring door was stubbed out — "
            "there is a second path writing the envelope by hand"
        )

    def test_what_the_cli_parsed_is_what_the_door_receives(
        self, runner, store, monkeypatch,
    ):
        """The parsing IS the whole command, so it is the whole contract.

        Every value below is one the door validates and this file does not:
        the Kind name (a path segment), the schema (meta-schema), the
        relations (normalizer + contradiction check), the plane (registry
        vocabulary). A mutant that "helpfully" normalized any of them here
        would move a refusal away from the door that owns it."""
        seen: list[dict] = []

        async def _spy(live, **kwargs):
            seen.append(kwargs)
            return {"namespace": "ws-dead.dna.local", "kind": kwargs["kind"],
                    "name": "n", "approved": False, "proposed_by": None,
                    "version": "1", "schema": kwargs["schema"],
                    "relations": None, "plane": None}

        monkeypatch.setattr(
            "dna.application.kind_authoring.author_kind_impl", _spy)
        r = _run(
            runner, "kind", "Apolice", "--scope", "loja",
            "-d", "Uma apolice", "-f", "numero:string!=O numero",
            "-f", "valor:number",
            "--relation", "contratos=Contrato:many",
            "--trait", "record.append-only",
            "--presentation", "name,numero",
            "--plane", "record", "--workspace", "acme",
        )
        assert r.exit_code == 0, r.output
        kw = seen[0]
        assert kw["kind"] == "Apolice"
        assert kw["tenant"] == "acme"
        assert kw["traits"] == ["record.append-only"]
        assert kw["presentation"] == ["name", "numero"]
        assert kw["plane"] == "record"
        assert kw["relations"] == {
            "contratos": {"to": "Contrato", "cardinality": "many"}}
        assert kw["schema"] == {
            "type": "object",
            "description": "Uma apolice",
            "properties": {
                "numero": {"type": "string", "description": "O numero"},
                "valor": {"type": "number"},
                # Declared HERE because the relation named a field nobody
                # declared — see `_kind_schema`. Its type is the cardinality's
                # mechanical consequence, which is the same rule
                # `schema_contradictions` checks.
                "contratos": {"type": "array", "items": {"type": "string"},
                              "description": "Points at Contrato."},
            },
            "required": ["numero"],
        }

    def test_the_declaration_lands_as_a_real_kinddefinition_instance(
        self, runner, store,
    ):
        """The end-to-end half: a real store, a real write, a real file.

        Pinned on the fields the DOOR derives and this command never passes —
        ``alias``, ``origin``, ``target_api_version``, ``storage.container``.
        A second path would have had to invent all four, and the first thing a
        hand-rolled envelope gets wrong is that it invents them differently."""
        r = _run(runner, "kind", "Contrato", "--scope", "loja",
                 "-d", "Um contrato", "-f", "titulo:string!")
        assert r.exit_code == 0, r.output
        from dna._yaml import safe_load

        files = _kind_files(store)
        assert len(files) == 1
        doc = safe_load(files[0].read_text(encoding="utf-8"))
        assert doc["kind"] == "KindDefinition"
        spec = doc["spec"]
        assert spec["target_kind"] == "Contrato"
        assert spec["target_api_version"].endswith("/v1")
        assert spec["origin"] in spec["target_api_version"]
        assert spec["alias"].endswith("-contrato")
        assert spec["storage"] == {"type": "yaml", "container": "contratos"}
        assert spec["schema"]["properties"]["titulo"] == {"type": "string"}
        assert spec["schema"]["required"] == ["titulo"]


class TestInerteAteAprovar:
    """MUTANT: the command learns to approve what it authors.

    It never can — ``author_kind_impl`` builds the spec field by field and has
    no key for ``approved_by`` — but a CLI that PRINTED "created" without
    saying "inert" is the same defect one layer up: the author walks away
    believing the Kind works, and finds out when their first instance is
    accepted with no validation at all."""

    def test_nothing_is_approved_and_the_output_says_so(self, runner, store):
        r = _run(runner, "kind", "Contrato", "--scope", "loja")
        assert r.exit_code == 0, r.output
        from dna._yaml import safe_load

        spec = safe_load(_kind_files(store)[0].read_text(encoding="utf-8"))["spec"]
        assert "approved_by" not in spec and "approved_at" not in spec
        assert "approved    false" in r.output
        assert "human" in r.output


# ── the mutant: the ask stops being asked ────────────────────────────────────


class TestOPedidoDoTrait:
    """MUTANT: the trait vocabulary is typed into ``--help`` as a literal, or
    the slot is dropped in a rewrite.

    This is the exact defect slice 4 of the taxonomy spec measured and fixed
    one door over: of 47 descriptors, 47 declared ``plane`` and 8 declared
    ``traits``, because ``plane`` was asked for and ``traits`` was not.
    Coverage follows the ask. A hardcoded list passes every test written the
    day it is pasted and goes stale, silently, on the next registration — so
    the assertion is derived from the LIVE registry, never from a fixture."""

    def test_every_registered_trait_is_in_the_help(self, runner):
        from dna.kernel.kinds.traits import known_traits

        help_text = _run(runner, "kind", "--help").output
        registered = sorted(known_traits())
        assert registered, "no traits registered — this guard would be vacuous"
        missing = [name for name in registered if name not in help_text]
        assert not missing, (
            f"{len(missing)} registered trait(s) absent from `dna new kind "
            f"--help`: {missing}. The ask is PROJECTED from the registry "
            f"(`trait_ask`); a copy in the source goes stale in silence, which "
            f"is how `traits` reached 17% coverage the first time"
        )

    def test_a_trait_registered_now_reaches_the_help_now(self, runner, monkeypatch):
        """The mutant the previous test cannot see: a literal that HAPPENS to
        list every trait today. Register one more and a copy stops answering."""
        from dna.kernel.kinds import traits as traits_mod

        real = traits_mod.known_traits

        def _plus_one():
            return {**real(), "invented.for.this.test": "A trait nobody shipped."}

        monkeypatch.setattr(traits_mod, "known_traits", _plus_one)
        monkeypatch.setattr(traits_mod, "describe_traits", lambda **kw: (
            "\n".join(f"{kw.get('indent', '    ')}{n}" for n in _plus_one())))
        # The help is built per call (`_kind_help` runs at decoration, so the
        # command object is re-made here the same way the module does it).
        from dna_cli.new_cmd import _kind_help

        assert "invented.for.this.test" in _kind_help()

    def test_a_template_without_the_slot_refuses_instead_of_shipping_silently(
        self, monkeypatch,
    ):
        """The third mutant: somebody rewrites the help and drops the slot.

        A plain ``.replace`` on a template with no slot is a silent no-op — the
        command ships, the ask is gone, and nothing fails. So the absence
        refuses, the same way ``splice_trait_ask`` refuses one door over."""
        import dna_cli.new_cmd as mod

        monkeypatch.setattr(mod, "_KIND_HELP_TEMPLATE", "no slot here")
        with pytest.raises(RuntimeError, match="trait"):
            mod._kind_help()

    def test_asking_is_not_requiring(self, runner, store):
        """§8.4 — a Kind that declares no trait must still be born.

        The constant is the founder's and this command must not move it: the
        assertion pins BOTH halves, because a command that refused a
        trait-less Kind while the constant stayed ``False`` would have flipped
        the policy without touching the value that records it."""
        from dna.kernel.kinds.traits import TRAIT_REQUIRED_ENFORCED

        assert TRAIT_REQUIRED_ENFORCED is False
        r = _run(runner, "kind", "Contrato", "--scope", "loja")
        assert r.exit_code == 0, r.output
        from dna._yaml import safe_load

        spec = safe_load(_kind_files(store)[0].read_text(encoding="utf-8"))["spec"]
        assert spec["traits"] == []
        # And it is not refused SILENTLY either — the author is told what the
        # silence costs, which is the difference between an ask and a shrug.
        assert "no trait" in r.output


# ── the mutant: a second reading of the plane default ────────────────────────


class TestOPlanoEPerguntado:
    """MUTANT: the report prints the word ``record`` from a literal.

    i-123 moved the default and — the part a literal would miss — the default
    is not blind: ``default_plane`` reads ``COMPOSITION_SIGNALS`` first,
    because a descriptor carrying one of them is REFUSED next to ``record`` at
    registration. A literal is right today and reports a plane the store does
    not have on the day the decision moves. This monkeypatches the core's
    answer and requires the report to follow it."""

    def test_the_report_follows_the_cores_answer(self, runner, store, monkeypatch):
        import dna.kernel.kinds.base as base_mod

        monkeypatch.setattr(base_mod, "default_plane", lambda raw: "composition")
        r = _run(runner, "kind", "Contrato", "--scope", "loja", "--dry-run")
        assert r.exit_code == 0, r.output
        assert "plane       composition" in r.output

    def test_declared_beats_default_and_is_stored_as_declared(self, runner, store):
        """A DECLARED plane is stored; an undeclared one is not written at all.

        That asymmetry is the core's (``_checked_plane``), and it exists so
        "the author chose ``record``" stays distinguishable from "nobody
        asked". A CLI that filled the default in would settle §12.2 silently
        and make it unsettleable."""
        from dna._yaml import safe_load

        r = _run(runner, "kind", "Contrato", "--scope", "loja",
                 "--plane", "composition")
        assert r.exit_code == 0, r.output
        spec = safe_load(_kind_files(store)[0].read_text(encoding="utf-8"))["spec"]
        assert spec["plane"] == "composition"

        r2 = _run(runner, "kind", "Outro", "--scope", "loja")
        assert r2.exit_code == 0, r2.output
        other = next(p for p in _kind_files(store) if p.parent.name.endswith("Outro"))
        assert "plane" not in safe_load(other.read_text(encoding="utf-8"))["spec"]


# ── the mutant: --dry-run that is not dry ────────────────────────────────────


class TestDryRun:
    """MUTANT: the dry run mints a namespace so it can pretty-print the name.

    The tempting one, and the reason the plan deliberately does NOT print the
    instance name: ``assign_namespace`` mints on absence, so any code path
    that resolved the name for display would leave a ``KindNamespace`` claim
    behind — a dry run with a side effect, in the registry that decides
    ownership."""

    def test_writes_neither_the_kind_nor_a_namespace_claim(self, runner, store):
        r = _run(runner, "kind", "Contrato", "--scope", "loja",
                 "-f", "titulo:string!", "--dry-run")
        assert r.exit_code == 0, r.output
        assert _kind_files(store) == []
        assert _claims(store) == [store / "_lib" / "manifest.yaml"], (
            "a namespace claim was minted by a DRY run — the plan must not "
            "resolve a name it would have to mint to know"
        )

    def test_the_plan_shows_the_schema_that_would_land(self, runner, store):
        """The reviewable artifact is the schema, so the plan has to carry it —
        the same reason ``dna rename --dry-run`` prints the rewrites."""
        r = _run(runner, "kind", "Contrato", "--scope", "loja",
                 "-d", "Um contrato", "-f", "titulo:string!=O titulo",
                 "--dry-run")
        assert "Would author Kind Contrato" in r.output
        assert "titulo" in r.output and "O titulo" in r.output
        assert "Nothing was written" in r.output

    def test_json_plan_says_created_false(self, runner, store):
        r = _run(runner, "kind", "Contrato", "--scope", "loja",
                 "--dry-run", "--json")
        payload = json.loads(r.output)
        assert payload["dry_run"] is True and payload["created"] is False
        assert payload["approved"] is False
        assert payload["schema"]["type"] == "object"
        assert _kind_files(store) == []


# ── the mutant: an edit that surprises ───────────────────────────────────────


class TestReautorar:
    """MUTANT: ``--force`` warns about the rebuild unconditionally.

    ``author_kind_impl`` REBUILDS the spec and persists it, so a one-word edit
    with no ``--field`` leaves ``properties: {}``. The CLI must not merge (that
    would be a second reading of what an edit means) and must not warn blindly
    either: a warning that fires on every ``--force`` is one nobody reads by
    the time it fires on the edit that actually loses six fields. So the
    warning is DERIVED from the stored instance, and both directions are
    pinned."""

    def test_second_author_without_force_is_refused_and_names_the_cost(
        self, runner, store,
    ):
        assert _run(runner, "kind", "Contrato", "--scope", "loja",
                    "-f", "titulo:string!").exit_code == 0
        r = _run(runner, "kind", "Contrato", "--scope", "loja", "-d", "outro")
        assert r.exit_code != 0
        assert "--force" in r.output and "approval" in r.output

    def test_force_names_the_fields_it_drops(self, runner, store):
        assert _run(runner, "kind", "Contrato", "--scope", "loja",
                    "-f", "titulo:string", "-f", "valor:number").exit_code == 0
        r = _run(runner, "kind", "Contrato", "--scope", "loja",
                 "-d", "outro", "--force")
        assert r.exit_code == 0, r.output
        assert "REBUILT" in r.output
        assert "titulo" in r.output and "valor" in r.output

    def test_force_that_drops_nothing_says_nothing(self, runner, store):
        assert _run(runner, "kind", "Contrato", "--scope", "loja",
                    "-f", "titulo:string").exit_code == 0
        r = _run(runner, "kind", "Contrato", "--scope", "loja",
                 "-f", "titulo:string", "-f", "valor:number", "--force")
        assert r.exit_code == 0, r.output
        assert "REBUILT" not in r.output, (
            "the loss warning fired on an edit that lost nothing — a warning "
            "that always fires is a warning nobody reads"
        )

    def test_dry_run_of_an_edit_says_it_is_an_edit(self, runner, store):
        assert _run(runner, "kind", "Contrato", "--scope", "loja",
                    "-f", "titulo:string").exit_code == 0
        r = _run(runner, "kind", "Contrato", "--scope", "loja",
                 "-d", "outro", "--dry-run")
        assert r.exit_code == 0, r.output
        assert "Would RE-AUTHOR" in r.output
        assert "would drop its approval" in r.output


# ── the mutant: a refusal that reaches nobody ────────────────────────────────


class TestRecusaHonesta:
    """MUTANT: the handler catches ``ValueError`` and calls it done.

    The two refusal families are imported from ``_mcp_kinds`` precisely
    because enumerating them per face is the defect this house has already
    paid for twice: ``NamespaceRegistryUnreadable`` is a ``RuntimeError`` and
    ``KernelRefusal`` is a plain ``Exception``, so neither is caught by the
    obvious ``except ValueError`` — and both would reach the user as a
    traceback, which is a documented refusal delivered in the shape of a
    crash."""

    def test_a_kernel_refusal_reaches_the_user_named(self, runner, store, monkeypatch):
        from dna.kernel.errors import KernelRefusal

        class _Vetoed(KernelRefusal):
            pass

        async def _refuse(live, **kwargs):
            raise _Vetoed("the layer policy said no")

        monkeypatch.setattr(
            "dna.application.kind_authoring.author_kind_impl", _refuse)
        r = _run(runner, "kind", "Contrato", "--scope", "loja")
        assert r.exit_code != 0
        assert "_Vetoed" in r.output and "layer policy" in r.output

    def test_a_camelcase_violation_is_the_doors_refusal_not_ours(
        self, runner, store,
    ):
        """The Kind name reaches a filesystem PATH, so its guard is a security
        boundary — and it lives in the door. A copy of the regex here would be
        a second boundary that can disagree with the first."""
        r = _run(runner, "kind", "contrato", "--scope", "loja")
        assert r.exit_code != 0
        assert "CamelCase" in r.output
        assert _kind_files(store) == []

    def test_traversal_in_the_name_is_refused_and_writes_nothing(
        self, runner, store, tmp_path,
    ):
        r = _run(runner, "kind", "../../Escapou", "--scope", "loja")
        assert r.exit_code != 0
        assert list(tmp_path.glob("**/KIND.yaml")) == []

    def test_a_relation_must_declare_its_cardinality(self, runner, store):
        """MUTANT: reading cardinality off the field's ``type``.

        Available, tempting, and the exact inference
        ``dna.kernel.kinds.relations`` killed: cardinality states the MODEL's
        multiplicity, and a declaration the kernel ENFORCES may not be
        derived. A suggestion may be; this is not one."""
        r = _run(runner, "kind", "Apolice", "--scope", "loja",
                 "--relation", "contratos=Contrato")
        assert r.exit_code != 0
        assert "cardinality is required" in r.output

    def test_an_unusable_field_type_is_named(self, runner, store):
        r = _run(runner, "kind", "Contrato", "--scope", "loja",
                 "-f", "x:banana")
        assert r.exit_code != 0
        assert "banana" in r.output and "JSON Schema type" in r.output

    def test_no_workspace_refuses_and_names_both_ways_to_give_one(
        self, runner, store, monkeypatch,
    ):
        monkeypatch.delenv("DNA_TENANT", raising=False)
        r = _run(runner, "kind", "Contrato", "--scope", "loja")
        assert r.exit_code != 0
        assert "--workspace" in r.output and "DNA_TENANT" in r.output


class TestSemOExtraMcp:
    """MUTANT: ``dna new kind`` starts requiring ``dna-cli[mcp]``.

    This command imports its two refusal tuples from ``dna_cli._mcp_kinds`` on
    purpose — that module says in its own comment that they are "spelled once
    here so the two faces cannot drift", and a third face copying them would
    be the drift. The price of borrowing is a coupling that is INVISIBLE in
    any environment where ``fastmcp`` happens to be installed, which is every
    developer's — while CI installs the CLI as ``-e ".[dev]"``, without the
    extra. So the property is pinned at the source, the same way
    ``test_mcp_server.test_base_import_never_pulls_mcp`` pins it for the
    server: the module this command borrows from must import fastmcp only
    lazily.
    """

    def test_the_module_we_borrow_from_pulls_no_mcp_at_import(self):
        import pathlib

        import dna_cli._mcp_kinds as borrowed

        src = pathlib.Path(borrowed.__file__).read_text(encoding="utf-8")
        assert "from fastmcp" in src, (
            "this guard is only meaningful while the module DOES use fastmcp"
        )
        top_level = [
            ln for ln in src.splitlines()
            if ln.startswith(("import fastmcp", "from fastmcp",
                              "import mcp", "from mcp"))
        ]
        assert top_level == [], (
            f"`dna new kind` imports this module at runtime, so a top-level "
            f"MCP import here makes the command require `dna-cli[mcp]`: "
            f"{top_level}"
        )


class TestSemRegistro:
    """⚠️ i-142 — this class pinned a REFUSAL, and the refusal was the bug.

    It said: on a bare store the very first ``dna new kind`` fails, because
    ``assign_namespace`` READS the claim registry before it mints and the
    filesystem adapter answered a missing scope DIRECTORY with
    ``FileNotFoundError``. All true, and this face's message was the best of the
    four handlers that had grown around it — it NAMED the fix instead of saying
    "ask an operator", because here the caller usually IS the operator.

    It was still a handler for a store whose only sin was being NEW. Every other
    adapter answers ``[]`` for a scope that holds nothing, and on disk the first
    write creates the directory — so there was nothing to provision and nothing
    to name. The adapter tells the two absences apart now:

    * store present, ``_lib`` absent → **the authoring succeeds**, and ``_lib``
      appears because the mint writes it;
    * store ABSENT → still refuses, because that one IS a deployment fault
      (``StoreUnavailable``, which is still a ``FileNotFoundError``, so this
      face's handler catches it unchanged).

    Both halves are asserted, and the second is what keeps the first honest: a
    change that made EVERY absence "empty" would pass the first alone.
    """

    @pytest.fixture
    def bare(self, tmp_path, monkeypatch):
        base = tmp_path / ".dna"
        (base / "loja").mkdir(parents=True)
        (base / "loja" / "manifest.yaml").write_text(
            _GENOME.format(n="loja"), encoding="utf-8")
        monkeypatch.setenv("DNA_SOURCE_URL", f"file://{base.resolve()}")
        monkeypatch.delenv("DNA_BASE_DIR", raising=False)
        monkeypatch.setenv("DNA_TENANT", "acme")
        return base

    def test_a_brand_new_store_authors_its_first_kind(self, runner, bare):
        r = _run(runner, "kind", "Contrato", "--scope", "loja")
        assert r.exit_code == 0, r.output
        assert "Traceback" not in r.output
        # The registry scope is CREATED by the mint, not demanded from an
        # operator beforehand — which is the whole content of the fix.
        assert (bare / "_lib").is_dir(), (
            "the mint did not create the registry scope it used to refuse to "
            "read"
        )

    def test_a_store_that_is_not_there_still_refuses_without_a_traceback(
        self, runner, tmp_path, monkeypatch,
    ):
        monkeypatch.setenv(
            "DNA_SOURCE_URL", f"file://{(tmp_path / 'never-mounted').resolve()}")
        monkeypatch.delenv("DNA_BASE_DIR", raising=False)
        monkeypatch.setenv("DNA_TENANT", "acme")
        r = _run(runner, "kind", "Contrato", "--scope", "loja")
        assert r.exit_code != 0
        assert "Traceback" not in r.output


# ── the mutant: the i-111 vocabulary drifting back ───────────────────────────


class TestVocabulario:
    """MUTANT: ``dna new``'s own help calls an instance a Kind.

    It said *"Scaffold a valid Kind skeleton into a scope (agent | soul |
    guardrail | tool)"* until this command existed — the i-111 confusion alive
    in a ``--help`` line everybody reads, and it was harmless only while no
    command in the group made a Kind. Now one does, and the two words in one
    sentence have to mean two things."""

    def test_the_group_help_no_longer_calls_an_instance_a_kind(self, runner):
        help_text = runner.invoke(new, ["--help"]).output
        assert "Kind skeleton" not in help_text
        assert "INSTANCE" in help_text and "KIND" in help_text

    def test_kind_is_listed_as_its_own_command(self, runner):
        assert "kind" in new.commands
        assert "kind" in runner.invoke(new, ["--help"]).output


class TestRelacaoGanhaSeuCampo:
    """The one derivation this command makes, end to end.

    ``schema_contradictions`` REFUSES a relation with no property to live in,
    so a relation-only invocation would be refused BY THE DOOR if the property
    were not declared. That refusal is what this test would see if
    ``_kind_schema`` stopped declaring it — which is the point: the derivation
    is checked by the core's own rule, not by a second copy of it here."""

    def test_a_relation_only_kind_is_accepted_and_the_field_is_an_array(
        self, runner, store,
    ):
        r = _run(runner, "kind", "Apolice", "--scope", "loja",
                 "--relation", "contratos=Contrato:many")
        assert r.exit_code == 0, r.output
        from dna._yaml import safe_load

        spec = safe_load(_kind_files(store)[0].read_text(encoding="utf-8"))["spec"]
        assert spec["relations"] == {
            "contratos": {"to": "Contrato", "cardinality": "many"}}
        assert spec["schema"]["properties"]["contratos"]["type"] == "array"

    def test_an_explicit_field_wins_and_the_door_judges_the_disagreement(
        self, runner, store,
    ):
        """``one`` against an array is a contradiction, and it is the DOOR that
        says so — this command declares no opinion about the pair."""
        r = _run(runner, "kind", "Apolice", "--scope", "loja",
                 "-f", "contratos:array", "--relation", "contratos=Contrato:one")
        assert r.exit_code != 0
        assert "cardinality" in r.output and "array" in r.output

    def test_the_full_form_speaks_the_declarations_own_vocabulary(
        self, runner, store,
    ):
        r = _run(
            runner, "kind", "Apolice", "--scope", "loja",
            "--relation",
            "contratos={to: Contrato, cardinality: many, inverse_of: apolice}",
        )
        assert r.exit_code == 0, r.output
        from dna._yaml import safe_load

        spec = safe_load(_kind_files(store)[0].read_text(encoding="utf-8"))["spec"]
        assert spec["relations"]["contratos"]["inverse_of"] == "apolice"
