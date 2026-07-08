/**
 * CollabExtension — collaboration primitives (Comment Kind).
 *
 * Registers 1 KindPort:
 *   - Comment (collab-comment) — a remark or status change attached to any document
 *
 * Comments can be attached to any target document via `target_ref`.
 * They enable audit trails, discussions, and status-change history.
 * 1:1 parity with Python.
 */

import type { ExtensionHost, Extension, KindPort } from "../kernel/protocols.js";
import { KindBase } from "../kernel/kind_base.js";
import { SD } from "../kernel/protocols.js";
import type { Document } from "../kernel/document.js";

const API_VERSION = "github.com/ruinosus/dna/collab/v1";

// ---------------------------------------------------------------------------
// CommentKind
// ---------------------------------------------------------------------------

class CommentKind extends KindBase {
  readonly apiVersion = API_VERSION;
  readonly kind = "Comment";
  readonly alias = "collab-comment";
  readonly origin = "github.com/ruinosus/dna/collab";
  readonly isPromptTarget = false;
  readonly promptTargetPriority = 0;
  readonly flattenInContext = false;
  readonly storage = SD.yaml("comments");
  readonly graphStyle = { fill: "#F59E0B", stroke: "#D97706", textColor: "#fff" };
  readonly asciiIcon = "💬";
  readonly displayLabel = "Comments";
  readonly docs = "";

  // Comment can point to ANY kind via target_ref — no typed dep filter
  // because target can be Finding, EvalCase, Agent, etc.
  depFilters() { return {}; }
  schema() {
    return {
      type: "object",
      required: ["target_ref", "author", "body", "type", "created_at"],
      additionalProperties: true,
      properties: {
        target_ref: { type: "string", description: "Kind:name of the target document" },
        author: { type: "string" },
        body: { type: "string" },
        type: {
          type: "string",
          enum: ["note", "status_change", "assignment", "system"],
          default: "note",
        },
        created_at: { type: "string", format: "date-time" },
        // Fields when type=status_change:
        from_status: { type: "string" },
        to_status: { type: "string" },
        // Fields when type=assignment:
        assignee: { type: "string" },
        // Edits/attachments (future):
        edited_at: { type: "string" },
        attachments: { type: "array", items: { type: "string" } },
      },
    };
  }
  summary(doc: Document) {
    const spec = (doc.spec ?? {}) as Record<string, unknown>;
    const body = (spec.body as string) ?? "";
    return {
      target_ref: spec.target_ref ?? "",
      author: spec.author ?? "",
      type: spec.type ?? "note",
      body_preview: body ? body.slice(0, 80) : "",
    };
  }
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

export class CollabExtension implements Extension {
  readonly name = "collab";
  readonly version = "1.0.0";

  register(kernel: ExtensionHost): void {
    kernel.kind(new CommentKind());
  }
}
