"""``dna install`` — install bundles/Kinds from an external repo (s-dna-install).

The front door of the ecosystem: fetch a tree from a repository, detect the
DNA documents inside it with the kernel's registered readers, validate each
one, and write the valid ones into the local source through
``kernel.write_document`` — so every write guard the kernel has (schema
vetoes, tenancy rules, Kind retirement blocks) runs exactly as it would for
a locally-authored doc.

URI grammar (the same one ``GitHubResolver`` has always parsed for Genome
dependencies — see ``dna/adapters/resolvers/github.py``):

    github:owner/repo[/subdir][@ref]   # shallow clone, optional subtree + ref
    local:<path>                       # a directory on disk (offline-friendly)

SECURITY — manifests from a third-party repository are UNTRUSTED DATA, not
code you have reviewed. ``dna install`` treats them accordingly (the layered
defense SECURITY.md's threat model calls for — "a manifest is executable
behavior"):

  * only documents whose ``(apiVersion, kind)`` resolves to a registered
    KindPort are considered — everything else is rejected, not guessed at;
  * each doc's ``spec`` is validated against the Kind's JSON Schema BEFORE
    any write (the first defense); the kernel's own ``pre_save`` veto guards
    then run as the second;
  * document names must be plain slugs — path-shaped names (``../evil``)
    are rejected before they ever reach the filesystem adapter;
  * root Kinds (Genome) found in the fetched tree are never installed:
    ``dna install`` installs CONTENT into your scope, it does not let a
    remote repo redefine the scope's identity.

Provenance: every install upserts ``<scope>/installed.lock`` (the lockfile
shape from ``dna.kernel.lock`` — v3), recording per document the origin URI
pinned to the resolved commit, the path inside the fetched tree, and a
SHA-256 of the installed raw doc.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import click
import yaml

from dna_cli._ctx import dna_session, fail, print_json

# Names must be plain slugs: no separators, no traversal, no dotfiles.
# The FS adapter path-joins ``<scope>/<container>/<name>`` verbatim, so this
# guard is load-bearing, not cosmetic.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_SKIP_DIRS = {"node_modules", "__pycache__"}


# ─── scan ─────────────────────────────────────────────────────────────


@dataclass
class ScannedDoc:
    """One raw document found in the fetched tree."""
    raw: dict
    rel_path: str  # path of the bundle dir / yaml file, relative to the root


def _scan_tree(root: Path, readers: list, writers: list | None = None) -> list[ScannedDoc]:
    """Walk ``root`` detecting documents with the registered readers.

    Mirrors ``FilesystemCache._read_tree`` (the kernel's own reader-driven
    scan of resolved dependencies) with two install-specific twists: the
    root directory itself is probed first (so a URI can point straight at a
    single bundle), and standalone ``*.yaml`` documents are collected at
    every level.

    A claim consumes its BUNDLE, not the subtree (i-016). When a reader
    claims a directory, the matching WriterPort's ``serialize(raw)`` is the
    authoritative extent of the claimed bundle (``write ≡ serialize`` is
    enforced per registered pair by the round-trip conformance suite);
    everything the claim did not consume keeps scanning. So a single-file
    claim at the tree root (AGENTS.md) no longer hides the ``skills/`` tree
    next to it, while a Skill bundle (SKILL.md + companions) still scans as
    exactly ONE doc — its consumed files and subdirs are never re-collected.
    Without ``writers`` (or when no writer matches the claimed doc) the
    extent is unknowable and the scan falls back to the conservative
    historic semantics: the whole subtree is the bundle.
    """
    from dna.kernel.bundle.handle import FilesystemBundleHandle

    found: list[ScannedDoc] = []

    def _rel(p: Path) -> str:
        return "." if p == root else str(p.relative_to(root))

    def _consumed_paths(raw: dict) -> set[str] | None:
        """Relative paths making up the claimed bundle, or None = unknown."""
        for w in writers or ():
            try:
                if w.can_write(raw):
                    return {str(e["relativePath"]) for e in w.serialize(raw)}
            except Exception:  # noqa: BLE001 — the extent probe must never kill the scan
                return None
        return None

    def _visit(directory: Path) -> None:
        bundle = FilesystemBundleHandle(directory)
        consumed: set[str] = set()
        for reader in readers:
            try:
                if reader.detect(bundle):
                    raw = reader.read(bundle)
                    if not (isinstance(raw, dict) and raw.get("kind")):
                        return  # claimed but not a doc — subtree stays opaque
                    found.append(ScannedDoc(raw=raw, rel_path=_rel(directory)))
                    paths = _consumed_paths(raw)
                    if paths is None:
                        return  # unknown extent — the subtree is the bundle
                    consumed = paths
                    break  # first claiming reader wins for this directory
            except Exception as e:  # noqa: BLE001 — one broken bundle must not kill the scan
                click.secho(
                    f"warning: reader {type(reader).__name__} failed on "
                    f"{_rel(directory)}: {e}",
                    fg="yellow", err=True,
                )
        for yf in sorted(list(directory.glob("*.yaml")) + list(directory.glob("*.yml"))):
            if yf.name in consumed:
                continue  # part of the claimed bundle, not a standalone doc
            try:
                content = yaml.safe_load(yf.read_text(encoding="utf-8"))
            except (yaml.YAMLError, UnicodeDecodeError):
                continue
            if (
                isinstance(content, dict)
                and content.get("apiVersion")
                and content.get("kind")
                and isinstance(content.get("metadata"), dict)
                and content["metadata"].get("name")
            ):
                found.append(ScannedDoc(raw=content, rel_path=_rel(yf)))
        for sub in sorted(directory.iterdir()):
            if not sub.is_dir() or sub.name.startswith(".") or sub.name in _SKIP_DIRS:
                continue
            if any(p.startswith(sub.name + "/") for p in consumed):
                continue  # the claimed bundle owns this subdir — one doc, no dupes
            _visit(sub)

    _visit(root)
    return found


# ─── plan ─────────────────────────────────────────────────────────────


@dataclass
class PlanItem:
    """One document in the install plan."""
    kind: str
    name: str
    api_version: str
    rel_path: str
    action: str          # install | overwrite | skip | reject
    note: str = ""
    raw: dict = field(default_factory=dict)


def _validate_doc(kernel, scanned: ScannedDoc) -> str | None:
    """First-defense validation of an untrusted doc. Returns a rejection
    reason (didactic, one line) or None when the doc may proceed to the
    kernel write (where the pre_save veto guards run as second defense)."""
    raw = scanned.raw
    kind = raw.get("kind", "")
    api_version = raw.get("apiVersion", "")
    name = ((raw.get("metadata") or {}).get("name")) or ""

    if not name or not isinstance(name, str):
        return "document has no metadata.name"
    if not _SAFE_NAME.match(name) or ".." in name:
        return (
            f"name {name!r} is not a plain slug — path-shaped names are "
            f"rejected (untrusted input never reaches the filesystem layout)"
        )

    kp = kernel.kind_port_for(kind, api_version=api_version)
    if kp is None:
        return (
            f"Kind {kind!r} ({api_version}) is not registered in this kernel "
            f"— `dna kind list` shows what this installation understands"
        )
    if getattr(kp, "is_root", False):
        return (
            "root Kind (scope identity) — `dna install` installs content, "
            "it never lets a remote repo redefine the target scope's Genome"
        )

    schema = None
    try:
        schema = kp.schema()
    except Exception:  # noqa: BLE001 — a Kind without a working schema stays permissive
        schema = None
    if isinstance(schema, dict) and schema:
        import jsonschema
        try:
            jsonschema.validate(raw.get("spec") or {}, schema)
        except jsonschema.ValidationError as e:
            path = ".".join(str(p) for p in e.absolute_path) or "spec"
            return (
                f"schema validation failed at spec.{path}: {e.message} — "
                f"see `dna kind show {kind}` for the expected shape"
            )
    return None


async def _build_plan(
    kernel, scope: str, scanned: list[ScannedDoc], force: bool,
) -> list[PlanItem]:
    plan: list[PlanItem] = []
    seen: set[tuple[str, str]] = set()
    for sd in scanned:
        raw = sd.raw
        kind = str(raw.get("kind", ""))
        api_version = str(raw.get("apiVersion", ""))
        name = str(((raw.get("metadata") or {}).get("name")) or "")
        item = PlanItem(
            kind=kind, name=name, api_version=api_version,
            rel_path=sd.rel_path, action="install", raw=raw,
        )
        reason = _validate_doc(kernel, sd)
        if reason:
            item.action, item.note = "reject", reason
            plan.append(item)
            continue
        if (kind, name) in seen:
            item.action = "reject"
            item.note = "duplicate (kind, name) earlier in the fetched tree wins"
            plan.append(item)
            continue
        seen.add((kind, name))
        try:
            existing = await kernel.get_document(scope, kind, name)
        except FileNotFoundError:
            existing = None  # scope not born yet — no local doc to conflict with
        if existing is not None:
            if force:
                item.action, item.note = "overwrite", "exists locally — --force"
            else:
                item.action = "skip"
                item.note = "already exists locally (use --force to overwrite)"
        plan.append(item)
    return plan


# ─── provenance ───────────────────────────────────────────────────────


def _pinned_origin(uri: str, commit: str | None) -> str:
    """The origin URI pinned to the immutable revision that was fetched
    (``github:owner/repo[/subdir]@<commit>``); local trees stay as-is."""
    if not commit:
        return uri
    base = uri.split("@", 1)[0]
    return f"{base}@{commit}"


def _write_provenance(
    base_dir: str, scope: str, origin: str,
    installed: list[PlanItem],
) -> Path:
    """Upsert ``<scope>/installed.lock`` — reuses the kernel's lockfile v3
    shape (``dna.kernel.lock``) verbatim: merge by (kind, name), origin =
    pinned URI, path = location inside the fetched tree, sha256 of the
    canonical raw-doc JSON (same digest recipe as ``mi.lock.generate()``)."""
    from dna.kernel.lock import LockEntry, Lockfile, read_lockfile, write_lockfile

    lock_path = Path(base_dir) / scope / "installed.lock"
    existing = read_lockfile(lock_path)
    merged: dict[tuple[str, str], LockEntry] = {
        (e.kind, e.name): e for e in existing.documents
    }
    for item in installed:
        digest = hashlib.sha256(
            json.dumps(item.raw, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        merged[(item.kind, item.name)] = LockEntry(
            name=item.name, kind=item.kind, api_version=item.api_version,
            origin=origin, path=item.rel_path, sha256=digest,
        )
    lock = Lockfile(
        scope=scope,
        documents=sorted(merged.values(), key=lambda e: (e.kind, e.name)),
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    write_lockfile(lock, lock_path)
    return lock_path


# ─── fetch ────────────────────────────────────────────────────────────


@dataclass
class Fetched:
    root: Path
    origin: str          # provenance origin (commit-pinned for github)
    describe: str        # one-line human description of what was fetched


def _fetch(uri: str) -> Fetched:
    """Resolve a ``github:`` / ``local:`` URI to a directory tree.

    Network and not-found failures surface as didactic ClickExceptions,
    never tracebacks.
    """
    if uri.startswith("github:"):
        from dna.adapters.resolvers.github import GitHubResolver
        from dna.kernel.protocols import ResolveError
        try:
            ft = GitHubResolver().fetch_tree(uri)
        except ResolveError as e:
            raise click.ClickException(
                f"{e}\n\n"
                "Could not fetch the repository. Check that:\n"
                "  - the URI is github:owner/repo[/subdir][@ref] "
                "(e.g. github:anthropics/skills/skills@main)\n"
                "  - the repo is public and the ref/subdir exist\n"
                "  - you are online (offline? use local:<path> against a "
                "clone you already have)"
            ) from e
        pinned = _pinned_origin(uri, ft.commit)
        describe = f"{ft.owner}/{ft.repo}" + (f"/{ft.subdir}" if ft.subdir else "")
        if ft.ref:
            describe += f"@{ft.ref}"
        if ft.commit:
            describe += f" (commit {ft.commit[:12]})"
        return Fetched(root=ft.root, origin=pinned, describe=describe)

    if uri.startswith("local:"):
        path = Path(uri.removeprefix("local:")).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.is_dir():
            raise click.ClickException(
                f"local path {path} does not exist or is not a directory"
            )
        return Fetched(root=path, origin=uri, describe=str(path))

    raise click.ClickException(
        f"unsupported install URI {uri!r} — use github:owner/repo[/subdir][@ref] "
        f"or local:<path>"
    )


def _derive_scope(uri: str) -> str:
    """Default target scope from the URI: ``<owner>-<repo>`` for github,
    the directory basename for local."""
    if uri.startswith("github:"):
        from dna.adapters.resolvers.github import parse_github_uri
        owner, repo, _, _ = parse_github_uri(uri)
        slug = f"{owner}-{repo}"
    else:
        slug = Path(uri.removeprefix("local:")).name or "installed"
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", slug).strip("-").lower()
    return slug or "installed"


# ─── command ──────────────────────────────────────────────────────────

_ACTION_COLORS = {
    "install": "green", "overwrite": "cyan", "skip": "yellow", "reject": "red",
}
_ACTION_MARKS = {"install": "+", "overwrite": "~", "skip": "=", "reject": "!"}


def _print_plan(plan: list[PlanItem], scope: str, describe: str) -> None:
    click.secho(f"install plan — {describe} → scope {scope!r}", bold=True)
    for it in plan:
        mark = _ACTION_MARKS[it.action]
        line = f"  {mark} {it.action:<9} {it.kind}/{it.name}  ({it.rel_path})"
        click.secho(line, fg=_ACTION_COLORS[it.action])
        if it.note:
            click.secho(f"      {it.note}", fg=_ACTION_COLORS[it.action], dim=True)


@click.command("install")
@click.argument("uri")
@click.option(
    "--scope", "scope_opt", default=None,
    help="Target scope (default: derived from the URI — <owner>-<repo> for "
         "github:, the directory name for local:). Created with a minimal "
         "Genome when it does not exist yet.",
)
@click.option(
    "--dry-run", is_flag=True,
    help="Print the install plan (what would be written where, what gets "
         "rejected and why) and stop — nothing is fetched into the source.",
)
@click.option(
    "--force", is_flag=True,
    help="Overwrite documents that already exist locally (default: skip "
         "them with a warning).",
)
@click.option("--json", "as_json", is_flag=True, help="Machine-readable summary.")
def install(uri: str, scope_opt: str | None, dry_run: bool, force: bool, as_json: bool) -> None:
    """Install bundles/Kinds from a repository into the local source.

    URI is `github:owner/repo[/subdir][@ref]` (shallow clone) or
    `local:<path>` (a directory on disk). The fetched tree is scanned with the kernel's
    registered readers (Skill/Soul/AGENTS.md bundles, standalone YAML docs,
    ...); each detected document is validated and then written through
    kernel.write_document, so every write guard runs.

    Third-party manifests are UNTRUSTED DATA: schema validation is the first
    defense (an invalid doc is rejected with the reason; the install
    continues with the valid ones), the kernel's pre-save veto guards are
    the second. Root Kinds (Genome) in the fetched tree are never installed.
    Provenance lands in <scope>/installed.lock (origin pinned to the fetched
    commit). See SECURITY.md for the threat model this implements.

    Examples:

    \b
      dna install github:anthropics/skills/skills/pdf --scope market --dry-run
      dna install github:anthropics/skills/skills/pdf --scope market
      dna install local:../some-checkout/skills --scope playground --force
    """
    fetched = _fetch(uri)
    scope = scope_opt or _derive_scope(uri)

    with dna_session(scope) as s:
        kernel = s.kernel
        readers = list(kernel.active_readers)
        scanned = _scan_tree(fetched.root, readers, writers=list(kernel.active_writers))
        if not scanned:
            raise fail(
                f"no DNA documents detected in {fetched.describe} — nothing the "
                f"registered readers or the standalone-YAML scan recognize. "
                f"Point the URI at a subtree that contains bundles "
                f"(e.g. github:owner/repo/skills)."
            )

        plan = s.run(_build_plan(kernel, scope, scanned, force))
        writes = [p for p in plan if p.action in ("install", "overwrite")]
        rejected = [p for p in plan if p.action == "reject"]
        skipped = [p for p in plan if p.action == "skip"]

        if dry_run:
            if as_json:
                print_json({
                    "uri": uri, "origin": fetched.origin, "scope": scope,
                    "dry_run": True,
                    "plan": [
                        {"action": p.action, "kind": p.kind, "name": p.name,
                         "path": p.rel_path, "note": p.note}
                        for p in plan
                    ],
                })
            else:
                _print_plan(plan, scope, fetched.describe)
                click.secho(
                    f"\ndry-run: {len(writes)} to write · {len(skipped)} to skip "
                    f"· {len(rejected)} rejected — re-run without --dry-run to "
                    f"apply", bold=True,
                )
            return

        # Ensure the target scope exists (a scope is born from its Genome).
        base_dir = str(kernel.source_metadata().get("base_dir") or "")
        installed: list[PlanItem] = []
        write_failures: list[PlanItem] = []

        async def _apply() -> None:
            scope_dir = Path(base_dir) / scope if base_dir else None
            has_genome = scope_dir is not None and (
                (scope_dir / "Genome.yaml").exists()
                or (scope_dir / "manifest.yaml").exists()
            )
            if not has_genome:
                await kernel.write_document(scope, "Genome", scope, {
                    "apiVersion": "github.com/ruinosus/dna/v1",
                    "kind": "Genome",
                    "metadata": {
                        "name": scope,
                        "description": f"Created by `dna install {uri}`",
                    },
                    "spec": {},
                })
            for item in writes:
                try:
                    await kernel.write_document(scope, item.kind, item.name, item.raw)
                    installed.append(item)
                except Exception as e:  # noqa: BLE001 — guard veto/adapter error on ONE doc
                    item.action = "reject"
                    item.note = f"kernel write guard rejected it: {e}"
                    write_failures.append(item)

        s.run(_apply())
        rejected += write_failures

        lock_path: Path | None = None
        if installed and base_dir:
            lock_path = _write_provenance(base_dir, scope, fetched.origin, installed)

    if as_json:
        print_json({
            "uri": uri, "origin": fetched.origin, "scope": scope,
            "installed": [f"{p.kind}/{p.name}" for p in installed],
            "skipped": [f"{p.kind}/{p.name}" for p in skipped],
            "rejected": [
                {"doc": f"{p.kind}/{p.name}", "path": p.rel_path, "reason": p.note}
                for p in rejected
            ],
            "lockfile": str(lock_path) if lock_path else None,
        })
    else:
        _print_plan(plan, scope, fetched.describe)
        click.echo()
        click.secho(
            f"installed {len(installed)} · skipped {len(skipped)} · "
            f"rejected {len(rejected)}",
            fg="green" if installed else "yellow", bold=True,
        )
        if lock_path:
            click.secho(f"provenance → {lock_path}", dim=True)

    if not installed and not skipped:
        # Everything was rejected — nothing usable landed; exit non-zero so
        # scripts notice, with the reasons already printed above.
        raise click.exceptions.Exit(1)
