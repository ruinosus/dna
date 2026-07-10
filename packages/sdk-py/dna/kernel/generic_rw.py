"""GenericBundleReader and GenericBundleWriter — auto-generated from StorageDescriptor.

Custom kinds that follow the standard BUNDLE layout can use these instead of
hand-writing dedicated Reader/Writer classes.
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Any

import yaml

from dna.kernel.protocols import (
    BodyMode,
    ReaderPort,
    StorageDescriptor,
    WriterPort,
)
from dna.kernel.bundle_handle import BundleHandle

# Fields that belong in metadata rather than spec
_META_FIELDS = {"name", "description", "labels"}


class _LiteralBlockSafeDumper(yaml.SafeDumper):
    """SafeDumper that emits multi-line strings as literal block scalar.

    Default `yaml.dump` picks double-quoted style for strings with newlines,
    inserting `\\n` + line-continuation backslashes and re-escaping special
    chars. On long markdown content (chat transcripts, descriptions with
    tables) that produces fragile YAML that round-trips through PyYAML but
    is brittle to writer edits — and we've hit cases where the resulting
    scalar fails to re-parse, dropping the entire frontmatter.

    Block literal `|` style is the canonical YAML escape hatch for prose:
    indentation marks the scalar boundary, no inner escaping needed.
    """


def _literal_str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    """Pick a YAML scalar style robust to brittle round-trip.

    Heuristics (D-C hardening 2026-05-19):
      - multi-line strings → literal block ``|``
      - long strings (>200 chars) → literal block ``|`` (catches chat
        message content, long markdown bodies)
      - strings with embedded quotes (``"`` AND ``'``) → literal
        block ``|`` so PyYAML doesn't pick a quoted style that scans
        forward looking for an unmatched close-quote inside content

    Block literal ``|`` is YAML's safe escape hatch: indentation marks
    the boundary, no inner escaping needed.

    Caveat — block literal cannot be used for strings that:
      - start or end with whitespace (becomes ambiguous after indent)
      - contain only whitespace
    Falling back to default for those edge cases keeps the dumper safe.
    """
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    # Block-literal is ambiguous when the string STARTS with whitespace
    # (indentation marker collides). Trailing whitespace is fine — PyYAML
    # uses chomp indicators. Empty strings and short ones use default.
    if not data or data.lstrip() != data or len(data) < 80:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=None)
    # Block-literal threshold: long strings or quote-heavy strings.
    has_both_quotes = ('"' in data) and ("'" in data)
    if len(data) > 200 or has_both_quotes:
        # Trim trailing whitespace before block-literal — PyYAML will refuse
        # to emit ``|`` for strings that end in spaces (round-trip would
        # be lossy). Strip + restore via the chomp indicator (``|-``).
        # Caller's spec almost never depends on trailing spaces being
        # preserved verbatim; the alternative is a fragile quoted scalar.
        trimmed = data.rstrip()
        return dumper.represent_scalar(
            "tag:yaml.org,2002:str", trimmed + "\n", style="|",
        )
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=None)


_LiteralBlockSafeDumper.add_representer(str, _literal_str_representer)


def safe_yaml_dump(data: Any, **kwargs: Any) -> str:
    """``yaml.dump`` wrapper using ``_LiteralBlockSafeDumper``.

    All flags default to project conventions (block flow, unicode, no key
    sorting); callers can override via ``**kwargs``.
    """
    kwargs.setdefault("default_flow_style", False)
    kwargs.setdefault("allow_unicode", True)
    kwargs.setdefault("sort_keys", False)
    return yaml.dump(data, Dumper=_LiteralBlockSafeDumper, **kwargs)


class FrontmatterParseWarning(UserWarning):
    """Emitted when a bundle marker file has invalid YAML frontmatter.

    The kernel falls back to an empty frontmatter so a single bad file does
    not break manifest loading, but the failure is still surfaced loudly so
    authors can fix it instead of silently losing spec fields.
    """


class FrontmatterParseError(Exception):
    """Raised when YAML frontmatter parsing fails and the caller requested
    strict mode. Callers (e.g. SqlAlchemySource) catch this and fall back to
    the canonical doc content stored alongside the bundle marker so a
    corrupt marker does not silently wipe spec fields.

    The legacy ``_parse_frontmatter`` warning path remains the default —
    only callers that explicitly opt in via ``strict=True`` see this
    exception. This preserves the back-compat contract while letting the
    PG source pick the canonical JSONB row when the marker is broken.
    """

    def __init__(self, message: str, *, source: str | None = None) -> None:
        super().__init__(message)
        self.source = source


def _parse_frontmatter(
    text: str, *, source: str | None = None, strict: bool = False,
) -> tuple[dict[str, Any], str]:
    """Split marker file text into (frontmatter_dict, body_string).

    Returns an empty dict and the full text as body when there is no frontmatter.

    When ``strict=False`` (default — back-compat): invalid YAML emits a
    ``FrontmatterParseWarning`` and returns ``({}, text_body)`` so the rest
    of the load completes. Documents whose marker is broken end up with an
    anemic spec.

    When ``strict=True``: invalid YAML raises ``FrontmatterParseError``
    instead. Used by adapters that hold a canonical-spec fallback
    (e.g. SqlAlchemySource ships the parsed-at-write-time ``content``
    in ``dna_documents``). The adapter catches and uses the fallback,
    avoiding silent spec-wipe on a corrupted marker.
    """
    # D-C root cause (2026-05-19): the previous regex ``^---\n(.*?)---\n?``
    # matched the FIRST ``---`` it encountered inside the body of any
    # quoted-string YAML value (e.g. a chat message content containing
    # ``---`` as a markdown horizontal rule). That truncated the
    # frontmatter mid-scalar and produced a "while scanning a quoted
    # scalar / unexpected end of stream" parse error every time the
    # bundle was read. The new pattern requires the closing ``---`` to
    # be the only content on its own line (newline before AND after) —
    # matches YAML's spec for document separators and ignores in-body
    # horizontal rules.
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        # Final-line edge case: file may end with ``---`` and no trailing
        # newline (writer's behaviour varies). Accept that too.
        match = re.match(r"^---\n(.*?)\n---\s*$", text, re.DOTALL)
    if not match:
        return {}, text

    try:
        parsed = yaml.safe_load(match.group(1))
        fm = parsed if isinstance(parsed, dict) else {}
    except yaml.YAMLError as e:
        where = f" in {source}" if source else ""
        # Surface the YAML error line/column if the scanner provides it.
        mark = getattr(e, "problem_mark", None)
        location = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        msg = (
            f"Invalid YAML frontmatter{where}{location}: {e}. "
            f"Falling back to empty frontmatter — all spec fields from this "
            f"file will be missing. Fix the frontmatter and reload the manifest."
        )
        if strict:
            raise FrontmatterParseError(msg, source=source) from e
        warnings.warn(msg, FrontmatterParseWarning, stacklevel=2)
        fm = {}

    body = text[match.end():]
    return fm, body


def _parse_body(body: str, body_as: BodyMode) -> Any:
    """Parse a body string according to the given BodyMode."""
    if body_as == BodyMode.TEXT:
        return body.strip()

    if body_as == BodyMode.LIST:
        return [
            line.strip().removeprefix("- ")
            for line in body.splitlines()
            if line.strip().startswith("- ")
        ]

    if body_as == BodyMode.SECTIONS:
        sections: dict[str, str] = {}
        current_heading: str | None = None
        current_lines: list[str] = []

        for line in body.splitlines():
            # Only split on ## (not ### or ####)
            heading_match = re.match(r"^## (.+)$", line)
            if heading_match:
                # Flush previous block
                block = "\n".join(current_lines).strip()
                if current_heading is None:
                    if block:
                        sections["_preamble"] = block
                else:
                    sections[current_heading] = block
                current_heading = heading_match.group(1).strip()
                current_lines = []
            else:
                current_lines.append(line)

        # Flush last block
        block = "\n".join(current_lines).strip()
        if current_heading is None:
            if block:
                sections["_preamble"] = block
        else:
            sections[current_heading] = block

        return sections

    return body.strip()  # fallback


def _build_body(value: Any, body_as: BodyMode) -> str:
    """Serialize a spec value back to a body string."""
    if body_as == BodyMode.TEXT:
        return str(value) if value is not None else ""

    if body_as == BodyMode.LIST:
        if not isinstance(value, list):
            return ""
        return "\n".join(f"- {item}" for item in value)

    if body_as == BodyMode.SECTIONS:
        if not isinstance(value, dict):
            return ""
        parts: list[str] = []
        # _preamble goes first, without a heading
        if "_preamble" in value:
            parts.append(value["_preamble"].strip())
        for key, content in value.items():
            if key == "_preamble":
                continue
            parts.append(f"## {key}\n\n{content.strip()}")
        return "\n\n".join(parts)

    return str(value) if value is not None else ""


class GenericBundleReader(ReaderPort):
    """ReaderPort implementation auto-generated from a StorageDescriptor.

    Reads BUNDLE-layout directories by parsing a marker file's YAML frontmatter
    and body according to the descriptor's body_as / body_field / body_parser
    settings.

    ``strict_parse``: when True, propagates ``FrontmatterParseError`` on
    invalid YAML instead of silently returning a spec built only from the
    body. Adapters that hold a canonical-spec fallback (SqlAlchemySource via
    ``dna_documents.content``) opt in so corrupt markers no longer wipe
    spec. Default False keeps the legacy warning-and-degraded-spec path.
    """

    def __init__(
        self, sd: StorageDescriptor, api_version: str, kind: str,
        *, strict_parse: bool = False,
    ) -> None:
        self._sd = sd
        self._api_version = api_version
        self._kind = kind
        self._marker = sd.marker  # exposed for deferred registration detection
        self._strict_parse = strict_parse

    def detect(self, bundle: BundleHandle) -> bool:
        return bundle.exists(self._sd.marker)

    def read(self, bundle: BundleHandle) -> dict[str, Any]:
        marker_text = bundle.read_text(self._sd.marker)
        fm, body = _parse_frontmatter(
            marker_text, source=self._sd.marker, strict=self._strict_parse,
        )

        # Envelope-shape marker ({apiVersion, kind, metadata, spec}) — unwrap to
        # the inner spec/metadata instead of treating the envelope keys as spec
        # fields. The Postgres source's marker re-parse goes through THIS generic
        # reader (not the registered MarkdownBundleReader), and envelope-emitting
        # writers (e.g. HtmlArtifactWriter) produce envelope markers — without
        # this they round-trip as spec={apiVersion, kind, metadata, spec, ...}
        # (the envelope-as-spec bug; intermittent because the granular cache
        # masks it until a TTL miss re-reads from source).
        if isinstance(fm.get("spec"), dict) and ("apiVersion" in fm or "kind" in fm):
            env_meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
            metadata: dict[str, Any] = {"name": bundle.name, **env_meta}
            spec: dict[str, Any] = dict(fm["spec"])
        else:
            # Flat frontmatter — split metadata fields vs spec fields.
            metadata = {"name": bundle.name}
            spec = {}
            for key, val in fm.items():
                if key in _META_FIELDS:
                    metadata[key] = val
                else:
                    spec[key] = val

        # Parse body
        body_field = self._sd.body_field or "content"
        body_as = self._sd.body_as or BodyMode.TEXT

        if self._sd.body_parser is not None:
            # Custom parser overrides body_as
            spec.update(self._sd.body_parser(body))
        else:
            spec[body_field] = _parse_body(body, body_as)

        return {
            "apiVersion": self._api_version,
            "kind": self._kind,
            "metadata": metadata,
            "spec": spec,
        }


class GenericBundleWriter(WriterPort):
    """WriterPort implementation auto-generated from a StorageDescriptor.

    Writes BUNDLE-layout directories by serialising metadata + spec back into
    a marker file with YAML frontmatter and a body section.
    """

    def __init__(self, sd: StorageDescriptor, kind: str) -> None:
        self._sd = sd
        self._kind = kind  # exposed for deferred registration detection

    def can_write(self, raw: dict) -> bool:
        return raw.get("kind") == self._kind

    def write(self, bundle: BundleHandle, raw: dict) -> None:
        metadata = raw.get("metadata", {})
        spec = raw.get("spec", {})

        body_field = self._sd.body_field or "content"
        body_as = self._sd.body_as or BodyMode.TEXT

        # Build frontmatter dict: metadata fields first, then spec fields (excluding body_field)
        fm: dict[str, Any] = {}
        for key in _META_FIELDS:
            val = metadata.get(key)
            if val is not None:
                fm[key] = val
        for key, val in spec.items():
            if key != body_field:
                fm[key] = val

        fm_str = safe_yaml_dump(fm)

        # Build body
        body_value = spec.get(body_field)
        body_str = _build_body(body_value, body_as)

        content = f"---\n{fm_str}---\n\n{body_str}"
        bundle.write_text(self._sd.marker, content)

    def serialize(self, raw: dict) -> list[dict[str, str]]:
        """Return list of {relativePath, content} without writing to disk."""
        metadata = raw.get("metadata", {})
        spec = raw.get("spec", {})

        body_field = self._sd.body_field or "content"
        body_as = self._sd.body_as or BodyMode.TEXT

        # Build frontmatter dict: metadata fields first, then spec fields (excluding body_field)
        fm: dict = {}
        for key in _META_FIELDS:
            val = metadata.get(key)
            if val is not None:
                fm[key] = val
        for key, val in spec.items():
            if key != body_field and val is not None:
                fm[key] = val

        frontmatter = safe_yaml_dump(fm)

        # Build body
        body_value = spec.get(body_field)
        body_str = _build_body(body_value, body_as)

        content = f"---\n{frontmatter}---\n\n{body_str}"
        return [{"relativePath": self._sd.marker, "content": content}]


# ---------------------------------------------------------------------------
# MarkdownBundleReader — shared "envelope-or-flat" reader
# (s-markdown-bundle-reader-helper)
# ---------------------------------------------------------------------------

def _parse_marker_envelope(text: str) -> tuple[dict[str, Any], str]:
    """Frontmatter split used by the envelope-or-flat readers.

    Byte-for-byte the parser the ~10 hand-rolled single-marker readers shared
    (asset/imageprompt/intro/lesson/lottie/mediaitem/pictogram/research/
    teaching/html_artifact). Intentionally distinct from this module's stricter
    ``_parse_frontmatter`` (different regex / body handling) — kept identical so
    promoting those readers to ``MarkdownBundleReader`` does not change a single
    byte of their output. ``read()`` only consumes the frontmatter dict; the body
    is returned for parity but discarded.
    """
    match = re.match(r"^---\n(.*?)---\n?(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    try:
        parsed = yaml.safe_load(match.group(1)) or {}
        if isinstance(parsed, dict):
            return parsed, match.group(2).lstrip("\n")
    except yaml.YAMLError:
        # fail-soft BY CONTRACT: malformed frontmatter means "no envelope" —
        # the whole text is body (flat convention). Narrowed from bare
        # Exception (s-kernel-fail-soft-audit): only YAML syntax errors are
        # expected input variance; genuine bugs now propagate.
        pass
    return {}, text


class MarkdownBundleReader(ReaderPort):
    """Shared ReaderPort for the "envelope-or-flat" single-marker convention.

    Replaces ~10 copy-pasted hand-rolled readers (s-markdown-bundle-reader-helper).
    Reads ``<marker>``; if the frontmatter carries a ``spec`` dict it is treated
    as the standard envelope (apiVersion/kind/metadata/spec), otherwise the whole
    frontmatter is promoted to ``spec`` (flat older docs). Behaviour is
    byte-identical to the readers it replaces.

    Args:
        marker: bundle entry filename (e.g. ``"ASSET.md"``).
        kind: Kind name used as the fallback when frontmatter omits ``kind``.
        api_version: apiVersion fallback when frontmatter omits ``apiVersion``.
        owner_container: optional container the reader is scoped to (preserves
            the kernel's container-aware detection routing for Kinds that set it).
        strict_api_prefix: when given, ``detect()`` additionally parses the
            marker and only matches when ``kind`` equals this Kind OR the doc's
            ``apiVersion`` starts with this prefix (mirrors the stricter detect
            of asset/html_artifact). When None, ``detect()`` is a plain
            ``bundle.exists(marker)`` (the simple-exists readers).
    """

    def __init__(
        self,
        marker: str,
        kind: str,
        api_version: str,
        *,
        owner_container: str | None = None,
        strict_api_prefix: str | None = None,
    ) -> None:
        self._marker = marker
        self._kind = kind
        self._api_version = api_version
        self._strict_api_prefix = strict_api_prefix
        # _owner_container is a formal ReaderPort member; the Protocol
        # base provides the None default, so assign unconditionally.
        self._owner_container = owner_container

    def detect(self, bundle: BundleHandle) -> bool:
        if self._strict_api_prefix is None:
            return bundle.exists(self._marker)
        if not bundle.exists(self._marker):
            return False
        try:
            text = bundle.read_text(self._marker)
        except (OSError, UnicodeDecodeError, ValueError):
            # fail-soft BY CONTRACT: detect() is a probe — an unreadable
            # marker means "not this Kind's bundle". Narrowed from bare
            # Exception (s-kernel-fail-soft-audit): I/O + decode errors are
            # the expected variance; genuine bugs now propagate.
            return False
        fm, _body = _parse_marker_envelope(text)
        if not isinstance(fm, dict):
            return False
        if fm.get("kind") == self._kind:
            return True
        if str(fm.get("apiVersion", "")).startswith(self._strict_api_prefix):
            return True
        return False

    def read(self, bundle: BundleHandle) -> dict[str, Any]:
        text = bundle.read_text(self._marker)
        fm, _body = _parse_marker_envelope(text)
        if isinstance(fm, dict) and "spec" in fm and isinstance(fm["spec"], dict):
            metadata = fm.get("metadata") or {}
            metadata.setdefault("name", bundle.name)
            return {
                "apiVersion": fm.get("apiVersion", self._api_version),
                "kind": fm.get("kind", self._kind),
                "metadata": metadata,
                "spec": fm["spec"],
            }
        return {
            "apiVersion": self._api_version,
            "kind": self._kind,
            "metadata": {"name": bundle.name},
            "spec": fm,
        }
