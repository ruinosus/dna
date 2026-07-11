"""``dna new`` — scaffold a valid Kind skeleton into a scope.

s-dx-new-scaffolding — authoring an agent or a soul used to mean remembering
the envelope by hand (``apiVersion``/``kind``/``metadata``/``spec``), the
right bundle marker (``AGENT.md`` vs ``SOUL.md``), and which spec fields are
even allowed. ``dna new`` writes the correct skeleton for you — through
``kernel.write_document`` (never a hand-rolled YAML dump), so every write
guard, schema check and reader/writer round-trip runs exactly as on any other
write — leaving you with a valid doc whose only empty part is the prose you
came to write.

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

Idempotent: an existing doc is never overwritten without ``--force``.
"""
from __future__ import annotations

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
    """Shared write path: existence gate → kernel.write_document → report."""
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
        s.run(s.kernel.write_document(s.scope, kind, name, raw))
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


@click.group("new", help="Scaffold a valid Kind skeleton into a scope (agent | soul | guardrail | tool).")
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
