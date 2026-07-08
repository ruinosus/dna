"""Tests for CollabExtension — Comment Kind."""


class TestCommentKind:
    def test_metadata(self):
        from dna.extensions.collab import CommentKind
        k = CommentKind()
        assert k.api_version == "github.com/ruinosus/dna/collab/v1"
        assert k.kind == "Comment"
        assert k.alias == "collab-comment"
        assert k.origin == "github.com/ruinosus/dna/collab"

    def test_storage_yaml_container(self):
        from dna.extensions.collab import CommentKind
        k = CommentKind()
        assert k.storage.pattern == "yaml"
        assert k.storage.container == "comments"

    def test_dep_filters_empty(self):
        """Comment can reference any Kind — dep_filter is empty by design."""
        from dna.extensions.collab import CommentKind
        k = CommentKind()
        assert k.dep_filters() == {}

    def test_schema_required_fields(self):
        from dna.extensions.collab import CommentKind
        k = CommentKind()
        schema = k.schema()
        assert set(schema["required"]) == {"target_ref", "author", "body", "type", "created_at"}

    def test_schema_type_enum(self):
        from dna.extensions.collab import CommentKind
        k = CommentKind()
        schema = k.schema()
        assert schema["properties"]["type"]["enum"] == ["note", "status_change", "assignment", "system"]

    def test_parse_returns_raw(self):
        from dna.extensions.collab import CommentKind
        k = CommentKind()
        raw = {"target_ref": "Finding:xyz", "author": "alice", "body": "test", "type": "note", "created_at": "2026-04-14T00:00:00Z"}
        assert k.parse(raw) == raw

    def test_summary_extracts_preview(self):
        from dna.extensions.collab import CommentKind
        k = CommentKind()
        doc_mock = type("D", (), {"spec": {
            "target_ref": "Finding:xyz",
            "author": "alice",
            "type": "note",
            "body": "This is a long comment text that should be truncated in the summary view because it's very long indeed"
        }})()
        s = k.summary(doc_mock)
        assert s["target_ref"] == "Finding:xyz"
        assert s["author"] == "alice"
        assert len(s["body_preview"]) <= 80


class TestCollabExtension:
    def test_registers_comment_kind(self):
        from dna.extensions.collab import CollabExtension
        kinds = []
        fake_kernel = type("K", (), {"kind": lambda self, k: kinds.append(k)})()
        CollabExtension().register(fake_kernel)
        assert len(kinds) == 1
        assert kinds[0].kind == "Comment"

    def test_extension_metadata(self):
        from dna.extensions.collab import CollabExtension
        ext = CollabExtension()
        assert ext.name == "collab"
        assert ext.version == "1.0.0"
