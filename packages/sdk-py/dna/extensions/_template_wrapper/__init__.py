"""Template — WRAPPER extension skeleton.

Use this as a starting point when absorbing an external best-in-class
tool into the DNA SDK.

Architectural principle (codified Phase 14v.2):

    The DNA SDK does NOT reinvent the wheel. It WRAPS existing tools
    and adds organization (Kinds), governance (audit trail, multi-
    tenant), and compliance (Evidence, Findings cross-ref).

When to use this template (vs writing your own Kind from scratch):

  ✅ Use this when there's a mature OSS/CLI tool that already does
     the core work well (graphify, sbom, coverage, langfuse, ...)
  ✅ Use this when the tool's output is structured (JSON/YAML/file)
     that fits as a KnowledgeArtifact

  ❌ Don't use this for primitives the SDK owns (Agent, Skill,
     Soul, Module — these ARE the SDK's job to define)
  ❌ Don't use this when there's no clear external tool yet — write
     a normal extension with its own Kind

Pattern checklist (copy this into your wrapper extension's docstring):

  1. Hard dep declared in pyproject.toml extras:
       [project.optional-dependencies]
       <toolname> = ["external-package>=X.Y"]

  2. Extension.register() does NOT register Kinds (output is a generic
     KnowledgeArtifact).

  3. Extension.register() probes for the external CLI on PATH.
     Missing → loud warning + extension still loads (CLI later refuses).

  4. CLI subcommand `dna <toolname> build <path> --scope X`:
       a. Validates external tool installed (or fails with install hint)
       b. Subprocesses the tool with capture
       c. Reads the output artifact
       d. Computes sha256 + collects audit metadata (git_sha, who, when)
       e. Publishes as KnowledgeArtifact{tool: <toolname>, ...}
       f. Copies bytes to scope's knowledge-artifacts/ for serving
       g. Mirrors YAML manifest to base layer (visibility across tenants)
       h. (Optional) creates an MCPFederation doc if the tool has --mcp

  5. Doc in docs explaining the wrapper rationale + commands.

See ``dna.extensions.graphify`` for the canonical example.

For the FULL registration contract (Kind + Reader + Writer + hook +
descriptor — what a non-wrapper extension registers), see the commented
``FullContractExtension`` example at the bottom of this module and the
:class:`dna.kernel.protocols.ExtensionHost` Protocol, which
declares the whole registration-time vocabulary.
"""
from __future__ import annotations

import logging
import shutil

from dna.kernel.protocols import ExtensionHost


logger = logging.getLogger(__name__)


# ── Step 1: declare the external CLI binary name ──────────────────────
_TOOL_BINARY = "REPLACE-ME"        # e.g. "graphify", "cyclonedx-cli", "coverage"
_TOOL_PIP_EXTRA = "REPLACE-ME"     # e.g. "graphify", "sbom", "coverage"
_TOOL_PIP_PACKAGE = "REPLACE-ME"   # e.g. "graphifyy>=0.5"


def tool_available() -> bool:
    """True when the external CLI is on PATH."""
    return shutil.which(_TOOL_BINARY) is not None


class TemplateWrapperExtension:
    """Replace 'TemplateWrapper' with your tool's PascalCase name."""

    name = "REPLACE-ME"  # e.g. "graphify"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        # NOTE: NO kernel.kind() calls here — output is KnowledgeArtifact.
        # Wrapper extensions don't introduce new Kinds; they wrap external
        # tools and use the existing KnowledgeArtifact primitive.
        if not tool_available():
            logger.warning(
                f"[{self.name}] CLI '{_TOOL_BINARY}' not found on PATH. "
                f"Install with `pip install 'dna-sdk[{_TOOL_PIP_EXTRA}]'` "
                f"or `pip install {_TOOL_PIP_PACKAGE}`. The extension still "
                f"loads but `dna {self.name} build` will refuse until the "
                f"CLI is installed."
            )
        return None


# ═══════════════════════════════════════════════════════════════════════
# The FULL registration contract — annotated example (non-wrapper case)
# ═══════════════════════════════════════════════════════════════════════
#
# The wrapper skeleton above deliberately registers NOTHING. When your
# extension OWNS a Kind (the common case), `register()` is where you wire
# everything into the kernel. The parameter is typed as `ExtensionHost`
# (dna.kernel.protocols) — the explicit registration-time slice
# of the Kernel. Everything an extension may call at load time is on it:
#
#   kind / kind_from_descriptor / reader / writer / on / on_veto /
#   tool / composition_profile / hooks
#
# `kernel.load(ext)` fail-loud validates `name` (non-empty str),
# `version` (str) and `register` (callable) BEFORE calling register().
# `templates()` is optional — see the `TemplateProvider` Protocol.
#
# Uncomment, rename, and delete what you don't need:
#
#   from dna.kernel.descriptor_loader import load_descriptors
#   from dna.kernel.protocols import ExtensionHost
#
#   class FullContractExtension:
#       name = "mytool"            # globally unique; also the alias owner —
#                                  # Kind aliases become "mytool-<kind>"
#       version = "1.0.0"
#
#       def register(self, kernel: ExtensionHost) -> None:
#           # 1. A class-based DEFINITION Kind (identity + composition).
#           #    Only definition-plane Kinds with behavior (custom
#           #    prompt_section, graph_meta, ...) get a class. See
#           #    kernel.kind_base.KindBase for the base.
#           kernel.kind(MyToolKind())
#
#           # 2. Record Kinds are DATA, not classes (F3, 2026-06-10):
#           #    drop a kinds/<name>.kind.yaml (KindDefinition format)
#           #    into this package and synthesize the port from it.
#           #    The ratchet test blocks new record Kinds as classes.
#           for raw in load_descriptors("dna.extensions.mytool"):
#               kernel.kind_from_descriptor(raw)
#
#           # 3. Custom bundle format? Register a Reader (detect/scan)
#           #    and a Writer (emit) — e.g. a MYTOOL.md marker file.
#           #    Skip both when plain YAML storage is enough (the generic
#           #    machinery handles it).
#           kernel.reader(MyToolReader())
#           kernel.writer(MyToolWriter())
#
#           # 4. Lifecycle hooks. `on` = event subscriber (post_save, ...);
#           #    `on_veto` = write guard (pre_save) — raising VETOES the
#           #    write. Use `kernel.hooks.on_veto(..., key=...)` for
#           #    idempotent re-registration (key REPLACES, not stacks).
#           kernel.on("post_save", my_post_save_handler)
#           kernel.hooks.on_veto(
#               "pre_save", my_write_guard,
#               priority=10, key="mytool.my-write-guard",
#           )
#
#           # 5. Agent tools (@dna_tool metadata; Python-only for now).
#           kernel.tool(MY_TOOL_DEFINITION)
#
#           # 6. Orchestrator Kind? Declare how it wires to other Kinds.
#           kernel.composition_profile(MYTOOL_PROFILE)
#
#       # 7. OPTIONAL — ship scaffold file trees (TemplateProvider):
#       #    `kernel.list_templates()` aggregates these for Studio/CLI.
#       def templates(self):
#           return [MYTOOL_TEMPLATE]
