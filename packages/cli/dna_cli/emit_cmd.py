"""``dna emit`` — materialize a DNA agent into a runtime's NATIVE artifact.

The CLI half of the vendor-neutral emitter (``dna.emit``). Author an agent ONCE
in DNA (Agent + Soul + Guardrails + Tools) and ``dna emit`` renders the exact
artifact a target runtime consumes — the first concrete step of "DNA as the
Terraform of agents".

    dna emit <agent> --target agent-framework [--scope S] [--out FILE]
                     [--model M] [--provider P] [--json]
    dna emit --list-targets

The emission logic lives in the SDK (``dna.emit``): a pluggable ``EmitterPort``
registry. ``agent-framework`` is the first target; a new one (bedrock / vertex /
openai) is a class + one ``register_emitter(...)`` call — this CLI never changes.
"""
from __future__ import annotations

import click

from dna_cli._ctx import dna_session, fail, print_json


@click.command("emit", help="Emit a DNA agent as a target runtime's native artifact (the de-para).")
@click.argument("agent", required=False)
@click.option("--target", "-t", default=None,
              help="Runtime to emit for (e.g. agent-framework). See --list-targets.")
@click.option("--scope", default=None, help="Scope holding the agent (default: env / sole scope).")
@click.option("--out", "-o", "out_path", default=None,
              help="Write the artifact to this file instead of stdout.")
@click.option("--model", default=None,
              help="Override the model coordinate (else agent.spec.model / Genome default_llm).")
@click.option("--provider", default=None,
              help="Override the provider the target binds (e.g. AzureOpenAI, OpenAI).")
@click.option("--list-targets", "list_targets", is_flag=True,
              help="List the registered emit targets and exit.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output (artifact + de-para).")
def emit(agent, target, scope, out_path, model, provider, list_targets, as_json):
    """Render AGENT for a runtime TARGET.

    \b
    Examples:
      dna emit --list-targets
      dna emit concierge-grounded --target agent-framework
      dna emit triage -t agent-framework --scope support --out triage.agent.yaml
      dna emit greeter -t agent-framework --model openai:gpt-4o-mini
    """
    from dna.emit import available_targets, emit_agent, EmitError, UnknownTarget

    if list_targets:
        targets = available_targets()
        if as_json:
            print_json({"targets": targets})
            return
        click.secho("Registered emit targets:", fg="cyan")
        for t in targets:
            click.echo(f"  - {t}")
        return

    if not agent:
        raise fail("missing AGENT argument (or pass --list-targets)")
    if not target:
        raise fail("missing --target (see `dna emit --list-targets`)")

    with dna_session(scope) as s:
        try:
            result = emit_agent(s.mi, agent, target, model=model, provider=provider)
        except UnknownTarget as e:
            raise fail(str(e)) from None
        except EmitError as e:
            raise fail(f"emit failed: {e}") from None

    import os

    multi = len(result.artifacts) > 1

    if not multi and out_path:
        # Single-artifact path — byte-identical to before: write the one file.
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(result.artifact)
    elif multi:
        # Multi-artifact: --out is a DIRECTORY; write every EmitArtifact.path.
        if not out_path:
            raise fail("multi-artifact emit needs --out DIR (writes N files)")
        for a in result.artifacts:
            dest = os.path.join(out_path, a.path)
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(a.content)

    if as_json:
        print_json({
            "agent": agent,
            "target": result.target,
            "scope": s.scope,
            # Legacy keys (the role='agent' view) stay for back-compat …
            "filename": result.filename,
            "out": out_path,
            "artifact": result.artifact,
            # … with the full N-artifact list alongside.
            "artifacts": [
                {"path": a.path, "content": a.content, "role": a.role}
                for a in result.artifacts
            ],
            "mapping": result.mapping,
            "losses": result.losses,
        })
        return

    if multi:
        click.secho(
            f"Emitted {agent} → {target}: {len(result.artifacts)} files under {out_path}/",
            fg="green",
        )
    elif out_path:
        click.secho(f"Emitted {agent} → {target}: {out_path}", fg="green")
    else:
        click.echo(result.artifact, nl=False)
    # The de-para is honest about what did NOT survive — always surfaced (stderr,
    # so piping `dna emit ... > file` keeps the artifact clean).
    if result.losses:
        click.secho("\n# de-para — DNA axes with no slot in this target:", fg="yellow", err=True)
        for loss in result.losses:
            click.secho(f"#   - {loss}", fg="yellow", err=True)
