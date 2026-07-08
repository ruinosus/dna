# AgentDefinition (AGENTS.md)

AgentDefinition wraps a standalone `AGENTS.md` file as a first-class document
kind. `AGENTS.md` is an emerging community convention
(https://agents.md) for giving coding agents repo-level instructions —
similar in spirit to `README.md` but targeted at autonomous agents rather than
human readers.

The AgentsMdExtension scans for a top-level `AGENTS.md` in the manifest scope
and exposes its content as a document. It is NOT a prompt target on its own;
it is context material that agents and tooling can surface when operating in
that repository.

**When to use:** drop an `AGENTS.md` alongside your module manifest to record
repo-wide conventions, coding style, test commands, or operational notes that
any agent working in the scope should respect. Unlike Souls (which describe
voice) and Skills (which describe procedures), AgentContext describes the
environment the agent is working in.
