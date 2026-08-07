"""``dna new`` — scaffold a valid skeleton into a scope.

s-dx-new-scaffolding — authoring an agent or a soul used to mean remembering
the envelope by hand (``apiVersion``/``kind``/``metadata``/``spec``), the
right bundle marker (``AGENT.md`` vs ``SOUL.md``), and which spec fields are
even allowed. ``dna new`` writes the correct skeleton for you — through
``kernel.write_instance`` (never a hand-rolled YAML dump), so every write
guard, schema check and reader/writer round-trip runs exactly as on any other
write — leaving you with a valid doc whose only empty part is the prose you
came to write.

⚠️ **Four of these five commands create an INSTANCE, and one creates a KIND.**
This module's own help said *"scaffold a valid Kind skeleton"* for all of them
until 07/08/2026, which is exactly the Kind/Instância confusion i-111 retired,
alive in a ``--help`` line everybody reads: ``dna new agent`` creates an
instance OF the Agent Kind; it creates no Kind at all. Now that ``dna new
kind`` exists, the two words in one sentence have to mean two things.

  * ``dna new agent <name>`` — an Agent bundle (``agents/<name>/AGENT.md``)
    with a placeholder instruction body and the optional ``--soul`` /
    ``--guardrails`` / ``--layout`` / ``--model`` wiring pre-filled. Pair it
    with a named ``--layout`` (persona-first / instruction-first) and you never
    touch raw Mustache (s-dx-named-layouts).
  * ``dna new soul <name>`` — a Soul as a SINGLE ``SOUL.md`` file
    (s-dx-single-file-soul): no ``soul.json`` ceremony, just the persona prose.
    The 2-file soulspec.org format stays fully supported — this is the
    convenience on-ramp.
  * ``dna new guardrail <name>`` — a Guardrail bundle
    (``guardrails/<name>/GUARDRAIL.md``) with a starter rule + severity/scope.
  * ``dna new tool <name>`` — a Tool descriptor (``tools/<name>.yaml``).
  * ``dna new kind <Kind>`` — a KIND of your own: a ``KindDefinition``
    instance, INERT until a human approves it. It is the only command in this
    group that does not go through :func:`_write` — it delegates to
    ``dna.application.kind_authoring.author_kind_impl``, the SAME function the
    MCP tool ``author_kind`` and ``POST /v1/kinds`` call. See :func:`new_kind`
    for why a second authoring path was not written.

Idempotent: an existing doc is never overwritten without ``--force``.
"""
from __future__ import annotations

import os
import re

import click

from dna_cli._ctx import dna_session, fail, print_json


