/**
 * AutomationExtension — declarative background automation as data.
 *
 * 1:1 parity with Python `dna.extensions.automation`.
 *
 * Registers 1 Kind, from a descriptor (F3 — record Kinds are data, not
 * classes):
 *
 *   - Automation (`dna-automation`) — one doc declares WHEN background
 *     work fires (`on: {type: cron|hook|tool, ...}`) and WHAT runs
 *     (`runner: {kind: agent|tool, ref}` + `agent_directive` / `input` /
 *     result templating / spoken copy / `safety`). Tier A port from the
 *     internal SDK's automation extension (s-tier-a-automation) —
 *     upstream, this Kind unified an async-tool / bus-event / cron trio
 *     and killed hardcoded dispatch: adding or retargeting an automation
 *     is writing one YAML, zero deploy.
 *
 * What travels vs what does not (honest evolution):
 *
 *   - The DECLARATION travels: the Kind (descriptor), write-time
 *     validation (`automation/write-guards.ts`: 5-field cron parse + hook
 *     names against the kernel's typed `KNOWN_HOOK_NAMES` vocabulary) and
 *     the query helpers (`automationsFor` / `triggerKey`) a host executor
 *     reads.
 *   - EXECUTION does not: the SDK has no scheduler, bus or worker. The
 *     host reads Automation docs via the query helpers and runs them —
 *     the same declare-here/execute-in-the-host pattern as the CLI's
 *     `register_post_transition_hook`. The runner contract + a minimal
 *     example live in docs/concepts/builtin-kinds.md.
 *
 * Inheritable ⇒ never TENANTED: Automation is an inheritable `_lib`
 * default (it is in `DEFAULT_INHERITABLE_KINDS_V1`) → tenancy PERMISSIVE
 * (no `tenant_scope` in the descriptor): base writable in `_lib` +
 * per-tenant override via overlay.
 */

import type { ExtensionHost, Extension } from "../kernel/protocols.js";
import { loadDescriptors } from "../kernel/descriptor-loader.js";
import { registerWriteGuards } from "./automation/write-guards.js";

export class AutomationExtension implements Extension {
  name = "automation";
  version = "1.0.0";

  register(kernel: ExtensionHost) {
    // F3: Automation ships as kinds/automation.kind.yaml package data
    // (byte-identical Py↔TS mirror), registered through the SAME funnel as
    // per-scope KindDefinitions (plane lint + digest idempotency + builtin
    // conflict marker).
    for (const raw of loadDescriptors(import.meta.url, "automation/kinds")) {
      kernel.kindFromDescriptor(raw);
    }
    // Write-time semantic validation the JSON Schema cannot express: cron
    // expression parse + hook-name vocabulary (pre_save veto, helix
    // write-guards pattern).
    registerWriteGuards(kernel);
  }
}
