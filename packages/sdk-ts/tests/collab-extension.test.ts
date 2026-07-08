import { describe, test, expect } from "bun:test";
import { CollabExtension } from "../src/extensions/collab.js";
import { Kernel } from "../src/kernel/index.js";
import { SD } from "../src/kernel/protocols.js";

const API_VERSION = "github.com/ruinosus/dna/collab/v1";
const KIND_KEY = `${API_VERSION}\0Comment`;

// ---------------------------------------------------------------------------
// Extension registration
// ---------------------------------------------------------------------------

describe("CollabExtension", () => {
  test("registers exactly 1 kind", async () => {
    const k = new Kernel();
    const before = k._kinds.size;
    k.load(new CollabExtension());
    expect(k._kinds.size - before).toBe(1);
  });

  test("extension metadata", async () => {
    const ext = new CollabExtension();
    expect(ext.name).toBe("collab");
    expect(ext.version).toBe("1.0.0");
  });
});

// ---------------------------------------------------------------------------
// CommentKind metadata
// ---------------------------------------------------------------------------

describe("CommentKind metadata", () => {
  function getKind() {
    const k = new Kernel();
    k.load(new CollabExtension());
    const kp = k._kinds.get(KIND_KEY);
    if (!kp) throw new Error("CommentKind not found");
    return kp;
  }

  test("apiVersion", async () => {
    expect(getKind().apiVersion).toBe(API_VERSION);
  });

  test("kind", async () => {
    expect(getKind().kind).toBe("Comment");
  });

  test("alias", async () => {
    expect(getKind().alias).toBe("collab-comment");
  });

  test("origin", async () => {
    expect(getKind().origin).toBe("github.com/ruinosus/dna/collab");
  });

  test("isRoot is false", async () => {
    expect(getKind().isRoot).toBe(false);
  });

  test("isPromptTarget is false", async () => {
    expect(getKind().isPromptTarget).toBe(false);
  });

  test("flattenInContext is false", async () => {
    expect(getKind().flattenInContext).toBe(false);
  });

  test("promptTargetPriority is 0", async () => {
    expect(getKind().promptTargetPriority).toBe(0);
  });

  test("graphStyle matches spec", async () => {
    const kp = getKind();
    expect(kp.graphStyle).toEqual({
      fill: "#F59E0B",
      stroke: "#D97706",
      textColor: "#fff",
    });
  });

  test("asciiIcon", async () => {
    expect(getKind().asciiIcon).toBe("💬");
  });

  test("displayLabel", async () => {
    expect(getKind().displayLabel).toBe("Comments");
  });
});

// ---------------------------------------------------------------------------
// Storage descriptor
// ---------------------------------------------------------------------------

describe("CommentKind storage", () => {
  test("uses SD.yaml('comments')", async () => {
    const k = new Kernel();
    k.load(new CollabExtension());
    const kp = k._kinds.get(KIND_KEY)!;
    const expected = SD.yaml("comments");
    expect(kp.storage).toEqual(expected);
  });

  test("storage pattern is yaml", async () => {
    const k = new Kernel();
    k.load(new CollabExtension());
    const kp = k._kinds.get(KIND_KEY)!;
    expect(kp.storage.pattern).toBe("yaml");
  });

  test("storage container is 'comments'", async () => {
    const k = new Kernel();
    k.load(new CollabExtension());
    const kp = k._kinds.get(KIND_KEY)!;
    expect(kp.storage.container).toBe("comments");
  });
});

// ---------------------------------------------------------------------------
// depFilters
// ---------------------------------------------------------------------------

describe("CommentKind depFilters", () => {
  test("returns empty object — Comment can reference any Kind", async () => {
    const k = new Kernel();
    k.load(new CollabExtension());
    const kp = k._kinds.get(KIND_KEY)!;
    expect(kp.depFilters()).toEqual({});
  });
});

// ---------------------------------------------------------------------------
// Schema validation
// ---------------------------------------------------------------------------