def _validate_name(name: str) -> None:
    """Doc names are plain slugs — they become directory names on disk."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise fail(
            f"name {name!r} must be a slug (lowercase letters, digits, '-'; "
            f"start with a letter or digit)"
        )


def _exists(s, kind: str, name: str) -> bool:
    try:
        return s.get_doc(kind, name) is not None
    except Exception:  # noqa: BLE001 — a read miss means "does not exist"
        return False


def _write(s, kind: str, name: str, raw: dict, *, force: bool, as_json: bool,
           summary: str) -> None:
    """Shared write path: existence gate → kernel.write_instance → report."""
    if _exists(s, kind, name) and not force:
        if as_json:
            print_json({"created": False, "reason": "exists", "kind": kind,
                        "name": name, "scope": s.scope})
            return
        raise fail(
            f"{kind}/{name} already exists in scope {s.scope} — "
            f"re-run with --force to overwrite"
        )
    try:
        s.run(s.kernel.write_instance(s.scope, kind, name, raw))
    except Exception as e:  # noqa: BLE001
        raise fail(f"write failed: {e}") from e
    s.holder.reload()
    if as_json:
        print_json({"created": True, "kind": kind, "name": name,
                    "scope": s.scope, "spec_fields": sorted(raw["spec"].keys())})
        return
    click.secho(f"Created {kind}/{name} in scope {s.scope}", fg="green")
    click.echo(f"  {summary}")


# ── group ──────────────────────────────────────────────────────────────


@click.group(
    "new",
    help=(
        "Scaffold a valid skeleton into a scope — an INSTANCE "
        "(agent | soul | guardrail | tool), or a KIND of your own (kind)."
    ),
)
def new() -> None:
    """Group root."""


_LAYOUT_CHOICES = ["default", "instruction-first", "persona-first"]


@new.command("agent")
@click.argument("name")
@click.option("--scope", default=None, help="Scope to write into (default: env / sole scope).")
@click.option("--description", "-d", default=None, help="One-line description.")
@click.option("--soul", default=None, help="Name of a Soul doc to compose in.")
@click.option("--guardrails", default=None, help="Comma-separated Guardrail names to attach.")
@click.option("--layout", type=click.Choice(_LAYOUT_CHOICES), default=None,
              help="Named composition layout (s-dx-named-layouts) — 'persona-first' "
                   "puts the Soul before the instruction. Omit for the default.")
@click.option("--model", default=None, help="Model id (e.g. openai:gpt-4o-mini).")
@click.option("--force", is_flag=True, help="Overwrite an existing agent.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def new_agent(name, scope, description, soul, guardrails, layout, model, force, as_json):
    """Scaffold an Agent bundle (agents/<name>/AGENT.md) — fill in the instruction.

    The skeleton is a VALID Agent from the first write: correct envelope, a
    placeholder instruction body, and any --soul/--guardrails/--layout/--model
    wiring pre-filled. With --layout you order persona-vs-instruction by name
    and never hand-write Mustache.

    Examples:

    \b
      dna new agent triage
      dna new agent concierge --soul warm-host --layout persona-first
      dna new agent reviewer --guardrails safety,review-ethics --model openai:gpt-4o
    """
    _validate_name(name)
    spec: dict = {
        "instruction": (
            f"# {name}\n\n"
            "Describe what this agent does and how it should behave.\n\n"
            "Replace this body with your instruction — the composition layout "
            "handles ordering the persona and guardrails around it.\n"
        ),
    }
    if model:
        spec["model"] = model
    if soul:
        spec["soul"] = soul
    if guardrails:
        spec["guardrails"] = [g.strip() for g in guardrails.split(",") if g.strip()]
    if layout:
        spec["layout"] = layout
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": name, **({"description": description} if description else {})},
        "spec": spec,
    }
    with dna_session(scope) as s:
        wiring = []
        if soul:
            wiring.append(f"soul={soul}")
        if layout:
            wiring.append(f"layout={layout}")
        if guardrails:
            wiring.append(f"guardrails={spec['guardrails']}")
        detail = "edit agents/%s/AGENT.md" % name
        if wiring:
            detail += "  (" + ", ".join(wiring) + ")"
        _write(s, "Agent", name, raw, force=force, as_json=as_json, summary=detail)


@new.command("soul")
@click.argument("name")
@click.option("--scope", default=None, help="Scope to write into (default: env / sole scope).")
@click.option("--description", "-d", default=None, help="One-line description.")
@click.option("--force", is_flag=True, help="Overwrite an existing soul.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def new_soul(name, scope, description, force, as_json):
    """Scaffold a Soul as a SINGLE SOUL.md file — no soul.json ceremony.

    s-dx-single-file-soul: a Soul is authored from one SOUL.md; the
    2-file soulspec.org format (SOUL.md + soul.json + companions) stays fully
    supported for market fidelity, but the common case is a single file.

    Example:

    \b
      dna new soul warm-host -d "Patient, warm, concise concierge voice"
    """
    _validate_name(name)
    spec = {
        "soul_content": (
            f"# {name}\n\n"
            "Describe this persona's voice, values, and guiding principles as "
            "prose (not code).\n\n"
            "## Voice\n\n- ...\n\n## Principles\n\n- ...\n"
        ),
    }
    raw = {
        "apiVersion": "soulspec.org/v1",
        "kind": "Soul",
        "metadata": {"name": name, **({"description": description} if description else {})},
        "spec": spec,
    }
    with dna_session(scope) as s:
        _write(s, "Soul", name, raw, force=force, as_json=as_json,
               summary="edit souls/%s/SOUL.md (single-file — no soul.json needed)" % name)


_TOOL_TYPES = ["builtin", "http", "mcp", "python", "shell"]


@new.command("tool")
@click.argument("name")
@click.option("--scope", default=None, help="Scope to write into (default: env / sole scope).")
@click.option("--description", "-d", default=None,
              help="Agent-facing description — the text the model reads to "
                   "decide whether to call the tool (goes in metadata.description).")
@click.option("--type", "tool_type", type=click.Choice(_TOOL_TYPES), default="builtin",
              help="Invocation type. builtin | http | mcp | python | shell.")
@click.option("--force", is_flag=True, help="Overwrite an existing tool.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def new_tool(name, scope, description, tool_type, force, as_json):
    """Scaffold a Tool descriptor (tools/<name>.yaml) — tools as data.

    A Tool moves the agent-facing surface of a tool into the declarative plane:
    the ``description`` the model reads (metadata.description) + the
    ``input_schema`` of its arguments (surfaced as ``parameters`` by
    ``dna.load_tools`` / ``loadTools``). The skeleton is a VALID Tool from the
    first write, with a placeholder single-arg ``input_schema`` to edit.

    Examples:

    \b
      dna new tool generate-artifact -d "Render HTML/Markdown into a shareable artifact."
      dna new tool github-search --type http -d "Search GitHub code."
    """
    _validate_name(name)
    spec: dict = {
        "type": tool_type,
        "input_schema": {
            "type": "object",
            "properties": {
                "arg": {
                    "type": "string",
                    "description": "Replace with the tool's real parameters.",
                },
            },
        },
        "read_only": True,
    }
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Tool",
        "metadata": {
            "name": name,
            "description": description or f"Describe what the {name} tool does "
            "and when the model should call it.",
        },
        "spec": spec,
    }
    with dna_session(scope) as s:
        _write(s, "Tool", name, raw, force=force, as_json=as_json,
               summary="edit tools/%s.yaml (type=%s; set metadata.description + "
                       "spec.input_schema)" % (name, tool_type))


@new.command("guardrail")
@click.argument("name")
@click.option("--scope", default=None, help="Scope to write into (default: env / sole scope).")
@click.option("--description", "-d", default=None, help="One-line description.")
@click.option("--severity", type=click.Choice(["warn", "error"]), default="warn",
              help="warn lets the turn continue; error fails it.")
@click.option("--guard-scope", type=click.Choice(["input", "output", "both"]), default="both",
              help="Which side the guardrail runs on.")
@click.option("--force", is_flag=True, help="Overwrite an existing guardrail.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def new_guardrail(name, scope, description, severity, guard_scope, force, as_json):
    """Scaffold a Guardrail bundle (guardrails/<name>/GUARDRAIL.md).

    Example:

    \b
      dna new guardrail no-pii --severity error --guard-scope output
    """
    _validate_name(name)
    spec = {
        "instruction": (
            f"# {name}\n\nExplain the intent behind this rule set.\n"
        ),
        "rules": ["Replace this with your first directive."],
        "severity": severity,
        "scope": guard_scope,
    }
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Guardrail",
        "metadata": {"name": name, **({"description": description} if description else {})},
        "spec": spec,
    }
    with dna_session(scope) as s:
        _write(s, "Guardrail", name, raw, force=force, as_json=as_json,
               summary="edit guardrails/%s/GUARDRAIL.md (severity=%s, scope=%s)" % (
                   name, severity, guard_scope))


# ── ``dna new kind`` ────────────────────────────────────────────────────
#
# The slice-5 command of ``spec-solucao-como-template`` — and it exists BECAUSE
# that spec measured the founder's own premise and refused half of it. "Creating
# Kinds much faster" was already spent, and spent better: a `record` Kind is one
# YAML file and the portal renders 85 of them from one generic component. What
# was genuinely missing was smaller and dumber — `dna new` covered
# agent|soul|guardrail|tool and there was no way to make a KIND from the CLI at
# all, so the 47 shipped descriptors were written by hand.
#
# ⛔ So this is deliberately NOT a template engine, and it brings no dependency.
# Everything below is argument parsing plus ONE call.

#: The JSON Schema type names a ``--field`` may carry. The vocabulary is JSON
#: Schema's own, verbatim — not a dialect of ours that would have to be
#: translated somewhere. ``null`` is absent on purpose: a field whose only legal
#: value is null is a field that should not be declared.
_FIELD_TYPES = ("string", "integer", "number", "boolean", "array", "object")

#: What a ``--field`` NAME may be. Deliberately laxer than the Kind name (a spec
#: property is not a path segment) and still an ALLOW-list: it becomes a key in
#: a JSON Schema and the name of a possible relation.
_FIELD_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


def _parse_field(spec: str) -> tuple[str, dict, bool]:
    """``NAME[:TYPE][!][=DESCRIPTION]`` → ``(name, json-schema property, required)``.

    ``!`` marks the field REQUIRED and may sit after the name or after the type
    (``titulo!``, ``titulo:string!``). The type defaults to ``string`` — the one
    default here that is a guess, and it is the guess a schema is easiest to
    correct: widening a string later costs an edit, while a wrong ``integer``
    silently refuses the author's first instance.
    """
    left, _, description = spec.partition("=")
    left = left.strip()
    required = left.endswith("!")
    if required:
        left = left[:-1].strip()
    name, _, ftype = left.partition(":")
    name, ftype = name.strip(), (ftype.strip() or "string")
    if not _FIELD_NAME_RE.fullmatch(name):
        raise fail(
            f"--field {spec!r}: {name!r} is not a usable field name — letters, "
            f"digits, '_' and '-', starting with a letter or '_'"
        )
    if ftype not in _FIELD_TYPES:
        raise fail(
            f"--field {spec!r}: type {ftype!r} is not a JSON Schema type — "
            f"one of {', '.join(_FIELD_TYPES)}"
        )
    prop: dict = {"type": ftype}
    if description.strip():
        prop["description"] = description.strip()
    return name, prop, required


def _parse_relation(spec: str) -> tuple[str, dict]:
    """``FIELD=KIND:CARDINALITY`` or ``FIELD={to: …, cardinality: …, …}``.

    The long form is YAML and its keys are the DECLARATION's own —
    ``to``/``cardinality``/``inverse_of``/``by``, exactly as
    ``dna.kernel.kinds.relations`` spells them and exactly as the MCP tool
    documents them. No dialect is invented here, so nothing has to be
    translated and nothing can drift: what the author types is what is stored,
    and it is ``normalize_relations`` — not this function — that decides
    whether it is legal.

    ⚠️ ``cardinality`` is REQUIRED in the short form and this refuses without
    it, rather than reading it off the field's ``type``. That inference is
    available and it is the one this house has already ruled out: cardinality
    states the MODEL's multiplicity, and a declaration the kernel ENFORCES may
    not be derived (``dna.kernel.kinds.relations`` killed the name-shape guess
    for that reason). A suggestion may be derived; this is not one.
    """
    field, sep, value = spec.partition("=")
    field, value = field.strip(), value.strip()
    if not sep or not field or not value:
        raise fail(
            f"--relation {spec!r}: expected FIELD=KIND:CARDINALITY (e.g. "
            f"'cliente=Cliente:one') or FIELD={{to: …, cardinality: …}}"
        )
    if value.startswith("{"):
        from dna._yaml import safe_load

        try:
            parsed = safe_load(value)
        except Exception as exc:  # noqa: BLE001 — the author's own YAML
            raise fail(f"--relation {spec!r}: not readable as YAML — {exc}") from None
        if not isinstance(parsed, dict):
            raise fail(f"--relation {spec!r}: the long form must be a mapping")
        return field, parsed
    target, _, cardinality = value.partition(":")
    if not cardinality.strip():
        raise fail(
            f"--relation {spec!r}: cardinality is required — write "
            f"'{field}={target.strip()}:one' or '{field}={target.strip()}:many'. "
            f"It states your MODEL's multiplicity, so it is declared, never "
            f"read off the field's type"
        )
    return field, {"to": target.strip(), "cardinality": cardinality.strip()}


def _kind_schema(
    description: str | None,
    fields: tuple[str, ...],
    relations: dict[str, dict],
) -> dict:
    """The JSON Schema for the Kind's ``spec``, from what little was asked.

    Three things happen here and only the third is an opinion:

    * ``--description`` becomes the schema's own ``description``. There is no
      second place to put "what this Kind is" — ``author_kind_impl`` takes no
      such argument — and JSON Schema already has the field.
    * each ``--field`` becomes a property, in the order given.
    * a ``--relation`` whose field NOBODY declared gets its property declared
      here. That is not inference of a declaration:
      ``schema_contradictions`` REFUSES a relation with no property to live
      in, and the property's type is fully determined by the cardinality the
      author just wrote (``many`` is an array, ``one`` is not — the same rule
      that function checks). An explicit ``--field`` always wins; if the two
      disagree the DOOR says so, because a second reading of that rule here is
      exactly the drift this house keeps paying for.

    ``additionalProperties`` is left UNSET — i.e. open. A Kind born closed
    would refuse the author's own next field until they re-authored the Kind,
    and closing it later is one edit; opening it after instances exist is a
    migration.
    """
    props: dict[str, dict] = {}
    required: list[str] = []
    for spec in fields:
        name, prop, is_required = _parse_field(spec)
        props[name] = prop
        if is_required:
            required.append(name)
    for field, declaration in relations.items():
        if field in props:
            continue
        many = str(declaration.get("cardinality") or "").strip() == "many"
        target = declaration.get("to")
        says = f"Points at {target}." if isinstance(target, str) else "A relation."
        props[field] = (
            {"type": "array", "items": {"type": "string"}, "description": says}
            if many else {"type": "string", "description": says}
        )
    schema: dict = {"type": "object"}
    if description and description.strip():
        schema["description"] = description.strip()
    schema["properties"] = props
    if required:
        schema["required"] = required
    return schema


def _click_ask(text: str) -> str:
    """``trait_ask()``'s prose fitted to Click's help formatter.

    Click re-wraps every paragraph of a help string; the ask arrives already
    wrapped, with an indented vocabulary block whose shape carries the
    ``[carries …]`` annotations. So each paragraph is preceded by Click's own
    no-rewrap marker (``\\b`` alone on a line). Formatting only — not one word
    of the ask is written here, because the ask is DERIVED from the live trait
    registry and a copy of it in this file would be right on the day it was
    pasted and silently stale on the next registration.
    """
    return "\n\n".join("\b\n" + block for block in text.split("\n\n"))


_KIND_HELP_TEMPLATE = """\
Author a KIND of your own — a typed instance shape, INERT until approved.

