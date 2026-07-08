import { describe, it, expect } from "bun:test";
import { DeclarativeKindPort } from "../src/kernel/meta";

function makePort(spec: Record<string, unknown>): DeclarativeKindPort {
  // TypedKindDefinition expects a wrapped doc; reach in via the static
  // factory directly with a hand-built definition object that has the
  // shape DeclarativeKindPort consumes.
  const typedLike = {
    spec: {
      target_kind: spec.target_kind ?? "Meeting",
      target_api_version: spec.target_api_version ?? "user.local/v1",
      alias: spec.alias ?? "user-meeting",
      origin: spec.origin ?? "user.local",
      is_root: false,
      prompt_target: false,
      flatten_in_context: false,
      schema: spec.schema ?? {},
      storage: spec.storage ?? { type: "yaml", container: "meetings" },
      dep_filters: null,
      default_agent: null,
      docs: spec.docs ?? "",
    },
  };
  return new DeclarativeKindPort(typedLike as never);
}

const fakeDoc = (specBody: Record<string, unknown>) => ({
  kind: "Meeting",
  name: "reuniao-geral",
  apiVersion: "user.local/v1",
  spec: specBody,
  metadata: { name: "reuniao-geral" },
}) as never;

describe("DeclarativeKindPort.preview", () => {
  it("returns empty when both schema and spec are empty", async () => {
    const port = makePort({ schema: {} });
    const blocks = port.preview(fakeDoc({}));
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("empty");
  });

  it("renders short string fields as a fields block", async () => {
    const port = makePort({
      schema: {
        type: "object",
        required: ["title"],
        properties: {
          title: { type: "string", title: "Título" },
          location: { type: "string" },
        },
      },
    });
    const blocks = port.preview(
      fakeDoc({ title: "Standup diário", location: "Zoom" }),
    );
    const fields = blocks.find((b) => b.kind === "fields");
    expect(fields).toBeDefined();
    const labels = (fields!.fields ?? []).map((f) => f.label);
    expect(labels).toContain("Título");
    expect(labels).toContain("location");
  });

  it("renders markdown-format strings as standalone markdown blocks", async () => {
    const port = makePort({
      schema: {
        properties: {
          description: { type: "string", format: "markdown", title: "Descrição" },
        },
      },
    });
    const blocks = port.preview(
      fakeDoc({ description: "## Pauta\n\n- Item 1\n- Item 2" }),
    );
    const md = blocks.find((b) => b.kind === "markdown");
    expect(md).toBeDefined();
    expect(md!.title).toBe("Descrição");
    expect(md!.body).toContain("Pauta");
  });

  it("renders array<string> as bullet list inside a fields entry", async () => {
    const port = makePort({
      schema: {
        properties: {
          attendees: {
            type: "array",
            items: { type: "string" },
            title: "Participantes",
          },
        },
      },
    });
    const blocks = port.preview(
      fakeDoc({ attendees: ["alice", "bob", "carol"] }),
    );
    const fields = blocks.find((b) => b.kind === "fields");
    const entry = (fields?.fields ?? []).find((f) => f.label === "Participantes");
    expect(entry?.value).toContain("• alice");
    expect(entry?.value).toContain("• carol");
  });

  it("renders enum + boolean as fields entries", async () => {
    const port = makePort({
      schema: {
        properties: {
          priority: { type: "string", enum: ["baixa", "media", "alta"] },
          done: { type: "boolean" },
        },
      },
    });
    const blocks = port.preview(fakeDoc({ priority: "alta", done: true }));
    const fields = blocks.find((b) => b.kind === "fields");
    const labels = (fields?.fields ?? []).map((f) => f.label);
    expect(labels).toContain("priority");
    expect(labels).toContain("done");
    const done = (fields?.fields ?? []).find((f) => f.label === "done");
    expect(done?.value).toBe("true");
  });

  it("renders nested objects as code blocks", async () => {
    const port = makePort({
      schema: {
        properties: {
          config: { type: "object", title: "Config" },
        },
      },
    });
    const blocks = port.preview(
      fakeDoc({ config: { retries: 3, timeout: 60 } }),
    );
    const code = blocks.find((b) => b.kind === "code");
    expect(code?.title).toBe("Config");
    expect(code?.body).toContain('"retries"');
  });

  it("orders required fields before optional ones", async () => {
    const port = makePort({
      schema: {
        type: "object",
        required: ["title"],
        properties: {
          notes: { type: "string" },
          title: { type: "string" },
        },
      },
    });
    const blocks = port.preview(
      fakeDoc({ title: "Sprint review", notes: "ok" }),
    );
    const fields = blocks.find((b) => b.kind === "fields");
    const labels = (fields?.fields ?? []).map((f) => f.label);
    // title should come before notes because it's required
    expect(labels[0]).toBe("title");
  });
});