describe("CommentKind schema", () => {
  function getSchema() {
    const k = new Kernel();
    k.load(new CollabExtension());
    return k._kinds.get(KIND_KEY)!.schema() as Record<string, unknown>;
  }

  test("required fields", async () => {
    const schema = getSchema();
    expect(schema.required).toEqual([
      "target_ref",
      "author",
      "body",
      "type",
      "created_at",
    ]);
  });

  test("type is an enum", async () => {
    const schema = getSchema();
    const props = schema.properties as Record<string, Record<string, unknown>>;
    expect(props.type.type).toBe("string");
    expect(props.type.enum).toEqual([
      "note",
      "status_change",
      "assignment",
      "system",
    ]);
  });

  test("target_ref is a string", async () => {
    const schema = getSchema();
    const props = schema.properties as Record<string, Record<string, unknown>>;
    expect(props.target_ref.type).toBe("string");
  });

  test("author is a string", async () => {
    const schema = getSchema();
    const props = schema.properties as Record<string, Record<string, unknown>>;
    expect(props.author.type).toBe("string");
  });

  test("body is a string", async () => {
    const schema = getSchema();
    const props = schema.properties as Record<string, Record<string, unknown>>;
    expect(props.body.type).toBe("string");
  });

  test("created_at is date-time", async () => {
    const schema = getSchema();
    const props = schema.properties as Record<string, Record<string, unknown>>;
    expect(props.created_at.type).toBe("string");
    expect(props.created_at.format).toBe("date-time");
  });

  test("from_status and to_status are present", async () => {
    const schema = getSchema();
    const props = schema.properties as Record<string, Record<string, unknown>>;
    expect(props.from_status.type).toBe("string");
    expect(props.to_status.type).toBe("string");
  });

  test("assignee is present", async () => {
    const schema = getSchema();
    const props = schema.properties as Record<string, Record<string, unknown>>;
    expect(props.assignee.type).toBe("string");
  });

  test("attachments is an array of strings", async () => {
    const schema = getSchema();
    const props = schema.properties as Record<string, Record<string, unknown>>;
    expect(props.attachments.type).toBe("array");
    expect((props.attachments.items as Record<string, unknown>).type).toBe(
      "string",
    );
  });

  test("additionalProperties is true", async () => {
    const schema = getSchema();
    expect(schema.additionalProperties).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// parse returns raw
// ---------------------------------------------------------------------------

describe("CommentKind parse", () => {
  test("returns the raw object unchanged", async () => {
    const k = new Kernel();
    k.load(new CollabExtension());
    const kp = k._kinds.get(KIND_KEY)!;

    const raw = {
      apiVersion: API_VERSION,
      kind: "Comment",
      metadata: { name: "comment-1" },
      spec: {
        target_ref: "Finding:xyz",
        author: "alice",
        body: "looks good",
        type: "note",
        created_at: "2026-04-14T00:00:00Z",
      },
    };

    expect(kp.parse(raw)).toBe(raw);
  });
});

// ---------------------------------------------------------------------------
// summary extraction
// ---------------------------------------------------------------------------

describe("CommentKind summary", () => {
  function getKind() {
    const k = new Kernel();
    k.load(new CollabExtension());
    return k._kinds.get(KIND_KEY)!;
  }

  test("extracts target_ref, author, type, and body preview", async () => {
    const kp = getKind();
    const doc = {
      spec: {
        target_ref: "Finding:xyz",
        author: "alice",
        type: "note",
        body: "short body",
      },
    } as never;
    const sum = kp.summary(doc) as Record<string, unknown>;
    expect(sum.target_ref).toBe("Finding:xyz");
    expect(sum.author).toBe("alice");
    expect(sum.type).toBe("note");
    expect(sum.body_preview).toBe("short body");
  });

  test("truncates long body to 80 chars", async () => {
    const kp = getKind();
    const longBody =
      "This is a long comment text that should be truncated in the summary view because it is very long indeed";
    const doc = {
      spec: {
        target_ref: "Finding:xyz",
        author: "alice",
        type: "note",
        body: longBody,
      },
    } as never;
    const sum = kp.summary(doc) as Record<string, unknown>;
    expect((sum.body_preview as string).length).toBeLessThanOrEqual(80);
  });

  test("applies defaults when spec fields are absent", async () => {
    const kp = getKind();
    const doc = { spec: {} } as never;
    const sum = kp.summary(doc) as Record<string, unknown>;
    expect(sum.target_ref).toBe("");
    expect(sum.author).toBe("");
    expect(sum.type).toBe("note");
    expect(sum.body_preview).toBe("");
  });

  test("null-returning methods return null", async () => {
    const kp = getKind();
    expect(kp.getDefaultAgentName()).toBeNull();
    expect(kp.getLayerPolicies(null)).toBeNull();
    expect(kp.describe(null)).toBeNull();
    expect(kp.promptTemplate()).toBeNull();
  });
});
