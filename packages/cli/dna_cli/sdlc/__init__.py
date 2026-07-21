"""``dna sdlc`` command surface — decomposed package.

``sdlc_cmd.py`` grew to ~7.2k lines / 100 commands across 20 groups — half
the CLI. This package is the incremental decomposition of that module,
following the same idiom the kernel decomposition used
(``s-kernel-decompose-god-object`` → ``s-kernel-decomp-f2..f5``): extract a
seam, leave a ``# noqa: F401`` re-export behind, never big-bang
(``adr-faces-reorg``).

Import order matters only for *registration*, not for ``--help`` ordering —
``click.Group.list_commands`` sorts alphabetically, so moving a group between
modules cannot perturb the rendered CLI surface.

``dna_cli.sdlc_cmd`` remains the public import path: every name that used to
live there still resolves there.
"""
