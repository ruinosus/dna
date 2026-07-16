/**
 * DNA → **Amazon Bedrock Agent** emitter (TS twin of python
 * `dna.emit.bedrock`). Materializes an {@link EmitContext} into an AWS
 * **CloudFormation** template that declares an `AWS::Bedrock::Agent` resource —
 * the managed, declarative Bedrock Agents service. The SECOND runtime the SAME
 * DNA source emits to (the first is Microsoft agent-framework): the portability
 * proof — author once, emit per runtime.
 *
 * Why Bedrock **Agents** (not Strands / AgentCore): only Bedrock Agents has a
 * published *declarative* schema (`Instruction`, `FoundationModel`,
 * `ActionGroups` with a `FunctionSchema`) that maps field-for-field from a DNA
 * agent. Emitting a CloudFormation template gives a lintable, deployable artifact
 * that needs no AWS credential to produce or validate structurally.
 *
 * The de-para (DNA field → CloudFormation `AWS::Bedrock::Agent` field):
 *   metadata.name                     -> Resources.<Camel>Agent.Properties.AgentName
 *   metadata.description              -> Properties.Description        (when present)
 *   Soul + guardrails + instruction   -> Properties.Instruction        (flat, BYTE-EQUAL)
 *   spec.model (or Genome default_llm)-> Properties.FoundationModel     (provider token stripped)
 *   spec.tools[] (Tool Kind surfaces) -> Properties.ActionGroups[0].FunctionSchema.Functions[]
 *
 * `toTemplate` is the PURE de-para and is parity-critical: it must build the SAME
 * object the Python `to_template` builds from the same context.
 */
import { EmitResult } from "./index.js";
import type { EmitContext, EmitTool, EmitterPort } from "./index.js";

/** Bedrock `ParameterDetail.Type` allowed values. A JSON-Schema type outside
 *  this set (notably `object`) is coerced to `string` (the depth loss). */
const BEDROCK_PARAM_TYPES = new Set(["string", "number", "integer", "boolean", "array"]);

/** CloudFormation template format version — the stable, only value. */
const CFN_VERSION = "2010-09-09";

/** DNA provider tokens (the `prov:model` / `prov/model` prefixes DNA authors
 *  use). Stripped to expose the bare model id. Bedrock-native provider prefixes
 *  (anthropic./amazon./…) use a DOT and are NOT here, so a real Bedrock id (incl.
 *  a `:0` version suffix) passes through. */
const DNA_PROVIDER_TOKENS = new Set([
  "azure", "azureopenai", "azure_openai", "openai", "foundry", "azureaifoundry",
  "vertex", "google", "gemini",
]);

/** `concierge-grounded` → `ConciergeGrounded` (a valid CFN logical id). */
export function camel(name: string): string {
  return String(name)
    .replace(/_/g, "-")
    .split("-")
    .filter(Boolean)
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join("");
}

/** Project a DNA model coordinate → a Bedrock `FoundationModel` id. Bedrock
 *  encodes the provider inside the id (`anthropic.claude-v2`), so a DNA
 *  `prov:model` / `prov/model` provider token is dropped; a bare coordinate
 *  passes through unchanged. */
export function bedrockModelId(model: string | null): string | null {
  if (!model) return null;
  const ident = model.trim();
  if (ident.toLowerCase().startsWith("arn:")) return ident; // ARN — never split.
  const slash = ident.indexOf("/");
  if (slash >= 0) return ident.slice(slash + 1).trim(); // DNA slash coordinate.
  const colon = ident.indexOf(":");
  if (colon >= 0) {
    const token = ident.slice(0, colon).trim().toLowerCase();
    if (DNA_PROVIDER_TOKENS.has(token)) return ident.slice(colon + 1).trim();
  }
  return ident; // bare / Bedrock-native id (keeps any `:version`).
}

/** Project a Tool's input JSON Schema → Bedrock `Function.Parameters`
 *  (`{name: {Type, Description, Required}}`). Returns the map + whether any type
 *  was coerced (for the loss report). */
export function emitParameters(
  inputSchema: Record<string, unknown>,
): { params: Record<string, unknown>; coerced: boolean } {
  const props = inputSchema?.properties as Record<string, unknown> | undefined;
  if (!props || typeof props !== "object" || Object.keys(props).length === 0) {
    return { params: {}, coerced: false };
  }
  const required = Array.isArray(inputSchema.required) ? (inputSchema.required as string[]) : [];
  const requiredSet = new Set(required);

  const out: Record<string, unknown> = {};
  let coerced = false;
  for (const [pname, raw] of Object.entries(props)) {
    const pschema = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
    const jtype = (pschema.type as string) ?? "string";
    let btype: string;
    if (BEDROCK_PARAM_TYPES.has(jtype)) {
      btype = jtype;
    } else {
      btype = "string"; // object / unknown → flatten to string (recorded loss)
      coerced = true;
    }
    const detail: Record<string, unknown> = { Type: btype };
    if (pschema.description) detail.Description = pschema.description;
    detail.Required = requiredSet.has(pname);
    out[pname] = detail;
  }
  return { params: out, coerced };
}