\b
The one command in this group that creates a Kind rather than an instance of
one. `dna new kind Contrato` is enough: the name and, ideally, one line saying
what it is. Everything else — the apiVersion namespace, the alias, the storage
container, the plane — is derived or defaulted, and nothing that can be derived
is asked for.

\b
What lands is a real, auditable `KindDefinition` instance with NO approval
marker, so it validates nothing and routes nothing until a human approves it.
Re-running for the same Kind EDITS the declaration and drops the approval,
which is why --force is required for the second run.

\b
Examples:
  dna new kind Contrato -d "Um contrato assinado com um cliente"
  dna new kind Contrato -f 'titulo:string!=O titulo' -f assinado_em:string
  dna new kind Apolice --relation 'contratos=Contrato:many'
  dna new kind Contrato --dry-run

\b
--field is NAME[:TYPE][!][=DESCRIPTION]; `!` marks it required and the type
defaults to string. --relation is FIELD=KIND:CARDINALITY, or the full form
FIELD={to: Contrato, cardinality: many, inverse_of: apolice} whose keys are the
declaration's own. A relation whose field you did not declare gets one.

{{trait-vocabulary}}
"""


def _kind_help() -> str:
    """The ``dna new kind`` help text, with the LIVE trait vocabulary in it.

    Built at import (Click reads a command's help at decoration time), which is
    the CLI's equivalent of what ``_mcp_kinds._asks_for_traits`` does for the
    tool description. The reason is the measurement slice 4 of the taxonomy
    spec ran and this command must not undo: of 47 descriptors, 47 declare
    ``plane`` and 8 declared ``traits`` — same file, same author, same
    mechanism, 100% against 17%. The difference was that ``plane`` was ASKED
    for. A CLI asks in ``--help``, so that is where the vocabulary goes, and it
    is PROJECTED from the registry rather than typed out: a hand-written list
    is right on the day it is written and silently wrong on the day the next
    trait is registered.

    ⚠️ And asking is not requiring (§8.4 of that spec). Nothing in this command
    refuses a Kind that declares no trait, and ``TRAIT_REQUIRED_ENFORCED`` stays
    ``False`` — a field everyone must fill is a field everyone fills with
    anything.
    """
    from dna.application.kind_authoring import TRAIT_ASK_SLOT, trait_ask

    return _KIND_HELP_TEMPLATE.replace(TRAIT_ASK_SLOT, _click_ask(trait_ask()))


@new.command("kind", help=_kind_help())
@click.argument("kind_name")
@click.option("--scope", default=None,
              help="Scope to author into (default: env / sole scope).")
@click.option("--description", "-d", default=None,
              help="What this Kind IS, in one line — becomes the schema's "
                   "own `description`.")
@click.option("--field", "-f", "fields", multiple=True,
              help="NAME[:TYPE][!][=DESCRIPTION]. Repeatable; order is kept.")
@click.option("--trait", "traits", multiple=True,
              help="A role this Kind takes part in. Repeatable, OPTIONAL, and "
                   "never required — the vocabulary is in this help, and in "
                   "`dna kind traits`.")
@click.option("--relation", "relations", multiple=True,
              help="FIELD=KIND:CARDINALITY, or FIELD={to: …, cardinality: …}. "
                   "Repeatable.")
@click.option("--presentation", default=None,
              help="Comma-separated field order for how instances READ "
                   "(the short form: 'name,titulo,situacao').")
@click.option("--plane", type=click.Choice(["composition", "record"]), default=None,
              help="Omit unless you know which you mean — the difference is a "
                   "cost, not a taste. Undeclared is NOT the same as declaring "
                   "the default, and is stored as such.")
@click.option("--workspace", "-w", default=None,
              help="The workspace authoring this Kind (default: $DNA_TENANT). "
                   "It owns the apiVersion namespace the Kind lands under.")
@click.option("--force", is_flag=True,
              help="Re-author an existing Kind. The declaration is REBUILT, "
                   "not merged: a field you do not pass again is gone. The "
                   "edit also drops the approval.")
@click.option("--dry-run", is_flag=True,
              help="Print the plan and write nothing.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def new_kind(kind_name, scope, description, fields, traits, relations,
             presentation, plane, workspace, force, dry_run, as_json):
    """(help is built by ``_kind_help`` — see it for the trait ask.)

    ⚠️ **There is exactly one authoring path and this is not a second one.**
    The body below parses arguments and calls
    :func:`dna.application.kind_authoring.author_kind_impl` — the same function
    the MCP tool ``author_kind`` and ``POST /v1/kinds`` call, so the CamelCase
    guard (a security boundary: the Kind name reaches a filesystem PATH), the
    meta-schema check, the relation/schema contradiction check, the namespace
    gate, the audit stamps and the ``approved: false`` invariant are inherited
    rather than restated. A CLI that built its own ``KindDefinition`` envelope
    would be a second reading of every one of those, and two readings of one
    rule diverge — which is why this command is argument parsing around a
    single ``await``.
    """
    from dna.application.kind_authoring import (
        AuthoredKindNotFound,
        author_kind_impl,
        get_authored_kind_impl,
    )
    # The refusal families, IMPORTED from the face that first spelled them out
    # rather than re-enumerated here. ``_mcp_kinds`` says in its own comment
    # that the pair exists "spelled once here so the two faces cannot drift"; a
    # third face copying the tuple would be the drift it was written to
    # prevent. That module's top-level imports are the core + typing only — no
    # fastmcp, which is imported inside ``register_kind_tools``.
    from dna_cli._mcp_kinds import AUTHORING_REFUSALS, NO_REGISTRY

    tenant = (workspace or os.getenv("DNA_TENANT") or "").strip()
    if not tenant:
        raise fail(
            "a workspace is required to author a Kind: it OWNS the apiVersion "
            "namespace the Kind lands under, and a namespace claim is an "
            "ownership record — there is no unowned one to write. Pass "
            "--workspace <id> or set DNA_TENANT."
        )
    declared_relations = dict(_parse_relation(r) for r in relations)
    schema = _kind_schema(description, fields, declared_relations)
    declared_presentation = (
        [p.strip() for p in presentation.split(",") if p.strip()]
        if presentation else None
    )
    declared_traits = [t.strip() for t in traits if t.strip()]
    effective_plane = plane or _default_plane_for(schema, declared_traits)

    with dna_session(scope) as s:
        from dna.application.live import LiveDna

        live = LiveDna(base_scope=s.scope, kernel=s.kernel, provider=None)
        try:
            existing = s.run(get_authored_kind_impl(
                live, kind=kind_name, tenant=tenant,
            ))
        except AuthoredKindNotFound:
            existing = None
        except NO_REGISTRY as exc:
            raise _no_registry(exc) from None
        except AUTHORING_REFUSALS as exc:
            raise fail(f"{type(exc).__name__}: {exc}") from None

        if existing and not force and not dry_run:
            raise fail(
                f"Kind {kind_name!r} is already authored in scope {s.scope} "
                f"(approved={bool(existing.get('approved'))}) — re-run with "
                f"--force to EDIT it. The edit drops its approval marker, so a "
                f"human has to approve the new shape before it takes effect."
            )

        if dry_run:
            _report_kind_plan(
                kind_name, scope=s.scope, tenant=tenant, schema=schema,
                traits=declared_traits, relations=declared_relations,
                presentation=declared_presentation, plane=plane,
                effective_plane=effective_plane, existing=existing,
                as_json=as_json,
            )
            return

        from dna_cli.sdlc._common import _cli_actor, _now_iso

        try:
            out = s.run(author_kind_impl(
                live, kind=kind_name, schema=schema, tenant=tenant,
                now=_now_iso(), actor=_cli_actor(),
                traits=declared_traits or None,
                presentation=declared_presentation,
                relations=declared_relations or None,
                plane=plane,
            ))
        except NO_REGISTRY as exc:
            raise _no_registry(exc) from None
        except AUTHORING_REFUSALS as exc:
            # The type name is carried, exactly as ``_mcp_kinds._refuse``
            # carries it: a reader who sees ``SchemaGuardError: …`` can fix
            # their own call; one who sees an unexplained failure re-runs it.
            raise fail(f"{type(exc).__name__}: {exc}") from None
        s.holder.reload()
        scope_used = s.scope

    dropped = _dropped_properties(existing, schema)
    if as_json:
        print_json({**out, "plane_effective": effective_plane,
                    "edited": bool(existing), "dropped_properties": dropped})
        return
    verb = "Re-authored" if existing else "Authored"
    click.secho(
        f"{verb} Kind {out['kind']} in scope {scope_used} as {out['name']}",
        fg="green")
    click.echo(f"  apiVersion  {out['namespace']}/v1")
    click.echo(f"  plane       {effective_plane}"
               + ("" if plane else "  (default — you declared none)"))
    click.echo(f"  traits      {', '.join(declared_traits) or '(none declared)'}")
    click.secho(
        "  approved    false — it validates nothing and routes nothing until "
        "a human approves it.", fg="yellow")
    if existing:
        click.secho(
            "  ⚠️ the edit dropped the previous approval; the shape already in "
            "force stays in force until the new one is approved.", fg="yellow")
    if dropped:
        click.secho(
            f"  ⚠️ the declaration was REBUILT, not merged — {len(dropped)} "
            f"field(s) are gone: {', '.join(dropped)}. Pass them again to keep "
            f"them.", fg="red")
    if not declared_traits:
        click.echo(
            "\n  This Kind declares no trait — a legitimate answer, never "
            "refused. What it costs: nothing that reads a role will find it. "
            "`dna new kind --help` lists the live vocabulary.")
    for line in (out.get("suggestion") or "").splitlines():
        click.echo(f"  {line}")


def _default_plane_for(schema: dict, traits: list[str]) -> str:
    """The plane this Kind will HAVE when the author declared none.

    ⚠️ Delegated to :func:`dna.kernel.kinds.base.default_plane`, never
    re-decided. i-123 moved the default to ``record`` and that function does
    NOT answer ``record`` blindly — it reads ``COMPOSITION_SIGNALS`` off the
    descriptor first, because a Kind carrying one of them would be refused at
    registration next to ``record``. A CLI that printed the word "record" from
    a literal would be right until the day that decision moved, and would then
    report a plane the store does not have.

    The descriptor this command produces declares none of those signals
    (``author_kind_impl`` writes no ``prompt_target``/``is_root``/…), so the
    answer is ``record`` today — but it is ASKED, not assumed, and it is asked
    of the same mapping the registry lint reads.
    """
    from dna.kernel.kinds.base import default_plane

    return default_plane({"schema": schema, "traits": traits})


def _dropped_properties(existing: dict | None, schema: dict) -> list[str]:
    """The schema properties a re-author would REMOVE, named.

    MEASURED 07/08/2026, and it is the sharpest edge this command inherits:
    ``author_kind_impl`` rebuilds the spec from scratch and PERSISTS it
    (``write_instance`` does not merge), so ``dna new kind Contrato --force -d
    outro`` — a one-word edit — leaves ``properties: {}`` behind. That is
    correct and documented behaviour of the door, and the CLI must not "fix" it
    by merging: a merge here would be a second reading of what an edit means,
    and the door's reading is that an edit REPLACES the declaration a human
    approved.

    What the CLI owes is that the author is not surprised, so the loss is
    NAMED, from the stored instance, before and after it happens. Derived —
    never a static warning on ``--force``, which would fire on the edit that
    drops nothing and be ignored by the time it fires on the one that does.
    """
    if not existing:
        return []
    prior = existing.get("schema")
    prior_props = prior.get("properties") if isinstance(prior, dict) else None
    if not isinstance(prior_props, dict):
        return []
    kept = schema.get("properties")
    kept = kept if isinstance(kept, dict) else {}
    return sorted(str(p) for p in prior_props if p not in kept)


def _no_registry(exc: BaseException):
    """The store has no readable namespace-registry scope — an operator's
    missing directory, not a verdict on the call.

    The CLI is the one face whose caller usually IS the operator, so this names
    the fix instead of saying "ask an operator": ``_lib`` is a scope like any
    other and a Genome manifest is four lines. MEASURED 07/08/2026 on a bare
    store — ``assign_namespace`` READS the claim registry before it mints, and
    the filesystem adapter answers a missing scope directory with
    ``FileNotFoundError``, so the very first ``dna new kind`` against a fresh
    ``.dna`` fails here and nowhere else.
    """
    return fail(
        f"the namespace registry scope (`_lib`) is not readable in this store, "
        f"so no Kind can be authored: authoring reads the KindNamespace "
        f"registry before it mints a namespace. On a filesystem store, create "
        f"`<base>/_lib/manifest.yaml` declaring a Genome with `scope: _lib` "
        f"and retry. Underlying: {type(exc).__name__}: {exc}"
    )


def _report_kind_plan(kind_name, *, scope, tenant, schema, traits, relations,
                      presentation, plane, effective_plane, existing, as_json):
    """``--dry-run`` — the plan, and an honest gap in it.

    Same reason ``dna rename`` has one: the store this command writes to is
    usually a git-tracked ``.dna/``, so the result of a real run shows up in a
    PR diff, and the value of a dry run is seeing it before it is there.

    ⚠️ **The instance NAME is not printed, and that is not an oversight.** It
    is ``<namespace>--<Kind>``, and the namespace is MINTED by
    ``assign_namespace`` on a workspace's first author — a write. Reading the
    claim registry here to find an existing one would be a second reading of
    that function's contract ("the earliest ASSIGNED claim, by ``claimed_at``"),
    and a dry run that minted one would be a dry run with a side effect. So the
    plan says what it knows and names what it does not, which is the only shape
    of honest that survives.
    """
    import yaml

    if as_json:
        print_json({
            "dry_run": True, "created": False, "kind": kind_name,
            "scope": scope, "workspace": tenant, "schema": schema,
            "traits": traits, "relations": relations or None,
            "presentation": presentation, "plane": plane,
            "plane_effective": effective_plane,
            "edits_existing": bool(existing), "approved": False,
            "dropped_properties": _dropped_properties(existing, schema),
        })
        return
    verb = "Would RE-AUTHOR" if existing else "Would author"
    click.secho(f"{verb} Kind {kind_name} in scope {scope} "
                f"(workspace {tenant})", fg="cyan")
    click.echo(f"  plane       {effective_plane}"
               + ("" if plane else "  (default — you declared none)"))
    click.echo(f"  traits      {', '.join(traits) or '(none declared)'}")
    click.echo("  relations   "
               f"{', '.join(sorted(relations)) if relations else '(none declared)'}")
    if presentation:
        click.echo(f"  reads as    {', '.join(presentation)}")
    click.echo("  approved    false — authoring never approves.")
    if existing:
        click.secho("  ⚠️ this Kind already exists; the edit would drop its "
                    "approval.", fg="yellow")
        dropped = _dropped_properties(existing, schema)
        if dropped:
            click.secho(
                f"  ⚠️ and would REBUILD the declaration, not merge it — "
                f"{len(dropped)} field(s) would be gone: "
                f"{', '.join(dropped)}.", fg="red")
    click.echo("  schema:")
    for line in yaml.safe_dump(schema, sort_keys=False,
                               allow_unicode=True).splitlines():
        click.echo(f"    {line}")
    click.echo(
        "\nNothing was written (--dry-run). The instance will be named "
        "<namespace>--%s, where <namespace> is the one assigned to workspace "
        "%r — minted on the first real author, and stable afterwards."
        % (kind_name, tenant))
