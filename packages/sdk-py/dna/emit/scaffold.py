"""``dna.emit.scaffold`` — the CODE-FIRST flavor of the :class:`~dna.emit.EmitterPort`.

Some runtimes have **no declarative agent format** — you construct an agent object
in Python (OpenAI Agents SDK, LangGraph, Agno, DeepAgents all expose a simple
constructor: ``Agent(name=, instructions=, model=, tools=[])`` and friends). For
those there is nothing to map a YAML/JSON schema onto, so the emitter must produce
**source code**. It does so by **filling a curated template**, never by generating
code ad-hoc — the template captures the framework's best-practice idiom; the
emitter only routes to the right one and fills the blanks.

The mechanism is a **template library indexed by ``{framework × case}``**, plus a
tiny **case classifier**:

    scaffolds/<framework>/<case>.py.tmpl     # curated best-practice idiom per case
    select_scaffold(framework, ctx)          # inspect ctx's DNA signals → pick a case

There is deliberately NO single "one template per framework". A prompt-only agent,
a tool-calling (ReAct) agent, and a structured-output agent are DIFFERENT
structures in the SAME framework — each deserves its own curated template. The
classifier reads the signals the neutral :class:`~dna.emit.EmitContext` already
carries:

    - no tools            -> ``prompt-only``
    - tools present       -> ``with-tools``   (the ReAct / tool-calling idiom)
    - ``output_schema``   -> ``structured-output``

A framework may ship only a subset of cases; :func:`select_scaffold` falls back
down a generality chain (``structured-output`` → ``with-tools`` → ``prompt-only``)
and records the fallback as a loss, so the de-para stays honest.

Adding a CASE is additive and code-free-ish: drop a
``scaffolds/<framework>/<case>.py.tmpl`` and (if it's a genuinely new signal) add
one line to the classifier — no change to the emit core. See the
`How to write an emitter <../guides/writing-an-emitter.md>`_ guide.

**Future direction — Scaffold as a Kind.** Templates are read through an abstract
seam, :func:`resolve_scaffold` (a :class:`ScaffoldResolver`), *not* a hardcoded
file path. The MVP resolver reads package-data
(``emit/scaffolds/<framework>/<case>.py.tmpl``), but the seam lets a **second
source** plug in with no change to any emitter: a first-class **Scaffold Kind**
resolved by the kernel — scope-aware and overridable per tenant, like every other
DNA Kind. That is the DNA thesis applied to its own de-para: a team ships its
house-style template for a framework as an overlay instead of forking the SDK.
The promotion is tracked as story ``s-scaffold-as-kind``; this module only
guarantees the MVP does not paint us into a corner.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from dna.emit import EmitContext, EmitError, EmitResult

#: The generality fallback chain: a more specific case falls back to a more
#: general one when a framework does not (yet) ship that case's template.
_FALLBACK: dict[str, list[str]] = {
    "structured-output": ["structured-output", "with-tools", "prompt-only"],
    "with-tools": ["with-tools", "prompt-only"],
    "prompt-only": ["prompt-only"],
}


def py_str_literal(value: str) -> str:
    """Render ``value`` as a Python string literal that round-trips exactly.

    Uses ``repr`` so the emitted source is byte-equal-recoverable via
    ``ast.literal_eval`` — the mechanism behind the scaffold's byte-equal
    invariant hook (:meth:`ScaffoldEmitter.extract_instructions`). Correctness
    over prettiness: the instruction is emitted as a named ``INSTRUCTIONS``
    constant so the constructor call stays clean regardless.
    """
    return repr(value)


def py_identifier(name: str) -> str:
    """``kb-search`` → ``kb_search`` — a valid Python identifier for a tool stub."""
    out = []
    for ch in str(name).strip():
        out.append(ch if (ch.isalnum() or ch == "_") else "_")
    ident = "".join(out).strip("_") or "tool"
    if ident[0].isdigit():
        ident = f"_{ident}"
    return ident


def pg_env_var(ref: str) -> str:
    """Derive the env-var name that holds the Postgres DSN for an infra ``ref``.

    ``primary-pg`` → ``DNA_PRIMARY_PG_URL``. The emitter NEVER hardcodes a DSN
    literal — it emits an ``os.environ[...]`` read keyed by the ref, and the
    ``f-copilot-infra-binding`` feature wires the ref → env-var (a Terraform
    module output) at deploy time. Two slots that share one ``ref`` (one physical
    Postgres) resolve to the SAME env var, exactly as the design intends.
    """
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ref).strip("_").upper()
    return f"DNA_{slug}_URL"


def pg_url_expr(ref: str) -> str:
    """The Python expression that reads the Postgres DSN for ``ref`` from the env
    (``os.environ["DNA_PRIMARY_PG_URL"]``) — the emitted, never-hardcoded DSN."""
    return f'os.environ["{pg_env_var(ref)}"]'


def persistence_facts(ctx: EmitContext) -> dict[str, Any]:
    """Neutral persistence/knowledge-store facts shared by every scaffold emitter.

    Reads ``ctx.persistence`` (``{checkpoint, memory, cache}``) + ``ctx.
    knowledge_store`` into plain flags + env-var-backed DSN expressions, so each
    framework's copilot template maps the SAME facts onto its own classes
    (Agno ``PostgresDb``/``PgVector``, LangGraph ``PostgresSaver``/``PostgresStore``,
    MS-AF ``PostgresVectorStore`` + serialize-yourself). Kept in ONE place so the
    Py↔TS twin cannot drift. Absent/None slots → the framework default (in-memory),
    exactly the back-compat shape a copilot with no ``persistence`` block emits.
    """
    persistence = ctx.persistence or {}
    checkpoint = persistence.get("checkpoint") or {}
    memory = persistence.get("memory") or {}
    store = ctx.knowledge_store or {}
    embed = store.get("embed") or {}

    checkpoint_pg = checkpoint.get("backend") == "postgres"
    memory_pg = memory.get("backend") == "postgres"
    # checkpoint + memory may share one physical Postgres (one ``ref``) — prefer
    # the checkpoint ref, fall back to the memory ref for the shared DSN.
    pg_ref = checkpoint.get("ref") if checkpoint_pg else (memory.get("ref") if memory_pg else None)
    vector_pg = store.get("backend") == "pgvector"

    return {
        "checkpoint_pg": checkpoint_pg,
        "memory_pg": memory_pg,
        "checkpoint_ref": checkpoint.get("ref") if checkpoint_pg else None,
        "memory_ref": memory.get("ref") if memory_pg else None,
        "pg_ref": pg_ref,
        "vector_pg": vector_pg,
        "vector_ref": store.get("ref"),
        "embed_model": embed.get("model"),
        "embed_dims": embed.get("dims"),
    }


def classify_case(ctx: EmitContext) -> str:
    """The default case classifier — read the DNA signals the ctx already carries.

    ``output_schema`` → ``structured-output``; else tools → ``with-tools``; else
    ``prompt-only``. An emitter may override :meth:`ScaffoldEmitter.classify` to
    add a framework-specific case (e.g. a guardrail idiom), but the routing stays
    pure *selection*, never code generation.
    """
    if ctx.output_schema:
        return "structured-output"
    if ctx.tools:
        return "with-tools"
    return "prompt-only"


# ── the template-resolution seam (package-data today; Scaffold Kind tomorrow) ─


@runtime_checkable
class ScaffoldResolver(Protocol):
    """Resolve a ``{framework × case}`` template to its Mustache source.

    The ABSTRACT seam between an emitter and *where a template lives*. The MVP
    reads package-data (:class:`PackageDataScaffoldResolver`); a future
    kernel-backed resolver returns a per-scope/per-tenant **Scaffold Kind** body
    instead — swapping one for the other requires no change to any emitter.
    Returns ``None`` when the source has no template for that pair.
    """

    def resolve(self, framework: str, case: str) -> str | None:
        ...


class PackageDataScaffoldResolver:
    """The MVP resolver: read ``emit/scaffolds/<framework>/<case>.py.tmpl``."""

    def resolve(self, framework: str, case: str) -> str | None:
        from importlib.resources import files

        try:
            res = files("dna.emit").joinpath("scaffolds", framework, f"{case}.py.tmpl")
            if res.is_file():
                return res.read_text(encoding="utf-8")
        except (FileNotFoundError, ModuleNotFoundError, NotADirectoryError):
            return None
        return None


_ACTIVE_RESOLVER: ScaffoldResolver = PackageDataScaffoldResolver()


def set_scaffold_resolver(resolver: ScaffoldResolver) -> ScaffoldResolver:
    """Swap the active template resolver (e.g. a host's kernel-backed one). The
    seam the Scaffold-as-Kind promotion (``s-scaffold-as-kind``) plugs into."""
    global _ACTIVE_RESOLVER
    _ACTIVE_RESOLVER = resolver
    return resolver


def resolve_scaffold(framework: str, case: str) -> str | None:
    """Resolve a ``{framework × case}`` template through the active resolver."""
    return _ACTIVE_RESOLVER.resolve(framework, case)


@dataclass
class ScaffoldChoice:
    """The outcome of :func:`select_scaffold`: which case template to fill."""

    #: The case actually selected (a template file exists for it).
    case: str
    #: The template source (Mustache).
    template: str
    #: The case the classifier *requested* — differs from ``case`` when a
    #: framework did not ship the ideal template and we fell back (a loss).
    requested: str


def select_scaffold(
    framework: str,
    ctx: EmitContext,
    *,
    classify: Callable[[EmitContext], str] = classify_case,
    resolver: ScaffoldResolver | None = None,
) -> ScaffoldChoice:
    """Pick the ``{framework × case}`` template for ``ctx``.

    Classifies the case from the ctx's DNA signals, then resolves it to a real
    template *through the resolution seam* (:func:`resolve_scaffold`, or an
    explicit ``resolver``) — falling back down the generality chain when the ideal
    case is not shipped. Raises :class:`~dna.emit.EmitError` when the framework has
    no templates at all (a misconfigured emitter).
    """
    resolve = resolver.resolve if resolver is not None else resolve_scaffold
    requested = classify(ctx)
    for case in _FALLBACK.get(requested, [requested]):
        template = resolve(framework, case)
        if template is not None:
            return ScaffoldChoice(case=case, template=template, requested=requested)
    raise EmitError(
        f"no scaffold template for framework {framework!r} "
        f"(looked for case {requested!r} and its fallbacks)"
    )


class ScaffoldEmitter:
    """Base for a CODE-FIRST :class:`~dna.emit.EmitterPort`.

    A subclass is THIN — it declares the framework + target ids and supplies the
    framework-specific template variables (:meth:`render_context`), losses, and
    field mapping. Everything else — case selection, template fill, the byte-equal
    invariant hook — is inherited. This is why the next code-first targets
    (langgraph / agno / deepagents) are "a couple of template files + a small
    mapping", not a new engine.
    """

    #: Subdir under ``scaffolds/`` holding this framework's case templates.
    framework: str = ""
    #: Stable target id used on ``dna emit --target <id>``.
    target: str = ""
    #: Emitted-artifact extension (source code → ``py``).
    file_extension: str = "py"
    #: Optional template-resolution override (defaults to the active resolver —
    #: package-data today, a Scaffold Kind resolver tomorrow). The seam
    #: ``s-scaffold-as-kind`` plugs into without touching this emitter.
    resolver: ScaffoldResolver | None = None

    # ── the two hooks a subclass overrides ──────────────────────────────────

    def render_context(self, ctx: EmitContext, case: str) -> dict[str, Any]:
        """Framework-specific template variables (merged over the common ones)."""
        return {}

    def losses(self, ctx: EmitContext, choice: ScaffoldChoice) -> list[str]:
        """Framework-specific de-para losses (in addition to the common ones)."""
        return []

    def mapping(self) -> dict[str, str]:
        """Field-level de-para (``dna_field -> target_field``) for reporting."""
        return {}

    def classify(self, ctx: EmitContext) -> str:
        """The case classifier — override to add a framework-specific case."""
        return classify_case(ctx)

    # ── the inherited machinery ─────────────────────────────────────────────

    def _common_context(self, ctx: EmitContext) -> dict[str, Any]:
        return {
            "name": ctx.name,
            "name_literal": py_str_literal(ctx.name),
            "description": ctx.description,
            "has_description": bool(ctx.description),
            # INSTRUCTIONS constant — byte-equal, recoverable via ast.literal_eval.
            "instructions_literal": py_str_literal(ctx.instructions),
        }

    def _common_losses(self, ctx: EmitContext, choice: ScaffoldChoice) -> list[str]:
        losses = [
            "composition structure — Soul reuse + wired Guardrails flatten to one "
            "`INSTRUCTIONS` string (a code-first agent has no `soul:`/`guardrails:` slot)",
            "tenant overlay — a per-tenant persona without a fork has no code-first field",
            "eval-as-contract — prompt invariants (EvalCases) have no code-first slot",
        ]
        if choice.case != choice.requested:
            losses.append(
                f"scaffold case — the {choice.requested!r} idiom is not shipped for "
                f"{self.framework!r}; fell back to the {choice.case!r} template "
                "(structure closest to but not identical to the requested case)"
            )
        return losses

    def emit(self, ctx: EmitContext) -> EmitResult:
        try:
            import chevron
        except ModuleNotFoundError as exc:  # pragma: no cover - dev dep always present
            raise EmitError(
                "the scaffold emitter needs `chevron` (Mustache) — it ships with the SDK"
            ) from exc

        choice = select_scaffold(
            self.framework, ctx, classify=self.classify, resolver=self.resolver
        )
        variables = {**self._common_context(ctx), **self.render_context(ctx, choice.case)}
        artifact = chevron.render(choice.template, variables)

        losses = self._common_losses(ctx, choice) + self.losses(ctx, choice)
        return EmitResult(
            artifact=artifact,
            target=self.target,
            filename=f"{ctx.name}.{self.file_extension}",
            losses=losses,
            mapping=self.mapping(),
        )

    def extract_instructions(self, artifact: str) -> str | None:
        """Byte-equal invariant hook: AST-read the ``INSTRUCTIONS`` constant.

        Every scaffold template emits the composed prompt as a top-level
        ``INSTRUCTIONS = <literal>`` assignment, so the invariant check is uniform
        across all code-first targets and does not depend on the constructor
        shape. Also proves the artifact PARSES (a `py_compile`-grade guarantee).
        """
        import ast

        module = ast.parse(artifact)
        for node in module.body:
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == "INSTRUCTIONS":
                        return ast.literal_eval(node.value)
        return None
