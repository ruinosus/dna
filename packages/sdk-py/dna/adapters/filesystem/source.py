"""FilesystemSource — SourcePort backed by local .dna/ directories."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles
import yaml

from dna._yaml import safe_load
from dna.kernel.bundle.handle import FilesystemBundleHandle
from dna.kernel.protocols import SourcePort

if TYPE_CHECKING:
    from dna.kernel.capabilities import SourceCapabilities

logger = logging.getLogger(__name__)


def fs_tenant_segment(tenant: str | None) -> str | None:
    """Map a tenant value to a cross-platform-safe on-disk directory segment.

    The reserved personal-memory partition (ADR-personal-memory) carries a
    ``personal:<oid>`` value whose ``:`` scheme sigil is NOT a portable path
    segment (illegal on Windows, remapped by macOS Finder). The canonical tenant
    value — the PG ``tenant`` column, the ``tenant IN ('', X)`` read predicate,
    the kernel API — is UNCHANGED; only the FS directory name is encoded, by
    percent-escaping the ``:`` to ``%3A``. ``%`` is outside the ordinary
    tenant-slug charset (``[a-zA-Z0-9_\\-.]``), so an encoded personal segment can
    never collide with a real workspace's directory. A no-op for every ordinary
    tenant (they carry no ``:``) and for ``None``."""
    if tenant is None:
        return None
    return tenant.replace(":", "%3A")


class FilesystemSource(SourcePort):
    """Loads manifest instances from .dna/<scope>/ directories.

    Declares the contract explicitly (s-dna-source-conformance-kit): every
    in-repo adapter subclasses its port Protocol so the relationship is
    readable + statically checkable. NOTE: inheriting a Protocol makes
    ``isinstance`` pass *nominally* — behavior is verified by the public
    conformance kit (``dna.testing.source_conformance_suite``).
    """

    # Kernel back-ref installed by the writable subclass's ``attach_kernel``
    # (KernelAttachable). The read-only base never gets one; declared here so
    # ``self._kernel`` is a plain (documented) attribute, not a magic getattr.
    _kernel: object | None = None

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).resolve()

    def _contained(self, path: Path) -> Path:
        """Resolve ``path`` and refuse it unless it stays under ``base_dir``.

        BELT AND BRACES — deliberately redundant with the kernel guard
        (``validate_instance_name`` / ``validate_scope_name`` at
        ``Kernel.write_instance`` / ``fetch_bundle_entry`` / …), and the
        redundancy is the point. **Do not delete either layer as duplicated
        work.** The kernel guard is the PRIMARY seam: it is the door every
        application-layer writer goes through and it can name which input was
        wrong. This one exists because the adapter is reachable WITHOUT the
        kernel — ``dna.kernel.source.sync`` calls ``save_instance`` directly
        today (benignly: its names come from the source being copied, not from
        a request), the public conformance kit drives adapters on purpose, and
        an adapter that builds ``<base>/<scope>/<container>/<name>`` while
        trusting every segment is one refactor away from re-opening the escape
        that ``606812c`` closed.

        It also covers what a per-facade validator cannot reach cheaply:
        ``scope`` lands in a path on EVERY read (``load_all`` backs
        ``instance`` / ``list_instances`` / ``get_instance`` / ``query`` …),
        and ``ref`` / ``layer_value`` / a module ``version`` are path segments
        too. One check at the place the path is actually built covers all of
        them, including the door somebody adds tomorrow.

        Symlinks: ``resolve()`` follows them, so a scope or bundle DIRECTORY
        that is itself a symlink out of the store is refused. Measured before
        adopting this: zero symlinks under any ``.dna/`` tree or package tree in
        either repo. Individual content files reached by a directory SCAN are
        not checked here (the repo's own root ``AGENTS.md`` is symlinked into a
        scope by ``tests/test_agents_md_root.py``, and still works).

        COST, and where it is paid. ``Path.resolve()`` is a realpath: one lstat
        per path component, plus link traversal. This method is called on
        ``load_all``, which backs ``instance`` / ``list_instances`` /
        ``get_instance`` / ``query`` — so the syscalls land on the READ hot
        path, not only on writes, and they scale with the DEPTH of the store
        root rather than with the number of instances (once per facade call,
        not once per instance). It is a fixed handful of stats per call on a
        path prefix the OS has in its dentry cache; the alternative,
        ``os.path.normpath``, is pure string work and would cost nothing — and
        is rejected anyway, deliberately, because it is TEXTUAL: it cannot see
        a scope directory that is a symlink out of the store, and a containment
        check a symlink defeats is not a containment check. If this ever shows
        up in a profile, cache the resolved ``base_dir`` (it is fixed for the
        adapter's life) before weakening the check. The same trade-off, with
        the same reasoning, is made in
        ``dna.kernel.bundle.handle.FilesystemBundleHandle._entry_path``.
        """
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.base_dir)
        except ValueError as exc:
            from dna.kernel.errors import PathEscapesStoreRoot

            raise PathEscapesStoreRoot(
                f"{type(self).__name__} refused a path that leaves its store "
                f"root: {str(resolved)!r} is not under {str(self.base_dir)!r}. "
                f"Every segment this adapter joins — scope, container, instance "
                f"name, layer value, bundle entry, module version — is a PATH "
                f"COMPONENT, so one that traverses ('..', '/', an absolute "
                f"path) moves the anchor and puts the read or write outside the "
                f"store. Fix the caller's segment; do not widen this check."
            ) from exc
        return resolved

    def capabilities(self) -> "SourceCapabilities":
        """Explicit contract declaration (s-sourceport-contract-cleanup).

        Read-only FS source: granular reads + in-memory query/count, no
        write surface. Kept honest by the adapter conformance test, which
        asserts declaration == reflection-derived oracle.
        """
        from dna.kernel.capabilities import SourceCapabilities
        return SourceCapabilities(
            source="filesystem",
            drafts=False,
            versions=False,
            layers=True,
            bundle_read=True,
            bundle_write=True,
            kernel_attachable=False,
            granular_list=True,
            granular_one=True,
            query_pushdown=True,
            tenant_layer_writes=False,
            write_kwargs=frozenset(),
            delete_kwargs=frozenset(),
        )

    @property
    def supports_readers(self) -> bool:
        return True

    async def load_bootstrap_docs(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return Genome + KindDefinition + LayerPolicy docs.

        Phase 16 — replaces ``load_manifest``. Filesystem implementation:
        walks ``load_all`` (which is the adapter's only scan path) and
        filters by Kind name. Postgres + SQLite override with a
        ``WHERE kind IN (...)`` fast path.

        Tenant semantics: when ``tenant`` is set, the tenant-published
        ``Genome`` shadows the platform Genome (Phase 9 multi-tenant
        publishing). ``KindDefinition`` and ``LayerPolicy`` are
        structurally non-overlayable per Phase 16 — always read from
        the platform base. Tenant overlay sequence for Genome:

          1. ``<base>/tenants/<tenant>/scopes/<scope>/Genome.yaml``
          2. ``<base>/tenants/<tenant>/scopes/<scope>/manifest.yaml`` (legacy)
          3. ``<base>/<scope>/Genome.yaml``
          4. ``<base>/<scope>/manifest.yaml`` (legacy)
        """
        from dna.kernel.protocols import BOOTSTRAP_KIND_NAMES
        try:
            all_raws = await self.load_all(scope, readers=None)
        except FileNotFoundError:
            # Platform scope dir absent — tenant-only scopes still need
            # to resolve via the tenant overlay below.
            all_raws = []
        out = [d for d in all_raws if d.get("kind") in BOOTSTRAP_KIND_NAMES]

        if tenant:
            # Pull tenant-published Genome from
            # ``tenants/<t>/scopes/<s>/Genome.yaml`` and shadow the
            # platform Genome in the result.
            tenant_pkg = self._contained(
                self.base_dir / "tenants" / fs_tenant_segment(tenant)
                / "scopes" / scope / "Genome.yaml"
            )
            if tenant_pkg.exists():
                async with aiofiles.open(tenant_pkg, encoding="utf-8") as f:
                    tenant_doc = safe_load(await f.read())
                if isinstance(tenant_doc, dict) and tenant_doc.get("kind") == "Genome":
                    out = [d for d in out if d.get("kind") != "Genome"]
                    out.append(tenant_doc)
        return out

    async def load_all(
        self, scope: str, readers: list | None = None,
    ) -> list[dict[str, Any]]:
        scope_dir = self._contained(self.base_dir / scope)
        if not scope_dir.exists():
            raise FileNotFoundError(f"Scope not found: {scope_dir}")
        return await self._load_dir(scope_dir, readers or [], skip={"layers", "tenants"})

    async def list_doc_refs(
        self, scope: str, *, kind: str | None = None,
        tenant: str | None = None,
    ) -> list[tuple[str, str]]:
        """L1 granular access — FS impl projects from load_all.

        Não há ganho de perf vs load_all em FS (a leitura é cheap
        in-process disk), mas mantém o contract do Protocol consistente
        entre adapters. PG é onde o ganho real mora.

        Tenant: passado para load_layer quando set, união base+overlay.
        """
        if tenant:
            base = await self.load_all(scope, readers=self._effective_readers())
            overlay = await self.load_layer(
                scope, "tenant", tenant, readers=self._effective_readers(),
            )
            overlay_keys = {
                (d.get("kind", ""), d.get("metadata", {}).get("name") or d.get("name", ""))
                for d in overlay
            }
            base_filtered = [
                d for d in base
                if (
                    (d.get("kind", ""), d.get("metadata", {}).get("name") or d.get("name", ""))
                    not in overlay_keys
                )
            ]
            docs = overlay + base_filtered
        else:
            docs = await self.load_all(scope, readers=self._effective_readers())

        refs: list[tuple[str, str]] = []
        for d in docs:
            k = d.get("kind", "")
            n = d.get("metadata", {}).get("name") or d.get("name", "")
            if not k or not n:
                continue
            if kind and k != kind:
                continue
            refs.append((k, n))
        refs.sort()
        return refs

    async def load_one(
        self, scope: str, kind: str, name: str, *,
        readers: list | None = None,
        tenant: str | None = None,
    ) -> dict[str, Any] | None:
        """L1 granular access — FS impl projects from load_all.

        Mesma observação que list_doc_refs: FS não ganha perf, mas
        respeita o contract. Tenant overlay shadows base.
        """
        effective_readers = readers or self._effective_readers()
        # Tenant overlay path
        if tenant:
            overlay_docs = await self.load_layer(
                scope, "tenant", tenant, readers=effective_readers,
            )
            for d in overlay_docs:
                if d.get("kind") == kind and (
                    d.get("metadata", {}).get("name") == name
                    or d.get("name") == name
                ):
                    return d
        # Base layer
        base_docs = await self.load_all(scope, readers=effective_readers)
        for d in base_docs:
            if d.get("kind") == kind and (
                d.get("metadata", {}).get("name") == name
                or d.get("name") == name
            ):
                return d
        return None

    async def query(
        self, scope: str, kind: str, *,
        filter=None, projection=None, limit=None, offset=None,
        order_by=None, tenant=None,
    ):
        """Marco A — query layer. FS adapter rides the shared in-memory
        core (``query_fallback.query_via_load_all``: load_all + Python
        filter). Acceptable because FS source is dev-mode only with
        small scopes. Native push-down is the purview of the SQL
        adapters (s-postgres-source-query-impl,
        s-sqlite-source-query-impl).

        Story s-filesystem-source-query-impl may optimize this later if
        FS scopes grow (e.g., index by kind via directory layout). For
        now: correct semantics via shared helpers.
        """
        from dna.kernel.query.fallback import query_via_load_all
        async for row in query_via_load_all(
            self, scope, kind,
            filter=filter, projection=projection, limit=limit,
            offset=offset, order_by=order_by, tenant=tenant,
            readers=self._query_readers(),
        ):
            yield row

    async def count(
        self, scope: str, kind: str, *,
        filter=None, group_by=None, tenant=None,
    ) -> dict[str, Any]:
        """F2 — rides ``self.query`` via the shared aggregation helper
        (``query_fallback.count_via_query``). FS é dev-mode com scopes
        pequenos; push-down é dos adapters SQL."""
        from dna.kernel.query.fallback import count_via_query
        return await count_via_query(
            self, scope, kind, filter=filter, group_by=group_by, tenant=tenant,
        )

    def _effective_readers(self) -> list:
        """Internal helper — returns the instance readers list (may be empty)."""
        return list(getattr(self, "_readers", []) or [])

    def _query_readers(self) -> list:
        """Readers for the query path. Prefer the attached kernel's LIVE
        readers over the source's snapshot (the snapshot is captured at
        ``attach_kernel`` time, BEFORE extensions register their generic
        bundle readers via lazy init) — without this preference, query()
        misses every bundle-format kind (Agent, Skill, Soul, …).
        Detached sources use their own readers list."""
        if self._kernel is not None:
            return list(getattr(self._kernel, "_readers", []) or [])
        return self._effective_readers()

    async def resolve_ref(self, scope: str, ref: str) -> str:
        # ``ref`` is a RELATIVE PATH by contract (``prompts/x.md``), so it
        # cannot be validated as a single component — only containment bounds
        # it. Same rule the bundle-entry guard applies to ``entry``.
        path = self._contained(self.base_dir / scope / ref)
        if not path.exists():
            return ""
        async with aiofiles.open(path, encoding="utf-8") as f:
            return await f.read()

    async def load_layer(
        self, scope: str, layer_id: str, layer_value: str,
        readers: list | None = None,
    ) -> list[dict[str, Any]]:
        # Phase 2b: tenant layers live at tenants/<X>/scopes/<S>/, other
        # layers (branch, region, user) keep the legacy <scope>/layers/
        # path. Tenant reads check the new path first, falling back to
        # the legacy layers/tenant/<X>/ for pre-migration data.
        # ``_validate_layer_segments`` guards the WRITE path only; this READ
        # door never went through it, so containment is what bounds it here.
        if layer_id == "tenant":
            new_dir = self._contained(
                self.base_dir / "tenants" / fs_tenant_segment(layer_value)
                / "scopes" / scope
            )
            if new_dir.exists():
                return await self._load_dir(
                    new_dir, readers=readers or [], skip=set()
                )
            legacy_dir = self._contained(
                self.base_dir / scope / "layers" / "tenant" / layer_value
            )
            if legacy_dir.exists():
                return await self._load_dir(
                    legacy_dir, readers=readers or [], skip=set()
                )
            return []
        # Non-tenant layers keep the legacy <scope>/layers/<id>/<val> path
        layer_dir = self._contained(
            self.base_dir / scope / "layers" / layer_id / layer_value
        )
        if not layer_dir.exists():
            return []
        return await self._load_dir(layer_dir, readers=readers or [], skip=set())

    async def _load_dir(
        self, directory: Path, readers: list, skip: set[str],
    ) -> list[dict[str, Any]]:
        """Load YAMLs + reader-detected bundles from a directory.

        Readers take priority: if a reader detects a bundle directory,
        any YAML file with the same stem is skipped to avoid duplicates.
        """
        instances: list[dict[str, Any]] = []
        reader_matched: set[str] = set()  # stems matched by readers

        # 1. Invoke readers first (bundles take priority)
        if readers:
            # Readers on the scope root directory itself
            bundle = FilesystemBundleHandle(directory)
            for reader in readers:
                try:
                    if reader.detect(bundle):
                        doc = reader.read(bundle)
                        if isinstance(doc, dict) and "kind" in doc:
                            instances.append(doc)
                            reader_matched.add(directory.name)
                except Exception as e:
                    logger.warning("Reader error on %s: %s", directory, e)

            # Readers on subdirectories
            await self._read_recursive(directory, readers, instances, skip, reader_matched)

        # 2. Load YAML files. Dedup against reader-loaded bundles is done in
        # step 3 by (kind, name) — stem-only dedup would drop docs of a
        # different kind that happen to share a name (e.g. Soul/brad and
        # Agent/brad in the same layer).
        for yaml_file in sorted(directory.rglob("*.yaml")):
            if any(part in skip for part in yaml_file.relative_to(directory).parts):
                continue
            try:
                async with aiofiles.open(yaml_file, encoding="utf-8") as f:
                    content = safe_load(await f.read())
                if isinstance(content, dict) and "kind" in content:
                    instances.append(content)
            except yaml.YAMLError as e:
                logger.warning("Error parsing %s: %s", yaml_file, e)

        # 3. Deduplicate by kind/name — readers (first) take priority over YAML (later)
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for doc in instances:
            name = doc.get("metadata", {}).get("name") or doc.get("name", "")
            key = f"{doc.get('kind', '')}/{name}"
            if key not in seen:
                seen.add(key)
                deduped.append(doc)
        return deduped

    async def _read_recursive(
        self, directory: Path, readers: list,
        instances: list[dict[str, Any]], skip: set[str],
        reader_matched: set[str],
    ) -> None:
        # H3 — container-aware reader routing.
        #
        # The scanner walks subdirs of ``directory``. Each subdir IS a
        # bundle (or a non-bundle subdir). The PARENT directory's name
        # equals the bundle's *container* (e.g. ``graphify-artifacts/
        # my-graph/`` → container = ``graphify-artifacts``).
        #
        # Pre-H3, we tried every registered reader in order and stopped
        # at first match. That broke when two readers detected the same
        # marker file (e.g. two extensions both using MANIFEST.md):
        # the alphabetically-first extension's reader silently captured
        # the other's bundles.
        #
        # H3 fix: prefer readers whose ``_owner_container`` member matches
        # the parent directory name. Unscoped readers (the None default —
        # ``_owner_container`` is a formal ReaderPort member since
        # s-dna-rw-roundtrip-suite, no longer duck-typed) are tried only
        # as fallback.
        container = directory.name
        owned_readers = [
            r for r in readers if r._owner_container == container
        ]
        global_readers = [
            r for r in readers if r._owner_container is None
        ]
        # Order: container-owned first, then unscoped fallback. Readers
        # owned by a DIFFERENT container are skipped — they cannot
        # legitimately match here.
        ordered_readers = owned_readers + global_readers
        for subdir in sorted(directory.iterdir()):
            if not subdir.is_dir() or subdir.name in skip:
                continue
            # Phase 12g — underscore-prefixed dirs are reserved for archive
            # / migration sinks (_archived, _legacy). Excluded universally
            # so a Doc moved into _archived/ stops appearing in listings
            # without needing per-doc enabled=false flips.
            if subdir.name.startswith("_"):
                continue
            matched = False
            bundle = FilesystemBundleHandle(subdir)
            for reader in ordered_readers:
                try:
                    if reader.detect(bundle):
                        doc = reader.read(bundle)
                        if isinstance(doc, dict) and "kind" in doc:
                            instances.append(doc)
                        reader_matched.add(subdir.name)
                        matched = True
                        break
                except Exception as e:
                    logger.warning("Reader error on %s: %s", subdir, e)
            if not matched:
                await self._read_recursive(subdir, readers, instances, skip, reader_matched)

    async def close(self) -> None:
        pass

    def _bundle_root(
        self,
        scope: str,
        container: str,
        name: str,
        *,
        tenant: str | None = None,
    ) -> Path:
        """Resolve the ``<container>/<name>`` bundle root directory — the
        tenant overlay layout when ``tenant`` is truthy, else the shared
        base layer.

        Single source of truth for bundle-root path construction, used by
        ``fetch_bundle_entry``, ``write_bundle_entry``, ``delete_bundle_entry``
        and ``list_bundle_entries`` alike, so the path-traversal guard
        (``resolved.relative_to(bundle_root)``) is anchored on the SAME
        directory everywhere and can never drift out of sync between the
        four bundle-entry primitives (it previously did: write/delete only
        guarded against escaping ``base_dir`` as a whole, which let a
        crafted ``entry`` like ``"../../../../<other>/SKILL.md"`` escape a
        tenant's own bundle and clobber a DIFFERENT bundle's — including the
        shared base bundle other tenants inherit from).

        Containment (``_contained``) is applied to the result, so a traversing
        ``scope``/``container``/``name`` can no longer MOVE the anchor the
        entry check is measured against — which is exactly how the read door
        escaped: the entry guard passed because the root it was anchored on had
        already been relocated outside the store.

        ``entry`` VS ``name`` — WRITE THIS DOWN, because forgetting it is what
        left the class open. Both are caller-influenced text that becomes a
        location on disk; they are held to DIFFERENT rules because they are
        different SHAPES:

          ``scope`` / ``container`` / ``name``
              ONE path component each. No ``/`` at all, never ``.`` or ``..``.
              ``validate_scope_name`` / ``validate_instance_name``.
          ``entry``
              A RELATIVE PATH, anchored at the root this method returns. ``/``
              is legitimate and normal — 482 of the 492 real bundle entries
              measured across both repos carry one, the deepest is 8 segments,
              every single one contains a dot. ``validate_bundle_entry``.

        Same concept, two doors, two rules — and for two commits only one door
        was guarded. The consequence was not theoretical: a bundle entry path
        is ALSO derived from instance CONTENT by the registered writers
        (``spec.source_files``, ``spec.root_files``,
        ``spec.scripts|references|assets``, ``spec.extras``,
        ``spec.instruction_file``), and every one of those wrote a file outside
        the store root through ``Kernel.write_instance`` itself, on the base
        lane and the tenant lane alike. If you add a third shape here, decide
        which of the two rules it is BEFORE you join it onto anything.
        """
        if tenant:
            return self._contained(
                self.base_dir / "tenants" / fs_tenant_segment(tenant) / "scopes" / scope
                / container / name
            )
        return self._contained(self.base_dir / scope / container / name)

    def _bundle_entry_target(
        self, bundle_root: Path, entry: str, *, resolve_leaf: bool,
    ) -> Path:
        """Join ``entry`` onto ``bundle_root`` under the ONE bundle-entry rule.

        WHY THIS EXISTS: ``entry`` had TWO DOORS WITH TWO RULES. The kernel
        door (``FilesystemBundleHandle._entry_path``) validates the shape with
        ``validate_bundle_entry`` and refuses with ``InvalidBundleEntry`` /
        ``PathEscapesStoreRoot``; these three adapter primitives —
        ``write_bundle_entry`` / ``fetch_bundle_entry`` /
        ``delete_bundle_entry`` — built ``bundle_root / entry`` directly with
        an ad-hoc ``resolve() + relative_to`` and never called the validator at
        all. Measured on the SAME bundle and the SAME entry:

            symlinked LEAF   adapter: FileNotFoundError | handle: ACCEPTED
            absolute entry   adapter: FileNotFoundError | handle: InvalidBundleEntry
            traversing entry adapter: FileNotFoundError | handle: InvalidBundleEntry
            empty entry      adapter: IsADirectoryError | handle: InvalidBundleEntry

        Security-wise the adapter door WAS closed — nothing escaped. The bug is
        the VOCABULARY. ``FileNotFoundError`` is not a ``KernelRefusal``, so a
        face relays a security refusal as **404, not a denial** — precisely the
        masking ``KernelRefusal`` and ``tests/test_kernel_refusal_base.py``
        exist to prevent. An operator reading a 404 concludes "typo in the
        path"; the truth is "this input was refused". (The empty-entry case was
        worse than cosmetic: it wrote a stray ``<name>.tmp`` beside the bundle
        root before failing on the rename.)

        THE ASYMMETRY IS DELIBERATE and is the same one the handle draws — see
        ``FilesystemBundleHandle._entry_path``. On a WRITE or DELETE the LEAF is
        resolved, because a symlinked leaf is an escape primitive: following it
        puts the bytes (or the ``unlink``) outside the bundle, and a synced or
        cloned bundle can carry a link it did not author. On a READ only the
        PARENT CHAIN is resolved, because a symlinked FILE is content — this
        repo symlinks its own root ``AGENTS.md`` into a scope on purpose
        (``tests/test_agents_md_root.py``) and it is read through the handle.
        Aligning the read door here is what makes the two doors agree: the same
        entry previously scanned fine through the handle and 404'd through this
        primitive. A symlinked DIRECTORY is refused in both directions.

        TWO LAYERS, kept separate on purpose (do not collapse them): the shape
        rule names WHICH input was wrong and is identical on every backend; the
        containment check catches what no textual rule can see — a directory on
        the path that is a link or a mount out of the bundle.
        """
        from dna.kernel.errors import PathEscapesStoreRoot, validate_bundle_entry

        validate_bundle_entry(entry)
        target = bundle_root / entry
        checked = target.resolve() if resolve_leaf else target.parent.resolve()
        if checked != bundle_root and bundle_root not in checked.parents:
            raise PathEscapesStoreRoot(
                f"bundle entry {entry!r} resolves to {str(checked)!r}, which is "
                f"outside the bundle root {str(bundle_root)!r}. The entry passed "
                f"the shape rule, so something on its path is a link or a mount "
                f"pointing out of the bundle. The bundle is the boundary — not "
                f"the store root: an entry that stayed inside the store but left "
                f"THIS bundle would reach a different tenant's bundle, or the "
                f"shared base bundle every tenant inherits from."
            )
        return target

    def write_bundle_entry(
        self,
        scope: str,
        container: str,
        name: str,
        entry: str,
        content: bytes | str,
        *,
        tenant: str | None = None,
        kind: str | None = None,
    ) -> None:
        """BundleEntryWritable impl — write a text OR binary entry to the bundle dir.

        Mirror of ``fetch_bundle_entry`` resolution order:
          1. Tenant-scoped layout when ``tenant`` is provided.
          2. Base layer otherwise.

        Creates parent directories on demand and writes atomically
        (write-to-temp + rename) so a crash mid-write never produces
        a torn file.

        ``kind`` is accepted for protocol parity but ignored — the
        filesystem layout namespaces bundles by ``container``.

        Refuses with ``InvalidBundleEntry`` / ``PathEscapesStoreRoot`` (both
        ``KernelRefusal``) — NOT ``FileNotFoundError``, which a face would
        relay as a 404 instead of a denial. See ``_bundle_entry_target``.
        """
        del kind
        bundle_root = self._bundle_root(scope, container, name, tenant=tenant)
        # MUTATING — the leaf is resolved too, so a symlinked entry cannot put
        # the bytes outside the bundle.
        target = self._bundle_entry_target(bundle_root, entry, resolve_leaf=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: tmp file + rename. Same dir to avoid cross-FS
        # rename issues.
        import os
        tmp = target.with_suffix(target.suffix + ".tmp")
        # i-083 — accept str (text entries: instruction fragments, asset.json,
        # scripts) as well as bytes (binary: images, fonts). Text is written
        # UTF-8 so the round-trip matches the DB adapters' `content` column.
        if isinstance(content, str):
            tmp.write_text(content, encoding="utf-8")
        else:
            tmp.write_bytes(content)
        os.replace(tmp, target)

    def fetch_bundle_entry(
        self,
        scope: str,
        container: str,
        name: str,
        entry: str,
        *,
        tenant: str | None = None,
        kind: str | None = None,
    ) -> bytes:
        """Phase 14w — read a binary bundle entry through the source.

        Resolution order honors the tenant overlay convention:
          1. ``<base>/tenants/<tenant>/scopes/<scope>/<container>/<name>/<entry>``
             when ``tenant`` is set.
          2. ``<base>/<scope>/<container>/<name>/<entry>`` (base layer).

        Path-traversal is prevented by ensuring the resolved entry path
        stays under the resolved bundle dir.

        Raises ``FileNotFoundError`` when the bundle or entry is absent.

        ``kind`` is accepted for protocol parity with SQL adapters but
        ignored — the filesystem layout already namespaces bundles by
        ``container`` (each Kind's container is a distinct
        sub-directory), so collision is impossible at this layer.
        """
        del kind  # not needed on filesystem; container path disambiguates
        roots: list[Path] = []
        if tenant:
            roots.append(self._bundle_root(scope, container, name, tenant=tenant))
        roots.append(self._bundle_root(scope, container, name, tenant=None))
        for bundle_root in roots:
            # READ — the parent chain only, so a symlinked FILE stays readable
            # (the root-AGENTS.md pattern). A refusal PROPAGATES rather than
            # falling through to the next root: the shape is root-independent,
            # and a containment failure means a link out of the bundle, which
            # is a denial, not a miss.
            cand = self._bundle_entry_target(bundle_root, entry, resolve_leaf=False)
            if cand.is_file():
                return cand.read_bytes()
        raise FileNotFoundError(
            f"Bundle entry not found: scope={scope!r} container={container!r} "
            f"name={name!r} entry={entry!r} tenant={tenant!r}"
        )

    def list_bundle_entries(
        self,
        scope: str,
        container: str,
        name: str,
        *,
        tenant: str | None = None,
        only_tenant: bool = False,
        kind: str | None = None,
    ) -> list[str]:
        """s-strain-bundle-fork B1 — list entry paths for a bundle.

        Composed (default): union of the tenant overlay dir + the base
        bundle dir, relative entry paths, deduped + sorted. ``only_tenant``
        restricts to just the tenant overlay dir (or the base dir when no
        tenant, mirroring the SQL adapters' ``tenant or ""`` sentinel).

        ``kind`` is accepted for protocol parity but ignored — the
        filesystem layout already namespaces bundles by ``container``.
        """
        del kind
        base_dir = self._bundle_root(scope, container, name, tenant=None)
        tenant_dir = (
            self._bundle_root(scope, container, name, tenant=tenant)
            if tenant else None
        )
        if only_tenant:
            dirs = [tenant_dir if tenant_dir is not None else base_dir]
        else:
            dirs = ([tenant_dir] if tenant_dir is not None else []) + [base_dir]
        entries: set[str] = set()
        for d in dirs:
            if not d.is_dir():
                continue
            for p in d.rglob("*"):
                if p.is_file():
                    entries.add(p.relative_to(d).as_posix())
        return sorted(entries)

    def delete_bundle_entry(
        self,
        scope: str,
        container: str,
        name: str,
        entry: str,
        *,
        tenant: str | None = None,
        kind: str | None = None,
    ) -> bool:
        """s-strain-bundle-fork B1 — delete ONE entry file for ``tenant``
        (the base bundle dir when ``tenant`` is None). Returns True if the
        file existed. Reverting a tenant fork deletes the tenant-scoped
        copy so ``fetch_bundle_entry`` falls back to the base layer again.

        ``kind`` is accepted for protocol parity but ignored (see
        ``fetch_bundle_entry``).
        """
        del kind
        bundle_root = self._bundle_root(scope, container, name, tenant=tenant)
        # MUTATING — the leaf is resolved too. A symlinked entry would
        # otherwise ``unlink`` a file outside the bundle, which is the delete
        # twin of the symlinked-leaf write escape.
        target = self._bundle_entry_target(bundle_root, entry, resolve_leaf=True)
        if not target.is_file():
            return False
        target.unlink()
        return True
