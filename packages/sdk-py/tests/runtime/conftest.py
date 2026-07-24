"""Collection guard for the runtime adapter/middleware suite.

These tests exercise ``dna.runtime`` (the LangChain/LangGraph copilot machine),
whose modules import ``langchain`` / ``fastapi`` at their top. The ``runtime``
extra is deliberately OUT of ``[dev]``/``[all]`` (heavy — see
packages/sdk-py/pyproject.toml), so the base ``sdk-py`` and ``postgres`` CI jobs
install without it.

pytest collection runs BEFORE marker filtering, so without this guard those jobs
— which never RUN these tests (the postgres job filters to ``-m
requires_postgres``) — would still FAIL to COLLECT them on the missing imports,
turning the whole job red. ``collect_ignore_glob`` drops the directory entirely
when the optional deps are absent; the CI ``sdk-py`` job installs
``.[dev,runtime]`` + fastapi + ag-ui-langgraph so the suite runs there. The
``maf`` adapter tests carry their own ``importorskip('agent_framework')`` — that
extra is heavy enough to stay out even of the runtime job.
"""

collect_ignore_glob: list[str] = []
try:
    import fastapi  # noqa: F401
    import langchain_core  # noqa: F401
except ModuleNotFoundError:
    collect_ignore_glob = ["*"]