/** Project the agent's tools → a single Bedrock action group. The executor is
 *  `CustomControl: RETURN_CONTROL` — Bedrock returns the tool call to the CALLER
 *  (the faithful mapping for DNA's client-side tools; no Lambda ARN needed). */
function emitActionGroups(ctx: EmitContext): { groups: Record<string, unknown>[]; coerced: boolean } {
  const functions: Record<string, unknown>[] = [];
  let anyCoerced = false;
  for (const t of ctx.tools) {
    const fn: Record<string, unknown> = { Name: t.name };
    if (t.description) fn.Description = t.description;
    const { params, coerced } = emitParameters((t.parameters ?? {}) as Record<string, unknown>);
    anyCoerced = anyCoerced || coerced;
    if (Object.keys(params).length > 0) fn.Parameters = params;
    functions.push(fn);
  }
  const group = {
    ActionGroupName: `${ctx.name}-actions`,
    Description: `DNA-emitted tools for agent ${ctx.name}`,
    ActionGroupExecutor: { CustomControl: "RETURN_CONTROL" },
    FunctionSchema: { Functions: functions },
  };
  return { groups: [group], coerced: anyCoerced };
}

export class BedrockEmitter implements EmitterPort {
  readonly target = "bedrock";
  readonly fileExtension = "bedrock.json";

  /** The PURE de-para: {@link EmitContext} → the CloudFormation object. Field
   *  order is intentional and preserved by JSON.stringify (insertion order). */
  toTemplate(ctx: EmitContext): Record<string, unknown> {
    const logicalId = `${camel(ctx.name)}Agent`;

    const props: Record<string, unknown> = { AgentName: ctx.name };
    if (ctx.description) props.Description = ctx.description;
    const modelId = bedrockModelId(ctx.model);
    if (modelId) props.FoundationModel = modelId;
    props.Instruction = ctx.instructions; // verbatim — the byte-equal gate
    if (ctx.tools.length > 0) props.ActionGroups = emitActionGroups(ctx).groups;
    props.AutoPrepare = true;

    return {
      AWSTemplateFormatVersion: CFN_VERSION,
      Description: `DNA-emitted Amazon Bedrock Agent: ${ctx.name}`,
      Resources: {
        [logicalId]: { Type: "AWS::Bedrock::Agent", Properties: props },
      },
    };
  }

  emit(ctx: EmitContext): EmitResult {
    const template = this.toTemplate(ctx);
    const artifact = JSON.stringify(template, null, 2) + "\n";

    const losses = [
      "composition structure — Soul reuse + wired Guardrails flatten to one " +
        "`Instruction` string (Bedrock `GuardrailConfiguration` is an " +
        "ID-referenced Bedrock Guardrail, not DNA's composed guardrails)",
      "tenant overlay — a per-tenant persona without a fork has no Bedrock Agent field",
      "eval-as-contract — prompt invariants (EvalCases) have no Bedrock slot",
    ];
    if (ctx.tools.length > 0) {
      losses.push(
        "tool parameter depth — Bedrock `ParameterDetail` is a flat " +
          "{Type, Description, Required} map (Type ∈ string|number|integer|" +
          "boolean|array); JSON-Schema `default`, `enum`, nested object " +
          "`properties`, and array `items` typing are dropped",
      );
    }
    if (ctx.outputSchema) {
      losses.push(
        "output_schema — Bedrock Agent has no structured-response / " +
          "output-schema field; the agent's typed output contract is dropped",
      );
    }
    if (ctx.model === null) {
      losses.push(
        "model unbound in DNA and none supplied — emitted template has no " +
          "`FoundationModel`; pass provider/model or set spec.model / Genome default_llm",
      );
    } else {
      losses.push(
        "model coordinate — a DNA `azure/openai` coordinate is not a Bedrock " +
          "foundation-model id; `FoundationModel` needs a Bedrock model id or " +
          "inference-profile ARN, plus an `AgentResourceRoleArn` at deploy",
      );
    }

    const mapping: Record<string, string> = {
      "metadata.name": "Resources.<id>Agent.Properties.AgentName",
      "metadata.description": "Properties.Description",
      "buildPrompt (Soul+guardrails+instruction)": "Properties.Instruction (byte-equal)",
      "spec.model / Genome.default_llm": "Properties.FoundationModel",
      "spec.tools[] (Tool Kind)": "Properties.ActionGroups[].FunctionSchema.Functions[]",
      "Tool.input_schema.properties": "Function.Parameters{Type,Description,Required}",
    };

    return new EmitResult({
      artifact,
      target: this.target,
      filename: `${ctx.name}.${this.fileExtension}`,
      losses,
      mapping,
    });
  }

  /** Byte-equal invariant hook: read `Properties.Instruction` back from the
   *  emitted CloudFormation template. */
  extractInstructions(artifact: string): string | null {
    const template = JSON.parse(artifact) as { Resources?: Record<string, any> };
    const resources = template.Resources ?? {};
    const first = Object.values(resources)[0] as { Properties?: { Instruction?: unknown } } | undefined;
    const value = first?.Properties?.Instruction;
    return typeof value === "string" ? value : null;
  }
}
